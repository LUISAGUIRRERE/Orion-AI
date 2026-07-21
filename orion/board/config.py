"""Configuration for orion.board, resolved once from environment
variables -- same dataclass/from_env() pattern already established by
orion.runtime.config.RuntimeConfig, orion.intelligence.config.IntelligenceConfig,
orion.business.config.BusinessConfig, and orion.governance.config.GovernanceConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage


def _default_workspace_dir() -> Path:
    # workspace/board/ -- verified free of any prior owner before
    # choosing it, the same check every prior Sprint's config.py has
    # done for its own workspace subdirectory.
    return bridge_storage.WORKSPACE_DIR / "board"


@dataclass(frozen=True)
class BoardConfig:
    workspace_dir: Path = field(default_factory=_default_workspace_dir)

    @classmethod
    def from_env(cls) -> "BoardConfig":
        workspace_dir = Path(os.environ.get("ORION_BOARD_WORKSPACE", str(_default_workspace_dir())))
        return cls(workspace_dir=workspace_dir)
