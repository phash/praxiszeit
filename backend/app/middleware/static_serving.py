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


class RequestSizeLimitMiddleware:
    """
    Limits request body size — pure ASGI so it enforces the cap even when the
    client uses ``Transfer-Encoding: chunked`` (no Content-Length header). The
    previous BaseHTTPMiddleware variant only checked the Content-Length
    header, which a malicious client could simply omit by switching to chunked
    encoding and stream an arbitrarily large body.

    Strategy: wrap the ASGI ``receive`` so we count bytes across every
    ``http.request`` message and abort the request the moment cumulative size
    exceeds ``max_size``.

    Default: 2MB (matching nginx.conf's client_max_body_size).
    """

    def __init__(self, app, max_size: int = 2 * 1024 * 1024):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Fast-path: if the client sent a Content-Length we can reject before
        # reading any body at all.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self.max_size:
                        return await self._send_413(send)
                except ValueError:
                    # malformed Content-Length — force-reject
                    return await self._send_413(send)
                break

        received_bytes = 0

        async def wrapped_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"") or b""
                received_bytes += len(body)
                if received_bytes > self.max_size:
                    # Signal end-of-stream so downstream cleanup runs, then
                    # raise so the app sees the aborted request.
                    raise _RequestTooLargeError()
            return message

        try:
            await self.app(scope, wrapped_receive, send)
        except _RequestTooLargeError:
            await self._send_413(send)

    async def _send_413(self, send):
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        })
        await send({
            "type": "http.response.body",
            "body": b"Request body too large",
        })


class _RequestTooLargeError(Exception):
    """Internal signal used by RequestSizeLimitMiddleware to abort reads."""
    pass
