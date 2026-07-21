"""ORION Runtime -- BETA 007.

A resident process (`orion runtime start`) that eliminates copy/paste
as the way ORION executes missions. Nothing in this package replaces
any existing subsystem: it is a thin, real orchestration layer wired
directly on top of the Mission Framework (orion.bridge), the Prompt
Composer, the Executor + ProviderAdapter/ClaudeCodeAdapter, the
Autonomous Execution Pipeline (which already owns Validation and Git),
and the Experience Engine -- every one of those keeps its exact
existing contract and behavior.

Modules:
    models.py    -- QueueItem/QueueItemStatus, WorkerStatus,
                     RuntimeState, request/response DTOs.
    storage.py   -- YAML persistence for the queue and runtime state.
    config.py    -- RuntimeConfig, read once from environment vars.
    events.py    -- real-time event bus (SSE) layered on top of the
                     Mission Framework's own persisted event log.
    queue.py     -- the Runtime's own persistent Mission Queue ledger.
    worker.py    -- one polling loop; delegates the actual mission
                     lifecycle to orion.agents.builder.agent.process_next().
    scheduler.py -- owns N Worker threads (ORION_WORKERS).
    services.py  -- the only entry point orion.runtime.api / the CLI
                     may call.
    api.py       -- FastAPI app: REST + Server-Sent Events.
"""
