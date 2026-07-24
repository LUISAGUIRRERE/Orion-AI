"""Public entry points for orion.intelligence -- the only module the
CLI (bin/orion), the Runtime (orion.runtime), and The Window are
allowed to call directly. Same "one entry point per subsystem"
convention orion.executor.services/orion.experience.services/
orion.runtime.services already establish. Every function here is a
thin, real orchestration over repository_analyzer/project_index/
architecture_map/dependency_graph/component_finder/impact_analyzer/
task_planner/knowledge_graph/reviewer -- no business logic is
duplicated here that already lives in one of those modules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from orion.execution import git_manager
from orion.intelligence import (
    architecture_map,
    component_finder,
    dependency_graph,
    impact_analyzer,
    knowledge_graph,
    project_index,
    reviewer,
    storage,
    task_planner,
)
from orion.intelligence.architecture_map import ArchitectureNode
from orion.intelligence.component_finder import ComponentMatch
from orion.intelligence.config import IntelligenceConfig
from orion.intelligence.dependency_graph import DependencyGraph
from orion.intelligence.impact_analyzer import ImpactReport
from orion.intelligence.knowledge_graph import KnowledgeGraph
from orion.intelligence.project_index import ProjectIndex
from orion.intelligence.reviewer import ReviewReport
from orion.intelligence.task_planner import Plan
from orion.projects import registry as project_registry

AUTHOR = "Intelligence"


def _emit(mission_id: str | None, event_type: str, message: str) -> None:
    """Real event emission, reusing orion.runtime.events.emit (never a
    parallel event system) -- works whether or not a Runtime API
    process is currently running, since emit() always records through
    orion.bridge.services.record_event first (durable) and only
    additionally publishes to the in-process SSE bus if something is
    listening. A no-op, safely, when ``mission_id`` is None (e.g. a
    standalone `orion analyze` with no mission attached)."""
    if not mission_id:
        return
    from orion.runtime import events as runtime_events

    runtime_events.emit(mission_id, event_type, message, AUTHOR)


def resolve_repo_root(project_key: str) -> Path:
    """Same resolution orion.execution.pipeline.run() already uses for
    a Mission's project: a registered Project's own local_path if it
    has one, otherwise ORION-AI's own checkout. project_key="" or
    "_self" always means ORION-AI's own checkout."""
    if not project_key or project_key == storage.SELF_PROJECT_KEY:
        return git_manager.REPO_ROOT
    project = project_registry.get_project(project_key)
    if project and project.local_path:
        return Path(project.local_path)
    return git_manager.REPO_ROOT


def analyze_project(
    project_key: str = "",
    force_full: bool = False,
    mission_id: str | None = None,
) -> ProjectIndex:
    """repository_analyzer + project_index, real and incremental
    unless ``force_full``. This is what `orion analyze`/`orion
    understand` and every other Intelligence function that needs a
    fresh index call first."""
    _emit(mission_id, "analysis_started", f"Analizando proyecto '{project_key or storage.SELF_PROJECT_KEY}'.")
    repo_root = resolve_repo_root(project_key)
    index = project_index.build_index(repo_root, project_key or storage.SELF_PROJECT_KEY, force_full=force_full)
    _emit(
        mission_id,
        "analysis_finished",
        f"Analisis completado: {index.file_count()} archivos indexados en '{project_key or storage.SELF_PROJECT_KEY}'.",
    )
    return index


def get_architecture_map(project_key: str = "", mission_id: str | None = None) -> ArchitectureNode:
    """Real architecture_map.build_architecture_map over a fresh index."""
    index = analyze_project(project_key, mission_id=mission_id)
    tree = architecture_map.build_architecture_map(index)
    storage.write_yaml(storage.architecture_map_path(project_key or storage.SELF_PROJECT_KEY), tree.to_dict())
    return tree


def get_dependency_graph(project_key: str = "", mission_id: str | None = None) -> DependencyGraph:
    """Real dependency_graph.build_dependency_graph over a fresh index."""
    index = analyze_project(project_key, mission_id=mission_id)
    graph = dependency_graph.build_dependency_graph(index)
    storage.write_yaml(storage.dependency_graph_path(project_key or storage.SELF_PROJECT_KEY), graph.to_dict())
    _emit(mission_id, "graph_updated", f"Grafo de dependencias actualizado: {len(graph.module_paths)} modulos.")
    return graph


def find_components(
    query: str,
    project_key: str = "",
    limit: int = 15,
    mission_id: str | None = None,
) -> list[ComponentMatch]:
    """Real component_finder.find_components search over a fresh index."""
    index = analyze_project(project_key, mission_id=mission_id)
    config = IntelligenceConfig.from_env()
    return component_finder.find_components(index, query, limit=limit, threshold=config.similarity_threshold)


def compute_impact(
    target_paths: list[str],
    project_key: str = "",
    mission_id: str | None = None,
) -> ImpactReport:
    """Real impact_analyzer.compute_impact for a fresh index/graph pair; persists the report."""
    index = analyze_project(project_key, mission_id=mission_id)
    graph = get_dependency_graph(project_key, mission_id=mission_id)
    report = impact_analyzer.compute_impact(index, graph, target_paths)

    report_id = uuid.uuid4().hex[:12]
    storage.write_yaml(storage.impact_report_path(project_key or storage.SELF_PROJECT_KEY, report_id), report.to_dict())
    _emit(
        mission_id,
        "impact_ready",
        f"Impacto calculado: {len(report.affected_files)} archivo(s) afectado(s), "
        f"{len(report.related_tests)} prueba(s) relacionada(s), riesgo {report.risk}.",
    )
    return report


def run_review(paths: list[str], project_key: str = "", mission_id: str | None = None) -> ReviewReport:
    """Real reviewer.review_files over the given paths; persists the report."""
    repo_root = resolve_repo_root(project_key)
    report = reviewer.review_files(paths, repo_root)

    report_id = uuid.uuid4().hex[:12]
    storage.write_yaml(storage.review_report_path(project_key or storage.SELF_PROJECT_KEY, report_id), report.to_dict())
    _emit(
        mission_id,
        "review_completed",
        f"Revision completada sobre {len(paths)} archivo(s): {len(report.findings)} hallazgo(s), "
        f"{'aprobada' if report.passed() else 'con errores'}.",
    )
    return report


def plan_request(request: str, project_key: str = "", mission_id: str | None = None) -> Plan:
    """Real task_planner.plan_request; persists the resulting Plan under
    this project's storage. Shared by both `orion plan` and
    prepare_request() below -- the decomposition logic itself lives
    only in task_planner.py."""
    plan = task_planner.plan_request(request)
    storage.write_yaml(storage.plan_path(project_key or storage.SELF_PROJECT_KEY, plan.plan_id), plan.to_dict())
    _emit(mission_id, "planner_ready", f"Plan generado ('{plan.template}'): {len(plan.steps)} mision(es).")
    return plan


def get_knowledge_graph() -> KnowledgeGraph:
    """Load the single global Knowledge Graph."""
    return knowledge_graph.load_knowledge_graph()


def record_mission_knowledge(
    mission_id: str,
    mission_title: str,
    provider_name: str | None,
    files_touched: list[str],
    confidence_score: float | None,
) -> KnowledgeGraph:
    """Record a finished Mission's real outcome into the Knowledge Graph and persist it."""
    graph = knowledge_graph.load_knowledge_graph()
    knowledge_graph.record_mission_knowledge(graph, mission_id, mission_title, provider_name, files_touched, confidence_score)
    knowledge_graph.save_knowledge_graph(graph)
    _emit(
        mission_id,
        "knowledge_updated",
        f"Knowledge Graph actualizado: {graph.node_count()} nodos, {graph.edge_count()} relaciones.",
    )
    return graph


@dataclass
class IntelligenceBrief:
    """Exactly what a CEO reading `orion ask`'s output needs to see
    before ORION starts working -- every number below comes from a
    real analysis of the real project, never a placeholder."""

    project_key: str
    request: str
    index_file_count: int
    reusable_components: list[ComponentMatch]
    plan: Plan
    impact: ImpactReport
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "project_key": self.project_key,
            "request": self.request,
            "index_file_count": self.index_file_count,
            "reusable_components": [m.to_dict() for m in self.reusable_components],
            "plan": self.plan.to_dict(),
            "impact": self.impact.to_dict(),
        }

    def summary_text(self) -> str:
        """The exact shape of message this Sprint's success criteria
        asks ORION to produce internally before executing."""
        lines = [
            "He analizado el proyecto.",
            f"Encontre {len(self.reusable_components)} componentes reutilizables.",
            f"El cambio afectara {len(self.impact.affected_files)} archivos.",
            f"Hay {len(self.impact.related_tests)} pruebas relacionadas.",
            f"He dividido el trabajo en {len(self.plan.steps)} misiones.",
            f"El riesgo es {self.impact.risk}.",
            "Comienzo la ejecucion.",
        ]
        return "\n".join(lines)


def prepare_request(request: str, project_key: str = "", mission_id: str | None = None) -> IntelligenceBrief:
    """The real "understand before you write a line of code" pass:
    analyze the project, find real reuse candidates for this request,
    decompose it into a real Plan, and compute the real impact of the
    top reuse candidates -- everything `orion ask` prints before a
    single Mission is created. Reused as-is by
    orion.runtime.services.ask() (see BETA 008's Runtime integration)
    so the CLI and the Runtime API produce identical, real briefs.
    """
    index = analyze_project(project_key, mission_id=mission_id)
    matches = component_finder.find_components(
        index, request, limit=15, threshold=IntelligenceConfig.from_env().similarity_threshold
    )
    _emit(mission_id, "component_search_completed", f"Componentes reutilizables encontrados: {len(matches)}.")

    plan = plan_request(request, project_key=project_key, mission_id=mission_id)

    graph = dependency_graph.build_dependency_graph(index)
    target_paths = [m.path for m in matches[:10]]
    if target_paths:
        impact = impact_analyzer.compute_impact(index, graph, target_paths)
    else:
        from datetime import datetime, timezone

        impact = ImpactReport(
            target_paths=[],
            affected_modules=[],
            affected_files=[],
            related_tests=[],
            complexity_sum=0,
            risk="bajo",
            reasons=["No se encontraron componentes existentes relacionados con esta peticion: se creara codigo nuevo."],
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    _emit(
        mission_id,
        "impact_ready",
        f"Impacto calculado: {len(impact.affected_files)} archivo(s), riesgo {impact.risk}.",
    )

    from datetime import datetime, timezone

    return IntelligenceBrief(
        project_key=project_key or storage.SELF_PROJECT_KEY,
        request=request,
        index_file_count=index.file_count(),
        reusable_components=matches,
        plan=plan,
        impact=impact,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
