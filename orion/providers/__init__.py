"""Real Provider Adapters for the Executor.

One subpackage per external AI provider -- today only
orion.providers.claude_code, in the future orion.providers.codex_cli,
orion.providers.gemini_cli, orion.providers.jules, etc. Each
subpackage registers its adapter(s) with orion.executor.registry as
an import-time side effect, the same way the built-in
deterministic_local adapter (orion.executor.adapters.deterministic)
already does.

orion.executor never imports any of these subpackages by name.
orion.executor.services discovers them dynamically, by convention: if
adapter '<x>' isn't registered when a mission asks for it, it attempts
``importlib.import_module(f"orion.providers.{x}")`` before failing.
This is exactly what makes "cambiar unicamente la configuracion:
provider = 'claude_code'" true -- no import, no wiring, no code change
anywhere in orion.executor is needed to add a new real provider.
"""
