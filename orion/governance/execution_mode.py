"""The four official Execution Modes this Sprint defines, and their
real behavioral profile (not just a label): what each mode may do
without asking, whether it creates tests, whether it keeps working
after a fix, and what it must never do. Every other governance engine
reads a mode's ModeProfile rather than special-casing mode names
inline -- one real source of truth per mode.

Persistence: a single current-mode record under
workspace/governance/mode.yaml, read fresh every call (same convention
orion.runtime.storage/orion.business.storage already use), with a full
history of every change (who/when/why) kept alongside it so a mode
switch is itself an auditable event, never a silent flip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from orion.governance import storage
from orion.governance.config import (
    MODE_DEVELOPMENT,
    MODE_HARDENING,
    MODE_PRODUCTION,
    MODE_RELEASE,
    VALID_MODES,
    GovernanceConfig,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ModeProfile:
    """Real capabilities for one Execution Mode -- every field here is
    read by policy_engine/approval_engine, never re-guessed inline."""

    mode: str
    description: str
    can_auto_fix_bugs: bool
    can_create_tests_automatically: bool
    can_continue_after_fix: bool
    can_apply_local_fixes: bool
    stops_only_for_architecture_or_breaking: bool
    generates_pull_request_instead_of_direct_change: bool
    never_modifies_production_directly: bool
    requires_approval_for_everything: bool


_PROFILES: dict[str, ModeProfile] = {
    MODE_DEVELOPMENT: ModeProfile(
        mode=MODE_DEVELOPMENT,
        description="Extremadamente conservador: pregunta todo, no modifica nada automaticamente.",
        can_auto_fix_bugs=False,
        can_create_tests_automatically=False,
        can_continue_after_fix=False,
        can_apply_local_fixes=False,
        stops_only_for_architecture_or_breaking=False,
        generates_pull_request_instead_of_direct_change=False,
        never_modifies_production_directly=False,
        requires_approval_for_everything=True,
    ),
    MODE_HARDENING: ModeProfile(
        mode=MODE_HARDENING,
        description="Puede corregir bugs pequeños, crea tests automaticamente, continua trabajando.",
        can_auto_fix_bugs=True,
        can_create_tests_automatically=True,
        can_continue_after_fix=True,
        can_apply_local_fixes=True,
        stops_only_for_architecture_or_breaking=False,
        generates_pull_request_instead_of_direct_change=False,
        never_modifies_production_directly=False,
        requires_approval_for_everything=False,
    ),
    MODE_RELEASE: ModeProfile(
        mode=MODE_RELEASE,
        description="Prioridad absoluta: estabilidad. Puede aplicar fixes locales. Solo se detiene por cambios de arquitectura.",
        can_auto_fix_bugs=True,
        can_create_tests_automatically=True,
        can_continue_after_fix=True,
        can_apply_local_fixes=True,
        stops_only_for_architecture_or_breaking=True,
        generates_pull_request_instead_of_direct_change=False,
        never_modifies_production_directly=False,
        requires_approval_for_everything=False,
    ),
    MODE_PRODUCTION: ModeProfile(
        mode=MODE_PRODUCTION,
        description="Nunca modifica produccion directamente: genera Pull Requests y solicita aprobacion.",
        can_auto_fix_bugs=True,
        can_create_tests_automatically=True,
        can_continue_after_fix=False,
        can_apply_local_fixes=False,
        stops_only_for_architecture_or_breaking=False,
        generates_pull_request_instead_of_direct_change=True,
        never_modifies_production_directly=True,
        requires_approval_for_everything=False,
    ),
}


def get_profile(mode: str) -> ModeProfile:
    if mode not in _PROFILES:
        raise ValueError(f"Modo de ejecucion desconocido: '{mode}'. Modos validos: {', '.join(VALID_MODES)}.")
    return _PROFILES[mode]


def get_mode() -> str:
    """The real current mode, persisted -- never re-derived or
    guessed. Falls back to GovernanceConfig.default_mode (the most
    conservative one) the first time ORION ever runs, before any
    `orion mode set` has happened."""
    storage.ensure_governance_storage()
    record = storage.read_yaml(storage.mode_path(), None)
    if record is None or "mode" not in record:
        return GovernanceConfig.from_env().default_mode
    return record["mode"]


def set_mode(mode: str, author: str = "ORION", reason: str = "") -> ModeProfile:
    """Real, persisted mode switch. Raises ValueError for an unknown
    mode rather than silently accepting it -- a governance layer that
    can be pushed into an undefined mode by a typo is not trustworthy."""
    profile = get_profile(mode)  # validates
    storage.ensure_governance_storage()
    previous = get_mode()
    record = {
        "mode": mode,
        "previous_mode": previous,
        "author": author,
        "reason": reason,
        "changed_at": _now_iso(),
    }
    storage.write_yaml(storage.mode_path(), record)
    history_entry = dict(record)
    history_entry["event"] = "mode_changed"
    from orion.governance.storage import GOVERNANCE_DIR

    history_path = GOVERNANCE_DIR / "mode_history.yaml"
    storage.append_yaml_list(history_path, history_entry)
    return profile


def get_mode_history() -> list[dict]:
    from orion.governance.storage import GOVERNANCE_DIR

    return storage.read_yaml(GOVERNANCE_DIR / "mode_history.yaml", [])
