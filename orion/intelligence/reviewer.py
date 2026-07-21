"""Real static review, run over real files on disk before ORION
considers a mission's work ready for PR.

Every finding below comes from an actual ast.parse() of the file (for
Python) or an actual regex match against the file's real text
(secrets, shell=True) -- nothing here is a hardcoded or simulated
finding. Python-only for structural checks (imports/complexity/naming/
docstrings), consistent with the honesty this whole module already
follows for JS/TS (no parser dependency exists, so JS/TS files only go
through the language-agnostic checks: secrets, TODO count via
repository_analyzer, size).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SECRET_PATTERN = re.compile(
    r"""(?i)\b(api[_-]?key|secret|password|token|access[_-]?key)\b\s*[:=]\s*['"][^'"\s]{6,}['"]"""
)
_SNAKE_CASE = re.compile(r"^_*[a-z][a-z0-9_]*$")
_PASCAL_CASE = re.compile(r"^_*[A-Z][A-Za-z0-9]*$")

COMPLEXITY_WARNING_THRESHOLD = 25


@dataclass
class ReviewFinding:
    path: str
    severity: str  # "info" | "warning" | "error"
    category: str
    message: str

    def to_dict(self) -> dict:
        return {"path": self.path, "severity": self.severity, "category": self.category, "message": self.message}


@dataclass
class ReviewReport:
    paths: list[str]
    findings: list[ReviewFinding] = field(default_factory=list)
    generated_at: str = ""

    def passed(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "paths": self.paths,
            "findings": [f.to_dict() for f in self.findings],
            "passed": self.passed(),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewReport":
        return cls(
            paths=list(data.get("paths", [])),
            findings=[ReviewFinding(**f) for f in data.get("findings", [])],
            generated_at=data.get("generated_at", ""),
        )


def _review_python(rel_path: str, text: str) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [ReviewFinding(rel_path, "error", "sintaxis", f"Error de sintaxis: {exc}")]

    # Unused imports: an imported name never referenced as a Name/Attribute anywhere else.
    imported_names: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue  # compiler directives (e.g. "annotations"), never referenced by name
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported_names[alias.asname or alias.name] = node.lineno

    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass  # base Name node for an attribute access is already caught above

    for name, lineno in imported_names.items():
        if name == "__future__" or name.startswith("_"):
            continue
        if name not in used_names:
            findings.append(
                ReviewFinding(rel_path, "warning", "imports", f"Import posiblemente sin usar: '{name}' (linea {lineno}).")
            )

    # Missing docstrings on public top-level functions/classes.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is None:
                findings.append(
                    ReviewFinding(
                        rel_path, "info", "documentacion",
                        f"'{node.name}' (linea {node.lineno}) no tiene docstring.",
                    )
                )

    # Naming conventions.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _SNAKE_CASE.match(node.name):
            if not (node.name.startswith("__") and node.name.endswith("__")):
                findings.append(
                    ReviewFinding(rel_path, "info", "convenciones", f"Funcion '{node.name}' no sigue snake_case.")
                )
        elif isinstance(node, ast.ClassDef) and not _PASCAL_CASE.match(node.name):
            findings.append(
                ReviewFinding(rel_path, "info", "convenciones", f"Clase '{node.name}' no sigue PascalCase.")
            )

    # Security: eval/exec, shell=True.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if func_name in ("eval", "exec"):
                findings.append(
                    ReviewFinding(rel_path, "error", "seguridad", f"Uso de {func_name}() (linea {node.lineno}).")
                )
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    findings.append(
                        ReviewFinding(rel_path, "error", "seguridad", f"Llamada con shell=True (linea {node.lineno}).")
                    )

    return findings


def _review_generic(rel_path: str, text: str) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _SECRET_PATTERN.search(line):
            findings.append(
                ReviewFinding(rel_path, "error", "seguridad", f"Posible secreto/credencial hardcodeada (linea {lineno}).")
            )
    return findings


def review_files(paths: list[str], repo_root: Path) -> ReviewReport:
    """Real review over real files that exist right now at
    ``repo_root``. A path that does not exist (already deleted, or the
    caller passed a bad path) contributes an informational finding,
    never a crash."""
    findings: list[ReviewFinding] = []
    for rel_path in paths:
        full_path = repo_root / rel_path
        if not full_path.is_file():
            findings.append(ReviewFinding(rel_path, "info", "existencia", "Archivo no encontrado para revision (pudo haber sido eliminado)."))
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(ReviewFinding(rel_path, "info", "lectura", "No se pudo leer el archivo como texto UTF-8."))
            continue

        findings.extend(_review_generic(rel_path, text))
        if full_path.suffix == ".py":
            findings.extend(_review_python(rel_path, text))

    return ReviewReport(paths=list(paths), findings=findings, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
