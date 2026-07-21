"""Real, rule-based decomposition of a natural-language request into an
ordered list of concrete steps.

Deliberately not an LLM call: every other deterministic piece of
ORION's own core (Executor's deterministic_local adapter, the
Experience Engine's rule-based confidence scoring, GitManager) follows
the same "predictable, inspectable, no external dependency" pattern,
and a Planner whose behavior a CEO cannot reason about from reading
this file would be a worse fit for "Director Tecnico Autonomo" than
one that is. Real LLM reasoning (Claude Code) still does the actual
implementation work per resulting Mission -- this module only decides
*how many* Missions a request should become and what each one is
about, from real keyword signals in the request text.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñ0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


@dataclass
class PlanStep:
    order: int
    title: str
    description: str
    mission_type: str = "executor"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "title": self.title,
            "description": self.description,
            "mission_type": self.mission_type,
            "tags": self.tags,
        }


@dataclass
class Plan:
    plan_id: str
    request: str
    template: str
    steps: list[PlanStep]
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "request": self.request,
            "template": self.template,
            "steps": [s.to_dict() for s in self.steps],
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        return cls(
            plan_id=data["plan_id"],
            request=data["request"],
            template=data["template"],
            steps=[
                PlanStep(
                    order=s["order"],
                    title=s["title"],
                    description=s["description"],
                    mission_type=s.get("mission_type", "executor"),
                    tags=list(s.get("tags", [])),
                )
                for s in data.get("steps", [])
            ],
            generated_at=data["generated_at"],
        )


# Each template: (trigger keywords, template name, step titles in order).
# Checked in order; the first template whose keywords intersect the
# request's real tokens wins. No match falls through to _DEFAULT_STEPS.
_TEMPLATES: list[tuple[set[str], str, list[str]]] = [
    (
        {"pagina", "página", "page", "vista", "screen", "ui", "interfaz", "seccion", "sección"},
        "pagina_full_stack",
        [
            "Analizar UI y diseño existente",
            "Implementar backend y modelo de datos",
            "Implementar frontend y componentes de interfaz",
            "Exponer o ajustar API",
            "Migraciones de base de datos, si aplica",
            "Escribir pruebas",
            "Revision final antes de PR",
        ],
    ),
    (
        {"api", "endpoint", "endpoints"},
        "api",
        [
            "Disenar contrato de API",
            "Implementar el servicio",
            "Escribir pruebas",
            "Revision final antes de PR",
        ],
    ),
    (
        {"bug", "error", "fix", "corregir", "arreglar", "falla", "rompe", "roto"},
        "bugfix",
        [
            "Reproducir y diagnosticar el problema",
            "Implementar la correccion",
            "Escribir o actualizar pruebas de regresion",
            "Revision final antes de PR",
        ],
    ),
    (
        {"refactor", "refactorizar", "limpiar", "reorganizar"},
        "refactor",
        [
            "Analizar impacto del refactor",
            "Implementar el refactor",
            "Confirmar que las pruebas existentes siguen pasando",
            "Revision final antes de PR",
        ],
    ),
]

_DEFAULT_TEMPLATE = "generico"
_DEFAULT_STEPS = [
    "Implementar el cambio solicitado",
    "Escribir pruebas",
    "Revision final antes de PR",
]


def plan_request(request: str) -> Plan:
    """Real decomposition: matches ``request``'s actual tokens against
    known templates; never returns zero steps (falls back to
    _DEFAULT_STEPS, so a request that matches nothing is still one
    real, executable Mission rather than silently dropped)."""
    tokens = _tokens(request)

    template_name = _DEFAULT_TEMPLATE
    step_titles = _DEFAULT_STEPS
    for keywords, name, titles in _TEMPLATES:
        if tokens & keywords:
            template_name = name
            step_titles = titles
            break

    plan_id = uuid.uuid4().hex[:12]
    steps = [
        PlanStep(
            order=i + 1,
            title=title,
            description=f"{title} -- parte del plan para: {request}",
            tags=[f"plan:{plan_id}", f"plan-step:{i + 1}"],
        )
        for i, title in enumerate(step_titles)
    ]

    return Plan(
        plan_id=plan_id,
        request=request,
        template=template_name,
        steps=steps,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
