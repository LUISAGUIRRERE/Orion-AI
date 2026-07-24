"""The Builder Agent itself.

Finds the next READY mission, takes it, runs it through the correct
handler, records every step as a timeline event on the Mission
Framework, and always leaves the mission in a consistent terminal
state: REVIEW on success, FAILED on any error. Never RUNNING forever.

The Builder's own operational status (BuilderState) is persisted to
``workspace/builder_state.yaml``, not just held in memory. The Builder
is normally invoked as a separate process from the web server (there is
no execution-trigger API route, by design — see executor.py), so an
in-memory-only state would never be visible to The Window's dashboard,
which reads it from the server process. Persisting it, the same way
every other piece of Bridge data is persisted, closes that gap.
"""

from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from orion.bridge import services as bridge_services
from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission, MissionStatus
from orion.board import services as board_services
from orion.business import services as business_services
from orion.execution import pipeline as execution_pipeline
from orion.experience import services as experience_services
from orion.governance import services as governance_services
from orion.intelligence import services as intelligence_services
from orion.prompt_composer import services as prompt_composer_services

AUTHOR = "Builder"
STATE_FILE: Path = bridge_storage.WORKSPACE_DIR / "builder_state.yaml"


@dataclass
class BuilderState:
    """The Builder's current operational status, surfaced to The Window."""

    status: str = "idle"
    current_mission_id: str | None = None
    current_handler: str | None = None
    # Sprint 009 (Multi Project Engine): minimal, backward-compatible
    # addition — which project (see orion.projects) the current
    # mission belongs to, if any. None for missions with no
    # project_id, exactly like before this Sprint.
    current_project_id: str | None = None
    completed_today: int = 0
    failed_today: int = 0
    last_activity: str | None = None
    day: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())

    def roll_day(self) -> None:
        """Reset the daily counters when the UTC date changes."""
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day = today
            self.completed_today = 0
            self.failed_today = 0

    def touch(self) -> None:
        """Record that the Builder just did something."""
        self.last_activity = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> BuilderState:
    """Load the Builder's persisted state, or a fresh idle state if none exists."""
    if not STATE_FILE.exists():
        return BuilderState()
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    state = BuilderState(**{**asdict(BuilderState()), **data})
    state.roll_day()
    return state


# BETA 007 concurrency fix: _save_state() writes the *entire*
# BuilderState file in one shot on every call, and run_claimed_mission()
# (unlike claim_next_ready_mission()) is intentionally allowed to run
# truly in parallel across Workers processing distinct missions -- so
# concurrent _save_state() calls for different missions could
# previously interleave their writes to the same file, corrupting it.
# This lock only prevents that write-write corruption; it does not
# make multi-field read-modify-write sequences (e.g. completed_today
# += 1) atomic across threads -- BuilderState was designed for a
# single Builder process/cycle (Sprint 006) and its per-mission fields
# (current_mission_id, current_handler) were never meant to describe
# more than one mission at a time. Under real concurrency they become
# best-effort/last-writer-wins, a pre-existing semantic limitation of
# this dataclass that this Sprint does not attempt to redesign -- only
# the file-corruption crash is in scope and fixed here.
_STATE_FILE_LOCK = threading.Lock()


def _save_state(state: BuilderState) -> None:
    """Persist the Builder's state so any process can read it."""
    with _STATE_FILE_LOCK:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write (temp file + os.replace), same fix and same
        # reasoning as orion.runtime.storage._atomic_write_yaml: a
        # plain open(path, "w") truncates before it finishes writing,
        # so a concurrent, unlocked reader (get_state(), used by The
        # Window) could observe a partial file. _STATE_FILE_LOCK above
        # already serializes writer-vs-writer; this makes the write
        # itself safe for readers that never take that lock.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(STATE_FILE.parent), prefix=f".{STATE_FILE.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(asdict(state), fh)
            os.replace(tmp_name, STATE_FILE)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def get_state() -> BuilderState:
    """Return the Builder's current, persisted state."""
    return _load_state()


def _find_next_ready_mission() -> Mission | None:
    """Find the first READY mission, preferring queue order."""
    for mission_id in bridge_services.get_queue():
        mission = bridge_services.get_mission(mission_id)
        if mission is not None and mission.status == MissionStatus.READY:
            return mission
    # Fall back to a full scan in case a READY mission isn't in the
    # queue (e.g. it was re-opened directly via PATCH .../status).
    for mission in bridge_services.list_missions():
        if mission.status == MissionStatus.READY:
            return mission
    return None


def _record_experience_safely(mission_id: str) -> None:
    """Generate this mission's Experience Report, never letting a
    failure here affect the mission's own terminal status -- the same
    defensive pattern already used for orion.prompt_composer above.
    Looked up fresh (not passed the in-memory Mission) so this always
    reflects the mission's final, persisted state."""
    mission = bridge_services.get_mission(mission_id)
    if mission is None:
        return
    report = None
    try:
        report = experience_services.record_experience(mission)
    except Exception as exc:  # noqa: BLE001 - recording experience must never crash the agent
        bridge_services.record_event(mission_id, "experience_generation_failed", str(exc), AUTHOR)

    # BETA 008: fold this mission's real, already-computed outcome
    # (files actually touched, confidence score) into the global
    # Knowledge Graph -- "grows automatically", per the Sprint, rather
    # than requiring a separate manual step. provider_name is left
    # None: ExperienceReport does not currently track which provider
    # ran the mission, and this must never guess one.
    try:
        intelligence_services.record_mission_knowledge(
            mission_id=mission.id,
            mission_title=mission.title,
            provider_name=None,
            files_touched=list(report.files_modified) if report is not None else [],
            confidence_score=report.confidence_score if report is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 - knowledge recording must never crash the agent
        bridge_services.record_event(mission_id, "knowledge_recording_failed", str(exc), AUTHOR)

    # BETA 009: "cada Mission completada debe actualizar Knowledge,
    # Roadmap, Goals" -- real, conservative learning (see
    # business_services.learn_from_mission's own docstring for why
    # this deliberately never auto-writes a Decision Log entry).
    try:
        business_services.learn_from_mission(mission.id, mission.title, mission.description)
    except Exception as exc:  # noqa: BLE001 - business learning must never crash the agent
        bridge_services.record_event(mission_id, "business_learning_failed", str(exc), AUTHOR)


# BETA 007 (Runtime): process_next() used to have exactly one caller
# at a time by construction (a single COO/Builder cycle). The Runtime
# now calls it from multiple concurrent Worker threads
# (orion.runtime.worker.Worker), which exposed a real TOCTOU race
# between "scan for the next READY mission" and "mark it RUNNING":
# two threads could both find the same READY mission before either
# had claimed it. This lock serializes only that short claim window
# (scan + transition to RUNNING), never the mission's actual work
# below (Prompt Composer / Executor / Provider / Git / Experience),
# so concurrent Workers still execute in real parallel once each has
# claimed a distinct mission -- see
# tests/test_runtime.py::SchedulerTests::
# test_concurrent_workers_each_process_a_distinct_mission_exactly_once,
# which reproduced the race before this fix and passes with it.
_CLAIM_LOCK = threading.Lock()


def claim_next_ready_mission() -> Mission | None:
    """Atomically find the next READY mission and transition it to
    RUNNING (recording builder_assigned/builder_started), or return
    None if nothing is READY. The whole find-then-transition happens
    under _CLAIM_LOCK -- see the comment above the lock's definition.

    Public (no leading underscore) since BETA 007:
    orion.runtime.worker.Worker calls this directly rather than
    re-implementing its own "find the next READY mission" scan, which
    is exactly what caused the race this lock exists to prevent in the
    first place -- a second, unlocked scan implementation living in a
    different module could always see a mission as READY a moment
    before this one had actually claimed it. There is now exactly one
    scan-and-claim implementation, used by both process_next() (the
    original, single-caller entry point) and Worker.run_once().
    """
    with _CLAIM_LOCK:
        state = _load_state()
        mission = _find_next_ready_mission()
        if mission is None:
            state.status = "idle"
            _save_state(state)
            return None

        state.status = "working"
        state.current_mission_id = mission.id
        state.touch()
        _save_state(state)

        bridge_services.record_event(
            mission.id, "builder_assigned", f"Builder tomo la mission '{mission.title}'.", AUTHOR
        )
        mission = bridge_services.update_status(mission.id, MissionStatus.RUNNING, author=AUTHOR)
        assert mission is not None
        bridge_services.record_event(mission.id, "builder_started", "Builder inicio la ejecucion.", AUTHOR)
        return mission


def process_next() -> Mission | None:
    """Process exactly one READY mission end to end.

    Returns the mission in its final state (REVIEW or FAILED), or None
    if no READY mission was found.
    """
    mission = claim_next_ready_mission()
    if mission is None:
        return None
    return run_claimed_mission(mission)


def run_claimed_mission(mission: Mission) -> Mission | None:
    """Runs the rest of process_next()'s original body for a Mission
    that has *already* been claimed (already RUNNING) via
    claim_next_ready_mission() -- split out so orion.runtime.worker.Worker
    can do its own queue bookkeeping/event emission in between the
    claim and the actual work, without duplicating either half."""
    state = _load_state()
    state.current_handler = mission.mission_type
    state.current_project_id = mission.project_id or None
    _save_state(state)

    # Prompt Composer integration: the Builder no longer has any
    # business building context for a mission itself -- that is now
    # orion.prompt_composer's job. The Composer's PromptPackage is
    # persisted as evidence and logged on the mission timeline, but is
    # not yet fed into TaskRunner/the handler: the handlers registered
    # in orion.agents.builder.registry are still the deterministic
    # Sprint 006/BETA 001 ones, not a real Executor that consumes a
    # PromptPackage. Wiring a real Executor is the next Sprint's work
    # (see docs/PROMPT_COMPOSER.md); composing and recording context
    # for every mission, starting now, is this Sprint's. Wrapped in
    # try/except for the same reason the pipeline call below is: a
    # context-discovery failure must never crash the agent or leave a
    # mission stuck RUNNING.
    try:
        prompt_package = prompt_composer_services.compose_for_mission(mission)
        bridge_services.record_event(
            mission.id,
            "prompt_composed",
            (
                f"Prompt Package generado: {len(prompt_package.related_files)} archivo(s) relacionado(s), "
                f"{len(prompt_package.recent_commits)} commit(s) reciente(s), "
                f"{len(prompt_package.coding_standards.sources) + len(prompt_package.architecture_rules.sources)} "
                "documento(s) de contexto descubiertos."
            ),
            AUTHOR,
        )
    except Exception as exc:  # noqa: BLE001 - composing context must never crash the agent
        bridge_services.record_event(mission.id, "prompt_composer_failed", str(exc), AUTHOR)

    # BETA 009: Business Brain -> Context Engine -> Project Intelligence,
    # in exactly that order (this Sprint's own Mission Flow). Real,
    # deterministic company/project resolution from the mission's own
    # text -- never asked for, never guessed by an LLM. When it
    # resolves, resolve_context() has *already* called into
    # orion.intelligence.services itself for the resolved technical
    # project (never a second, duplicate analysis here -- "no duplicar
    # Project Intelligence"). Deliberately informational either way,
    # same as every other BETA 008 hook in this function: a failure
    # here must never block or fail a mission whose actual work has
    # not even started yet.
    business_brief = None
    try:
        business_brief = business_services.resolve_context(mission.description or mission.title, mission_id=mission.id)
        bridge_services.record_event(mission.id, "business_context_loaded", business_brief.summary_text(), AUTHOR)
    except Exception as exc:  # noqa: BLE001 - resolution must never crash or block the agent
        bridge_services.record_event(mission.id, "business_context_failed", str(exc), AUTHOR)

    fallback_intelligence_brief = None
    if business_brief is None or not business_brief.resolved.resolved:
        # No real Company matched this request (or resolution itself
        # errored) -- fall back to BETA 008's own direct Project
        # Intelligence pass, unchanged, so missions unrelated to any
        # registered business (including ORION-AI's own missions, and
        # every existing BETA 007/008 test) keep their exact prior
        # behavior.
        try:
            fallback_intelligence_brief = intelligence_services.prepare_request(
                mission.description or mission.title,
                project_key=mission.project_id or "",
                mission_id=mission.id,
            )
            bridge_services.record_event(mission.id, "intelligence_brief", fallback_intelligence_brief.summary_text(), AUTHOR)
        except Exception as exc:  # noqa: BLE001 - analysis must never crash or block the agent
            bridge_services.record_event(mission.id, "intelligence_failed", str(exc), AUTHOR)

    # BETA 010: Business Brain/Project Intelligence -> Risk Engine ->
    # Policy Engine -> Decision Engine, exactly this Sprint's own
    # Mission Flow order, before the Pipeline ever runs. Reuses --
    # never recomputes -- whichever real ImpactReport the block above
    # already produced (business_brief.intelligence_brief when
    # Business Brain resolved a company with a real repo, or
    # fallback_intelligence_brief otherwise); honestly passes
    # impact=None when neither exists (Risk Engine's own documented,
    # disclosed floor for "no real data", never a fabricated risk
    # level).
    if business_brief is not None and business_brief.intelligence_brief is not None:
        governance_impact = business_brief.intelligence_brief.impact
    elif fallback_intelligence_brief is not None:
        governance_impact = fallback_intelligence_brief.impact
    else:
        governance_impact = None

    try:
        # evaluate_change() already emits its own "governance_evaluated"
        # event (orion.governance.services._emit) -- recording it again
        # here would double-emit the same event type, the exact class
        # of bug BETA 008 already found once for review_completed.
        governance_evaluation = governance_services.evaluate_change(
            mission.description or mission.title,
            mission_id=mission.id,
            project_id=mission.project_id or "",
            impact=governance_impact,
        )
    except Exception as exc:  # noqa: BLE001 - a Governance failure must never crash or silently block the agent
        governance_evaluation = None
        bridge_services.record_event(mission.id, "governance_failed", str(exc), AUTHOR)

    # B-011 (AI Board Orchestrator): decides which Board members'
    # stages this Mission's pipeline goes through and persists that
    # decision -- purely a coordination/labeling layer, never a second
    # execution path (see orion.board.board_engine's own docstring).
    # Reuses -- never recomputes -- Governance's own category when it
    # is available ("no duplicar Governance"), the same reuse pattern
    # already applied above for Business Brain's ImpactReport. Runs
    # regardless of whether Governance's decision is a hard stop: a
    # Mission waiting on human approval still benefits from having its
    # intended pipeline already decided and visible. Wrapped so a
    # Board failure can never crash or block the agent, same as every
    # other hook in this function.
    board_category = (
        governance_evaluation.classification.category if governance_evaluation is not None else None
    )
    board_decision = board_services.decide_and_record(
        mission.id, mission.description or mission.title, category=board_category
    )
    if board_decision is None:
        bridge_services.record_event(mission.id, "board_failed", "No se pudo decidir el pipeline del Board.", AUTHOR)

    if governance_evaluation is not None and governance_evaluation.decision.hard_stop:
        # A real, per-change safety signal (Architecture / Breaking
        # Change / CRITICAL risk) -- not merely the current Execution
        # Mode's blanket posture (see PolicyOutcome.hard_stop's own
        # docstring). This is the one real gate this Sprint's brief
        # asks for: "Solo debe detenerse cuando exista una decision de
        # arquitectura o de negocio que realmente requiera intervencion
        # humana." Every other Mission -- including every existing
        # BETA 007/008/009 test mission, none of which ever trigger
        # this -- proceeds exactly as before.
        bridge_services.record_event(mission.id, "governance_hard_stop", governance_evaluation.decision.rationale, AUTHOR)
        bridge_services.update_status(mission.id, MissionStatus.WAITING, author=AUTHOR)
        state.status = "idle"
        state.current_mission_id = None
        state.current_handler = None
        state.current_project_id = None
        state.touch()
        _save_state(state)
        _record_experience_safely(mission.id)
        return bridge_services.get_mission(mission.id)

    try:
        pipeline_result = execution_pipeline.run(mission)
    except Exception as exc:  # noqa: BLE001 - the pipeline itself must never crash the agent
        bridge_services.record_event(mission.id, "builder_failed", str(exc), AUTHOR)
        bridge_services.update_status(mission.id, MissionStatus.FAILED, author=AUTHOR)
        state.status = "idle"
        state.failed_today += 1
        state.current_mission_id = None
        state.current_handler = None
        state.current_project_id = None
        state.touch()
        _save_state(state)
        _record_experience_safely(mission.id)
        return bridge_services.get_mission(mission.id)

    if not pipeline_result.success:
        bridge_services.record_event(mission.id, "builder_failed", pipeline_result.message, AUTHOR)
        bridge_services.update_status(mission.id, MissionStatus.FAILED, author=AUTHOR)
        state.status = "idle"
        state.failed_today += 1
        state.current_mission_id = None
        state.current_handler = None
        state.current_project_id = None
        state.touch()
        _save_state(state)
        _record_experience_safely(mission.id)
        return bridge_services.get_mission(mission.id)

    result = pipeline_result.handler_result

    bridge_services.record_event(
        mission.id, "builder_progress", f"Handler '{mission.mission_type}' ejecutado.", AUTHOR
    )
    for artifact_name in result.artifacts:
        bridge_services.record_event(
            mission.id, "artifact_created", f"Artifact generado: {artifact_name}", AUTHOR
        )

    bridge_services.update_status(mission.id, MissionStatus.REVIEW, author=AUTHOR)
    bridge_services.record_event(
        mission.id, "builder_completed", result.summary or "Mission completada y enviada a revision.", AUTHOR
    )

    state.status = "idle"
    state.completed_today += 1
    state.current_mission_id = None
    state.current_handler = None
    state.touch()
    _save_state(state)

    _record_experience_safely(mission.id)
    return bridge_services.get_mission(mission.id)
