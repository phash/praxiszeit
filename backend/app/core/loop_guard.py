"""Kundenfall 2026-11-15, Log-Audit Punkt 3 (LC-7): asyncio-Loop-Waechter fuer Windows.

Unter Windows (Proactor-Loop) faengt CPython einen Fehler beim ``accept()``
ab ("Accept failed on a socket", beim Kunden WinError 64), meldet ihn an den
Loop-Exception-Handler und SCHLIESST den Listening-Socket. Der Prozess lebt
weiter, nimmt aber keine Verbindung mehr an — und der Wachhund in
``praxiszeit-server.py`` prueft nur, ob der Prozess lebt (``poll()``). Beim
Kunden war PraxisZeit so tagelang nicht erreichbar, obwohl der Dienst "lief".

Deshalb: in diesem Fall CRITICAL protokollieren und den Prozess hart mit
Exit 1 beenden (``os._exit``: ein geordnetes Herunterfahren braeuchte genau den
Loop, der gerade kaputt ist). Der Wachhund startet uvicorn dann neu.

Log-Audit D (RT-5): WinError 10054 in ``_call_connection_lost`` (Browser hat
die Verbindung hart geschlossen) ist reines Rauschen — tausende Tracebacks im
Dienstprotokoll. Er geht nur noch auf DEBUG. Alles andere unveraendert an den
Standard-Handler.

Nur unter ``win32`` installiert; Linux/macOS/Docker bleiben unberuehrt.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Callable, Optional

logger = logging.getLogger("app.core.loop_guard")
# Fuer die CRITICAL-Zeile der uvicorn-Logger: hat dort Handler mit Uhrzeit
# (Dienstprotokoll) und haengt am DBErrorHandler (Admin-Fehlerseite).
_critical_logger = logging.getLogger("uvicorn.error")

_WINERROR_NETNAME_DELETED = 64
_WINERROR_CONNECTION_RESET = 10054
_ACCEPT_FAILED = "Accept failed on a socket"


def _flush_logging() -> None:
    for lg in (_critical_logger, logging.getLogger()):
        for h in lg.handlers:
            try:
                h.flush()
            except Exception:  # noqa: BLE001
                pass
    try:
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


def make_loop_exception_handler(exit_fn: Callable[[int], None] = os._exit):
    """Baut den Handler ``(loop, context)``; ``exit_fn`` ist fuer Tests ersetzbar."""

    def _handler(loop, context: dict) -> None:
        message = str(context.get("message") or "")
        exc = context.get("exception")
        winerror = getattr(exc, "winerror", None)

        listener_dead = _ACCEPT_FAILED in message or (
            # WinError 64 ohne Transport = nicht an einer einzelnen Verbindung,
            # sondern am Listener. Mit Transport ist es ein einzelner
            # Verbindungsabbruch — der darf nie den ganzen Dienst beenden.
            isinstance(exc, OSError) and winerror == _WINERROR_NETNAME_DELETED
            and "transport" not in context and "protocol" not in context
        )
        if listener_dead:
            _critical_logger.critical(
                "Der Server nimmt keine Verbindungen mehr an (%s: %s). Der Prozess "
                "wird beendet und vom Dienst neu gestartet.",
                message or "Socket-Fehler", exc,
            )
            _flush_logging()
            exit_fn(1)
            return

        if (isinstance(exc, ConnectionResetError) and winerror == _WINERROR_CONNECTION_RESET
                and "_call_connection_lost" in message):
            logger.debug("Verbindung vom Client zurueckgesetzt (WinError 10054): %s", message)
            return

        loop.default_exception_handler(context)

    return _handler


def install_loop_guard(loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
    """Im laufenden Loop installieren (Lifespan). True, wenn installiert."""
    if sys.platform != "win32":
        return False
    loop = loop or asyncio.get_running_loop()
    loop.set_exception_handler(make_loop_exception_handler())
    return True
