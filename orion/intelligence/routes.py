"""HTTP API for orion.intelligence (BETA 008: Project Intelligence).

Same pattern orion.experience.routes/orion.projects.routes already
establish: a separate router, not folded into orion.window.routes,
mounted alongside the other kernel routers in orion.window.app. Every
endpoint here is a thin wrapper over orion.intelligence.services --
the only module allowed to hold real business logic for this
subsystem.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from orion.intelligence import services as intelligence_services

router = APIRouter(prefix="/api", tags=["intelligence"])


class ImpactRequest(BaseModel):
    paths: list[str]
    project_id: str = ""


class PlanRequest(BaseModel):
    request: str
    project_id: str = ""


class ReviewRequest(BaseModel):
    paths: list[str]
    project_id: str = ""


class UnderstandRequest(BaseModel):
    request: str
    project_id: str = ""


@router.get("/intelligence/index")
async def api_intelligence_index(project_id: str = "", force_full: bool = False) -> dict:
    """Real repository_analyzer + project_index scan, incremental
    unless force_full=True."""
    index = intelligence_services.analyze_project(project_id, force_full=force_full)
    return index.to_dict()


@router.get("/intelligence/architecture")
async def api_intelligence_architecture(project_id: str = "") -> dict:
    tree = intelligence_services.get_architecture_map(project_id)
    return tree.to_dict()


@router.get("/intelligence/dependencies")
async def api_intelligence_dependencies(project_id: str = "") -> dict:
    graph = intelligence_services.get_dependency_graph(project_id)
    return graph.to_dict()


@router.get("/intelligence/components")
async def api_intelligence_components(query: str, project_id: str = "", limit: int = 15) -> list[dict]:
    matches = intelligence_services.find_components(query, project_id, limit=limit)
    return [m.to_dict() for m in matches]


@router.post("/intelligence/impact")
async def api_intelligence_impact(payload: ImpactRequest) -> dict:
    report = intelligence_services.compute_impact(payload.paths, project_key=payload.project_id)
    return report.to_dict()


@router.post("/intelligence/plan")
async def api_intelligence_plan(payload: PlanRequest) -> dict:
    plan = intelligence_services.plan_request(payload.request, project_key=payload.project_id)
    return plan.to_dict()


@router.post("/intelligence/review")
async def api_intelligence_review(payload: ReviewRequest) -> dict:
    report = intelligence_services.run_review(payload.paths, project_key=payload.project_id)
    return report.to_dict()


@router.post("/intelligence/understand")
async def api_intelligence_understand(payload: UnderstandRequest) -> dict:
    """The full pre-execution brief: reusable components, plan, and
    impact -- exactly what orion.runtime.services.ask(auto_plan=True)
    computes internally before creating any Mission."""
    brief = intelligence_services.prepare_request(payload.request, project_key=payload.project_id)
    return brief.to_dict() | {"summary_text": brief.summary_text()}


@router.get("/intelligence/knowledge-graph")
async def api_intelligence_knowledge_graph() -> dict:
    graph = intelligence_services.get_knowledge_graph()
    return graph.to_dict()
