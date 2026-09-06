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

REPO_ROOT = Path(__file__).parents[5]
ROOTS = ("direct", "factory", "filesystem", "hermes")


@pytest.fixture(scope="module")
def race_reopen_outputs(
    tmp_path_factory, request: pytest.FixtureRequest,
) -> dict[tuple[str, str, str], dict[str, object]]:
    """One batched interpreter for every collected scenario/root/phase element.

    Each element runs with its own storage root (first/reopen pairs share
    one root) through the same per-element ``run`` the single-element
    mode uses, guarded by the runner's per-element alarm timeout.
    """

    base = tmp_path_factory.mktemp("race_batch")
    selected_pairs: set[tuple[str, str]] = set()
    for item in request.session.items:
        if "race_reopen_outputs" not in item.fixturenames:
            continue
        callspec = getattr(item, "callspec", None)
        params = getattr(callspec, "params", {})
        scenario = params.get("scenario")
        root = params.get("root")
        if isinstance(scenario, str) and isinstance(root, str):
            selected_pairs.add((scenario, root))
    elements = []
    for scenario in GRAPH_SCENARIO_BEHAVIOR:
        for root in ROOTS:
            if (scenario, root) not in selected_pairs:
                continue
            storage_root = base / scenario / root
            for phase in ("first", "reopen"):
                elements.append(
                    {
                        "storage_root": str(storage_root),
                        "root": root,
                        "scenario": scenario,
                        "phase": phase,
                        "output": str(base / "outputs" / f"{scenario}-{root}-{phase}.json"),
                    }
                )
    (base / "outputs").mkdir(parents=True, exist_ok=True)
    manifest = base / "batch-manifest.json"
    manifest.write_text(json.dumps({"elements": elements}), encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "memorii"
    subprocess.run(
        (
            sys.executable,
            "-m",
            "tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner",
            "--batch",
            str(manifest),
        ),
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        timeout=180 * len(elements),
    )
    return {
        (element["scenario"], element["root"], element["phase"]): json.loads(
            Path(element["output"]).read_text(encoding="utf-8")
        )
        for element in elements
    }


def _assert_race_outputs(
    behavior: str,
    first: dict[str, object],
    reopened: dict[str, object],
) -> None:
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
    elif behavior in {"resolved_conflict", "reused_unfinished"}:
        assert first["semantic_ingestion"] == "source_only"
        assert first["conflict_calls"] == 1
        assert first["graph_effects"] == (
            3 if behavior == "reused_unfinished" else 1
        )
    elif behavior == "real_related_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["cas_attempts"] == 3
        assert first["graph_effects"] == 2
        assert first["admission_count"] == 2
    elif behavior == "exhausted_conflict":
        assert first["semantic_ingestion"] == "source_only"
        assert first["exhausted_conflict_calls"] == 2
        assert first["graph_effects"] == 0
    elif behavior == "lost_ack":
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 0
        assert first["graph_effects"] == 1
    else:
        assert first["semantic_ingestion"] == "source_only"
        assert first["partial_conflict_calls"] == 1
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


def _assert_source_progress_evidence(
    scenario: str, first: dict[str, object], reopened: dict[str, object],
) -> None:
    evidence = first["source_progress_evidence"]
    assert isinstance(evidence, list)
    expected = ["plan_published", "attempt_published", "planned"] * (
        3 if scenario == "source_progress_related_conflict" else 1
    )
    assert [item["kind"] for item in evidence] == expected
    for offset in range(0, len(evidence), 3):
        generation = evidence[offset:offset + 3]
        assert len({item["plan_member_payload_digest"] for item in generation}) == 1
        assert len({item["replay_member_payload_digest"] for item in generation}) == 1
        assert all(len(item["progress_digest"]) == 64 for item in generation)
    assert reopened["source_progress_evidence"] == evidence


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("scenario", tuple(GRAPH_SCENARIO_BEHAVIOR))
def test_graph_race_reopens_in_an_independent_jsonl_process(
    root: str,
    scenario: str,
    race_reopen_outputs: dict[tuple[str, str, str], dict[str, object]],
) -> None:
    behavior = GRAPH_SCENARIO_BEHAVIOR[scenario]
    first = race_reopen_outputs[(scenario, root, "first")]
    reopened = race_reopen_outputs[(scenario, root, "reopen")]
    _assert_race_outputs(behavior, first, reopened)
    if scenario.startswith("source_progress_"):
        _assert_source_progress_evidence(scenario, first, reopened)


def test_graph_race_canary_reopens_via_two_independent_subprocesses(
    tmp_path,
) -> None:
    """Permanent canary: one scenario pair stays on the two-subprocess path.

    The batched mode must stay equivalent to genuinely independent
    first/reopen processes; this canary keeps that property continuously
    proven on the real two-interpreter flow.
    """

    scenario = "reused_committed"
    behavior = GRAPH_SCENARIO_BEHAVIOR[scenario]
    storage_root = tmp_path / scenario / "direct"
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
                "direct",
                scenario,
                phase,
                str(output),
            ),
            cwd=REPO_ROOT,
            env=environment,
            check=True,
            timeout=180,
        )
        outputs.append(json.loads(output.read_text(encoding="utf-8")))
    first, reopened = outputs
    _assert_race_outputs(behavior, first, reopened)
