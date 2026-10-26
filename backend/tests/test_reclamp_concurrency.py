"""Spec 2026-10-08, 17.5 (PostgreSQL-only): Nebenläufigkeit der Arbeitszeit-Änderung.

Ein Schreiber, der während einer laufenden Änderung auf die Ankersperre trifft
(P5), wartet und kappt danach mit den NEUEN Blöcken — unter READ COMMITTED läse
er sonst noch den alten Snapshot und bliebe von der Neukappung unerfasst.
Parametrisiert über alle Pfade aus 17.5: clock_out, create_time_entry,
admin_update_time_entry, CR-Genehmigung (UPDATE) und der Auto-Close in
GET /clock-status. Anerkennen, Admin-Update und CR-Genehmigung parallel zu einer
Neukappung desselben Eintrags enden ohne Deadlock (Anker vor Zeile, P5/13.3).
Dazu zwei Lösch-Wettläufe (9.7, Review Task 11): paralleles DELETE derselben
Zeile → 404, DELETE parallel zu clock_out → Blöcke des Vorgängers. Dazu die
Kollision aus 17.5/9.2 Schritt 8 gegen den echten Unique-Index (Gesamtreview
PR3): übersprungen statt IntegrityError, und ein im selben Lauf frei gewordener
Beginn scheitert nicht an der Primärschlüssel-Reihenfolge der UPDATEs. Muster:
test_concurrency.py (echte Endpunkt-Funktionen, SessionLocal +
set_tenant_context).

Gegenprobe (2026-10-11, Wegwerf-PG18): ohne die Ankersperre des jeweiligen
Schreibpfads bzw. ohne das Neulesen der Zeile beim Löschen scheitern die sieben
Schreiber-Fälle am gespeicherten Ergebnis (Eintrag unter den falschen Blöcken,
zweites „gelöscht"), nicht nur an der Reihenfolge; mit Zeile-vor-Anker beim
Anerkennen, im Admin-Update bzw. im UPDATE-Zweig der CR-Genehmigung scheitern
die drei Reihenfolge-Fälle mit 40P01 — die Verschiebe-Fälle desselben Pfads
bleiben dabei grün (Review Task 13)."""
from __future__ import annotations

import os
import threading
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text, create_engine

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL")
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not APP_DB_URL or not ADMIN_DB_URL or not ADMIN_DB_URL.startswith("postgresql"):
    pytest.skip("test_reclamp_concurrency.py braucht PostgreSQL (APP_DB_URL + ADMIN_DB_URL)",
                allow_module_level=True)

import app.schemas.time_entry as time_entry_schemas  # noqa: E402
from app.database import SessionLocal, set_tenant_context  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.models import ChangeRequest, TimeEntry, TimeEntryAuditLog, User, WorkingHoursChange  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402
from app.routers import admin_change_requests, admin_time_entries, admin_users, time_entries  # noqa: E402
from app.schemas.change_request import ChangeRequestReview  # noqa: E402
from app.schemas.time_entry import ClockOutRequest, TimeEntryCreate, TimeEntryUpdate  # noqa: E402
from app.schemas.working_hours_change import WorkingHoursChangeCreate  # noqa: E402
from app.services import wh_change_service  # noqa: E402
from app.services.timezone_service import LOCAL_TZ  # noqa: E402

TENANT_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000100")
ADMIN_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000200")
DAY = date(2099, 6, 1)  # Montag
NEXT_DAY = DAY + timedelta(days=1)  # „heute" für den Auto-Close eines offenen Eintrags von gestern
PREV_TUESDAY = DAY - timedelta(days=6)  # vor dem Wirkungsbereich, ohne Blöcke — Ausgangstag der Verschiebungen
EMPTY = {"blocks": [], "pause_minutes": 0}
OLD = [{"blocks": [{"start": "08:00", "end": "18:00"}], "pause_minutes": 0}] + [EMPTY] * 4
NEW = [{"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "16:00"}],
        "pause_minutes": 0}] + [EMPTY] * 4


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


def _wipe(conn):
    # change_requests vor time_entries (FK time_entry_id), Protokoll zuerst (FK change_request_id).
    for table in ("time_entry_audit_logs", "change_requests", "time_entries", "working_hours_changes", "absences"):
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": str(TENANT_ID)})


@pytest.fixture(scope="module")
def seed(admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.execute(text("DELETE FROM security_events WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("INSERT INTO tenants (id, name, slug, is_active, mode) "
                      "VALUES (:id, 'Reclamp Wettlauf', 'reclamp-wettlauf', true, 'multi')"), {"id": str(TENANT_ID)})
    for uid, name, role in ((USER_ID, "reclamp_user", "EMPLOYEE"), (ADMIN_ID, "reclamp_admin", "ADMIN")):
        conn.execute(text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash, first_name, last_name, role,
                               weekly_hours, vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :u, :e, 'not-real', 'R', 'Test', :role, 10, 30, 1, true)
        """), {"id": str(uid), "tid": str(TENANT_ID), "u": name, "e": f"{name}@test.local", "role": role})
    yield
    _wipe(conn)
    conn.execute(text("DELETE FROM security_events WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.close()


@pytest.fixture
def fresh(seed, admin_engine):
    conn = admin_engine.connect()
    _wipe(conn)
    conn.close()
    session = SessionLocal()
    set_tenant_context(session, TENANT_ID)
    session.add(WorkingHoursChange(
        user_id=USER_ID, tenant_id=TENANT_ID, effective_from=date(2099, 1, 1), weekly_hours=10,
        use_daily_schedule=True, hours_monday=10, hours_tuesday=0, hours_wednesday=0, hours_thursday=0,
        hours_friday=0, work_days_per_week=1, blocks=OLD,
    ))
    session.commit()
    session.close()
    yield


def _with_session(fn):
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        return fn(session)
    finally:
        session.close()


def _change_thread(results: list):
    """Thread A legt die Änderung ab ``DAY`` an. Mit Schutzpaket: liegt beim
    Rechenpfad schon ein geschlossener Eintrag an ``DAY``, der unter den neuen
    Blöcken angerechnete Zeit verliert, ist die Änderung eine Verkürzung (a) und
    scheiterte ohne Grund/Haken mit 400 (9.5) — der Wettlauf fände nie statt.
    Das betrifft nur das Anerkennen (08–18 verliert die Lücke, 150 Min) und die
    beiden Reihenfolge-Fälle (``_entry_on_day``, 08–17). Bei den
    Verschiebe-Fällen liegt der Eintrag dann noch vor ``DAY``
    (``_entry_to_move``), bei den übrigen gibt es noch keinen geschlossenen —
    dort bleibt das Schutzpaket wirkungslos (Gegenprobe ohne: nur diese drei
    Fälle scheitern mit 400)."""
    def run(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        try:
            admin_users.create_working_hours_change(
                user_id=str(USER_ID),
                change_data=WorkingHoursChangeCreate(
                    effective_from=DAY, blocks=NEW, retroactive_reason_type="erfassungsfehler",
                    retroactive_reason_text="Wettlauf-Test: Arbeitszeit war falsch hinterlegt",
                    wage_risk_confirmed=True),
                db=session, current_user=admin)
            results.append(("change", time_module.monotonic()))
        except Exception as exc:  # pragma: no cover — Fehler sichtbar machen
            session.rollback()
            results.append(("change-error", repr(exc)))
    _with_session(run)


def _race(monkeypatch, writer, *, today=DAY, now=time(18, 0), change=None, early=False):
    """Thread A legt die Änderung an (bzw. ``change``, z. B. ``_delete_thread``)
    und hält die Ankersperre danach noch 0,8 s; Thread B startet erst, wenn A den
    Rechenpfad (Snapshot, Neukappungs-Abfrage) unter der Sperre schon durchlaufen
    hat, aber noch nicht committet ist — genau das Fenster aus P5: ohne
    Ankersperre läse B jetzt den alten Snapshot, und die bereits gelaufene
    Neukappung erfasste seinen Eintrag nicht mehr (der Eintrag bliebe unter den
    alten Blöcken). Läge die Verzögerung VOR dem Rechenpfad, fände A's
    Neukappung einen ungesperrt geschriebenen Eintrag von B noch und kappte ihn
    nach — der Test sähe dann nur die Reihenfolge, nicht den Schaden.

    ``early=True`` startet B dagegen, sobald A die Ankersperre hält, noch VOR dem
    Rechenpfad (A hat noch keine Eintragszeile gesperrt): der Fall für die
    Sperr-REIHENFOLGE (P5, 13.3; Anerkennen, Admin-Update, CR-Genehmigung) —
    ein Schreiber, der die Zeile vor dem Anker nähme, hielte sie, wenn A's
    Neukappung sie braucht, und wartete selbst auf den Anker → Deadlock (40P01).

    ``today``/``now`` gelten nur für Schreiber B (``time_entries`` und die
    Datumsprüfung der Eintrags-Schemas) — A rechnet mit dem echten „heute", für A
    ist die Änderung ab ``DAY`` also zukunftsdatiert und schließt keinen offenen
    Eintrag selbst."""
    has_lock = threading.Event()
    real_run = wh_change_service.run_change

    def slow_run(*args, **kwargs):
        # create/delete_working_hours_change sperren VOR run_change.
        if early:
            has_lock.set()
            time_module.sleep(0.8)
            return real_run(*args, **kwargs)
        result = real_run(*args, **kwargs)
        has_lock.set()
        time_module.sleep(0.8)
        return result

    monkeypatch.setattr(wh_change_service, "run_change", slow_run)
    monkeypatch.setattr(time_entries, "_today_local", lambda: today)
    monkeypatch.setattr(time_entries, "_now_local", lambda: datetime.combine(today, now, tzinfo=LOCAL_TZ))
    # TimeEntryCreate.validate_not_future bindet today_local beim Import — ohne
    # diesen Patch lehnt das Schema DAY (2099) als Zukunftsdatum ab.
    monkeypatch.setattr(time_entry_schemas, "today_local", lambda: today)
    results: list = []
    a = threading.Thread(target=change or _change_thread, args=(results,))

    def b_target():
        has_lock.wait(timeout=5)
        try:
            _with_session(writer)
            results.append(("writer", time_module.monotonic()))
        except Exception as exc:  # pragma: no cover
            results.append(("writer-error", repr(exc)))

    b = threading.Thread(target=b_target)
    a.start(); b.start(); a.join(timeout=30); b.join(timeout=30)
    return dict((r[0], r[1]) for r in results)


def _the_entry():
    return _with_session(lambda s: s.query(TimeEntry).filter(TimeEntry.user_id == USER_ID, TimeEntry.date == DAY).one())


def _add(obj):
    """Legt ``obj`` in einer eigenen Sitzung an und gibt die ID zurück."""
    return _with_session(lambda s: (s.add(obj), s.commit(), obj.id)[2])


def _entry_to_move():
    """Geschlossener Eintrag 08:00–17:00 am Dienstag VOR ``DAY`` — außerhalb des
    Wirkungsbereichs der Änderung, die ihn deshalb weder neu kappt noch sperrt.
    Schreiber B verschiebt ihn auf ``DAY``: dann schützt ALLEIN die Ankersperre
    vor dem alten Snapshot. Läge er schon an ``DAY``, hielte A ihn nach der
    Neukappung zeilengesperrt, B läse erst nach A's Commit — der Test bliebe
    grün, auch wenn der Pfad die Ankersperre gar nicht nähme (Gegenprobe). Die
    Sperr-Reihenfolge prüft dafür ``_entry_on_day`` mit ``early=True``."""
    return _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=PREV_TUESDAY, start_time=time(8),
                          end_time=time(17), break_minutes=45, clamp_grace_minutes=15))


def _entry_on_day():
    """Geschlossener Eintrag 08:00–17:00 direkt an ``DAY`` — unter den ALTEN
    Blöcken (08–18, Hülle 07:45–18:15) ungekappt, unter den neuen verliert er
    Zeit. Gegenstück zu ``_entry_to_move`` für die Sperr-REIHENFOLGE: A's
    Neukappung braucht genau diese Zeile; mit ``early=True`` steht B schon am
    Anker, bevor A sie sperrt (P5, Anker vor Zeile)."""
    return _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                          end_time=time(17), break_minutes=45, clamp_grace_minutes=15))


def _assert_waited_and_clamped(done, raw_end=time(18, 0)):
    assert "change" in done and "writer" in done, done
    assert done["writer"] >= done["change"]
    e = _the_entry()
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(16, 15), raw_end, 150)
    return e


def test_clock_out_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    _with_session(lambda s: (s.add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                                             end_time=None, break_minutes=0, clamp_grace_minutes=15)), s.commit()))

    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.clock_out(body=ClockOutRequest(break_minutes=45), db=session, current_user=user)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_create_time_entry_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.create_time_entry(
            entry_data=TimeEntryCreate(date=DAY, start_time=time(8), end_time=time(18), break_minutes=45),
            db=session, current_user=user)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_admin_update_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """PUT /api/admin/time-entries/{id}: der Eintrag wandert auf ``DAY`` und
    endet um 18:00 — gekappt mit den NEUEN Blöcken (Hülle 16:15, Lücke
    12:15–14:45), nicht mit dem alten Snapshot."""
    entry_id = _entry_to_move()

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_time_entries.admin_update_time_entry(
            entry_id=str(entry_id), entry_data=TimeEntryUpdate(date=DAY, end_time=time(18), break_minutes=45),
            db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_admin_update_takes_the_anchor_before_the_row(fresh, monkeypatch):
    """Sperr-Reihenfolge (P5, 13.3) beim Admin-Update: der Eintrag liegt schon
    an ``DAY`` und B startet, solange A nur den Anker hält. Nähme der Pfad die
    Eintragszeile vor dem Anker, hielte B sie, wenn A's Neukappung sie braucht,
    und wartete selbst auf den Anker → 40P01 (im Betrieb ein 500 beim
    Bearbeiten eines Eintrags, der gerade neu gekappt wird). Der Verschiebe-Fall
    oben sieht das nicht — dort sperrt A die Zeile nie (Gegenprobe)."""
    entry_id = _entry_on_day()

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_time_entries.admin_update_time_entry(
            entry_id=str(entry_id), entry_data=TimeEntryUpdate(end_time=time(18), break_minutes=45),
            db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer, early=True))


def test_change_request_approval_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """POST /api/admin/change-requests/{id}/review, UPDATE-Zweig: der Antrag
    verschiebt den Eintrag auf ``DAY`` mit Ende 18:00 (wie beim Admin-Update)."""
    entry_id = _entry_to_move()
    cr_id = _add(ChangeRequest(
        tenant_id=TENANT_ID, user_id=USER_ID, entry_kind="time_entry", request_type=ChangeRequestType.UPDATE,
        status=ChangeRequestStatus.PENDING, time_entry_id=entry_id, proposed_date=DAY,
        proposed_start_time=time(8), proposed_end_time=time(18), proposed_break_minutes=45,
        original_date=PREV_TUESDAY, original_start_time=time(8), original_end_time=time(17),
        original_break_minutes=45, reason="Wettlauf-Test: Eintrag auf den richtigen Tag verschoben"))

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_change_requests.review_change_request(
            request_id=str(cr_id), review=ChangeRequestReview(action="approve"), db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer))


def test_change_request_approval_takes_the_anchor_before_the_row(fresh, monkeypatch):
    """Sperr-Reihenfolge (P5, 13.3) im UPDATE-Zweig der CR-Genehmigung: der
    Antrag verlängert einen Eintrag, der schon an ``DAY`` liegt, auf 18:00; B
    startet, solange A nur den Anker hält (wie beim Admin-Update oben)."""
    entry_id = _entry_on_day()
    cr_id = _add(ChangeRequest(
        tenant_id=TENANT_ID, user_id=USER_ID, entry_kind="time_entry", request_type=ChangeRequestType.UPDATE,
        status=ChangeRequestStatus.PENDING, time_entry_id=entry_id, proposed_date=DAY,
        proposed_start_time=time(8), proposed_end_time=time(18), proposed_break_minutes=45,
        original_date=DAY, original_start_time=time(8), original_end_time=time(17),
        original_break_minutes=45, reason="Wettlauf-Test: tatsächliches Ende nachgetragen"))

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        admin_change_requests.review_change_request(
            request_id=str(cr_id), review=ChangeRequestReview(action="approve"), db=session, current_user=admin)

    _assert_waited_and_clamped(_race(monkeypatch, writer, early=True))


def test_clock_status_auto_close_waits_and_clamps_with_the_new_blocks(fresh, monkeypatch):
    """GET /api/time-entries/clock-status mit offenem Eintrag von gestern: der
    Auto-Close (PR1 Task 8, Ende 23:59 über clamp) nimmt die Ankersperre zuerst
    und kappt danach mit den neuen Blöcken."""
    _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                   end_time=None, break_minutes=0, clamp_grace_minutes=15))

    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.get_clock_status(
            request=SimpleNamespace(state=SimpleNamespace()), db=session, current_user=user)

    e = _assert_waited_and_clamped(_race(monkeypatch, writer, today=NEXT_DAY, now=time(8, 0)),
                                   raw_end=time(23, 59))
    assert e.auto_closed is True


def test_credit_override_parallel_to_a_reclamp_does_not_deadlock(fresh, monkeypatch):
    """POST /api/admin/time-entries/{id}/credit-override (PR2, 13.3) parallel zur
    Neukappung desselben Eintrags: Anker vor Zeile auf beiden Seiten, kein 40P01.
    B startet früh (``early``), solange A nur den Anker hält — nähme das
    Anerkennen die Eintragszeile vor dem Anker, verklemmte es sich hier mit
    A's Neukappung (Gegenprobe). Direkt über die Endpunkt-Funktion — über ``app.routes`` ist sie nicht
    auffindbar (FastAPI ≥ 0.137 legt eingebundene Router als ``_IncludedRouter``
    ohne ``.path`` ab); fehlt sie, scheitert schon der Attributzugriff hart."""
    endpoint = admin_time_entries.admin_credit_override
    entry_id = _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                              end_time=time(18), break_minutes=45, clamp_grace_minutes=15))

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        endpoint(entry_id=str(entry_id), db=session, current_user=admin)

    done = _race(monkeypatch, writer, early=True)
    assert "change" in done and "writer" in done, done   # kein 40P01 auf einer der beiden Seiten
    e = _the_entry()
    assert (e.credit_override, e.uncredited_minutes, e.start_time, e.end_time) == (True, 0, time(8), time(18))


# ── Löschen (Review Task 11): dieselbe Ankersperre wie das Anlegen ──────────


def _later_row():
    """Zweite Verlaufszeile ab ``DAY`` mit den NEUEN Blöcken — die früheste Zeile
    ist gesperrt, solange spätere existieren; gelöscht wird also diese."""
    return _add(WorkingHoursChange(
        user_id=USER_ID, tenant_id=TENANT_ID, effective_from=DAY, weekly_hours=5, use_daily_schedule=True,
        hours_monday=5, hours_tuesday=0, hours_wednesday=0, hours_thursday=0, hours_friday=0,
        work_days_per_week=1, blocks=NEW))


def _delete_thread(change_id):
    """Thread A als Löschen der Zeile ``change_id`` (statt Anlegen); ``_race``
    verzögert auch hier ``run_change`` hinter der Ankersperre."""
    def thread(results: list):
        def run(session):
            admin = session.query(User).filter(User.id == ADMIN_ID).first()
            try:
                admin_users.delete_working_hours_change(
                    user_id=str(USER_ID), change_id=str(change_id), db=session, current_user=admin, body=None)
                results.append(("change", time_module.monotonic()))
            except Exception as exc:  # pragma: no cover — Fehler sichtbar machen
                session.rollback()
                results.append(("change-error", repr(exc)))
        _with_session(run)
    return thread


def test_parallel_delete_of_the_same_row_is_404(fresh, monkeypatch):
    """Zwei gleichzeitige DELETEs derselben Zeile: der zweite wartet auf die
    Ankersperre, liest die Zeile danach neu (Task 11, Abweichung 3) und antwortet
    404. Ohne das Neulesen meldete auch er Erfolg — SQLAlchemy warnt bei 0
    gelöschten Zeilen nur — und schriebe eine zweite Sammelzeile „… gelöscht"."""
    row_id = _later_row()
    statuses: list = []

    def writer(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        try:
            admin_users.delete_working_hours_change(
                user_id=str(USER_ID), change_id=str(row_id), db=session, current_user=admin, body=None)
            statuses.append("deleted")
        except HTTPException as exc:
            session.rollback()
            statuses.append((exc.status_code, exc.detail))

    done = _race(monkeypatch, writer, change=_delete_thread(row_id))
    assert "change" in done and "writer" in done, done
    assert statuses == [(404, "Stundenänderung nicht gefunden")]

    def state(s):
        rows = s.query(WorkingHoursChange).filter(WorkingHoursChange.id == row_id).count()
        summaries = s.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == TENANT_ID, TimeEntryAuditLog.user_id == USER_ID,
            TimeEntryAuditLog.source == "wh_reclamp", TimeEntryAuditLog.time_entry_id.is_(None),
            TimeEntryAuditLog.new_note.like("Arbeitszeit-Änderung ab 01.06.2099 gelöscht: %")).count()
        return rows, summaries

    assert _with_session(state) == (0, 1)


def test_clock_out_during_a_delete_waits_and_clamps_with_the_predecessor_blocks(fresh, monkeypatch):
    """Löschen der Zeile ab ``DAY`` (NEUE Blöcke) parallel zum Ausstempeln:
    ``clock_out`` wartet auf die Ankersperre und kappt danach mit den Blöcken des
    Vorgängers (08–18, Hülle bis 18:15) — mit dem vor der Sperre gelesenen Stand
    hätte es auf 16:15 gekappt (150 Min nicht angerechnet)."""
    row_id = _later_row()
    _add(TimeEntry(tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(8),
                   end_time=None, break_minutes=0, clamp_grace_minutes=15))

    def writer(session):
        user = session.query(User).filter(User.id == USER_ID).first()
        time_entries.clock_out(body=ClockOutRequest(break_minutes=45), db=session, current_user=user)

    done = _race(monkeypatch, writer, change=_delete_thread(row_id))
    assert "change" in done and "writer" in done, done
    assert done["writer"] >= done["change"]
    e = _the_entry()
    assert (e.end_time, e.uncredited_minutes) == (time(18, 0), 0)


# ── Kollision (Spec 17.5 „Überspringen je Grund … Kollision auf PG", 9.2 Schritt 8) ──
# Auf ``time_entries`` liegt der NICHT verzögerbare Unique-Index
# ``uq_tenant_user_date_start (tenant_id, user_id, date, start_time)``. Die Session
# flusht nicht automatisch (``autoflush=False``); ``run_change`` flusht die
# Neukappung erst als Ganzes, und SQLAlchemy ordnet die UPDATEs einer Tabelle nach
# Primärschlüssel — nicht nach der Reihenfolge, in der die Schleife die Einträge
# bearbeitet. Gesamtreview PR3.

COLLISION_NEW = [{"blocks": [{"start": "07:35", "end": "18:00"}], "pause_minutes": 0}] + [EMPTY] * 4
LOW_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000301")
HIGH_ID = uuid.UUID("ccccccc3-0000-4000-8000-000000000302")


def _save_change(blocks):
    """Legt die Änderung ab ``DAY`` über den Anlege-Endpunkt an (Schutzpaket
    dabei, falls die Änderung als Verkürzung gilt) und gibt die Zählwerte der
    Antwort zurück: (``adjusted_time_entries``, ``skipped_time_entries``)."""
    def run(session):
        admin = session.query(User).filter(User.id == ADMIN_ID).first()
        change = admin_users.create_working_hours_change(
            user_id=str(USER_ID),
            change_data=WorkingHoursChangeCreate(
                effective_from=DAY, blocks=blocks, retroactive_reason_type="erfassungsfehler",
                retroactive_reason_text="Kollisions-Test: Arbeitszeit war falsch hinterlegt",
                wage_risk_confirmed=True),
            db=session, current_user=admin)
        return change.adjusted_time_entries, change.skipped_time_entries
    return _with_session(run)


def _day_entries():
    return _with_session(lambda s: sorted(
        (e.id, e.start_time, e.raw_start_time, e.end_time)
        for e in s.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID, TimeEntry.user_id == USER_ID,
                                           TimeEntry.date == DAY)))


def _summary_note():
    return _with_session(lambda s: s.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == TENANT_ID, TimeEntryAuditLog.user_id == USER_ID,
        TimeEntryAuditLog.source == "wh_reclamp", TimeEntryAuditLog.time_entry_id.is_(None)).one().new_note)


@pytest.mark.parametrize("ids", [(LOW_ID, HIGH_ID), (HIGH_ID, LOW_ID)], ids=["a-zuerst", "b-zuerst"])
def test_unique_collision_is_skipped_on_postgres(fresh, ids):
    """Neue Blöcke Mo 08:05–18:00 (Hülle ab 07:50): Eintrag a (gestempelt 07:30,
    gekappt 07:45) bekäme den Beginn 07:50 — dort beginnt schon Eintrag b. Die
    Prüfung aus 9.2 Schritt 8 überspringt a, ein IntegrityError entsteht nicht;
    a bleibt unverändert, die Sammelzeile nennt die Überschneidung. Beide
    Primärschlüssel-Reihenfolgen, weil sie die Reihenfolge der UPDATEs bestimmen."""
    a_id, b_id = ids
    _add(TimeEntry(id=a_id, tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(7, 45),
                   raw_start_time=time(7, 30), end_time=time(9), break_minutes=0, clamp_grace_minutes=15))
    _add(TimeEntry(id=b_id, tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(7, 50),
                   end_time=time(7, 55), break_minutes=0, clamp_grace_minutes=15))
    before = _day_entries()
    blocks = [{"blocks": [{"start": "08:05", "end": "18:00"}], "pause_minutes": 0}] + [EMPTY] * 4
    assert _save_change(blocks) == (0, 1)
    assert _day_entries() == before
    assert ", 1 übersprungen (1 Überschneidung) · " in _summary_note()


@pytest.mark.parametrize("ids", [(LOW_ID, HIGH_ID), (HIGH_ID, LOW_ID)], ids=["a-zuerst", "b-zuerst"])
def test_start_vacated_in_the_same_run_does_not_collide_on_postgres(fresh, ids):
    """Eintrag b (gestempelt 07:10, gespeichert 07:30 — gekappt mit einem früheren,
    größeren Puffer) rückt unter der neuen Hülle (ab 07:20) auf 07:20 vor; Eintrag
    a (gestempelt 07:30, gekappt 07:45) übernimmt dabei b's alten Beginn 07:30.
    Die Python-Prüfung lässt das zu (b ist zuerst dran, sein neuer Beginn ist
    eingeplant). Postgres prüft den Index aber je UPDATE: liefe a's UPDATE vor
    b's, scheiterte das Speichern mit einem IntegrityError (500) — je nach
    Primärschlüssel. Erwartet: beide Einträge neu gekappt, kein Fehler."""
    a_id, b_id = ids
    _add(TimeEntry(id=a_id, tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(7, 45),
                   raw_start_time=time(7, 30), end_time=time(12), break_minutes=0, clamp_grace_minutes=15))
    _add(TimeEntry(id=b_id, tenant_id=TENANT_ID, user_id=USER_ID, date=DAY, start_time=time(7, 30),
                   raw_start_time=time(7, 10), end_time=time(7, 40), break_minutes=0, clamp_grace_minutes=30))
    assert _save_change(COLLISION_NEW) == (2, 0)
    starts = {e[0]: (e[1], e[2]) for e in _day_entries()}
    assert starts == {a_id: (time(7, 30), None), b_id: (time(7, 20), time(7, 10))}
