# ORION OS

**ORION OS** is an AI-powered Business Intelligence Operating System.

## Mission

ORION exists to understand businesses, discover opportunities, recommend valuable products and services, coordinate specialized AI agents, and continuously improve its own knowledge.

## What ORION Is Not

- ORION is **not** a CRM.
- ORION is **not** a scraper.
- ORION is **not** an automation platform.

ORION is an operating system that coordinates specialized AI agents to help businesses grow.

## Status

**Pre-alpha. Documentation-first. No production code yet.**

The repository currently contains governance and architecture documentation only. The first software component — the Executive Orchestrator — is described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) but not yet implemented.

## Repository Layout

- [`AGENTS.md`](AGENTS.md) — entry point describing the AI Board and how each AI role should operate in this repository.
- [`.ai/`](.ai/) — AI Board governance: membership, roles, decision process, handoff template, and per-agent system prompts.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and MVP component descriptions.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decision record (ADR) log.

## How Work Gets Done

1. A change is proposed and, if architectural, recorded as a decision in `docs/DECISIONS.md`.
2. Implementation work begins only from an **approved GitHub Issue**.
3. Changes are submitted as Pull Requests and reviewed independently — no AI approves its own work.
4. Luis Aguirre (CEO / Product Owner) holds final authority on all product and business decisions.

See [`.ai/DECISION_PROCESS.md`](.ai/DECISION_PROCESS.md) for the full governance workflow.
