"""OpenClaw/Pi contract adapters: pinned hosts, closed classification."""

from __future__ import annotations

import pytest
from memorii.integrations.openclaw.adapter import (
    OpenClawInputClassification,
    OpenClawPluginManifest,
    OpenClawSenderIdentity,
    bind_openclaw_session,
)
from memorii.integrations.pi.adapter import (
    PiEventKind,
    PiExtensionManifest,
    PiSessionCoordinate,
    translate_pi_event,
)


def _manifest() -> OpenClawPluginManifest:
    return OpenClawPluginManifest(
        host_version="1.4",
        memory_slot="memorii",
        permitted_hooks=("prompt_inject", "session_start"),
        sidecar_url="http://127.0.0.1:8000",
        credential_path="/credentials/one",
    )


def _sender() -> OpenClawSenderIdentity:
    return OpenClawSenderIdentity(channel_id="chan:1", account_id="acct:1", sender_id="user:a")


def test_manifest_pins_host_version_and_permitted_hooks() -> None:
    with pytest.raises(ValueError, match="unsupported OpenClaw host version"):
        OpenClawPluginManifest(
            host_version="9.0",
            memory_slot="m",
            permitted_hooks=(),
            sidecar_url="http://127.0.0.1:1",
            credential_path="/x",
        )
    # model_copy bypasses validation by design; the parse boundary enforces.
    with pytest.raises(ValueError, match="not permitted"):
        OpenClawPluginManifest.model_validate(
            _manifest().model_dump() | {"permitted_hooks": ["arbitrary_hook"]}
        )


def test_system_and_forwarded_input_never_become_source_authority() -> None:
    manifest = _manifest()
    sender = _sender()
    for kind in ("system_event", "forwarded"):
        result = bind_openclaw_session(
            manifest,
            sender=sender,
            classification=OpenClawInputClassification(
                input_kind=kind,  # type: ignore[arg-type]
                sender=sender,
            ),
            runtime_text="[memorii] anything",
        )
        assert result["status"] == "denied"
        assert "not source authority" in result["reason"]
        assert result["prompt_block"] is None


def test_unbound_sender_yields_explicit_unavailable() -> None:
    result = bind_openclaw_session(
        _manifest(),
        sender=_sender(),
        classification=OpenClawInputClassification(
            input_kind="user_message", sender=_sender()
        ),
        runtime_text=None,
    )
    assert result["status"] == "unavailable"


def test_authorized_sender_receives_bounded_block_in_its_slot() -> None:
    result = bind_openclaw_session(
        _manifest(),
        sender=_sender(),
        classification=OpenClawInputClassification(
            input_kind="user_message", sender=_sender()
        ),
        runtime_text="[memorii v1] task=t rev=1 status=ready",
    )
    assert result["status"] == "ready"
    assert result["memory_slot"] == "memorii"
    assert result["prompt_block"].startswith("[memorii v1]")


def test_classification_must_match_session_sender() -> None:
    other = OpenClawSenderIdentity(
        channel_id="chan:1", account_id="acct:1", sender_id="user:other"
    )
    with pytest.raises(ValueError, match="does not match"):
        bind_openclaw_session(
            _manifest(),
            sender=_sender(),
            classification=OpenClawInputClassification(
                input_kind="user_message", sender=other
            ),
            runtime_text=None,
        )


def _pi_manifest() -> PiExtensionManifest:
    return PiExtensionManifest(
        host_version="1.2",
        sidecar_url="http://127.0.0.1:8000",
        credential_path="/credentials/one",
    )


def test_pi_manifest_pins_version() -> None:
    with pytest.raises(ValueError, match="unsupported Pi host version"):
        PiExtensionManifest(
            host_version="7.0",
            sidecar_url="http://127.0.0.1:1",
            credential_path="/x",
        )


def test_pi_fork_denies_without_explicit_authorization() -> None:
    result = translate_pi_event(
        _pi_manifest(),
        coordinate=PiSessionCoordinate(session_id="s:1", branch_id="b:2"),
        event=PiEventKind(kind="branch_fork"),
    )
    assert result["status"] == "denied"
    assert result["action"] == "create_new_task_required"


def test_pi_fork_authorized_and_lifecycle_events_translate() -> None:
    coordinate = PiSessionCoordinate(session_id="s:1", branch_id="b:1")
    fork = translate_pi_event(
        _pi_manifest(),
        coordinate=coordinate,
        event=PiEventKind(kind="branch_fork"),
        continue_same_task_authorized=True,
    )
    assert fork["status"] == "ready"
    settle = translate_pi_event(
        _pi_manifest(),
        coordinate=coordinate,
        event=PiEventKind(kind="final_settle"),
    )
    assert settle["settle"] is True
    compaction = translate_pi_event(
        _pi_manifest(),
        coordinate=coordinate,
        event=PiEventKind(kind="pre_compaction"),
    )
    assert compaction["checkpoint_before_compaction"] is True
