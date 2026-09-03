"""Independent-process JSONL race-reopen proof across graph scenarios."""



from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    GRAPH_SCENARIO_BEHAVIOR,
)


@pytest.mark.parametrize("root", ("direct", "factory", "filesystem", "hermes"))
@pytest.mark.parametrize("scenario", tuple(GRAPH_SCENARIO_BEHAVIOR))
def test_graph_race_reopens_in_an_independent_jsonl_process(
    root: str, scenario: str, tmp_path,
) -> None:
    behavior = GRAPH_SCENARIO_BEHAVIOR[scenario]
    storage_root = tmp_path / scenario / root
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "memorii"
    outputs: list[dict[str, object]] = []
    for phase in ("first", "reopen"):
        output = tmp_path / f"{scenario}-{phase}.json"
        subprocess.run(
            (
                sys.executable,
                "-m",
                "tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner",
                str(storage_root),
                root,
                scenario,
                phase,
                str(output),
            ),
            cwd=Path(__file__).parents[5],
            env=environment,
            check=True,
            timeout=180,
        )
        outputs.append(json.loads(output.read_text(encoding="utf-8")))

    first, reopened = outputs
    if behavior == "scope_revoked":
        assert first["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert first["cas_attempts"] == 1
        assert first["graph_effects"] == 0
    elif behavior in {
        "unrelated_conflict", "normal_success", "lease_renewed", "lease_reclaimed",
        "mixed_version", "rollback",
    }:
        assert first["semantic_ingestion"] == "source_only"
        assert first["cas_attempts"] == 1
        assert first["graph_effects"] == 1
    elif behavior in {
        "durable_retry", "coordinator_removed", "authority_omitted",
        "writer_changed", "writer_unavailable",
    }:
        assert first["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert first["unavailable_calls"] == (1 if behavior == "durable_retry" else 0)
        assert first["graph_effects"] == 0
    elif behavior == "resolved_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["conflict_calls"] == 2
        assert first["graph_effects"] == 1
    elif behavior == "exhausted_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["exhausted_conflict_calls"] == 2
        assert first["graph_effects"] == 1
    elif behavior == "lost_ack":
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 0
        assert first["graph_effects"] == 1
    else:
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 4
        assert first["graph_effects"] == 3
    if behavior == "lost_ack":
        assert first["lost_ack_injected"] is True
    if behavior == "terminal_locator":
        assert first["terminal_locator_removed"] == 1
    if behavior == "terminal_locator":
        assert reopened["semantic_ingestion"] != "source_only"
        assert reopened["scan_calls"] == 0
    elif behavior == "mixed_version":
        assert reopened["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable",
            "source_alignment_authority_unavailable",
        }
    elif behavior == "rollback":
        assert reopened["semantic_ingestion"] == "graph_transaction_authority_unavailable"
        assert reopened["prior_terminal_semantic_ingestion"] == "source_only"
    elif behavior in {"writer_changed", "writer_unavailable"}:
        assert reopened["semantic_ingestion"] in {
            "graph_transaction_authority_unavailable", "source_only",
            "source_alignment_authority_unavailable",
        }
    else:
        assert reopened["semantic_ingestion"] == first["semantic_ingestion"]
    assert reopened["cas_attempts"] == 0
    assert reopened["graph_effects"] == 0
    assert reopened["unavailable_calls"] == 0
    assert reopened["conflict_calls"] == 0
    assert reopened["partial_conflict_calls"] == 0
    assert reopened["exhausted_conflict_calls"] == 0
    if behavior != "rollback":
        assert all(value == 0 for value in reopened["lane_calls"].values())
    if behavior == "mixed_version":
        assert first["mixed_version_fixture_mutations"] > 0
    if behavior in {"reused_committed", "reused_final", "reused_unfinished"}:
        evidence = first["successor_evidence"]
        successor = next(item for item in evidence["attempts"] if item["attempt_index"] == 1)
        assert successor["trigger"] == "related_version_conflict"
        assert evidence["lineages"]
        assert evidence["pre_execution"]
        authorities = successor["authority"]["group_member_authorities"]
        expected_kind = behavior
        assert any(item["kind"] == expected_kind for item in authorities)
        # The retained arm is carried through both the successor lineage and
        # the pre-execution identity closure; it is not a selector alias.
        retained = next(item for item in authorities if item["kind"] == expected_kind)
        retained_group_id = retained["transaction_group_id"]
        latest = dict(evidence["lineages"][-1]["latest_entry_by_group"])
        identities = dict(evidence["pre_execution"][-1]["identity_by_group"])
        assert retained_group_id in latest
        assert retained_group_id in identities


