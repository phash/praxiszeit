"""#377 § 2 Abs. 2 MiLoG: Arbeitszeitkonto-Prüfungen (50 % + 12-Monats-Ausgleich).

Reine LESE-Schicht über calculation_service — das auditierte Calc-Modell bleibt
eingefroren. Weiche Warnungen, nichts blockiert. Alle Funktionen liefern None,
wenn das Opt-in-Flag aus ist.

Modellentscheidungen (Spec § 7):
- Vereinbarte Monatszeit ohne Baustein 2 aus den Wochenstunden abgeleitet
  (× 13/3). BEIDE Seiten des 50-%-Vergleichs nutzen diese FLACHE Größe, nicht den
  werktags-/absenz-schwankenden Tages-Soll.
- FIFO-Aging seedet den letzten Jahresabschluss-Carryover als ältesten (noch
  offenen) Posten; ein Konto-Defizit wird als laufender Überhang mitgeführt (ein
  net-negatives Konto hat keine gebankten Stunden); ein nur durch den Carryover-
  Seed getragener Posten wird als "unvollständig prüfbar" markiert (§ 7.3).

Perf: die Router-Hot-Loops (users-overview, dashboard) reichen bereits berechnete
Werte (`monthly_actual`, `detailed`) rein, damit pro MA nur EIN Overtime-Pass läuft.
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


def account_hours_in_month(db, user, year: int, month: int, up_to_date: date = None,
                           monthly_actual=None) -> Decimal:
    """Auf das Konto eingestellte Plusstunden des Monats = max(0, Ist − vereinbarte
    Monatszeit). FLACHE Basis (Spec § 7.1). `monthly_actual` (falls vorberechnet)
    spart den zusätzlichen get_monthly_actual-Pass in den Hot-Loops."""
    if monthly_actual is None:
        monthly_actual = calculation_service.get_monthly_actual(db, user, year, month, up_to_date=up_to_date)
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    surplus = Decimal(str(monthly_actual)) - agreed
    return surplus if surplus > 0 else Decimal("0")


def milog_50_check(db, user, year: int, month: int, up_to_date: date = None,
                   monthly_actual=None):
    """None, wenn Flag aus / kein Stundentracking / keine sinnvolle Vertragszeit /
    Konto-Plusstunden ≤ 50 % der vereinbarten Monatszeit. Sonst
    {account_hours, cap, agreed_monthly, caveat}."""
    if not user.milog_working_time_account or not user.track_hours:
        return None
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    if agreed <= 0:
        # Ein Arbeitszeitkonto mit 0 vereinbarten Monatsstunden hat keine
        # sinnvolle 50-%-Grenze — sonst würde jede Plusstunde warnen.
        return None
    cap = agreed / 2
    account = account_hours_in_month(db, user, year, month, up_to_date=up_to_date,
                                     monthly_actual=monthly_actual)
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


def settlement_aging(db, user, as_of: date, detailed=None):
    """12-Monats-Ausgleichsfrist (§ 2 Abs. 2 S. 2 MiLoG). FIFO über die Monats-
    Deltas (Ist − Soll) des Kontos: Plus = Einzahlung (monatsstamped), Minus =
    Ausgleich (verbraucht älteste zuerst; ein Über-Defizit wird als laufender
    Überhang mitgeführt, damit ein net-negatives Konto keine gebankten Stunden
    zeigt). Der letzte Jahresabschluss-Carryover wird als ÄLTESTER offener Posten
    geseedet; trägt am Ende NUR dieser Seed den offenen Bestand und ist er (nach
    konservativem Alter) nicht überfällig, wird `incomplete=True` gesetzt (das
    wahre Alter der gefalteten Vor-Carryover-Historie ist unbekannt, § 7.3).

    None, wenn Flag aus / kein Stundentracking / kein offener Posten. `detailed`
    (falls vorberechnet) spart den get_overtime_history_detailed-Pass."""
    if not user.milog_working_time_account or not user.track_hours:
        return None
    if detailed is None:
        detailed = calculation_service.get_overtime_history_detailed(db, user, as_of.year, as_of.month)
    if not detailed:
        return None

    deposits = []  # [[year, month, remaining_hours, is_seed]] FIFO
    carried_deficit = Decimal("0")

    # letzter Carryover ≤ as_of-Jahr = letzte Konto-Fortschreibung; sein Saldo ist
    # der Öffnungssaldo (Alt-Stunden), gestempelt auf Dez des Vorjahres → maximales
    # (konservatives) Alter. F-026: tenant-scoped Query.
    carryovers = [c for c in db.query(YearCarryover).filter(
        YearCarryover.user_id == user.id,
        YearCarryover.tenant_id == user.tenant_id,
    ).all() if c.year <= as_of.year]
    start_ym = None
    if carryovers:
        latest = max(carryovers, key=lambda c: c.year)
        start_ym = (latest.year, 1)
        opening = Decimal(str(latest.overtime_hours))
        if opening > 0:
            deposits.append([latest.year - 1, 12, opening, True])
        elif opening < 0:
            carried_deficit = -opening

    for (y, m) in sorted(detailed.keys()):
        if start_ym is not None and (y, m) < start_ym:
            continue
        mo = detailed[(y, m)]
        delta = Decimal(str(mo.actual)) - Decimal(str(mo.target))
        if delta > 0:
            # zuerst ein mitgeführtes Defizit auffüllen (Konto klettert erst auf 0)
            if carried_deficit > 0:
                use = min(carried_deficit, delta)
                carried_deficit -= use
                delta -= use
            if delta > 0:
                deposits.append([y, m, delta, False])
        elif delta < 0:
            owe = -delta
            while owe > 0 and deposits:
                if deposits[0][2] <= owe:
                    owe -= deposits[0][2]
                    deposits.pop(0)
                else:
                    deposits[0][2] -= owe
                    owe = Decimal("0")
            if owe > 0:
                carried_deficit += owe

    if not deposits:
        return None
    oy, om, rem, is_seed = deposits[0]
    age = (as_of.year - oy) * 12 + (as_of.month - om)
    overdue = age > 12  # "binnen zwölf Kalendermonaten" → überfällig erst ab M+13
    # Nur-Seed-getragener, (noch) nicht überfälliger Bestand: wahres Alter unbekannt.
    incomplete = bool(is_seed and not overdue)
    return {"oldest_year": oy, "oldest_month": om, "age_months": age,
            "hours": float(rem), "overdue": overdue, "due_soon": 11 <= age <= 12,
            "incomplete": incomplete}


def settlement_warning_text(aging: dict) -> str:
    if aging.get("incomplete"):
        return (
            f"MILOG_SETTLEMENT_DUE: Konto-Stunden aus einem abgeschlossenen Jahr "
            f"({aging['hours']:.1f}h) — Konto kann nicht vollständig auf die 12-Monats-"
            f"Ausgleichsfrist geprüft werden (§ 2 Abs. 2 MiLoG), bitte manuell prüfen."
        )
    when = "überfällig" if aging["overdue"] else "bald fällig"
    return (
        f"MILOG_SETTLEMENT_DUE: Konto-Stunden aus {aging['oldest_month']:02d}/{aging['oldest_year']} "
        f"({aging['hours']:.1f}h) {when} — Ausgleich binnen 12 Monaten (§ 2 Abs. 2 MiLoG)."
    )
