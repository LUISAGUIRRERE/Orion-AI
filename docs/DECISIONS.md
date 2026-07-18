# Decisions

Architecture Decision Record (ADR) log for ORION OS. Every major architectural decision is recorded here, in order, and is never deleted — superseded decisions are marked as such, not removed.

Every ADR must include: Title, Status, Author, Reviewed by, Approved by, Date, Supersedes, Context, Decision, Consequences.

**Supersedes** is optional and should contain the identifier of any previous ADR that this decision replaces (e.g. `ADR-0002`). If this ADR does not replace an earlier one, use `None`.

## ADR-0001: Adopt an AI Board Governance Model

**Status:**
Accepted

**Author:**
Claude

**Reviewed by:**
Nemotron

**Approved by:**
Luis Aguirre

**Date:**
2026-07-17

**Supersedes:**
None

**Context:**
ORION OS will be built collaboratively by one human and multiple AI models, each with different strengths. Without explicit separation of duties, an AI model could propose, implement, and approve its own work, removing any independent check on quality or direction.

**Decision:**
Establish an AI Board with six seats — Luis Aguirre (CEO/Product Owner), ChatGPT (Chief AI Architect), Claude (Chief Software Architect), Jules (Lead Software Engineer), Nemotron (Principal Engineering Reviewer), and AutoClaw (Operations Engineer). Architecture, implementation, review, and approval are kept as separate responsibilities. No AI approves its own work. Nemotron never reviews its own work. Luis holds final authority on all product and business decisions.

**Consequences:**
All future work must flow through this structure: proposal → recorded decision (if architectural) → approved GitHub Issue → implementation → independent review → final approval. This adds process overhead but prevents any single actor from being both author and approver of the same work.

## ADR-0002: Define ORION OS Mission and Non-Goals

**Status:**
Accepted

**Author:**
Claude

**Reviewed by:**
Nemotron

**Approved by:**
Luis Aguirre

**Date:**
2026-07-17

**Supersedes:**
None

**Context:**
The repository existed with governance scaffolding but no definition of what ORION OS actually is, risking scope drift as different Board members contribute.

**Decision:**
ORION OS is an AI-powered Business Intelligence Operating System whose mission is to understand businesses, discover opportunities, recommend valuable products and services, coordinate specialized AI agents, and continuously improve its own knowledge. ORION is explicitly **not** a CRM, **not** a scraper, and **not** an automation platform.

**Consequences:**
Future architecture and product proposals should be evaluated against this mission and these non-goals. Features that reduce ORION to a CRM, scraper, or pure automation tool are out of scope unless this decision is explicitly superseded.

## ADR-0003: Define MVP Scope as the Executive Orchestrator

**Status:**
Accepted

**Author:**
Claude

**Reviewed by:**
Nemotron

**Approved by:**
Luis Aguirre

**Date:**
2026-07-17

**Supersedes:**
None

**Context:**
ORION OS is pre-alpha with no production code. A starting point for implementation needs to be defined before any GitHub Issues can be approved.

**Decision:**
The first software component to be built will be the **Executive Orchestrator**, which coordinates a set of specialized agents: Planner, Memory, Knowledge, Business Scout, Business Profiler, Opportunity Engine, Recommendation Engine, and Communication Agent. At this stage, these components are described conceptually in `docs/ARCHITECTURE.md` only — none are implemented.

**Consequences:**
Implementation work should not begin on any of these components until each has an approved GitHub Issue scoping it. This ADR authorizes description and design work, not code.

## ADR-0004: Introduce ORION OS Constitution, Team Mapping, and Multi-Agent Protocol Layer

**Status:**
Accepted

**Author:**
Claude

**Reviewed by:**
Not yet performed by Nemotron — approved directly by Luis Aguirre in a live governance session. Formal Nemotron review is an open item.

**Approved by:**
Luis Aguirre

**Date:**
2026-07-17

**Supersedes:**
None (extends ADR-0001 and ADR-0002; does not replace them)

**Context:**
A parallel, vendor-specific set of governance documents already existed under `.ai/` (Board, Roles, Decision Process) when a request was made to design a vendor-agnostic operating system for coordinating AI software engineers, producing `ORION.md`, `ROLES.md`, `PROTOCOL.md`, and `WORKFLOW.md`. An initial draft duplicated existing governance with an incompatible, abstract role taxonomy, risking two competing sources of truth. Luis directed that the existing `.ai/` governance remain authoritative, that no document be replaced without justification, and that new capabilities be layered on top instead.

**Decision:**
- `.ai/BOARD.md`, `.ai/ROLES.md`, `.ai/DECISION_PROCESS.md`, `.ai/HANDOFF_TEMPLATE.md`, `AGENTS.md`, `README.md`, and `docs/ARCHITECTURE.md` remain the authoritative operational governance and product definition. Unchanged in substance.
- `ROLES.md` at the repository root was removed; it duplicated `.ai/ROLES.md` with an incompatible taxonomy.
- `ORION.md` was redefined from a repository charter into the Constitution of ORION OS: a conceptual/philosophical document covering operating principles, vendor-independent concepts, architectural philosophy, collaboration philosophy, and mission philosophy. It defers all operational governance to `.ai/`.
- Definition of Done and Quality Standards, originally drafted inside the charter version of `ORION.md`, were moved into `.ai/DECISION_PROCESS.md`, evolving it rather than creating a competing checklist.
- A new file, `.orion/TEAM.md`, was created to map abstract, vendor-independent roles (Product Owner, CTO, Architect, Builder, Reviewer, GitOps, Research, Documentation) to their current concrete implementations, so that implementation turnover never requires changing `ORION.md`.
- `PROTOCOL.md` and `WORKFLOW.md` were created as new capabilities — a multi-agent communication protocol and an end-to-end lifecycle — layered on top of the three governance paths already defined in `.ai/DECISION_PROCESS.md`, using only artifacts that already exist in this repository (GitHub Issues, Pull Requests, ADRs, Handoff Records). No new document types or approval states were introduced.

**Consequences:**
- The repository now has a single coherent governance model with two layers: `.ai/` (who, concretely, and the exact approval mechanics) and `ORION.md`/`PROTOCOL.md`/`WORKFLOW.md`/`.orion/TEAM.md` (the vendor-independent principles and lifecycle those mechanics operate within).
- `.orion/TEAM.md` currently records two role reassignments and one new implementation (Codex as Builder, Jules reassigned to GitOps) relative to `.ai/ROLES.md`'s current text, and leaves Research and Documentation unassigned. Reconciling `.ai/ROLES.md`/`.ai/BOARD.md` with this mapping — or accepting the two as deliberately distinct — is an open governance item.
- Formal Nemotron review of this ADR has not yet occurred and should be obtained to close the Architecture/Governance path per `.ai/DECISION_PROCESS.md`.

## ADR-0005: Establish the ORION OS Mission Framework

**Status:**
Accepted

**Author:**
Claude (Chief Software Architect)

**Reviewed by:**
Nemotron

**Approved by:**
Luis Aguirre

**Date:**
2026-07-17

**Supersedes:**
None (extends ADR-0004)

**Context:**
ADR-0004 established a vendor-independent governance layer (`ORION.md`, `PROTOCOL.md`, `WORKFLOW.md`, `.orion/TEAM.md`) above the existing `.ai/` AI Board governance. During Sprint 0 validation of that model, Codex correctly refused to implement work because no authoritative execution contract existed to bound what a Builder may touch; Nemotron reviewed the resulting Mission Framework architecture proposal and approved it with recommendations; Jules validated that Git mechanics (branch, commit, push, PR) can be exercised independently of implementation. The missing artifact identified by all participants was a formal Mission Framework — recorded as an architecture proposal and then authorized as MISSION-0001.

**Decision:**
Introduce the Mission as a new artifact type: the execution contract between Product Owner, Chief Architect, Builder, Reviewer, and GitOps for one bounded unit of implementation work. No Builder work begins without an Approved Mission. The framework is implemented as `.orion/missions/README.md` (framework definition, lifecycle, Mission Log) and `.orion/missions/MISSION_TEMPLATE.md` (reusable per-mission template), and is layered on existing governance without redesigning it:

- `.ai/DECISION_PROCESS.md`'s Implementation path gains one required step, "Mission approved," between "Issue approved" and Builder execution.
- `ORION.md` gains one principle under Vendor-Independent Concepts: implementation never begins without a bounded execution contract.
- `PROTOCOL.md` gains "Mission" as an artifact type, with its lifecycle declared as a justified specialization of the generic approval flow in §6.
- `WORKFLOW.md` Stage 5 (Architecture) exit criteria and Stage 6 (Implementation) artifact both gain the Approved Mission requirement.
- `.github/PULL_REQUEST_TEMPLATE.md` gains a checklist line requiring the Mission ID and GitOps Checklist confirmation.
- Mission Ownership, Review Owner, and Merge Owner fields name abstract roles, resolved to concrete agents through `.orion/TEAM.md`; individual Missions may record the resolved names for traceability without the framework itself hardcoding them.

This ADR was executed under MISSION-0001, the first Mission issued under this framework, applied to its own implementation — delivered as a Pull Request rather than a direct merge to `main`, establishing the review-then-merge mechanic the framework itself now requires going forward.

**Consequences:**
- Every future implementation Issue requires an Approved Mission before Builder work starts.
- `.orion/TEAM.md`'s current disagreement with `.ai/ROLES.md` (Codex recorded as Builder, Jules recorded as GitOps — neither reflected in `.ai/ROLES.md`'s seat descriptions) becomes operationally load-bearing, since Mission Ownership resolves through `TEAM.md`. This remains an open item for Luis to resolve.
- Pull Requests going forward are expected to reference a Mission ID; PRs without one should be treated as Minor Documentation only, per `.ai/DECISION_PROCESS.md`.

## ADR Template

Use this template for every new ADR:

```
## ADR-000X: Title

**Status:**
Proposed | Accepted | Superseded

**Author:**


**Reviewed by:**


**Approved by:**


**Date:**


**Supersedes:**
None, or the identifier of the ADR this decision replaces (e.g. ADR-0002)

**Context:**


**Decision:**


**Consequences:**

```
