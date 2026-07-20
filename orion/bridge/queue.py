"""A simple, persistent mission queue.

Supports adding, taking the next mission, listing, and removing.
Automatic execution is intentionally not implemented in this Sprint.
"""

from __future__ import annotations

from orion.bridge import storage


def enqueue(mission_id: str) -> list[str]:
    """Add a mission id to the back of the queue, if not already present."""
    queue = storage.read_queue()
    if mission_id not in queue:
        queue.append(mission_id)
        storage.write_queue(queue)
    return queue


def take_next() -> str | None:
    """Remove and return the mission id at the front of the queue, if any."""
    queue = storage.read_queue()
    if not queue:
        return None
    next_id = queue.pop(0)
    storage.write_queue(queue)
    return next_id


def list_queue() -> list[str]:
    """Return the current queue, front to back, without modifying it."""
    return storage.read_queue()


def remove(mission_id: str) -> list[str]:
    """Remove a specific mission id from the queue, if present."""
    queue = storage.read_queue()
    if mission_id in queue:
        queue.remove(mission_id)
        storage.write_queue(queue)
    return queue
