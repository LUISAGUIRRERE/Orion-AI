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

from orion.bridge import storage as bridge_storage


@dataclass
class ValidationResult:
    """The outcome of validating every file a mission touched."""

    passed: bool
    errors: list[str] = field(default_factory=list)


def run(files: list[str]) -> ValidationResult:
    """Validate every file path in ``files`` (repository-relative)."""
    errors: list[str] = []
    for rel_path in files:
        path = bridge_storage.REPO_ROOT / rel_path
        if path.suffix != ".py":
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel_path}: {exc}")
    return ValidationResult(passed=not errors, errors=errors)
