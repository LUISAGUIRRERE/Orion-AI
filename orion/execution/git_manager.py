"""GitManager — the only module allowed to run git commands for ORION's
Execution Pipeline.

No other module (Workspace, TaskRunner, Pipeline itself) may invoke
git directly. Every operation here is safe and reversible: no
``git reset --hard``, no ``git clean -fd``, no ``git push --force``,
no forced checkout. A failed git command always raises
``GitManagerError`` instead of being swallowed, so the Pipeline can
always tell "nothing to do" apart from "something went wrong".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from orion.bridge import storage as bridge_storage

REPO_ROOT: Path = bridge_storage.REPO_ROOT


class GitManagerError(RuntimeError):
    """Raised when a git operation fails."""


def _run(*args: str) -> str:
    """Run a git command against the repository root and return stdout.

    Raises GitManagerError with the command's stderr on any non-zero
    exit code. Never uses shell=True, never accepts a destructive flag.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitManagerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def current_branch() -> str:
    """Return the name of the currently checked-out branch."""
    return _run("rev-parse", "--abbrev-ref", "HEAD")


def is_clean(exclude: list[str] | None = None) -> bool:
    """Return True if the working tree has no staged, unstaged, or
    untracked changes.

    ``exclude`` accepts repository-relative paths to ignore while
    checking — used to ignore ``workspace/missions/``, the Command
    Bridge's own runtime data store (mission.yaml, events.yaml, the
    shared queue file, ...), which is naturally untracked/mutating
    outside of any pipeline run and is not "contamination" the way an
    uncommitted change to a tracked source file would be. What gets
    committed to a mission's branch is a deliberate snapshot taken at
    commit time (see GitManager.commit), not this cleanliness check.
    """
    args = ["status", "--porcelain", "-uall"]
    if exclude:
        args.append("--")
        args.append(".")
        args.extend(f":(exclude){path}" for path in exclude)
    return _run(*args) == ""


def sync_base_branch(base: str = "main") -> None:
    """Check out ``base`` and fast-forward it to ``origin/base``.

    Uses a fast-forward-only merge, never a hard reset, so it can never
    discard local history: if the branches have diverged, the merge is
    rejected and GitManagerError is raised instead of forcing anything.
    """
    _run("checkout", base)
    _run("fetch", "origin", base)
    _run("merge", "--ff-only", f"origin/{base}")


def create_branch(name: str, base: str = "main") -> None:
    """Create and check out a new branch from the latest ``base``.

    Fails loudly (GitManagerError) if a branch with this name already
    exists — the Pipeline never silently reuses or overwrites a branch.
    """
    sync_base_branch(base)
    _run("checkout", "-b", name)


def checkout(branch: str) -> None:
    """Switch to an existing branch. Never forced."""
    _run("checkout", branch)


def commit(message: str, paths: list[str]) -> str:
    """Stage exactly ``paths`` and commit them. Returns the new commit hash.

    Deliberately never ``git add -A``: a mission's commit must contain
    only the deliverable the handler produced, never the Mission
    Framework's own operational data (mission.yaml, events.yaml, the
    shared queue file, the Pipeline's own state file). Those are
    ORION's live database, not source content, and mixing them into a
    mission's branch is what caused Sprint 008's own validation to
    fail while testing this Pipeline: writing a timeline event after
    the commit made the mission branch "dirty" again relative to its
    own tracked files, so returning to main was refused. Committing
    only the explicit deliverable paths avoids that class of bug
    entirely.

    Uses ``git add -f`` on these explicit paths only (never on a
    wildcard): a mission's own artifacts live under
    ``workspace/missions/<id>/artifacts/``, and that whole tree is
    itself gitignored (Sprint 008/009, to stop `git add -A` from
    sweeping in unrelated Bridge/Registry data). ``-f`` overrides that
    ignore rule for exactly the files TaskRunner reports it wrote —
    never for anything this function was not explicitly told to add —
    so the original protection stays intact everywhere else. Only
    ever called after validation has passed — see pipeline.py.
    """
    if not paths:
        raise GitManagerError("No hay archivos que confirmar: la lista de paths esta vacia.")
    _run("add", "-f", *paths)
    _run("commit", "-m", message)
    return get_commit_hash()


def push(branch: str) -> None:
    """Push ``branch`` to origin, creating its upstream. Never forced."""
    _run("push", "-u", "origin", branch)


def get_commit_hash() -> str:
    """Return the full hash of the current HEAD."""
    return _run("rev-parse", "HEAD")


def delete_local_branch(name: str) -> None:
    """Delete a local branch (safe, non-forced: refuses if unmerged)."""
    _run("branch", "-d", name)


def pull_request_url(branch: str) -> str:
    """Build the manual PR-creation URL for a branch.

    api.github.com is unreachable from this environment, so Pull
    Requests cannot be opened automatically. This mirrors the link
    format handed to the CEO for every prior Sprint's delivery.
    """
    origin = _run("remote", "get-url", "origin")
    repo = origin.removesuffix(".git")
    if "github.com/" in repo:
        repo = repo.split("github.com/", 1)[1]
    elif "github.com:" in repo:
        repo = repo.split("github.com:", 1)[1]
    return f"https://github.com/{repo}/pull/new/{branch}"
