"""Drive one interactive ``hermes`` primary-CLI chat turn over a pty.

The Memorii provider's local Level 2 authority admits only Hermes' primary
CLI context (platform=cli, agent_context=primary, agent_workspace=hermes);
one-shot -z turns skip MemoryManager entirely and ACP sessions are denied
by that gate on purpose. A pseudo-terminal is therefore the honest
headless driver for the certification journey.
"""
from __future__ import annotations

import os
import pty
import select
import signal
import time


def chat_turn(
    command: list[str],
    environment: dict[str, str],
    message: str,
    *,
    timeout: float = 240.0,
) -> tuple[int, str]:
    """Run one chat turn; returns (exit code, transcript text)."""
    pid, descriptor = pty.fork()
    if pid == 0:
        os.chdir("/tmp/hermes-journey-work")
        os.execve(command[0], command, environment)
        os._exit(127)
    output: list[bytes] = []
    deadline = time.monotonic() + timeout
    typed = False
    exited = False
    exit_code = -1
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([descriptor], [], [], 2.0)
            if readable:
                try:
                    chunk = os.read(descriptor, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.append(chunk)
                text = b"".join(output).decode("utf-8", "replace")
                if not typed and "\u276f" in text:
                    # Prompt box rendered: type the turn message.
                    time.sleep(1.0)
                    os.write(descriptor, (message + "\r").encode("utf-8"))
                    typed = True
                if typed and not exited and "stub reply: acknowledged and recorded." in text:
                    # The model answered; end the turn cleanly.
                    os.write(descriptor, b"/exit\r")
                    exited = True
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited == pid:
                exit_code = os.waitstatus_to_exitcode(status)
                break
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return exit_code, b"".join(output).decode("utf-8", "replace")
