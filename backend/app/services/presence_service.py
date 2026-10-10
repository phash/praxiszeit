"""Spec 2026-10-08, 8.3 / 8.4 (P14, P22): weiche ArbZG-Warnungen auf der
TATSÄCHLICHEN Anwesenheit laut Stempel — und der Hinweis auf den
Pausen-Doppelabzug (``BREAK_IN_GAP``).

Die harten Prüfungen (§3 10 h, §4) rechnen weiter auf der ANGERECHNETEN Zeit
(E43). Eine Lücke zwischen Arbeitsblöcken oder eine Neukappung darf einen
echten Verstoß aber nicht verschwinden lassen (Rechtsbewertung Pflicht 4):
diese Warnungen sehen die Rohstempel. Sie blockieren nie.

Anwesenheit eines Eintrags = ``work_window_service.presence_minutes`` —
Rohstempel abzüglich erfasster Pause, bei ``auto_closed`` bis zum wirksamen
Ende (P18), offene Einträge zählen nicht. Lücken werden NICHT abgezogen.

Ohne Kappung ist Anwesenheit = angerechnete Zeit; dann greift bereits die
harte Prüfung, und hier kommt nichts dazu.
"""
from datetime import date, timedelta
from typing import NamedTuple, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import TimeEntry
from app.services import work_window_service
# EINE Quelle für „H:MM" und Minuten-seit-Mitternacht (PR1-Schnittstelle).
from app.services.work_window_service import _hm, _min

PRESENCE_DAILY_CODE = "PRESENCE_DAILY_HOURS"
PRESENCE_BREAK_CODE = "PRESENCE_BREAK"
PRESENCE_WEEKLY_CODE = "PRESENCE_WEEKLY_HOURS"
BREAK_IN_GAP_CODE = "BREAK_IN_GAP"

DAILY_LIMIT_MINUTES = 10 * 60
WEEKLY_LIMIT_MINUTES = 48 * 60
# §4 Satz 1 ArbZG: > 9 h → 45 Min, > 6 h → 30 Min (von oben nach unten).
_BREAK_RULES = ((9 * 60, 45), (6 * 60, 30))


class DayPresence(NamedTuple):
    presence_minutes: int        # Σ presence_minutes der geschlossenen Einträge
    credited_minutes: int        # Σ net_hours (angerechnet), je Eintrag in Minuten
    recorded_break_minutes: int  # erfasste Pausen ≥ 15 + Abstände zwischen Einträgen ≥ 15
    has_gap: bool                # mindestens ein Eintrag mit uncredited_minutes > 0


def credited_minutes(entries: Sequence) -> int:
    """Σ angerechnete Zeit (``net_hours``) der geschlossenen Einträge in Minuten —
    JE EINTRAG auf Minuten gerundet, dann summiert (wie ``credit_summary_text``).
    ``net_hours`` trägt nur 2 Nachkommastellen (±0,2 Min je Eintrag); erst summiert
    und dann umgerechnet wich das Ergebnis ab etwa drei Einträgen um eine Minute
    von ``_net_minutes`` ab, dessen Summe die harten Prüfungen bilden — die
    Bedingungen „harte §3-Prüfung / ``WEEKLY_HOURS_WARNING`` kam nicht" (P14/P22)
    kippten an der Grenze in beide Richtungen (Doppelmeldung ohne Kappung bzw. ein
    echter Verstoß verschwand aus den Warnungen). Die harten Prüfungen summieren
    ebenfalls ganze Minuten (``_calculate_daily/weekly_net_hours``), daher gilt
    ``≤ 600``/``≤ 2880`` hier genau dann, wenn dort ``> 10.0``/``> 48.0`` nicht
    anschlug."""
    return sum(int(round(float(e.net_hours or 0) * 60)) for e in entries if e.end_time is not None)


def closed_entries(db: Session, user, start: date, end: date) -> list:
    """Geschlossene Einträge der Person im Zeitraum (F-026: Mandantenfilter)."""
    return (
        db.query(TimeEntry)
        .filter(
            TimeEntry.user_id == user.id,
            TimeEntry.tenant_id == user.tenant_id,
            TimeEntry.date >= start,
            TimeEntry.date <= end,
            TimeEntry.end_time.isnot(None),
        )
        .all()
    )


def _presence_span(entry) -> tuple:
    start = entry.raw_start_time or entry.start_time
    if getattr(entry, "auto_closed", False):
        end = entry.end_time            # P18: 23:59 ist kein Stempel
    else:
        end = entry.raw_end_time or entry.end_time
    return _min(start), _min(end)


def day_presence(entries: Sequence) -> DayPresence:
    """Anwesenheit des Tages über die GESCHLOSSENEN Einträge. Abstände zwischen
    Einträgen über die Vereinigung der Anwesenheits-Intervalle (eine
    Überlappung ergibt keinen erfundenen Abstand)."""
    closed = [e for e in entries if e.end_time is not None]
    gaps, reach = 0, None
    for start, end in sorted(_presence_span(e) for e in closed):
        if reach is not None and start - reach >= 15:
            gaps += start - reach
        reach = end if reach is None else max(reach, end)
    declared = sum(int(e.break_minutes or 0) for e in closed if int(e.break_minutes or 0) >= 15)
    return DayPresence(
        presence_minutes=sum(work_window_service.presence_minutes(e) for e in closed),
        credited_minutes=credited_minutes(closed),
        recorded_break_minutes=declared + gaps,
        has_gap=any(int(getattr(e, "uncredited_minutes", 0) or 0) > 0 for e in closed),
    )


def _required_break(presence: int) -> int:
    for limit, need in _BREAK_RULES:
        if presence > limit:
            return need
    return 0


def daily_presence_warnings(day: DayPresence, *, break_check_passed: bool) -> list:
    """``PRESENCE_DAILY_HOURS`` nur, wenn die harte §3-Prüfung auf angerechneter
    Zeit nicht gegriffen hat (angerechnet ≤ 10 h). ``PRESENCE_BREAK`` nur, wenn
    die §4-Prüfung auf angerechneter Zeit BESTANDEN hat — weder 400 noch
    Ausnahme (``BREAK_WAIVER``/202); seit #499 gibt es kein ``BREAK_WARNING``
    mehr, deshalb entscheidet der Aufrufer am Ergebnis von
    ``validate_daily_break`` (P14). Keine Bedingung „nur dank Lückensegmenten"."""
    out = []
    if day.presence_minutes > DAILY_LIMIT_MINUTES and day.credited_minutes <= DAILY_LIMIT_MINUTES:
        out.append(
            f"{PRESENCE_DAILY_CODE}: §3 ArbZG: Laut Stempel {_hm(day.presence_minutes)} h anwesend "
            f"(abzüglich erfasster Pausen) – mehr als 10 Stunden. Angerechnet werden "
            f"{_hm(day.credited_minutes)} h; die Höchstgrenze gilt für die tatsächliche Arbeitszeit."
        )
    need = _required_break(day.presence_minutes)
    if break_check_passed and need and day.recorded_break_minutes < need:
        if day.has_gap:
            text = (
                f"§4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – "
                f"eine Ruhepause ist nicht erfasst ({_hm(day.presence_minutes)} h Anwesenheit). "
                f"Die Lücke gilt nur dann als Pause, wenn sie tatsächlich frei war."
            )
        else:
            text = (
                f"§4 ArbZG: Laut Stempel {_hm(day.presence_minutes)} h anwesend ohne ausreichende "
                f"erfasste Ruhepause; angerechnet werden nur {_hm(day.credited_minutes)} h. "
                f"Die Pausenpflicht gilt für die tatsächliche Arbeitszeit."
            )
        out.append(f"{PRESENCE_BREAK_CODE}: {text}")
    return out


def weekly_presence_warning(entries: Sequence) -> Optional[str]:
    """P22: Anwesenheit der Kalenderwoche (Mo–So) > 48 h, solange die
    angerechnete Zeit ≤ 48 h ist (sonst kam ``WEEKLY_HOURS_WARNING`` schon)."""
    closed = [e for e in entries if e.end_time is not None]
    presence = sum(work_window_service.presence_minutes(e) for e in closed)
    credited = credited_minutes(closed)
    if presence > WEEKLY_LIMIT_MINUTES and credited <= WEEKLY_LIMIT_MINUTES:
        return (
            f"{PRESENCE_WEEKLY_CODE}: §3 ArbZG: Laut Stempel {_hm(presence)} h in dieser Woche "
            f"anwesend (abzüglich erfasster Pausen) – mehr als 48 Stunden. Angerechnet werden "
            f"{_hm(credited)} h; die Grenze gilt für die tatsächliche Arbeitszeit."
        )
    return None


def break_in_gap_warning(entry) -> Optional[str]:
    """Spec 8.4 (E45): Pause > 0 UND nicht angerechnete Lücke am selben Eintrag —
    der Doppelabzug wird sichtbar statt still."""
    brk = int(entry.break_minutes or 0)
    gap = int(getattr(entry, "uncredited_minutes", 0) or 0)
    if brk > 0 and gap > 0:
        return (
            f"{BREAK_IN_GAP_CODE}: Pause in der Lücke wird zusätzlich abgezogen: {brk} Min Pause "
            f"und {_hm(gap)} h nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der "
            f"Lücke, bitte die Pause auf 0 setzen."
        )
    return None


def presence_hints(entry, day_entries: Sequence, week_entries: Sequence, *,
                   break_check_passed: bool) -> list:
    """Die weichen Warnungen aus 8.3/8.4 über bereits gesammelte Einträge —
    Reihenfolge ``BREAK_IN_GAP``, Tag, Woche. EINE Quelle für die Schreibpfade
    (``presence_warnings``, Einträge aus der DB) und die XLS-Vorschau (Bestand
    plus Zeilen der Datei, ohne die von einer Zeile überschriebenen Einträge).
    Prüft §18 NICHT — das tut der Aufrufer."""
    out = []
    if entry is not None:
        gap = break_in_gap_warning(entry)
        if gap:
            out.append(gap)
    out.extend(daily_presence_warnings(
        day_presence(day_entries), break_check_passed=break_check_passed,
    ))
    weekly = weekly_presence_warning(week_entries)
    if weekly:
        out.append(weekly)
    return out


def plain_text(warning: str) -> str:
    """Spec 8.3: die XLS-Vorschau zeigt die Warnung als Klartext ohne Code."""
    return warning.split(": ", 1)[1]


def presence_warnings(db: Session, user, d: date, *, break_check_passed: bool, entry=None) -> list:
    """Alle weichen Warnungen aus 8.3/8.4 für den Tag ``d`` — NACH dem Schreiben
    aufrufen (die DB enthält den Eintrag). ``entry`` = der eben geschriebene
    Eintrag (für ``BREAK_IN_GAP``). §18 (``exempt_from_arbzg``) → keine."""
    if user is None or getattr(user, "exempt_from_arbzg", False):
        return []
    monday = d - timedelta(days=d.weekday())
    return presence_hints(
        entry,
        closed_entries(db, user, d, d),
        closed_entries(db, user, monday, monday + timedelta(days=6)),
        break_check_passed=break_check_passed,
    )
