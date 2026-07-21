"""The AI Board's six Mission-pipeline stages, as data -- never a new
role, never a new agent. This module only *names* the stage of a
Mission each stage is real-world responsible for, and points at the
ORION-AI module that already, today, performs that stage's actual
work -- so "que miembro participa en cada etapa" has one real answer
instead of an invented one.

G-012 REMEDIATION (after Codex REQUEST CHANGES): this module used to
hold a second, hardcoded copy of Board member names/roles as a
"fallback" whenever ``.ai/board.yaml`` failed to load, and cached the
resolved result once at import time for the life of the process.
Codex correctly flagged both as real problems:

  HIGH #1 -- a hardcoded fallback name/role *is* a second operational
  source of truth, even if the strings started out identical to
  board.yaml's. If board.yaml cannot be loaded, this module must not
  fabricate an identity: it now returns an explicit, structured
  failure (``board_seat=None`` + ``board_seat_error=<message>``)
  instead.

  HIGH #2 -- a module-level snapshot loaded once at import time means
  every consumer for the rest of the process's life sees whatever
  board.yaml looked like at import time, not its current content.
  There is now no cross-call cache anywhere in this module:
  ``get_member()``/``list_members()`` resolve the seat label fresh,
  every single call, directly against ``orion.board.canonical``.

This also cleanly separates two concerns Codex named directly:
*pipeline structure* (which stage exists, what real module implements
it, which events indicate it ran -- all static B-011 facts, entirely
independent of board.yaml) from *Board membership* (who currently
holds that seat, per ``.ai/board.yaml`` -- resolved fresh, never
baked into the static pipeline data).

Deliberate, disclosed gap: QA and Experience have no dedicated AI
Board seat in ``.ai/board.yaml`` today -- they are automated gates/
systems (orion.execution.validation, orion.experience.services), not
people or personas. Rather than inventing seats for them (which
B-011's own "NO crear nuevos roles" forbids), their
``board_seat_member_ids`` is simply empty.

``event_signatures`` are real, already-emitted event *types* (see
orion.agents.builder.agent, orion.execution.pipeline,
orion.intelligence.services, orion.experience.services) -- the exact
vocabulary board_router.py reads back from a mission's own recorded
history to derive real progress, never a fabricated status.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from orion.board import canonical


@dataclass(frozen=True)
class BoardMember:
    key: str
    display_name: str
    # References into .ai/board.yaml's member ids -- never a resolved
    # string baked in at definition time. Empty means "no dedicated
    # AI Board seat" (QA, Experience), the same disclosed gap as
    # before, now structural rather than a bare ``None`` with no
    # record of *why*.
    board_seat_member_ids: tuple[str, ...]
    implemented_by: str
    description: str
    event_signatures: tuple[str, ...]
    # Resolved fresh by get_member()/list_members() on every call --
    # never set directly, never cached across calls. ``board_seat`` is
    # the human-readable label when resolution succeeded (or None if
    # this stage has no dedicated seat, or resolution failed).
    # ``board_seat_error`` is the real, undecorated error message when
    # resolution was attempted and failed -- never fabricated text
    # standing in for a name.
    board_seat: str | None = None
    board_seat_error: str | None = None


_TEMPLATES: dict[str, BoardMember] = {
    "architect": BoardMember(
        key="architect",
        display_name="Architect",
        board_seat_member_ids=("chatgpt", "claude"),
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
        board_seat_member_ids=("jules",),
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
        board_seat_member_ids=("nemotron",),
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
        board_seat_member_ids=(),
        implemented_by="orion.execution.validation",
        description=(
            "Compuerta automatica de validacion (no es una persona ni "
            "un miembro del AI Board hoy -- se registra aqui sin "
            "asiento en vez de inventar un septimo, que B-011 prohibe "
            "explicitamente). El codigo real es el paso de Validation "
            "del Pipeline."
        ),
        event_signatures=("validation_started", "validation_passed", "validation_failed"),
    ),
    "gitops": BoardMember(
        key="gitops",
        display_name="GitOps",
        board_seat_member_ids=("autoclaw",),
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
        board_seat_member_ids=(),
        implemented_by="orion.experience.services (Experience Engine)",
        description=(
            "Cierra toda mission con un aprendizaje persistido -- no "
            "tiene asiento humano/IA propio (es un sistema, igual que "
            "QA), y se registra asi en vez de inventarle uno. El "
            "codigo real es el Experience Engine de BETA 004."
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


def _resolve_seat(template: BoardMember) -> BoardMember:
    """Resolves ``board_seat`` fresh against the canonical source --
    never cached, never fabricated. Called anew on every
    get_member()/list_members() invocation, so every consumer always
    sees the current, on-disk .ai/board.yaml, not a stale snapshot."""
    if not template.board_seat_member_ids:
        return template  # no dedicated seat by design -- not a failure

    try:
        config = canonical.load_board_config()
    except canonical.BoardConfigurationError as exc:
        return replace(template, board_seat=None, board_seat_error=str(exc))

    labels: list[str] = []
    missing: list[str] = []
    for member_id in template.board_seat_member_ids:
        member = config.get(member_id)
        if member is None:
            missing.append(member_id)
        else:
            labels.append(member.seat_label())

    if missing:
        return replace(
            template,
            board_seat=None,
            board_seat_error=f"canonical board.yaml has no member(s) with id(s): {', '.join(missing)}",
        )

    return replace(template, board_seat=" / ".join(labels), board_seat_error=None)


def get_member(key: str) -> BoardMember:
    return _resolve_seat(_TEMPLATES[key])


def list_members() -> list[BoardMember]:
    return [_resolve_seat(_TEMPLATES[k]) for k in ALL_KEYS]


# Backward-compatible name: a dict of the *static pipeline templates*
# (key, display_name, implemented_by, description, event_signatures,
# board_seat_member_ids) -- never resolved seat data, since that must
# never be a fixed, cached snapshot (HIGH #2). Anything that needs the
# current resolved board_seat must call get_member()/list_members().
MEMBERS: dict[str, BoardMember] = dict(_TEMPLATES)
