"""Command Bridge — the single channel through which missions, messages,
and events move between The Window, the CEO, and every agent.

No agent talks to another agent directly. Everything passes through
this module and is persisted.
"""
