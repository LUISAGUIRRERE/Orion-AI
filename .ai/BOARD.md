# AI Board

The AI Board is ORION OS's governance body. It combines one human with final authority and five specialized AI roles, each with a distinct and non-overlapping responsibility.

## Purpose

The Board exists to keep architecture, implementation, review, and approval as separate responsibilities as ORION OS is built — so no single actor (human or AI) can propose, build, and approve the same piece of work.

## Membership

| Name | Role | Authority |
|---|---|---|
| Luis Aguirre | CEO and Product Owner | Final authority on all product and business decisions |
| ChatGPT | Chief AI Architect | Product architecture, AI strategy, long-term vision, system design |
| Claude | Chief Software Architect | Documentation, software architecture, engineering standards, repository organization |
| Jules | Lead Software Engineer | Implements approved GitHub Issues through Pull Requests |
| Nemotron | Principal Engineering Reviewer | Independently reviews architecture, documentation, and implementation; never reviews its own work |
| AutoClaw | Operations Engineer | Automation, tooling, CI/CD, and operational workflows |

Full responsibilities and boundaries for each seat are defined in [`ROLES.md`](ROLES.md).

## Operating Model

- The Board operates asynchronously — there are no scheduled meetings; work moves through GitHub Issues, Pull Requests, and recorded decisions.
- Architectural proposals come from ChatGPT (AI strategy) or Claude (software architecture) and are recorded in [`../docs/DECISIONS.md`](../docs/DECISIONS.md).
- Implementation happens only after Luis approves a GitHub Issue.
- Every Pull Request is reviewed by Nemotron before Luis gives final approval.
- Disagreements between Board members are escalated to Luis, whose decision is final.

See [`DECISION_PROCESS.md`](DECISION_PROCESS.md) for the step-by-step workflow and [`HANDOFF_TEMPLATE.md`](HANDOFF_TEMPLATE.md) for how work is handed off between members.
