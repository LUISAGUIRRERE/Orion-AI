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
