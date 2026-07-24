"""GitManager — the only module allowed to run git commands for ORION's
Execution Pipeline.

No other module (Workspace, TaskRunner, Pipeline itself) may invoke
git directly. Every operation here is safe and reversible: no
``git reset --hard``, no ``git clean -fd``, no ``git push --force``,
no forced checkout. A failed git command always raises
``GitManagerError`` instead of being swallowed, so the Pipeline can
always tell "nothing to do" apart from "something went wrong".

ORION ALPHA 001 addition: every function now accepts an optional
``repo_root``, defaulting to ``REPO_ROOT`` (this environment's own
Orion-AI checkout) so every pre-existing caller keeps working exactly
as before. The Multi-Project Engine (Sprint 009) already let a Project
carry its own ``repository`` URL, but nothing actually pointed
GitManager at a different physical checkout — every mission still ran
against Orion-AI's own repo regardless of which project it belonged
to. This is the minimal fix that closes that gap: a Project's
``local_path`` (see orion/projects/models.py) resolves to the
``repo_root`` Pipeline passes down here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from orion.bridge import storage as bridge_storage

REPO_ROOT: Path = bridge_storage.REPO_ROOT


class GitManagerError(RuntimeError):
    """Raised when a git operation fails."""


def _run(*args: str, repo_root: Path = REPO_ROOT) -> str:
    """Run a git command against ``repo_root`` and return stdout.

    Raises GitManagerError with the command's stderr on any non-zero
    exit code. Never uses shell=True, never accepts a destructive flag.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitManagerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def current_branch(repo_root: Path = REPO_ROOT) -> str:
    """Return the name of the currently checked-out branch.

    Falls back to ``symbolic-ref`` for a completely unborn branch
    (zero commits anywhere yet), where ``rev-parse --abbrev-ref HEAD``
    has nothing to resolve.
    """
    try:
        return _run("rev-parse", "--abbrev-ref", "HEAD", repo_root=repo_root)
    except GitManagerError:
        return _run("symbolic-ref", "--short", "HEAD", repo_root=repo_root)


def is_clean(exclude: list[str] | None = None, repo_root: Path = REPO_ROOT) -> bool:
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
    return _run(*args, repo_root=repo_root) == ""


def sync_base_branch(base: str = "main", repo_root: Path = REPO_ROOT) -> None:
    """Check out ``base`` and fast-forward it to ``origin/base``.

    Uses a fast-forward-only merge, never a hard reset, so it can never
    discard local history: if the branches have diverged, the merge is
    rejected and GitManagerError is raised instead of forcing anything.

    Tolerates a brand-new repository with no commits at all yet (an
    "unborn" branch): if ``origin`` has no ``base`` ref either, there
    is nothing to fetch or fast-forward to, so this is a no-op instead
    of an error. This only ever applies once, to a project's very
    first commit.
    """
    try:
        _run("checkout", base, repo_root=repo_root)
    except GitManagerError:
        # A completely unborn repository (zero commits ever) has no
        # `base` ref to check out yet — `checkout` fails even though
        # HEAD already symbolically points at it. Confirm that before
        # treating this as a genuine failure.
        current = _run("symbolic-ref", "--short", "HEAD", repo_root=repo_root)
        if current != base:
            raise
    try:
        _run("fetch", "origin", base, repo_root=repo_root)
    except GitManagerError:
        # No such ref on origin either — nothing to sync yet. This
        # only ever applies once, to a project's very first commit.
        return
    _run("merge", "--ff-only", f"origin/{base}", repo_root=repo_root)


def create_branch(name: str, base: str = "main", repo_root: Path = REPO_ROOT) -> None:
    """Create and check out a new branch from the latest ``base``.

    Fails loudly (GitManagerError) if a branch with this name already
    exists — the Pipeline never silently reuses or overwrites a branch.
    """
    sync_base_branch(base, repo_root=repo_root)
    _run("checkout", "-b", name, repo_root=repo_root)


def checkout(branch: str, repo_root: Path = REPO_ROOT) -> None:
    """Switch to an existing branch. Never forced.

    Tolerates a completely unborn branch (zero commits ever) the same
    way ``sync_base_branch`` and ``current_branch`` do: ``checkout``
    has no ref to switch to yet even though HEAD already symbolically
    points at it.
    """
    try:
        _run("checkout", branch, repo_root=repo_root)
    except GitManagerError:
        current = _run("symbolic-ref", "--short", "HEAD", repo_root=repo_root)
        if current != branch:
            raise


def commit(message: str, paths: list[str], repo_root: Path = REPO_ROOT) -> str:
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
    wildcard): a mission's own artifacts, when written into ORION's
    own workspace, live under a gitignored tree (Sprint 008/009, to
    stop `git add -A` from sweeping in unrelated Bridge/Registry
    data). ``-f`` overrides that ignore rule for exactly the files
    TaskRunner reports it wrote — never for anything this function was
    not explicitly told to add — so the original protection stays
    intact everywhere else. Only ever called after validation has
    passed — see pipeline.py.
    """
    if not paths:
        raise GitManagerError("No hay archivos que confirmar: la lista de paths esta vacia.")
    _run("add", "-f", *paths, repo_root=repo_root)
    _run("commit", "-m", message, repo_root=repo_root)
    return get_commit_hash(repo_root=repo_root)


def push(branch: str, repo_root: Path = REPO_ROOT) -> None:
    """Push ``branch`` to origin, creating its upstream. Never forced."""
    _run("push", "-u", "origin", branch, repo_root=repo_root)


def get_commit_hash(repo_root: Path = REPO_ROOT) -> str:
    """Return the full hash of the current HEAD."""
    return _run("rev-parse", "HEAD", repo_root=repo_root)


def delete_local_branch(name: str, repo_root: Path = REPO_ROOT, force: bool = False) -> None:
    """Delete a local branch. ``force=False`` (default, every existing
    caller): safe, non-forced ``-d``, refuses if unmerged. ``force=True``
    (BETA 010, orion.governance.rollback): ``-D``, for abandoning a
    Mission's own throwaway branch that is *known* unmerged -- the
    caller is expected to have already confirmed via
    is_branch_merged() that this is a real Mission branch, not shared
    history, before ever passing force=True."""
    flag = "-D" if force else "-d"
    _run("branch", flag, name, repo_root=repo_root)


def is_branch_merged(name: str, base: str = "main", repo_root: Path = REPO_ROOT) -> bool:
    """Real check via ``git branch --merged <base>`` -- never guessed.
    Added for orion.governance.rollback so it never has to reach past
    GitManager into a raw git call itself (GitManager remains the only
    module that ever touches git, same rule every prior Sprint kept)."""
    output = _run("branch", "--merged", base, repo_root=repo_root)
    merged_names = {line.strip().lstrip("* ").strip() for line in output.splitlines() if line.strip()}
    return name in merged_names


def recent_commits(limit: int = 5, repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    """Return up to ``limit`` recent commits reachable from HEAD, most
    recent first: hash, author, date (ISO 8601), message.

    Read-only (``git log``), added for the Prompt Composer (BETA 001
    follow-up) so it can discover real project history without any
    module other than GitManager ever running git directly. Tolerates
    a repository with zero commits (returns an empty list instead of
    raising) the same way the other unborn-repo-tolerant functions in
    this module do.
    """
    try:
        raw = _run(
            "log",
            f"-{limit}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
            repo_root=repo_root,
        )
    except GitManagerError:
        return []
    if not raw:
        return []
    commits: list[dict[str, str]] = []
    for line in raw.split("\n"):
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        commit_hash, author, date, message = parts
        commits.append({"hash": commit_hash, "author": author, "date": date, "message": message})
    return commits


def list_remote_branches(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return every remote-tracking branch known locally (e.g.
    'origin/main', 'origin/mission/atman/MISSION-0022'), as of the
    last fetch this environment performed -- this never itself talks
    to the network, so it is always safe and fast to call.

    Read-only (``git branch -r``), added for the Prompt Composer's
    best-effort "related Pull Requests" discovery: ORION has no
    GitHub API access in this environment (see ``pull_request_url``
    below), so a locally-known remote branch is the closest available
    signal for "there might be an open PR here".
    """
    try:
        raw = _run("branch", "-r", "--format=%(refname:short)", repo_root=repo_root)
    except GitManagerError:
        return []
    return [line.strip() for line in raw.split("\n") if line.strip() and "HEAD ->" not in line]


def pull_request_url(branch: str, repo_root: Path = REPO_ROOT) -> str:
    """Build the manual PR-creation URL for a branch.

    api.github.com is unreachable from this environment, so Pull
    Requests cannot be opened automatically. This mirrors the link
    format handed to the CEO for every prior Sprint's delivery.
    """
    origin = _run("remote", "get-url", "origin", repo_root=repo_root)
    repo = origin.removesuffix(".git")
    if "github.com/" in repo:
        repo = repo.split("github.com/", 1)[1]
    elif "github.com:" in repo:
        repo = repo.split("github.com:", 1)[1]
    return f"https://github.com/{repo}/pull/new/{branch}"
