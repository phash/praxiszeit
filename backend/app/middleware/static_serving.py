from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses.
    Replicates the headers from nginx.conf for native mode (SERVE_FRONTEND=True),
    but also useful as defense-in-depth when running behind nginx.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        # F-050: HSTS only on HTTPS. Setting HSTS over HTTP is useless in
        # Chrome/Firefox (they ignore it) but Safari historically accepted
        # it, which can brick a native-Windows install that was accessed
        # via HTTP:// first. Gate on COOKIE_SECURE (operator explicitly
        # enabled HTTPS) OR the current request scheme actually being
        # https — whichever we can observe.
        is_https = (
            settings.COOKIE_SECURE
            or request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits request body size (replaces nginx client_max_body_size in native mode).
    Default: 2MB (matching nginx.conf).
    """

    def __init__(self, app, max_size: int = 2 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return PlainTextResponse(
                "Request body too large",
                status_code=413,
            )
        return await call_next(request)
