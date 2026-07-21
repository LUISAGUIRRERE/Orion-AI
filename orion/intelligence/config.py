"""Configuration for orion.intelligence, resolved once from environment
variables -- same dataclass/from_env() pattern already established by
orion.runtime.config.RuntimeConfig and
orion.providers.claude_code.config.ClaudeCodeConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage

# Directories never worth scanning for any project ORION analyzes --
# version control internals, dependency caches, build output, and
# ORION's own runtime data when the target happens to be Orion-AI
# itself. Matched against any path component, not just the root.
DEFAULT_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        "workspace",  # ORION's own runtime data (missions/, companies/, knowledge/, runtime/)
        ".idea",
        ".vscode",
    }
)

# File extensions worth reading content for (imports/exports/TODOs/
# complexity). Everything else is indexed by path/type/size only --
# real, useful metadata without pretending to parse binary or markup
# ORION has no real parser for.
DEFAULT_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".vue",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
    }
)

# Files above this size are indexed (path/type/size/mtime) but never
# read into memory for content-based analysis (imports, TODOs,
# complexity, similarity) -- protects analysis from pathological huge
# generated files (lockfiles, bundles) without excluding them from the
# index entirely.
DEFAULT_MAX_CONTENT_BYTES = 512_000


def _default_workspace_dir() -> Path:
    return bridge_storage.WORKSPACE_DIR / "intelligence"


@dataclass(frozen=True)
class IntelligenceConfig:
    workspace_dir: Path = field(default_factory=_default_workspace_dir)
    # Real, similarity-search threshold (0-1) above which
    # component_finder considers a file a serious reuse candidate.
    similarity_threshold: float = 0.55
    max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES
    ignored_dirs: frozenset[str] = field(default_factory=lambda: DEFAULT_IGNORED_DIRS)
    source_extensions: frozenset[str] = field(default_factory=lambda: DEFAULT_SOURCE_EXTENSIONS)

    @classmethod
    def from_env(cls) -> "IntelligenceConfig":
        workspace_dir = Path(os.environ.get("ORION_INTELLIGENCE_WORKSPACE", str(_default_workspace_dir())))
        threshold = float(os.environ.get("ORION_INTELLIGENCE_SIMILARITY_THRESHOLD", "0.55"))
        max_bytes = int(os.environ.get("ORION_INTELLIGENCE_MAX_CONTENT_BYTES", str(DEFAULT_MAX_CONTENT_BYTES)))
        return cls(workspace_dir=workspace_dir, similarity_threshold=threshold, max_content_bytes=max_bytes)
