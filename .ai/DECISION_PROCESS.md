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
Jules
  ↓
Nemotron
  ↓
Luis
  ↓
Merge
```

Any change to application code. Implementation never begins without an approved GitHub Issue.

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

## Standing Principles

- **Avoid vendor lock-in** — prefer portable, replaceable choices over proprietary dependencies.
- **Avoid overengineering** — build only what the current, approved scope requires.
- **Separation of duties** — architecture, implementation, review, and approval remain distinct responsibilities at all times.
- **No invented governance** — if a situation isn't covered by an existing rule, stop and ask Luis rather than assuming one. See `AGENTS.md`.
