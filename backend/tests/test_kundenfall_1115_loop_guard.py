"""Kundenfall 2026-11-15, Log-Audit Punkt 3 (LC-7) und Rauschen D (RT-5):
unter Windows (Proactor-Loop) schliesst CPython nach „Accept failed on a
socket" (WinError 64) den Listening-Socket — der Prozess lebt weiter, nimmt
aber keine Verbindung mehr an, und der Wachhund (prueft nur ``poll()``) merkt
nichts. Der Loop-Handler beendet den Prozess dann hart (Exit 1), der Wachhund
startet neu. WinError 10054 in ``_call_connection_lost`` ist reines Rauschen
und geht nur noch auf DEBUG.
"""
import asyncio
import logging

import pytest

from app.core import loop_guard


def _winerr(cls, code, text="x"):
    e = cls(text)
    e.winerror = code  # auf Linux gibt es das Attribut nicht von selbst
    return e


class _Loop:
    def __init__(self):
        self.default_calls = []

    def default_exception_handler(self, context):
        self.default_calls.append(context)


@pytest.fixture
def exits():
    calls = []
    return calls, loop_guard.make_loop_exception_handler(exit_fn=calls.append)


def test_accept_failed_exits_with_1(exits, caplog):
    calls, handler = exits
    loop = _Loop()
    with caplog.at_level(logging.CRITICAL):
        handler(loop, {"message": "Accept failed on a socket",
                       "exception": _winerr(OSError, 64), "socket": object()})
    assert calls == [1]
    assert loop.default_calls == []
    assert any(r.levelno == logging.CRITICAL and "neu gestartet" in r.getMessage()
               for r in caplog.records)


def test_winerror_64_without_transport_exits(exits):
    calls, handler = exits
    handler(_Loop(), {"message": "Unhandled", "exception": _winerr(OSError, 64)})
    assert calls == [1]


def test_winerror_64_on_a_single_connection_does_not_exit(exits):
    """Ein einzelner Verbindungsabbruch (transport im Kontext) beendet nie den Dienst."""
    calls, handler = exits
    loop = _Loop()
    handler(loop, {"message": "Fatal read error on pipe transport",
                   "exception": _winerr(OSError, 64), "transport": object()})
    assert calls == []
    assert len(loop.default_calls) == 1


def test_10054_in_call_connection_lost_is_debug_only(exits, caplog):
    calls, handler = exits
    loop = _Loop()
    with caplog.at_level(logging.DEBUG, logger=loop_guard.logger.name):
        handler(loop, {
            "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
            "exception": _winerr(ConnectionResetError, 10054),
        })
    assert calls == []
    assert loop.default_calls == []
    recs = [r for r in caplog.records if r.name == loop_guard.logger.name]
    assert recs and all(r.levelno == logging.DEBUG for r in recs)


def test_10054_elsewhere_goes_to_default(exits):
    calls, handler = exits
    loop = _Loop()
    handler(loop, {"message": "something else", "exception": _winerr(ConnectionResetError, 10054)})
    assert calls == [] and len(loop.default_calls) == 1


def test_other_errors_go_to_default_handler(exits):
    calls, handler = exits
    loop = _Loop()
    handler(loop, {"message": "Task exception was never retrieved", "exception": ValueError("x")})
    assert calls == [] and len(loop.default_calls) == 1


def test_install_only_on_windows(monkeypatch):
    async def _probe():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop_guard.sys, "platform", "linux")
        assert loop_guard.install_loop_guard() is False
        assert loop.get_exception_handler() is None
        monkeypatch.setattr(loop_guard.sys, "platform", "win32")
        assert loop_guard.install_loop_guard() is True
        assert loop.get_exception_handler() is not None
    asyncio.run(_probe())
