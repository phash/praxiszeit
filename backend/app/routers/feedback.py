"""In-App-Problemmeldung (#136, #557 — Protokoll mrd-report-1).

Zwei Schritte, beide als Proxy (CORS; Schlüssel, Lizenz, Version und OS gehören
nicht ins Frontend):

* ``POST /api/feedback/preview`` baut die Meldung serverseitig (Kontextblock,
  optional bereinigter Protokollauszug, bereinigt über den PraxisZeit-Sanitizer)
  und liefert exakt die Felder, die gesendet würden — ohne ``credential``.
* ``POST /api/feedback/send`` nimmt Titel und Beschreibung aus der Vorschau
  zurück, bereinigt sie erneut (idempotent, Schutz gegen manipulierte Clients),
  setzt die Serverfelder neu und leitet über ``report_client.send_report`` weiter.

Warum Neusenden statt Vorschau-Token: zustandslos (mehrere uvicorn-Worker,
Neustart zwischen Vorschau und Senden), der Dialog braucht die volle Meldung
ohnehin für „Als Datei speichern“, und der Sanitizer ist idempotent — ein
manipulierter Client kann nur Text senden, den er auch hätte tippen können.

NB: KEIN ``from __future__ import annotations`` hier — der ``@limiter.limit``-
Wrapper (slowapi) loest Type-Hints sonst in seinem eigenen Modul-Namespace auf,
wo ``FeedbackPreviewIn`` unbekannt ist; FastAPI sieht den Body dann als
Query-Param und liefert 422.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.deployment import is_saas
from app.core.limiter import limiter
from app.core.report_sanitize_pz import sanitize_praxiszeit_text
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserRole
from app.services import report_client
from app.services.report_log_extract import build_log_extract, native_log_dir
from app.services.report_payload import (
    BOARD_URL, DESCRIPTION_MAX, TITLE_MAX, USER_TEXT_MAX, ServerErrorHint,
    build_fields, build_preview, collect_server_fields, resolve_error_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

CREDENTIAL_NOTE = "mrk_praxiszeit_… (nicht angezeigt)"
ADMIN_ONLY_DETAIL = "Nur für Administratoren."
NO_LICENSE_DETAIL = "Ohne hinterlegte Lizenz ist keine Bug-Meldung möglich."
ERROR_LOG_NOT_FOUND_DETAIL = "Fehlereintrag nicht gefunden."
ATTACHMENT_DETAIL = "Nur PNG- oder JPEG-Bilder bis 5 MB."
ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024

_IMAGE_TYPES = {
    "image/png": (b"\x89PNG\r\n\x1a\n", "screenshot.png"),
    "image/jpeg": (b"\xff\xd8\xff", "screenshot.jpg"),
}

Kind = Literal["bug", "feedback", "crash"]
Severity = Literal["low", "medium", "high", "critical"]


class ServerErrorIn(BaseModel):
    status: int = Field(ge=500, le=599)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1, max_length=500, pattern=r"^/api/")


class FeedbackPreviewIn(BaseModel):
    kind: Kind = "bug"
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    text: str = Field(min_length=1, max_length=USER_TEXT_MAX)
    severity: Severity = "medium"
    contact_email: Optional[EmailStr] = Field(default=None, max_length=254)
    include_log: bool = False
    error_log_id: Optional[UUID] = None
    server_error: Optional[ServerErrorIn] = None


class FeedbackPreviewOut(BaseModel):
    transport: str
    title: str
    description: str
    fields: Dict[str, str]
    credential_note: Optional[str]
    log_line_count: int
    truncated: bool
    board_url: str
    contact_email_dropped: bool


class FeedbackSendIn(BaseModel):
    kind: Kind = "bug"
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    severity: Severity = "medium"
    contact_email: Optional[EmailStr] = Field(default=None, max_length=254)
    error_fingerprint: Optional[str] = Field(default=None, max_length=64, pattern=r"^[0-9a-f]+$")


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _forbid_admin_only(user: User, *, crash: bool, extras: bool = False) -> None:
    if (crash or extras) and not _is_admin(user):
        raise HTTPException(status_code=403, detail=ADMIN_ONLY_DETAIL)


@router.post("/preview", response_model=FeedbackPreviewOut)
@limiter.limit("30/hour")
def preview_feedback(
    request: Request,
    payload: FeedbackPreviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Meldung zusammenstellen und so zurückgeben, wie sie gesendet würde."""
    _forbid_admin_only(
        current_user,
        crash=payload.kind == "crash",
        extras=payload.include_log or payload.error_log_id is not None
        or payload.server_error is not None,
    )
    now = datetime.now(timezone.utc)
    server = collect_server_fields()

    # Gleicher Sichtbereich wie die Liste „Fehler-Monitoring“
    # (routers/error_logs.py): on-prem ohne Filter, SaaS eigener Mandant + NULL.
    scope = current_user.tenant_id if is_saas() else None
    error = None
    if payload.error_log_id is not None:
        try:
            error = resolve_error_context(
                db, scope, error_log_id=payload.error_log_id, server_error=None, now=now)
        except LookupError:
            raise HTTPException(status_code=404, detail=ERROR_LOG_NOT_FOUND_DETAIL)
    elif payload.server_error is not None:
        hint = ServerErrorHint(
            payload.server_error.status, payload.server_error.method, payload.server_error.path)
        error = resolve_error_context(
            db, current_user.tenant_id, error_log_id=None, server_error=hint, now=now)

    log_lines = (
        build_log_extract(db, scope, native_log_dir())
        if payload.include_log else None
    )
    built = build_preview(
        title=payload.title, user_text=payload.text, server=server, now_utc=now,
        error=error, log_lines=log_lines,
    )
    transport = report_client.current_transport()
    contact = str(payload.contact_email) if payload.contact_email else None
    fields = build_fields(
        transport=transport, kind=payload.kind, title=built.title,
        description=built.description, severity=payload.severity, contact_email=contact,
        error_fingerprint=error.fingerprint if error is not None else None, server=server,
    )
    return FeedbackPreviewOut(
        transport=transport,
        title=built.title,
        description=built.description,
        fields=fields,
        credential_note=CREDENTIAL_NOTE if transport == "mrd-report-1" else None,
        log_line_count=built.log_line_count,
        truncated=built.truncated,
        board_url=BOARD_URL,
        contact_email_dropped=transport == "legacy" and contact is not None,
    )


def _read_attachment(attachment: Optional[UploadFile]) -> Optional[tuple]:
    if attachment is None:
        return None
    spec = _IMAGE_TYPES.get((attachment.content_type or "").lower())
    data = attachment.file.read(ATTACHMENT_MAX_BYTES + 1)
    if spec is None or not data or len(data) > ATTACHMENT_MAX_BYTES or not data.startswith(spec[0]):
        raise HTTPException(status_code=422, detail=ATTACHMENT_DETAIL)
    return (spec[1], data, attachment.content_type.lower())


@router.post("/send")
@limiter.limit("10/hour")
def send_feedback(
    request: Request,
    payload: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    """Vorschau-Text senden. 200 bei Annahme, 502 bei jedem Upstream-/Transportfehler."""
    try:
        body = FeedbackSendIn.model_validate_json(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False))
    _forbid_admin_only(current_user, crash=body.kind == "crash")
    # PZ-R9: Fingerprints stammen nur aus admin-only Fehlerkontexten.
    fingerprint = body.error_fingerprint if _is_admin(current_user) else None

    server = collect_server_fields()
    transport = report_client.current_transport()
    if transport == "legacy" and not server.license_id:
        # Altweg verlangt license_id (BETA_MODE liefert "beta"); mrd-report-1 nicht.
        raise HTTPException(status_code=400, detail=NO_LICENSE_DETAIL)

    file_part = _read_attachment(attachment)
    # Für Vorschau-Text ein No-op (idempotent); schützt vor manipulierten Clients.
    title = sanitize_praxiszeit_text(body.title)[:TITLE_MAX]
    description = sanitize_praxiszeit_text(body.description)[:DESCRIPTION_MAX]
    fields = build_fields(
        transport=transport, kind=body.kind, title=title, description=description,
        severity=body.severity,
        contact_email=str(body.contact_email) if body.contact_email else None,
        error_fingerprint=fingerprint, server=server,
    )
    result = report_client.send_report(fields, file_part)
    if not result.ok:
        return JSONResponse(
            status_code=502,
            content={"detail": result.detail, "upstream_status": result.upstream_status},
        )
    return {"status": "received", "ref": result.ref, "id": result.report_id,
            "board_url": BOARD_URL}
