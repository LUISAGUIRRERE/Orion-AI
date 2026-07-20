"""Tests for orion.providers.claude_code.

Standard library unittest only, no external calls of any kind -- no
real Claude Code SDK/CLI is ever invoked; health_check() is exercised
against whatever (if anything) happens to be on this sandbox's PATH,
and execute() is exercised end to end, confirming it reaches the
documented, deliberately-unimplemented _invoke() boundary and returns
a clean, structured FAILED result rather than raising or crashing.

Run with:

    python3 -m unittest tests.test_claude_code_adapter -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge.models import Mission, MissionStatus
from orion.executor.models import ExecutionStatus
from orion.executor.registry import get_adapter
from orion.prompt_composer import composer as pc_composer
from orion.providers.claude_code.adapter import ClaudeCodeAdapter, ClaudeCodeNotAvailableError
from orion.providers.claude_code.config import ClaudeCodeConfig


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_package():
    mission = Mission(
        id="MISSION-CLAUDE-CODE-TEST",
        title="Claude Code adapter test mission",
        description="",
        mission_type="executor",
        status=MissionStatus.NEW,
        created_at=_now(),
        updated_at=_now(),
    )
    # repo_root doesn't need to be a real git repo for compose(): the
    # discovery step degrades gracefully over a plain empty directory,
    # exactly like it does for any repo missing optional docs.
    import tempfile

    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    package = pc_composer.compose(mission, None, repo_root, all_missions=[mission])
    return package, tmp


class ClaudeCodeAdapterRegistrationTests(unittest.TestCase):
    def test_adapter_self_registers_on_import(self) -> None:
        # orion.providers.claude_code was already imported by the
        # module import above (adapter.py) -- confirms the same
        # import-time registration side effect the deterministic
        # adapter uses.
        adapter = get_adapter("claude_code")
        self.assertIsInstance(adapter, ClaudeCodeAdapter)


class ClaudeCodeAdapterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ClaudeCodeAdapter(config=ClaudeCodeConfig(cli_path="orion-nonexistent-cli-binary"))
        self.package, self._tmp = _make_package()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_health_check_reports_unhealthy_when_binary_missing(self) -> None:
        health = self.adapter.health_check()
        self.assertFalse(health.healthy)
        self.assertIn("no se encontro en PATH", health.message)
        self.assertTrue(health.checked_at)

    def test_health_check_still_reports_unhealthy_when_binary_present(self) -> None:
        # Point cli_path at a binary that genuinely exists on any
        # POSIX system (e.g. 'sh') to prove health_check() doesn't
        # flip to healthy=True just because *some* binary was found --
        # it must stay honest about _invoke() not being implemented.
        adapter = ClaudeCodeAdapter(config=ClaudeCodeConfig(cli_path="sh"))
        health = adapter.health_check()
        self.assertFalse(health.healthy)
        self.assertIn("todavia no invoca al SDK/CLI real", health.message)

    def test_execute_reaches_invoke_boundary_and_fails_cleanly(self) -> None:
        result = self.adapter.execute(self.package)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.mission_id, self.package.mission.id)
        self.assertEqual(result.adapter, "claude_code")
        self.assertIn("_invoke() no esta implementado", result.error)
        self.assertEqual(result.artifacts, [])
        self.assertTrue(result.started_at)
        self.assertTrue(result.finished_at)

    def test_execute_never_raises(self) -> None:
        # Whatever _invoke() does, execute() itself must never let an
        # exception escape -- same contract every adapter must honor,
        # enforced here directly against the real implementation
        # rather than only against orion.executor.services' generic
        # try/except.
        try:
            self.adapter.execute(self.package)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"execute() must never raise, raised {type(exc).__name__}: {exc}")

    def test_invoke_raises_the_documented_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as workspace:
            with self.assertRaises(ClaudeCodeNotAvailableError) as ctx:
                self.adapter._invoke(self.package, Path(workspace))
            self.assertIn("no hay SDK/CLI de Claude Code disponible", str(ctx.exception))

    def test_write_package_persists_real_json(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as workspace:
            workspace_path = Path(workspace)
            self.adapter._write_package(self.package, workspace_path)
            written = workspace_path / "prompt_package.json"
            self.assertTrue(written.is_file())
            data = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(data["mission"]["id"], self.package.mission.id)

    def test_collect_modified_files_reads_real_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as workspace:
            workspace_path = Path(workspace)
            (workspace_path / "output.txt").write_text("hello from claude code", encoding="utf-8")
            artifacts = ClaudeCodeAdapter._collect_modified_files(workspace_path, ["output.txt", "missing.txt"])
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].path, "output.txt")
            self.assertEqual(artifacts[0].content, "hello from claude code")

    def test_cancel_is_honestly_false(self) -> None:
        self.assertFalse(self.adapter.cancel(self.package.mission.id))

    def test_capabilities_documents_the_gap(self) -> None:
        caps = self.adapter.capabilities()
        self.assertEqual(caps.name, "claude_code")
        self.assertFalse(caps.supports_cancel)
        self.assertEqual(caps.max_timeout_seconds, self.adapter._config.timeout_seconds)
        self.assertIn("_invoke", caps.notes)

    def test_config_reads_only_env_var_names_never_secrets(self) -> None:
        # Structural guard, same pattern as
        # test_executor.test_no_network_or_credentials_used: the
        # config/adapter source must never contain a literal secret,
        # only environment-variable *names*.
        import inspect

        from orion.providers.claude_code import adapter as adapter_module
        from orion.providers.claude_code import config as config_module

        for module in (adapter_module, config_module):
            source = inspect.getsource(module)
            for forbidden in ("requests", "httpx", "sk-", "api_key=", "Authorization", "Bearer "):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
