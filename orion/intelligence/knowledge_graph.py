"""ORION's Knowledge Graph: typed nodes and relations, not just files.

Seeded once with ORION's own static conceptual schema (Mission
produce PromptPackage, PromptPackage consume Executor, Executor usa
Provider, Provider produce ExecutionResult, ExecutionResult ->
Validation, Validation aprende Experience -- exactly the chain this
Sprint's brief lists), then grows a real, concrete node/edge for every
mission ORION actually processes (see record_mission_knowledge,
called from orion.intelligence.services once a mission's real
ExecutionResult/experience report exist) -- never a static diagram
pretending to be alive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.intelligence import storage

SCHEMA_EDGES: list[tuple[str, str, str]] = [
    ("Mission", "produce", "PromptPackage"),
    ("PromptPackage", "consume", "Executor"),
    ("Executor", "usa", "Provider"),
    ("Provider", "produce", "ExecutionResult"),
    ("ExecutionResult", "valida", "Validation"),
    ("Validation", "aprende", "Experience"),
]


@dataclass
class KnowledgeNode:
    id: str
    type: str
    label: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "label": self.label, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeNode":
        return cls(id=data["id"], type=data["type"], label=data.get("label", data["id"]), metadata=dict(data.get("metadata", {})))


@dataclass
class KnowledgeEdge:
    source: str
    relation: str
    target: str

    def to_dict(self) -> dict:
        return {"source": self.source, "relation": self.relation, "target": self.target}

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEdge":
        return cls(source=data["source"], relation=data["relation"], target=data["target"])


@dataclass
class KnowledgeGraph:
    nodes: dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: list[KnowledgeEdge] = field(default_factory=list)
    updated_at: str = ""

    def add_node(self, node_id: str, node_type: str, label: str | None = None, **metadata) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].metadata.update(metadata)
            return
        self.nodes[node_id] = KnowledgeNode(id=node_id, type=node_type, label=label or node_id, metadata=metadata)

    def add_edge(self, source: str, relation: str, target: str) -> None:
        edge = KnowledgeEdge(source=source, relation=relation, target=target)
        if edge not in self.edges:
            self.edges.append(edge)

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGraph":
        graph = cls(updated_at=data.get("updated_at", ""))
        for raw in data.get("nodes", []):
            node = KnowledgeNode.from_dict(raw)
            graph.nodes[node.id] = node
        graph.edges = [KnowledgeEdge.from_dict(raw) for raw in data.get("edges", [])]
        return graph


def _seed(graph: KnowledgeGraph) -> None:
    for source, relation, target in SCHEMA_EDGES:
        graph.add_node(source, "Concept", source)
        graph.add_node(target, "Concept", target)
        graph.add_edge(source, relation, target)


def load_knowledge_graph() -> KnowledgeGraph:
    raw = storage.read_yaml(storage.knowledge_graph_path(), None)
    if raw is None:
        graph = KnowledgeGraph()
        _seed(graph)
        return graph
    graph = KnowledgeGraph.from_dict(raw)
    _seed(graph)  # idempotent: add_node/add_edge both no-op on repeats
    return graph


def save_knowledge_graph(graph: KnowledgeGraph) -> None:
    graph.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    storage.write_yaml(storage.knowledge_graph_path(), graph.to_dict())


def record_mission_knowledge(
    graph: KnowledgeGraph,
    mission_id: str,
    mission_title: str,
    provider_name: str | None,
    files_touched: list[str],
    confidence_score: float | None,
) -> KnowledgeGraph:
    """Grow the graph with one real mission's real outcome -- exactly
    the "El Knowledge Graph debe crecer automaticamente" requirement.
    Never fabricates a relation for data that was not actually
    provided (a None provider_name, for instance, simply adds no
    Provider-instance edge for this mission)."""
    mission_node = f"Mission:{mission_id}"
    graph.add_node(mission_node, "Mission", f"{mission_id} — {mission_title}")
    graph.add_edge(mission_node, "produce", "PromptPackage")
    graph.add_edge("PromptPackage", "consume", "Executor")

    if provider_name:
        provider_node = f"Provider:{provider_name}"
        graph.add_node(provider_node, "Provider", provider_name)
        graph.add_edge("Executor", "usa", provider_node)
        result_node = f"ExecutionResult:{mission_id}"
        graph.add_node(result_node, "ExecutionResult", f"Resultado de {mission_id}")
        graph.add_edge(provider_node, "produce", result_node)
        graph.add_edge(result_node, "valida", "Validation")

    for path in files_touched:
        file_node = f"File:{path}"
        graph.add_node(file_node, "File", path)
        graph.add_edge(mission_node, "afecta", file_node)

    if confidence_score is not None:
        experience_node = f"Experience:{mission_id}"
        graph.add_node(experience_node, "Experience", f"Experiencia de {mission_id}", confidence=confidence_score)
        graph.add_edge("Validation", "aprende", experience_node)

    return graph
