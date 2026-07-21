"""Idempotent generator/drift-checker for the two documents this
Mission (G-012) found genuinely duplicating -- not narrating -- the
AI Board roster by hand: the "AI Board" table in ``AGENTS.md`` and the
"Membership" table in ``.ai/BOARD.md``. Both are now rendered from
``.ai/board.yaml`` (see orion.board.canonical) between explicit
BEGIN/END markers; everything else in either file (headings, prose,
Operating Model, Purpose, Rules) is untouched, hand-written, and
remains authoritative.

Deliberately does NOT touch ``.ai/ROLES.md``: it is full narrative
prose (May / May not / Boundaries) with no simple table to regenerate,
and this Mission's own brief says not to convert an entire narrative
document into generated output "solo por comodidad".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orion.board.canonical import BoardConfiguration, REPO_ROOT, load_board_config

BEGIN_MARKER = "<!-- BEGIN GENERATED: .ai/board.yaml (orion.board.generator) -->"
END_MARKER = "<!-- END GENERATED -->"

AGENTS_MD_PATH: Path = REPO_ROOT / "AGENTS.md"
BOARD_MD_PATH: Path = REPO_ROOT / ".ai" / "BOARD.md"


class GeneratorError(RuntimeError):
    """Raised when a target file cannot be safely regenerated (e.g.
    missing BEGIN/END markers) -- never silently overwrites a file it
    cannot find its own boundaries in."""


@dataclass(frozen=True)
class DriftResult:
    path: Path
    has_drift: bool
    rendered: str


def _format_agents_table(config: BoardConfiguration) -> str:
    lines = [BEGIN_MARKER, "", "| Name | Role | Responsible For | Prompt |", "|---|---|---|---|"]
    for member in config.members:
        if member.documentation_path:
            prompt_cell = f"[`{Path(member.documentation_path).name}`]({member.documentation_path})"
        else:
            prompt_cell = "— (human)"
        responsible_for = member.responsibilities[0] if member.responsibilities else ""
        lines.append(f"| {member.display_name} | {member.role} | {responsible_for} | {prompt_cell} |")
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _format_board_md_table(config: BoardConfiguration) -> str:
    lines = [BEGIN_MARKER, "", "| Name | Role | Authority |", "|---|---|---|"]
    for member in config.members:
        authority = member.responsibilities[0] if member.responsibilities else ""
        lines.append(f"| {member.display_name} | {member.role} | {authority} |")
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _render_between_markers(original_text: str, generated_block: str, path: Path) -> str:
    if BEGIN_MARKER not in original_text or END_MARKER not in original_text:
        raise GeneratorError(
            f"{path} is missing the BEGIN/END GENERATED markers; refusing to guess where to write "
            "the generated table (run this once manually to establish the markers first)."
        )
    before, rest = original_text.split(BEGIN_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    return before + generated_block + after


def _targets(config: BoardConfiguration) -> list[tuple[Path, str]]:
    return [
        (AGENTS_MD_PATH, _format_agents_table(config)),
        (BOARD_MD_PATH, _format_board_md_table(config)),
    ]


def check_drift(config: BoardConfiguration | None = None) -> list[DriftResult]:
    """Never writes anything. Returns one DriftResult per generated
    target, each stating whether the file on disk currently differs
    from what would be (re)generated."""
    if config is None:
        config = load_board_config()
    results = []
    for path, block in _targets(config):
        if not path.is_file():
            raise GeneratorError(f"generation target does not exist: {path}")
        original = path.read_text(encoding="utf-8")
        rendered = _render_between_markers(original, block, path)
        results.append(DriftResult(path=path, has_drift=(rendered != original), rendered=rendered))
    return results


def generate(config: BoardConfiguration | None = None, check_only: bool = False) -> list[DriftResult]:
    """Regenerates every target from the canonical Board configuration.
    Idempotent and deterministic: given the same board.yaml, produces
    byte-identical output every time (stable member order, no
    timestamps). Writes only the files that actually changed. When
    ``check_only`` is True, never writes -- same contract as
    check_drift(), returned in the same shape so CLI callers share one
    code path for both commands."""
    results = check_drift(config=config)
    if not check_only:
        for result in results:
            if result.has_drift:
                result.path.write_text(result.rendered, encoding="utf-8")
    return results
