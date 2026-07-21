"""Decision Log: what a company already decided, and why -- so ORION
never re-opens a settled debate ("Elegimos WordPress. Motivo: Rapidez.").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Decision:
    id: str
    company_id: str
    decision: str
    reason: str = ""
    date: str = ""
    author: str = ""
    impact: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "decision": self.decision,
            "reason": self.reason,
            "date": self.date,
            "author": self.author,
            "impact": self.impact,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Decision":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            decision=data["decision"],
            reason=data.get("reason", ""),
            date=data.get("date", ""),
            author=data.get("author", ""),
            impact=data.get("impact", ""),
            created_at=data.get("created_at", _now_iso()),
        )


def load_decisions(company_id: str) -> list[Decision]:
    raw = storage.read_yaml(storage.decisions_path(company_id), default=[])
    return [Decision.from_dict(item) for item in raw]


def save_decisions(company_id: str, decisions: list[Decision]) -> None:
    storage.write_yaml(storage.decisions_path(company_id), [d.to_dict() for d in decisions])


def record_decision(
    company_id: str, decision: str, reason: str = "", date: str = "", author: str = "", impact: str = ""
) -> Decision:
    entry = Decision(
        id=uuid.uuid4().hex[:12], company_id=company_id, decision=decision, reason=reason,
        date=date or _now_iso()[:10], author=author, impact=impact,
    )
    decisions = load_decisions(company_id)
    decisions.append(entry)
    save_decisions(company_id, decisions)
    return entry
