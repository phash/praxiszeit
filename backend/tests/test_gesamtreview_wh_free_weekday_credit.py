"""Gesamtreview 1.20 (Fund 4): kein Soll, keine Gutschrift — auch nach einer
Arbeitszeit-Änderung, die einen Wochentag frei macht.

Bert hat Blöcke Mo–Fr 08:00–16:00 mit Pause 30 (7,5 h/Tag) und ist am Di
15.09.2026 krank (gebucht mit 7,5 h). Ab 01.09. arbeitet er dienstags nicht mehr
(Dienstag ohne Blöcke → Tagessoll 0). Die Rückrechnung übersprang den Tag
(``target <= 0``), die Krankmeldung stand weiter mit 7,5 h da — und
``credit_day_weight`` gewichtet einen Wochentag mit 1,0: Soll 0 gegen 7,5 h
Gutschrift = +7:30 h Überstunden für einen Krankentag ohne Arbeitspflicht, ohne
Zeile in der Vorschau und ohne Protokoll.

Jetzt setzt die Rückrechnung die Ist-Gutschrift (SICK/TRAINING) an einem Tag
ohne Soll auf 0; Urlaub & Co. bleiben wie bisher stehen (ihre ``hours`` tragen
kein Saldo). Das Löschen der Änderung zieht sie symmetrisch zurück."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, TimeEntryAuditLog
from app.routers.admin_users import _delete_change_row
from app.services import calculation_service, wh_change_service as svc
from tests.test_endpoints import test_app
from tests.wh_change_helpers import absence, add_row, admin_client, change_row, freeze
from tests.work_blocks_fixtures import block_week

DAY = [("08:00", "16:00")]
FULL = block_week(pause=30, mon=DAY, tue=DAY, wed=DAY, thu=DAY, fri=DAY)
NO_TUESDAY = block_week(pause=30, mon=DAY, wed=DAY, thu=DAY, fri=DAY)
EFF = date(2026, 9, 1)
SICK_DAY = date(2026, 9, 15)       # Dienstag
TRAINING_DAY = date(2026, 9, 22)   # Dienstag
VACATION_DAY = date(2026, 9, 29)   # Dienstag


def _day_saldo(db, user, d):
    db.expire_all()
    return calculation_service.get_range_actual(db, user, d, d) - calculation_service.get_range_target(db, user, d, d)


def _bert(db, user):
    add_row(db, user, date(2026, 3, 1), week=FULL)
    sick = absence(db, user, SICK_DAY, AbsenceType.SICK, 7.5)
    training = absence(db, user, TRAINING_DAY, AbsenceType.TRAINING, 7.5)
    vacation = absence(db, user, VACATION_DAY, AbsenceType.VACATION, 7.5)
    return sick, training, vacation


def test_free_weekday_zeroes_the_credit(db, test_user, test_admin, monkeypatch):
    freeze(monkeypatch)
    sick, training, vacation = _bert(db, test_user)
    assert _day_saldo(db, test_user, SICK_DAY) == Decimal("0")

    impact = svc.run_change(db, test_user, admin_id=test_admin.id, effective_from=EFF,
                            apply=lambda: db.add(change_row(test_user, EFF, week=NO_TUESDAY)))

    assert sorted((a.date, a.absence_type, a.old_hours, a.new_hours) for a in impact.absences) == [
        (SICK_DAY, AbsenceType.SICK, Decimal("7.50"), Decimal("0.00")),
        (TRAINING_DAY, AbsenceType.TRAINING, Decimal("7.50"), Decimal("0.00")),
    ]
    # Die Gutschrift sinkt genau mit dem Soll — keine Verkürzung (9.5 (c)).
    assert impact.credit_reductions == []
    # Fünf Dienstage bis zum Stichtag (01.09.–06.10., ohne den Urlaubstag 29.09.,
    # dessen Soll der Urlaub schon vorher entlastete) verlieren je 7,5 h Soll; die
    # Gutschrift sinkt um die beiden Abwesenheiten — vorher blieb sie stehen
    # (Δ angerechnet 0, Saldo +37,5 statt +22,5).
    assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
        Decimal("-37.5"), Decimal("-15.0"), Decimal("22.5"))
    db.flush()
    for a in (sick, training):
        db.refresh(a)
        assert Decimal(str(a.hours)) == Decimal("0")
        assert Decimal(str(a.raw_hours)) == Decimal("7.5")   # Rückversicherung bleibt
    db.refresh(vacation)
    assert Decimal(str(vacation.hours)) == Decimal("7.5")   # Urlaub: übersprungen, nicht auf 0
    for d in (SICK_DAY, TRAINING_DAY):
        assert _day_saldo(db, test_user, d) == Decimal("0")


def test_deleting_the_change_restores_the_credit(db, test_user, test_admin, monkeypatch):
    freeze(monkeypatch)
    sick, _, _ = _bert(db, test_user)
    row = add_row(db, test_user, EFF, week=NO_TUESDAY)
    # Stand nach dem Anlegen (wie oben): Gutschrift 0.
    calculation_service.retarget_absence_hours(
        db, test_user, EFF, date(2026, 10, 8),
        old_full_target_by_date=calculation_service.absence_full_targets(db, test_user, EFF, date(2026, 10, 8)))
    db.commit()
    db.refresh(sick)
    assert Decimal(str(sick.hours)) == Decimal("0")

    impact = svc.run_change(db, test_user, admin_id=test_admin.id, effective_from=EFF,
                            apply=lambda: _delete_change_row(db, test_user, test_admin, row))

    assert (SICK_DAY, Decimal("0.00"), Decimal("7.50")) in [
        (a.date, a.old_hours, a.new_hours) for a in impact.absences]
    assert impact.credit_reductions == []
    db.flush()
    db.refresh(sick)
    assert Decimal(str(sick.hours)) == Decimal("7.5")
    assert _day_saldo(db, test_user, SICK_DAY) == Decimal("0")


def test_existing_row_is_zeroed_by_the_next_covering_change(db, test_user, test_admin, monkeypatch):
    """Bestand (Gesamtreview 1.20, Nachzug zu Fund 4): Eine Krankmeldung, die
    schon VOR 1.20.0 an einem frei gewordenen Dienstag mit den alten 7,5 h
    stehen blieb (die Rückrechnung übersprang den Tag damals), korrigiert das
    Update nicht von selbst. Die Rückrechnung gleicht jede Zeile im
    Wirkungsbereich an das Tagessoll an — die nächste Änderung, deren Bereich
    den Tag umfasst, setzt sie also auf 0, auch wenn sie nur den Montag ändert.
    Weil das Soll dort schon 0 war, sinkt nur die Gutschrift: das
    Überstundenkonto fällt, die Änderung ist eine Verkürzung (Kriterium b).
    So steht es im CHANGELOG, in BERECHNUNGEN (TZ-E) und im Admin-Handbuch."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=FULL)
    sick = absence(db, test_user, SICK_DAY, AbsenceType.SICK, 7.5)
    # Altzustand: Dienstag frei ab 01.09. OHNE Rückrechnung (wie vor dem Fix).
    add_row(db, test_user, EFF, week=NO_TUESDAY)
    assert _day_saldo(db, test_user, SICK_DAY) == Decimal("7.5")   # Phantom-Gutschrift

    later = date(2026, 9, 7)   # Montag
    shorter_monday = block_week(pause=30, mon=[("08:00", "15:00")], wed=DAY, thu=DAY, fri=DAY)
    impact = svc.run_change(db, test_user, admin_id=test_admin.id, effective_from=later,
                            apply=lambda: db.add(change_row(test_user, later, week=shorter_monday)))

    assert impact.changed_weekdays == [0]   # nur Montag geändert …
    assert [(a.date, a.absence_type, a.old_hours, a.new_hours) for a in impact.absences] == [
        (SICK_DAY, AbsenceType.SICK, Decimal("7.50"), Decimal("0.00"))]   # … der Dienstag trotzdem
    # Fünf Montage verlieren je 1 h Soll, die Gutschrift sinkt um die 7,5 h.
    assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
        Decimal("-5.00"), Decimal("-7.50"), Decimal("-2.50"))
    assert impact.shortening_reasons == ["saldo"]
    # „Ab heute" lässt die Zeile stehen (der Wirkungsbereich beginnt danach).
    assert impact.earliest_lossless_date == date(2026, 10, 8)
    db.flush()
    db.refresh(sick)
    assert Decimal(str(sick.hours)) == Decimal("0")
    assert _day_saldo(db, test_user, SICK_DAY) == Decimal("0")


JUNE = date(2026, 6, 1)
LEGACY_DAY = date(2026, 6, 16)   # Dienstag, Alt-Zeile ohne Halbtags-Information
MODERN_DAY = date(2026, 6, 23)   # Dienstag, heutige Buchung (half_day=False)


def test_legacy_row_without_half_day_is_never_adjusted(db, test_user, test_admin, monkeypatch):
    """Grenze (Gesamtreview 1.20, Nachzug zu Fund 4): Alt-Zeilen ohne
    Halbtags-Information (``half_day IS NULL`` — gebucht vor 1.10.0 (#205), über
    einen genehmigten Änderungsantrag vor 1.16.0) fasst die Rückrechnung NIE an
    (C1, ``retarget_absence_hours``) — auch nicht auf 0 an einem frei gewordenen
    Wochentag. Ein Krankentag dieser Art behält dort seine Stunden, die Gutschrift
    bleibt im Saldo, ohne Zeile in der Vorschau. Bewusst so (C1: ein Umschreiben
    löschte die einzige Spur eines Alt-Halbtags, und das Löschen der Änderung
    könnte den Wert nicht wiederherstellen); dokumentiert in BERECHNUNGEN (§4.2,
    TZ-E „Bestand"), CHANGELOG und Admin-Handbuch — Korrektur von Hand."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=FULL)
    legacy = absence(db, test_user, LEGACY_DAY, AbsenceType.SICK, 7.5, half_day=None)
    modern = absence(db, test_user, MODERN_DAY, AbsenceType.SICK, 7.5)

    impact = svc.run_change(db, test_user, admin_id=test_admin.id, effective_from=JUNE,
                            apply=lambda: db.add(change_row(test_user, JUNE, week=NO_TUESDAY)))

    # Nur die heutige Buchung wird auf 0 gesetzt — die Alt-Zeile fehlt in der Vorschau.
    assert [(a.date, a.old_hours, a.new_hours) for a in impact.absences] == [
        (MODERN_DAY, Decimal("7.50"), Decimal("0.00"))]
    db.flush()
    db.refresh(legacy)
    db.refresh(modern)
    assert Decimal(str(legacy.hours)) == Decimal("7.5")
    assert Decimal(str(modern.hours)) == Decimal("0")
    assert _day_saldo(db, test_user, LEGACY_DAY) == Decimal("7.5")   # dokumentierte Grenze
    assert _day_saldo(db, test_user, MODERN_DAY) == Decimal("0")


def test_legacy_row_on_already_free_weekday_stays_on_the_next_change(db, test_user, test_admin, monkeypatch):
    """Dieselbe Grenze für den Bestand: Anders als eine heutige Buchung
    (``test_existing_row_is_zeroed_by_the_next_covering_change``) setzt auch die
    nächste Änderung, deren Wirkungsbereich den Tag umfasst, eine Alt-Zeile ohne
    Halbtags-Information nicht auf 0 — keine Gutschrift sinkt, also auch keine
    Verkürzung aus dieser Zeile."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=FULL)
    legacy = absence(db, test_user, LEGACY_DAY, AbsenceType.SICK, 7.5, half_day=None)
    # Altzustand: Dienstag frei ab 01.06. OHNE Rückrechnung.
    add_row(db, test_user, JUNE, week=NO_TUESDAY)
    assert _day_saldo(db, test_user, LEGACY_DAY) == Decimal("7.5")

    later = date(2026, 6, 8)   # Montag
    shorter_monday = block_week(pause=30, mon=[("08:00", "15:00")], wed=DAY, thu=DAY, fri=DAY)
    impact = svc.run_change(db, test_user, admin_id=test_admin.id, effective_from=later,
                            apply=lambda: db.add(change_row(test_user, later, week=shorter_monday)))

    assert impact.absences == []
    assert impact.credited_delta == Decimal("0")
    assert "saldo" not in impact.shortening_reasons
    db.flush()
    db.refresh(legacy)
    assert Decimal(str(legacy.hours)) == Decimal("7.5")
    assert _day_saldo(db, test_user, LEGACY_DAY) == Decimal("7.5")


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def test_preview_and_saving_name_and_log_the_absence(client, db, test_user):
    """Vorschau nennt die Abwesenheit, das Speichern protokolliert sie je Zeile."""
    sick, _, _ = _bert(db, test_user)
    body = {"effective_from": EFF.isoformat(), "blocks": NO_TUESDAY}

    preview = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["affected_absences"] == 2
    assert preview.json()["is_shortening"] is False

    resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json=body)
    assert resp.status_code in (200, 201), resp.text
    db.expire_all()
    assert Decimal(str(db.get(Absence, sick.id).hours)) == Decimal("0")
    notes = [r.new_note for r in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == test_user.id,
        TimeEntryAuditLog.source == "wh_change",
        TimeEntryAuditLog.old_date == SICK_DAY,
    )]
    assert notes == ["Krank 0,0 h — Arbeitszeit-Änderung ab 01.09.2026"]
    assert _day_saldo(db, test_user, SICK_DAY) == Decimal("0")
