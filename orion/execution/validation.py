"""Pre-commit validation for the Execution Pipeline.

Nothing is ever committed unless every check here passes. A failed
validation always ends the mission in FAILED and the pipeline never
runs ``git commit`` — see pipeline.py's Golden Rule.

Kept deliberately simple, per this Sprint's spec: every touched Python
file must at least parse. Non-Python artifacts (markdown, text, etc.)
have nothing to validate syntactically and always pass. Future Sprints
can register additional checks here without changing the Pipeline.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge import storage as bridge_storage


@dataclass
class ValidationResult:
    """The outcome of validating every file a mission touched."""

    passed: bool
    errors: list[str] = field(default_factory=list)


def run(files: list[str], repo_root: Path = bridge_storage.REPO_ROOT) -> ValidationResult:
    """Validate every file path in ``files`` (repository-relative).

    BETA 003 fix: ``repo_root`` is now an explicit parameter, defaulting
    to Orion-AI's own repository exactly as before (zero behavior
    change for every existing caller). This was a latent bug since
    ORION ALPHA 001 introduced external repo_roots: validation always
    checked ``bridge_storage.REPO_ROOT / rel_path`` regardless of which
    project a mission actually belonged to. It never surfaced before
    now because every non-``.py`` file (every artifact any mission has
    produced against an external project so far -- markdown, TSX,
    JSON, CSS) is skipped below without ever being read, so the wrong
    path was silently never touched. It would have raised on the first
    ``.py`` file ever committed to an external project. Discovered
    while wiring the Executor (BETA 003), fixed here rather than
    deferred, since a `.py` artifact from a future adapter would have
    hit it immediately.
    """
    errors: list[str] = []
    for rel_path in files:
        path = repo_root / rel_path
        if path.suffix != ".py":
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel_path}: {exc}")
    return ValidationResult(passed=not errors, errors=errors)
