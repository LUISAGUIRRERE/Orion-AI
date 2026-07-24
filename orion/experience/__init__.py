"""Experience Engine -- ORION's operational memory.

Not a log database: after every mission, this package turns what
actually happened (the Mission itself, its PromptPackage, its
ExecutionResult if it had one, the Execution Pipeline's own outcome --
what this package calls the "Git Result" -- and its event timeline)
into two durable, reusable things:

- an ExperienceReport (models.py) -- structured evidence of what one
  mission achieved, cost, and revealed;
- zero or more KnowledgeItem entries in the Knowledge Store
  (knowledge_store.py) -- Patterns, Decisions, Lessons, Risks,
  Opportunities, and Best Practices, each traceable back to the
  mission that produced it.

Classification in this v1 is entirely deterministic (see rules.py) --
no AI call of any kind. The point of this Sprint is the contract: a
consistent, queryable shape for "what did we learn", not (yet) genuine
judgment about what any of it means.

Completely decoupled from orion.prompt_composer, orion.executor, and
orion.execution.git_manager: this package only ever reads their
already-public, already-persisted outputs (PromptPackage YAML,
ExecutionResult YAML, the Pipeline's own outcome YAML, the Mission
Framework's own event log) through their existing storage/service
modules -- it never imports their internals and never asks any of
them to change how they work. See orion.experience.services for the
single entry point orion.agents.builder.agent calls.
"""
