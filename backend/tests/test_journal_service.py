"""Tests für journal_service."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import journal_service, calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_entry(db, user, d, start_h, end_h, break_min=0):
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_absence(db, user, d, atype, hours=8.0, half_day=None):
    absence = Absence(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        type=atype,
        hours=hours,
        half_day=half_day,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return absence


def test_journal_returns_correct_day_count(db, test_user):
    """Prüft dass das Journal exakt so viele Tage enthält wie der Monat hat — Grundlage für lückenlose Monatsansicht."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert len(result["days"]) == 31


def test_journal_work_day_has_correct_type(db, test_user):
    """Prüft dass ein Werktag mit Zeiteintrag als 'work' klassifiziert wird und die Ist-Stunden stimmen."""
    monday = date(2026, 3, 9)
    _make_entry(db, test_user, monday, 8, 17, break_min=60)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["type"] == "work"
    assert day["actual_hours"] == pytest.approx(8.0)


def test_journal_weekend_has_weekend_type(db, test_user):
    """Prüft dass Wochenendtage als 'weekend' mit 0h Soll markiert werden — keine Fehlberechnung am Wochenende."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-14")
    assert day["type"] == "weekend"
    assert day["actual_hours"] == 0.0
    assert day["target_hours"] == 0.0


def test_journal_holiday_has_holiday_type(db, test_user):
    """Prüft dass Feiertage als 'holiday' mit Name und 0h Soll angezeigt werden — kein Defizit an Feiertagen."""
    h = PublicHoliday(date=date(2026, 3, 11), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-11")
    assert day["type"] == "holiday"
    assert day["holiday_name"] == "Testfeiertag"
    assert day["target_hours"] == 0.0


def test_journal_vacation_day(db, test_user):
    """Prüft dass Urlaubstage als 'vacation' mit ausgeglichenem Saldo erscheinen — Urlaub erzeugt kein Defizit.

    L3 (Audit 2026-07-31): Soll UND Ist sind an einem GANZTAGS-Urlaubstag ohne
    Zeiteintrag jetzt 0,00 — dieselbe Quelle wie get_monthly_target (der Tag
    faellt aus dem Soll) und wie der §16-Dateiexport
    (export_service.absence_day_target → 0). Frueher schrieb das Journal hier
    ``actual = target = Σ absence.hours`` (8/8) und buchte damit nicht erbrachte
    Arbeit als erbracht. Der Saldo bleibt unveraendert 0,00, und die Tageszeilen
    summieren sich jetzt zum Monats-Summary."""
    tuesday = date(2026, 3, 10)
    _make_absence(db, test_user, tuesday, AbsenceType.VACATION, hours=8.0)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "vacation"
    assert day["target_hours"] == 0.0
    assert day["actual_hours"] == 0.0
    assert day["balance"] == 0.0


def test_journal_empty_work_day_is_deficit(db, test_user):
    """Prüft dass ein Werktag ohne Zeiteintrag als 'empty' mit negativem Saldo erscheint — Fehlstunden sichtbar."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    monday = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert monday["type"] == "empty"
    assert monday["actual_hours"] == 0.0
    assert monday["target_hours"] == pytest.approx(8.0)
    assert monday["balance"] == pytest.approx(-8.0)


def test_journal_monthly_summary(db, test_user):
    """Prüft dass die Monatsübersicht konsistent mit dem calculation_service berechnet wird — keine Abweichungen."""
    from app.services import calculation_service
    result = journal_service.get_journal(db, test_user, 2026, 3)
    expected_target = float(calculation_service.get_monthly_target(db, test_user, 2026, 3))
    assert result["monthly_summary"]["target_hours"] == pytest.approx(expected_target)


def test_journal_yearly_overtime_zero_without_entries(db, test_user):
    """Prüft dass ohne Zeiteinträge die Jahresüberstunden 0 sind — sauberer Ausgangszustand."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["yearly_overtime"] == 0.0


def test_journal_user_info_included(db, test_user):
    """Prüft dass Benutzerinfos im Journal enthalten sind — Frontend braucht Name für die Anzeige."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["user"]["first_name"] == test_user.first_name
    assert result["user"]["last_name"] == test_user.last_name


def test_journal_day_actuals_windowed_match_monthly_actual(db, test_user):
    """#198: Ein TimeEntry VOR first_work_day darf das Tages-Ist nicht aufblaehen.
    Summe der Tageszeilen muss dem (gefensterten) Monats-Ist entsprechen."""
    test_user.first_work_day = date(2026, 3, 16)  # Eintritt Mitte Maerz
    db.commit()
    _make_entry(db, test_user, date(2026, 3, 9), 8, 16)    # Mo, VOR Eintritt (out-of-window)
    _make_entry(db, test_user, date(2026, 3, 23), 8, 16)   # Mo, nach Eintritt (zaehlt)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    sum_day_actual = round(sum(d["actual_hours"] for d in result["days"]), 2)
    monthly_actual = round(float(calculation_service.get_monthly_actual(db, test_user, 2026, 3)), 2)
    assert sum_day_actual == monthly_actual

    mar9 = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert mar9["actual_hours"] == 0.0   # out-of-window -> kein Ist
    mar23 = next(d for d in result["days"] if d["date"] == "2026-03-23")
    assert mar23["actual_hours"] == 8.0  # in-window -> zaehlt


def test_journal_paid_leave_day_type(db, test_user):
    # Fix: PAID_LEAVE war nicht in _ABSENCE_TYPE_MAP → wurde als "other" typisiert.
    _make_absence(db, test_user, date(2026, 3, 4), AbsenceType.PAID_LEAVE)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-04")
    assert day["type"] == "paid_leave"


def test_journal_masks_custom_reason_absence_without_health_data(db, test_user):
    # #312/#376 DSGVO: eine Absence mit reason_id (z. B. Kind krank) muss ohne
    # angeforderte Gesundheitsdaten maskiert werden (Tagestyp + Label → "absent").
    from app.models import AbsenceReason
    r = AbsenceReason(tenant_id=DEFAULT_TENANT_ID, name="Kind krank",
                      base_behavior="unpaid_free", is_active=True, tracks_child_sick_limit=True)
    db.add(r); db.commit(); db.refresh(r)
    a = Absence(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=date(2026, 3, 5),
                type=AbsenceType.OTHER, hours=Decimal("8"), reason_id=r.id)
    db.add(a); db.commit()

    masked = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=False)
    day_m = next(d for d in masked["days"] if d["date"] == "2026-03-05")
    assert day_m["type"] == "absent"
    assert day_m["absences"][0]["type"] == "absent"
    assert "Kind krank" not in str(day_m)

    shown = journal_service.get_journal(db, test_user, 2026, 3, include_health_data=True)
    day_s = next(d for d in shown["days"] if d["date"] == "2026-03-05")
    assert day_s["absences"][0]["type"] == "Kind krank"  # eigener Grund-Name sichtbar


def test_journal_renders_without_error_for_fixed_mode_user(db, default_tenant):
    """Finding 3 (Whole-Branch-Review, #377 Baustein 2b): ein Fix-Modus-MA
    (use_fixed_monthly_target) darf im Journal weder crashen noch eine
    irreführende Kumulierung zeigen. Die Tageszeilen bleiben bewusst die
    GEPLANTE Anwesenheit (kein Per-Tag-Zerlegen des flachen Monats-Solls,
    siehe Kommentar bei _eff_daily_target) — die maßgebliche Soll/Ist/Saldo-
    Zahl ist monthly_summary (modus-bewusst über get_monthly_target/actual)."""
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db)  # agreed=40h fix, Mo+Mi geplant à 3h
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                     start_time=time(8, 0), end_time=time(19, 0), break_minutes=60))
    db.commit()

    result = journal_service.get_journal(db, u, 2025, 3)  # no crash
    assert len(result["days"]) == 31

    expected_target = calculation_service.get_monthly_target(db, u, 2025, 3)
    expected_actual = calculation_service.get_monthly_actual(db, u, 2025, 3)
    assert result["monthly_summary"]["target_hours"] == pytest.approx(float(expected_target))
    assert result["monthly_summary"]["actual_hours"] == pytest.approx(float(expected_actual))
    assert result["monthly_summary"]["balance"] == pytest.approx(
        float(expected_actual - expected_target))

    # Bewusst KEINE Assertion, dass Σ(day["target_hours"]) == monthly_summary
    # (Finding 3: erwartete Divergenz bei fixem Monats-Soll, kein Bug).


# --- Audit 2026-07-31 / L2 + L3: die Tageszeile muss aus DERSELBEN Quelle -----
# kommen wie Berechnung (calculation_service) und §16-Datei (export_service).
#
# L2 (Regression aus 1.18.0): die dort eingefuehrte Klemmung des soll-
#     reduzierenden Anteils wurde auch auf HALBTAGS-Abwesenheiten angewandt;
#     _day_soll_contribution klemmt bewusst nur ganztaegige (`half is False`).
# L3: bei einer Abwesenheit OHNE Zeiteintrag wurde `actual = target =
#     Σ absence.hours` gesetzt — bei einem Halbtag also die offene
#     Arbeitshaelfte als erbrachtes Ist gutgeschrieben (gruen statt Defizit).

def test_journal_half_day_absence_with_work_matches_calculation(db, test_user):
    """L2: ½ Urlaub (4 h) an einem 8-h-Tag, an dem 6 h gearbeitet wurden.
    Tageszeile muss Soll 4 / Ist 6 / Saldo +2 zeigen (wie die Berechnung und
    die §16-Datei), nicht die 1.18.0-Klemmung 6/6/0."""
    monday = date(2026, 3, 9)
    _make_entry(db, test_user, monday, 8, 15, break_min=60)  # 6h netto
    _make_absence(db, test_user, monday, AbsenceType.VACATION, hours=4.0, half_day=True)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["target_hours"] == 4.0
    assert day["actual_hours"] == 6.0
    assert day["balance"] == 2.0


def test_journal_half_day_absence_without_entry_shows_deficit(db, test_user):
    """L3: ½ Urlaub (4 h) an einem 8-h-Tag OHNE Zeiteintrag. Die offene
    Arbeitshaelfte ist NICHT erbracht → Soll 4 / Ist 0 / Saldo −4 (statt
    4/4/0, wo genau die fehlende Erfassung unsichtbar wurde)."""
    monday = date(2026, 3, 9)
    _make_absence(db, test_user, monday, AbsenceType.VACATION, hours=4.0, half_day=True)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["target_hours"] == 4.0
    assert day["actual_hours"] == 0.0
    assert day["balance"] == -4.0


def test_journal_full_day_absence_with_kept_entry_unchanged(db, test_user):
    """Kontrolltest (Byte-Identitaet): der GANZTAGS-Fall mit behaltenem
    Zeiteintrag (F1 aus 1.18.0, „+"-Knopf mit keep_time_entries) bleibt
    unveraendert Soll 6 / Ist 6 / Saldo 0 — nur der nicht gearbeitete Teil
    des Tages faellt weg."""
    monday = date(2026, 3, 9)
    _make_entry(db, test_user, monday, 8, 15, break_min=60)  # 6h netto
    # create_absence klemmt die Stunden auf max(0, 8 − 6) = 2
    _make_absence(db, test_user, monday, AbsenceType.VACATION, hours=2.0, half_day=False)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["target_hours"] == 6.0
    assert day["actual_hours"] == 6.0
    assert day["balance"] == 0.0


def test_journal_day_rows_sum_to_monthly_summary(db, test_user):
    """L2+L3 Invariante: mit gemischten Abwesenheiten (Halbtag mit Arbeit,
    Ganztag ohne Arbeit, Krank, Ueberstundenausgleich) muessen die Tageszeilen
    in der Summe exakt das Monats-Summary ergeben — Tageszeile und Berechnung
    haben jetzt dieselbe Quelle. (Nur fuer Nicht-Fix-Modus-MA, siehe
    test_journal_renders_without_error_for_fixed_mode_user.)"""
    _make_entry(db, test_user, date(2026, 3, 9), 8, 15, break_min=60)   # 6h + ½ Urlaub
    _make_absence(db, test_user, date(2026, 3, 9), AbsenceType.VACATION, hours=4.0, half_day=True)
    _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, hours=8.0, half_day=False)
    _make_absence(db, test_user, date(2026, 3, 11), AbsenceType.SICK, hours=8.0, half_day=False)
    _make_absence(db, test_user, date(2026, 3, 12), AbsenceType.OVERTIME, hours=8.0, half_day=False)
    _make_entry(db, test_user, date(2026, 3, 13), 8, 16, break_min=0)   # 8h regulaer

    result = journal_service.get_journal(db, test_user, 2026, 3)
    sum_target = round(sum(d["target_hours"] for d in result["days"]), 2)
    sum_actual = round(sum(d["actual_hours"] for d in result["days"]), 2)
    assert sum_target == pytest.approx(result["monthly_summary"]["target_hours"])
    assert sum_actual == pytest.approx(result["monthly_summary"]["actual_hours"])


# --- Audit 2026-07-31 / uebernommen aus Welle B ------------------------------
# Feiertag MIT Krank-/Fortbildungs-Abwesenheit. Die zu schuetzende Invariante ist
# unveraendert: die Tageszeile muss dasselbe sagen wie das ``monthly_summary`` im
# SELBEN Response. Der erwartete WERT hat sich mit Fund K des Audits 2026-07-31
# geaendert — die Gutschrift folgt jetzt der Soll-Struktur des Tages
# (``calculation_service.credit_day_weight``), an einem Feiertag ist sie also 0
# statt eines vollen Tagessolls Phantom-Ueberstunden. Beide Seiten stehen jetzt
# auf 0; vorher standen beide (falsch) auf 8.

def test_journal_holiday_with_sick_matches_calculation(db, test_user):
    """Krank an einem Feiertag: Soll 0 (Feiertag) UND Ist 0 (keine Gutschrift an
    einem Tag ohne Arbeitspflicht) — und beides deckungsgleich mit
    get_monthly_actual im selben Response."""
    d = date(2026, 3, 11)  # Mittwoch
    db.add(PublicHoliday(date=d, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    _make_absence(db, test_user, d, AbsenceType.SICK, hours=8.0)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(x for x in result["days"] if x["date"] == "2026-03-11")
    assert day["target_hours"] == 0.0
    assert day["actual_hours"] == 0.0
    assert day["balance"] == 0.0

    expected_actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
    assert round(sum(x["actual_hours"] for x in result["days"]), 2) == pytest.approx(
        float(expected_actual))
    assert result["monthly_summary"]["actual_hours"] == pytest.approx(float(expected_actual))


def test_journal_holiday_with_training_matches_calculation(db, test_user):
    """Dieselbe Regel fuer Fortbildung (der zweite ist-gutgeschriebene Typ)."""
    d = date(2026, 3, 11)
    db.add(PublicHoliday(date=d, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    _make_absence(db, test_user, d, AbsenceType.TRAINING, hours=6.0)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(x for x in result["days"] if x["date"] == "2026-03-11")
    assert day["actual_hours"] == 0.0

    expected_actual = calculation_service.get_monthly_actual(db, test_user, 2026, 3)
    assert result["monthly_summary"]["actual_hours"] == pytest.approx(float(expected_actual))


def test_journal_holiday_without_absence_unchanged(db, test_user):
    """Kontrolltest (Byte-Identitaet): ein Feiertag ohne Abwesenheit und ein
    Feiertag, an dem gearbeitet wurde, bleiben unveraendert."""
    d = date(2026, 3, 11)
    db.add(PublicHoliday(date=d, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(x for x in result["days"] if x["date"] == "2026-03-11")
    assert day["actual_hours"] == 0.0
    assert day["target_hours"] == 0.0

    _make_entry(db, test_user, d, 9, 13)  # 4h am Feiertag gearbeitet
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(x for x in result["days"] if x["date"] == "2026-03-11")
    assert day["actual_hours"] == 4.0
    assert day["target_hours"] == 0.0


def test_journal_holiday_with_vacation_stays_zero(db, test_user):
    """Kontrolltest: ein NICHT ist-gutgeschriebener Typ (Urlaub) am Feiertag
    aendert nichts — 0/0/0, genau wie get_monthly_actual ihn nicht zaehlt."""
    d = date(2026, 3, 11)
    db.add(PublicHoliday(date=d, name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    _make_absence(db, test_user, d, AbsenceType.VACATION, hours=8.0)

    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(x for x in result["days"] if x["date"] == "2026-03-11")
    assert day["actual_hours"] == 0.0
    assert day["target_hours"] == 0.0


# ── #463: Tageszeilen im festen Monats-Soll ──────────────────────────────────


def test_journal_meldet_den_fixen_modus(db, default_tenant, test_user):
    """Ohne dieses Kennzeichen kann die Oberflaeche die Tagesspalten nicht
    einordnen und zeigt Zahlen ohne definierte Bedeutung."""
    from tests.test_fixed_monthly_target import _mk

    assert journal_service.get_journal(db, test_user, 2025, 3)["use_fixed_monthly_target"] is False
    u = _mk(db)
    assert journal_service.get_journal(db, u, 2025, 3)["use_fixed_monthly_target"] is True


def test_journal_flag_verlangt_auch_die_vereinbarte_monatszeit(db, default_tenant):
    """Dieselbe Bedingung wie in get_range_actual/-target: das Flag allein
    genuegt nicht, ohne agreed_monthly_hours gibt es kein festes Soll."""
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db, agreed_monthly_hours=None)
    assert journal_service.get_journal(db, u, 2025, 3)["use_fixed_monthly_target"] is False


def test_urlaubstag_im_fixmodus_zeigt_geplante_stunden_und_gutschrift(db, default_tenant):
    """Der gemeldete Fall (#463): ein Urlaubstag stand als 0 Ist / 0 Soll da.

    Im Fix-Modus mindert Urlaub das flache Soll gerade NICHT — er schreibt die
    geplanten Stunden dem Ist gut (``fixed_month_credit``). Die Tageszeile muss
    dieselbe Geschichte erzaehlen wie die Monatssumme darunter.
    """
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db)  # Mo + Mi geplant, je 3 h
    _make_absence(db, u, date(2025, 3, 3), AbsenceType.VACATION, hours=3.0)  # Montag

    tag = next(d for d in journal_service.get_journal(db, u, 2025, 3)["days"]
               if d["date"] == "2025-03-03")
    assert tag["target_hours"] == pytest.approx(3.0)   # geplante Anwesenheit
    assert tag["actual_hours"] == pytest.approx(3.0)   # bezahlter Fehltag → Gutschrift


def test_ungeplanter_wochentag_bleibt_im_fixmodus_bei_null(db, default_tenant):
    """Dienstag ist im Tagesplan nicht belegt — dort gibt es nichts zu planen
    und nichts gutzuschreiben."""
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db)
    _make_absence(db, u, date(2025, 3, 4), AbsenceType.VACATION, hours=3.0)  # Dienstag

    tag = next(d for d in journal_service.get_journal(db, u, 2025, 3)["days"]
               if d["date"] == "2025-03-04")
    assert tag["target_hours"] == pytest.approx(0.0)
    assert tag["actual_hours"] == pytest.approx(0.0)


def test_krank_wird_im_fixmodus_nicht_doppelt_gutgeschrieben(db, default_tenant):
    """SICK laeuft schon ueber ``credited_absences``; ein zweites Gutschreiben
    ueber den Fix-Zweig wuerde den Tag verdoppeln."""
    from tests.test_fixed_monthly_target import _mk

    u = _mk(db)
    _make_absence(db, u, date(2025, 3, 5), AbsenceType.SICK, hours=3.0)  # Mittwoch

    tag = next(d for d in journal_service.get_journal(db, u, 2025, 3)["days"]
               if d["date"] == "2025-03-05")
    assert tag["actual_hours"] == pytest.approx(3.0)
    assert tag["target_hours"] == pytest.approx(3.0)


def test_normalmodus_bleibt_unveraendert(db, test_user):
    """Kontrolle: fuer alle anderen Mitarbeitenden aendert #463 nichts."""
    _make_absence(db, test_user, date(2025, 3, 3), AbsenceType.VACATION, hours=8.0)

    tag = next(d for d in journal_service.get_journal(db, test_user, 2025, 3)["days"]
               if d["date"] == "2025-03-03")
    # Urlaub mindert im Normalmodell das Soll → 0/0, Saldo 0.
    assert tag["target_hours"] == pytest.approx(0.0)
    assert tag["balance"] == pytest.approx(0.0)
