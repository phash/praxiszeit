"""Audit 2026-07-31 — Fund K: Ist-Gutschrift an einem Tag ohne Arbeitspflicht.

TRAINING/SICK reduzieren das Soll NICHT — stattdessen wird die Ist-Seite mit den
Stunden der Abwesenheit gutgeschrieben (``credited_absences``). Der Zweck ist
Saldo-Neutralitaet: das Soll bleibt stehen, die Gutschrift gleicht es aus.

Die vier Gutschrift-Schleifen im ``calculation_service`` summierten
``Absence.hours`` jedoch ROH, waehrend das Soll daneben strukturell reduziert
wird: ``_day_soll_contribution`` setzt Feiertage auf 0, die Aufrufer
ueberspringen Wochenenden, und der #146-Sondertagsfaktor halbiert (bzw. nullt)
das Tagessoll am 24./31.12. Folge:

* **Feiertag + Krank/Fortbildung** → Soll 0, Ist +8 h = ein voller Tag
  **Phantom-Ueberstunden**. Wer ueber Weihnachten krankgeschrieben war, sammelte
  je Feiertag +8 h. Rechtlich falsch: fuer den Feiertag gilt die
  Feiertagsverguetung (§ 2 EntgFG, ueber § 4 Abs. 2 EntgFG), nicht zusaetzlich
  eine Entgeltfortzahlung wegen Krankheit (§ 3 EntgFG).
* **Wochenende + Krank/Fortbildung** → derselbe Fall, Soll 0.
* **Halbtags-Sondertag (24./31.12. = ``half_day``) + Krank** → Soll 4 h, Ist 8 h
  (``create_absence`` bucht dort das VOLLE Tagessoll, der Faktor lebt allein auf
  der Soll-Seite) = +4 h aus dem Nichts. Dieser Fall ist ueber die NORMALE
  Direktbuchung erreichbar, ohne Altdaten und ohne Aenderungsantrag.

Fix: ``calculation_service.credit_day_weight`` — die Gutschrift folgt derselben
Tages-STRUKTUR wie das Soll (Wochenende/Feiertag 0, Sondertag mit dem
#146-Faktor). Bewusst KEIN Deckel auf das Tagessoll: eine Fortbildung, die
laenger dauerte als der Arbeitstag, bleibt echte Mehrarbeit.

Die Tests pruefen JEDE der fuenf Flaechen, die die Gutschrift kennen
(get_range_actual/get_monthly_actual, get_overtime_account,
get_overtime_history_detailed, get_ytd_summary, journal_service) — genau die
Fehlerklasse „an einer Stelle geaendert, an der anderen nicht", die dieses
Projekt mehrfach getroffen hat.
"""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import Absence, AbsenceType, PublicHoliday, TimeEntry
from app.models.system_setting import SystemSetting
from app.services import calculation_service, journal_service
from tests.conftest import DEFAULT_TENANT_ID


# Juni 2026: 01.06. = Montag, 03.06. = Mittwoch, 06.06. = Samstag.
MONDAY = date(2026, 6, 1)
WEDNESDAY = date(2026, 6, 3)
SATURDAY = date(2026, 6, 6)
TUESDAY = date(2026, 6, 9)
# 24./31.12.2026 sind beide Donnerstage — also regulaere Werktage, an denen nur
# die Sondertags-Konfiguration etwas aendert.
DEC24 = date(2026, 12, 24)
DEC31 = date(2026, 12, 31)


def _absence(db, user, d, atype, hours=8.0, half_day=None):
    a = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        type=atype, hours=hours, half_day=half_day,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _holiday(db, d, name="Testfeiertag"):
    h = PublicHoliday(date=d, name=name, year=d.year, tenant_id=DEFAULT_TENANT_ID)
    db.add(h)
    db.commit()
    return h


def _entry(db, user, d, start_h=9, end_h=17, break_min=0):
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(start_h, 0), end_time=time(end_h, 0), break_minutes=break_min,
    )
    db.add(e)
    db.commit()
    return e


def _special_day(db, prefix, mode):
    db.add(SystemSetting(key=f"{prefix}_mode", value=mode,
                         description=prefix, tenant_id=DEFAULT_TENANT_ID))
    db.add(SystemSetting(key=f"{prefix}_counts_as_vacation", value="false",
                         description=prefix, tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def _month_balance(db, user, year, month) -> Decimal:
    return (calculation_service.get_monthly_actual(db, user, year, month)
            - calculation_service.get_monthly_target(db, user, year, month))


# ---------------------------------------------------------------------------
# RED-Reproduktion: Feiertag
# ---------------------------------------------------------------------------

def test_krank_am_feiertag_erzeugt_keine_ueberstunden(db, test_user):
    """Kern des Fundes: Krank am Feiertag → Soll 0, Ist 0, Saldo 0.

    Vor dem Fix: Soll 0 (Feiertag faellt aus get_monthly_target), Ist 8 h
    (credited_absences summierte roh) → +8 h Phantom-Ueberstunden.
    """
    _holiday(db, WEDNESDAY)
    baseline_target = calculation_service.get_monthly_target(db, test_user, 2026, 6)
    baseline_actual = calculation_service.get_monthly_actual(db, test_user, 2026, 6)

    _absence(db, test_user, WEDNESDAY, AbsenceType.SICK, hours=8.0)

    assert calculation_service.get_monthly_target(db, test_user, 2026, 6) == baseline_target
    assert calculation_service.get_monthly_actual(db, test_user, 2026, 6) == baseline_actual
    assert _month_balance(db, test_user, 2026, 6) == baseline_actual - baseline_target


def test_fortbildung_am_feiertag_erzeugt_keine_ueberstunden(db, test_user):
    """Gilt fuer TRAINING genauso wie fuer SICK — beide sind ist-gutgeschrieben."""
    _holiday(db, WEDNESDAY)
    before = _month_balance(db, test_user, 2026, 6)
    _absence(db, test_user, WEDNESDAY, AbsenceType.TRAINING, hours=8.0)
    assert _month_balance(db, test_user, 2026, 6) == before


def test_feiertagsarbeit_bleibt_ueberstunde(db, test_user):
    """Abgrenzung: wer am Feiertag TATSAECHLICH arbeitet, behaelt die Ueberstunden.

    Nur die Gutschrift der Abwesenheit faellt weg, nicht die gestempelte Zeit.
    """
    _holiday(db, WEDNESDAY)
    before = _month_balance(db, test_user, 2026, 6)
    _entry(db, test_user, WEDNESDAY, 9, 17)  # 8 h echte Feiertagsarbeit
    _absence(db, test_user, WEDNESDAY, AbsenceType.SICK, hours=8.0)
    assert _month_balance(db, test_user, 2026, 6) == before + Decimal("8.00")


# ---------------------------------------------------------------------------
# Nachbarfall: Wochenende (ebenfalls Soll 0)
# ---------------------------------------------------------------------------

def test_krank_am_samstag_erzeugt_keine_ueberstunden(db, test_user):
    """Ein Wochenendtag hat kein Soll — die Soll-Schleifen ueberspringen ihn
    kategorisch. Die Gutschrift tat es nicht. Erreichbar, weil der Pfad
    ``admin_change_requests.review_change_request`` (UPDATE) das Datum einer
    bestehenden Abwesenheit ohne Wochenend-/Feiertagspruefung verschiebt und die
    ``hours`` dabei NICHT neu berechnet."""
    before = _month_balance(db, test_user, 2026, 6)
    _absence(db, test_user, SATURDAY, AbsenceType.SICK, hours=8.0)
    assert _month_balance(db, test_user, 2026, 6) == before


# ---------------------------------------------------------------------------
# Sondertage 24./31.12. — halbes Soll, also halbe Gutschrift
# ---------------------------------------------------------------------------

def test_krank_am_halben_sondertag_kostet_nur_das_halbe_soll(db, test_user):
    """24.12. als ``half_day``: Soll 4 h → Gutschrift 4 h, Saldo unveraendert.

    ``create_absence`` bucht dort das VOLLE Tagessoll (8 h) als ``hours`` — der
    #146-Faktor lebt allein auf der Soll-Seite. Roh gutgeschrieben ergab das
    8 h Ist gegen 4 h Soll = +4 h aus dem Nichts. Ueber die normale
    Direktbuchung erreichbar (Halbtags-Sondertage sind KEINE freien Tage und
    werden von keinem Buchungspfad ausgeschlossen).
    """
    _special_day(db, "special_day_dec24", "half_day")
    before = _month_balance(db, test_user, 2026, 12)
    _absence(db, test_user, DEC24, AbsenceType.SICK, hours=8.0)

    # Tages-Saldo 0: Soll 4 / Ist 4. Gegenueber dem unerfassten Monat (der Tag
    # stand dort mit −4 h zu Buche) also genau +4 — nicht +8.
    assert calculation_service.get_range_target(db, test_user, DEC24, DEC24) == Decimal("4.00")
    assert calculation_service.get_range_actual(db, test_user, DEC24, DEC24) == Decimal("4.00")
    assert _month_balance(db, test_user, 2026, 12) == before + Decimal("4.00")
    assert calculation_service.get_daily_target(test_user) == Decimal("8.00")


def test_krank_am_freien_sondertag_zaehlt_gar_nicht(db, test_user):
    """31.12. als ``free``: Soll 0 wie an einem Feiertag → Gutschrift 0."""
    _special_day(db, "special_day_dec31", "free")
    before = _month_balance(db, test_user, 2026, 12)
    _absence(db, test_user, DEC31, AbsenceType.SICK, hours=8.0)
    assert _month_balance(db, test_user, 2026, 12) == before
    assert calculation_service.get_range_actual(db, test_user, DEC31, DEC31) == Decimal("0.00")


# ---------------------------------------------------------------------------
# Kontrolltests: Byte-Identitaet ausserhalb des geprueften Falls
# ---------------------------------------------------------------------------

def test_krank_am_normalen_werktag_bleibt_unveraendert(db, test_user):
    """Der Regelfall: Krank an einem gewoehnlichen Dienstag.

    Soll bleibt stehen (SICK ist nicht soll-reduzierend), Ist wird VOLL
    gutgeschrieben → Tages-Saldo 0. Genau das Verhalten von vorher; Gewicht 1,0.
    """
    before = _month_balance(db, test_user, 2026, 6)
    _absence(db, test_user, TUESDAY, AbsenceType.SICK, hours=8.0)
    assert calculation_service.get_range_target(db, test_user, TUESDAY, TUESDAY) == Decimal("8.00")
    assert calculation_service.get_range_actual(db, test_user, TUESDAY, TUESDAY) == Decimal("8.00")
    assert _month_balance(db, test_user, 2026, 6) == before + Decimal("8.00")


def test_kranktag_zaehlt_wie_ein_gearbeiteter_tag(db, test_user):
    """Die eigentliche Invariante hinter der Gutschrift, als Vergleichstest:
    ein Kranktag muss den Saldo exakt so bewegen wie ein wirklich gearbeiteter
    Tag gleicher Laenge — an einem Werktag ebenso wie an einem Feiertag (dort
    beide 0)."""
    sick_before = _month_balance(db, test_user, 2026, 6)
    _absence(db, test_user, TUESDAY, AbsenceType.SICK, hours=8.0)
    sick_delta = _month_balance(db, test_user, 2026, 6) - sick_before

    db.query(Absence).delete()
    db.commit()
    work_before = _month_balance(db, test_user, 2026, 6)
    _entry(db, test_user, TUESDAY, 9, 17)
    work_delta = _month_balance(db, test_user, 2026, 6) - work_before

    assert sick_delta == work_delta == Decimal("8.00")


def test_kein_deckel_auf_das_tagessoll(db, test_user):
    """Abgrenzung: eine Fortbildung, die laenger dauerte als der Arbeitstag,
    bleibt echte Mehrarbeit — der Tag traegt Soll 8 / Ist 10 = +2. Die Regel
    lautet „die Gutschrift folgt der Soll-STRUKTUR des Tages", NICHT
    „Gutschrift = Soll"."""
    before = _month_balance(db, test_user, 2026, 6)
    _absence(db, test_user, TUESDAY, AbsenceType.TRAINING, hours=10.0)
    assert calculation_service.get_range_target(db, test_user, TUESDAY, TUESDAY) == Decimal("8.00")
    assert calculation_service.get_range_actual(db, test_user, TUESDAY, TUESDAY) == Decimal("10.00")
    assert _month_balance(db, test_user, 2026, 6) == before + Decimal("10.00")


def test_sondertag_ohne_konfiguration_bleibt_voller_werktag(db, test_user):
    """Kontrolltest zum #394-Vorbild: ohne gesetzte Sondertags-Konfiguration
    (Default ``working_day``) ist der 24.12. ein normaler Arbeitstag — volles
    Soll, volle Gutschrift, Gewicht 1,0. Byte-identisch zu vorher."""
    before = _month_balance(db, test_user, 2026, 12)
    _absence(db, test_user, DEC24, AbsenceType.SICK, hours=8.0)
    assert calculation_service.get_range_target(db, test_user, DEC24, DEC24) == Decimal("8.00")
    assert calculation_service.get_range_actual(db, test_user, DEC24, DEC24) == Decimal("8.00")
    assert _month_balance(db, test_user, 2026, 12) == before + Decimal("8.00")


def test_credit_day_weight_direkt(db, test_user):
    """Der Helper selbst — die eine Quelle fuer alle fuenf Flaechen."""
    w = calculation_service.credit_day_weight
    assert w(TUESDAY, set(), {}) == Decimal("1")          # normaler Werktag
    assert w(SATURDAY, set(), {}) == Decimal("0")         # Wochenende
    assert w(WEDNESDAY, {WEDNESDAY}, {}) == Decimal("0")  # Feiertag
    assert w(WEDNESDAY, set(), None) == Decimal("1")      # special_cfg optional

    from app.services import special_days_service
    _special_day(db, "special_day_dec24", "half_day")
    cfg = special_days_service.get_special_day_config(db, DEFAULT_TENANT_ID, 2026)
    assert w(DEC24, set(), cfg) == Decimal("0.5")
    # Ein Feiertag gewinnt auch dann, wenn er zugleich Sondertag ist.
    assert w(DEC24, {DEC24}, cfg) == Decimal("0")


# ---------------------------------------------------------------------------
# Alle Gutschrift-Flaechen muessen dasselbe sagen
# ---------------------------------------------------------------------------

def test_alle_gutschrift_flaechen_stimmen_ueberein(db, test_user):
    """Ueberstundenkonto, Monatsverlauf und YTD duerfen nicht auseinanderlaufen.

    Der Fund lebte in VIER wortgleichen Kopien der Gutschrift-Schleife
    (get_range_actual, get_overtime_account, get_overtime_history_detailed,
    get_ytd_summary). Wird eine davon vergessen, widerspricht das
    Ueberstundenkonto dem Monatsbericht.
    """
    _holiday(db, WEDNESDAY)
    _entry(db, test_user, MONDAY, 9, 17)  # verankert den Konto-Startpunkt
    _absence(db, test_user, WEDNESDAY, AbsenceType.SICK, hours=8.0)
    _absence(db, test_user, SATURDAY, AbsenceType.TRAINING, hours=8.0)

    account = calculation_service.get_overtime_account(db, test_user, 2026, 6)
    history = calculation_service.get_overtime_history_detailed(db, test_user, 2026, 6)

    # Die in MonthlyOvertime gepinnten Invarianten muessen weiter gelten.
    assert history[(2026, 6)].cumulative == account
    assert history[(2026, 6)].actual == calculation_service.get_monthly_actual(db, test_user, 2026, 6)
    assert history[(2026, 6)].target == calculation_service.get_monthly_target(db, test_user, 2026, 6)

    # Weder der Feiertag noch der Samstag hat Ist beigesteuert: das Monats-Ist
    # ist genau die eine gestempelte Schicht.
    assert calculation_service.get_monthly_actual(db, test_user, 2026, 6) == Decimal("8.00")

    ytd = calculation_service.get_ytd_summary(db, test_user, 2026)
    assert ytd["actual_hours"] == 8.00


def test_ytd_zaehlt_die_feiertagsgutschrift_nicht(db, test_user):
    """get_ytd_summary hat eine eigene Gutschrift-Schleife — separat gepinnt."""
    _holiday(db, WEDNESDAY)
    before = calculation_service.get_ytd_summary(db, test_user, 2026)["actual_hours"]
    _absence(db, test_user, WEDNESDAY, AbsenceType.SICK, hours=8.0)
    assert calculation_service.get_ytd_summary(db, test_user, 2026)["actual_hours"] == before


# ---------------------------------------------------------------------------
# Journal — die fuenfte Flaeche (eigene Per-Tag-Schleife)
# ---------------------------------------------------------------------------

def test_journal_feiertag_mit_krank_zeigt_kein_ist(db, test_user):
    """Die Tageszeile muss dasselbe sagen wie das ``monthly_summary`` daneben.

    Der Vorgaenger-Commit dieses Audits addierte die Gutschrift im
    Wochenend-/Feiertagszweig, weil ``get_range_actual`` sie damals ungefiltert
    summierte. Jetzt filtern beide Seiten — und zwar ueber denselben Helper.
    """
    _holiday(db, WEDNESDAY)
    _absence(db, test_user, WEDNESDAY, AbsenceType.SICK, hours=8.0)

    result = journal_service.get_journal(db, test_user, 2026, 6)
    row = next(r for r in result["days"] if r["date"] == WEDNESDAY.isoformat())
    assert row["type"] == "holiday"
    assert row["actual_hours"] == 0.0
    assert row["target_hours"] == 0.0
    assert row["balance"] == 0.0

    # Und die Summe der Tageszeilen deckt sich mit dem Monats-Summary.
    assert sum(r["actual_hours"] for r in result["days"]) == pytest.approx(
        result["monthly_summary"]["actual_hours"])


def test_journal_halber_sondertag_mit_krank_haelftig(db, test_user):
    """Halbtags-Sondertag im Journal: Soll 4 / Ist 4 / Saldo 0."""
    _special_day(db, "special_day_dec24", "half_day")
    _absence(db, test_user, DEC24, AbsenceType.SICK, hours=8.0)

    result = journal_service.get_journal(db, test_user, 2026, 12)
    row = next(r for r in result["days"] if r["date"] == DEC24.isoformat())
    assert row["target_hours"] == 4.0
    assert row["actual_hours"] == 4.0
    assert row["balance"] == 0.0
    assert sum(r["actual_hours"] for r in result["days"]) == pytest.approx(
        result["monthly_summary"]["actual_hours"])


def test_journal_normaler_kranktag_unveraendert(db, test_user):
    """Kontrolltest: der Regelfall bleibt 8 / 8 / 0."""
    _absence(db, test_user, TUESDAY, AbsenceType.SICK, hours=8.0)
    result = journal_service.get_journal(db, test_user, 2026, 6)
    row = next(r for r in result["days"] if r["date"] == TUESDAY.isoformat())
    assert row["target_hours"] == 8.0
    assert row["actual_hours"] == 8.0
    assert row["balance"] == 0.0
