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

import os
import tempfile
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


def _escape_markdown_table_cell(value: str) -> str:
    """G-012 REMEDIATION (HIGH #4): a display_name/role/responsibility
    containing a literal ``|`` would otherwise split a Markdown table
    cell and corrupt the generated table's structure. Escapes ``|``
    and collapses any embedded newline (which would just as surely
    break a one-line table row) into a single space -- never silently
    drops content."""
    return value.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _format_agents_table(config: BoardConfiguration) -> str:
    lines = [BEGIN_MARKER, "", "| Name | Role | Responsible For | Prompt |", "|---|---|---|---|"]
    for member in config.members:
        if member.documentation_path:
            prompt_label = _escape_markdown_table_cell(Path(member.documentation_path).name)
            prompt_cell = f"[`{prompt_label}`]({member.documentation_path})"
        else:
            prompt_cell = "— (human)"
        responsible_for = member.responsibilities[0] if member.responsibilities else ""
        display_name = _escape_markdown_table_cell(member.display_name)
        role = _escape_markdown_table_cell(member.role)
        responsible_for = _escape_markdown_table_cell(responsible_for)
        lines.append(f"| {display_name} | {role} | {responsible_for} | {prompt_cell} |")
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _format_board_md_table(config: BoardConfiguration) -> str:
    lines = [BEGIN_MARKER, "", "| Name | Role | Authority |", "|---|---|---|"]
    for member in config.members:
        authority = member.responsibilities[0] if member.responsibilities else ""
        display_name = _escape_markdown_table_cell(member.display_name)
        role = _escape_markdown_table_cell(member.role)
        authority = _escape_markdown_table_cell(authority)
        lines.append(f"| {display_name} | {role} | {authority} |")
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


def _prepare_temp_file(path: Path, content: str) -> str:
    """Writes ``content`` into a fresh temp file in ``path``'s own
    directory and returns its name -- never touches ``path`` itself.
    Kept as its own step (separate from the ``os.replace()`` swap) so
    that, in generate() below, every target's temp file can be fully
    prepared (the slow part: allocating and writing the file's bytes)
    BEFORE any target's real path is mutated (the fast part: the swap
    itself) -- G-012 REMEDIATION ROUND 2, HIGH #3 remaining, step 2."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return tmp_name


def _atomic_write(path: Path, content: str) -> None:
    """Single-file atomic write: temp-file-in-the-same-directory +
    os.replace(), the exact same idiom already used by
    orion.governance.storage.write_yaml and orion.board.storage.
    write_yaml -- never a direct write_text(), which can leave a
    truncated/partial file on disk if the process is interrupted
    mid-write. os.replace() is atomic on the same filesystem, so a
    reader always sees either the old, complete content or the new,
    complete content for THIS ONE FILE, never a mix of the two.

    This per-file guarantee is real, but it is not the same claim as
    "replacing several files together is atomic" -- it is not; see
    generate()'s compensating-rollback mechanism below for how the
    multi-file case is actually made coherent, and
    docs/BOARD_SOURCE_OF_TRUTH.md for the documented, honest scope of
    each guarantee."""
    tmp_name = _prepare_temp_file(path, content)
    try:
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def generate(config: BoardConfiguration | None = None, check_only: bool = False) -> list[DriftResult]:
    """Regenerates every target from the canonical Board configuration.
    Idempotent and deterministic: given the same board.yaml, produces
    byte-identical output every time (stable member order, no
    timestamps). When ``check_only`` is True, never writes -- same
    contract as check_drift(), returned in the same shape so CLI
    callers share one code path for both commands.

    G-012 REMEDIATION ROUND 2 (HIGH #3 remaining, per Codex's second
    REQUEST CHANGES): each individual ``os.replace()`` is atomic on
    the same filesystem (see ``_atomic_write()``/``_prepare_temp_file()``
    above), but writing this module's TWO targets (``AGENTS.md`` and
    ``.ai/BOARD.md``) was, before this fix, a plain sequential loop --
    if the second ``os.replace()`` failed after the first had already
    succeeded, the repository was left with one file regenerated and
    one not, a real inter-file inconsistency. There is still no
    filesystem transaction spanning multiple files (ordinary
    filesystems don't offer one, and this module does not pretend
    otherwise -- see the docstrings above and
    docs/BOARD_SOURCE_OF_TRUTH.md). Instead, this is a compensating
    rollback:

      1. Every target is already rendered AND validated by
         check_drift() above before anything is mutated (missing
         BEGIN/END markers or a missing target file raise
         GeneratorError right there, before any write is attempted).
      2. Every target's ORIGINAL on-disk content is read and kept as a
         backup, and every target's new content is fully written into
         its own temp file (``_prepare_temp_file()``) -- still without
         touching any target's real path. If this step itself fails
         (e.g. disk full while preparing a temp file), no target has
         been touched at all: the leftover temp files are cleaned up
         and a GeneratorError is raised.
      3. Only once every temp file is ready does this function start
         swapping them in, one ``os.replace()`` per target, in the
         same deterministic order as ``_targets()``.
      4. If a LATER ``os.replace()`` fails, every target already
         swapped in this same run is restored -- via another
         ``_atomic_write()`` -- back to the backed-up original content
         read in step 2, any not-yet-consumed temp files are deleted,
         and a GeneratorError describing exactly what failed (and
         whether the rollback itself succeeded) is raised. No target
         is ever left holding a "partially new" or mixed-revision
         state, and a subsequent, unpatched call to generate() can
         complete normally afterward.

    Real, disclosed limit: the restore step in point 4 is itself a
    real filesystem write, and could theoretically fail too (e.g. the
    disk that just failed a replace is now completely full or
    unwritable) -- in that rare case this function raises a
    GeneratorError naming every target it could not restore, rather
    than silently reporting success; manual inspection is genuinely
    required at that point, exactly as the error message says."""
    results = check_drift(config=config)
    if check_only:
        return results

    to_write = [r for r in results if r.has_drift]
    if not to_write:
        return results

    backups: dict[Path, str] = {r.path: r.path.read_text(encoding="utf-8") for r in to_write}

    prepared: list[tuple[Path, str]] = []
    try:
        for result in to_write:
            tmp_name = _prepare_temp_file(result.path, result.rendered)
            prepared.append((result.path, tmp_name))
    except BaseException as exc:
        for _, tmp_name in prepared:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        raise GeneratorError(
            f"generate() failed preparing a temporary file before replacing any target ({exc}); "
            "no target file was modified"
        ) from exc

    replaced: list[Path] = []
    try:
        for path, tmp_name in prepared:
            os.replace(tmp_name, path)
            replaced.append(path)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path in replaced:
            try:
                _atomic_write(path, backups[path])
            except BaseException as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")

        for path, tmp_name in prepared:
            if path not in replaced and os.path.exists(tmp_name):
                os.unlink(tmp_name)

        if rollback_errors:
            raise GeneratorError(
                f"generate() failed replacing a target ({exc}); compensating rollback ALSO failed "
                f"for: {'; '.join(rollback_errors)} -- targets may be left in an inconsistent state, "
                "inspect manually before retrying"
            ) from exc

        raise GeneratorError(
            f"generate() failed replacing a target ({exc}); every target already replaced in this "
            "run was restored to its content from before this call, and no target was left "
            "partially written or holding a mixed revision -- a subsequent generate() call can "
            "retry normally"
        ) from exc

    return results
