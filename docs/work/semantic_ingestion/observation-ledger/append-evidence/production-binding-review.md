# Activated Provider Production Candidate

Scope: activated ingestion and durable ledger recovery. Public graph retrieval,
statistical acceptance, operational certification and whole-M5 closure remain
outside this round. No active writer; root freezes production/test/generated
files in production-candidate.json. Reviewers are read-only.

The Spark preflight's capture-tool roots are not ordinary production triggers;
that caller-count claim is unsupported. Coordinator correction from code and
the executed provider regression:

- provider/service.py:699 sync_event -> _ingest_event:776 -> provider ingestion.
- provider/ingestion.py:1502 invokes graph_bundle.execute for ordinary ingestion
  (the other invocation at1358 handles recovery).
- bootstrap_graph_repository.py:413 passes the typed request to atomic group
  commit; :437 passes typed terminal publication to the same atomic owner.
- atomic_store.py:12511 group commit and :10972 source publication construct
  native members and ledger entry/head in one conditional write.
- writer_admission.py:910 selects the snapshot validator registered to the exact
  atomic capability, after current admission/manifest checks. The closed grammar
  binds locator, receipt, delta, head and selected registry publication.
- atomic_store.py:12058 merges proposed/current records into one detached
  snapshot and invokes canonical replay at11981, including immutable native
  and source evidence verification. Missing callbacks fail closed.
- writer_admission.py rechecks lease expiry after expensive validation.

One canonical group port and one terminal port are called by the coordinator;
these are not capture or test-only entry points. The regression invokes the
public provider with fake host/model transport and real registered artifacts,
admission, graph construction and JSONL persistence. It is not installed-wheel
or live-provider acceptance evidence.

Validation at freeze: consolidated regression 279 passed / 1 failed; the one
failure was old admission restart and all four affected route cases subsequently
passed. Terminal fixture update passed3; limit consistency passed2; expiry
guard passed1; registry vectors passed58; Ruff passed. Final compatibility delta,
Pyright and full provider rerun are running. Previous provider run reached four
entries for two sources then failed JSONL reopen because fanout operation IDs
compared Python tuple/list representations. Current candidate compares canonical
JSON content, preserving exact persisted values. Review this correction and
remaining pending evidence explicitly; no milestone approval is claimed.
