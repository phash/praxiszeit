"""Self-service endpoints für den eingeloggten Mitarbeiter.

Aktuell:
    GET /api/me/data-export — DSGVO Art. 15 Auskunfts-Export (Issue #119)

Routenmuster ``/api/me/*`` ist reserviert für Self-Service ohne Admin-Rolle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import TimeEntryAuditLog, User
from app.services import lifecycle_service, type_colors_service


router = APIRouter(prefix="/api/me", tags=["self-service"])


@router.get("/type-colors")
def get_my_type_colors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """#157: Effektive Typ-Farben des eigenen Tenants — für Kalender-/Dialog-
    Rendering. Für jeden authentifizierten Nutzer (nicht nur Admin) verfügbar."""
    return type_colors_service.get_type_colors(db, current_user.tenant_id)


# Rate-Limit: 5/Tag pro IP. Per-User waere semantisch korrekter, dafuer
# muesste der Limiter den User aus dem JWT-Cookie extrahieren. Pragmatischer
# Kompromiss: IP-basiert (slowapi-Default) verhindert Scraping, der zusaetz-
# liche Audit-Log-Eintrag pro Export macht Missbrauch nachvollziehbar.
@router.get("/data-export")
@limiter.limit("5/day")
def data_export(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DSGVO Art. 15 Self-Service Auskunfts-Export (Issue #119).

    Liefert alle personenbezogenen Daten des aufrufenden Mitarbeiters
    als JSON-Download. Tenant-gescoped via RLS + F-026, fremde User
    im gleichen Tenant sind ausgeschlossen.

    Schreibt fuer DSGVO-Nachvollziehbarkeit einen Audit-Log-Eintrag
    mit ``source='self_data_export'``.
    """
    payload = lifecycle_service.build_self_export_payload(db, current_user)

    # Audit-Log mit Counts im Note-Feld fuer Nachvollziehbarkeit. Wird NACH
    # dem Payload geschrieben, erscheint also erst im NAECHSTEN Export — das
    # ist OK, der Eintrag dient der Admin-Aufsicht, nicht der Eigen-Auskunft.
    # Source-Marker 'self_data_export' = 16 Zeichen, unter dem 40er-Limit
    # aus Migration 037.
    db.add(
        TimeEntryAuditLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="self_data_export",
            source="self_data_export",
            new_note=(
                f"Self-Service DSGVO Art. 15 Export: "
                f"{payload['counts']['time_entries']} Zeiteintraege, "
                f"{payload['counts']['absences']} Abwesenheiten, "
                f"{payload['counts']['vacation_requests']} Urlaubsantraege, "
                f"{payload['counts']['change_requests']} Aenderungsantraege"
            ),
        )
    )
    db.commit()

    blob = lifecycle_service.export_as_json_bytes(payload)
    filename = (
        f"PraxisZeit_MeineDaten_{current_user.username}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    )
    return StreamingResponse(
        iter([blob]),
        media_type="application/json",
        # Review 2026-06-23: filename enthaelt den username (nicht zeichen-
        # restringiert) -> RFC-5987-encoden statt roh interpolieren.
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)},
    )
