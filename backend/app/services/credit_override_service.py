"""Spec 2026-10-08, 13.3 / P3 / P4 / P21: „Anerkennen" — die gesamte
gestempelte Zeit eines Eintrags wird angerechnet, dauerhaft.

EINE Quelle für beide Wege: die Admin-Aktion (``POST /admin/time-entries/{id}/
credit-override``) und die Genehmigung eines Antrags „Anrechnung beantragen"
bzw. „genehmigen und anerkennen" (``admin_change_requests``). Die Sperren
(Anker VOR Zeile, P5) nimmt der Aufrufer. Kein Pfad setzt das Flag zurück (P3),
eine Rücknahme gibt es nicht (P11).
"""
from datetime import time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import TimeEntry, TimeEntryAuditLog
from app.services import presence_service, work_window_service

CREDIT_OVERRIDE_SOURCE = "credit_override"  # 15 Zeichen < varchar(40)
OPEN_ENTRY_DETAIL = "Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden."
AUTO_CLOSED_DETAIL = (
    "Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen."
)
_BY_ADMIN = "von der Verwaltung anerkannt"
_ON_REQUEST = "auf Antrag der beschäftigten Person von der Verwaltung anerkannt"


def start_taken_detail(t: time) -> str:
    return f"Ein anderer Eintrag an diesem Tag beginnt bereits um {t.strftime('%H:%M')}."


def lacks_actual_end(entry: TimeEntry, proposed_end: Optional[time]) -> bool:
    """P18/P21: Bringt ein Antrag zu einem automatisch geschlossenen Eintrag
    KEIN tatsächliches Ende mit? Das gespeicherte (gekappte) Ende, das Rohende
    und das synthetische 23:59 zählen nicht: die Genehmigung machte über
    ``unclamp_input`` daraus wieder 23:59 (Review Focus 3), und Anerkennen
    rechnete bis dorthin an — bis zu 16 h, das Schlupfloch, das E36/E42
    schließen. EINE Regel für „Anrechnung beantragen" (MA-Antrag) und
    „genehmigen und anerkennen" (Genehmigung, Precondition)."""
    return bool(entry.auto_closed) and proposed_end in (
        entry.end_time, entry.raw_end_time, work_window_service.AUTO_CLOSE_RAW_END,
    )


def load_entry_locked(db: Session, tenant_id, entry_id) -> Optional[TimeEntry]:
    """Den Eintrag mit Zeilensperre laden — NACH der Ankersperre (P5)."""
    return (
        db.query(TimeEntry)
        .filter(TimeEntry.id == entry_id, TimeEntry.tenant_id == tenant_id)  # F-026
        .with_for_update()
        .first()
    )


def apply_credit_override(
    db: Session, entry: TimeEntry, *, changed_by_id, on_request: bool, change_request_id=None,
) -> bool:
    """Spec 13.3 Schritte 2–5. ``False`` = war schon anerkannt (idempotent,
    kein Protokoll). Wirft 400 (offen, ``auto_closed``) bzw. 409 (Kollision)."""
    if entry.end_time is None:
        raise HTTPException(status_code=400, detail=OPEN_ENTRY_DETAIL)
    if entry.auto_closed:
        # P18: das Rohende 23:59 ist kein Stempel — anerkannt würden sonst bis
        # zu 16 h (das Schlupfloch, das E36/E42 schließen).
        raise HTTPException(status_code=400, detail=AUTO_CLOSED_DETAIL)
    if entry.credit_override:
        return False

    new_start = entry.raw_start_time or entry.start_time
    new_end = entry.raw_end_time or entry.end_time
    if new_start != entry.start_time:
        # UNIQUE (tenant, user, date, start_time): sauberes 409 statt
        # IntegrityError → 500 auf PostgreSQL.
        clash = db.query(TimeEntry.id).filter(
            TimeEntry.user_id == entry.user_id,
            TimeEntry.tenant_id == entry.tenant_id,  # F-026
            TimeEntry.date == entry.date,
            TimeEntry.start_time == new_start,
            TimeEntry.id != entry.id,
        ).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail=start_taken_detail(new_start))

    old_start, old_end = entry.start_time, entry.end_time
    old_note = work_window_service.credit_summary_text(entry)
    entry.start_time, entry.end_time = new_start, new_end
    entry.raw_start_time = None
    entry.raw_end_time = None
    entry.uncredited_minutes = 0
    entry.credit_override = True
    # clamp_grace_minutes bleibt (13.3 Schritt 4) — ohne Wirkung, solange das Flag gilt.
    suffix = _ON_REQUEST if on_request else _BY_ADMIN
    # Über die Objektschicht: der before_insert-Hook setzt row_hash (#121).
    db.add(TimeEntryAuditLog(
        time_entry_id=entry.id,
        user_id=entry.user_id,
        changed_by=changed_by_id,
        action="update",
        source=CREDIT_OVERRIDE_SOURCE,
        change_request_id=change_request_id,
        tenant_id=entry.tenant_id,
        old_date=entry.date,
        old_start_time=old_start,
        old_end_time=old_end,
        old_break_minutes=entry.break_minutes,
        old_note=old_note,
        new_date=entry.date,
        new_start_time=new_start,
        new_end_time=new_end,
        new_break_minutes=entry.break_minutes,
        new_note=f"{work_window_service.credit_summary_text(entry)} — {suffix}",
    ))
    db.flush()
    return True


def override_warnings(db: Session, user, entry: TimeEntry, *, include_weekly: bool = True) -> list:
    """Spec 13.3 Schritt 6 / P4: nach dem Anerkennen nur WEICHE Warnungen —
    §3 (Tag), §4, 48 h und die Anwesenheits-Warnungen. Nach dem Commit
    aufrufen. ``include_weekly=False`` für die CR-Genehmigung, deren
    Nachprüfung die 48-h-Warnung schon selbst ausgibt.

    §4 kommt hier als ``BREAK_WARNING`` — seit #499 ist §4 an allen
    Schreibwegen sonst eine Sperre bzw. eine dokumentierte Ausnahme
    (``BREAK_WAIVER``); Anerkennen ändert aber nur die Anrechnung, nicht den
    Nachweis, und darf geleistete Arbeit nicht verstecken (P4)."""
    # Lokal: die Grenzwerte leben im Router-Modul; ein Modulimport hier zöge
    # den Router beim Laden des Dienstes mit.
    from app.routers.time_entries import (
        MAX_DAILY_HOURS_HARD, MAX_DAILY_HOURS_WARN, MAX_WEEKLY_HOURS_WARN,
    )
    from app.services.break_validation_service import validate_daily_break

    if user is None or getattr(user, "exempt_from_arbzg", False):
        return []
    out = []
    # Ganze Minuten je Eintrag wie die harten Prüfungen (presence_service.credited_minutes).
    day_hours = presence_service.credited_minutes(
        presence_service.closed_entries(db, user, entry.date, entry.date)) / 60
    if day_hours > MAX_DAILY_HOURS_HARD:
        out.append(
            f"DAILY_HOURS_HARD: Tagesarbeitszeit beträgt {day_hours:.1f}h und überschreitet "
            f"die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG)."
        )
    elif day_hours > MAX_DAILY_HOURS_WARN:
        out.append("DAILY_HOURS_WARNING")
    # Nach dem Anerkennen gibt es keine Lücke mehr (uncredited 0, keine Kappung).
    break_error = validate_daily_break(
        db, user, entry.date, entry.start_time, entry.end_time, entry.break_minutes,
        uncredited_segments=[], tenant_id=entry.tenant_id, exclude_entry_id=entry.id,
    )
    if break_error:
        out.append(f"BREAK_WARNING: {break_error}")
    if include_weekly:
        monday = entry.date - timedelta(days=entry.date.weekday())
        week_hours = presence_service.credited_minutes(presence_service.closed_entries(
            db, user, monday, monday + timedelta(days=6))) / 60
        if week_hours > MAX_WEEKLY_HOURS_WARN:
            out.append("WEEKLY_HOURS_WARNING")
    out.extend(presence_service.presence_warnings(
        db, user, entry.date, break_check_passed=break_error is None, entry=entry,
    ))
    return out
