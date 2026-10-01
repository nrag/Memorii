"""Drive real ``hermes chat`` primary-CLI turns over a pseudo-terminal.

The Memorii provider's local Level 2 authority admits only Hermes' primary
CLI context (platform=cli, agent_context=primary, agent_workspace=hermes);
one-shot -z turns skip MemoryManager entirely and ACP sessions are denied
by that gate on purpose. A pseudo-terminal running the seeded interactive
chat (``hermes chat --cli -q MESSAGE`` submits the first turn literally on
a real TTY) is therefore the honest headless driver: the full session
machinery runs, including the MemoryManager and the Memorii provider.
"""
from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import termios
import time


def seeded_chat_turn(
    command: list[str],
    environment: dict[str, str],
    message: str,
    *,
    marker: str = "acknowledged and recorded.",
    settle: "callable[[], bool] | None" = None,
    timeout: float = 300.0,
) -> tuple[bool, str]:
    """Run one seeded chat turn; returns (marker seen, transcript text).

    ``settle``, when given, delays the clean /exit until it returns true
    (bounded): the completed-turn memory pipeline flushes AFTER the reply
    renders, so exiting on the marker alone can race the durable write.
    """
    pid, descriptor = pty.fork()
    if pid == 0:
        os.chdir("/tmp/hermes-journey-work")
        argv = [*command, "--cli", "-q", message]
        os.execve(command[0], argv, environment)
        os._exit(127)
    # A real window size keeps TUI input handling well-formed.
    fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    output: list[bytes] = []
    deadline = time.monotonic() + timeout
    answered = False
    exited = False
    exit_code: int | None = None
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
                if marker in text:
                    answered = True
                    if not exited:
                        if settle is None:
                            time.sleep(1.0)
                            os.write(descriptor, b"/exit\r")
                            exited = True
                        else:
                            settle_deadline = time.monotonic() + 45.0
                            while time.monotonic() < settle_deadline:
                                if settle():
                                    break
                                time.sleep(1.0)
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
    if exit_code is None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    return answered, b"".join(output).decode("utf-8", "replace")
