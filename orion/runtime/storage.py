"""Persistence for orion.runtime: the Queue ledger (QueueItem per
mission) and the Runtime's own operational state.

Same plain-YAML-under-workspace/ pattern every other ORION module
already uses (orion.bridge.storage, orion.executor.storage,
orion.experience.storage, ...) -- one file per concern, read fresh on
every call, no new database, no new dependency. This is exactly what
makes "la cola debe sobrevivir reinicios" true: nothing here is
in-memory-only.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import yaml

from orion.runtime.config import RuntimeConfig
from orion.runtime.models import QueueItem, RuntimeState

_CONFIG = RuntimeConfig.from_env()

RUNTIME_DIR: Path = _CONFIG.workspace_dir
QUEUE_FILE: Path = _CONFIG.queue_path
STATE_FILE: Path = RUNTIME_DIR / "runtime_state.yaml"


def ensure_runtime_storage() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


# BETA 007 concurrency fix (found via
# tests/test_runtime.py::SchedulerTests::
# test_concurrent_workers_each_process_a_distinct_mission_exactly_once):
# QUEUE_FILE is a single YAML file holding *every* mission's QueueItem
# in one dict. save_item()/delete_item() each do a full
# read-whole-file -> mutate one key -> write-whole-file cycle. Once
# claim_next_ready_mission() correctly lets multiple Workers claim
# *distinct* missions in real parallel (see orion.agents.builder.agent
# and orion.runtime.worker), those Workers' own queue bookkeeping calls
# started racing on this same file: two threads reading the same base
# snapshot before either had written back meant one thread's update
# silently overwrote the other's (lost update), or -- since PyYAML's
# dump is not an atomic replace -- two near-simultaneous writes could
# interleave into genuinely corrupt YAML. This lock makes each
# save_item()/delete_item() call's read-mutate-write cycle atomic with
# respect to every other one in this process.
_QUEUE_LOCK = threading.Lock()


def _load_queue_raw() -> dict[str, dict]:
    ensure_runtime_storage()
    if not QUEUE_FILE.exists():
        return {}
    with QUEUE_FILE.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _atomic_write_yaml(path: Path, data: object) -> None:
    """Write ``data`` to ``path`` as YAML without ever leaving a
    reader able to observe a partial write.

    BETA 007 concurrency fix (second half of the same bug _QUEUE_LOCK
    above addresses): _QUEUE_LOCK serializes writer-vs-writer access,
    but load_item()/list_items()/depth_by_status() are deliberately
    read *without* holding it (reads should never block on a writer
    that might be mid-mutation for an unrelated mission). A plain
    ``open(path, "w")`` truncates the file immediately and then writes
    incrementally, so an unlocked reader could open and read the file
    in that exact window and see a truncated/partial document -- which
    is what actually produced the YAML ParserError seen when running
    this Sprint's full test suite (a Worker thread still finishing its
    own write while another test's read raced it). Writing to a
    temporary file in the same directory and then os.replace()-ing it
    into place is atomic on POSIX: any concurrent reader always sees
    either the complete old file or the complete new one, never
    something in between, regardless of locking.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _save_queue_raw(data: dict[str, dict]) -> None:
    ensure_runtime_storage()
    _atomic_write_yaml(QUEUE_FILE, data)


def save_item(item: QueueItem) -> None:
    with _QUEUE_LOCK:
        data = _load_queue_raw()
        data[item.mission_id] = item.model_dump(mode="json")
        _save_queue_raw(data)


def load_item(mission_id: str) -> QueueItem | None:
    data = _load_queue_raw()
    raw = data.get(mission_id)
    return None if raw is None else QueueItem(**raw)


def list_items() -> list[QueueItem]:
    data = _load_queue_raw()
    return [QueueItem(**raw) for raw in data.values()]


def delete_item(mission_id: str) -> None:
    with _QUEUE_LOCK:
        data = _load_queue_raw()
        if mission_id in data:
            del data[mission_id]
            _save_queue_raw(data)


def load_state() -> RuntimeState:
    ensure_runtime_storage()
    if not STATE_FILE.exists():
        return RuntimeState()
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return RuntimeState(**(data or {}))


def save_state(state: RuntimeState) -> None:
    ensure_runtime_storage()
    _atomic_write_yaml(STATE_FILE, state.model_dump(mode="json"))
