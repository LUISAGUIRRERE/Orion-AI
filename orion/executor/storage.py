"""Persistence for a mission's ExecutionRequest/ExecutionResult.

Same YAML-under-the-mission's-own-directory pattern as
orion.bridge.storage and orion.prompt_composer.storage: every piece of
a mission's evidence lives together under
workspace/missions/<mission-id>/, never in a second index.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from orion.bridge import storage as bridge_storage
from orion.executor.models import ExecutionRequest, ExecutionResult


def _request_path(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "execution_request.yaml"


def _result_path(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "execution_result.yaml"


def save_request(mission_id: str, request: ExecutionRequest) -> Path:
    path = _request_path(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(request.model_dump(mode="json"), fh, allow_unicode=True, sort_keys=False)
    return path


def load_request(mission_id: str) -> ExecutionRequest | None:
    path = _request_path(mission_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return None if data is None else ExecutionRequest(**data)


def save_result(mission_id: str, result: ExecutionResult) -> Path:
    path = _result_path(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(result.model_dump(mode="json"), fh, allow_unicode=True, sort_keys=False)
    return path


def load_result(mission_id: str) -> ExecutionResult | None:
    path = _result_path(mission_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return None if data is None else ExecutionResult(**data)
