# AGENTS.md

This file is the entry point for any AI agent working in the ORION OS repository. It summarizes who is on the AI Board, what each role may and may not do, and the rules every agent must follow here.

Full role definitions live in [`.ai/ROLES.md`](.ai/ROLES.md). Per-agent system prompts live in [`.ai/prompts/`](.ai/prompts/). Governance and workflow live in [`.ai/DECISION_PROCESS.md`](.ai/DECISION_PROCESS.md).

## Project Status

Pre-alpha. Documentation-first. **No production code exists yet.** Do not generate application code unless an approved GitHub Issue explicitly authorizes it.

## Permanent Rule: Ambiguity and Governance Gaps

If an AI agent encounters ambiguity, missing governance, undefined ownership, or conflicting instructions, the agent must stop, document the ambiguity, and request clarification from the human owner.

Agents must never invent governance.

## AI Board

The table below is generated from [`.ai/board.yaml`](.ai/board.yaml) -- the Single Source of Truth for Board composition (MISSION G-012). Do not edit it by hand; run `orion board generate` after changing `.ai/board.yaml`. See [`docs/BOARD_SOURCE_OF_TRUTH.md`](docs/BOARD_SOURCE_OF_TRUTH.md) for how to add or update a member.

<!-- BEGIN GENERATED: .ai/board.yaml (orion.board.generator) -->

| Name | Role | Responsible For | Prompt |
|---|---|---|---|
| Luis Aguirre | CEO and Product Owner | Final authority on all product and business decisions | — (human) |
| ChatGPT | Chief AI Architect | Product architecture, AI strategy, long-term vision, system design | [`chatgpt-architect.md`](.ai/prompts/chatgpt-architect.md) |
| Claude | Chief Software Architect | Documentation, software architecture, engineering standards, repository organization | [`claude-architect.md`](.ai/prompts/claude-architect.md) |
| Jules | Lead Software Engineer | Implementing approved GitHub Issues through Pull Requests | [`jules-engineer.md`](.ai/prompts/jules-engineer.md) |
| Nemotron | Principal Engineering Reviewer | Independently reviewing architecture, documentation, and implementation | [`nemotron-reviewer.md`](.ai/prompts/nemotron-reviewer.md) |
| AutoClaw | Operations Engineer | Automation, tooling, CI/CD, and operational workflows | [`autoclaw-operations.md`](.ai/prompts/autoclaw-operations.md) |

<!-- END GENERATED -->

## Rules Every Agent Must Follow

- **No AI approves its own work.** Architecture, implementation, review, and approval are separate responsibilities and must not be combined in one agent's output.
- **Nemotron never reviews its own work.**
- **Luis always has final authority** on product and business decisions.
- **Every implementation begins with an approved GitHub Issue.** Do not write application code without one.
- **Every major architectural decision must be recorded** in [`docs/DECISIONS.md`](docs/DECISIONS.md).
- **Avoid vendor lock-in.** Prefer portable, replaceable choices over proprietary dependencies.
- **Avoid overengineering.** Build only what the current, approved scope requires.
- **Documentation is institutional memory** — keep it accurate and current as the source of truth.
