"""Context discovery for the Prompt Composer.

Every function here reads from a target repository's own filesystem
(via a plain ``repo_root: Path``) or from ORION's own Mission
Framework / GitManager. Nothing here assumes a technology stack --
the filenames and directories recognized (TEAM.md, docs/ARCHITECTURE.md,
design-tokens/, docs/adr/, ...) are ORION's own documentation
conventions (established in ORION ALPHA 001/BETA 001), not anything
tied to Next.js, React, WordPress, Flutter, or any other framework. A
repository that follows none of these conventions simply yields fewer
discovered documents -- discovery degrades gracefully, it never fails
a mission.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orion.bridge.models import Mission
from orion.execution import git_manager
from orion.prompt_composer.models import (
    CommitReference,
    FileReference,
    PullRequestReference,
    RelatedMissionReference,
)
from orion.projects.models import Project

_EXCERPT_CHARS = 2000

# category -> candidate paths, relative to repo_root, checked in order;
# the first match wins. Only ORION's own documentation conventions.
_SINGLE_FILE_CANDIDATES: dict[str, list[str]] = {
    "team": ["TEAM.md", ".ai/TEAM.md"],
    "agent_context": ["CLAUDE.md", "AGENTS.md"],
    "readme": ["README.md"],
    "architecture": ["docs/ARCHITECTURE.md", "ARCHITECTURE.md"],
    "design_system": ["docs/DESIGN_SYSTEM.md"],
    "content_guide": ["docs/CONTENT_GUIDE.md"],
}

_ADR_DIRS = ["docs/adr", "docs/decisions", "adr"]
_DESIGN_TOKEN_DIRS = ["design-tokens", "tokens"]
_DESIGN_TOKEN_SUFFIXES = (".json", ".css")


@dataclass
class DiscoveredDoc:
    """One piece of documentation the Composer found in a real repo."""

    category: str
    path: str
    excerpt: str


def _read_doc(category: str, relpath: str, full_path: Path) -> DiscoveredDoc:
    try:
        text = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    excerpt = text[:_EXCERPT_CHARS]
    if len(text) > _EXCERPT_CHARS:
        excerpt += "\n...(truncado)"
    return DiscoveredDoc(category=category, path=relpath, excerpt=excerpt)


def discover_docs(repo_root: Path) -> list[DiscoveredDoc]:
    """Find every recognized documentation file that actually exists in
    ``repo_root``. Never raises -- a project with none of these files
    simply yields an empty list.
    """
    found: list[DiscoveredDoc] = []

    for category, candidates in _SINGLE_FILE_CANDIDATES.items():
        for relpath in candidates:
            full = repo_root / relpath
            if full.is_file():
                found.append(_read_doc(category, relpath, full))
                break

    for adr_dir in _ADR_DIRS:
        full_dir = repo_root / adr_dir
        if full_dir.is_dir():
            for path in sorted(full_dir.glob("*.md")):
                found.append(_read_doc("adr", str(path.relative_to(repo_root)), path))
            break

    for tokens_dir in _DESIGN_TOKEN_DIRS:
        full_dir = repo_root / tokens_dir
        if full_dir.is_dir():
            for path in sorted(full_dir.iterdir()):
                if path.is_file() and path.suffix in _DESIGN_TOKEN_SUFFIXES:
                    found.append(_read_doc("design_tokens", str(path.relative_to(repo_root)), path))
            break

    return found


def discover_related_files(mission: Mission) -> list[FileReference]:
    """Files the mission itself already names -- its own artifact_path
    or artifact_files keys. Deliberately does not guess at file paths
    mentioned in free-text description: a wrong guess is worse than no
    guess, and a future mission can add a smarter heuristic once this
    is used against real, varied missions.
    """
    files: list[FileReference] = []
    if mission.artifact_path:
        files.append(FileReference(path=mission.artifact_path, reason="artifact_path declarado por la mision"))
    for relpath in mission.artifact_files:
        files.append(FileReference(path=relpath, reason="artifact_files declarado por la mision"))
    return files


def discover_related_missions(mission: Mission, all_missions: list[Mission]) -> list[RelatedMissionReference]:
    """Other missions related by project or by shared tags.

    Both signals already exist in the Mission Framework (project_id
    from Sprint 009, tags from Sprint 004) -- this is pure read-side
    aggregation, exactly like orion.projects.services already does for
    the Business Overview.
    """
    related: list[RelatedMissionReference] = []
    for other in all_missions:
        if other.id == mission.id:
            continue
        reasons: list[str] = []
        if mission.project_id and other.project_id == mission.project_id:
            reasons.append("mismo proyecto")
        shared_tags = sorted(set(mission.tags) & set(other.tags))
        if shared_tags:
            reasons.append(f"tags compartidos: {', '.join(shared_tags)}")
        if reasons:
            related.append(
                RelatedMissionReference(
                    mission_id=other.id,
                    title=other.title,
                    status=other.status.value,
                    relation="; ".join(reasons),
                )
            )
    return related


def discover_recent_commits(repo_root: Path, limit: int = 5) -> list[CommitReference]:
    """The target repository's own recent history, via GitManager --
    never git commands run directly from this module."""
    return [CommitReference(**c) for c in git_manager.recent_commits(limit, repo_root=repo_root)]


def discover_related_pull_requests(mission: Mission, repo_root: Path) -> list[PullRequestReference]:
    """Best-effort: other mission branches already known locally.

    ORION has no GitHub API access in this environment (see
    orion.execution.git_manager.pull_request_url), so this can never
    be a real query against GitHub's Pull Request state -- only a
    locally-inferred signal, and every result says so explicitly via
    its own ``status`` field.
    """
    own_branch = f"mission/{mission.project_id}/{mission.id}" if mission.project_id else f"mission/{mission.id}"
    related: list[PullRequestReference] = []
    for remote_branch in git_manager.list_remote_branches(repo_root=repo_root):
        name = remote_branch.removeprefix("origin/")
        if not name.startswith("mission/") or name == own_branch:
            continue
        try:
            url = git_manager.pull_request_url(name, repo_root=repo_root)
        except git_manager.GitManagerError:
            continue
        related.append(
            PullRequestReference(
                branch=name,
                url=url,
                status="inferido de una rama remota local; sin confirmar via la API de GitHub",
            )
        )
    return related


def discover_project_status(project: Project | None) -> dict[str, object]:
    """The project's current operational status, reusing
    orion.projects.services (Sprint 009) instead of recomputing it --
    a Mission's context should never drift from what the Projects view
    itself reports. Imported locally to avoid a module-load-time
    dependency cycle between orion.prompt_composer and orion.projects.
    """
    if project is None:
        return {
            "repo": "Orion-AI (kernel)",
            "note": "Esta mision no pertenece a ningun proyecto registrado (project_id vacio).",
        }
    from orion.projects import services as project_services

    return project_services.describe_project(project)
