"""#377 § 2 Abs. 2 MiLoG: Arbeitszeitkonto-Prüfungen (50 % + 12-Monats-Ausgleich).

Reine LESE-Schicht über calculation_service — das auditierte Calc-Modell bleibt
eingefroren. Weiche Warnungen, nichts blockiert. Alle Funktionen liefern None,
wenn das Opt-in-Flag aus ist.

Modellentscheidungen (Spec § 7):
- Vereinbarte Monatszeit ohne Baustein 2 aus den Wochenstunden abgeleitet
  (× 13/3). BEIDE Seiten des 50-%-Vergleichs nutzen diese FLACHE Größe, nicht den
  werktags-/absenz-schwankenden Tages-Soll — sonst false-fires in kurzen und
  verpasste Verstöße in langen Monaten.
- FIFO-Aging seedet den letzten Jahresabschluss-Carryover als ältesten (noch
  offenen) Posten, sonst wären die überfällig-verdächtigen Alt-Stunden unsichtbar.
"""
from datetime import date
from decimal import Decimal

from app.models import YearCarryover
from app.services import calculation_service

AGREED_MONTHLY_FACTOR = Decimal(13) / Decimal(3)  # 52 Wochen / 12 Monate = 4,333…

# Der § 2 Abs. 2 MiLoG-Deckel bindet nur die MINDESTLOHNWIRKSAMEN Stunden; da
# PraxisZeit keine Lohndaten hält, ist die reine Stundenprüfung eine WEICHE
# Warnung. Dieser Zusatz macht das transparent (Spec § 7.2).
_WAGE_CAVEAT = ("sofern zur Mindestlohnhöhe vergütet; bei höherer Vergütung ggf. "
                "unkritisch — bitte prüfen")


def agreed_monthly_hours(db, user, ref_date: date) -> Decimal:
    """Vertraglich vereinbarte Monatszeit = Wochenstunden(zum Datum) × 13/3.
    (Baustein 2 ersetzt das später durch eine direkt vereinbarte Monatszahl.)"""
    weekly = calculation_service.get_weekly_hours_for_date(db, user, ref_date)
    return Decimal(str(weekly)) * AGREED_MONTHLY_FACTOR


def account_hours_in_month(db, user, year: int, month: int, up_to_date: date = None) -> Decimal:
    """Auf das Konto eingestellte Plusstunden des Monats = max(0, Ist − vereinbarte
    Monatszeit). FLACHE Basis (nicht der Tages-Soll), damit sie nicht mit der
    Werktagszahl schwankt und ein bezahlter Abwesenheitstag keine Extra-Kapazität
    vortäuscht (Spec § 7.1)."""
    actual = calculation_service.get_monthly_actual(db, user, year, month, up_to_date=up_to_date)
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    surplus = Decimal(str(actual)) - agreed
    return surplus if surplus > 0 else Decimal("0")


def milog_50_check(db, user, year: int, month: int, up_to_date: date = None):
    """None, wenn Flag aus / kein Stundentracking / Konto-Plusstunden ≤ 50 % der
    vereinbarten Monatszeit. Sonst {account_hours, cap, agreed_monthly, caveat}."""
    if not user.milog_working_time_account or not user.track_hours:
        return None
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    cap = agreed / 2
    account = account_hours_in_month(db, user, year, month, up_to_date=up_to_date)
    if account > cap:
        return {"account_hours": float(account), "cap": float(cap),
                "agreed_monthly": float(agreed), "caveat": _WAGE_CAVEAT}
    return None


def milog_50_warning_text(chk: dict) -> str:
    """Stabiler Warncode + Detailtext für das `warnings`-Muster (wie ArbZG)."""
    return (
        f"MILOG_ACCOUNT_50: Konto-Plusstunden dieses Monats ({chk['account_hours']:.1f}h) "
        f"über 50 % der vereinbarten Monatszeit (Grenze {chk['cap']:.1f}h, § 2 Abs. 2 MiLoG; "
        f"{chk['caveat']})."
    )


def settlement_aging(db, user, as_of: date):
    """12-Monats-Ausgleichsfrist (§ 2 Abs. 2 S. 2 MiLoG). FIFO über die
    Monats-Deltas (Ist − Soll) des Kontos: Plus = Einzahlung (monatsstamped),
    Minus = Ausgleich (verbraucht älteste zuerst). Der letzte Jahresabschluss-
    Carryover wird als ÄLTESTER offener Posten geseedet (sonst wären die
    überfällig-verdächtigen Alt-Stunden unsichtbar). None, wenn Flag aus / kein
    offener Posten."""
    if not user.milog_working_time_account or not user.track_hours:
        return None
    detailed = calculation_service.get_overtime_history_detailed(db, user, as_of.year, as_of.month)
    if not detailed:
        return None

    deposits = []  # [[year, month, remaining_hours]] FIFO
    # letzter Carryover ≤ as_of-Jahr = letzte Konto-Fortschreibung; seine
    # overtime_hours sind der Öffnungssaldo (Alt-Stunden), gestempelt auf Dez des
    # Vorjahres → maximales (konservatives) Alter.
    carryovers = [c for c in db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id).all() if c.year <= as_of.year]
    start_ym = None
    if carryovers:
        latest = max(carryovers, key=lambda c: c.year)
        start_ym = (latest.year, 1)
        opening = Decimal(str(latest.overtime_hours))
        if opening > 0:
            deposits.append([latest.year - 1, 12, opening])

    for (y, m) in sorted(detailed.keys()):
        if start_ym is not None and (y, m) < start_ym:
            continue
        mo = detailed[(y, m)]
        delta = Decimal(str(mo.actual)) - Decimal(str(mo.target))
        if delta > 0:
            deposits.append([y, m, delta])
        elif delta < 0:
            owe = -delta
            while owe > 0 and deposits:
                if deposits[0][2] <= owe:
                    owe -= deposits[0][2]
                    deposits.pop(0)
                else:
                    deposits[0][2] -= owe
                    owe = Decimal("0")

    if not deposits:
        return None
    oy, om, rem = deposits[0]
    age = (as_of.year - oy) * 12 + (as_of.month - om)
    # "binnen zwölf Kalendermonaten": überfällig erst AB Monat M+13 (Spec § 7.4).
    return {"oldest_year": oy, "oldest_month": om, "age_months": age,
            "hours": float(rem), "overdue": age > 12, "due_soon": 11 <= age <= 12}


def settlement_warning_text(aging: dict) -> str:
    when = "überfällig" if aging["overdue"] else "bald fällig"
    return (
        f"MILOG_SETTLEMENT_DUE: Konto-Stunden aus {aging['oldest_month']:02d}/{aging['oldest_year']} "
        f"({aging['hours']:.1f}h) {when} — Ausgleich binnen 12 Monaten (§ 2 Abs. 2 MiLoG)."
    )
