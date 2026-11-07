"""Plausibilitätsprüfungen für Zeiteinträge an allen Schreibpfaden (Audit
2026-11-07, #538/#540).

Überschneidungen (A1-02): Zeiteinträge EINER Person am selben Tag dürfen sich
nicht überschneiden — sonst zählt dieselbe Zeit doppelt ins Ist, in §3/§4 und in
die §16-Exporte. Verglichen wird die tatsächliche ANWESENHEIT laut Stempel
(Rohstempel, beim automatisch geschlossenen Eintrag das wirksame Ende —
``work_window_service.presence_end``), nicht die gekappte Zeit: zwei
Stempelzeiten, die sich überschneiden, waren auch dann gleichzeitig, wenn die
Kappung eine davon auf 0 h zusammenzieht. Ein laufender Eintrag reicht von
seinem Beginn bis „jetzt" (heute) bzw. bis zum Tagesende (früherer Tag, noch
nicht automatisch geschlossen). Aneinanderstoßende Einträge (Ende = nächster
Beginn) sind erlaubt. Bestandsdaten bleiben unangetastet: Bearbeitungen prüfen
nur, wenn sich die Anwesenheit des Eintrags ändert.

Frontend-Zwilling: ``frontend/src/utils/entryOverlap.ts`` (gleiche Fälle in
``tests/test_entry_overlap.py`` und ``entryOverlap.test.ts``, gleicher
Hinweistext).
"""
from datetime import date, datetime, time
from typing import Iterable, NamedTuple, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import TimeEntry

DAY_END_MINUTES = 24 * 60

# HTTP-Status der Sperre (Produktentscheidung #538: „sperren mit Hinweis").
OVERLAP_STATUS = 409


class Interval(NamedTuple):
    """Anwesenheit eines Eintrags in Minuten seit Mitternacht, [start, end)."""
    start: int
    end: int
    running: bool = False


def _m(t: time) -> int:
    return t.hour * 60 + t.minute


def _hhmm(minutes: int) -> str:
    if minutes >= DAY_END_MINUTES:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def presence_bounds(start: time, raw_start: Optional[time], end: Optional[time],
                    raw_end: Optional[time], *, auto_closed: bool = False):
    """(Beginn, Ende) der Anwesenheit aus den Werten, die gespeichert werden
    bzw. sind — dieselbe Regel wie ``work_window_service.presence_end`` und
    ``presence_minutes``. ``None`` als Ende = laufender Eintrag."""
    s = raw_start or start
    if end is None:
        return s, None
    e = end if auto_closed else (raw_end or end)
    return s, e


def interval(start: time, end: Optional[time], *, on: date, today: date,
             now: time) -> Interval:
    """Anwesenheitsintervall. Offenes Ende: heute bis ``now`` (mindestens eine
    Minute — ein eben begonnener Eintrag belegt seine Startminute), an einem
    früheren Tag bis Tagesende."""
    s = _m(start)
    if end is None:
        e = max(_m(now), s + 1) if on == today else DAY_END_MINUTES
        return Interval(s, max(e, s + 1), True)
    return Interval(s, _m(end), False)


def entry_interval(entry, *, today: date, now: time) -> Interval:
    s, e = presence_bounds(entry.start_time, entry.raw_start_time, entry.end_time,
                           entry.raw_end_time, auto_closed=bool(getattr(entry, "auto_closed", False)))
    return interval(s, e, on=entry.date, today=today, now=now)


def overlaps(a: Interval, b: Interval) -> bool:
    """Echte Überschneidung; Ende = Beginn des anderen zählt nicht. Ein
    Eintrag ohne Dauer (Beginn = Ende) belegt seine Minute."""
    a_end = a.end if a.end > a.start else a.start + 1
    b_end = b.end if b.end > b.start else b.start + 1
    return a.start < b_end and b.start < a_end


def overlap_detail(other: Interval, day: date) -> str:
    """Hinweistext der Sperre — wortgleich zum Frontend (``overlapMessage``)."""
    if other.running:
        what = f"dem laufenden Eintrag ab {_hhmm(other.start)}"
    else:
        what = f"dem Eintrag {_hhmm(other.start)}–{_hhmm(other.end)}"
    return (
        f"Überschneidung mit {what} am {day.strftime('%d.%m.%Y')}: Zeiteinträge "
        f"einer Person dürfen sich nicht überschneiden. Bitte die Zeiten anpassen "
        f"oder den vorhandenen Eintrag bearbeiten."
    )


def find_overlap(db: Session, *, tenant_id, user_id, day: date, candidate: Interval,
                 today: date, now: time, exclude_ids: Iterable = ()) -> Optional[Interval]:
    """Erstes Bestandsintervall des Tages, das ``candidate`` überschneidet
    (F-026: Mandantenfilter zusätzlich zu RLS)."""
    exclude = {e for e in exclude_ids if e is not None}
    q = db.query(TimeEntry).filter(
        TimeEntry.tenant_id == tenant_id,
        TimeEntry.user_id == user_id,
        TimeEntry.date == day,
    )
    for e in q.order_by(TimeEntry.start_time).all():
        if e.id in exclude:
            continue
        other = entry_interval(e, today=today, now=now)
        if overlaps(candidate, other):
            return other
    return None


def assert_no_overlap(db: Session, *, tenant_id, user_id, day: date, candidate: Interval,
                      today: date, now: time, exclude_ids: Iterable = ()) -> None:
    """409 mit Hinweis auf den kollidierenden Eintrag."""
    other = find_overlap(db, tenant_id=tenant_id, user_id=user_id, day=day,
                         candidate=candidate, today=today, now=now, exclude_ids=exclude_ids)
    if other is not None:
        raise HTTPException(status_code=OVERLAP_STATUS, detail=overlap_detail(other, day))


def assert_entry_no_overlap(db: Session, entry, *, today: date, now: time,
                            before: Optional[tuple] = None) -> None:
    """Prüft einen (geänderten) Eintrag im Speicher gegen die übrigen Einträge
    seines Tages. ``before`` = (Datum, Intervall) vor der Änderung: unverändert
    → keine Prüfung (Bestand bleibt bearbeitbar, z. B. Notiz an einer alten
    Überschneidung)."""
    cand = entry_interval(entry, today=today, now=now)
    if before is not None:
        b_day, b_int = before
        if b_day == entry.date and (b_int.start, b_int.end, b_int.running) == (
                cand.start, cand.end, cand.running):
            return
        # Laufender Eintrag: „bis jetzt" wandert mit — nur Beginn/Datum zählen.
        if b_day == entry.date and b_int.running and cand.running and b_int.start == cand.start:
            return
    assert_no_overlap(db, tenant_id=entry.tenant_id, user_id=entry.user_id, day=entry.date,
                      candidate=cand, today=today, now=now, exclude_ids=(entry.id,))


def snapshot(entry, *, today: date, now: time) -> tuple:
    """(Datum, Intervall) für ``assert_entry_no_overlap(before=...)``."""
    return entry.date, entry_interval(entry, today=today, now=now)


# ── A1-09: Plausibilität der eingegebenen Zeiten ──────────────────────────────

FUTURE_END_DETAIL = (
    "Das Ende liegt in der Zukunft. Bitte nur bereits geleistete Arbeitszeit "
    "eintragen – das Ende kann nach Arbeitsende nachgetragen werden."
)


def future_end_error(day: date, end: Optional[time], *, today: date, now: datetime) -> Optional[str]:
    """Ein Ende für HEUTE nach der aktuellen Uhrzeit ist erfundene Zeit (§16)."""
    if end is None or day != today:
        return None
    if _m(end) > _m(now.time()):
        return FUTURE_END_DETAIL
    return None


def break_span_error(start: Optional[time], end: Optional[time], break_minutes) -> Optional[str]:
    """Eine Pause, die so lang ist wie der Eintrag oder länger, ist keine
    Pause (und drückt §3-Netto auf 0)."""
    if start is None or end is None or not break_minutes:
        return None
    span = _m(end) - _m(start)
    if span > 0 and int(break_minutes) >= span:
        return (
            f"Die Pause ({int(break_minutes)} Min.) ist so lang wie der Eintrag oder "
            f"länger ({span} Min.). Bitte die tatsächliche Pause eintragen."
        )
    return None
