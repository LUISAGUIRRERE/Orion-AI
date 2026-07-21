"""Decides, for one Mission, which Board members participate and in
what order -- the coordination layer B-011 asks for, nothing else.

Reuses -- never recomputes -- orion.governance.change_classifier's own
category decision whenever the caller already has one (the normal
case: orion.agents.builder.agent's hook runs this right after its
Governance hook and passes governance_evaluation.classification.
category straight through, the same "no duplicar Governance" reuse
pattern BETA 010 already established for Business Brain's own
ImpactReport). Only falls back to calling classify_change() itself
when no category is supplied (Governance unavailable/failed, or a
dry-run CLI/API call with no mission yet), mirroring every other
fallback in this codebase: never silently guessing, always disclosing
which path ran.

Deliberately rule-based, not an LLM call -- same reasoning
orion.governance.policy_engine and orion.intelligence.task_planner
already document for themselves: predictable, inspectable, no
external dependency, and a coordination layer whose pipeline choice a
CEO cannot audit from reading this file would defeat B-011's own
"decidir automaticamente" requirement just as much as an unauditable
Governance decision would defeat BETA 010's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from orion.board.member_registry import get_member
from orion.governance.change_classifier import ChangeCategory, classify_change

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñ0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


class MissionKind(str, Enum):
    """A Release is not a *change category* (it usually touches no
    files of its own -- see orion.governance.change_classifier's own
    eight categories, none of which is "Release") but a distinct
    *mission kind*: shipping already-reviewed work, not producing new
    work to review. Kept separate from ChangeCategory on purpose,
    the same way BETA 010 keeps "que tipo de cambio es" and "que tan
    arriesgado es" as two genuinely separate questions."""

    REGULAR = "Regular"
    RELEASE = "Release"


_RELEASE_KEYWORDS: set[str] = {
    "release", "lanza", "lanzamiento", "lanzar", "publica", "publicar",
    "publicacion", "despliega", "desplegar", "despliegue", "deploy",
    "produccion", "production", "version", "tag", "etiqueta", "ship",
    "shipping",
}


def classify_mission_kind(text: str) -> MissionKind:
    """Real keyword-overlap detection, same style as
    orion.governance.change_classifier.classify_change -- whole
    tokens only, never a substring match."""
    if _tokens(text) & _RELEASE_KEYWORDS:
        return MissionKind.RELEASE
    return MissionKind.REGULAR


# Deterministic pipeline per ChangeCategory, for MissionKind.REGULAR.
# The two worked examples this Sprint's brief gives verbatim are kept
# exactly as given:
#   - "Nueva Feature" -> Architect, Builder, Reviewer, QA, GitOps, Experience
#   - "Bug pequeño"   -> Builder, QA, Experience
# The remaining six categories are filled in following the same
# reasoning the brief's own two examples establish: Architect only
# joins when real design/direction is at stake; GitOps only joins when
# the change actually ships (a pure Architecture discussion does not
# commit/push anything of its own yet); every category ends in
# Experience, since every Mission -- successful or not -- must leave a
# real, persisted lesson (BETA 004's own unconditional guarantee).
PIPELINE_BY_CATEGORY: dict[ChangeCategory, tuple[str, ...]] = {
    ChangeCategory.BUG_FIX: ("builder", "qa", "experience"),
    ChangeCategory.REFACTOR: ("builder", "reviewer", "qa", "experience"),
    ChangeCategory.OPTIMIZATION: ("builder", "qa", "experience"),
    ChangeCategory.FEATURE: ("architect", "builder", "reviewer", "qa", "gitops", "experience"),
    ChangeCategory.BREAKING_CHANGE: ("architect", "builder", "reviewer", "qa", "gitops", "experience"),
    ChangeCategory.ARCHITECTURE: ("architect", "reviewer", "experience"),
    ChangeCategory.DOCUMENTATION: ("builder", "reviewer", "gitops", "experience"),
    ChangeCategory.INFRASTRUCTURE: ("architect", "builder", "reviewer", "qa", "gitops", "experience"),
}

# The third worked example, verbatim: "Release -> Reviewer -> GitOps ->
# Experience". A Release mission overrides the category-based pipeline
# entirely (it is not "about" any single category of change -- it is
# about shipping whatever already passed review).
RELEASE_PIPELINE: tuple[str, ...] = ("reviewer", "gitops", "experience")


@dataclass(frozen=True)
class BoardPipeline:
    kind: MissionKind
    category: ChangeCategory | None
    stages: tuple[str, ...]
    rule: str

    def summary_text(self) -> str:
        stage_names = " -> ".join(get_member(s).display_name for s in self.stages)
        return f"{self.rule}: {stage_names}"


def decide_pipeline(request_text: str, category: ChangeCategory | None = None) -> BoardPipeline:
    """The one real decision this module makes. ``category`` should be
    the already-computed orion.governance.change_classifier category
    for this same request whenever the caller has one -- passing it
    skips a second, duplicate classify_change() call. When it is None,
    this classifies the text itself (dry runs, or Governance having
    failed/being unavailable for this Mission)."""
    kind = classify_mission_kind(request_text)
    if kind is MissionKind.RELEASE:
        return BoardPipeline(
            kind=kind,
            category=category,
            stages=RELEASE_PIPELINE,
            rule="Release detectado por palabra clave",
        )

    resolved_category = category
    used_own_classification = False
    if resolved_category is None:
        resolved_category = classify_change(request_text).category
        used_own_classification = True

    stages = PIPELINE_BY_CATEGORY.get(resolved_category, PIPELINE_BY_CATEGORY[ChangeCategory.FEATURE])
    rule = (
        f"Categoria '{resolved_category.value}'"
        + (" (clasificada por Board, sin Governance disponible)" if used_own_classification else " (reutilizada de Governance)")
    )
    return BoardPipeline(kind=kind, category=resolved_category, stages=stages, rule=rule)
