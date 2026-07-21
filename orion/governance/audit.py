"""The Audit trail: every real Governance decision, permanently
recorded -- decision, policy applied, riesgo, confianza, resultado,
tiempo. "Nunca perder trazabilidad" (this Sprint's own rule) means
this module only ever appends, never edits or deletes a past entry.

Also the real source of "Historial" for orion.governance.risk_engine:
once a Mission's real outcome is known (success/failure, from
orion.execution.pipeline's own result), record_outcome() closes the
loop so a future change in the same category can honestly reuse past
track record instead of guessing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.governance import storage
from orion.governance.change_classifier import ChangeCategory
from orion.governance.confidence_engine import ConfidenceAssessment
from orion.governance.decision_engine import Decision
from orion.governance.risk_engine import RiskAssessment


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AuditEntry:
    id: str
    mission_id: str
    request: str
    category: str
    risk_level: str
    confidence_score: float
    decision_action: str
    decision_rationale: str
    execution_mode: str
    result: str = "pending"  # "pending" | "success" | "failure" | "rolled_back"
    recorded_at: str = field(default_factory=_now_iso)
    resolved_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "request": self.request,
            "category": self.category,
            "risk_level": self.risk_level,
            "confidence_score": self.confidence_score,
            "decision_action": self.decision_action,
            "decision_rationale": self.decision_rationale,
            "execution_mode": self.execution_mode,
            "result": self.result,
            "recorded_at": self.recorded_at,
            "resolved_at": self.resolved_at,
        }


def record_decision(
    mission_id: str,
    request: str,
    category: ChangeCategory,
    risk: RiskAssessment,
    confidence: ConfidenceAssessment,
    decision: Decision,
    execution_mode: str,
) -> AuditEntry:
    """Real, immediate audit of a Governance decision -- recorded the
    moment the decision is made, before execution even starts, so a
    crash mid-mission never loses the fact that a decision happened."""
    entry = AuditEntry(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        request=request,
        category=category.value,
        risk_level=risk.level.value,
        confidence_score=confidence.score,
        decision_action=decision.policy_outcome.action.value,
        decision_rationale=decision.rationale,
        execution_mode=execution_mode,
    )
    storage.ensure_governance_storage()
    storage.append_yaml_list(storage.audit_log_path(), entry.to_dict())
    return entry


def record_outcome(entry_id: str, result: str) -> AuditEntry | None:
    """Real, honest close-out of a previously recorded decision --
    never invents a new entry, only updates the matching one by id.
    Returns None if the id is not found rather than raising, since a
    caller closing out a mission's outcome must never crash the agent
    (same defensive posture every other Governance write follows)."""
    entries = storage.read_yaml(storage.audit_log_path(), [])
    for raw in entries:
        if raw.get("id") == entry_id:
            raw["result"] = result
            raw["resolved_at"] = _now_iso()
            storage.write_yaml(storage.audit_log_path(), entries)
            return AuditEntry(**raw)
    return None


def list_entries(category: str | None = None, mission_id: str | None = None) -> list[dict]:
    entries = storage.read_yaml(storage.audit_log_path(), [])
    if category is not None:
        entries = [e for e in entries if e.get("category") == category]
    if mission_id is not None:
        entries = [e for e in entries if e.get("mission_id") == mission_id]
    return entries


def count_outcomes_by_category(category: ChangeCategory) -> tuple[int, int]:
    """Real (success_count, failure_count) for a category, from
    already-resolved audit entries only -- "pending" entries (no real
    outcome yet) never count as either. This is exactly the
    ``history_success_count``/``history_failure_count`` real historial
    input orion.governance.risk_engine.assess_risk() expects."""
    entries = list_entries(category=category.value)
    success = sum(1 for e in entries if e.get("result") == "success")
    failure = sum(1 for e in entries if e.get("result") in ("failure", "rolled_back"))
    return success, failure
