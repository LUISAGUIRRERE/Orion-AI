"""Public entry point for the Prompt Composer.

This is the only function the rest of ORION (today: the Builder
Agent) should call. It resolves a mission's project and repository
exactly the way orion.execution.pipeline already resolves them for
the Execution Pipeline (Sprint 009 + ORION ALPHA 001's repo_root fix),
so a PromptPackage always describes the same repository the mission
will actually be executed against -- then delegates the real
discovery/composition work to composer.py and persists the result.
"""

from __future__ import annotations

from pathlib import Path

from orion.bridge import services as bridge_services
from orion.bridge.models import Mission
from orion.execution import git_manager
from orion.projects import registry as project_registry
from orion.prompt_composer import composer, storage
from orion.prompt_composer.models import PromptPackage


def compose_for_mission(mission: Mission) -> PromptPackage:
    """Build and persist the PromptPackage for a single mission."""
    project = project_registry.get_project(mission.project_id) if mission.project_id else None
    repo_root = Path(project.local_path) if project and project.local_path else git_manager.REPO_ROOT
    all_missions = bridge_services.list_missions()

    package = composer.compose(mission, project, repo_root, all_missions=all_missions)
    storage.save(mission.id, package)
    return package
