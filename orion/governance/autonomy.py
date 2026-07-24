"""What ORION is allowed to do alone, as real facts derived from an
ExecutionMode's ModeProfile plus a change's Category -- never a second,
parallel copy of the mode/category logic. orion.governance.policy_engine
reads these functions instead of re-deriving mode/category behavior
itself, so there is exactly one place "puede actuar solo" is decided.
"""

from __future__ import annotations

from orion.governance.change_classifier import ChangeCategory
from orion.governance.execution_mode import ModeProfile

# Categories APPROVAL ENGINE's own brief lists as "never ask for":
# bugs locales, imports, tipado, tests, refactors pequeños. Mapped
# onto this Sprint's eight real categories.
_NEVER_ASK_CATEGORIES = {
    ChangeCategory.BUG_FIX,
    ChangeCategory.REFACTOR,
    ChangeCategory.OPTIMIZATION,
    ChangeCategory.DOCUMENTATION,
}

# Categories APPROVAL ENGINE's own brief lists as "always ask for":
# arquitectura, APIs publicas, modelo de negocio, seguridad, cambios
# destructivos. Mapped onto this Sprint's eight real categories --
# Breaking Change is the closest real category to "cambios
# destructivos"/"APIs publicas", Architecture to "arquitectura".
_ALWAYS_ASK_CATEGORIES = {
    ChangeCategory.ARCHITECTURE,
    ChangeCategory.BREAKING_CHANGE,
}


def requires_human_review_by_category_alone(category: ChangeCategory) -> bool:
    """True when the category itself is always in the human-review
    set, regardless of risk/confidence/mode -- Architecture and
    Breaking Change never get to skip review purely on good numbers."""
    return category in _ALWAYS_ASK_CATEGORIES


def is_never_ask_category(category: ChangeCategory) -> bool:
    return category in _NEVER_ASK_CATEGORIES


def can_act_autonomously(profile: ModeProfile, category: ChangeCategory) -> bool:
    """Real, mode-and-category-derived answer to "can ORION act
    without asking right now". MODE_DEVELOPMENT never can (asks
    everything, by explicit design). Every other mode still always
    stops for the always-ask categories -- a mode never overrides a
    category's own review requirement, only whether the *rest* of the
    categories still need to ask."""
    if profile.requires_approval_for_everything:
        return False
    if requires_human_review_by_category_alone(category):
        return False
    return profile.can_auto_fix_bugs or profile.can_apply_local_fixes
