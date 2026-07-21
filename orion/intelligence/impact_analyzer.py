"""Real impact analysis: before ORION modifies a file, this module
computes exactly what actually depends on it (via
dependency_graph.DependencyGraph.impacted_by, itself built from real
ast-extracted imports), which real test files are related, and a
risk/complexity read-out -- never a guessed or hardcoded number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.intelligence.dependency_graph import DependencyGraph, module_name_for_path
from orion.intelligence.project_index import ProjectIndex


@dataclass
class ImpactReport:
    target_paths: list[str]
    affected_modules: list[str]
    affected_files: list[str]
    related_tests: list[str]
    complexity_sum: int
    risk: str
    reasons: list[str] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "target_paths": self.target_paths,
            "affected_modules": self.affected_modules,
            "affected_files": self.affected_files,
            "related_tests": self.related_tests,
            "complexity_sum": self.complexity_sum,
            "risk": self.risk,
            "reasons": self.reasons,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImpactReport":
        return cls(**data)


def _find_related_tests(index: ProjectIndex, affected_modules: set[str], affected_files: set[str]) -> list[str]:
    """A test file is "related" if it either (a) really imports one of
    the affected modules (real ast-extracted FileRecord.imports, same
    source of truth the dependency graph itself uses), or (b) its own
    filename follows the test_<module>.py / <module>_test.py
    convention against an affected file's stem -- both real,
    convention-based signals, never a guess at test coverage that
    doesn't exist."""
    affected_stems = {path.rsplit("/", 1)[-1].rsplit(".", 1)[0] for path in affected_files}
    related: set[str] = set()

    for record in index.files.values():
        if record.purpose != "test":
            continue
        if set(record.imports) & affected_modules:
            related.add(record.path)
            continue
        test_stem = record.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        normalized = test_stem
        for prefix in ("test_",):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        for suffix in ("_test", ".test", ".spec"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        if normalized in affected_stems:
            related.add(record.path)

    return sorted(related)


def compute_impact(index: ProjectIndex, graph: DependencyGraph, target_paths: list[str]) -> ImpactReport:
    """Real, honest impact for one or more target paths. A target path
    that is not Python (no module resolution possible with this
    Sprint's real ast-based graph) still contributes to
    ``affected_files`` (itself) but cannot contribute transitive
    dependents -- documented via ``reasons``, never silently
    fabricated as zero-impact."""
    affected_modules: set[str] = set()
    affected_files: set[str] = {p for p in target_paths}
    reasons: list[str] = []

    for target_path in target_paths:
        module_name = module_name_for_path(target_path)
        if module_name is None:
            reasons.append(f"'{target_path}' no es un modulo Python: solo se cuenta el archivo mismo, sin dependientes transitivos.")
            continue
        dependents = graph.impacted_by(module_name)
        if not dependents:
            reasons.append(f"'{module_name}' no tiene dependientes internos conocidos en el grafo actual.")
        affected_modules.add(module_name)
        affected_modules.update(dependents)
        for dep_module in dependents:
            dep_path = graph.module_paths.get(dep_module)
            if dep_path:
                affected_files.add(dep_path)

    complexity_sum = sum(
        index.files[path].complexity for path in affected_files if path in index.files
    )
    related_tests = _find_related_tests(index, affected_modules, affected_files)

    file_count = len(affected_files)
    if file_count <= 3:
        risk = "bajo"
    elif file_count <= 10:
        risk = "medio"
    else:
        risk = "alto"

    core_purposes = {"api", "service", "model"}
    touches_core_without_tests = any(
        index.files[path].purpose in core_purposes
        for path in affected_files
        if path in index.files
    ) and not related_tests
    if touches_core_without_tests and risk == "bajo":
        risk = "medio"
        reasons.append("toca componentes core (api/service/model) sin pruebas relacionadas encontradas: riesgo elevado un nivel.")

    return ImpactReport(
        target_paths=list(target_paths),
        affected_modules=sorted(affected_modules),
        affected_files=sorted(affected_files),
        related_tests=related_tests,
        complexity_sum=complexity_sum,
        risk=risk,
        reasons=reasons,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
