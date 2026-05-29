"""In-App Bug-Reporting (#136).

Proxy-Endpoint: der eingeloggte Nutzer meldet aus der App einen Fehler/Feedback;
das Backend ergaenzt serverseitig license_id (customer_id der Lizenz), App-Version
und OS und leitet die Meldung als multipart/form-data an den zentralen pzweb-
Bug-Tracker weiter (POST {FEEDBACK_SERVER_URL}/v1/bugs).

Warum Proxy statt Direkt-POST aus dem Browser: CORS, und license_id/Version/OS
gehoeren nicht ins Frontend. Host wird gegen die Update-Allowlist geprueft.

NB: KEIN ``from __future__ import annotations`` hier — der ``@limiter.limit``-
Wrapper (slowapi) loest Type-Hints sonst in seinem eigenen Modul-Namespace auf,
wo ``FeedbackReportIn`` unbekannt ist; FastAPI sieht den Body dann als
Query-Param und liefert 422.
"""

import logging
import platform
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core import license as license_module
from app.core.limiter import limiter
from app.core.updater import APP_VERSION, _ALLOWED_UPDATE_HOSTS
from app.middleware.auth import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Outbound-Timeout zum pzweb-Bug-Tracker. Grosszuegig genug fuer langsame
# Verbindungen, aber begrenzt damit ein haengendes pzweb den App-Request nicht
# ewig blockiert.
_PZWEB_TIMEOUT_SECONDS = 15.0


class FeedbackReportIn(BaseModel):
    """Vom Frontend gesendeter Body. license_id/app_version/os ergaenzt der Server."""
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    severity: Literal["low", "medium", "high", "critical"] = "medium"


def _verify_feedback_host(url: str) -> None:
    """Refuse a feedback target URL outside the allowlist; enforce HTTPS.

    Reuses ``_ALLOWED_UPDATE_HOSTS`` — die pzweb-Domain steht dort bereits.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Feedback server URL must use HTTPS: {url}")
    if parsed.hostname not in _ALLOWED_UPDATE_HOSTS:
        raise ValueError(f"Feedback server host '{parsed.hostname}' not in allowlist")


@router.post("/report")
@limiter.limit("10/hour")
def report_feedback(
    request: Request,
    payload: FeedbackReportIn,
    current_user: User = Depends(get_current_user),
):
    """Leite eine Bug-/Feedback-Meldung an den pzweb-Bug-Tracker weiter.

    Antworten ans Frontend (App bleibt immer stabil, nie 500/Crash):
      200  -> {"status": "received", "id": <pzweb-id>}
      400  -> keine Lizenz hinterlegt (ohne customer_id keine Meldung moeglich)
      409  -> pzweb 403 (Lizenz inaktiv/abgelaufen)
      429  -> pzweb 429 (Rate-Limit)
      502  -> Netzwerk-/Server-Fehler beim pzweb-Call
    """
    lic = license_module.get_current_license()
    license_id = getattr(lic, "customer_id", "") if lic else ""
    if not license_id:
        if settings.BETA_MODE:
            # In der Beta gibt es keine Lizenz — Bug-Reports sollen trotzdem
            # möglich sein (gerade in der Beta will man Feedback). Synthetische
            # license_id, damit pzweb die Meldung einer Beta-Quelle zuordnen kann.
            license_id = "beta"
        else:
            raise HTTPException(
                status_code=400,
                detail="Ohne hinterlegte Lizenz ist keine Bug-Meldung möglich.",
            )

    target = f"{settings.FEEDBACK_SERVER_URL.rstrip('/')}/v1/bugs"
    try:
        _verify_feedback_host(target)
    except ValueError as exc:
        logger.warning("Feedback target rejected: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Feedback-Server ist nicht korrekt konfiguriert.",
        )

    # multipart/form-data: jedes Feld als eigener Part (None = kein Dateiname).
    files = {
        "license_id": (None, license_id),
        "title": (None, payload.title),
        "description": (None, payload.description),
        "app_version": (None, APP_VERSION),
        "os": (None, platform.system().lower()),
        "severity": (None, payload.severity),
    }

    try:
        resp = httpx.post(
            target,
            files=files,
            timeout=_PZWEB_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        logger.warning("Feedback forward to pzweb failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Feedback-Server nicht erreichbar, bitte später erneut versuchen.",
        )

    if resp.status_code == 201:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return {"status": "received", "id": body.get("id")}
    if resp.status_code == 403:
        raise HTTPException(
            status_code=409,
            detail="Lizenz inaktiv oder abgelaufen — Bug-Meldung derzeit nicht möglich.",
        )
    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Zu viele Meldungen, bitte später erneut versuchen.",
        )
    if resp.status_code == 422:
        raise HTTPException(status_code=400, detail="Ungültige Eingabe.")

    logger.warning("pzweb /v1/bugs returned unexpected status %s", resp.status_code)
    raise HTTPException(
        status_code=502,
        detail="Feedback-Server-Fehler, bitte später erneut versuchen.",
    )
