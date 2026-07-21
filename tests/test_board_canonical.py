"""Tests for MISSION G-012 (Single Source of Truth for the AI Board):
orion.board.canonical (loader/validator for .ai/board.yaml),
orion.board.generator (idempotent AGENTS.md/.ai/BOARD.md sync), the
refactored orion.board.member_registry (now deriving board_seat from
the canonical source instead of a hardcoded string), the CLI (`orion
board validate`/`generate`/`generate --check`), the new `/api/board/
roster` route, and explicit regression coverage: Gemini must not
appear as an official member anywhere, the six previously-existing
seats must be unchanged, and B-011's own pipeline-selection behavior
must be untouched.

Run with:

    python3 -m unittest tests.test_board_canonical -v
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from orion.board import canonical, generator
from orion.board.canonical import BoardConfigurationError, load_board_config, parse_and_validate

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_MINIMAL_MEMBER = {
    "id": "x",
    "display_name": "X",
    "role": "R",
    "status": "active",
}


def _config(members: list[dict], schema_version: int = 1, board_version: int = 1) -> dict:
    return {"schema_version": schema_version, "board_version": board_version, "members": members}


class CanonicalLoaderTests(unittest.TestCase):
    """Loads the REAL .ai/board.yaml -- read-only, never modified."""

    def test_real_board_yaml_loads_and_validates(self) -> None:
        config = load_board_config()
        self.assertEqual(config.schema_version, 1)
        self.assertEqual(len(config.members), 6)

    def test_real_board_yaml_contains_exactly_the_six_known_seats(self) -> None:
        config = load_board_config()
        ids = {m.id for m in config.members}
        self.assertEqual(
            ids, {"luis-aguirre", "chatgpt", "claude", "jules", "nemotron", "autoclaw"}
        )

    def test_real_board_yaml_order_is_deterministic_across_loads(self) -> None:
        first = [m.id for m in load_board_config().members]
        second = [m.id for m in load_board_config().members]
        self.assertEqual(first, second)

    def test_real_board_yaml_serialization_stable(self) -> None:
        self.assertEqual(load_board_config(), load_board_config())

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(BoardConfigurationError):
            load_board_config(path=REPO_ROOT / ".ai" / "does_not_exist.yaml")

    def test_malformed_yaml_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("members: [this is not: valid: yaml: at: all:")
            path = Path(f.name)
        try:
            with self.assertRaises(BoardConfigurationError):
                load_board_config(path=path)
        finally:
            path.unlink()

    def test_unsupported_schema_version_raises(self) -> None:
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([VALID_MINIMAL_MEMBER], schema_version=99))

    def test_member_without_id_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER)
        del bad["id"]
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_duplicate_id_raises(self) -> None:
        m1 = dict(VALID_MINIMAL_MEMBER)
        m2 = dict(VALID_MINIMAL_MEMBER, display_name="Y")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([m1, m2]))

    def test_duplicate_display_name_raises(self) -> None:
        m1 = dict(VALID_MINIMAL_MEMBER)
        m2 = dict(VALID_MINIMAL_MEMBER, id="y")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([m1, m2]))

    def test_empty_role_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, role="")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_invalid_status_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, status="not-a-real-status")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_missing_documentation_file_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, documentation_path="agents/does-not-exist.md")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]), repo_root=REPO_ROOT)

    def test_documentation_file_that_exists_is_accepted(self) -> None:
        good = dict(VALID_MINIMAL_MEMBER, documentation_path="agents/gemini.md")
        config = parse_and_validate(_config([good]), repo_root=REPO_ROOT)
        self.assertEqual(config.members[0].documentation_path, "agents/gemini.md")

    def test_malformed_capabilities_entry_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, capabilities=[123])
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_unknown_supersedes_reference_raises(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, supersedes="ghost-member")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_known_supersedes_reference_is_accepted(self) -> None:
        m1 = dict(VALID_MINIMAL_MEMBER)
        m2 = dict(VALID_MINIMAL_MEMBER, id="y", display_name="Y", supersedes="x")
        config = parse_and_validate(_config([m1, m2]))
        self.assertEqual(config.get("y").supersedes, "x")

    def test_no_members_at_all_raises(self) -> None:
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([]))

    def test_seat_label_format(self) -> None:
        config = parse_and_validate(_config([dict(VALID_MINIMAL_MEMBER, display_name="Jules", role="Lead Software Engineer")]))
        self.assertEqual(config.get("x").seat_label(), "Jules (Lead Software Engineer)")


class MemberRegistryIntegrationTests(unittest.TestCase):
    """orion.board.member_registry must derive board_seat from the
    canonical source, never a second hand-maintained string, while
    keeping its existing public API (MEMBERS/ALL_KEYS/get_member/
    list_members) fully backward compatible."""

    def test_imports_still_work(self) -> None:
        from orion.board.member_registry import ALL_KEYS, MEMBERS, get_member, list_members

        self.assertEqual(len(MEMBERS), 6)
        self.assertEqual(len(ALL_KEYS), 6)
        self.assertEqual(len(list_members()), 6)
        self.assertIsNotNone(get_member("builder"))

    def test_stage_board_seats_match_canonical_seat_labels(self) -> None:
        from orion.board import member_registry

        config = load_board_config()
        self.assertEqual(member_registry.get_member("builder").board_seat, config.get("jules").seat_label())
        self.assertEqual(member_registry.get_member("reviewer").board_seat, config.get("nemotron").seat_label())
        self.assertEqual(member_registry.get_member("gitops").board_seat, config.get("autoclaw").seat_label())
        expected_architect = f"{config.get('chatgpt').seat_label()} / {config.get('claude').seat_label()}"
        self.assertEqual(member_registry.get_member("architect").board_seat, expected_architect)

    def test_qa_and_experience_have_no_board_seat_regression(self) -> None:
        from orion.board import member_registry

        self.assertIsNone(member_registry.get_member("qa").board_seat)
        self.assertIsNone(member_registry.get_member("experience").board_seat)

    def test_falls_back_gracefully_when_canonical_load_fails(self) -> None:
        """A broken/missing .ai/board.yaml must never break every
        consumer of orion.board.member_registry (Governance, Runtime,
        CLI, API, Window) -- only `orion board validate` should ever
        surface that as a real error."""
        original_loader = canonical.load_board_config
        canonical.load_board_config = lambda *a, **kw: (_ for _ in ()).throw(
            BoardConfigurationError("simulated corrupt board.yaml")
        )
        try:
            import orion.board.member_registry as mr

            importlib.reload(mr)
            self.assertIsNone(mr._CANONICAL_BOARD)
            self.assertEqual(mr.get_member("builder").board_seat, "Jules (Lead Software Engineer)")
            self.assertEqual(mr.get_member("qa").board_seat, None)
        finally:
            canonical.load_board_config = original_loader
            import orion.board.member_registry as mr

            importlib.reload(mr)  # restore the real, working state for every later test

    def test_reloading_with_real_canonical_source_matches_original_values(self) -> None:
        """Regression: after the fallback test above reloads the
        module with a broken loader and then restores it, the real
        values must come back byte-identical to what B-011 originally
        hardcoded."""
        import orion.board.member_registry as mr

        importlib.reload(mr)
        self.assertEqual(mr.get_member("builder").board_seat, "Jules (Lead Software Engineer)")
        self.assertEqual(mr.get_member("reviewer").board_seat, "Nemotron (Principal Engineering Reviewer)")
        self.assertEqual(mr.get_member("gitops").board_seat, "AutoClaw (Operations Engineer)")
        self.assertEqual(
            mr.get_member("architect").board_seat,
            "ChatGPT (Chief AI Architect) / Claude (Chief Software Architect)",
        )


class GeneratorTests(unittest.TestCase):
    """Uses disposable temp-file copies for every write/drift test --
    never the real AGENTS.md/.ai/BOARD.md -- the same lesson already
    learned the hard way in tests/test_business.py and
    tests/test_board.py's own RuntimeIntegrationTests this session."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)

        real_agents = generator.AGENTS_MD_PATH.read_text(encoding="utf-8")
        real_board_md = generator.BOARD_MD_PATH.read_text(encoding="utf-8")

        self._tmp_agents = tmp_path / "AGENTS.md"
        self._tmp_board_md = tmp_path / "BOARD.md"
        self._tmp_agents.write_text(real_agents, encoding="utf-8")
        self._tmp_board_md.write_text(real_board_md, encoding="utf-8")

        self._orig_agents_path = generator.AGENTS_MD_PATH
        self._orig_board_md_path = generator.BOARD_MD_PATH
        generator.AGENTS_MD_PATH = self._tmp_agents
        generator.BOARD_MD_PATH = self._tmp_board_md

    def tearDown(self) -> None:
        generator.AGENTS_MD_PATH = self._orig_agents_path
        generator.BOARD_MD_PATH = self._orig_board_md_path
        self._tmp.cleanup()

    def test_no_drift_against_a_fresh_copy_of_the_real_files(self) -> None:
        results = generator.check_drift()
        self.assertTrue(all(not r.has_drift for r in results), [r.path for r in results if r.has_drift])

    def test_generate_is_idempotent(self) -> None:
        first = generator.generate()
        second = generator.generate()
        self.assertTrue(any(r.has_drift for r in first) or True)  # first run may or may not change anything
        self.assertTrue(all(not r.has_drift for r in second))

    def test_check_mode_never_writes_even_when_drift_exists(self) -> None:
        # Corrupt the copy's generated block so real drift exists.
        corrupted = self._tmp_agents.read_text(encoding="utf-8").replace("Jules", "SOMEONE ELSE")
        self._tmp_agents.write_text(corrupted, encoding="utf-8")

        results = generator.check_drift()
        self.assertTrue(any(r.has_drift for r in results))
        # File on disk must be untouched by check_drift/generate(check_only=True).
        generator.generate(check_only=True)
        self.assertEqual(self._tmp_agents.read_text(encoding="utf-8"), corrupted)

    def test_generate_fixes_real_drift(self) -> None:
        corrupted = self._tmp_agents.read_text(encoding="utf-8").replace("Jules", "SOMEONE ELSE")
        self._tmp_agents.write_text(corrupted, encoding="utf-8")

        results = generator.generate()
        self.assertTrue(any(r.has_drift for r in results))
        fixed_text = self._tmp_agents.read_text(encoding="utf-8")
        self.assertIn("Jules", fixed_text)
        self.assertNotIn("SOMEONE ELSE", fixed_text)

        # And it is now idempotent again.
        second = generator.generate()
        self.assertTrue(all(not r.has_drift for r in second))

    def test_missing_markers_raises_generator_error(self) -> None:
        self._tmp_agents.write_text("# no markers here at all\n", encoding="utf-8")
        with self.assertRaises(generator.GeneratorError):
            generator.check_drift()

    def test_missing_target_file_raises_generator_error(self) -> None:
        self._tmp_agents.unlink()
        with self.assertRaises(generator.GeneratorError):
            generator.check_drift()


class CLITests(unittest.TestCase):
    """Real subprocess invocations of bin/orion against the REAL,
    checked-in .ai/board.yaml/AGENTS.md/.ai/BOARD.md -- read-only
    commands only (validate, generate --check); never `generate`
    without --check here, to avoid any risk of a subprocess writing to
    this session's real working tree."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "orion"), *args],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )

    def test_board_validate(self) -> None:
        result = self._run("board", "validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("luis-aguirre", result.stdout)
        self.assertIn("autoclaw", result.stdout)

    def test_board_generate_check_reports_no_drift_on_real_repo(self) -> None:
        result = self._run("board", "generate", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Sin cambios", result.stdout)


class APIRouteTests(unittest.TestCase):
    def test_roster_route_returns_six_members(self) -> None:
        from orion.board import routes as board_routes

        roster = board_routes.get_roster()
        self.assertEqual(len(roster), 6)
        ids = {m["id"] for m in roster}
        self.assertEqual(ids, {"luis-aguirre", "chatgpt", "claude", "jules", "nemotron", "autoclaw"})
        for m in roster:
            self.assertNotIn("prompt_contents", m)  # never exposes full prompt file contents

    def test_members_route_still_reflects_canonical_seats(self) -> None:
        from orion.board import routes as board_routes

        members = {m["key"]: m for m in board_routes.get_members()}
        self.assertEqual(members["builder"]["board_seat"], "Jules (Lead Software Engineer)")


class RegressionTests(unittest.TestCase):
    """Explicit regression coverage this Mission's own brief demands:
    Gemini stays excluded unless a real ADR adds it, no member was
    silently dropped or duplicated, roles are unchanged, and B-011's
    own pipeline-selection behavior is untouched by any of this."""

    def test_gemini_is_not_an_official_member(self) -> None:
        config = load_board_config()
        ids = {m.id for m in config.members}
        display_names = {m.display_name for m in config.members}
        self.assertNotIn("gemini", ids)
        self.assertNotIn("Gemini", display_names)

    def test_gemini_not_present_in_generated_tables(self) -> None:
        self.assertNotIn("Gemini", generator.AGENTS_MD_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("Gemini", generator.BOARD_MD_PATH.read_text(encoding="utf-8"))

    def test_all_six_previous_members_still_present(self) -> None:
        config = load_board_config()
        ids = {m.id for m in config.members}
        self.assertEqual(len(ids), 6)
        self.assertEqual(
            ids, {"luis-aguirre", "chatgpt", "claude", "jules", "nemotron", "autoclaw"}
        )

    def test_roles_unchanged_from_ai_roles_md(self) -> None:
        expected_roles = {
            "luis-aguirre": "CEO and Product Owner",
            "chatgpt": "Chief AI Architect",
            "claude": "Chief Software Architect",
            "jules": "Lead Software Engineer",
            "nemotron": "Principal Engineering Reviewer",
            "autoclaw": "Operations Engineer",
        }
        config = load_board_config()
        for member_id, expected_role in expected_roles.items():
            self.assertEqual(config.get(member_id).role, expected_role, member_id)

    def test_b011_worked_examples_are_unaffected_by_g012(self) -> None:
        """The exact 3 pipeline examples from B-011's own brief must
        still resolve identically -- G-012 only changed where
        board_seat *labels* come from, never stage routing."""
        from orion.board import board_engine

        feature = board_engine.decide_pipeline("Construye la pagina de Cursos")
        self.assertEqual(feature.stages, ("architect", "builder", "reviewer", "qa", "gitops", "experience"))

        bug = board_engine.decide_pipeline("Arregla el bug de login que falla intermitentemente")
        self.assertEqual(bug.stages, ("builder", "qa", "experience"))

        release = board_engine.decide_pipeline("Lanza el release v0.9.0-beta a produccion")
        self.assertEqual(release.stages, ("reviewer", "gitops", "experience"))

    def test_window_board_page_still_renders(self) -> None:
        import asyncio

        from orion.window.routes import board_page

        class FakeRequest:
            pass

        response = asyncio.run(board_page(FakeRequest()))
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
