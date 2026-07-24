"""REST + SSE surface for orion.runtime -- the only way The Window and
`orion ask` talk to the Runtime from this Sprint forward. Every route
here is a thin wrapper around orion.runtime.services; no route
contains its own business logic.

Run with:

    uvicorn orion.runtime.api:app --host 0.0.0.0 --port 8090

or via the CLI:

    orion runtime start
"""

from __future__ import annotations

import asyncio
import json
import queue as stdlib_queue

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from orion.runtime import events as runtime_events
from orion.runtime import services as runtime_services
from orion.runtime.config import RuntimeConfig
from orion.runtime.models import MissionAskRequest, MissionAskResponse

router = APIRouter()


@router.post("/missions", response_model=MissionAskResponse)
async def create_mission(payload: MissionAskRequest) -> MissionAskResponse:
    return runtime_services.ask(payload)


@router.get("/missions")
async def list_missions_endpoint() -> list[dict]:
    return [m.model_dump(mode="json") for m in runtime_services.list_missions()]


@router.get("/missions/{mission_id}")
async def get_mission_endpoint(mission_id: str) -> dict:
    mission = runtime_services.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' no encontrada.")
    item = runtime_services.queue_item(mission_id)
    return {
        "mission": mission.model_dump(mode="json"),
        "queue_item": item.model_dump(mode="json") if item else None,
    }


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission_endpoint(mission_id: str) -> dict:
    mission = runtime_services.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' no encontrada.")
    accepted = runtime_services.cancel_mission(mission_id)
    return {"mission_id": mission_id, "cancel_requested": accepted}


@router.get("/health")
async def health_endpoint() -> dict:
    report = runtime_services.health_report()
    return report.model_dump(mode="json")


@router.get("/queue")
async def queue_endpoint() -> dict:
    items = runtime_services.queue_snapshot()
    return {
        "items": [i.model_dump(mode="json") for i in items],
        "depth_by_status": runtime_services.queue_depth(),
    }


@router.get("/events")
async def sse_events_endpoint() -> StreamingResponse:
    """Server-Sent Events: The Window subscribes here and updates
    itself without a refresh (see orion/window/static/runtime.js)."""

    async def event_stream():
        subscriber = runtime_events.BUS.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.get_event_loop().run_in_executor(None, subscriber.get, True, 15)
                except stdlib_queue.Empty:
                    # Heartbeat so proxies/browsers never consider an
                    # idle connection dead.
                    yield ": heartbeat\n\n"
                    continue
                payload = {
                    "mission_id": event.mission_id,
                    "type": event.type,
                    "message": event.message,
                    "source": event.source,
                    "timestamp": event.timestamp,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            runtime_events.BUS.unsubscribe(subscriber)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app = FastAPI(title="ORION Runtime API", description="Mission Queue + Workers, resident in the VPS.")

# BETA 007 (The Window integration): The Window (port 8080, see
# orion.window) and this Runtime API (port 8090 by default) are two
# separate FastAPI apps/origins on the same host -- a browser fetch()
# from a page served by one to the other is a cross-origin request.
# Both are operated by the same CEO/operator on their own VPS (this is
# not a public multi-tenant service), so allowing every origin is a
# reasonable, minimal way to let The Window's "Nueva misión" button and
# its SSE subscription (see orion/window/static/js/runtime.js) reach
# this API without adding a config knob nobody asked for.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def on_startup() -> None:
    from orion.bridge import storage as bridge_storage
    from orion.projects import registry as project_registry
    from orion.projects import storage as project_storage
    from orion.runtime import storage as runtime_storage

    bridge_storage.ensure_bridge_storage()
    project_storage.ensure_projects_storage()
    project_registry.ensure_default_projects()
    runtime_storage.ensure_runtime_storage()
    runtime_services.start_runtime(RuntimeConfig.from_env())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    runtime_services.stop_runtime()
