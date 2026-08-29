"""#450: Zwei kleine Funde aus dem Release-Review 1.18.2.

1. ``set_user_qualifications`` committete ohne Übersetzung eines
   Eindeutigkeits-Konflikts → HTTP 500 mit Traceback für einen reinen
   Bedienkonflikt (zwei Admins, zwei Browser-Tabs).
2. Die Namensfelder hatten keine Längengrenze gegen ``String(255)``-Spalten →
   ein zu langer Name bricht auf PostgreSQL beim COMMIT ab (500 statt 422).
   Die Suite läuft gegen SQLite, das varchar-Längen ignoriert — deshalb prüfen
   diese Tests am Rand (Pydantic), nicht in der Datenbank.
"""
import pytest
from pydantic import ValidationError

from app.routers.shift_planning import (
    LocationIn,
    PlanDuplicateIn,
    PlanIn,
    SlotIn,
    WorkstationIn,
)

_WS = "11111111-2222-4333-8444-555555555555"

_TOO_LONG = "x" * 256


def test_location_name_length_is_bounded():
    LocationIn(name="x" * 255)
    with pytest.raises(ValidationError):
        LocationIn(name=_TOO_LONG)


def test_workstation_name_length_is_bounded():
    WorkstationIn(name="x" * 255)
    with pytest.raises(ValidationError):
        WorkstationIn(name=_TOO_LONG)


def test_plan_name_length_is_bounded():
    PlanIn(name="x" * 255)
    with pytest.raises(ValidationError):
        PlanIn(name=_TOO_LONG)


def test_duplicate_name_length_is_bounded():
    PlanDuplicateIn(name="x" * 255)
    with pytest.raises(ValidationError):
        PlanDuplicateIn(name=_TOO_LONG)


@pytest.mark.parametrize("model", [LocationIn, WorkstationIn, PlanIn, PlanDuplicateIn])
def test_empty_name_is_rejected_at_the_edge(model):
    with pytest.raises(ValidationError):
        model(name="")


def test_qualification_conflict_becomes_409(db, default_tenant, monkeypatch):
    """Verliert ein zweiter Schreiber das Rennen auf uq_tenant_user_workstation,
    muss das ein 409 sein — kein 500 mit Traceback im Fehlerprotokoll."""
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.models import User, UserRole
    from app.routers import shift_planning as sp
    from tests.conftest import DEFAULT_TENANT_ID

    admin = User(
        username="lim_admin", email="lim_admin@t.de", password_hash="h",
        first_name="A", last_name="D", role=UserRole.ADMIN, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    target = User(
        username="lim_target", email="lim_target@t.de", password_hash="h",
        first_name="T", last_name="G", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    def _boom():
        raise IntegrityError("INSERT", {}, Exception("uq_tenant_user_workstation"))

    monkeypatch.setattr(db, "commit", _boom)

    with pytest.raises(HTTPException) as exc:
        sp.set_user_qualifications(
            target.id, sp.QualificationsIn(workstation_ids=[]), db=db, current_user=admin,
        )
    assert exc.value.status_code == 409


# ── Release-Review 1.19.0: dieselbe Klasse, aber die ZAHLENfelder ───────────
# #450 hat die Namensfelder gebunden und die Zahlen uebersehen. Beides bricht
# auf PostgreSQL erst beim COMMIT ab: ``_commit_or_conflict`` faengt nur
# IntegrityError, einen DataError-Handler gibt es nicht — also HTTP 500 statt
# 422. Live nachgestellt mit min_staff=99999 und sort_order=3000000000.


def test_min_staff_ist_nach_oben_gebunden():
    """``shift_slots.min_staff`` ist auf PostgreSQL ``smallint``."""
    SlotIn(workstation_id=_WS, weekday=0, start_time="08:00", end_time="12:00", min_staff=999)
    with pytest.raises(ValidationError):
        SlotIn(workstation_id=_WS, weekday=0, start_time="08:00", end_time="12:00",
               min_staff=99999)


def test_min_staff_bleibt_nach_unten_gebunden():
    """Der frühere Negativ-Validator ist durch ge=0 ersetzt — die Regel bleibt."""
    with pytest.raises(ValidationError):
        SlotIn(workstation_id=_WS, weekday=0, start_time="08:00", end_time="12:00",
               min_staff=-1)


@pytest.mark.parametrize("model", [LocationIn, WorkstationIn])
def test_sort_order_ist_gebunden(model):
    """``sort_order`` ist ``integer`` (2^31)."""
    model(name="ok", sort_order=100000)
    with pytest.raises(ValidationError):
        model(name="ok", sort_order=3000000000)
    with pytest.raises(ValidationError):
        model(name="ok", sort_order=-1)


def test_uebliche_werte_bleiben_erlaubt():
    """Kontrolle: die Grenzen duerfen den Normalbetrieb nicht einengen."""
    SlotIn(workstation_id=_WS, weekday=1, start_time="08:00", end_time="12:00", min_staff=3)
    LocationIn(name="Hauptstelle", sort_order=10)
    WorkstationIn(name="Tresen", sort_order=0)
