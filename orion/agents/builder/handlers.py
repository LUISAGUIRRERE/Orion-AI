"""Mission handlers: one class per mission type, no if/else dispatch.

Each handler implements ``MissionHandler.run`` and receives the mission
plus its ``artifacts/`` directory. It writes whatever files it produces
there and returns a ``HandlerResult`` describing what it made. Which
handler runs for a given mission is decided by ``registry.py``, never
here.

The actual work each handler performs is intentionally simple and
deterministic: this Sprint builds the operational skeleton (dispatch,
execution, evidence, reporting) that every future, smarter handler will
plug into — not the intelligence behind each mission type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orion.bridge.models import Mission


@dataclass
class HandlerResult:
    """What a handler produced for a mission."""

    artifacts: list[str] = field(default_factory=list)
    summary: str = ""


class MissionHandler:
    """Base interface every mission handler must implement."""

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        """Execute the mission and return the artifacts it produced."""
        raise NotImplementedError


class DocumentationHandler(MissionHandler):
    """Produces a documentation report for the mission."""

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        path = artifacts_dir / "report.md"
        path.write_text(
            f"# {mission.title}\n\n{mission.description or 'Sin descripcion.'}\n",
            encoding="utf-8",
        )
        return HandlerResult(artifacts=[path.name], summary="Reporte de documentacion generado.")


class ResearchHandler(MissionHandler):
    """Produces research notes for the mission."""

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        path = artifacts_dir / "notes.md"
        path.write_text(
            f"# Investigacion: {mission.title}\n\nObjetivo: {mission.description or '-'}\n",
            encoding="utf-8",
        )
        return HandlerResult(artifacts=[path.name], summary="Notas de investigacion generadas.")


class ScaffoldHandler(MissionHandler):
    """Produces a minimal scaffold summary for the mission."""

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        path = artifacts_dir / "summary.md"
        path.write_text(
            f"# Scaffold: {mission.title}\n\nEstructura propuesta pendiente de detalle.\n",
            encoding="utf-8",
        )
        return HandlerResult(artifacts=[path.name], summary="Resumen de scaffold generado.")


class CodeGenerationHandler(MissionHandler):
    """Produces real source files for the mission.

    BETA 001: when a mission carries ``artifact_files`` (a mapping of
    exact repository-relative path -> exact file content, e.g.
    ``{"components/home/Hero.tsx": "<the real component source>"}``),
    this handler writes each one verbatim -- unlike
    DocumentationHandler/ResearchHandler/ScaffoldHandler, source code
    cannot tolerate an injected "# Title" heading, so there is no
    template wrapping here. ``result.artifacts`` then holds those same
    repository-relative paths, which TaskRunner uses to relocate each
    file into the target project's repository, all as part of one
    mission/branch/commit.

    A mission with no ``artifact_files`` set -- every code_generation
    mission created before this Sprint -- falls back to the original
    Sprint 006 stub. Zero behavior change for existing missions.
    """

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        if mission.artifact_files:
            written: list[str] = []
            for relpath, content in mission.artifact_files.items():
                path = artifacts_dir / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                written.append(relpath)
            return HandlerResult(
                artifacts=written,
                summary=f"{len(written)} archivo(s) de codigo real generados.",
            )
        path = artifacts_dir / "generated.py"
        path.write_text(
            f'"""Generated stub for mission {mission.id}: {mission.title}."""\n',
            encoding="utf-8",
        )
        return HandlerResult(artifacts=[path.name], summary="Stub de codigo generado.")
