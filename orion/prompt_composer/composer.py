"""The Prompt Composer's core orchestration: Mission + Project +
Repository -> PromptPackage.

Deliberately deterministic and template-based -- this module never
calls an AI provider itself. Its job is discovery and structuring
only; producing the actual best possible *content* of each section
(a genuinely smart suggested plan, a genuinely well-reasoned execution
prompt) is real, future work once this v1 has been exercised against
real missions. That boundary is intentional: this Sprint builds the
context-discovery engine, not a second AI agent bolted onto it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from orion.bridge.models import Mission
from orion.prompt_composer import discovery
from orion.prompt_composer.discovery import DiscoveredDoc
from orion.prompt_composer.models import (
    ArchitectureRules,
    BusinessContext,
    CodingStandards,
    ExecutionPrompt,
    FileReference,
    MissionSummary,
    ProjectSummary,
    PromptPackage,
    SuggestedPlan,
    TechnicalContext,
)
from orion.projects.models import Project

_ACCEPTANCE_MARKERS = ("criterio de aceptacion", "criterios de aceptacion", "acceptance criteria")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _docs_by_category(docs: list[DiscoveredDoc], category: str) -> list[DiscoveredDoc]:
    return [d for d in docs if d.category == category]


def _build_business_context(project: Project | None) -> BusinessContext:
    if project is None:
        return BusinessContext(
            project_name="Orion-AI",
            project_description="El propio kernel de ORION -- esta mision no pertenece a un proyecto registrado.",
        )
    return BusinessContext(
        project_name=project.name,
        project_description=project.description,
        business_unit=str(project.metadata.get("business_unit_slug", "")),
    )


def _build_technical_context(docs: list[DiscoveredDoc], project_status: dict[str, object]) -> TechnicalContext:
    def summary_of(category: str) -> str:
        matches = _docs_by_category(docs, category)
        return matches[0].excerpt if matches else ""

    token_docs = _docs_by_category(docs, "design_tokens")
    return TechnicalContext(
        architecture_summary=summary_of("architecture"),
        design_system_summary=summary_of("design_system"),
        design_tokens_summary="; ".join(d.path for d in token_docs),
        content_guide_summary=summary_of("content_guide"),
        project_status=project_status,
    )


def _build_coding_standards(docs: list[DiscoveredDoc]) -> CodingStandards:
    relevant = [d for d in docs if d.category in ("team", "agent_context", "content_guide")]
    sources = [FileReference(path=d.path, reason=f"documento de tipo '{d.category}'") for d in relevant]
    notes: list[str] = []
    if any(d.category == "agent_context" for d in docs):
        notes.append(
            "Existe un archivo de contexto para agentes (CLAUDE.md/AGENTS.md) en este repositorio: "
            "su contenido tiene prioridad sobre cualquier convencion generica de este PromptPackage."
        )
    if not sources:
        notes.append(
            "No se encontraron documentos de estandares explicitos (TEAM.md, CLAUDE.md/AGENTS.md, "
            "content guide). Seguir las convenciones ya presentes en el codigo existente del repositorio."
        )
    return CodingStandards(sources=sources, notes=notes)


def _build_architecture_rules(docs: list[DiscoveredDoc]) -> ArchitectureRules:
    relevant = [d for d in docs if d.category in ("architecture", "adr", "design_system")]
    sources = [FileReference(path=d.path, reason=f"documento de tipo '{d.category}'") for d in relevant]
    notes: list[str] = []
    if not sources:
        notes.append(
            "No se encontro documentacion de arquitectura explicita (docs/ARCHITECTURE.md, ADRs, "
            "design system). Inferir la estructura a partir de los archivos relacionados antes de "
            "introducir un patron nuevo."
        )
    return ArchitectureRules(sources=sources, notes=notes)


def _extract_acceptance_criteria(mission: Mission) -> list[str]:
    text = mission.description or ""
    lowered = text.lower()
    for marker in _ACCEPTANCE_MARKERS:
        idx = lowered.find(marker)
        if idx == -1:
            continue
        tail = text[idx:].split("\n\n")[0]
        lines = [line.strip(" -•").strip() for line in tail.split("\n") if line.strip()]
        criteria = lines[1:] if len(lines) > 1 else lines
        if criteria:
            return criteria
    if text:
        return [f"El entregable coincide con lo descrito en la mision: {text[:280]}"]
    return [f"La mision '{mission.title}' se considera completa cuando pasa las validaciones del Execution Pipeline."]


def _build_suggested_plan(
    mission: Mission, related_files: list[FileReference], docs: list[DiscoveredDoc]
) -> SuggestedPlan:
    steps = ["Leer el contexto de negocio y tecnico provisto en este PromptPackage."]
    if docs:
        steps.append(f"Revisar los {len(docs)} documento(s) de contexto descubiertos antes de escribir nada.")
    if related_files:
        steps.append(f"Revisar los {len(related_files)} archivo(s) ya relacionados con esta mision.")
    steps.append(f"Implementar el trabajo descrito por la mision: {mission.title}.")
    steps.append("Validar el resultado contra los criterios de aceptacion.")
    steps.append("Dejar el entregable listo para el commit del Execution Pipeline.")
    return SuggestedPlan(steps=steps)


def _build_execution_prompt(
    mission: Mission,
    business_context: BusinessContext,
    technical_context: TechnicalContext,
    acceptance_criteria: list[str],
    suggested_plan: SuggestedPlan,
) -> ExecutionPrompt:
    lines = [
        f"Mision: {mission.title}",
        f"Descripcion: {mission.description or '(sin descripcion adicional)'}",
        f"Proyecto: {business_context.project_name} — {business_context.project_description or '(sin descripcion)'}",
    ]
    if technical_context.architecture_summary:
        lines.append("Contexto de arquitectura disponible: si (ver architecture_rules.sources).")
    if technical_context.design_system_summary:
        lines.append("Sistema de diseno disponible: si (ver technical_context.design_system_summary).")
    lines.append("Criterios de aceptacion:")
    lines.extend(f"  - {c}" for c in acceptance_criteria)
    lines.append("Plan sugerido:")
    lines.extend(f"  {i + 1}. {s}" for i, s in enumerate(suggested_plan.steps))
    instructions = "\n".join(lines)

    constraints = [
        "No modificar produccion sin autorizacion explicita.",
        "Respetar el sistema de diseno y los estandares existentes descubiertos en este paquete.",
        "El resultado debe ser codigo o contenido real, no un placeholder, salvo que la mision indique lo contrario.",
    ]
    return ExecutionPrompt(instructions=instructions, constraints=constraints)


def compose(
    mission: Mission,
    project: Project | None,
    repo_root: Path,
    all_missions: list[Mission],
) -> PromptPackage:
    """Build the full PromptPackage for a single mission.

    Pure with respect to global state: every input it needs (the
    mission, its project if any, the repository to search, and the
    full mission list for the "related missions" signal) is passed in
    explicitly, which is what makes this function directly testable
    without touching ORION's live Bridge/Registry storage. Resolving
    those inputs from a bare Mission is orion.prompt_composer.services'
    job, not this module's.
    """
    docs = discovery.discover_docs(repo_root)
    related_files = discovery.discover_related_files(mission)
    related_missions = discovery.discover_related_missions(mission, all_missions)
    recent_commits = discovery.discover_recent_commits(repo_root)
    related_prs = discovery.discover_related_pull_requests(mission, repo_root)
    project_status = discovery.discover_project_status(project)

    business_context = _build_business_context(project)
    technical_context = _build_technical_context(docs, project_status)
    coding_standards = _build_coding_standards(docs)
    architecture_rules = _build_architecture_rules(docs)
    acceptance_criteria = _extract_acceptance_criteria(mission)
    suggested_plan = _build_suggested_plan(mission, related_files, docs)
    execution_prompt = _build_execution_prompt(
        mission, business_context, technical_context, acceptance_criteria, suggested_plan
    )

    return PromptPackage(
        mission=MissionSummary.from_mission(mission),
        project=ProjectSummary.from_project(project) if project else None,
        business_context=business_context,
        technical_context=technical_context,
        coding_standards=coding_standards,
        architecture_rules=architecture_rules,
        related_files=related_files,
        related_missions=related_missions,
        recent_commits=recent_commits,
        related_pull_requests=related_prs,
        acceptance_criteria=acceptance_criteria,
        suggested_plan=suggested_plan,
        execution_prompt=execution_prompt,
        generated_at=_now_iso(),
    )
