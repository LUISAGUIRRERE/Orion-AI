"""The AI Board's six seats, as data -- never a new role, never a new
agent. ``.ai/BOARD.md`` and ``.ai/ROLES.md`` already define who Luis
Aguirre, ChatGPT, Claude, Jules, Nemotron, and AutoClaw are and what
each may and may not do; this module only *names* the stage of a
Mission each of them is real-world responsible for, and points at the
ORION-AI module that already, today, performs that stage's actual
work -- so "que miembro participa en cada etapa" has one real answer
instead of an invented one.

Deliberate, disclosed gap: QA has no dedicated AI Board seat in
``.ai/ROLES.md`` today -- it is an automated gate (orion.execution.
validation), not a person or persona. Rather than inventing a seventh
Board member to fill that gap (which B-011's own "NO crear nuevos
roles" forbids), QA is registered here with ``board_seat=None`` and a
short, honest note. Everything else in this module mirrors a seat that
already exists in ``.ai/ROLES.md``.

``event_signatures`` are real, already-emitted event *types* (see
orion.agents.builder.agent, orion.execution.pipeline,
orion.intelligence.services, orion.experience.services) -- the exact
vocabulary board_router.py reads back from a mission's own recorded
history to derive real progress, never a fabricated status.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoardMember:
    key: str
    display_name: str
    board_seat: str | None
    implemented_by: str
    description: str
    event_signatures: tuple[str, ...]


MEMBERS: dict[str, BoardMember] = {
    "architect": BoardMember(
        key="architect",
        display_name="Architect",
        board_seat="ChatGPT (Chief AI Architect) / Claude (Chief Software Architect)",
        implemented_by="orion.business.services (Business Brain) + orion.intelligence.services (Project Intelligence)",
        description=(
            "Entiende el pedido en el contexto real del negocio y del "
            "repositorio antes de que se escriba una sola linea: a que "
            "empresa/proyecto pertenece, que archivos e impacto tiene, "
            "que plan de pasos sigue. En .ai/BOARD.md este trabajo de "
            "diseno/arquitectura lo proponen ChatGPT y Claude; el codigo "
            "real que ya hace el analisis equivalente por mission es "
            "Business Brain + Project Intelligence (BETA 008/009), sin "
            "duplicarlos aqui."
        ),
        event_signatures=(
            "business_context_loaded",
            "intelligence_brief",
            "planner_ready",
            "analysis_started",
        ),
    ),
    "builder": BoardMember(
        key="builder",
        display_name="Builder",
        board_seat="Jules (Lead Software Engineer)",
        implemented_by="orion.agents.builder.agent + orion.execution.pipeline (Executor step)",
        description=(
            "Implementa unicamente lo ya aprobado -- exactamente lo que "
            ".ai/ROLES.md dice de Jules: nunca fija arquitectura ni "
            "direccion de producto por si mismo. El codigo real es el "
            "Builder agent y el paso de ejecucion del Pipeline."
        ),
        event_signatures=(
            "builder_started",
            "prompt_composed",
            "execution_started",
            "builder_progress",
            "artifact_created",
        ),
    ),
    "reviewer": BoardMember(
        key="reviewer",
        display_name="Reviewer",
        board_seat="Nemotron (Principal Engineering Reviewer)",
        implemented_by="orion.intelligence.reviewer (via orion.intelligence.services.run_review)",
        description=(
            "Revisa el trabajo ya hecho, nunca lo suyo propio -- la "
            "misma regla de no-autorrevision que .ai/ROLES.md fija para "
            "Nemotron. El codigo real es el Reviewer de BETA 008, "
            "ejecutado por el Pipeline antes del commit/PR."
        ),
        event_signatures=("review_completed", "review_failed"),
    ),
    "qa": BoardMember(
        key="qa",
        display_name="QA",
        board_seat=None,
        implemented_by="orion.execution.validation",
        description=(
            "Compuerta automatica de validacion (no es una persona ni "
            "un miembro del AI Board en .ai/ROLES.md hoy -- se registra "
            "aqui con board_seat=None en vez de inventar un septimo "
            "asiento, que B-011 prohibe explicitamente). El codigo real "
            "es el paso de Validation del Pipeline."
        ),
        event_signatures=("validation_started", "validation_passed", "validation_failed"),
    ),
    "gitops": BoardMember(
        key="gitops",
        display_name="GitOps",
        board_seat="AutoClaw (Operations Engineer)",
        implemented_by="orion.execution.git_manager (via orion.execution.pipeline)",
        description=(
            "Automatiza rama/commit/push/PR -- exactamente el rol "
            "operativo que .ai/ROLES.md fija para AutoClaw, incluyendo "
            "que nunca aprueba sus propios cambios operativos. El "
            "codigo real es GitManager, invocado por el Pipeline."
        ),
        event_signatures=("branch_created", "commit_created", "push_completed", "pr_ready"),
    ),
    "experience": BoardMember(
        key="experience",
        display_name="Experience",
        board_seat=None,
        implemented_by="orion.experience.services (Experience Engine)",
        description=(
            "Cierra toda mission con un aprendizaje persistido -- no "
            "tiene asiento humano/IA propio en .ai/ROLES.md (es un "
            "sistema, igual que QA), y se registra asi en vez de "
            "inventarle uno. El codigo real es el Experience Engine de "
            "BETA 004."
        ),
        event_signatures=(
            "experience_generated",
            "pattern_detected",
            "lesson_recorded",
            "recommendation_created",
        ),
    ),
}

ALL_KEYS: tuple[str, ...] = ("architect", "builder", "reviewer", "qa", "gitops", "experience")


def get_member(key: str) -> BoardMember:
    return MEMBERS[key]


def list_members() -> list[BoardMember]:
    return [MEMBERS[k] for k in ALL_KEYS]
