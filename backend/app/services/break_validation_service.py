"""§4 ArbZG — Pausenprüfung über den Tag (Spec 2026-10-08, Abschnitt 8.2).

Basis ist die ANGERECHNETE Zeit: nicht angerechnete Lückenminuten sind keine
Arbeitszeit (Abzug von der Bruttozeit); ein Lückensegment ≥ 15 Min zählt als
Pausenabschnitt (geplante Ruhepause, E43). ``daily_break_figures`` ist die eine
Rechenregel — ``xls_import_service._check_arbzg`` nutzt sie mit.
"""
from datetime import date, time
from typing import NamedTuple, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import TimeEntry
from app.services import settings_service


# #499: Mandanten-Schalter für die Ausnahme „Pflicht-Pause war nicht möglich"
# (#144). Default AN = bisheriges Verhalten. AUS → keine Ausnahme mehr, an
# keinem Schreibpfad: der §4-Verstoß bleibt eine harte Sperre.
BREAK_EXCEPTION_ALLOWED = "break_exception_allowed"

BREAK_EXCEPTION_DISABLED_HINT = (
    "Die Ausnahme „Pflicht-Pause war nicht möglich“ ist in dieser Praxis "
    "abgeschaltet – bitte die Pause erfassen."
)


def is_break_exception_allowed(db: Session, tenant_id) -> bool:
    """#499: darf ein §4-Verstoß per dokumentierter Begründung erfasst werden?"""
    return settings_service.get_bool_setting(
        db, BREAK_EXCEPTION_ALLOWED, tenant_id=tenant_id, default=True,
    )


def break_waiver_rejection(
    db: Session, tenant_id, break_error: str, waiver_reason: Optional[str],
) -> Optional[str]:
    """#499: entscheidet einheitlich für ALLE Schreibpfade, ob ein §4-Verstoß
    (``break_error``) per Ausnahme durchgelassen wird.

    Liefert ``None``, wenn die Ausnahme greift (Begründung vorhanden UND der
    Mandant erlaubt Ausnahmen) — sonst den Text für die 400-Antwort. Ist die
    Ausnahme abgeschaltet, nennt der Text das ausdrücklich, damit die
    Oberfläche nicht erneut nach einer Begründung fragt.
    """
    if not is_break_exception_allowed(db, tenant_id):
        return f"{break_error} {BREAK_EXCEPTION_DISABLED_HINT}"
    if not (waiver_reason or "").strip():
        return break_error
    return None


def _time_to_minutes(t: time) -> int:
    """Convert a time object to total minutes since midnight."""
    return t.hour * 60 + t.minute


class BreakBlock(NamedTuple):
    start: int             # wirksamer Beginn, Minuten seit Mitternacht
    end: int               # wirksames Ende
    break_minutes: int     # erfasste Pause
    deduct_minutes: int    # nicht angerechnete Minuten (Abzug von der Bruttozeit)
    pause_segments: tuple  # Lückensegmente ≥ 15 Min, die als Pausenabschnitt zählen


def break_block_for_new(start_time: time, end_time: time, break_minutes: int,
                        uncredited_segments: Sequence[int]) -> BreakBlock:
    """Neuer bzw. geänderter Eintrag: die Segmente kommen vom Aufrufer
    (``work_window_service.gap_segments`` aus denselben Eingaben wie ``clamp``)."""
    segs = [int(s) for s in uncredited_segments]
    return BreakBlock(
        _time_to_minutes(start_time), _time_to_minutes(end_time), int(break_minutes or 0),
        sum(segs), tuple(s for s in segs if s >= 15),
    )


def break_block_for_entry(db: Session, user, entry, *, wh_changes=None,
                          soll_free_dates=None) -> BreakBlock:
    """Bestehender Eintrag: Segmente aus seinen GESPEICHERTEN wirksamen Zeiten,
    den Blöcken des Datums und SEINEM Puffer (E80). Weicht Σ Segmente vom
    gespeicherten ``uncredited_minutes`` ab (Bestand ohne gespeicherten Puffer
    nach einer Puffer-Änderung), zählt der gespeicherte Wert als Abzug und NICHT
    als Pausenabschnitt (strenge Richtung, 8.2). Anerkannte Einträge
    (``credit_override``) haben keine Segmente."""
    start, end = _time_to_minutes(entry.start_time), _time_to_minutes(entry.end_time)
    brk = int(entry.break_minutes or 0)
    stored = int(entry.uncredited_minutes or 0)
    # Ohne gespeicherte Lückenminuten gibt es nichts als Pause zu werten: Σ
    # Segmente ist dann entweder 0 (keine Segmente) oder weicht ab (strenge
    # Richtung, ebenfalls keine Segmente). Spart für jeden Bestandseintrag (Altfenster
    # = Einzelblock, ``uncredited`` 0) die Abfrage von Snapshot und Feiertagen.
    if stored == 0 or entry.credit_override:
        return BreakBlock(start, end, brk, stored, ())

    from app.services import work_window_service

    segs = work_window_service.gap_segments(
        db, user, entry.date, entry.start_time, entry.end_time,
        work_window_service.grace_for_entry(db, entry), credit_override=False,
        wh_changes=wh_changes, soll_free_dates=soll_free_dates,
    )
    if sum(segs) != stored:
        return BreakBlock(start, end, brk, stored, ())
    return BreakBlock(start, end, brk, stored, tuple(s for s in segs if s >= 15))


def daily_break_figures(blocks: Sequence[BreakBlock]) -> tuple:
    """(Netto-Arbeitsminuten, wirksame Pause) über alle Blöcke des Tages.

    Netto = Σ (Ende − Beginn − Abzug) − erfasste Pausen ≥ 15 (§4 Satz 2).
    Wirksame Pause = erfasste Pausen ≥ 15 + Abstände zwischen Einträgen ≥ 15 +
    Lückensegmente ≥ 15.

    A-M2: die 15-Minuten-Regel gilt für die erfasste Pause JEDES Eintrags des
    Tages, nicht nur des neuen — eine 10-Minuten-Pause zählt nie als Abschnitt,
    gleich aus welchem Eintrag sie stammt."""
    ordered = sorted(blocks, key=lambda b: b.start)
    gross = sum(b.end - b.start - b.deduct_minutes for b in ordered)
    declared = sum(b.break_minutes for b in ordered if b.break_minutes >= 15)
    gaps = 0
    for prev, cur in zip(ordered, ordered[1:]):
        gap = cur.start - prev.end
        if gap >= 15:
            gaps += gap
    segments = sum(sum(b.pause_segments) for b in ordered)
    return gross - declared, declared + gaps + segments


def validate_daily_break(
    db: Session,
    user,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    *,
    uncredited_segments: Sequence[int],
    tenant_id,
    exclude_entry_id=None,
) -> Optional[str]:
    """§4 ArbZG: > 6 h → 30 Min, > 9 h → 45 Min, Abschnitte ≥ 15 Min.

    Maßstab ist der ganze TAG (#499): alle geschlossenen Einträge des Tages
    plus der neue/geänderte. Eine Lücke unter 15 Minuten zwischen zwei
    Einträgen ist keine Pause — aneinandergereihte Einträge zählen wie ein
    durchgehender Block.

    ``uncredited_segments`` = ``work_window_service.gap_segments`` des neuen
    bzw. geänderten Eintrags (Pflicht, Spec 8.2). ``tenant_id`` Pflicht (7.3).
    Returns an error message string if invalid, None if valid."""
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == tenant_id,  # F-026 (Spec 7.3)
        TimeEntry.date == entry_date,
    )
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    blocks = [
        break_block_for_entry(db, user, e)
        for e in query.order_by(TimeEntry.start_time).all()
        if e.end_time is not None
    ]
    blocks.append(break_block_for_new(start_time, end_time, break_minutes, uncredited_segments))

    net_work_minutes, total_effective_break = daily_break_figures(blocks)

    if net_work_minutes > 540 and total_effective_break < 45:
        return (
            f"Bei mehr als 9 Stunden Arbeitszeit ist eine Pause von mindestens 45 Minuten erforderlich (ArbZG §4). "
            f"Aktuelle Netto-Arbeitszeit: {net_work_minutes // 60}h {net_work_minutes % 60}min, "
            f"Gesamtpause: {total_effective_break} Minuten."
        )
    if net_work_minutes > 360 and total_effective_break < 30:
        return (
            f"Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4). "
            f"Aktuelle Netto-Arbeitszeit: {net_work_minutes // 60}h {net_work_minutes % 60}min, "
            f"Gesamtpause: {total_effective_break} Minuten."
        )
    # §4 Satz 2: Pausenabschnitte müssen mindestens 15 Minuten betragen
    if break_minutes is not None and 0 < break_minutes < 15:
        return (
            f"Pausenabschnitte müssen mindestens 15 Minuten betragen (§4 Satz 2 ArbZG). "
            f"Eingegebene Pause: {break_minutes} Minuten."
        )
    return None
