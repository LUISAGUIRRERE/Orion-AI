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
