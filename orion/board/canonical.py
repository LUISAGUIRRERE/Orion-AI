"""Loads and validates the Single Source of Truth for the AI Board's
composition (MISSION G-012): ``.ai/board.yaml``.

This is deliberately a *different* concept from
orion.board.member_registry's own BoardMember: this module models the
real AI Board *seats* (who: Luis Aguirre, ChatGPT, Claude, Jules,
Nemotron, AutoClaw) exactly as already decided in ADR-0001 and
described in ``.ai/BOARD.md``/``.ai/ROLES.md``/``AGENTS.md``.
orion.board.member_registry models Mission *pipeline stages*
(Architect/Builder/Reviewer/QA/GitOps/Experience) and already existed
before this Mission (B-011) -- it is not duplicated or replaced here,
only made to read its ``board_seat`` label from this canonical source
instead of a second, hand-maintained string.

Uses only PyYAML and the standard library, both already a dependency
of every other module in ``orion.governance``/``orion.business`` --
no new dependency introduced, per this Mission's own constraint.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from orion.bridge import storage as bridge_storage

REPO_ROOT: Path = bridge_storage.REPO_ROOT
BOARD_YAML_PATH: Path = REPO_ROOT / ".ai" / "board.yaml"

SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1,)
VALID_STATUSES: tuple[str, ...] = ("active", "inactive", "proposed")


class BoardConfigurationError(ValueError):
    """Raised for any invalid, ambiguous, or unsafe ``.ai/board.yaml``
    -- always with an explicit, actionable message naming the exact
    member/field at fault, never a bare stack trace."""


@dataclass(frozen=True)
class CanonicalBoardMember:
    id: str
    display_name: str
    role: str
    status: str
    responsibilities: tuple[str, ...]
    restrictions: tuple[str, ...]
    capabilities: tuple[str, ...]
    documentation_path: str | None
    supersedes: str | None

    def seat_label(self) -> str:
        """The exact short label orion.board.member_registry's own
        ``board_seat`` field already used before this Mission (e.g.
        "Jules (Lead Software Engineer)") -- now derived, not
        hardcoded."""
        return f"{self.display_name} ({self.role})"


@dataclass(frozen=True)
class BoardConfiguration:
    schema_version: int
    board_version: int
    members: tuple[CanonicalBoardMember, ...]

    def get(self, member_id: str) -> CanonicalBoardMember | None:
        for member in self.members:
            if member.id == member_id:
                return member
        return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BoardConfigurationError(message)


def _validate_member_shape(raw: Any, index: int) -> None:
    _require(isinstance(raw, dict), f"members[{index}] must be a mapping, got {type(raw).__name__}")
    _require(bool(raw.get("id")), f"members[{index}] is missing a required 'id'")
    _require(bool(raw.get("display_name")), f"member '{raw.get('id')}' is missing a required 'display_name'")
    _require(bool(raw.get("role")), f"member '{raw.get('id')}' has an empty 'role'")
    status = raw.get("status")
    _require(
        status in VALID_STATUSES,
        f"member '{raw.get('id')}' has an invalid status '{status}' (must be one of {VALID_STATUSES})",
    )
    for field_name in ("responsibilities", "restrictions", "capabilities"):
        value = raw.get(field_name, [])
        _require(isinstance(value, list), f"member '{raw.get('id')}'.{field_name} must be a list, got {type(value).__name__}")
        for item in value:
            _require(
                isinstance(item, str) and item.strip(),
                f"member '{raw.get('id')}'.{field_name} contains a malformed (non-string or empty) entry",
            )
    doc_path = raw.get("documentation_path")
    _require(
        doc_path is None or isinstance(doc_path, str),
        f"member '{raw.get('id')}'.documentation_path must be a string or null",
    )


def _parse_member(raw: dict) -> CanonicalBoardMember:
    return CanonicalBoardMember(
        id=raw["id"],
        display_name=raw["display_name"],
        role=raw["role"],
        status=raw["status"],
        responsibilities=tuple(raw.get("responsibilities", [])),
        restrictions=tuple(raw.get("restrictions", [])),
        capabilities=tuple(raw.get("capabilities", [])),
        documentation_path=raw.get("documentation_path"),
        supersedes=raw.get("supersedes"),
    )


def parse_and_validate(data: Any, repo_root: Path = REPO_ROOT) -> BoardConfiguration:
    """Real, from-scratch validation of an already-parsed YAML
    document -- never trusts partial validation done elsewhere. Raises
    BoardConfigurationError with a specific, actionable message on the
    first problem found; never silently drops or fabricates data."""
    _require(isinstance(data, dict), "board.yaml must contain a mapping at the top level")

    schema_version = data.get("schema_version")
    _require(isinstance(schema_version, int), "board.yaml is missing a valid integer 'schema_version'")
    _require(
        schema_version in SUPPORTED_SCHEMA_VERSIONS,
        f"board.yaml declares schema_version {schema_version}, but this ORION only supports {SUPPORTED_SCHEMA_VERSIONS}",
    )

    board_version = data.get("board_version")
    _require(isinstance(board_version, int), "board.yaml is missing a valid integer 'board_version'")

    raw_members = data.get("members")
    _require(isinstance(raw_members, list) and len(raw_members) > 0, "board.yaml must declare at least one member under 'members'")

    for index, raw in enumerate(raw_members):
        _validate_member_shape(raw, index)

    members = tuple(_parse_member(raw) for raw in raw_members)

    seen_ids: set[str] = set()
    seen_display_names: set[str] = set()
    all_ids = {m.id for m in members}
    for member in members:
        _require(member.id not in seen_ids, f"duplicate member id '{member.id}'")
        seen_ids.add(member.id)

        _require(
            member.display_name not in seen_display_names,
            f"duplicate display_name '{member.display_name}' (member '{member.id}')",
        )
        seen_display_names.add(member.display_name)

        if member.documentation_path is not None:
            doc_file = repo_root / member.documentation_path
            _require(
                doc_file.is_file(),
                f"member '{member.id}' references missing documentation file: {member.documentation_path}",
            )

        if member.supersedes is not None:
            _require(
                member.supersedes in all_ids,
                f"member '{member.id}' has supersedes='{member.supersedes}', which is not a known member id",
            )

    return BoardConfiguration(schema_version=schema_version, board_version=board_version, members=members)


def load_board_config(path: Path = BOARD_YAML_PATH, repo_root: Path = REPO_ROOT) -> BoardConfiguration:
    """Reads and validates ``.ai/board.yaml`` (or the given path).
    Raises BoardConfigurationError for any missing file, malformed
    YAML, or schema/reference violation -- never returns a partial or
    fabricated configuration."""
    if not path.is_file():
        raise BoardConfigurationError(f"canonical Board configuration not found at {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise BoardConfigurationError(f"board.yaml is not valid YAML: {exc}") from exc
    return parse_and_validate(data, repo_root=repo_root)
