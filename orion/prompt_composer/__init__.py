"""Prompt Composer -- ORION's model-agnostic context-building layer.

This package is the only place in ORION that turns a Mission into the
full context an implementation needs. It knows nothing about any
specific AI provider or coding agent (no Claude, Codex, or Gemini
specific formatting lives here) and nothing about any specific
technology stack (no Next.js/React/WordPress/Flutter assumptions) --
it only knows how to discover and structure context that already
exists in a project's own repository and in ORION's own Mission
Framework.

Its single public entry point is ``services.compose_for_mission``,
which the Builder Agent calls. See ``composer.py`` for the actual
discovery-to-PromptPackage logic and ``models.py`` for the neutral,
structured output (``PromptPackage``) every future execution adapter
(Claude Code, Codex CLI, Gemini CLI, Jules, ...) will translate from.
"""
