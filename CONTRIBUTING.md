# Contributing to ORION OS

ORION OS is pre-alpha and documentation-first. This document describes how work happens in this repository. For AI agents, see [`AGENTS.md`](AGENTS.md); for full governance, see [`.ai/`](.ai/).

## Documentation-First Philosophy

Documentation is ORION's institutional memory. A component is described in `docs/ARCHITECTURE.md` before it is implemented, and a decision is recorded in `docs/DECISIONS.md` before it is treated as final. If it isn't written down, it didn't happen.

## GitHub Issues

All implementation work begins with an approved GitHub Issue. An Issue must be approved by Luis Aguirre before any code is written. Issues should reference the relevant section of `docs/ARCHITECTURE.md` or the ADR that authorizes the work.

## Pull Requests

Every Pull Request must use the checklist in [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md). A Pull Request must:

- Reference an approved Issue (for implementation) or an ADR (for architecture/governance changes).
- Be reviewed independently by Nemotron.
- Be approved and merged by Luis. No AI Board member approves or merges its own work.

## ADR Workflow

Major architectural or governance decisions are recorded as Architecture Decision Records (ADRs) in `docs/DECISIONS.md`. Every ADR includes: Title, Status, Author, Reviewed by, Approved by, Date, Context, Decision, and Consequences. See [`.ai/DECISION_PROCESS.md`](.ai/DECISION_PROCESS.md) for the three governance paths (minor documentation, architecture/governance, implementation) that determine who touches a change before it merges.

## AI Board Workflow

ORION OS is built by an AI Board of one human and five AI roles, each with a distinct responsibility. See [`.ai/BOARD.md`](.ai/BOARD.md) for membership and operating model, [`.ai/ROLES.md`](.ai/ROLES.md) for what each role may and may not do, and [`.ai/prompts/`](.ai/prompts/) for each role's system prompt. No AI approves its own work, and Luis always has final authority.

## Status

Pre-alpha. No application code, no CI, no automation exist yet. Contributions at this stage are documentation and governance only, unless an approved Issue says otherwise.
