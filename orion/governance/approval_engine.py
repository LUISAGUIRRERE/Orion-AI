"""The real Approval Queue: the one place a pending Governance
decision waits for a real human answer.

Per this Sprint's own APPROVAL ENGINE rule ("Solo solicitar aprobacion
cuando exista una decision real"), this module is never consulted to
*decide whether* something needs approval -- that is
orion.governance.policy_engine/decision_engine's job, already done by
the time request_approval() is called here. This module only manages
the lifecycle of a decision that has already been flagged
needs_approval=True: create the request, let a human approve/reject
it, and report its real current status. Nothing here re-implements
the never-ask/always-ask category rules orion.governance.autonomy
already owns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.governance import storage
from orion.governance.decision_engine import Decision


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ApprovalRequest:
    id: str
    mission_id: str
    request: str
    category: str
    risk_level: str
    confidence_score: float
    decision_type: str  # "approval" | "human_decision"
    rationale: str
    status: str = "pending"  # "pending" | "approved" | "rejected"
    requested_at: str = field(default_factory=_now_iso)
    resolved_by: str = ""
    resolved_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "request": self.request,
            "category": self.category,
            "risk_level": self.risk_level,
            "confidence_score": self.confidence_score,
            "decision_type": self.decision_type,
            "rationale": self.rationale,
            "status": self.status,
            "requested_at": self.requested_at,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "notes": self.notes,
        }


def request_approval(
    mission_id: str,
    request_text: str,
    category: str,
    risk_level: str,
    confidence_score: float,
    decision: Decision,
) -> ApprovalRequest:
    """Create a real, persisted approval request. Only ever called
    once decision_engine.decide() has already answered needs_approval
    True for this exact decision -- this function does not re-check
    that itself, by design (single source of truth for the "ask or
    not" question)."""
    entry = ApprovalRequest(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        request=request_text,
        category=category,
        risk_level=risk_level,
        confidence_score=confidence_score,
        decision_type=decision.policy_outcome.decision_type,
        rationale=decision.rationale,
    )
    storage.ensure_governance_storage()
    storage.append_yaml_list(storage.approvals_path(), entry.to_dict())
    return entry


def _load_all() -> list[dict]:
    return storage.read_yaml(storage.approvals_path(), [])


def _save_all(entries: list[dict]) -> None:
    storage.write_yaml(storage.approvals_path(), entries)


def list_pending() -> list[dict]:
    return [e for e in _load_all() if e.get("status") == "pending"]


def list_all() -> list[dict]:
    return _load_all()


def get(request_id: str) -> dict | None:
    for entry in _load_all():
        if entry.get("id") == request_id:
            return entry
    return None


def approve(request_id: str, approver: str, notes: str = "") -> dict | None:
    entries = _load_all()
    for entry in entries:
        if entry.get("id") == request_id:
            entry["status"] = "approved"
            entry["resolved_by"] = approver
            entry["resolved_at"] = _now_iso()
            entry["notes"] = notes
            _save_all(entries)
            return entry
    return None


def reject(request_id: str, approver: str, notes: str = "") -> dict | None:
    entries = _load_all()
    for entry in entries:
        if entry.get("id") == request_id:
            entry["status"] = "rejected"
            entry["resolved_by"] = approver
            entry["resolved_at"] = _now_iso()
            entry["notes"] = notes
            _save_all(entries)
            return entry
    return None
