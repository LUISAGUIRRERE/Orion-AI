"""Configuration for the Claude Code adapter.

Reads only environment-variable *names* -- never a secret value
embedded in source. No credential is read, stored, or referenced
anywhere in this module: authentication is whatever ``claude auth
login`` (interactive) or ``ANTHROPIC_API_KEY`` (environment) already
set up outside of ORION's control. This adapter never manages
credentials itself -- it only shells out to the CLI and reports
honestly what it finds via health_check() (see adapter.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaudeCodeConfig:
    """Runtime configuration for ClaudeCodeAdapter, resolved once at
    construction time from environment variables.

    Every flag this config maps to a real, *verified* CLI flag --
    verified against the actual binary installed in this environment
    (``claude --version`` -> 2.1.209) via ``claude --help``. See
    docs/CLAUDE_CODE_ADAPTER.md for the full inspection record.

    cli_path (env: ORION_CLAUDE_CODE_BIN, default 'claude'):
        binary name/path health_check()/_invoke() use.

    timeout_seconds (env: ORION_CLAUDE_CODE_TIMEOUT, default 300):
        hard ceiling _invoke() enforces itself via a real subprocess
        timeout plus real process-group termination. The installed
        CLI has no native --timeout flag (confirmed absent from
        ``claude --help``), so this is enforced entirely on ORION's
        side, never delegated to the CLI.

    model (env: ORION_CLAUDE_CODE_MODEL, default None): passed as
        --model when set (a real, confirmed flag). None means "don't
        pass --model at all", deferring to the CLI's own default
        model rather than guessing one.

    max_turns (env: ORION_CLAUDE_CODE_MAX_TURNS, default None):
        reserved for a future CLI version. The installed CLI (2.1.209)
        exposes no per-turn-limit flag for `-p` sessions (confirmed
        absent from ``claude --help`` -- there is no --max-turns and
        no equivalent). Stored so the configuration surface matches
        this Sprint's spec exactly, but deliberately never translated
        into an invented flag: see adapter.py's _build_args(), which
        never references it, and execute(), which notes in its
        summary when a mission configured this and it had no effect.
    """

    cli_path: str = "claude"
    timeout_seconds: int = 300
    model: str | None = None
    max_turns: int | None = None

    @classmethod
    def from_env(cls) -> "ClaudeCodeConfig":
        max_turns_raw = os.environ.get("ORION_CLAUDE_CODE_MAX_TURNS")
        return cls(
            cli_path=os.environ.get("ORION_CLAUDE_CODE_BIN", "claude"),
            timeout_seconds=int(os.environ.get("ORION_CLAUDE_CODE_TIMEOUT", "300")),
            model=os.environ.get("ORION_CLAUDE_CODE_MODEL") or None,
            max_turns=int(max_turns_raw) if max_turns_raw else None,
        )
