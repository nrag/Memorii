"""Lease renewal for active memory-evolution operations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from threading import Event, Thread

logger = logging.getLogger(__name__)


class EvolutionLeaseHeartbeat:
    def __init__(self, *, renew: Callable[[], bool], interval: timedelta) -> None:
        self._renew = renew
        self._interval_seconds = interval.total_seconds()
        self._stopped = Event()
        self._thread = Thread(target=self._run, name="memory-evolution-lease", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stopped.wait(self._interval_seconds):
            try:
                if not self._renew():
                    return
            except Exception:
                logger.exception("memory_evolution_lease_renewal_failed")
                return
