"""Tests for orion.prompt_composer.

Uses only the standard library's unittest (no pytest, no new external
dependency), consistent with every prior Sprint's "no new dependencies"
rule. Run with:

    python3 -m unittest tests.test_prompt_composer -v

Every test that needs a "repository" builds a real, disposable git
repo under a TemporaryDirectory and cleans it up automatically --
never touches Orion-AI's own working tree or any real project.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge.models import Mission, MissionStatus
from orion.execution import git_manager
from orion.projects.models import Project
from orion.prompt_composer import composer, discovery
from orion.prompt_composer.models import PromptPackage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_mission(**overrides: object) -> Mission:
    defaults: dict[str, object] = dict(
        id="MISSION-TEST",
        title="Test mission",
        description="",
        mission_type="documentation",
        status=MissionStatus.NEW,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Mission(**defaults)  # type: ignore[arg-type]


def _make_project(**overrides: object) -> Project:
    defaults: dict[str, object] = dict(
        project_id="testproj",
        name="Test Project",
        description="A disposable project used only by tests.",
        repository="",
        default_branch="main",
        created_at=_now(),
        updated_at=_now(),
        metadata={"business_unit_slug": "testproj"},
    )
    defaults.update(overrides)
    return Project(**defaults)  # type: ignore[arg-type]


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message], check=True)


class DiscoveryTests(unittest.TestCase):
    """discovery.py against a real, disposable repository -- never
    against Orion-AI's own working tree."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        _init_repo(self.repo_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_discover_docs_finds_known_conventions(self) -> None:
        (self.repo_root / "TEAM.md").write_text("# Team\n", encoding="utf-8")
        (self.repo_root / "README.md").write_text("# Readme\n", encoding="utf-8")
        (self.repo_root / "docs").mkdir()
        (self.repo_root / "docs" / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
        (self.repo_root / "docs" / "DESIGN_SYSTEM.md").write_text("# Design System\n", encoding="utf-8")
        (self.repo_root / "design-tokens").mkdir()
        (self.repo_root / "design-tokens" / "tokens.json").write_text("{}", encoding="utf-8")
        (self.repo_root / "docs" / "adr").mkdir()
        (self.repo_root / "docs" / "adr" / "0001-use-git.md").write_text("# ADR 1\n", encoding="utf-8")

        docs = discovery.discover_docs(self.repo_root)
        by_category = {d.category: d for d in docs}

        self.assertEqual(by_category["team"].path, "TEAM.md")
        self.assertEqual(by_category["readme"].path, "README.md")
        self.assertEqual(by_category["architecture"].path, "docs/ARCHITECTURE.md")
        self.assertEqual(by_category["design_system"].path, "docs/DESIGN_SYSTEM.md")
        self.assertEqual(by_category["design_tokens"].path, "design-tokens/tokens.json")
        self.assertTrue(any(d.category == "adr" and d.path.endswith("0001-use-git.md") for d in docs))

    def test_discover_docs_empty_repo_yields_nothing(self) -> None:
        self.assertEqual(discovery.discover_docs(self.repo_root), [])

    def test_discover_docs_never_raises_on_binary_or_missing(self) -> None:
        # A README.md that isn't valid UTF-8 must not blow up discovery.
        (self.repo_root / "README.md").write_bytes(b"\xff\xfe not real utf-8")
        docs = discovery.discover_docs(self.repo_root)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].excerpt, "")

    def test_recent_commits_on_unborn_repo_is_empty(self) -> None:
        self.assertEqual(git_manager.recent_commits(repo_root=self.repo_root), [])

    def test_recent_commits_after_real_commits(self) -> None:
        (self.repo_root / "a.txt").write_text("a", encoding="utf-8")
        _commit_all(self.repo_root, "first commit")
        (self.repo_root / "b.txt").write_text("b", encoding="utf-8")
        _commit_all(self.repo_root, "second commit")

        commits = discovery.discover_recent_commits(self.repo_root, limit=5)
        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0].message, "second commit")
        self.assertEqual(commits[1].message, "first commit")
        self.assertTrue(all(c.hash for c in commits))

    def test_discover_related_files_from_artifact_fields(self) -> None:
        mission = _make_mission(artifact_path="docs/ARCHITECTURE.md")
        files = discovery.discover_related_files(mission)
        self.assertEqual([f.path for f in files], ["docs/ARCHITECTURE.md"])

        mission2 = _make_mission(
            id="MISSION-TEST-2",
            artifact_files={"a.tsx": "x", "b.tsx": "y"},
        )
        files2 = discovery.discover_related_files(mission2)
        self.assertEqual(sorted(f.path for f in files2), ["a.tsx", "b.tsx"])

    def test_discover_related_missions_by_project_and_tags(self) -> None:
        mission = _make_mission(project_id="atman", tags=["home", "componente"])
        same_project = _make_mission(id="MISSION-B", project_id="atman", title="Other atman mission")
        shared_tag = _make_mission(id="MISSION-C", project_id="", tags=["componente"], title="Unrelated project, shared tag")
        unrelated = _make_mission(id="MISSION-D", project_id="other", tags=["nothing"], title="Unrelated")

        related = discovery.discover_related_missions(mission, [mission, same_project, shared_tag, unrelated])
        related_ids = {r.mission_id for r in related}

        self.assertIn("MISSION-B", related_ids)
        self.assertIn("MISSION-C", related_ids)
        self.assertNotIn("MISSION-D", related_ids)
        self.assertNotIn(mission.id, related_ids)  # never relates a mission to itself

    def test_discover_project_status_without_project(self) -> None:
        status = discovery.discover_project_status(None)
        self.assertIn("note", status)


class ComposerTests(unittest.TestCase):
    """composer.compose() end to end against a real disposable repo."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        _init_repo(self.repo_root)
        (self.repo_root / "docs").mkdir()
        (self.repo_root / "docs" / "ARCHITECTURE.md").write_text("# Architecture\nSome real content.\n", encoding="utf-8")
        (self.repo_root / "README.md").write_text("# Readme\n", encoding="utf-8")
        (self.repo_root / "a.txt").write_text("a", encoding="utf-8")
        _commit_all(self.repo_root, "initial commit")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_compose_produces_a_full_package(self) -> None:
        mission = _make_mission(
            title="Build the thing",
            description="Some work.\n\nCriterio de aceptacion:\n- Debe compilar\n- Debe verse bien\n",
            project_id="testproj",
            tags=["x"],
        )
        project = _make_project(project_id="testproj")

        package = composer.compose(mission, project, self.repo_root, all_missions=[mission])

        self.assertIsInstance(package, PromptPackage)
        self.assertEqual(package.mission.id, mission.id)
        self.assertEqual(package.project.project_id, "testproj")
        self.assertEqual(package.business_context.project_name, "Test Project")
        self.assertIn("Some real content.", package.technical_context.architecture_summary)
        self.assertEqual(package.acceptance_criteria, ["Debe compilar", "Debe verse bien"])
        self.assertTrue(package.suggested_plan.steps)
        self.assertIn(mission.title, package.execution_prompt.instructions)
        self.assertTrue(package.execution_prompt.constraints)
        self.assertEqual(len(package.recent_commits), 1)

    def test_compose_without_project_is_still_valid(self) -> None:
        mission = _make_mission(title="Kernel work, no project")
        package = composer.compose(mission, None, self.repo_root, all_missions=[mission])

        self.assertIsNone(package.project)
        self.assertEqual(package.business_context.project_name, "Orion-AI")

    def test_compose_falls_back_to_generic_acceptance_criteria(self) -> None:
        mission = _make_mission(title="No explicit criteria", description="Just do it.")
        package = composer.compose(mission, None, self.repo_root, all_missions=[mission])
        self.assertEqual(len(package.acceptance_criteria), 1)
        self.assertIn("Just do it.", package.acceptance_criteria[0])

    def test_compose_is_json_round_trippable(self) -> None:
        mission = _make_mission(title="Round trip me")
        package = composer.compose(mission, None, self.repo_root, all_missions=[mission])
        dumped = package.model_dump(mode="json")
        rebuilt = PromptPackage(**dumped)
        self.assertEqual(rebuilt, package)

    def test_compose_never_invents_a_provider_specific_format(self) -> None:
        # Guard against regressions that would sneak vendor-specific
        # formatting (Claude/Codex/Gemini message-role structures, XML
        # tags, etc.) into what must stay a neutral text block.
        mission = _make_mission(title="Neutral check")
        package = composer.compose(mission, None, self.repo_root, all_missions=[mission])
        forbidden_markers = ["<system>", "role:", "Human:", "Assistant:", "###Instruction"]
        for marker in forbidden_markers:
            self.assertNotIn(marker, package.execution_prompt.instructions)


if __name__ == "__main__":
    unittest.main()
