"""Hermes completed-turn bridge to the canonical Bootstrap V3 execution owner."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_hex

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import (
    InProcessScopedReadAuthority,
    ScopedNamespaceGrantRow,
)
from memorii.core.scoped_context.contracts import (
    ScopedContextBudget,
    ScopedContextRequest,
    ScopedContextStatus,
)
from memorii.core.semantic_ingestion.hermes_completed_turn_admission import (
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
)
from memorii.domain.enums import MemoryDomain

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CompletedTurnWork:
    admitted: object
    ingress: object


@dataclass(frozen=True)
class _RecoverySweep:
    pass


class HermesCompletedTurnRuntime:
    """Run one authenticated, complete Hermes turn through existing V3 owners."""

    def __init__(
        self,
        *,
        service: ProviderMemoryService,
        installation_id: str,
        issue_host_ingress: Callable[[str, str, datetime], AuthenticatedHostIngress],
        scoped_read_authority: InProcessScopedReadAuthority,
        require_current_authority: Callable[[], None],
        project_task_id: str,
        authenticated_agent_id: str,
        authenticated_author_id: str,
    ) -> None:
        self._service = service
        self._installation_id = installation_id
        self._issue_host_ingress = issue_host_ingress
        self._scoped_read_authority = scoped_read_authority
        self._require_current_authority = require_current_authority
        self._project_task_id = project_task_id
        self._authenticated_agent_id = authenticated_agent_id
        self._authenticated_author_id = authenticated_author_id
        self._work: queue.Queue[_CompletedTurnWork | _RecoverySweep] = queue.Queue()
        self._condition = threading.Condition()
        self._outstanding = 0
        self._failures: list[BaseException] = []
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="memorii-hermes-semantic-worker",
            daemon=True,
        )
        self._worker.start()
        self._enqueue(_RecoverySweep())

    def sync_completed_turn(
        self,
        *,
        user_content: str,
        assistant_content: str,
        messages: list[dict[str, object]] | None,
        session_id: str,
        authenticated_author_id: str | None,
        received_at: datetime,
    ) -> None:
        author = authenticated_author_id.strip() if isinstance(authenticated_author_id, str) else ""
        if author != self._authenticated_author_id or received_at.tzinfo is None:
            raise ValueError("Hermes completed-turn authentication is incomplete")
        # Re-open the installation authority immediately before any ingress,
        # egress, or durable operation. A changed/expired sidecar fails closed.
        self._require_current_authority()
        canonical_messages = _canonicalize_completed_messages(
            messages=messages, user_content=user_content, assistant_content=assistant_content
        )
        ordinal = sum(1 for item in canonical_messages if item["role"] == "assistant")
        host_ingress = self._issue_host_ingress(session_id, author, received_at)
        ingress = self._service._preflight_ingress(host_ingress)
        if ingress is None:
            raise ValueError("Hermes completed-turn ingress is unavailable")
        request = HermesCompletedTurnAdmissionRequest(
            installation_id=self._installation_id,
            session_id=session_id,
            authenticated_author_id=author,
            authenticated_agent_id=self._authenticated_agent_id,
            project_task_namespace=self._project_task_id,
            turn_ordinal=ordinal,
            canonical_transcript_digest=_canonical_messages_digest(canonical_messages),
            completed_messages=(
                HermesCompletedTurnMessage(role="user", content=user_content),
                HermesCompletedTurnMessage(role="assistant", content=assistant_content),
            ),
            completed_at=received_at,
            ingress=ingress,
        )
        binding = self._service._semantic_writer_admission.commit_binding(
            self._service._semantic_writer_admission.current()
        )
        admitted = HermesCompletedTurnAdmissionService(
            atomic_store=self._service._semantic_atomic_store, writer_binding=binding
        ).admit(request)
        self._enqueue(_CompletedTurnWork(admitted=admitted, ingress=ingress))

    def _enqueue(self, work: _CompletedTurnWork | _RecoverySweep) -> None:
        with self._condition:
            self._outstanding += 1
        self._work.put(work)

    def _worker_loop(self) -> None:
        while True:
            work = self._work.get()
            try:
                if isinstance(work, _RecoverySweep):
                    self._recover_pending()
                else:
                    self._process(work)
            except Exception as exc:
                logger.exception("hermes_completed_turn_semantic_worker_failed")
                with self._condition:
                    self._failures.append(exc)
            finally:
                with self._condition:
                    self._outstanding -= 1
                    self._condition.notify_all()
                self._work.task_done()

    def _recover_pending(self) -> None:
        """Resume retained V3 work after the prior claim's short lease expires."""
        deadline = time.monotonic() + 65.0
        while True:
            self._require_current_authority()
            outcomes = self._service.reconcile_memory_evolution()
            retryable = [outcome for outcome in outcomes if outcome.retryable]
            if not retryable:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Hermes semantic recovery remained pending")
            time.sleep(1.0)

    def _process(self, work: _CompletedTurnWork) -> None:
        admitted = work.admitted
        ingress = work.ingress
        user_admission = admitted.normalization_inputs.source_admissions[0]
        coordinator = self._service._provider_ingestion
        with self._service._new_canonical_evidence_arena() as arena:
            handoff_with_lease = coordinator._bootstrap_prepare_and_handoff(
                prepared_admission=user_admission,
                authenticated_ingress=ingress,
                canonical_evidence_arena=arena,
            )
            if handoff_with_lease is None:
                raise ValueError("Hermes completed-turn Bootstrap handoff is unavailable")
            handoff, evidence_lease = handoff_with_lease
            try:
                terminal, guard = coordinator._run_semantic_ingestion(
                    operation_id=user_admission.operation_fence_binding.operation_id,
                    observation=user_admission.observation,
                    authenticated_ingress=ingress,
                    lease_session=None,
                    operation_fence=user_admission.operation_fence_binding,
                    bootstrap_handoff=handoff,
                    canonical_evidence_arena=arena,
                    canonical_evidence_lease=evidence_lease,
                )
            finally:
                if evidence_lease is not None:
                    evidence_lease.release()
        if "bootstrap_graph_terminal_persisted" not in terminal.reason_codes:
            raise RuntimeError(
                "Hermes completed-turn Bootstrap graph did not persist: "
                + ",".join(terminal.reason_codes)
            )

    def wait_for_idle(self, *, timeout: float = 1200.0) -> None:
        """Wait for admitted work and surface the first worker failure."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._outstanding:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Hermes semantic worker did not become idle")
                self._condition.wait(remaining)
            if self._failures:
                failure = self._failures.pop(0)
                raise RuntimeError("Hermes semantic worker failed") from failure

    def prefetch(self, *, query: str, session_id: str, authenticated_author_id: str, now: datetime) -> str:
        """Read committed semantic context through one fresh host-bound grant."""
        author = authenticated_author_id.strip()
        if (
            not query.strip()
            or author != self._authenticated_author_id
            or now.tzinfo is None
        ):
            return ""
        self._require_current_authority()
        task_id = self._project_task_id
        state_id = sha256(
            (
                "memorii.hermes.prefetch.v1:"
                f"{task_id}:{session_id}:{author}:{self._authenticated_agent_id}:"
                f"{query}:{now.isoformat()}:{token_hex(16)}"
            ).encode()
        ).hexdigest()
        rows = (ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC,
            task_id=task_id,
            session_id=None,
            user_id=author,
            agent_id=self._authenticated_agent_id,
            execution_node_id=None,
            solver_run_id=None,
        ),)
        handle = self._scoped_read_authority.provision(
            host_task_id=task_id,
            host_state_id=state_id,
            rows=rows,
            expires_at=now.replace(microsecond=0) + timedelta(minutes=1),
        )
        try:
            activation = self._service.retrieve_context(
                ScopedContextRequest(
                    host_task_id=task_id,
                    host_state_id=state_id,
                    declared_complete_mandatory_set=True,
                    mandatory_record_references=(),
                    optional_query=query,
                    optional_domains=(MemoryDomain.SEMANTIC,),
                    budget=ScopedContextBudget(
                        max_mandatory_items=1,
                        max_optional_items=8,
                        max_optional_omission_ids=8,
                        max_rendered_utf8_bytes=4096,
                    ),
                    reference_time=now,
                ),
                opaque_host_ingress=handle,
            )
        finally:
            self._scoped_read_authority.revoke(handle)
        if activation.status not in {ScopedContextStatus.COMPLETE, ScopedContextStatus.PARTIAL_OPTIONAL}:
            return ""
        return "\n".join(item.rendered_text for item in activation.optional_items)


def _canonicalize_completed_messages(
    *, messages: list[dict[str, object]] | None, user_content: str, assistant_content: str
) -> tuple[dict[str, object], ...]:
    """Validate the closed Hermes ABI and return its canonical full transcript."""
    if not messages or len(messages) < 2:
        raise ValueError("Hermes completed-turn transcript is incomplete")
    canonical = tuple(_canonicalize_message(item) for item in messages)
    if canonical[-1]["role"] != "assistant" or canonical[-1]["content"] != assistant_content:
        raise ValueError("Hermes completed-turn transcript does not end in the supplied pair")
    preceding_users = [item for item in canonical[:-1] if item["role"] == "user"]
    if not preceding_users or preceding_users[-1]["content"] != user_content:
        raise ValueError("Hermes completed-turn transcript does not end in the supplied pair")
    pending_calls: set[str] = set()
    for item in canonical:
        if item["role"] == "assistant":
            pending_calls.update(call["id"] for call in item.get("tool_calls", ()))
        elif item["role"] == "tool":
            call_id = item["tool_call_id"]
            if call_id not in pending_calls:
                raise ValueError("Hermes tool message is unmatched")
            pending_calls.remove(call_id)
    if pending_calls:
        raise ValueError("Hermes transcript has unmatched tool calls")
    return canonical


def _canonicalize_message(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) - {"role", "content", "tool_calls", "tool_call_id"}:
        raise ValueError("Hermes transcript message is not a closed object")
    role = value.get("role")
    if role not in {"system", "developer", "user", "assistant", "tool"}:
        raise ValueError("Hermes transcript role is unsupported")
    content = _canonical_text(value.get("content"))
    if role in {"system", "developer", "user"}:
        if set(value) != {"role", "content"}:
            raise ValueError("Hermes transcript message has invalid role fields")
        return {"role": role, "content": content}
    if role == "tool":
        if set(value) != {"role", "content", "tool_call_id"}:
            raise ValueError("Hermes tool message has invalid fields")
        call_id = _canonical_text(value.get("tool_call_id"))
        return {"role": role, "content": content, "tool_call_id": call_id}
    if set(value) not in ({"role", "content"}, {"role", "content", "tool_calls"}):
        raise ValueError("Hermes assistant message has invalid fields")
    result: dict[str, object] = {"role": role, "content": content}
    if "tool_calls" in value:
        calls = value["tool_calls"]
        if type(calls) is not list or not calls:
            raise ValueError("Hermes assistant tool calls are invalid")
        result["tool_calls"] = tuple(_canonicalize_tool_call(call) for call in calls)
    return result


def _canonicalize_tool_call(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"id", "type", "function"} or value.get("type") != "function":
        raise ValueError("Hermes assistant tool call is invalid")
    function = value["function"]
    if type(function) is not dict or set(function) != {"name", "arguments"}:
        raise ValueError("Hermes assistant tool function is invalid")
    arguments = _canonical_text(function["arguments"])
    try:
        parsed = json.loads(arguments, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        canonical_arguments = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Hermes tool arguments are not canonical JSON") from exc
    if arguments != canonical_arguments:
        raise ValueError("Hermes tool arguments are not canonical JSON")
    return {"id": _canonical_text(value["id"]), "type": "function", "name": _canonical_text(function["name"]), "arguments": arguments}


def _canonical_text(value: object) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        raise ValueError("Hermes transcript strings must be nonblank NFC text")
    return value


def _canonical_messages_digest(messages: tuple[dict[str, object], ...]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(b"memorii.hermes.completed-turn.transcript.v1\0" + payload).hexdigest()


__all__ = ["HermesCompletedTurnRuntime"]
