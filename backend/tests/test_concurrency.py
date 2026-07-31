"""
Concurrency integration tests against real Postgres.

These tests exist to catch races that can only manifest under true parallel
execution — they would silently pass against SQLite, which serialises at the
connection level. The runtime dependency is identical to test_tenant_rls.py:
the backend container's DATABASE_URL.
"""

from __future__ import annotations

import os
import threading
import time as time_module
import uuid
from datetime import date, time, datetime

import pytest
from sqlalchemy import create_engine, text

APP_DB_URL = os.environ.get("APP_DB_URL") or os.environ.get("DATABASE_URL")
ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not APP_DB_URL or not ADMIN_DB_URL:
    pytest.skip(
        "test_concurrency.py needs DATABASE_URL + DATABASE_URL_MIGRATIONS; "
        "run with `docker compose exec backend pytest …`.",
        allow_module_level=True,
    )

# F-Review (wrong-test finding): exercise the REAL locking/read code from
# app/routers/time_entries.py instead of a hand-rolled raw-SQL reimplementation
# that diverged from it (and silently omitted the F-026 tenant filter).
#
# Review 2026-07-14 (fix-A6c): go one step further and call the REAL
# `clock_in()` endpoint function itself (not just `_get_open_entry`), so the
# test exercises the User-row anchor lock added in front of it. A bare
# `SELECT ... FOR UPDATE` on zero matching rows locks nothing under READ
# COMMITTED — see the long comment in `clock_in` — so calling only
# `_get_open_entry` would never prove the anchor lock does anything.
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import SessionLocal, set_tenant_context
from app.models import Absence, AbsenceType, TimeEntry, User
from app.models.change_request import (
    ChangeRequest, ChangeRequestStatus, ChangeRequestType,
)
from app.routers import absences as absences_router
from app.routers import admin_time_entries as admin_time_entries_router
from app.routers import change_requests as change_requests_router
from app.routers import company_closures as company_closures_router
from app.routers import time_entries
from app.schemas.absence import AbsenceCreate
from app.schemas.time_entry import ClockInRequest, TimeEntryUpdate
from app.services.timezone_service import LOCAL_TZ


TENANT_ID = uuid.UUID("ccccccc1-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("ccccccc1-0000-4000-8000-000000000100")


@pytest.fixture(scope="module")
def admin_engine():
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def app_engine():
    eng = create_engine(APP_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def concurrency_seed(admin_engine):
    """Create the test tenant + user; clean up after module."""
    conn = admin_engine.connect()
    # Best-effort pre-cleanup (company_closures VOR users: created_by ist ein FK)
    conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM change_requests WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM absences WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM company_closures WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})

    conn.execute(text("""
        INSERT INTO tenants (id, name, slug, is_active, mode)
        VALUES (:id, :name, :slug, true, 'multi')
    """), {"id": str(TENANT_ID), "name": "Concurrency Test", "slug": "concurrency-test"})

    conn.execute(text("""
        INSERT INTO users (id, tenant_id, username, email, password_hash,
                           first_name, last_name, role, weekly_hours,
                           vacation_days, work_days_per_week, is_active)
        VALUES (:id, :tid, :u, :e, 'not-real', 'C', 'Test', 'EMPLOYEE',
                40, 30, 5, true)
    """), {
        "id": str(USER_ID), "tid": str(TENANT_ID),
        "u": "concurrency_test_user", "e": "concurrency@test.local",
    })

    yield

    conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM change_requests WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM absences WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM company_closures WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
    conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(TENANT_ID)})
    conn.close()


# fix-A6c: fixed "today" for both threads, but a DIFFERENT clock-in minute
# per thread. This deliberately keeps `uq_tenant_user_date_start` (tenant,
# user, date, start_time) from being able to catch a duplicate — the two
# inserts have different `start_time` values — so the ONLY thing that can
# still prevent a double-clock-in here is the User-row anchor lock in
# `clock_in`. A same-minute race would let the unique constraint mask a
# missing/removed anchor lock (see fix-A6b-report.md); this test must not
# depend on that safety net if it is to have teeth against a regression.
_FAKE_TODAY = date(2099, 6, 1)
_fake_time_by_thread: dict = {}


def _fake_now_local():
    t = _fake_time_by_thread[threading.get_ident()]
    return datetime.combine(_FAKE_TODAY, t, tzinfo=LOCAL_TZ)


def _fake_today_local():
    return _FAKE_TODAY


def _run_clock_in_attempt(
    results: list,
    idx: int,
    barrier: threading.Barrier,
    fake_time,
):
    """Call the REAL `app.routers.time_entries.clock_in()` endpoint function
    directly (not a reimplementation) so the test exercises everything the
    endpoint does, including the User-row anchor lock added in front of
    `_get_open_entry`. `time_entries._now_local`/`_today_local` are
    monkeypatched module-wide by the test (before threads start) to
    `_fake_now_local`/`_fake_today_local`; this thread registers its own
    fixed `fake_time` under its thread-id so both threads land on the same
    fake "today" but a different minute (see module comment above).

    Uses `app.database.SessionLocal` + `set_tenant_context` (the REAL
    production wiring, not a raw `SET LOCAL` on an ad-hoc sessionmaker):
    `clock_in` does `db.refresh(entry)` AFTER `db.commit()`, which starts a
    new transaction, and plain `SET LOCAL` is transaction-scoped — only
    `SessionLocal`'s `after_begin` event listener (registered in
    app/database.py) re-applies `app.tenant_id` on that new transaction, so
    the post-commit refresh still passes RLS.
    """
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        current_user = session.query(User).filter(User.id == USER_ID).first()
        _fake_time_by_thread[threading.get_ident()] = fake_time

        # Align the two threads so they enter clock_in() at nearly the same
        # instant — this is the actual concurrency being tested.
        barrier.wait(timeout=5)

        time_entries.clock_in(
            body=ClockInRequest(note=None), db=session, current_user=current_user,
        )
        results.append(("inserted", idx))
    except HTTPException as e:
        # "Bereits eingestempelt" — the expected loser outcome when the
        # anchor lock correctly serializes the two attempts.
        session.rollback()
        results.append(("rejected", idx, e.status_code))
    except IntegrityError as e:
        session.rollback()
        results.append(("error", idx, "IntegrityError"))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", idx, type(e).__name__))
    finally:
        del _fake_time_by_thread[threading.get_ident()]
        session.close()


def test_parallel_clock_in_serializes(app_engine, concurrency_seed, admin_engine, monkeypatch):
    """
    Two threads race the REAL `clock_in()` endpoint function from
    app/routers/time_entries.py (not a raw-SQL reimplementation) for the SAME
    user, at nearly the same instant, on the same fake "today" but different
    minutes (so the `uq_tenant_user_date_start` unique constraint cannot mask
    a broken/missing anchor lock — see module comment above). Only ONE of the
    two racing attempts may survive as an open entry — otherwise the user
    ends up with two overlapping open entries, which is exactly the §16
    double-clock-in gap this test guards against.

    Regression coverage: commenting out the `db.query(User)...with_for_update()`
    anchor lock in `clock_in` (VULN-009 / review 2026-07-14 fix) makes this
    test fail with 2 inserted/open entries instead of 1 — verified manually
    against Postgres 18 as part of the fix, see fix-A6c-report.md.
    """
    # Ensure the user has no open entry before the race starts
    admin = admin_engine.connect()
    admin.execute(text("DELETE FROM time_entries WHERE user_id = :u"), {"u": str(USER_ID)})
    admin.close()

    monkeypatch.setattr(time_entries, "_now_local", _fake_now_local)
    monkeypatch.setattr(time_entries, "_today_local", _fake_today_local)

    results: list = []
    barrier = threading.Barrier(2)
    t1 = threading.Thread(
        target=_run_clock_in_attempt, args=(results, 1, barrier, time(9, 0)),
    )
    t2 = threading.Thread(
        target=_run_clock_in_attempt, args=(results, 2, barrier, time(9, 1)),
    )
    t1.start(); t2.start(); t1.join(); t2.join()

    outcomes = [r[0] for r in results]
    inserted = outcomes.count("inserted")
    errored = [r for r in results if r[0] == "error"]
    # The loser must be rejected either by the application-level "Bereits
    # eingestempelt" check (outcome "rejected") or, as a defense-in-depth
    # backstop, by a DB-level unique/exclusion violation (outcome "error" /
    # IntegrityError) — never a silent duplicate and never an unrelated crash.
    for r in errored:
        assert r[2] == "IntegrityError", f"Unexpected error type on loser thread: {r}"
    assert inserted == 1, f"Expected exactly 1 insert, got outcomes={outcomes}"

    # Verify DB state: exactly one open entry
    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        count = conn.execute(
            text("SELECT COUNT(*) FROM time_entries WHERE user_id = :u AND end_time IS NULL"),
            {"u": str(USER_ID)},
        ).scalar()
        assert count == 1


# =============================================================================
# Audit 2026-07-31 — Nebenläufigkeit / Zustandsübergänge
# =============================================================================

# Zwei Werktage weit in der Zukunft (Mi/Do), damit die Tests keine echten
# Feiertags-/Sondertagskonfigurationen treffen und sich nicht gegenseitig sehen.
_ABS_DAY = date(2099, 6, 3)   # Mittwoch
_ABS_DAY2 = date(2099, 6, 4)  # Donnerstag


@pytest.fixture
def clean_absence_state(admin_engine):
    """Leert Anträge + Abwesenheiten des Test-Tenants vor UND nach dem Test."""
    def _wipe():
        conn = admin_engine.connect()
        conn.execute(text("DELETE FROM change_requests WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM absences WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.close()

    _wipe()
    yield
    _wipe()


# --- A3: Rückziehen darf keine bereits erfolgte Genehmigung überschreiben -----


def _seed_pending_cr() -> uuid.UUID:
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        cr = ChangeRequest(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            request_type=ChangeRequestType.CREATE,
            status=ChangeRequestStatus.PENDING,
            entry_kind="time_entry",
            proposed_date=_ABS_DAY,
            proposed_start_time=time(9, 0),
            proposed_end_time=time(17, 0),
            proposed_break_minutes=30,
            reason="Audit-Test 2026-07-31",
        )
        session.add(cr)
        session.commit()
        session.refresh(cr)
        return cr.id
    finally:
        session.close()


def _run_withdraw(results: list, cr_id):
    """Ruft die ECHTE Endpoint-Funktion `withdraw_change_request` auf."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == USER_ID).first()
        change_requests_router.withdraw_change_request(
            request_id=str(cr_id), db=session, current_user=me,
        )
        results.append(("withdrawn",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_withdraw_cannot_delete_an_approved_change_request(
    concurrency_seed, clean_absence_state, app_engine,
):
    """Zurückziehen während der Admin genehmigt: der Antrag darf NICHT verschwinden.

    Ohne ``with_for_update()`` liest ``withdraw_change_request`` ein veraltetes
    Abbild (PENDING), setzt sein ``DELETE … WHERE id = :id`` ab und wartet auf
    die Zeilensperre; nach dem Commit des Genehmigers qualifiziert Postgres die
    Bedingung unter READ COMMITTED neu (EvalPlanQual) — die Bedingung nennt nur
    die ``id``, also wird der inzwischen GENEHMIGTE Antrag gelöscht. Seine
    Seiteneffekte (gebuchte Zeit / Abwesenheit) bleiben bestehen, und das
    FK ``ON DELETE SET NULL`` auf ``time_entry_audit_logs.change_request_id``
    schreibt am ``before_insert``-Hook vorbei → der gespeicherte ``row_hash``
    (#121) wird stale und ``verify-integrity`` meldet eine legitime Zeile als
    manipuliert.

    Sitzung A sperrt die Antragszeile GENAU so wie
    ``admin_change_requests.review_change_request`` (``with_for_update``) und
    flippt den Status; der Commit folgt erst, nachdem der Mitarbeiter sein
    Zurückziehen abgesetzt hat.
    """
    cr_id = _seed_pending_cr()

    approver = SessionLocal()
    set_tenant_context(approver, TENANT_ID)
    cr = (
        approver.query(ChangeRequest)
        .filter(ChangeRequest.id == cr_id, ChangeRequest.tenant_id == TENANT_ID)
        .with_for_update()
        .first()
    )
    assert cr is not None
    cr.status = ChangeRequestStatus.APPROVED
    approver.flush()  # Zeilensperre + neue Version, noch NICHT committed

    results: list = []
    t = threading.Thread(target=_run_withdraw, args=(results, cr_id))
    t.start()
    time_module.sleep(1.0)
    # Beide Varianten (mit/ohne Fix) warten hier — die eine an der Lesesperre,
    # die andere an der DELETE-Sperre. Diese Zusicherung ist nur eine
    # Plausibilitätsprüfung, dass die Sitzungen wirklich kollidieren.
    assert not results, f"Kein Konflikt entstanden (Ergebnis bereits da: {results})"

    approver.commit()
    approver.close()
    t.join(timeout=20)

    assert results == [("rejected", 400)], (
        f"Zurückziehen hätte den genehmigten Antrag mit 400 ablehnen müssen: {results}"
    )

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        row = conn.execute(
            text("SELECT status FROM change_requests WHERE id = :i"), {"i": str(cr_id)},
        ).first()
    assert row is not None, "Der genehmigte Antrag wurde vom Zurückziehen gelöscht"
    assert row[0] == "approved", row[0]


# --- A2: zwei Abwesenheiten am selben Tag ------------------------------------


def _run_create_absence(results: list, absence_type, day):
    """Ruft die ECHTE Endpoint-Funktion `create_absence` auf."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == USER_ID).first()
        absences_router.create_absence(
            absence_data=AbsenceCreate(date=day, type=absence_type, hours=8.0),
            db=session, current_user=me,
        )
        results.append(("created",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except IntegrityError:
        session.rollback()
        results.append(("error", "IntegrityError"))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_absence_booking_waits_on_the_user_anchor_lock(
    concurrency_seed, clean_absence_state, app_engine,
):
    """Zwei Buchungen UNTERSCHIEDLICHEN Typs am selben Tag dürfen nicht beide durchgehen.

    Das UNIQUE ist ``(tenant, user, date, TYPE)`` — zwei verschiedene Typen
    kollidieren auf DB-Ebene also NICHT. Griff die Anker-Sperre auf der
    Benutzerzeile nur für ``VACATION``, schützte sonst allein ein
    ``with_for_update()`` auf einer LEEREN Ergebnismenge, das unter READ
    COMMITTED nichts sperrt: beide Buchungen liefen durch (Soll 0 UND Ist +8 h
    am selben Tag, dazu ggf. ein verbrauchter Urlaubstag).

    Sitzung A hält die Anker-Sperre und bucht danach TRAINING; der Thread bucht
    KRANK und muss warten, bis die Benutzerzeile frei ist — und sieht dann den
    Konflikt (409).
    """
    holder = SessionLocal()
    set_tenant_context(holder, TENANT_ID)
    holder.query(User).filter(
        User.id == USER_ID, User.tenant_id == TENANT_ID,
    ).with_for_update().first()

    results: list = []
    t = threading.Thread(target=_run_create_absence, args=(results, AbsenceType.SICK, _ABS_DAY))
    t.start()
    time_module.sleep(1.5)
    assert not results, (
        "create_absence lief an der Anker-Sperre der Benutzerzeile vorbei "
        f"(Ergebnis: {results}) — die Sperre greift offenbar nur für VACATION."
    )

    holder.add(Absence(
        user_id=USER_ID, tenant_id=TENANT_ID, date=_ABS_DAY,
        type=AbsenceType.TRAINING, hours=8.0, half_day=False,
    ))
    holder.commit()
    holder.close()

    t.join(timeout=20)
    assert results == [("rejected", 409)], results

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        n = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE user_id = :u AND date = :d"),
            {"u": str(USER_ID), "d": _ABS_DAY},
        ).scalar()
    assert n == 1, f"Doppelbuchung: {n} Abwesenheiten am selben Tag"


def test_same_type_double_booking_never_raises_integrity_error(
    concurrency_seed, clean_absence_state, app_engine,
):
    """Gleicher Typ parallel: verständliche Meldung statt nacktem IntegrityError (HTTP 500).

    Sitzung A legt die Abwesenheit an und hält sie UNCOMMITTED. VOR dem Fix sah
    die Existenz-Sonde des Threads sie nicht, sein INSERT wartete am
    Unique-Index und scheiterte nach dem Commit von A mit einem ungefangenen
    ``IntegrityError`` → HTTP 500.

    Sitzung A ist hier KÜNSTLICH: sie fügt die Abwesenheit ein, ohne vorher den
    Anker zu greifen — im Produktivcode tut das keiner der vier
    ``Absence(...)``-Schreibpfade. Sie hält deshalb nur den impliziten
    ``FOR KEY SHARE`` des Fremdschlüssels.

    Seit der Anker ``FOR NO KEY UPDATE`` ist (Audit 2026-07-31, Restklasse —
    Begründung im Kopf von ``app/routers/admin_helpers.py``) kollidiert der
    Thread damit NICHT mehr: er läuft an der Benutzerzeile vorbei, seine
    Existenz-Sonde sieht die uncommittete Zeile nicht, sein INSERT wartet am
    Unique-Index und endet nach dem Commit von A im 409-Übersetzer um
    ``db.commit()``. Genau dafür ist der da. (Vorher endete derselbe Fall im
    idempotenten Skip mit 400 — deshalb lässt die Zusicherung unten beide
    Codes zu.)

    Dass zwei ECHTE, jeweils geankerte Buchungen weiterhin an der Benutzerzeile
    serialisieren, prüft
    ``test_two_real_absence_bookings_still_serialize_on_the_anchor`` — das ist
    der produktionsrelevante Fall.

    Zusicherung hier: NIE ein ``IntegrityError``/500, immer genau eine Zeile.
    """
    blocker = SessionLocal()
    set_tenant_context(blocker, TENANT_ID)
    blocker.add(Absence(
        user_id=USER_ID, tenant_id=TENANT_ID, date=_ABS_DAY2,
        type=AbsenceType.SICK, hours=8.0, half_day=False,
    ))
    blocker.flush()

    results: list = []
    t = threading.Thread(target=_run_create_absence, args=(results, AbsenceType.SICK, _ABS_DAY2))
    t.start()
    time_module.sleep(1.5)
    assert not results, f"Kein Konflikt entstanden (Ergebnis bereits da: {results})"

    blocker.commit()
    blocker.close()

    t.join(timeout=20)
    assert len(results) == 1 and results[0][0] == "rejected", (
        f"Erwartet: saubere HTTP-Ablehnung, bekommen: {results}"
    )
    assert results[0][1] in (400, 409), results

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        n = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE user_id = :u AND date = :d"),
            {"u": str(USER_ID), "d": _ABS_DAY2},
        ).scalar()
    assert n == 1, n


# --- Übernommen aus Welle C: delete_absence ohne Anker-Sperre ----------------


def _seed_absence_with_cr() -> tuple:
    """Eine Abwesenheit + einen Änderungsantrag, der sie referenziert."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        ab = Absence(
            user_id=USER_ID, tenant_id=TENANT_ID, date=_ABS_DAY,
            type=AbsenceType.SICK, hours=8.0, half_day=False,
        )
        session.add(ab)
        session.flush()
        cr = ChangeRequest(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            request_type=ChangeRequestType.UPDATE,
            status=ChangeRequestStatus.PENDING,
            entry_kind="absence",
            absence_id=ab.id,
            proposed_date=_ABS_DAY,
            reason="Audit-Test 2026-07-31 (Welle C)",
        )
        session.add(cr)
        session.commit()
        return ab.id, cr.id
    finally:
        session.close()


def _run_delete_absence(results: list, absence_id):
    """Ruft die ECHTE Endpoint-Funktion `delete_absence` auf."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == USER_ID).first()
        absences_router.delete_absence(
            absence_id=str(absence_id), db=session, current_user=me,
        )
        results.append(("deleted",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_delete_absence_locks_the_user_row_before_the_change_request(
    concurrency_seed, clean_absence_state, app_engine,
):
    """Löschen einer Abwesenheit muss dieselbe Sperrreihenfolge nutzen wie die
    Antrags-Genehmigung: Benutzerzeile ZUERST, dann die abhängige Zeile.

    ``delete_absence`` setzte referenzierende ``change_requests``-Zeilen auf
    NULL (= Sperre auf der Antragszeile), bevor es überhaupt die Benutzerzeile
    berührte — die Session ist ``autoflush=False``, der zuvor per ``db.add``
    vorgemerkte Audit-Log-INSERT (der über den Fremdschlüssel implizit ein
    ``FOR KEY SHARE`` auf ``users`` nimmt) wird erst beim späteren ``flush()``
    ausgeführt. ``review_change_request`` sperrt umgekehrt erst die
    Benutzerzeile (``FOR UPDATE``) und dann die Antragszeile — klassisches
    ABBA: beide Vorgänge blockieren sich gegenseitig, Postgres schießt einen
    von beiden mit ``deadlock detected`` ab (HTTP 500 für den Anwender).

    Ablauf: Sitzung A macht Schritt 1 der Genehmigung (Anker auf ``users``).
    Der Thread ruft ``delete_absence``. Danach macht A Schritt 2 (Antragszeile).
    Ohne den Anker in ``delete_absence`` hält der Thread zu diesem Zeitpunkt
    bereits die Antragszeile und wartet auf ``users`` → Deadlock. Mit dem Anker
    wartet er VOR der Antragszeile, A kommt durch, danach der Thread.
    """
    absence_id, cr_id = _seed_absence_with_cr()

    reviewer = SessionLocal()
    set_tenant_context(reviewer, TENANT_ID)
    # Schritt 1 von review_change_request: Anker auf der Benutzerzeile.
    assert reviewer.query(User).filter(
        User.id == USER_ID, User.tenant_id == TENANT_ID,
    ).with_for_update().first() is not None

    results: list = []
    t = threading.Thread(target=_run_delete_absence, args=(results, absence_id))
    t.start()
    time_module.sleep(1.5)
    assert not results, (
        f"Das Löschen lief trotz gehaltener Anker-Sperre durch: {results}"
    )

    # Schritt 2 von review_change_request: die Antragszeile. Ohne den Anker im
    # Löschpfad hält der Thread sie bereits → deadlock detected.
    locked_cr = reviewer.query(ChangeRequest).filter(
        ChangeRequest.id == cr_id, ChangeRequest.tenant_id == TENANT_ID,
    ).with_for_update().first()
    assert locked_cr is not None
    reviewer.commit()
    reviewer.close()

    t.join(timeout=20)
    assert results == [("deleted",)], results

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        n = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE id = :a"), {"a": str(absence_id)},
        ).scalar()
        ref = conn.execute(
            text("SELECT absence_id FROM change_requests WHERE id = :c"), {"c": str(cr_id)},
        ).scalar()
    assert n == 0
    assert ref is None


# --- Betriebsferien: Anker-Sperre vor der abhängigen Schließungszeile ---------

_CLOSURE_START = date(2099, 9, 7)  # Montag
_CLOSURE_END = date(2099, 9, 9)    # Mittwoch
# Zweiter Admin desselben Mandanten: Betriebsferien sperren ALLE Teilnehmer-
# Zeilen, also braucht die Kreuz-Konstellation eine zweite Benutzerzeile.
USER2_ID = uuid.UUID("ccccccc1-0000-4000-8000-000000000101")


@pytest.fixture
def clean_closure_state(admin_engine):
    """Leert Betriebsferien + Abwesenheiten + Audit-Zeilen des Test-Tenants.

    Legt zusätzlich einen ZWEITEN teilnehmenden Benutzer an (und räumt ihn
    wieder ab): Betriebsferien sperren die Zeilen aller Teilnehmer, ein
    Sperr-Zyklus über zwei Zeilen braucht also zwei Teilnehmer.
    """
    def _wipe():
        conn = admin_engine.connect()
        conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM absences WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM company_closures WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(USER2_ID)})
        conn.close()

    _wipe()
    conn = admin_engine.connect()
    conn.execute(text("""
        INSERT INTO users (id, tenant_id, username, email, password_hash,
                           first_name, last_name, role, weekly_hours,
                           vacation_days, work_days_per_week, is_active)
        VALUES (:id, :tid, :u, :e, 'not-real', 'C2', 'Test', 'ADMIN',
                40, 30, 5, true)
    """), {
        "id": str(USER2_ID), "tid": str(TENANT_ID),
        "u": "concurrency_test_admin2", "e": "concurrency2@test.local",
    })
    conn.close()
    yield
    _wipe()


def _run_create_closure(results: list, acting_user_id=USER_ID, name="Audit-Test Betriebsferien",
                        barrier: threading.Barrier = None):
    """Ruft die ECHTE Endpoint-Funktion `create_closure` auf."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == acting_user_id).first()
        if barrier is not None:
            barrier.wait(timeout=10)
        company_closures_router.create_closure(
            data=company_closures_router.CompanyClosureCreate(
                name=name,
                start_date=_CLOSURE_START,
                end_date=_CLOSURE_END,
            ),
            db=session, current_user=me,
        )
        results.append(("created",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except OperationalError as e:
        session.rollback()
        results.append(
            ("deadlock",) if "deadlock detected" in str(e).lower()
            else ("error", "OperationalError")
        )
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_create_closure_locks_the_user_rows_before_inserting_the_closure(
    concurrency_seed, clean_closure_state, app_engine, monkeypatch,
):
    """Betriebsferien anlegen darf die Schließungszeile NICHT vor dem Anker schreiben.

    ``company_closures.created_by`` ist ein nicht aufschiebbarer Fremdschlüssel
    auf ``users``: der INSERT der Schließungszeile nimmt auf der Zeile des
    handelnden Admins ein ``FOR KEY SHARE`` und hält es bis zum Commit. Stand er
    VOR ``_lock_participant_rows``, verlangte dieselbe Transaktion unmittelbar
    danach ein ``FOR UPDATE`` auf genau dieser Zeile (der Admin ist über
    ``receives_company_closures`` per Voreinstellung selbst Teilnehmer) — eine
    Sperr-Eskalation und damit die Umkehrung der projektweiten Reihenfolge
    Benutzer → abhängige Zeile. Eine gleichzeitige Sitzung, die den Anker
    regulär als Erstes greift (zweites ``create_closure``, ``update_closure``,
    ``absences.create_absence``, Antrags-Genehmigung), stellt sich zwischen
    beide Schritte: sie wartet auf das ``FOR KEY SHARE``, wir warten auf ihre
    Tuple-Sperre → ``deadlock detected`` (HTTP 500, voller Rollback).

    Ablauf: ``_get_workdays`` wird für diesen Test verlangsamt, um das Fenster
    zwischen den beiden Schritten von wenigen Millisekunden auf Sekunden zu
    dehnen (die Funktion läuft in BEIDEN Varianten zwischen ihnen). Der Thread
    legt die Betriebsferien an; die Hauptsitzung greift währenddessen den Anker.

    - VOR dem Fix: der Thread hält bereits das ``FOR KEY SHARE`` aus dem INSERT
      → die Hauptsitzung blockiert, der Thread eskaliert auf ``FOR UPDATE``
      → Deadlock, ``results == [("deadlock",)]``.
    - MIT dem Fix: der Thread sperrt erst NACH ``_get_workdays`` und hat noch
      nichts geschrieben → die Hauptsitzung bekommt den Anker sofort, der Thread
      wartet brav an der Benutzerzeile und kommt nach dem Commit durch.
    """
    real_get_workdays = company_closures_router._get_workdays

    def _slow_get_workdays(start, end, holidays):
        days = real_get_workdays(start, end, holidays)
        time_module.sleep(2.0)
        return days

    monkeypatch.setattr(company_closures_router, "_get_workdays", _slow_get_workdays)

    results: list = []
    t = threading.Thread(target=_run_create_closure, args=(results,))
    t.start()
    # Vor dem Fix ist der INSERT zu diesem Zeitpunkt bereits raus (er steht vor
    # der verlangsamten Arbeitstags-Ermittlung), mit dem Fix noch nicht.
    time_module.sleep(1.0)

    rival = SessionLocal()
    lock_error: list = []
    blocked_while_locked = False
    try:
        set_tenant_context(rival, TENANT_ID)
        rival.query(User).filter(
            User.id == USER_ID, User.tenant_id == TENANT_ID,
        ).with_for_update().first()
        time_module.sleep(1.5)
        # Mit dem Fix muss der Thread jetzt an der gehaltenen Anker-Sperre warten.
        blocked_while_locked = not results
        rival.commit()
    except OperationalError as e:
        rival.rollback()
        lock_error.append(str(e).splitlines()[0])
    finally:
        rival.close()

    t.join(timeout=30)

    assert not lock_error, (
        f"Die Gegenspieler-Sitzung wurde selbst abgeschossen: {lock_error}"
    )
    assert results == [("created",)], (
        "create_closure schreibt die Schließungszeile vor der Anker-Sperre — "
        f"Sperr-Eskalation auf der Admin-Zeile: {results}"
    )
    assert blocked_while_locked, (
        "create_closure lief an der gehaltenen Anker-Sperre vorbei — die "
        "Benutzerzeilen werden offenbar nicht (mehr) vor der Buchung gesperrt."
    )

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        closures = conn.execute(
            text("SELECT COUNT(*) FROM company_closures WHERE tenant_id = :t"),
            {"t": str(TENANT_ID)},
        ).scalar()
        absences = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE user_id = :u AND date BETWEEN :a AND :b"),
            {"u": str(USER_ID), "a": _CLOSURE_START, "b": _CLOSURE_END},
        ).scalar()
    assert closures == 1, closures
    assert absences == 3, f"3 Arbeitstage erwartet, gebucht: {absences}"


def test_two_parallel_closure_creations_do_not_deadlock(
    concurrency_seed, clean_closure_state, app_engine, monkeypatch,
):
    """Zwei Admins legen gleichzeitig Betriebsferien an — das darf nicht knallen.

    Das ist die Konstellation, die der Abschluss-Review zweimal gegen die
    laufende Postgres reproduziert hat. Solange die Schließungszeile VOR der
    Anker-Sperre geschrieben wurde, hielt jede der beiden Transaktionen über
    ``company_closures.created_by`` ein ``FOR KEY SHARE`` auf der Zeile IHRES
    Admins und verlangte danach ein ``FOR UPDATE`` auf BEIDE Admin-Zeilen
    (beide sind Teilnehmer):

        T1: KEY SHARE(A)                T2: KEY SHARE(B)
        T1: FOR UPDATE(A) ✓, (B) ⏳     T2: FOR UPDATE(A) ⏳

    → Zyklus, ``deadlock detected``, HTTP 500 mit vollem Rollback für den
    abgeschossenen Vorgang.

    MIT der vorgezogenen Sperre schreibt keine der beiden Transaktionen etwas,
    bevor sie alle Teilnehmer-Zeilen in EINER nach ``id`` sortierten Anweisung
    gesperrt hat: die zweite wartet vollständig, läuft danach durch und sieht
    die bereits gebuchten Abwesenheiten (überspringt sie).

    ``_get_workdays`` wird verlangsamt, damit beide Transaktionen die Phase
    zwischen den beiden Schritten garantiert überlappen — ohne das Fenster wäre
    der Zyklus nur ein Millisekunden-Zufall.
    """
    real_get_workdays = company_closures_router._get_workdays

    def _slow_get_workdays(start, end, holidays):
        days = real_get_workdays(start, end, holidays)
        time_module.sleep(2.0)
        return days

    monkeypatch.setattr(company_closures_router, "_get_workdays", _slow_get_workdays)

    results: list = []
    barrier = threading.Barrier(2)
    t1 = threading.Thread(
        target=_run_create_closure, args=(results, USER_ID, "Betriebsferien A", barrier),
    )
    t2 = threading.Thread(
        target=_run_create_closure, args=(results, USER2_ID, "Betriebsferien B", barrier),
    )
    t1.start(); t2.start()
    t1.join(timeout=40); t2.join(timeout=40)

    assert results == [("created",), ("created",)], (
        "Zwei gleichzeitige Betriebsferien liefen in einen Sperr-Zyklus "
        f"(Schließungszeile vor der Anker-Sperre geschrieben): {results}"
    )

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        closures = conn.execute(
            text("SELECT COUNT(*) FROM company_closures WHERE tenant_id = :t"),
            {"t": str(TENANT_ID)},
        ).scalar()
        absences = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE tenant_id = :t AND date BETWEEN :a AND :b"),
            {"t": str(TENANT_ID), "a": _CLOSURE_START, "b": _CLOSURE_END},
        ).scalar()
    assert closures == 2, closures
    # 2 Teilnehmer × 3 Arbeitstage — der Verlierer sieht die bereits gebuchten
    # Tage unter der Anker-Sperre und überspringt sie (keine Doppelbuchung).
    assert absences == 6, f"Erwartet 6 Abwesenheiten (2 MA × 3 Tage), gebucht: {absences}"


def _run_delete_closure(results: list, closure_id):
    """Ruft die ECHTE Endpoint-Funktion `delete_closure` auf."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == USER_ID).first()
        company_closures_router.delete_closure(
            closure_id=str(closure_id), db=session, current_user=me,
        )
        results.append(("deleted",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except OperationalError as e:
        session.rollback()
        results.append(
            ("deadlock",) if "deadlock detected" in str(e).lower()
            else ("error", "OperationalError")
        )
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_delete_closure_locks_the_user_rows_before_touching_absences(
    concurrency_seed, clean_closure_state, app_engine,
):
    """Betriebsferien löschen muss dieselbe Reihenfolge nutzen wie Anlegen/Ändern.

    ``delete_closure`` war der einzige der drei Betriebsferien-Pfade ganz ohne
    Anker: er löschte die generierten Abwesenheiten (Sperren auf ``absences``),
    schrieb die Summen-Audit-Zeile (``FOR KEY SHARE`` auf der Admin-Zeile) und
    ließ ggf. den #314-Re-Split weitere Abwesenheiten umschreiben — alles in der
    Reihenfolge Abwesenheit → Benutzer. Gegen ein gleichzeitiges
    ``create_closure``/``create_absence`` (Benutzer → Abwesenheit) ist das das
    bekannte ABBA.

    Ablauf wie bei ``test_delete_absence_locks_the_user_row_before_the_change_request``:
    Sitzung A macht Schritt 1 eines Buchungspfads (Anker auf der Benutzerzeile),
    der Thread löscht die Betriebsferien, danach macht A Schritt 2 (Sperre auf
    den Abwesenheiten des MA).

    - OHNE Anker im Löschpfad hat der Thread die Abwesenheiten zu diesem
      Zeitpunkt bereits gelöscht (Sperren darauf) und wartet am Commit auf die
      ``FOR KEY SHARE`` seiner Audit-Zeile — die A per ``FOR UPDATE`` hält.
      A wartet auf die Abwesenheiten → ``deadlock detected``.
    - MIT Anker wartet der Thread VOR den Abwesenheiten, A kommt durch, danach
      der Thread.
    """
    session = SessionLocal()
    set_tenant_context(session, TENANT_ID)
    me = session.query(User).filter(User.id == USER_ID).first()
    created = company_closures_router.create_closure(
        data=company_closures_router.CompanyClosureCreate(
            name="Zu löschende Betriebsferien",
            start_date=_CLOSURE_START,
            end_date=_CLOSURE_END,
        ),
        db=session, current_user=me,
    )
    closure_id = created.id
    session.close()

    holder = SessionLocal()
    set_tenant_context(holder, TENANT_ID)
    assert holder.query(User).filter(
        User.id == USER_ID, User.tenant_id == TENANT_ID,
    ).with_for_update().first() is not None

    results: list = []
    t = threading.Thread(target=_run_delete_closure, args=(results, closure_id))
    t.start()
    time_module.sleep(1.0)
    assert not results, (
        "delete_closure lief an der gehaltenen Anker-Sperre komplett vorbei: "
        f"{results}"
    )

    # Schritt 2 der Buchungspfade: die Abwesenheiten des MA sperren. Ohne Anker
    # im Löschpfad hält der Thread sie bereits → Zyklus.
    probe_error: list = []
    try:
        holder.query(Absence).filter(
            Absence.user_id == USER_ID, Absence.tenant_id == TENANT_ID,
        ).with_for_update().all()
        holder.commit()
    except OperationalError as e:
        holder.rollback()
        probe_error.append(str(e).splitlines()[0])
    finally:
        holder.close()

    t.join(timeout=30)
    assert not probe_error, (
        f"Die Gegenspieler-Sitzung wurde selbst abgeschossen: {probe_error}"
    )
    assert results == [("deleted",)], (
        "delete_closure fasst die Abwesenheiten vor der Anker-Sperre an "
        f"(Reihenfolge Abwesenheit → Benutzer): {results}"
    )

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        closures = conn.execute(
            text("SELECT COUNT(*) FROM company_closures WHERE tenant_id = :t"),
            {"t": str(TENANT_ID)},
        ).scalar()
        absences = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE tenant_id = :t"),
            {"t": str(TENANT_ID)},
        ).scalar()
    assert closures == 0, closures
    assert absences == 0, absences


# =============================================================================
# Restklasse aus dem Abschluss-Review: Kreuz-Sperren über eine ZWEITE Zeile
# =============================================================================
#
# Der Abschluss-Review (`.superpowers/sdd/audit-2026-07-31/fix-closure-deadlock.md`,
# Punkt 7.1/7.2) hat zwei Konstellationen benannt und bewusst offen gelassen:
#
#   (1) Ein Buchungspfad sperrt die Zeile der MITARBEITERIN und schreibt danach
#       eine Audit-Zeile mit dem handelnden ADMIN als Urheber. Deren
#       Fremdschlüssel nimmt ein ``FOR KEY SHARE`` auf einer ZWEITEN, nicht
#       geankerten Benutzerzeile. Gegen die sortierte Teilnehmer-Sperre der
#       Betriebsferien ist das ein Zyklus, sobald die Admin-Zeile VOR der
#       Mitarbeiterzeile sortiert.
#   (2) ``admin_time_entries`` nimmt überhaupt nie einen Anker: es sperrt die
#       ZEITEINTRAGS-Zeile und braucht danach ``FOR KEY SHARE`` auf den
#       Benutzerzeilen — während die Betriebsferien die Benutzerzeilen halten
#       und danach genau diesen Zeiteintrag löschen.
#
# Beide Zyklen brauchen ZWEI Objekte und ZWEI gleichzeitige Vorgänge; eine
# Sperr-Eskalation auf EINER Zeile deadlockt nicht.
#
# Gemessene Konfliktmatrix von Postgres (eigene Messung gegen die laufende DB,
# deckt sich mit der Dokumentation):
#
#     gehalten \ angefordert   KEY SHARE   SHARE   NO KEY UPDATE   UPDATE
#     FOR KEY SHARE            frei        frei    frei            KONFLIKT
#     FOR SHARE                frei        frei    KONFLIKT        KONFLIKT
#     FOR NO KEY UPDATE        frei        KONFLIKT KONFLIKT       KONFLIKT
#     FOR UPDATE               KONFLIKT    KONFLIKT KONFLIKT       KONFLIKT
#
# Daraus folgt die gewählte Lösung: die Anker gehen auf ``FOR NO KEY UPDATE``.
# Sie schließen sich weiterhin GEGENSEITIG aus (Zeile 3, Spalte 3) — die
# Serialisierung aller Buchungspfade pro Mitarbeiterin bleibt also erhalten —,
# kollidieren aber nicht mehr mit dem impliziten ``FOR KEY SHARE`` jedes
# Kind-INSERTs (Zeile 3, Spalte 1). Genau diese Kollision war die einzige
# Wartekante, die die beiden Zyklen oben schließt.

_XLOCK_DAY = _CLOSURE_START  # Montag, liegt in der Betriebsferien-Spanne

# Dritter Benutzer: ein handelnder ADMIN, dessen UUID VOR der des Mitarbeiters
# sortiert. Die Betriebsferien sperren alle Teilnehmer in EINER nach ``id``
# sortierten Anweisung — ohne diese Sortierlage greifen sie die Mitarbeiter-
# zeile zuerst und der Zyklus (1) kommt gar nicht zustande.
ADMIN_LOW_ID = uuid.UUID("ccccccc1-0000-4000-8000-00000000000a")
assert str(ADMIN_LOW_ID) < str(USER_ID), "Testvoraussetzung: Admin-UUID sortiert vor der MA-UUID"


@pytest.fixture
def clean_cross_lock_state(admin_engine):
    """Wie ``clean_closure_state``, zusätzlich mit dem VOR-sortierenden Admin."""
    def _wipe():
        conn = admin_engine.connect()
        conn.execute(text("DELETE FROM time_entry_audit_logs WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM change_requests WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM absences WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM company_closures WHERE tenant_id = :t"), {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM users WHERE id IN (:u1, :u2)"),
                     {"u1": str(USER2_ID), "u2": str(ADMIN_LOW_ID)})
        conn.close()

    _wipe()
    conn = admin_engine.connect()
    for uid, uname, mail, first in (
        (USER2_ID, "concurrency_test_admin2", "concurrency2@test.local", "C2"),
        (ADMIN_LOW_ID, "concurrency_test_admin_low", "concurrency_low@test.local", "CL"),
    ):
        conn.execute(text("""
            INSERT INTO users (id, tenant_id, username, email, password_hash,
                               first_name, last_name, role, weekly_hours,
                               vacation_days, work_days_per_week, is_active)
            VALUES (:id, :tid, :u, :e, 'not-real', :f, 'Test', 'ADMIN',
                    40, 30, 5, true)
        """), {"id": str(uid), "tid": str(TENANT_ID), "u": uname, "e": mail, "f": first})
    conn.close()
    yield
    _wipe()


def _seed_time_entry(day=_XLOCK_DAY, user_id=USER_ID) -> uuid.UUID:
    """Ein abgeschlossener Zeiteintrag am Zieltag (09:00–17:00, 30 min Pause)."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        entry = TimeEntry(
            user_id=user_id, tenant_id=TENANT_ID, date=day,
            start_time=time(9, 0), end_time=time(17, 0), break_minutes=30,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry.id
    finally:
        session.close()


def _slow(fn, seconds: float):
    """Verlangsamt ``fn`` um ``seconds`` VOR dem eigentlichen Aufruf."""
    def _wrapped(*args, **kwargs):
        time_module.sleep(seconds)
        return fn(*args, **kwargs)
    return _wrapped


def _run_create_absence_for(results: list, acting_user_id, target_user_id, day,
                            absence_type=AbsenceType.SICK, barrier=None):
    """Ruft die ECHTE ``create_absence``.

    ``target_user_id=None`` = Eigenbuchung (``user_id`` im Payload weglassen —
    ein Nicht-Admin, der ihn setzt, bekommt 403).
    """
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == acting_user_id).first()
        if barrier is not None:
            barrier.wait(timeout=15)
        absences_router.create_absence(
            absence_data=AbsenceCreate(
                date=day, type=absence_type, hours=8.0,
                user_id=str(target_user_id) if target_user_id is not None else None,
            ),
            db=session, current_user=me,
        )
        results.append(("created",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except OperationalError as e:
        session.rollback()
        results.append(
            ("deadlock",) if "deadlock detected" in str(e).lower()
            else ("error", "OperationalError")
        )
    except IntegrityError:
        session.rollback()
        results.append(("error", "IntegrityError"))
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def _run_admin_update_time_entry(results: list, acting_user_id, entry_id, note):
    """Ruft die ECHTE ``admin_time_entries.admin_update_time_entry``."""
    session = SessionLocal()
    try:
        set_tenant_context(session, TENANT_ID)
        me = session.query(User).filter(User.id == acting_user_id).first()
        admin_time_entries_router.admin_update_time_entry(
            entry_id=str(entry_id),
            entry_data=TimeEntryUpdate(note=note),
            db=session, current_user=me,
        )
        results.append(("updated",))
    except HTTPException as e:
        session.rollback()
        results.append(("rejected", e.status_code))
    except OperationalError as e:
        session.rollback()
        results.append(
            ("deadlock",) if "deadlock detected" in str(e).lower()
            else ("error", "OperationalError")
        )
    except Exception as e:  # pragma: no cover — surface the failure
        session.rollback()
        results.append(("error", type(e).__name__))
    finally:
        session.close()


def test_absence_booking_by_an_admin_does_not_deadlock_with_a_parallel_closure(
    concurrency_seed, clean_cross_lock_state, app_engine, monkeypatch,
):
    """Restklasse (1): Buchung sperrt die MA-Zeile, Audit-Zeile greift die ADMIN-Zeile.

    ``create_absence`` sperrt die Zeile der Mitarbeiterin (Anker) und löscht
    danach die Zeiteinträge des Tages — mit Audit-Zeile, deren ``changed_by``
    auf den handelnden Admin zeigt. Dieser Fremdschlüssel nimmt ein
    ``FOR KEY SHARE`` auf einer ZWEITEN Benutzerzeile, die der Anker nicht
    enthält. Die Betriebsferien sperren umgekehrt ALLE Teilnehmerzeilen in
    EINER nach ``id`` sortierten Anweisung — und die Admin-Zeile sortiert hier
    absichtlich VOR der Mitarbeiterzeile:

        T1 (Buchung):  FOR UPDATE(MA) ✓            → KEY SHARE(Admin) ⏳
        T2 (Ferien):   FOR UPDATE(Admin) ✓         → FOR UPDATE(MA)   ⏳
                                                   → Zyklus, deadlock detected

    Der Zyklus verschwindet, sobald der Anker ``FOR NO KEY UPDATE`` ist: das
    ``FOR KEY SHARE`` von T1 kollidiert dann nicht mehr mit der von T2
    gehaltenen Sperre (gemessene Matrix im Kopf dieses Abschnitts), T1 läuft
    durch, gibt die MA-Zeile frei und T2 kommt danach dran. Die gegenseitige
    Ausschlusswirkung der beiden Anker bleibt (NO KEY UPDATE ⊥ NO KEY UPDATE) —
    T2 wartet weiterhin auf T1.

    Die beiden Verlangsamungen dehnen das Fenster zwischen „Anker" und
    „abhängiger Schreibzugriff" von Millisekunden auf Sekunden; ohne sie wäre
    der Zyklus reiner Zeitzufall.
    """
    _seed_time_entry()

    monkeypatch.setattr(
        absences_router, "_create_audit_log",
        _slow(absences_router._create_audit_log, 2.5),
    )
    monkeypatch.setattr(
        company_closures_router, "_get_workdays",
        _slow(company_closures_router._get_workdays, 1.0),
    )

    results: list = []
    barrier = threading.Barrier(2)
    t_absence = threading.Thread(
        target=_run_create_absence_for,
        args=(results, ADMIN_LOW_ID, USER_ID, _XLOCK_DAY, AbsenceType.SICK, barrier),
    )
    t_closure = threading.Thread(
        target=_run_create_closure,
        args=(results, USER2_ID, "Kreuzsperren-Betriebsferien", barrier),
    )
    t_absence.start(); t_closure.start()
    t_absence.join(timeout=60); t_closure.join(timeout=60)

    assert ("deadlock",) not in results, (
        "Sperr-Zyklus über zwei Benutzerzeilen: die Buchung hält die MA-Zeile "
        "und will die Admin-Zeile (Audit-Fremdschlüssel), die Betriebsferien "
        f"halten die Admin-Zeile und wollen die MA-Zeile. Ergebnis: {results}"
    )
    assert sorted(results) == [("created",), ("created",)], results


def test_admin_time_entry_edit_does_not_deadlock_with_a_parallel_closure(
    concurrency_seed, clean_cross_lock_state, app_engine, monkeypatch,
):
    """Restklasse (2): ``admin_time_entries`` nimmt nie einen Anker.

    ``admin_update_time_entry`` sperrt die ZEITEINTRAGS-Zeile (``FOR UPDATE``)
    und schreibt danach eine Audit-Zeile, deren Fremdschlüssel ``FOR KEY SHARE``
    auf der Mitarbeiter- UND der Admin-Zeile nehmen. Die Betriebsferien halten
    genau diese Benutzerzeilen und löschen danach die Zeiteinträge der
    abgedeckten Tage:

        T1 (Zeitkorrektur): FOR UPDATE(Zeiteintrag) ✓ → KEY SHARE(MA)        ⏳
        T2 (Ferien):        FOR UPDATE(MA)          ✓ → FOR UPDATE(Zeiteintrag) ⏳
                                                      → Zyklus, deadlock detected

    Bemerkenswert: dieser Zyklus braucht nur EINE Benutzerzeile — die zweite
    Ecke ist die Zeiteintrags-Zeile. Er ist damit deutlich leichter erreichbar
    als (1) und hängt an keiner Sortierlage.

    Auch hier reicht ``FOR NO KEY UPDATE`` am Anker: T1s ``FOR KEY SHARE``
    kollidiert nicht mehr mit T2s Sperre, T1 kommt durch, gibt die
    Zeiteintrags-Zeile frei, T2 löscht sie danach. Ein Anker in
    ``admin_time_entries`` ist dafür NICHT nötig (und wäre teuer: er würde
    jede Zeitkorrektur zusätzlich auf der Admin-Zeile serialisieren).
    """
    entry_id = _seed_time_entry()

    monkeypatch.setattr(
        admin_time_entries_router, "_create_audit_log",
        _slow(admin_time_entries_router._create_audit_log, 2.5),
    )
    monkeypatch.setattr(
        company_closures_router, "_get_workdays",
        _slow(company_closures_router._get_workdays, 1.0),
    )

    results: list = []
    t_edit = threading.Thread(
        target=_run_admin_update_time_entry,
        args=(results, USER2_ID, entry_id, "Kreuzsperren-Korrektur"),
    )
    t_closure = threading.Thread(
        target=_run_create_closure,
        args=(results, USER2_ID, "Kreuzsperren-Betriebsferien 2"),
    )
    t_edit.start(); t_closure.start()
    t_edit.join(timeout=60); t_closure.join(timeout=60)

    assert ("deadlock",) not in results, (
        "Sperr-Zyklus Zeiteintrag ↔ Benutzerzeile: die Zeitkorrektur hält den "
        "Zeiteintrag und will die Benutzerzeile (Audit-Fremdschlüssel), die "
        f"Betriebsferien halten die Benutzerzeile und wollen den Zeiteintrag: {results}"
    )
    assert sorted(results) == [("created",), ("updated",)], results


def test_two_real_absence_bookings_still_serialize_on_the_anchor(
    concurrency_seed, clean_absence_state, app_engine,
):
    """Gegenprobe zur schwächeren Sperrform: die Ausschlusswirkung bleibt.

    ``FOR NO KEY UPDATE`` kollidiert nicht mehr mit dem impliziten
    ``FOR KEY SHARE`` eines Kind-INSERTs — das ist der Zweck der Änderung. Es
    kollidiert aber weiterhin mit sich selbst, und JEDER produktive
    Absence-Schreibpfad greift den Anker (``create_absence``,
    ``review_vacation_request``, ``review_change_request``, Betriebsferien —
    die vier ``Absence(...)``-Konstruktionsstellen im Produktivcode). Zwei
    ECHTE gleichzeitige Buchungen serialisieren also unverändert an der
    Benutzerzeile: eine legt an, die andere sieht die Zeile danach im
    geprüften Zweig und wird sauber abgelehnt — kein ``IntegrityError``,
    keine Doppelbuchung.

    Diese Zusicherung ist genau die, die der Abschluss-Review als Argument
    GEGEN die schwächere Sperrform angeführt hat (dort belegt über eine
    künstliche Sitzung, die eine Abwesenheit OHNE Anker einfügt). Hier wird sie
    über die echten Endpunkt-Funktionen geprüft — der produktionsrelevante
    Fall.
    """
    results: list = []
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(
            target=_run_create_absence_for,
            args=(results, USER_ID, None, _ABS_DAY, AbsenceType.SICK, barrier),
        )
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)

    assert ("error", "IntegrityError") not in results, results
    assert sorted(results) == [("created",), ("rejected", 400)], (
        "Erwartet: eine Buchung legt an, die zweite wird im geprüften Zweig "
        f"abgelehnt (400). Bekommen: {results}"
    )

    with app_engine.connect() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(TENANT_ID)})
        n = conn.execute(
            text("SELECT COUNT(*) FROM absences WHERE user_id = :u AND date = :d"),
            {"u": str(USER_ID), "d": _ABS_DAY},
        ).scalar()
    assert n == 1, f"Doppelbuchung: {n} Abwesenheiten am selben Tag"


def test_no_router_locks_user_rows_directly():
    """Statische Absicherung der Regel: Benutzerzeilen nur über den Helfer sperren.

    Der Fix der Restklasse besteht darin, dass JEDE Anker-Sperre auf ``users``
    ``FOR NO KEY UPDATE`` ist (siehe Kopf von ``app/routers/admin_helpers.py``).
    Ein einzelnes neu hinzugefügtes ``db.query(User)…with_for_update()`` in
    einem Router holt die Deadlock-Klasse vollständig zurück — und zwar
    unbemerkt, weil es sich nur unter echter Parallelität zeigt.

    Dieser Test ist die Leitplanke: er parst die Router-Quellen und lässt eine
    ``with_for_update``-Kette über ``query(User)`` ausschließlich in
    ``admin_helpers`` und nur mit ``key_share=True`` zu. Er braucht keine
    Datenbank — er liegt hier, weil die Regel hier begründet und belegt wird.
    """
    import ast
    import pathlib

    routers = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"
    assert routers.is_dir(), routers

    def _locks_user(call: ast.Call) -> bool:
        """Läuft die Aufrufkette dieses with_for_update über ``query(User)``?"""
        node = call.func
        while True:
            if isinstance(node, ast.Attribute):
                node = node.value
            elif isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute) and f.attr == "query"
                        and any(isinstance(a, ast.Name) and a.id == "User"
                                for a in node.args)):
                    return True
                node = f
            else:
                return False

    offenders: list = []
    for path in sorted(routers.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "with_for_update"):
                continue
            if not _locks_user(node):
                continue
            key_share = any(
                kw.arg == "key_share"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
            )
            if path.name != "admin_helpers.py" or not key_share:
                offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, (
        "Benutzerzeilen werden direkt gesperrt statt über "
        "`admin_helpers.lock_user_row(s)` — das holt die Kreuz-Sperren-"
        "Deadlocks zurück (Begründung im Kopf von admin_helpers.py). "
        f"Fundstellen: {offenders}"
    )
