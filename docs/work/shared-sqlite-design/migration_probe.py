"""Bounded mechanism probe, not a production SQLite backend or migrator."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        legacy = JsonlMemoryPlaneStore(root / 'legacy')
        for ident, text, visibility in (
            ('fact-a', 'first', MemoryRecordVisibility.RUNTIME_CONTEXT),
            ('catalog-control', 'inert', MemoryRecordVisibility.INTERNAL_CONTROL),
            ('fact-a', 'second', MemoryRecordVisibility.RUNTIME_CONTEXT),
        ):
            legacy.write_records((CanonicalMemoryRecord(
                memory_id=ident, domain=MemoryDomain.SEMANTIC,
                text=text, status=CommitStatus.CANDIDATE, visibility=visibility,
            ),))
        source = root / 'legacy' / 'memory_records.jsonl'
        original = source.read_bytes()
        database = sqlite3.connect(root / 'data.sqlite')
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('PRAGMA synchronous=FULL')
        database.executescript('''
            CREATE TABLE batches(revision INTEGER PRIMARY KEY, data_revision INTEGER, original BLOB);
            CREATE TABLE current_records(id TEXT PRIMARY KEY, payload TEXT, ordinal INTEGER);
            CREATE TABLE runtime_receipts(id TEXT PRIMARY KEY);
        ''')
        with database:
            ordinal = 0
            for raw in original.splitlines(keepends=True):
                batch = json.loads(raw)
                database.execute('INSERT INTO batches VALUES(?,?,?)',
                                 (batch['revision'], batch['data_revision'], raw))
                for record in batch['records']:
                    payload = json.dumps(record, sort_keys=True)
                    database.execute('''INSERT INTO current_records VALUES(?,?,?)
                        ON CONFLICT(id) DO UPDATE SET payload=excluded.payload''',
                        (record['memory_id'], payload, ordinal))
                    ordinal += 1
        recovered = b''.join(row[0] for row in database.execute('SELECT original FROM batches ORDER BY revision'))
        assert recovered == original
        restored = tuple(CanonicalMemoryRecord.model_validate_json(row[0]) for row in
                         database.execute('SELECT payload FROM current_records ORDER BY ordinal'))
        data_revision, records = legacy.read_snapshot()
        write_revision, _ = legacy.read_write_snapshot()
        assert restored == records
        assert (write_revision, data_revision) == (3, 2)
        assert database.execute('SELECT revision,data_revision FROM batches ORDER BY revision DESC LIMIT 1').fetchone() == (3, 2)
        try:
            with database:
                database.execute("UPDATE current_records SET payload='corrupt' WHERE id='fact-a'")
                database.execute("INSERT INTO runtime_receipts VALUES('operation-a')")
                raise RuntimeError('induced before commit')
        except RuntimeError:
            pass
        assert not database.execute('SELECT * FROM runtime_receipts').fetchall()
        assert CanonicalMemoryRecord.model_validate_json(database.execute(
            "SELECT payload FROM current_records WHERE id='fact-a'").fetchone()[0]).text == 'second'
        with database:
            database.execute("INSERT INTO runtime_receipts VALUES('operation-a')")
        database.close()
        database = sqlite3.connect(root / 'data.sqlite')
        assert database.execute('SELECT * FROM runtime_receipts').fetchall() == [('operation-a',)]
        assert source.read_bytes() == original
        assert database.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        print(json.dumps({'original_batch_bytes_preserved': True, 'latest_records_equal': True,
                          'write_revision': write_revision, 'data_revision': data_revision,
                          'coupled_transaction_rollback': True, 'reopen_receipt': True,
                          'legacy_source_unchanged': True, 'sqlite': sqlite3.sqlite_version,
                          'source_digest': hashlib.sha256(original).hexdigest()}))

if __name__ == '__main__':
    main()
