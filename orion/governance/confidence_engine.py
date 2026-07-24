"""Real confidence scoring before a change is executed: how likely is
ORION to get this right, from 0.0 to 1.0.

Consumes -- never recomputes -- two other real, already-existing
sources of truth: orion.intelligence's ImpactReport (tests/impact) and
orion.experience's Knowledge Store (what similar past missions
actually taught ORION). This is deliberately the same "reuse, do not
duplicate" discipline every governance engine in this Sprint follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orion.experience.knowledge_store import list_items
from orion.experience.models import KnowledgeItem
from orion.governance.risk_engine import RiskLevel
from orion.intelligence.impact_analyzer import ImpactReport

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñ0-9]+")

# Real bug found via smoke-testing this Sprint (the same class of bug
# BETA 009's planner.py already hit once with a fuzzy-match fallback):
# a naive token-overlap check without stopword filtering matched "el
# bug de login" against completely unrelated Knowledge Store items
# purely because both strings contain "el"/"de". Excluding common
# Spanish/English stopwords from the *overlap* check (never from the
# tokens themselves, so callers needing raw tokens elsewhere are
# unaffected) means "similar" only ever means real shared vocabulary.
_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "en", "y", "a", "que", "un", "una",
    "unos", "unas", "para", "por", "con", "sin", "su", "sus", "es", "al",
    "lo", "se", "no", "si", "o", "u", "e", "the", "of", "in", "to", "for",
    "and", "a", "an", "is", "on", "with",
}


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def _significant_tokens(text: str) -> set[str]:
    """Same tokenization as _tokens(), minus stopwords -- used
    specifically for similarity/overlap checks, where a shared
    stopword must never count as evidence of real similarity."""
    return _tokens(text) - _STOPWORDS


_RISK_TO_IMPACT_SCORE: dict[RiskLevel, float] = {
    RiskLevel.LOW: 1.0,
    RiskLevel.MEDIUM: 0.7,
    RiskLevel.HIGH: 0.4,
    RiskLevel.CRITICAL: 0.1,
}


@dataclass
class ConfidenceAssessment:
    score: float
    factors: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    similar_items_found: int = 0

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
            "reasons": self.reasons,
            "similar_items_found": self.similar_items_found,
        }


def _tests_factor(impact: ImpactReport | None) -> tuple[float, str | None]:
    if impact is None:
        return 0.3, "Sin datos reales de impacto: no se puede confirmar cobertura de pruebas."
    if impact.related_tests:
        return 0.8, f"{len(impact.related_tests)} prueba(s) relacionada(s) real(es) encontrada(s)."
    return 0.3, "No se encontraron pruebas relacionadas reales para el area afectada."


def _experience_and_similarity_factors(
    request_text: str, project_id: str, knowledge_items: list[KnowledgeItem] | None
) -> tuple[float, float, int, list[str]]:
    """Real experience + similarity factors from the Knowledge Store.
    ``knowledge_items`` is injectable for tests; production callers
    leave it None and this queries orion.experience.knowledge_store
    for real, already-persisted items."""
    reasons: list[str] = []
    items = knowledge_items if knowledge_items is not None else list_items(project_id=project_id or None)

    if not items:
        reasons.append("Sin experiencia previa real registrada: confianza neutral por falta de historial.")
        return 0.5, 0.5, 0, reasons

    experience_score = sum(i.confidence for i in items) / len(items)

    request_tokens = _significant_tokens(request_text)
    similar: list[KnowledgeItem] = []
    for item in items:
        item_tokens = _significant_tokens(f"{item.title} {item.description}")
        if request_tokens & item_tokens:
            similar.append(item)

    if not similar:
        reasons.append("Ninguna experiencia previa comparte keywords reales con esta peticion.")
        similarity_score = 0.5
    else:
        similarity_score = sum(i.confidence for i in similar) / len(similar)
        reasons.append(
            f"{len(similar)} experiencia(s) previa(s) real(es) con overlap de keywords, confianza promedio {similarity_score:.2f}."
        )

    return experience_score, similarity_score, len(similar), reasons


def assess_confidence(
    request_text: str,
    impact: ImpactReport | None,
    risk_level: RiskLevel,
    project_id: str = "",
    knowledge_items: list[KnowledgeItem] | None = None,
) -> ConfidenceAssessment:
    """Real confidence, 0.0-1.0, from four factors: Tests, Experiencias
    anteriores, Similitud con cambios previos, Impacto -- averaged
    with equal weight, never a single factor deciding alone."""
    tests_score, tests_reason = _tests_factor(impact)
    experience_score, similarity_score, similar_count, exp_reasons = _experience_and_similarity_factors(
        request_text, project_id, knowledge_items
    )
    impact_score = _RISK_TO_IMPACT_SCORE[risk_level]

    reasons = [r for r in [tests_reason] if r] + exp_reasons
    reasons.append(f"Nivel de riesgo {risk_level.value} aporta {impact_score:.2f} al factor de impacto.")

    factors = {
        "tests": tests_score,
        "experiencias_anteriores": experience_score,
        "similitud": similarity_score,
        "impacto": impact_score,
    }
    score = sum(factors.values()) / len(factors)
    score = max(0.0, min(1.0, score))

    return ConfidenceAssessment(score=score, factors=factors, reasons=reasons, similar_items_found=similar_count)
