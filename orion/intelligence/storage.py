"""Persistence for orion.intelligence: plain, atomic YAML under
``workspace/intelligence/<project_key>/``, the same
file-per-concern-read-fresh-every-call pattern every other ORION
module already uses (orion.bridge.storage, orion.runtime.storage,
...). Deliberately generic -- this module never imports a model class
from project_index.py/dependency_graph.py/etc. (that would create an
import cycle, since those modules call back into this one to persist
themselves); it only knows paths and how to read/write YAML safely.

Every ORION-owned repository ORION might ever analyze (Orion-AI
itself, ATMAN, CGISO, Tealife, Casino, future Business Units) gets its
own subdirectory, keyed by ``project_key`` -- an orion.projects
project_id for a registered project, or the literal string ``"_self"``
for ORION's own checkout when no project_id applies (e.g. `orion
analyze` run with no --project).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from orion.intelligence.config import IntelligenceConfig

_CONFIG = IntelligenceConfig.from_env()
INTELLIGENCE_DIR: Path = _CONFIG.workspace_dir

SELF_PROJECT_KEY = "_self"


def project_dir(project_key: str) -> Path:
    safe_key = project_key or SELF_PROJECT_KEY
    return INTELLIGENCE_DIR / safe_key


def ensure_project_storage(project_key: str) -> None:
    project_dir(project_key).mkdir(parents=True, exist_ok=True)
    (project_dir(project_key) / "reports").mkdir(parents=True, exist_ok=True)


def index_path(project_key: str) -> Path:
    return project_dir(project_key) / "index.yaml"


def architecture_map_path(project_key: str) -> Path:
    return project_dir(project_key) / "architecture_map.yaml"


def dependency_graph_path(project_key: str) -> Path:
    return project_dir(project_key) / "dependency_graph.yaml"


def knowledge_graph_path() -> Path:
    # The Knowledge Graph is deliberately global, not per-project: it
    # models ORION's own operational entities (Mission, PromptPackage,
    # Executor, Provider, ExecutionResult, Validation, Experience),
    # which exist once per ORION installation, plus project component
    # entities namespaced by project_key inside node ids -- one graph,
    # not one per project, so cross-project relationships (e.g. "this
    # pattern was learned on ATMAN, reused on CGISO") are representable.
    return INTELLIGENCE_DIR / "knowledge_graph.yaml"


def impact_report_path(project_key: str, report_id: str) -> Path:
    return project_dir(project_key) / "reports" / f"impact-{report_id}.yaml"


def review_report_path(project_key: str, report_id: str) -> Path:
    return project_dir(project_key) / "reports" / f"review-{report_id}.yaml"


def plan_path(project_key: str, plan_id: str) -> Path:
    return project_dir(project_key) / "reports" / f"plan-{plan_id}.yaml"


def read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if data is not None else default


def write_yaml(path: Path, data: Any) -> None:
    """Atomic write (temp file + os.replace), same fix/reasoning as
    orion.runtime.storage._atomic_write_yaml and
    orion.bridge.storage._write_yaml: a plain open(path, "w") truncates
    before it finishes writing, so a concurrent reader (The Window, a
    second `orion` CLI invocation) could observe a partial document.
    Applied here from the start, since BETA 007 already proved this
    class of bug is real once more than one process/thread can touch
    the same file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def list_report_ids(project_key: str, prefix: str) -> list[str]:
    reports_dir = project_dir(project_key) / "reports"
    if not reports_dir.is_dir():
        return []
    ids = []
    for path in reports_dir.glob(f"{prefix}-*.yaml"):
        ids.append(path.stem[len(prefix) + 1 :])
    return sorted(ids)
