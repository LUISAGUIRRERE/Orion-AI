"""ORION Project Intelligence (BETA 008).

Understands a real repository before ORION writes a single line of
code: repository_analyzer.py (real filesystem/AST scanning),
project_index.py (persistent, incrementally-updated per-file index),
architecture_map.py (live module tree), dependency_graph.py (real
import graph + blast-radius queries), component_finder.py (real
similarity search for reuse), impact_analyzer.py (real risk/impact
report), task_planner.py (rule-based decomposition into real
Missions), knowledge_graph.py (typed nodes/edges, grows from real
events), reviewer.py (real static checks), services.py (the one
entry point every caller -- CLI, Runtime, The Window -- uses),
storage.py (persistence), config.py (env-driven configuration).

Nothing here duplicates or replaces the Mission Framework, Prompt
Composer, Executor, GitManager, or Experience Engine -- it reads from
a project's real filesystem and from ORION's own already-persisted
data, and it feeds real findings *into* those existing systems as
additional context/events, never as a parallel execution path.
"""
