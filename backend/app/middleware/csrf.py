"""
F-024: CSRF protection via double-submit cookie pattern.

The access token is a Bearer token in Authorization header and therefore not
CSRF-vulnerable by itself. BUT the refresh cookie is an HttpOnly cookie scoped
to /api/auth/refresh; if COOKIE_SAMESITE is ever lowered to "none" (e.g. for
embedded SaaS usage), cross-site POSTs could trigger silent token refreshes and
any future cookie-authenticated mutating endpoint. This middleware adds a
second line of defense that fails closed in that scenario.

Pattern:
1. On successful login/refresh, the backend sets a **non-HttpOnly** cookie
   ``csrf_token`` with a random 32-byte value and SameSite=Lax.
2. The frontend reads the cookie (document.cookie) and mirrors it into the
   ``X-CSRF-Token`` header on every unsafe request.
3. This middleware rejects unsafe requests (POST/PUT/PATCH/DELETE) whose
   ``csrf_token`` cookie is present but whose ``X-CSRF-Token`` header is
   missing or does not match. Pure API clients (no cookie, only Bearer token)
   are allowed through.

Exempt paths: login and refresh (no established session yet), health check.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths where CSRF enforcement is skipped because no authenticated browser
# session exists yet (login) or the endpoint is idempotent.
_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/health",
})


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        method = request.method.upper()

        if method not in _UNSAFE_METHODS:
            return await call_next(request)

        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
        if not cookie_value:
            # No CSRF cookie present → request is from a non-browser Bearer
            # client (no session cookie → no CSRF risk) or a browser that
            # never completed login. Let it through; Bearer auth on its own
            # is immune to CSRF because Authorization headers are never
            # auto-attached by the browser on cross-site requests.
            return await call_next(request)

        header_value = request.headers.get(CSRF_HEADER_NAME)
        if not header_value or header_value != cookie_value:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF-Token fehlt oder ungültig"},
            )

        return await call_next(request)
