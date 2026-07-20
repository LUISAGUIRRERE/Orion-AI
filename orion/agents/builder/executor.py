"""Execution entry point for the Builder Agent.

No background scheduler runs automatically — Sprint 005's Mission Queue
explicitly does not implement automatic execution yet, and this Sprint
respects that. The Builder is invoked explicitly, either one mission at
a time or in a bounded loop until the queue has no READY work left.
"""

from __future__ import annotations

from orion.agents.builder import agent


def run_once() -> str:
    """Process exactly one READY mission, if any. Returns a status line."""
    mission = agent.process_next()
    if mission is None:
        return "No hay misiones READY para procesar."
    return f"Mission {mission.id} procesada -> estado final: {mission.status.value}"


def run_until_idle(max_missions: int = 50) -> int:
    """Process READY missions one after another until none remain.

    Bounded by ``max_missions`` as a safety limit against an
    unexpectedly large or misbehaving queue. Returns how many missions
    were processed.
    """
    processed = 0
    while processed < max_missions:
        mission = agent.process_next()
        if mission is None:
            break
        processed += 1
    return processed


if __name__ == "__main__":
    count = run_until_idle()
    print(f"Builder Agent: {count} mision(es) procesada(s).")
