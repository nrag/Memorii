import json, sqlite3, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as d:
    path=Path(d)/"current.db"
    c=sqlite3.connect(path)
    c.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE outbox(id TEXT PRIMARY KEY,state TEXT); CREATE TABLE target(id TEXT PRIMARY KEY, status TEXT); CREATE TABLE receipt(id TEXT PRIMARY KEY, digest TEXT); INSERT INTO outbox VALUES('d','delivering');")
    b=sqlite3.connect(Path(d)/"old.db")
    c.backup(b)
    sql=("INSERT INTO target VALUES('d','candidate')","INSERT INTO receipt VALUES('d','digest')","UPDATE outbox SET state='delivered' WHERE id='d'")
    for cut in range(1,4):
        c.execute("BEGIN IMMEDIATE")
        for statement in sql[:cut]: c.execute(statement)
        c.rollback()
        assert c.execute("SELECT state FROM outbox").fetchone()==("delivering",)
        assert c.execute("SELECT count(*) FROM target").fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM receipt").fetchone()==(0,)
    with c:
        for statement in sql: c.execute(statement)
    c.close()
    c=sqlite3.connect(path)
    assert c.execute("SELECT state FROM outbox JOIN receipt USING(id)").fetchone()==("delivered",)
    assert c.execute("SELECT count(*) FROM target").fetchone()==(1,)
    assert b.execute("SELECT count(*) FROM receipt").fetchone()==(0,)
    print(json.dumps({"sqlite":sqlite3.sqlite_version,"rollback_cuts":3,"committed_reopen":True,"older_backup_loses_receipt":True}))
