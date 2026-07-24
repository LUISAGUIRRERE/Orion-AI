"""The persistent, incrementally-updated Project Index.

Wraps orion.intelligence.repository_analyzer's real filesystem scan
with persistence (orion.intelligence.storage) and the incremental
skip-if-unchanged behavior repository_analyzer.analyze_file() already
implements: build_index() always loads whatever index was previously
persisted for this project_key and passes its files through as
``previous_files``, so a file whose size/mtime did not change since
the last build is never re-read or re-parsed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from orion.intelligence import storage
from orion.intelligence.config import IntelligenceConfig
from orion.intelligence.repository_analyzer import FileRecord, RepositoryProfile, scan_repository


@dataclass
class ProjectIndex:
    project_key: str
    repo_root: str
    generated_at: str
    profile: RepositoryProfile
    files: dict[str, FileRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "project_key": self.project_key,
            "repo_root": self.repo_root,
            "generated_at": self.generated_at,
            "profile": self.profile.to_dict(),
            "files": {path: record.to_dict() for path, record in self.files.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectIndex":
        return cls(
            project_key=data["project_key"],
            repo_root=data["repo_root"],
            generated_at=data["generated_at"],
            profile=RepositoryProfile.from_dict(data.get("profile", {})),
            files={path: FileRecord.from_dict(rec) for path, rec in data.get("files", {}).items()},
        )

    def file_count(self) -> int:
        return len(self.files)

    def files_by_purpose(self, purpose: str) -> list[FileRecord]:
        return [r for r in self.files.values() if r.purpose == purpose]


def load_index(project_key: str) -> ProjectIndex | None:
    """Read whatever index is currently persisted, without touching
    the filesystem being indexed. None if never built."""
    raw = storage.read_yaml(storage.index_path(project_key), None)
    if raw is None:
        return None
    return ProjectIndex.from_dict(raw)


def build_index(
    repo_root: Path,
    project_key: str,
    config: IntelligenceConfig | None = None,
    force_full: bool = False,
) -> ProjectIndex:
    """Build (or incrementally update) the persistent index for
    ``project_key``, whose real files live at ``repo_root``.

    ``force_full=True`` discards any previously persisted index before
    scanning, so every file is re-read/re-parsed regardless of its
    stat -- useful for `orion understand --force` or after a config
    change that affects how files are classified/parsed. Default
    behavior (``force_full=False``) is the real incremental path this
    Sprint's spec asks for.
    """
    config = config or IntelligenceConfig.from_env()
    storage.ensure_project_storage(project_key)

    previous = None if force_full else load_index(project_key)
    previous_files = previous.files if previous is not None else {}

    profile, records = scan_repository(repo_root, config, previous_files=previous_files)

    index = ProjectIndex(
        project_key=project_key,
        repo_root=str(repo_root),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        profile=profile,
        files={record.path: record for record in records},
    )
    storage.write_yaml(storage.index_path(project_key), index.to_dict())
    return index


def ensure_fresh_index(
    repo_root: Path,
    project_key: str,
    config: IntelligenceConfig | None = None,
) -> ProjectIndex:
    """The one function most callers (services.py, the Worker's
    intelligence hook) should use: reuses a persisted index as-is if
    it exists (project_index.py's own persistence already means
    "understand" was run at some point), rebuilding incrementally on
    top of it either way so any files that changed on disk since are
    picked up for free without a caller having to decide "is this
    stale?" themselves. This is always incremental (never
    force_full) -- callers that explicitly want a full re-scan use
    build_index(..., force_full=True) directly (e.g. `orion understand
    --force`).
    """
    return build_index(repo_root, project_key, config=config, force_full=False)
