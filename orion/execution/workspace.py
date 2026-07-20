"""Workspace — isolates one mission's work within the repository.

ORION does not clone a separate working copy per mission; this
environment has a single checkout. "Isolation" here means: refuse to
start a mission's work on top of another mission's leftovers (the
repository must be clean and on the base branch first), track every
file the mission touches, and always return the checkout to the base
branch when done — success or failure — so the next mission always
starts clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orion.execution import git_manager

# Command Bridge and agent runtime data: naturally untracked/mutating
# outside of any pipeline run, and not "contamination" the way an
# uncommitted change to a tracked source file would be. Listed
# explicitly rather than relying solely on .gitignore, since the base
# branch's committed .gitignore may lag behind (e.g. right before this
# Sprint's own change to it is merged).
RUNTIME_PATHS: tuple[str, ...] = (
    "workspace/missions/",
    "workspace/builder_state.yaml",
    "workspace/coo_state.yaml",
    "workspace/execution_state.yaml",
    "workspace/events.db",
    # Sprint 009 (Multi Project Engine): the Project Registry's own
    # data (workspace/companies/), for the same reason as
    # workspace/missions/ above — it is written by normal Bridge/
    # Registry operation before the Pipeline ever runs (e.g. seeding
    # the example companies on startup), not by this mission's own
    # work, and GitManager.commit() only ever stages the explicit
    # deliverable files a handler produced, never this directory.
    "workspace/companies/",
)


class WorkspaceError(RuntimeError):
    """Raised when a workspace cannot be safely prepared or is left dirty."""


@dataclass
class Workspace:
    """A single mission's isolated slice of the repository."""

    mission_id: str
    base_branch: str = "main"
    files: list[str] = field(default_factory=list)

    def prepare(self) -> None:
        """Check out the base branch and verify the tree is clean.

        Raises WorkspaceError instead of touching anything if the
        repository is dirty — never assumes it is safe to discard
        whatever is there.
        """
        git_manager.checkout(self.base_branch)
        if not git_manager.is_clean(exclude=list(RUNTIME_PATHS)):
            raise WorkspaceError(
                f"El repositorio tiene cambios sin confirmar en '{self.base_branch}'; "
                f"no se puede preparar un Workspace limpio para {self.mission_id}."
            )

    def track(self, path: str) -> None:
        """Record a file this mission created or modified."""
        self.files.append(path)

    def cleanup(self) -> None:
        """Return the checkout to the base branch, leaving no trace."""
        git_manager.checkout(self.base_branch)
