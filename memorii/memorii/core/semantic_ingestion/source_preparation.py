"""Producer-owned Step-2 prepared-source authority.

The pipeline deliberately never accepts a prepared source supplied by its
caller.  Step 2 produces an immutable authority and publishes it to this
repository; consumers load and revalidate that exact authority by source
identity before any learned work begins.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from hashlib import sha256
from threading import RLock
from typing import Protocol

from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapSegmentGrammarProof,
    VerifiedBootstrapProfile,
    classify_bootstrap_input,
)
from memorii.core.memory_evolution.semantic_analysis.source_contracts import (
    BootstrapDeclaredSegmentLanguageRoute,
    PreparedSegment,
    PreparedSource,
    SegmentLanguageRouteSet,
    TextPreparationRequest,
)
from memorii.core.semantic_ingestion.contracts import (
    ProjectionTextSpan,
    SegmentLocalTextSpan,
    SourceSpanReference,
    contract_digest,
)


class PreparedSourceRepository(Protocol):
    """Atomic publication/read boundary owned by the ingestion coordinator."""

    def publish(self, prepared: PreparedSource) -> PreparedSource: ...

    def load(self, *, source_id: str, source_digest: str) -> PreparedSource | None: ...


class InMemoryPreparedSourceRepository:
    """Deterministic repository implementation for a coordinator lifetime.

    Production composition must provide a durable coordinator-owned adapter;
    this implementation is intentionally useful only where the coordinator's
    lifetime is itself the persistence boundary (for example tests).
    """

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], PreparedSource] = {}
        self._lock = RLock()

    def publish(self, prepared: PreparedSource) -> PreparedSource:
        value = PreparedSource.model_validate(prepared.model_dump(mode="python"))
        key = (value.source_id, value.source_digest)
        with self._lock:
            existing = self._values.get(key)
            if existing is not None and existing != value:
                raise ValueError("prepared source publication conflicts with retained authority")
            self._values[key] = value
        return value

    def load(self, *, source_id: str, source_digest: str) -> PreparedSource | None:
        with self._lock:
            value = self._values.get((source_id, source_digest))
        if value is None:
            return None
        try:
            return PreparedSource.model_validate(value.model_dump(mode="python"))
        except ValueError as exc:
            raise ValueError("published prepared source is invalid") from exc


class AtomicStorePreparedSourceRepository:
    """Durable Step-2 repository backed exclusively by the transaction owner."""

    def __init__(self, *, atomic_store: object, writer_binding: Callable[[], object]) -> None:
        self._atomic_store = atomic_store
        self._writer_binding = writer_binding

    def publish(self, prepared: PreparedSource) -> PreparedSource:
        published = self._atomic_store.publish_prepared_source(
            prepared, writer_binding=self._writer_binding()
        )
        return PreparedSource.model_validate(published.model_dump(mode="python"))

    def load(self, *, source_id: str, source_digest: str) -> PreparedSource | None:
        value = self._atomic_store.load_prepared_source(
            source_id=source_id, source_digest=source_digest
        )
        if value is None:
            return None
        return PreparedSource.model_validate(value.model_dump(mode="python"))


class BootstrapTextPreparationProducer:
    """Produce the frozen local-English prepared authority from verified V1 bytes.

    This is deliberately neither a language detector nor a generic route
    selector.  The only selectable route is the exact host-declared English
    grammar form embedded in the already verified profile.
    """

    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?=\s|$)")
    _TOKEN = re.compile(r"\S+")

    def __init__(self, *, profile: VerifiedBootstrapProfile) -> None:
        if not profile.enabled:
            raise ValueError("bootstrap text preparation requires an enabled verified profile")
        self._profile = profile

    @classmethod
    def classify_projection_eligibility(
        cls,
        *,
        profile: VerifiedBootstrapProfile,
        ingress: object,
        projection: object,
    ) -> tuple[str, str | None, str | None]:
        """Classify a retained projection using the same child partition as Step-2.

        A multi-child source has no synthetic whole-source grammar row.  It is
        eligible only when every sealed child independently selects an exact
        corpus literal.  The producer repeats this partition and emits the
        corresponding route/proof for every child before any writer handoff.
        """
        parents = tuple(getattr(projection, "segments", ()))
        if not parents:
            return "unsupported_input", "unsupported_grammar", None
        children: list[str] = []
        for parent in parents:
            parent_text = getattr(parent, "semantic_text", None)
            if not isinstance(parent_text, str) or not parent_text:
                return "unsupported_input", "unsupported_grammar", None
            for start, end in cls._safe_ranges(
                parent_text,
                profile.artifacts.profile_manifest.preparation_policy.max_segment_characters,
            ):
                children.append(parent_text[start:end])
        if not children:
            return "unsupported_input", "unsupported_grammar", None

        # Keep the legacy one-segment classification byte-for-byte intact.
        if len(children) == 1 and len(parents) == 1:
            return classify_bootstrap_input(
                profile=profile,
                ingress=ingress,
                normalized_segment=children[0].encode("utf-8"),
            )

        matched_case_ids: list[str] = []
        for child in children:
            outcome, reason, case_id = classify_bootstrap_input(
                profile=profile,
                ingress=ingress,
                normalized_segment=child.strip().encode("utf-8"),
            )
            if outcome != "selected_pipeline_pending":
                return outcome, reason, case_id
            if case_id is None:
                raise ValueError("selected bootstrap child has no corpus case")
            matched_case_ids.append(case_id)
        # The Step-1 outcome schema deliberately records one corpus case only.
        # The complete ordered child-case binding is persisted in Step-2 proofs.
        return "selected_pipeline_pending", None, None

    def __call__(self, request: TextPreparationRequest) -> PreparedSource:
        observation = request.observation
        profile = self._profile
        manifest = profile.artifacts.profile_manifest
        if request.policy != manifest.preparation_policy:
            raise ValueError("text preparation policy is not owned by the verified profile")
        if not observation.is_step_one_admitted:
            raise ValueError("bootstrap text preparation requires complete Step-1 admission")
        evidence = observation.bootstrap_language_evidence
        if evidence is None:
            raise ValueError("bootstrap text preparation requires authenticated language evidence")
        projection = observation.semantic_text_projection
        context = observation.semantic_context
        carriers = observation.segment_governance_carriers
        admissions = observation.message_admission_carriers
        governance_artifact = observation.governance_carrier_artifact
        if (
            projection.retained_source_digest != observation.source_digest
            or projection.projection_text != observation.text
            or context.source_id != observation.source_id
            or context.source_digest != observation.source_digest
            or carriers != projection.segment_governance_carriers
            or admissions != projection.message_admission_carriers
            or governance_artifact.segment_governance != carriers
            or governance_artifact.message_admissions != admissions
            or governance_artifact.required_outcome_scopes != projection.required_outcome_scopes
            or evidence.source_id != observation.source_id
            or evidence.source_digest != observation.source_digest
            or evidence.original_text_digest != sha256(observation.text.encode("utf-8")).hexdigest()
            or evidence.segment_governance_carriers_digest != carriers.carrier_set_digest
            or evidence.message_admission_carriers_digest != admissions.carrier_set_digest
            or evidence.governance_carrier_artifact_digest != governance_artifact.artifact_digest
        ):
            raise ValueError("Step-1 preparation authority is substituted")

        prepared_segments: list[PreparedSegment] = []
        routes = []
        proofs: list[BootstrapSegmentGrammarProof] = []
        sentence_spans: list[SourceSpanReference] = []
        token_spans: list[SourceSpanReference] = []
        admissions_by_binding = {
            identity.segment_governance_binding_digest: identity
            for identity in admissions.identities
        }
        for parent in projection.segments:
            parent_text = parent.semantic_text
            child_ranges = self._safe_ranges(parent_text, request.policy.max_segment_characters)
            for start, end in child_ranges:
                child_text = parent_text[start:end]
                normalized_child_text = child_text.strip()
                corpus_case = self._matching_case(normalized_child_text, evidence)
                if corpus_case is None or corpus_case.disposition != "supported_form":
                    raise ValueError("bootstrap text preparation input is nonpromoting")
                span_digest = sha256(child_text.encode("utf-8")).hexdigest()
                normalized_digest = sha256(normalized_child_text.encode("utf-8")).hexdigest()
                segment_id = self._segment_id(observation.source_id, parent.segment_id, start, end)
                owned_projection = ProjectionTextSpan.create(
                    artifact=projection.projection_text_artifact,
                    start=parent.projection_span.start + start,
                    end=parent.projection_span.start + end,
                    substring_digest=span_digest,
                )
                owned_local = SegmentLocalTextSpan.create(
                    artifact=parent.segment_text_artifact,
                    start=start,
                    end=end,
                    substring_digest=span_digest,
                )
                proof = BootstrapSegmentGrammarProof.create(
                    source_id=observation.source_id,
                    segment_id=segment_id,
                    language_evidence_tuple=("en", "authenticated_host_declaration", "trusted", "agrees"),
                    bootstrap_language_evidence_digest=evidence.evidence_digest,
                    corpus_case_id=corpus_case.case_id,
                    normalized_segment_digest=normalized_digest,
                )
                route = BootstrapDeclaredSegmentLanguageRoute.create(
                    schema_id="memorii.semantic_ingestion.bootstrap_declared_segment_language_route",
                    schema_version=1,
                    source_id=observation.source_id,
                    source_digest=observation.source_digest,
                    segment_id=segment_id,
                    parent_projection_segment_id=parent.segment_id,
                    segment_text_artifact_id=parent.segment_text_artifact.artifact_id,
                    segment_text_artifact_digest=parent.segment_text_artifact.artifact_digest,
                    segment_text_content_digest=parent.segment_text_artifact.content_digest,
                    declared_language="en",
                    language_evidence_kind="authenticated_host_declaration",
                    language_evidence_trust="trusted",
                    governance_agreement="agrees",
                    bootstrap_language_evidence_digest=evidence.evidence_digest,
                    bootstrap_profile_manifest_digest=manifest.profile_digest,
                    preparation_policy_fingerprint=request.policy.policy_fingerprint,
                    component_root_digest=manifest.component_root_digest,
                    corpus_case_id=corpus_case.case_id,
                    normalized_segment_digest=normalized_digest,
                    grammar_proof_digest=proof.proof_digest,
                    decision="selected",
                )
                span = self._span(
                    observation.source_id, projection.projection_digest, parent, owned_projection,
                    owned_local,
                )
                sentence_spans.append(span)
                token_spans.extend(
                    self._token_spans(
                        observation.source_id, projection.projection_digest, parent, child_text,
                        owned_projection, owned_local,
                    )
                )
                prepared_segments.append(PreparedSegment(
                    segment_id=segment_id,
                    parent_projection_segment_id=parent.segment_id,
                    owned_projection_span=owned_projection,
                    context_projection_span=parent.projection_span,
                    owned_segment_span=owned_local,
                    context_segment_span=parent.text_mapping_proof.segment_span,
                    text_mapping_proof=parent.text_mapping_proof,
                    segment_governance=parent.segment_governance,
                    message_admission_identity=admissions_by_binding.get(parent.segment_governance.binding_digest),
                    language_route=route,
                    code_switch_spans=(),
                    boundary_flags=frozenset({"sentence"}),
                ))
                routes.append(route)
                proofs.append(proof)

        body = {
            "source_id": observation.source_id,
            "semantic_text": projection.projection_text,
            "semantic_text_projection": projection,
            "source_digest": observation.source_digest,
            "semantic_context": context,
            "segment_language_routes": SegmentLanguageRouteSet.create(
                source_id=observation.source_id, source_digest=observation.source_digest,
                routes=tuple(routes),
            ),
            "segment_governance_carriers": carriers,
            "message_admission_carriers": admissions,
            "governance_carrier_artifact": governance_artifact,
            "sentence_spans": tuple(sentence_spans),
            "segments": tuple(prepared_segments),
            "token_spans": tuple(token_spans),
            "grammar_proofs": tuple(proofs),
            "preparation_policy": request.policy,
            "status": "complete",
            "diagnostics": (),
        }
        return PreparedSource(
            **body,
            preparation_fingerprint=contract_digest(
                b"memorii.semantic-ingestion.prepared-source.v1", body
            ),
        )

    @classmethod
    def _safe_ranges(cls, text: str, maximum: int) -> tuple[tuple[int, int], ...]:
        if not text:
            raise ValueError("bootstrap text preparation cannot promote an empty segment")
        sentence_ends = [match.end() for match in cls._SENTENCE_BOUNDARY.finditer(text)]
        if not sentence_ends or sentence_ends[-1] != len(text):
            sentence_ends.append(len(text))
        ranges: list[tuple[int, int]] = []
        start = 0
        for sentence_end in sentence_ends:
            if sentence_end <= start:
                continue
            ranges.extend(cls._bounded_ranges(text, start, sentence_end, maximum))
            start = sentence_end
        return tuple(ranges)

    @staticmethod
    def _bounded_ranges(text: str, start: int, end: int, maximum: int) -> tuple[tuple[int, int], ...]:
        ranges: list[tuple[int, int]] = []
        cursor = start
        while end - cursor > maximum:
            boundaries = tuple(
                match.start()
                for match in re.finditer(r"\s", text[cursor + 1:cursor + maximum + 1])
            )
            if not boundaries:
                raise ValueError("bootstrap text preparation has no safe bounded segment boundary")
            boundary = cursor + 1 + boundaries[-1]
            ranges.append((cursor, boundary + 1))
            cursor = boundary + 1
        ranges.append((cursor, end))
        return tuple(ranges)

    def _matching_case(self, text: str, evidence: object):
        for case in self._profile.artifacts.grammar_corpus.cases:
            if (
                case.normalized_segment_bytes == text.encode("utf-8")
                and case.declared_language == evidence.language_declaration
                and case.language_evidence_kind == evidence.language_evidence_kind
                and case.language_evidence_trust == evidence.language_evidence_trust
                and case.governance_agreement == evidence.language_governance_agreement
            ):
                return case
        return None

    @staticmethod
    def _segment_id(source_id: str, parent_id: str, start: int, end: int) -> str:
        return "bootstrap-segment:" + sha256(
            f"{source_id}\0{parent_id}\0{start}\0{end}".encode()
        ).hexdigest()

    @staticmethod
    def _span(source_id: str, projection_digest: str, parent: object, projection_span: ProjectionTextSpan, local_span: SegmentLocalTextSpan) -> SourceSpanReference:
        return SourceSpanReference.create(
            source_id=source_id,
            projection_digest=projection_digest,
            projection_segment_id=parent.segment_id,
            retained_text_artifact=parent.text_mapping_proof.retained_span.artifact,
            projection_span=projection_span,
            segment_local_span=local_span,
            text_mapping_proof=parent.text_mapping_proof,
            source_reference=parent.source_reference,
        )

    def _token_spans(self, source_id: str, projection_digest: str, parent: object, text: str, projection_span: ProjectionTextSpan, local_span: SegmentLocalTextSpan) -> list[SourceSpanReference]:
        spans: list[SourceSpanReference] = []
        for token in self._TOKEN.finditer(text):
            token_text = token.group()
            digest = sha256(token_text.encode("utf-8")).hexdigest()
            spans.append(self._span(
                source_id, projection_digest, parent,
                ProjectionTextSpan.create(
                    artifact=projection_span.artifact,
                    start=projection_span.start + token.start(), end=projection_span.start + token.end(),
                    substring_digest=digest,
                ),
                SegmentLocalTextSpan.create(
                    artifact=local_span.artifact,
                    start=local_span.start + token.start(), end=local_span.start + token.end(),
                    substring_digest=digest,
                ),
            ))
        return spans


class TextPreparationService:
    """Run the configured deterministic Step-2 producer and publish its output."""

    def __init__(
        self,
        *,
        producer: Callable[[TextPreparationRequest], PreparedSource],
        repository: PreparedSourceRepository,
    ) -> None:
        self._producer = producer
        self._repository = repository

    def prepare_and_publish(self, request: TextPreparationRequest) -> PreparedSource:
        """Prepare from the complete immutable request, then publish exact bytes.

        No caller may smuggle a separate source-text string or policy into the
        producer: both are already sealed in the request/observation pair.
        """
        return self._repository.publish(self.prepare(request))

    def prepare(self, request: TextPreparationRequest) -> PreparedSource:
        """Produce and validate exact source authority without publishing it."""
        observation = request.observation
        prepared = PreparedSource.model_validate(
            self._producer(request).model_dump(mode="python")
        )
        if (
            prepared.source_id != observation.source_id
            or prepared.source_digest != observation.source_digest
            or prepared.semantic_text != observation.text
            or prepared.preparation_policy != request.policy
        ):
            raise ValueError("text preparation producer returned substituted source authority")
        # The legacy observation model has no digest field.  The prepared
        # contract remains the digest authority and repository key.
        return prepared

    @classmethod
    def for_verified_bootstrap_profile(
        cls, *, profile: VerifiedBootstrapProfile, repository: PreparedSourceRepository,
    ) -> TextPreparationService:
        """Construct the only production producer from verified profile authority."""
        return cls(producer=BootstrapTextPreparationProducer(profile=profile), repository=repository)


__all__ = [
    "InMemoryPreparedSourceRepository",
    "AtomicStorePreparedSourceRepository",
    "BootstrapTextPreparationProducer",
    "PreparedSourceRepository",
    "TextPreparationService",
]
