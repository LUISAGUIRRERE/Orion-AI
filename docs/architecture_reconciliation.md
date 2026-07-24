# ORION Architecture Reconciliation Audit — Technical Report (MISSION 002)

## 1. Executive Summary

As ORION OS transitions from a multi-agent orchestrator into an autonomous **Digital CEO**, it has accumulated multiple layers of architectural scaffolding. Systems like the **AI Board, Dispatcher, Runtime, Mission Pipeline, Governance, and Scheduler** cohabitate in the codebase.

While the system is highly stable and passes 100% of its test suites, a deep-dive architectural reconciliation reveals that **ORION currently houses multiple competing architectures from different developmental generations**.

The legacy, synchronous, single-caller design (exemplified by the **COO Agent and its Dispatcher**) operates as a "phantom loop" alongside the modern, multi-threaded **Runtime Scheduler & Worker pool**. Furthermore, the execution contract is bifurcated between legacy rule-based **Mission Handlers** and the modern **generic Executor and Provider Adapter** layer.

This report reconciles these architectural generations, maps out a streamlined, 3-tier canonical architecture, and provides a clear, 4-phase migration strategy to retire obsolete components, eliminate technical debt, and establish a rock-solid, production-grade foundation for the next five years of ORION's evolution.

---

## 2. Current Architecture & Execution Engines

ORION currently contains several components capable of executing or coordinating work. The table below audits and reconciles every engine present in the codebase:

### 2.1. Audit of Active Execution Engines

| Component | Purpose | Current Usage | Strengths | Weaknesses | Recommendation |
|---|---|---|---|---|---|
| **Runtime Scheduler** (`orion.runtime.scheduler`) | Manages the worker thread pool. | Spawns N Worker threads to poll the Queue concurrently. | Safe, GIL-friendly multi-threading, simple. | Limited to standard process-level threads. | **RETAIN.** Core orchestrator of the physical thread pool. |
| **Runtime Worker** (`orion.runtime.worker`) | Claims queue items and coordinates execution lifecycle. | Grabs READY missions and triggers the Builder Agent. | Handles cancellation and WAITING statuses correctly. | Tight coupling to the synchronous Builder Agent. | **RETAIN.** Essential for queue status transitions. |
| **Builder Agent** (`orion.agents.builder.agent`) | Executes claimed missions and discovers context. | Decides context, risk, and runs the Pipeline. | Thread-safe scan-and-claim locks, strong error fallback. | Overburdened with business, risk, and board logic. | **REFACTOR.** Extract business/risk parsing into separate services. |
| **Execution Pipeline** (`orion.execution.pipeline`) | Manages isolated workspaces, branches, and commits. | Prepares workspace, branches, validates, commits, and pushes. | Clean sandboxing, atomic file writes, reverts to main. | Sync local filesystem writes; lacks virtualized sandbox. | **RETAIN & ISOLATE.** Move file writes into Docker sandboxes. |
| **Task Runner** (`orion.execution.task_runner`) | Delegates work to legacy handlers or the Executor. | Routes legacy handlers or `orion.executor.services`. | Clean backward-compatible proxy. | Represents a bifurcated handler contract. | **PHASE OUT.** Route all mission types through the generic Executor. |
| **Executor** (`orion.executor.services`) | Coordinates Provider Adapters. | Loads PromptPackages and executes Provider Adapters. | Modular, vendor-agnostic, importlib plugin discovery. | Still runs inside a synchronous thread pool. | **RETAIN & EVOLVE.** Make it the single execution entry point. |
| **COO Agent / Scheduler** (`orion.agents.coo`) | Legacy offline task-assigner and cycle scheduler. | **DEAD CODE.** Only invoked to show mock state on The Window. | Completely offline and dependency-free. | Bypassed entirely by the Runtime Worker loop. | **DISAPPEAR.** Retire entirely and remove from dashboard. |

---

## 3. Responsibility Matrix

An audit of the subsystems reveals the following overlap, conflicts, and ownership lines:

| Subsystem | Single Responsibility | Current Responsibility | Duplicated Responsibility | Conflict / Gap | Owner |
|---|---|---|---|---|---|
| **Bridge Queue** | Simple list of queued mission IDs. | Core queue pointer. | Overlaps with Runtime Queue's states. | Dual tracking of "next ready" item. | `orion.bridge` |
| **Runtime Queue** | Thread-safe transactional queue items. | Bookkeeping of active worker execution states. | Partially duplicates Bridge Queue. | Disagreement on terminal queue states. | `orion.runtime` |
| **COO Dispatcher** | Assign mission to a builder. | Registers `mission.owner`. | Overlapped by Runtime Worker claiming. | Bypassed; does not block execution. | `orion.agents.coo` |
| **Task Planner** | Intent decomposition into multiple missions. | Creates sequenced plan steps. | Looks similar to Board routing templates. | Overlapping tokenization and keyword rules. | `orion.intelligence` |
| **Board Engine** | Determine pipeline stages per mission. | Assigns Board members and stages. | Retrospective tracking of completed stages. | Passive tracking only; does not active-steer. | `orion.board` |
| **Governance Engine** | Evaluate policy and risk of change. | Assesses risk, classifications, hard stops. | Category evaluation duplicated by Board. | Unified via B-011's category reuse. | `orion.governance` |

---

## 4. Competing Implementations Analysis

### 4.1. The Scheduling Duplication (COO vs Runtime)
- **The Duplication:** The system has two competing scheduler loops:
  1. The **COO Agent scheduler** (`orion.agents.coo.scheduler`) which scans the queue and assigns the mission's owner to `builder-1` as an offline step.
  2. The **Runtime Scheduler** (`orion.runtime.scheduler`) which spawns concurrent Workers to scan, transition, and execute READY missions directly on thread pools.
- **The Core Issue:** Under the modern Runtime loop, the COO's dispatcher is completely bypassed. The Runtime Worker claims the next READY mission *regardless* of whether the COO dispatcher has assigned it or not. The COO's cycle is only triggered manually or mocked to render on The Window dashboard.
- **Reconciliation:** The COO Agent represents a legacy, early-generation conceptual design. It must be retired entirely.

### 4.2. The Execution Contract Duplication (Handlers vs Executor)
- **The Duplication:** There are currently two parallel execution pathways:
  1. **Legacy Handlers** (`orion/agents/builder/handlers.py`) which implement a `MissionHandler` interface with simple, deterministic mocks for `documentation`, `research`, `scaffold`, and `code_generation`.
  2. **The Modern Executor** (`orion/executor/services.py`) which executes the `executor` mission type, consuming the compiled `PromptPackage` and invoking polymorphic `ProviderAdapter`s (like `claude_code` or `deterministic_local`).
- **The Core Issue:** This bifurcated contract requires maintaining two entirely separate execution architectures, registry systems, and file relocation mechanisms.
- **Reconciliation:** Legacy handlers must be deprecated. All mission types must be unified under the generic **Executor** model. A documentation mission should simply be an `executor` mission running with an adapter that generates markdown files, preserving structural coherence.

---

## 5. Runtime & Board Layer Audits

### 5.1. Runtime Layer Audit
- **Overlap:** The **Bridge Queue** (`workspace/queue.json`) and **Runtime Queue** (`workspace/runtime_queue.yaml`) represent redundant queue state files. The Runtime Queue wraps the Bridge Queue with concurrency-safe locking and cancellation states.
- **Gap:** The local `ThreadPoolExecutor` blocks python threads while waiting on long subprocess Claude Code loops. This prevents horizontal scaling across cluster boundaries.
- **Action:** Merge the queues. Replace the dual YAML file filesystems with a single ACID-compliant SQLite backend or lightweight local database.

### 5.2. Board Layer Audit
- **Assessment:** Does the Board truly act as the central orchestrator? **No.**
- **The Hard Truth:** The AI Board is currently a **passive tracking layer**. `compute_progress` parses completed mission event logs *retrospectively* to show checkmarks on the dashboard. The physical execution is entirely controlled by the Runtime Worker and the Execution Pipeline.
- **Action:** Elevate the Board from a passive log tracker to an **active execution coordinator**. The Board Orchestrator should actively dispatch sub-tasks to individual provider adapters mapped to specific board members (e.g. Chat GPT for architecture, Nemotron for review), wait for their responses, and step through the pipeline states programmatically.

---

## 6. Canonical Architecture (The Ideal Blueprint)

If ORION OS were rewritten today, it would follow a clean, 3-tier layering model, completely removing duplicate dispatch loops and legacy mock handlers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           1. INTERFACE LAYER                            │
│    FastAPI Gateway  ◄──►  SSE Event Bus  ◄──►  Command CLI (bin/orion)  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         2. ORCHESTRATION LAYER                          │
│     AI Board Orchestrator  ◄──►  Active Mission Pipeline Controller     │
│             ▲                                       ▲                   │
│             ▼                                       ▼                   │
│     Governance Policy                     SQLite / Redis Job Queue      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           3. EXECUTION LAYER                            │
│                      Universal Executor (Task Engine)                   │
│                                    │                                    │
│            ┌───────────────────────┴───────────────────────┐            │
│            ▼                                               ▼            │
│  [ deterministic_local ]                      [ claude_code ]           │
│  (In-Memory Test Sandbox)                (Docker-isolated Subprocess)   │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Tier 1: Interface Layer:** The thin REST/SSE FastAPI router and the CLI, talking exclusively to Tier 2 services.
- **Tier 2: Orchestration Layer:** The Active Board Orchestrator manages the Mission Flow, evaluating Governance policies before dispatch, and enqueuing tasks into a robust, transactional queue.
- **Tier 3: Execution Layer:** The single, universal Executor coordinates stateless Provider Adapters. Every execution takes place inside ephemeral, isolated Docker sandboxes with no direct host privileges.

---

## 7. Migration Strategy

The migration of ORION OS's architecture to the canonical model will proceed in 4 phases:

### Phase 1: Retire the Legacy COO Agent
- **Objective:** Eliminate the obsolete, bypassed COO scheduler and dispatcher.
- **Execution:** Remove `orion.agents.coo`, delete `coo_state.yaml`, and strip out the COO panel from The Window dashboard (`board.html` / `routes.py`). Update the pipeline view to show active Runtime Worker statuses instead.
- **Effort:** Low (1-2 days) | **Complexity:** Low | **Risks:** Minimal.

### Phase 2: Unify Execution Handlers under the Universal Executor
- **Objective:** Deprecate legacy `MissionHandler`s and transition all work to the Executor.
- **Execution:** Re-map `documentation`, `research`, and `scaffold` to execute as `executor` missions. Provide default PromptPackage instructions matching the old mock headers, executing them via `deterministic_local` (in tests) or a real provider. Remove `orion/agents/builder/handlers.py` and `orion/agents/builder/registry.py`.
- **Effort:** Medium (4-5 days) | **Complexity:** Medium | **Risks:** High probability of breaking legacy tests; requires updating mock expectations in `tests/test_executor.py`.

### Phase 3: Transition to ACID SQLite Queueing
- **Objective:** Merge redundant Bridge/Runtime Queue files into a single reliable transactional database.
- **Execution:** Implement an SQLite-backed queue manager. Replace `queue.json` and `runtime_queue.yaml` with a single `orion.db` database file containing `missions` and `queue_items` tables, fully protected by transactional locking.
- **Effort:** Medium (5-6 days) | **Complexity:** Medium | **Risks:** Requires updating storage wrappers across multiple subsystems.

### Phase 4: Upgrade the Board to an Active Orchestrator
- **Objective:** Elevate the Board from passive retrospective log parsing to active state-machine steering.
- **Execution:** Implement `BoardOrchestrator`. For a given mission pipeline (e.g. Architect -> Builder -> Reviewer), the orchestrator executes each stage by enqueuing a sub-execution request to the corresponding Board Member's designated provider adapter, dynamically monitoring status, and transitioning only upon verified validation.
- **Effort:** High (8-10 days) | **Complexity:** High | **Risks:** Major architectural shift; requires extensive simulation tests and telemetry tracking.

---

## 8. Technical Risks & Mitigations

1. **Test Suite Regressions (High Risk):** Deprecating legacy handlers and registry files will break pre-existing unit and integration tests designed around the Sprint 006 mocks.
   - *Mitigation:* Ensure Phase 2 is executed incrementally. Introduce backward-compatible adapter wrappers that mimic legacy output files during migration before completely deleting the legacy handlers.
2. **Concurrency and State Race Conditions (Medium Risk):** Moving to an active orchestrator with concurrent worker threads could introduce transaction lock contention in SQLite if multiple threads write simultaneously.
   - *Mitigation:* Implement robust WAL (Write-Ahead Logging) mode in SQLite and wrap all database modifications in atomic, self-retrying transaction handlers.
3. **Subprocess Orphan Leakage (Low Risk):** Under multi-threaded active orchestration, if a worker thread dies or is killed, child processes spawned by provider adapters could become orphaned.
   - *Mitigation:* Register process IDs in a centralized, OS-level process tracker that kills all recorded children on parent process termination.

---

## 9. Long-Term Five-Year Vision: ORION as the Digital CEO

In five years, ORION OS will operate not as a tool directory, but as an autonomous, high-performing corporate executive:

- **Autonomous Departmental Hierarchies:** ORION will coordinate departments (e.g., Engineering, Marketing, Finance) populated by specialized agent pools. The Board will act as the "Cabinet of Directors", resolving conflicts, auditing risks, and dynamically re-allocating cloud compute budgets.
- **Self-Optimizing Architecture:** The System will continuously analyze its own telemetry, identify execution bottlenecks or adapter failures, and dynamically refactor its own provider adapter routes (e.g., automatically routing a task to Codex if Sonnet experiences high API latency).
- **Zero Host Trust (Safe Sandboxing):** Every external tool execution, file write, or shell command will take place inside ephemeral, micro-virtualized container clusters with real-time network sniffing and intrusion detection, guaranteeing complete isolation from host systems.

---

## 10. Immediate Next Steps

To kick off the Architecture Reconciliation immediately:

1. **Approve Phase 1 (Retire COO):** Issue a formal ADR (ADR-0007) proposing the complete deprecation of `orion.agents.coo` and the COO panel.
2. **Standardize the Executor Contract:** Transition the remaining core developer focus exclusively to the `PromptPackage` and `ProviderAdapter` structures. Any new capabilities (e.g., Ollama or Gemini integrations) must be built strictly as `ProviderAdapter` classes, never legacy handlers.
3. **Initialize the SQLite migration:** Create a prototype schema for the unified database backend to prove transaction safety under concurrent worker loads.
