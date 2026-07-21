"""Tests for orion.board (MISSION B-011: AI Board Orchestrator).

Standard library unittest only, same convention as every other test
module in this repo. Covers member_registry (the six real seats, no
invented roles), board_engine (the three exact worked pipeline
examples this Mission's brief gives verbatim, plus the remaining
categories and Release-kind detection), board_router (real progress
derivation from a Mission's own recorded events, never a fabricated
status), mission_pipeline (persistence), services.py orchestration,
the CLI, the API, Runtime integration, and the "no duplicar
Governance" category-reuse contract.

Run with:

    python3 -m unittest tests.test_board -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orion.board import board_engine, board_router, member_registry, mission_pipeline
from orion.board import services as board_services
from orion.board import storage as board_storage
from orion.board.board_engine import BoardPipeline, MissionKind
from orion.governance.change_classifier import ChangeCategory

REPO_ROOT = Path(__file__).resolve().parent.parent


class IsolatedBoardTestCase(unittest.TestCase):
    """Redirects orion.board.storage's persistence directory at a temp
    path for the duration of each test -- never touches Orion-AI's
    real workspace/board/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = board_storage.BOARD_DIR
        board_storage.BOARD_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        board_storage.BOARD_DIR = self._orig_dir
        self._tmp.cleanup()


class MemberRegistryTests(unittest.TestCase):
    def test_exactly_six_members_no_new_roles(self) -> None:
        members = member_registry.list_members()
        self.assertEqual(len(members), 6)
        self.assertEqual({m.key for m in members}, set(member_registry.ALL_KEYS))

    def test_every_member_points_at_a_real_already_existing_module(self) -> None:
        for member in member_registry.list_members():
            self.assertTrue(member.implemented_by, member.key)
            self.assertTrue(member.event_signatures, member.key)

    def test_qa_and_experience_have_no_dedicated_ai_board_seat(self) -> None:
        # Disclosed gap, not a fabricated seventh/eighth role: neither
        # QA nor Experience is a person/persona in .ai/ROLES.md today.
        self.assertIsNone(member_registry.get_member("qa").board_seat)
        self.assertIsNone(member_registry.get_member("experience").board_seat)

    def test_architect_builder_reviewer_gitops_map_to_real_board_seats(self) -> None:
        for key in ("architect", "builder", "reviewer", "gitops"):
            self.assertIsNotNone(member_registry.get_member(key).board_seat, key)


class BoardEngineTests(unittest.TestCase):
    """The three exact worked examples this Mission's brief gives,
    verbatim, plus the remaining categories and Release detection."""

    def test_example_1_nueva_feature(self) -> None:
        pipeline = board_engine.decide_pipeline("Construye la pagina de Cursos")
        self.assertEqual(pipeline.kind, MissionKind.REGULAR)
        self.assertEqual(
            pipeline.stages,
            ("architect", "builder", "reviewer", "qa", "gitops", "experience"),
        )

    def test_example_2_bug_pequeno(self) -> None:
        pipeline = board_engine.decide_pipeline("Arregla el bug de login que falla intermitentemente")
        self.assertEqual(pipeline.stages, ("builder", "qa", "experience"))

    def test_example_3_release(self) -> None:
        pipeline = board_engine.decide_pipeline("Lanza el release v0.9.0-beta a produccion")
        self.assertEqual(pipeline.kind, MissionKind.RELEASE)
        self.assertEqual(pipeline.stages, ("reviewer", "gitops", "experience"))

    def test_release_keywords_detected_in_spanish_and_english(self) -> None:
        for text in (
            "Publica la nueva version",
            "Despliega a produccion",
            "Ship the new release",
            "Crea el tag de esta version",
        ):
            self.assertEqual(board_engine.classify_mission_kind(text), MissionKind.RELEASE, text)

    def test_regular_text_is_not_misclassified_as_release(self) -> None:
        self.assertEqual(
            board_engine.classify_mission_kind("Construye la pagina de Cursos"), MissionKind.REGULAR
        )

    def test_every_governance_category_has_a_deterministic_pipeline(self) -> None:
        for category in ChangeCategory:
            pipeline = board_engine.decide_pipeline("texto sin importancia", category=category)
            self.assertEqual(pipeline.category, category)
            self.assertGreater(len(pipeline.stages), 0)
            self.assertEqual(pipeline.stages[-1], "experience")  # every pipeline ends in Experience

    def test_architecture_category_excludes_gitops_and_builder(self) -> None:
        # A pure architecture discussion does not ship or build anything
        # of its own yet.
        pipeline = board_engine.decide_pipeline("texto", category=ChangeCategory.ARCHITECTURE)
        self.assertNotIn("gitops", pipeline.stages)
        self.assertNotIn("builder", pipeline.stages)

    def test_category_reuse_skips_a_second_classification(self) -> None:
        calls = {"count": 0}
        original = board_engine.classify_change

        def _counting_classify_change(text: str):
            calls["count"] += 1
            return original(text)

        board_engine.classify_change = _counting_classify_change
        try:
            board_engine.decide_pipeline("Arregla el bug", category=ChangeCategory.BUG_FIX)
            self.assertEqual(calls["count"], 0, "must not re-classify when a category is supplied")
            board_engine.decide_pipeline("Arregla el bug", category=None)
            self.assertEqual(calls["count"], 1, "must classify exactly once when none is supplied")
        finally:
            board_engine.classify_change = original


class BoardRouterTests(unittest.TestCase):
    """Real progress derivation from a mission's own recorded events."""

    def setUp(self) -> None:
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

    def tearDown(self) -> None:
        self._inner.tearDown()

    def test_progress_starts_all_pending(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate

        mission = bridge_services.create_mission(
            MissionCreate(title="Arregla el bug de login", mission_type="executor"), author="test"
        )
        pipeline = board_engine.decide_pipeline("Arregla el bug de login")
        progress = board_router.compute_progress(mission.id, pipeline)
        self.assertTrue(all(p.status == "pending" for p in progress))
        self.assertEqual(board_router.next_stage(mission.id, pipeline), "builder")
        self.assertFalse(board_router.is_pipeline_complete(mission.id, pipeline))

    def test_progress_reflects_real_recorded_events_never_fabricated(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate

        mission = bridge_services.create_mission(
            MissionCreate(title="Arregla el bug de login", mission_type="executor"), author="test"
        )
        pipeline = board_engine.decide_pipeline("Arregla el bug de login")
        # Real signature event for "builder"
        bridge_services.record_event(mission.id, "builder_started", "Builder inicio.", "test")
        progress = board_router.compute_progress(mission.id, pipeline)
        by_key = {p.key: p for p in progress}
        self.assertEqual(by_key["builder"].status, "completed")
        self.assertEqual(by_key["qa"].status, "pending")
        self.assertEqual(board_router.next_stage(mission.id, pipeline), "qa")

        # Complete every remaining real signature event
        bridge_services.record_event(mission.id, "validation_passed", "OK", "test")
        bridge_services.record_event(mission.id, "experience_generated", "OK", "test")
        self.assertTrue(board_router.is_pipeline_complete(mission.id, pipeline))


class MissionPipelineTests(IsolatedBoardTestCase):
    def test_save_and_load_roundtrip(self) -> None:
        pipeline = board_engine.decide_pipeline("Construye la pagina de Cursos")
        state = mission_pipeline.save_state("MISSION-0001", pipeline)
        self.assertEqual(state.mission_id, "MISSION-0001")

        loaded = mission_pipeline.load_state("MISSION-0001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.stages, pipeline.stages)
        self.assertEqual(loaded.as_pipeline().stages, pipeline.stages)

    def test_load_missing_mission_returns_none(self) -> None:
        self.assertIsNone(mission_pipeline.load_state("NO-EXISTE"))

    def test_list_states_returns_every_persisted_mission(self) -> None:
        mission_pipeline.save_state("MISSION-A", board_engine.decide_pipeline("Construye X"))
        mission_pipeline.save_state("MISSION-B", board_engine.decide_pipeline("Arregla el bug"))
        states = mission_pipeline.list_states()
        self.assertEqual({s.mission_id for s in states}, {"MISSION-A", "MISSION-B"})


class ServicesTests(IsolatedBoardTestCase):
    def setUp(self) -> None:
        super().setUp()
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

    def tearDown(self) -> None:
        self._inner.tearDown()
        super().tearDown()

    def test_decide_and_record_persists_and_emits_one_event(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate

        mission = bridge_services.create_mission(
            MissionCreate(title="Construye la pagina de Cursos", mission_type="executor"), author="test"
        )
        decision = board_services.decide_and_record(mission.id, mission.title)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.pipeline.stages[0], "architect")

        loaded = board_services.get_decision(mission.id)
        self.assertEqual(loaded.pipeline.stages, decision.pipeline.stages)

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertEqual(event_types.count("board_pipeline_decided"), 1)

    def test_get_progress_none_when_no_decision_persisted(self) -> None:
        self.assertIsNone(board_services.get_progress("NUNCA-DECIDIDA"))

    def test_describe_members_matches_registry(self) -> None:
        self.assertEqual(len(board_services.describe_members()), 6)

    def test_list_decisions(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate

        m1 = bridge_services.create_mission(MissionCreate(title="Construye X", mission_type="executor"), author="test")
        m2 = bridge_services.create_mission(MissionCreate(title="Arregla el bug", mission_type="executor"), author="test")
        board_services.decide_and_record(m1.id, m1.title)
        board_services.decide_and_record(m2.id, m2.title)
        decisions = board_services.list_decisions()
        self.assertEqual({d.mission_id for d in decisions}, {m1.id, m2.id})


class CLITests(unittest.TestCase):
    """Real subprocess invocations of bin/orion, isolated at a temp
    ORION_BOARD_WORKSPACE/ORION_BRIDGE_WORKSPACE."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ)
        self.env["ORION_BOARD_WORKSPACE"] = str(Path(self._tmp.name) / "board")
        self.env["ORION_GOVERNANCE_WORKSPACE"] = str(Path(self._tmp.name) / "governance")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "orion"), *args],
            cwd=str(REPO_ROOT), env=self.env, capture_output=True, text=True, timeout=60,
        )

    def test_board_members(self) -> None:
        result = self._run("board", "members")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Architect", result.stdout)
        self.assertIn("Jules", result.stdout)

    def test_board_pipeline_dry_run(self) -> None:
        result = self._run("board", "pipeline", "Construye la pagina de Cursos")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run", result.stdout)
        self.assertIn("Architect", result.stdout)

    def test_board_progress_missing_mission_returns_nonzero(self) -> None:
        result = self._run("board", "progress", "--mission-id", "NO-EXISTE")
        self.assertNotEqual(result.returncode, 0)


class APIRouteTests(IsolatedBoardTestCase):
    """orion.board.routes functions invoked directly (no TestClient/
    httpx2 dependency -- same technique tests/test_governance.py::
    APIRouteTests already established)."""

    def setUp(self) -> None:
        super().setUp()
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

    def tearDown(self) -> None:
        self._inner.tearDown()
        super().tearDown()

    def test_members_route(self) -> None:
        from orion.board import routes as board_routes

        members = board_routes.get_members()
        self.assertEqual(len(members), 6)

    def test_pipeline_dry_run_route(self) -> None:
        from orion.board import routes as board_routes

        result = board_routes.get_pipeline_dry_run(request="Construye la pagina de Cursos")
        self.assertEqual(result["stages"][0], "architect")

    def test_pipeline_for_mission_404_when_missing(self) -> None:
        from fastapi import HTTPException

        from orion.board import routes as board_routes

        with self.assertRaises(HTTPException) as ctx:
            board_routes.get_pipeline_for_mission("NO-EXISTE")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_pipeline_and_progress_routes_after_a_real_decision(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate

        from orion.board import routes as board_routes

        mission = bridge_services.create_mission(
            MissionCreate(title="Arregla el bug de login", mission_type="executor"), author="test"
        )
        board_services.decide_and_record(mission.id, mission.title)

        pipeline_response = board_routes.get_pipeline_for_mission(mission.id)
        self.assertEqual(pipeline_response["stages"], ["builder", "qa", "experience"])

        progress_response = board_routes.get_progress_for_mission(mission.id)
        self.assertEqual(len(progress_response), 3)
        self.assertTrue(all(p["status"] == "pending" for p in progress_response))


class RuntimeIntegrationTests(unittest.TestCase):
    """Real orion.agents.builder.agent.run_claimed_mission() Mission
    Flow integration: the Board must decide and persist a pipeline for
    every Mission (regardless of whether Governance hard-stops it),
    reusing Governance's own category rather than re-classifying --
    "no duplicar Governance" verified against the real Mission Flow,
    not just in isolation.

    Real, found-the-hard-way hazard fixed here: the "ordinary mission"
    test below is deliberately a Bug Fix (LOW risk, no hard_stop), so
    run_claimed_mission() reaches the real Pipeline, which calls
    orion.execution.workspace.Workspace.prepare() -- a REAL
    `git checkout main` against whatever git_manager.REPO_ROOT
    resolves to. tests/test_business.py::RuntimeIntegrationTests
    already found and fixed this exact class of bug for its own
    Pipeline-reaching test; this class repeats that same fix rather
    than reintroducing the hazard for orion.board's own tests: clone
    the real repo into a disposable temp directory and point
    git_manager.REPO_ROOT there for the duration of this class, so
    these tests never touch the developer's actual working tree."""

    def setUp(self) -> None:
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

        from orion.governance import storage as governance_storage

        self._gov_tmp = tempfile.TemporaryDirectory()
        self._orig_gov_dir = governance_storage.GOVERNANCE_DIR
        governance_storage.GOVERNANCE_DIR = Path(self._gov_tmp.name)

        from orion.business import storage as business_storage

        self._business_tmp = tempfile.TemporaryDirectory()
        self._orig_business_dir = business_storage.BUSINESS_DIR
        business_storage.BUSINESS_DIR = Path(self._business_tmp.name)

        self._board_tmp = tempfile.TemporaryDirectory()
        self._orig_board_dir = board_storage.BOARD_DIR
        board_storage.BOARD_DIR = Path(self._board_tmp.name)

        from orion.execution import git_manager

        self._repo_tmp = tempfile.TemporaryDirectory()
        self._clone_root = Path(self._repo_tmp.name) / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", str(REPO_ROOT), str(self._clone_root)], check=True
        )
        subprocess.run(["git", "-C", str(self._clone_root), "config", "user.email", "test@orion.local"], check=True)
        subprocess.run(["git", "-C", str(self._clone_root), "config", "user.name", "Orion Test"], check=True)
        self._orig_repo_root = git_manager.REPO_ROOT
        git_manager.REPO_ROOT = self._clone_root

        from orion.governance import execution_mode

        execution_mode.set_mode(execution_mode.MODE_HARDENING, author="test", reason="board runtime integration test")

    def tearDown(self) -> None:
        from orion.execution import git_manager

        git_manager.REPO_ROOT = self._orig_repo_root
        self._repo_tmp.cleanup()

        board_storage.BOARD_DIR = self._orig_board_dir
        self._board_tmp.cleanup()

        from orion.business import storage as business_storage

        business_storage.BUSINESS_DIR = self._orig_business_dir
        self._business_tmp.cleanup()

        from orion.governance import storage as governance_storage

        governance_storage.GOVERNANCE_DIR = self._orig_gov_dir
        self._gov_tmp.cleanup()

        self._inner.tearDown()

    def test_ordinary_mission_gets_a_board_pipeline_decided_and_persisted(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        mission = bridge_services.create_mission(
            MissionCreate(
                title="Arregla el bug de login que falla intermitentemente",
                description="Arregla el bug de login que falla intermitentemente",
                mission_type="executor",
            ),
            author="test",
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")
        builder_agent.run_claimed_mission(mission)

        decision = board_services.get_decision(mission.id)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.pipeline.stages, ("builder", "qa", "experience"))

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertEqual(event_types.count("board_pipeline_decided"), 1)

    def test_hard_stop_mission_still_gets_a_board_pipeline_decided(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        mission = bridge_services.create_mission(
            MissionCreate(
                title="Elimina el endpoint viejo de autenticacion",
                description="Elimina el endpoint viejo de autenticacion, rompe compatibilidad con clientes antiguos",
                mission_type="executor",
            ),
            author="test",
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")
        finished = builder_agent.run_claimed_mission(mission)
        self.assertEqual(finished.status, MissionStatus.WAITING)

        decision = board_services.get_decision(mission.id)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.pipeline.category, ChangeCategory.BREAKING_CHANGE)

    def test_board_reuses_governance_category_no_duplicate_classification(self) -> None:
        """The real end-to-end contract: Board's persisted category
        must equal Governance's own audit category for the same
        Mission, and orion.board.board_engine.classify_change must
        never run a second time during the real Mission Flow when
        Governance already classified the request."""
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus
        from orion.governance import services as governance_services

        calls = {"count": 0}
        original = board_engine.classify_change

        def _counting_classify_change(text: str):
            calls["count"] += 1
            return original(text)

        board_engine.classify_change = _counting_classify_change
        try:
            mission = bridge_services.create_mission(
                MissionCreate(
                    title="Refactoriza el modulo de usuarios, hay mucho codigo duplicado",
                    description="Refactoriza el modulo de usuarios, hay mucho codigo duplicado",
                    mission_type="executor",
                ),
                author="test",
            )
            bridge_services.update_status(mission.id, MissionStatus.READY, author="test")
            builder_agent.run_claimed_mission(mission)

            self.assertEqual(calls["count"], 0, "Board must reuse Governance's category, not reclassify")

            decision = board_services.get_decision(mission.id)
            audit_entries = governance_services.list_audit(mission_id=mission.id)
            self.assertEqual(len(audit_entries), 1)
            self.assertEqual(decision.pipeline.category.value, audit_entries[0]["category"])
        finally:
            board_engine.classify_change = original


if __name__ == "__main__":
    unittest.main()
