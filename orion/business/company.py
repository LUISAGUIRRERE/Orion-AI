"""The Company: the real center of orion.business.

A Company is deliberately richer than both orion.projects.models.Project
(the technical/operational record: repository, branch, missions) and
orion.window.models.BusinessUnit (Sprint 004's narrative dashboard
snapshot: status/health/objective/decisions/opportunities). It does
not replace either -- see services.migrate_existing() -- it is the
layer above them: what the business actually *is*, not just what
ORION is currently building for it or reporting about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Company:
    id: str
    name: str
    description: str = ""
    mission: str = ""
    vision: str = ""
    values: list[str] = field(default_factory=list)
    market: str = ""
    clients: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    business_model: str = ""
    objectives: list[str] = field(default_factory=list)
    kpis: dict[str, str] = field(default_factory=dict)
    status: str = "active"
    # Real, technical project_ids from orion.projects' Multi-Project
    # Engine (the "code" representation of this company) -- never a
    # duplicate git-tracking record of its own. Empty until a real
    # technical project is linked.
    repositories: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    # Ids into orion.business.documents' store, not embedded content.
    documentation: list[str] = field(default_factory=list)
    # Free-form aliases/keywords this company is known by in natural
    # language, beyond its own name (e.g. a product name that implies
    # the company without ever naming it) -- used by planner.py's real
    # keyword matching, never an LLM guess.
    aliases: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "mission": self.mission,
            "vision": self.vision,
            "values": self.values,
            "market": self.market,
            "clients": self.clients,
            "competitors": self.competitors,
            "business_model": self.business_model,
            "objectives": self.objectives,
            "kpis": self.kpis,
            "status": self.status,
            "repositories": self.repositories,
            "websites": self.websites,
            "documentation": self.documentation,
            "aliases": self.aliases,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            mission=data.get("mission", ""),
            vision=data.get("vision", ""),
            values=list(data.get("values", [])),
            market=data.get("market", ""),
            clients=list(data.get("clients", [])),
            competitors=list(data.get("competitors", [])),
            business_model=data.get("business_model", ""),
            objectives=list(data.get("objectives", [])),
            kpis=dict(data.get("kpis", {})),
            status=data.get("status", "active"),
            repositories=list(data.get("repositories", [])),
            websites=list(data.get("websites", [])),
            documentation=list(data.get("documentation", [])),
            aliases=list(data.get("aliases", [])),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


def load_company(company_id: str) -> Company | None:
    data = storage.read_yaml(storage.company_path(company_id), default=None)
    return None if data is None else Company.from_dict(data)


def save_company(company: Company) -> None:
    company.updated_at = _now_iso()
    storage.write_yaml(storage.company_path(company.id), company.to_dict())


def create_company(company_id: str, name: str, **fields) -> Company:
    """Raises ValueError if a Company with this id already exists --
    the exact same "never silently overwrite" convention
    orion.projects.registry.register_project already established."""
    if load_company(company_id) is not None:
        raise ValueError(f"La empresa '{company_id}' ya existe.")
    company = Company(id=company_id, name=name, **fields)
    save_company(company)
    return company


def list_companies() -> list[Company]:
    companies = []
    for company_id in storage.list_company_ids():
        company = load_company(company_id)
        if company is not None:
            companies.append(company)
    return sorted(companies, key=lambda c: c.id)
