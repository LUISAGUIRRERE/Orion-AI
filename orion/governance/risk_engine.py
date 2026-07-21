"""Real risk assessment before a change is executed.

Consumes -- never recomputes -- orion.intelligence's own real
ImpactReport (affected files/modules, related tests, complexity),
exactly the same "no duplicar Project Intelligence" discipline
orion.business already established for BETA 009. This module's only
real job is to turn that already-computed impact data (plus the
change's category and, optionally, real historical outcomes from
orion.governance.audit) into one of the four risk levels this
Sprint's brief asks for.

Deliberately points-based and inspectable, not a black-box score: any
of the six named factors (Archivos afectados, Dependencias, Cobertura
de pruebas, Complejidad, Historial, Impacto) can be read straight off
a RiskAssessment.factors dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from orion.governance.change_classifier import ChangeCategory
from orion.intelligence.impact_analyzer import ImpactReport


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_LEVEL_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _LEVEL_ORDER.index(a) >= _LEVEL_ORDER.index(b) else b


def _level_from_points(points: int) -> RiskLevel:
    if points <= 1:
        return RiskLevel.LOW
    if points <= 3:
        return RiskLevel.MEDIUM
    if points <= 5:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


# A change in these categories is never trusted to score its way down
# to a low risk level purely on small-impact numbers: their real-world
# blast radius (irreversibility for Breaking Change, cross-cutting
# scope for Architecture, external-system exposure for Infrastructure)
# is not something a file-count/complexity heuristic can see.
_CATEGORY_FLOOR: dict[ChangeCategory, RiskLevel] = {
    ChangeCategory.BREAKING_CHANGE: RiskLevel.CRITICAL,
    ChangeCategory.ARCHITECTURE: RiskLevel.HIGH,
    ChangeCategory.INFRASTRUCTURE: RiskLevel.MEDIUM,
}

# Real, disclosed thresholds (not fabricated precision): the same
# 3/10-file-count breakpoints orion.intelligence.impact_analyzer
# already uses for its own bajo/medio/alto, expressed here as points
# so they combine additively with the other five factors instead of
# each one alone deciding the whole level.
_FILE_COUNT_BREAKPOINTS = (3, 10)
_MODULE_COUNT_BREAKPOINTS = (3, 10)
_COMPLEXITY_BREAKPOINTS = (20, 60)


def _bucket(value: int, breakpoints: tuple[int, int]) -> int:
    low, high = breakpoints
    if value <= low:
        return 0
    if value <= high:
        return 1
    return 2


@dataclass
class RiskAssessment:
    level: RiskLevel
    points: int
    factors: dict[str, int]
    reasons: list[str] = field(default_factory=list)
    impact_available: bool = True

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "points": self.points,
            "factors": self.factors,
            "reasons": self.reasons,
            "impact_available": self.impact_available,
        }


def assess_risk(
    category: ChangeCategory,
    impact: ImpactReport | None,
    history_failure_count: int = 0,
    history_success_count: int = 0,
) -> RiskAssessment:
    """Real risk assessment. ``impact`` is orion.intelligence's own
    ImpactReport for this change (None when no real repository/impact
    data is available yet -- e.g. a Business Brain company with no
    technical project linked, same honest gap BETA 009 already
    reports as "riesgo desconocido" rather than fabricating one).
    ``history_failure_count``/``history_success_count`` are real counts
    of past orion.governance.audit entries for this same category
    (never inferred, always passed in by the caller from real data).
    """
    reasons: list[str] = []

    if impact is None:
        # No real impact data: never assume LOW just because nothing
        # was measured. MEDIUM is the honest floor for "unmeasured",
        # exactly the same posture orion.business.services takes when
        # it reports risk "desconocido" instead of guessing "bajo".
        factors = {
            "archivos_afectados": 0,
            "dependencias": 0,
            "cobertura_de_pruebas": 0,
            "complejidad": 0,
            "historial": 0,
            "impacto": 1,
        }
        reasons.append("No hay ImpactReport real disponible: piso conservador MEDIUM, nunca LOW sin datos.")
        level = RiskLevel.MEDIUM
    else:
        file_points = _bucket(len(impact.affected_files), _FILE_COUNT_BREAKPOINTS)
        module_points = _bucket(len(impact.affected_modules), _MODULE_COUNT_BREAKPOINTS)
        complexity_points = _bucket(impact.complexity_sum, _COMPLEXITY_BREAKPOINTS)
        coverage_points = 0 if impact.related_tests else 1
        if coverage_points:
            reasons.append("Sin pruebas relacionadas encontradas: riesgo de cobertura.")

        # "Impacto" is deliberately a distinct signal from "Archivos
        # afectados": it reuses orion.intelligence's own already-
        # synthesized bajo/medio/alto verdict (which itself already
        # factors in core-purpose-without-tests escalation, see
        # impact_analyzer.compute_impact) rather than re-deriving raw
        # file count a second time under a different name.
        impact_points = {"bajo": 0, "medio": 1, "alto": 2}.get(impact.risk, 1)

        history_points = 0
        if history_failure_count > 0:
            history_points = 1
            reasons.append(
                f"Historial real: {history_failure_count} resultado(s) fallido(s) previos en esta categoria."
            )
        elif history_success_count >= 3:
            history_points = -1
            reasons.append(
                f"Historial real: {history_success_count} resultado(s) exitosos previos en esta categoria."
            )

        points = max(
            0,
            file_points + module_points + complexity_points + coverage_points + impact_points + history_points,
        )
        level = _level_from_points(points)

        factors = {
            "archivos_afectados": file_points,
            "dependencias": module_points,
            "cobertura_de_pruebas": coverage_points,
            "complejidad": complexity_points,
            "historial": history_points,
            "impacto": impact_points,
        }

    floor = _CATEGORY_FLOOR.get(category)
    if floor is not None and _LEVEL_ORDER.index(floor) > _LEVEL_ORDER.index(level):
        reasons.append(f"Categoria '{category.value}' impone un piso minimo de riesgo {floor.value}.")
        level = floor

    points_total = max(0, sum(factors.values())) if impact is not None else 1

    return RiskAssessment(
        level=level,
        points=points_total,
        factors=factors,
        reasons=reasons,
        impact_available=impact is not None,
    )
