"""Public entry points for orion.governance -- the only module the
CLI (bin/orion), the Runtime, and The Window are allowed to call
directly. Same "one entry point per subsystem" convention every prior
Sprint's own services.py already establishes.

evaluate_change() is the real Mission Flow step this Sprint inserts
between Project Intelligence and the Prompt Composer: Risk Engine ->
Policy Engine -> Decision Engine, in that order, using real inputs
only (an ImpactReport already computed by orion.intelligence, real
historial from this module's own Audit log) -- never a second,
duplicate analysis of the repository or the business context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.governance import approval_engine, audit, autonomy, rollback
from orion.governance import execution_mode as execution_mode_module
from orion.governance.change_classifier import ChangeCategory, Classification, classify_change
from orion.governance.confidence_engine import ConfidenceAssessment, assess_confidence
from orion.governance.decision_engine import Decision, decide
from orion.governance.execution_mode import ModeProfile
from orion.governance.policy_engine import PolicyOutcome, evaluate_policy
from orion.governance.risk_engine import RiskAssessment, RiskLevel, assess_risk
from orion.intelligence.impact_analyzer import ImpactReport

AUTHOR = "Governance"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(mission_id: str | None, event_type: str, message: str) -> None:
    """Real event emission, reusing orion.runtime.events.emit -- same
    convention orion.intelligence.services/orion.business.services
    already follow, never a parallel event system."""
    if not mission_id:
        return
    from orion.runtime import events as runtime_events

    runtime_events.emit(mission_id, event_type, message, AUTHOR)


@dataclass
class GovernanceEvaluation:
    """Everything ORION decided about one change, before executing a
    single line of it -- classification, risk, confidence, the policy
    rule that applied, and the resulting Decision. Always audited
    (see evaluate_change below), never computed and thrown away."""

    request: str
    classification: Classification
    risk: RiskAssessment
    confidence: ConfidenceAssessment
    mode_profile: ModeProfile
    policy_outcome: PolicyOutcome
    decision: Decision
    audit_entry_id: str
    approval_request_id: str | None = None
    generated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "category": self.classification.category.value,
            "risk": self.risk.to_dict(),
            "confidence": self.confidence.to_dict(),
            "mode": self.mode_profile.mode,
            "policy": self.policy_outcome.to_dict(),
            "decision": self.decision.to_dict(),
            "audit_entry_id": self.audit_entry_id,
            "approval_request_id": self.approval_request_id,
            "generated_at": self.generated_at,
        }

    def summary_text(self) -> str:
        lines = [
            f"Categoria de cambio: {self.classification.category.value}.",
            f"Riesgo: {self.risk.level.value}.",
            f"Confianza: {self.confidence.score:.2f}.",
            f"Modo de ejecucion: {self.mode_profile.mode}.",
            f"Decision: {self.policy_outcome.rule}",
        ]
        if self.decision.needs_approval:
            lines.append("Se requiere aprobacion antes de continuar.")
        elif self.decision.should_split_mission:
            lines.append("Se recomienda dividir la mision antes de continuar.")
        else:
            lines.append("ORION puede continuar de forma autonoma.")
        return "\n".join(lines)


def evaluate_change(
    request_text: str,
    mission_id: str = "",
    project_id: str = "",
    impact: ImpactReport | None = None,
    category_override: ChangeCategory | None = None,
) -> GovernanceEvaluation:
    """The real BETA 010 Mission Flow step: classify -> assess risk
    (reusing ``impact``, orion.intelligence's own already-computed
    ImpactReport -- never recomputed here) -> assess confidence ->
    apply policy for the current Execution Mode -> decide. Always
    recorded to the Audit log before returning, and opens a real
    Approval Queue entry whenever the Decision says one is needed --
    "toda decision debe quedar auditada", no exceptions."""
    classification = classify_change(request_text) if category_override is None else Classification(
        category=category_override, matched_keywords=[], scores={}
    )
    category = classification.category

    success_count, failure_count = audit.count_outcomes_by_category(category)
    risk = assess_risk(category, impact, history_failure_count=failure_count, history_success_count=success_count)
    confidence = assess_confidence(request_text, impact, risk.level, project_id=project_id)

    mode = execution_mode_module.get_mode()
    mode_profile = execution_mode_module.get_profile(mode)

    policy_outcome = evaluate_policy(category, risk, confidence, mode_profile)
    decision = decide(policy_outcome, risk)

    entry = audit.record_decision(
        mission_id or "(sin mision)", request_text, category, risk, confidence, decision, mode
    )

    approval_id: str | None = None
    if decision.needs_approval:
        req = approval_engine.request_approval(
            mission_id or "(sin mision)", request_text, category.value, risk.level.value, confidence.score, decision
        )
        approval_id = req.id
        _emit(mission_id, "governance_approval_requested", decision.rationale)

    _emit(mission_id, "governance_evaluated", f"{category.value} / {risk.level.value} / {confidence.score:.2f} -> {policy_outcome.action.value}")

    return GovernanceEvaluation(
        request=request_text,
        classification=classification,
        risk=risk,
        confidence=confidence,
        mode_profile=mode_profile,
        policy_outcome=policy_outcome,
        decision=decision,
        audit_entry_id=entry.id,
        approval_request_id=approval_id,
    )


def close_mission_outcome(audit_entry_id: str, result: str, mission_id: str = "") -> None:
    """Real, honest close-out once a mission's actual result is known
    -- feeds orion.governance.audit's historial, which the *next*
    change in this same category will really use via
    evaluate_change()'s own success_count/failure_count lookup above."""
    audit.record_outcome(audit_entry_id, result)
    _emit(mission_id, "governance_outcome_recorded", f"Resultado real registrado: {result}.")


def rollback_mission(mission_id: str, branch: str, repo_root=None):
    result = rollback.rollback_mission(mission_id, branch, repo_root=repo_root)
    _emit(mission_id, "governance_rollback_attempted", result.reason)
    return result


def get_mode() -> str:
    return execution_mode_module.get_mode()


def set_mode(mode: str, author: str = "ORION", reason: str = "") -> ModeProfile:
    return execution_mode_module.set_mode(mode, author=author, reason=reason)


def get_mode_profile() -> ModeProfile:
    return execution_mode_module.get_profile(execution_mode_module.get_mode())


def approve_request(request_id: str, approver: str, notes: str = "") -> dict | None:
    return approval_engine.approve(request_id, approver, notes)


def reject_request(request_id: str, approver: str, notes: str = "") -> dict | None:
    return approval_engine.reject(request_id, approver, notes)


def list_pending_approvals() -> list[dict]:
    return approval_engine.list_pending()


def list_audit(category: str | None = None, mission_id: str | None = None) -> list[dict]:
    return audit.list_entries(category=category, mission_id=mission_id)


def describe_policies() -> list[dict]:
    """A real, human-readable description of the rule table
    orion.governance.policy_engine.evaluate_policy() actually applies
    -- generated from the same worked examples this Sprint's own
    brief gives, for `orion policy`/GET /api/governance/policies to
    show without duplicating the rule logic itself."""
    return [
        {"rule": "Architecture -> Detener -> Esperar decision humana.", "categoria": "Architecture"},
        {"rule": "Breaking Change -> Detener -> Solicitar aprobacion.", "categoria": "Breaking Change"},
        {"rule": "Riesgo CRITICAL -> Detener -> Solicitar aprobacion (cualquier categoria).", "categoria": "*"},
        {"rule": f"Modo actual sin autonomia para la categoria -> Detener -> Solicitar aprobacion.", "categoria": "*"},
        {
            "rule": "Bug Fix AND Riesgo LOW AND Confianza > umbral -> Corregir automaticamente -> Crear test -> Ejecutar suite -> Continuar.",
            "categoria": "Bug Fix",
        },
        {
            "rule": "Categoria de bajo riesgo (Refactor/Optimization/Documentation/Bug Fix) AND Riesgo LOW/MEDIUM AND Confianza >= 0.7 -> Aplicar -> Ejecutar suite -> Continuar.",
            "categoria": "Bug Fix / Refactor / Optimization / Documentation",
        },
        {
            "rule": "Riesgo HIGH por alcance AND Confianza >= 0.6 -> Continuar, candidato a dividir la mision.",
            "categoria": "*",
        },
        {
            "rule": "Riesgo LOW/MEDIUM AND Confianza >= 0.5 -> Continuar sin pausa.",
            "categoria": "Feature / Infrastructure",
        },
        {"rule": "Ninguna regla aplica -> Detener -> Solicitar aprobacion.", "categoria": "*"},
    ]
