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

## ADR-0006: Single Source of Truth for AI Board Composition

**Status:**
Accepted

**Author:**
Claude

**Reviewed by:**
Not yet performed by Nemotron — implemented under MISSION G-012's explicit RELEASE/HARDENING autonomy policy, which authorizes recording this ADR as part of the mission's own governance/audit step. Formal Nemotron review is an open item, consistent with the precedent already set by ADR-0004.

**Approved by:**
Luis Aguirre (via MISSION G-012's own governance instructions)

**Date:**
2026-07-21

**Supersedes:**
None (extends ADR-0001; does not replace it)

**Context:**
The AI Board's roster (Luis Aguirre, ChatGPT, Claude, Jules, Nemotron, AutoClaw — established in ADR-0001) was recorded by hand in two places with independently-maintained tables: `AGENTS.md`'s "AI Board" section and `.ai/BOARD.md`'s "Membership" section. Nothing enforced agreement between them, and `orion/board/member_registry.py` (introduced by MISSION B-011 for a different concern — Mission pipeline stage routing) separately hardcoded short labels for four of the same six seats. A request to add `agents/gemini.md` (a system-prompt-style document for a proposed "Gemini" research agent) surfaced the risk directly: nothing in the repository distinguished "a file describing an agent exists" from "this agent is an approved AI Board member," and no single place could be checked to answer that question authoritatively.

**Decision:**
Introduce `.ai/board.yaml` as the single, machine-readable Single Source of Truth for AI Board *composition* (who: id, display name, role, status, short responsibilities/restrictions, and a pointer to that member's documentation). It is loaded and validated by `orion.board.canonical.load_board_config()`, which rejects malformed input with a specific, actionable error rather than silently accepting it.

- `AGENTS.md`'s "AI Board" table and `.ai/BOARD.md`'s "Membership" table are now generated from `.ai/board.yaml` by `orion.board.generator`, between explicit `BEGIN GENERATED`/`END GENERATED` markers; everything else in both files remains hand-written.
- `.ai/ROLES.md` (full prose per seat), `.ai/prompts/*.md` (system prompts), `agents/*.md` (per-agent instructions), and this ADR log are **not** generated — they remain authoritative, hand-written documents, per this Mission's own explicit instruction not to convert narrative decisions into generated data.
- `orion.board.member_registry` (B-011's Mission pipeline stage registry — a distinct concept from Board *membership*) references canonical member ids (`board_seat_member_ids`) rather than hardcoding display names/roles, and resolves the actual label fresh, on every call, directly against `.ai/board.yaml` — never once at import time. If the canonical file cannot be loaded, the resolved `board_seat` is `None` with an explicit `board_seat_error` describing why, never a fabricated fallback identity; this was corrected during Codex's first review round (see the Remediation note below), which correctly flagged an earlier draft's hardcoded fallback strings as a second, undisclosed operational source of truth.
- `orion board validate` / `orion board generate` / `orion board generate --check` are the only supported ways to check or regenerate the derived tables; hand-editing the generated blocks is explicitly against convention (documented in `docs/BOARD_SOURCE_OF_TRUTH.md`) and will be silently overwritten by the next `generate`.
- **Gemini is deliberately not listed in `.ai/board.yaml`.** `agents/gemini.md` exists, but no ADR has approved Gemini as an official Board seat — per this Mission's own explicit rule, a file under `agents/` is not itself a membership decision. Adding Gemini (or any member) requires an ADR first, then a `.ai/board.yaml` edit, never the reverse.

**Consequences:**
- Future Board composition changes touch exactly one structured file (`.ai/board.yaml`) plus, when applicable, `.ai/ROLES.md`'s narrative prose — never two independently-maintained tables.
- `orion board generate --check` can be wired into CI to catch any future hand-edit of the generated blocks (drift) before merge.
- This ADR does not resolve `.orion/TEAM.md`'s pre-existing, separately-tracked disagreement with `.ai/ROLES.md` about abstract role assignments (Codex as "Builder," Jules as "GitOps") — that remains a distinct, already-open governance item per ADR-0004/ADR-0005, deliberately out of scope here since it concerns `PROTOCOL.md`'s abstract role-mapping layer, not AI Board membership itself.
- A pre-existing, intermittent concurrency test flake in `tests/test_runtime.py::SchedulerTests` (unrelated to this Mission — no file it touches was modified here) was newly reproduced during this Mission's repeated validation runs and is disclosed in MISSION G-012's final report as a known, pre-existing issue, not introduced or fixed by this change.

**Remediation (2026-07-21):** Codex's first independent review (REQUEST CHANGES) found four HIGH-severity issues in the initial implementation: (1) a hardcoded fallback name/role in `orion.board.member_registry` was itself a second operational source of truth; (2) a module-level cache resolved once at import time meant consumers could see a stale board.yaml for the life of the process; (3) `orion.board.generator`'s writes were not atomic; (4) `orion.board.canonical`'s validation accepted absolute/traversal documentation paths, treated `bool` as a valid `int` version, didn't type-check ids/names/roles as strings, and silently accepted unknown keys. All four were fixed on the same branch (no scope change, no new members, no new APIs/commands/screens): the fallback was replaced with an explicit `board_seat=None` + `board_seat_error=<message>` failure state; the cache was removed entirely in favor of per-call resolution; writes now go through a temp file + `os.replace()`; validation now rejects all of the above explicitly, and Markdown table generation now escapes `|`/newlines in member fields.

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
