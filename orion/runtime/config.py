"""Configuration for orion.runtime, resolved once from environment
variables -- same pattern as orion.providers.claude_code.config.

Variables (exactly the five this Sprint's spec lists):
    ORION_PROVIDER        -- which ProviderAdapter Workers use by
                              default (already read by
                              orion.executor.services; re-read here
                              only so RuntimeConfig/health_report can
                              report it, never a second source of
                              truth).
    ORION_WORKERS         -- how many Worker threads the Scheduler
                              starts. Default 1.
    ORION_RUNTIME_PORT     -- port `orion runtime start` binds the
                              REST/SSE API to. Default 8090 (The
                              Window already owns 8080).
    ORION_QUEUE_PATH       -- exact path to the Runtime's persistent
                              queue YAML file. Default
                              <ORION_WORKSPACE>/queue.yaml.
    ORION_WORKSPACE        -- directory for the Runtime's own runtime
                              data (queue.yaml, runtime_state.yaml).
                              Default workspace/runtime/ under this
                              environment's Orion-AI checkout -- the
                              same convention as workspace/missions/,
                              workspace/companies/, workspace/knowledge/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage


def _default_workspace_dir() -> Path:
    return bridge_storage.WORKSPACE_DIR / "runtime"


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str = "claude_code"
    workers: int = 1
    port: int = 8090
    workspace_dir: Path = field(default_factory=_default_workspace_dir)
    queue_path: Path = field(default_factory=lambda: _default_workspace_dir() / "queue.yaml")
    poll_interval_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        workspace_dir = Path(os.environ.get("ORION_WORKSPACE", str(_default_workspace_dir())))
        queue_path = Path(os.environ.get("ORION_QUEUE_PATH", str(workspace_dir / "queue.yaml")))
        return cls(
            provider=os.environ.get("ORION_PROVIDER", "claude_code"),
            workers=max(1, int(os.environ.get("ORION_WORKERS", "1"))),
            port=int(os.environ.get("ORION_RUNTIME_PORT", "8090")),
            workspace_dir=workspace_dir,
            queue_path=queue_path,
        )
