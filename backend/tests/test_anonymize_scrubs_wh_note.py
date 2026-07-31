"""Fund F (Abschluss-Review #431): Art.17-Anonymisierung (POST
.../users/{id}/anonymize) scrubbt gezielt personenbezogene Felder (Name,
E-Mail, sogar `department` mit der Begruendung "Org-Zuordnung ist PII") und
loescht alle Abwesenheiten — liess bisher aber die Vertragshistorie
(`working_hours_changes`) VOLLSTAENDIG unangetastet, samt ihres frei
tippbaren `note`-Textes (bis 500 Zeichen, vom Wochenstunden-Dialog angeboten
und im Verlauf wieder angezeigt, seit #431 zusaetzlich in drei
Export-Payloads).

Die Zeilen selbst MUESSEN bleiben (sie tragen das historische Soll fuer die
§16-Aufbewahrung — dieselbe Begruendung wie bei den TimeEntries). Der
Freitext hat aber keine Aufbewahrungspflicht und ist Admin-Freiprosa ueber
den anonymisierten Mitarbeitenden ("Rueckkehr nach Elternzeit", ein Klarname
in einem Nebensatz, ...) — er muss scrubben wie die anderen Felder.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole, WorkingHoursChange
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _deactivated_user(db, name):
    """Kein `deactivated_at` → Legacy-Zweig, keine 14-Tage-Sperrfrist (wie
    `test_purge_user_fk_cleanup.py`)."""
    u = User(
        username=name, email=f"{name}@x.de", password_hash="x", first_name=name,
        last_name="P", role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=False, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_anonymize_scrubs_working_hours_change_note(admin_client, db):
    u = _deactivated_user(db, "wh_note_user")
    change = WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=u.id, effective_from=date(2026, 1, 1),
        weekly_hours=20.0, note="Rückkehr nach Elternzeit, Rücksprache mit Peter Müller",
    )
    db.add(change)
    db.commit()
    change_id = change.id

    r = admin_client.post(f"/api/admin/users/{u.id}/anonymize")
    assert r.status_code == 200, r.text

    db.expire_all()
    row = db.query(WorkingHoursChange).filter(WorkingHoursChange.id == change_id).first()
    # Zeile bleibt — sie traegt das historische Soll (§16) — …
    assert row is not None
    assert row.effective_from == date(2026, 1, 1)
    assert float(row.weekly_hours) == pytest.approx(20.0)
    # … aber der Freitext ist weg.
    assert row.note is None


def test_anonymize_scrubs_every_wh_change_row_of_the_user(admin_client, db):
    """Mehrere Vertragsaenderungen ueber die Jahre — der Scrub darf nicht nur
    die juengste Zeile treffen (Bulk-UPDATE ohne LIMIT waere hier ein
    naheliegender, aber falscher erster Entwurf gewesen)."""
    u = _deactivated_user(db, "wh_note_user_multi")
    rows = [
        WorkingHoursChange(
            tenant_id=DEFAULT_TENANT_ID, user_id=u.id, effective_from=date(y, 1, 1),
            weekly_hours=20.0 + y, note=f"Notiz {y}",
        )
        for y in (2024, 2025, 2026)
    ]
    db.add_all(rows)
    db.commit()
    row_ids = [r.id for r in rows]

    assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

    db.expire_all()
    remaining = db.query(WorkingHoursChange).filter(WorkingHoursChange.id.in_(row_ids)).all()
    assert len(remaining) == 3  # keine Zeile geloescht
    assert all(r.note is None for r in remaining)


def test_anonymize_does_not_crash_on_rows_without_a_note(admin_client, db):
    """Guard: die gezielte Filterung auf `note IS NOT NULL` darf note=None-Zeilen
    weder anfassen noch zum Stolperstein fuer den Bulk-UPDATE werden."""
    u = _deactivated_user(db, "wh_no_note_user")
    change = WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=u.id, effective_from=date(2026, 1, 1),
        weekly_hours=20.0, note=None,
    )
    db.add(change)
    db.commit()
    change_id = change.id

    r = admin_client.post(f"/api/admin/users/{u.id}/anonymize")
    assert r.status_code == 200, r.text

    db.expire_all()
    row = db.query(WorkingHoursChange).filter(WorkingHoursChange.id == change_id).first()
    assert row is not None and row.note is None


def test_anonymize_does_not_touch_another_users_wh_note(admin_client, db, test_user):
    """F-026-Gegenprobe: der Scrub ist auf DIESEN Mitarbeitenden begrenzt."""
    u = _deactivated_user(db, "wh_note_user_scoped")
    other_change = WorkingHoursChange(
        tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, effective_from=date(2026, 1, 1),
        weekly_hours=30.0, note="Notiz eines anderen Mitarbeitenden",
    )
    db.add(other_change)
    db.commit()
    other_id = other_change.id

    assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

    db.expire_all()
    row = db.query(WorkingHoursChange).filter(WorkingHoursChange.id == other_id).first()
    assert row is not None and row.note == "Notiz eines anderen Mitarbeitenden"
