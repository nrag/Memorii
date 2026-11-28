# Signed Authority At Socket Release

- Operation: implementation
- Fidelity: Level 2 private Linux release-boundary experiment
- Baseline: `65fccb47` of `codex/durable-delivery-implementation`
- Design: [Sealed startup custody](../../design/sealed_startup_custody.md)
- Related evidence: [Storage-owner boundary](owner.plan.md) and [retained worker](worker.plan.md)
- Status: eight Linux socket cases passed. Production transport and native qualification remain open.

## Scope

Extend the credential, signed publication and grant checks through the exact response byte boundary. A synthetic staged v8 fixture is logically verified using the ordinary installed verifier. The isolated service UID pins its physical image through the existing test VFS, verifies its signed tuple against the retained SQLite view, then serves an exact task-bound fixture response to an independently launched kernel-authenticated client UID.

Each bounded nonblocking send takes the same publication fence as fixture authority mutations. Check the grant registry epoch, current credential ID and principal, task and expiration against the bound read grant, and the current signed finalized publication, selector, control journal, trust and suppression coordinates. Check the native integrity latch for the actual send. Credential rotation reuses the existing credential creation and lookup format with one fixture-private index replacement. Tokens travel through private subprocess pipes and the protected local socket. Evidence contains no bearer token or raw fixture bytes.

## Required Evidence

- Unchanged authority delivers the exact complete length-framed BLOB to the real socket client.
- Invalid signature on an otherwise unchanged publication and an authenticated but different control tuple each deny a buffered result before its first byte. The second case deliberately updates only the control tuple, keeping the retained view stale.
- Rotate the credential before first send and during live backpressure. The old credential releases no additional bytes after the authority change. A subsequent request on the replacement credential receives the complete response under the same retained owner.
- Advance the real grant registry epoch during backpressure. Race at a real EAGAIN and record the exact committed offset. The client receives that exact prefix with an incomplete frame after denial.
- Kill the dedicated liveness-pipe holder while a response is parked before send and under backpressure. Resume after the worker observes EOF and closes admissions under the fence. A competing owner fails to take the lock while the view is retained and obtains it after the worker drains and exits.

The separate test controller and listener remain alive after killing the liveness holder. The test orders sends against observed, fenced admission closure. It cannot claim ordering against the exact instant of an unobserved death or prove production supervisor crash recovery. The endpoint serves a fixed synthetic task and does not implement general raw-source authorization or a production transport. Keep v7 default and production sealed startup disabled.

## Results

The [Linux observations](signed-release-linux-container.jsonl) use one fresh logically verified v8 fixture per case. The owner and actual stream client run under distinct UIDs with no effective capabilities. Each complete frame is 180,663 bytes. All eight owners closed their retained view at completion.

| Case | Parked bytes already accepted by the socket | Bytes received by the client | Follow-up |
| --- | ---: | ---: | --- |
| Unchanged authority | — | 180,663 | Complete frame |
| Bad signature, same publication digest | 0 | 0 | Refused |
| Valid signature, different control tuple | 0 | 0 | Refused |
| Credential rotation before first byte | 0 | 0 | Replacement receives 180,663 bytes |
| Credential rotation under backpressure | 8,064 | 8,064 | Replacement receives 180,663 bytes |
| Grant revocation under backpressure | 8,064 | 8,064 | Incomplete frame rejected by the client |
| Liveness holder killed before first byte | 0 | 0 | Lock available after worker exits |
| Liveness holder killed under backpressure | 8,064 | 8,064 | Lock available after worker exits |

Backpressure counts come from successful kernel sends before the fixture pauses on EAGAIN. The client receives exactly that byte prefix and verifies its digest, so eventual denial cannot mask an extra write after the mutation. The two liveness cases verified a contender failed while the owner was paused and reclaimed the lock only after the owner closed its view and exited. Reclaiming the lock in this test is a probe. It does not run a successor publication recovery protocol.

The offline container reused the [cached runtime and native extension build](owner.plan.md#reproduction), mounted current product and support sources read-only, and ran `release_boundary_linux.py supervise /tmp/retainedvfs.so`. Independent test and correctness review confirmed the signature/fence and lifecycle ordering for the bounded proof, and identified the need for an exact parked byte anchor. The final run contains the anchor for every denial. All 16 existing focused macOS tests passed with warnings treated as errors after adding the release hook. Ruff and whitespace checks passed. No production sources, persisted contracts, or default formats changed.

## Next Action

Extend the isolated owner to real writable-transition and installation-inventory erasure paths before production integration.
