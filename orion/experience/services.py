"""Public entry point for the Experience Engine.

orion.agents.builder.agent is the only intended caller: after a
mission reaches its terminal state (REVIEW or FAILED), it calls
``record_experience`` once, wrapped in its own try/except -- the same
defensive pattern already used for orion.prompt_composer and
orion.executor -- so a failure here can never leave a mission stuck or
crash the Builder.
"""

from __future__ import annotations

from orion.bridge import services as bridge_services
from orion.bridge.models import Mission
from orion.experience import engine, knowledge_store, storage
from orion.experience.models import ExperienceReport, KnowledgeItemType
from orion.experience.rules import extract_knowledge_items

AUTHOR = "ExperienceEngine"

_EVENT_BY_TYPE = {
    KnowledgeItemType.PATTERN: "pattern_detected",
    KnowledgeItemType.LESSON: "lesson_recorded",
    KnowledgeItemType.BEST_PRACTICE: "recommendation_created",
    KnowledgeItemType.OPPORTUNITY: "recommendation_created",
    # DECISION and RISK items are persisted in the Knowledge Store and
    # linked from the report like every other item, but this Sprint
    # specifies exactly four event types -- none of them map to
    # DECISION/RISK, so no event is invented for them here.
}


def record_experience(mission: Mission) -> ExperienceReport:
    """Build, persist, and record events for one mission's experience.
    Always returns a complete ExperienceReport; never partially writes
    one."""
    report = engine.build_report(mission)
    storage.save_report(report)
    storage.save_summary(report)
    bridge_services.record_event(
        mission.id,
        "experience_generated",
        f"Experience Report generado (confianza {report.confidence_score}).",
        AUTHOR,
    )

    items = extract_knowledge_items(mission, report)
    saved_ids: list[str] = []
    for item in items:
        knowledge_store.save_item(item)
        saved_ids.append(item.id)
        event_type = _EVENT_BY_TYPE.get(item.type)
        if event_type is not None:
            bridge_services.record_event(mission.id, event_type, item.title, AUTHOR)

    if saved_ids:
        report.knowledge_item_ids = saved_ids
        storage.save_report(report)  # re-save once with the final knowledge item ids attached

    return report
