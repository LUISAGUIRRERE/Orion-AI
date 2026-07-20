"""HTTP API for the Experience Engine and Knowledge Store.

A separate router (not added into orion/window/routes.py, not added
into orion/bridge/routes.py), mounted alongside the other kernel
routers in orion/window/app.py -- the same pattern
orion.projects.routes already established.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orion.experience import knowledge_store, storage
from orion.experience.models import ExperienceReport, KnowledgeItem, KnowledgeItemType

router = APIRouter(prefix="/api", tags=["experience"])


@router.get("/experience/{mission_id}", response_model=ExperienceReport)
async def api_experience_report(mission_id: str) -> ExperienceReport:
    """Return one mission's Experience Report as JSON."""
    report = storage.load_report(mission_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No hay Experience Report para '{mission_id}'.")
    return report


@router.get("/knowledge", response_model=list[KnowledgeItem])
async def api_knowledge_list(
    type: KnowledgeItemType | None = None,  # noqa: A002 - matches the query param name intentionally
    project_id: str | None = None,
    tag: str | None = None,
) -> list[KnowledgeItem]:
    """Return every KnowledgeItem, optionally filtered by type,
    project, or tag -- this is the answer to "what can we reuse" /
    "what should we avoid" without re-reading any mission's full
    execution history."""
    return knowledge_store.list_items(item_type=type, project_id=project_id, tag=tag)


@router.get("/knowledge/{item_id}", response_model=KnowledgeItem)
async def api_knowledge_detail(item_id: str) -> KnowledgeItem:
    """Return a single KnowledgeItem by id."""
    item = knowledge_store.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Knowledge item '{item_id}' not found")
    return item
