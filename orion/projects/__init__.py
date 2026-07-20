"""ORION's Multi-Project Engine.

ORION does not administer a single repository — it administers an
organization made of multiple companies, each owning one or more
projects. This package is the Project Registry and the layer that
makes the rest of ORION (Command Bridge, Builder, COO, Execution
Pipeline) project-aware, without rewriting any of them: a mission now
optionally carries a ``project_id``, and everything here reads that
field to group, report, and namespace work by project.

Nothing in ``orion.agents.builder`` or ``orion.agents.coo`` is modified
by this package beyond the minimal, backward-compatible additions
documented in this Sprint's delivery notes (a `current_project_id`
field on BuilderState). The Command Bridge gains three optional
Mission fields (project_id, repository, working_branch) — everything
else here is a new, additive layer on top.
"""
