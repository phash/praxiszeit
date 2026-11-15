"""Kundenfall 2026-11-15: Protokoll-Einstellungen fuer Dienstprotokoll und Docker-Log.

Log-Audit Punkt 8 (NET-1): Der Logger ``praxiszeit.security`` (AUTH-Zeilen aus
``routers/auth.py``) hatte keinen eigenen Handler. uvicorn konfiguriert nur
seine eigenen Logger, die Wurzel bleibt leer — die Zeilen liefen ueber
``logging.lastResort``: ohne Uhrzeit, ohne IP, und INFO-Zeilen (``login_success``,
``logout``) fielen ganz weg. Wer wann von welchem Rechner gesperrt wurde, war
aus dem Kundenprotokoll nicht ablesbar.

Jetzt ein eigener Handler nach stderr (nativ: NSSM schreibt ``service-stderr.log``,
Docker: ``docker compose logs backend``) mit Zeitstempel und ``ip=``. Die IP
kommt aus einer ContextVar, die ``ClientIpContextMiddleware`` je Anfrage setzt
(gleiche Regel wie das Rate-Limit: ``limiter._get_real_ip``). ``propagate =
False``: nativ startet praxiszeit-server.py uvicorn mit ``--log-config``, dort
hat die Wurzel einen stderr-Handler — ohne die Sperre stuende jede AUTH-Zeile
zweimal in service-stderr.log (einmal ohne ``ip=``; Review-Fund). Die Tests
lesen die Zeilen trotzdem ueber ``caplog`` (``tests/conftest.py`` reicht den
Logger an die Wurzel weiter).

Log-Audit Punkt 17 (NET-3): drei Polling-Endpunkte machten 86 % des
Access-Logs aus. ``PollingAccessLogFilter`` verwirft nur deren 2xx-Zeilen;
401, 307 und 5xx bleiben sichtbar.

Beide ``install_*``-Funktionen sind idempotent (mehrfacher Import von
``app.main``, Tests).
"""
from __future__ import annotations

import contextvars
import logging
import sys

SECURITY_LOGGER = "praxiszeit.security"
ACCESS_LOGGER = "uvicorn.access"
_MARKER = "_praxiszeit_security_handler"

client_ip_var: contextvars.ContextVar[str] = contextvars.ContextVar("praxiszeit_client_ip", default="-")


class ClientIpFilter(logging.Filter):
    """Haengt ``record.client_ip`` an (``-`` ausserhalb einer Anfrage)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "client_ip"):
            # Steuerzeichen wie in auth._safe_log_text: eine IP aus einem
            # vertrauten Proxy-Header darf keine Zeile faelschen.
            from app.core.db_errors import _CONTROL_CHARS
            record.client_ip = _CONTROL_CHARS.sub(" ", client_ip_var.get())[:64]
        return True


def install_security_log_handler() -> None:
    lg = logging.getLogger(SECURITY_LOGGER)
    if not any(isinstance(f, ClientIpFilter) for f in lg.filters):
        lg.addFilter(ClientIpFilter())
    if any(getattr(h, _MARKER, False) for h in lg.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(ClientIpFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s ip=%(client_ip)s",
    ))
    setattr(handler, _MARKER, True)
    lg.addHandler(handler)
    # Eigener Handler reicht: nicht zusaetzlich an den Wurzel-Handler der
    # nativen uvicorn-Logkonfiguration (doppelte Zeilen, Review-Fund).
    lg.propagate = False
    # INFO: login_success/logout gehoeren zur Spur (vorher von der Wurzel-Stufe
    # WARNING verschluckt).
    lg.setLevel(logging.INFO)


class ClientIpContextMiddleware:
    """Reine ASGI-Middleware: setzt ``client_ip_var`` fuer die Dauer der Anfrage.

    Der Threadpool fuer synchrone Endpunkte uebernimmt den Kontext
    (``run_in_threadpool`` kopiert ContextVars)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        try:
            from starlette.requests import Request
            from app.core.limiter import _get_real_ip
            ip = _get_real_ip(Request(scope))
        except Exception:  # noqa: BLE001 — Protokoll-Detail, nie die Anfrage kippen
            ip = "-"
        token = client_ip_var.set(ip or "-")
        try:
            await self.app(scope, receive, send)
        finally:
            client_ip_var.reset(token)


POLLING_PATHS = frozenset({
    "/api/time-entries/clock-status",
    "/api/admin/change-requests/pending-count",
    "/api/admin/vacation-requests/pending-count",
})


class PollingAccessLogFilter(logging.Filter):
    """Verwirft 2xx-Zeilen der Polling-Endpunkte im uvicorn-Access-Log.

    uvicorn uebergibt ``(client, method, full_path, http_version, status)`` als
    ``record.args``. Andere Formen (andere uvicorn-Version) werden nie verworfen.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        try:
            path = str(args[2]).split("?", 1)[0].rstrip("/") or "/"
            status = int(args[4])
        except (TypeError, ValueError):
            return True
        return not (path in POLLING_PATHS and 200 <= status < 300)


def install_access_log_filter() -> None:
    lg = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, PollingAccessLogFilter) for f in lg.filters):
        lg.addFilter(PollingAccessLogFilter())
