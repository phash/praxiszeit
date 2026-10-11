"""Spec 9.7/P13 (19.1 Nr. 4): Löschen einer Verlaufszeile — symmetrische
Rückrechnung, Verkürzungsschutz, Rücksetzung statt Löschen."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models import (
    AbsenceType, TimeEntry, TimeEntryAuditLog, User, UserRole, WorkingHoursChange, YearCarryover,
)
from app.models.tenant import Tenant
from app.routers.admin_users import _sync_user_from_change
from app.services import calculation_service, reclamp_audit, wh_change_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, MONDAYS, RETRO_REASON, TODAY, absence, add_row, admin_client, entry, freeze, reclamp_logs,
    set_grace, t, with_pauses,
)
from tests.work_blocks_fixtures import block_week

LONGER_PAUSED = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], tue=[("08:00", "12:00")],
                                       thu=[("08:00", "12:00")]), mon=60)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _create(client, user, body):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _delete_preview(client, user, change_id):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes/{change_id}/delete-preview", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _delete(client, user, change_id, body=None):
    return client.request("DELETE", f"/api/admin/users/{user.id}/working-hours-changes/{change_id}", json=body)


def _rows(db, user):
    db.expire_all()
    return [(r.effective_from, float(r.weekly_hours)) for r in db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id).order_by(WorkingHoursChange.effective_from)]


class TestReset:
    def test_deleting_a_target_drop_is_a_shortening_with_reset_body(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["shortening_reasons"], body["earliest_lossless_date"]) == (
            True, ["saldo"], "2026-10-08")
        assert body["reset_body"] == {
            "effective_from": "2026-10-08", "reset_of_change_id": change["id"], "use_daily_schedule": False,
            "weekly_hours": 40.0, "work_days_per_week": 5, "remove_legacy_window": True}

    def test_reset_body_creates_a_new_row_and_keeps_the_old_one(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        created = _create(client, test_user, reset)
        assert created["adjusted_time_entries"] == 0
        assert _rows(db, test_user) == [(date(2026, 8, 31), 40.0), (date(2026, 9, 1), 30.0), (date(2026, 10, 8), 40.0)]
        notes = [s.new_note for s in reclamp_logs(db, test_user, summary=True)]
        assert any(" · Rücksetzung der Änderung ab 01.09.2026 · " in n for n in notes)
        # Spec 17.5: Dashboard-Hinweis mit Rücksetzungstext. Nach Art statt nach
        # Position — SQLite stempelt beide Sammelzeilen in derselben Sekunde.
        [notice] = [n for n in reclamp_audit.schedule_change_notices(db, test_user) if n["kind"] == "reset"]
        assert notice["text"] == (
            "Die Arbeitszeit-Änderung ab 01.09.2026 wurde ab 08.10.2026 auf den vorherigen Stand "
            "zurückgesetzt (neu: 40,0 h/Woche (gleichmäßig, 5 Tage)).")

    def test_reset_body_does_not_reclamp_the_past(self, client, db, test_user):
        """Spec 17.5/P13: die Rücksetzung kappt die Vergangenheit NICHT neu. Der
        Eintrag hat durch die Änderung 15 Min gewonnen (18:15 → 18:30); ein echtes
        Löschen nähme sie ihm wieder, die Rücksetzung ab heute lässt ihn stehen."""
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        past = entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 30))
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})

        def state():
            db.expire_all()
            e = db.query(TimeEntry).filter(TimeEntry.id == past.id).one()
            return (e.date, e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes,
                    e.clamp_grace_minutes)

        before = state()
        assert before[2] == t(18, 30), "Vorbedingung: die Änderung hat den Eintrag verlängert"
        rows_before = [r[0] for r in _rows(db, test_user)]
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        assert reset == {"effective_from": "2026-10-08", "reset_of_change_id": change["id"], "blocks": ANNA_WEEK}
        created = _create(client, test_user, reset)
        assert created["adjusted_time_entries"] == 0
        assert state() == before
        assert [r[0] for r in _rows(db, test_user)] == rows_before + [date(2026, 10, 8)], \
            "die zurückgesetzte Zeile ab 01.09. bleibt bestehen"

    def test_changed_reset_body_is_409(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json={**reset, "weekly_hours": 39})
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."

    def test_reset_body_with_blocks_is_accepted_after_track_hours_went_off(self, client, db, test_user):
        """Spec 17.2 / P24: die Rücksetzung trägt die Blöcke der Vorgängerzeile. Wurde
        die Person inzwischen auf track_hours=false gestellt (leitend, #191), nimmt
        der Anlege-Endpunkt den unveränderten reset_body trotzdem an — Blöcke sind
        dort zulässig („ohne Wirkung", 11.2), die Zeile behält sie."""
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        shorter = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], tue=[("08:00", "12:00")],
                             thu=[("08:00", "12:00")])
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": shorter})
        reset = _delete_preview(client, test_user, change["id"])["reset_body"]
        assert reset == {"effective_from": "2026-10-08", "reset_of_change_id": change["id"], "blocks": ANNA_WEEK}
        test_user.track_hours = False
        db.commit()
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json=reset)
        assert resp.status_code == 201, resp.text
        assert resp.json()["blocks"] == ANNA_WEEK
        db.expire_all()
        last = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id, WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID,
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        assert (last.effective_from, last.blocks) == (date(2026, 10, 8), ANNA_WEEK)

    def test_no_reset_body_when_deleting_does_not_shorten(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45, **RETRO_REASON})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["reset_body"]) == (False, None)

    def test_no_reset_body_when_p25_applies(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        _create(client, test_user, {"effective_from": "2026-10-08", "weekly_hours": 35})
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["reset_body"], body["earliest_lossless_date"]) == (True, None, None)
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400
        assert resp.json()["detail"].endswith(
            "– oder abbrechen: Die Änderung liegt vollständig vor der Änderung ab 08.10.2026; "
            "nur rückwirkend mit Begründung oder abbrechen.")


class TestRetroactiveDelete:
    def test_without_reason_is_400_with_reset_hint(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert detail.startswith("Das Löschen verkürzt rückwirkend (Überstundenkonto −")
        assert detail.endswith("– oder ab dem 08.10.2026 auf den vorherigen Stand zurücksetzen.")
        assert len(_rows(db, test_user)) == 2

    def test_with_reason_deletes_and_answers_204_without_adjustments(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        assert _delete(client, test_user, change["id"], RETRO_REASON).status_code == 204
        assert _rows(db, test_user) == [(date(2026, 8, 31), 40.0)]
        [summary] = [s for s in reclamp_logs(db, test_user, summary=True) if " gelöscht: " in s.new_note]
        assert summary.new_note.startswith("Arbeitszeit-Änderung ab 01.09.2026 gelöscht: 0 Einträge neu berechnet")
        assert " · Verkürzung · Grund: [Erfassungsfehler korrigiert] " in summary.new_note

    def test_with_reason_and_an_adjusted_absence_answers_200(self, client, db, test_user):
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], RETRO_REASON)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"adjusted_absences": 1, "adjusted_time_entries": 0, "skipped_time_entries": 0,
                               "warning": None}

    def test_loss_in_a_closed_year_is_400(self, client, db, test_user):
        test_user.first_work_day = date(2025, 1, 1)
        db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        change = _create(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], RETRO_REASON)
        assert (resp.status_code, resp.json()["detail"]) == (400, wh_change_service.closed_year_detail([2025]))

    def test_earliest_row_stays_locked(self, client, db, test_user):
        _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        baseline = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).order_by(
            WorkingHoursChange.effective_from).first()
        body = _delete_preview(client, test_user, baseline.id)
        assert body["blocked_reason"].startswith("Dies ist die früheste erfasste Stundenänderung")
        assert _delete(client, test_user, baseline.id).status_code == 400


class TestFutureDelete:
    def test_future_row_without_entries_writes_exactly_one_summary(self, client, db, test_user, test_admin):
        """Spec 17.5/P20 (Review Task 11): auch das Löschen einer zukunftsdatierten
        Zeile ohne Einträge und Abwesenheiten schreibt genau eine Sammelzeile mit
        ``changed_by`` — wie das Anlegen (``test_reclamp.py``). Das Protokoll hängt
        nicht am Wirkungsdatum (anders als der Spiegel)."""
        change = _create(client, test_user, {"effective_from": "2026-11-02", "weekly_hours": 25})
        assert _delete(client, test_user, change["id"]).status_code == 204
        [summary] = [s for s in reclamp_logs(db, test_user, summary=True) if " gelöscht: " in s.new_note]
        assert summary.changed_by == test_admin.id
        assert summary.new_note == (
            "Arbeitszeit-Änderung ab 02.11.2026 gelöscht: 0 Einträge neu berechnet, Δ +0 Min, Saldo Δ +0 Min "
            "· Puffer 15 Min · Vertrag: 25,0 h/Woche (gleichmäßig, 5 Tage) → 40,0 h/Woche (gleichmäßig, 5 Tage)")
        assert reclamp_logs(db, test_user, summary=False) == []


class TestDeletePreviewCriteria:
    """Spec 17.5: ``delete-preview`` inkl. Kriterien (a)–(c), bezogen auf den
    Wechsel zum Vorgänger-Snapshot; die DELETE-400 nennt dieselben Kriterien
    (11.4). Ein vertauschter alter/neuer Snapshot im Lösch-Pfad fiele hier auf."""

    def test_entry_losing_credit_is_criterion_a(self, client, db, test_user):
        """Die Änderung verlängert Montag 18:00 → 19:00 (Pause hält das Tagessoll);
        der Eintrag hat dadurch 15 Min gewonnen. Das Löschen nimmt sie ihm wieder:
        (a) und — ohne Soll-Ausgleich — (b)."""
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        e = entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 30))
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
        rows_before = _rows(db, test_user)
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["shortening_reasons"], body["lost_credited_hours"],
                body["saldo_delta_hours"], body["earliest_lossless_date"]) == (
            True, ["entries", "saldo"], 0.25, -0.25, "2026-10-08")
        assert [(c["old_end"], c["new_end"]) for c in body["time_entry_changes"]] == [("18:30:00", "18:15:00")]
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert detail.startswith("Das Löschen verkürzt rückwirkend (1 Eintrag verliert angerechnete Zeit; "
                                 "Überstundenkonto −0:15 h): ")
        assert detail.endswith("– oder ab dem 08.10.2026 auf den vorherigen Stand zurücksetzen.")
        db.expire_all()
        assert (_rows(db, test_user), db.get(TimeEntry, e.id).end_time) == (rows_before, t(18, 30)), \
            "die 400 rollt Löschen und Neukappung zurück"

    def test_absence_credit_dropping_is_criterion_c(self, client, db, test_user):
        """Misch-Tag Krank + Arbeit 08–13 bei Tagessoll 8 h (Puffer 0). Die Änderung
        (Montag 08–12 + 14–18, Soll gleich) kappt die Arbeit auf 4 h, F1 hebt die
        Gutschrift 3 → 4 h. Das Löschen gibt der Arbeit die Stunde zurück und senkt
        die Gutschrift 4 → 3 h bei unverändertem Tagessoll: nur (c), Saldo 0."""
        set_grace(db, 0)
        add_row(db, test_user, date(2026, 3, 1), week=block_week(mon=[("08:00", "13:00"), ("15:00", "18:00")]))
        sick = absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 3.0)
        entry(db, test_user, MONDAYS[1], t(8), t(13), grace=0)
        change = _create(client, test_user, {
            "effective_from": "2026-09-01",
            "blocks": block_week(mon=[("08:00", "12:00"), ("14:00", "18:00")]), **RETRO_REASON})
        db.refresh(sick)
        assert float(sick.hours) == 4.0, "Vorbedingung: F1 hat die Gutschrift beim Anlegen angehoben"
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["shortening_reasons"], body["saldo_delta_hours"]) == (
            True, ["absence_credit"], 0.0)
        assert [(r["date"], r["old_hours"], r["new_hours"]) for r in body["absence_credit_reductions"]] == [
            (MONDAYS[1].isoformat(), 4.0, 3.0)]
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Das Löschen verkürzt rückwirkend (1 Abwesenheits-Gutschrift sinkt): ")
        db.refresh(sick)
        assert float(sick.hours) == 4.0, "die 400 rollt die Rückrechnung zurück"

    def test_open_entry_today_moves_the_reset_to_tomorrow(self, client, db, test_user):
        """P1: die Änderung verlängert Donnerstag (heute) auf 08–16; die Person ist
        seit 08:00 eingestempelt. Das Löschen kürzte ihre Hülle für jedes Ende nach
        12:15 → (a) über den offenen Eintrag, verlustfrei erst ab morgen — auch die
        Rücksetzung."""
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        longer_thu = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                                thu=[("08:00", "16:00")])
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": longer_thu, **RETRO_REASON})
        open_today = entry(db, test_user, TODAY, t(8), None)
        body = _delete_preview(client, test_user, change["id"])
        assert (body["is_shortening"], body["shortening_reasons"], body["earliest_lossless_date"]) == (
            True, ["entries"], "2026-10-09")
        assert body["reset_body"] == {"effective_from": "2026-10-09", "reset_of_change_id": change["id"],
                                      "blocks": ANNA_WEEK}
        resp = _delete(client, test_user, change["id"])
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Das Löschen verkürzt rückwirkend (1 Eintrag verliert angerechnete Zeit): ")
        assert resp.json()["detail"].endswith("– oder ab dem 09.10.2026 auf den vorherigen Stand zurücksetzen.")
        # Die Rücksetzung ab morgen verkürzt nichts mehr — ohne Grund speicherbar,
        # der offene Eintrag bleibt offen.
        created = _create(client, test_user, body["reset_body"])
        assert created["adjusted_time_entries"] == 0
        db.expire_all()
        assert db.get(TimeEntry, open_today.id).end_time is None


class TestDeleteBodyValidation:
    """Abweichung 4 (Task 11): der DELETE-Body wird untypisiert angenommen und mit
    derselben Regel und demselben deutschen Text geprüft wie der Anlege-Body —
    ein typisierter Parameter brächte FastAPIs englische Listen-422 zurück."""

    def test_short_reason_text_is_a_german_422(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], {**RETRO_REASON, "retroactive_reason_text": "kurz"})
        assert (resp.status_code, resp.json()["detail"]) == (422, "Die Begründung muss mindestens 10 Zeichen lang sein.")
        assert len(_rows(db, test_user)) == 2

    def test_non_object_body_is_a_422_with_a_text(self, client, db, test_user):
        change = _create(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        resp = _delete(client, test_user, change["id"], "x")
        assert resp.status_code == 422, resp.text
        assert isinstance(resp.json()["detail"], str) and resp.json()["detail"]
        assert len(_rows(db, test_user)) == 2


class TestDeletePreviewWritesNothing:
    """Spec 9.3/10.3: die Lösch-Vorschau rollt immer zurück und protokolliert
    nie — weder Verlaufszeilen noch Einträge, Abwesenheiten oder Protokoll."""

    def test_rows_entries_and_log_unchanged(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 30))
        sick = absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 7.0)
        change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
        db.expire_all()
        rows_before = _rows(db, test_user)
        log_before = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).count()
        entries_before = sorted((e.start_time, e.end_time, e.uncredited_minutes)
                                for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id))
        body = _delete_preview(client, test_user, change["id"])
        assert body["affected_time_entries"] == 1
        db.expire_all()
        assert _rows(db, test_user) == rows_before
        assert db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).count() == log_before
        assert sorted((e.start_time, e.end_time, e.uncredited_minutes)
                      for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id)) == entries_before
        db.refresh(sick)
        assert float(sick.hours) == 7.0

    @staticmethod
    def _foreign_rows(db, user) -> dict:
        """Zeile einer Kollegin im selben Mandanten und Zeile eines fremden
        Mandanten — beide unter dem Pfad-User nicht auffindbar."""
        colleague = User(username="kollegin", email="kollegin@example.com", password_hash="x",
                         first_name="K", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0,
                         vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=user.tenant_id)
        other_tenant_id = uuid.UUID("00000000-0000-0000-0000-0000000000fe")
        db.add(Tenant(id=other_tenant_id, name="Fremd", slug="fremd", is_active=True, mode="single"))
        stranger = User(username="fremd", email="fremd@example.com", password_hash="x",
                        first_name="F", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0,
                        vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=other_tenant_id)
        db.add_all([colleague, stranger])
        db.commit()
        colleague_row = add_row(db, colleague, date(2026, 9, 1), weekly_hours=30)
        stranger_row = WorkingHoursChange(user_id=stranger.id, tenant_id=other_tenant_id,
                                          effective_from=date(2026, 9, 1), weekly_hours=30,
                                          use_daily_schedule=False, work_days_per_week=5)
        db.add(stranger_row)
        db.commit()
        db.refresh(stranger_row)
        return {"kollegin": colleague_row.id, "fremder-mandant": stranger_row.id}

    @pytest.mark.parametrize("target", ["kollegin", "fremder-mandant", "unbekannt"])
    @pytest.mark.parametrize("method", ["preview", "delete"])
    def test_foreign_or_unknown_change_is_404(self, client, db, test_user, method, target):
        """F-026 (Review Task 11): ``_change_in_tenant`` filtert Person UND
        Mandant. Ohne den Personenfilter löschte DELETE unter dem Pfad-User die
        Zeile einer Kollegin und kappte gegen den falschen Snapshot neu."""
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
        foreign = self._foreign_rows(db, test_user)
        change_id = foreign.get(target, uuid.uuid4())
        if method == "preview":
            resp = client.post(
                f"/api/admin/users/{test_user.id}/working-hours-changes/{change_id}/delete-preview", json={})
        else:
            resp = _delete(client, test_user, change_id, RETRO_REASON)
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Stundenänderung nicht gefunden"
        db.expire_all()
        assert db.query(WorkingHoursChange).filter(WorkingHoursChange.id.in_(list(foreign.values()))).count() == 2
        assert _rows(db, test_user) == [(date(2026, 1, 1), 40.0)]
        assert db.query(TimeEntryAuditLog).count() == 0


def test_create_then_delete_restores_every_entry(client, db, test_user):
    """Spec 17.5 Reversibilität: anlegen + löschen → alle Einträge byte-gleich."""
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    for d in MONDAYS[1:]:
        entry(db, test_user, d, t(8), t(12))
    entry(db, test_user, MONDAYS[1], t(15), t(18, 15))
    entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 30))
    entry(db, test_user, MONDAYS[4], t(15), t(18))

    def snapshot():
        db.expire_all()
        return sorted((str(e.id), e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes)
                      for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id))

    before = snapshot()
    change = _create(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
    assert change["adjusted_time_entries"] == 1
    assert snapshot() != before
    resp = _delete(client, test_user, change["id"], RETRO_REASON)
    assert resp.status_code == 200, resp.text
    assert snapshot() == before
    db.expire_all()
    assert {e.clamp_grace_minutes for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id)} == {15}
    [row] = [r for r in reclamp_logs(db, test_user, summary=False) if "Löschung" in r.new_note]
    assert row.new_note.endswith("— Löschung der Arbeitszeit-Änderung ab 01.09.2026 · Grund: "
                                 f"[Erfassungsfehler korrigiert] {RETRO_REASON['retroactive_reason_text']}")


# ── Lückenzeile beim Löschen (Nachtrag Review Task 10) ───────────────────────


def _carryover(db, user, year):
    db.add(YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, year=year, overtime_hours=0,
                         vacation_days=0, source="manual"))
    db.commit()


def _mmk_history(db, user):
    """Realfall MMK (Prod-Kopie): älteste Zeile 12.01., kein ``first_work_day``,
    Übertrag 2026 — das Konto beginnt am 01.01.; die User-Zeile spiegelt die
    Zeile vom 01.07. (7/0/7/0/6), an ihr hängen die Tage 01.–11.01. Gelöscht
    wird die Juli-Zeile."""
    _carryover(db, user, 2026)
    add_row(db, user, date(2026, 1, 12), weekly_hours=40)
    july = add_row(db, user, date(2026, 7, 1), day_hours=(7, 0, 7, 0, 6))
    _sync_user_from_change(user, july)
    db.commit()
    return july


def _september_history(db, user):
    """Zwei Zeilen im September, der Spiegel steht auf 30 h; das Konto beginnt
    am 01.01. (Monatserster des ältesten Eintrags, der Jahressaldo am 01.01.)."""
    add_row(db, user, date(2026, 9, 7), weekly_hours=40)
    later = add_row(db, user, date(2026, 9, 15), weekly_hours=30)
    _sync_user_from_change(user, later)
    db.commit()
    return later


def _old_vacation_history(db, user):
    """Ein Urlaubstag am Freitag, 22.08.2025, vor jeder Verlaufszeile; der
    Spiegel steht auf einem Plan ohne Freitag. Fiele er nach dem Löschen auf
    40 h zurück, zählte der Freitag wieder als Verbrauch."""
    add_row(db, user, date(2026, 9, 7), weekly_hours=40)
    later = add_row(db, user, date(2026, 9, 15), day_hours=(10, 10, 10, 10, 0))
    _sync_user_from_change(user, later)
    absence(db, user, date(2025, 8, 22), AbsenceType.VACATION, 8.0)
    db.commit()
    return later


class TestUncoveredPastIsFrozenOnDelete:
    """Nachtrag Review Task 10: Tage vor der ältesten Verlaufszeile lösen über die
    User-Zeile auf, und der Spiegel nach dem Löschen verschiebt ihr Soll — ohne
    dass Lösch-Vorschau, Schutzpaket oder Protokoll es sehen. Das Löschen friert
    die Lücke deshalb wie das Anlegen ein; danach bewegt der Commit Konto und
    Jahressaldo genau um den Saldo der Lösch-Vorschau und den Urlaubsverbrauch
    außerhalb des Wirkungsbereichs gar nicht."""

    @staticmethod
    def _measures(db, user):
        db.expire_all()
        user = db.query(User).filter(User.id == user.id).one()
        cutoff = calculation_service.get_soll_cutoff_date(db, user)
        return (
            float(calculation_service.get_overtime_account(db, user, 2026, 10, cutoff_date=cutoff)),
            float(calculation_service.get_ytd_summary(db, user, 2026, cutoff_date=cutoff)["overtime"]),
            float(calculation_service.get_vacation_account(db, user, 2025)["used_days"]),
            float(calculation_service.get_vacation_account(db, user, 2026)["used_days"]),
        )

    @pytest.mark.parametrize("setup", [_mmk_history, _september_history, _old_vacation_history],
                             ids=["realfall-mmk-uebertrag", "jahressaldo-ab-0101", "urlaub-vor-dem-verlauf"])
    def test_commit_moves_only_what_the_delete_preview_shows(self, client, db, test_user, setup):
        doomed = setup(db, test_user)
        entry(db, test_user, date(2026, 9, 21), t(8), t(16))
        before = self._measures(db, test_user)
        preview = _delete_preview(client, test_user, doomed.id)
        assert preview["blocked_reason"] is None
        resp = _delete(client, test_user, doomed.id, RETRO_REASON if preview["is_shortening"] else None)
        assert resp.status_code in (200, 204), resp.text
        delta = preview["saldo_delta_hours"]
        assert self._measures(db, test_user) == pytest.approx(
            (before[0] + delta, before[1] + delta, before[2], before[3]))

    def test_gap_row_carries_the_mirrored_snapshot(self, client, db, test_user):
        """Die Lückenzeile schreibt den bisher aufgelösten Vertrag der Tage vor der
        ältesten Zeile fort (hier der Spiegel der Juli-Zeile)."""
        doomed = _mmk_history(db, test_user)
        entry(db, test_user, date(2026, 9, 21), t(8), t(16))
        resp = _delete(client, test_user, doomed.id, RETRO_REASON)
        assert resp.status_code in (200, 204), resp.text
        db.expire_all()
        rows = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == test_user.id).order_by(WorkingHoursChange.effective_from).all()
        assert [r.effective_from for r in rows] == [date(2026, 1, 1), date(2026, 1, 12)]
        frozen = rows[0]
        assert (float(frozen.weekly_hours), frozen.use_daily_schedule,
                [None if v is None else float(v) for v in (frozen.hours_monday, frozen.hours_tuesday,
                                                           frozen.hours_wednesday, frozen.hours_thursday,
                                                           frozen.hours_friday)]) == (
            20.0, True, [7.0, None, 7.0, None, 6.0])
        test_user = db.query(User).filter(User.id == test_user.id).one()
        assert float(test_user.weekly_hours) == 40.0, "Spiegel auf die jüngste verbleibende Zeile ≤ heute"

    def test_deleting_the_only_row_freezes_nothing(self, client, db, test_user):
        """Bestandsverhalten: ohne verbleibende Zeile gibt es keine Lücke davor."""
        only = add_row(db, test_user, date(2026, 9, 7), weekly_hours=40)
        entry(db, test_user, date(2026, 9, 21), t(8), t(16))
        resp = _delete(client, test_user, only.id, RETRO_REASON)
        assert resp.status_code in (200, 204), resp.text
        assert _rows(db, test_user) == []
