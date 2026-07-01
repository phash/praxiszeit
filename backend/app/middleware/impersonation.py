"""Read-only enforcement for impersonation sessions (#370).

When a request carries an impersonation access token (``imp`` claim), every write
method is rejected with 403. This is the hard guarantee behind #370: an admin
viewing the app *as* an employee can never perform an action that would be
attributed to the employee (§16 ArbZG / Willenserklärungen). Reads pass through
unchanged; the single write allowed is ending the session.

Mirrors ``LicenseReadOnlyMiddleware``: the JWT is decoded lazily per request
(cheap on the hot path) and no DB access is needed — the ``imp`` claim alone is
authoritative because the token is signed with ``SECRET_KEY``.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services.auth_service import decode_token

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths that must remain callable *with* an impersonation token. Ending the
# session is the one write an impersonated request needs to perform.
_EXEMPT_PATHS = frozenset({"/api/admin/impersonate/end"})


class ImpersonationReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject write requests made under a read-only impersonation token."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method in _WRITE_METHODS and request.url.path not in _EXEMPT_PATHS:
            if _is_impersonation_request(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Nur-Lese-Modus: In der Ansicht als Mitarbeiter:in sind keine "
                            "Änderungen möglich. Kehren Sie zu Ihrem Admin-Konto zurück."
                        )
                    },
                )
        return await call_next(request)


def _is_impersonation_request(request: Request) -> bool:
    """True if the bearer token carries an ``imp`` claim (impersonation session)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    payload = decode_token(auth.split(" ", 1)[1]) or {}
    return bool(payload.get("imp"))
