"""Offline-only adapter coverage for the certified English parser pair."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from time import sleep

import pytest
from memorii.core.semantic_ingestion.contracts import (
    LinguisticAnalysisRequest,
    SegmentAnalysisInput,
    SegmentLanguageResourceBinding,
    SegmentLanguageRoute,
)
from memorii.core.semantic_ingestion.linguistic_adapters import (
    AnalyzerAssetManifest,
    LinguisticAdapterUnavailable,
    SpacyLinguisticAdapter,
    StanzaLinguisticAdapter,
    _verified_stanza_torch_load_context,
    shipped_analyzer_asset_manifests,
    verify_local_assets,
)
from tests.unit.core.semantic_ingestion.test_source_analysis_contracts import _proposal


class _StanzaWord:
    def __init__(self, start: int, end: int, head: int, deprel: str, lemma: str, upos: str) -> None:
        self.start_char = start
        self.end_char = end
        self.id = start + 1
        self.head = head
        self.deprel = deprel
        self.lemma = lemma
        self.upos = upos
        self.xpos = None
        self.feats = None


class _StanzaDocument:
    def __init__(self) -> None:
        self.sentences = [
            type(
                "Sentence",
                (),
                {"words": [_StanzaWord(0, 5, 2, "nsubj", "alice", "PROPN"), _StanzaWord(6, 11, 0, "root", "work", "VERB")]},
            )()
        ]


class _SpacyToken:
    def __init__(self, index: int, text: str, head_index: int, dep: str, pos: str) -> None:
        self.i = index
        self.idx = 0 if index == 0 else 6
        self.text = text
        self.head = self if head_index == index else None
        self._head_index = head_index
        self.dep_ = dep
        self.lemma_ = text.lower()
        self.pos_ = pos
        self.tag_ = ""
        self.morph = ""


class _SpacyDocument:
    def __init__(self) -> None:
        alice = _SpacyToken(0, "Alice", 1, "nsubj", "PROPN")
        works = _SpacyToken(1, "works", 1, "ROOT", "VERB")
        alice.head = works
        works.head = works
        self.sents = [(alice, works)]


def _request(adapter: StanzaLinguisticAdapter | SpacyLinguisticAdapter) -> LinguisticAnalysisRequest:
    proposal = _proposal()
    route = proposal.language_route
    assert route.resource_binding is not None
    stanza = (
        adapter.manifest
        if adapter.manifest.analyzer_kind == "stanza"
        else StanzaLinguisticAdapter(asset_root=Path("/private/tmp/memorii-stanza-en-1.14.0")).manifest
    )
    spacy = (
        adapter.manifest
        if adapter.manifest.analyzer_kind == "spacy"
        else SpacyLinguisticAdapter(asset_root=Path(".venv/lib/python3.12/site-packages/en_core_web_trf")).manifest
    )
    binding = SegmentLanguageResourceBinding.create(
        selected_language="en",
        proposal_capability_fingerprint=route.resource_binding.proposal_capability_fingerprint,
        stanza_analyzer_manifest_digest=stanza.manifest_digest,
        spacy_analyzer_manifest_digest=spacy.manifest_digest,
        predicate_event_manifest_digest=route.resource_binding.predicate_event_manifest_digest,
        temporal_resolver_manifest_digest=route.resource_binding.temporal_resolver_manifest_digest,
    )
    selected_route = SegmentLanguageRoute.create(
        **(route.model_dump(mode="python", exclude={"route_digest"}) | {"resource_binding": binding})
    )
    segment = SegmentAnalysisInput.create(
        source_id=proposal.source_id,
        source_digest=proposal.source_digest,
        segment_id=proposal.segment_id,
        preparation_fingerprint=proposal.preparation_fingerprint,
        parent_projection_segment_id=selected_route.parent_projection_segment_id,
        segment_governance=proposal.segment_governance,
        message_admission_identity=proposal.message_admission_identity,
        governance_carrier_artifact=proposal.governance_carrier_artifact,
        context_text=proposal.owned_text,
        segment_text="Alice works" + " " * (80 - len("Alice works")),
        language_route=selected_route,
    )
    return LinguisticAnalysisRequest.create(segment=segment, analyzer_manifest=adapter.manifest)


@pytest.mark.parametrize(
    ("adapter_type", "document"),
    [(StanzaLinguisticAdapter, _StanzaDocument()), (SpacyLinguisticAdapter, _SpacyDocument())],
)
def test_adapters_normalize_independent_fake_outputs_without_import_or_network(
    monkeypatch: pytest.MonkeyPatch,
    adapter_type: type[StanzaLinguisticAdapter] | type[SpacyLinguisticAdapter],
    document: object,
) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.linguistic_adapters.verify_local_assets", lambda **_: None
    )
    adapter = adapter_type(asset_root=Path("/not-used"), pipeline_factory=lambda: lambda _: document)
    analysis = adapter.analyze(_request(adapter))
    assert analysis is not None
    assert analysis.status == "complete"
    assert tuple(token.surface_text for token in analysis.tokens) == ("Alice", "works")
    assert analysis.dependencies[0].governor_token_id == analysis.tokens[1].token_id
    assert analysis.dependencies[1].governor_token_id is None


def test_adapter_fails_closed_for_substituted_manifest_or_inexact_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "memorii.core.semantic_ingestion.linguistic_adapters.verify_local_assets", lambda **_: None
    )
    adapter = StanzaLinguisticAdapter(asset_root=Path("/not-used"), pipeline_factory=lambda: lambda _: _StanzaDocument())
    request = _request(adapter)
    assert adapter.analyze(request.model_copy(update={"analyzer_manifest": SpacyLinguisticAdapter(asset_root=Path("/not-used")).manifest})) is None
    inexact = request.model_copy(update={"segment": request.segment.model_copy(update={"segment_text": "short"})})
    assert adapter.analyze(inexact) is None


def test_adapter_classifies_bounded_input_without_invoking_pipeline() -> None:
    adapter = StanzaLinguisticAdapter(
        asset_root=Path("/not-used"),
        pipeline_factory=lambda: (_ for _ in ()).throw(AssertionError()),
        max_segment_characters=4,
    )
    assert adapter.analyze(_request(adapter)) is None
    assert adapter.last_failure_reason == "resource_limit_exceeded"


STANZA_ASSET_ROOT = Path("/private/tmp/memorii-stanza-en-1.14.0")


@pytest.mark.skipif(
    not STANZA_ASSET_ROOT.is_dir(),
    reason="local stanza analyzer assets are provisioned on demand; this "
    "witness runs only where the asset root exists",
)
def test_shipped_manifests_verify_real_local_english_assets() -> None:
    import en_core_web_trf

    manifests = shipped_analyzer_asset_manifests()
    verify_local_assets(
        manifest=manifests["stanza-en-1.14.0"], asset_root=STANZA_ASSET_ROOT
    )
    verify_local_assets(
        manifest=manifests["spacy-en-trf-3.8.0"],
        asset_root=Path(en_core_web_trf.__file__).resolve().parent / "en_core_web_trf-3.8.0",
    )


def test_asset_verifier_rejects_missing_or_tampered_tree(tmp_path: Path) -> None:
    manifest = shipped_analyzer_asset_manifests()["stanza-en-1.14.0"]
    with pytest.raises(LinguisticAdapterUnavailable):
        verify_local_assets(manifest=manifest, asset_root=tmp_path)


def test_changed_asset_never_reaches_pipeline_construction(tmp_path: Path) -> None:
    model = tmp_path / "model.pt"
    model.write_bytes(b"verified-bytes")
    manifest = AnalyzerAssetManifest(
        analyzer_id="stanza-en-1.14.0",
        analyzer_kind="stanza",
        library_version="1.14.0",
        adapter_version="1",
        supported_languages=("en",),
        processor_configuration=("tokenize",),
        files=(("model.pt", "b" * 64),),
        distribution_wheel_sha256="c" * 64,
    )
    adapter = StanzaLinguisticAdapter(asset_root=tmp_path, pipeline_factory=lambda: (_ for _ in ()).throw(AssertionError()))
    object.__setattr__(adapter, "_asset_manifest", manifest)
    object.__setattr__(adapter, "_manifest", manifest.contract())
    request = _request(adapter)
    assert adapter.analyze(request) is None


def _one_file_stanza_manifest(model: Path) -> AnalyzerAssetManifest:
    return AnalyzerAssetManifest(
        analyzer_id="stanza-en-1.14.0",
        analyzer_kind="stanza",
        library_version="1.14.0",
        adapter_version="1",
        supported_languages=("en",),
        processor_configuration=("tokenize",),
        files=((model.name, sha256(model.read_bytes()).hexdigest()),),
        distribution_wheel_sha256="c" * 64,
    )


def test_stanza_torch_compatibility_rehashes_targets_and_restores_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import torch

    model = tmp_path / "model.pt"
    model.write_bytes(b"verified-bytes")
    manifest = _one_file_stanza_manifest(model)
    calls: list[tuple[object, object]] = []

    def original(target: object, *args: object, **kwargs: object) -> object:
        calls.append((target, kwargs.get("weights_only")))
        return "loaded"

    monkeypatch.setattr(torch, "load", original)
    with _verified_stanza_torch_load_context(asset_root=tmp_path, manifest=manifest):
        assert torch.load(model, weights_only=True) == "loaded"
    assert torch.load is original
    assert calls == [(model.resolve(), False)]

    outside = tmp_path.parent / "outside.pt"
    outside.write_bytes(b"outside")
    with _verified_stanza_torch_load_context(asset_root=tmp_path, manifest=manifest):
        with pytest.raises(LinguisticAdapterUnavailable, match="outside"):
            torch.load(outside)
        with pytest.raises(LinguisticAdapterUnavailable, match="filesystem path"):
            torch.load(BytesIO(b"file-like"))
    assert torch.load is original

    model.write_bytes(b"changed")
    with pytest.raises(LinguisticAdapterUnavailable, match="hash mismatch"), _verified_stanza_torch_load_context(
        asset_root=tmp_path, manifest=manifest
    ):
        pass
    assert torch.load is original


def test_stanza_torch_compatibility_serializes_and_restores_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import torch

    model = tmp_path / "model.pt"
    model.write_bytes(b"verified-bytes")
    manifest = _one_file_stanza_manifest(model)
    active = 0
    maximum_active = 0
    state_lock = Lock()

    def original(target: object, *args: object, **kwargs: object) -> object:
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        sleep(0.01)
        with state_lock:
            active -= 1
        raise RuntimeError("loader failure")

    monkeypatch.setattr(torch, "load", original)

    def load_in_thread() -> None:
        with _verified_stanza_torch_load_context(
            asset_root=tmp_path, manifest=manifest
        ), pytest.raises(RuntimeError, match="loader failure"):
            torch.load(model)

    first = Thread(target=load_in_thread)
    second = Thread(target=load_in_thread)
    first.start()
    second.start()
    first.join()
    second.join()
    assert maximum_active == 1
    assert torch.load is original
