"""Bounded SQLite mechanism probe, not a Memorii backend or durability certification."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def child(path, phase):
    import os
    db = connect(path)
    db.execute("BEGIN IMMEDIATE")
    db.execute("INSERT INTO batches VALUES (1, 'delivery', 'digest')")
    for kind in ("execution", "solver", "overlay", "directory", "receipt"):
        db.execute("INSERT INTO state VALUES (?, 1)", (kind,))
    if phase == "before_commit":
        os._exit(17)
    db.commit()
    os._exit(18)


def run():
    results = {}
    with tempfile.TemporaryDirectory() as root:
        for phase in ("before_commit", "after_commit"):
            path = str(Path(root) / f"{phase}.sqlite")
            db = connect(path)
            db.executescript("CREATE TABLE batches (seq INTEGER PRIMARY KEY, delivery TEXT UNIQUE, digest TEXT); CREATE TABLE state (kind TEXT PRIMARY KEY, revision INTEGER);")
            db.close()
            proc = subprocess.run([sys.executable, __file__, path, phase], check=False)
            db = connect(path)
            counts = (db.execute("SELECT count(*) FROM batches").fetchone()[0], db.execute("SELECT count(*) FROM state").fetchone()[0])
            assert counts == ((0, 0) if phase == "before_commit" else (1, 5))
            results[phase] = {"exit": proc.returncode, "batches": counts[0], "state_rows": counts[1]}
            if phase == "after_commit":
                assert db.execute("SELECT digest FROM batches WHERE delivery='delivery'").fetchone()[0] == "digest"
                reader = connect(path)
                reader.execute("BEGIN")
                assert reader.execute("SELECT min(revision) FROM state").fetchone()[0] == 1
                db.execute("UPDATE state SET revision=2")
                db.commit()
                assert reader.execute("SELECT max(revision) FROM state").fetchone()[0] == 1
                reader.rollback()
                assert reader.execute("SELECT min(revision) FROM state").fetchone()[0] == 2
                backup = sqlite3.connect(str(Path(root) / "backup.sqlite"))
                db.backup(backup)
                assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert backup.execute("SELECT min(revision) FROM state").fetchone()[0] == 2
                backup.close()
                reader.close()
                results["snapshot_and_backup"] = "passed"
            db.close()
    print(json.dumps({"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version, "results": results, "limits": "Process termination only; not power loss, production schema, authorization, full-root backup, or independent reducer proof."}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 3:
        child(sys.argv[1], sys.argv[2])
    else:
        run()
