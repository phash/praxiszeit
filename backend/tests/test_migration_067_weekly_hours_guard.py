"""F3 (Release-Gate 1.18.0): der 067-Backfill darf die Grenzen nicht sprengen.

Migration 067 zieht ``working_hours_changes.weekly_hours`` fuer Tagesplan-
Mitarbeitende auf die Summe der fuenf Tageswerte. Bis 1.17.0 war ein Tagesplan
frei setzbar (``schemas/user.py`` begrenzt nur je Tag auf 24), es gibt also
Bestandsdaten mit Wochensummen weit ueber der Schema-Obergrenze:

* ab Ø 20 h/Tag bricht die **Migration selbst** mit ``numeric field overflow``
  ab (Zielspalte ``Numeric(4,2)``, max 99,99) — auf echtem Postgres 18
  reproduziert, die DB bleibt auf 066 stehen und das Update ist blockiert;
* schon ab > 60 h liefert ``GET /users/{id}/working-hours-changes`` danach einen
  ``ResponseValidationError`` → HTTP 500, weil das Lese-Schema ``le=60`` traegt.

Die SQL des Backfills ist Postgres-spezifisch und laeuft nicht in dieser
SQLite-Suite (der Beleg dafuer liegt im Postgres-Lauf). Was hier getestet wird,
ist die Kopplung, die still auseinanderlaufen kann: die Konstante in der
Migration MUSS die Obergrenze des Lese-Schemas sein.
"""
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.working_hours_change import (
    WorkingHoursChangeBase,
    WorkingHoursChangeResponse,
)

MIGRATION = (Path(__file__).resolve().parents[1]
             / "alembic" / "versions" / "2026_07_29_1200-067_schedule_history.py")


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig067", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _schema_upper_bound() -> float:
    for meta in WorkingHoursChangeBase.model_fields["weekly_hours"].metadata:
        if hasattr(meta, "le"):
            return meta.le
    raise AssertionError("weekly_hours traegt keine le-Grenze mehr")


def test_migration_bound_matches_read_schema():
    """Die Klemmgrenze der Migration ist die Obergrenze des Lese-Schemas."""
    assert _load_migration()._MAX_WEEKLY_HOURS == _schema_upper_bound()


def test_backfill_sum_is_bounded_in_sql():
    """Der Backfill vergleicht die Wochensumme gegen die Grenze — ohne diesen
    Vergleich kehrt der Overflow zurueck."""
    src = MIGRATION.read_text(encoding="utf-8")
    assert "{_WEEK_SUM} <= {_MAX_WEEKLY_HOURS}" in src, (
        "Der Backfill klemmt die Wochensumme nicht mehr")
    assert "WARNUNG (Migration 067)" in src, (
        "Die Guard-Abfrage nennt betroffene Datensaetze nicht mehr beim Namen")


def test_read_schema_rejects_oversized_weekly_hours():
    """Beleg fuer die Folge eines ungeklammerten Backfills: eine Zeile mit 75 h
    laesst sich nicht mehr ausliefern (HTTP 500 statt Stundenverlauf)."""
    with pytest.raises(ValidationError):
        WorkingHoursChangeResponse.model_validate({
            "id": "00000000-0000-0000-0000-000000000001",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "effective_from": "2026-03-15",
            "weekly_hours": 75.0,
            "use_daily_schedule": True,
            "created_at": "2026-03-15T00:00:00Z",
        })
