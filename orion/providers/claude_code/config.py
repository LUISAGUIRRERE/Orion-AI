"""Configuration for the Claude Code adapter.

Reads only environment-variable *names* -- never a secret value
embedded in source, and no credential is read anywhere in this
module. This Sprint explicitly does not connect real credentials
("No conectar todavia claves privadas"): ClaudeCodeAdapter.execute()
cannot actually invoke a real provider yet (see adapter.py's
_invoke() docstring for exactly why), so there is nothing here that
needs to authenticate with anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeCodeConfig:
    """Runtime configuration for ClaudeCodeAdapter, resolved once at
    construction time from environment variables.

    cli_path: the Claude Code CLI binary name/path health_check()
        looks for on PATH. Configurable via ORION_CLAUDE_CODE_CLI so
        a real deployment can point at a non-default install location
        without any code change.
    timeout_seconds: the ceiling a real _invoke() implementation would
        pass to its subprocess/SDK call. Configurable via
        ORION_CLAUDE_CODE_TIMEOUT_SECONDS. Note this is independent of
        (and would typically be smaller than) the Executor's own
        per-request timeout_seconds in orion.executor.models.
    """

    cli_path: str = "claude"
    timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "ClaudeCodeConfig":
        return cls(
            cli_path=os.environ.get("ORION_CLAUDE_CODE_CLI", "claude"),
            timeout_seconds=int(os.environ.get("ORION_CLAUDE_CODE_TIMEOUT_SECONDS", "300")),
        )
