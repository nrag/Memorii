"""Capture immutable terminal fixtures using an isolated committed checkout."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    sys.path.insert(0, str(checkout / "memorii"))
    import memorii
    from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
    from memorii.core.semantic_ingestion.contracts import encode_semantic_contract
    from tests.unit.core.semantic_ingestion.test_bootstrap_graph_root_composition import (
        test_all_normal_roots_execute_graph_terminal_once,
    )

    if not Path(memorii.__file__).resolve().is_relative_to(checkout):
        raise RuntimeError("historical capture imported the wrong checkout")
    original = SemanticIngestionAtomicStore.persist_bootstrap_graph_terminal_v3
    captured = []

    def capture(store, *, request):
        result = original(store, request=request)
        captured.append((request, result, store._memory_plane.list_records()))
        return result

    SemanticIngestionAtomicStore.persist_bootstrap_graph_terminal_v3 = capture
    with tempfile.TemporaryDirectory(prefix="memorii-historical-terminal-") as scratch:
        test_all_normal_roots_execute_graph_terminal_once("direct", Path(scratch))
    if len(captured) != 1:
        raise RuntimeError("historical fixture did not perform exactly one terminal publication")
    request, reload, records = captured[0]
    args.output.mkdir(parents=True, exist_ok=False)
    payloads = {
        "publication-request.ctv": encode_semantic_contract(request),
        "publication-intent.ctv": encode_semantic_contract(request.publication_intent),
        "terminal-reload.ctv": encode_semantic_contract(reload),
        "memory-records.json": json.dumps(
            [json.loads(record.model_dump_json()) for record in records],
            sort_keys=True, separators=(",", ":"),
        ).encode(),
    }
    manifest = {
        "source_revision": "191826cd3afb38bf605a337a71d576063b3bae5e",
        "source": "isolated git archive; real direct provider sync; synthetic fixture authority",
        "files": [],
    }
    for name, raw in payloads.items():
        packed = gzip.compress(raw, mtime=0)
        (args.output / (name + ".gz")).write_bytes(packed)
        manifest["files"].append({
            "path": name + ".gz", "sha256": sha256(packed).hexdigest(),
            "uncompressed_sha256": sha256(raw).hexdigest(), "uncompressed_bytes": len(raw),
        })
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
