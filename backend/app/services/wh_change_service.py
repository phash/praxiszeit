"""Spec 2026-10-08, Abschnitt 9: Rückwirkung einer Arbeitszeit-Änderung.

EIN Rechenpfad (9.3 Schritte 2–7) für Anlegen, Löschen und beide Vorschauen:

2. offene Einträge vergangener Tage im Wirkungsbereich schließen (P23) — unter
   dem ALTEN Snapshot, mit der handelnden Admin als ``changed_by``;
3. Saldo, heutigen Tag und volles Tagessoll je Abwesenheit VORHER festhalten;
4. die Änderung anwenden (Callback: Zeile anlegen bzw. löschen);
5. Einträge der geänderten Wochentage neu kappen (aktueller Puffer, E47);
6. Abwesenheiten mit F1-Klemmung nachziehen (E51 — erst Einträge, dann
   Abwesenheiten);
7. Saldo nachher und Klassifikation nach 9.4/9.5 (a)–(c).

Kein commit, kein Protokoll, keine Sperre: das gehört dem Router — die Vorschau
rollt danach zurück und darf nichts festschreiben (E57).
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, NamedTuple, Optional

from sqlalchemy.orm import Session

from app.models import TimeEntry, User, WorkingHoursChange
from app.services import (
    calculation_service, presence_service, timezone_service, work_blocks_service, work_window_service,
)

SHORTENING_ENTRIES = "entries"
SHORTENING_SALDO = "saldo"
SHORTENING_ABSENCE_CREDIT = "absence_credit"

P25_NOTE = "Die Änderung liegt vollständig vor der Änderung ab {date}; nur rückwirkend mit Begründung oder abbrechen."
MILOG_ACCOUNT_WARNING = (
    "Diese Person führt ein Arbeitszeitkonto nach § 2 Abs. 2 MiLoG bzw. hat eine vereinbarte "
    "Monatsarbeitszeit. Eine rückwirkende Kürzung angerechneter Zeit verändert den Kontostand und kann "
    "Mindestlohnansprüche sowie die 12-Monats-Ausgleichsfrist berühren."
)
MILOG_GENERAL_WARNING = (
    "Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung Mindestlohnansprüche (§§ 1, 3 MiLoG) "
    "und die Aufzeichnung nach § 17 MiLoG berühren."
)
SONSTIGES_CONFIRM_DETAIL = (
    "Bei „Sonstiges“ bitte bestätigen, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht "
    "nicht gedeckt ist."
)
_ASK = "Bitte Grund, Begründung und die Bestätigung zum Vergütungsrisiko angeben"
_ZERO = Decimal("0")


class ChangeImpact(NamedTuple):
    window: object                 # calculation_service.RetargetWindow
    grace: int                     # angewandter (aktueller) Mandanten-Puffer, E47
    old_schedule: object           # Snapshot am Wirkungsdatum VOR der Änderung
    new_schedule: object           # … und danach
    changed_weekdays: list
    stale_closed: int              # P23: vorher geschlossene Alteinträge
    reclamp: object                # work_window_service.ReclampResult
    open_entry_loses: bool         # P1: offener Eintrag von heute verliert
    absences: list                 # alle nachgezogenen AbsenceRetarget
    credit_reductions: list        # davon 9.5 (c)
    target_delta: Decimal
    credited_delta: Decimal
    saldo_delta: Decimal
    open_day_saldo_delta: Decimal
    shortening_reasons: list
    shortening_closed_years: list
    earliest_lossless_date: Optional[date]
    earliest_lossless_note: Optional[str]
    months: list
    arbzg: dict
    entries_before: dict           # id → transiente Kopie „vorher" (Protokoll 10.1)

    @property
    def is_shortening(self) -> bool:
        return bool(self.shortening_reasons)


def _saldo_by_year(db: Session, user: User, start: date, end: date, cutoff: date) -> Dict[int, tuple]:
    """Spec 9.5 (b): (Soll, Ist) je Jahr über die Monate des Wirkungsbereichs bis
    zum Saldo-Stichtag (#313), über ``get_monthly_target``/``get_monthly_actual``
    (der #377-Fix-Modus geht so mit), OHNE Jahresüberträge. Tage vor ``start``
    im ersten Monat ändern sich durch die Änderung nicht — sie fallen in der
    Differenz heraus."""
    last = min(end, cutoff)
    result: Dict[int, tuple] = {}
    if last < start:
        return result
    y, m = start.year, start.month
    while (y, m) <= (last.year, last.month):
        target = calculation_service.get_monthly_target(db, user, y, m, up_to_date=cutoff)
        actual = calculation_service.get_monthly_actual(db, user, y, m, up_to_date=cutoff)
        t0, a0 = result.get(y, (_ZERO, _ZERO))
        result[y] = (t0 + target, a0 + actual)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return result


def _day_saldo(db: Session, user: User, d: date) -> Decimal:
    """Saldo-Anteil EINES Tages (Gutschrift/Ist − Soll), wie die Monatsfunktionen
    ihn zählen; ein offener Eintrag trägt 0 h bei (``net_hours`` ohne Ende)."""
    return (calculation_service.get_range_actual(db, user, d, d)
            - calculation_service.get_range_target(db, user, d, d))


def _snapshot(e: TimeEntry) -> TimeEntry:
    """Transiente Kopie (nie in der Session) — „vorher" für Protokoll (10.1) und
    ArbZG-Befunde (P22)."""
    return TimeEntry(date=e.date, start_time=e.start_time, end_time=e.end_time,
                     raw_start_time=e.raw_start_time, raw_end_time=e.raw_end_time,
                     break_minutes=e.break_minutes, uncredited_minutes=e.uncredited_minutes,
                     auto_closed=e.auto_closed)


def _arbzg_counts(entries, minutes_of: Callable) -> tuple:
    """(Tage > 10 h, Kalenderwochen > 48 h) — Grenzen und Minutenrechnung wie die
    weichen Anwesenheits-Warnungen (``presence_service``, P22), damit Vorschau
    und Warnung an der Grenze nicht auseinanderlaufen."""
    per_day: Dict = defaultdict(int)
    per_week: Dict = defaultdict(int)
    for e in entries:
        minutes = minutes_of(e)
        per_day[e.date] += minutes
        per_week[e.date.isocalendar()[:2]] += minutes
    return (sum(1 for v in per_day.values() if v > presence_service.DAILY_LIMIT_MINUTES),
            sum(1 for v in per_week.values() if v > presence_service.WEEKLY_LIMIT_MINUTES))


def _credited_minutes(e) -> int:
    return presence_service.credited_minutes([e])


def _next_change(db: Session, user: User, effective_from: date) -> Optional[WorkingHoursChange]:
    return db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
        WorkingHoursChange.effective_from > effective_from,
    ).order_by(WorkingHoursChange.effective_from.asc()).first()


def run_change(db: Session, user: User, *, admin_id, effective_from: date,
               apply: Callable[[], None]) -> ChangeImpact:
    """Spec 9.3 Schritte 2–7 (Docstring des Moduls). ``apply`` legt die neue Zeile
    an bzw. löscht die bestehende — ohne commit."""
    from app.routers.time_entries import _close_stale_entry  # lokal: kein Router-Import beim Modul-Laden

    today = timezone_service.today_local()
    window = calculation_service.retarget_window(db, user, effective_from)

    # Schritt 2 (P23): offene Einträge vergangener Tage — unter dem alten Snapshot,
    # mit ihrem gespeicherten Puffer, Audit ``auto_close`` mit der Admin.
    stale = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        TimeEntry.end_time.is_(None),
        TimeEntry.date >= window.start,
        TimeEntry.date <= window.end,
        TimeEntry.date < today,
    ).order_by(TimeEntry.date).all()
    for e in stale:
        _close_stale_entry(db, e, changed_by_id=admin_id)
    if stale:
        db.flush()

    # Schritt 3 — nach Schritt 2: das Schließen ist nicht Wirkung der Änderung.
    old_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    cutoff = calculation_service.get_soll_cutoff_date(db, user, today)
    today_in_window = window.start <= today <= window.end
    open_today = None
    if today_in_window:
        open_today = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,  # F-026
            TimeEntry.date == today,
            TimeEntry.end_time.is_(None),
        ).first()
    # Heute offener Tag (9.5 (b)): offener Eintrag, kein geschlossener — der Tag
    # liegt hinter dem Stichtag. Zählt heute schon (Stichtag heute), gehört sein
    # Anteil zu ``saldo_delta`` und entscheidet über H (``earliest_lossless_date``).
    open_day = open_today is not None and cutoff < today
    today_counts = today_in_window and cutoff == today
    saldo_before = _saldo_by_year(db, user, window.start, window.end, cutoff)
    today_before = _day_saldo(db, user, today) if (open_day or today_counts) else _ZERO
    old_full = calculation_service.absence_full_targets(db, user, window.start, window.end)
    old_today_blocks = work_window_service.get_scheduled_blocks(db, user, today) if open_today else []
    before = {e.id: _snapshot(e) for e in presence_service.closed_entries(db, user, window.start, window.end)}

    # Schritt 4
    apply()
    db.flush()

    # Schritt 5
    new_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    weekdays = work_blocks_service.changed_weekdays(old_schedule.blocks, new_schedule.blocks)
    grace = work_window_service.get_grace_minutes(db, user.tenant_id)
    reclamp = work_window_service.reclamp_time_entries(
        db, user, window.start, window.end, set(weekdays), old_schedule.blocks, grace)
    db.flush()
    open_loses = False
    if (open_today is not None and user.track_hours and not open_today.credit_override
            and today.weekday() in weekdays):
        # P1: das Ausstempeln kappt mit dem gespeicherten Puffer des Eintrags (E80).
        open_loses = work_window_service.open_entry_loses(
            old_today_blocks, work_window_service.get_scheduled_blocks(db, user, today),
            work_window_service.grace_for_entry(db, open_today), open_today.start_time,
            timezone_service.now_local().time(),
        )

    # Schritt 6 (E51: erst Einträge, dann Abwesenheiten)
    absences = []
    if window.has_absences:
        absences = calculation_service.retarget_absence_hours(
            db, user, window.start, window.end, old_full_target_by_date=old_full)

    # Schritt 7
    saldo_after = _saldo_by_year(db, user, window.start, window.end, cutoff)
    years = sorted(set(saldo_before) | set(saldo_after))
    zero = (_ZERO, _ZERO)
    target_delta = sum((saldo_after.get(y, zero)[0] - saldo_before.get(y, zero)[0] for y in years), _ZERO)
    credited_delta = sum((saldo_after.get(y, zero)[1] - saldo_before.get(y, zero)[1] for y in years), _ZERO)
    saldo_by_year = {
        y: (saldo_after.get(y, zero)[1] - saldo_after.get(y, zero)[0])
        - (saldo_before.get(y, zero)[1] - saldo_before.get(y, zero)[0])
        for y in years
    }
    saldo_delta = credited_delta - target_delta
    today_delta = (_day_saldo(db, user, today) - today_before) if (open_day or today_counts) else _ZERO
    open_day_delta = today_delta if open_day else _ZERO

    losing = [c for c in reclamp.changed if c.new_net < c.old_net]
    reductions = [a for a in absences if a.credit_reduction]
    closed = calculation_service.closed_years_in_range(
        db, user.tenant_id, range(window.start.year, window.end.year + 1))
    reasons = []
    if losing or open_loses:
        reasons.append(SHORTENING_ENTRIES)
    if saldo_delta < 0 or open_day_delta < 0 or any(saldo_by_year.get(y, _ZERO) < 0 for y in closed):
        reasons.append(SHORTENING_SALDO)
    if reductions:
        reasons.append(SHORTENING_ABSENCE_CREDIT)
    loss_years = ({c.date.year for c in losing} | {a.date.year for a in reductions}
                  | {y for y, d in saldo_by_year.items() if d < 0})
    if open_loses or open_day_delta < 0:
        loss_years.add(today.year)

    # 9.5: earliest_lossless_date = max(heute, A + 1, C + 1, H), begrenzt durch P25.
    earliest, note = None, None
    if reasons:
        tomorrow = today + timedelta(days=1)
        candidates = [today]
        if losing:
            candidates.append(max(c.date for c in losing) + timedelta(days=1))           # A
        if reductions:
            candidates.append(max(a.date for a in reductions) + timedelta(days=1))       # C
        if open_loses or (today_counts and today_delta < 0) or open_day_delta < 0:
            candidates.append(tomorrow)                                                   # A heute / H (P1)
        earliest = max(candidates)
        nxt = _next_change(db, user, effective_from)
        if nxt is not None and earliest >= nxt.effective_from:                            # P25
            note = P25_NOTE.format(date=nxt.effective_from.strftime("%d.%m.%Y"))
            earliest = None

    months: Dict[str, list] = defaultdict(lambda: [0, _ZERO, _ZERO])
    for c in reclamp.changed:
        bucket = months[c.date.strftime("%Y-%m")]
        bucket[0] += 1
        bucket[1] += c.old_net
        bucket[2] += c.new_net
    after = presence_service.closed_entries(db, user, window.start, window.end)
    credited_before = _arbzg_counts(before.values(), _credited_minutes)
    credited_after = _arbzg_counts(after, _credited_minutes)
    presence = _arbzg_counts(after, work_window_service.presence_minutes)

    return ChangeImpact(
        window=window, grace=grace, old_schedule=old_schedule, new_schedule=new_schedule,
        changed_weekdays=weekdays, stale_closed=len(stale), reclamp=reclamp, open_entry_loses=open_loses,
        absences=absences, credit_reductions=reductions, target_delta=target_delta,
        credited_delta=credited_delta, saldo_delta=saldo_delta, open_day_saldo_delta=open_day_delta,
        shortening_reasons=reasons,
        shortening_closed_years=sorted(y for y in closed if y in loss_years) if reasons else [],
        earliest_lossless_date=earliest, earliest_lossless_note=note,
        months=[{"month": k, "entries": v[0], "net_before": float(v[1]), "net_after": float(v[2])}
                for k, v in sorted(months.items())],
        arbzg={
            "days_over_10_credited_before": credited_before[0],
            "days_over_10_credited_after": credited_after[0],
            "days_over_10_presence": presence[0],
            "weeks_over_48_credited_before": credited_before[1],
            "weeks_over_48_credited_after": credited_after[1],
            "weeks_over_48_presence": presence[1],
        },
        entries_before=before,
    )


def _change_out(c) -> dict:
    return {
        "entry_id": str(c.entry_id), "date": c.date,
        "old_start": c.old_start, "old_end": c.old_end, "old_uncredited": c.old_uncredited,
        "old_net": float(c.old_net), "new_start": c.new_start, "new_end": c.new_end,
        "new_uncredited": c.new_uncredited, "new_net": float(c.new_net), "not_extendable": c.not_extendable,
    }


def milog_warnings(user, impact: ChangeImpact) -> List[str]:
    """Spec 9.5/P26: nur bei einer Verkürzung — Konto-/Monatszeit-Satz bei
    ``milog_working_time_account`` oder ``agreed_monthly_hours``, der allgemeine
    Mindestlohnsatz bei JEDER (Minijobber ohne Kennzeichen, Risiko 9)."""
    if not impact.is_shortening:
        return []
    out = []
    if getattr(user, "milog_working_time_account", False) or getattr(user, "agreed_monthly_hours", None):
        out.append(MILOG_ACCOUNT_WARNING)
    out.append(MILOG_GENERAL_WARNING)
    return out


def preview_fields(impact: ChangeImpact, user) -> dict:
    """Spec 11.3: die neuen Vorschau-Felder aus EINEM flush/Rollback-Lauf."""
    changed = impact.reclamp.changed
    return {
        "changed_weekdays": impact.changed_weekdays,
        "affected_time_entries": len(changed),
        "time_entry_months": impact.months,
        "time_entry_changes": [_change_out(c) for c in changed],
        "skipped_time_entries": [
            {"entry_id": str(s.entry_id), "date": s.date, "reason": s.reason} for s in impact.reclamp.skipped],
        "not_extendable_count": len(impact.reclamp.flagged),
        "not_extendable_entries": [_change_out(c) for c in impact.reclamp.flagged],
        "is_shortening": impact.is_shortening,
        "shortening_reasons": impact.shortening_reasons,
        "shortening_closed_years": impact.shortening_closed_years,
        "earliest_lossless_date": impact.earliest_lossless_date,
        "earliest_lossless_note": impact.earliest_lossless_note,
        "lost_credited_hours": float(sum((c.old_net - c.new_net for c in changed if c.new_net < c.old_net), _ZERO)),
        "target_delta_hours": float(impact.target_delta),
        "credited_delta_hours": float(impact.credited_delta),
        "saldo_delta_hours": float(impact.saldo_delta),
        "open_day_saldo_delta_hours": float(impact.open_day_saldo_delta),
        "absence_f1_adjustments": sum(1 for a in impact.absences if a.f1_clamped),
        "absence_credit_reductions": [
            {"absence_id": str(a.absence_id), "date": a.date, "old_hours": float(a.old_hours),
             "new_hours": float(a.new_hours)} for a in impact.credit_reductions],
        "stale_entries_closed": impact.stale_closed,
        "arbzg_findings": impact.arbzg,
        "milog_warning": milog_warnings(user, impact),
        "affected_absences": len(impact.absences),
    }


def _hm(hours) -> str:
    """Stunden als „H:MM" (Betrag) — Minutenformat aus ``work_window_service``."""
    return work_window_service._hm(int(round(abs(Decimal(str(hours))) * 60)))


def _signed(hours) -> str:
    """Anzeige-Vorzeichen: echtes Minus U+2212 (Spec 11.4), sonst „+"."""
    return ("−" if Decimal(str(hours)) < 0 else "+") + _hm(hours)


def criteria_text(impact: ChangeImpact) -> str:
    """Spec 11.4: {Kriterien} — „3 Einträge verlieren angerechnete Zeit;
    Überstundenkonto −3:45 h; 1 Abwesenheits-Gutschrift sinkt" bzw. „Soll heute
    +1:00 h während eingestempelt"."""
    parts = []
    if SHORTENING_ENTRIES in impact.shortening_reasons:
        n = sum(1 for c in impact.reclamp.changed if c.new_net < c.old_net) + (1 if impact.open_entry_loses else 0)
        parts.append("1 Eintrag verliert angerechnete Zeit" if n == 1 else f"{n} Einträge verlieren angerechnete Zeit")
    if SHORTENING_SALDO in impact.shortening_reasons:
        if impact.saldo_delta < 0:
            parts.append(f"Überstundenkonto {_signed(impact.saldo_delta)} h")
        if impact.open_day_saldo_delta < 0:
            parts.append(f"Soll heute {_signed(-impact.open_day_saldo_delta)} h während eingestempelt")
        if impact.saldo_delta >= 0 and impact.open_day_saldo_delta >= 0:
            years = ", ".join(str(y) for y in impact.shortening_closed_years)
            parts.append(f"Überstundenkonto im abgeschlossenen Jahr {years} gesenkt")
    if SHORTENING_ABSENCE_CREDIT in impact.shortening_reasons:
        n = len(impact.credit_reductions)
        parts.append("1 Abwesenheits-Gutschrift sinkt" if n == 1 else f"{n} Abwesenheits-Gutschriften sinken")
    return "; ".join(parts)


def closed_year_detail(years: List[int]) -> str:
    """Spec 11.4 — genannt wird das GRÖSSTE Jahr (sonst scheiterte auch der Vorschlag)."""
    y = max(years)
    return (f"Rückwirkende Verkürzung in das abgeschlossene Jahr {y} ist gesperrt. "
            f"Bitte die Änderung frühestens ab 01.01.{y + 1} wirksam werden lassen.")


def protection_error(impact: ChangeImpact, reason, *, deleting: bool, reset_offered: bool) -> Optional[str]:
    """Spec 9.5/11.4 — ``None`` = speicherbar, sonst der 400-Text. Reihenfolge:
    abgeschlossenes Jahr (auch mit Grund gesperrt) → fehlender Grund/Haken →
    „Sonstiges" ohne zweiten Haken. ``reason`` trägt die vier
    ``RetroReasonFields`` (Anlege- bzw. DELETE-Body) oder ist ``None``."""
    if not impact.is_shortening:
        return None
    if impact.shortening_closed_years:
        return closed_year_detail(impact.shortening_closed_years)
    complete = bool(reason is not None and reason.retroactive_reason_type
                    and reason.retroactive_reason_text and reason.wage_risk_confirmed)
    if not complete:
        crit = criteria_text(impact)
        if deleting:
            head = f"Das Löschen verkürzt rückwirkend ({crit}): {_ASK}"
            if reset_offered and impact.earliest_lossless_date is not None:
                return (f"{head} – oder ab dem {impact.earliest_lossless_date:%d.%m.%Y} "
                        f"auf den vorherigen Stand zurücksetzen.")
        else:
            head = f"Rückwirkende Verkürzung ({crit}): {_ASK}"
            if impact.earliest_lossless_date is not None:
                return f"{head} – oder die Änderung ab dem {impact.earliest_lossless_date:%d.%m.%Y} wirksam werden lassen."
        if impact.earliest_lossless_note:
            return f"{head} – oder abbrechen: {impact.earliest_lossless_note}"
        return f"{head} – oder abbrechen."
    if reason.retroactive_reason_type == "sonstiges" and not reason.other_reason_risk_confirmed:
        return SONSTIGES_CONFIRM_DETAIL
    return None


def reset_body(predecessor, effective_from: date, change_id) -> dict:
    """P13/9.7 — fertiger Anlege-Body „ab ‹Datum› auf den vorherigen Stand
    zurücksetzen": der Vorgänger-Snapshot samt neuen Blöcken; ein Altfenster
    trägt der Server selbst nach (der Schreibweg nimmt keine Altfenster an),
    deshalb nur Modusfelder und — ohne Fenster — ``remove_legacy_window``."""
    body: dict = {"effective_from": effective_from.isoformat(), "reset_of_change_id": str(change_id)}
    parsed = (None if predecessor.blocks is None
              else work_blocks_service.ParsedWeek(predecessor.blocks, predecessor.block_pauses))
    if parsed is not None and not work_blocks_service.is_legacy_week(parsed):
        body["blocks"] = work_blocks_service.week_blocks_to_json(parsed.blocks, parsed.pauses)
        return body
    if predecessor.use_daily_schedule:
        body["use_daily_schedule"] = True
        for key, value in zip(work_blocks_service.HOURS_FIELDS, predecessor.day_hours):
            body[key] = None if value is None else float(value)
    else:
        body["use_daily_schedule"] = False
        body["weekly_hours"] = float(predecessor.weekly_hours)
    body["work_days_per_week"] = int(predecessor.work_days_per_week)
    if parsed is None:
        body["remove_legacy_window"] = True
    return body
