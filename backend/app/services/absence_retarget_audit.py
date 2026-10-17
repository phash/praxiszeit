"""Einzelzeilen des Änderungsprotokolls für gerechnete Abwesenheits-Stunden
(``calculation_service.AbsenceRetarget``, Task 15).

EINE Quelle für das Zeilenformat „<Typ> <alt> h" → „<Typ> <neu> h — <Auslöser>"
— genutzt von der Arbeitszeit-Änderung (Anlegen/Löschen,
``admin_users._log_wh_change_retarget``, Quelle ``wh_change``) und vom
Anerkennen an einem Misch-Tag (``credit_override_service``, Quelle
``credit_override``, Gesamtreview 1.20 Fund 1).

Der Typ steht als eingebautes Label, nie als Name eines eigenen Grundes (#312):
der kann gesundheitsbezogen sein („Reha"), und den Typ treibt ohnehin die
Berechnung. Gerade über das Label („Krank ") erkennt
``admin_time_entries._audit_note_is_health_sensitive`` die Zeile als Art.-9-Datum.

Die Zeilen entstehen per ORM (``db.add``), damit der ``before_insert``-Hook den
``row_hash`` (#121) berechnet. Keine stille Obergrenze (300 Abwesenheiten → 300
Zeilen). Nie aus einer Vorschau aufrufen — die rollt zurück.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import TimeEntryAuditLog
from app.services.export_service import ABSENCE_TYPE_LABELS_DE, format_hours_de


def add_absence_retarget_rows(
    db: Session,
    adjusted: Iterable,
    *,
    user_id,
    changed_by,
    tenant_id,
    source: str,
    trigger: str,
    change_request_id=None,
) -> None:
    """Je tatsächlich angepasster Abwesenheit eine Zeile: ``old_date``/``new_date``
    tragen das (unveränderte) Datum — die Rückrechnung verschiebt nie den Tag,
    nur die Stunden, damit die Zeile im Protokoll nicht wie eine Verschiebung
    aussieht. ``trigger`` ist der Auslöser im Klartext, identisch auf jeder
    Zeile."""
    for rec in adjusted:
        label = ABSENCE_TYPE_LABELS_DE.get(rec.absence_type.value, rec.absence_type.value)
        db.add(TimeEntryAuditLog(
            time_entry_id=None,
            user_id=user_id,
            changed_by=changed_by,
            action="update",
            source=source,
            change_request_id=change_request_id,
            old_date=rec.date,
            new_date=rec.date,
            old_note=f"{label} {format_hours_de(rec.old_hours)} h",
            new_note=f"{label} {format_hours_de(rec.new_hours)} h — {trigger}",
            tenant_id=tenant_id,
        ))
