# Decision Process

This describes how a change moves from idea to merged work in ORION OS, and how decisions are recorded.

## Governance Paths

There are three governance paths, depending on the type of change.

### Minor Documentation

```
Claude
  ↓
Luis approval
```

A change qualifies as Minor Documentation **only** if it does not modify any of the following:

- Any ADR
- Any role or responsibility under `.ai/`
- The AI Board
- Governance rules
- Approval authority
- Security rules
- The ORION mission
- Project non-goals
- MVP scope
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`

If a change touches any item on that list, it automatically follows the Architecture or Governance path below, regardless of how small it appears.

### Architecture or Governance

```
Claude
  ↓
Nemotron review
  ↓
Luis approval
  ↓
Merge
```

Any change to architecture, product vision, governance rules, or any item listed above under Minor Documentation. Must be recorded as an ADR in `docs/DECISIONS.md`.

### Implementation

```
Issue approved
  ↓
Mission approved
  ↓
Jules
  ↓
Nemotron
  ↓
Luis
  ↓
Merge
```

Any change to application code. Implementation never begins without an approved GitHub Issue, and never begins without an Approved Mission defining exactly what may be created or modified. See [`.orion/missions/README.md`](../.orion/missions/README.md) for how a Mission is authored and approved.

## Escalation

Any disagreement between AI Board members is escalated to Luis. His decision is final and does not require consensus from the other roles.

## Recording Decisions

Every major architectural or governance decision must be recorded in `docs/DECISIONS.md` as an ADR, including:

- Title
- Status
- Author
- Reviewed by
- Approved by
- Date
- Supersedes
- Context
- Decision
- Consequences

Documentation is treated as institutional memory: if a decision isn't recorded, it doesn't count as made.

## Definition of Done

A change is Done only when all of the following hold:

- It traces to an approved GitHub Issue (implementation) or an accepted ADR (architecture/governance).
- It was implemented consistently with the Issue or ADR it claims to satisfy; any deviation is documented in the Pull Request, not silent.
- It has automated tests proportional to its risk, and they pass.
- It was independently reviewed by the current Reviewer implementation (see `.orion/TEAM.md`), and that reviewer did not author the change.
- It meets the Quality Standards below.
- Documentation affected by the change (`README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, or any other affected document) was updated in the same Pull Request.
- It was approved and merged by Luis, following the applicable governance path above.

This applies uniformly regardless of which concrete agent performed the work — see `.orion/TEAM.md` for who currently holds each function.

## Quality Standards

- **Correctness.** Behavior matches the approved Issue or ADR; deviations are documented, not silent.
- **Testability.** Nothing is considered complete without a test strategy; untestable designs are flagged during architecture review rather than accepted later.
- **Security.** No secret, credential, or token is ever committed. Inputs are treated as untrusted by default. Security-relevant changes require explicit independent review sign-off before merge.
- **Readability.** Code and documents are written for the next agent to read cold, without access to the conversation that produced them.
- **Consistency.** New work follows conventions already established in the repository unless a documented ADR changes them.
- **Minimalism.** The smallest change that correctly solves the problem is preferred over the most general one — consistent with "Avoid overengineering" below.
- **Observability.** Anything that can fail in production must be detectable without reading source code.

## Standing Principles

- **Avoid vendor lock-in** — prefer portable, replaceable choices over proprietary dependencies.
- **Avoid overengineering** — build only what the current, approved scope requires.
- **Separation of duties** — architecture, implementation, review, and approval remain distinct responsibilities at all times.
- **No invented governance** — if a situation isn't covered by an existing rule, stop and ask Luis rather than assuming one. See `AGENTS.md`.
