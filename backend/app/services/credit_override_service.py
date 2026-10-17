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

from app.models import TimeEntry, TimeEntryAuditLog, User
from app.services import (
    absence_retarget_audit, calculation_service, presence_service, work_window_service,
)

CREDIT_OVERRIDE_SOURCE = "credit_override"  # 15 Zeichen < varchar(40)
OPEN_ENTRY_DETAIL = "Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden."
AUTO_CLOSED_DETAIL = (
    "Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen."
)
_BY_ADMIN = "von der Verwaltung anerkannt"
_ON_REQUEST = "auf Antrag der beschäftigten Person von der Verwaltung anerkannt"
# Gesamtreview 1.20 (Fund 1): Auslöser der Einzelzeile, wenn das Anerkennen die
# Gutschrift einer Abwesenheit am selben Tag neu klemmt (F1, Misch-Tag).
MIXED_DAY_TRIGGER = "an die anerkannte Arbeitszeit des Tages angeglichen"


def start_taken_detail(t: time) -> str:
    return f"Ein anderer Eintrag an diesem Tag beginnt bereits um {t.strftime('%H:%M')}."


def lacks_actual_end(entry: TimeEntry, proposed_end: Optional[time]) -> bool:
    """P18/P21: Bringt ein Antrag zu einem automatisch geschlossenen Eintrag
    KEIN tatsächliches Ende mit? Das gespeicherte (gekappte) Ende zählt nicht:
    die Genehmigung machte über ``unclamp_input`` daraus wieder 23:59 (Review
    Focus 3), und Anerkennen rechnete bis dorthin an — bis zu 16 h, das
    Schlupfloch, das E36/E42 schließen. Ein Antrag ohne Ende bringt ebenfalls
    keins mit. EINE Regel für „Anrechnung beantragen" (MA-Antrag) und
    „genehmigen und anerkennen" (Genehmigung, Precondition) — und dieselbe wie
    ``work_window_service.end_is_correction``, nach der die Genehmigung das
    Kennzeichen aufhebt (sonst lehnte ``apply_credit_override`` erst nach der
    Statusänderung ab).

    **Entschieden 2026-10-11 (Produktinhaber, P18):** ein eingetragenes 23:59
    ist ein tatsächliches Ende (bis dahin zählten Rohende und 23:59 hier nicht)
    — die Formulare schicken das wirksame Ende, ein 23:59 kommt nur aus echter
    Eingabe. Kappt der Auto-Close das 23:59 nicht (Tag ohne Blöcke,
    ``track_hours=False`` auch mit Blöcken, halboffenes Altfenster, Hülle bis
    23:59), ist das wirksame Ende selbst 23:59: dort bleibt ein 23:59 vom Echo
    nicht zu unterscheiden und zählt nicht (Grenzfall von ``end_is_correction``).
    Minutengenau (``work_window_service.same_minute``, Review Task 6)."""
    return bool(entry.auto_closed) and (
        proposed_end is None
        or not work_window_service.end_is_correction(proposed_end, entry.end_time)
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
    kein Protokoll). Wirft 400 (offen, ``auto_closed``) bzw. 409 (Kollision).

    Gesamtreview 1.20 (Fund 1): steht am Tag eine Abwesenheit (Misch-Tag,
    gebucht mit ``keep_time_entries``), wird ihre Gutschrift danach auf den
    nicht gearbeiteten Rest neu geklemmt (F1, Spec 9.6) — sonst zählte das Ist
    die anerkannte Arbeit UND die beim Buchen gegen das gekappte Netto geklemmte
    Gutschrift. Eine Einzelzeile je angeglichener Abwesenheit, Quelle
    ``credit_override`` wie die Zeile des Eintrags."""
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
    # Fund 1: F1 am Tag neu anwenden — dieselbe Rechnung wie die Rückrechnung
    # (``calculation_service.reapply_f1_for_day``); ``raw_hours`` bleibt stehen.
    # Die Ankersperre der Person hält der Aufrufer (P5).
    # Erst flushen: die Session läuft mit ``autoflush=False``, die Neuklemmung
    # liest die Einträge des Tages per SQL. Ohne Flush sähe sie bei
    # „Genehmigen und anerkennen" mit Datumswechsel den Eintrag noch am alten
    # Tag (Zieltag ungeklemmt, Phantom-Saldo). Die Kollisionsprüfung oben ist
    # schon gelaufen — der neue Beginn verletzt die UNIQUE-Regel nicht.
    db.flush()
    owner = db.query(User).filter(
        User.id == entry.user_id,
        User.tenant_id == entry.tenant_id,  # F-026
    ).first()
    if owner is not None:
        absence_retarget_audit.add_absence_retarget_rows(
            db, calculation_service.reapply_f1_for_day(db, owner, entry.date),
            user_id=entry.user_id,
            changed_by=changed_by_id,
            tenant_id=entry.tenant_id,
            source=CREDIT_OVERRIDE_SOURCE,
            trigger=MIXED_DAY_TRIGGER,
            change_request_id=change_request_id,
        )
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
    Nachweis, und darf geleistete Arbeit nicht verstecken (P4). Damit ist dies
    die EINZIGE Quelle von ``BREAK_WARNING`` (Gesamtreview 1.20 B1 geprüft):
    ``BREAK_WAIVER`` behauptete eine dokumentierte Ausnahme, die es nicht gibt,
    ``PRESENCE_BREAK`` meint die Anwesenheit laut Stempel. Das Frontend
    (``utils/arbzgWarnings.ts``) zeigt den §4-Text ohne Code."""
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
