"""BusinessProject: one product/initiative under a Company (Website,
Mobile App, AI Academy, ...).

Named ``BusinessProject`` (not ``Project``) inside this module
deliberately: orion.projects.models.Project already owns that name for
the technical/git-tracked record (repository, branch, local_path).
The two are related, never merged -- a BusinessProject *optionally*
points at a real orion.projects project_id via
``technical_project_id`` when one exists (see company "atman", which
does), and stays without one when a business initiative has no code
yet (e.g. "Podcast").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BusinessProject:
    id: str
    company_id: str
    name: str
    description: str = ""
    status: str = "active"
    # Optional link into orion.projects' Multi-Project Engine -- the
    # one and only place a repository/branch/local_path is ever
    # recorded. None means "no code yet" (a real, honest state, not
    # an error).
    technical_project_id: str | None = None
    # Real matching signal for planner.resolve_request(): tokens a
    # free-text request should hit for this specific initiative to be
    # selected within its company (e.g. Website's keywords include
    # "cursos" because a Cursos *page* lives inside the Website
    # project, not as its own top-level BusinessProject).
    keywords: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "technical_project_id": self.technical_project_id,
            "keywords": self.keywords,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessProject":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=data.get("status", "active"),
            technical_project_id=data.get("technical_project_id"),
            keywords=list(data.get("keywords", [])),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


def load_projects(company_id: str) -> list[BusinessProject]:
    raw = storage.read_yaml(storage.projects_path(company_id), default=[])
    return [BusinessProject.from_dict(item) for item in raw]


def save_projects(company_id: str, projects: list[BusinessProject]) -> None:
    storage.write_yaml(storage.projects_path(company_id), [p.to_dict() for p in projects])


def add_project(
    company_id: str, name: str, description: str = "", technical_project_id: str | None = None,
    keywords: list[str] | None = None,
) -> BusinessProject:
    project = BusinessProject(
        id=uuid.uuid4().hex[:12], company_id=company_id, name=name, description=description,
        technical_project_id=technical_project_id, keywords=list(keywords or []),
    )
    projects = load_projects(company_id)
    projects.append(project)
    save_projects(company_id, projects)
    return project


def get_project(company_id: str, project_id: str) -> BusinessProject | None:
    for project in load_projects(company_id):
        if project.id == project_id:
            return project
    return None


def list_all_projects() -> list[BusinessProject]:
    """Every BusinessProject across every registered Company -- the
    real search space planner.resolve_request() matches a free-text
    request against."""
    from orion.business import company as company_module

    projects: list[BusinessProject] = []
    for company in company_module.list_companies():
        projects.extend(load_projects(company.id))
    return projects
