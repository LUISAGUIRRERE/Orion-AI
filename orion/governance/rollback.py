"""Real rollback for a Mission whose changes degrade the project.

Grounded in how orion.execution.pipeline actually works (verified by
reading it, not assumed): a Mission's changes live entirely on its own
``mission/<id>`` branch -- the Pipeline commits and pushes that branch
but never merges it into ``main`` itself (see
orion.execution.pipeline.run, which stops after git_manager.push()).
That means "revertir" a mission that has not yet been merged is always
safe and real: abandon its branch. A branch that has *already* been
merged into main by a human via a PR is a different, much more
consequential situation -- this module deliberately refuses to rewrite
shared history automatically for that case and instead reports it
plainly, so a real human decision (exactly this Sprint's own
"decision de arquitectura o de negocio" carve-out) is what handles it,
not an automatic force-revert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orion.execution import git_manager
from orion.governance import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RollbackResult:
    mission_id: str
    branch: str
    rolled_back: bool
    reason: str
    evidence: dict = field(default_factory=dict)
    performed_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "branch": self.branch,
            "rolled_back": self.rolled_back,
            "reason": self.reason,
            "evidence": self.evidence,
            "performed_at": self.performed_at,
        }


def rollback_mission(mission_id: str, branch: str, repo_root=None) -> RollbackResult:
    """Real rollback: abandons ``branch`` (the mission's own, never
    shared history) if it exists locally and was never merged into
    main. Never force-pushes, never rewrites main. Every attempt --
    successful or refused -- is recorded as evidence, never silently
    dropped."""
    repo_root = repo_root or git_manager.REPO_ROOT
    evidence: dict = {}

    try:
        merged_into_main = git_manager.is_branch_merged(branch, base="main", repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001 - a git failure here must not crash Governance
        evidence["git_error"] = str(exc)
        result = RollbackResult(
            mission_id=mission_id,
            branch=branch,
            rolled_back=False,
            reason=f"No se pudo inspeccionar la rama '{branch}' via git: {exc}",
            evidence=evidence,
        )
        _record(result)
        return result

    if merged_into_main:
        result = RollbackResult(
            mission_id=mission_id,
            branch=branch,
            rolled_back=False,
            reason=(
                f"La rama '{branch}' ya fue fusionada a main -- revertir historia compartida "
                "automaticamente no es seguro. Se requiere una decision humana explicita."
            ),
            evidence=evidence,
        )
        _record(result)
        return result

    try:
        git_manager.checkout("main", repo_root=repo_root)
        git_manager.delete_local_branch(branch, repo_root=repo_root, force=True)
        evidence["local_branch_deleted"] = branch
    except Exception as exc:  # noqa: BLE001
        evidence["git_error"] = str(exc)
        result = RollbackResult(
            mission_id=mission_id,
            branch=branch,
            rolled_back=False,
            reason=f"No se pudo eliminar la rama local '{branch}': {exc}",
            evidence=evidence,
        )
        _record(result)
        return result

    result = RollbackResult(
        mission_id=mission_id,
        branch=branch,
        rolled_back=True,
        reason=f"Rama '{branch}' abandonada localmente: nunca se fusiono a main, sin impacto en historia compartida.",
        evidence=evidence,
    )
    _record(result)
    return result


def _record(result: RollbackResult) -> None:
    storage.ensure_governance_storage()
    storage.append_yaml_list(storage.rollbacks_path(), result.to_dict())


def list_rollbacks() -> list[dict]:
    return storage.read_yaml(storage.rollbacks_path(), [])
