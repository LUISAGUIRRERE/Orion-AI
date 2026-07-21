"""HTTP routes for The Window: HTML pages and JSON API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from orion.agents.builder import agent as builder_agent
from orion.agents.coo import agent as coo_agent
from orion.agents.coo import metrics as coo_metrics
from orion.bridge import services as bridge_services
from orion.execution import pipeline as execution_pipeline
from orion.experience import knowledge_store, storage as experience_storage
from orion.business import services as business_services
from orion.governance import services as governance_services
from orion.intelligence import services as intelligence_services
from orion.projects import registry as project_registry
from orion.projects import services as project_services
from orion.window import services
from orion.window.models import BusinessUnit, DashboardSummary, Event

templates = Jinja2Templates(directory=str(services.REPO_ROOT / "orion" / "window" / "templates"))

pages_router = APIRouter()
api_router = APIRouter(prefix="/api")


def _topbar_context() -> dict[str, str | int]:
    """Shared context for the top bar, present on every page."""
    now = datetime.now(timezone.utc)
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M UTC"),
        "business_unit_count": len(services.load_business_units()),
        "event_count": services.count_events(),
    }


@pages_router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render the main dashboard: business unit cards and recent events."""
    summary = services.get_dashboard_summary()
    mission_summary = bridge_services.get_mission_summary()
    builder_state = builder_agent.get_state()
    coo_state = coo_agent.get_state()
    coo_metrics_data = coo_metrics.compute()
    execution_state = execution_pipeline.get_state()
    business_overview = project_services.business_overview()
    context = {
        "summary": summary,
        "mission_summary": mission_summary,
        "builder_state": builder_state,
        "coo_state": coo_state,
        "coo_metrics": coo_metrics_data,
        "execution_state": execution_state,
        "business_overview": business_overview,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "index.html", context)


@pages_router.get("/business/{slug}", response_class=HTMLResponse)
async def business_detail_page(request: Request, slug: str) -> HTMLResponse:
    """Render the detail page for a single business unit."""
    unit = services.get_business_unit(slug)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"Business unit '{slug}' not found")
    context = {"unit": unit, **_topbar_context()}
    return templates.TemplateResponse(request, "project.html", context)


@pages_router.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request) -> HTMLResponse:
    """Render the list of every project ORION administers."""
    projects = project_registry.list_projects()
    companies = [project_services.describe_project(p) for p in projects]
    context = {"companies": companies, **_topbar_context()}
    return templates.TemplateResponse(request, "projects.html", context)


@pages_router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(request: Request, project_id: str) -> HTMLResponse:
    """Render a single project: configuration, metrics, and its missions."""
    project = project_registry.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    context = {
        "project": project,
        "summary": project_services.describe_project(project),
        "missions": project_services.missions_for_project(project_id),
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "project_detail.html", context)


@pages_router.get("/missions", response_class=HTMLResponse)
async def missions_page(request: Request) -> HTMLResponse:
    """Render the list of every mission tracked by the Command Bridge."""
    missions = bridge_services.list_missions()
    context = {"missions": missions, **_topbar_context()}
    return templates.TemplateResponse(request, "missions.html", context)


@pages_router.get("/missions/{mission_id}", response_class=HTMLResponse)
async def mission_detail_page(request: Request, mission_id: str) -> HTMLResponse:
    """Render a single mission: info, timeline, messages, and events."""
    mission = bridge_services.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    experience_report = experience_storage.load_report(mission_id)
    knowledge_items = [
        item for item in knowledge_store.list_items() if item.source_mission_id == mission_id
    ]
    context = {
        "mission": mission,
        "events": bridge_services.get_events(mission_id),
        "messages": bridge_services.get_messages(mission_id),
        "experience_report": experience_report,
        "knowledge_items": knowledge_items,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "mission_detail.html", context)


@api_router.get("/dashboard", response_model=DashboardSummary)
async def api_dashboard() -> DashboardSummary:
    """Return the aggregated dashboard payload as JSON."""
    return services.get_dashboard_summary()


@api_router.get("/business", response_model=list[BusinessUnit])
async def api_business_list() -> list[BusinessUnit]:
    """Return every business unit as JSON."""
    return services.load_business_units()


@api_router.get("/business/{name}", response_model=BusinessUnit)
async def api_business_detail(name: str) -> BusinessUnit:
    """Return a single business unit by slug as JSON."""
    unit = services.get_business_unit(name)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"Business unit '{name}' not found")
    return unit


@api_router.get("/events", response_model=list[Event])
async def api_events(limit: int = 50) -> list[Event]:
    """Return the most recent events as JSON."""
    return services.get_events(limit=limit)


# ---------------------------------------------------------------------------
# BETA 008: Project Intelligence pages. Deliberately call
# orion.intelligence.services directly (never orion.intelligence.routes'
# JSON API internally) -- the exact same convention every other page
# above already follows: HTML pages call the owning subsystem's
# services module directly, while a separate JSON API router (mounted
# in orion.window.app) exists in parallel for external consumers.
# ---------------------------------------------------------------------------


def _project_choices() -> list[str]:
    """Every project_key a person could sensibly pick from this
    dropdown: ORION-AI's own checkout, plus every registered Project."""
    return [""] + [p.project_id for p in project_registry.list_projects()]


@pages_router.get("/intelligence", response_class=HTMLResponse)
async def intelligence_index_page(request: Request, project_id: str = "") -> HTMLResponse:
    """Proyecto: a real, freshly (incrementally) analyzed summary of
    the selected project -- languages, frameworks, entrypoints, TODOs,
    purpose breakdown."""
    index = intelligence_services.analyze_project(project_id)
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "index": index,
        "profile": index.profile,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_index.html", context)


@pages_router.get("/intelligence/architecture", response_class=HTMLResponse)
async def intelligence_architecture_page(request: Request, project_id: str = "") -> HTMLResponse:
    """Arquitectura / Mapa: the live architecture tree, built fresh
    from the current index every time this page is requested."""
    tree = intelligence_services.get_architecture_map(project_id)
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "tree": tree,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_architecture.html", context)


@pages_router.get("/intelligence/dependencies", response_class=HTMLResponse)
async def intelligence_dependencies_page(
    request: Request, project_id: str = "", impacted_by: str = ""
) -> HTMLResponse:
    """Dependencias: the real dependency graph, with an optional real
    "what depends on this" query (DependencyGraph.impacted_by)."""
    graph = intelligence_services.get_dependency_graph(project_id)
    impacted: list[str] | None = None
    resolved_module: str | None = None
    if impacted_by:
        resolved_module = graph.module_for_path(impacted_by) if ("/" in impacted_by or impacted_by.endswith(".py")) else impacted_by
        impacted = graph.impacted_by(resolved_module) if resolved_module else []
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "graph": graph,
        "impacted_by": impacted_by,
        "resolved_module": resolved_module,
        "impacted": impacted,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_dependencies.html", context)


@pages_router.get("/intelligence/impact", response_class=HTMLResponse)
async def intelligence_impact_page(request: Request, project_id: str = "", paths: str = "") -> HTMLResponse:
    """Impacto: a real pre-modification Impact Analysis over one or
    more repo-relative paths, submitted one per line."""
    path_list = [p.strip() for p in paths.splitlines() if p.strip()]
    report = intelligence_services.compute_impact(path_list, project_key=project_id) if path_list else None
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "paths_raw": paths,
        "report": report,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_impact.html", context)


@pages_router.get("/intelligence/plan", response_class=HTMLResponse)
async def intelligence_plan_page(request: Request, project_id: str = "", plan_request: str = "") -> HTMLResponse:
    """Plan: the rule-based Task Planner's real decomposition of a
    natural-language request into one or more Missions."""
    plan = intelligence_services.plan_request(plan_request, project_key=project_id) if plan_request.strip() else None
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "plan_request": plan_request,
        "plan": plan,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_plan.html", context)


@pages_router.get("/intelligence/review", response_class=HTMLResponse)
async def intelligence_review_page(request: Request, project_id: str = "", paths: str = "") -> HTMLResponse:
    """Revisión: a real Reviewer pass (syntax/imports/docstrings/
    naming/security/secrets) over one or more repo-relative paths."""
    path_list = [p.strip() for p in paths.splitlines() if p.strip()]
    report = intelligence_services.run_review(path_list, project_key=project_id) if path_list else None
    context = {
        "project_id": project_id,
        "project_choices": _project_choices(),
        "paths_raw": paths,
        "report": report,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_review.html", context)


@pages_router.get("/intelligence/knowledge-graph", response_class=HTMLResponse)
async def intelligence_knowledge_graph_page(request: Request) -> HTMLResponse:
    """Knowledge Graph: ORION's single, global, ever-growing model of
    its own operational schema plus every project component it has
    ever touched."""
    graph = intelligence_services.get_knowledge_graph()
    context = {
        "graph": graph,
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "intelligence_knowledge_graph.html", context)


# ---------------------------------------------------------------------------
# BETA 009: Business Brain pages. /companies (not /business, which
# Sprint 004's BusinessUnit pages already own) -- one list page plus
# one rich per-company Dashboard covering every section this Sprint
# asks for (Proyectos/Objetivos/Roadmap/Branding/Documentos/
# Decisiones/Conocimiento) in a single page, matching the spec's own
# "cada empresa tendra su propio Dashboard".
# ---------------------------------------------------------------------------


@pages_router.get("/companies", response_class=HTMLResponse)
async def companies_page(request: Request) -> HTMLResponse:
    companies = business_services.list_companies()
    context = {"companies": companies, **_topbar_context()}
    return templates.TemplateResponse(request, "companies.html", context)


@pages_router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_dashboard_page(request: Request, company_id: str) -> HTMLResponse:
    company = business_services.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Empresa '{company_id}' no encontrada.")
    context = {
        "company": company,
        "projects": business_services.list_projects(company_id),
        "brand": business_services.get_brand(company_id),
        "goals": business_services.list_goals(company_id),
        "roadmap": business_services.list_roadmap(company_id),
        "documents": business_services.list_documents(company_id),
        "decisions": business_services.list_decisions(company_id),
        "knowledge": business_services.list_knowledge(company_id),
        "memory": business_services.recall_memory(company_id),
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "company_dashboard.html", context)


# ---------------------------------------------------------------------------
# BETA 010: Governance page. One page covering every section this
# Sprint's own WINDOW list asks for -- Governance/Policies/Risk/
# Confidence/Audit/Execution Mode/Approval Queue -- same "single real
# Dashboard" convention the Business Brain company page already
# established, rather than seven separate near-empty pages.
# ---------------------------------------------------------------------------


@pages_router.get("/governance", response_class=HTMLResponse)
async def governance_page(request: Request) -> HTMLResponse:
    mode_profile = governance_services.get_mode_profile()
    context = {
        "mode_profile": mode_profile,
        "mode_history": list(reversed(governance_services.execution_mode_module.get_mode_history()))[:20],
        "policies": governance_services.describe_policies(),
        "pending_approvals": governance_services.list_pending_approvals(),
        "all_approvals": list(reversed(governance_services.approval_engine.list_all()))[:30],
        "audit_entries": list(reversed(governance_services.list_audit()))[:30],
        "rollbacks": governance_services.rollback.list_rollbacks(),
        **_topbar_context(),
    }
    return templates.TemplateResponse(request, "governance.html", context)
