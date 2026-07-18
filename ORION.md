# ORION.md — The Constitution of ORION OS

| Field | Value |
|---|---|
| Document type | Constitution (conceptual / philosophical) |
| Status | Active |
| Version | 2.0.0 |
| Approved by | Luis Aguirre |

## Purpose of this document

ORION OS coordinates independent software engineering agents — human or artificial — around a shared mission, a shared repository, and a shared set of rules. This document is its Constitution: it describes the *kind* of system ORION OS is and the principles it must never violate, regardless of which concrete agents implement it today or in the future.

This document does **not** duplicate operational governance. It does not define who is on the Board, what each seat may or may not do, or how a change moves from idea to merge — that is defined, authoritatively, in `AGENTS.md` and `.ai/` (`BOARD.md`, `ROLES.md`, `DECISION_PROCESS.md`, `HANDOFF_TEMPLATE.md`). It does not restate the product mission or architecture — that lives in `README.md` and `docs/ARCHITECTURE.md`. It does not define the current mapping of abstract roles to concrete agents — that lives in `.orion/TEAM.md`. It does not define how agents exchange work — that lives in `PROTOCOL.md` and `WORKFLOW.md`.

What this document defines is the layer above all of that: the principles those documents must be consistent with, and the philosophy that justifies why they are shaped the way they are.

## 1. Operating Principles of the AI Coordination System

1. **Documents over conversation.** Coordination happens through artifacts committed to the repository, not through ephemeral exchanges. A decision that exists only in a conversation does not exist.
2. **Segregation of duties.** The agent that produces a piece of work is never the agent that approves it. This is structural, not a matter of trust.
3. **Reversibility.** Every change that reaches the trunk must be revertible without special knowledge. If it cannot be reverted safely, it should not have been merged.
4. **Traceability.** Every artifact links back to the request, decision, or issue that justifies its existence. No orphan work.
5. **Memory as a first-class citizen.** Knowledge produced during delivery — decisions, research, retrospectives — is captured as durable documentation, not left inside a session that will eventually be discarded.
6. **Quality is continuous, not a phase.** Quality gates apply throughout the lifecycle, not only at the end of it.
7. **Human accountability.** A human is always the final point of accountability for what ships, independent of how much of the work was produced autonomously.

## 2. Vendor-Independent Concepts

The single concept this Constitution protects above all others: **a role is a function, not an identity.**

"Architect," "Builder," "Reviewer," "GitOps," and every other function ORION OS needs are defined by what they are responsible for and what authority they carry — never by which model, product, or vendor currently performs them. An implementation can be replaced entirely — a new model, a new tool, a system that does not exist yet — without requiring any change to this document, because this document never names one.

The concrete answer to "who currently plays this role" is deliberately kept out of this Constitution and lives in `.orion/TEAM.md`, precisely so that it can change often and cheaply while the principles here change rarely, if ever.

This separation exists for one reason: the coordination system must outlive any individual agent. If a role definition were written in terms of a specific vendor, the system would need to be rewritten every time that vendor's product changed or was replaced. Written in terms of function and authority, it does not.

## 3. Architectural Philosophy

- **Evolutionary, not big-upfront.** Architecture is expected to change; structural decisions are recorded so change is deliberate, not accidental.
- **Boundaries before implementation.** Structural boundaries are decided before building starts; changing them later is itself an architectural decision, not an implementation detail.
- **Technology neutrality.** Architectural reasoning describes capabilities and contracts, not vendor products, except where a specific technology is itself the documented decision.
- **Fit for purpose over fashion.** Complexity must be justified by a requirement, not by precedent, trend, or what a particular tool makes convenient.
- **Single source of truth.** The system's real, current architecture is described in exactly one living document (`docs/ARCHITECTURE.md`). Design discussion that preceded a change is historical once merged; the living document is authoritative.

## 4. Collaboration Philosophy

Multiple agents working on the same system at the same time only stay coherent if collaboration is structured, not improvised.

- Work is handed off through explicit artifacts (issues, pull requests, architecture decision records, handoff records), never assumed to be understood implicitly.
- Disagreement between roles is expected and is resolved through escalation to a human authority, not through the more persistent or more persuasive agent prevailing.
- No agent is trusted by default to have full context; every artifact is written so that an agent encountering it cold — with no memory of how it came to exist — can act on it correctly.
- Collaboration protocols (see `PROTOCOL.md`) are designed around the roles defined by this Constitution, not around the specific agents in `.orion/TEAM.md` at any given time.

## 5. Mission Philosophy

ORION OS treats "what the system is trying to accomplish" and "which agents are accomplishing it" as two separate questions with two separate lifecycles.

The mission — what ORION exists to do for the business it serves — is defined in `README.md` and `docs/ARCHITECTURE.md`, and changes only when a deliberate product decision changes it. The roster of agents carrying out that mission changes far more often, for reasons that have nothing to do with the mission itself: a better model becomes available, a tool is deprecated, a new capability emerges.

This Constitution exists so that the second kind of change never forces the first. An agent turnover is an operational event, recorded in `.orion/TEAM.md`. A mission change is a product event, recorded as an ADR in `docs/DECISIONS.md`. Conflating the two — letting a change of implementation quietly become a change of mission, or vice versa — is the failure mode this document is written to prevent.

---

## Amendment log

| Version | Date | Change | Approved by |
|---|---|---|---|
| 1.0.0 | 2026-07-17 | Initial charter (superseded — duplicated governance already defined in `.ai/`, `README.md`, and `docs/ARCHITECTURE.md`) | — |
| 2.0.0 | 2026-07-17 | Redefined as the Constitution of ORION OS: conceptual/philosophical layer only. Governance, roles, decision process, Definition of Done, and Quality Standards moved to or kept in `.ai/`; role-to-implementation mapping moved to `.orion/TEAM.md`. | Luis Aguirre |
