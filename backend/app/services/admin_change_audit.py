"""#537 (Audit 2026-11-07, A2-5): dauerhafte Spur fuer Verwaltungsaenderungen,
die Ist, Saldo oder Urlaub bewegen, ohne einen Zeiteintrag zu beruehren.

Manuelle Ueberträge, Jahresabschluss anlegen/loeschen, Einstellungen (z. B. der
Kappungspuffer) und eigene Feiertage hinterliessen bisher nichts ausser
hoechstens einer rotierenden Logzeile: wer den Ueberstunden-Uebertrag von
+40 h auf 0 h setzte, war nicht nachweisbar. Die Zeilen gehen in
``time_entry_audit_logs`` — dort sind sie gehasht und verkettet (#121/#537) und
erscheinen im Aenderungsprotokoll der betroffenen Person bzw. (bei
mandantenweiten Vorgaengen) des handelnden Verwalters.

``action`` und ``source`` sind ``varchar(40)`` — alle Marker hier < 40 Zeichen.
Labels im Frontend: ``frontend/src/constants/auditSources.ts`` und
``AuditLog.tsx`` (``actionLabels``).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import TimeEntryAuditLog

ACTION_CARRYOVER_SET = "carryover_set"
ACTION_CARRYOVER_DELETE = "carryover_delete"
ACTION_SETTING_CHANGE = "setting_change"
ACTION_HOLIDAY_CHANGE = "holiday_change"
ACTION_USER_FIELD_CHANGE = "user_field_change"
SOURCE_CARRYOVER = "carryover"          # manueller Uebertrag
SOURCE_YEAR_CLOSING = "year_closing"    # Jahresabschluss anlegen/loeschen
SOURCE_SETTINGS = "settings"
SOURCE_HOLIDAYS = "holidays"
SOURCE_USER_ADMIN = "user_admin"        # Benutzerverwaltung (PUT /admin/users)

# A1-17: Felder der Benutzerverwaltung, die ArbZG-Auswertungen oder das
# Beschaeftigungsfenster steuern. § 18 nimmt eine Person aus allen
# ArbZG-Berichten heraus (auch rueckwirkend), das Fenster filtert Soll und Ist
# — wer das wann umstellte, muss nachweisbar sein.
USER_TRACKED_FIELDS = {
    "exempt_from_arbzg": "Ausgenommen nach § 18 ArbZG",
    "is_night_worker": "Nachtarbeitnehmer (§ 6 ArbZG)",
    "first_work_day": "Erster Arbeitstag",
    "last_work_day": "Letzter Arbeitstag",
}


def _num(value, digits: int) -> str:
    return f"{Decimal(str(value or 0)):.{digits}f}".replace(".", ",")


def carryover_text(year: int, overtime_hours, vacation_days, origin: Optional[str]) -> str:
    origin_label = {"manual": "manuell", "year_closing": "Jahresabschluss"}.get(origin or "", origin or "")
    text = (
        f"Übertrag {year}: Überstunden {_num(overtime_hours, 2)} h, "
        f"Urlaub {_num(vacation_days, 1)} Tage"
    )
    return f"{text} ({origin_label})" if origin_label else text


def log_change(db: Session, *, tenant_id, user_id, changed_by, action: str, source: str,
               old_text: Optional[str], new_text: Optional[str]) -> TimeEntryAuditLog:
    log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user_id,
        changed_by=changed_by,
        action=action,
        source=source,
        old_note=old_text,
        new_note=new_text,
        tenant_id=tenant_id,
    )
    db.add(log)
    return log


def log_carryover(db: Session, *, carryover_user_id, tenant_id, changed_by, year: int,
                  before, after, source: str) -> None:
    """``before``/``after`` = (overtime_hours, vacation_days, origin) oder None."""
    if before == after:
        return
    log_change(
        db, tenant_id=tenant_id, user_id=carryover_user_id, changed_by=changed_by,
        action=ACTION_CARRYOVER_SET if after is not None else ACTION_CARRYOVER_DELETE,
        source=source,
        old_text=carryover_text(year, *before) if before is not None else None,
        new_text=carryover_text(year, *after) if after is not None else None,
    )


def carryover_state(carryover):
    if carryover is None:
        return None
    return (
        Decimal(str(carryover.overtime_hours or 0)),
        Decimal(str(carryover.vacation_days or 0)),
        carryover.source,
    )


def log_setting(db: Session, *, current_user, key: str, old_value, new_value) -> None:
    if old_value == new_value:
        return
    log_change(
        db, tenant_id=current_user.tenant_id, user_id=current_user.id,
        changed_by=current_user.id, action=ACTION_SETTING_CHANGE, source=SOURCE_SETTINGS,
        old_text=f"{key} = {old_value}" if old_value is not None else f"{key} (nicht gesetzt)",
        new_text=f"{key} = {new_value}",
    )


def holiday_text(holiday_date, name) -> str:
    return f"Feiertag {holiday_date.strftime('%d.%m.%Y')}: {name}"


def log_holiday(db: Session, *, current_user, before, after) -> None:
    """``before``/``after`` = (date, name) oder None."""
    if before == after:
        return
    log_change(
        db, tenant_id=current_user.tenant_id, user_id=current_user.id,
        changed_by=current_user.id, action=ACTION_HOLIDAY_CHANGE, source=SOURCE_HOLIDAYS,
        old_text=holiday_text(*before) if before else None,
        new_text=holiday_text(*after) if after else None,
    )


def _user_field_value(value) -> str:
    if value is None:
        return "nicht gesetzt"
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    return str(value)


def log_user_fields(db: Session, *, current_user, user, update_data: dict) -> None:
    """A1-17: je geaendertem Feld aus ``USER_TRACKED_FIELDS`` eine Zeile im
    Aenderungsprotokoll der Person (alt → neu, handelnder Verwalter).
    VOR dem Zuweisen aufrufen: ``user`` traegt noch die alten Werte."""
    for field, label in USER_TRACKED_FIELDS.items():
        if field not in update_data:
            continue
        old, new = getattr(user, field, None), update_data[field]
        if old == new:
            continue
        log_change(
            db, tenant_id=user.tenant_id, user_id=user.id,
            changed_by=current_user.id, action=ACTION_USER_FIELD_CHANGE,
            source=SOURCE_USER_ADMIN,
            old_text=f"{label}: {_user_field_value(old)}",
            new_text=f"{label}: {_user_field_value(new)}",
        )
