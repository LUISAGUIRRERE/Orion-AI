"""TaskRunner — executes a mission's actual work inside a prepared
Workspace.

Sprint 008 does not introduce a second way to "do the work": it reuses
the Builder's existing handler registry (Sprint 006) exactly as
before. The only difference is that the handler now writes its
artifacts while the repository is checked out on the mission's own
branch, so what it produces becomes real, committable file changes
instead of untracked scratch output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion.agents.builder import registry
from orion.agents.builder.handlers import HandlerResult
from orion.bridge import storage as bridge_storage
from orion.bridge.models import Mission


@dataclass
class TaskResult:
    """What the mission's handler produced, as repo-relative paths."""

    handler_result: HandlerResult
    files: list[str] = field(default_factory=list)


def execute(mission: Mission) -> TaskResult:
    """Run the mission's registered handler and report what it wrote."""
    handler = registry.get_handler(mission.mission_type)
    artifacts_dir = bridge_storage.mission_dir(mission.id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result = handler.run(mission, artifacts_dir)
    files = [
        str((artifacts_dir / name).relative_to(bridge_storage.REPO_ROOT))
        for name in result.artifacts
    ]
    return TaskResult(handler_result=result, files=files)
