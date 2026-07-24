# PROTOCOL.md — Multi-Agent Communication Protocol

| Field | Value |
|---|---|
| Document type | Operational protocol (new capability) |
| Status | Active |
| Version | 1.1.0 |
| Layered on | `.ai/DECISION_PROCESS.md` (authoritative governance paths), `.ai/HANDOFF_TEMPLATE.md`, `.orion/TEAM.md` (role mapping) |
| Does not replace | `.ai/BOARD.md`, `.ai/ROLES.md`, `.ai/DECISION_PROCESS.md` |

## Purpose

`.ai/DECISION_PROCESS.md` already defines three governance paths (Minor Documentation, Architecture or Governance, Implementation) and names who moves work through each one. This document does not change those paths. It formalizes the mechanics *within* them: what agents hand each other, in what state, and what happens when they disagree — so the same rules apply no matter which concrete agent currently holds a role in `.orion/TEAM.md`.

Every rule below is written in terms of **abstract roles** (Product Owner, CTO, Architect, Builder, Reviewer, GitOps, Research, Documentation), not concrete agents. Resolve a role to its current implementation via `.orion/TEAM.md`.

## Core rule

Agents do not coordinate through free-form conversation. They coordinate through artifacts that already exist in this repository's toolchain — GitHub Issues, Pull Requests, Architecture Decision Records (`docs/DECISIONS.md`), and Handoff Records (`.ai/HANDOFF_TEMPLATE.md`) — committed or filed where anyone, including an agent with no memory of how the artifact came to exist, can read it and act on it. No new artifact types are introduced by this protocol; it governs how the existing ones move between roles.

## 1. Artifacts and their roles

| Artifact | Raised by | Consumed by | Already defined in |
|---|---|---|---|
| GitHub Issue | Product Owner (or any role, approved by Product Owner) | Builder | `CONTRIBUTING.md` |
| Design discussion / Research findings | CTO, Architect, or Research | Architect, Product Owner | Captured inline in the Issue or folded into an ADR's Context |
| Architecture Decision Record (ADR) | CTO or Architect | Reviewer, Product Owner (ratifies) | `docs/DECISIONS.md` |
| Mission | Architect or Product Owner | Builder | [`.orion/missions/README.md`](.orion/missions/README.md) and `MISSION_TEMPLATE.md` |
| Pull Request | Builder | Reviewer, GitOps | `.github/PULL_REQUEST_TEMPLATE.md` |
| Handoff Record | Any role transferring work | Receiving role | `.ai/HANDOFF_TEMPLATE.md` |
| Retrospective Note | Documentation (or whoever closes the work) | All roles | New under this protocol — filed as a comment on the closing Issue/PR, or as a `docs/DECISIONS.md` entry when it produces a process change |

No implementation work is consumed by a Builder without a Mission. A Mission's lifecycle (Draft → Approved → In Progress → Review → Blocked → Completed → Merged → Archived, defined in `.orion/missions/README.md`) is a justified specialization of the generic approval flow in §6 below: unlike other artifacts, a Mission represents ongoing execution, not a single approval event, so it needs states none of the others do.

## 2. Inputs

An artifact is not valid input to the next role until it satisfies the validation already required by `.ai/DECISION_PROCESS.md` for its governance path, plus:

- It references the artifact that justifies it (an Issue references the need behind it; a Pull Request references its Issue or ADR; a Handoff Record references what is being handed off and why).
- It is filed where the toolchain expects it (repository, not a private message or session-only note).

A role receiving an incomplete artifact returns it to the author with what is missing, rather than acting on assumptions.

## 3. Outputs

An artifact is not authoritative output until its state genuinely reflects reality:

- An Issue is not "approved" until Luis has approved it, per `CONTRIBUTING.md`.
- An ADR is not "Accepted" until it carries Author, Reviewed by, and Approved by, per the template in `docs/DECISIONS.md`.
- A Pull Request is not ready to merge until it carries an independent Reviewer sign-off, per `.ai/ROLES.md`.

## 4. Validation

Validation gates are the ones already defined by `.ai/DECISION_PROCESS.md`'s three governance paths, applied per artifact:

- **Issues** are validated by Product Owner approval before Builder may start.
- **ADRs** are validated against the template fields in `docs/DECISIONS.md` (Title, Status, Author, Reviewed by, Approved by, Date, Supersedes, Context, Decision, Consequences) — incomplete fields mean the ADR is not yet Accepted.
- **Pull Requests** are validated against the Definition of Done and Quality Standards in `.ai/DECISION_PROCESS.md` before Reviewer sign-off.

## 5. Approval flow

Approval flow is exactly the three paths already defined in `.ai/DECISION_PROCESS.md`:

```
Minor Documentation:        Author → Luis
Architecture / Governance:  Author → Reviewer → Luis → Merge
Implementation:             Issue approved → Builder → Reviewer → Luis → Merge
```

This protocol adds no additional approval stage. What it adds is precision about *who* — by role, not by name — occupies each position in the flow, resolved through `.orion/TEAM.md` at the time the work happens.

## 6. Conflict resolution

1. **Direct resolution.** The two roles in conflict exchange one round of artifact revision (for example, a revised ADR responding to Reviewer feedback) attempting to resolve it within their own authority as defined in `.ai/ROLES.md`.
2. **Bounded retry.** At most one additional round is attempted. Conflict resolution is not an open-ended negotiation.
3. **Escalation.** If unresolved, either role escalates to Luis, per the Escalation rule already defined in `.ai/DECISION_PROCESS.md`.

No role resolves a conflict by acting outside the authority `.ai/ROLES.md` grants it. An action taken outside that authority is invalid and must be reverted, regardless of whether it "solved" the immediate disagreement.

## 7. Escalation

Escalation triggers, in addition to unresolved conflict (§6):

- An artifact sits unactioned past a reasonable service window for its governance path.
- A role believes a decision was made outside the authority `.ai/ROLES.md` grants the deciding role.
- A security, safety, or irreversibility concern is identified that the current role cannot resolve alone.

Every escalation goes to Luis, per `.ai/DECISION_PROCESS.md`. His resolution is binding and, where it sets precedent, is recorded as an ADR in `docs/DECISIONS.md`.

---

## Amendment log

| Version | Date | Change | Approved by |
|---|---|---|---|
| 1.0.0 | 2026-07-17 | Initial protocol, layered on existing `.ai/DECISION_PROCESS.md` governance paths | Luis Aguirre |
| 1.1.0 | 2026-07-17 | Added Mission as a new artifact type. Part of MISSION-0001 (ADR-0005). | Luis Aguirre |
