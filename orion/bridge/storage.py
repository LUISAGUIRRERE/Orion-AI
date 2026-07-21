"""YAML-backed persistence for the Command Bridge.

Missions, their messages, and their timeline events are stored as
plain YAML files under ``workspace/missions/<mission-id>/``. This
module is self-contained (it does not import from ``orion.window``)
so the Bridge can be used independently of The Window.

The Window's own event log (business-unit updates) keeps using SQLite,
per Sprint 005's explicit instruction. Mission data never touches it.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
WORKSPACE_DIR: Path = REPO_ROOT / "workspace"
MISSIONS_DIR: Path = WORKSPACE_DIR / "missions"
QUEUE_FILE: Path = MISSIONS_DIR / "_queue.yaml"


def ensure_bridge_storage() -> None:
    """Create the missions directory and an empty queue file if missing."""
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not QUEUE_FILE.exists():
        _write_yaml(QUEUE_FILE, [])


def _read_yaml(path: Path, default: Any) -> Any:
    """Read a YAML file, returning ``default`` if it is missing or empty."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if data is not None else default


# BETA 007 concurrency fix (found via the full test suite run under
# tests/test_runtime.py's Worker/Scheduler tests, which -- unlike
# every caller before this Sprint -- can have multiple real threads
# reading and writing the same mission's events.yaml/missions.yaml at
# once): a plain open(path, "w") truncates the file before writing,
# so a concurrent reader could observe a partial document, and two
# concurrent writers' read-modify-write cycles could race and drop
# each other's update. _WRITE_LOCK serializes writers in this
# process; the temp-file + os.replace() pattern (same one used in
# orion.runtime.storage and orion.agents.builder.agent) makes each
# individual write atomic from any reader's point of view, locked or
# not.
_WRITE_LOCK = threading.Lock()


def _write_yaml(path: Path, data: Any) -> None:
    """Write ``data`` to ``path`` as YAML, creating parent directories."""
    with _WRITE_LOCK:
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


def mission_dir(mission_id: str) -> Path:
    """Return the storage directory for a given mission id."""
    return MISSIONS_DIR / mission_id


def mission_exists(mission_id: str) -> bool:
    """Return True if a mission with this id has been persisted."""
    return (mission_dir(mission_id) / "mission.yaml").is_file()


def list_mission_ids() -> list[str]:
    """Return every persisted mission id, sorted."""
    if not MISSIONS_DIR.exists():
        return []
    return sorted(
        p.name
        for p in MISSIONS_DIR.iterdir()
        if p.is_dir() and (p / "mission.yaml").is_file()
    )


def read_mission(mission_id: str) -> dict[str, Any] | None:
    """Read a mission's ``mission.yaml``, or None if it does not exist."""
    return _read_yaml(mission_dir(mission_id) / "mission.yaml", None)


def write_mission(mission_id: str, data: dict[str, Any]) -> None:
    """Persist a mission's data and ensure its ``artifacts/`` folder exists."""
    unit_dir = mission_dir(mission_id)
    (unit_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    _write_yaml(unit_dir / "mission.yaml", data)


def read_messages(mission_id: str) -> list[dict[str, Any]]:
    """Read every message stored for a mission, in append order."""
    return _read_yaml(mission_dir(mission_id) / "messages.yaml", [])


def append_message(mission_id: str, message: dict[str, Any]) -> None:
    """Append a message to a mission's conversation. Never removes any."""
    messages = read_messages(mission_id)
    messages.append(message)
    _write_yaml(mission_dir(mission_id) / "messages.yaml", messages)


def read_events(mission_id: str) -> list[dict[str, Any]]:
    """Read every timeline event stored for a mission, in append order."""
    return _read_yaml(mission_dir(mission_id) / "events.yaml", [])


def append_event(mission_id: str, event: dict[str, Any]) -> None:
    """Append a timeline event to a mission's history."""
    events = read_events(mission_id)
    events.append(event)
    _write_yaml(mission_dir(mission_id) / "events.yaml", events)


def read_queue() -> list[str]:
    """Read the current queue of mission ids, front to back."""
    return _read_yaml(QUEUE_FILE, [])


def write_queue(queue: list[str]) -> None:
    """Persist the queue of mission ids."""
    _write_yaml(QUEUE_FILE, queue)
