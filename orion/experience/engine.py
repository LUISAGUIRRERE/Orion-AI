"""orion.experience.engine -- builds an ExperienceReport for one
mission, purely by reading already-persisted data from the other
kernel modules through their own public storage/service APIs.

Never imports orion.prompt_composer, orion.executor, or
orion.execution.git_manager internals -- only their existing
load()/get_outcome() read paths, exactly like orion.projects.services
already does for Builder/Pipeline state (Sprint 009's own established
pattern for cross-module reads without cross-module coupling).
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.bridge import services as bridge_services
from orion.bridge.models import Mission
from orion.execution import pipeline as execution_pipeline
from orion.executor import storage as executor_storage
from orion.experience import rules
from orion.experience.models import ExperienceReport
from orion.prompt_composer import storage as prompt_storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_report(mission: Mission) -> ExperienceReport:
    """Gather every input this Sprint specifies (Mission, PromptPackage,
    ExecutionResult, the Pipeline's own outcome -- the "Git Result" --
    and the mission's event timeline) and classify them deterministically
    into the report's fixed structure. Every input is optional except
    the Mission itself: a legacy handler mission has no ExecutionResult,
    a mission whose Prompt Composer step failed has no PromptPackage,
    and a mission that never reached the Pipeline has no outcome -- the
    report is still built, just with those sections empty rather than
    raising.
    """
    package = prompt_storage.load(mission.id)
    execution_result = executor_storage.load_result(mission.id)
    outcome = execution_pipeline.get_outcome(mission.id)
    events = bridge_services.get_events(mission.id)

    errors = rules.errors_encountered(events)
    patterns = rules.detect_patterns(mission, execution_result, outcome)
    recommendations = rules.build_recommendations(mission, package, outcome)
    confidence = rules.compute_confidence(outcome, errors)

    return ExperienceReport(
        mission_id=mission.id,
        project_id=mission.project_id,
        mission_summary=rules.summarize_mission(mission),
        objectives_achieved=rules.objectives_achieved(package, outcome),
        files_modified=rules.files_touched(outcome),
        artifacts_generated=rules.artifacts_generated(execution_result, outcome),
        execution_metrics=rules.execution_metrics(outcome),
        errors_encountered=errors,
        fixes_applied=rules.fixes_applied(events),
        patterns_detected=patterns,
        reusable_components=rules.detect_reusable_components(outcome),
        recommendations=recommendations,
        confidence_score=confidence,
        generated_at=_now_iso(),
    )
