from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("candidate-manifest-v3.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-candidate-lock", required=True)
    args = parser.parse_args()
    failures: list[str] = []
    if _sha256(MANIFEST) != args.expected_candidate_lock:
        failures.append("candidate_lock_mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tracked = {item["path"]: item for item in manifest["tracked_files"]}
    required = {
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/blocker-remediation-v2.md",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/vcc_exp_005_owner_codec_span_feasibility.py",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/vcc-exp-005-owner-codec-span-feasibility-v1.json",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/build_production_entrypoint_bindings_v3.py",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/production-entrypoint-bindings-v3.json",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/validate_production_entrypoint_bindings_v3.py",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/production-entrypoint-bindings-v3-validation.json",
        "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/validate_candidate_manifest_v3.py",
    }
    if not required.issubset(tracked):
        failures.append("missing_v3_artifact")
    for relative, item in tracked.items():
        path = ROOT / relative
        if not path.is_file() or _sha256(path) != item["sha256"]:
            failures.append(f"tracked_artifact_mismatch:{relative}")
    ledger = json.loads((ROOT / "docs/work/semantic-ingestion-validated-canonical-closure-2026-08-17/production-entrypoint-bindings-v3.json").read_text(encoding="utf-8"))
    if ledger.get("candidate_manifest") != MANIFEST.name:
        failures.append("ledger_candidate_binding_mismatch")
    result = {
        "schema": "memorii.design-candidate-validation.v3",
        "passed": not failures,
        "candidate_lock": args.expected_candidate_lock,
        "tracked_artifact_count": len(tracked),
        "failures": failures,
    }
    print(json.dumps(result, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
