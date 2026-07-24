"""ORION's Autonomous Execution Pipeline.

Takes a mission the Builder has been assigned and carries it through a
real development cycle on the repository itself: a workspace is
prepared, a mission branch is created, the mission's existing handler
does the work, validations run, and — only if they pass — the change
is committed and pushed, with a Pull Request URL ready for review.

No module outside ``git_manager.py`` is allowed to run git commands
directly. No module outside ``task_runner.py`` decides what the
mission actually does — that responsibility stays with the Builder's
existing handler registry (Sprint 006). This package only adds the
git lifecycle around it.
"""
