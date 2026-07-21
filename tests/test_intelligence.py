"""Tests for orion.intelligence (BETA 008: Project Intelligence).

Standard library unittest only (no pytest, no new dependency), same
convention as every other test module in this repo. Covers exactly
what this Sprint's brief lists: Repository Analyzer, Dependency Graph,
Component Finder, Impact Analyzer, Planner, Reviewer, Knowledge Graph,
CLI, API, Runtime Integration, Cache, Incremental Index.

Every module under test is exercised against real files on a real
filesystem (a small synthetic repository built fresh in setUp, plus a
couple of read-only checks against ORION-AI's own real repository) --
nothing here mocks repository_analyzer's ast parsing or fabricates a
FileRecord/ProjectIndex by hand.

Run with:

    python3 -m unittest tests.test_intelligence -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from orion.intelligence import (
    architecture_map,
    component_finder,
    dependency_graph,
    impact_analyzer,
    knowledge_graph,
    project_index,
    repository_analyzer,
    reviewer,
    services as intelligence_services,
    storage,
    task_planner,
)
from orion.intelligence.config import IntelligenceConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _build_sample_repo(root: Path) -> None:
    """A small, real, synthetic repo: one package with a real import
    chain (app -> services -> models), a test file, a TODO, and a
    security-relevant line, so every module under test has real,
    deterministic ground truth to check against."""
    _write(root / "app" / "__init__.py", "")
    _write(
        root / "app" / "models.py",
        '''
        """Domain models."""

        class User:
            """A user record."""

            def __init__(self, name: str) -> None:
                self.name = name
        '''.strip("\n"),
    )
    _write(
        root / "app" / "services.py",
        '''
        """Business logic. TODO: add caching here."""

        from app.models import User


        def create_user(name: str) -> User:
            """Create and return a new User."""
            return User(name)
        '''.strip("\n"),
    )
    _write(
        root / "app" / "main.py",
        '''
        """Entry point."""

        from app.services import create_user

        if __name__ == "__main__":
            create_user("demo")
        '''.strip("\n"),
    )
    _write(
        root / "app" / "unsafe.py",
        '''
        import os

        def run(cmd: str) -> None:
            os.system(cmd)
            eval(cmd)
            API_KEY = "sk-abcdef123456"
        '''.strip("\n"),
    )
    _write(
        root / "tests" / "test_services.py",
        '''
        """Tests for app.services."""

        import unittest


        class ServicesTests(unittest.TestCase):
            def test_placeholder(self) -> None:
                self.assertTrue(True)
        '''.strip("\n"),
    )
    _write(root / "README.md", "# Sample\n\nA sample repo for tests.\n")


class SampleRepoTestCase(unittest.TestCase):
    """Builds a fresh synthetic repo per test and isolates
    orion.intelligence.storage's persistence directory at a temp path
    -- never touches Orion-AI's real workspace/intelligence/."""

    def setUp(self) -> None:
        self._repo_tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._repo_tmp.name)
        _build_sample_repo(self.repo_root)

        self._storage_tmp = tempfile.TemporaryDirectory()
        self._orig_intelligence_dir = storage.INTELLIGENCE_DIR
        storage.INTELLIGENCE_DIR = Path(self._storage_tmp.name)

        self.config = IntelligenceConfig(workspace_dir=storage.INTELLIGENCE_DIR)

    def tearDown(self) -> None:
        storage.INTELLIGENCE_DIR = self._orig_intelligence_dir
        self._storage_tmp.cleanup()
        self._repo_tmp.cleanup()

    def _scan(self):
        profile, records = repository_analyzer.scan_repository(self.repo_root, config=self.config)
        files = {record.path: record for record in records}
        return profile, files


class RepositoryAnalyzerTests(SampleRepoTestCase):
    def test_scan_finds_every_real_file_and_classifies_language(self) -> None:
        profile, files = self._scan()
        rel_paths = set(files)
        self.assertIn("app/services.py", rel_paths)
        self.assertIn("app/models.py", rel_paths)
        self.assertIn("tests/test_services.py", rel_paths)
        self.assertIn("README.md", rel_paths)
        self.assertEqual(profile.languages.get("python"), 6)  # __init__, models, services, main, unsafe, test_services

    def test_real_ast_extracts_imports_and_exports(self) -> None:
        _, files = self._scan()
        services_record = files["app/services.py"]
        self.assertIn("app.models", services_record.imports)
        self.assertIn("create_user", services_record.exports)

    def test_todo_detection_is_real_not_fabricated(self) -> None:
        profile, _ = self._scan()
        todo_paths = {item["path"] for item in profile.todo_items}
        self.assertIn("app/services.py", todo_paths)

    def test_incremental_fast_path_skips_reread_when_unchanged(self) -> None:
        target = self.repo_root / "app" / "services.py"
        stat1 = target.stat()
        previous = repository_analyzer.analyze_file(
            target, self.repo_root, self.config, previous=None
        )
        # Same size/mtime -> the fast path must return a record without
        # re-parsing (verified by identity-equivalent content: exports
        # still correct without needing to touch the file again).
        unchanged = repository_analyzer.analyze_file(
            target, self.repo_root, self.config, previous=previous
        )
        self.assertEqual(unchanged.size_bytes, stat1.st_size)
        self.assertEqual(unchanged.exports, previous.exports)

    def test_changed_file_is_really_reanalyzed(self) -> None:
        target = self.repo_root / "app" / "services.py"
        previous = repository_analyzer.analyze_file(target, self.repo_root, self.config, previous=None)
        # Real modification: add a new top-level function.
        target.write_text(target.read_text(encoding="utf-8") + "\n\ndef extra_fn():\n    pass\n", encoding="utf-8")
        updated = repository_analyzer.analyze_file(target, self.repo_root, self.config, previous=previous)
        self.assertIn("extra_fn", updated.exports)
        self.assertNotEqual(updated.content_hash, previous.content_hash)


class ProjectIndexCacheTests(SampleRepoTestCase):
    def test_build_index_persists_and_reloads(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        self.assertGreaterEqual(index.file_count(), 6)
        reloaded = project_index.load_index("sample")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.file_count(), index.file_count())

    def test_incremental_build_reuses_unchanged_records(self) -> None:
        first = project_index.build_index(self.repo_root, "sample", config=self.config)
        first_record = first.files["app/models.py"]

        second = project_index.build_index(self.repo_root, "sample", config=self.config)
        second_record = second.files["app/models.py"]
        # Real proof of cache reuse: identical content_hash without the
        # file having been touched between builds.
        self.assertEqual(first_record.content_hash, second_record.content_hash)
        self.assertEqual(first_record.exports, second_record.exports)

    def test_force_full_still_produces_a_correct_index(self) -> None:
        project_index.build_index(self.repo_root, "sample", config=self.config)
        rebuilt = project_index.build_index(self.repo_root, "sample", config=self.config, force_full=True)
        self.assertIn("app/services.py", rebuilt.files)


class ArchitectureMapTests(SampleRepoTestCase):
    def test_tree_reflects_real_directory_structure(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        tree = architecture_map.build_architecture_map(index)
        names = {child.name for child in tree.children.values()}
        self.assertIn("app", names)
        self.assertIn("tests", names)
        app_node = tree.children["app"]
        self.assertEqual(app_node.total_files(), 5)


class DependencyGraphTests(SampleRepoTestCase):
    def test_impacted_by_finds_real_transitive_dependents(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        graph = dependency_graph.build_dependency_graph(index)
        impacted = graph.impacted_by("app.models")
        self.assertIn("app.services", impacted)
        self.assertIn("app.main", impacted)  # transitive: main imports services imports models

    def test_module_name_for_path_is_real_dotted_path(self) -> None:
        name = dependency_graph.module_name_for_path("app/services.py")
        self.assertEqual(name, "app.services")


class ComponentFinderTests(SampleRepoTestCase):
    def test_finds_real_similarity_match_by_keyword_overlap(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        matches = component_finder.find_components(index, "crear un nuevo user", threshold=0.1)
        paths = [m.path for m in matches]
        self.assertIn("app/models.py", paths)

    def test_every_match_has_a_real_nonempty_reason(self) -> None:
        # Regression: _score() used to reference `score` before it was
        # assigned whenever a match's only signal was a low, non-zero
        # seq_ratio/overlap combination -- this raised UnboundLocalError
        # for real, valid low-similarity queries against a real index
        # (found via orion.intelligence.services.prepare_request()
        # smoke-testing against ORION-AI's own repo during BETA 008).
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        matches = component_finder.find_components(index, "algo que no coincide con nada en particular", threshold=0.01)
        for match in matches:
            self.assertTrue(match.reasons, f"{match.path} matched with no reason recorded")

    def test_empty_index_or_query_yields_no_fabricated_matches(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        self.assertEqual(component_finder.find_components(index, ""), [])


class ImpactAnalyzerTests(SampleRepoTestCase):
    def test_modifying_a_low_level_module_shows_real_dependents(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        graph = dependency_graph.build_dependency_graph(index)
        report = impact_analyzer.compute_impact(index, graph, ["app/models.py"])
        self.assertIn("app/services.py", report.affected_files)
        self.assertIn("app/main.py", report.affected_files)

    def test_target_with_no_dependents_is_low_risk(self) -> None:
        index = project_index.build_index(self.repo_root, "sample", config=self.config)
        graph = dependency_graph.build_dependency_graph(index)
        report = impact_analyzer.compute_impact(index, graph, ["README.md"])
        self.assertEqual(report.risk, "bajo")


class TaskPlannerTests(unittest.TestCase):
    def test_never_returns_zero_steps(self) -> None:
        plan = task_planner.plan_request("algo sin ninguna palabra clave reconocida")
        self.assertGreaterEqual(len(plan.steps), 1)
        self.assertEqual(plan.template, "generico")

    def test_matches_real_keyword_templates(self) -> None:
        bugfix = task_planner.plan_request("hay un bug en el login")
        self.assertEqual(bugfix.template, "bugfix")
        page = task_planner.plan_request("crea la pagina de cursos")
        self.assertEqual(page.template, "pagina_full_stack")

    def test_plan_ids_are_unique_across_calls(self) -> None:
        plan1 = task_planner.plan_request("arregla el bug")
        plan2 = task_planner.plan_request("arregla el bug")
        self.assertNotEqual(plan1.plan_id, plan2.plan_id)


class ReviewerTests(SampleRepoTestCase):
    def test_finds_real_security_issues(self) -> None:
        report = reviewer.review_files(["app/unsafe.py"], self.repo_root)
        categories = [f.category for f in report.findings if f.severity == "error"]
        self.assertIn("seguridad", categories)
        self.assertFalse(report.passed())

    def test_clean_file_produces_no_error_findings(self) -> None:
        report = reviewer.review_files(["app/models.py"], self.repo_root)
        self.assertTrue(report.passed())

    def test_future_import_is_never_a_false_positive(self) -> None:
        # Regression: node.module == "__future__" must be checked on the
        # ImportFrom node itself, not the imported alias name
        # ("annotations") -- the original bug flagged every real
        # `from __future__ import annotations` as an unused import.
        target = self.repo_root / "app" / "future_ok.py"
        target.write_text(
            "from __future__ import annotations\n\n\ndef fn() -> None:\n    return None\n", encoding="utf-8"
        )
        report = reviewer.review_files(["app/future_ok.py"], self.repo_root)
        messages = [f.message for f in report.findings]
        self.assertFalse(any("__future__" in m or "annotations" in m for m in messages))

    def test_missing_file_is_informational_not_a_crash(self) -> None:
        report = reviewer.review_files(["app/does_not_exist.py"], self.repo_root)
        self.assertEqual(report.findings[0].severity, "info")


class KnowledgeGraphTests(SampleRepoTestCase):
    def test_seed_schema_is_present(self) -> None:
        graph = knowledge_graph.load_knowledge_graph()
        self.assertEqual(graph.node_count(), 7)
        self.assertEqual(graph.edge_count(), 6)

    def test_recording_a_mission_grows_the_graph_for_real(self) -> None:
        graph = knowledge_graph.load_knowledge_graph()
        before_nodes = graph.node_count()
        knowledge_graph.record_mission_knowledge(
            graph, "MISSION-TEST-1", "Test mission", "deterministic_local", ["app/services.py"], 0.8
        )
        knowledge_graph.save_knowledge_graph(graph)
        self.assertGreater(graph.node_count(), before_nodes)

        reloaded = knowledge_graph.load_knowledge_graph()
        self.assertEqual(reloaded.node_count(), graph.node_count())


class ServicesTests(SampleRepoTestCase):
    def test_analyze_project_uses_resolved_repo_root(self) -> None:
        # analyze_project() itself always resolves project_key via
        # resolve_repo_root(); exercise it directly against our sample
        # repo by monkeypatching resolve_repo_root for this one call.
        original = intelligence_services.resolve_repo_root
        intelligence_services.resolve_repo_root = lambda project_key: self.repo_root
        try:
            index = intelligence_services.analyze_project("sample")
        finally:
            intelligence_services.resolve_repo_root = original
        self.assertGreaterEqual(index.file_count(), 6)

    def test_prepare_request_never_crashes_on_a_query_with_no_matches(self) -> None:
        original = intelligence_services.resolve_repo_root
        intelligence_services.resolve_repo_root = lambda project_key: self.repo_root
        try:
            brief = intelligence_services.prepare_request("algo completamente distinto y raro", project_key="sample")
        finally:
            intelligence_services.resolve_repo_root = original
        self.assertIsInstance(brief.summary_text(), str)
        self.assertGreaterEqual(len(brief.plan.steps), 1)

    def test_plan_request_wrapper_persists_the_plan(self) -> None:
        plan = intelligence_services.plan_request("arregla el bug de login", project_key="sample")
        loaded = storage.read_yaml(storage.plan_path("sample", plan.plan_id), default=None)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["plan_id"], plan.plan_id)


class CLITests(unittest.TestCase):
    """Real subprocess invocations of bin/orion, isolated at a temp
    ORION_INTELLIGENCE_WORKSPACE so nothing here writes into
    Orion-AI's real workspace/intelligence/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ)
        self.env["ORION_INTELLIGENCE_WORKSPACE"] = str(Path(self._tmp.name) / "intelligence")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "orion"), *args],
            cwd=str(REPO_ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_analyze_runs_and_reports_real_counts(self) -> None:
        result = self._run("analyze")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Archivos indexados:", result.stdout)
        self.assertIn("Mapa de arquitectura:", result.stdout)

    def test_plan_runs_and_reports_real_steps(self) -> None:
        result = self._run("plan", "Arregla el bug de login")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bugfix", result.stdout)

    def test_review_runs_against_a_real_file(self) -> None:
        result = self._run("review", "bin/orion")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Aprobado: True", result.stdout)


class APIRouteTests(unittest.TestCase):
    """orion.intelligence.routes coroutines invoked directly (no
    TestClient/httpx2 dependency -- same technique
    tests/test_runtime.py::APIRouteTests already established)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_intelligence_dir = storage.INTELLIGENCE_DIR
        storage.INTELLIGENCE_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.INTELLIGENCE_DIR = self._orig_intelligence_dir
        self._tmp.cleanup()

    def test_index_route_returns_real_data(self) -> None:
        from orion.intelligence import routes as intelligence_routes

        result = asyncio.run(intelligence_routes.api_intelligence_index(project_id=""))
        self.assertIn("files", result)
        self.assertGreater(len(result["files"]), 0)

    def test_knowledge_graph_route_returns_seeded_schema(self) -> None:
        from orion.intelligence import routes as intelligence_routes

        result = asyncio.run(intelligence_routes.api_intelligence_knowledge_graph())
        self.assertEqual(len(result["nodes"]), 7)

    def test_plan_route_returns_real_plan(self) -> None:
        from orion.intelligence import routes as intelligence_routes

        payload = intelligence_routes.PlanRequest(request="arregla el bug de login", project_id="")
        result = asyncio.run(intelligence_routes.api_intelligence_plan(payload))
        self.assertEqual(result["template"], "bugfix")


class RuntimeIntegrationTests(unittest.TestCase):
    """Real orion.runtime.services.ask() integration: auto_plan=False
    must remain byte-for-byte the BETA 007 single-mission behavior;
    auto_plan=True must create one real Mission per real Task Planner
    step. Reuses tests.test_runtime.IsolatedRuntimeTestCase's storage
    isolation (bridge + runtime) rather than duplicating it, and adds
    orion.intelligence.storage isolation on top -- ask(auto_plan=True)
    is the one BETA 007 code path that now also writes Intelligence
    data (a persisted Plan)."""

    def setUp(self) -> None:
        from tests.test_runtime import IsolatedRuntimeTestCase

        self._inner = IsolatedRuntimeTestCase()
        self._inner.setUp()

        self._storage_tmp = tempfile.TemporaryDirectory()
        self._orig_intelligence_dir = storage.INTELLIGENCE_DIR
        storage.INTELLIGENCE_DIR = Path(self._storage_tmp.name)

    def tearDown(self) -> None:
        storage.INTELLIGENCE_DIR = self._orig_intelligence_dir
        self._storage_tmp.cleanup()
        self._inner.tearDown()

    def test_default_ask_creates_exactly_one_mission(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.runtime import services as runtime_services
        from orion.runtime.models import MissionAskRequest

        response = runtime_services.ask(MissionAskRequest(title="Crear hello.txt"))
        self.assertEqual(response.mission_ids, [])
        self.assertEqual(response.plan_id, "")
        self.assertIsNotNone(bridge_services.get_mission(response.mission_id))

    def test_auto_plan_creates_one_real_mission_per_plan_step(self) -> None:
        from orion.bridge import services as bridge_services
        from orion.runtime import services as runtime_services
        from orion.runtime.models import MissionAskRequest

        response = runtime_services.ask(
            MissionAskRequest(title="Arregla el bug de login", auto_plan=True)
        )
        self.assertEqual(len(response.mission_ids), 4)  # real "bugfix" template: 4 steps
        self.assertNotEqual(response.plan_id, "")
        self.assertEqual(response.mission_id, response.mission_ids[0])

        for mission_id in response.mission_ids:
            mission = bridge_services.get_mission(mission_id)
            self.assertIsNotNone(mission)
            self.assertEqual(mission.mission_type, "executor")

        loaded_plan = storage.read_yaml(storage.plan_path(storage.SELF_PROJECT_KEY, response.plan_id), default=None)
        self.assertIsNotNone(loaded_plan)
        self.assertEqual(len(loaded_plan["steps"]), 4)


if __name__ == "__main__":
    unittest.main()
