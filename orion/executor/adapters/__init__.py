"""Provider Adapters for the Executor.

Importing this package registers every built-in adapter (currently:
``deterministic_local``) as a side effect -- see each adapter module's
own docstring. orion.executor.services imports this package for
exactly that reason before ever calling
orion.executor.registry.get_adapter.
"""

from orion.executor.adapters import deterministic  # noqa: F401 -- import registers the built-in adapter
