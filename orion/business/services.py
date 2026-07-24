"""Public entry points for orion.business -- the only module the CLI
(bin/orion), the Runtime (orion.runtime), and The Window are allowed
to call directly. Same "one entry point per subsystem" convention
orion.executor.services/orion.experience.services/orion.intelligence.services
already establish.

Business Brain consumes orion.intelligence (BETA 008) here, and only
here -- never re-implements repository analysis, impact scoring, or
task planning. It only decides *which* company/project a request
belongs to and layers real business context (branding, goals,
roadmap, remembered facts) on top before Project Intelligence ever
runs.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import brand as brand_module
from orion.business import company as company_module
from orion.business import decisions as decisions_module
from orion.business import documents as documents_module
from orion.business import goals as goals_module
from orion.business import knowledge as knowledge_module
from orion.business import memory as memory_module
from orion.business import planner
from orion.business import project as project_module
from orion.business import roadmap as roadmap_module
from orion.business.brand import Brand
from orion.business.company import Company
from orion.business.config import BusinessConfig
from orion.business.decisions import Decision
from orion.business.documents import BusinessDocument
from orion.business.goals import Goal
from orion.business.knowledge import KnowledgeItem
from orion.business.planner import BusinessContext, ResolvedContext
from orion.business.project import BusinessProject
from orion.business.roadmap import RoadmapItem
from orion.intelligence import services as intelligence_services
from orion.intelligence.services import IntelligenceBrief
from orion.projects import registry as project_registry

AUTHOR = "BusinessBrain"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(mission_id: str | None, event_type: str, message: str) -> None:
    """Real event emission, reusing orion.runtime.events.emit (see
    orion.intelligence.services._emit -- same convention, never a
    parallel event system). No-op when there is no mission_id (a
    standalone `orion company`/`orion goals` CLI call, for instance)."""
    if not mission_id:
        return
    from orion.runtime import events as runtime_events

    runtime_events.emit(mission_id, event_type, message, AUTHOR)


# ---------------------------------------------------------------------------
# Company / Project / Brand / Goals / Roadmap / Knowledge / Memory /
# Documents / Decisions -- thin CRUD wrappers. All real business logic
# for each concern lives in that concern's own module; this is only
# the fan-out every caller (CLI/API/Window/Runtime) is allowed to use.
# ---------------------------------------------------------------------------


def create_company(company_id: str, name: str, **fields) -> Company:
    return company_module.create_company(company_id, name, **fields)


def get_company(company_id: str) -> Company | None:
    return company_module.load_company(company_id)


def list_companies() -> list[Company]:
    return company_module.list_companies()


def update_company(company_id: str, **fields) -> Company | None:
    company = company_module.load_company(company_id)
    if company is None:
        return None
    for key, value in fields.items():
        if hasattr(company, key):
            setattr(company, key, value)
    company_module.save_company(company)
    return company


def add_project(company_id: str, name: str, **fields) -> BusinessProject:
    return project_module.add_project(company_id, name, **fields)


def list_projects(company_id: str) -> list[BusinessProject]:
    return project_module.load_projects(company_id)


def list_all_projects() -> list[BusinessProject]:
    return project_module.list_all_projects()


def set_brand(company_id: str, **fields) -> Brand:
    return brand_module.set_brand(company_id, **fields)


def get_brand(company_id: str) -> Brand | None:
    return brand_module.load_brand(company_id)


def add_goal(company_id: str, title: str, **fields) -> Goal:
    return goals_module.add_goal(company_id, title, **fields)


def list_goals(company_id: str) -> list[Goal]:
    return goals_module.load_goals(company_id)


def add_roadmap_item(company_id: str, title: str, **fields) -> RoadmapItem:
    return roadmap_module.add_item(company_id, title, **fields)


def list_roadmap(company_id: str, status: str | None = None) -> list[RoadmapItem]:
    return roadmap_module.list_by_status(company_id, status)


def add_knowledge_fact(company_id: str, fact: str, **fields) -> KnowledgeItem:
    return knowledge_module.add_fact(company_id, fact, **fields)


def list_knowledge(company_id: str, category: str | None = None) -> list[KnowledgeItem]:
    return knowledge_module.list_knowledge(company_id, category)


def remember(company_id: str, key: str, value: str) -> None:
    memory_module.remember(company_id, key, value)


def recall_memory(company_id: str) -> dict[str, list[str]]:
    return memory_module.all_memory(company_id)


def register_document(company_id: str, title: str, doc_type: str, **fields) -> BusinessDocument:
    return documents_module.register_document(company_id, title, doc_type, **fields)


def list_documents(company_id: str) -> list[BusinessDocument]:
    return documents_module.list_documents(company_id)


def record_decision(company_id: str, decision: str, **fields) -> Decision:
    return decisions_module.record_decision(company_id, decision, **fields)


def list_decisions(company_id: str) -> list[Decision]:
    return decisions_module.load_decisions(company_id)


# ---------------------------------------------------------------------------
# Migration: bootstrap real Company/BusinessProject records from the
# two systems that already existed before BETA 009 -- never a second,
# competing copy of either.
# ---------------------------------------------------------------------------

_DOMAIN_PATTERN = re.compile(r"\b[\w-]+\.(?:com|io|net|org|co|app)\b", re.IGNORECASE)


def migrate_existing() -> list[Company]:
    """Real, generic, idempotent migration: for every orion.projects
    Project whose metadata links it to a Sprint 004 BusinessUnit (see
    orion.projects.registry._SEED_PROJECTS' business_unit_slug), create
    a real Company (only if one does not already exist for that id --
    never overwrites a Company someone has since edited by hand) that
    merges both systems' real fields, plus one default BusinessProject
    linking back to the real technical project. Applies uniformly to
    every company in the registry, not just ATMAN/CGISO -- no
    company-specific logic here."""
    from orion.window import services as window_services

    business_units = {unit.slug: unit for unit in window_services.load_business_units()}
    created: list[Company] = []

    for technical_project in project_registry.list_projects():
        slug = technical_project.metadata.get("business_unit_slug", technical_project.project_id)
        if company_module.load_company(slug) is not None:
            continue  # already migrated (or created directly) -- never overwritten

        unit = business_units.get(slug)
        objectives = [unit.objective] if unit and unit.objective else []
        description = technical_project.description or (f"Unidad de negocio '{slug}'.")

        websites = sorted(set(_DOMAIN_PATTERN.findall(description)))

        company = company_module.create_company(
            company_id=slug,
            name=technical_project.name,
            description=description,
            status=technical_project.status,
            objectives=objectives,
            repositories=[technical_project.project_id],
            websites=websites,
        )
        created.append(company)

        # One default BusinessProject per migrated company, linking
        # back to the one real technical project the Multi-Project
        # Engine already tracks for it.
        project_module.add_project(
            slug, "Website", description=f"Presencia web/producto principal de {technical_project.name}.",
            technical_project_id=technical_project.project_id,
            keywords=[technical_project.name.lower(), slug],
        )

        if unit is not None:
            for decision_text in unit.decisions:
                decisions_module.record_decision(
                    slug, decision_text, reason="Migrado desde Sprint 004 (BusinessUnit).", author="ORION (migracion)",
                )
            for opportunity in unit.opportunities:
                roadmap_module.add_item(slug, opportunity, status="idea", description="Migrado desde Sprint 004 (BusinessUnit).")
            for mission_title in unit.missions:
                roadmap_module.add_item(slug, mission_title, status="in_progress", description="Migrado desde Sprint 004 (BusinessUnit).")

    return created


def enrich_atman_with_real_data() -> Company | None:
    """Curated, explicitly-sourced real facts for ATMAN -- not
    inferred, not guessed. Sources, disclosed:

    - Branding colors/personality: given directly by the CEO in the
      BETA 009 spec itself ("Azul marino, Dorado, Blanco... Premium,
      Espiritual, Elegante"), consistent with the real design tokens
      at atman/design-tokens/tokens.css (cosmic-ink = dark blue-violet,
      ember = warm gold).
    - Tech stack: given directly by the CEO in the BETA 009 spec
      ("ATMAN vende cursos, usa Tutor LMS, usa WordPress") plus the
      real facts in atman/docs/ARCHITECTURE.md (v1/atmanme.com is
      WordPress with the Inspiro/WPZOOM theme; v2 is a Next.js+
      TypeScript+Tailwind rebuild in progress).
    - Website project keywords: "cursos" is added explicitly because
      the CEO's own worked example ("Construye la pagina de Cursos")
      must resolve to ATMAN's Website project.
    - Goal "Incrementar conversiones": the CEO's own literal
      CRITERIO DE EXITO example objective for this exact request.

    Idempotent: safe to call repeatedly (set_brand/remember/add_goal/
    add_fact are all themselves idempotent or additive).
    """
    company = company_module.load_company("atman")
    if company is None:
        return None

    company.aliases = sorted(set(company.aliases) | {"atman"})
    company.websites = sorted(set(company.websites) | {"atmanme.com"})
    company_module.save_company(company)

    brand_module.set_brand(
        "atman",
        colors=["Azul marino", "Dorado", "Blanco"],
        personality=["Premium", "Espiritual", "Elegante"],
        tone="Cercano, informado, adulto -- afirma sin prometer, nunca predictivo ni absoluto.",
        typography="Sans-serif humanista (Inter), escala 12-56px, pesos 400/500/700.",
    )

    memory_module.remember_many(
        "atman", "tech_stack",
        ["WordPress", "Tutor LMS", "LiteSpeed", "Hostinger", "Next.js (v2, en construccion)", "TypeScript", "Tailwind CSS"],
    )
    knowledge_module.add_fact("atman", "ATMAN vende cursos", category="business_model", source="beta009_spec")
    knowledge_module.add_fact(
        "atman", "v1 (atmanme.com) es WordPress con tema Inspiro/WPZOOM y el plugin vedicastroapi",
        category="tech_stack", source="atman/docs/ARCHITECTURE.md",
    )
    knowledge_module.add_fact(
        "atman", "v2 (en construccion) es un rebuild greenfield en Next.js + TypeScript + Tailwind, git-first",
        category="tech_stack", source="atman/docs/ARCHITECTURE.md",
    )

    goal_titles = {g.title for g in goals_module.load_goals("atman")}
    if "Incrementar conversiones" not in goal_titles:
        goals_module.add_goal("atman", "Incrementar conversiones", description="Objetivo del proyecto Website.")
    if "Incrementar suscripciones" not in goal_titles:
        goals_module.add_goal("atman", "Incrementar suscripciones", description="Objetivo de negocio de ATMAN (cursos/membresias).")

    projects = project_module.load_projects("atman")
    for p in projects:
        if p.name == "Website":
            merged_keywords = sorted(set(p.keywords) | {"cursos", "curso", "pagina", "web", "sitio", "blog", "membresia", "membresias"})
            if merged_keywords != sorted(p.keywords):
                p.keywords = merged_keywords
                p.updated_at = _now_iso()
                project_module.save_projects("atman", projects)
            break

    documents_module.register_document(
        "atman", "ARCHITECTURE.md", "markdown", path_or_url="/sessions/laughing-zealous-hawking/atman/docs/ARCHITECTURE.md",
        tags=["arquitectura", "stack"],
    )
    documents_module.register_document(
        "atman", "DESIGN_SYSTEM.md", "markdown", path_or_url="/sessions/laughing-zealous-hawking/atman/docs/DESIGN_SYSTEM.md",
        tags=["branding", "diseno"],
    )

    return company_module.load_company("atman")


# ---------------------------------------------------------------------------
# Resolution: the real "who is this for" step every Mission goes
# through before Project Intelligence/the Planner ever run.
# ---------------------------------------------------------------------------


@dataclass
class BusinessBrief:
    """The exact real answer the CRITERIO DE EXITO asks ORION to
    produce internally, before executing a single line: which real
    Company/Project this is, what it's for, how it should look, what
    it runs on, and how risky the change is -- computed, never
    templated with placeholder text."""

    request: str
    resolved: ResolvedContext
    context: BusinessContext
    objective: str = ""
    risk: str = "desconocido"
    plan_steps: int = 0
    intelligence_available: bool = False
    # BETA 010 (Governance): the real IntelligenceBrief this brief's
    # own resolve_context() already computed, when it computed one --
    # never a second call. Optional/None for the unresolved case and
    # for the no-real-repo branch (which only calls plan_request(),
    # not prepare_request(), so no ImpactReport exists yet). Consumed
    # by orion.governance.services.evaluate_change() so Risk Engine
    # never has to re-derive impact data itself.
    intelligence_brief: "IntelligenceBrief | None" = None
    generated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "company": self.resolved.company.id if self.resolved.company else None,
            "project": self.context.resolved.project.name if self.context.resolved.project else None,
            "objective": self.objective,
            "repository": self.context.repository_display,
            "branding": self.context.branding.colors if self.context.branding else [],
            "technology": self.context.technology,
            "risk": self.risk,
            "plan_steps": self.plan_steps,
            "intelligence_available": self.intelligence_available,
            "generated_at": self.generated_at,
        }

    def summary_text(self) -> str:
        """Exactly the CRITERIO DE EXITO shape: one label per line,
        its real value(s) on the line(s) after it."""
        if not self.resolved.resolved:
            return (
                "No pude identificar a que empresa pertenece esta peticion.\n"
                "No hay suficiente contexto real para continuar sin preguntar."
            )

        lines = [
            "Empresa:", self.resolved.company.name,
            "Proyecto:", (self.resolved.project.name if self.resolved.project else "(sin proyecto especifico)"),
            "Objetivo:", (self.objective or "(sin objetivo definido)"),
            "Repositorio:", (self.context.repository_display or "(no vinculado aun)"),
            "Branding:",
        ]
        lines.extend(self.context.branding.colors if self.context.branding and self.context.branding.colors else ["(sin branding definido)"])
        lines.append("Tecnologia:")
        lines.extend(self.context.technology if self.context.technology else ["(sin tecnologia registrada)"])
        lines.append("Nivel de riesgo:")
        lines.append(f"{self.risk.capitalize()}.")
        lines.append("Plan generado.")
        lines.append("Comenzando ejecucion.")
        return "\n".join(lines)


def _has_real_repo(technical_project_id: str | None) -> bool:
    if not technical_project_id:
        return False
    project = project_registry.get_project(technical_project_id)
    return bool(project and project.local_path)


def resolve_context(request: str, mission_id: str | None = None) -> BusinessBrief:
    """The real Business Brain -> Context Engine -> Project
    Intelligence step of BETA 009's Mission Flow. Never asks a
    clarifying question: if nothing real resolves, the returned
    BusinessBrief says so honestly (see summary_text() above) instead
    of guessing."""
    config = BusinessConfig.from_env()
    resolved = planner.resolve_request(request, config)
    _emit(
        mission_id, "company_resolved",
        f"Empresa resuelta: {resolved.company.name if resolved.company else '(ninguna)'} "
        f"(metodo={resolved.method}, confianza={resolved.confidence:.2f}).",
    )

    context = planner.load_business_context(resolved)
    _emit(mission_id, "context_loaded", f"Contexto de negocio cargado para '{resolved.company.id if resolved.company else '-'}'.")

    if not resolved.resolved:
        return BusinessBrief(request=request, resolved=resolved, context=context)

    objective = context.active_goals[0].title if context.active_goals else (
        resolved.company.objectives[0] if resolved.company.objectives else ""
    )

    risk = "desconocido"
    plan_steps = 0
    intelligence_available = False
    technical_project_id = context.technical_project_id

    intelligence_brief_obj: "IntelligenceBrief | None" = None
    if _has_real_repo(technical_project_id):
        brief = intelligence_services.prepare_request(request, project_key=technical_project_id, mission_id=mission_id)
        risk = brief.impact.risk
        plan_steps = len(brief.plan.steps)
        intelligence_available = True
        intelligence_brief_obj = brief
    else:
        plan = intelligence_services.plan_request(
            request, project_key=(technical_project_id or ""), mission_id=mission_id
        )
        plan_steps = len(plan.steps)
        risk = "bajo" if not technical_project_id else "desconocido"

    return BusinessBrief(
        request=request, resolved=resolved, context=context, objective=objective,
        risk=risk, plan_steps=plan_steps, intelligence_available=intelligence_available,
        intelligence_brief=intelligence_brief_obj,
    )


def learn_from_mission(mission_id: str, mission_title: str, mission_description: str) -> None:
    """Real, conservative learning: updates Knowledge and Roadmap for
    the resolved company. Deliberately does NOT auto-write a Decision
    Log entry -- a Decision is a deliberate human call ("Elegimos X,
    motivo Y"), and inferring one from every completed Mission would
    fill the log with noise, undermining the one property the spec
    asks it to have ("nunca volver a discutir decisiones ya
    tomadas"). Decisions stay create_decision()-only, triggered
    explicitly via CLI/API/Window."""
    resolved = planner.resolve_request(mission_description or mission_title)
    if not resolved.resolved:
        return

    company_id = resolved.company.id
    knowledge_module.add_fact(
        company_id, f"Mision {mission_id} completada: {mission_title}",
        category="mission_history", source=mission_id,
    )

    matching_item = None
    for item in roadmap_module.load_roadmap(company_id):
        if item.title.strip().lower() == mission_title.strip().lower():
            matching_item = item
            break
    if matching_item is not None:
        roadmap_module.link_mission(company_id, matching_item.id, mission_id)
        if matching_item.status != "done":
            roadmap_module.update_status(company_id, matching_item.id, "done")
    else:
        new_item = roadmap_module.add_item(company_id, mission_title, status="done", project_id=(resolved.project.id if resolved.project else None))
        roadmap_module.link_mission(company_id, new_item.id, mission_id)

    # Real, conservative goal attribution: only link this Mission to a
    # Goal whose own title/description genuinely shares a token with
    # the Mission's text -- never the first active Goal by default,
    # which would fabricate a contribution that was never actually
    # evaluated.
    from orion.business.planner import _tokens

    mission_tokens = _tokens(f"{mission_title} {mission_description}")
    for goal in goals_module.list_active(company_id):
        goal_tokens = _tokens(f"{goal.title} {goal.description}")
        if mission_tokens & goal_tokens:
            goals_module.link_mission(company_id, goal.id, mission_id)

    _emit(mission_id, "business_knowledge_updated", f"Conocimiento de negocio actualizado para '{company_id}'.")
