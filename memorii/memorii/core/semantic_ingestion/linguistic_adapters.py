"""Offline, manifest-bound linguistic adapters.

The adapters deliberately know nothing about proposals or graph state.  They
turn one sealed :class:`SegmentAnalysisInput` into the normalized typed parser
evidence contracts, after checking the exact local asset inventory.  Neither
adapter downloads resources or performs an implicit model lookup.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from pickle import UnpicklingError
from threading import Lock
from typing import Any, Literal, Protocol

from memorii.core.semantic_ingestion.contracts import (
    AnalyzerManifest,
    DependencyArc,
    LinguisticAnalysis,
    LinguisticAnalysisRequest,
    LinguisticFeature,
    LinguisticToken,
    ProjectionTextSpan,
    SegmentLocalTextSpan,
    SourceSpanReference,
    contract_digest,
)


class LinguisticAdapterUnavailable(RuntimeError):
    """A selected local analyzer cannot establish its certified inputs."""


class _Pipeline(Protocol):
    def __call__(self, text: str) -> Any: ...


_STANZA_TORCH_LOAD_LOCK = Lock()


@dataclass(frozen=True)
class AnalyzerAssetManifest:
    """One reviewed, path-relative offline resource inventory."""

    analyzer_id: str
    analyzer_kind: Literal["stanza", "spacy"]
    library_version: str
    adapter_version: str
    supported_languages: tuple[str, ...]
    processor_configuration: tuple[str, ...]
    files: tuple[tuple[str, str], ...]
    distribution_wheel_sha256: str

    @property
    def resource_manifest_digest(self) -> str:
        return contract_digest(
            b"memorii.semantic-ingestion.local-analyzer-assets.v1",
            {
                "analyzer_id": self.analyzer_id,
                "analyzer_kind": self.analyzer_kind,
                "library_version": self.library_version,
                "adapter_version": self.adapter_version,
                "supported_languages": self.supported_languages,
                "processor_configuration": self.processor_configuration,
                "files": self.files,
                "distribution_wheel_sha256": self.distribution_wheel_sha256,
            },
        )

    def contract(self) -> AnalyzerManifest:
        file_hashes = tuple(digest for _, digest in self.files)
        processor_digest = contract_digest(
            b"memorii.semantic-ingestion.local-analyzer-processors.v1",
            {"processors": self.processor_configuration},
        )
        fingerprint = contract_digest(
            b"memorii.semantic-ingestion.local-analyzer-fingerprint.v2",
            {
                "resource_manifest_digest": self.resource_manifest_digest,
                "processor_configuration_digest": processor_digest,
                "distribution_wheel_sha256": self.distribution_wheel_sha256,
            },
        )
        return AnalyzerManifest.create(
            analyzer_id=self.analyzer_id,
            analyzer_kind=self.analyzer_kind,
            library_version=self.library_version,
            resource_manifest_digest=self.resource_manifest_digest,
            model_file_hashes=file_hashes,
            processor_configuration_digest=processor_digest,
            adapter_version=self.adapter_version,
            supported_languages=self.supported_languages,
            analyzer_fingerprint=fingerprint,
        )


def shipped_analyzer_asset_manifests() -> dict[str, AnalyzerAssetManifest]:
    """Load the package-owned reviewed inventory without contacting a registry."""

    resource = files("memorii.core.semantic_ingestion").joinpath(
        "resources/english_linguistic_analyzers.v1.json"
    )
    payload = json.loads(resource.read_text(encoding="ascii"))
    if payload.get("schema") != "memorii.semantic-ingestion.local-analyzer-assets.v1":
        raise LinguisticAdapterUnavailable("local analyzer asset manifest schema is unsupported")
    manifests: dict[str, AnalyzerAssetManifest] = {}
    for raw in payload.get("analyzers", []):
        files_value = tuple((str(item["path"]), str(item["sha256"])) for item in raw["files"])
        if not files_value or tuple(sorted(path for path, _ in files_value)) != tuple(path for path, _ in files_value):
            raise LinguisticAdapterUnavailable("local analyzer asset manifest paths are not canonical")
        if any(len(digest) != 64 for _, digest in files_value):
            raise LinguisticAdapterUnavailable("local analyzer asset manifest contains invalid hash")
        manifest = AnalyzerAssetManifest(
            analyzer_id=str(raw["analyzer_id"]),
            analyzer_kind=raw["analyzer_kind"],
            library_version=str(raw["library_version"]),
            adapter_version=str(raw["adapter_version"]),
            supported_languages=tuple(raw["supported_languages"]),
            processor_configuration=tuple(raw["processor_configuration"]),
            files=files_value,
            distribution_wheel_sha256=str(raw["distribution_wheel_sha256"]),
        )
        if manifest.analyzer_id in manifests:
            raise LinguisticAdapterUnavailable("local analyzer asset manifest duplicates analyzer id")
        manifests[manifest.analyzer_id] = manifest
    if set(manifests) != {"stanza-en-1.14.0", "spacy-en-trf-3.8.0"}:
        raise LinguisticAdapterUnavailable("local analyzer asset manifest has an incomplete analyzer pair")
    return manifests


def verify_local_assets(*, manifest: AnalyzerAssetManifest, asset_root: Path) -> None:
    """Verify every required runtime model byte before importing a library.

    The root is supplied by composition.  It is never inferred from a network
    cache or a library default path, which keeps model provenance explicit.
    """

    try:
        root = asset_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise LinguisticAdapterUnavailable("local analyzer asset root is missing") from exc
    if root.is_symlink() or not root.is_dir():
        raise LinguisticAdapterUnavailable("local analyzer asset root is not a real directory")
    for relative_path, expected_digest in manifest.files:
        candidate = root.joinpath(relative_path)
        if candidate.is_symlink() or not candidate.is_file():
            raise LinguisticAdapterUnavailable("local analyzer asset is missing or symlinked")
        if root not in candidate.resolve().parents:
            raise LinguisticAdapterUnavailable("local analyzer asset escaped its root")
        with candidate.open("rb") as handle:
            actual_digest = sha256(handle.read()).hexdigest()
        if actual_digest != expected_digest:
            raise LinguisticAdapterUnavailable("local analyzer asset hash mismatch")


@contextmanager
def _verified_stanza_torch_load_context(
    *, asset_root: Path, manifest: AnalyzerAssetManifest
) -> Any:
    """Allow Stanza's reviewed serialized models only while it constructs.

    Torch 2.2 has no scoped safe-globals API, while Stanza 1.14.0 loads the
    verified English model with ``weights_only=True``. Full pickle is allowed
    only for the exact byte-verified model named by this manifest: every load
    target stays beneath the verified root, is immediately rehashed, and the
    temporary process-global wrapper is serialized and restored in ``finally``.
    """

    if manifest.analyzer_kind != "stanza":
        raise LinguisticAdapterUnavailable("Torch compatibility is only valid for Stanza assets")
    verify_local_assets(manifest=manifest, asset_root=asset_root)
    root = asset_root.resolve(strict=True)
    expected = dict(manifest.files)
    try:
        import torch
    except ImportError as exc:
        raise LinguisticAdapterUnavailable("Stanza requires the pinned local Torch runtime") from exc
    with _STANZA_TORCH_LOAD_LOCK:
        original_load = torch.load

        def verified_load(target: object, *args: object, **kwargs: object) -> object:
            if not isinstance(target, (str, Path)):
                raise LinguisticAdapterUnavailable("Stanza model load requires a verified filesystem path")
            try:
                path = Path(target).resolve(strict=True)
                relative = path.relative_to(root).as_posix()
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                raise LinguisticAdapterUnavailable("Stanza model load target is outside the verified asset root") from exc
            expected_digest = expected.get(relative)
            if expected_digest is None or path.is_symlink() or not path.is_file():
                raise LinguisticAdapterUnavailable("Stanza model load target is not a declared verified asset")
            with path.open("rb") as handle:
                if sha256(handle.read()).hexdigest() != expected_digest:
                    raise LinguisticAdapterUnavailable("Stanza model changed after asset verification")
            options = dict(kwargs)
            options["weights_only"] = False
            return original_load(path, *args, **options)

        torch.load = verified_load
        try:
            yield
        finally:
            torch.load = original_load


class _BaseAdapter:
    def __init__(
        self,
        *,
        manifest: AnalyzerAssetManifest,
        asset_root: Path,
        pipeline_factory: Callable[[], _Pipeline] | None = None,
        max_segment_characters: int = 4096,
    ) -> None:
        if max_segment_characters <= 0:
            raise ValueError("local analyzer segment limit must be positive")
        self._asset_manifest = manifest
        self._manifest = manifest.contract()
        self._asset_root = asset_root
        self._pipeline_factory = pipeline_factory
        self._pipeline: _Pipeline | None = None
        self._max_segment_characters = max_segment_characters
        self._last_failure_reason: str | None = None

    @property
    def manifest(self) -> AnalyzerManifest:
        return self._manifest

    @property
    def last_failure_reason(self) -> str | None:
        """Non-authoritative local diagnostic; callers still receive no analysis."""

        return self._last_failure_reason

    def analyze(self, request: LinguisticAnalysisRequest) -> LinguisticAnalysis | None:
        self._last_failure_reason = None
        if request.analyzer_manifest != self._manifest:
            self._last_failure_reason = "manifest_mismatch"
            return None
        if request.segment.language_route.selected_language not in self._manifest.supported_languages:
            self._last_failure_reason = "unsupported_language"
            return None
        if len(request.segment.segment_text) > self._max_segment_characters:
            self._last_failure_reason = "resource_limit_exceeded"
            return None
        try:
            verify_local_assets(manifest=self._asset_manifest, asset_root=self._asset_root)
            pipeline = self._pipeline or self._build_pipeline()
            self._pipeline = pipeline
            return self._normalize(request=request, document=pipeline(request.segment.segment_text))
        except MemoryError:
            self._last_failure_reason = "resource_exhausted"
            return None
        except TimeoutError:
            self._last_failure_reason = "analysis_timeout"
            return None
        except (ImportError, OSError, RuntimeError, TypeError, ValueError, AttributeError, UnpicklingError):
            self._last_failure_reason = "analyzer_unavailable"
            return None

    def _build_pipeline(self) -> _Pipeline:
        if self._pipeline_factory is None:
            raise NotImplementedError
        return self._pipeline_factory()

    def _normalize(self, *, request: LinguisticAnalysisRequest, document: Any) -> LinguisticAnalysis:
        raise NotImplementedError

    def _span(self, *, request: LinguisticAnalysisRequest, start: int, end: int) -> SourceSpanReference:
        context = request.segment.context_text
        width = context.segment_local_span.end - context.segment_local_span.start
        if len(request.segment.segment_text) != width or not 0 <= start < end <= width:
            raise LinguisticAdapterUnavailable("analysis input lacks one exact segment coordinate")
        text = request.segment.segment_text[start:end]
        digest = sha256(text.encode("utf-8")).hexdigest()
        return SourceSpanReference.create(
            source_id=request.segment.source_id,
            projection_digest=context.projection_digest,
            projection_segment_id=context.projection_segment_id,
            retained_text_artifact=context.retained_text_artifact,
            projection_span=ProjectionTextSpan.create(
                artifact=context.projection_span.artifact,
                start=context.projection_span.start + start,
                end=context.projection_span.start + end,
                substring_digest=digest,
            ),
            segment_local_span=SegmentLocalTextSpan.create(
                artifact=context.segment_local_span.artifact,
                start=context.segment_local_span.start + start,
                end=context.segment_local_span.start + end,
                substring_digest=digest,
            ),
            text_mapping_proof=context.text_mapping_proof,
            source_reference=context.source_reference,
        )

    def _analysis(
        self,
        *,
        request: LinguisticAnalysisRequest,
        tokens: tuple[LinguisticToken, ...],
        dependencies: tuple[DependencyArc, ...],
    ) -> LinguisticAnalysis:
        return LinguisticAnalysis.create(
            source_id=request.segment.source_id,
            source_digest=request.segment.source_digest,
            preparation_fingerprint=request.segment.preparation_fingerprint,
            segment_id=request.segment.segment_id,
            segment_language_route_digest=request.segment.language_route.route_digest,
            analyzer_manifest_digest=self._manifest.manifest_digest,
            analyzer_fingerprint=self._manifest.analyzer_fingerprint,
            language=request.segment.language_route.selected_language,
            tokens=tokens,
            mentions=(),
            clauses=(),
            dependencies=dependencies,
            status="complete",
            diagnostics=(),
        )


class StanzaLinguisticAdapter(_BaseAdapter):
    """Primary offline Stanza adapter with an explicit no-download pipeline."""

    def __init__(
        self,
        *,
        asset_root: Path,
        pipeline_factory: Callable[[], _Pipeline] | None = None,
        max_segment_characters: int = 4096,
    ) -> None:
        super().__init__(
            manifest=shipped_analyzer_asset_manifests()["stanza-en-1.14.0"],
            asset_root=asset_root,
            pipeline_factory=pipeline_factory,
            max_segment_characters=max_segment_characters,
        )

    def _build_pipeline(self) -> _Pipeline:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()
        import stanza

        with _verified_stanza_torch_load_context(
            asset_root=self._asset_root, manifest=self._asset_manifest
        ):
            return stanza.Pipeline(
                lang="en",
                processors="tokenize,mwt,pos,lemma,depparse",
                dir=str(self._asset_root),
                download_method=None,
                use_gpu=False,
                verbose=False,
            )

    def _normalize(self, *, request: LinguisticAnalysisRequest, document: Any) -> LinguisticAnalysis:
        rows: list[tuple[Any, int, int]] = []
        for sentence_index, sentence in enumerate(document.sentences):
            for word_index, word in enumerate(sentence.words):
                if word.start_char is None or word.end_char is None or word.id is None:
                    raise LinguisticAdapterUnavailable("Stanza emitted a token without exact character offsets")
                rows.append((word, sentence_index, word_index))
        return self._normalize_rows(request=request, rows=rows, head=lambda word: int(word.head), relation=lambda word: str(word.deprel))

    def _normalize_rows(
        self,
        *,
        request: LinguisticAnalysisRequest,
        rows: list[tuple[Any, int, int]],
        head: Callable[[Any], int],
        relation: Callable[[Any], str],
    ) -> LinguisticAnalysis:
        if not rows:
            raise LinguisticAdapterUnavailable("analyzer produced no syntactic tokens")
        tokens: list[LinguisticToken] = []
        token_by_sentence_word: dict[tuple[int, int], LinguisticToken] = {}
        for word, sentence_index, word_index in rows:
            start, end = int(word.start_char), int(word.end_char)
            features = _features(getattr(word, "feats", None))
            token = LinguisticToken.create(
                source_span=self._span(request=request, start=start, end=end),
                surface_text=request.segment.segment_text[start:end],
                lemma=str(getattr(word, "lemma", "") or request.segment.segment_text[start:end]).lower(),
                upos=str(getattr(word, "upos", "X") or "X"),
                xpos=_none_or_string(getattr(word, "xpos", None)),
                morphological_features=features,
                sentence_index=sentence_index,
                word_index=word_index,
                syntactic_word_index=word_index,
                multi_word_token_span=None,
            )
            tokens.append(token)
            token_by_sentence_word[(sentence_index, word_index + 1)] = token
        # The typed contract intentionally admits one rooted dependency tree.
        # A multi-sentence source must be routed as separate analysis segments.
        if len({sentence for _, sentence, _ in rows}) != 1:
            raise LinguisticAdapterUnavailable("analyzer segment has multiple dependency roots")
        arcs: list[DependencyArc] = []
        for (word, sentence_index, _), token in zip(rows, tokens, strict=True):
            raw_head = head(word)
            governor = None if raw_head == 0 else token_by_sentence_word.get((sentence_index, raw_head))
            if raw_head != 0 and governor is None:
                raise LinguisticAdapterUnavailable("analyzer dependency head is outside its segment")
            arcs.append(
                DependencyArc.create(
                    dependent_token_id=token.token_id,
                    governor_token_id=None if governor is None else governor.token_id,
                    relation="root" if governor is None else relation(word),
                    enhanced=False,
                )
            )
        return self._analysis(
            request=request,
            tokens=tuple(tokens),
            dependencies=tuple(arcs),
        )


class SpacyLinguisticAdapter(StanzaLinguisticAdapter):
    """Independent spaCy corroboration adapter with the same output contract."""

    def __init__(
        self,
        *,
        asset_root: Path,
        pipeline_factory: Callable[[], _Pipeline] | None = None,
        max_segment_characters: int = 4096,
    ) -> None:
        _BaseAdapter.__init__(
            self,
            manifest=shipped_analyzer_asset_manifests()["spacy-en-trf-3.8.0"],
            asset_root=asset_root,
            pipeline_factory=pipeline_factory,
            max_segment_characters=max_segment_characters,
        )

    def _build_pipeline(self) -> _Pipeline:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()
        import spacy

        return spacy.load(str(self._asset_root), exclude=[])

    def _normalize(self, *, request: LinguisticAnalysisRequest, document: Any) -> LinguisticAnalysis:
        rows: list[tuple[Any, int, int]] = []
        for sentence_index, sentence in enumerate(document.sents):
            for word_index, token in enumerate(sentence):
                rows.append((_SpacyWord(token), sentence_index, word_index))
        return self._normalize_rows(
            request=request,
            rows=rows,
            head=lambda word: word.head_index,
            relation=lambda word: word.deprel,
        )


class _SpacyWord:
    """Minimal normalized view that keeps spaCy-specific objects out of helpers."""

    def __init__(self, token: Any) -> None:
        self.start_char = token.idx
        self.end_char = token.idx + len(token.text)
        self.id = token.i + 1
        self.head_index = 0 if token.head.i == token.i else token.head.i + 1
        self.deprel = token.dep_
        self.lemma = token.lemma_
        self.upos = token.pos_
        self.xpos = token.tag_ or None
        self.feats = str(token.morph)


def _none_or_string(value: object) -> str | None:
    return None if value in (None, "", "_") else str(value)


def _features(value: object) -> tuple[LinguisticFeature, ...]:
    if not value or value == "_":
        return ()
    entries: list[LinguisticFeature] = []
    for item in str(value).split("|"):
        if "=" not in item:
            continue
        name, raw_value = item.split("=", 1)
        entries.append(LinguisticFeature.create(name=name, value=raw_value))
    if len({item.name for item in entries}) != len(entries):
        raise LinguisticAdapterUnavailable("analyzer emitted duplicate morphological feature")
    return tuple(sorted(entries, key=lambda item: (item.name, item.value, item.feature_digest)))


__all__ = [
    "AnalyzerAssetManifest",
    "LinguisticAdapterUnavailable",
    "SpacyLinguisticAdapter",
    "StanzaLinguisticAdapter",
    "shipped_analyzer_asset_manifests",
    "verify_local_assets",
]
