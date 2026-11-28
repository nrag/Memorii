# Storage and operator security

Status: verified for this slice. Requirements: SEC-01 and SEC-02.

## Baseline reproduction

Built the wheel offline from the Git archive for
`80fc585228cf0b7d3e59067012f3d6998f34bbf8`. Wheel SHA-256 was
`bd2f67739d50d0994143ea9217e82da68aebe0bb113057ef343ecaf44c9e11d6`.
Imported the installed package outside the checkout on macOS CPython 3.12.16
and from a Linux arm64 Docker container with networking disabled.
With umask 022, called `StorageAdministrationService.initialize()` and
`acquire_verified_snapshot()`. Schema was v8. The installation and partition
were 0755. The database, live WAL and SHM were 0644. In Docker, a process running
with UID/GID 65534 and no supplementary groups could open all three SQLite
files for reading. The probe used a disposable initialized installation.

The baseline storage contract, operator, backup fence, older restore and raw
payload upgrade suites passed on the same archived revision (92 tests).

The installed service creates the control database in its constructor, before
`initialize()`. The operator CLI also constructs a writer registry, whose
constructor can create parent directories. Admission must precede those entry
points and the legacy fresh-root restore copy path. Exact and older restore
select named generations, requiring separate selected-path validation. Backup
and restore staging already use private temporary directories.

## Production entrypoint bindings

| Boundary | Production path and authority | Witness |
| --- | --- | --- |
| Fresh admission | Installed initializer constructs `StorageAdministrationService`, admits the installation and control custody before signing key or SQLite work, then initializes the signed partition. | Installed-wheel before/after probe at umask 022 with live WAL and SHM. |
| Managed reopen and selection | `open_managed_partition` and runtime intake open the service. Verified acquisition selects the authority-matching generation and opens the partition through its protected storage path. | Managed factory and native intake tests, named-generation tests, opened SQLite artifacts. |
| Backup and restore | `memorii-operator` binds `BackupRestoreOperator` using an owner capability and a private wrapping-key file. Staging and generation activation retain signed tuple and authority checks. Legacy fresh-host boot copies into a private root. | Installed operator backup/create/verify/stage and restore recovery tests. |
| Legacy adoption | The approved migration plan and exclusive plane lock authorize adoption by `migrate_legacy_installation`. Legacy bytes remain part of the source authority. | Migration recovery and byte-preservation tests. |
| Diagnostic release | `memorii-operator`, `memorii-consume`, and governance doctor map failures to closed diagnostics before stdout, stderr or log release. | Synthetic markers, rejected former flags, and valid machine-output checks. |

The coordinator reproduced the installed boundary and verified final delivery.
An independent mapper covered constructor order, alternative restore and
migration roots, and retired flag parsing. Specification, correctness and
test reviews covered the changed security boundary. Their findings added
descriptor-relative repair, permission denial without loss of prepared
restore intent, private legacy restore sources, private control migration,
macOS ACL rejection, and adapter resume error redaction. Delta review drove
private backup lifetime locking and custody checks at the backup snapshot open.

## Patched-wheel evidence

The final wheel SHA-256 was
`57ea3c9ca5666ebd252cc5008a13ac5849239d4f19ebb626bf05bc86f2d41ce0`.
On macOS and in Linux arm64 Docker it produced 0700 for the installation
and partition and 0600 for the database, live WAL and SHM. The second Linux
UID was denied access to all three SQLite files. Both installed operators
created and verified a backup using private file arguments, staged and
verified it, activated it, and opened the restored generation. Retired argv
flags and malformed input files kept synthetic markers out of diagnostics.
The installed consumer on both platforms also withheld markers for malformed
legacy intake and a corrupt spool row. Both initializers selected v8.

Ran 170 targeted unit and integration tests with warnings as errors and 30
additional sidecar integration tests with loopback enabled. Ruff, configured
Pyright, and the unit shard inventory passed. The macOS ACL test exercised
an inherited ACL on a mode-0700 directory, refused it before SQLite creation,
then initialized after the test removed the ACL. Node callback probes covered
credential file and malformed response redaction in Pi and OpenClaw. Linux
evidence here uses Docker and establishes permission behavior.

Review disposition for this slice records `remaining_validated_p1_p2: []`.
Use the documented operator-controlled ancestor requirement. Permission
repair does not revoke existing open descriptors. Managed replacement-host
recovery and exact release-candidate qualification remain separate work.

## Private managed storage

Start at `StorageAdministrationService` in
`memorii/memorii/core/storage_administration/service.py` and
`PartitionDataRepository` in `memorii/memorii/stores/sqlite/partition.py`.
Trace creation and opening of the root, partition, SQLite file and WAL, SHM,
journal, backup, restore staging and their temporary material. Reuse existing
private-control creation patterns where they give the same guarantees. Create
private files and directories before writing sensitive bytes. Validate owner,
type, and access at acquisition. Avoid a process-wide umask change and avoid
following links or recursively chmodding paths the operator did not authorize.
Supply a safe diagnosis and explicit repair path for operator-controlled
installations. Previously exposed installations need private replacement
inodes before writes resume. Keep the existing disclosure contract for exports.

Extend `tests/unit/core/test_storage_administration_operator.py` and run
`tests/integration/test_backup_snapshot_fence.py`. Record a clean wheel
initialization under umask 022, a separate Linux UID attempting to read data
and sidecars under a traversable parent, macOS ownership and mode checks,
insecure existing-root denial and safe repair, interrupted initialization and
restore, and linked or replaced inputs. Verify owner access and successful
restart, backup and restore as well as denial.

## Secret input and diagnostics

In `memorii/memorii/tools/runtime_operator.py`, adopt private file input
consistent with restore staging for the backup recovery key and reusable
owner capability. Remove the unused hidden restore-plan key flag and migrate
examples and callers. Check the file at open time, reject unsafe modes and
types, and keep secrets out of argv, child-process arguments, and logs.
Keep valid machine-readable stdout. Use a closed error code and safe context
for malformed secret values, legacy intake or drain failures in
`memorii/memorii/tools/runtime_consume.py`, and doctor output in
`memorii/memorii/core/storage_administration/operator_governance.py`.
Use a module logger for diagnostics and the host logger or UI for adapter
diagnostics. Preserve the scope and privacy of the existing credential pipe.

Drive real CLI subprocesses and host failure paths with synthetic markers
in malformed keys, authority, and source input. Inspect argv, stdout, stderr,
health JSON and captured log records. Require useful closed diagnostics and
absence of marker values in those outputs. Verify success formats and exit
statuses on existing commands. Review the operator input surface and installed
governance boundary independently before closing this milestone.
