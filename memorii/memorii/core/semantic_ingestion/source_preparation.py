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
    VerifiedBootstrapProfile,
    classify_bootstrap_input,
)
from memorii.core.memory_evolution.semantic_analysis.source_contracts import (
    BootstrapFreeformSegmentLanguageRoute,
    PreparedSegment,
    PreparedSource,
    SegmentLanguageRouteSet,
    TextPreparationRequest,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapFreeformSegmentProof,
    ProjectionTextSpan,
    SegmentLocalTextSpan,
    SourceSpanReference,
    certified_roundtrip,
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
        value = certified_roundtrip(prepared)
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
            return certified_roundtrip(value)
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
        return certified_roundtrip(published)

    def load(self, *, source_id: str, source_digest: str) -> PreparedSource | None:
        value = self._atomic_store.load_prepared_source(
            source_id=source_id, source_digest=source_digest
        )
        if value is None:
            return None
        return certified_roundtrip(value)


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
        """Classify a retained projection using its exact Step-2 partition."""
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

        for child in children:
            outcome, reason, case_id = classify_bootstrap_input(
                profile=profile,
                ingress=ingress,
                normalized_segment=child.encode("utf-8"),
            )
            if outcome != "selected_pipeline_pending":
                return outcome, reason, case_id
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
        proofs: list[BootstrapFreeformSegmentProof] = []
        sentence_spans: list[SourceSpanReference] = []
        token_spans: list[SourceSpanReference] = []
        admissions_by_binding = {
            identity.segment_governance_binding_digest: identity
            for identity in admissions.identities
        }
        child_index = 0
        for parent in projection.segments:
            parent_text = parent.semantic_text
            child_ranges = self._safe_ranges(parent_text, request.policy.max_segment_characters)
            for start, end in child_ranges:
                child_text = parent_text[start:end]
                if child_index >= profile.artifacts.freeform_admission_policy.max_child_segments:
                    raise ValueError("bootstrap text preparation exceeds freeform child cap")
                # The Step-1 observation owns the authenticated language
                # evidence.  Do not treat the observation itself as host
                # ingress: it deliberately has no mutable ingress fields.
                outcome, reason, _ = classify_bootstrap_input(
                    profile=profile,
                    ingress=evidence,
                    normalized_segment=child_text.encode("utf-8"),
                )
                if outcome != "selected_pipeline_pending":
                    raise ValueError(f"bootstrap freeform preparation input is nonpromoting: {reason}")
                span_digest = sha256(child_text.encode("utf-8")).hexdigest()
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
                policy = profile.artifacts.freeform_admission_policy
                raw_prefix = projection.projection_text[: parent.projection_span.start + start]
                route = BootstrapFreeformSegmentLanguageRoute.create(
                    schema_id="memorii.semantic_ingestion.bootstrap_freeform_segment_language_route",
                    schema_version=1,
                    source_id=observation.source_id,
                    source_digest=observation.source_digest,
                    semantic_projection_id=projection.projection_text_artifact.artifact_id,
                    semantic_projection_digest=projection.projection_digest,
                    parent_projection_segment_id=parent.segment_id,
                    segment_id=segment_id,
                    segment_text_artifact_id=parent.segment_text_artifact.artifact_id,
                    segment_text_artifact_digest=parent.segment_text_artifact.artifact_digest,
                    segment_text_content_digest=parent.segment_text_artifact.content_digest,
                    prepared_segment_index=child_index,
                    unicode_scalar_start=parent.projection_span.start + start,
                    unicode_scalar_end=parent.projection_span.start + end,
                    utf8_byte_start=len(raw_prefix.encode("utf-8")),
                    utf8_byte_end=len((raw_prefix + child_text).encode("utf-8")),
                    raw_segment_digest=span_digest,
                    profile_coordinate="memorii.bootstrap_local_english_rule@current",
                    profile_digest=manifest.profile_digest,
                    capability_manifest_coordinate="memorii.bootstrap_grammar_capability_manifest@current",
                    capability_manifest_digest=profile.artifacts.grammar_capability_manifest.manifest_digest,
                    freeform_policy_coordinate="memorii.bootstrap_freeform_admission_policy@1",
                    freeform_policy_digest=policy.policy_digest,
                    component_root_coordinate="memorii.bootstrap_component_root@1",
                    component_root_digest=manifest.component_root_digest,
                    resource_policy_coordinate="memorii.text_preparation_policy@1",
                    resource_policy_digest=request.policy.policy_fingerprint,
                    declared_language="en",
                    trusted_language_evidence_digest=evidence.evidence_digest,
                )
                proof = BootstrapFreeformSegmentProof.create(
                    schema_id="memorii.semantic_ingestion.bootstrap_freeform_segment_proof",
                    schema_version=1,
                    segment_id=route.segment_id,
                    raw_segment_bytes=child_text.encode("utf-8"),
                    source_id=observation.source_id,
                    source_digest=observation.source_digest,
                    semantic_projection_id=projection.projection_text_artifact.artifact_id,
                    semantic_projection_digest=projection.projection_digest,
                    parent_projection_segment_id=route.parent_projection_segment_id,
                    prepared_segment_index=route.prepared_segment_index,
                    segment_text_artifact_id=route.segment_text_artifact_id,
                    segment_text_artifact_digest=route.segment_text_artifact_digest,
                    segment_text_content_digest=route.segment_text_content_digest,
                    unicode_scalar_start=route.unicode_scalar_start,
                    unicode_scalar_end=route.unicode_scalar_end,
                    utf8_byte_start=route.utf8_byte_start,
                    utf8_byte_end=route.utf8_byte_end,
                    raw_segment_digest=route.raw_segment_digest,
                    profile_coordinate=route.profile_coordinate,
                    profile_digest=route.profile_digest,
                    capability_manifest_coordinate=route.capability_manifest_coordinate,
                    capability_manifest_digest=route.capability_manifest_digest,
                    freeform_policy_coordinate=route.freeform_policy_coordinate,
                    freeform_policy_digest=route.freeform_policy_digest,
                    component_root_coordinate=route.component_root_coordinate,
                    component_root_digest=route.component_root_digest,
                    resource_policy_coordinate=route.resource_policy_coordinate,
                    resource_policy_digest=route.resource_policy_digest,
                    declared_language=route.declared_language,
                    trusted_language_evidence_digest=route.trusted_language_evidence_digest,
                    route_digest=route.route_digest,
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
                child_index += 1

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
            "segment_proofs": tuple(proofs),
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
        prepared = certified_roundtrip(self._producer(request))
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
