"""Brand: one company's real visual/verbal identity, loaded
automatically once a Company is resolved -- never re-asked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.business import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Brand:
    company_id: str
    colors: list[str] = field(default_factory=list)
    typography: str = ""
    logo: str = ""
    tone: str = ""
    personality: list[str] = field(default_factory=list)
    iconography: str = ""
    components: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    design_guides: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "colors": self.colors,
            "typography": self.typography,
            "logo": self.logo,
            "tone": self.tone,
            "personality": self.personality,
            "iconography": self.iconography,
            "components": self.components,
            "templates": self.templates,
            "design_guides": self.design_guides,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Brand":
        return cls(
            company_id=data["company_id"],
            colors=list(data.get("colors", [])),
            typography=data.get("typography", ""),
            logo=data.get("logo", ""),
            tone=data.get("tone", ""),
            personality=list(data.get("personality", [])),
            iconography=data.get("iconography", ""),
            components=list(data.get("components", [])),
            templates=list(data.get("templates", [])),
            design_guides=list(data.get("design_guides", [])),
            updated_at=data.get("updated_at", _now_iso()),
        )


def load_brand(company_id: str) -> Brand | None:
    data = storage.read_yaml(storage.brand_path(company_id), default=None)
    return None if data is None else Brand.from_dict(data)


def save_brand(brand: Brand) -> None:
    brand.updated_at = _now_iso()
    storage.write_yaml(storage.brand_path(brand.company_id), brand.to_dict())


def set_brand(company_id: str, **fields) -> Brand:
    """Create or replace a Company's Brand record in one call --
    branding is small enough that partial-field PATCH semantics would
    add complexity with no real benefit here."""
    brand = Brand(company_id=company_id, **fields)
    save_brand(brand)
    return brand
