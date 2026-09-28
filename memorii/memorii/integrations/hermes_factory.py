"""First-party Hermes factory for the installation-bound Level 2 trial.

This is an admission boundary only.  It verifies package profile material and
the operator's sidecar before constructing the existing provider service.  The
semantic runtime, completed-turn admission, and protected recall are composed
by later milestones, so this binding deliberately refuses turn ingress.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    AuthenticatedOriginLineageEvidence,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import EntityType
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.learned_replay import LearnedRetainedSourceReplayService
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority
from memorii.core.semantic_ingestion.catalog_authority import (
    AgentLocalCatalogAuthorityScope,
    AuthenticatedPrincipalAgent,
    CatalogAuthorityCoordinate,
    CatalogAuthorityError,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    PairedEvaluationAuthority,
    ResolvedCatalogAuthority,
    ResolvedStructuredSubmissionAuthority,
    SourceScopeGrant,
    StructuredFactReadAuthority,
    StructuredSubmissionAuthorityRequest,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import PackageIndexedCatalogBundleLocator
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    ObserverBindingIdentity,
)
from memorii.core.semantic_ingestion.coverage_observer import (
    OntologyObservationRequest,
    OntologyObservationResult,
)
from memorii.core.semantic_ingestion.coverage_recurrence import RelationGapSignature
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    CurrentReleaseBootstrapV3HostMaterialBuilder,
    local_level2_bootstrap_authorization_from_sidecar,
)
from memorii.core.semantic_ingestion.learned_relation import (
    ActivationPolicy,
    FrozenMentorsPairedEvaluator,
    IsolatedMentorsEvaluationExecutor,
    LearnedRelationCandidateService,
    LearnedRelationRuntime,
    OntologyActivation,
    OntologyCatalogVersion,
    OntologyChangeProposal,
    PairedEvaluationCaseOutcome,
    PairedEvaluationCatalogBundle,
    learned_catalog_pointer_memory_id,
)
from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle
from memorii.core.user_context.preference_delegations import PreferenceDelegationRepository
from memorii.core.user_context.preferences import (
    PreferenceAccessPolicy,
    PreferenceHolderAuthority,
    PreferenceService,
)
from memorii.integrations.hermes_local_authority import (
    LocalLevel2AuthorityError,
    load_local_level2_authority,
    load_local_structured_tool_authority,
)
from memorii.integrations.hermes_runtime_binding import (
    HermesAuthenticatedForwardingReceipt,
    HermesAuthenticatedOriginReceipt,
    HermesOriginReceipt,
    HermesProviderRuntimeBinding,
)

_PREFERENCE_TOPIC_TYPES = {
    "ProductService": EntityType.PRODUCT_SERVICE,
    "Asset": EntityType.ASSET,
    "Place": EntityType.PLACE,
}


class _LocalNoKeyMentorsObserver:
    """Closed local observer for direct `Person mentors Person` evidence."""

    _DIRECT_MENTORS = re.compile(
        r"(?P<subject>[A-Z][A-Za-z'-]{0,63}) mentors (?P<object>[A-Z][A-Za-z'-]{0,63})\."
    )
    binding = ObserverBindingIdentity(
        binding_version="memorii.hermes.local-no-key-mentors-observer.v1",
        provider="memorii_local", model="none", prompt_version="direct-mentors:v1",
        transport="deterministic_local", egress_policy_digest=sha256(
            b"memorii.hermes.local-no-key-mentors-observer.egress.v1"
        ).hexdigest(),
        output_schema_digest=sha256(
            b"memorii.hermes.local-no-key-mentors-observer.schema.v1"
        ).hexdigest(),
    )

    def observe(self, request: OntologyObservationRequest) -> OntologyObservationResult:
        match = self._DIRECT_MENTORS.fullmatch(request.source_text)
        if match is None:
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
            )
        quote = request.source_text[:-1]
        return OntologyObservationResult.create(
            semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
            source_span=CoverageSourceSpan(start=0, end=len(quote)),
            source_quote=quote,
            signature=RelationGapSignature.create(
                normalized_relation_meaning="mentors",
                subject_type_id="Person",
                object_type_id="Person",
                domain_id="organization",
                evidence_rule_id="direct_assertion:v1",
            ),
        )


def _preference_topic_identity_resolver(
    *,
    service,
    holder_user_id: str,
):
    """Bind Preferences to the current canonical semantic entity owner."""

    def identity_is_current(
        requested_holder_id: str,
        canonical_topic_id: str,
        topic_type: str,
        topic_quote: str,
    ) -> bool:
        expected_type = _PREFERENCE_TOPIC_TYPES.get(topic_type)
        if requested_holder_id != holder_user_id or expected_type is None:
            return False
        quote_key = " ".join(unicodedata.normalize("NFKC", topic_quote).casefold().split())
        return bool(quote_key) and service.current_semantic_entity_matches(
            canonical_entity_id=canonical_topic_id,
            asserted_type=expected_type.value,
            normalized_alias_key=quote_key,
            expected_fact_scope=f"user:{holder_user_id}",
        )

    return identity_is_current


def _isolated_mentors_evaluation_cases(
    proposal: OntologyChangeProposal,
    cases: tuple[tuple[str, str, str], ...],
    binding_digest: str,
    corpus_digest: str,
    budget_digest: str,
    context: object,
) -> tuple[PairedEvaluationCaseOutcome, ...]:
    """Run the frozen corpus through separate parent and candidate roots."""
    from memorii.core.semantic_ingestion.structured_fact_read import StructuredFactReadRequest

    def build_root(path: Path, *, candidate: bool):
        # The factory is the canonical composition root.  A fresh storage
        # directory gives each arm its own memory plane, grant records, pin
        # records, writer state, and protected-reader snapshot.
        isolated_context = SimpleNamespace(**(vars(context) | {"storage_root": path}))
        if not candidate:
            return _build_local_level2_runtime_binding(
                isolated_context, _enable_ontology_observer=False,
            )
        # The private root derives its account identity through ordinary
        # factory composition, then reopens the same isolated store with the
        # exact inert bundle authority.  Nothing is selected or activated.
        identity_root = _build_local_level2_runtime_binding(
            isolated_context, _enable_ontology_observer=False,
        )
        identity_runtime = identity_root.completed_turn_runtime
        if identity_runtime is None:
            raise ValueError("isolated completed-turn runtime is unavailable")
        try:
            scope = proposal.catalog_scope
            if (
                identity_runtime._authenticated_author_id != scope.principal_id
                or identity_runtime._authenticated_agent_id != scope.agent_id
            ):
                raise ValueError("paired evaluation proposal is outside the isolated owner scope")
        finally:
            identity_runtime.close()
        bundle = PairedEvaluationCatalogBundle.from_proposal(proposal=proposal)
        authority = PairedEvaluationAuthority.create(
            proposal_id=proposal.proposal_id,
            parent_catalog_digest=proposal.parent_catalog_digest,
            evaluation_bundle_digest=bundle.bundle_digest,
            catalog_scope=proposal.catalog_scope,
            isolated_store_digest=sha256(str(path).encode("utf-8")).hexdigest(),
        )
        return _build_local_level2_runtime_binding(
            isolated_context,
            _paired_evaluation_authority=authority,
            _paired_evaluation_bundle=bundle,
            _enable_ontology_observer=False,
        )

    def arguments(
        sentence: str, *, expected: str,
    ) -> dict[str, object]:
        # The fixed corpus has no model output.  The normal structured runtime
        # still validates the typed proposal, exact source span, materializes
        # a request, and runs the ordinary atomic terminal.
        subject, object_quote = "Ada", "Bea"
        if sentence == "Cora mentors Dax.":
            subject, object_quote = "Cora", "Dax"
        predicate_id = "reports_to" if sentence == "Ada reports to Bea." else "mentors"
        anchor = "reports to" if predicate_id == "reports_to" else "mentors"
        proposal: dict[str, object] = {
                "abstained": False,
                "mentions": [
                    {"local_id": "subject", "mention_quote": subject, "mention_context_quote": sentence, "proposed_type": "Person"},
                    {"local_id": "object", "mention_quote": object_quote, "mention_context_quote": sentence, "proposed_type": "Person"},
                ],
                "facts": [{
                    "kind": "fact", "local_id": predicate_id, "predicate_id": predicate_id,
                    "subject_entity_ref": "subject", "object": {"kind": "entity", "entity_ref": "object"},
                    "assertion_quote": sentence, "predicate_anchor_quote": anchor,
                    "polarity": "positive", "commitment": "asserted",
                    "attributed_to_entity_ref": None, "temporal_qualifier_quotes": [],
                }],
                "corrections": [], "retractions": [], "action_states": [], "identity_operations": [],
            }
        return {
            "schema_version": 1,
            "source_quote": sentence,
            "source_quote_start": 0,
            "subject_quote": subject,
            "predicate_anchor_quote": anchor,
            "object_quote": object_quote,
            "proposal": proposal,
        }

    def execute(
        runtime: object, *, case_id: str, sentence: str, expected: str,
        ordinal: int, candidate: bool,
    ) -> tuple[str, str]:
        author = runtime._authenticated_author_id
        session_id = f"isolated-evaluation:{'candidate' if candidate else 'parent'}:{ordinal}"
        captured_at = datetime.now(UTC)
        runtime.capture_user_turn(
            session_id=session_id,
            turn_ordinal=1,
            message=sentence,
            authenticated_author_id=author,
            received_at=captured_at,
        )
        runtime.get_tool_schemas()
        call_arguments = arguments(
            sentence,
            expected=("candidate_commit_and_read" if case_id == "scope-provenance-veto" else expected),
        )
        if case_id == "scope-provenance-veto" and candidate:
            active = runtime._active_turn
            if active is None:
                raise ValueError("isolated paired evaluation capture is unavailable")
            result = runtime._service.submit_structured_fact(
                runtime._structured_tool_request(
                    active=active, arguments=call_arguments, mentors=True,
                ),
                authenticated_host_ingress=runtime._issue_host_ingress(
                    session_id, author, datetime.now(UTC),
                ),
            )
        else:
            result = runtime.handle_tool_call(
                tool_name="memorii_submit_fact", arguments=call_arguments,
            )
        # The scope/provenance veto intentionally calls the service root
        # directly, whose closed response is a typed model rather than the
        # Hermes JSON dictionary returned by ``handle_tool_call``.  Preserve
        # its terminal denial instead of converting it to ``unavailable``.
        status = (
            result.get("status") if isinstance(result, dict)
            else getattr(result, "status", "unavailable")
        )
        if status == "rejected":
            status = "denied"
        if status != "committed":
            return str(status), "unavailable"
        records = runtime._service._memory_plane.list_records()
        claim = next(
            record for record in records
            if record.content.get("runtime_context_projection_kind") == "bootstrap_v3_claim_assertion"
        )
        subject_id = claim.content["claim_identity"]["subject_assertion_ref"]["logical_entity_id_at_assertion"]
        read = runtime.read_structured_facts(
            request=StructuredFactReadRequest(
                predicate_id=("reports_to" if case_id == "parent-regression" else "mentors"),
                subject_entity_id=subject_id,
            ),
            session_id=session_id,
            authenticated_author_id=author,
            now=datetime.now(UTC),
        )
        return str(status), "read" if read.status == "ok" and read.items else str(read.status)

    outcomes: list[PairedEvaluationCaseOutcome] = []
    forbidden_control_kinds = {
        "learned_ontology_change_proposal_v1",
        "learned_ontology_catalog_version_v1",
        "learned_ontology_activation_attempt_v1",
    }
    for ordinal, (case_id, sentence, expected) in enumerate(cases, start=1):
        with tempfile.TemporaryDirectory(prefix="memorii-paired-parent-") as parent_root, tempfile.TemporaryDirectory(prefix="memorii-paired-candidate-") as candidate_root:
            parent = build_root(Path(parent_root), candidate=False)
            candidate = build_root(Path(candidate_root), candidate=True)
            parent_runtime = parent.completed_turn_runtime
            candidate_runtime = candidate.completed_turn_runtime
            if parent_runtime is None or candidate_runtime is None:
                raise ValueError("isolated completed-turn runtime is unavailable")
            try:
                parent_status, parent_read = execute(
                    parent_runtime, case_id=case_id, sentence=sentence, expected=expected,
                    ordinal=ordinal, candidate=False,
                )
                candidate_status, candidate_read = execute(
                    candidate_runtime, case_id=case_id, sentence=sentence, expected=expected,
                    ordinal=ordinal, candidate=True,
                )
                outcomes.append(PairedEvaluationCaseOutcome(
                    case_id=case_id, expected=expected,
                    parent_status=(
                        "read"
                        if case_id == "parent-regression"
                        and parent_status == "committed"
                        and parent_read == "read"
                        else parent_status
                        if parent_status in {"committed", "read", "denied", "abstained", "unavailable"}
                        else "unavailable"
                    ),
                    candidate_status=candidate_status if candidate_status in {"committed", "read", "denied", "abstained", "unavailable"} else "unavailable",
                    candidate_read_status=candidate_read if candidate_read in {"read", "denied", "abstained", "unavailable"} else "unavailable",
                    binding_digest=binding_digest, corpus_digest=corpus_digest, budget_digest=budget_digest,
                ))
                for runtime in (parent_runtime, candidate_runtime):
                    records = runtime._service._memory_plane.list_records()
                    if any(record.source_kind in forbidden_control_kinds for record in records):
                        raise ValueError("isolated paired evaluation created learned activation control")
                    if any(record.memory_id.startswith("learned-catalog-pointer:") for record in records):
                        raise ValueError("isolated paired evaluation selected a catalog")
            finally:
                parent_runtime.close()
                candidate_runtime.close()
    return tuple(outcomes)


def build_local_level2_runtime_binding(context: object) -> object:
    """Construct the standard verified first-party Hermes runtime binding."""
    return _build_local_level2_runtime_binding(context)


def build_local_level2_authenticated_source_runtime(context: object) -> object:
    """Expose the Level-2 authority chain through the non-Hermes adapter.

    This is deliberately a composition bridge, not a second learner.  The
    generic adapter receives only an authenticated source envelope; the
    factory retains selection, evaluation, and protected-read authority.
    """
    from memorii.integrations.authenticated_source import (
        AuthenticatedSourceLearnedOntologyBinding,
        AuthenticatedSourceSubmission,
        build_authenticated_source_runtime,
    )

    binding = _build_local_level2_runtime_binding(
        context,
        _recover_pending_semantic_work=False,
    )
    if not isinstance(binding, HermesProviderRuntimeBinding):
        raise TypeError("local Level 2 runtime binding is invalid")
    if (
        binding.activate_learned_candidate is None
        or binding.approve_learned_candidate is None
        or binding.learned_ontology_status is None
        or binding.completed_turn_runtime is None
    ):
        raise LocalLevel2AuthorityError("local learned ontology is unavailable")
    reader = getattr(binding.completed_turn_runtime, "read_structured_facts", None)
    if not callable(reader):
        raise LocalLevel2AuthorityError("local structured reader is unavailable")

    def issue_ingress(submission: AuthenticatedSourceSubmission) -> AuthenticatedHostIngress:
        if (
            submission.session_id is None
            or submission.user_id != getattr(context, "user_id", None)
        ):
            raise ValueError("authenticated source submission lacks session identity")
        return binding.issue_ingress(
            SimpleNamespace(
                hook="sync_turn",
                session_id=submission.session_id,
                user_id=binding.absent_author_id,
                received_at=submission.timestamp or datetime.now(UTC),
                agent_id=_canonical_agent_id(getattr(context, "agent_identity", None)),
            )
        )

    return build_authenticated_source_runtime(
        issue_ingress=issue_ingress,
        provider_service=binding.service,
        learned_ontology=AuthenticatedSourceLearnedOntologyBinding(
            activate_candidate=binding.activate_learned_candidate,
            approve_candidate=binding.approve_learned_candidate,
            status=binding.learned_ontology_status,
            read_structured_facts=lambda request: reader(
                request=request,
                session_id="generic-authenticated-source",
                authenticated_author_id=binding.absent_author_id,
                now=datetime.now(UTC),
            ),
            close=binding.completed_turn_runtime.close,
        ),
    )


def _build_local_level2_runtime_binding(
    context: object,
    *,
    _provision_structured_authority: bool = True,
    _allow_existing_operator_binding: bool = False,
    _paired_evaluation_authority: PairedEvaluationAuthority | None = None,
    _paired_evaluation_bundle: PairedEvaluationCatalogBundle | None = None,
    _enable_ontology_observer: bool = True,
    _recover_pending_semantic_work: bool = True,
) -> object:
    """Construct one verified, first-party Hermes binding without model I/O.

    The bridge supplies a typed context, but this module avoids importing the
    optional Hermes ABC at import time.  Local authority verification precedes
    memory-plane construction, service startup, credentials, and any remote
    transport construction.
    """

    hermes_home = getattr(context, "hermes_home", None)
    storage_root = getattr(context, "storage_root", None)
    if hermes_home is None or storage_root is None:
        raise TypeError("Hermes factory context is invalid")
    context_kind = _require_local_cli_context(context)

    bundle = load_project_assertions_bundle()
    sidecar = load_local_level2_authority(hermes_home=hermes_home)
    authorization = sidecar.get("authorization")
    if not isinstance(authorization, dict) or {
        field: authorization.get(field) for field in bundle.profile_digests
    } != dict(bundle.profile_digests):
        raise LocalLevel2AuthorityError("local Level 2 authority profile binding is invalid")

    now = datetime.now(UTC)
    authorization = local_level2_bootstrap_authorization_from_sidecar(sidecar, now=now)
    operator_id = (
        "memorii:hermes:operator:"
        + sha256((f"memorii.hermes.local-level2-operator.v1:{authorization.installation_id}").encode()).hexdigest()
    )
    agent_id = _canonical_agent_id(getattr(context, "agent_identity", None))
    primary_agent_id = _bind_single_local_operator_context(
        storage_root=storage_root,
        installation_id=authorization.installation_id,
        raw_user_id=getattr(context, "user_id", None),
        agent_id=agent_id,
        context_kind=context_kind,
        allow_existing_operator_binding=_allow_existing_operator_binding,
    )
    ingress_resolver = _LocalLevel2IngressResolver(
        installation_id=authorization.installation_id,
        operator_id=operator_id,
    )

    def authority_is_current() -> bool:
        try:
            current_bundle = load_project_assertions_bundle()
            current = load_local_level2_authority(hermes_home=hermes_home)
            current_authorization = local_level2_bootstrap_authorization_from_sidecar(current, now=datetime.now(UTC))
            current = current_authorization == authorization and dict(current_bundle.profile_digests) == dict(
                bundle.profile_digests
            )
            if not current or context_kind != "delegated":
                return current
            current_plane = MemoryPlaneService(
                record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane")
            )
            return PreferenceDelegationRepository(current_plane).active(operator_id, agent_id)
        except (OSError, TypeError, ValueError):
            return False

    memory_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane")
    )

    try:
        if context_kind != "primary":
            raise LocalLevel2AuthorityError("delegated preference agents cannot submit semantic facts")
        load_local_structured_tool_authority(hermes_home=hermes_home, now=now)
    except LocalLevel2AuthorityError:
        structured_resolver = None
    else:
        structured_resolver = _LocalLevel2StructuredSubmissionResolver(
            installation_id=authorization.installation_id,
            operator_id=operator_id,
            agent_id=agent_id,
            project_task_id=_project_task_id(
                authorization.installation_id, bundle.profile_digests["semantic_contract_digest"]
            ),
            authority_is_current=authority_is_current,
            structured_tool_is_current=lambda: _structured_tool_is_current(hermes_home),
            memory_plane=memory_plane,
            paired_evaluation_authority=_paired_evaluation_authority,
            paired_evaluation_bundle=_paired_evaluation_bundle,
        )

    capability, verifier = CurrentReleaseBootstrapV3HostMaterialBuilder.build_capability(
        authorization=authorization,
        now=now,
        authenticated_ingress_resolver=ingress_resolver,
        structured_submission_authority_resolver=structured_resolver,
        authorization_is_current=authority_is_current,
    )
    delegation_repository = PreferenceDelegationRepository(memory_plane)
    if context_kind == "delegated" and not delegation_repository.active(operator_id, agent_id):
        raise LocalLevel2AuthorityError("Hermes preference agent delegation is unavailable")
    scoped_read_authority = InProcessScopedReadAuthority(now_provider=lambda: datetime.now(UTC))
    observer = _LocalNoKeyMentorsObserver() if _enable_ontology_observer else None
    service = build_provider_memory_service_from_env(
        memory_plane=memory_plane,
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=verifier,
        scoped_read_authority=scoped_read_authority,
        ontology_observer_capability=observer,
        ontology_observer_authorizer=(lambda ingress, binding: (
            observer is not None
            and binding == observer.binding
            and ingress.delivery_principal_binding.principal_subject_id == operator_id
            and ingress.authenticated_agent_id == agent_id
        )) if observer is not None else None,
    )
    if service._composed_semantic_runtime is None:
        raise RuntimeError(
            "Hermes local Level 2 semantic runtime is unavailable: " + service._bootstrap_unavailable_reason
        )
    # Both the seed and generated default bundle are governed startup fences.
    # A captured turn therefore pins one persisted catalog version before the
    # tool schema is advertised.
    service.ensure_catalog_seed_genesis()
    service.ensure_default_catalog_release()
    preference_service = PreferenceService(
        memory_plane=memory_plane,
        policy=PreferenceAccessPolicy(
            holder_authorities=(
                PreferenceHolderAuthority(holder_user_id=operator_id, primary_agent_id=primary_agent_id),
            ),
            grants=(),
            delegation_repository=delegation_repository,
        ),
        topic_identity_is_current=_preference_topic_identity_resolver(
            service=service,
            holder_user_id=operator_id,
        ),
        delegation_repository=delegation_repository,
    )
    if structured_resolver is not None and _provision_structured_authority:
        # The local tool cannot be advertised until its complete, factory-bound
        # authority tuple is durably active in the semantic writer's store.
        service.provision_structured_submission_authority(
            authority=structured_resolver.issued_authority(),
        )
    # A prior process can stop after atomic callback admission but before the
    # worker creates its handoff. Drain that retained operation before the
    # activation reload verifies that every active control is terminal.
    if _recover_pending_semantic_work:
        recovery_deadline = time.monotonic() + 65.0
        while True:
            if not authority_is_current():
                raise LocalLevel2AuthorityError("local Level 2 authority is unavailable")
            recovery_outcomes = service.reconcile_memory_evolution()
            if not any(outcome.retryable for outcome in recovery_outcomes):
                break
            if time.monotonic() >= recovery_deadline:
                raise RuntimeError("Hermes semantic recovery remained pending")
            time.sleep(1.0)
    # The current Bootstrap capability owns the canonical registry and the
    # installation-bound local activation target. Complete the cutover before
    # Hermes can admit a completed turn, so no source can enter a partial
    # semantic runtime.
    # The generic authenticated-source composition does not own Hermes
    # completed-turn recovery. Its no-model observations may retain retryable
    # bootstrap work for a future capable host, while the already-activated
    # writer and learned replay/read roots remain usable across restart.
    has_observation_ledger_activation = any(
        record.source_kind == "semantic_ingestion_observation_ledger_activation"
        for record in memory_plane.list_records()
    )
    if _recover_pending_semantic_work or not has_observation_ledger_activation:
        service.activate_observation_ledger()
    from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import (
        HermesCompletedTurnRuntime,
    )
    from memorii.integrations.hermes_runtime_binding import HermesProviderRuntimeBinding

    def issue_completed_turn_ingress(
        session_id: str,
        author_id: str,
        received_at: datetime,
        origin_receipt: HermesOriginReceipt | None = None,
        source_content_digest: str | None = None,
    ) -> AuthenticatedHostIngress:
        if origin_receipt is not None and (
            not isinstance(source_content_digest, str)
            or (
                isinstance(origin_receipt, HermesAuthenticatedOriginReceipt)
                and (
                    origin_receipt.session_id != session_id
                    or origin_receipt.source_content_digest != source_content_digest
                )
            )
            or (
                isinstance(origin_receipt, HermesAuthenticatedForwardingReceipt)
                and (
                    origin_receipt.child_session_id != session_id
                    or origin_receipt.child_source_content_digest
                    != source_content_digest
                )
            )
        ):
            raise ValueError("Hermes origin receipt does not bind the captured source")
        return ingress_resolver.issue(
            SimpleNamespace(
                hook="sync_turn",
                session_id=session_id,
                user_id=author_id,
                agent_id=agent_id,
                received_at=received_at,
                upstream_origin_receipt=origin_receipt,
            )
        )

    def require_current_authority() -> None:
        if not authority_is_current():
            raise LocalLevel2AuthorityError("local Level 2 authority is unavailable")

    def revoke_current_structured_grant(grant_kind: str) -> None:
        """Revoke only the current factory-issued grant for this signed-in binding."""
        if structured_resolver is None:
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        if grant_kind not in {"source", "fact", "catalog_visibility"}:
            raise ValueError("structured grant kind is invalid")
        authority = structured_resolver.issued_authority()
        grant = {
            "source": authority.source_grant,
            "fact": authority.fact_grant,
            "catalog_visibility": authority.catalog_visibility_grant,
        }[grant_kind]
        service.revoke_structured_submission_authority_grant(
            grant_kind=grant_kind,
            grant=grant,
        )

    project_task_id = _project_task_id(
        authorization.installation_id,
        bundle.profile_digests["semantic_contract_digest"],
    )

    class _InstalledReplayWriter:
        """Bind catalog replay to the installed completed-turn writer root."""

        def __init__(self) -> None:
            self.runtime = None

        def replay_retained_source(self, **kwargs: object) -> str:
            if self.runtime is None or structured_resolver is None:
                return "deleted"
            # Selection has changed the resolver's chosen catalog.  Publish
            # that exact grant tuple before the ordinary writer resolves the
            # captured source pin and applies its final commit fence.
            try:
                authority = structured_resolver.issued_authority()
                service.provision_structured_submission_authority(authority=authority)
                self.runtime._structured_authority_request = (
                    structured_resolver.issued_authority_request()
                )
            except (OSError, ValueError):
                return "revoked"
            source_id = kwargs.get("source_id")
            source_digest = kwargs.get("source_digest")
            try:
                captured = service._semantic_atomic_store.classify_captured_turn_source(
                    source_id=source_id,
                    source_digest=source_digest,
                )
            except (OSError, TypeError, ValueError):
                return "deleted"
            if captured:
                return self.runtime.replay_retained_source(**kwargs)
            return self._replay_generic_retained_source(**kwargs)

        def _replay_generic_retained_source(self, **kwargs: object) -> str:
            if generic_replay is None:
                return "revoked"
            try:
                return generic_replay.replay_retained_source(**kwargs)
            except TypeError:
                return "revoked"

    generic_replay = (
        None
        if structured_resolver is None
        else LearnedRetainedSourceReplayService(
            service=service,
            authority_request=structured_resolver.issued_authority_request,
            issue_ingress=issue_completed_turn_ingress,
        )
    )
    replay_writer = _InstalledReplayWriter()

    learned_runtime = LearnedRelationRuntime(
        memory_plane=memory_plane,
        replay_writer=replay_writer,
        policy_for_scope=lambda scope: ActivationPolicy(
            owner_principal_id=scope.principal_id,
            owner_agent_id=scope.agent_id,
        ),
    )
    paired_evaluator = FrozenMentorsPairedEvaluator()
    candidate_service = LearnedRelationCandidateService(
        memory_plane=memory_plane,
        runtime=learned_runtime,
        evaluator=paired_evaluator,
    )

    class _InstalledRecurrenceCandidateAdmitter:
        def admit_recurrence_for_observation(
            self, *, group_id: str, principal_id: str, agent_id: str,
        ) -> object:
            if (principal_id, agent_id) != (operator_id, agent_id_outer):
                raise LocalLevel2AuthorityError("learned recurrence owner is unavailable")
            return candidate_service.admit_recurrence(
                group_id=group_id,
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id=principal_id, agent_id=agent_id,
                ),
            )

    agent_id_outer = agent_id
    # A missing model/API key leaves observation pending by design.  The
    # candidate admitter belongs to the service-owned observer runner and is
    # installed only when that runner (and its durable repositories) exists.
    # The evaluation/replay path itself remains fully local and no-key.
    if service._coverage_observer_runner is not None:
        service.install_eligible_recurrence_candidate_admitter(
            _InstalledRecurrenceCandidateAdmitter()
        )
    completed_runtime = HermesCompletedTurnRuntime(
        service=service,
        installation_id=authorization.installation_id,
        issue_host_ingress=issue_completed_turn_ingress,
        scoped_read_authority=scoped_read_authority,
        require_current_authority=require_current_authority,
        project_task_id=project_task_id,
        authenticated_agent_id=agent_id,
        authenticated_author_id=operator_id,
        structured_authority_request=(
            structured_resolver.issued_authority_request() if structured_resolver is not None else None
        ),
        structured_tool_is_current=(
            (lambda: authority_is_current() and _structured_tool_is_current(hermes_home))
            if structured_resolver is not None else None
        ),
        structured_fact_read_authority=(
            structured_resolver.issued_read_authority if structured_resolver is not None else None
        ),
        preference_service=preference_service,
        recover_pending_on_start=_recover_pending_semantic_work,
    )
    replay_writer.runtime = completed_runtime
    paired_evaluator.bind_executor(IsolatedMentorsEvaluationExecutor(
        run_isolated_cases=lambda proposal, cases, binding_digest, corpus_digest, budget_digest: (
            _isolated_mentors_evaluation_cases(
                proposal, cases, binding_digest, corpus_digest, budget_digest, context,
            )
        ),
    ))
    learned_scope = AgentLocalCatalogAuthorityScope(
        principal_id=operator_id, agent_id=agent_id,
    )
    # Startup owns the two selection crash windows.  Recovery only retries
    # immutable retained evidence through the same installed writer root.
    learned_runtime.recover(learned_scope)

    def activate_learned_candidate(proposal_id: str) -> OntologyActivation:
        activation = learned_runtime.activate_candidate(
            proposal_id=proposal_id, principal_id=operator_id, agent_id=agent_id,
        )
        if structured_resolver is None:
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        completed_runtime._structured_authority_request = structured_resolver.issued_authority_request()
        return activation

    def approve_learned_candidate(proposal_id: str) -> OntologyChangeProposal:
        return learned_runtime.approve_candidate(
            proposal_id=proposal_id, principal_id=operator_id, agent_id=agent_id,
        )

    def select_prior_learned_version(target_version_digest: str) -> OntologyActivation:
        """Select a prior version through the installed owner authority."""
        activation = learned_runtime.select_prior_version(
            catalog_scope=learned_scope,
            target_version_digest=target_version_digest,
            principal_id=operator_id,
            agent_id=agent_id,
        )
        if structured_resolver is None:
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        authority = structured_resolver.issued_authority()
        service.provision_structured_submission_authority(authority=authority)
        completed_runtime._structured_authority_request = structured_resolver.issued_authority_request()
        return activation

    return HermesProviderRuntimeBinding(
        service=service,
        issue_ingress=ingress_resolver.issue,
        completed_turn_runtime=completed_runtime,
        absent_author_id=operator_id,
        revoke_structured_submission_grant=(
            revoke_current_structured_grant if structured_resolver is not None else None
        ),
        activate_learned_candidate=activate_learned_candidate,
        approve_learned_candidate=approve_learned_candidate,
        select_prior_learned_version=select_prior_learned_version,
        learned_ontology_runtime=learned_runtime,
        learned_ontology_status=lambda: learned_runtime.status(learned_scope),
        issue_origin_receipt=ingress_resolver.issue_origin_receipt,
        issue_forwarding_receipt=ingress_resolver.issue_forwarding_receipt,
    )


def revoke_local_level2_structured_grant(*, context: object, grant_kind: str) -> None:
    """Run the verified local operator action before or after grant provisioning.

    The caller supplies only a closed grant-kind selector.  Factory composition
    derives the signed-in installation, operator, agent, and exact grant tuple
    from current authority artifacts before the public service performs its
    canonical durable revoke.
    """
    binding = _build_local_level2_runtime_binding(
        context,
        _provision_structured_authority=False,
        _allow_existing_operator_binding=True,
    )
    from memorii.integrations.hermes_runtime_binding import HermesProviderRuntimeBinding

    if type(binding) is not HermesProviderRuntimeBinding:
        raise RuntimeError("Hermes local revocation binding is invalid")
    action = binding.revoke_structured_submission_grant
    if not callable(action):
        raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
    try:
        action(grant_kind)
    finally:
        runtime = binding.completed_turn_runtime
        close = getattr(runtime, "close", None) if runtime is not None else None
        if callable(close):
            close()


@dataclass(frozen=True)
class _LocalLevel2IngressEvidence:
    session_id: str
    author_id: str
    agent_id: str
    origin_lineage_evidence: AuthenticatedOriginLineageEvidence | None = None


def _has_agent_local_learned_control(
    *, records: tuple[object, ...], scope: AgentLocalCatalogAuthorityScope,
) -> bool:
    """Return whether this owner has begun a learned catalog lifecycle.

    The pointer coordinate itself is scope-bound, so it remains an admission
    signal even if its payload was corrupted.  Versions and attempts use
    typed payloads because their record identities are content addressed.
    """
    if any(
        getattr(record, "memory_id", None) == learned_catalog_pointer_memory_id(scope)
        for record in records
    ):
        return True
    for record in records:
        source_kind = getattr(record, "source_kind", None)
        content = getattr(record, "content", None)
        if not isinstance(content, dict):
            continue
        try:
            if source_kind == "learned_ontology_catalog_version_v1":
                if OntologyCatalogVersion.model_validate(content["version"]).catalog_scope == scope:
                    return True
            elif (
                source_kind == "learned_ontology_activation_attempt_v1"
                and OntologyActivation.model_validate(content["activation"]).catalog_scope == scope
            ):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


class _LocalLevel2StructuredSubmissionResolver:
    """Issue only current local structured authority for the pinned account."""

    def __init__(
        self,
        *,
        installation_id: str,
        operator_id: str,
        agent_id: str,
        project_task_id: str,
        authority_is_current,
        structured_tool_is_current,
        memory_plane: MemoryPlaneService,
        paired_evaluation_authority: PairedEvaluationAuthority | None = None,
        paired_evaluation_bundle: PairedEvaluationCatalogBundle | None = None,
    ) -> None:
        self._installation_id = installation_id
        self._operator_id = operator_id
        self._agent_id = agent_id
        self._authority_is_current = authority_is_current
        self._structured_tool_is_current = structured_tool_is_current
        self._memory_plane = memory_plane
        if (paired_evaluation_authority is None) != (paired_evaluation_bundle is None):
            raise LocalLevel2AuthorityError("paired evaluation authority is incomplete")
        self._paired_evaluation_authority = paired_evaluation_authority
        self._paired_evaluation_bundle = paired_evaluation_bundle
        expected = AuthenticatedPrincipalAgent(principal_id=operator_id, agent_id=agent_id)
        catalog_scope = CatalogAuthorityScope(schema_version=1, kind="base")
        self._issued_request = StructuredSubmissionAuthorityRequest(
            authenticated=expected,
            source_grant=SourceScopeGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "source", f"task:{project_task_id}"),
                grant_version=1,
                source_scope=f"task:{project_task_id}",
                authenticated=expected,
            ),
            fact_grant=FactScopeGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "fact", f"user:{operator_id}"),
                grant_version=1,
                fact_scope=f"user:{operator_id}",
                authenticated=expected,
            ),
            catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "catalog_visibility", catalog_scope),
                grant_version=1,
                catalog_scope=catalog_scope,
                authenticated=expected,
                purpose="visibility_status",
            ),
        )
        self.resolver_binding_digest = sha256(
            (
                "memorii.hermes.local-level2.structured-submission-resolver.v1:"
                f"{installation_id}:{operator_id}:{agent_id}"
            ).encode()
        ).hexdigest()

    def _selected_catalog(self):
        if self._paired_evaluation_authority is not None:
            bundle = self._paired_evaluation_bundle
            assert bundle is not None
            authority = self._paired_evaluation_authority
            if (
                bundle.bundle_digest != authority.evaluation_bundle_digest
                or bundle.proposal_id != authority.proposal_id
                or bundle.catalog_scope != authority.catalog_scope
            ):
                raise CatalogAuthorityError("paired evaluation bundle is unavailable")
            return ResolvedCatalogAuthority(
                catalog_scope=bundle.catalog_scope,
                catalog_digest=bundle.version.catalog_digest,
                genesis_selection_digest=authority.authority_digest,
            )
        scope = AgentLocalCatalogAuthorityScope(
            principal_id=self._operator_id, agent_id=self._agent_id,
        )
        _revision, records = self._memory_plane.read_snapshot()
        try:
            bundle, _pointer = PackageIndexedCatalogBundleLocator().locate_selected(
                records,
                scope=scope,
                authenticated=AuthenticatedPrincipalAgent(
                    principal_id=self._operator_id, agent_id=self._agent_id,
                ),
            )
        except CatalogAuthorityError:
            # A base catalog remains selectable until this owner has any
            # learned control state.  Once a learned pointer, version, or
            # activation exists, an invalid selected closure must deny this
            # request rather than silently reinterpreting it as base state.
            if _has_agent_local_learned_control(records=records, scope=scope):
                raise
            return ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
        return bundle.catalog

    def _request_for_catalog(self, catalog) -> StructuredSubmissionAuthorityRequest:
        expected = self._issued_request.authenticated
        return StructuredSubmissionAuthorityRequest(
            authenticated=expected,
            source_grant=self._issued_request.source_grant,
            fact_grant=self._issued_request.fact_grant,
            catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                grant_id=_grant_id(self._installation_id, self._operator_id, self._agent_id, "catalog_visibility", catalog.catalog_scope),
                grant_version=1,
                catalog_scope=catalog.catalog_scope,
                authenticated=expected,
                purpose="visibility_status",
            ),
            expected_catalog_digest=catalog.catalog_digest,
        )

    def resolve_submission_authority(
        self,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
        request: StructuredSubmissionAuthorityRequest,
    ) -> ResolvedStructuredSubmissionAuthority | None:
        if not self._authority_is_current():
            return None
        if not self._structured_tool_is_current():
            return None
        expected = self._issued_request.authenticated
        try:
            catalog = self._selected_catalog()
            expected_request = self._request_for_catalog(catalog)
        except ValueError:
            return None
        if (
            request != expected_request
            or authenticated_ingress.delivery_principal_binding.principal_subject_id != self._operator_id
            or authenticated_ingress.authenticated_agent_id != self._agent_id
        ):
            return None
        if request.expected_catalog_digest != catalog.catalog_digest:
            return None
        return ResolvedStructuredSubmissionAuthority(
            authenticated=expected,
            source_grant=request.source_grant,
            fact_grant=request.fact_grant,
            catalog_visibility_grant=request.catalog_visibility_grant,
            catalog=catalog,
            provider_model_prompt_provenance_digest=(request.provider_model_prompt_provenance_digest),
            paired_evaluation_authority=self._paired_evaluation_authority,
            paired_evaluation_bundle=(
                self._paired_evaluation_bundle.model_dump(mode="python")
                if self._paired_evaluation_bundle is not None else None
            ),
        )

    def issued_authority(self) -> ResolvedStructuredSubmissionAuthority:
        """Return the exact local tuple that this resolver will accept."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        catalog = self._selected_catalog()
        return ResolvedStructuredSubmissionAuthority(
            authenticated=self._issued_request.authenticated,
            source_grant=self._issued_request.source_grant,
            fact_grant=self._issued_request.fact_grant,
            catalog_visibility_grant=self._request_for_catalog(catalog).catalog_visibility_grant,
            catalog=catalog,
            paired_evaluation_authority=self._paired_evaluation_authority,
            paired_evaluation_bundle=(
                self._paired_evaluation_bundle.model_dump(mode="python")
                if self._paired_evaluation_bundle is not None else None
            ),
        )

    def issued_authority_request(self) -> StructuredSubmissionAuthorityRequest:
        """Return the factory-owned request the resolver alone will attest."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        return self._request_for_catalog(self._selected_catalog())

    def issued_read_authority(self) -> StructuredFactReadAuthority | None:
        """Issue the current fact/catalog grant pair for one protected read."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            return None
        request = self.issued_authority_request()
        return StructuredFactReadAuthority(
            authenticated=request.authenticated,
            fact_grant=request.fact_grant,
            catalog_visibility_grant=request.catalog_visibility_grant,
            paired_evaluation_authority=self._paired_evaluation_authority,
            paired_evaluation_bundle=(
                self._paired_evaluation_bundle.model_dump(mode="python")
                if self._paired_evaluation_bundle is not None else None
            ),
        )


class _LocalLevel2IngressResolver:
    """Translate the authenticated Hermes callback into the local trial authority."""

    def __init__(self, *, installation_id: str, operator_id: str) -> None:
        self._installation_id = installation_id
        self._operator_id = operator_id
        self._origin_receipt_lock = RLock()
        self._issued_origin_receipts: dict[str, HermesOriginReceipt] = {}

    def issue_origin_receipt(
        self,
        session_id: str,
        turn_ordinal: int,
        author_id: str,
        source_content_digest: str,
    ) -> HermesAuthenticatedOriginReceipt:
        if author_id != self._operator_id:
            raise ValueError("Hermes origin receipt author is substituted")
        receipt = HermesAuthenticatedOriginReceipt.create(
            session_id=session_id,
            turn_ordinal=turn_ordinal,
            author_id=author_id,
            source_content_digest=source_content_digest,
        )
        with self._origin_receipt_lock:
            self._issued_origin_receipts[receipt.receipt_digest] = receipt
        return receipt

    def issue_forwarding_receipt(
        self,
        origin_receipt: HermesAuthenticatedOriginReceipt,
        child_session_id: str,
        child_source_content_digest: str,
    ) -> HermesAuthenticatedForwardingReceipt:
        with self._origin_receipt_lock:
            if (
                self._issued_origin_receipts.get(origin_receipt.receipt_digest)
                != origin_receipt
            ):
                raise ValueError("Hermes forwarding origin was not factory-issued")
            receipt = HermesAuthenticatedForwardingReceipt.create(
                origin_receipt=origin_receipt,
                child_session_id=child_session_id,
                child_source_content_digest=child_source_content_digest,
            )
            self._issued_origin_receipts[receipt.receipt_digest] = receipt
            return receipt

    def issue(self, request: object) -> AuthenticatedHostIngress:
        session_id = getattr(request, "session_id", None)
        user_id = getattr(request, "user_id", None)
        received_at = getattr(request, "received_at", None)
        agent_id = getattr(request, "agent_id", None)
        hook = getattr(request, "hook", None)
        upstream_origin_receipt = getattr(request, "upstream_origin_receipt", None)
        if agent_id is None:
            agent_id = _canonical_agent_id(getattr(request, "agent_identity", None))
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(received_at, datetime):
            raise TypeError("Hermes ingress request is invalid")
        author = user_id.strip() if isinstance(user_id, str) else ""
        if author != self._operator_id:
            raise ValueError("Hermes local Level 2 operator identity is substituted")
        if not isinstance(agent_id, str) or not agent_id:
            raise TypeError("Hermes agent identity is invalid")
        origin_lineage_evidence = None
        if upstream_origin_receipt is not None:
            with self._origin_receipt_lock:
                issued_receipt = self._issued_origin_receipts.get(
                    getattr(upstream_origin_receipt, "receipt_digest", "")
                )
            if (
                hook not in {"sync_turn", "delegation"}
                or not isinstance(
                    upstream_origin_receipt,
                    (HermesAuthenticatedOriginReceipt, HermesAuthenticatedForwardingReceipt),
                )
                or not upstream_origin_receipt.verify()
                or issued_receipt != upstream_origin_receipt
            ):
                raise ValueError("Hermes upstream origin receipt is invalid")
            origin_receipt = (
                upstream_origin_receipt.origin_receipt
                if isinstance(
                    upstream_origin_receipt, HermesAuthenticatedForwardingReceipt
                )
                else upstream_origin_receipt
            )
            if (
                origin_receipt.author_id != author
                or (
                    isinstance(
                        upstream_origin_receipt,
                        HermesAuthenticatedForwardingReceipt,
                    )
                    and upstream_origin_receipt.child_session_id != session_id
                )
            ):
                raise ValueError("Hermes upstream origin receipt is invalid")
            origin_lineage_evidence = AuthenticatedOriginLineageEvidence.create(
                authority_digest=sha256(
                    b"memorii.hermes.local-origin-authority.v1\0"
                    + encode_typed_value(
                        (self._installation_id, self._operator_id, agent_id)
                    )
                ).hexdigest(),
                origin_receipt_digest=sha256(
                    b"memorii.hermes.local-origin-receipt.v1\0"
                    + encode_typed_value(
                        (
                            self._installation_id,
                            self._operator_id,
                            agent_id,
                            origin_receipt.session_id,
                            origin_receipt.turn_ordinal,
                            origin_receipt.source_content_digest,
                            origin_receipt.receipt_digest,
                        )
                    )
                ).hexdigest(),
            )
        evidence = _LocalLevel2IngressEvidence(
            session_id=session_id,
            author_id=author,
            agent_id=agent_id,
            origin_lineage_evidence=origin_lineage_evidence,
        )
        return AuthenticatedHostIngress(
            provider_identity="hermes",
            principal_handle=evidence,
            session_handle=evidence,
            received_at=received_at,
        )

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        if (
            host_ingress.provider_identity != "hermes"
            or not isinstance(host_ingress.principal_handle, _LocalLevel2IngressEvidence)
            or host_ingress.principal_handle is not host_ingress.session_handle
            or server_time.tzinfo is None
        ):
            raise ValueError("Hermes local Level 2 ingress is invalid")
        if host_ingress.received_at.tzinfo is None:
            raise ValueError("Hermes local Level 2 ingress timestamp is invalid")
        evidence = host_ingress.principal_handle
        scopes = RequiredOutcomeScopeSet.create(
            tenant_partition_id=f"local:{self._installation_id}",
            scopes={
                f"session:{evidence.session_id}",
                f"user:{evidence.author_id}",
            },
        )
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id=evidence.author_id,
            tenant_partition_id=scopes.tenant_partition_id,
            provider_identity="hermes",
        )
        provenance = sha256(f"memorii.local-level2:{self._installation_id}:{evidence.author_id}".encode()).hexdigest()
        return AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            authenticated_agent_id=evidence.agent_id,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
            language_declaration="en",
            language_evidence_kind="authenticated_host_declaration",
            language_evidence_trust="trusted",
            language_governance_agreement="agrees",
            semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
                classification="local_level2_project_assertions",
                provider="openai",
                model="gpt-4.1-nano",
                region="operator-configured",
                retention_mode="store_false",
                training_use=False,
            ),
            semantic_source_authority=AuthenticatedSemanticSourceAuthority(
                authority_class="official",
                authenticated_provenance_class="authenticated_user",
                governing_principal_id=evidence.author_id,
                policy_revision="bootstrap-v3-local-level2",
                provenance_digest=provenance,
            ),
            semantic_source_interval=AuthenticatedSemanticSourceInterval(
                # The host-signed completion instant is the source interval
                # coordinate.  Replaying a delivery must reconstruct the same
                # Step-1 material; the current server time is only used to
                # validate this ingress call above.
                start=host_ingress.received_at,
                end=None,
                authority_basis="server_source_metadata",
                provenance_digest=provenance,
                policy_revision="bootstrap-v3-local-level2",
            ),
            origin_lineage_evidence=evidence.origin_lineage_evidence,
        )


def _canonical_agent_id(value: object) -> str:
    if value is None:
        return "memorii.hermes.agent.absent.v1"
    if isinstance(value, str):
        if not value.strip() or unicodedata.normalize("NFC", value) != value:
            raise LocalLevel2AuthorityError("Hermes agent identity is invalid")
        payload = value
    else:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise LocalLevel2AuthorityError("Hermes agent identity is invalid") from exc
    return "memorii:hermes:agent:" + sha256(b"memorii.hermes.agent-identity.v1\0" + payload.encode("utf-8")).hexdigest()


def _project_task_id(installation_id: str, semantic_contract_digest: str) -> str:
    return (
        "memorii:hermes:task:"
        + sha256(
            (f"memorii.hermes.project_assertions.task.v1:{installation_id}:{semantic_contract_digest}").encode()
        ).hexdigest()
    )


def _grant_id(
    installation_id: str,
    operator_id: str,
    agent_id: str,
    grant_kind: str,
    scope: str | CatalogAuthorityCoordinate,
) -> str:
    """Derive the stable v1 grant coordinate from verified factory inputs."""
    digest = sha256(
        b"memorii.hermes.local-structured-grant.v1\0"
        + encode_typed_value(
            (
                installation_id,
                operator_id,
                agent_id,
                grant_kind,
                scope.model_dump(mode="python")
                if isinstance(scope, (CatalogAuthorityScope, AgentLocalCatalogAuthorityScope))
                else scope,
            )
        )
    ).hexdigest()
    return f"hermes-local-structured-grant:v1:{grant_kind}:{digest}"


def _structured_tool_is_current(hermes_home: Path) -> bool:
    try:
        load_local_structured_tool_authority(hermes_home=hermes_home, now=datetime.now(UTC))
    except (OSError, TypeError, ValueError):
        return False
    return True


def _require_local_cli_context(context: object) -> str:
    """Classify the primary or explicitly delegated Hermes CLI context."""

    kind = getattr(context, "agent_context", None)
    parent = getattr(context, "parent_session_id", None)
    if getattr(context, "platform", None) != "cli" or kind not in {"primary", "delegated"}:
        raise LocalLevel2AuthorityError("local Level 2 requires Hermes CLI execution")
    if kind == "primary" and (
        getattr(context, "agent_workspace", None) != "hermes" or parent is not None
    ):
        raise LocalLevel2AuthorityError("local Level 2 primary context is invalid")
    if kind == "delegated" and (not isinstance(parent, str) or not parent.strip()):
        raise LocalLevel2AuthorityError("local Level 2 delegated context is invalid")
    return kind


def _bind_single_local_operator_context(
    *,
    storage_root: Path,
    installation_id: str,
    raw_user_id: object,
    agent_id: str,
    context_kind: str,
    allow_existing_operator_binding: bool = False,
) -> str:
    """Use raw Hermes identity only to deny multi-user reuse of one local profile."""

    raw_user = raw_user_id.strip() if isinstance(raw_user_id, str) else ""
    if raw_user_id is not None and not raw_user:
        raise LocalLevel2AuthorityError("Hermes raw user consistency value is invalid")
    binding = {
        "schema": "memorii.hermes.local-operator-context.v1",
        "installation_id": installation_id,
        "primary_agent_id": agent_id,
        "raw_user_consistency_digest": sha256(
            b"memorii.hermes.raw-user-consistency.v1\0" + raw_user.encode("utf-8")
        ).hexdigest(),
    }
    if context_kind != "primary" and not (storage_root / "local-operator-context.json").exists():
        raise LocalLevel2AuthorityError("local Level 2 primary context must initialize the profile")
    payload = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    storage_root.mkdir(parents=True, exist_ok=True)
    path = storage_root / "local-operator-context.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = json.loads(path.read_bytes())
        except (OSError, TypeError, ValueError) as exc:
            raise LocalLevel2AuthorityError("local Level 2 operator context is invalid") from exc
        if (
            not isinstance(existing, dict)
            or existing.get("schema") != "memorii.hermes.local-operator-context.v1"
            or existing.get("installation_id") != installation_id
            or not isinstance(existing.get("raw_user_consistency_digest"), str)
            or not isinstance(existing.get("primary_agent_id"), str)
        ):
            raise LocalLevel2AuthorityError("local Level 2 operator context is invalid") from None
        if raw_user_id is None and allow_existing_operator_binding:
            return existing["primary_agent_id"]
        if existing["raw_user_consistency_digest"] != binding["raw_user_consistency_digest"]:
            raise LocalLevel2AuthorityError(
                "local Level 2 profile is already bound to another Hermes user context"
            ) from None
        if context_kind == "primary" and existing["primary_agent_id"] != agent_id:
            raise LocalLevel2AuthorityError("local Level 2 primary agent identity is substituted") from None
        return existing["primary_agent_id"]
    if raw_user_id is None and allow_existing_operator_binding:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise LocalLevel2AuthorityError("local Level 2 operator context is absent")
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return agent_id


__all__ = ["build_local_level2_runtime_binding", "revoke_local_level2_structured_grant"]
