"""Persistence for orion.governance: plain, atomic YAML under
``workspace/governance/``, the exact same file-per-concern
read-fresh-every-call pattern orion.business.storage /
orion.intelligence.storage already established. Deliberately generic
-- never imports a dataclass from policy_engine.py/audit.py/etc.
(same anti-cycle reason orion.business.storage documents).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from orion.governance.config import GovernanceConfig

_CONFIG = GovernanceConfig.from_env()
GOVERNANCE_DIR: Path = _CONFIG.workspace_dir


def ensure_governance_storage() -> None:
    GOVERNANCE_DIR.mkdir(parents=True, exist_ok=True)


def mode_path() -> Path:
    return GOVERNANCE_DIR / "mode.yaml"


def audit_log_path() -> Path:
    return GOVERNANCE_DIR / "audit_log.yaml"


def approvals_path() -> Path:
    return GOVERNANCE_DIR / "approvals.yaml"


def rollbacks_path() -> Path:
    return GOVERNANCE_DIR / "rollbacks.yaml"


def read_yaml(path: Path, default: Any) -> Any:
    """Read one YAML file, or ``default`` if it does not exist yet."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return default if data is None else data


def write_yaml(path: Path, data: Any) -> None:
    """Atomic write: temp file + os.replace(), the same fix BETA 007
    found necessary under concurrent access, applied here from the
    start."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def append_yaml_list(path: Path, item: dict) -> None:
    """Append one record to a YAML file holding a list -- the audit
    log and approval queue's own append pattern. Reads the full list,
    appends, atomically rewrites: correct for this Sprint's real
    scale (single-repo, human-reviewed history), same tradeoff
    orion.experience.knowledge_store already accepts for its own
    append-heavy store."""
    items = read_yaml(path, [])
    items.append(item)
    write_yaml(path, items)
