"""The Business Brain's own planner: resolve which real Company and
BusinessProject a free-text request belongs to -- deterministically,
by real keyword matching, never an LLM guess -- then load every real
piece of context that Company/Project already has, including calling
into orion.intelligence (never re-implementing it) for architecture/
impact/plan once a real technical repository is known.

This is the literal "Business Brain -> Context Engine -> Project
Intelligence" step of BETA 009's Mission Flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orion.business import brand as brand_module
from orion.business import company as company_module
from orion.business import goals as goals_module
from orion.business import memory as memory_module
from orion.business import project as project_module
from orion.business import roadmap as roadmap_module
from orion.business.company import Company
from orion.business.config import BusinessConfig
from orion.business.project import BusinessProject

_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "un", "una", "y", "en", "para",
    "con", "the", "a", "an", "of", "for", "to", "and", "build", "construye",
    "construir", "crea", "crear", "pagina", "page", "haz", "hacer",
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_PATTERN.findall(text.lower()) if t and t not in _STOPWORDS}


@dataclass
class ResolvedContext:
    """The real outcome of resolve_request(): which Company/BusinessProject
    (if any) a free-text request maps to, and how confident/how that
    conclusion was reached -- never fabricated when nothing real matches."""

    company: Company | None = None
    project: BusinessProject | None = None
    confidence: float = 0.0
    method: str = "none"  # "explicit_company_name" | "keyword_match" | "none"
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.company is not None


def resolve_request(request_text: str, config: BusinessConfig | None = None) -> ResolvedContext:
    """Real, deterministic resolution, in two passes:

    1. Explicit mention: the request literally names a Company (by its
       real ``name`` or one of its real ``aliases``) -- the strongest,
       most certain signal, checked first and matched as a whole word
       so "CGISO" never matches inside an unrelated longer token.
    2. Keyword overlap: score every real BusinessProject across every
       Company by overlap between the request's tokens and that
       project's own ``keywords`` (plus its name) -- the same
       real-signals-only technique orion.intelligence.component_finder
       already uses for code, applied here to business initiatives.

    Returns an unresolved ResolvedContext (company=None) if nothing
    real crosses the threshold -- never a guess.
    """
    config = config or BusinessConfig.from_env()
    tokens = _tokens(request_text)
    text_lower = request_text.lower()

    companies = company_module.list_companies()

    # Pass 1: explicit company name/alias.
    for company in companies:
        names = [company.name, company.id, *company.aliases]
        for name in names:
            if not name:
                continue
            if re.search(rf"\b{re.escape(name.lower())}\b", text_lower):
                projects = project_module.load_projects(company.id)
                best_project, best_score, best_keywords = _best_project_match(tokens, projects)
                return ResolvedContext(
                    company=company, project=best_project, confidence=1.0,
                    method="explicit_company_name", matched_keywords=best_keywords,
                )

    # Pass 2: real keyword overlap against every project of every company.
    best_company: Company | None = None
    best_project: BusinessProject | None = None
    best_score = 0.0
    best_keywords: list[str] = []
    for company in companies:
        projects = project_module.load_projects(company.id)
        project, score, keywords = _best_project_match(tokens, projects)
        if project is not None and score > best_score:
            best_company, best_project, best_score, best_keywords = company, project, score, keywords

    if best_company is not None and best_score >= config.match_threshold:
        return ResolvedContext(
            company=best_company, project=best_project, confidence=best_score,
            method="keyword_match", matched_keywords=best_keywords,
        )

    return ResolvedContext()


def _best_project_match(
    tokens: set[str], projects: list[BusinessProject]
) -> tuple[BusinessProject | None, float, list[str]]:
    """Real keyword overlap only -- deliberately no character-level
    fuzzy fallback (SequenceMatcher) here, unlike
    orion.intelligence.component_finder: two unrelated business
    requests can share enough characters to cross a low fuzzy
    threshold purely by chance, and getting company resolution wrong
    is far more consequential than getting a code-reuse suggestion
    wrong. A project is only ever selected when at least one real
    token is actually shared with its own name/keywords."""
    best: BusinessProject | None = None
    best_score = 0.0
    best_keywords: list[str] = []
    for project in projects:
        project_tokens = _tokens(project.name) | {kw.lower() for kw in project.keywords}
        if not tokens or not project_tokens:
            continue
        overlap = tokens & project_tokens
        if not overlap:
            continue
        score = len(overlap) / len(tokens)
        if score > best_score:
            best, best_score, best_keywords = project, score, sorted(overlap)
    return best, best_score, best_keywords


@dataclass
class BusinessContext:
    """Everything a Mission needs from the Business Brain before
    Project Intelligence/the Planner/the Prompt Composer ever run:
    who this is for, what they want, how it should look, and what is
    already known -- loaded automatically, never asked for again."""

    resolved: ResolvedContext
    active_goals: list = field(default_factory=list)
    open_roadmap_items: list = field(default_factory=list)
    branding: brand_module.Brand | None = None
    technology: list[str] = field(default_factory=list)
    repository_display: str = ""
    technical_project_id: str | None = None


def _resolve_repository_display(company: Company, project: BusinessProject | None) -> str:
    """A real, human-meaningful value for "Repositorio:" -- prefers a
    known website (e.g. "atmanme.com"), then the real repository URL
    or local clone path of the linked technical project (never the
    bare technical_project_id string, which is an internal key, not a
    repository), then finally that raw id only as a last, honest
    resort when nothing more descriptive is known."""
    if company.websites:
        return company.websites[0]

    from orion.projects import registry as project_registry

    technical_project_id = project.technical_project_id if project else None
    if technical_project_id:
        technical_project = project_registry.get_project(technical_project_id)
        if technical_project is not None:
            return technical_project.local_path or technical_project.repository or technical_project_id

    return company.repositories[0] if company.repositories else ""


def load_business_context(resolved: ResolvedContext) -> BusinessContext:
    """Load every real piece of context a resolved Company/BusinessProject
    already has -- branding, active goals, open roadmap items, and
    remembered technology facts. Never touches orion.intelligence
    itself (see orion.business.services.prepare_request, which layers
    that on top) -- this function's job is exactly "load the Business
    Brain's own context", nothing more."""
    if resolved.company is None:
        return BusinessContext(resolved=resolved)

    company = resolved.company
    brand = brand_module.load_brand(company.id)
    technology = memory_module.recall(company.id, "tech_stack")
    repository_display = _resolve_repository_display(company, resolved.project)

    return BusinessContext(
        resolved=resolved,
        active_goals=goals_module.list_active(company.id),
        open_roadmap_items=[i for i in roadmap_module.load_roadmap(company.id) if i.status in ("idea", "backlog", "in_progress")],
        branding=brand,
        technology=technology,
        repository_display=repository_display,
        technical_project_id=resolved.project.technical_project_id if resolved.project else None,
    )
