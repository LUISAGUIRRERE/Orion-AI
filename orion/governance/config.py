"""Configuration for orion.governance, resolved once from environment
variables -- same dataclass/from_env() pattern already established by
orion.runtime.config.RuntimeConfig, orion.intelligence.config.IntelligenceConfig,
and orion.business.config.BusinessConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage


def _default_workspace_dir() -> Path:
    # workspace/governance/ -- verified free of any prior owner before
    # choosing it (unlike workspace/business/, which BETA 009 found
    # already belonged to Sprint 004's BusinessUnit model).
    return bridge_storage.WORKSPACE_DIR / "governance"


# The only four official Execution Modes this Sprint defines. Kept as
# plain string constants (not an enum) so config/env values, storage,
# and the CLI/API all share one literal vocabulary without an import
# cycle into orion.governance.execution_mode.
MODE_DEVELOPMENT = "MODE_DEVELOPMENT"
MODE_HARDENING = "MODE_HARDENING"
MODE_RELEASE = "MODE_RELEASE"
MODE_PRODUCTION = "MODE_PRODUCTION"

VALID_MODES = (MODE_DEVELOPMENT, MODE_HARDENING, MODE_RELEASE, MODE_PRODUCTION)


@dataclass(frozen=True)
class GovernanceConfig:
    workspace_dir: Path = field(default_factory=_default_workspace_dir)
    # The mode ORION starts in when no mode has ever been set for real
    # (see execution_mode.get_mode()) -- deliberately the most
    # conservative one. Autonomy is something ORION must be handed
    # explicitly (via `orion mode set ...` or POST /api/governance/mode),
    # never something it defaults itself into.
    default_mode: str = MODE_DEVELOPMENT
    # Confidence threshold (0-1) the policy examples in this Sprint's
    # brief use ("Confianza > 0.95"). Kept configurable rather than
    # hardcoded inside policy_engine so it can be tuned per-deployment
    # without a code change.
    high_confidence_threshold: float = 0.95

    @classmethod
    def from_env(cls) -> "GovernanceConfig":
        workspace_dir = Path(os.environ.get("ORION_GOVERNANCE_WORKSPACE", str(_default_workspace_dir())))
        default_mode = os.environ.get("ORION_GOVERNANCE_DEFAULT_MODE", MODE_DEVELOPMENT)
        if default_mode not in VALID_MODES:
            default_mode = MODE_DEVELOPMENT
        threshold = float(os.environ.get("ORION_GOVERNANCE_HIGH_CONFIDENCE", "0.95"))
        return cls(workspace_dir=workspace_dir, default_mode=default_mode, high_confidence_threshold=threshold)
