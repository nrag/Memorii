/* Disposable prototype: one SQLite owner and concurrent guarded socket writes. */
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <pthread.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <openssl/sha.h>
#include <sqlite3ext.h>
SQLITE_EXTENSION_INIT1

#define BLOCK_BYTES 65536
#define MAX_IMAGE_BYTES ((sqlite3_int64)8 * 1024 * 1024 * 1024)
#define VFS_NAME "memorii-retained-test"
#define TOKEN_PREFIX "/memorii-retained-test/"
#define TOKEN_HEX_LENGTH 32

static const unsigned char block_domain[] = "memorii.sealed-image-block.v2";
static sqlite3_vfs retained_vfs;
static pthread_mutex_t release_mutex = PTHREAD_MUTEX_INITIALIZER;

typedef struct {
    sqlite3_file base;
    int fd;
} RetainedFile;

/* All SQLite work and these control functions run on one owner thread. */
static struct {
    int pending_fd;
    int opened;
    int failed;
    sqlite3_int64 size;
    sqlite3_int64 blocks;
    sqlite3_int64 reads;
    unsigned char *digests;
    char path[sizeof(TOKEN_PREFIX) + TOKEN_HEX_LENGTH];
} lease = {.pending_fd = -1};

static void put_u64(unsigned char *dst, uint64_t value) {
    for (int i = 7; i >= 0; --i) {
        dst[i] = (unsigned char)(value & 255);
        value >>= 8;
    }
}

static int reject_read(void *output, int amount, int error) {
    pthread_mutex_lock(&release_mutex);
    lease.failed = 1;
    pthread_mutex_unlock(&release_mutex);
    if (amount > 0) memset(output, 0, (size_t)amount);
    return error;
}

/* The caller holds the broker's publication fence. Never block on the socket. */
ssize_t fixture_send_retained(int fd, const void *data, size_t length) {
    pthread_mutex_lock(&release_mutex);
    ssize_t written = -1;
    if (!lease.opened || lease.failed) {
        errno = EACCES;
    } else {
        int flags = MSG_DONTWAIT;
#ifdef MSG_NOSIGNAL
        flags |= MSG_NOSIGNAL;
#endif
        written = send(fd, data, length, flags);
    }
    int saved_errno = errno;
    pthread_mutex_unlock(&release_mutex);
    errno = saved_errno;
    return written;
}

static int read_block(int fd, sqlite3_int64 start, unsigned char *data, size_t size) {
    size_t done = 0;
    while (done < size) {
        ssize_t n = pread(fd, data + done, size - done, (off_t)(start + (sqlite3_int64)done));
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return SQLITE_IOERR_READ;
        done += (size_t)n;
    }
    return SQLITE_OK;
}

static int retained_read(sqlite3_file *file, void *output, int amount, sqlite3_int64 offset) {
    RetainedFile *image = (RetainedFile *)file;
    unsigned char input[sizeof(block_domain) + 8 + BLOCK_BYTES];
    unsigned char digest[SHA256_DIGEST_LENGTH];
    unsigned char *bytes = input + sizeof(block_domain) + 8;
    unsigned char *out = output;
    int remaining = amount;
    ++lease.reads;

    if (lease.failed || amount < 0 || offset < 0 || offset > INT64_MAX - amount) {
        return reject_read(output, amount, SQLITE_IOERR_READ);
    }
    memcpy(input, block_domain, sizeof(block_domain));
    while (remaining > 0 && offset < lease.size) {
        sqlite3_int64 index = offset / BLOCK_BYTES;
        sqlite3_int64 start = index * BLOCK_BYTES;
        sqlite3_int64 available = lease.size - start;
        size_t length = (size_t)(available < BLOCK_BYTES ? available : BLOCK_BYTES);
        size_t skip = (size_t)(offset - start);
        size_t take = length - skip;
        if (take > (size_t)remaining) take = (size_t)remaining;
        if (read_block(image->fd, start, bytes, length) != SQLITE_OK) {
            return reject_read(output, amount, SQLITE_IOERR_READ);
        }
        put_u64(input + sizeof(block_domain), (uint64_t)index);
        if (!SHA256(input, sizeof(block_domain) + 8 + length, digest)
                || memcmp(digest, lease.digests + index * SHA256_DIGEST_LENGTH, sizeof(digest)) != 0) {
            return reject_read(output, amount, SQLITE_IOERR_DATA);
        }
        ++lease.blocks;
        memcpy(out, bytes + skip, take);
        out += take;
        offset += (sqlite3_int64)take;
        remaining -= (int)take;
    }
    if (remaining) {
        memset(out, 0, (size_t)remaining);
        return SQLITE_IOERR_SHORT_READ;
    }
    return SQLITE_OK;
}

static int retained_close(sqlite3_file *file) {
    RetainedFile *image = (RetainedFile *)file;
    pthread_mutex_lock(&release_mutex);
    lease.opened = 0;
    pthread_mutex_unlock(&release_mutex);
    int rc = close(image->fd);
    image->fd = -1;
    sqlite3_free(lease.digests);
    lease.digests = NULL;
    return rc == 0 ? SQLITE_OK : SQLITE_IOERR_CLOSE;
}

static int deny_write(sqlite3_file *file, const void *src, int n, sqlite3_int64 offset) {
    (void)file; (void)src; (void)n; (void)offset;
    return SQLITE_READONLY;
}

static int deny_truncate(sqlite3_file *file, sqlite3_int64 size) {
    (void)file; (void)size;
    return SQLITE_READONLY;
}

static int deny_sync(sqlite3_file *file, int flags) {
    (void)file; (void)flags;
    return SQLITE_READONLY;
}

static int retained_size(sqlite3_file *file, sqlite3_int64 *size) {
    (void)file;
    *size = lease.size;
    return SQLITE_OK;
}

static int retained_lock(sqlite3_file *file, int level) {
    (void)file;
    return level <= SQLITE_LOCK_SHARED ? SQLITE_OK : SQLITE_READONLY;
}

static int retained_unlock(sqlite3_file *file, int level) {
    (void)file; (void)level;
    return SQLITE_OK;
}

static int no_reserved_lock(sqlite3_file *file, int *result) {
    (void)file;
    *result = 0;
    return SQLITE_OK;
}

static int no_file_control(sqlite3_file *file, int op, void *arg) {
    (void)file; (void)op; (void)arg;
    return SQLITE_NOTFOUND;
}

static int sector_size(sqlite3_file *file) {
    (void)file;
    return 4096;
}

static int characteristics(sqlite3_file *file) {
    (void)file;
    return SQLITE_IOCAP_IMMUTABLE;
}

/* Version 1 deliberately supplies neither shared-memory nor mapped reads. */
static const sqlite3_io_methods methods = {
    .iVersion = 1,
    .xClose = retained_close,
    .xRead = retained_read,
    .xWrite = deny_write,
    .xTruncate = deny_truncate,
    .xSync = deny_sync,
    .xFileSize = retained_size,
    .xLock = retained_lock,
    .xUnlock = retained_unlock,
    .xCheckReservedLock = no_reserved_lock,
    .xFileControl = no_file_control,
    .xSectorSize = sector_size,
    .xDeviceCharacteristics = characteristics,
};

static int retained_open(sqlite3_vfs *vfs, const char *name, sqlite3_file *file, int flags, int *out) {
    (void)vfs;
    RetainedFile *image = (RetainedFile *)file;
    image->base.pMethods = NULL;
    if (!name || lease.pending_fd < 0 || lease.opened || lease.failed || strcmp(name, lease.path)
            || !(flags & SQLITE_OPEN_MAIN_DB) || !(flags & SQLITE_OPEN_READONLY)
            || (flags & (SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_DELETEONCLOSE))) {
        return SQLITE_CANTOPEN;
    }
    image->fd = lease.pending_fd;
    lease.pending_fd = -1;
    pthread_mutex_lock(&release_mutex);
    lease.opened = 1;
    pthread_mutex_unlock(&release_mutex);
    image->base.pMethods = &methods;
    if (out) *out = SQLITE_OPEN_READONLY;
    return SQLITE_OK;
}

static int retained_path(sqlite3_vfs *vfs, const char *name, int size, char *out) {
    (void)vfs;
    if (!name || strcmp(name, lease.path) || strlen(name) >= (size_t)size) return SQLITE_CANTOPEN;
    memcpy(out, name, strlen(name) + 1);
    return SQLITE_OK;
}

static int no_path_access(sqlite3_vfs *vfs, const char *name, int flags, int *result) {
    (void)vfs; (void)name; (void)flags;
    *result = 0;
    return SQLITE_OK;
}

static int deny_delete(sqlite3_vfs *vfs, const char *name, int flags) {
    (void)vfs; (void)name; (void)flags;
    return SQLITE_READONLY;
}

static void pin(sqlite3_context *ctx, int argc, sqlite3_value **args) {
    (void)argc;
    sqlite3_int64 size = sqlite3_value_int64(args[1]);
    const char *token = (const char *)sqlite3_value_text(args[3]);
    int fd = sqlite3_value_int(args[0]);
    struct stat info;
    int flags = fcntl(fd, F_GETFL);

    if (lease.pending_fd >= 0 || lease.opened || size <= 0 || size > MAX_IMAGE_BYTES
            || !token || sqlite3_value_bytes(args[3]) != TOKEN_HEX_LENGTH
            || strspn(token, "0123456789abcdef") != TOKEN_HEX_LENGTH
            || flags < 0 || (flags & O_ACCMODE) != O_RDONLY
            || fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) || info.st_size != size
            || sqlite3_value_type(args[2]) != SQLITE_BLOB) {
        sqlite3_result_error(ctx, "invalid retained image pin", -1);
        return;
    }
    size_t digest_bytes = (size_t)((size + BLOCK_BYTES - 1) / BLOCK_BYTES) * SHA256_DIGEST_LENGTH;
    const void *table = sqlite3_value_blob(args[2]);
    if (!table || sqlite3_value_bytes(args[2]) != (int)digest_bytes) {
        sqlite3_result_error(ctx, "invalid retained digest table", -1);
        return;
    }
    unsigned char *digests = sqlite3_malloc64(digest_bytes);
    if (!digests) {
        sqlite3_result_error_nomem(ctx);
        return;
    }
    int duplicate = fcntl(fd, F_DUPFD_CLOEXEC, 0);
    if (duplicate < 0) {
        sqlite3_free(digests);
        sqlite3_result_error(ctx, "cannot duplicate retained descriptor", -1);
        return;
    }
    memcpy(digests, table, digest_bytes);
    lease.digests = digests;
    lease.pending_fd = duplicate;
    lease.size = size;
    pthread_mutex_lock(&release_mutex);
    lease.failed = 0;
    pthread_mutex_unlock(&release_mutex);
    lease.blocks = lease.reads = 0;
    sqlite3_snprintf(sizeof(lease.path), lease.path, "%s%s", TOKEN_PREFIX, token);
    sqlite3_result_text(ctx, lease.path, -1, SQLITE_TRANSIENT);
}

static void drop_pending(sqlite3_context *ctx, int argc, sqlite3_value **args) {
    (void)ctx; (void)argc; (void)args;
    if (lease.pending_fd >= 0) {
        close(lease.pending_fd);
        lease.pending_fd = -1;
        sqlite3_free(lease.digests);
        lease.digests = NULL;
    }
}

static void status(sqlite3_context *ctx, int argc, sqlite3_value **args) {
    (void)argc; (void)args;
    char *result = sqlite3_mprintf("[%d,%lld,%lld]", lease.failed, lease.reads, lease.blocks);
    if (!result) {
        sqlite3_result_error_nomem(ctx);
        return;
    }
    sqlite3_result_text(ctx, result, -1, sqlite3_free);
}

int sqlite3_retainedvfs_init(sqlite3 *db, char **error, const sqlite3_api_routines *api) {
    (void)error;
    SQLITE_EXTENSION_INIT2(api);
    sqlite3_vfs *existing = sqlite3_vfs_find(VFS_NAME);
    sqlite3_vfs *original = sqlite3_vfs_find(NULL);
    if (!original || (existing && existing != &retained_vfs)) return SQLITE_ERROR;

    const struct {
        const char *name;
        int argc;
        void (*call)(sqlite3_context *, int, sqlite3_value **);
    } commands[] = {
        {"fixture_pin", 4, pin},
        {"fixture_drop_pending", 0, drop_pending},
        {"fixture_status", 0, status},
    };
    const int properties = SQLITE_UTF8 | SQLITE_DIRECTONLY;
    int rc = SQLITE_OK;
    size_t installed = 0;
    for (; installed < sizeof(commands) / sizeof(commands[0]); ++installed) {
        rc = sqlite3_create_function(db, commands[installed].name, commands[installed].argc, properties,
                                     NULL, commands[installed].call, NULL, NULL);
        if (rc != SQLITE_OK) break;
    }
    /* Publish process-wide callbacks only after the private control surface works. */
    if (rc == SQLITE_OK && !existing) {
        retained_vfs = *original;
        retained_vfs.iVersion = 1;
        retained_vfs.szOsFile = sizeof(RetainedFile);
        retained_vfs.zName = VFS_NAME;
        retained_vfs.pNext = NULL;
        retained_vfs.xOpen = retained_open;
        retained_vfs.xFullPathname = retained_path;
        retained_vfs.xAccess = no_path_access;
        retained_vfs.xDelete = deny_delete;
        retained_vfs.xDlOpen = NULL;
        retained_vfs.xDlError = NULL;
        retained_vfs.xDlSym = NULL;
        retained_vfs.xDlClose = NULL;
        rc = sqlite3_vfs_register(&retained_vfs, 0);
    }
    if (rc == SQLITE_OK) return SQLITE_OK_LOAD_PERMANENTLY;

    /* Never let the loader unload code still referenced by SQLite. */
    int callbacks_remain = 0;
    while (installed > 0) {
        --installed;
        if (sqlite3_create_function(db, commands[installed].name, commands[installed].argc, properties,
                                    NULL, NULL, NULL, NULL) != SQLITE_OK) {
            callbacks_remain = 1;
        }
    }
    return callbacks_remain ? SQLITE_OK_LOAD_PERMANENTLY : rc;
}
