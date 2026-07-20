"""YAML-backed persistence for the Project Registry.

Each project is stored as plain YAML under
``workspace/companies/<project_id>/project.yaml``, mirroring exactly
the pattern the Command Bridge already uses for missions
(``orion/bridge/storage.py``) — self-contained, computes its own
paths, and never imports from ``orion.bridge`` or ``orion.window``.

Every project also gets ``missions/``, ``metrics/``, and ``events/``
subdirectories, per this Sprint's spec. They are created as reserved
scaffolding for future project-local artifacts (e.g. generated
reports); the actual mission data itself continues to live exclusively
in the Command Bridge's own ``workspace/missions/`` store, which stays
the single source of truth — duplicating it here would risk the two
copies drifting out of sync.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
WORKSPACE_DIR: Path = REPO_ROOT / "workspace"
COMPANIES_DIR: Path = WORKSPACE_DIR / "companies"


def ensure_projects_storage() -> None:
    """Create the companies directory if missing."""
    COMPANIES_DIR.mkdir(parents=True, exist_ok=True)


def project_dir(project_id: str) -> Path:
    """Return the storage directory for a given project id."""
    return COMPANIES_DIR / project_id


def project_exists(project_id: str) -> bool:
    """Return True if a project with this id has been registered."""
    return (project_dir(project_id) / "project.yaml").is_file()


def list_project_ids() -> list[str]:
    """Return every registered project id, sorted."""
    if not COMPANIES_DIR.exists():
        return []
    return sorted(
        p.name
        for p in COMPANIES_DIR.iterdir()
        if p.is_dir() and (p / "project.yaml").is_file()
    )


def read_project(project_id: str) -> dict[str, Any] | None:
    """Read a project's ``project.yaml``, or None if it does not exist."""
    path = project_dir(project_id) / "project.yaml"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_project(project_id: str, data: dict[str, Any]) -> None:
    """Persist a project's data and ensure its reserved subdirectories exist."""
    company_dir = project_dir(project_id)
    for sub in ("missions", "metrics", "events"):
        (company_dir / sub).mkdir(parents=True, exist_ok=True)
    path = company_dir / "project.yaml"
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
