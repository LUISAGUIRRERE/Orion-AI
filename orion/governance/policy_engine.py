"""The real policy table: ordered SI/ENTONCES rules combining Change
Category, Risk, Confidence and the current Execution Mode into one
concrete PolicyOutcome. Deliberately a plain ordered list of ``if``
checks -- ORION's Director Tecnico Autonomo philosophy this Sprint
asks for ("No emociones. No intuicion. Politicas.") means every
decision must be traceable to one specific, readable rule, never a
black-box score threshold alone.

Rules are evaluated top to bottom; the first one that matches wins
(more specific/conservative rules are listed first on purpose, so a
Breaking Change can never accidentally fall through to a permissive
generic rule below it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from orion.governance import autonomy
from orion.governance.change_classifier import ChangeCategory
from orion.governance.config import GovernanceConfig
from orion.governance.confidence_engine import ConfidenceAssessment
from orion.governance.execution_mode import ModeProfile
from orion.governance.risk_engine import RiskAssessment, RiskLevel


class PolicyAction(str, Enum):
    AUTO_APPLY_AND_CONTINUE = "auto_apply_and_continue"
    CONTINUE = "continue"
    STOP_REQUEST_APPROVAL = "stop_request_approval"
    STOP_HUMAN_DECISION = "stop_human_decision"


@dataclass
class PolicyOutcome:
    action: PolicyAction
    decision_type: str  # "none" | "approval" | "human_decision"
    create_test: bool
    run_suite: bool
    continue_after: bool
    generate_pr: bool
    rule: str
    # True only for a stop that is intrinsic to *this specific change*
    # (Architecture, Breaking Change, CRITICAL risk -- rules 1-3
    # below): a real, per-change safety signal. False for a stop that
    # comes only from the current Execution Mode's blanket posture
    # (rule 4, MODE_DEVELOPMENT's "pregunta todo") or the generic
    # fallback -- those are real decisions too (always audited, always
    # queued for approval), but orion.runtime's own Mission Flow
    # integration only hard-blocks the Pipeline on hard_stop=True, so
    # introducing Governance never silently changes the outcome of
    # every Mission ORION has ever run under the conservative default
    # mode. See orion.agents.builder.agent's Governance hook.
    hard_stop: bool = False

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "decision_type": self.decision_type,
            "create_test": self.create_test,
            "run_suite": self.run_suite,
            "continue_after": self.continue_after,
            "generate_pr": self.generate_pr,
            "rule": self.rule,
            "hard_stop": self.hard_stop,
        }


def evaluate_policy(
    category: ChangeCategory,
    risk: RiskAssessment,
    confidence: ConfidenceAssessment,
    mode_profile: ModeProfile,
    config: GovernanceConfig | None = None,
) -> PolicyOutcome:
    config = config or GovernanceConfig.from_env()
    generate_pr = mode_profile.generates_pull_request_instead_of_direct_change

    # Rule 1 -- Architecture always waits for an explicit human
    # decision, regardless of risk/confidence/mode. This Sprint's own
    # Caso 4 ("Cambio de arquitectura. Debe esperar decision humana.")
    # names this exact category, not a risk level.
    if category is ChangeCategory.ARCHITECTURE:
        return PolicyOutcome(
            action=PolicyAction.STOP_HUMAN_DECISION,
            decision_type="human_decision",
            create_test=False,
            run_suite=False,
            continue_after=False,
            generate_pr=generate_pr,
            rule="Architecture -> Detener -> Esperar decision humana.",
            hard_stop=True,
        )

    # Rule 2 -- Breaking Change always stops and requests approval,
    # the exact second worked example in this Sprint's brief.
    if category is ChangeCategory.BREAKING_CHANGE:
        return PolicyOutcome(
            action=PolicyAction.STOP_REQUEST_APPROVAL,
            decision_type="approval",
            create_test=False,
            run_suite=False,
            continue_after=False,
            generate_pr=generate_pr,
            rule="Breaking Change -> Detener -> Solicitar aprobacion.",
            hard_stop=True,
        )

    # Rule 3 -- CRITICAL risk always stops for approval, no matter how
    # small the category or how confident ORION is: a Bug Fix whose
    # real blast radius turned out huge is not "local" anymore.
    if risk.level is RiskLevel.CRITICAL:
        return PolicyOutcome(
            action=PolicyAction.STOP_REQUEST_APPROVAL,
            decision_type="approval",
            create_test=False,
            run_suite=False,
            continue_after=False,
            generate_pr=generate_pr,
            rule="Riesgo CRITICAL -> Detener -> Solicitar aprobacion, sin importar la categoria.",
            hard_stop=True,
        )

    # Rule 4 -- the current mode itself forbids autonomous action for
    # this category (MODE_DEVELOPMENT always; other modes for the
    # always-ask categories, already covered above, or when the mode
    # simply cannot apply local fixes at all).
    if not autonomy.can_act_autonomously(mode_profile, category):
        return PolicyOutcome(
            action=PolicyAction.STOP_REQUEST_APPROVAL,
            decision_type="approval",
            create_test=False,
            run_suite=False,
            continue_after=False,
            generate_pr=generate_pr,
            rule=f"Modo {mode_profile.mode} no permite accion autonoma para '{category.value}'.",
        )

    # Rule 5 -- the exact first worked example: Bug Fix AND riesgo LOW
    # AND confianza > threshold (0.95 by default) -> corregir
    # automaticamente -> crear test -> ejecutar suite -> continuar.
    if (
        category is ChangeCategory.BUG_FIX
        and risk.level is RiskLevel.LOW
        and confidence.score > config.high_confidence_threshold
    ):
        return PolicyOutcome(
            action=PolicyAction.AUTO_APPLY_AND_CONTINUE,
            decision_type="none",
            create_test=mode_profile.can_create_tests_automatically,
            run_suite=True,
            continue_after=mode_profile.can_continue_after_fix,
            generate_pr=generate_pr,
            rule="Bug Fix AND Riesgo LOW AND Confianza > umbral -> Corregir automaticamente -> Crear test -> Ejecutar suite -> Continuar.",
        )

    # Rule 6 -- any other never-ask category (Refactor, Optimization,
    # Documentation, and Bug Fix that did not clear rule 5's higher
    # bar) with LOW/MEDIUM risk and reasonable confidence: apply and
    # continue, still creating a regression test for a real Bug Fix.
    if (
        autonomy.is_never_ask_category(category)
        and risk.level in (RiskLevel.LOW, RiskLevel.MEDIUM)
        and confidence.score >= 0.7
        and mode_profile.can_apply_local_fixes
    ):
        return PolicyOutcome(
            action=PolicyAction.AUTO_APPLY_AND_CONTINUE,
            decision_type="none",
            create_test=mode_profile.can_create_tests_automatically and category is ChangeCategory.BUG_FIX,
            run_suite=True,
            continue_after=mode_profile.can_continue_after_fix,
            generate_pr=generate_pr,
            rule=f"'{category.value}' AND Riesgo {risk.level.value} AND Confianza >= 0.7 -> Aplicar -> Ejecutar suite -> Continuar.",
        )

    # Rule 6.5 -- HIGH risk that is real but *wide*, not uncertain:
    # good confidence and a mode that can apply local fixes means the
    # risk here comes from touching many files/dependents, not from
    # ORION being unsure what to do. Rather than stopping outright,
    # let it proceed -- orion.governance.decision_engine.decide() is
    # the one that actually turns this exact shape (HIGH risk + wide
    # scope + not stopped) into "should_split_mission=True", so the
    # real mitigation for size-driven risk is decomposition, not a
    # blanket halt.
    if (
        risk.level is RiskLevel.HIGH
        and confidence.score >= 0.6
        and mode_profile.can_apply_local_fixes
        and not mode_profile.requires_approval_for_everything
    ):
        return PolicyOutcome(
            action=PolicyAction.CONTINUE,
            decision_type="none",
            create_test=False,
            run_suite=True,
            continue_after=mode_profile.can_continue_after_fix,
            generate_pr=generate_pr,
            rule=f"'{category.value}' AND Riesgo HIGH (por alcance) AND Confianza >= 0.6 -> Continuar, candidato a dividir la mision.",
        )

    # Rule 7 -- Feature/Infrastructure (or a never-ask category that
    # did not clear rule 6's confidence bar) with acceptable risk:
    # this Sprint's own Caso 3 ("Refactor seguro. Debe continuar.")
    # covers the safe-continue shape even when nothing needs "fixing"
    # -- ORION proceeds without pausing, but does not silently invent
    # a fix/test cycle for a category that is not a correction.
    if risk.level in (RiskLevel.LOW, RiskLevel.MEDIUM) and confidence.score >= 0.5 and mode_profile.can_apply_local_fixes:
        return PolicyOutcome(
            action=PolicyAction.CONTINUE,
            decision_type="none",
            create_test=False,
            run_suite=True,
            continue_after=mode_profile.can_continue_after_fix,
            generate_pr=generate_pr,
            rule=f"'{category.value}' AND Riesgo {risk.level.value} AND Confianza >= 0.5 -> Continuar sin pausa.",
        )

    # Default -- anything that fell through every rule above (HIGH
    # risk, low confidence, or a mode that cannot apply local fixes at
    # all) stops honestly rather than guessing.
    return PolicyOutcome(
        action=PolicyAction.STOP_REQUEST_APPROVAL,
        decision_type="approval",
        create_test=False,
        run_suite=False,
        continue_after=False,
        generate_pr=generate_pr,
        rule=f"Ninguna regla de autonomia aplica ('{category.value}', riesgo {risk.level.value}, confianza {confidence.score:.2f}) -> Detener -> Solicitar aprobacion.",
    )
