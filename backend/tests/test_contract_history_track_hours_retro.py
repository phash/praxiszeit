"""Teil A, Task 10: rückwirkende Umstellung der Stundenzählung (``track_hours``)
— Variante A (Spec A3).

Die Umstellung läuft über DENSELBEN Rechenpfad wie eine Stundenänderung
(``wh_change_service.run_change``): alle Wochentage gelten als geändert, die
Zeiteinträge im Wirkungsbereich werden nach dem Snapshot des Tages gekappt
(eingeschaltet) bzw. entkappt (ausgeschaltet), die Abwesenheiten auf das
Tagessoll bzw. 0 gezogen. Anerkannte Einträge (``credit_override``) bleiben
unberührt; Löschen stellt den Ausgangszustand bitgleich wieder her.

Dokumentierte Entscheidung: ``clamp_grace_minutes`` wird beim Entkappen NICHT
zurückgesetzt (``clamp`` liefert dort ``grace_minutes=None`` = „Wert stehen
lassen", E79). Der gespeicherte Puffer ist nur die Erinnerung, mit welchem
Puffer der Eintrag zuletzt gekappt wurde — an einem Tag ohne Stundenzählung
wirkt er nicht. Der Bitgleichheits-Test vergleicht ihn deshalb nicht."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, TimeEntry, WorkingHoursChange
from app.services import calculation_service as cs
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    RETRO_REASON, absence, add_row, admin_client, entry, freeze, reclamp_logs, t,
)
from tests.work_blocks_fixtures import block_week

TODAY = date(2026, 11, 3)
EFF = date(2026, 6, 1)
ENTRY_DAY = date(2026, 6, 2)
ABSENCE_DAY = date(2026, 6, 3)
# 08:00–12:00 Mo–Fr, Pause 0 → Tagessoll 4,00 h (derive_targets).
WEEK = block_week(mon=[("08:00", "12:00")], tue=[("08:00", "12:00")], wed=[("08:00", "12:00")],
                  thu=[("08:00", "12:00")], fri=[("08:00", "12:00")])


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch, TODAY)
    yield admin_client(db, test_admin)
    test_app.dependency_overrides.clear()


def url(user) -> str:
    return f"/api/admin/users/{user.id}/working-hours-changes"


def body(track_hours: bool, **extra) -> dict:
    return {"effective_from": EFF.isoformat(), "blocks": WEEK, "track_hours": track_hours,
            **RETRO_REASON, **extra}


def _set_mode(db, user, tracked: bool) -> None:
    """Person mit Verlaufszeile ab 01.01.2026 (Blöcke 08–12 Mo–Fr) im Modus ``tracked``."""
    user.track_hours = tracked
    db.commit()
    add_row(db, user, date(2026, 1, 1), week=WEEK, track_hours=tracked)
    db.refresh(user)


def _entry_state(db, e):
    db.expire_all()
    e = db.get(TimeEntry, e.id)
    return (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, int(e.uncredited_minutes or 0))


def _hours(db, a) -> float:
    db.expire_all()
    return float(db.get(Absence, a.id).hours)


def state(db, user) -> tuple:
    """Alles, was die Rücknahme wiederherstellen muss (ohne ``clamp_grace_minutes``,
    siehe Modul-Docstring)."""
    db.expire_all()
    entries = tuple(
        (e.id, e.date, e.start_time, e.end_time, e.raw_start_time, e.raw_end_time,
         int(e.uncredited_minutes or 0), Decimal(str(e.net_hours)), bool(e.auto_closed))
        for e in db.query(TimeEntry).filter(TimeEntry.user_id == user.id).order_by(TimeEntry.date, TimeEntry.id)
    )
    absences = tuple(
        (a.id, Decimal(str(a.hours)), Decimal(str(a.raw_hours)) if a.raw_hours is not None else None)
        for a in db.query(Absence).filter(Absence.user_id == user.id).order_by(Absence.date)
    )
    balances = tuple(cs.get_monthly_balance(db, user, 2026, m) for m in range(1, 13))
    return entries, absences, balances


def test_track_hours_on_from_june_retroactive(db, test_user, client):   # Spec A3
    u = test_user
    _set_mode(db, u, False)
    e = entry(db, u, ENTRY_DAY, t(7), t(13))
    vac = absence(db, u, ABSENCE_DAY, AbsenceType.VACATION, hours=0.0)
    may_before = cs.get_monthly_balance(db, u, 2026, 5)
    june_before = cs.get_monthly_balance(db, u, 2026, 6)

    r = client.post(url(u), json=body(True))
    assert r.status_code == 201, r.text

    assert _hours(db, vac) == 4.0                  # Tagessoll aus den Blöcken, nicht 8
    assert _entry_state(db, e) == (t(7, 45), t(12, 15), t(7), t(13), 0)
    db.expire_all()
    assert cs.get_monthly_balance(db, u, 2026, 5) == may_before
    # Saldo Juni neu: Soll (22 Werktage − 1 Urlaubstag) × 4 h, Ist = gekappter Eintrag 4,5 h.
    june_after = cs.get_monthly_balance(db, u, 2026, 6)
    assert june_after != june_before
    assert cs.get_monthly_target(db, u, 2026, 6) == Decimal("84")
    assert cs.get_monthly_actual(db, u, 2026, 6) == Decimal("4.5")
    assert june_after == Decimal("4.5") - Decimal("84")
    assert reclamp_logs(db, u, summary=True)


def test_delete_restores_bit_identical(db, test_user, client):
    u = test_user
    _set_mode(db, u, False)
    entry(db, u, ENTRY_DAY, t(7), t(13))
    entry(db, u, date(2026, 6, 8), t(8, 30), t(11))
    absence(db, u, ABSENCE_DAY, AbsenceType.VACATION, hours=0.0)
    absence(db, u, date(2026, 6, 4), AbsenceType.SICK, hours=0.0)
    absence(db, u, date(2026, 6, 5), AbsenceType.VACATION, hours=0.0, half_day=True)
    snapshot = state(db, u)

    r = client.post(url(u), json=body(True))
    assert r.status_code == 201, r.text
    assert state(db, u) != snapshot, "Vorbedingung: das Einschalten hat etwas bewegt"

    db.expire_all()
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == u.id, WorkingHoursChange.effective_from == EFF).one()
    resp = client.request("DELETE", f"{url(u)}/{change.id}", json=RETRO_REASON)
    assert resp.status_code in (200, 204), resp.text
    assert state(db, u) == snapshot


def _delete_change(db, client, u):
    db.expire_all()
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == u.id, WorkingHoursChange.effective_from == EFF).one()
    resp = client.request("DELETE", f"{url(u)}/{change.id}", json=RETRO_REASON)
    assert resp.status_code in (200, 204), resp.text


def test_untracked_auto_close_round_trip_never_restores_2359(db, test_user, client):
    """Fix-Runde 1 (Finding 1): bewusst NICHT bitgleich. Ein ohne
    Stundenzählung automatisch geschlossener Eintrag steht auf 23:59 ohne
    Rohende. Das Einschalten kappt ihn (Ende auf der Hülle bzw. Kollaps,
    Rohende 23:59); die Rücknahme entkappt nach P18 nur bis zum wirksamen
    Ende — das synthetische 23:59 wird nie wieder angerechnet (Sicherheitsfund
    F1: sonst stünden ~16 h ohne Ausstempeln in §16-Belegen und im § 3 ArbZG)."""
    u = test_user
    _set_mode(db, u, False)
    late = entry(db, u, date(2026, 6, 9), t(19), t(23, 59), auto_closed=True)
    early = entry(db, u, date(2026, 6, 10), t(8), t(23, 59), auto_closed=True)

    assert client.post(url(u), json=body(True)).status_code == 201
    assert _entry_state(db, late) == (t(19), t(19), t(19), t(23, 59), 0)
    assert _entry_state(db, early) == (t(8), t(12, 15), None, t(23, 59), 0)

    _delete_change(db, client, u)
    assert _entry_state(db, late) == (t(19), t(19), None, t(23, 59), 0)
    assert _entry_state(db, early) == (t(8), t(12, 15), None, t(23, 59), 0)


def test_track_hours_off_unclamps_and_zeroes_absences(db, test_user, client):
    u = test_user
    _set_mode(db, u, True)
    e = entry(db, u, ENTRY_DAY, t(7, 45), t(12, 15), raw_start=t(7), raw_end=t(13))
    sick = absence(db, u, ABSENCE_DAY, AbsenceType.SICK, hours=4.0)
    vac = absence(db, u, date(2026, 6, 4), AbsenceType.VACATION, hours=4.0)

    r = client.post(url(u), json=body(False))
    assert r.status_code == 201, r.text

    assert _entry_state(db, e) == (t(7), t(13), None, None, 0)
    assert _hours(db, sick) == 0.0
    assert _hours(db, vac) == 0.0
    db.expire_all()
    assert float(db.get(Absence, sick.id).raw_hours) == 4.0     # raw_hours bleibt
    assert float(db.get(Absence, vac.id).raw_hours) == 4.0


def test_credit_override_entry_untouched(db, test_user, client):
    u = test_user
    _set_mode(db, u, False)
    e = entry(db, u, ENTRY_DAY, t(7), t(13), credit_override=True)
    before = _entry_state(db, e)

    r = client.post(url(u), json=body(True))
    assert r.status_code == 201, r.text
    assert _entry_state(db, e) == before


def test_changed_weekdays_all_on_track_hours_change(db, test_user, client):
    u = test_user
    _set_mode(db, u, False)
    r = client.post(url(u) + "/preview", json=body(True))
    assert r.status_code == 200, r.text
    assert r.json()["changed_weekdays"] == [0, 1, 2, 3, 4]
    # Gegenprobe: unveränderte Blöcke und Stundenzählung → kein Wochentag.
    r = client.post(url(u) + "/preview", json=body(False))
    assert r.status_code == 200, r.text
    assert r.json()["changed_weekdays"] == []


def test_blocks_with_track_hours_off_are_stored_and_inert(db, test_user, client):   # Review Focus 5
    u = test_user
    add_row(db, u, date(2026, 1, 1), weekly_hours=40, track_hours=True)
    e = entry(db, u, ENTRY_DAY, t(7), t(13))

    r = client.post(url(u), json=body(False))
    assert r.status_code == 201, r.text
    db.expire_all()
    row = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == u.id, WorkingHoursChange.effective_from == EFF).one()
    assert row.blocks is not None and row.track_hours is False
    assert _entry_state(db, e) == (t(7), t(13), None, None, 0)


def test_switch_off_then_delete_restores_tracked_auto_close(db, test_user, client):
    """Gegenrichtung zur Rücknahme: gekappter Auto-Close (Ende auf der Hülle,
    Rohende 23:59) → ausgeschaltet bleibt das wirksame Ende (P18) → gelöscht
    bitgleich."""
    u = test_user
    _set_mode(db, u, True)
    e = entry(db, u, ENTRY_DAY, t(8), t(12, 15), raw_end=t(23, 59), auto_closed=True)
    sick = absence(db, u, ABSENCE_DAY, AbsenceType.SICK, hours=4.0)
    snapshot = state(db, u)

    r = client.post(url(u), json=body(False))
    assert r.status_code == 201, r.text
    # P18: das wirksame Ende bleibt die Eingabe, nie das synthetische 23:59.
    assert _entry_state(db, e) == (t(8), t(12, 15), None, t(23, 59), 0)
    assert _hours(db, sick) == 0.0

    resp = client.request("DELETE", f"{url(u)}/{r.json()['id']}", json=RETRO_REASON)
    assert resp.status_code in (200, 204), resp.text
    assert state(db, u) == snapshot


def test_always_untracked_person_hours_change_touches_nothing(db, test_user, client):
    """Fix-Runde 1 (Finding 2): vorher UND nachher ohne Stundenzählung — eine
    gewöhnliche rückwirkende Stundenänderung lässt Altbestand stehen (wie vor
    Task 10): keine Rückrechnung, keine Entkappung, kein Grund nötig, keine
    Einzelprotokolle."""
    from app.models import TimeEntryAuditLog
    u = test_user
    _set_mode(db, u, False)
    sick = absence(db, u, ABSENCE_DAY, AbsenceType.SICK, hours=8.0)
    e = entry(db, u, ENTRY_DAY, t(7, 45), t(12, 15), raw_start=t(7), raw_end=t(13))
    before = _entry_state(db, e)

    r = client.post(url(u), json={"effective_from": EFF.isoformat(), "weekly_hours": 30})
    assert r.status_code == 201, r.text
    assert _hours(db, sick) == 8.0
    assert _entry_state(db, e) == before
    db.expire_all()
    assert db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == u.id, TimeEntryAuditLog.source == "wh_change").count() == 0
    assert reclamp_logs(db, u, summary=False) == []


def _row_count(db, u) -> int:
    db.expire_all()
    return db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == u.id).count()


def test_retroactive_switch_on_without_reason_is_400_and_previewed_as_shortening(db, test_user, client):
    """F031: die Schutzpaket-Pflicht gilt auch für reine Vertragsänderungen. Das
    Einschalten ab 01.06. kappt den Eintrag und hebt das Soll → Verkürzung → 400
    ohne Grund, nichts geschrieben; die Vorschau meldet sie."""
    u = test_user
    _set_mode(db, u, False)
    e = entry(db, u, ENTRY_DAY, t(7), t(13))
    rows = _row_count(db, u)
    plain = {"effective_from": EFF.isoformat(), "blocks": WEEK, "track_hours": True}

    p = client.post(url(u) + "/preview", json=plain)
    assert p.status_code == 200, p.text
    assert p.json()["is_shortening"] is True
    assert {"entries", "saldo"} & set(p.json()["shortening_reasons"])

    r = client.post(url(u), json=plain)
    assert r.status_code == 400, r.text
    assert "Rückwirkende Verkürzung" in r.json()["detail"]
    assert _row_count(db, u) == rows
    assert _entry_state(db, e) == (t(7), t(13), None, None, 0)


def test_retroactive_switch_off_with_negative_balance_needs_no_reason(db, test_user, client):
    """F031 (Gegenprobe): Ausschalten hebt das Soll auf und entkappt. Hat die Person
    im Fenster kein Plus (nur eine Krankheit ohne Einträge → Saldo ≤ 0), sinkt der
    Saldo nicht — die Änderung verlangt keinen Grund. Die Gutschrift der Krankheit
    fällt mit dem Soll auf 0. (Mit Plus-Stunden im Fenster ist es eine Verkürzung,
    s. nächster Test.)"""
    u = test_user
    _set_mode(db, u, True)
    sick = absence(db, u, ABSENCE_DAY, AbsenceType.SICK, hours=4.0)
    plain = {"effective_from": EFF.isoformat(), "blocks": WEEK, "track_hours": False}

    p = client.post(url(u) + "/preview", json=plain)
    assert p.status_code == 200, p.text
    assert p.json()["is_shortening"] is False

    r = client.post(url(u), json=plain)
    assert r.status_code == 201, r.text
    assert _hours(db, sick) == 0.0


def test_retroactive_switch_off_with_plus_hours_is_a_shortening(db, test_user, client):
    """Gegenprobe zum Vorigen: Einträge über dem Soll im Fenster (Plus-Saldo) gehen
    mit dem Ausschalten verloren → Saldo sinkt → Verkürzung: Vorschau meldet
    ``saldo``, das Schreiben ohne Grund ist 400 „Rückwirkende Verkürzung“."""
    u = test_user
    _set_mode(db, u, True)
    eff = date(2026, 11, 2)   # Montag vor „heute“ (03.11.): Fenster = ein Tag mit Plus
    entry(db, u, eff, t(8), t(14))   # 6 h bei Tagessoll 4 h → +2 h
    rows = _row_count(db, u)
    plain = {"effective_from": eff.isoformat(), "blocks": WEEK, "track_hours": False}

    p = client.post(url(u) + "/preview", json=plain)
    assert p.status_code == 200, p.text
    assert p.json()["is_shortening"] is True
    assert "saldo" in p.json()["shortening_reasons"]

    r = client.post(url(u), json=plain)
    assert r.status_code == 400, r.text
    assert "Rückwirkende Verkürzung" in r.json()["detail"]
    assert _row_count(db, u) == rows


def test_delete_of_switch_off_without_reason_is_400(db, test_user, client):
    """F031 (DELETE): das Löschen der Ausschaltung führt die Stundenzählung wieder
    ein und kappt rückwirkend — ohne Grund 400, die Zeile bleibt."""
    u = test_user
    _set_mode(db, u, True)
    e = entry(db, u, ENTRY_DAY, t(7), t(13), raw_start=t(7), raw_end=t(13))
    r = client.post(url(u), json=body(False))
    assert r.status_code == 201, r.text
    rows = _row_count(db, u)
    before = _entry_state(db, e)

    resp = client.request("DELETE", f"{url(u)}/{r.json()['id']}")
    assert resp.status_code == 400, resp.text
    assert _row_count(db, u) == rows
    assert _entry_state(db, e) == before
