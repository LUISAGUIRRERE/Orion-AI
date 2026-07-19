"""Business logic for The Window.

Two data sources are used, deliberately kept simple:

- Business units are read from persistent YAML files under
  ``workspace/business/<slug>/business.yaml`` (PyYAML).
- Events are appended to and read from a small SQLite database at
  ``workspace/events.db`` (stdlib ``sqlite3``, no ORM).

Nothing here talks to the network or to any external service. This is
the minimum needed to make The Window functional.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from orion.window.models import (
    BusinessUnit,
    BusinessUnitCard,
    DashboardSummary,
    Event,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
WORKSPACE_DIR: Path = REPO_ROOT / "workspace"
BUSINESS_DIR: Path = WORKSPACE_DIR / "business"
DB_PATH: Path = WORKSPACE_DIR / "events.db"

# Example data seeded on first run only. Existing files are never
# overwritten, per the "no romper / no eliminar" Sprint restriction.
_SEED_BUSINESS_UNITS: dict[str, dict[str, Any]] = {
    "atman": {
        "name": "ATMAN",
        "status": "active",
        "health": "green",
        "objective": "Escalar el negocio principal y consolidar los procesos core.",
        "missions": ["Optimizar el funnel de ventas", "Cerrar acuerdo con proveedor clave"],
        "business": {"stage": "growth", "revenue_status": "estable"},
        "events": [],
        "decisions": ["Aprobar presupuesto de marketing Q3"],
        "opportunities": ["Expandir a nuevo segmento de clientes"],
    },
    "cgiso": {
        "name": "CGISO",
        "status": "active",
        "health": "yellow",
        "objective": "Estabilizar operaciones y reducir tiempos de entrega.",
        "missions": ["Renegociar contrato con socio logístico"],
        "business": {"stage": "operations", "revenue_status": "bajo presión"},
        "events": [],
        "decisions": ["Definir nuevo proveedor logístico"],
        "opportunities": [],
    },
    "casino": {
        "name": "CASINO",
        "status": "paused",
        "health": "red",
        "objective": "Resolver bloqueo regulatorio antes de reanudar operación.",
        "missions": [],
        "business": {"stage": "blocked", "revenue_status": "detenido"},
        "events": [],
        "decisions": ["Decidir si se continúa o se cierra la unidad"],
        "opportunities": [],
    },
    "tealife": {
        "name": "TEALIFE",
        "status": "active",
        "health": "green",
        "objective": "Lanzar nueva línea de producto.",
        "missions": ["Finalizar empaque", "Validar proveedor de materia prima"],
        "business": {"stage": "launch", "revenue_status": "creciendo"},
        "events": [],
        "decisions": [],
        "opportunities": ["Entrar a mercado internacional"],
    },
    "resonance": {
        "name": "RESONANCE",
        "status": "planning",
        "health": "yellow",
        "objective": "Definir modelo de negocio inicial.",
        "missions": ["Completar investigación de mercado"],
        "business": {"stage": "planning", "revenue_status": "pre-revenue"},
        "events": [],
        "decisions": ["Aprobar plan de negocio inicial"],
        "opportunities": ["Alianza estratégica potencial"],
    },
    "autismo": {
        "name": "AUTISMO",
        "status": "active",
        "health": "green",
        "objective": "Ampliar cobertura del programa actual.",
        "missions": ["Capacitar nuevo equipo terapéutico"],
        "business": {"stage": "growth", "revenue_status": "estable"},
        "events": [],
        "decisions": [],
        "opportunities": ["Convenio con nueva institución educativa"],
    },
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_workspace() -> None:
    """Create the workspace layout and seed example data if missing.

    Idempotent: never overwrites a ``business.yaml`` that already
    exists, and only seeds initial events if the events table is empty.
    """
    BUSINESS_DIR.mkdir(parents=True, exist_ok=True)
    for slug, data in _SEED_BUSINESS_UNITS.items():
        unit_dir = BUSINESS_DIR / slug
        unit_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = unit_dir / "business.yaml"
        if not yaml_path.exists():
            with yaml_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)

    _init_db()
    if count_events() == 0:
        _seed_initial_events()


def _init_db() -> None:
    """Create the events table if it does not already exist."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                business_unit TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                autor TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _seed_initial_events() -> None:
    """Insert a handful of example events on first run."""
    seed = [
        ("update", "atman", "Cierre de mes completado sin incidencias.", "ORION"),
        ("alert", "casino", "Operación pausada por revisión regulatoria.", "ORION"),
        ("decision", "resonance", "Pendiente aprobar plan de negocio inicial.", "ORION"),
        ("update", "tealife", "Nueva línea de producto avanza según plan.", "ORION"),
    ]
    for tipo, business_unit, mensaje, autor in seed:
        log_event(tipo=tipo, business_unit=business_unit, mensaje=mensaje, autor=autor)


def log_event(tipo: str, business_unit: str, mensaje: str, autor: str) -> Event:
    """Store a new event and return it."""
    fecha = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO events (fecha, tipo, business_unit, mensaje, autor) VALUES (?, ?, ?, ?, ?)",
            (fecha, tipo, business_unit, mensaje, autor),
        )
        conn.commit()
        event_id = cursor.lastrowid
    return Event(id=event_id, fecha=fecha, tipo=tipo, business_unit=business_unit, mensaje=mensaje, autor=autor)


def get_events(limit: int = 50) -> list[Event]:
    """Return the most recent events, newest first."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, fecha, tipo, business_unit, mensaje, autor FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [Event(**dict(row)) for row in rows]


def count_events() -> int:
    """Return the total number of stored events."""
    if not DB_PATH.exists():
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    return int(row[0])


def load_business_units() -> list[BusinessUnit]:
    """Load every business unit from ``workspace/business/*/business.yaml``."""
    units: list[BusinessUnit] = []
    if not BUSINESS_DIR.exists():
        return units
    for unit_dir in sorted(BUSINESS_DIR.iterdir()):
        yaml_path = unit_dir / "business.yaml"
        if not yaml_path.is_file():
            continue
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        units.append(BusinessUnit(slug=unit_dir.name, **data))
    return units


def get_business_unit(slug: str) -> BusinessUnit | None:
    """Load a single business unit by its slug, or ``None`` if it doesn't exist."""
    yaml_path = BUSINESS_DIR / slug / "business.yaml"
    if not yaml_path.is_file():
        return None
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return BusinessUnit(slug=slug, **data)


def _to_card(unit: BusinessUnit) -> BusinessUnitCard:
    """Reduce a full BusinessUnit into the summary shown on a dashboard card."""
    return BusinessUnitCard(
        slug=unit.slug,
        name=unit.name,
        status=unit.status,
        health=unit.health,
        active_missions=len(unit.missions),
        next_decision=unit.next_decision,
    )


def get_dashboard_summary() -> DashboardSummary:
    """Build the aggregated payload the dashboard needs in a single call."""
    units = load_business_units()
    return DashboardSummary(
        business_unit_count=len(units),
        event_count=count_events(),
        business_units=[_to_card(u) for u in units],
        recent_events=get_events(limit=10),
    )
