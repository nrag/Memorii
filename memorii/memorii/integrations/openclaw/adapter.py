"""OpenClaw memory-plugin adapter: typed translation, pinned contract.

This module is the contract binding the design requires: it translates
OpenClaw's native plugin surfaces (explicit memory slot, permitted
lifecycle hooks, channel account/sender identity) into Memorii's
versioned runtime protocol through the Python client. It is
contract-faithful but NOT certified installed support: the plugin
carries a pinned host contract and fails closed when the host does not
match; actual host-version certification is an external prerequisite
before advertising an installed adapter.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OPENCLAW_HOST_CONTRACT = "openclaw-memory-plugin/v1"
SUPPORTED_HOST_VERSIONS: frozenset[str] = frozenset({"1.x"})


class OpenClawPluginManifest(BaseModel):
    """Closed manifest mirror of the native plugin registration surface."""

    host_contract: Literal["openclaw-memory-plugin/v1"] = OPENCLAW_HOST_CONTRACT
    host_version: str = Field(min_length=1)
    memory_slot: str = Field(min_length=1)
    permitted_hooks: tuple[str, ...] = ()
    sidecar_url: str = Field(min_length=1)
    credential_path: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def version_and_hooks_are_pinned(self) -> OpenClawPluginManifest:
        major = self.host_version.split(".", 1)[0] + ".x"
        if major not in SUPPORTED_HOST_VERSIONS:
            raise ValueError(
                f"unsupported OpenClaw host version {self.host_version};"
                f" supported: {sorted(SUPPORTED_HOST_VERSIONS)}"
            )
        allowed = {"prompt_inject", "session_start", "session_switch", "tool_call"}
        unknown = set(self.permitted_hooks) - allowed
        if unknown:
            raise ValueError(f"hooks not permitted by the host contract: {sorted(unknown)}")
        return self


class OpenClawSenderIdentity(BaseModel):
    """Channel account/sender distinction the design requires."""

    channel_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    sender_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class OpenClawInputClassification(BaseModel):
    """Forwarded/system inputs never become committed source evidence."""

    input_kind: Literal["user_message", "system_event", "forwarded"]
    sender: OpenClawSenderIdentity

    model_config = ConfigDict(extra="forbid", frozen=True)

    def eligible_as_source(self) -> bool:
        return self.input_kind == "user_message"


class OpenClawPromptBlock:
    """Bounded authorized prompt enrichment for the permitted hook."""

    def __init__(self, runtime_text: str) -> None:
        self._runtime_text = runtime_text

    def render(self) -> str:
        return self._runtime_text


def bind_openclaw_session(
    manifest: OpenClawPluginManifest,
    *,
    sender: OpenClawSenderIdentity,
    classification: OpenClawInputClassification,
    runtime_text: str | None,
) -> dict[str, object]:
    """One hook invocation: authorize, classify, and translate.

    System and forwarded inputs never establish source authority; they
    deny mutation. A denied or unknown sender yields an explicit
    unavailable marker rather than a best-effort memory view.
    """
    if classification.sender != sender:
        raise ValueError("classification sender does not match the session sender")
    if not classification.eligible_as_source():
        return {
            "status": "denied",
            "reason": f"{classification.input_kind} input is not source authority",
            "prompt_block": None,
        }
    if runtime_text is None:
        return {
            "status": "unavailable",
            "reason": "no authorized durable runtime binding for this sender",
            "prompt_block": None,
        }
    return {
        "status": "ready",
        "prompt_block": OpenClawPromptBlock(runtime_text).render(),
        "memory_slot": manifest.memory_slot,
    }
