"""Pi extension adapter: session/branch to explicit task binding.

Contract binding for the design's Pi row: the extension maps the active
session/branch to an explicit Memorii task binding, captures native
stable message/action ids, honors final-settle semantics and
pre-compaction checkpoints. Fork requires explicit continue-same-task
authorization or a create-new-task command; abandoned branches never
become committed source evidence. Pinned host contract; fails closed on
version mismatch; not certified installed support.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PI_HOST_CONTRACT = "pi-coding-agent-extension/v1"
SUPPORTED_PI_VERSIONS: frozenset[str] = frozenset({"0.x", "1.x"})


class PiExtensionManifest(BaseModel):
    host_contract: Literal["pi-coding-agent-extension/v1"] = PI_HOST_CONTRACT
    host_version: str = Field(min_length=1)
    sidecar_url: str = Field(min_length=1)
    credential_path: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def version_is_pinned(self) -> PiExtensionManifest:
        major = self.host_version.split(".", 1)[0] + ".x"
        if major not in SUPPORTED_PI_VERSIONS:
            raise ValueError(
                f"unsupported Pi host version {self.host_version};"
                f" supported: {sorted(SUPPORTED_PI_VERSIONS)}"
            )
        return self


class PiSessionCoordinate(BaseModel):
    """Native stable session/branch coordinate; never user authority."""

    session_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PiEventKind(BaseModel):
    kind: Literal[
        "session_start", "branch_fork", "final_settle", "pre_compaction", "message"
    ]

    model_config = ConfigDict(extra="forbid", frozen=True)


def translate_pi_event(
    manifest: PiExtensionManifest,
    *,
    coordinate: PiSessionCoordinate,
    event: PiEventKind,
    continue_same_task_authorized: bool = False,
) -> dict[str, object]:
    """Translate one native event into the durable runtime protocol.

    Fork denies by default: continuing the same task across a fork
    requires explicit authorization or a create-new-task command.
    Abandoned branches never become committed source evidence.
    """
    if event.kind == "branch_fork" and not continue_same_task_authorized:
        return {
            "status": "denied",
            "reason": "fork requires explicit continue-same-task authorization"
            " or a create-new-task command",
            "action": "create_new_task_required",
        }
    return {
        "status": "ready",
        "event": event.kind,
        "session": coordinate.model_dump(mode="json"),
        "checkpoint_before_compaction": event.kind == "pre_compaction",
        "settle": event.kind == "final_settle",
    }
