"""Tests for orion.executor.

Standard library unittest only (no pytest, no new dependency). No
external calls of any kind: every adapter used here is a local,
in-process test double -- including the ones that simulate a timeout
or a crash -- and every "repository" is a real, disposable git repo
under a TemporaryDirectory. Never touches Orion-AI's own working tree
or any real project.

Run with:

    python3 -m unittest tests.test_executor -v
"""

from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission, MissionStatus
from orion.execution import task_runner
from orion.executor.models import ExecutionArtifact, ExecutionRequest, ExecutionResult, ExecutionStatus
from orion.executor.registry import get_adapter, register_adapter
from orion.executor.services import ExecutorError, _resolve_adapter_name, run_for_mission
from orion.prompt_composer import composer as pc_composer
from orion.prompt_composer import storage as pc_storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_mission(**overrides: object) -> Mission:
    defaults: dict[str, object] = dict(
        id="MISSION-EXECUTOR-TEST",
        title="Executor test mission",
        description="",
        mission_type="executor",
        status=MissionStatus.NEW,
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Mission(**defaults)  # type: ignore[arg-type]


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True)


class _SlowAdapter:
    """Deliberately sleeps longer than the test's timeout -- proves
    the Executor enforces its timeout rather than trusting the adapter
    to respect it."""

    name = "test_slow"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        time.sleep(2)
        return ExecutionResult(
            mission_id=request.mission_id, adapter=self.name, status=ExecutionStatus.SUCCEEDED
        )


class _CrashingAdapter:
    """Always raises -- proves adapter exceptions are captured
    structurally instead of propagating raw."""

    name = "test_crashing"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise ValueError("simulated adapter failure, never a real provider error")


class _EchoAdapter:
    """Deterministic, minimal adapter used to check the artifact
    write-through path without depending on the built-in adapter's
    exact wording."""

    name = "test_echo"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            mission_id=request.mission_id,
            adapter=self.name,
            status=ExecutionStatus.SUCCEEDED,
            artifacts=[ExecutionArtifact(path="echo.txt", content="echoed", description="test")],
            summary="echoed ok",
        )


register_adapter(_SlowAdapter())
register_adapter(_CrashingAdapter())
register_adapter(_EchoAdapter())


class ExecutorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        _init_repo(self.repo_root)
        self._cleanup_mission_ids: list[str] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for mission_id in self._cleanup_mission_ids:
            mission_dir = bridge_storage.mission_dir(mission_id)
            if mission_dir.exists():
                import shutil

                shutil.rmtree(mission_dir, ignore_errors=True)

    def _prepare(self, mission: Mission) -> None:
        """Compose and persist a real PromptPackage, exactly what the
        Builder does before task_runner.execute() ever runs -- the
        Executor must never be exercised without this having happened
        first, so every test goes through it too."""
        package = pc_composer.compose(mission, None, self.repo_root, all_missions=[mission])
        pc_storage.save(mission.id, package)
        self._cleanup_mission_ids.append(mission.id)

    def test_deterministic_adapter_is_the_default(self) -> None:
        mission = _make_mission()
        self.assertEqual(_resolve_adapter_name(mission), "deterministic_local")

    def test_adapter_tag_overrides_the_default(self) -> None:
        mission = _make_mission(tags=["adapter:test_echo"])
        self.assertEqual(_resolve_adapter_name(mission), "test_echo")

    def test_missing_prompt_package_is_a_hard_failure(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-NO-PACKAGE")
        with self.assertRaises(ExecutorError):
            run_for_mission(mission, self.repo_root)

    def test_unknown_adapter_is_a_hard_failure(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-UNKNOWN", tags=["adapter:nope_not_real"])
        self._prepare(mission)
        with self.assertRaises(ExecutorError):
            run_for_mission(mission, self.repo_root)

    def test_successful_execution_writes_real_files(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-ECHO", tags=["adapter:test_echo"])
        self._prepare(mission)
        files, summary = run_for_mission(mission, self.repo_root)
        self.assertEqual(files, ["echo.txt"])
        self.assertEqual((self.repo_root / "echo.txt").read_text(encoding="utf-8"), "echoed")
        self.assertEqual(summary, "echoed ok")

    def test_deterministic_adapter_via_task_runner(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-DETERMINISTIC")
        self._prepare(mission)
        result = task_runner.execute(mission, repo_root=self.repo_root)
        self.assertEqual(result.files, [f"execution-log/{mission.id}.md"])
        content = (self.repo_root / result.files[0]).read_text(encoding="utf-8")
        self.assertIn("NO fue generado por un proveedor de IA real", content)

    def test_crashing_adapter_is_captured_structurally(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-CRASH", tags=["adapter:test_crashing"])
        self._prepare(mission)
        with self.assertRaises(ExecutorError) as ctx:
            run_for_mission(mission, self.repo_root)
        self.assertIn("simulated adapter failure", str(ctx.exception))

        from orion.executor import storage as exec_storage

        result = exec_storage.load_result(mission.id)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("simulated adapter failure", result.error)

    def test_slow_adapter_times_out(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-TIMEOUT", tags=["adapter:test_slow"])
        self._prepare(mission)

        import orion.executor.services as executor_services

        original_timeout = executor_services.DEFAULT_TIMEOUT_SECONDS
        executor_services.DEFAULT_TIMEOUT_SECONDS = 1
        try:
            with self.assertRaises(ExecutorError) as ctx:
                run_for_mission(mission, self.repo_root)
        finally:
            executor_services.DEFAULT_TIMEOUT_SECONDS = original_timeout

        self.assertIn("no respondio dentro de", str(ctx.exception))

        from orion.executor import storage as exec_storage

        result = exec_storage.load_result(mission.id)
        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)

    def test_events_recorded_on_success(self) -> None:
        mission = _make_mission(id="MISSION-EXECUTOR-EVENTS")
        self._prepare(mission)
        run_for_mission(mission, self.repo_root)
        # The mission itself was never persisted via bridge_services.create_mission
        # in this test (only the PromptPackage/mission object were built in
        # memory) — record_event still writes to workspace/missions/<id>/events.yaml
        # regardless of whether mission.yaml exists there, so this checks that
        # file directly rather than going through get_events (which requires
        # a persisted Mission).
        events_path = bridge_storage.mission_dir(mission.id) / "events.yaml"
        self.assertTrue(events_path.is_file())
        import yaml

        events = yaml.safe_load(events_path.read_text(encoding="utf-8"))
        event_types = [e["type"] for e in events]
        self.assertIn("execution_requested", event_types)
        self.assertIn("execution_started", event_types)
        self.assertIn("execution_completed", event_types)

    def test_no_network_or_credentials_used(self) -> None:
        # Structural guard: the deterministic adapter's module must not
        # import anything network- or credential-related. A simple,
        # honest proxy: its source contains none of these tokens.
        import inspect

        from orion.executor.adapters import deterministic

        source = inspect.getsource(deterministic)
        for forbidden in ("requests", "httpx", "urllib", "socket", "api_key", "API_KEY", "Authorization"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
