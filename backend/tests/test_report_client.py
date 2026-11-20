"""mrd-report-1-Client (#557, Task 6): Transport, Ausweichhost, Konfiguration.

Kein echter Netzaufruf: ``report_client.httpx.post`` wird durch einen
Recorder ersetzt (Muster ``test_feedback._Recorder``).
"""
from __future__ import annotations

import logging
import socket
import ssl
import warnings

import httpx
import pytest

from app.config import Settings, settings
from app.services import report_client

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


def _phase_sum(t):
    return t.connect + t.write + t.read


def _wrapped(cls, cause, msg="boom"):
    """httpx-Fehler mit Ursache wie in httpx/httpcore (``raise … from exc``)."""
    exc = cls(msg)
    exc.__cause__ = cause
    return exc


class _Recorder:
    """Nimmt httpx.post-Aufrufe auf; ``outcomes`` = Antworten oder Ausnahmen der Reihe nach."""

    def __init__(self, *outcomes):
        self.calls = []
        self._outcomes = list(outcomes)

    def __call__(self, url, *args, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        out = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(out, BaseException):
            raise out
        return out


@pytest.fixture
def mrd(monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", KEY)
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_BASE_URL", "https://report.mr-development.de")


def _patch(monkeypatch, *outcomes):
    rec = _Recorder(*outcomes)
    monkeypatch.setattr(report_client.httpx, "post", rec)
    return rec


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
    assert kw["follow_redirects"] is False
    assert isinstance(kw["timeout"], httpx.Timeout)
    assert 0 < _phase_sum(kw["timeout"]) <= report_client.REPORT_TIMEOUT_SECONDS


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
    # Restbudget, nie mehr als das Gesamtbudget
    assert _phase_sum(rec.calls[1]["kwargs"]["timeout"]) <= report_client.REPORT_TIMEOUT_SECONDS
    assert res.ok is True and res.ref == "praxiszeit-8"


class _Clock:
    """Ersetzt ``report_client.time``; jeder httpx.post-Aufruf verbraucht ``step`` Sekunden."""

    def __init__(self, step):
        self.now = 1000.0
        self.step = step

    def monotonic(self):
        return self.now


def test_phased_timeout_sums_within_total_and_remaining_budget(monkeypatch, mrd):
    clock = _Clock(step=4.0)
    monkeypatch.setattr(report_client, "time", clock)
    seen = []

    def post(url, *args, **kwargs):
        seen.append((url, kwargs["timeout"]))
        clock.now += clock.step
        if len(seen) == 1:
            raise _wrapped(httpx.ConnectError, socket.gaierror(-2, "x"))
        return _resp(201, {"id": "i", "ref": "r"})

    monkeypatch.setattr(report_client.httpx, "post", post)
    assert report_client.send_report(dict(FIELDS)).ok is True
    first, second = seen[0][1], seen[1][1]
    assert _phase_sum(first) <= report_client.REPORT_TIMEOUT_SECONDS + 1e-9
    assert _phase_sum(first) > report_client.REPORT_TIMEOUT_SECONDS - 0.5
    assert _phase_sum(second) <= report_client.REPORT_TIMEOUT_SECONDS - 4.0 + 1e-9
    for t in (first, second):
        assert t.pool == t.connect and min(t.connect, t.write, t.read) > 0


def test_no_fallback_when_budget_is_used_up(monkeypatch, mrd):
    clock = _Clock(step=15.0)
    monkeypatch.setattr(report_client, "time", clock)
    calls = []

    def post(url, *args, **kwargs):
        calls.append(url)
        clock.now += clock.step
        raise _wrapped(httpx.ConnectError, socket.gaierror(-2, "x"))

    monkeypatch.setattr(report_client.httpx, "post", post)
    res = report_client.send_report(dict(FIELDS))
    assert len(calls) == 1 and res.ok is False and res.upstream_status is None


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
