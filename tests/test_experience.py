"""Tests for orion.experience (Experience Engine + Knowledge Store).

Standard library unittest only, no external calls of any kind -- no
AI provider, no network. Every mission/report used here is built and
persisted under a temporary, isolated workspace directory (monkey-
patched onto orion.bridge.storage / orion.experience.knowledge_store),
never against Orion-AI's own real workspace/ tree.

Run with:

    python3 -m unittest tests.test_experience -v
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge import storage as bridge_storage
from orion.bridge.models import Event, Mission, MissionStatus
from orion.experience import engine, knowledge_store, rules, services, storage
from orion.experience.models import KnowledgeItemType


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_mission(**overrides: object) -> Mission:
    defaults: dict[str, object] = dict(
        id="MISSION-EXP-TEST",
        title="Experience test mission",
        description="",
        mission_type="documentation",
        status=MissionStatus.NEW,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Mission(**defaults)  # type: ignore[arg-type]


def _make_event(mission_id: str, event_type: str, message: str = "") -> Event:
    return Event(id=1, mission_id=mission_id, type=event_type, message=message, author="Test", timestamp=_now())


class IsolatedWorkspaceTestCase(unittest.TestCase):
    """Redirects every storage module this Sprint touches at a
    temporary directory for the duration of each test, restoring the
    real paths in tearDown. Never touches Orion-AI's real workspace/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)

        self._orig_missions_dir = bridge_storage.MISSIONS_DIR
        self._orig_knowledge_dir = knowledge_store.KNOWLEDGE_DIR

        bridge_storage.MISSIONS_DIR = tmp_path / "missions"
        knowledge_store.KNOWLEDGE_DIR = tmp_path / "knowledge"
        bridge_storage.MISSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        bridge_storage.MISSIONS_DIR = self._orig_missions_dir
        knowledge_store.KNOWLEDGE_DIR = self._orig_knowledge_dir
        self._tmp.cleanup()


class RulesTests(unittest.TestCase):
    """Pure-function tests -- no filesystem involved at all."""

    def test_objectives_achieved_only_on_review(self) -> None:
        from orion.prompt_composer.models import (
            BusinessContext,
            ExecutionPrompt,
            MissionSummary,
            PromptPackage,
            SuggestedPlan,
            TechnicalContext,
            CodingStandards,
            ArchitectureRules,
        )

        package = PromptPackage(
            mission=MissionSummary(id="X", title="t", description="", mission_type="documentation", priority="normal", status="NEW"),
            business_context=BusinessContext(project_name="P"),
            technical_context=TechnicalContext(),
            coding_standards=CodingStandards(),
            architecture_rules=ArchitectureRules(),
            acceptance_criteria=["Debe compilar"],
            suggested_plan=SuggestedPlan(steps=["hacerlo"]),
            execution_prompt=ExecutionPrompt(instructions="x"),
            generated_at=_now(),
        )
        self.assertEqual(rules.objectives_achieved(package, {"result": "REVIEW"}), ["Debe compilar"])
        self.assertEqual(rules.objectives_achieved(package, {"result": "FAILED"}), [])
        self.assertEqual(rules.objectives_achieved(package, None), [])

    def test_errors_encountered_filters_by_event_type(self) -> None:
        events = [
            _make_event("M", "created", "creada"),
            _make_event("M", "builder_failed", "algo fallo"),
            _make_event("M", "validation_failed", "no valido"),
        ]
        self.assertEqual(rules.errors_encountered(events), ["algo fallo", "no valido"])

    def test_fixes_applied_is_always_empty_in_v1(self) -> None:
        self.assertEqual(rules.fixes_applied([]), [])

    def test_detect_reusable_components_matches_components_path(self) -> None:
        outcome = {"files_created": ["components/home/Hero.tsx", "docs/ARCHITECTURE.md"], "files_modified": []}
        self.assertEqual(rules.detect_reusable_components(outcome), ["components/home/Hero.tsx"])

    def test_compute_confidence(self) -> None:
        self.assertEqual(rules.compute_confidence(None, []), 0.0)
        self.assertEqual(rules.compute_confidence({"result": "FAILED"}, []), 0.0)
        self.assertEqual(rules.compute_confidence({"result": "REVIEW"}, []), 1.0)
        self.assertEqual(rules.compute_confidence({"result": "REVIEW"}, ["e1", "e2"]), 0.8)

    def test_detect_patterns_groups_files_in_same_directory(self) -> None:
        outcome = {"result": "REVIEW", "files_created": ["components/home/Hero.tsx", "components/home/CTA.tsx"]}
        patterns = rules.detect_patterns(_make_mission(), None, outcome)
        self.assertTrue(any("Grupo de 2 archivos" in p for p in patterns))


class ExtractKnowledgeItemsTests(unittest.TestCase):
    def test_extracts_all_expected_types(self) -> None:
        from orion.experience.models import ExperienceReport

        mission = _make_mission(project_id="atman", tags=["adapter:deterministic_local"])
        report = ExperienceReport(
            mission_id=mission.id,
            project_id="atman",
            mission_summary="s",
            patterns_detected=["Un patron real detectado."],
            recommendations=["No se encontro documentacion de arquitectura para este proyecto; considerar agregarla.", "Reutilizar este enfoque."],
            errors_encountered=["fallo algo"],
            confidence_score=0.5,
            generated_at=_now(),
        )
        items = rules.extract_knowledge_items(mission, report)
        types = {item.type for item in items}
        self.assertIn(KnowledgeItemType.PATTERN, types)
        self.assertIn(KnowledgeItemType.OPPORTUNITY, types)
        self.assertIn(KnowledgeItemType.BEST_PRACTICE, types)
        self.assertIn(KnowledgeItemType.LESSON, types)
        self.assertIn(KnowledgeItemType.RISK, types)
        self.assertIn(KnowledgeItemType.DECISION, types)
        for item in items:
            self.assertEqual(item.source_mission_id, mission.id)
            self.assertEqual(item.project_id, "atman")


class EngineAndServicesTests(IsolatedWorkspaceTestCase):
    def test_build_report_with_no_pipeline_data_yet(self) -> None:
        mission = _make_mission()
        bridge_storage.write_mission(mission.id, mission.model_dump(mode="json"))
        report = engine.build_report(mission)
        self.assertEqual(report.mission_id, mission.id)
        self.assertEqual(report.confidence_score, 0.0)
        self.assertEqual(report.objectives_achieved, [])

    def test_record_experience_persists_report_and_events(self) -> None:
        mission = _make_mission(id="MISSION-EXP-RECORD")
        bridge_storage.write_mission(mission.id, mission.model_dump(mode="json"))

        report = services.record_experience(mission)

        self.assertIsNotNone(storage.load_report(mission.id))
        self.assertTrue((bridge_storage.mission_dir(mission.id) / "experience_summary.md").is_file())

        events = [e.type for e in self._read_events(mission.id)]
        self.assertIn("experience_generated", events)

    def test_record_experience_creates_knowledge_items_on_success(self) -> None:
        mission = _make_mission(id="MISSION-EXP-KNOW", tags=["adapter:deterministic_local"])
        bridge_storage.write_mission(mission.id, mission.model_dump(mode="json"))

        # Simulate a successful pipeline outcome without running the
        # real Pipeline (out of scope for this test; already covered
        # by tests.test_prompt_composer / tests.test_executor).
        from orion.execution import pipeline as execution_pipeline

        original_get_outcome = execution_pipeline.get_outcome
        execution_pipeline.get_outcome = lambda mission_id: (
            {"result": "REVIEW", "files_created": ["components/home/Hero.tsx"], "files_modified": [], "execution_seconds": 1.0, "validation": "passed", "commit_hash": "abc", "branch": "b", "pull_request": "url"}
            if mission_id == mission.id
            else original_get_outcome(mission_id)
        )
        try:
            report = services.record_experience(mission)
        finally:
            execution_pipeline.get_outcome = original_get_outcome

        self.assertTrue(report.knowledge_item_ids)
        items = knowledge_store.list_items(project_id=mission.project_id or None)
        # project_id is "" here (no project), so filter by source mission instead
        items = [i for i in knowledge_store.list_items() if i.source_mission_id == mission.id]
        self.assertTrue(items)
        self.assertEqual({i.id for i in items}, set(report.knowledge_item_ids))

        events = [e.type for e in self._read_events(mission.id)]
        self.assertIn("pattern_detected", events)

    def test_record_experience_never_raises_even_with_broken_mission_data(self) -> None:
        # A mission that was never persisted at all: build_report must
        # still work off the in-memory Mission object alone.
        mission = _make_mission(id="MISSION-EXP-ORPHAN")
        report = services.record_experience(mission)
        self.assertEqual(report.mission_id, mission.id)

    @staticmethod
    def _read_events(mission_id: str) -> list:
        from orion.bridge import services as bridge_services

        return bridge_services.get_events(mission_id)


class KnowledgeStoreTests(IsolatedWorkspaceTestCase):
    def test_save_and_list_and_filter(self) -> None:
        from orion.experience.models import KnowledgeItem

        item1 = KnowledgeItem(
            id="K1", type=KnowledgeItemType.PATTERN, title="t1", description="d1",
            source_mission_id="M1", project_id="atman", tags=["x"], created_at=_now(),
        )
        item2 = KnowledgeItem(
            id="K2", type=KnowledgeItemType.LESSON, title="t2", description="d2",
            source_mission_id="M2", project_id="other", tags=["y"], created_at=_now(),
        )
        knowledge_store.save_item(item1)
        knowledge_store.save_item(item2)

        self.assertEqual(len(knowledge_store.list_items()), 2)
        self.assertEqual([i.id for i in knowledge_store.list_items(item_type=KnowledgeItemType.PATTERN)], ["K1"])
        self.assertEqual([i.id for i in knowledge_store.list_items(project_id="atman")], ["K1"])
        self.assertEqual([i.id for i in knowledge_store.list_items(tag="y")], ["K2"])
        self.assertEqual(knowledge_store.get_item("K1").title, "t1")
        self.assertIsNone(knowledge_store.get_item("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
