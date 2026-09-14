# Scoped Memory Context Usage

Scoped context is an opt-in, typed provider read. It does not change
`prefetch`, create an ingestion path, or persist an index. A trusted host owns
the in-process authority, provisions one finite grant, and keeps the returned
opaque handle in that process.

```python
from datetime import UTC, datetime, timedelta

from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.scoped_context.contracts import ScopedContextBudget, ScopedContextRequest, ScopedRecordReference
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.domain.enums import MemoryDomain

now = datetime.now(UTC)
authority = InProcessScopedReadAuthority(now_provider=lambda: datetime.now(UTC))
handle = authority.provision(
    host_task_id="task-42",
    host_state_id="state-9",
    rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, task_id="task-42"),),
    expires_at=now + timedelta(minutes=5),
)
request = ScopedContextRequest(
    host_task_id="task-42",
    host_state_id="state-9",
    declared_complete_mandatory_set=True,
    mandatory_record_references=(ScopedRecordReference(record_id="semantic:constraint", purpose="constraint"),),
    optional_query="deployment constraints",
    optional_domains=(MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC),
    budget=ScopedContextBudget(max_mandatory_items=4, max_optional_items=8, max_optional_omission_ids=4, max_rendered_utf8_bytes=8_192),
    reference_time=now,
)
# The host supplies its canonical memory-plane service when it has one.
provider = build_provider_memory_service_from_env(scoped_read_authority=authority)
activation = provider.retrieve_context(request, opaque_host_ingress=handle)
```

Pass `scoped_read_authority=authority` when constructing the provider through
`build_provider_memory_service_from_env`, `FilesystemStorageBundle`, or
`HermesMemoryProvider`. A missing, forged, expired, revoked, or wrong-label
handle returns `DENIED` with no snapshot revision, record-derived IDs, or
authority receipt. Snapshot backend/decode faults return `UNAVAILABLE`; a
scorer or structured dependency outage preserves successfully resolved
mandatory items and is reported in `omissions`.

The operation resolves authority before its one canonical snapshot read and
revalidates before release. It reads only the captured clone, writes no
canonical records, and builds its lexical index in memory for that request.
Mandatory references span all six domains and fail as a whole on overflow or
unresolved eligibility. Optional material is limited to authorized semantic
and episodic records; item and rendered-byte limits omit whole records and
report a capped omission list.

Handles are opaque and process-local. Do not serialize them, put grants in the
request, use an all-null namespace row without a finite `allowed_record_ids`
set, or use this API as a prefetch fallback. Restarting or recreating the
authority invalidates prior handles. This local composition proof does not
authorize a host deployment, remote retrieval, or a rollout policy.
