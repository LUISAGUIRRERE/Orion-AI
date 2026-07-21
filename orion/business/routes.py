"""HTTP API for orion.business (BETA 009: Business Brain).

Same pattern orion.intelligence.routes/orion.experience.routes/
orion.projects.routes already establish: a separate router, mounted
alongside the other kernel routers in orion.window.app. Every
endpoint is a thin wrapper over orion.business.services -- the only
module allowed to hold real business logic for this subsystem.

Routes are namespaced under /api/brain (GET /api/brain/companies, not
a bare GET /companies) -- not just the general /api prefix every other
kernel router uses, and deliberately not /api/business either.
Discovered live while smoke-testing this router, in two layers:
1. orion.projects.routes already owns GET /api/projects, and
   orion.experience.routes already owns GET /api/knowledge (its own,
   older, unrelated "Knowledge Store" from BETA 004) -- FastAPI
   silently matched whichever router was registered first, so
   /api/knowledge was returning Experience's data, not Business
   Brain's.
2. Namespacing under /api/business did not fix it either:
   orion.window.routes already registers GET /api/business/{name}
   (Sprint 004's BusinessUnit-by-slug lookup) on api_router, mounted
   before this router -- a single-segment wildcard that swallows any
   path shaped like /api/business/<anything>, so /api/business/companies
   was being matched as name="companies" against that *older* route.
   Fixed by moving one level further away, to /api/brain, which no
   existing route pattern in this codebase can match.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orion.business import services as business_services

router = APIRouter(prefix="/api/brain", tags=["business"])


class CompanyCreateRequest(BaseModel):
    company_id: str
    name: str
    description: str = ""
    mission: str = ""
    vision: str = ""
    market: str = ""
    business_model: str = ""


class ProjectCreateRequest(BaseModel):
    company_id: str
    name: str
    description: str = ""
    technical_project_id: str | None = None
    keywords: list[str] = Field(default_factory=list)


class UnderstandRequest(BaseModel):
    request: str


@router.get("/companies")
async def api_companies_list() -> list[dict]:
    return [c.to_dict() for c in business_services.list_companies()]


@router.get("/companies/{company_id}")
async def api_company_detail(company_id: str) -> dict:
    company = business_services.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Empresa '{company_id}' no encontrada.")
    return company.to_dict()


@router.post("/companies")
async def api_companies_create(payload: CompanyCreateRequest) -> dict:
    try:
        company = business_services.create_company(
            payload.company_id, payload.name, description=payload.description, mission=payload.mission,
            vision=payload.vision, market=payload.market, business_model=payload.business_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return company.to_dict()


@router.get("/projects")
async def api_projects_list(company_id: str = "") -> list[dict]:
    projects = business_services.list_projects(company_id) if company_id else business_services.list_all_projects()
    return [p.to_dict() for p in projects]


@router.post("/projects")
async def api_projects_create(payload: ProjectCreateRequest) -> dict:
    project = business_services.add_project(
        payload.company_id, payload.name, description=payload.description,
        technical_project_id=payload.technical_project_id, keywords=payload.keywords,
    )
    return project.to_dict()


@router.get("/goals")
async def api_goals_list(company_id: str) -> list[dict]:
    return [g.to_dict() for g in business_services.list_goals(company_id)]


@router.get("/roadmap")
async def api_roadmap_list(company_id: str, status: str | None = None) -> list[dict]:
    return [i.to_dict() for i in business_services.list_roadmap(company_id, status)]


@router.get("/branding")
async def api_branding(company_id: str) -> dict:
    brand = business_services.get_brand(company_id)
    if brand is None:
        raise HTTPException(status_code=404, detail=f"No hay branding registrado para '{company_id}'.")
    return brand.to_dict()


@router.get("/knowledge")
async def api_knowledge(company_id: str) -> dict:
    return {
        "facts": [k.to_dict() for k in business_services.list_knowledge(company_id)],
        "memory": business_services.recall_memory(company_id),
    }


@router.get("/decisions")
async def api_decisions(company_id: str) -> list[dict]:
    return [d.to_dict() for d in business_services.list_decisions(company_id)]


@router.post("/understand")
async def api_business_understand(payload: UnderstandRequest) -> dict:
    """The real "who is this for" resolution -- Company/Project/
    branding/objective/risk -- exactly what the Runtime resolves
    automatically before creating a Mission."""
    brief = business_services.resolve_context(payload.request)
    return brief.to_dict() | {"summary_text": brief.summary_text()}
