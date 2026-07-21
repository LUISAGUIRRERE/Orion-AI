"""Documents: real metadata for a company's real files (PDF/DOCX/
Markdown/specs/meeting notes/Fireflies transcripts/roadmaps) -- never
their content stored here (see knowledge.py for what was actually
extracted from them). A ``path_or_url`` that points at a real local
file gets real size/mtime recorded; anything else (a URL, or a path
that does not exist in this environment) is still registered, just
without those two fields -- never fabricated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from orion.business import storage

DOCUMENT_TYPES = frozenset({"pdf", "docx", "markdown", "spec", "meeting", "fireflies", "roadmap", "other"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BusinessDocument:
    id: str
    company_id: str
    title: str
    doc_type: str = "other"
    path_or_url: str = ""
    tags: list[str] = field(default_factory=list)
    size_bytes: int | None = None
    modified_at: str | None = None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "path_or_url": self.path_or_url,
            "tags": self.tags,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessDocument":
        return cls(
            id=data["id"],
            company_id=data["company_id"],
            title=data["title"],
            doc_type=data.get("doc_type", "other"),
            path_or_url=data.get("path_or_url", ""),
            tags=list(data.get("tags", [])),
            size_bytes=data.get("size_bytes"),
            modified_at=data.get("modified_at"),
            created_at=data.get("created_at", _now_iso()),
        )


def load_documents(company_id: str) -> list[BusinessDocument]:
    raw = storage.read_yaml(storage.documents_path(company_id), default=[])
    return [BusinessDocument.from_dict(item) for item in raw]


def save_documents(company_id: str, docs: list[BusinessDocument]) -> None:
    storage.write_yaml(storage.documents_path(company_id), [d.to_dict() for d in docs])


def register_document(
    company_id: str, title: str, doc_type: str, path_or_url: str = "", tags: list[str] | None = None
) -> BusinessDocument:
    doc_type = doc_type if doc_type in DOCUMENT_TYPES else "other"
    size_bytes: int | None = None
    modified_at: str | None = None
    if path_or_url:
        local = Path(path_or_url)
        if local.is_file():
            stat = local.stat()
            size_bytes = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    doc = BusinessDocument(
        id=uuid.uuid4().hex[:12], company_id=company_id, title=title, doc_type=doc_type,
        path_or_url=path_or_url, tags=list(tags or []), size_bytes=size_bytes, modified_at=modified_at,
    )
    docs = load_documents(company_id)
    docs.append(doc)
    save_documents(company_id, docs)
    return doc


def list_documents(company_id: str, doc_type: str | None = None) -> list[BusinessDocument]:
    docs = load_documents(company_id)
    if doc_type is None:
        return docs
    return [d for d in docs if d.doc_type == doc_type]
