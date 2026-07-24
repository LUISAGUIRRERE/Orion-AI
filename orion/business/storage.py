"""Persistence for orion.business: plain, atomic YAML under
``workspace/business_brain/<company_id>/``, the same
file-per-concern-read-fresh-every-call pattern orion.intelligence.storage
already established (and, before that, orion.runtime.storage /
orion.bridge.storage). Deliberately generic -- never imports a
dataclass from company.py/project.py/goals.py/etc. (that would create
an import cycle, since those modules call back into this one to
persist themselves); it only knows paths and how to read/write YAML
safely.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from orion.business.config import BusinessConfig

_CONFIG = BusinessConfig.from_env()
BUSINESS_DIR: Path = _CONFIG.workspace_dir


def ensure_business_storage() -> None:
    BUSINESS_DIR.mkdir(parents=True, exist_ok=True)


def company_dir(company_id: str) -> Path:
    return BUSINESS_DIR / company_id


def ensure_company_storage(company_id: str) -> None:
    company_dir(company_id).mkdir(parents=True, exist_ok=True)


def company_path(company_id: str) -> Path:
    return company_dir(company_id) / "company.yaml"


def projects_path(company_id: str) -> Path:
    return company_dir(company_id) / "projects.yaml"


def brand_path(company_id: str) -> Path:
    return company_dir(company_id) / "brand.yaml"


def knowledge_path(company_id: str) -> Path:
    return company_dir(company_id) / "knowledge.yaml"


def memory_path(company_id: str) -> Path:
    return company_dir(company_id) / "memory.yaml"


def documents_path(company_id: str) -> Path:
    return company_dir(company_id) / "documents.yaml"


def roadmap_path(company_id: str) -> Path:
    return company_dir(company_id) / "roadmap.yaml"


def goals_path(company_id: str) -> Path:
    return company_dir(company_id) / "goals.yaml"


def decisions_path(company_id: str) -> Path:
    return company_dir(company_id) / "decisions.yaml"


def list_company_ids() -> list[str]:
    if not BUSINESS_DIR.exists():
        return []
    return sorted(p.name for p in BUSINESS_DIR.iterdir() if p.is_dir() and company_path(p.name).exists())


def read_yaml(path: Path, default: Any) -> Any:
    """Read one YAML file, or ``default`` if it does not exist yet --
    every *_path() above points at a file that legitimately might not
    exist yet (a company with no Decisions recorded, for instance)."""
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return default if data is None else data


def write_yaml(path: Path, data: Any) -> None:
    """Atomic write: temp file + os.replace(), the exact fix BETA 007
    found necessary for orion.runtime.storage/orion.bridge.storage
    under concurrent access, applied here from the start rather than
    retrofitted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
