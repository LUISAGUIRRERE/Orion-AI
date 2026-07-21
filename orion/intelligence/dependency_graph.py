"""The real Dependency Graph -- built from the actual `import`/`from
... import` statements orion.intelligence.repository_analyzer._extract_python
already collected via ast (Python only; see resolution caveat below).

Resolution, honestly documented rather than pretended-precise: a
Python file's per-import strings (e.g. "orion.executor.services", or
"orion.executor" for a `from orion.executor import registry`
statement) are matched against the real set of module/package names
derived from every Python file this project's ProjectIndex actually
found. An exact submodule match ("orion.executor.services") produces
an edge straight to that file's own module. A package-level import
("orion.executor") produces an edge to that package as a whole -- this
project has no JS/TS-grade symbol resolution, so "depends on
orion.executor" is as precise as an import of one specific name from
that package's __init__ can honestly be represented without it. Any
import that resolves to neither is treated as external and excluded
from the internal graph (still visible per-file in the ProjectIndex's
own FileRecord.imports, never lost, just not graphed).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from orion.intelligence.project_index import ProjectIndex


def module_name_for_path(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    stem = path[: -len(".py")]
    parts = stem.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _package_names_for_path(path: str) -> list[str]:
    """Every real package-level dotted prefix a Python file's own path
    implies, e.g. "orion/executor/adapters/deterministic.py" implies
    packages "orion", "orion.executor", "orion.executor.adapters" --
    derived purely from directory structure, so this works whether or
    not each directory literally has an __init__.py (implicit
    namespace packages resolve the same way real Python resolves
    them)."""
    parts = path.split("/")[:-1]  # directories only, not the filename
    names = []
    for i in range(1, len(parts) + 1):
        names.append(".".join(parts[:i]))
    return names


@dataclass
class DependencyGraph:
    project_key: str
    generated_at: str
    # module/package dotted name -> the real file path it corresponds
    # to (only present for actual modules, not synthetic package nodes
    # that have no matching __init__.py file of their own).
    module_paths: dict[str, str] = field(default_factory=dict)
    purposes: dict[str, str] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=dict)  # module -> [modules it imports]
    reverse_edges: dict[str, list[str]] = field(default_factory=dict)  # module -> [modules that import it]

    def to_dict(self) -> dict:
        return {
            "project_key": self.project_key,
            "generated_at": self.generated_at,
            "module_paths": self.module_paths,
            "purposes": self.purposes,
            "edges": self.edges,
            "reverse_edges": self.reverse_edges,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyGraph":
        return cls(
            project_key=data["project_key"],
            generated_at=data["generated_at"],
            module_paths=dict(data.get("module_paths", {})),
            purposes=dict(data.get("purposes", {})),
            edges={k: list(v) for k, v in data.get("edges", {}).items()},
            reverse_edges={k: list(v) for k, v in data.get("reverse_edges", {}).items()},
        )

    def dependents_of(self, module_name: str) -> list[str]:
        """Direct dependents only -- modules that import this one."""
        return list(self.reverse_edges.get(module_name, []))

    def dependencies_of(self, module_name: str) -> list[str]:
        return list(self.edges.get(module_name, []))

    def impacted_by(self, module_name: str) -> list[str]:
        """Transitive closure over reverse_edges: every module that
        depends on ``module_name`` either directly or through some
        chain of internal imports -- the real "what breaks if I change
        this" answer."""
        seen: set[str] = set()
        queue: deque[str] = deque(self.reverse_edges.get(module_name, []))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(self.reverse_edges.get(current, []))
        return sorted(seen)

    def module_for_path(self, path: str) -> str | None:
        for module, mpath in self.module_paths.items():
            if mpath == path:
                return module
        return None


def build_dependency_graph(index: ProjectIndex) -> DependencyGraph:
    from datetime import datetime, timezone

    real_modules: dict[str, str] = {}
    package_names: set[str] = set()
    purposes: dict[str, str] = {}

    for record in index.files.values():
        if record.language != "python":
            continue
        module_name = module_name_for_path(record.path)
        if module_name:
            real_modules[module_name] = record.path
            purposes[module_name] = record.purpose
        package_names.update(_package_names_for_path(record.path))

    # Every real module is also, by definition, resolvable as itself;
    # every directory-derived package name that has no matching
    # __init__.py module is still a valid resolution target (a
    # namespace package), just with no single file path of its own.
    resolvable = set(real_modules) | package_names

    edges: dict[str, set[str]] = {name: set() for name in real_modules}
    reverse_edges: dict[str, set[str]] = {name: set() for name in real_modules}

    for record in index.files.values():
        if record.language != "python":
            continue
        source_module = module_name_for_path(record.path)
        if source_module is None or source_module not in real_modules:
            continue
        for imported in record.imports:
            imported = imported.lstrip(".")  # relative-import dots carry no resolvable info here
            if not imported:
                continue
            target: str | None = None
            if imported in real_modules:
                target = imported
            else:
                # Walk the dotted path from most to least specific --
                # "orion.executor.services.helper" (an imported NAME,
                # not a module) should still resolve to the real
                # module "orion.executor.services" if that prefix
                # exists.
                candidate_parts = imported.split(".")
                for cut in range(len(candidate_parts), 0, -1):
                    candidate = ".".join(candidate_parts[:cut])
                    if candidate in real_modules or candidate in package_names:
                        target = candidate
                        break
            if target is None or target == source_module:
                continue
            edges.setdefault(source_module, set()).add(target)
            reverse_edges.setdefault(target, set()).add(source_module)

    graph = DependencyGraph(
        project_key=index.project_key,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        module_paths=real_modules,
        purposes=purposes,
        edges={k: sorted(v) for k, v in edges.items() if v},
        reverse_edges={k: sorted(v) for k, v in reverse_edges.items() if v},
    )
    return graph
