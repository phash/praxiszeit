"""mrd-report-1-Client (#557, Task 6): Transport, Ausweichhost, Konfiguration.

Kein echter Netzaufruf: ``report_client._transport`` wird durch einen
``httpx.MockTransport`` mit Recorder ersetzt (``tests/report_transport_stub``).
"""
from __future__ import annotations

import logging
import socket
import ssl
import time
import warnings

import anyio
import httpx
import pytest

from app.config import Settings, settings
from app.services import report_client
from tests.report_transport_stub import install

KEY = "mrk_praxiszeit_Zufall123abc"
FIELDS = {
    "protocol": "mrd-report-1",
    "product": "praxiszeit",
    "install_id": "6f1c1c7e-4d0b-4c8e-9a51-0a8b2f9d3e11",
    "kind": "bug",
    "title": "Es hakt",
    "description": "Beim Stempeln passiert X",
    "app_version": "1.24.3",
    "os": "linux",
    "channel": "stable",
    "severity": "medium",
}
LEGACY_FIELDS = {
    "license_id": "beta",
    "title": "Es hakt",
    "description": "Beim Stempeln passiert X",
    "app_version": "1.24.3",
    "os": "linux",
    "severity": "medium",
}


def _resp(status, json_body=None, content=None):
    req = httpx.Request("POST", "https://report.mr-development.de/v1/reports")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=req)
    return httpx.Response(status, content=content or b"", request=req)


def _wrapped(cls, cause, msg="boom"):
    """httpx-Fehler mit Ursache wie in httpx/httpcore (``raise … from exc``)."""
    exc = cls(msg)
    exc.__cause__ = cause
    return exc


@pytest.fixture
def mrd(monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", KEY)
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_BASE_URL", "https://report.mr-development.de")


def _patch(monkeypatch, *outcomes):
    return install(monkeypatch, *outcomes)


# --- Transport mrd-report-1 ---------------------------------------------------

def test_201_returns_ref_and_id(monkeypatch, mrd):
    rec = _patch(monkeypatch, _resp(201, {"id": "abc-uuid", "ref": "praxiszeit-7", "status": "received"}))
    res = report_client.send_report(dict(FIELDS))
    assert res == report_client.ReportResult(
        ok=True, upstream_status=201, ref="praxiszeit-7", report_id="abc-uuid", detail=None
    )
    assert rec.calls[0]["url"] == "https://report.mr-development.de/v1/reports"
    assert report_client.current_transport() == "mrd-report-1"


def test_201_with_non_object_body_has_no_ref(monkeypatch, mrd):
    _patch(monkeypatch, _resp(201, ["x"]))
    res = report_client.send_report(dict(FIELDS))
    assert res.ok is True and res.ref is None and res.report_id is None


def test_sends_credential_protocol_and_all_fields_as_form_parts(monkeypatch, mrd):
    rec = _patch(monkeypatch, _resp(201, {"id": "i", "ref": "r"}))
    report_client.send_report(dict(FIELDS), ("screenshot.png", b"\x89PNG...", "image/png"))
    kw = rec.calls[0]["kwargs"]
    files = kw["files"]
    as_dict = {name: part for name, part in files}
    for name, value in FIELDS.items():
        assert as_dict[name] == (None, value)
    assert as_dict["credential"] == (None, KEY)
    assert as_dict["protocol"] == (None, "mrd-report-1")
    assert as_dict["attachment"] == ("screenshot.png", b"\x89PNG...", "image/png")


def test_dns_error_on_both_hosts_tries_each_once(monkeypatch, mrd):
    rec = _patch(
        monkeypatch,
        _wrapped(httpx.ConnectError, socket.gaierror(-2, "Name or service not known")),
        _wrapped(httpx.ConnectError, socket.gaierror(-2, "Name or service not known")),
    )
    res = report_client.send_report(dict(FIELDS))
    assert [c["url"] for c in rec.calls] == [
        "https://report.mr-development.de/v1/reports",
        "https://praxiszeit.mr-development.de/v1/reports",
    ]
    assert res.ok is False and res.upstream_status is None
    assert res.detail == "Meldeserver nicht erreichbar."


def test_tls_error_falls_back_once_and_succeeds(monkeypatch, mrd):
    rec = _patch(
        monkeypatch,
        _wrapped(httpx.ConnectError, ssl.SSLCertVerificationError("certificate verify failed")),
        _resp(201, {"id": "i2", "ref": "praxiszeit-8"}),
    )
    res = report_client.send_report(dict(FIELDS))
    assert len(rec.calls) == 2
    assert rec.calls[1]["url"] == "https://praxiszeit.mr-development.de/v1/reports"
    assert res.ok is True and res.ref == "praxiszeit-8"


# --- Gesamtbudget (Review F8/F11) und 201 mit unlesbarem Body (F16) ----------
# httpx-Timeouts gelten je Socket-Operation, nicht für die ganze Anfrage: ein
# langsamer Upload in vielen Stücken lief beliebig lange. Das Budget ist jetzt
# eine Wanduhr-Frist über den ganzen Versand inklusive Ausweichversuch.

BUDGET = 0.4


@pytest.fixture
def short_budget(monkeypatch):
    monkeypatch.setattr(report_client, "REPORT_TIMEOUT_SECONDS", BUDGET)


def _slow(seconds, then=None):
    async def handler(request):
        await anyio.sleep(seconds)
        if isinstance(then, BaseException):
            raise then
        return then if then is not None else _resp(201, {"id": "late", "ref": "late"})
    return handler


def _timed(fn):
    t0 = time.monotonic()
    res = fn()
    return res, time.monotonic() - t0


def test_slow_upstream_is_cut_at_the_total_budget(monkeypatch, mrd, short_budget):
    rec = _patch(monkeypatch, _slow(5.0))
    res, took = _timed(lambda: report_client.send_report(dict(FIELDS)))
    assert took < BUDGET + 1.0
    assert len(rec.calls) == 1
    assert (res.ok, res.upstream_status, res.detail) == (False, None, "Meldeserver nicht erreichbar.")


def test_total_budget_includes_the_fallback(monkeypatch, mrd, short_budget):
    dns = _wrapped(httpx.ConnectError, socket.gaierror(-2, "x"))
    rec = _patch(monkeypatch, _slow(BUDGET * 0.5, dns), _slow(5.0))
    res, took = _timed(lambda: report_client.send_report(dict(FIELDS)))
    assert len(rec.calls) == 2
    assert took < BUDGET + 1.0
    assert res.ok is False and res.upstream_status is None


def test_no_fallback_when_budget_is_used_up(monkeypatch, mrd, short_budget):
    dns = _wrapped(httpx.ConnectError, socket.gaierror(-2, "x"))
    rec = _patch(monkeypatch, _slow(BUDGET + 0.2, dns))
    res = report_client.send_report(dict(FIELDS))
    assert len(rec.calls) == 1 and res.ok is False and res.upstream_status is None


class _BrokenBody(httpx.AsyncByteStream):
    def __init__(self, exc=None, stall=None):
        self.exc, self.stall = exc, stall

    async def __aiter__(self):
        if self.stall:
            await anyio.sleep(self.stall)
        if self.exc:
            raise self.exc
        yield b'{"id": "x", "ref": "spaet"}'


@pytest.mark.parametrize("exc", [
    httpx.ReadTimeout("timed out"),
    httpx.RemoteProtocolError("peer closed connection"),
    httpx.ReadError("reset"),
])
def test_201_with_unreadable_body_counts_as_sent(monkeypatch, mrd, exc):
    # PZ-R14 wie im C#-ReportSender: der Server hat gespeichert, ein erneutes
    # Senden erzeugte eine Dublette.
    _patch(monkeypatch, httpx.Response(201, stream=_BrokenBody(exc=exc)))
    res = report_client.send_report(dict(FIELDS))
    assert (res.ok, res.upstream_status, res.ref, res.report_id) == (True, 201, None, None)


def test_201_with_body_stalling_past_the_budget_counts_as_sent(monkeypatch, mrd, short_budget):
    _patch(monkeypatch, httpx.Response(201, stream=_BrokenBody(stall=5.0)))
    res, took = _timed(lambda: report_client.send_report(dict(FIELDS)))
    assert took < BUDGET + 1.0
    assert (res.ok, res.upstream_status, res.ref) == (True, 201, None)


def test_non_201_with_unreadable_body_keeps_the_status(monkeypatch, mrd):
    _patch(monkeypatch, httpx.Response(429, stream=_BrokenBody(exc=httpx.ReadError("x"))))
    res = report_client.send_report(dict(FIELDS))
    assert (res.ok, res.upstream_status) == (False, 429)
    assert res.detail == "Zu viele Meldungen, bitte später erneut versuchen."


def test_tls_error_after_connect_never_falls_back(monkeypatch, mrd):
    # PZ-R7: Body schon gesendet — TLS-Fehler beim Lesen/Schreiben ist kein Handshake-Fehler
    for cls in (httpx.ReadError, httpx.WriteError):
        rec = _patch(monkeypatch, _wrapped(cls, ssl.SSLError(1, "bad record mac")))
        res = report_client.send_report(dict(FIELDS))
        assert len(rec.calls) == 1, cls.__name__
        assert res.ok is False and res.upstream_status is None


def test_no_fallback_when_base_is_the_fallback_host(monkeypatch, mrd):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_BASE_URL", "https://praxiszeit.mr-development.de")
    rec = _patch(monkeypatch, _wrapped(httpx.ConnectError, socket.gaierror(-2, "x")))
    res = report_client.send_report(dict(FIELDS))
    assert len(rec.calls) == 1 and res.ok is False


@pytest.mark.parametrize("outcome", [
    httpx.ReadTimeout("timed out"),
    httpx.ConnectTimeout("timed out"),
    httpx.RemoteProtocolError("connection reset"),
    _wrapped(httpx.ConnectError, ConnectionRefusedError(111, "refused")),
    _resp(503, content=b"<html>bad gateway</html>"),
])
def test_timeout_and_http_status_never_fall_back(monkeypatch, mrd, outcome):
    rec = _patch(monkeypatch, outcome)
    res = report_client.send_report(dict(FIELDS))
    assert len(rec.calls) == 1
    assert res.ok is False
    if isinstance(outcome, httpx.Response):
        assert res.upstream_status == 503
        assert res.detail == "Meldeserver-Fehler, bitte später erneut versuchen."
    else:
        assert res.upstream_status is None
        assert res.detail == "Meldeserver nicht erreichbar."


@pytest.mark.parametrize("body", [
    {"detail": "Unbekanntes Protokoll"},
    {"detail": "irgendetwas anderes"},
    None,
])
def test_400_always_asks_for_an_app_update(monkeypatch, mrd, body):
    # Review F9 / README §3: „Programmlogik entscheidet allein am Statuscode“ —
    # 400 = Server kennt mrd-report-1 nicht (mehr) -> „App-Update nötig“.
    _patch(monkeypatch, _resp(400, body) if body is not None else _resp(400, content=b"<html>"))
    res = report_client.send_report(dict(FIELDS))
    assert (res.ok, res.upstream_status) == (False, 400)
    assert "bitte PraxisZeit aktualisieren" in res.detail
    if body and body["detail"] == "Unbekanntes Protokoll":
        assert res.detail.startswith("Unbekanntes Protokoll")


def test_status_mapping_uses_detail_when_string(monkeypatch, mrd):
    _patch(monkeypatch, _resp(422, {"detail": "Feld 'title' ist zu lang (max. 200)"}))
    res = report_client.send_report(dict(FIELDS))
    assert (res.ok, res.upstream_status, res.detail) == (False, 422, "Feld 'title' ist zu lang (max. 200)")

    _patch(monkeypatch, _resp(413))
    res = report_client.send_report(dict(FIELDS))
    assert (res.upstream_status, res.detail) == (413, "Anhang zu groß.")

    _patch(monkeypatch, _resp(422, {"detail": "x" * 500}))
    assert len(report_client.send_report(dict(FIELDS)).detail) == 300


@pytest.mark.parametrize("status,text", [
    (400, "Meldeprotokoll vom Server nicht unterstützt – bitte PraxisZeit aktualisieren."),
    (403, "Meldung abgelehnt (Meldeschlüssel, Produkt oder Installation gesperrt)."),
    (413, "Anhang zu groß."),
    (422, "Meldung vom Server abgelehnt."),
    (429, "Zu viele Meldungen, bitte später erneut versuchen."),
    (507, "Meldeserver-Fehler, bitte später erneut versuchen."),
    (302, "Meldeserver-Fehler, bitte später erneut versuchen."),
])
def test_status_defaults_without_string_detail(monkeypatch, mrd, status, text):
    # detail fehlt bzw. ist kein String (FastAPI-422-Liste)
    _patch(monkeypatch, _resp(status, {"detail": [{"loc": ["x"]}]}))
    res = report_client.send_report(dict(FIELDS))
    assert (res.ok, res.upstream_status, res.detail) == (False, status, text)


def test_unexpected_exception_never_raises(monkeypatch, mrd):
    _patch(monkeypatch, RuntimeError("kaputt"))
    res = report_client.send_report(dict(FIELDS))
    assert res.ok is False and res.upstream_status is None
    assert isinstance(res.internal_error, RuntimeError)  # D7: Router protokolliert ihn


def test_network_failure_is_not_marked_internal(monkeypatch, mrd):
    _patch(monkeypatch, httpx.ConnectTimeout("t"))
    res = report_client.send_report(dict(FIELDS))
    assert res.ok is False and res.internal_error is None


# --- Transport legacy ---------------------------------------------------------

def test_empty_key_uses_legacy_bugs_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    monkeypatch.setattr(settings, "FEEDBACK_SERVER_URL", "https://praxiszeit.mr-development.de")
    assert report_client.current_transport() == "legacy"
    rec = _patch(monkeypatch, _resp(201, {"id": "legacy-id"}))
    res = report_client.send_report(dict(LEGACY_FIELDS))
    assert len(rec.calls) == 1
    assert rec.calls[0]["url"].endswith("/v1/bugs")
    assert rec.calls[0]["url"] == "https://praxiszeit.mr-development.de/v1/bugs"
    names = [name for name, _ in rec.calls[0]["kwargs"]["files"]]
    assert "credential" not in names and "protocol" not in names
    assert res.ok is True and res.report_id == "legacy-id" and res.ref is None


def test_legacy_never_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    rec = _patch(monkeypatch, _wrapped(httpx.ConnectError, socket.gaierror(-2, "x")))
    res = report_client.send_report(dict(LEGACY_FIELDS))
    assert len(rec.calls) == 1 and res.ok is False and res.upstream_status is None


def test_legacy_host_outside_update_allowlist_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    monkeypatch.setattr(settings, "FEEDBACK_SERVER_URL", "https://evil.example.com")
    rec = _patch(monkeypatch, _resp(201, {"id": "x"}))
    res = report_client.send_report(dict(LEGACY_FIELDS))
    assert rec.calls == [] and res.ok is False and res.upstream_status is None


def test_report_base_outside_allowlist_is_refused_at_send(monkeypatch, mrd):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_BASE_URL", "https://evil.example.com")
    rec = _patch(monkeypatch, _resp(201, {"id": "x"}))
    res = report_client.send_report(dict(FIELDS))
    assert rec.calls == [] and res.ok is False


# --- Schlüssel nie in Logs ----------------------------------------------------

def test_key_never_logged(monkeypatch, mrd, caplog):
    caplog.set_level(logging.DEBUG)
    # Ausnahmetexte, die den Schlüssel enthalten könnten, dürfen nicht durchsickern
    _patch(
        monkeypatch,
        _wrapped(httpx.ConnectError, socket.gaierror(-2, f"bad {KEY}"), msg=f"fail {KEY}"),
        _resp(403, {"detail": f"Meldeschlüssel ungültig {KEY}"}),
    )
    res = report_client.send_report(dict(FIELDS))
    _patch(monkeypatch, httpx.ReadTimeout(f"timeout {KEY}"))
    res2 = report_client.send_report(dict(FIELDS))
    _patch(monkeypatch, RuntimeError(f"kaputt {KEY}"))
    res3 = report_client.send_report(dict(FIELDS))
    assert caplog.records, "Fehlschläge sollen protokolliert werden (Status/Host)"
    assert "mrk_" not in caplog.text
    for r in (res2, res3):
        assert "mrk_" not in (r.detail or "")
    assert res.upstream_status == 403
    # Server-detail darf durchgereicht werden, ein Schlüssel darin nicht
    assert "mrk_" not in (res.detail or "")
    assert "mrk_" not in repr(res)


# --- is_dns_or_tls_error ------------------------------------------------------

def test_is_dns_or_tls_error_walks_chain():
    assert report_client.is_dns_or_tls_error(socket.gaierror(-2, "x"))
    assert report_client.is_dns_or_tls_error(ssl.SSLError(1, "x"))
    assert report_client.is_dns_or_tls_error(_wrapped(httpx.ConnectError, ssl.SSLCertVerificationError("x")))
    inner = httpx.ConnectError("mid")
    inner.__context__ = socket.gaierror(-3, "temp")
    assert report_client.is_dns_or_tls_error(_wrapped(httpx.ConnectError, inner))
    assert not report_client.is_dns_or_tls_error(httpx.ReadTimeout("x"))
    assert not report_client.is_dns_or_tls_error(_wrapped(httpx.ConnectError, ConnectionRefusedError()))
    # Zyklus terminiert
    a = httpx.ConnectError("a")
    b = httpx.ConnectError("b")
    a.__cause__, b.__cause__ = b, a
    assert not report_client.is_dns_or_tls_error(a)


# --- Konfiguration ------------------------------------------------------------

_BASE_ENV = {
    "SECRET_KEY": "a1b2c3d4" * 8,
    "ADMIN_EMAIL": "ci@example.invalid",
    "ADMIN_PASSWORD": "LocalCiDummy2025X",
}


def _settings(**kw):
    return Settings(_env_file=None, **_BASE_ENV, **kw)


def test_defaults():
    s = _settings()
    assert s.FEEDBACK_REPORT_KEY == ""
    assert s.FEEDBACK_REPORT_BASE_URL == "https://report.mr-development.de"
    from app.config import REPORT_ALLOWED_HOSTS
    assert REPORT_ALLOWED_HOSTS == frozenset({"report.mr-development.de", "praxiszeit.mr-development.de"})
    assert report_client.REPORT_FALLBACK_BASE == "https://praxiszeit.mr-development.de"
    assert report_client.REPORT_TIMEOUT_SECONDS == 15.0


@pytest.mark.parametrize("url", [
    "https://evil.example.com",
    "http://report.mr-development.de",
    "https://report.mr-development.de/v1",
    "https://report.mr-development.de?x=1",
    "https://report.mr-development.de#f",
    "https://report.mr-development.de:8443",
    "https://user@report.mr-development.de",
    "https://report.mr-development.de.evil.com",
])
def test_base_url_validator_rejects_foreign_host_and_path(url):
    with pytest.raises(ValueError):
        _settings(FEEDBACK_REPORT_BASE_URL=url)


def test_base_url_validator_accepts_both_hosts():
    assert _settings(FEEDBACK_REPORT_BASE_URL="https://report.mr-development.de/").FEEDBACK_REPORT_BASE_URL \
        == "https://report.mr-development.de"
    assert _settings(FEEDBACK_REPORT_BASE_URL="https://praxiszeit.mr-development.de").FEEDBACK_REPORT_BASE_URL \
        == "https://praxiszeit.mr-development.de"


@pytest.mark.parametrize("bad", [
    "geheim",
    "mrk_x_abc",                     # Slug zu kurz
    "mrk_PraxisZeit_abc",            # Großbuchstaben im Slug
    "mrk_praxiszeit_",               # kein Zufallsteil
    "mrk_praxiszeit_ab cd",          # Leerzeichen
    "mrk_praxiszeit_" + "a" * 120,   # > 128 Zeichen
])
def test_invalid_key_is_ignored_with_warning(bad):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s = _settings(FEEDBACK_REPORT_KEY=bad)
    assert s.FEEDBACK_REPORT_KEY == ""
    msgs = [str(w.message) for w in caught]
    assert any("FEEDBACK_REPORT_KEY" in m for m in msgs)
    assert all(bad not in m for m in msgs)


def test_valid_key_is_stripped_and_kept():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        s = _settings(FEEDBACK_REPORT_KEY=f"  {KEY}\n")
    assert s.FEEDBACK_REPORT_KEY == KEY
    assert _settings(FEEDBACK_REPORT_KEY="   ").FEEDBACK_REPORT_KEY == ""


def test_toml_feedback_section_maps_to_env():
    from app.config import _TOML_KEY_MAP
    assert _TOML_KEY_MAP[("feedback", "report_key")] == "FEEDBACK_REPORT_KEY"
    assert _TOML_KEY_MAP[("feedback", "report_base_url")] == "FEEDBACK_REPORT_BASE_URL"


def test_send_honours_https_proxy_from_environment(monkeypatch):
    """#557 D2: ein eigener Transport schaltet httpx' Umgebungs-Proxy ab
    (``trust_env`` gilt nur ohne ``transport``). Praxisnetze mit Pflicht-Proxy
    kämen sonst nicht mehr raus. Kein Netzaufruf: ``send`` bricht vorher ab."""
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", KEY)
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_BASE_URL", "https://report.mr-development.de")
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.praxis.invalid:3128")
    monkeypatch.setenv("https_proxy", "http://proxy.praxis.invalid:3128")
    seen = []

    class Probe(httpx.AsyncClient):
        async def send(self, request, **kwargs):
            seen.append(self._transport_for_url(request.url))
            raise httpx.ReadTimeout("stop", request=request)

    monkeypatch.setattr(report_client.httpx, "AsyncClient", Probe)
    result = report_client.send_report(dict(FIELDS))

    assert result.ok is False
    assert len(seen) == 1
    pool = getattr(seen[0], "_pool", None)
    assert type(pool).__name__ == "AsyncHTTPProxy"
    assert pool._proxy_url.host == b"proxy.praxis.invalid"
