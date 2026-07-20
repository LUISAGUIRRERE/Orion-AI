"""Dynamic adapter registry for the Executor.

Unlike orion.agents.builder.registry (a fixed dict of mission_type ->
handler, all four handlers built into Sprint 006), this registry is
meant to be extended by adapters that don't ship inside this package:
a future Claude Code adapter, Codex CLI adapter, Gemini CLI adapter,
etc. each register themselves by calling ``register_adapter`` --
usually as a side effect of being imported -- rather than being wired
into this module by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type hints -- importing this at runtime would create a
    # cycle, since orion.executor.adapters.__init__ imports the built-in
    # adapters, which import register_adapter from this module.
    from orion.executor.adapters.base import ProviderAdapter

_ADAPTERS: dict[str, "ProviderAdapter"] = {}


def register_adapter(adapter: "ProviderAdapter") -> None:
    """Register (or replace) an adapter under its own ``name``.

    Deliberately permissive about overwriting: re-importing a module
    that registers itself must never raise, so this registry stays
    safe to touch from tests and from repeated imports alike.
    """
    _ADAPTERS[adapter.name] = adapter


def get_adapter(name: str) -> "ProviderAdapter":
    """Return the adapter registered under ``name``.

    Raises KeyError if none is registered -- the Executor treats an
    unknown adapter as a hard failure for the mission, never a silent
    no-op, the same way orion.agents.builder.registry.get_handler
    already does for an unknown mission_type.
    """
    try:
        return _ADAPTERS[name]
    except KeyError as exc:
        raise KeyError(f"No hay ningun adaptador registrado con el nombre '{name}'") from exc


def available_adapters() -> list[str]:
    """Every adapter name currently registered."""
    return sorted(_ADAPTERS)
