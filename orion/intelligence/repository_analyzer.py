"""Real repository scanning -- no simulated or hardcoded findings.

Every fact this module produces comes from actually reading the
filesystem at ``repo_root``: real ``os.walk``, real ``ast.parse`` for
Python source (imports, exports, TODOs, a McCabe-style complexity
count), real regex-based import/export extraction for JS/TS (no JS
parser dependency exists in this project, so this is a best-effort
heuristic, documented as such below), and real presence checks for
Docker/Compose/CI/env/manifest files. A file this module cannot make
sense of is still indexed (path/type/size/mtime) -- it just carries no
imports/exports/complexity, exactly like project_index.py's own
"degrades gracefully" convention already established by
orion.prompt_composer.discovery.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from orion.intelligence.config import IntelligenceConfig

# ---------------------------------------------------------------------------
# Per-file record
# ---------------------------------------------------------------------------


@dataclass
class FileRecord:
    """Real, observed facts about one file. See module docstring for
    what "real" means here -- nothing below is inferred without
    reading the actual file."""

    path: str  # POSIX-style, relative to repo_root
    language: str
    purpose: str
    size_bytes: int
    modified_at: str
    content_hash: str | None  # None for files never read (binary/too large)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    todo_count: int = 0
    complexity: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "purpose": self.purpose,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "content_hash": self.content_hash,
            "imports": self.imports,
            "exports": self.exports,
            "todo_count": self.todo_count,
            "complexity": self.complexity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileRecord":
        return cls(
            path=data["path"],
            language=data.get("language", "other"),
            purpose=data.get("purpose", "other"),
            size_bytes=data.get("size_bytes", 0),
            modified_at=data.get("modified_at", ""),
            content_hash=data.get("content_hash"),
            imports=list(data.get("imports", [])),
            exports=list(data.get("exports", [])),
            todo_count=data.get("todo_count", 0),
            complexity=data.get("complexity", 0),
        )


# ---------------------------------------------------------------------------
# Repository-level profile
# ---------------------------------------------------------------------------


@dataclass
class RepositoryProfile:
    """Real, repo-wide signals -- every field is either a direct file
    presence check or a real count derived from scanned files."""

    languages: dict[str, int] = field(default_factory=dict)  # language -> file count
    frameworks: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_compose: bool = False
    has_ci: bool = False
    env_files: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    todo_items: list[dict] = field(default_factory=list)  # [{"path":..., "line":..., "text":...}]
    roadmap_files: list[str] = field(default_factory=list)
    counts_by_purpose: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "languages": self.languages,
            "frameworks": self.frameworks,
            "has_docker": self.has_docker,
            "has_compose": self.has_compose,
            "has_ci": self.has_ci,
            "env_files": self.env_files,
            "entrypoints": self.entrypoints,
            "todo_items": self.todo_items,
            "roadmap_files": self.roadmap_files,
            "counts_by_purpose": self.counts_by_purpose,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RepositoryProfile":
        return cls(
            languages=dict(data.get("languages", {})),
            frameworks=list(data.get("frameworks", [])),
            has_docker=data.get("has_docker", False),
            has_compose=data.get("has_compose", False),
            has_ci=data.get("has_ci", False),
            env_files=list(data.get("env_files", [])),
            entrypoints=list(data.get("entrypoints", [])),
            todo_items=list(data.get("todo_items", [])),
            roadmap_files=list(data.get("roadmap_files", [])),
            counts_by_purpose=dict(data.get("counts_by_purpose", {})),
        )


_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sh": "shell",
    ".sql": "sql",
}

_FRAMEWORK_MARKERS: dict[str, str] = {
    "manage.py": "django",
    "next.config.js": "next.js",
    "next.config.ts": "next.js",
    "angular.json": "angular",
    "vue.config.js": "vue",
    "nuxt.config.js": "nuxt",
    "artisan": "laravel",
    "Gemfile": "ruby-on-rails" ,
}

_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|XXX)\b[:\s]*(.*)", re.IGNORECASE)
_JS_IMPORT_PATTERN = re.compile(
    r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|require\()\s*['"]([^'"]+)['"]"""
)
_JS_EXPORT_PATTERN = re.compile(
    r"""export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z0-9_$]+)"""
)


def _relpath(full: Path, repo_root: Path) -> str:
    return full.relative_to(repo_root).as_posix()


def _is_ignored(rel_parts: tuple[str, ...], ignored_dirs: frozenset[str]) -> bool:
    return any(part in ignored_dirs for part in rel_parts)


def _classify_purpose(rel_path: str) -> str:
    lower = rel_path.lower()
    parts = lower.split("/")
    name = parts[-1]

    if "test" in parts or name.startswith("test_") or name.endswith("_test.py") or ".test." in name or ".spec." in name:
        return "test"
    if name in ("dockerfile",) or name.startswith("docker-compose"):
        return "config"
    if name in (".env", ".env.example", ".env.local") or name.startswith(".env."):
        return "env"
    if parts[0] == ".github" and "workflows" in parts:
        return "ci"
    if name in ("readme.md", "roadmap.md", "backlog.md", "changelog.md") or parts[0] == "docs":
        return "documentation"
    if "template" in parts or name.endswith((".html", ".jinja", ".jinja2")):
        return "template"
    if "static" in parts or "assets" in parts or "public" in parts or name.endswith(
        (".css", ".scss", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".woff", ".woff2")
    ):
        return "asset"
    if "bin" in parts or "scripts" in parts or name.endswith(".sh"):
        return "script"
    if name in ("cli.py", "__main__.py") or "cli" in parts:
        return "cli"
    if "api" in parts or name in ("routes.py", "api.py", "urls.py"):
        return "api"
    if "model" in name or "models" in parts:
        return "model"
    if "controller" in name or "controllers" in parts or "views" in parts or "routes" in parts:
        return "controller"
    if "service" in name or "services" in parts:
        return "service"
    if name in ("package.json", "requirements.txt", "pyproject.toml", "pipfile", "gemfile", "cargo.toml", "go.mod"):
        return "config"
    return "source"


def _extract_python(text: str) -> tuple[list[str], list[str], int]:
    """Real AST-based extraction: import module names, top-level
    def/class names, and a McCabe-style complexity count (1 + number
    of branch/boolean-operator/comprehension nodes in the whole
    file). Falls back to empty results (never raises) on a file this
    Python version's own parser rejects -- e.g. Python 2 source."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], [], 0

    imports: list[str] = []
    exports: list[str] = []
    complexity = 1
    _branch_types = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.BoolOp,
        ast.IfExp,
        ast.comprehension,
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * (node.level or 0)
            imports.append(f"{prefix}{node.module or ''}")
        elif isinstance(node, _branch_types):
            complexity += 1

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.append(node.name)

    return imports, exports, complexity


def _extract_js(text: str) -> tuple[list[str], list[str]]:
    """Regex-based, deliberately best-effort: no JS/TS parser is a
    dependency of this project. Real signal (actual import/require/
    export statements present in the real file text), just not a full
    parse -- documented here rather than silently pretending this is
    as rigorous as the Python path."""
    imports = _JS_IMPORT_PATTERN.findall(text)
    exports = _JS_EXPORT_PATTERN.findall(text)
    return imports, exports


def _count_todos(text: str) -> int:
    return sum(1 for _ in _TODO_PATTERN.finditer(text))


def _collect_todo_items(rel_path: str, text: str, limit: int = 20) -> list[dict]:
    items = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _TODO_PATTERN.search(line)
        if match:
            items.append({"path": rel_path, "line": lineno, "text": line.strip()[:200]})
            if len(items) >= limit:
                break
    return items


def analyze_file(
    full_path: Path,
    repo_root: Path,
    config: IntelligenceConfig,
    previous: "FileRecord | None" = None,
) -> FileRecord:
    """Analyze exactly one real file on disk. Never raises: any
    read/parse failure degrades to a bare path/type/size/mtime record,
    the same graceful-degradation convention
    orion.prompt_composer.discovery already established.

    Incremental fast path (project_index.py's own "No volver a
    recorrer archivos que no cambiaron"): if ``previous`` is given and
    its size_bytes/modified_at match this file's *current* stat
    exactly, ``previous`` is returned unchanged -- the file's content
    is never re-read, re-parsed, or re-hashed. This is the one shared
    implementation both a plain, one-shot scan (scan_repository with
    no previous state) and an incremental index rebuild
    (project_index.build_index, which always has previous state) go
    through, so the skip-if-unchanged logic exists in exactly one
    place.
    """
    rel_path = _relpath(full_path, repo_root)
    ext = full_path.suffix.lower()
    language = _LANGUAGE_BY_EXT.get(ext, "other")
    purpose = _classify_purpose(rel_path)

    try:
        stat = full_path.stat()
        size_bytes = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        size_bytes = 0
        modified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if previous is not None and previous.size_bytes == size_bytes and previous.modified_at == modified_at:
        return previous

    content_hash: str | None = None
    imports: list[str] = []
    exports: list[str] = []
    todo_count = 0
    complexity = 0

    should_read_content = ext in config.source_extensions and size_bytes <= config.max_content_bytes
    if should_read_content:
        try:
            text = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        if text is not None:
            content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            todo_count = _count_todos(text)
            if language == "python":
                imports, exports, complexity = _extract_python(text)
            elif language in ("javascript", "typescript", "vue"):
                imports, exports = _extract_js(text)

    return FileRecord(
        path=rel_path,
        language=language,
        purpose=purpose,
        size_bytes=size_bytes,
        modified_at=modified_at,
        content_hash=content_hash,
        imports=imports,
        exports=exports,
        todo_count=todo_count,
        complexity=complexity,
    )


def scan_repository(
    repo_root: Path,
    config: IntelligenceConfig | None = None,
    previous_files: dict[str, FileRecord] | None = None,
) -> tuple[RepositoryProfile, list[FileRecord]]:
    """Real, full filesystem walk of ``repo_root``. Returns a
    repo-level profile plus one FileRecord per non-ignored file.
    Never raises for an individual unreadable file -- see
    analyze_file(). Raises only if ``repo_root`` itself does not
    exist, exactly like every git_manager/Workspace call in this
    project already does for a missing repository.

    ``previous_files`` (path -> FileRecord from an earlier run, keyed
    exactly like project_index.ProjectIndex.files) enables the
    incremental fast path described on analyze_file() for every file
    whose stat is unchanged since that earlier run. The directory walk
    itself is never skipped (new/deleted files must still be
    discovered), only each individual file's content re-read/re-parse
    is skipped when nothing about it changed.
    """
    config = config or IntelligenceConfig.from_env()
    previous_files = previous_files or {}
    if not repo_root.is_dir():
        raise FileNotFoundError(f"repo_root no existe o no es un directorio: {repo_root}")

    records: list[FileRecord] = []
    profile = RepositoryProfile()

    for root, dirnames, filenames in os.walk(repo_root):
        root_path = Path(root)
        rel_root_parts = root_path.relative_to(repo_root).parts
        if _is_ignored(rel_root_parts, config.ignored_dirs):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in config.ignored_dirs]

        for filename in filenames:
            full_path = root_path / filename
            rel_parts = full_path.relative_to(repo_root).parts
            if _is_ignored(rel_parts, config.ignored_dirs):
                continue

            rel_path_str = full_path.relative_to(repo_root).as_posix()
            record = analyze_file(full_path, repo_root, config, previous=previous_files.get(rel_path_str))
            records.append(record)

            profile.languages[record.language] = profile.languages.get(record.language, 0) + 1
            profile.counts_by_purpose[record.purpose] = profile.counts_by_purpose.get(record.purpose, 0) + 1

            if filename in _FRAMEWORK_MARKERS:
                fw = _FRAMEWORK_MARKERS[filename]
                if fw not in profile.frameworks:
                    profile.frameworks.append(fw)
            if filename.lower() == "dockerfile":
                profile.has_docker = True
            if filename.lower().startswith("docker-compose"):
                profile.has_compose = True
            if rel_root_parts[:2] == (".github", "workflows"):
                profile.has_ci = True
            if record.purpose == "env":
                profile.env_files.append(record.path)
            if record.purpose == "cli" or filename in ("__main__.py",) or (root_path.name == "bin"):
                profile.entrypoints.append(record.path)
            if filename.lower() in ("roadmap.md", "backlog.md"):
                profile.roadmap_files.append(record.path)
            if record.todo_count:
                try:
                    text = full_path.read_text(encoding="utf-8")
                    profile.todo_items.extend(_collect_todo_items(record.path, text))
                except (OSError, UnicodeDecodeError):
                    pass

    # Framework hints from package.json dependency keys, if present.
    package_json = repo_root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for marker, fw in (("react", "react"), ("vue", "vue"), ("next", "next.js"), ("express", "express"), ("fastify", "fastify")):
                if marker in deps and fw not in profile.frameworks:
                    profile.frameworks.append(fw)
        except (OSError, ValueError):
            pass

    pyproject = repo_root / "pyproject.toml"
    requirements = repo_root / "requirements.txt"
    for pyfile, needle_fw in ((pyproject, None), (requirements, None)):
        if pyfile.is_file():
            try:
                text = pyfile.read_text(encoding="utf-8").lower()
                for marker, fw in (("fastapi", "fastapi"), ("django", "django"), ("flask", "flask"), ("pydantic", "pydantic")):
                    if marker in text and fw not in profile.frameworks:
                        profile.frameworks.append(fw)
            except OSError:
                pass

    return profile, records
