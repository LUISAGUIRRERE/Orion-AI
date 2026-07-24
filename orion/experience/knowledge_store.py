"""The Knowledge Store: persistence and queries for KnowledgeItem.

Deliberately not a database -- one YAML file per item under
workspace/knowledge/, the same flat-directory-of-YAML-files pattern
orion.bridge.storage and orion.projects.storage already use. Listing
and filtering means scanning that directory; at the scale ORION
operates at (missions measured in the tens to low hundreds, not
millions), that is simple, transparent, and grep-able -- exactly the
"knowledge base, not a log database" the Sprint asked for: every item
here is small, structured, and individually meaningful, not an
appended stream of raw events.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from orion.bridge import storage as bridge_storage
from orion.experience.models import KnowledgeItem, KnowledgeItemType

KNOWLEDGE_DIR: Path = bridge_storage.WORKSPACE_DIR / "knowledge"


def _item_path(item_id: str) -> Path:
    return KNOWLEDGE_DIR / f"{item_id}.yaml"


def save_item(item: KnowledgeItem) -> Path:
    path = _item_path(item.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(item.model_dump(mode="json"), fh, allow_unicode=True, sort_keys=False)
    return path


def get_item(item_id: str) -> KnowledgeItem | None:
    path = _item_path(item_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return None if data is None else KnowledgeItem(**data)


def list_items(
    item_type: KnowledgeItemType | None = None,
    project_id: str | None = None,
    tag: str | None = None,
) -> list[KnowledgeItem]:
    """Every KnowledgeItem, optionally filtered. Oldest first, the same
    convention orion.execution.pipeline.list_outcomes() already uses."""
    if not KNOWLEDGE_DIR.exists():
        return []
    items: list[KnowledgeItem] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data is None:
            continue
        item = KnowledgeItem(**data)
        if item_type is not None and item.type != item_type:
            continue
        if project_id is not None and item.project_id != project_id:
            continue
        if tag is not None and tag not in item.tags:
            continue
        items.append(item)
    items.sort(key=lambda i: i.created_at)
    return items
