"""Generate the v12 ingress-gated writer-admission production binding map."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "production-entrypoint-bindings-v12.json"
EDGES = (
    ("factory_root", "memorii/memorii/core/provider/factory.py", "ProviderMemoryService("),
    ("hermes_root", "memorii/memorii/integrations/hermes_provider.py", ".sync_event("),
    ("ingress_resolve", "memorii/memorii/core/provider/service.py", "ingress = self._resolve_ingress(authenticated_host_ingress)"),
    ("writer_after_ingress", "memorii/memorii/core/provider/service.py", "if ingress is not None:\n            self._ensure_writer_admission_record()"),
    ("writer_preserve", "memorii/memorii/core/provider/service.py", "self._semantic_writer_admission.current()"),
    ("writer_create", "memorii/memorii/core/provider/service.py", "self._semantic_writer_admission.create_initial_evidence_only("),
)


def main() -> None:
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for _, path, _ in EDGES}
    output = {
        "schema": "memorii.production-entrypoint-bindings.v12",
        "family": "ingress_gated_writer_admission",
        "edges": EDGES,
        "source_hashes": {path: sha256(source.encode()).hexdigest() for path, source in sorted(sources.items())},
        "production_roots": {
            "factory": {"path": "memorii/memorii/core/provider/factory.py", "caller_count": sources["memorii/memorii/core/provider/factory.py"].count("ProviderMemoryService(")},
            "hermes": {"path": "memorii/memorii/integrations/hermes_provider.py", "caller_count": sources["memorii/memorii/integrations/hermes_provider.py"].count(".sync_event(")},
        },
        "durable_outcomes": {
            "absent_or_rejected_ingress": "no writer-admission record is created",
            "resolved_ingress_missing_record": "one existing evidence-only writer-admission record is created",
            "resolved_ingress_existing_record": "current() validates/preserves it; malformed records fail closed",
        },
    }
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
