"""Deterministic classification rules for the Experience Engine.

Every function here is a pure function of already-known data (the
Mission, its PromptPackage, its ExecutionResult if any, the Pipeline's
own outcome dict, and the mission's event list) -- none of them call
an AI provider, none of them guess. This is deliberate: this Sprint's
job is to define the *contract* (a consistent, structured shape for
"what did we learn"), not to build real judgment yet. A future Sprint
can replace any one of these functions with a smarter, AI-assisted
version without changing ExperienceReport's shape or anything that
depends on it.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from datetime import datetime, timezone

from orion.bridge.models import Event, Mission
from orion.executor.models import ExecutionResult
from orion.experience.models import ExperienceReport, KnowledgeItem, KnowledgeItemType
from orion.prompt_composer.models import PromptPackage

_ERROR_EVENT_TYPES = {
    "builder_failed",
    "execution_failed",
    "validation_failed",
    "prompt_composer_failed",
}


def summarize_mission(mission: Mission) -> str:
    return f"{mission.title} (tipo: {mission.mission_type}, prioridad: {mission.priority})."


def objectives_achieved(package: PromptPackage | None, outcome: dict[str, Any] | None) -> list[str]:
    """Only ever claims an objective was achieved when the Pipeline
    itself recorded a successful outcome -- never inferred from intent
    alone."""
    if not outcome or outcome.get("result") != "REVIEW":
        return []
    return list(package.acceptance_criteria) if package else []


def files_touched(outcome: dict[str, Any] | None) -> list[str]:
    if not outcome:
        return []
    return list(outcome.get("files_created", [])) + list(outcome.get("files_modified", []))


def artifacts_generated(execution_result: ExecutionResult | None, outcome: dict[str, Any] | None) -> list[str]:
    if execution_result is not None:
        return [a.path for a in execution_result.artifacts]
    return files_touched(outcome)


def execution_metrics(outcome: dict[str, Any] | None) -> dict[str, Any]:
    if not outcome:
        return {}
    return {
        "execution_seconds": outcome.get("execution_seconds"),
        "validation": outcome.get("validation"),
        "result": outcome.get("result"),
        "commit_hash": outcome.get("commit_hash"),
        "branch": outcome.get("branch"),
        "pull_request": outcome.get("pull_request"),
    }


def errors_encountered(events: list[Event]) -> list[str]:
    return [e.message for e in events if e.type in _ERROR_EVENT_TYPES]


def fixes_applied(events: list[Event]) -> list[str]:  # noqa: ARG001 - signature kept symmetric with the rest
    """v1 limitation, stated plainly: ORION has no automatic retry
    mechanism yet, so there is nothing here for this function to
    detect deterministically. Always empty until a retry/self-healing
    mechanism exists to observe."""
    return []


def detect_patterns(
    mission: Mission,
    execution_result: ExecutionResult | None,
    outcome: dict[str, Any] | None,
) -> list[str]:
    patterns: list[str] = []
    if outcome and outcome.get("result") == "REVIEW":
        patterns.append(f"Mision tipo '{mission.mission_type}' completada sin errores de validacion.")
    if execution_result is not None:
        patterns.append(f"Ejecucion delegada al Executor con el adaptador '{execution_result.adapter}'.")

    files = files_touched(outcome)
    dirs = {str(PurePosixPath(f).parent) for f in files if "/" in f}
    if len(files) > 1 and len(dirs) == 1:
        patterns.append(f"Grupo de {len(files)} archivos relacionados generados juntos en '{next(iter(dirs))}'.")
    return patterns


def detect_reusable_components(outcome: dict[str, Any] | None) -> list[str]:
    """Files that look like reusable UI/library building blocks -- a
    simple, honest heuristic (path contains a 'components/' segment),
    not a judgment about actual reusability."""
    return [f for f in files_touched(outcome) if "components/" in f]


def build_recommendations(
    mission: Mission, package: PromptPackage | None, outcome: dict[str, Any] | None
) -> list[str]:
    recommendations: list[str] = []
    if outcome and outcome.get("result") == "FAILED":
        recommendations.append("Revisar el error registrado en esta mision antes de reintentarla.")
    elif outcome and outcome.get("result") == "REVIEW":
        recommendations.append(
            f"Este enfoque para misiones de tipo '{mission.mission_type}' puede reutilizarse "
            "en misiones similares del mismo proyecto."
        )
    if package is not None:
        if not package.architecture_rules.sources:
            recommendations.append(
                "No se encontro documentacion de arquitectura para este proyecto; considerar agregarla."
            )
        if not package.coding_standards.sources:
            recommendations.append(
                "No se encontraron estandares de codigo explicitos para este proyecto; considerar agregarlos."
            )
    return recommendations


def compute_confidence(outcome: dict[str, Any] | None, errors: list[str]) -> float:
    """A simple, transparent formula, not a learned score: 0.0 for any
    mission that did not reach REVIEW, otherwise 1.0 minus a small
    penalty per error event recorded along the way (there can be error
    events even on a mission that ultimately recovered and succeeded)."""
    if not outcome or outcome.get("result") != "REVIEW":
        return 0.0
    score = 1.0 - (0.1 * len(errors))
    return max(0.0, min(1.0, round(score, 2)))



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_knowledge_items(mission: Mission, report: ExperienceReport) -> list[KnowledgeItem]:
    """Turn one ExperienceReport into zero or more Knowledge Store
    entries, using the same six-type taxonomy this Sprint specifies.
    Every rule here traces back to a concrete, already-verified signal
    in the report -- never an invented insight. Deeper, genuinely
    domain-specific lessons (the kind a human curator or a future
    AI-assisted classifier would add) are explicitly out of scope for
    this v1; see docs/EXPERIENCE_ENGINE.md.
    """
    items: list[KnowledgeItem] = []
    now = _now_iso()

    def _make(item_type: KnowledgeItemType, title: str, description: str, extra_tags: list[str] | None = None) -> KnowledgeItem:
        index = len(items)
        return KnowledgeItem(
            id=f"KNOW-{mission.id}-{item_type.value}-{index}",
            type=item_type,
            title=title[:120],
            description=description,
            source_mission_id=mission.id,
            project_id=mission.project_id,
            tags=list(mission.tags) + (extra_tags or []),
            confidence=report.confidence_score,
            created_at=now,
        )

    for pattern_text in report.patterns_detected:
        items.append(_make(KnowledgeItemType.PATTERN, pattern_text, pattern_text))

    for recommendation in report.recommendations:
        is_gap = "no se encontro" in recommendation.lower()
        item_type = KnowledgeItemType.OPPORTUNITY if is_gap else KnowledgeItemType.BEST_PRACTICE
        items.append(_make(item_type, recommendation, recommendation))

    for error in report.errors_encountered:
        items.append(_make(KnowledgeItemType.LESSON, f"Evitar: {error}", error))

    if report.errors_encountered:
        items.append(
            _make(
                KnowledgeItemType.RISK,
                f"Riesgo detectado ejecutando misiones de tipo '{mission.mission_type}'",
                "; ".join(report.errors_encountered),
                extra_tags=[mission.mission_type],
            )
        )

    for tag in mission.tags:
        if tag.startswith("adapter:"):
            adapter_name = tag.removeprefix("adapter:")
            items.append(
                _make(
                    KnowledgeItemType.DECISION,
                    f"Se selecciono el adaptador '{adapter_name}' para esta mision",
                    f"La mision {mission.id} se ejecuto explicitamente con el adaptador '{adapter_name}' "
                    "(tag adapter:<nombre>).",
                    extra_tags=[adapter_name],
                )
            )

    return items