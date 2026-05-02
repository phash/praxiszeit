from pathlib import Path

from fastapi.responses import FileResponse
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


# Headers we propagate from the inner middleware chain onto SPA-fallback
# responses. SPAFallbackMiddleware sits OUTSIDE SecurityHeadersMiddleware in
# the stack (added later in main.py → wraps it), so a Response constructed
# inside dispatch() bypasses SecurityHeadersMiddleware unless we copy the
# headers it set on the inner 404 response.
_PROPAGATED_SECURITY_HEADERS = (
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Content-Security-Policy",
    "Strict-Transport-Security",
)


class SPAFallbackMiddleware(BaseHTTPMiddleware):
    """
    Serves the SPA shell (index.html) for unknown GET routes so React Router
    can resolve client-side routes after a hard reload, plus serves arbitrary
    static files that live in the frontend dist root (favicons, manifests,
    fonts) without an explicit mount. Replaces nginx
    ``try_files $uri $uri/ /index.html``.

    Asset vs. navigation
    --------------------
    Requests whose last path segment contains a ``.`` are treated as static
    asset requests *unless* the client explicitly asks for HTML
    (``Accept: text/html``). Asset requests that hit a 404 do NOT fall
    through to ``index.html`` — they return a real 404. This prevents a
    classic post-update breakage: a stale Service Worker (left over from a
    previous app version) requests an old hashed CSS bundle that no longer
    exists on disk; without this guard the middleware would happily reply
    with ``index.html`` and ``Content-Type: text/html``, which the browser
    refuses to apply as a stylesheet — leading to an unstyled page on every
    navigation until the user manually unregisters the SW.
    """

    def __init__(self, app, frontend_dir: Path, index_html: bytes):
        super().__init__(app)
        self._frontend_dir = Path(frontend_dir).resolve()
        self._index_html = index_html

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if (request.method != "GET"
                or response.status_code != 404
                or request.url.path.startswith("/api/")):
            return response

        path = request.url.path
        rel_path = path.lstrip("/")
        if rel_path:
            file_path = self._frontend_dir / rel_path
            try:
                resolved = file_path.resolve()
            except (OSError, ValueError):
                resolved = None
            if (resolved is not None
                    and self._frontend_dir in resolved.parents
                    and file_path.is_file()):
                file_response = FileResponse(str(file_path))
                _propagate_security_headers(response, file_response)
                return file_response

        if _looks_like_asset_request(path, request.headers.get("accept", "")):
            return response

        if not self._index_html:
            return response

        spa_headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}
        for name in _PROPAGATED_SECURITY_HEADERS:
            value = response.headers.get(name)
            if value is not None:
                spa_headers[name] = value
        return Response(
            content=self._index_html,
            media_type="text/html",
            headers=spa_headers,
        )


def _looks_like_asset_request(path: str, accept_header: str) -> bool:
    """A request looks like a static asset if its last path segment has an
    extension AND the client did not explicitly ask for HTML navigation.

    Browsers requesting CSS/JS/images send ``Accept: text/css,*/*;q=0.1``,
    ``image/png,*/*`` etc. — never ``text/html``. Top-level navigations send
    ``Accept: text/html,...``. This makes the rule safe even for SPA routes
    that happen to contain a dot (``/users/john.doe``)."""
    last_segment = path.rsplit("/", 1)[-1]
    if "." not in last_segment:
        return False
    if path.startswith("/assets/"):
        # /assets/* is reserved for hashed bundles. Clients should never
        # navigate to those URLs — short-circuit independent of Accept.
        return True
    if "text/html" in accept_header.lower():
        return False
    return True


def _propagate_security_headers(source: Response, target: Response) -> None:
    """Copy security headers from source to target (only if not already set
    on target). Used to keep CSP/HSTS/etc. on responses that the SPA fallback
    constructs after the inner SecurityHeadersMiddleware ran."""
    for name in _PROPAGATED_SECURITY_HEADERS:
        if name in target.headers:
            continue
        value = source.headers.get(name)
        if value is not None:
            target.headers[name] = value
