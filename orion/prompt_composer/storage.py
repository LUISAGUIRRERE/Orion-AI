"""Persistence for a mission's PromptPackage.

Same pattern as orion.bridge.storage: plain YAML, stored alongside
that mission's own data under workspace/missions/<mission-id>/, so a
PromptPackage is always found next to the mission it belongs to and
never needs a second lookup index.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from orion.bridge import storage as bridge_storage
from orion.prompt_composer.models import PromptPackage


def _path_for(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "prompt_package.yaml"


def save(mission_id: str, package: PromptPackage) -> Path:
    """Persist a PromptPackage for a mission, overwriting any previous
    one -- a mission only ever has its latest PromptPackage on disk,
    matching how mission.yaml itself is a single current snapshot,
    not a history."""
    path = _path_for(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(package.model_dump(mode="json"), fh, allow_unicode=True, sort_keys=False)
    return path


def load(mission_id: str) -> PromptPackage | None:
    """Load a mission's persisted PromptPackage, or None if it has
    never had one composed (e.g. it predates this Sprint, or hasn't
    reached the Builder yet)."""
    path = _path_for(mission_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return None if data is None else PromptPackage(**data)
