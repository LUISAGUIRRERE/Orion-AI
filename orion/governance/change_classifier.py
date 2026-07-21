"""Real, rule-based classification of a change/request into one of
the eight categories this Sprint defines. Deliberately not an LLM
call, same reasoning orion.intelligence.task_planner already
documents for its own rule-based decomposition: predictable,
inspectable, no external dependency, and a governance layer whose
category decisions a CEO cannot audit from reading this file would
defeat the entire point of "politicas explicitas, medibles y
auditables."

Classification looks only at the request/mission text (title +
description) -- never at execution results, which do not exist yet at
this point in the Mission Flow (Risk Engine / Policy Engine / Decision
Engine all run *before* the Executor). Real impact data (files
affected, core-purpose touches) belongs to Risk Engine, which already
gets it from orion.intelligence's own ImpactReport -- this module
never re-derives it, keeping "que tipo de cambio es" and "que tan
arriesgado es" as two genuinely separate questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñ0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


class ChangeCategory(str, Enum):
    """Exactly the eight categories this Sprint's brief lists, nothing
    invented on top of it."""

    BUG_FIX = "Bug Fix"
    REFACTOR = "Refactor"
    OPTIMIZATION = "Optimization"
    FEATURE = "Feature"
    BREAKING_CHANGE = "Breaking Change"
    ARCHITECTURE = "Architecture"
    DOCUMENTATION = "Documentation"
    INFRASTRUCTURE = "Infrastructure"


# Real keyword signals, Spanish and English (every real request this
# session has ever seen -- ORION's own user writes almost exclusively
# in Spanish). Order inside each set does not matter; overlap with
# _tokens() is what counts. Kept as *sets* of whole tokens (never
# substrings) so "documenta" never accidentally matches inside an
# unrelated word.
_KEYWORDS: dict[ChangeCategory, set[str]] = {
    ChangeCategory.BREAKING_CHANGE: {
        "breaking", "incompatible", "rompe", "rompimiento", "elimina", "eliminar", "elimino",
        "remove", "removes", "removed", "deprecate", "deprecar", "deprecado", "descontinua",
        "descontinuar", "migracion", "migration", "cambia", "cambiar", "renombra", "renombrar",
    },
    ChangeCategory.ARCHITECTURE: {
        "arquitectura", "architecture", "rediseña", "redisena", "rediseño", "redesign",
        "reestructura", "reestructurar", "restructure", "restructuracion", "stack", "framework",
        "reemplaza", "reemplazar", "replatform", "replatforming", "monolito", "microservicio",
        "microservicios", "capa", "capas",
    },
    ChangeCategory.INFRASTRUCTURE: {
        "infraestructura", "infrastructure", "deploy", "despliega", "desplegar", "ci", "cd",
        "cicd", "docker", "dockerfile", "pipeline", "servidor", "server", "hosting", "vps",
        "dns", "nginx", "kubernetes", "k8s", "terraform", "provisioning",
    },
    ChangeCategory.BUG_FIX: {
        "bug", "bugs", "fix", "arregla", "arreglar", "arreglo", "corrige", "corregir",
        "correccion", "error", "errores", "falla", "fallando", "crash", "crashea", "roto",
        "rota", "defecto", "issue",
    },
    ChangeCategory.OPTIMIZATION: {
        "optimiza", "optimizar", "optimizacion", "optimize", "performance", "rendimiento",
        "velocidad", "lento", "lenta", "acelera", "acelerar", "cache", "cachea", "latencia",
        "latency", "throughput",
    },
    ChangeCategory.REFACTOR: {
        "refactor", "refactoriza", "refactorizar", "refactoring", "reorganiza", "reorganizar",
        "limpia", "limpiar", "cleanup", "simplifica", "simplificar", "duplicado", "duplicada",
    },
    ChangeCategory.DOCUMENTATION: {
        "documenta", "documentar", "documentacion", "documentation", "readme", "docs", "doc",
        "comentarios", "docstring", "docstrings", "manual", "guia",
    },
    ChangeCategory.FEATURE: {
        "nueva", "nuevo", "agrega", "agregar", "añade", "anade", "añadir", "anadir", "add",
        "feature", "funcionalidad", "construye", "construir", "build", "crea", "crear", "cree",
        "implementa", "implementar", "pagina", "página", "page", "modulo", "módulo",
    },
}

# Tie-break priority, most-conservative-first: when two categories
# score equally on the same text, this Sprint's own risk posture
# ("no debe dejar de detenerse por decisiones de arquitectura/negocio
# reales") means it is always safer to over-classify toward the
# category that demands more scrutiny than to under-classify toward
# one that does not.
_TIE_BREAK_ORDER = [
    ChangeCategory.BREAKING_CHANGE,
    ChangeCategory.ARCHITECTURE,
    ChangeCategory.INFRASTRUCTURE,
    ChangeCategory.BUG_FIX,
    ChangeCategory.OPTIMIZATION,
    ChangeCategory.REFACTOR,
    ChangeCategory.FEATURE,
    ChangeCategory.DOCUMENTATION,
]


@dataclass
class Classification:
    category: ChangeCategory
    matched_keywords: list[str]
    scores: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "matched_keywords": self.matched_keywords,
            "scores": self.scores,
        }


def classify_change(text: str) -> Classification:
    """Real keyword-overlap classification -- never a fabricated
    default. When nothing in the text matches any category's
    keywords, this honestly falls back to FEATURE (the most common
    real shape of a request with no explicit fix/refactor/doc/infra
    signal is "build/add something new"), not to a silently
    conservative guess dressed up as certainty."""
    tokens = _tokens(text)
    scores: dict[ChangeCategory, int] = {cat: len(tokens & kws) for cat, kws in _KEYWORDS.items()}

    best_score = max(scores.values())
    if best_score == 0:
        winner = ChangeCategory.FEATURE
        matched: list[str] = []
    else:
        tied = [cat for cat, score in scores.items() if score == best_score]
        winner = next(cat for cat in _TIE_BREAK_ORDER if cat in tied)
        matched = sorted(tokens & _KEYWORDS[winner])

    return Classification(
        category=winner,
        matched_keywords=matched,
        scores={cat.value: score for cat, score in scores.items()},
    )
