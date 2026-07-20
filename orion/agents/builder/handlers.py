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
    """Produces a generated code stub for the mission."""

    def run(self, mission: Mission, artifacts_dir: Path) -> HandlerResult:
        path = artifacts_dir / "generated.py"
        path.write_text(
            f'"""Generated stub for mission {mission.id}: {mission.title}."""\n',
            encoding="utf-8",
        )
        return HandlerResult(artifacts=[path.name], summary="Stub de codigo generado.")
