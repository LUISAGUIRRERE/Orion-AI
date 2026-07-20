"""FastAPI application entry point for The Window.

Run with:

    uvicorn orion.window.app:app --host 0.0.0.0 --port 8080

or directly:

    python -m orion.window.app
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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


@app.on_event("startup")
async def on_startup() -> None:
    """Ensure the workspace (business units + events database) exists."""
    services.ensure_workspace()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orion.window.app:app", host="0.0.0.0", port=8080)
