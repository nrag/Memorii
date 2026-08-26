"""Generate v13 construction-safe writer-admission bindings."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "production-entrypoint-bindings-v13.json"
EDGES = (
    ("service_resolve", "memorii/memorii/core/provider/service.py", "ingress = self._resolve_ingress(authenticated_host_ingress)"),
    ("service_gate", "memorii/memorii/core/provider/service.py", "if ingress is not None:\n            self._ensure_writer_admission_record()"),
    ("capability_deferred", "memorii/memorii/core/semantic_ingestion/capability.py", "writers = SemanticWriterAdmissionStore("),
    ("factory", "memorii/memorii/core/provider/factory.py", "ProviderMemoryService("),
    ("hermes", "memorii/memorii/integrations/hermes_provider.py", "authenticated_host_ingress=authenticated_host_ingress"),
    ("filesystem", "memorii/memorii/core/filesystem_storage/bundle.py", "build_provider_memory_service_from_env("),
)
def main() -> None:
    sources = {path: (ROOT / path).read_text() for _, path, _ in EDGES}
    payload = {"schema": "memorii.production-entrypoint-bindings.v13", "edges": EDGES, "source_hashes": {p: sha256(s.encode()).hexdigest() for p, s in sources.items()}, "caller_counts": {"factory": sources["memorii/memorii/core/provider/factory.py"].count("ProviderMemoryService("), "hermes": sources["memorii/memorii/integrations/hermes_provider.py"].count("authenticated_host_ingress=authenticated_host_ingress"), "filesystem": sources["memorii/memorii/core/filesystem_storage/bundle.py"].count("build_provider_memory_service_from_env(")}, "behavioral_evidence": "test_builtin_local_capability_wires_provider_hermes_and_filesystem_without_entrypoint_patch; writer ingress matrix"}
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
if __name__ == "__main__":
    main()
