# Architecture

## Mission

ORION OS is an AI-powered Business Intelligence Operating System. It understands businesses, discovers opportunities, recommends valuable products and services, coordinates specialized AI agents, and continuously improves its own knowledge.

ORION is not a CRM, not a scraper, and not an automation platform. It is an operating system that coordinates specialized AI agents to help businesses grow.

## Status

**Pre-alpha.** The components below are described conceptually only. None are implemented. No application code exists in this repository yet.

## MVP: The Executive Orchestrator

The first software component to be built will be the **Executive Orchestrator**.

The Executive Orchestrator coordinates a set of specialized agents, routing work and information between them so that ORION can act on a business's behalf as a coherent system rather than a collection of disconnected tools.

## Specialized Agents (Descriptions Only)

The Executive Orchestrator is planned to coordinate the following specialized agents. These are conceptual descriptions of intended purpose — none are implemented, and none should be implemented from this document alone.

### Planner
Breaks down ORION's goals for a business into concrete, sequenced steps, and determines which specialized agents need to act, and in what order.

### Memory
Maintains ORION's persistent understanding of a business over time — what has already been learned, decided, or acted on — so that other agents don't have to rediscover context.

### Knowledge
Maintains and provides access to ORION's general knowledge base — domain, market, and product knowledge that isn't specific to any one business.

### Business Scout
Discovers and surfaces businesses and opportunities relevant to ORION's mission.

### Business Profiler
Builds and maintains a structured understanding of a specific business — what it does, how it operates, and what it needs.

### Opportunity Engine
Identifies growth opportunities for a given business, based on its profile and ORION's knowledge.

### Recommendation Engine
Turns identified opportunities into concrete, actionable recommendations of products or services.

### Communication Agent
Handles communication with or on behalf of a business — presenting findings, recommendations, and updates.

## Cross-Cutting Principles

- **Avoid vendor lock-in** — architecture choices should favor portability and replaceability over proprietary dependencies.
- **Avoid overengineering** — build only what current, approved scope requires; the components above are described, not scaffolded.
- **Documentation is institutional memory** — this document is the source of truth for ORION's intended architecture and must be kept current as decisions are made.

## Related

- Major architectural decisions are recorded in [`DECISIONS.md`](DECISIONS.md).
- Governance and how architecture gets approved: [`../.ai/DECISION_PROCESS.md`](../.ai/DECISION_PROCESS.md).
