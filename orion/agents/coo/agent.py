"""The COO Agent itself.

Owns the COO's own operational status (persisted, same pattern as the
Builder Agent's state in Sprint 006) and wraps the scheduler's cycle so
that status stays accurate across processes. The COO never executes a
mission and never creates an artifact — see scheduler.py and
dispatcher.py for what actually happens during a cycle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from orion.agents.coo import scheduler
from orion.bridge import storage as bridge_storage

STATE_FILE: Path = bridge_storage.WORKSPACE_DIR / "coo_state.yaml"


@dataclass
class COOState:
    """The COO's current operational status, surfaced to The Window."""

    status: str = "idle"
    assignments_today: int = 0
    last_assignment: str | None = None
    last_scan: str | None = None
    day: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())

    def roll_day(self) -> None:
        """Reset the daily counters when the UTC date changes."""
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day = today
            self.assignments_today = 0


def _load_state() -> COOState:
    """Load the COO's persisted state, or a fresh idle state if none exists."""
    if not STATE_FILE.exists():
        return COOState()
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    state = COOState(**{**asdict(COOState()), **data})
    state.roll_day()
    return state


def _save_state(state: COOState) -> None:
    """Persist the COO's state so any process can read it."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(asdict(state), fh)


def get_state() -> COOState:
    """Return the COO's current, persisted state."""
    return _load_state()


def run_cycle() -> dict[str, object]:
    """Run exactly one scan-and-assign cycle, updating the COO's own
    status around it. Delegates the actual scanning and assignment
    mechanics to ``scheduler.run_cycle()`` — this function owns only
    the COO's own status bookkeeping.
    """
    state = _load_state()
    state.status = "scanning"
    _save_state(state)

    result = scheduler.run_cycle()

    state = _load_state()
    state.status = "idle"
    state.last_scan = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if result.get("assigned"):
        state.assignments_today += 1
        state.last_assignment = state.last_scan
    _save_state(state)

    return result


if __name__ == "__main__":
    print(run_cycle())
