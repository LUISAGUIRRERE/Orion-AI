# TEAM.md — Role-to-Implementation Mapping

This document maps ORION OS's abstract, vendor-independent roles (defined conceptually in `ORION.md`, operationalized in `PROTOCOL.md` and `WORKFLOW.md`) to the concrete agents currently filling them.

This mapping is intentionally replaceable. Any row may change — a new tool, model, or human can take over a role — without requiring a change to `ORION.md`, `PROTOCOL.md`, or `WORKFLOW.md`. Only this file, and where relevant `.ai/ROLES.md` and `AGENTS.md`, need to change.

`.ai/ROLES.md` and `AGENTS.md` remain the authoritative source for what each named Board seat may and may not do. This file only records **which current implementation answers to which abstract function** — it does not redefine responsibilities, authority, or boundaries.

## Current mapping

| Abstract role | Current implementation | Corresponding Board seat (`.ai/ROLES.md`) |
|---|---|---|
| Product Owner | Luis Aguirre | CEO / Product Owner |
| CTO | ChatGPT | Chief AI Architect |
| Architect | Claude Code | Chief Software Architect |
| Builder | Codex | — (not yet defined as a distinct Board seat; see note below) |
| Reviewer | Nemotron | Principal Engineering Reviewer |
| GitOps | Jules | — (previously mapped to "Lead Software Engineer" / implementation; reassigned here to repository mechanics, see note below) |
| Research | Unassigned | — |
| Documentation | Unassigned (currently absorbed by Architect) | — |

## Open items

This mapping introduces two implementations (Codex as Builder, Jules as GitOps) and two role reassignments relative to the Board membership currently recorded in `.ai/BOARD.md` and `.ai/ROLES.md`:

- `.ai/ROLES.md` describes Jules as "Lead Software Engineer" implementing approved Issues (the Builder function), not GitOps.
- `.ai/ROLES.md` does not currently mention Codex at all.
- AutoClaw ("Operations Engineer" in `.ai/BOARD.md`) is not represented in this mapping.
- Research and Documentation have no current dedicated implementation; today that work is absorbed ad hoc by whoever holds Architect.

None of this overrides `.ai/BOARD.md` or `.ai/ROLES.md` — those remain authoritative. This table reflects the mapping as directed for ORION OS's multi-agent protocol layer. Reconciling it with the Board's formal seat definitions (updating `.ai/ROLES.md`/`.ai/BOARD.md`, or accepting the two layers as deliberately distinct) is an open governance item for Luis to resolve on the Architecture or Governance path defined in `.ai/DECISION_PROCESS.md`.

## Amendment log

| Date | Change | Approved by |
|---|---|---|
| 2026-07-17 | Initial mapping established | Luis Aguirre |
