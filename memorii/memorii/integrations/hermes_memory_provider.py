"""Optional NousResearch Hermes external-memory provider bridge.

This module is loaded by Hermes through its entry-point discovery mechanism.
It deliberately imports the Hermes ABC here, rather than from Memorii's normal
package roots, so installing or importing Memorii does not require Hermes.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.memory_provider import MemoryProvider  # pyright: ignore[reportMissingImports]

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider, build_started_hermes_memory_provider
from memorii.integrations.hermes_runtime_binding import HermesProviderRuntimeBinding

_SERVICE_FACTORY_ENTRY_POINT_GROUP = "memorii.hermes.provider_service"
_FIRST_PARTY_FACTORY_VALUE = "memorii.integrations.hermes_factory:build_local_level2_runtime_binding"


@dataclass(frozen=True)
class HermesProviderServiceContext:
    """Deployment-owned inputs for constructing one configured provider service."""

    storage_root: Path
    hermes_home: Path
    session_id: str
    user_id: str | None
    agent_identity: object | None
    agent_workspace: object | None
    parent_session_id: str | None


@dataclass(frozen=True)
class HermesIngressRequest:
    """Host evidence supplied to the deployment-owned ingress issuer."""

    hook: str
    session_id: str
    user_id: str | None
    agent_identity: object | None
    turn_author: dict[str, Any] | None
    received_at: datetime


class MemoriiHermesMemoryProvider(MemoryProvider):
    """Adapt Hermes lifecycle hooks to the canonical Memorii provider."""

    def __init__(self) -> None:
        self._provider: HermesMemoryProvider | None = None
        self._session_id = ""
        self._default_user_id: str | None = None
        self._turn_user_id: ContextVar[str | None] = ContextVar("memorii_hermes_turn_user_id", default=None)
        self._agent_identity: object | None = None
        self._issue_ingress: Callable[[HermesIngressRequest], AuthenticatedHostIngress] | None = None
        self._completed_turn_runtime: object | None = None
        self._absent_author_id = "memorii.hermes.author.absent.v1"

    @property
    def name(self) -> str:
        return "memorii"

    def is_available(self) -> bool:
        """Hermes discovery loads only the configured deployment factory."""

        return _service_factory_status()[0] is not None

    def unavailable_reason(self) -> str:
        """Explain unavailable external configuration without touching storage."""

        return _service_factory_status()[1] or ""

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        storage_root = _resolve_storage_root(hermes_home=kwargs.get("hermes_home"))
        resolved_session_id = _require_nonempty_text(session_id, "session_id")
        user_id = _optional_text(kwargs.get("user_id")) or _optional_text(kwargs.get("user_id_alt"))
        factory, reason = _service_factory_status()
        if factory is None:
            raise RuntimeError(f"Memorii Hermes provider is unavailable: {reason}")
        binding = factory(
            HermesProviderServiceContext(
                storage_root=storage_root,
                hermes_home=_path_from_value(kwargs.get("hermes_home"), "hermes_home"),
                session_id=resolved_session_id,
                user_id=user_id,
                agent_identity=kwargs.get("agent_identity"),
                agent_workspace=kwargs.get("agent_workspace"),
                parent_session_id=_optional_text(kwargs.get("parent_session_id")),
            )
        )
        if type(binding) is not HermesProviderRuntimeBinding:
            raise TypeError("Memorii Hermes service factory must return HermesProviderRuntimeBinding")
        if not isinstance(binding.service, ProviderMemoryService) or not callable(binding.issue_ingress):
            raise TypeError("Memorii Hermes runtime binding is invalid")
        provider = build_started_hermes_memory_provider(service=binding.service)
        self._provider = provider
        self._session_id = resolved_session_id
        self._default_user_id = user_id
        self._turn_user_id.set(user_id)
        self._agent_identity = kwargs.get("agent_identity")
        self._issue_ingress = binding.issue_ingress
        self._completed_turn_runtime = binding.completed_turn_runtime
        self._absent_author_id = binding.absent_author_id

    def get_tool_schemas(self) -> list[dict[str, object]]:
        return []

    def handle_tool_call(self, tool_name: str, arguments: dict[str, object]) -> object:
        del arguments
        raise ValueError(f"Memorii does not provide Hermes tool {tool_name!r}")

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        user_id = self._current_user_id()
        runtime = self._completed_turn_runtime
        prefetch = getattr(runtime, "prefetch", None) if runtime is not None else None
        if runtime is not None:
            if not callable(prefetch):
                raise TypeError("Memorii completed-turn runtime is invalid")
            return prefetch(
                query=query,
                session_id=self._effective_session_id(session_id),
                authenticated_author_id=self._absent_author_id,
                now=datetime.now(UTC),
            )
        return self._require_provider().prefetch(
            query,
            session_id=self._effective_session_id(session_id),
            user_id=user_id,
        )

    def on_turn_start(
        self,
        turn_number: int,
        message: str,
        **kwargs: Any,
    ) -> None:
        del turn_number, message
        self._require_provider()
        observed = _optional_text(kwargs.get("author_id"))
        if self._completed_turn_runtime is not None and observed is not None and observed != self._default_user_id:
            raise ValueError("Hermes local Level 2 author identity changed")
        self._turn_user_id.set(observed or self._default_user_id)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict[str, object]] | None = None,
        turn_author: dict[str, Any] | None = None,
    ) -> None:
        effective_session_id = self._effective_session_id(session_id)
        effective_user_id = (
            _optional_text(turn_author.get("id")) if turn_author is not None else None
        ) or self._current_user_id()
        runtime = self._completed_turn_runtime
        if runtime is not None:
            if effective_user_id is not None and effective_user_id != self._default_user_id:
                raise ValueError("Hermes local Level 2 author identity changed")
            sync = getattr(runtime, "sync_completed_turn", None)
            if not callable(sync):
                raise TypeError("Memorii completed-turn runtime is invalid")
            sync(
                user_content=user_content,
                assistant_content=assistant_content,
                messages=messages,
                session_id=effective_session_id,
                authenticated_author_id=self._absent_author_id,
                received_at=datetime.now(UTC),
            )
            return
        self._require_provider().sync_turn(
            user_content,
            assistant_content,
            operation_id=_operation_id(
                "sync_turn",
                effective_session_id,
                messages if messages is not None else [user_content, assistant_content],
            ),
            session_id=effective_session_id,
            user_id=effective_user_id,
            authenticated_host_ingress=self._require_ingress(
                hook="sync_turn",
                session_id=effective_session_id,
                user_id=effective_user_id,
                turn_author=turn_author,
            ),
        )

    def on_session_end(self, messages: list[dict[str, object]] | list[str]) -> None:
        self._require_provider().on_session_end(
            messages,
            operation_id=_operation_id("session_end", self._session_id, messages),
            session_id=self._session_id,
            user_id=self._current_user_id(),
            authenticated_host_ingress=self._require_ingress(hook="session_end"),
        )

    def on_pre_compress(self, messages: list[dict[str, object]] | list[str]) -> str:
        self._require_provider().on_pre_compress(
            messages,
            operation_id=_operation_id("pre_compress", self._session_id, messages),
            session_id=self._session_id,
            user_id=self._current_user_id(),
            authenticated_host_ingress=self._require_ingress(hook="pre_compress"),
        )
        return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._require_provider().on_memory_write(
            action,
            target,
            content,
            operation_id=_operation_id("memory_write", self._session_id, [action, target, content, metadata]),
            session_id=self._session_id,
            user_id=self._current_user_id(),
            authenticated_host_ingress=self._require_ingress(hook="memory_write"),
        )

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        child_session_id: str = "",
        **kwargs: Any,
    ) -> None:
        del kwargs
        effective_session_id = self._effective_session_id(child_session_id)
        self._require_provider().on_delegation(
            task,
            result,
            operation_id=_operation_id("delegation", effective_session_id, [task, result]),
            session_id=effective_session_id,
            user_id=self._current_user_id(),
            authenticated_host_ingress=self._require_ingress(hook="delegation", session_id=effective_session_id),
        )

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs: Any,
    ) -> None:
        del reset, rewound
        self._require_provider()
        switched_user_id = _optional_text(kwargs.get("user_id")) or _optional_text(kwargs.get("user_id_alt"))
        if self._completed_turn_runtime is not None and (
            parent_session_id or (switched_user_id is not None and switched_user_id != self._default_user_id)
        ):
            raise ValueError("Hermes local Level 2 execution context changed")
        self._session_id = _require_nonempty_text(new_session_id, "new_session_id")
        self._default_user_id = switched_user_id or self._default_user_id
        self._turn_user_id.set(self._default_user_id)

    def shutdown(self) -> None:
        self._provider = None
        self._issue_ingress = None
        self._completed_turn_runtime = None
        self._absent_author_id = "memorii.hermes.author.absent.v1"

    def _require_provider(self) -> HermesMemoryProvider:
        if self._provider is None:
            raise RuntimeError("Memorii Hermes provider has not been initialized")
        return self._provider

    def _effective_session_id(self, supplied_session_id: str) -> str:
        return _optional_text(supplied_session_id) or self._session_id

    def _current_user_id(self) -> str | None:
        return self._turn_user_id.get() or self._default_user_id

    def _require_ingress(
        self,
        *,
        hook: str,
        session_id: str | None = None,
        user_id: str | None = None,
        turn_author: dict[str, Any] | None = None,
    ) -> AuthenticatedHostIngress:
        issuer = self._issue_ingress
        if issuer is None:
            raise RuntimeError("Memorii Hermes ingress issuer has not been initialized")
        ingress = issuer(
            HermesIngressRequest(
                hook=hook,
                session_id=session_id or self._session_id,
                user_id=user_id or self._current_user_id(),
                agent_identity=self._agent_identity,
                turn_author=turn_author,
                received_at=datetime.now(UTC),
            )
        )
        if not isinstance(ingress, AuthenticatedHostIngress):
            raise TypeError("Memorii Hermes ingress issuer must return AuthenticatedHostIngress")
        return ingress


def _resolve_storage_root(*, hermes_home: object) -> Path:
    root = _path_from_value(hermes_home, "hermes_home") / "memorii"
    if root.exists() and not root.is_dir():
        raise ValueError(f"Memorii storage root is not a directory: {root}")
    return root


def _path_from_value(value: object, field_name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{field_name} must be a nonempty filesystem path")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be a nonempty filesystem path")
    return Path(text).expanduser()


def _require_nonempty_text(value: object, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} must be nonempty")
    return text


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _operation_id(hook: str, session_id: str, evidence: object) -> str:
    """Hash canonical completed-hook evidence for durable replay identity.

    When Hermes supplies ``messages`` it differentiates equal turn text at
    different transcript positions.  The documented fallback hashes the turn
    payload itself, so a retry remains idempotent but indistinguishable
    consecutive turns without a transcript cannot be separated.
    """

    payload = json.dumps(
        {"evidence": evidence, "hook": hook, "session_id": session_id},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"hermes:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _service_factory_status() -> tuple[Any | None, str | None]:
    try:
        entry_points = tuple(importlib.metadata.entry_points(group=_SERVICE_FACTORY_ENTRY_POINT_GROUP))
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, f"cannot discover {_SERVICE_FACTORY_ENTRY_POINT_GROUP}: {exc}"
    if not entry_points:
        return None, f"no {_SERVICE_FACTORY_ENTRY_POINT_GROUP} factory is installed"
    if len(entry_points) != 1:
        return None, f"multiple {_SERVICE_FACTORY_ENTRY_POINT_GROUP} factories are installed"
    if entry_points[0].value != _FIRST_PARTY_FACTORY_VALUE:
        return None, f"configured {_SERVICE_FACTORY_ENTRY_POINT_GROUP} factory is not the Memorii first-party factory"
    try:
        factory = entry_points[0].load()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, f"configured {_SERVICE_FACTORY_ENTRY_POINT_GROUP} factory cannot load: {exc}"
    if not callable(factory):
        return None, f"configured {_SERVICE_FACTORY_ENTRY_POINT_GROUP} value is not callable"
    return factory, None
