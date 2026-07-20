"""The Autonomous Execution Pipeline.

Carries an assigned mission from "Builder took it" to "Pull Request
ready": prepares a Workspace, creates a mission branch, runs the
mission's existing handler through TaskRunner, validates the result,
and only if validation passes, commits and pushes it. Every step is
recorded on the Mission Framework's own event log, and the repository
checkout always ends back on ``main`` — success or failure — so the
next mission always starts clean.

This module never runs git directly (see git_manager.py) and never
decides what a mission's work actually is (see task_runner.py). Its
only job is the lifecycle around that work.

The Pipeline's own operational status (ExecutionState) is persisted to
``workspace/execution_state.yaml``, for the same reason BuilderState
and COOState are: it may be invoked from a subprocess separate from
the web server, and The Window reads it from the server process.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from orion.bridge import services as bridge_services
from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission
from orion.execution import git_manager, task_runner, validation
from orion.execution.git_manager import GitManagerError
from orion.execution.workspace import Workspace, WorkspaceError
from orion.projects import registry as project_registry

AUTHOR = "Pipeline"
STATE_FILE: Path = bridge_storage.WORKSPACE_DIR / "execution_state.yaml"


@dataclass
class ExecutionState:
    """The Pipeline's current operational status, surfaced to The Window."""

    workspace: str | None = None
    current_branch: str = "main"
    current_commit: str | None = None
    validation_status: str = "idle"
    repository_status: str = "clean"
    last_push: str | None = None
    pull_request: str | None = None


@dataclass
class PipelineResult:
    """What running the Pipeline for one mission produced.

    ``handler_result`` is passed through so the Builder can keep
    recording its own ``artifact_created`` events exactly as it did
    before this Sprint — the Pipeline does not duplicate that
    reporting, it only adds the git lifecycle around it.
    """

    success: bool
    message: str
    handler_result: Any = None
    branch: str | None = None
    commit_hash: str | None = None
    pull_request: str | None = None


def _load_state() -> ExecutionState:
    if not STATE_FILE.exists():
        return ExecutionState()
    with STATE_FILE.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    return ExecutionState(**{**asdict(ExecutionState()), **data})


def _save_state(state: ExecutionState) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(asdict(state), fh)


def get_state() -> ExecutionState:
    """Return the Pipeline's current, persisted state."""
    return _load_state()


def _outcome_path(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "execution.yaml"


def _write_outcome(mission_id: str, outcome: dict[str, Any]) -> None:
    path = _outcome_path(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(outcome, fh, allow_unicode=True, sort_keys=False)


def get_outcome(mission_id: str) -> dict[str, Any] | None:
    """Return the recorded execution outcome for a mission, if any."""
    path = _outcome_path(mission_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_outcomes() -> list[dict[str, Any]]:
    """Every recorded execution outcome across all missions, oldest first."""
    outcomes = []
    for mission_id in bridge_storage.list_mission_ids():
        outcome = get_outcome(mission_id)
        if outcome is not None:
            outcomes.append(outcome)
    outcomes.sort(key=lambda o: o.get("finished_at") or "")
    return outcomes


def _discard_files(files: list[str], repo_root: Path) -> None:
    """Remove exactly the files a failed mission just created.

    Deliberately not ``git clean -fd``: only the specific paths
    TaskRunner reported are touched, nothing else in the tree.
    """
    for rel_path in files:
        path = repo_root / rel_path
        if path.is_file():
            path.unlink()


def run(mission: Mission) -> PipelineResult:
    """Run the full pipeline for a mission the Builder has taken.

    Always restores the repository to ``main`` before returning,
    whatever the outcome, and always writes a terminal execution
    outcome for the mission — never leaves it undocumented.
    """
    # Sprint 009 (Multi Project Engine): namespace the branch by
    # project when the mission has one, so missions from different
    # projects can never collide on the same branch name even while
    # they share this environment's single physical repository. A
    # mission with no project_id keeps the exact Sprint 008 branch
    # format — zero behavior change for pre-Sprint-009 missions.
    project = project_registry.get_project(mission.project_id) if mission.project_id else None
    branch = f"mission/{mission.project_id}/{mission.id}" if mission.project_id else f"mission/{mission.id}"
    # ORION ALPHA 001: a project with its own local clone (see
    # orion/projects/models.py Project.local_path) makes every git
    # operation below run against that repository instead of
    # Orion-AI's own — the entire rest of this function is unchanged
    # either way. No project, or a project with no local_path yet,
    # keeps the exact Sprint 008 behavior (Orion-AI's own repo_root).
    repo_root = Path(project.local_path) if project and project.local_path else git_manager.REPO_ROOT
    base_branch = project.default_branch if project else "main"
    state = _load_state()
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    outcome: dict[str, Any] = {
        "mission_id": mission.id,
        "project_id": mission.project_id or None,
        "branch": branch,
        "commit_hash": None,
        "files_created": [],
        "files_modified": [],
        "tests_executed": [],
        "validation": "not_run",
        "result": "FAILED",
        "execution_seconds": 0.0,
        "pull_request": None,
        "started_at": started_at,
        "finished_at": None,
    }

    def _finish(result: PipelineResult, validation_status: str, repo_status: str) -> PipelineResult:
        outcome["validation"] = validation_status
        outcome["result"] = "REVIEW" if result.success else "FAILED"
        outcome["execution_seconds"] = round(time.monotonic() - started_monotonic, 3)
        outcome["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        outcome["commit_hash"] = result.commit_hash
        outcome["pull_request"] = result.pull_request
        _write_outcome(mission.id, outcome)

        state.workspace = None
        state.current_branch = base_branch
        state.validation_status = validation_status
        state.repository_status = repo_status
        _save_state(state)
        return result

    # 1. Workspace
    workspace = Workspace(mission_id=mission.id, base_branch=base_branch, repo_root=repo_root)
    state.workspace = mission.id
    state.repository_status = "preparing"
    _save_state(state)
    bridge_services.record_event(
        mission.id, "workspace_created", f"Workspace preparado para {mission.id}.", AUTHOR
    )

    if project is not None:
        bridge_services.record_event(
            mission.id,
            "project_loaded",
            f"Proyecto '{project.name}' cargado (repositorio: {project.repository or '-'}, "
            f"branch base: {project.default_branch}).",
            AUTHOR,
        )

    try:
        workspace.prepare()
    except WorkspaceError as exc:
        bridge_services.record_event(mission.id, "execution_finished", str(exc), AUTHOR)
        return _finish(
            PipelineResult(success=False, message=str(exc)), "not_run", "dirty"
        )

    # 2. Branch
    try:
        git_manager.create_branch(branch, base=base_branch, repo_root=repo_root)
    except GitManagerError as exc:
        workspace.cleanup()
        bridge_services.record_event(mission.id, "execution_finished", str(exc), AUTHOR)
        return _finish(
            PipelineResult(success=False, message=str(exc)), "not_run", "clean"
        )

    state.current_branch = branch
    _save_state(state)
    bridge_services.record_event(mission.id, "branch_created", f"Rama '{branch}' creada.", AUTHOR)

    # 3. Execute the mission's actual work
    bridge_services.record_event(mission.id, "execution_started", "Ejecucion del trabajo iniciada.", AUTHOR)
    try:
        task_result = task_runner.execute(mission, repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001 - any handler failure must fail the mission cleanly
        bridge_services.record_event(mission.id, "execution_finished", f"Fallo la ejecucion: {exc}", AUTHOR)
        workspace.cleanup()
        return _finish(
            PipelineResult(success=False, message=str(exc)), "not_run", "clean"
        )

    for path in task_result.files:
        workspace.track(path)
    outcome["files_created"] = list(task_result.files)
    bridge_services.record_event(mission.id, "execution_finished", "Ejecucion del trabajo finalizada.", AUTHOR)

    # 4. Validate
    state.validation_status = "running"
    _save_state(state)
    bridge_services.record_event(mission.id, "validation_started", "Validaciones iniciadas.", AUTHOR)
    validation_result = validation.run(task_result.files)

    if not validation_result.passed:
        bridge_services.record_event(
            mission.id, "validation_failed", "; ".join(validation_result.errors), AUTHOR
        )
        _discard_files(task_result.files, repo_root)
        workspace.cleanup()
        return _finish(
            PipelineResult(
                success=False,
                message="Validacion fallida: " + "; ".join(validation_result.errors),
                handler_result=task_result.handler_result,
            ),
            "failed",
            "clean",
        )

    bridge_services.record_event(mission.id, "validation_passed", "Validaciones superadas.", AUTHOR)

    # 5. Commit — only the deliverable files, never the Bridge's own
    # operational data (see GitManager.commit's docstring).
    try:
        commit_hash = git_manager.commit(
            f"feat: mission {mission.id} — {mission.title}",
            paths=task_result.files,
            repo_root=repo_root,
        )
    except GitManagerError as exc:
        _discard_files(task_result.files, repo_root)
        workspace.cleanup()
        bridge_services.record_event(mission.id, "execution_finished", f"Fallo el commit: {exc}", AUTHOR)
        return _finish(
            PipelineResult(success=False, message=str(exc), handler_result=task_result.handler_result),
            "passed",
            "clean",
        )

    state.current_commit = commit_hash
    _save_state(state)
    bridge_services.record_event(mission.id, "commit_created", f"Commit {commit_hash[:12]} creado.", AUTHOR)

    # 6. Push
    try:
        git_manager.push(branch, repo_root=repo_root)
    except GitManagerError as exc:
        workspace.cleanup()
        bridge_services.record_event(mission.id, "execution_finished", f"Fallo el push: {exc}", AUTHOR)
        return _finish(
            PipelineResult(
                success=False,
                message=str(exc),
                handler_result=task_result.handler_result,
                commit_hash=commit_hash,
            ),
            "passed",
            "clean",
        )

    # Return to main immediately after a successful push, before any
    # further Mission Framework bookkeeping — the mission branch must
    # be left exactly as pushed, never dirtied again afterwards.
    workspace.cleanup()

    push_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.last_push = push_time
    _save_state(state)
    bridge_services.record_event(mission.id, "push_completed", f"Rama '{branch}' publicada.", AUTHOR)

    # 7. Pull Request (URL only — api.github.com is unreachable here)
    pr_url = git_manager.pull_request_url(branch, repo_root=repo_root)
    state.pull_request = pr_url
    _save_state(state)
    bridge_services.record_event(mission.id, "pr_ready", pr_url, AUTHOR)

    if project is not None:
        bridge_services.record_event(
            mission.id,
            "project_completed",
            f"Trabajo del proyecto '{project.name}' completado para la mision {mission.id}.",
            AUTHOR,
        )

    return _finish(
        PipelineResult(
            success=True,
            message="Pipeline completado.",
            handler_result=task_result.handler_result,
            branch=branch,
            commit_hash=commit_hash,
            pull_request=pr_url,
        ),
        "passed",
        "clean",
    )
