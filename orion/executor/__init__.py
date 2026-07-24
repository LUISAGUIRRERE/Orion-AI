"""Executor -- ORION's provider-agnostic execution layer.

Takes a PromptPackage (built entirely by orion.prompt_composer -- the
Executor never builds its own context) and delegates the actual work
to a configurable Provider Adapter. The Executor itself:

- never runs git (see orion.execution.git_manager, the only module
  allowed to);
- never decides architecture (that is already decided by whatever
  produced the PromptPackage's technical_context/architecture_rules);
- never discovers context on its own (see orion.prompt_composer);
- contains no logic specific to React, Next.js, WordPress, Flutter,
  or any other technology stack.

Its only jobs are: build a neutral ExecutionRequest, hand it to the
adapter registered under the requested name, enforce a timeout,
capture any error in a structured ExecutionResult, and persist both
as evidence. See orion.executor.services.run_for_mission, the single
entry point orion.execution.task_runner calls.
"""
