"""Art. 17 DSGVO: die EINZEL-Anonymisierung (``POST .../users/{id}/anonymize``)
darf keinen Klarnamen im Aenderungsprotokoll stehen lassen.

Warum diese Datei existiert
===========================
Der Mandanten-Pfad (``lifecycle_service.anonymize_tenant``) leert seit dem
Release-Review 1.18.1 die Freitext-Notizen des Protokolls. Der ungleich
haeufiger benutzte Weg ist aber der Einzel-Pfad: eine ausgeschiedene
Mitarbeiterin macht ihr Recht auf Loeschung geltend. Er scrubbte Name, E-Mail,
Lichtbild, 2FA-Geheimnis, Abteilung und die Vertragsnotiz — und liess dieselben
Identifikatoren im Protokoll stehen.

Die drei Wege, auf denen der Klarname dort landet (alle im Repo belegt):

1. ``auth.py:528`` — bei JEDEM Selbstbedienungs-E-Mail-Wechsel:
   ``old_note = "E-Mail geändert: <alt> → <neu>"``. Zeile: ``user_id`` = sie.
2. ``reports.py`` (10 Stellen) — ``new_note = "… gelesen von Admin:
   {current_user.username}"``. War sie selbst Admin, steht ihr Benutzername auf
   den Zeilen ANDERER Beschaeftigter (``user_id`` = der andere).
3. ``journal.py:65`` — ``new_note = "Monatsjournal … von {user.username} …
   gelesen von Admin: {current_user.username}"``. Hier ist ``user_id`` der
   ADMIN, der Benutzername der BETROFFENEN steht im Text. Diese Zeile trifft
   weder ein ``user_id``- noch ein ``changed_by``-Filter — sie ist der Grund,
   warum der Scrub ueber den Inhalt gehen muss und nicht ueber die Zuordnung
   allein.

Dazu die Art.-9-Spur: ``absences.delete_absence`` schreibt
``old_note = "absence:sick:8.0h"``. Der Anonymisierungslauf loescht die
Abwesenheiten selbst — die Gesundheitsangabe ueberlebte ihn im Protokoll.

#121: ``old_note``/``new_note`` gehen in den ``row_hash`` ein. Jede Aenderung
muss ueber die Objektschicht laufen und den Hash neu berechnen, sonst meldet
``GET /api/admin/audit/verify-integrity`` danach legitime Zeilen als
manipuliert.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core import audit_integrity
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import TimeEntryAuditLog, User, UserRole
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

NAME = "maria.schulz"
MAIL = "maria.schulz@praxis.invalid"


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _deactivated_user(db, name=NAME, email=MAIL):
    """Kein ``deactivated_at`` → Legacy-Zweig, keine 14-Tage-Sperrfrist
    (Muster aus ``test_anonymize_scrubs_wh_note.py``)."""
    u = User(
        username=name, email=email, password_hash="x", first_name="Maria",
        last_name="Schulz", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=False,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _log(db, **kw):
    row = TimeEntryAuditLog(tenant_id=DEFAULT_TENANT_ID, time_entry_id=None, **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _pseudonym(user_id) -> str:
    """Genau der Wert, den ``anonymize_user`` in ``users.username`` schreibt."""
    return f"deleted_{str(user_id)[:8]}"


def _reload(db, row_id):
    db.expire_all()
    return db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.id == row_id).one()


class TestEigeneZeilen:
    """Zeilen, die ueber die Betroffene gefuehrt werden (``user_id`` = sie)."""

    def test_mailwechsel_notiz_ist_weg(self, admin_client, db):
        u = _deactivated_user(db)
        row = _log(db, user_id=u.id, changed_by=u.id, action="update",
                   source="self_service",
                   old_note=f"E-Mail geändert: {MAIL} → neu@praxis.invalid")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        assert _reload(db, row.id).old_note is None

    def test_gesundheitsspur_ist_weg(self, admin_client, db):
        """Art. 9: der Lauf loescht die Abwesenheiten — ihre Typangabe darf
        nicht im Protokoll ueberleben."""
        u = _deactivated_user(db)
        row = _log(db, user_id=u.id, changed_by=u.id, action="delete",
                   source="dsgvo", old_note="absence:sick:8.0h")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        assert _reload(db, row.id).old_note is None

    def test_zeile_und_struktur_bleiben(self, admin_client, db):
        """Die Zeile selbst belegt, wer wann was an einer Zeitaufzeichnung
        geaendert hat (§16) — nur die Prosa geht."""
        u = _deactivated_user(db)
        row = _log(db, user_id=u.id, changed_by=u.id, action="update",
                   source="manual", old_date=date(2026, 3, 2),
                   new_date=date(2026, 3, 2), new_break_minutes=30,
                   old_note="Fahrt zu Frau Meier", new_note="korrigiert")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        after = _reload(db, row.id)
        assert after.action == "update"
        assert after.old_date == date(2026, 3, 2)
        assert after.new_break_minutes == 30
        assert after.old_note is None and after.new_note is None


class TestFremdeZeilenMitIhremNamen:
    """Zeilen ANDERER Beschaeftigter, in deren Text ihr Name steht. Hier darf
    NICHT die ganze Notiz fallen — das waere die §16-Prosa der anderen."""

    def test_name_als_handelnde_adminin_wird_ersetzt(self, admin_client, db, test_user):
        u = _deactivated_user(db)
        row = _log(db, user_id=test_user.id, changed_by=u.id,
                   action="health_data_read", source="dsgvo",
                   new_note=f"Monatsreport 2026-03 (inkl. Krankheitsstunden) gelesen von Admin: {NAME}")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        after = _reload(db, row.id)
        assert NAME not in (after.new_note or "")
        assert _pseudonym(u.id) in after.new_note
        assert after.new_note.startswith("Monatsreport 2026-03 (inkl. Krankheitsstunden)"), (
            "die Aussage der Zeile muss erhalten bleiben"
        )

    def test_name_als_betroffene_in_fremder_zeile_wird_ersetzt(self, admin_client, db, test_admin):
        """Der ``journal.py``-Fall: die Zeile laeuft auf den ADMIN (``user_id``
        UND ``changed_by``), ihr Benutzername steht nur im Text. Ein Scrub, der
        allein ueber die Zuordnung geht, sieht diese Zeile nie."""
        u = _deactivated_user(db)
        row = _log(db, user_id=test_admin.id, changed_by=test_admin.id,
                   action="health_data_read", source="dsgvo",
                   new_note=(f"Monatsjournal 2026-03 von {NAME} (inkl. Krankheitsdaten) "
                             f"gelesen von Admin: {test_admin.username}"))

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        after = _reload(db, row.id)
        assert NAME not in after.new_note
        assert _pseudonym(u.id) in after.new_note
        assert test_admin.username in after.new_note, "der handelnde Admin bleibt nachvollziehbar"

    def test_mailadresse_in_fremder_zeile_wird_ersetzt(self, admin_client, db, test_admin):
        u = _deactivated_user(db)
        row = _log(db, user_id=test_admin.id, changed_by=test_admin.id,
                   action="update", source="manual",
                   new_note=f"Rueckfrage an {MAIL} gestellt")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        after = _reload(db, row.id)
        assert MAIL not in after.new_note
        assert after.new_note.startswith("Rueckfrage an ")

    def test_fremde_notiz_ohne_ihren_namen_bleibt_unveraendert(self, admin_client, db, test_user):
        """Kein Kollateralschaden: die Notiz eines anderen Beschaeftigten, in der
        sie nicht vorkommt, bleibt woertlich stehen."""
        u = _deactivated_user(db)
        row = _log(db, user_id=test_user.id, changed_by=test_user.id,
                   action="update", source="manual",
                   old_note="Notiz eines anderen Mitarbeitenden",
                   new_note="Notiz eines anderen Mitarbeitenden (neu)")

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        after = _reload(db, row.id)
        assert after.old_note == "Notiz eines anderen Mitarbeitenden"
        assert after.new_note == "Notiz eines anderen Mitarbeitenden (neu)"


class TestManipulationsschutz:
    """#121: der Lauf darf keine Zeile als 'tampered' zuruecklassen."""

    def test_alle_zeilen_verifizieren_nach_dem_lauf(self, admin_client, db, test_user):
        u = _deactivated_user(db)
        eigene = _log(db, user_id=u.id, changed_by=u.id, action="update",
                      source="self_service",
                      old_note=f"E-Mail geändert: {MAIL} → neu@praxis.invalid")
        fremde = _log(db, user_id=test_user.id, changed_by=u.id,
                      action="health_data_read", source="dsgvo",
                      new_note=f"Jahresreport 2026 gelesen von Admin: {NAME}")
        unbeteiligt = _log(db, user_id=test_user.id, changed_by=test_user.id,
                           action="create", source="manual",
                           old_date=date(2026, 3, 2), new_break_minutes=30)
        hash_vorher = unbeteiligt.row_hash
        assert hash_vorher, "Vorrichtung: die Kontrollzeile traegt einen Hash"

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        db.expire_all()
        rows = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID).all()
        schal = [r.id for r in rows if not audit_integrity.verify_row(r)]
        assert not schal, f"row_hash nach der Anonymisierung nicht mehr gueltig: {schal}"

        assert _reload(db, eigene.id).old_note is None
        assert NAME not in (_reload(db, fremde.id).new_note or "")
        # Die unbeteiligte Zeile wurde nicht angefasst — auch ihr Hash nicht.
        assert _reload(db, unbeteiligt.id).row_hash == hash_vorher


class TestOhneProtokollNotizen:
    """Kontrolle: der Lauf bleibt fehlerfrei, wenn es nichts zu scrubben gibt."""

    def test_anonymisierung_laeuft_ohne_notizen_durch(self, admin_client, db):
        u = _deactivated_user(db)
        _log(db, user_id=u.id, changed_by=u.id, action="create", source="manual",
             old_date=date(2026, 3, 2))

        r = admin_client.post(f"/api/admin/users/{u.id}/anonymize")
        assert r.status_code == 200, r.text

        db.expire_all()
        after = db.query(User).filter(User.id == u.id).one()
        assert after.username.startswith("deleted_")
        assert after.email is None
