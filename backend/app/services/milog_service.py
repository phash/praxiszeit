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
from calendar import monthrange
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


def agreed_monthly_hours(db, user, ref_date: date, wh_changes=None) -> Decimal:
    """Vertraglich vereinbarte Monatszeit. #377 Baustein 2a: wenn für den Monat
    eine Monatszahl hinterlegt ist (`agreed_monthly_hours`), gilt diese exakt;
    sonst flach aus den Wochenstunden(zum Datum) abgeleitet (× 13/3).

    Teil A (Task 11): die Zahl kommt aus dem Monatsvertrag (Snapshot am
    Monatsersten von ``ref_date``), nie aus der User-Zeile."""
    explicit = calculation_service.month_contract(
        db, user, ref_date.year, ref_date.month, wh_changes).agreed_monthly_hours
    if explicit is not None:
        return Decimal(str(explicit))
    weekly = calculation_service.get_weekly_hours_for_date(db, user, ref_date, wh_changes)
    return Decimal(str(weekly)) * AGREED_MONTHLY_FACTOR


def _tracks_hours_in_month(db, user, year: int, month: int, wh_changes) -> bool:
    """F002: ``track_hours`` darf mitten im Monat wechseln (anders als die drei
    Minijob-Felder, die nur zum Monatsersten wirken). Der Monat hat ein
    Arbeitszeitkonto, sobald an IRGENDEINEM seiner Tage Stunden gezählt werden —
    das Konto (``get_overtime_history_detailed``) bucht genau diesen Anteil."""
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return calculation_service.tracks_hours_in_range(db, user, first, last, wh_changes)


def month_has_account(db, user, year: int, month: int, wh_changes=None) -> bool:
    """Hat der Monat ein MiLoG-Arbeitszeitkonto? Konto-Flag laut Monatsvertrag
    (Snapshot am 1.) UND Stundenzählung an irgendeinem Tag des Monats (F002) —
    DAS Gate aller MiLoG-Warnflächen."""
    if wh_changes is None:
        wh_changes = calculation_service.user_wh_changes(db, user)
    mc = calculation_service.month_contract(db, user, year, month, wh_changes)
    return mc.milog_working_time_account and _tracks_hours_in_month(db, user, year, month, wh_changes)


def account_hours_in_month(db, user, year: int, month: int, up_to_date: date = None,
                           monthly_actual=None, wh_changes=None) -> Decimal:
    """Auf das Konto eingestellte Plusstunden des Monats = max(0, Ist − vereinbarte
    Monatszeit). FLACHE Basis (Spec § 7.1). `monthly_actual` (falls vorberechnet)
    spart den zusätzlichen get_monthly_actual-Pass in den Hot-Loops; ``wh_changes``
    (Preload der Verlaufszeilen, Teil A) die Vertrags-Queries."""
    if monthly_actual is None:
        monthly_actual = calculation_service.get_monthly_actual(db, user, year, month, up_to_date=up_to_date,
                                                                wh_changes=wh_changes)
    agreed = agreed_monthly_hours(db, user, date(year, month, 1), wh_changes)
    surplus = Decimal(str(monthly_actual)) - agreed
    return surplus if surplus > 0 else Decimal("0")


def milog_50_check(db, user, year: int, month: int, up_to_date: date = None,
                   monthly_actual=None, wh_changes=None):
    """None, wenn Flag aus / kein Stundentracking / keine sinnvolle Vertragszeit /
    Konto-Plusstunden ≤ 50 % der vereinbarten Monatszeit. Sonst
    {account_hours, cap, agreed_monthly, caveat}."""
    # Teil A (Task 11): beide Flags aus DEMSELBEN Monatsvertrag.
    if wh_changes is None:  # Teil A (Task 12): einmal laden, an alle Helfer reichen
        wh_changes = calculation_service.user_wh_changes(db, user)
    if not month_has_account(db, user, year, month, wh_changes):
        return None
    agreed = agreed_monthly_hours(db, user, date(year, month, 1), wh_changes)
    if agreed <= 0:
        # Ein Arbeitszeitkonto mit 0 vereinbarten Monatsstunden hat keine
        # sinnvolle 50-%-Grenze — sonst würde jede Plusstunde warnen.
        return None
    cap = agreed / 2
    account = account_hours_in_month(db, user, year, month, up_to_date=up_to_date,
                                     monthly_actual=monthly_actual, wh_changes=wh_changes)
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


def monthly_exceeded_check(db, user, year: int, month: int, up_to_date: date = None,
                           wh_changes=None):
    """#377 Baustein 2b: weiche Plausibilitäts-Warnung, wenn das Monats-Ist
    (inkl. Gutschriften) die vereinbarte Monatsarbeitszeit eines Fix-Modus-MA
    übersteigt. None, wenn der Modus aus ist / kein Stundentracking / keine
    vereinbarte Monatszahl hinterlegt / Ist ≤ agreed. Prüft hier bewusst NUR
    `use_fixed_monthly_target` + `track_hours` (nicht `milog_working_time_
    account`) — reine Fix-Soll-Plausibilität, kein 50-%-/Aging-Bezug. Das ist
    trotzdem KONSISTENT mit den anderen #377-Warnungen: `use_fixed_monthly_
    target=True` setzt `milog_working_time_account=True` zwingend voraus
    (Invariante, erzwungen beim Anlegen — `UserBase.check_fixed_monthly_target_
    requirements` — und für jede Verlaufszeile auf deren Snapshot —
    `admin_users._contract_rule_error`), also ist in jedem Monat mit festem Soll
    das Konto-Flag ohnehin an. Alle 5 Call-Sites (dashboard.py, admin_users.py,
    time_entries.py) rufen diese Funktion folglich nur hinter dem Konto-Gate des
    Monatsvertrags auf — das ist KEINE zusätzliche Einschränkung, sondern deckt
    sich mit der Invariante."""
    # Teil A (Task 11): Modus und Zahl aus dem Monatsvertrag, Stundenzählung an
    # irgendeinem Tag des Monats (F002).
    if wh_changes is None:  # Teil A (Task 12): einmal laden, an alle Helfer reichen
        wh_changes = calculation_service.user_wh_changes(db, user)
    mc = calculation_service.month_contract(db, user, year, month, wh_changes)
    if not mc.use_fixed_monthly_target or not _tracks_hours_in_month(db, user, year, month, wh_changes):
        return None
    agreed = mc.agreed_monthly_hours
    if not agreed:
        return None
    agreed = Decimal(str(agreed))
    actual = calculation_service.get_monthly_actual(db, user, year, month, up_to_date=up_to_date,
                                                    wh_changes=wh_changes)
    if actual > agreed:
        return {"month_actual": float(actual), "agreed": float(agreed), "year": year, "month": month}
    return None


def monthly_exceeded_warning_text(chk: dict) -> str:
    """Stabiler Warncode + Detailtext (wie milog_50_warning_text)."""
    return (f"MILOG_MONTHLY_EXCEEDED: Erfasste Stunden {chk['month_actual']:.1f}h im "
            f"{chk['month']:02d}/{chk['year']} übersteigen die vereinbarte Monatsarbeitszeit "
            f"({chk['agreed']:.1f}h). Bitte prüfen (sofern zur Mindestlohnhöhe vergütet).")


def settlement_aging(db, user, as_of: date, detailed=None, wh_changes=None):
    """12-Monats-Ausgleichsfrist (§ 2 Abs. 2 S. 2 MiLoG). FIFO über die Monats-
    Deltas (Ist − Soll) des Kontos: Plus = Einzahlung (monatsstamped), Minus =
    Ausgleich (verbraucht älteste zuerst; ein Über-Defizit wird als laufender
    Überhang mitgeführt, damit ein net-negatives Konto keine gebankten Stunden
    zeigt). Der letzte Jahresabschluss-Carryover wird als ÄLTESTER offener Posten
    geseedet; trägt am Ende NUR dieser Seed den offenen Bestand und ist er (nach
    konservativem Alter) nicht überfällig, wird `incomplete=True` gesetzt (das
    wahre Alter der gefalteten Vor-Carryover-Historie ist unbekannt, § 7.3).

    None, wenn Flag aus / kein Stundentracking / kein offener Posten. `detailed`
    (falls vorberechnet) spart den get_overtime_history_detailed-Pass.

    Teil A (Task 11): Konto-Flag je MONAT laut Monatsvertrag, Stundenzählung an
    irgendeinem Tag des Monats (F002, ``_tracks_hours_in_month``) — None,
    wenn der Monat von ``as_of`` kein Arbeitszeitkonto hat; das FIFO nimmt nur
    Monate mit Konto auf (Monate ohne Konto zahlen weder ein noch aus).
    ``wh_changes`` = optionaler Preload der Verlaufszeilen (Task 12)."""
    if wh_changes is None:
        wh_changes = calculation_service.user_wh_changes(db, user)

    def _account_month(y: int, m: int) -> bool:
        return month_has_account(db, user, y, m, wh_changes)

    if not _account_month(as_of.year, as_of.month):
        return None
    if detailed is None:
        # Finding 8 (review 2026-07-14): a direct call (no pre-computed
        # ``detailed``) MUST apply the #313 Saldo-Stichtag itself — mirrors the
        # push-callers (dashboard.py / admin_users.py), which always compute
        # this cutoff before calling get_overtime_history_detailed. Without it
        # the running, unfinished month is compared against a FULL month-Soll
        # while only month-to-date Ist exists, fabricating a phantom deficit
        # that eats the FIFO seed and silently drops MILOG_SETTLEMENT_DUE.
        cutoff = calculation_service.get_soll_cutoff_date(db, user, today=as_of)
        detailed = calculation_service.get_overtime_history_detailed(
            db, user, as_of.year, as_of.month, cutoff_date=cutoff, wh_changes=wh_changes
        )
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

    # #377 Baustein 2a bewusst SOLL-basiert (Review-Entscheid): das 12-Monats-
    # Aging akkumuliert die pro Monat gebankten Plusstunden = Ist − das TATSÄCHLICHE
    # Monats-Soll dieses Monats. Das Soll neutralisiert Feiertage, Soll-reduzierende
    # Abwesenheiten (Urlaub/bezahlte Freistellung), Beschäftigungs-Teilmonate und
    # den Saldo-Stichtag korrekt (Urlaub ist KEIN Freizeitausgleich und darf das
    # Arbeitszeitkonto nicht belasten). Die vereinbarte Monatszahl (agreed_monthly_
    # hours) ist die vertragliche Bezugsgröße für die 50-%-PRÜFUNG, nicht die
    # Monats-Duty für die Akkumulation — daher fließt sie hier bewusst NICHT ein.
    for (y, m) in sorted(detailed.keys()):
        if start_ym is not None and (y, m) < start_ym:
            continue
        if not _account_month(y, m):  # Teil A: Monat ohne Arbeitszeitkonto
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
