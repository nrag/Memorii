# Target Authority Binding Preflight

Read-only mapper: target_binding_map (Spark code-mapper); root reconciled the
existing symbols and constructor calls. Baseline HEAD 191826cd, dirty tree.
This is a construction preflight, not evidence of target reachability.

| Boundary | Existing owner / call | Current target status | Required implementation |
| --- | --- | --- | --- |
| Host composition | ProviderMemoryService.__init__, service.py:476; stores result in _composed_semantic_runtime:497 | No target fields or explicit provider activation method | Add protected capability target input, forward one verified context; explicit host method uses stored runtime |
| Configuration failure | service.py:489 rethrows TypedValueRegistryConfigurationError, then catches general ValueError into absent runtime | A new target error would currently be swallowed unless handled explicitly | Rethrow invalid configured target errors before the fallback catch; absent target alone may preserve legacy composition |
| Built-in owner | capability.py:301 build_semantic_ingestion_runtime; registry verification:332; writer construction:340 | Only registry history shared today | Verify selected target before writer/store creation; supply same context to runtime/writer/store |
| Runtime owner | AuthorizedSemanticIngestionRuntime fields writer_admission, atomic_store, typed_value_registry_history | Target context and explicit host method absent | Enforce shared protected context; derive current writer binding internally, then call atomic owner |
| Writer owner | writer_admission.py:175 SemanticWriterAdmissionStore constructor | Optional registry only; drain/activation unavailable | Retain verified target context and revalidate it with exact predecessor before drain |
| Atomic owner | atomic_store.py:1007 SemanticIngestionAtomicStore; activate_observation_ledger:1129 | Always raises before mutation | Revalidate context; later activation packet supplies actual full-inventory CAS |
| Raw control | typed_value_decoder_sources.py:119 parse_canonical_raw_json_object | Existing bounded strict parser available | Reuse parser with target byte/node/depth caps; apply closed target grammar separately |
| Signature | tools/semantic_ingestion_signature_verifier.py Ed25519SignatureVerifier.verify | Existing profile/key-pair verifier; no target caller | Inject protocol into core; thin release/host adapter composes existing verifier |

Mapper suggestions to search a literal `signatureinterfaces` name or reopen the
approved owner decision were not adopted: that was a conceptual request, and
the target design is already approved. No target function has a production
caller yet. The parent binding JSON must retain that fact until integration.

Nonproduction recipe construction uses Python 3.12.14 and Node v26.7.0. Both
implementations agree on the additional site-locator implementation vector in
target-identity-input.json / target-identity-expected.json. This does not imply
CI Python 3.11 or package/bootstrap parity.
