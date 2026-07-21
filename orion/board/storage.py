"""Persistence for orion.board: plain, atomic YAML under
``workspace/board/``, the exact same file-per-concern read-fresh-
every-call pattern orion.governance.storage / orion.business.storage /
orion.intelligence.storage already established. Deliberately generic
-- never imports a dataclass from board_engine.py/member_registry.py
(same anti-cycle reason those modules' own docstrings document).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from orion.board.config import BoardConfig

_CONFIG = BoardConfig.from_env()
BOARD_DIR: Path = _CONFIG.workspace_dir


def ensure_board_storage() -> None:
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    missions_dir().mkdir(parents=True, exist_ok=True)


def missions_dir() -> Path:
    return BOARD_DIR / "missions"


def mission_state_path(mission_id: str) -> Path:
    return missions_dir() / f"{mission_id}.yaml"


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
