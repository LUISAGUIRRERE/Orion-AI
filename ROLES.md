# ROLES.md — Role Definitions and Authority

| Field | Value |
|---|---|
| Document type | Governance |
| Status | Active |
| Version | 1.0.0 |
| Owner | Board |
| Derives authority from | `ORION.md` |

## How to read this document

A **role** is a function within ORION OS, not an identity. Roles are agent-agnostic: any human or AI agent capable of meeting a role's Responsibilities and operating within its Restrictions may be assigned to it for a given unit of work. The concrete assignment of agents to roles for a specific engagement is recorded separately in `.ai/ROLES.md`, and must never contradict the definitions below.

Two rules apply across every role:

1. **No self-approval.** An agent may not occupy the Builder and Reviewer roles for the same unit of work.
2. **Authority is bounded.** A role may act unilaterally only within its stated Authority. Anything outside it must be proposed, not executed.

---

## Role summary

| Role | Primary concern | Approves | Cannot do |
|---|---|---|---|
| Product Owner | What gets built and why | Roadmap, scope, priority | Cannot approve its own architecture or code |
| Architect | How the system is structured | Design documents, ADRs | Cannot merge its own designs without Reviewer sign-off |
| Builder | Implementation | Nothing (proposes only) | Cannot approve or merge its own work |
| Reviewer | Correctness and quality gate | Pull Requests, test adequacy | Cannot author the change it reviews |
| GitOps | Repository integrity and release mechanics | Merge execution, release cut | Cannot change scope, design, or code content |
| Research Agent | Evidence and options | Nothing (informs only) | Cannot make binding decisions |
| Documentation Agent | Knowledge capture and living docs | Documentation accuracy | Cannot alter decisions it documents |

---

## Product Owner

### Responsibilities
- Own the Vision-to-Roadmap translation: turn ideas and problems into prioritized, written roadmap items.
- Define and maintain acceptance criteria for each roadmap item.
- Arbitrate priority conflicts between roadmap items.
- Represent stakeholders who are outside ORION OS (users, business, sponsors).
- Chair Sprint Planning and Sprint Review.

### Authority
- Final say on **what** gets built and **in what order**.
- May re-scope a sprint mid-flight, with a written note explaining why.
- May reject a completed unit of work on the grounds that it does not meet the original intent, even if it is technically correct.

### Inputs
- Ideas and problem statements (from any source: users, Board, other roles).
- Research Agent findings relevant to prioritization.
- Sprint Review outcomes and Retrospective findings.

### Outputs
- `roadmap/ROADMAP.md` entries (prioritized, with acceptance criteria).
- Sprint Plans (scope and exit criteria for a sprint).
- Written scope decisions and rejections.

### Restrictions
- Does not decide architecture, technology, or implementation approach.
- Does not approve its own roadmap items for quality — that is the Reviewer's and Architect's domain.
- Cannot bypass the Decision Process in `ORION.md` §5 for hard-to-reverse decisions, even as Product Owner.

### Success metrics
- Roadmap items have clear, testable acceptance criteria before they enter a sprint.
- Low rate of scope disputes reaching Board escalation.
- Delivered work matches accepted intent (low post-delivery rejection rate).

---

## Architect

### Responsibilities
- Translate roadmap items into technical designs and module/service boundaries.
- Maintain `docs/ARCHITECTURE.md` as the living, current-state description of the system.
- Write and maintain Architecture Decision Records for cross-cutting or hard-to-reverse decisions.
- Review designs proposed by Builders for structural fit before implementation starts.

### Authority
- Final say on **how** the system is structured, within the bounds of the Decision Process (`ORION.md` §5).
- May reject an implementation approach on structural grounds before a Builder starts work.
- May request that a unit of work be decomposed further before it is buildable.

### Inputs
- Roadmap items and acceptance criteria from the Product Owner.
- Research Agent findings on technical options and trade-offs.
- Current-state `docs/ARCHITECTURE.md`.

### Outputs
- Design documents for cross-cutting or hard-to-reverse work.
- ADR entries in `docs/DECISIONS.md`.
- Updates to `docs/ARCHITECTURE.md`.

### Restrictions
- Does not implement application code (that is the Builder's role).
- Cannot ratify its own hard-to-reverse decisions — those require Board ratification per `ORION.md` §5.
- Cannot override Product Owner priority decisions.

### Success metrics
- `docs/ARCHITECTURE.md` accurately reflects the deployed system at all times.
- Low rate of implementation rework caused by design gaps.
- ADRs exist for all cross-cutting or hard-to-reverse changes with no retroactive gaps.

---

## Builder

### Responsibilities
- Implement approved designs as working, tested code.
- Write automated tests proportional to the risk of the change.
- Keep changes small and independently reviewable.
- Flag design gaps back to the Architect rather than resolving ambiguity unilaterally.

### Authority
- Full authority over implementation details within an approved design (local, reversible decisions per `ORION.md` §5).
- May propose design changes, but may not adopt them without Architect approval if they affect structure or contracts.

### Inputs
- Approved design or ADR from the Architect.
- Acceptance criteria from the Product Owner.
- Current codebase and `docs/ARCHITECTURE.md`.

### Outputs
- Pull Requests containing code, tests, and updated documentation.
- Implementation notes for anything that deviated from the design, with rationale.

### Restrictions
- Cannot approve or merge its own Pull Request.
- Cannot change architecture, scope, or priority unilaterally.
- Cannot skip tests or documentation updates required by the Definition of Done.

### Success metrics
- Pull Requests pass Review with a low rate of correctness-related rejection.
- Test coverage proportional to risk, consistently applied.
- Low rate of undocumented deviation from approved designs.

---

## Reviewer

### Responsibilities
- Independently verify that a Pull Request meets the Definition of Done (`ORION.md` §6) and Quality Standards (`ORION.md` §7).
- Verify that tests actually exercise the claimed behavior, not just that they pass.
- Check that documentation was updated alongside the change.
- Record the review outcome as a Review Report (see `PROTOCOL.md`).

### Authority
- Final gatekeeper before a Pull Request may be merged: no merge without Reviewer approval.
- May request changes, and the Pull Request cannot proceed until they are resolved or explicitly overridden by the Board.

### Inputs
- The Pull Request (code, tests, documentation) from the Builder.
- The approved design or ADR the Pull Request claims to implement.
- Definition of Done and Quality Standards from `ORION.md`.

### Outputs
- Review Report (approve, request changes, or reject) per `PROTOCOL.md`.
- Specific, actionable feedback tied to a standard or criterion, never a matter of unstated preference.

### Restrictions
- Cannot review a Pull Request it authored, in whole or in significant part.
- Cannot change scope or design during review — only assess conformance; scope or design gaps are escalated back to Product Owner or Architect, not resolved in review.
- Cannot approve a Pull Request that fails an explicit Definition of Done item.

### Success metrics
- Defects found in review versus defects found post-merge (should trend toward review).
- Review turnaround time within the service level agreed in `PROTOCOL.md`.
- Consistency of standards applied across reviews.

---

## GitOps

### Responsibilities
- Own the mechanics of the repository: branching, merge execution, tagging, and release cuts.
- Verify that a Pull Request is mergeable, revertible, and does not break the build before executing the merge.
- Execute releases per the Release stage of `WORKFLOW.md`.
- Maintain repository hygiene (stale branches, credentials hygiene, protected branch rules).

### Authority
- Final say on **when and how** an approved change physically enters `main` and is released.
- May block a merge on integrity grounds (failing build, unresolved conflicts, irreversible history) even if the Reviewer already approved it — this is a mechanical block, not a scope or design objection, and must be logged and immediately visible to the Reviewer and Builder.

### Inputs
- An approved Pull Request (Reviewer sign-off present).
- Release criteria from the Product Owner and Architect.

### Outputs
- Merge commits, tags, and release artifacts.
- Release notes summarizing what shipped, generated from merged Pull Requests.

### Restrictions
- Cannot approve a Pull Request on scope, design, or correctness grounds — that authority belongs to the Reviewer and Architect.
- Cannot alter code content; may only act on repository mechanics.
- Cannot skip the Reviewer sign-off requirement, ever.

### Success metrics
- Zero irreversible merges to `main`.
- Release cuts free of last-minute manual intervention.
- Mean time from Reviewer approval to merge stays low and predictable.

---

## Research Agent

### Responsibilities
- Investigate technical options, prior art, constraints, and risks on request from the Product Owner or Architect.
- Produce comparative findings with sources and trade-offs, not recommendations dressed as decisions.
- Validate assumptions that a design or roadmap item depends on.

### Authority
- None to decide. The Research Agent informs; it never approves, rejects, or commits to a course of action.

### Inputs
- A specific research question or assumption to validate, scoped by the requesting role.

### Outputs
- Research Report: question, method, findings, sources, and explicitly labeled open uncertainties.

### Restrictions
- Cannot present findings as a decision.
- Cannot skip citing sources or evidence for a claim.
- Cannot expand scope beyond the question it was asked; new questions go back to the requester.

### Success metrics
- Findings hold up under later implementation (low rate of research-driven rework).
- Turnaround time appropriate to the decision it feeds.
- Traceability from every Research Report to the decision it informed.

---

## Documentation Agent

### Responsibilities
- Keep living documents (`docs/ARCHITECTURE.md`, root governance documents when directed by the Board) synchronized with reality.
- Capture Knowledge Capture and Retrospective artifacts per `WORKFLOW.md`.
- Ensure every merged Pull Request that changes behavior also updates the documentation that describes that behavior.

### Authority
- May block a Pull Request from being marked Done (not from being merged — that is GitOps) if required documentation is missing, per the Definition of Done.

### Inputs
- Merged Pull Requests and their associated design documents or ADRs.
- Retrospective and Sprint Review notes.

### Outputs
- Updated living documents.
- Retrospective records under `docs/retrospectives/`.
- Knowledge Capture entries linked to the work that produced them.

### Restrictions
- Cannot alter the substance of a decision while documenting it — only record it faithfully.
- Cannot originate architecture or scope decisions; it documents them.

### Success metrics
- Zero drift between living documents and deployed reality, measured at each release.
- Every merged Pull Request with a behavior change has a corresponding documentation update.
- Retrospective and Knowledge Capture completion rate per sprint.

---

## Amendment log

| Version | Date | Change | Approved by |
|---|---|---|---|
| 1.0.0 | 2026-07-17 | Initial role definitions | Board |
