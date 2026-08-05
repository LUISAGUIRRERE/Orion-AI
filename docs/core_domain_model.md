# ORION Core Domain Model Specification

This specification documents the **ORION Core (`orion.core`) Domain Model**, detailing how the cognitive business operating system structures strategic business concepts independently from execution and infrastructure.

---

## 1. Purpose of ORION Core

The purpose of `orion.core` is to model the **declarative, strategic operating structures** of autonomous digital businesses.

Unlike the Runtime (which is concerned with process execution, message queueing, concurrency, and git management), ORION Core defines the semantic domain entities—**Organizations, Professional Roles, Departments, Capabilities, Decisions, Meetings, Opportunities, Business Memory, Knowledge Facts, and Goals**—that represent *how a business represents and reasons about itself*.

By decoupling business representation from runtimes and LLM providers, we ensure that:
1. Business logic remains completely vendor-independent.
2. Decisions, rules, and structures can be simulated, tested, and audited in a zero-dependency environment.
3. The system remains portable and ready to adopt future agent runtimes or execution models.

---

## 2. Decoupling Boundaries

ORION establishes a strict, single-direction dependency flow across its four main layers:

```text
┌────────────────────────────────────────────────────────┐
│                      1. FOUNDATION                     │
│  The Constitution (ORION.md), Multi-agent Protocol     │
│  (PROTOCOL.md), and Lifecycle (WORKFLOW.md).           │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│                        2. CORE                         │
│  The business organization (orion.core): entities,     │
│  roles, memory, and semantic business models.          │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│                       3. RUNTIME                       │
│  Execution infrastructure (orion.runtime): queueing,   │
│  scheduling, workers, and git workflows.               │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│                      4. PROVIDERS                      │
│  Replaceable AI adapters (orion.providers)             │
│  shelling out to Claude Code, Gemini CLI, etc.         │
└────────────────────────────────────────────────────────┘
```

- **Core to Runtime Boundary:** Core defines the entities that Runtime executes against. Core has **zero imports or dependencies** on `orion.runtime` or `orion.providers`. Runtime handles the mechanics of claiming, executing, and persisting missions, but knows nothing about the underlying business rules modeled in Core.
- **Providers to Runtime Boundary:** Providers are swappable adapter plugins registering themselves at runtime. `orion.runtime` communicates with adapters solely through the neutral `PromptPackage` and `ExecutionResult` interfaces, completely isolating LLM-specific parameters from Core.

---

## 3. Entity Catalog & File Layout

Every business domain concept is implemented under a single flat-module package layout:

```text
orion/core/
├── __init__.py           # Package initialization
├── capability.py         # Capability class
├── decision.py           # BusinessDecision class
├── department.py         # Department class
├── goal.py               # BusinessGoal class
├── knowledge.py          # KnowledgeFact class
├── meeting.py            # Meeting class
├── memory.py             # MemoryLedger class
├── opportunity.py        # Opportunity class
├── organization.py       # Organization class
└── role.py               # ProfessionalRole class
```

### 3.1. Entity Relationship Diagram (ERD)

The entities associate logically to map out a complete corporate hierarchy:

```text
       ┌──────────────────┐
       │   Organization   │
       └────────┬─────────┘
                │ (1)
                ▼ (1)
       ┌──────────────────┐ (1)      (1) ┌──────────────────┐
       │   MemoryLedger   │◄─────────────┤   BusinessGoal   │
       └──────────────────┘              └──────────────────┘
                │ (1)                             │ (1)
                ▼ (N)                             ▼ (N)
       ┌──────────────────┐ (1)      (1) ┌──────────────────┐
       │    Department    │◄─────────────┤   Opportunity    │
       └────────┬─────────┘              └──────────────────┘
                │ (1)
                ▼ (N)
       ┌──────────────────┐              ┌──────────────────┐
       │    Capability    │              │  KnowledgeFact   │
       └──────────────────┘              └──────────────────┘
                │ (1)                             │ (1)
                ▼ (N)                             ▼ (N)
       ┌──────────────────┐              ┌──────────────────┐
       │ ProfessionalRole ├─────────────►│ BusinessDecision │
       └────────┬─────────┘ (N)      (1) └──────────────────┘
                │ (N)
                ▼ (1)
       ┌──────────────────┐
       │     Meeting      │
       └──────────────────┘
```

---

## 4. Lifecycle Enums & Invariants

### 4.1. `ProfessionalRole` Seats
- **File:** `orion/core/role.py`
- **Enum Statuses:** `Literal["active", "inactive", "proposed"]`
- **Invariant:** A seat with `"proposed"` status represents a planned role that lacks authority to execute pipeline actions or modify memory.

### 4.2. `BusinessDecision` Status
- **File:** `orion/core/decision.py`
- **Enum Statuses:** `Literal["proposed", "accepted", "superseded", "rejected"]`
- **Invariant:** A decision marked `"superseded"` must specify the corresponding newer Decision ID that replaces its rationale, preserving auditability.

### 4.3. `BusinessGoal` Progress
- **File:** `orion/core/goal.py`
- **Enum Statuses:** `Literal["not_started", "in_progress", "completed", "blocked"]`
- **Invariant:** If progress percentage $\ge 100.0$, the status must resolve to `"completed"`.

### 4.4. `Opportunity` Strategic Score
- **File:** `orion/core/opportunity.py`
- **Formula Invariant:**
  $$\text{Strategic Score} = \frac{(\text{Business Value} \times \text{ROI} \times \text{Confidence}) - \text{Risk}}{\text{Cost} \times \text{Urgency}}$$
  Where $\text{ROI} = \frac{\text{Business Value}}{\max(0.01, \text{Cost})}$. Costs and Urgencies are clamped to non-zero values to prevent Division-by-Zero runtime exceptions.

---

## 5. Implementation Decisions & Rationale

### 5.1. Pydantic Choice
ORION Core utilizes **Pydantic v2** (`pydantic.BaseModel`) for its entities.
- **Rationale:** Pydantic provides out-of-the-box strong typing, automatic schema enforcement, and seamless JSON serialization/deserialization. This allows ORION's C-Suite to dump business memory states and load organization models directly from file systems or remote APIs without writing custom parser code.

### 5.2. Flat-Module Package Layout
ORION Core purposefully departs from the originally suggested "package-per-domain" directory tree (e.g. separate directories for each class).
- **Technical Justification:** In a pre-alpha, prototyping phase, nested directory trees introduce severe file-exploration fatigue and require complex relative import cycles (e.g., `from ...organization.models import Organization`). A flat structure keeps imports concise, maintains perfect readability, and eliminates python package-lookup overhead entirely, satisfying the constitution's "Avoid overengineering" rule.

---

## 6. Extension Strategy & Strategic Non-Goals

### 6.1. Extension Strategy
To add a new vertical (such as a Legal Department or Paid Media tracking):
1. Define the corresponding entities in a new file under `orion/core/` (e.g. `orion/core/legal.py`).
2. Inherit from `BaseModel` to guarantee serialization compatibility.
3. Implement validation rules directly using Pydantic’s `@field_validator` hooks.

### 6.2. Explicit Non-Goals
- **No Git or Execution Logic in Core:** `orion.core` will never initiate git branches, handle git pushes, or invoke subprocesses. That responsibility resides solely inside the Runtime and Provider layers.
- **No Live Network Calls:** Core entities are passive domain models; they do not fetch external APIs or connect directly to databases.

### 6.3. Known Limitations
- Threading concurrency locks are currently delegated entirely to the Runtime Worker layer; Core entities themselves do not implement mutex guards.

---

## 7. Recommended Next Sprint

In the next sprint, we recommend **Incremental Runtime Integration**:
1. Connect `orion.core` objects to the FastAPI and template routers of `orion.window` (The Window).
2. Establish database schemas (SQLite/PostgreSQL) mapped directly from the Pydantic Core models to enable transactional persistence.
3. Bridge `orion.core.opportunity` with the Runtime Worker loop to allow automated task enqueuing based on strategic opportunity scores.
