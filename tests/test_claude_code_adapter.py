"""Tests for orion.providers.claude_code (BETA 006: Claude Code Live
Invocation).

Standard library unittest only. No test here ever calls the real
Claude Code provider: every subprocess-level test launches a small,
disposable, real executable ("fake CLI") that mimics the parts of the
real `claude` CLI's behavior this adapter depends on -- confirmed
against the actual binary installed in this environment (see
docs/CLAUDE_CODE_ADAPTER.md). The fake CLI is a real subprocess (not a
Python mock), so these tests exercise real process launch, real
stdin/stdout/stderr plumbing, real timeouts, and real process-group
termination -- just never a real AI provider.

Run with:

    python3 -m unittest tests.test_claude_code_adapter -v
"""

from __future__ import annotations

import inspect
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge.models import Mission, MissionStatus
from orion.executor.models import ExecutionStatus
from orion.executor.registry import get_adapter
from orion.prompt_composer import composer as pc_composer
from orion.providers.claude_code import adapter as adapter_module
from orion.providers.claude_code import config as config_module
from orion.providers.claude_code.adapter import ClaudeCodeAdapter
from orion.providers.claude_code.config import ClaudeCodeConfig

FAKE_CLI_SOURCE = '''#!/usr/bin/env python3
import json, os, sys, time

def main():
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "auth" and argv[1] == "status":
        logged_in = os.environ.get("FAKE_CLAUDE_LOGGED_IN", "1") == "1"
        print(json.dumps({"loggedIn": logged_in, "authMethod": "test", "apiProvider": "test"}))
        return 0

    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "success")
    try:
        sys.stdin.read()
    except Exception:
        pass

    if scenario == "success":
        with open("hello.txt", "w", encoding="utf-8") as f:
            f.write("hola desde claude code falso\\n")
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "listo", "num_turns": 1}))
        return 0
    if scenario == "no_changes":
        print(json.dumps({"type": "result", "is_error": False, "result": "sin cambios"}))
        return 0
    if scenario == "provider_error":
        print(json.dumps({"type": "result", "subtype": "error", "is_error": True, "result": "Simulated provider error"}))
        return 1
    if scenario == "nonzero_exit_no_error_flag":
        print(json.dumps({"type": "result", "is_error": False, "result": "exit raro"}))
        return 2
    if scenario == "bad_json":
        sys.stdout.write("esto no es json\\n")
        return 0
    if scenario == "sleep":
        time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP_SECONDS", "30")))
        print(json.dumps({"type": "result", "is_error": False, "result": "desperte"}))
        return 0
    if scenario == "huge_stdout":
        sys.stdout.write("X" * 500000)
        sys.stdout.write(json.dumps({"type": "result", "is_error": False, "result": "ok"}))
        return 0
    if scenario == "huge_stderr":
        sys.stderr.write("E" * 500000)
        print(json.dumps({"type": "result", "is_error": False, "result": "ok"}))
        return 0
    if scenario == "delete_file":
        if os.path.exists("seed.txt"):
            os.remove("seed.txt")
        print(json.dumps({"type": "result", "is_error": False, "result": "eliminado"}))
        return 0
    if scenario == "modify_file":
        with open("seed.txt", "w", encoding="utf-8") as f:
            f.write("contenido modificado\\n")
        print(json.dumps({"type": "result", "is_error": False, "result": "modificado"}))
        return 0
    if scenario == "leak_check":
        secret = os.environ.get("ORION_TEST_FAKE_SECRET", "")
        with open("leak_probe.txt", "w", encoding="utf-8") as f:
            f.write("no deberiamos necesitar escribir el secreto aqui\\n")
        print(json.dumps({"type": "result", "is_error": False, "result": "ok, secreto no citado"}))
        return 0

    print(json.dumps({"type": "result", "is_error": True, "result": f"escenario desconocido: {scenario}"}))
    return 1

if __name__ == "__main__":
    sys.exit(main())
'''


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_package():
    mission = Mission(
        id="MISSION-CLAUDE-CODE-LIVE-TEST",
        title="Claude Code live invocation test mission",
        description="",
        mission_type="executor",
        status=MissionStatus.NEW,
        created_at=_now(),
        updated_at=_now(),
    )
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    package = pc_composer.compose(mission, None, repo_root, all_missions=[mission])
    return package, tmp


class _FakeCliTestCase(unittest.TestCase):
    """Base class: writes a real, disposable fake `claude` executable
    for the duration of each test."""

    def setUp(self) -> None:
        self._fake_dir = tempfile.mkdtemp(prefix="orion-fake-claude-")
        self.fake_cli_path = Path(self._fake_dir) / "fake-claude"
        self.fake_cli_path.write_text(FAKE_CLI_SOURCE, encoding="utf-8")
        self.fake_cli_path.chmod(0o755)
        self._env_overrides: dict[str, str | None] = {}

    def tearDown(self) -> None:
        shutil.rmtree(self._fake_dir, ignore_errors=True)
        for key, original in self._env_overrides.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def _set_env(self, key: str, value: str) -> None:
        if key not in self._env_overrides:
            self._env_overrides[key] = os.environ.get(key)
        os.environ[key] = value

    def _adapter(self, timeout_seconds: int = 30, model: str | None = None) -> ClaudeCodeAdapter:
        return ClaudeCodeAdapter(
            config=ClaudeCodeConfig(cli_path=str(self.fake_cli_path), timeout_seconds=timeout_seconds, model=model)
        )


class RegistrationTests(unittest.TestCase):
    def test_adapter_self_registers_on_import(self) -> None:
        adapter = get_adapter("claude_code")
        self.assertIsInstance(adapter, ClaudeCodeAdapter)


class HealthCheckTests(_FakeCliTestCase):
    def test_missing_binary(self) -> None:
        adapter = ClaudeCodeAdapter(config=ClaudeCodeConfig(cli_path="orion-definitely-not-a-real-binary"))
        health = adapter.health_check()
        self.assertFalse(health.healthy)
        self.assertIn("no se encontro en PATH", health.message)

    def test_healthy_when_fake_cli_reports_logged_in(self) -> None:
        self._set_env("FAKE_CLAUDE_LOGGED_IN", "1")
        adapter = self._adapter()
        health = adapter.health_check()
        self.assertTrue(health.healthy)
        self.assertIn("autenticado", health.message)

    def test_unhealthy_when_fake_cli_reports_logged_out(self) -> None:
        self._set_env("FAKE_CLAUDE_LOGGED_IN", "0")
        adapter = self._adapter()
        health = adapter.health_check()
        self.assertFalse(health.healthy)
        self.assertIn("no hay sesion activa", health.message)


class ExecuteContractTests(_FakeCliTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._set_env("FAKE_CLAUDE_LOGGED_IN", "1")
        self.package, self._pkg_tmp = _make_package()

    def tearDown(self) -> None:
        self._pkg_tmp.cleanup()
        super().tearDown()

    def _run(self, scenario: str, **adapter_kwargs):
        self._set_env("FAKE_CLAUDE_SCENARIO", scenario)
        adapter = self._adapter(**adapter_kwargs)
        return adapter, adapter.execute(self.package)

    def test_execute_creates_a_real_file(self) -> None:
        _, result = self._run("success")
        self.assertEqual(result.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(len(result.artifacts), 1)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.path, "hello.txt")
        self.assertEqual(artifact.change_type, "created")
        self.assertEqual(artifact.content, "hola desde claude code falso\n")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.adapter, "claude_code")

    def test_execute_no_changes_is_still_success(self) -> None:
        _, result = self._run("no_changes")
        self.assertEqual(result.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(result.artifacts, [])

    def test_execute_provider_error_is_failed(self) -> None:
        _, result = self._run("provider_error")
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("Simulated provider error", result.error)
        self.assertEqual(result.exit_code, 1)

    def test_execute_nonzero_exit_without_error_flag_is_still_failed(self) -> None:
        _, result = self._run("nonzero_exit_no_error_flag")
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.exit_code, 2)

    def test_execute_unparseable_output_is_failed(self) -> None:
        _, result = self._run("bad_json")
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("no se pudo interpretar", result.error.lower())

    def test_execute_enforces_its_own_timeout(self) -> None:
        self._set_env("FAKE_CLAUDE_SLEEP_SECONDS", "10")
        start = time.monotonic()
        _, result = self._run("sleep", timeout_seconds=1)
        elapsed = time.monotonic() - start
        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        self.assertLess(elapsed, 8, "el timeout debio cortar el proceso mucho antes que el sleep de 10s")

    def test_execute_cancellation_kills_the_real_process(self) -> None:
        self._set_env("FAKE_CLAUDE_SLEEP_SECONDS", "30")
        self._set_env("FAKE_CLAUDE_SCENARIO", "sleep")
        adapter = self._adapter(timeout_seconds=60)

        result_box: list = []

        def _run_execute():
            result_box.append(adapter.execute(self.package))

        thread = threading.Thread(target=_run_execute)
        start = time.monotonic()
        thread.start()
        # Give the subprocess a moment to actually launch and register
        # its PID before we try to cancel it.
        time.sleep(0.5)
        cancelled = adapter.cancel(self.package.mission.id)
        thread.join(timeout=15)
        elapsed = time.monotonic() - start

        self.assertTrue(cancelled)
        self.assertFalse(thread.is_alive(), "execute() debio terminar poco despues de cancel(), no tras los 30s de sleep")
        self.assertLess(elapsed, 15)
        self.assertEqual(len(result_box), 1)
        self.assertEqual(result_box[0].status, ExecutionStatus.CANCELLED)

    def test_cancel_with_no_active_mission_is_honestly_false(self) -> None:
        adapter = self._adapter()
        self.assertFalse(adapter.cancel("MISSION-NEVER-RAN"))

    def test_execute_huge_stdout_is_bounded(self) -> None:
        _, result = self._run("huge_stdout")
        # The JSON result gets pushed past the capture cap by the huge
        # payload preceding it -- unparseable, and correctly FAILED
        # rather than silently guessing at success.
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertLessEqual(len(result.stdout_excerpt), adapter_module.MAX_EXCERPT_CHARS + 200)

    def test_execute_huge_stderr_is_bounded(self) -> None:
        _, result = self._run("huge_stderr")
        self.assertEqual(result.status, ExecutionStatus.SUCCEEDED)
        self.assertLessEqual(len(result.stderr_excerpt), adapter_module.MAX_EXCERPT_CHARS + 200)

    def test_execute_short_circuits_when_unhealthy(self) -> None:
        adapter = ClaudeCodeAdapter(config=ClaudeCodeConfig(cli_path="orion-definitely-not-a-real-binary"))
        result = adapter.execute(self.package)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("health_check() fallo", result.error)

    def test_max_turns_configured_without_cli_support_is_noted_not_silently_dropped(self) -> None:
        self._set_env("FAKE_CLAUDE_LOGGED_IN", "1")
        self._set_env("FAKE_CLAUDE_SCENARIO", "success")
        adapter = ClaudeCodeAdapter(
            config=ClaudeCodeConfig(cli_path=str(self.fake_cli_path), timeout_seconds=30, max_turns=5)
        )
        result = adapter.execute(self.package)
        self.assertEqual(result.status, ExecutionStatus.SUCCEEDED)
        self.assertIn("MAX_TURNS", result.summary)

    def test_secret_env_value_never_appears_in_result(self) -> None:
        self._set_env("ORION_TEST_FAKE_SECRET", "sk-totally-fake-secret-value-12345")
        _, result = self._run("leak_check")
        blob = " ".join(
            [result.summary, result.error, result.stdout_excerpt, result.stderr_excerpt]
        )
        self.assertNotIn("sk-totally-fake-secret-value-12345", blob)


class SourceGuardTests(unittest.TestCase):
    def test_no_shell_true_anywhere(self) -> None:
        source = inspect.getsource(adapter_module)
        self.assertNotIn("shell=True", source)

    def test_no_network_or_hardcoded_secrets_in_adapter_or_config(self) -> None:
        for module in (adapter_module, config_module):
            source = inspect.getsource(module)
            for forbidden in ("requests", "httpx", "sk-", "api_key=", "Authorization", "Bearer "):
                self.assertNotIn(forbidden, source)


class FileChangeDetectionTests(unittest.TestCase):
    """Direct, subprocess-free tests of the snapshot/diff/artifact
    logic that turns a before/after workspace into ExecutionArtifacts."""

    def setUp(self) -> None:
        self.adapter = ClaudeCodeAdapter(config=ClaudeCodeConfig(cli_path="unused"))
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diff_detects_created_modified_deleted(self) -> None:
        (self.workspace / "unchanged.txt").write_text("same", encoding="utf-8")
        (self.workspace / "to_modify.txt").write_text("before", encoding="utf-8")
        (self.workspace / "to_delete.txt").write_text("bye", encoding="utf-8")
        before = self.adapter._snapshot(self.workspace)

        (self.workspace / "to_modify.txt").write_text("after", encoding="utf-8")
        (self.workspace / "to_delete.txt").unlink()
        (self.workspace / "new_file.txt").write_text("brand new", encoding="utf-8")
        after = self.adapter._snapshot(self.workspace)

        created, modified, deleted = self.adapter._diff(before, after)
        self.assertEqual(created, ["new_file.txt"])
        self.assertEqual(modified, ["to_modify.txt"])
        self.assertEqual(deleted, ["to_delete.txt"])

    def test_build_artifacts_reads_real_content_and_sets_change_type(self) -> None:
        (self.workspace / "created.txt").write_text("hola", encoding="utf-8")
        (self.workspace / "modified.txt").write_text("nuevo", encoding="utf-8")
        artifacts = self.adapter._build_artifacts(
            self.workspace, created=["created.txt"], modified=["modified.txt"], deleted=["gone.txt"]
        )
        by_path = {a.path: a for a in artifacts}
        self.assertEqual(by_path["created.txt"].change_type, "created")
        self.assertEqual(by_path["created.txt"].content, "hola")
        self.assertEqual(by_path["modified.txt"].change_type, "modified")
        self.assertEqual(by_path["gone.txt"].change_type, "deleted")
        self.assertEqual(by_path["gone.txt"].content, "")

    def test_snapshot_excludes_dot_git_and_dot_claude(self) -> None:
        (self.workspace / ".git").mkdir()
        (self.workspace / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
        (self.workspace / ".claude").mkdir()
        (self.workspace / ".claude" / "state.json").write_text("{}", encoding="utf-8")
        (self.workspace / "real.txt").write_text("real", encoding="utf-8")

        snapshot = self.adapter._snapshot(self.workspace)
        self.assertEqual(list(snapshot), ["real.txt"])


class SubprocessMechanicsTests(_FakeCliTestCase):
    """Direct tests of _invoke() against a controlled cwd, decoupled
    from execute()'s own workspace lifecycle -- this is what lets us
    genuinely test deletion/modification of a pre-existing file."""

    def setUp(self) -> None:
        super().setUp()
        self._set_env("FAKE_CLAUDE_LOGGED_IN", "1")
        self._work_tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._work_tmp.name)

    def tearDown(self) -> None:
        self._work_tmp.cleanup()
        super().tearDown()

    def test_invoke_lets_the_real_process_delete_a_file(self) -> None:
        (self.cwd / "seed.txt").write_text("seed", encoding="utf-8")
        self._set_env("FAKE_CLAUDE_SCENARIO", "delete_file")
        adapter = self._adapter()
        before = adapter._snapshot(self.cwd)

        outcome = adapter._invoke(adapter._build_args(), self.cwd, "", "MISSION-INVOKE-DELETE")

        after = adapter._snapshot(self.cwd)
        created, modified, deleted = adapter._diff(before, after)
        self.assertEqual(outcome.returncode, 0)
        self.assertFalse(outcome.timed_out)
        self.assertEqual(deleted, ["seed.txt"])
        self.assertEqual(created, [])
        self.assertEqual(modified, [])

    def test_invoke_lets_the_real_process_modify_a_file(self) -> None:
        (self.cwd / "seed.txt").write_text("contenido original", encoding="utf-8")
        self._set_env("FAKE_CLAUDE_SCENARIO", "modify_file")
        adapter = self._adapter()
        before = adapter._snapshot(self.cwd)

        adapter._invoke(adapter._build_args(), self.cwd, "", "MISSION-INVOKE-MODIFY")

        after = adapter._snapshot(self.cwd)
        created, modified, deleted = adapter._diff(before, after)
        self.assertEqual(modified, ["seed.txt"])
        self.assertEqual((self.cwd / "seed.txt").read_text(encoding="utf-8"), "contenido modificado\n")

    def test_invoke_registers_pid_only_while_active(self) -> None:
        self._set_env("FAKE_CLAUDE_SCENARIO", "sleep")
        self._set_env("FAKE_CLAUDE_SLEEP_SECONDS", "2")
        adapter = self._adapter()
        mission_id = "MISSION-INVOKE-PID"

        outcome_box: list = []

        def _run():
            outcome_box.append(adapter._invoke(adapter._build_args(), self.cwd, "", mission_id))

        thread = threading.Thread(target=_run)
        thread.start()
        time.sleep(0.5)
        with adapter._lock:
            active_during = mission_id in adapter._active_processes
        thread.join(timeout=10)
        with adapter._lock:
            active_after = mission_id in adapter._active_processes

        self.assertTrue(active_during, "el PID debio estar registrado mientras el proceso seguia activo")
        self.assertFalse(active_after, "el estado debio limpiarse al terminar")
        self.assertEqual(len(outcome_box), 1)
        self.assertFalse(outcome_box[0].timed_out)


class ClaudeCodeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys = (
            "ORION_CLAUDE_CODE_BIN",
            "ORION_CLAUDE_CODE_TIMEOUT",
            "ORION_CLAUDE_CODE_MODEL",
            "ORION_CLAUDE_CODE_MAX_TURNS",
        )
        self._originals = {key: os.environ.get(key) for key in self._keys}
        for key in self._keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._originals.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_defaults_when_nothing_set(self) -> None:
        config = ClaudeCodeConfig.from_env()
        self.assertEqual(config.cli_path, "claude")
        self.assertEqual(config.timeout_seconds, 300)
        self.assertIsNone(config.model)
        self.assertIsNone(config.max_turns)

    def test_reads_every_documented_env_var(self) -> None:
        os.environ["ORION_CLAUDE_CODE_BIN"] = "/usr/local/bin/claude"
        os.environ["ORION_CLAUDE_CODE_TIMEOUT"] = "45"
        os.environ["ORION_CLAUDE_CODE_MODEL"] = "sonnet"
        os.environ["ORION_CLAUDE_CODE_MAX_TURNS"] = "8"

        config = ClaudeCodeConfig.from_env()
        self.assertEqual(config.cli_path, "/usr/local/bin/claude")
        self.assertEqual(config.timeout_seconds, 45)
        self.assertEqual(config.model, "sonnet")
        self.assertEqual(config.max_turns, 8)


if __name__ == "__main__":
    unittest.main()
