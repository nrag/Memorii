"""Regression checks for the one active bootstrap normalization wire grammar."""

from __future__ import annotations

import ast
from pathlib import Path

from memorii.core.semantic_ingestion import contracts


def test_bootstrap_normalization_v3_has_one_active_request_declaration() -> None:
    module = Path(contracts.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module)
    active = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "BootstrapSourceNormalizationAtomicWriteRequestV3"
    ]

    assert len(active) == 1
    assert not hasattr(contracts, "SourceNormalizationAtomicWriteRequestV3")


def test_bootstrap_normalization_stage_uses_the_canonical_request_type() -> None:
    stage_path = Path(contracts.__file__).with_name("source_normalization_stage.py")
    stage = stage_path.read_text(encoding="utf-8")
    names = {
        node.id
        for node in ast.walk(ast.parse(stage))
        if isinstance(node, ast.Name)
    }

    assert "SourceNormalizationAtomicWriteRequestV3" not in names
    assert "BootstrapSourceNormalizationAtomicWriteRequestV3" in names
    assert ".model_construct(" not in stage


def test_bootstrap_normalization_v3_persists_one_exact_native_reduction_core() -> None:
    module = Path(contracts.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module)
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    core = classes["BootstrapNormalizationRequestCoreV3"]
    reduction = classes["BootstrapSemanticReductionAuthorityMemberV3"]
    request = classes["BootstrapSourceNormalizationAtomicWriteRequestV3"]
    assert len([node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == core.name]) == 1
    assert len([node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == reduction.name]) == 1
    request_fields = {
        node.target.id
        for node in request.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert {"normalization_request_core", "semantic_reduction_authority"} <= request_fields
