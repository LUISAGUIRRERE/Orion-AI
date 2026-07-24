"""Configuration for orion.business, resolved once from environment
variables -- same dataclass/from_env() pattern already established by
orion.runtime.config.RuntimeConfig and orion.intelligence.config.IntelligenceConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage


def _default_workspace_dir() -> Path:
    # Deliberately NOT "workspace/business" -- that directory is
    # already owned by orion.window.services' Sprint 004 BusinessUnit
    # model (workspace/business/<slug>/business.yaml). Reusing it here
    # would silently collide with those files. Business Brain gets its
    # own directory and *reads* the Sprint 004 data via migrate_existing()
    # instead of overwriting it in place.
    return bridge_storage.WORKSPACE_DIR / "business_brain"


@dataclass(frozen=True)
class BusinessConfig:
    workspace_dir: Path = field(default_factory=_default_workspace_dir)
    # Real, deterministic keyword-match threshold (0-1) above which
    # planner.resolve_request() considers a BusinessProject a genuine
    # match for a free-text request -- same convention
    # orion.intelligence.config.similarity_threshold already uses.
    match_threshold: float = 0.2

    @classmethod
    def from_env(cls) -> "BusinessConfig":
        workspace_dir = Path(os.environ.get("ORION_BUSINESS_WORKSPACE", str(_default_workspace_dir())))
        threshold = float(os.environ.get("ORION_BUSINESS_MATCH_THRESHOLD", "0.2"))
        return cls(workspace_dir=workspace_dir, match_threshold=threshold)
