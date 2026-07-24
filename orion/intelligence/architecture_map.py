"""The live Architecture Map: a directory-derived module tree built
fresh from a ProjectIndex every time it's requested (see
services.get_architecture_map) -- "vivo" here means "always reflects
the index's current state," not "separately, expensively
recomputed" -- building the tree from an already-built ProjectIndex is
cheap (one pass over already-known file paths), so there is no
separate incremental-cache concern the way there is for the index
itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion.intelligence.project_index import ProjectIndex


@dataclass
class ArchitectureNode:
    name: str
    path: str  # "" for the synthetic root
    file_count: int = 0
    children: dict[str, "ArchitectureNode"] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "file_count": self.file_count,
            "children": [child.to_dict() for child in sorted(self.children.values(), key=lambda n: n.name)],
        }

    def total_files(self) -> int:
        return self.file_count + sum(child.total_files() for child in self.children.values())


def build_architecture_map(index: ProjectIndex, max_depth: int = 3) -> ArchitectureNode:
    """Group every indexed file by its directory path, up to
    ``max_depth`` directory levels deep, into a real tree -- e.g. for
    this repository: ORION -> orion -> {runtime, window, agents/builder,
    providers/claude_code, intelligence, ...}, exactly the shape the
    Sprint's own example asks for, derived from real paths, not a
    hardcoded list of module names.
    """
    root = ArchitectureNode(name=index.project_key or "root", path="")

    for record in index.files.values():
        parts = record.path.split("/")
        dir_parts = parts[:-1]  # the file's own name is a leaf, not a tree node
        node = root
        for depth, part in enumerate(dir_parts[:max_depth]):
            if part not in node.children:
                child_path = "/".join(dir_parts[: depth + 1])
                node.children[part] = ArchitectureNode(name=part, path=child_path)
            node = node.children[part]
        node.file_count += 1

    return root
