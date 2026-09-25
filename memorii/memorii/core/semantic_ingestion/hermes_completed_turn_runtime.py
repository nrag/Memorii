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
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
)
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
    HermesCompletedTurnAdmission,
    HermesCompletedTurnAdmissionRequest,
    HermesCompletedTurnAdmissionService,
    HermesCompletedTurnMessage,
)
from memorii.domain.enums import MemoryDomain

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CompletedTurnWork:
    admitted: HermesCompletedTurnAdmission
    ingress: AuthenticatedIngressContext


@dataclass(frozen=True)
class _RecoverySweep:
    pass


@dataclass(frozen=True)
class _StopWorker:
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
        self._work: queue.Queue[_CompletedTurnWork | _RecoverySweep | _StopWorker] = queue.Queue()
        self._condition = threading.Condition()
        self._outstanding = 0
        self._failures: list[BaseException] = []
        self._closed = False
        self._stopped = False
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
        with self._condition:
            if self._closed:
                raise RuntimeError("Hermes semantic worker is closed")
        author = authenticated_author_id.strip() if isinstance(authenticated_author_id, str) else ""
        if author != self._authenticated_author_id or received_at.tzinfo is None:
            raise ValueError("Hermes completed-turn authentication is incomplete")
        # Re-open the installation authority immediately before any ingress,
        # egress, or durable operation. A changed/expired sidecar fails closed.
        self._require_current_authority()
        canonical_messages = _canonicalize_completed_messages(
            messages=messages, user_content=user_content, assistant_content=assistant_content
        )
        # Hermes may redeliver the same persisted completion after the callback
        # clock has advanced.  Source retention is bound to the transcript's
        # final persisted timestamp, never to the callback delivery time.
        completed_at = _completed_turn_timestamp(canonical_messages)
        ordinal = sum(1 for item in canonical_messages if item["role"] == "assistant")
        host_ingress = self._issue_host_ingress(session_id, author, completed_at)
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
            completed_at=completed_at,
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
            if self._closed:
                raise RuntimeError("Hermes semantic worker is closed")
            self._outstanding += 1
        self._work.put(work)

    def _worker_loop(self) -> None:
        while True:
            work = self._work.get()
            if isinstance(work, _StopWorker):
                self._work.task_done()
                return
            try:
                if isinstance(work, _RecoverySweep):
                    self._recover_pending()
                    with self._condition:
                        # A successful reconciliation resolves every retained
                        # post-admission failure before a caller can observe idle.
                        self._failures.clear()
                else:
                    self._process(work)
            except Exception as exc:
                logger.exception("hermes_completed_turn_semantic_worker_failed")
                with self._condition:
                    self._failures.append(exc)
                if isinstance(work, _CompletedTurnWork):
                    # A work failure can leave admitted V3 state pending after
                    # its lease. Reconcile once; a failed sweep stays visible
                    # and never schedules an unbounded recovery loop.
                    self._enqueue(_RecoverySweep())
            finally:
                with self._condition:
                    self._outstanding -= 1
                    self._condition.notify_all()
                self._work.task_done()

    def close(self, *, timeout: float = 1200.0) -> None:
        """Drain admitted work, stop the daemon, and reject future ingress."""
        with self._condition:
            if self._stopped:
                return
            self._closed = True
        try:
            self.wait_for_idle(timeout=timeout)
        finally:
            self._work.put(_StopWorker())
            self._worker.join(timeout=timeout)
            if self._worker.is_alive():
                raise TimeoutError("Hermes semantic worker did not stop")
            with self._condition:
                self._stopped = True

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
        """Wait for admitted work and surface an unresolved worker failure."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._outstanding:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Hermes semantic worker did not become idle")
                self._condition.wait(remaining)
            if self._failures:
                failure = self._failures[0]
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
            tool_calls = item.get("tool_calls", ())
            if not isinstance(tool_calls, tuple):
                raise ValueError("Hermes assistant tool calls are invalid")
            for call in tool_calls:
                if not isinstance(call, dict) or not isinstance(call.get("id"), str):
                    raise ValueError("Hermes assistant tool calls are invalid")
                pending_calls.add(call["id"])
        elif item["role"] == "tool":
            call_id = item["tool_call_id"]
            if not isinstance(call_id, str) or call_id not in pending_calls:
                raise ValueError("Hermes tool message is unmatched")
            pending_calls.remove(call_id)
    if pending_calls:
        raise ValueError("Hermes transcript has unmatched tool calls")
    return canonical


def _canonicalize_message(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("Hermes transcript message is not a closed object")
    role = value.get("role")
    if role not in {"system", "developer", "user", "assistant", "tool"}:
        raise ValueError("Hermes transcript role is unsupported")
    persistence_fields = {"timestamp", "_db_persisted", "_row_id"}
    allowed_fields = {
        "system": {"role", "content", *persistence_fields},
        "developer": {"role", "content", *persistence_fields},
        "user": {
            "role", "content", *persistence_fields, "display_kind", "display_metadata",
            "platform_message_id", "api_content",
        },
        "assistant": {
            "role", "content", *persistence_fields, "reasoning", "finish_reason",
            "reasoning_content", "reasoning_details", "anthropic_content_blocks",
            "bedrock_content_blocks", "codex_reasoning_items", "codex_message_items",
            "api_content", "tool_calls",
        },
        "tool": {
            "role", "content", *persistence_fields, "tool_call_id", "name", "tool_name",
            "_tool_output_risk", "effect_disposition",
        },
    }
    unexpected_fields = set(value) - allowed_fields[role]
    if unexpected_fields:
        fields = ", ".join(sorted(unexpected_fields))
        raise ValueError(f"Hermes transcript {role} message has unsupported fields: {fields}")
    if role in {"system", "developer", "user"}:
        content = _canonical_text(value.get("content"))
        return _with_canonical_timestamp({"role": role, "content": content}, value)
    if role == "tool":
        content = _canonical_text(value.get("content"))
        if "tool_call_id" not in value:
            raise ValueError("Hermes tool message has invalid fields")
        call_id = _canonical_text(value.get("tool_call_id"))
        return _with_canonical_timestamp(
            {"role": role, "content": content, "tool_call_id": call_id}, value
        )
    content_value = value.get("content")
    textless_tool_call = content_value == "" and "tool_calls" in value
    content = "" if textless_tool_call else _canonical_text(content_value)
    result: dict[str, object] = {"role": role, "content": content}
    if "tool_calls" in value:
        calls = value["tool_calls"]
        if type(calls) is not list or not calls:
            raise ValueError("Hermes assistant tool calls are invalid")
        result["tool_calls"] = tuple(_canonicalize_tool_call(call) for call in calls)
    return _with_canonical_timestamp(result, value)


def _with_canonical_timestamp(result: dict[str, object], raw: dict[str, object]) -> dict[str, object]:
    """Retain only a validated, canonical persisted Hermes message timestamp."""
    if "timestamp" in raw:
        result["timestamp"] = _canonical_timestamp(raw["timestamp"])
    return result


def _completed_turn_timestamp(canonical_messages: tuple[dict[str, object], ...]) -> datetime:
    """Return the immutable timestamp bound to the final persisted completion."""
    final_timestamp = canonical_messages[-1].get("timestamp")
    if not isinstance(final_timestamp, str):
        raise ValueError("Hermes completed-turn transcript is missing its final timestamp")
    return _parse_canonical_timestamp(final_timestamp)


def _canonical_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Hermes transcript timestamp is invalid")
    return _parse_canonical_timestamp(value).isoformat().replace("+00:00", "Z")


def _parse_canonical_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Hermes transcript timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Hermes transcript timestamp is invalid")
    return parsed.astimezone(UTC)


def _canonicalize_tool_call(value: object) -> dict[str, str]:
    if (
        type(value) is not dict
        or set(value) - {"id", "call_id", "response_item_id", "type", "function", "extra_content"}
        or value.get("type") != "function"
        or "id" not in value
        or "function" not in value
    ):
        raise ValueError("Hermes assistant tool call is invalid")
    function = value["function"]
    if type(function) is not dict or set(function) != {"name", "arguments"}:
        raise ValueError("Hermes assistant tool function is invalid")
    arguments = _canonical_text(function["arguments"])
    try:
        parsed = json.loads(
            arguments,
            object_pairs_hook=_reject_duplicate_json_object_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        canonical_arguments = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Hermes tool arguments are not valid JSON") from exc
    return {
        "id": _canonical_text(value["id"]),
        "type": "function",
        "name": _canonical_text(function["name"]),
        "arguments": canonical_arguments,
    }


def _reject_duplicate_json_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Hermes tool arguments contain duplicate object keys")
        result[key] = value
    return result


def _canonical_text(value: object) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        raise ValueError("Hermes transcript strings must be nonblank NFC text")
    return value


def _canonical_messages_digest(messages: tuple[dict[str, object], ...]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(b"memorii.hermes.completed-turn.transcript.v1\0" + payload).hexdigest()


__all__ = ["HermesCompletedTurnRuntime"]
