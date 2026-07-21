"""Memory: permanent, structured key -> value facts about a company --
not documents, not conversations. "ATMAN usa: Tutor LMS, WordPress,
LiteSpeed, Hostinger" lives here under key "tech_stack" so ORION never
has to ask again.

Deliberately simpler than knowledge.py: knowledge.py holds free-form,
individually-sourced facts with categories/tags (a growing log);
memory.py holds the small set of settled, structured attributes a
Company is looked up by (its real "profile"), one list of real values
per key, deduplicated.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(company_id: str) -> dict:
    return storage.read_yaml(storage.memory_path(company_id), default={"facts": {}, "updated_at": ""})


def _save(company_id: str, data: dict) -> None:
    data["updated_at"] = _now_iso()
    storage.write_yaml(storage.memory_path(company_id), data)


def remember(company_id: str, key: str, value: str) -> None:
    """Append ``value`` under ``key`` if not already remembered
    (case-insensitive dedup) -- e.g. remember("atman", "tech_stack", "WordPress")."""
    data = _load(company_id)
    facts: dict[str, list[str]] = data.setdefault("facts", {})
    values = facts.setdefault(key, [])
    if not any(v.strip().lower() == value.strip().lower() for v in values):
        values.append(value.strip())
    _save(company_id, data)


def remember_many(company_id: str, key: str, values: list[str]) -> None:
    for value in values:
        remember(company_id, key, value)


def recall(company_id: str, key: str) -> list[str]:
    data = _load(company_id)
    return list(data.get("facts", {}).get(key, []))


def all_memory(company_id: str) -> dict[str, list[str]]:
    return dict(_load(company_id).get("facts", {}))
