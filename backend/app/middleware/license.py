"""License enforcement middleware.

When a native-install license has expired, the app enters read-only mode:
data remains viewable and exportable (ArbZG-compliant), but all writes are
rejected with HTTP 403.

Implementing this as ASGI middleware (rather than per-endpoint dependencies)
guarantees new write endpoints are covered by default — the review that
triggered this module found `require_writable` existed but was attached to
zero routes.

Auth endpoints stay writable so admins can still log in, refresh their
session, and log out of an expired-license deployment.
"""

from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.core import license as license_module
from app.core.deployment import is_onprem


_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that must stay writable regardless of license state:
# - login/logout/refresh: admins must still be able to access the tenant to
#   read data and export records (§16 ArbZG)
# - CSP report-only endpoints (if any): no user-data mutation
_EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/password-reset",
)


class LicenseReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject write requests when the license is in read-only mode."""

    def __init__(self, app: ASGIApp, exempt_prefixes: Iterable[str] = _EXEMPT_PATH_PREFIXES):
        super().__init__(app)
        self._exempt = tuple(exempt_prefixes)

    async def dispatch(self, request: Request, call_next):
        # On-prem: license file gates writes.
        if (
            is_onprem()
            and request.method in _WRITE_METHODS
            and license_module.is_read_only()
            and not request.url.path.startswith(self._exempt)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Lizenz abgelaufen. Die Anwendung befindet sich im Nur-Lese-Modus. "
                        "Bestehende Daten bleiben lesbar und exportierbar. "
                        "Bitte erneuern Sie Ihre Lizenz, um wieder Eingaben zu ermöglichen."
                    )
                },
            )

        # SaaS: tenant subscription_status='suspended' → read-only. We look
        # up the tenant via the JWT tid claim; unauthenticated requests
        # short-circuit because they have no tenant to check against.
        if (
            not is_onprem()
            and request.method in _WRITE_METHODS
            and not request.url.path.startswith(self._exempt)
            and not request.url.path.startswith("/api/webhooks/")  # Stripe webhook must write
        ):
            suspended_msg = _check_saas_suspend(request)
            if suspended_msg is not None:
                return JSONResponse(status_code=403, content={"detail": suspended_msg})

        return await call_next(request)


def _check_saas_suspend(request: Request) -> str | None:
    """Return a human-readable message when the caller's tenant is suspended,
    else None. Decoded lazily per-request — cheap enough for the hot path."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None  # no JWT → the auth layer will reject; nothing for us to do
    token = auth.split(" ", 1)[1]

    from app.database import SessionLocal, set_superadmin_context
    from app.models.tenant import Tenant
    from app.services.auth_service import decode_token

    payload = decode_token(token) or {}
    tid = payload.get("tid")
    if not tid:
        return None

    db = SessionLocal()
    try:
        set_superadmin_context(db)
        tenant = db.query(Tenant).filter(Tenant.id == tid).first()
        if tenant and tenant.subscription_status == "suspended":
            return (
                "Konto gesperrt. Der Schreibzugriff ist deaktiviert; "
                "bestehende Daten bleiben lesbar und exportierbar. "
                "Bitte aktualisieren Sie Ihre Zahlungsmethode."
            )
    finally:
        db.close()
    return None
