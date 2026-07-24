"""Turns one real PolicyOutcome (plus the RiskAssessment that produced
it) into the five explicit yes/no questions this Sprint's brief asks
Governance to answer before any execution starts:

    ¿Puede resolverlo solo?
    ¿Necesita aprobacion?
    ¿Debe detenerse?
    ¿Debe dividir la mision?
    ¿Debe generar un PR?

Deliberately a thin translation layer -- orion.governance.policy_engine
already made the real SI/ENTONCES decision; this module only shapes
that decision into the vocabulary the rest of ORION (Runtime, The
Window, CLI) asks for.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion.governance.policy_engine import PolicyAction, PolicyOutcome
from orion.governance.risk_engine import RiskAssessment, RiskLevel

# A mission is only worth splitting when it is both risky AND wide in
# real scope (many affected files or many dependents) -- splitting a
# small, contained CRITICAL change (e.g. one destructive migration
# script) into smaller missions would not actually reduce its real
# risk, only add bookkeeping.
_SPLIT_RISK_LEVELS = (RiskLevel.HIGH, RiskLevel.CRITICAL)


@dataclass
class Decision:
    can_resolve_alone: bool
    needs_approval: bool
    should_stop: bool
    should_split_mission: bool
    should_generate_pr: bool
    rationale: str
    policy_outcome: PolicyOutcome

    @property
    def hard_stop(self) -> bool:
        """True only when the stop is intrinsic to this specific
        change (Architecture/Breaking Change/CRITICAL risk), never
        merely the current Execution Mode's blanket posture -- see
        PolicyOutcome.hard_stop's own docstring for why this
        distinction exists and who reads it."""
        return self.should_stop and self.policy_outcome.hard_stop

    def to_dict(self) -> dict:
        return {
            "can_resolve_alone": self.can_resolve_alone,
            "needs_approval": self.needs_approval,
            "should_stop": self.should_stop,
            "hard_stop": self.hard_stop,
            "should_split_mission": self.should_split_mission,
            "should_generate_pr": self.should_generate_pr,
            "rationale": self.rationale,
            "policy": self.policy_outcome.to_dict(),
        }


def decide(policy_outcome: PolicyOutcome, risk: RiskAssessment) -> Decision:
    can_resolve_alone = policy_outcome.action in (
        PolicyAction.AUTO_APPLY_AND_CONTINUE,
        PolicyAction.CONTINUE,
    )
    should_stop = policy_outcome.action in (
        PolicyAction.STOP_REQUEST_APPROVAL,
        PolicyAction.STOP_HUMAN_DECISION,
    )
    needs_approval = policy_outcome.decision_type in ("approval", "human_decision")

    wide_scope = risk.factors.get("archivos_afectados", 0) >= 2 or risk.factors.get("dependencias", 0) >= 2
    should_split_mission = risk.level in _SPLIT_RISK_LEVELS and wide_scope and not should_stop

    return Decision(
        can_resolve_alone=can_resolve_alone,
        needs_approval=needs_approval,
        should_stop=should_stop,
        should_split_mission=should_split_mission,
        should_generate_pr=policy_outcome.generate_pr,
        rationale=policy_outcome.rule,
        policy_outcome=policy_outcome,
    )
