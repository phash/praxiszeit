"""#537 (Audit 2026-11-07, A2-1/2/3/5/8/12/13): Aenderungsprotokoll als Beweismittel.

SQLite-Teil. Was nur PostgreSQL zeigt (Trigger, entzogene Rechte,
SECURITY-DEFINER-Funktionen, ON DELETE SET NULL als Eigentuemerin), prueft
``test_076_audit_chain_pg.py``.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core import audit_integrity
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    SecurityEvent, SystemSetting, TimeEntry, TimeEntryAuditLog, User, UserRole, YearCarryover,
)
from app.models.error_log import ErrorLog
from app.routers.admin_helpers import _create_audit_log
from app.services import audit_chain_service
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


def _entry(db, user, **kw):
    fields = dict(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=date(2026, 3, 2),
        start_time=time(7, 45), end_time=time(16, 15), break_minutes=30,
        raw_start_time=time(6, 0), raw_end_time=time(18, 0), uncredited_minutes=210,
        note="Notdienst",
    )
    fields.update(kw)
    e = TimeEntry(**fields)
    db.add(e)
    db.commit()
    return e


def _audit(db, user, admin, **kw):
    fields = dict(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, changed_by=admin.id,
        action="update", source="manual",
        old_date=date(2026, 1, 6), old_start_time=time(8, 0), old_end_time=time(16, 0),
        new_date=date(2026, 1, 6), new_start_time=time(8, 0), new_end_time=time(17, 0),
        new_note="nachher",
    )
    fields.update(kw)
    row = TimeEntryAuditLog(**fields)
    db.add(row)
    db.commit()
    return row


def _set_legacy_cutoff(db, when):
    """Wie Migration 076: feste Grenze fuer Altbestand ohne Pruefsumme."""
    db.add(SystemSetting(key=audit_chain_service.LEGACY_CUTOFF_KEY, tenant_id=DEFAULT_TENANT_ID,
                         value=audit_integrity.canonical_timestamp(when)))
    db.commit()


def _make_legacy_v2(db, row):
    """Eine Zeile so zuruecksetzen, wie Migration 076 Altbestand vorfindet:
    v2-Hash ueber die Fremdschluessel, Kopien wie der Backfill."""
    row.hash_version = None
    row.entry_ref = row.time_entry_id
    row.changed_by_ref = row.changed_by
    row.change_request_ref = row.change_request_id
    row.row_hash = audit_integrity.compute_row_hash(row)
    db.commit()


# ── A2-3: Rohstempel ─────────────────────────────────────────────────────────

class TestRawStampsInAudit:
    def test_admin_delete_keeps_actual_stamps(self, admin_client, db, test_user):
        """Probe p8: 06:00–18:00, angerechnet 07:45–16:15. Nach dem Loeschen
        muss die tatsaechliche Arbeitszeit im Protokoll stehen."""
        e = _entry(db, test_user)
        eid = e.id
        db.expire_all()
        r = admin_client.delete(f"/api/admin/time-entries/{eid}")
        assert r.status_code in (200, 204), r.text
        row = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.entry_ref == eid, TimeEntryAuditLog.action == "delete",
        ).one()
        assert row.old_start_time == time(7, 45)
        assert row.old_raw_start_time == time(6, 0)
        assert row.old_raw_end_time == time(18, 0)
        assert row.old_presence_end_time == time(18, 0)
        assert row.old_uncredited_minutes == 210
        assert row.new_raw_start_time is None  # Loeschung: kein Nachher
        assert audit_integrity.verify_row(row)

    def test_update_records_before_and_after_stamps(self, db, test_user, test_admin):
        e = _entry(db, test_user)
        eid = e.id
        db.expire_all()
        e = db.query(TimeEntry).filter(TimeEntry.id == eid).one()
        old = {"date": e.date, "start_time": e.start_time, "end_time": e.end_time,
               "break_minutes": e.break_minutes, "note": e.note}
        e.raw_end_time = time(19, 0)
        e.uncredited_minutes = 270
        _create_audit_log(db, e.id, test_user.id, test_admin.id, action="update",
                          old_entry=old, new_entry=e, tenant_id=DEFAULT_TENANT_ID)
        db.commit()
        row = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.entry_ref == eid).one()
        assert (row.old_raw_end_time, row.old_uncredited_minutes) == (time(18, 0), 210)
        assert (row.new_raw_end_time, row.new_uncredited_minutes) == (time(19, 0), 270)
        assert row.new_presence_end_time == time(19, 0)

    def test_auto_closed_presence_end_is_effective_end(self, db, test_user, test_admin):
        """Das synthetische 23:59 eines automatisch geschlossenen Eintrags ist
        kein Stempel — Ende der Anwesenheit = wirksames Ende (presence_end)."""
        e = _entry(db, test_user, end_time=time(16, 15), raw_end_time=time(23, 59),
                   auto_closed=True)
        _create_audit_log(db, e.id, test_user.id, test_admin.id, action="update",
                          old_entry=e, new_entry=e, tenant_id=DEFAULT_TENANT_ID)
        db.commit()
        row = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.entry_ref == e.id).one()
        assert row.new_raw_end_time == time(23, 59)
        assert row.new_presence_end_time == time(16, 15)

    def test_rows_without_entry_untouched(self, db, test_user, test_admin):
        row = _audit(db, test_user, test_admin, action="setting_change", source="settings",
                     old_date=None, old_start_time=None, old_end_time=None,
                     new_date=None, new_start_time=None, new_end_time=None)
        assert row.new_raw_start_time is None and row.old_presence_end_time is None


# ── A2-1/A2-2: Pruefsumme v3 ────────────────────────────────────────────────

class TestHashV3:
    def test_new_rows_are_v3_with_refs_and_created_at(self, db, test_user, test_admin):
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, time_entry_id=e.id)
        assert row.hash_version == 3
        assert row.entry_ref == e.id and row.changed_by_ref == test_admin.id
        assert row.created_at is not None
        assert audit_integrity.verify_row(row)

    def test_nulled_foreign_keys_keep_hash_valid(self, db, test_user, test_admin):
        """A2-1: ON DELETE SET NULL nullt time_entry_id/changed_by — die
        Pruefsumme laeuft ueber die festen Kopien und bleibt gueltig."""
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, time_entry_id=e.id)
        row.time_entry_id = None
        row.changed_by = None
        db.commit()
        db.expire_all()
        assert audit_integrity.verify_row(db.get(TimeEntryAuditLog, row.id))

    def test_redirected_foreign_key_is_tampering(self, db, test_user, test_admin):
        row = _audit(db, test_user, test_admin)
        row.changed_by = test_user.id  # Urheber umgebogen
        db.commit()
        assert not audit_integrity.verify_row(row)

    @pytest.mark.parametrize("field,value", [
        ("created_at", datetime(2020, 1, 1, tzinfo=timezone.utc)),
        ("new_raw_end_time", time(20, 0)),
        ("new_uncredited_minutes", 5),
        ("new_end_time", time(18, 0)),
    ])
    def test_tampering_detected(self, db, test_user, test_admin, field, value):
        row = _audit(db, test_user, test_admin)
        setattr(row, field, value)
        db.commit()
        db.expire_all()
        assert not audit_integrity.verify_row(db.get(TimeEntryAuditLog, row.id))

    def test_legacy_v2_survives_entry_deletion_via_ref(self, db, test_user, test_admin):
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, time_entry_id=e.id)
        _make_legacy_v2(db, row)
        assert audit_integrity.verify_row(row)
        row.time_entry_id = None  # Loeschung NACH Migration 076
        db.commit()
        assert audit_integrity.verify_row(row)

    def test_listener_never_writes_unhashed_rows(self, db, test_user, test_admin, monkeypatch):
        """A2-2: ein Hash-Fehler wurde verschluckt und erzeugte eine Zeile mit
        row_hash NULL, die als Altbestand durchging."""
        def _boom(_row):
            raise RuntimeError("kein Schluessel")
        monkeypatch.setattr(audit_integrity, "compute_row_hash", _boom)
        db.add(TimeEntryAuditLog(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
                                 changed_by=test_admin.id, action="update", source="manual"))
        with pytest.raises(RuntimeError):
            db.commit()
        db.rollback()


# ── Pruefung, Kette, Luecken ────────────────────────────────────────────────

class TestVerifyAndChain:
    def test_create_then_delete_entry_stays_intact(self, admin_client, db, test_user):
        """A2-1, Probe p2: Anlegen + Loeschen eines Eintrags erzeugte zwei
        dauerhafte Fehlalarme."""
        e = _entry(db, test_user)
        _create_audit_log(db, e.id, test_user.id, test_user.id, action="create",
                          new_entry=e, tenant_id=DEFAULT_TENANT_ID)
        db.commit()
        assert admin_client.delete(f"/api/admin/time-entries/{e.id}").status_code in (200, 204)
        # SQLite laeuft ohne FK — die Nullung von PostgreSQL nachstellen
        for row in db.query(TimeEntryAuditLog).all():
            row.time_entry_id = None
        db.commit()
        result = admin_client.get("/api/admin/audit/verify-integrity").json()
        assert result["tampered"] == 0 and result["intact"] is True

    def test_unhashed_row_newer_than_first_hash_is_tampered(self, db, test_user, test_admin):
        _audit(db, test_user, test_admin)
        late = _audit(db, test_user, test_admin)
        late.row_hash = None
        late.hash_version = None
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["tampered"] == 1 and not result["intact"]

    def test_genuine_legacy_unhashed_row_is_not_tampered(self, db, test_user, test_admin):
        _set_legacy_cutoff(db, datetime(2026, 2, 1, tzinfo=timezone.utc))
        old = _audit(db, test_user, test_admin)
        old.row_hash = None
        old.hash_version = None
        old.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _audit(db, test_user, test_admin)
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["legacy_unhashed"] == 1 and result["intact"]

    def test_legacy_row_of_entry_deleted_before_076_reported_separately(self, db, test_user, test_admin):
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, time_entry_id=e.id)
        _make_legacy_v2(db, row)
        # vor 076 geloescht: Fremdschluessel genullt, Kopie gab es nie
        row.time_entry_id = None
        row.entry_ref = None
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["legacy_entry_deleted"] == 1
        assert result["tampered"] == 0 and result["intact"]

    def test_seal_builds_chain(self, db, test_user, test_admin):
        for _ in range(3):
            _audit(db, test_user, test_admin)
        assert audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID) == 3
        db.commit()
        seqs = sorted(r.chain_seq for r in db.query(TimeEntryAuditLog).all())
        assert seqs == [1, 2, 3]
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["sealed"] == 3 and result["intact"]
        assert audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID) == 0  # idempotent

    def test_deleted_sealed_row_is_detected(self, db, test_user, test_admin):
        rows = [_audit(db, test_user, test_admin) for _ in range(3)]
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        db.delete(rows[1])  # Zeile in der Mitte heimlich entfernt
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["missing_links"] == 1 and result["missing_seqs"] == [2]
        assert not result["intact"]

    def test_truncated_tail_is_detected(self, db, test_user, test_admin):
        rows = [_audit(db, test_user, test_admin) for _ in range(3)]
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        db.delete(rows[2])  # letztes Glied — keine Luecke dahinter
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert not result["intact"]

    def test_forged_chain_link_is_detected(self, db, test_user, test_admin):
        rows = [_audit(db, test_user, test_admin) for _ in range(2)]
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        rows[1].chain_hash = "0" * 64
        db.commit()
        assert not audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)["intact"]

    def test_legitimate_delete_leaves_marker_and_stays_intact(self, db, test_user, test_admin):
        rows = [_audit(db, test_user, test_admin) for _ in range(4)]
        n = audit_chain_service.delete_rows(
            db, [rows[1], rows[3]], tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id,
            changed_by=test_admin.id, source="dsgvo", reason="Test",
        )
        db.commit()
        assert n == 2
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == audit_chain_service.PURGE_ACTION).one()
        assert "Kettenglieder 2,4" in marker.new_note
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["missing_links"] == 0 and result["intact"], result

    def test_forged_marker_does_not_cover_gap(self, db, test_user, test_admin):
        rows = [_audit(db, test_user, test_admin) for _ in range(3)]
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        db.delete(rows[1])
        fake = _audit(db, test_user, test_admin, action=audit_chain_service.PURGE_ACTION,
                      new_note="Kettenglieder 2 entfernt")
        fake.new_note = "Kettenglieder 2 entfernt (erfunden)"  # nach dem Hashen geaendert
        db.commit()
        assert not audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)["intact"]

    def test_marker_ranges_round_trip(self):
        assert audit_chain_service._ranges([1, 2, 3, 7, 9, 10]) == "1-3,7,9-10"
        assert audit_chain_service.parse_marker_seqs("Kettenglieder 1-3,7,9-10 entfernt") == {1, 2, 3, 7, 9, 10}


# ── A2-8 / Art. 17 ──────────────────────────────────────────────────────────

class TestArt17Paths:
    def test_set_notes_rehashes_only_valid_rows(self, db, test_user, test_admin):
        good = _audit(db, test_user, test_admin, new_note="maria@x.de")
        bad = _audit(db, test_user, test_admin, new_note="x")
        bad.new_end_time = time(23, 0)  # vorher manipuliert
        db.commit()
        audit_chain_service.set_notes(db, good, None, "[anonymisiert]")
        audit_chain_service.set_notes(db, bad, None, "[anonymisiert]")
        db.commit()
        assert audit_integrity.verify_row(good)
        assert not audit_integrity.verify_row(bad)  # nicht reingewaschen

    def test_scrub_does_not_break_chain(self, db, test_user, test_admin):
        row = _audit(db, test_user, test_admin, new_note="maria@x.de")
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        audit_chain_service.set_notes(db, row, None, None)
        db.commit()
        assert audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)["intact"]

    def test_purge_user_marks_removed_links(self, admin_client, db, test_admin):
        u = User(username="weg", email="weg@x.de", password_hash="x", first_name="W",
                 last_name="P", role=UserRole.EMPLOYEE, weekly_hours=40, vacation_days=30,
                 work_days_per_week=5, is_active=False, tenant_id=DEFAULT_TENANT_ID)
        db.add(u)
        db.commit()
        _audit(db, test_admin, test_admin)
        own = _audit(db, u, u)
        authored = _audit(db, test_admin, u)
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        own_seq = own.chain_seq
        assert admin_client.delete(f"/api/admin/users/{u.id}/purge").status_code == 200
        db.expire_all()
        kept = db.get(TimeEntryAuditLog, authored.id)
        assert kept is not None and kept.changed_by != test_admin.id  # A2-8
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == audit_chain_service.PURGE_ACTION).one()
        assert own_seq in audit_chain_service.parse_marker_seqs(marker.new_note)
        result = audit_chain_service.check_tenant(db, DEFAULT_TENANT_ID, actor="t",
                                                  record_failure=False)
        assert result["intact"], result

    def test_retention_purge_writes_marker(self, db, test_user, test_admin):
        """A2-13: absence_creation-Zeilen (Loeschbeleg eines durch Abwesenheit
        ersetzten Eintrags) gehen erst 730 Tage nach dem Loeschtag — und nur
        mit Vermerk."""
        from app.services.lifecycle_service import purge_expired_vacation_audit_logs
        old = _audit(db, test_user, test_admin, source="absence_creation", action="delete")
        old.created_at = datetime.now(timezone.utc) - timedelta(days=731)
        young = _audit(db, test_user, test_admin, source="absence_creation", action="delete")
        young.created_at = datetime.now(timezone.utc) - timedelta(days=729)
        manual = _audit(db, test_user, test_admin, source="manual", action="delete")
        manual.created_at = datetime.now(timezone.utc) - timedelta(days=2000)
        for r in (old, young, manual):  # Hash nach dem Zurueckdatieren neu
            r.row_hash = audit_integrity.compute_row_hash(r)
        db.commit()
        assert purge_expired_vacation_audit_logs(db) == 1
        ids = {r.id for r in db.query(TimeEntryAuditLog).all()}
        assert old.id not in ids and young.id in ids and manual.id in ids
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == audit_chain_service.PURGE_ACTION).one()
        assert marker.source == "retention" and marker.changed_by is None
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        assert audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)["intact"]


# ── A2-5: Verwaltungsaenderungen ────────────────────────────────────────────

class TestAdminChangeAudit:
    def _rows(self, db, action):
        return db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.action == action).all()

    def test_manual_carryover_logged(self, admin_client, db, test_user):
        r = admin_client.put(f"/api/admin/users/{test_user.id}/carryovers/2027",
                             json={"overtime_hours": 40, "vacation_days": 3})
        assert r.status_code == 200, r.text
        r = admin_client.put(f"/api/admin/users/{test_user.id}/carryovers/2027",
                             json={"overtime_hours": 0, "vacation_days": 3})
        assert r.status_code == 200
        rows = sorted(self._rows(db, "carryover_set"), key=lambda r: r.created_at)
        assert len(rows) == 2
        assert rows[1].user_id == test_user.id and rows[1].source == "carryover"
        assert "Überstunden 40,00 h" in rows[1].old_note
        assert "Überstunden 0,00 h" in rows[1].new_note
        assert audit_integrity.verify_row(rows[1])

    def test_year_closing_create_and_delete_logged(self, admin_client, db, test_user, test_admin):
        r = admin_client.post("/api/admin/year-closing/2025")
        assert r.status_code == 200, r.text
        created = self._rows(db, "carryover_set")
        assert {row.user_id for row in created} >= {test_user.id}
        assert all(row.source == "year_closing" and row.old_note is None for row in created)
        r = admin_client.delete("/api/admin/year-closing/2025")
        assert r.status_code == 200, r.text
        deleted = self._rows(db, "carryover_delete")
        assert len(deleted) == len(created)
        assert all(row.new_note is None and "Übertrag 2026" in row.old_note for row in deleted)
        assert db.query(YearCarryover).count() == 0

    def test_arbzg_relevant_user_fields_logged(self, admin_client, db, test_user, test_admin):
        """A1-17: § 18 nimmt die Person aus allen ArbZG-Berichten — die
        Umstellung (wie Nachtarbeit und Beschaeftigungsfenster) braucht eine
        dauerhafte Spur mit altem/neuem Wert und handelnder Person."""
        test_user.exempt_from_arbzg = False
        test_user.is_night_worker = False
        db.commit()
        r = admin_client.put(f"/api/admin/users/{test_user.id}", json={
            "exempt_from_arbzg": True, "is_night_worker": True,
            "first_work_day": "2024-02-01", "last_work_day": "2027-12-31",
            "first_name": test_user.first_name,
        })
        assert r.status_code == 200, r.text
        rows = {row.old_note.split(":")[0]: row for row in self._rows(db, "user_field_change")}
        assert set(rows) == {"Ausgenommen nach § 18 ArbZG", "Nachtarbeitnehmer (§ 6 ArbZG)",
                             "Erster Arbeitstag", "Letzter Arbeitstag"}
        exempt = rows["Ausgenommen nach § 18 ArbZG"]
        assert exempt.old_note == "Ausgenommen nach § 18 ArbZG: nein"
        assert exempt.new_note == "Ausgenommen nach § 18 ArbZG: ja"
        assert exempt.user_id == test_user.id and exempt.changed_by == test_admin.id
        assert exempt.source == "user_admin" and exempt.time_entry_id is None
        assert rows["Erster Arbeitstag"].new_note == "Erster Arbeitstag: 01.02.2024"
        assert audit_integrity.verify_row(exempt)
        # Unveraendert zurueckgeschickt = keine weitere Zeile.
        r = admin_client.put(f"/api/admin/users/{test_user.id}",
                             json={"exempt_from_arbzg": True, "last_work_day": "2027-12-31"})
        assert r.status_code == 200, r.text
        assert len(self._rows(db, "user_field_change")) == 4

    def test_setting_change_logged(self, admin_client, db, test_admin):
        r = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "10"})
        assert r.status_code == 200, r.text
        r = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "10"})
        rows = self._rows(db, "setting_change")
        assert len(rows) == 1  # unveraendert = keine zweite Zeile
        assert rows[0].new_note == "work_window_grace_minutes = 10"
        assert rows[0].changed_by == test_admin.id

    def test_holiday_crud_logged(self, admin_client, db):
        r = admin_client.post("/api/holidays/", json={"date": "2026-06-15", "name": "Praxisjubiläum"})
        assert r.status_code == 201, r.text
        hid = r.json()["id"]
        assert admin_client.put(f"/api/holidays/{hid}", json={"name": "Jubiläum"}).status_code == 200
        assert admin_client.delete(f"/api/holidays/{hid}").status_code in (200, 204)
        rows = sorted(self._rows(db, "holiday_change"), key=lambda r: r.created_at)
        assert [(r.old_note is None, r.new_note is None) for r in rows] == [
            (True, False), (False, False), (False, True)]
        assert rows[1].new_note == "Feiertag 15.06.2026: Jubiläum"

    def test_reduced_day_logged(self, admin_client, db):
        r = admin_client.post("/api/admin/reduced-days/",
                              json={"date": "2026-02-16", "label": "Rosenmontag", "max_hours": 4})
        assert r.status_code == 201, r.text
        rows = self._rows(db, "reduced_day_change")
        assert len(rows) == 1 and "16.02.2026" in rows[0].new_note


# ── A2-12: Pruefung auf Knopfdruck, taeglicher Lauf, Meldung ────────────────

class TestIntegrityCheckRuns:
    def test_post_check_seals_and_stores_last_check(self, admin_client, db, test_user, test_admin):
        _audit(db, test_user, test_admin)
        r = admin_client.post("/api/admin/audit/verify-integrity")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intact"] and body["sealed"] == 1 and body["last_check"]["intact"]
        status = admin_client.get("/api/admin/audit/integrity-status").json()
        assert status["last_check"]["checked"] == 1

    def test_daily_check_reports_tampering(self, db, test_user, test_admin):
        row = _audit(db, test_user, test_admin)
        row.new_end_time = time(23, 0)
        db.commit()
        assert audit_chain_service.run_daily_check(db) == 1
        ev = db.query(SecurityEvent).filter(
            SecurityEvent.event == audit_chain_service.EVENT_AUDIT_INTEGRITY_FAILED).one()
        assert "1 veränderte Zeile" in ev.detail and ev.tenant_id == DEFAULT_TENANT_ID
        assert db.query(ErrorLog).filter(ErrorLog.logger == "app.audit_integrity").count() == 1
        last = audit_chain_service.read_last_check(db, DEFAULT_TENANT_ID)
        assert last["intact"] is False

    def test_daily_check_silent_when_intact(self, db, test_user, test_admin):
        _audit(db, test_user, test_admin)
        assert audit_chain_service.run_daily_check(db) == 0
        assert db.query(SecurityEvent).count() == 0
        assert db.query(SystemSetting).filter(
            SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY).count() == 1


# ── Review-Runde 2026-11-07: Kettenende, Herabstufung, Stempelreihenfolge ────

def _drop_head(db):
    db.query(SystemSetting).filter(
        SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY,
        SystemSetting.tenant_id == DEFAULT_TENANT_ID,
    ).delete()
    db.commit()


def _sealed(db, user, admin, n=3):
    rows = [_audit(db, user, admin) for _ in range(n)]
    audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
    db.commit()
    return rows


class TestChainHeadNeverRecreated:
    def test_cut_tail_and_deleted_head_stays_detected(self, db, test_user, test_admin):
        """Letztes Glied + Kettenende geloescht, danach eine neue Zeile: die
        Pruefung meldet das Kettenende — auch beim zweiten Lauf (kein Heilen)."""
        rows = _sealed(db, test_user, test_admin)
        db.delete(rows[2])
        db.commit()
        _drop_head(db)
        _audit(db, test_user, test_admin)
        for _ in range(2):
            res = audit_chain_service.check_tenant(db, DEFAULT_TENANT_ID, actor="t", record_failure=False)
            assert not res["intact"] and not res["head_ok"], res
            assert res["head_problem"] == "fehlt"
        assert db.query(SystemSetting).filter(
            SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY).count() == 0
        with pytest.raises(audit_chain_service.AuditChainBroken):
            audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)

    def test_destroyed_head_blocks_seal_and_delete(self, db, test_user, test_admin):
        rows = _sealed(db, test_user, test_admin)
        head = db.query(SystemSetting).filter(
            SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY).one()
        head.value = "kaputt"
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert not res["head_ok"] and "ungültig" in res["head_problem"]
        with pytest.raises(audit_chain_service.AuditChainBroken):
            audit_chain_service.delete_rows(
                db, [rows[0]], tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id,
                changed_by=test_admin.id, source="dsgvo", reason="Test")
        db.rollback()
        assert db.get(TimeEntryAuditLog, rows[0].id) is not None

    def test_replayed_older_head_is_detected(self, db, test_user, test_admin):
        _sealed(db, test_user, test_admin, n=2)
        old_value = db.query(SystemSetting).filter(
            SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY).one().value
        _audit(db, test_user, test_admin)
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        db.query(SystemSetting).filter(
            SystemSetting.key == audit_chain_service.HEAD_SETTING_KEY).one().value = old_value
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert not res["head_ok"] and "Glied 2" in res["head_problem"]

    def test_purge_user_is_blocked_with_hint(self, admin_client, db, test_admin):
        u = User(username="weg2", email="weg2@x.de", password_hash="x", first_name="W",
                 last_name="P", role=UserRole.EMPLOYEE, weekly_hours=40, vacation_days=30,
                 work_days_per_week=5, is_active=False, tenant_id=DEFAULT_TENANT_ID)
        db.add(u)
        db.commit()
        _audit(db, u, u)
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        _drop_head(db)
        r = admin_client.delete(f"/api/admin/users/{u.id}/purge")
        assert r.status_code == 409, r.text
        assert "Kettenende fehlt" in r.json()["detail"]
        db.expire_all()
        assert db.get(User, u.id) is not None

    def test_retention_skips_tenant_with_broken_head(self, db, test_user, test_admin):
        from app.services.lifecycle_service import purge_expired_vacation_audit_logs
        old = _audit(db, test_user, test_admin, source="absence_creation", action="delete")
        old.created_at = datetime.now(timezone.utc) - timedelta(days=731)
        old.row_hash = audit_integrity.compute_row_hash(old)
        db.commit()
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        _drop_head(db)
        assert purge_expired_vacation_audit_logs(db) == 0
        assert db.get(TimeEntryAuditLog, old.id) is not None

    def test_reanchor_documents_and_unblocks(self, admin_client, db, test_user, test_admin):
        rows = _sealed(db, test_user, test_admin)
        db.delete(rows[2])
        db.commit()
        _drop_head(db)
        r = admin_client.post("/api/admin/audit/reanchor", json={"reason": "kurz"})
        assert r.status_code == 422
        r = admin_client.post("/api/admin/audit/reanchor",
                              json={"reason": "Datensicherung vom 06.11. geprüft"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intact"] and body["head_ok"] and body["reanchored"] == 1, body
        assert body["last_check"]["head_ok"] is True
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == audit_chain_service.REANCHOR_ACTION).one()
        assert marker.chain_seq is not None and audit_integrity.verify_row(marker)
        assert "fehlt" in marker.old_note and "Datensicherung" in marker.new_note
        assert db.query(SecurityEvent).filter(
            SecurityEvent.event == "audit_chain_reanchored").count() == 1
        # Danach geht das Loeschen wieder
        assert audit_chain_service.delete_rows(
            db, [rows[0]], tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id,
            changed_by=test_admin.id, source="dsgvo", reason="Test") == 1
        # Kettenende in Ordnung → nichts neu zu setzen
        r = admin_client.post("/api/admin/audit/reanchor",
                              json={"reason": "noch einmal, ohne Befund"})
        assert r.status_code == 400


class TestNoDowngradeToLegacy:
    def test_sealed_v3_row_downgraded_to_legacy_is_tampered(self, db, test_user, test_admin):
        """Superuser: row_hash + hash_version auf NULL, created_at vor die erste
        gehashte Zeile → frueher "Altbestand", jetzt bricht das Kettenglied."""
        early = _audit(db, test_user, test_admin)
        rows = _sealed(db, test_user, test_admin, n=2)
        victim = rows[1]
        victim.row_hash = None
        victim.hash_version = None
        victim.new_note = "umgeschrieben"
        victim.created_at = early.created_at - timedelta(days=30)
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert str(victim.id) in res["tampered_ids"] and not res["intact"]

    def test_link_binds_hash_version(self):
        a = audit_integrity.compute_chain_hash("t", 1, "r", "", 3)
        assert a != audit_integrity.compute_chain_hash("t", 1, "r", "", None)


class TestLegacyChangeRequestRow:
    def test_v2_row_of_deleted_change_request_is_legacy(self, db, test_user, test_admin):
        import uuid as _uuid
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, source="change_request", time_entry_id=e.id)
        # v2-Hash ueber eine Antrags-id, die schon VOR 076 genullt wurde: der
        # Backfill fand NULL vor, die Kopie blieb leer.
        row.change_request_id = _uuid.uuid4()
        _make_legacy_v2(db, row)
        row.change_request_id = None
        row.change_request_ref = None
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert res["tampered"] == 0 and res["legacy_entry_deleted"] == 1, res

    def test_tampered_v2_row_without_cr_source_stays_tampered(self, db, test_user, test_admin):
        e = _entry(db, test_user)
        row = _audit(db, test_user, test_admin, source="manual", time_entry_id=e.id)
        _make_legacy_v2(db, row)
        row.new_note = "geaendert"
        db.commit()
        assert audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)["tampered"] == 1


class TestStampsAtConstruction:
    def test_two_rows_same_entry_one_flush_keep_intermediate_state(self, db, test_user, test_admin):
        """Zwei Protokollzeilen zum selben Eintrag in EINEM Flush: jede traegt
        den Stand, als sie gebaut wurde (nicht den Endstand)."""
        e = _entry(db, test_user)
        eid = e.id
        db.expire_all()
        e = db.query(TimeEntry).filter(TimeEntry.id == eid).one()
        snap = {"date": e.date, "start_time": e.start_time, "end_time": e.end_time,
                "break_minutes": e.break_minutes, "note": e.note}
        e.raw_end_time = time(19, 0)
        _create_audit_log(db, e.id, test_user.id, test_admin.id, action="update",
                          old_entry=snap, new_entry=e, tenant_id=DEFAULT_TENANT_ID)
        e.raw_end_time = time(20, 0)
        _create_audit_log(db, e.id, test_user.id, test_admin.id, action="update",
                          old_entry=snap, new_entry=e, tenant_id=DEFAULT_TENANT_ID)
        db.commit()
        rows = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.entry_ref == eid).all()
        pairs = sorted((r.old_raw_end_time, r.new_raw_end_time) for r in rows)
        assert pairs == [(time(18, 0), time(19, 0)), (time(19, 0), time(20, 0))]


class TestDeleteAfterConcurrentSeal:
    """Integration 2026-11-07: zwei Endlöschungen parallel. Die zweite hatte ihre
    Zeile geladen, bevor die erste versiegelte; ihr Objekt trug noch
    ``chain_seq = None``, der Vermerk nannte kein Kettenglied („Kettenglieder
    entfernt“) und die Prüfung meldete danach ein fehlendes Glied."""

    def test_marker_names_link_sealed_by_another_session(self, db, test_user, test_admin):
        from tests.conftest import TestingSessionLocal

        rows = [_audit(db, test_user, test_admin) for _ in range(3)]
        assert [r.chain_seq for r in rows] == [None, None, None]  # geladen, lose

        other = TestingSessionLocal()
        try:
            audit_chain_service.seal_chain(other, DEFAULT_TENANT_ID)
            other.commit()
        finally:
            other.close()

        audit_chain_service.delete_rows(
            db, [rows[1]], tenant_id=DEFAULT_TENANT_ID, user_id=test_admin.id,
            changed_by=test_admin.id, source="dsgvo", reason="Test",
        )
        db.commit()
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == audit_chain_service.PURGE_ACTION).one()
        assert "Kettenglieder 2 entfernt" in marker.new_note, marker.new_note
        audit_chain_service.seal_chain(db, DEFAULT_TENANT_ID)
        db.commit()
        result = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert result["missing_links"] == 0 and result["intact"], result


# ── Review-Runde 2: Altbestandsgrenze steht fest (Migration 076) ─────────────

class TestFixedLegacyCutoff:
    def test_cutoff_does_not_follow_the_oldest_hashed_row(self, db, test_user, test_admin):
        """Frueher: Grenze = MIN(created_at) der gehashten Zeilen. Fallen die
        aeltesten gehashten Zeilen weg (Aufbewahrungsfrist, Endloeschung),
        rueckte die Grenze nach hinten und eine ungehashte Zeile dazwischen
        galt als Altbestand."""
        t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        _set_legacy_cutoff(db, t0)
        hashed = _audit(db, test_user, test_admin)
        hashed.created_at = t0 + timedelta(days=10)
        hashed.row_hash = audit_integrity.compute_row_hash(hashed)
        late = _audit(db, test_user, test_admin)
        late.row_hash = None
        late.hash_version = None
        late.created_at = t0 + timedelta(days=5)
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert str(late.id) in res["tampered_ids"] and not res["intact"], res
        assert str(hashed.id) not in res["tampered_ids"]

    def test_without_recorded_cutoff_no_unhashed_row_is_legacy(self, db, test_user, test_admin):
        """Mandant ohne festgehaltene Grenze (nach 076 angelegt oder Grenze
        entfernt): eine ungehashte Zeile kann es dort nicht legitim geben."""
        hashed = _audit(db, test_user, test_admin)
        old = _audit(db, test_user, test_admin)
        old.row_hash = None
        old.hash_version = None
        old.created_at = hashed.created_at - timedelta(days=400)
        db.commit()
        res = audit_chain_service.verify_tenant(db, DEFAULT_TENANT_ID)
        assert res["legacy_unhashed"] == 0 and str(old.id) in res["tampered_ids"], res
