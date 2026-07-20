"""Handler registry for the Builder Agent.

Every mission type maps to exactly one handler instance here. Adding a
new mission type means adding one line to this registry and one new
handler class in ``handlers.py`` — never a new branch in ``agent.py``.
"""

from __future__ import annotations

from orion.agents.builder.handlers import (
    CodeGenerationHandler,
    DocumentationHandler,
    MissionHandler,
    ResearchHandler,
    ScaffoldHandler,
)

_HANDLERS: dict[str, MissionHandler] = {
    "documentation": DocumentationHandler(),
    "research": ResearchHandler(),
    "scaffold": ScaffoldHandler(),
    "code_generation": CodeGenerationHandler(),
}


def get_handler(mission_type: str) -> MissionHandler:
    """Return the handler registered for a mission type.

    Raises KeyError if no handler is registered — the Builder Agent
    treats that as a failure for the mission, never a silent no-op.
    """
    try:
        return _HANDLERS[mission_type]
    except KeyError as exc:
        raise KeyError(f"No handler registered for mission type '{mission_type}'") from exc


def available_types() -> list[str]:
    """Return every mission type with a registered handler."""
    return sorted(_HANDLERS)
