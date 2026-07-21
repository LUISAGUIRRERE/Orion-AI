"""Runtime Scheduler: owns N Worker threads (ORION_WORKERS, default 1).

Threads, not processes or asyncio tasks: each Worker's real work
(waiting on a Claude Code subprocess) already happens in a separate OS
process via orion.providers.claude_code.adapter, so a Python thread
here is never CPU-bound -- it only ever blocks on I/O (reading a YAML
file, waiting on a subprocess), which releases the GIL exactly when it
matters. This keeps concurrency here dependency-free and simple to
reason about ("debe poder crecer despues" -- just raise ORION_WORKERS,
nothing about Worker itself has to change).
"""

from __future__ import annotations

import threading

from orion.runtime.models import WorkerStatus
from orion.runtime.worker import Worker


class Scheduler:
    def __init__(self, worker_count: int = 1, poll_interval_seconds: float = 1.0) -> None:
        self.worker_count = max(1, worker_count)
        self.poll_interval_seconds = poll_interval_seconds
        self.workers: list[Worker] = []
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Idempotent: calling start() while already running is a
        no-op, never doubles the worker pool."""
        if self._threads:
            return
        for index in range(self.worker_count):
            worker = Worker(worker_id=f"worker-{index + 1}", poll_interval_seconds=self.poll_interval_seconds)
            thread = threading.Thread(target=worker.run_forever, name=worker.worker_id, daemon=True)
            self.workers.append(worker)
            self._threads.append(thread)
            thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal every Worker to stop and join its thread.

        BETA 007 bug fix (found via tests/test_runtime.py, which
        occasionally saw a Worker thread from one test's Scheduler
        silently steal a *later*, unrelated test's freshly-created
        mission): this used to clear self.workers/self._threads
        unconditionally, regardless of whether thread.join(timeout=...)
        actually succeeded. A thread that took longer than ``timeout``
        to notice its stop signal (real under CPU contention, since
        this is a soft timeout, not a kill) was silently forgotten
        about right here -- is_running() would then report False even
        though that daemon thread was still very much alive and
        polling in the background, and a second stop() call had
        nothing left to join. Only clearing once every thread has
        actually finished means is_running() stays truthful, and a
        caller that retries stop() after a False negative keeps
        joining the *same* still-alive threads until they really exit.
        """
        for worker in self.workers:
            worker.stop()
        for thread in self._threads:
            thread.join(timeout=timeout)
        if any(thread.is_alive() for thread in self._threads):
            return
        self.workers.clear()
        self._threads.clear()

    def is_running(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def worker_statuses(self) -> list[WorkerStatus]:
        return [
            WorkerStatus(
                worker_id=w.worker_id,
                busy=w.busy,
                current_mission_id=w.current_mission_id,
                processed_count=w.processed_count,
                failed_count=w.failed_count,
            )
            for w in self.workers
        ]
