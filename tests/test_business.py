"""Tests for orion.business (BETA 009: Business Brain).

Standard library unittest only (no pytest, no new dependency), same
convention as every other test module in this repo. Covers company/
project/brand CRUD, knowledge/memory/documents, roadmap/goals/
decisions, the real deterministic company/project resolver (including
regression coverage for the two real bugs found during development:
the fuzzy-match false positive, and repository_display showing a raw
internal id instead of a real URL), services.py orchestration
(migration, enrichment, resolve_context/BusinessBrief), the CLI, the
API, and Runtime integration (both branches of the BETA 009 Mission
Flow hook).

Run with:

    python3 -m unittest tests.test_business -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orion.business import (
    brand as brand_module,
    company as company_module,
    decisions as decisions_module,
    documents as documents_module,
    goals as goals_module,
    knowledge as knowledge_module,
    memory as memory_module,
    planner,
    project as project_module,
    roadmap as roadmap_module,
    services as business_services,
    storage,
)
REPO_ROOT = Path(__file__).resolve().parent.parent


class IsolatedBusinessTestCase(unittest.TestCase):
    """Redirects orion.business.storage's persistence directory at a
    temp path for the duration of each test -- never touches
    Orion-AI's real workspace/business_brain/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_business_dir = storage.BUSINESS_DIR
        storage.BUSINESS_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.BUSINESS_DIR = self._orig_business_dir
        self._tmp.cleanup()


class CompanyTests(IsolatedBusinessTestCase):
    def test_create_and_load_round_trips(self) -> None:
        company_module.create_company("atman", "ATMAN", description="Astrologia y bienestar")
        loaded = company_module.load_company("atman")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "ATMAN")

    def test_create_twice_raises(self) -> None:
        company_module.create_company("atman", "ATMAN")
        with self.assertRaises(ValueError):
            company_module.create_company("atman", "ATMAN otra vez")

    def test_list_companies_is_sorted(self) -> None:
        company_module.create_company("tealife", "TEALIFE")
        company_module.create_company("atman", "ATMAN")
        ids = [c.id for c in company_module.list_companies()]
        self.assertEqual(ids, sorted(ids))


class ProjectBrandTests(IsolatedBusinessTestCase):
    def test_add_and_list_projects(self) -> None:
        company_module.create_company("atman", "ATMAN")
        project_module.add_project("atman", "Website", keywords=["cursos", "web"])
        projects = project_module.load_projects("atman")
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, "Website")

    def test_set_and_load_brand(self) -> None:
        company_module.create_company("atman", "ATMAN")
        brand_module.set_brand("atman", colors=["Azul marino", "Dorado", "Blanco"])
        brand = brand_module.load_brand("atman")
        self.assertEqual(brand.colors, ["Azul marino", "Dorado", "Blanco"])


class KnowledgeMemoryDocumentsTests(IsolatedBusinessTestCase):
    def test_add_fact_dedups_case_insensitively(self) -> None:
        k1 = knowledge_module.add_fact("atman", "ATMAN vende cursos")
        k2 = knowledge_module.add_fact("atman", "atman vende cursos")
        self.assertEqual(k1.id, k2.id)
        self.assertEqual(len(knowledge_module.list_knowledge("atman")), 1)

    def test_memory_remember_many_dedups(self) -> None:
        memory_module.remember_many("atman", "tech_stack", ["WordPress", "wordpress", "Tutor LMS"])
        self.assertEqual(memory_module.recall("atman", "tech_stack"), ["WordPress", "Tutor LMS"])

    def test_register_document_captures_real_stat_for_local_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as fh:
            fh.write(b"# Real file\n")
            path = fh.name
        try:
            doc = documents_module.register_document("atman", "Test doc", "markdown", path_or_url=path)
            self.assertIsNotNone(doc.size_bytes)
            self.assertGreater(doc.size_bytes, 0)
            self.assertIsNotNone(doc.modified_at)
        finally:
            os.unlink(path)

    def test_register_document_without_local_file_has_no_fabricated_stat(self) -> None:
        doc = documents_module.register_document("atman", "External site", "other", path_or_url="https://example.com")
        self.assertIsNone(doc.size_bytes)
        self.assertIsNone(doc.modified_at)


class RoadmapGoalsDecisionsTests(IsolatedBusinessTestCase):
    def test_roadmap_status_transitions_and_mission_linking(self) -> None:
        item = roadmap_module.add_item("atman", "Pagina de Cursos", status="backlog")
        roadmap_module.update_status("atman", item.id, "in_progress")
        roadmap_module.link_mission("atman", item.id, "MISSION-0099")
        reloaded = roadmap_module.load_roadmap("atman")[0]
        self.assertEqual(reloaded.status, "in_progress")
        self.assertEqual(reloaded.mission_ids, ["MISSION-0099"])

    def test_invalid_roadmap_status_raises(self) -> None:
        item = roadmap_module.add_item("atman", "X")
        with self.assertRaises(ValueError):
            roadmap_module.update_status("atman", item.id, "not_a_real_status")

    def test_goal_mission_linking(self) -> None:
        goal = goals_module.add_goal("atman", "Incrementar conversiones")
        goals_module.link_mission("atman", goal.id, "MISSION-0099")
        reloaded = goals_module.list_active("atman")[0]
        self.assertIn("MISSION-0099", reloaded.mission_ids)

    def test_decision_log_records_full_context(self) -> None:
        decisions_module.record_decision("atman", "Elegimos WordPress", reason="Rapidez", author="Louis", impact="Alto")
        entry = decisions_module.load_decisions("atman")[0]
        self.assertEqual(entry.decision, "Elegimos WordPress")
        self.assertEqual(entry.reason, "Rapidez")


class PlannerResolutionTests(IsolatedBusinessTestCase):
    def setUp(self) -> None:
        super().setUp()
        company_module.create_company("atman", "ATMAN", websites=["atmanme.com"])
        company_module.create_company("cgiso", "CGISO")
        project_module.add_project("atman", "Website", technical_project_id="atman", keywords=["cursos", "web", "sitio"])
        project_module.add_project("atman", "Mobile App", keywords=["app", "movil"])
        brand_module.set_brand("atman", colors=["Azul marino", "Dorado", "Blanco"])

    def test_keyword_match_resolves_real_project(self) -> None:
        result = planner.resolve_request("Construye la pagina de Cursos")
        self.assertTrue(result.resolved)
        self.assertEqual(result.company.id, "atman")
        self.assertEqual(result.project.name, "Website")
        self.assertEqual(result.method, "keyword_match")

    def test_explicit_company_name_wins_over_keywords(self) -> None:
        result = planner.resolve_request("Arregla el bug de la app movil de CGISO")
        # CGISO is named explicitly, so it must win even though "app"/"movil"
        # are ATMAN's own Mobile App keywords.
        self.assertEqual(result.company.id, "cgiso")
        self.assertEqual(result.method, "explicit_company_name")

    def test_unrelated_text_never_produces_a_false_positive(self) -> None:
        # Regression: _best_project_match() used to fall back to a
        # SequenceMatcher character-similarity ratio, which could cross
        # the match threshold for completely unrelated text purely by
        # chance -- a real false positive found while validating BETA 009
        # against this exact repo's real Company data.
        result = planner.resolve_request("algo totalmente ajeno sin relacion con ninguna empresa coneguida xyz")
        self.assertFalse(result.resolved)

    def test_repository_display_resolves_real_url_not_internal_id(self) -> None:
        # Regression: repository_display used to show the bare
        # technical_project_id string (e.g. "cgiso") instead of a real
        # repository URL/local path or website.
        project_module.add_project("cgiso", "Website", technical_project_id="cgiso", keywords=["logistica"])
        result = planner.resolve_request("logistica de CGISO")
        context = planner.load_business_context(result)
        self.assertNotEqual(context.repository_display, "cgiso")

    def test_load_business_context_for_unresolved_is_empty_not_fabricated(self) -> None:
        result = planner.ResolvedContext()
        context = planner.load_business_context(result)
        self.assertIsNone(context.branding)
        self.assertEqual(context.technology, [])


class ServicesMigrationTests(IsolatedBusinessTestCase):
    def test_migrate_existing_is_idempotent(self) -> None:
        first = business_services.migrate_existing()
        self.assertGreater(len(first), 0)
        second = business_services.migrate_existing()
        self.assertEqual(second, [])  # nothing new to migrate the second time

    def test_migrate_existing_never_overwrites_a_hand_edited_company(self) -> None:
        business_services.migrate_existing()
        business_services.update_company("atman", description="Descripcion editada a mano")
        business_services.migrate_existing()
        reloaded = company_module.load_company("atman")
        self.assertEqual(reloaded.description, "Descripcion editada a mano")

    def test_enrich_atman_is_idempotent_and_adds_real_facts(self) -> None:
        business_services.migrate_existing()
        business_services.enrich_atman_with_real_data()
        business_services.enrich_atman_with_real_data()
        tech = memory_module.recall("atman", "tech_stack")
        self.assertEqual(len(tech), len(set(t.lower() for t in tech)))  # no duplicates
        self.assertIn("WordPress", tech)


class BusinessBriefTests(IsolatedBusinessTestCase):
    def setUp(self) -> None:
        super().setUp()
        business_services.migrate_existing()
        business_services.enrich_atman_with_real_data()

    def test_criterio_de_exito_format_for_atman_cursos(self) -> None:
        brief = business_services.resolve_context("Construye la pagina de Cursos")
        text = brief.summary_text()
        for expected_line in (
            "Empresa:", "ATMAN", "Proyecto:", "Website", "Objetivo:", "Incrementar conversiones",
            "Repositorio:", "atmanme.com", "Branding:", "Azul marino", "Dorado", "Blanco",
            "Tecnologia:", "WordPress", "Nivel de riesgo:", "Plan generado.", "Comenzando ejecucion.",
        ):
            self.assertIn(expected_line, text, f"'{expected_line}' missing from BusinessBrief.summary_text()")

    def test_unresolved_request_is_honest_not_fabricated(self) -> None:
        brief = business_services.resolve_context("peticion sin relacion alguna con cualquier empresa coneguida xyz123")
        self.assertFalse(brief.resolved.resolved)
        self.assertIn("No pude identificar", brief.summary_text())

    def test_cgiso_without_real_repo_reports_unknown_risk_honestly(self) -> None:
        brief = business_services.resolve_context("Optimiza el proceso logistico de CGISO")
        self.assertEqual(brief.resolved.company.id, "cgiso")
        self.assertFalse(brief.intelligence_available)
        self.assertEqual(brief.risk, "desconocido")


class LearnFromMissionTests(IsolatedBusinessTestCase):
    def setUp(self) -> None:
        super().setUp()
        business_services.migrate_existing()
        business_services.enrich_atman_with_real_data()

    def test_learn_from_mission_creates_and_links_roadmap_item(self) -> None:
        business_services.learn_from_mission("MISSION-TEST-1", "Construye la pagina de Cursos", "")
        items = [i for i in roadmap_module.load_roadmap("atman") if i.title == "Construye la pagina de Cursos"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "done")
        self.assertIn("MISSION-TEST-1", items[0].mission_ids)

    def test_learn_from_mission_records_knowledge(self) -> None:
        business_services.learn_from_mission("MISSION-TEST-2", "Construye la pagina de Cursos", "")
        facts = knowledge_module.list_knowledge("atman", category="mission_history")
        self.assertTrue(any("MISSION-TEST-2" in f.fact for f in facts))

    def test_learn_from_mission_does_nothing_for_unresolved_requests(self) -> None:
        before = len(knowledge_module.list_knowledge("atman"))
        business_services.learn_from_mission("MISSION-TEST-3", "algo sin relacion con nada coneguida xyz", "")
        after = len(knowledge_module.list_knowledge("atman"))
        self.assertEqual(before, after)


class CLITests(unittest.TestCase):
    """Real subprocess invocations of bin/orion, isolated at temp
    ORION_BUSINESS_WORKSPACE/ORION_INTELLIGENCE_WORKSPACE directories."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ)
        self.env["ORION_BUSINESS_WORKSPACE"] = str(Path(self._tmp.name) / "business_brain")
        self.env["ORION_INTELLIGENCE_WORKSPACE"] = str(Path(self._tmp.name) / "intelligence")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "orion"), *args],
            cwd=str(REPO_ROOT), env=self.env, capture_output=True, text=True, timeout=60,
        )

    def test_company_create_and_list(self) -> None:
        created = self._run("company", "create", "testco", "Test Co")
        self.assertEqual(created.returncode, 0, created.stderr)
        listed = self._run("company", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("testco", listed.stdout)

    def test_project_roadmap_goals_knowledge_run_without_crashing(self) -> None:
        self._run("company", "create", "testco", "Test Co")
        for args in (["project", "list"], ["roadmap"], ["goals"], ["knowledge"]):
            result = self._run(*args)
            self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")

    def test_understand_business_flag_reports_unresolved_honestly(self) -> None:
        result = self._run("understand", "peticion totalmente ajena sin relacion xyz123", "--business")
        self.assertEqual(result.returncode, 1)  # honest non-zero exit: nothing resolved
        self.assertIn("No pude identificar", result.stdout)


class APIRouteTests(unittest.TestCase):
    """orion.business.routes coroutines invoked directly (no
    TestClient/httpx2 dependency -- same technique
    tests/test_runtime.py::APIRouteTests and
    tests/test_intelligence.py::APIRouteTests already established)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_business_dir = storage.BUSINESS_DIR
        storage.BUSINESS_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.BUSINESS_DIR = self._orig_business_dir
        self._tmp.cleanup()

    def test_companies_create_then_list_route(self) -> None:
        from orion.business import routes as business_routes

        payload = business_routes.CompanyCreateRequest(company_id="testco", name="Test Co")
        created = asyncio.run(business_routes.api_companies_create(payload))
        self.assertEqual(created["id"], "testco")

        listed = asyncio.run(business_routes.api_companies_list())
        self.assertEqual(len(listed), 1)

    def test_company_detail_404_for_unknown_company(self) -> None:
        from fastapi import HTTPException

        from orion.business import routes as business_routes

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(business_routes.api_company_detail("does-not-exist"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_understand_route_returns_real_brief(self) -> None:
        from orion.business import routes as business_routes

        company_module.create_company("atman", "ATMAN", websites=["atmanme.com"])
        project_module.add_project("atman", "Website", keywords=["cursos"])
        payload = business_routes.UnderstandRequest(request="Construye la pagina de Cursos")
        result = asyncio.run(business_routes.api_business_understand(payload))
        self.assertEqual(result["company"], "atman")


class RuntimeIntegrationTests(unittest.TestCase):
    """Real orion.agents.builder.agent.run_claimed_mission() Mission
    Flow integration: a resolved request must record
    business_context_loaded and skip the BETA 008 fallback; an
    unresolved request must fall back to the exact BETA 008
    intelligence_brief behavior. Reuses
    tests.test_runtime.IsolatedRuntimeTestCase's bridge/runtime
    storage isolation rather than duplicating it, plus isolates
    orion.business.storage and orion.intelligence.storage on top."""

    def setUp(self) -> None:
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

        self._business_tmp = tempfile.TemporaryDirectory()
        self._orig_business_dir = storage.BUSINESS_DIR
        storage.BUSINESS_DIR = Path(self._business_tmp.name)

        from orion.intelligence import storage as intelligence_storage

        self._intelligence_tmp = tempfile.TemporaryDirectory()
        self._orig_intelligence_dir = intelligence_storage.INTELLIGENCE_DIR
        intelligence_storage.INTELLIGENCE_DIR = Path(self._intelligence_tmp.name)

    def tearDown(self) -> None:
        from orion.intelligence import storage as intelligence_storage

        intelligence_storage.INTELLIGENCE_DIR = self._orig_intelligence_dir
        self._intelligence_tmp.cleanup()
        storage.BUSINESS_DIR = self._orig_business_dir
        self._business_tmp.cleanup()
        self._inner.tearDown()

    def test_resolved_request_records_business_context_and_skips_fallback(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        company_module.create_company("atman", "ATMAN", websites=["atmanme.com"])
        project_module.add_project("atman", "Website", keywords=["cursos"])

        mission = bridge_services.create_mission(
            MissionCreate(title="Construye la pagina de Cursos", mission_type="executor"), author="test"
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")

        finished = builder_agent.run_claimed_mission(mission)
        self.assertIsNotNone(finished)

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertIn("business_context_loaded", event_types)
        self.assertNotIn("intelligence_brief", event_types)

    def test_unresolved_request_falls_back_to_beta008_intelligence_brief(self) -> None:
        from orion.agents.builder import agent as builder_agent
        from orion.bridge import services as bridge_services
        from orion.bridge.models import MissionCreate, MissionStatus

        mission = bridge_services.create_mission(
            MissionCreate(title="peticion sin relacion con ninguna empresa coneguida xyz", mission_type="executor"),
            author="test",
        )
        bridge_services.update_status(mission.id, MissionStatus.READY, author="test")

        finished = builder_agent.run_claimed_mission(mission)
        self.assertIsNotNone(finished)

        event_types = [e.type for e in bridge_services.get_events(mission.id)]
        self.assertIn("business_context_loaded", event_types)
        self.assertIn("intelligence_brief", event_types)


if __name__ == "__main__":
    unittest.main()
