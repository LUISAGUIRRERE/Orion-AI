"""TaskRunner — executes a mission's actual work inside a prepared
Workspace.

Sprint 008 does not introduce a second way to "do the work": it reuses
the Builder's existing handler registry (Sprint 006) exactly as
before. The only difference is that the handler now writes its
artifacts while the repository is checked out on the mission's own
branch, so what it produces becomes real, committable file changes
instead of untracked scratch output.

ORION ALPHA 001 addition: ``repo_root`` lets a mission's handler write
into a real external project's own clone instead of always into
Orion-AI's own workspace. When a mission also sets ``artifact_path``
(e.g. "docs/ARCHITECTURE.md"), the handler's single output file is
relocated there after it runs — the Handler interface itself
(``MissionHandler.run``) is untouched, so this stays a TaskRunner-only
change, not a Builder change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orion.agents.builder import registry
from orion.agents.builder.handlers import HandlerResult
from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission


@dataclass
class TaskResult:
    """What the mission's handler produced, as repo-relative paths."""

    handler_result: HandlerResult
    files: list[str] = field(default_factory=list)


def execute(mission: Mission, repo_root: Path | None = None) -> TaskResult:
    """Run the mission's registered handler and report what it wrote.

    ``repo_root`` defaults to Orion-AI's own repository (Sprint 008
    behavior, unchanged). When a mission belongs to a project with its
    own clone, Pipeline passes that project's repo_root instead.
    """
    if repo_root is None:
        repo_root = bridge_storage.REPO_ROOT

    handler = registry.get_handler(mission.mission_type)
    external_project = repo_root != bridge_storage.REPO_ROOT

    if external_project:
        # Keep ORION's own scratch area clearly labeled and out of the
        # way inside the target repository; relocated below if the
        # mission asked for a specific final path.
        artifacts_dir = repo_root / ".orion-scratch" / mission.id
    else:
        artifacts_dir = bridge_storage.mission_dir(mission.id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result = handler.run(mission, artifacts_dir)

    if external_project and mission.artifact_path:
        produced = artifacts_dir / result.artifacts[0]
        target = repo_root / mission.artifact_path
        target.parent.mkdir(parents=True, exist_ok=True)
        produced.replace(target)
        files = [str(target.relative_to(repo_root))]
        try:
            artifacts_dir.rmdir()
        except OSError:
            pass
    else:
        files = [
            str((artifacts_dir / name).relative_to(repo_root))
            for name in result.artifacts
        ]

    return TaskResult(handler_result=result, files=files)
