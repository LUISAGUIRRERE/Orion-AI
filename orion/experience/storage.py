"""Persistence for a mission's ExperienceReport: experience_report.yaml
(always) and experience_summary.md (optional, human-readable
rendering) under workspace/missions/<mission-id>/ -- the same
directory every other piece of a mission's evidence already lives in
(prompt_package.yaml, execution_request.yaml, execution_result.yaml,
execution.yaml).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from orion.bridge import storage as bridge_storage
from orion.experience.models import ExperienceReport


def _report_path(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "experience_report.yaml"


def _summary_path(mission_id: str) -> Path:
    return bridge_storage.mission_dir(mission_id) / "experience_summary.md"


def save_report(report: ExperienceReport) -> Path:
    path = _report_path(report.mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(report.model_dump(mode="json"), fh, allow_unicode=True, sort_keys=False)
    return path


def load_report(mission_id: str) -> ExperienceReport | None:
    path = _report_path(mission_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return None if data is None else ExperienceReport(**data)


def _bulleted(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (ninguno)"


def render_summary_markdown(report: ExperienceReport) -> str:
    """A short, human-readable rendering of the report -- what a CEO
    or a future mission's author would actually want to read, not a
    dump of the YAML."""
    lines = [
        f"# Experience Report — {report.mission_id}",
        "",
        report.mission_summary,
        "",
        f"**Confianza:** {report.confidence_score}",
        "",
        "## Objetivos alcanzados",
        _bulleted(report.objectives_achieved),
        "",
        "## Archivos tocados",
        _bulleted(report.files_modified),
        "",
        "## Artifacts generados",
        _bulleted(report.artifacts_generated),
        "",
        "## Errores encontrados",
        _bulleted(report.errors_encountered),
        "",
        "## Patrones detectados",
        _bulleted(report.patterns_detected),
        "",
        "## Componentes reutilizables",
        _bulleted(report.reusable_components),
        "",
        "## Recomendaciones",
        _bulleted(report.recommendations),
        "",
    ]
    return "\n".join(lines) + "\n"


def save_summary(report: ExperienceReport) -> Path:
    path = _summary_path(report.mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary_markdown(report), encoding="utf-8")
    return path
