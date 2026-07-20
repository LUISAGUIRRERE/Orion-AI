"""FastAPI application entry point for The Window.

Run with:

    uvicorn orion.window.app:app --host 0.0.0.0 --port 8080

or directly:

    python -m orion.window.app
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from orion.bridge import storage as bridge_storage
from orion.bridge.routes import router as bridge_api_router
from orion.experience.routes import router as experience_api_router
from orion.projects import registry as project_registry
from orion.projects import storage as project_storage
from orion.projects.routes import router as projects_api_router
from orion.window import services
from orion.window.routes import api_router, pages_router

app = FastAPI(title="ORION — The Window", description="CEO Control Center for ORION OS.")

app.mount(
    "/static",
    StaticFiles(directory=str(services.REPO_ROOT / "orion" / "window" / "static")),
    name="static",
)

app.include_router(pages_router)
app.include_router(api_router)
app.include_router(bridge_api_router)
app.include_router(projects_api_router)
app.include_router(experience_api_router)


@app.on_event("startup")
async def on_startup() -> None:
    """Ensure the workspace (business units, events database, the
    Command Bridge's mission storage, and the Project Registry) exists.
    """
    services.ensure_workspace()
    bridge_storage.ensure_bridge_storage()
    project_storage.ensure_projects_storage()
    project_registry.ensure_default_projects()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orion.window.app:app", host="0.0.0.0", port=8080)
