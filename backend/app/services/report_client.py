"""Ausgehender Meldeweg der In-App-Meldung (#557, Protokoll mrd-report-1).

Zwei Transporte:

* ``mrd-report-1`` (``FEEDBACK_REPORT_KEY`` gesetzt): ``POST
  {FEEDBACK_REPORT_BASE_URL}/v1/reports`` mit den Feldern plus ``credential``.
  Einmaliger Ausweichversuch auf ``REPORT_FALLBACK_BASE`` NUR bei einem DNS-
  oder TLS-Handshake-Fehler, also ``httpx.ConnectError`` (nie bei HTTP-Status,
  Verbindungsabbruch, Lese-/Schreibfehler oder Timeout).
* ``legacy`` (kein Schlüssel): ``POST {FEEDBACK_SERVER_URL}/v1/bugs`` wie bisher,
  Host gegen ``updater._ALLOWED_UPDATE_HOSTS`` geprüft, ohne Ausweichhost.

``send_report`` wirft nie; Gesamtbudget ``REPORT_TIMEOUT_SECONDS`` inklusive
Ausweichversuch, je Versuch als ``httpx.Timeout`` mit aus dem Restbudget
aufgeteilten Phasen (connect + write + read ≤ Rest). Protokolliert werden nur Statuscode, Host und Fehlerart — nie
Felder, Schlüssel oder Antworttext. Vertrag: pzweb
``docs/protocols/mrd-report-1/README.md``.
"""
from __future__ import annotations

import logging
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

from app.config import REPORT_ALLOWED_HOSTS, settings
from app.core.updater import _ALLOWED_UPDATE_HOSTS

logger = logging.getLogger(__name__)

REPORT_FALLBACK_BASE = "https://praxiszeit.mr-development.de"
REPORT_TIMEOUT_SECONDS = 15.0

_DETAIL_MAX = 300
_UNREACHABLE = "Meldeserver nicht erreichbar."
_MISCONFIGURED = "Meldeserver ist nicht korrekt konfiguriert."
_DEFAULT_DETAIL = "Meldeserver-Fehler, bitte später erneut versuchen."
_STATUS_DETAIL = {
    400: "Meldeprotokoll vom Server nicht unterstützt – bitte PraxisZeit aktualisieren.",
    403: "Meldung abgelehnt (Meldeschlüssel, Produkt oder Installation gesperrt).",
    413: "Anhang zu groß.",
    422: "Meldung vom Server abgelehnt.",
    429: "Zu viele Meldungen, bitte später erneut versuchen.",
}


@dataclass(frozen=True)
class ReportResult:
    ok: bool
    upstream_status: int | None
    ref: str | None
    report_id: str | None
    detail: str | None


def current_transport() -> Literal["mrd-report-1", "legacy"]:
    return "mrd-report-1" if settings.FEEDBACK_REPORT_KEY else "legacy"


def is_dns_or_tls_error(exc: BaseException) -> bool:
    """True, wenn in der Ursachenkette (``__cause__``/``__context__``) ein
    Namensauflösungs- oder TLS-Fehler steckt (httpx verpackt sie in ConnectError)."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, (socket.gaierror, ssl.SSLError)):
            return True
        for nxt in (cur.__cause__, cur.__context__):
            if nxt is not None:
                stack.append(nxt)
    return False


def _host(url: str) -> str:
    return urlparse(url).hostname or ""


def _fail(status: int | None, detail: str) -> ReportResult:
    return ReportResult(ok=False, upstream_status=status, ref=None, report_id=None, detail=detail)


def _str_or_none(value) -> str | None:
    return value if isinstance(value, str) else None


def _interpret(resp: httpx.Response, host: str) -> ReportResult:
    status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = None
    if status == 201:
        if not isinstance(body, dict):
            body = {}
        return ReportResult(
            ok=True, upstream_status=201,
            ref=_str_or_none(body.get("ref")), report_id=_str_or_none(body.get("id")),
            detail=None,
        )
    logger.warning("Report to %s rejected with status %s", host, status)
    detail = body.get("detail") if isinstance(body, dict) else None
    key = settings.FEEDBACK_REPORT_KEY
    if not isinstance(detail, str) or not detail.strip() or (key and key in detail):
        detail = _STATUS_DETAIL.get(status, _DEFAULT_DETAIL)
    return _fail(status, detail[:_DETAIL_MAX])


def _phased_timeout(remaining: float) -> httpx.Timeout:
    """PZ-R8: Phasen aus dem Restbudget teilen, damit connect + write + read
    zusammen nie über das Restbudget hinausgehen (Pool = Connect)."""
    connect = remaining * 0.4
    return httpx.Timeout(connect=connect, write=remaining * 0.2, read=remaining * 0.4, pool=connect)


def _should_fall_back(exc: httpx.HTTPError) -> bool:
    """PZ-R7: nur DNS-/TLS-Handshake-Fehler — beide erscheinen als ConnectError.
    Ein TLS-Fehler beim Lesen/Schreiben (Body evtl. schon gesendet) zählt nicht."""
    return isinstance(exc, httpx.ConnectError) and is_dns_or_tls_error(exc)


def _post(url: str, files: list, timeout: httpx.Timeout) -> httpx.Response:
    return httpx.post(url, files=files, timeout=timeout, follow_redirects=False)


def _targets() -> tuple[list[str], str] | None:
    """(Ziel-URLs der Reihe nach, Endpunkt-Pfad) oder None bei Fehlkonfiguration."""
    if current_transport() == "legacy":
        base = settings.FEEDBACK_SERVER_URL.rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_UPDATE_HOSTS:
            return None
        return [f"{base}/v1/bugs"], "legacy"
    base = settings.FEEDBACK_REPORT_BASE_URL.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname not in REPORT_ALLOWED_HOSTS:
        return None
    urls = [f"{base}/v1/reports"]
    if parsed.hostname != _host(REPORT_FALLBACK_BASE):
        urls.append(f"{REPORT_FALLBACK_BASE}/v1/reports")
    return urls, "mrd-report-1"


def send_report(
    fields: dict[str, str], attachment: tuple[str, bytes, str] | None = None
) -> ReportResult:
    """Meldung senden. Wirft nie; Ergebnis für den Router (Task 7)."""
    try:
        return _send(fields, attachment)
    except Exception as exc:  # noqa: BLE001 — Meldeweg darf die App nie stören
        logger.warning("Report send failed unexpectedly (%s)", type(exc).__name__)
        return _fail(None, _UNREACHABLE)


def _send(fields: dict[str, str], attachment) -> ReportResult:
    targets = _targets()
    if targets is None:
        logger.warning("Report target rejected: host not in allowlist")
        return _fail(None, _MISCONFIGURED)
    urls, transport = targets

    parts = [(name, (None, value)) for name, value in fields.items()]
    if transport == "mrd-report-1":
        parts = [p for p in parts if p[0] != "credential"]
        parts.append(("credential", (None, settings.FEEDBACK_REPORT_KEY)))
    if attachment is not None:
        parts.append(("attachment", attachment))

    deadline = time.monotonic() + REPORT_TIMEOUT_SECONDS
    for index, url in enumerate(urls):
        host = _host(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            resp = _post(url, parts, _phased_timeout(remaining))
        except httpx.HTTPError as exc:
            dns_tls = _should_fall_back(exc)
            logger.warning(
                "Report to %s failed (%s%s)", host, type(exc).__name__,
                ", dns/tls" if dns_tls else "",
            )
            if dns_tls and index + 1 < len(urls):
                continue
            return _fail(None, _UNREACHABLE)
        return _interpret(resp, host)
    return _fail(None, _UNREACHABLE)
