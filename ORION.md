# ORION.md — ORION OS Charter

| Field | Value |
|---|---|
| Document type | Charter |
| Status | Active |
| Version | 1.0.0 |
| Owner | Board (Product Owner + Architect) |
| Applies to | All agents, human or AI, operating under ORION OS |

## Purpose of this document

ORION OS is an operating system for software delivery, not a piece of software itself. It does not compile, run, or ship. It coordinates independent software engineering agents — human or artificial — around a shared vision, a shared set of rules, and a shared repository, so that work produced by different agents at different times is coherent, auditable, and safe to merge.

This document is the constitution of that system. `ROLES.md`, `PROTOCOL.md`, and `WORKFLOW.md` derive their authority from it. Where any other document conflicts with this one, this document prevails until formally amended.

---

## 1. Vision

A software organization where any number of independent engineering agents — regardless of who or what built them — can contribute to the same product, at the same time, without a human having to mediate every handoff, because the rules of collaboration are written down, machine-readable, and enforced by process rather than by personality.

## 2. Mission

ORION OS exists to:

1. Define unambiguous roles, authority, and accountability for every participant in the software lifecycle.
2. Replace ad-hoc conversation between agents with structured, versioned, reviewable documents.
3. Guarantee that every unit of work — idea, design, code, or decision — can be traced from origin to release.
4. Keep the system independent of any specific AI vendor, model, or tool, so that the coordination layer outlives any individual agent.
5. Make quality, safety, and reversibility non-negotiable defaults rather than optional practices.

## 3. Principles

1. **Documents over conversation.** Agents communicate through artifacts with defined schemas, not free-form chat. A decision that only exists in a conversation does not exist.
2. **Vendor neutrality.** No document, role, or process may name or depend on a specific AI provider or model. Any agent capable of fulfilling a role's responsibilities may be assigned that role.
3. **Explicit authority.** Every role has a bounded, written scope of what it may decide alone, what it may propose, and what it may never do. Silence is not authority.
4. **Segregation of duties.** The agent that builds a change is never the agent that approves it. Authorship and approval are always separated.
5. **Small, verifiable increments.** Work is decomposed until each unit can be independently reviewed, tested, and reverted.
6. **Traceability by default.** Every artifact links to the request, decision, or issue that justifies its existence. No orphan work.
7. **Reversibility.** Every change that reaches `main` must be revertible without special knowledge. If it cannot be reverted safely, it cannot be merged.
8. **Memory is a first-class citizen.** Knowledge produced during the lifecycle (decisions, retrospectives, research) is captured as durable, searchable documentation — not left in transient sessions.
9. **Quality is not a phase.** Quality gates apply continuously (design, build, review, release), not only at the end.
10. **Human accountability.** A human (the Board) is always the final point of accountability for what ships, regardless of how much of the work was produced autonomously.

## 4. Governance

ORION OS is governed by a **Board**, composed at minimum of one human Product Owner and one Architect (human or delegated). The Board:

- Owns this document and all root-level governance documents (`ORION.md`, `ROLES.md`, `PROTOCOL.md`, `WORKFLOW.md`).
- Approves amendments to governance documents (see §5).
- Resolves escalations that roles cannot resolve between themselves (see `PROTOCOL.md`).
- Is accountable for every release, independent of which agents produced the underlying work.

Governance artifacts (board composition, standing decisions, meeting or session records) live under `.ai/BOARD.md`. Operational role assignments for a given engagement live under `.ai/ROLES.md` and must remain consistent with the definitions in this repository's `ROLES.md`; the former assigns agents to roles, the latter defines what the roles mean.

Governance is deliberately lightweight: it exists to make disagreements resolvable, not to slow down routine work. Routine work never requires Board involvement; only exceptions, conflicts, and amendments do.

## 5. Decision Process

Decisions are classified by blast radius:

| Class | Examples | Who decides | Record required |
|---|---|---|---|
| **Reversible / local** | Naming, file layout inside a module, code style within existing standards | Builder or Architect, alone | Optional inline comment |
| **Reversible / cross-cutting** | New dependency, module boundary, API contract | Architect, with Reviewer sign-off | Architecture Decision Record (ADR) in `docs/DECISIONS.md` |
| **Hard to reverse** | Data model migrations, public interfaces, removing a capability | Architect proposes, Board ratifies | ADR + Board ratification entry |
| **Governance** | Changes to `ORION.md`, `ROLES.md`, `PROTOCOL.md`, `WORKFLOW.md` | Board only | Amendment entry in this document's changelog and in `.ai/BOARD.md` |

Standard flow for any decision above the "local" class:

1. **Proposal** — the initiating role writes a short problem statement and at least one alternative considered.
2. **Review** — affected roles comment against the proposal document (see `PROTOCOL.md` for the review mechanics).
3. **Decision record** — the outcome, rationale, and rejected alternatives are written down, even if the decision was obvious.
4. **Ratification** — decisions above "reversible / cross-cutting" require explicit Board sign-off before implementation starts.

Undocumented decisions are treated as if they were never made and may be reopened at any time without penalty to whoever reopens them.

## 6. Definition of Done

A unit of work is Done only when **all** of the following hold:

- [ ] It traces to a documented request (idea, roadmap item, or defect).
- [ ] It was implemented against an approved design where one is required (see `WORKFLOW.md` §Architecture).
- [ ] It has automated tests proportional to its risk, and they pass.
- [ ] It was reviewed by a Reviewer who did not author it, and the review is recorded.
- [ ] It meets the Quality Standards in §7.
- [ ] Documentation affected by the change (user-facing or internal) was updated in the same change set.
- [ ] It was merged through the Pull Request flow defined in `WORKFLOW.md`, with GitOps confirming the merge is clean and revertible.
- [ ] Any decisions made along the way are captured per §5.
- [ ] Knowledge worth keeping (why, not just what) was captured per `WORKFLOW.md` §Knowledge Capture.

A sprint, roadmap item, or release is Done only when every unit of work it contains is Done, and the Retrospective for it has been held (see `WORKFLOW.md`).

## 7. Quality Standards

- **Correctness.** Behavior matches the approved design; deviations are documented, not silent.
- **Testability.** Nothing is considered complete without a test strategy; untestable designs are rejected at Architecture review.
- **Security.** No secret, credential, or token is ever committed. Inputs are treated as untrusted by default. Security-relevant changes require explicit Reviewer sign-off.
- **Readability.** Code and documents are written for the next agent to read them cold, without access to the conversation that produced them.
- **Consistency.** New work follows the conventions already established in the repository unless a documented decision changes them.
- **Minimalism.** The smallest change that correctly solves the problem is preferred over the most general one.
- **Observability.** Anything that can fail in production must be detectable without reading source code.

Quality is verified, not assumed: every gate in `WORKFLOW.md` exists to check one or more of the standards above.

## 8. Repository Structure

```
/
├── ORION.md              # This document — the charter
├── ROLES.md              # Role definitions and authority
├── PROTOCOL.md           # Inter-agent communication protocol
├── WORKFLOW.md           # End-to-end lifecycle
├── .ai/
│   ├── BOARD.md          # Board composition and standing governance decisions
│   ├── DECISION_PROCESS.md   # Operational checklist derived from ORION.md §5
│   ├── HANDOFF_TEMPLATE.md   # Template for the Handoff Record (see PROTOCOL.md)
│   ├── ROLES.md          # Assignment of concrete agents to roles for this engagement
│   └── prompts/          # Agent-specific operating instructions (vendor-scoped, not part of governance)
├── docs/
│   ├── ARCHITECTURE.md   # Current-state architecture, kept living
│   ├── DECISIONS.md      # Log of Architecture Decision Records (ADRs)
│   └── retrospectives/   # One file per retrospective (see WORKFLOW.md)
├── roadmap/
│   └── ROADMAP.md        # Prioritized backlog of roadmap items
└── src/ ...              # Application code, owned by Builder/Reviewer, out of scope for this charter
```

This structure is normative for governance and knowledge artifacts (`.ai/`, `docs/`, `roadmap/`, root-level `*.md`). Application source layout under `src/` is an Architecture decision, not a governance one, and is documented in `docs/ARCHITECTURE.md`.

## 9. Sprint Philosophy

- Sprints are time-boxed containers for a coherent slice of the roadmap, not a unit of estimation ritual.
- Every sprint starts with a written Sprint Plan (scope, exit criteria, roles assigned) and ends with a Sprint Review and a Retrospective (`WORKFLOW.md`).
- Scope is fixed at sprint start; new requests during the sprint go to the next sprint unless the Product Owner explicitly re-scopes it, which requires a written note.
- A sprint may contain work from multiple roles in parallel, coordinated exclusively through the documents defined in `PROTOCOL.md` — never through ad-hoc synchronization.
- Sprint length is a Product Owner decision and may vary by roadmap item; ORION OS does not mandate a fixed cadence, only that the cadence be written down and stable within a sprint.

## 10. Architecture Philosophy

- **Evolutionary, not big-upfront.** Architecture is expected to change; every structural decision is recorded as an ADR so change is deliberate, not accidental.
- **Boundaries before implementation.** Module and service boundaries are decided before Builders start, and changes to those boundaries go through the Decision Process in §5.
- **Technology neutrality.** Architecture documents describe capabilities and contracts, not vendor products, except where a specific technology is itself the documented decision.
- **Fit for purpose over fashion.** Complexity must be justified by a requirement, not by precedent or trend.
- **Single source of truth.** `docs/ARCHITECTURE.md` always reflects the current, real state of the system. Design documents that preceded a change are historical once merged; the living document is authoritative.

## 11. Documentation Philosophy

- **Docs as code.** Documentation lives in the repository, is versioned with the code it describes, and goes through the same review gate.
- **Living over historical.** `ORION.md`, `ROLES.md`, `PROTOCOL.md`, `WORKFLOW.md`, and `docs/ARCHITECTURE.md` describe the current state and are kept current on every relevant change. Historical record (why something changed) lives in `docs/DECISIONS.md` and `docs/retrospectives/`, never mixed into the living documents.
- **Written for a cold reader.** Any agent — including one that has never seen this repository before — must be able to onboard from these documents alone.
- **No tribal knowledge.** If it is not written down, it is not part of the system, no matter how many agents "know" it.

---

## Amendment log

| Version | Date | Change | Approved by |
|---|---|---|---|
| 1.0.0 | 2026-07-17 | Initial charter | Board |
