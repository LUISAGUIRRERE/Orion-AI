# MISSION-XXXX

## Title
<Short, action-oriented title>

---

## Mission ID
MISSION-XXXX

---

## Status
DRAFT

---

## Priority
<P0 | P1 | P2 | P3>

---

## Requested By
<Name of the requesting Product Owner or Board member>

---

## Mission Owner
<Abstract role responsible for execution, e.g. Architect, Builder>

---

## Objective
<One or two sentences: the outcome this mission achieves and why it matters. State explicitly whether application code is included or excluded.>

---

# Background
<Why this mission exists. Reference the originating Issue, ADR, retrospective, or review finding that created the need.>

---

# Scope

## Included
<Concrete, enumerated list of what this mission covers.>

---

## Explicitly Excluded
<Everything adjacent that this mission deliberately does not attempt, even if related or tempting to include.>

---

# Authorized Files To Create
<Explicit list of paths the Builder may create. Nothing outside this list may be created.>

---

# Authorized Files To Modify
<Explicit list of paths the Builder may modify. Nothing outside this list may be modified.>

---

# Forbidden Files
Any file not explicitly listed above.
No additional folders.
No additional documentation.
No code, unless explicitly authorized above.
No configuration, unless explicitly authorized above.

---

# Deliverables
<Numbered list of concrete outputs the Builder must produce.>

---

# Acceptance Criteria
The implementation must:
- preserve existing governance
- introduce no duplicate concepts
- maintain one source of truth
- preserve vendor independence
- use existing terminology whenever possible
- contain no placeholder content
- resolve all internal Markdown links
- produce a clean git status except intended changes

<Add mission-specific acceptance criteria below this line if needed.>

---

# Builder Rules
Builder SHALL:
- implement only authorized files
- stop if governance becomes ambiguous
- stop if another authoritative source contradicts this Mission
- report every deviation

Builder SHALL NOT:
- redesign governance
- create undocumented folders
- rename existing documents
- introduce architecture outside Mission scope

---

# Review Checklist
Reviewer verifies:
- Mission completeness
- Consistency
- No duplicated governance
- No conflicting terminology
- Correct repository placement
- Internal links resolve
- Compliance with ADR process
- Compliance with AI Board rules

---

# GitOps Checklist
GitOps shall:
- Create branch
- Commit
- Push
- Open Pull Request
- Reference Mission ID
- Reference ADR (if one exists)
- Reference Issue (if one exists)

---

# Completion Definition
Mission is complete when:
- Builder implementation completed
- Reviewer approval received
- Product Owner authorizes merge
- Pull Request merged into main

---

# Standard Mission Results
Allowed outcomes are:
✅ Changes Applied
✅ Verification Passed (No Changes Required)
⚠ Changes Requested
⛔ Blocked

No other execution result is permitted.

---

# Dependencies
<Other Missions, ADRs, Issues, or governance documents this mission depends on. Unsatisfied dependencies block Approval.>

---

# Risks
<Risks specific to this mission. These must be reported rather than silently resolved.>

---

# Success Metric
<How this mission's outcome is measured after completion — outcome metrics, not process metrics.>

---

# Ownership
<Resolve each abstract role to its current implementation via `.orion/TEAM.md` at the time this mission is authored. Record the resolved names here for traceability; the framework itself never hardcodes them.>

Product Owner
<name>

Chief AI Architect
<name>

Architecture
<name>

Builder
<name>

Reviewer
<name>

GitOps
<name>

---

# Related ADR
<ADR ID in docs/DECISIONS.md, or "None">

---

# Notes
<Anything else future readers need, including whether this mission is a dogfooding/self-referential mission.>
