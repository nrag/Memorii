"""Manifest-bound client for the local Duckling temporal sidecar.

The sidecar is an analysis dependency, not a source of durable truth.  This
adapter accepts one sealed segment request, admits only a loopback endpoint,
and returns no result on every coordinate, transport, or output ambiguity.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    ResolvedTemporalCandidate,
    SegmentLanguageLaneOutcome,
    SegmentLanguageRouteSet,
    SourceSpanReference,
    TemporalResolution,
    TemporalResolutionRequest,
    TemporalResolverManifest,
    contract_digest,
)

_ABSOLUTE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


class DucklingTemporalResolverUnavailable(RuntimeError):
    """The certified local temporal authority is not available."""


class _HttpResponse(Protocol):
    def read(self) -> bytes: ...


_Transport = Callable[[Request, float], _HttpResponse]


@dataclass(frozen=True)
class DucklingRuntimeCoordinates:
    """Coordinates supplied by the sidecar release, never inferred at runtime."""

    image_digest: str
    ruleset_version: str
    locale_map_digest: str
    timezone_policy_digest: str
    adapter_schema_digest: str
    supported_construction_families: tuple[str, ...]

    def validate(self) -> None:
        if (
            not _HEX.fullmatch(self.image_digest)
            or not _HEX.fullmatch(self.locale_map_digest)
            or not _HEX.fullmatch(self.timezone_policy_digest)
            or not _HEX.fullmatch(self.adapter_schema_digest)
            or not self.ruleset_version
            or not self.supported_construction_families
            or self.supported_construction_families
            != tuple(sorted(set(self.supported_construction_families)))
        ):
            raise DucklingTemporalResolverUnavailable("Duckling runtime coordinates are malformed")

    def validate_manifest(self, manifest: TemporalResolverManifest) -> None:
        self.validate()
        if (
            manifest.binary_digest != self.image_digest
            or manifest.ruleset_version != self.ruleset_version
            or manifest.locale_map_digest != self.locale_map_digest
            or manifest.timezone_policy_digest != self.timezone_policy_digest
            or manifest.adapter_schema_digest != self.adapter_schema_digest
            or manifest.supported_construction_families != self.supported_construction_families
        ):
            raise DucklingTemporalResolverUnavailable("Duckling manifest does not bind the configured runtime")


class DucklingTemporalResolver:
    """Strict Duckling-to-``TemporalResolution`` adapter.

    A caller selects the locale and IANA timezone explicitly for every call.
    The adapter deliberately does not derive either value from host settings,
    request receipt time, or an ambient Duckling default.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        runtime_coordinates: DucklingRuntimeCoordinates,
        resolver_manifest: TemporalResolverManifest,
        transport: _Transport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._endpoint = _validate_loopback_endpoint(endpoint)
        runtime_coordinates.validate_manifest(resolver_manifest)
        if timeout_seconds <= 0:
            raise ValueError("Duckling timeout must be positive")
        self._coordinates = runtime_coordinates
        self._manifest = resolver_manifest
        self._transport = transport or _stdlib_transport
        self._timeout_seconds = timeout_seconds
        self._last_failure_reason: str | None = None

    @property
    def manifest(self) -> TemporalResolverManifest:
        return self._manifest

    @property
    def last_failure_reason(self) -> str | None:
        return self._last_failure_reason

    def resolve(
        self,
        request: TemporalResolutionRequest,
        *,
        locale: str,
        timezone: str,
    ) -> TemporalResolution | None:
        """Resolve exactly one selected source segment or fail closed."""

        self._last_failure_reason = None
        if request.resolver_manifest != self._manifest:
            return self._fail("manifest_mismatch")
        route = request.segment.language_route
        if route.decision != "selected" or route.resource_binding is None:
            return self._fail("unselected_route")
        if route.resource_binding.temporal_resolver_manifest_digest != self._manifest.manifest_digest:
            return self._fail("route_manifest_mismatch")
        if not _valid_locale(locale) or route.selected_language != locale.split("_", 1)[0].split("-", 1)[0]:
            return self._fail("unsupported_locale")
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            return self._fail("unsupported_timezone")
        reference = request.reference_evidence
        if reference is not None and reference.reference_instant.tzinfo is None:
            return self._fail("unauthenticated_reference_time")
        try:
            raw = self._call_sidecar(
                text=request.segment.segment_text,
                locale=locale,
                timezone=timezone,
                reference_time=None if reference is None else reference.reference_instant.astimezone(UTC),
            )
            candidates = self._parse_rows(
                raw=raw,
                request=request,
                locale=locale,
                timezone=timezone,
                zone=zone,
            )
            if not candidates:
                return self._fail("no_supported_temporal_candidates")
            if reference is None and any(not _ABSOLUTE_DATE.fullmatch(candidate.exact_text) for candidate in candidates):
                return self._fail("reference_time_required")
            return self._resolution(request=request, candidates=candidates, response=raw)
        except DucklingTemporalResolverUnavailable as exc:
            return self._fail(str(exc))
        except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            return self._fail("sidecar_unavailable")

    def _fail(self, reason: str) -> None:
        self._last_failure_reason = reason
        return None

    def _call_sidecar(
        self,
        *,
        text: str,
        locale: str,
        timezone: str,
        reference_time: datetime | None,
    ) -> list[object]:
        body: dict[str, str] = {
            "text": text,
            "locale": locale,
            "tz": timezone,
            "dims": json.dumps(["time"], separators=(",", ":")),
        }
        if reference_time is not None:
            body["reftime"] = reference_time.isoformat().replace("+00:00", "Z")
        # Duckling's documented /parse service accepts form fields.  Keeping
        # them in the request body avoids placing source text in a URL or log.
        encoded = urlencode(body, encoding="utf-8", errors="strict").encode("ascii")
        response = self._transport(
            Request(
                self._endpoint,
                data=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            ),
            self._timeout_seconds,
        )
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise DucklingTemporalResolverUnavailable("Duckling response is not a strict result list")
        return payload

    def _parse_rows(
        self,
        *,
        raw: list[object],
        request: TemporalResolutionRequest,
        locale: str,
        timezone: str,
        zone: ZoneInfo,
    ) -> tuple[ResolvedTemporalCandidate, ...]:
        candidates: list[ResolvedTemporalCandidate] = []
        seen_spans: set[tuple[int, int]] = set()
        for row in raw:
            assert isinstance(row, dict)
            if set(row) - {"start", "end", "body", "dim", "value", "latent"}:
                raise DucklingTemporalResolverUnavailable("Duckling response has an unknown top-level field")
            if row.get("dim") != "time" or row.get("latent") not in (False, None):
                continue
            start = _text_offset_to_scalar(request.segment.segment_text, row.get("start"))
            end = _text_offset_to_scalar(request.segment.segment_text, row.get("end"))
            if start >= end:
                raise DucklingTemporalResolverUnavailable("Duckling returned an empty temporal span")
            exact_text = request.segment.segment_text[start:end]
            if row.get("body") != exact_text:
                raise DucklingTemporalResolverUnavailable("Duckling returned an inexact temporal span")
            key = (start, end)
            if key in seen_spans or any(start < prior_end and prior_start < end for prior_start, prior_end in seen_spans):
                raise DucklingTemporalResolverUnavailable("Duckling returned an ambiguous temporal span")
            seen_spans.add(key)
            instant, grain = _parse_temporal_value(row.get("value"), zone)
            span = _source_span(request=request, start=start, end=end)
            identity = {
                "segment_id": request.segment.segment_id,
                "preparation_fingerprint": request.segment.preparation_fingerprint,
                "segment_language_route_digest": request.segment.language_route.route_digest,
                "source_span": span,
                "value_kind": "instant",
                "normalized_interval": TimeInterval(start=instant),
                "normalized_duration": None,
                "grain": grain,
                "locale": locale,
                "timezone": timezone,
                "reference_evidence": request.reference_evidence,
                "resolver_rule_id": f"{self._coordinates.ruleset_version}:time:value",
            }
            candidates.append(
                ResolvedTemporalCandidate.create(
                    **identity,
                    candidate_id=contract_digest(
                        b"memorii.semantic-ingestion.resolved-temporal-candidate-identity.v1", identity
                    ),
                    exact_text=exact_text,
                )
            )
        return tuple(sorted(candidates, key=lambda item: (item.source_span.reference_digest, item.candidate_digest)))

    def _resolution(
        self,
        *,
        request: TemporalResolutionRequest,
        candidates: tuple[ResolvedTemporalCandidate, ...],
        response: list[object],
    ) -> TemporalResolution:
        route = request.segment.language_route
        routes = SegmentLanguageRouteSet.create(
            source_id=request.segment.source_id,
            source_digest=request.segment.source_digest,
            routes=(route,),
        )
        artifact_digest = sha256(
            json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        outcome = SegmentLanguageLaneOutcome.create(
            lane="temporal_resolution",
            preparation_fingerprint=request.segment.preparation_fingerprint,
            segment_id=request.segment.segment_id,
            segment_language_route_digest=route.route_digest,
            resource_binding_digest=route.resource_binding.resource_binding_digest if route.resource_binding else None,
            selected_manifest_digest=self._manifest.manifest_digest,
            status="complete",
            artifact_digest=artifact_digest,
            reason_codes=(),
        )
        return TemporalResolution.create(
            source_id=request.segment.source_id,
            source_digest=request.segment.source_digest,
            preparation_fingerprint=request.segment.preparation_fingerprint,
            segment_language_routes=routes,
            segment_outcomes=(outcome,),
            candidates=candidates,
            ambiguous_spans=(),
            status="complete",
            diagnostics=(),
        )


def _validate_loopback_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/parse"}
    ):
        raise DucklingTemporalResolverUnavailable("Duckling endpoint must be an explicit loopback parse endpoint")
    return endpoint.rstrip("/") + "/parse" if not parsed.path else endpoint


def _stdlib_transport(request: Request, timeout: float) -> _HttpResponse:
    return urlopen(request, timeout=timeout)  # noqa: S310 - endpoint was validated above.


def _valid_locale(locale: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2,3}(?:[_-][A-Z]{2})?", locale))


def _text_offset_to_scalar(text: str, offset: object) -> int:
    if not isinstance(offset, int) or offset < 0:
        raise DucklingTemporalResolverUnavailable("Duckling offset is invalid")
    if offset > len(text):
        raise DucklingTemporalResolverUnavailable("Duckling offset is out of bounds")
    return offset


def _parse_temporal_value(value: object, zone: ZoneInfo) -> tuple[datetime, str]:
    if not isinstance(value, dict) or set(value) - {"type", "value", "grain", "values"}:
        raise DucklingTemporalResolverUnavailable("Duckling temporal value has an unsupported shape")
    primary = _parse_temporal_value_signature(
        {
            "type": value.get("type"),
            "value": value.get("value"),
            "grain": value.get("grain"),
        },
        zone,
    )
    alternatives = value.get("values")
    if alternatives is None:
        return primary
    if not isinstance(alternatives, list) or not alternatives:
        raise DucklingTemporalResolverUnavailable("Duckling temporal value has an unsupported shape")
    candidate_set = {primary}
    for alternate in alternatives:
        candidate_set.add(_parse_temporal_value_signature(alternate, zone))
    if len(candidate_set) != 1:
        raise DucklingTemporalResolverUnavailable("Duckling temporal value is ambiguous")
    return primary


def _parse_temporal_value_signature(value: object, zone: ZoneInfo) -> tuple[datetime, str]:
    if not isinstance(value, dict) or set(value) - {"type", "value", "grain"}:
        raise DucklingTemporalResolverUnavailable("Duckling temporal value has an unsupported shape")
    if value.get("type") != "value" or not isinstance(value.get("value"), str) or not isinstance(value.get("grain"), str):
        raise DucklingTemporalResolverUnavailable("Duckling temporal value is unsupported")
    return _parse_offset_instant(value["value"], zone), value["grain"]


def _parse_offset_instant(value: str, zone: ZoneInfo) -> datetime:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DucklingTemporalResolverUnavailable("Duckling returned an invalid normalized instant") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise DucklingTemporalResolverUnavailable("Duckling normalized instant has no offset")
    if instant.astimezone(zone).utcoffset() != instant.utcoffset():
        raise DucklingTemporalResolverUnavailable("Duckling normalized instant violates configured timezone")
    return instant.astimezone(UTC)


def _source_span(*, request: TemporalResolutionRequest, start: int, end: int) -> SourceSpanReference:
    # This reproduces the canonical source-span construction used by both
    # parser lanes without making temporal analysis depend on a parser class.
    context = request.segment.context_text
    width = context.segment_local_span.end - context.segment_local_span.start
    if len(request.segment.segment_text) != width or not 0 <= start < end <= width:
        raise DucklingTemporalResolverUnavailable("temporal input lacks one exact segment coordinate")
    text = request.segment.segment_text[start:end]
    digest = sha256(text.encode("utf-8")).hexdigest()
    from memorii.core.semantic_ingestion.contracts import ProjectionTextSpan, SegmentLocalTextSpan

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


__all__ = ["DucklingRuntimeCoordinates", "DucklingTemporalResolver", "DucklingTemporalResolverUnavailable"]
