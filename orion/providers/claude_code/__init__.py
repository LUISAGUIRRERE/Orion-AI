"""Claude Code Provider Adapter package.

Importing this package registers ClaudeCodeAdapter (name
'claude_code') with orion.executor.registry as a side effect. This
happens two ways, both supported:

- explicitly, if something imports orion.providers.claude_code
  directly;
- implicitly, via orion.executor.services' dynamic-discovery fallback
  the first time a mission resolves to adapter name 'claude_code' and
  it isn't registered yet (``importlib.import_module(
  "orion.providers.claude_code")``).
"""

from orion.providers.claude_code import adapter as _adapter  # noqa: F401 -- import registers ClaudeCodeAdapter
