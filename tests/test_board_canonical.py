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

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    # --- G-012 REMEDIATION (HIGH #4) hardening -------------------------

    def test_boolean_schema_version_rejected(self) -> None:
        """bool is a subclass of int in Python -- isinstance(True, int)
        is True. schema_version: true must be rejected explicitly, not
        silently accepted as version 1 (it would compare equal to 1)."""
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([VALID_MINIMAL_MEMBER], schema_version=True))

    def test_boolean_board_version_rejected(self) -> None:
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([VALID_MINIMAL_MEMBER], board_version=False))

    def test_non_string_id_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, id=42)
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_non_string_display_name_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, display_name=["not", "a", "string"])
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_non_string_role_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, role=123)
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_unknown_top_level_key_rejected(self) -> None:
        data = _config([VALID_MINIMAL_MEMBER])
        data["unexpected_extra_key"] = "surprise"
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(data)

    def test_unknown_member_key_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, unexpected_field="surprise")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_absolute_documentation_path_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, documentation_path="/etc/passwd")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]), repo_root=REPO_ROOT)

    def test_path_traversal_in_documentation_path_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, documentation_path="../../../../etc/passwd")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]), repo_root=REPO_ROOT)

    def test_traversal_that_stays_inside_repo_root_but_looks_suspicious_is_still_checked_for_existence(self) -> None:
        # ".." that resolves back inside the repo is not a traversal
        # *escape*, but the resulting path must still actually exist.
        bad = dict(VALID_MINIMAL_MEMBER, documentation_path="agents/../agents/does-not-exist.md")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]), repo_root=REPO_ROOT)

    def test_self_supersede_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, supersedes="x")
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))

    def test_non_string_supersedes_rejected(self) -> None:
        bad = dict(VALID_MINIMAL_MEMBER, supersedes=123)
        with self.assertRaises(BoardConfigurationError):
            parse_and_validate(_config([bad]))


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

    def test_every_pipeline_stage_seat_reference_resolves_in_canonical_source(self) -> None:
        """Consistency check between the two, deliberately-separated
        layers Codex asked for: B-011's static pipeline templates
        (board_seat_member_ids) and G-012's canonical roster
        (.ai/board.yaml). Every id a pipeline stage references must
        actually exist as a real member -- otherwise every call would
        silently resolve to an 'unavailable' error state instead of a
        real label."""
        from orion.board.member_registry import MEMBERS

        config = load_board_config()
        known_ids = {m.id for m in config.members}
        for key, template in MEMBERS.items():
            for member_id in template.board_seat_member_ids:
                self.assertIn(member_id, known_ids, f"{key} references unknown canonical id '{member_id}'")

    def test_qa_and_experience_have_no_board_seat_regression(self) -> None:
        from orion.board import member_registry

        self.assertIsNone(member_registry.get_member("qa").board_seat)
        self.assertIsNone(member_registry.get_member("experience").board_seat)

    def test_no_import_time_snapshot_exists(self) -> None:
        """G-012 REMEDIATION (HIGH #2): there must be no module-level
        cache resolved once at import time. Reloading the module twice
        in a row must not require any special reset step -- there is
        nothing cached to reset."""
        import orion.board.member_registry as mr

        self.assertFalse(hasattr(mr, "_CANONICAL_BOARD"), "no import-time snapshot may exist")

    def test_resolution_failure_never_fabricates_an_identity(self) -> None:
        """G-012 REMEDIATION (HIGH #1): when board.yaml cannot be
        loaded, board_seat must be None and board_seat_error must hold
        the real error -- never a hardcoded name/role standing in for
        real data."""
        original_loader = canonical.load_board_config

        def _boom(*a, **kw):
            raise BoardConfigurationError("simulated corrupt board.yaml")

        canonical.load_board_config = _boom
        try:
            from orion.board import member_registry as mr

            builder = mr.get_member("builder")
            self.assertIsNone(builder.board_seat)
            self.assertIn("simulated corrupt board.yaml", builder.board_seat_error)

            architect = mr.get_member("architect")
            self.assertIsNone(architect.board_seat)
            self.assertIn("simulated corrupt board.yaml", architect.board_seat_error)

            # QA/Experience have no dedicated seat by design -- this is
            # NOT a resolution failure, so no error should be reported.
            qa = mr.get_member("qa")
            self.assertIsNone(qa.board_seat)
            self.assertIsNone(qa.board_seat_error)
        finally:
            canonical.load_board_config = original_loader

    def test_resolution_reflects_current_file_state_every_call_no_caching(self) -> None:
        """G-012 REMEDIATION (HIGH #2): two consecutive calls must each
        independently query the canonical source -- proven by swapping
        the loader between calls and observing the change take effect
        immediately, with no stale value surviving from the first
        call."""
        from orion.board import member_registry as mr

        original_loader = canonical.load_board_config

        # First call: real config, seat should resolve normally.
        self.assertIsNotNone(mr.get_member("builder").board_seat)

        # Second call: loader now fails -- must be reflected immediately.
        canonical.load_board_config = lambda *a, **kw: (_ for _ in ()).throw(
            BoardConfigurationError("swapped mid-run")
        )
        try:
            broken = mr.get_member("builder")
            self.assertIsNone(broken.board_seat)
            self.assertIn("swapped mid-run", broken.board_seat_error)
        finally:
            canonical.load_board_config = original_loader

        # Third call: loader restored -- must resolve again immediately.
        restored = mr.get_member("builder")
        self.assertEqual(restored.board_seat, "Jules (Lead Software Engineer)")
        self.assertIsNone(restored.board_seat_error)

    def test_real_values_match_canonical_after_all_the_above(self) -> None:
        """Regression: after the failure-simulation tests above swap
        and restore the loader, the real values must still come back
        exactly matching .ai/board.yaml's own seat_label() output."""
        from orion.board import member_registry as mr

        config = load_board_config()
        self.assertEqual(mr.get_member("builder").board_seat, config.get("jules").seat_label())
        self.assertEqual(mr.get_member("reviewer").board_seat, config.get("nemotron").seat_label())
        self.assertEqual(mr.get_member("gitops").board_seat, config.get("autoclaw").seat_label())
        expected_architect = f"{config.get('chatgpt').seat_label()} / {config.get('claude').seat_label()}"
        self.assertEqual(mr.get_member("architect").board_seat, expected_architect)

    def test_members_dict_holds_static_templates_not_resolved_seats(self) -> None:
        """MEMBERS (the backward-compatible dict) must hold the static
        pipeline templates -- never a resolved, potentially-stale
        board_seat. Only get_member()/list_members() resolve seats,
        and only fresh, every call."""
        from orion.board.member_registry import MEMBERS

        for key, template in MEMBERS.items():
            self.assertIsNone(template.board_seat, f"MEMBERS['{key}'] must not hold a resolved seat")
            self.assertIsNone(template.board_seat_error)


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

    def test_write_is_atomic_no_leftover_temp_files(self) -> None:
        """G-012 REMEDIATION (HIGH #3): writes go through a temp file
        in the same directory + os.replace(); no stray .tmp file may
        remain after a successful generate()."""
        corrupted = self._tmp_agents.read_text(encoding="utf-8").replace("Jules", "SOMEONE ELSE")
        self._tmp_agents.write_text(corrupted, encoding="utf-8")

        generator.generate()

        siblings = list(self._tmp_agents.parent.iterdir())
        leftover_temp_files = [p for p in siblings if p.name.startswith(f".{self._tmp_agents.name}.") and p.name.endswith(".tmp")]
        self.assertEqual(leftover_temp_files, [], leftover_temp_files)

    def test_generated_table_escapes_pipe_and_newline_in_member_fields(self) -> None:
        """G-012 REMEDIATION (HIGH #4): a display_name/role/
        responsibility containing a literal '|' or a newline must not
        be able to corrupt the generated Markdown table's structure."""
        from orion.board.canonical import BoardConfiguration, CanonicalBoardMember

        member = CanonicalBoardMember(
            id="x",
            display_name="Weird | Name",
            role="Ro|le\nwith a newline",
            status="active",
            responsibilities=("Resp | onsibility",),
            restrictions=(),
            capabilities=(),
            documentation_path=None,
            supersedes=None,
        )
        config = BoardConfiguration(schema_version=1, board_version=1, members=(member,))

        table = generator._format_agents_table(config)
        data_rows = [
            line for line in table.splitlines()
            if line.startswith("|") and "Weird" in line
        ]
        self.assertEqual(len(data_rows), 1)
        row = data_rows[0]
        # Exactly 4 real (unescaped) cell-separator pipes plus the two
        # bounding pipes = 5 total '|' characters that are NOT preceded
        # by a backslash; every other '|' must be escaped.
        unescaped_pipes = sum(
            1 for i, ch in enumerate(row) if ch == "|" and (i == 0 or row[i - 1] != "\\")
        )
        self.assertEqual(unescaped_pipes, 5, row)
        self.assertNotIn("\n", row)


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
