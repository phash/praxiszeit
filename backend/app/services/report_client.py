"""Ausgehender Meldeweg der In-App-Meldung (#557, Protokoll mrd-report-1).

Zwei Transporte:

* ``mrd-report-1`` (``FEEDBACK_REPORT_KEY`` gesetzt): ``POST
  {FEEDBACK_REPORT_BASE_URL}/v1/reports`` mit den Feldern plus ``credential``.
  Einmaliger Ausweichversuch auf ``REPORT_FALLBACK_BASE`` NUR bei einem DNS-
  oder TLS-Handshake-Fehler, also ``httpx.ConnectError`` (nie bei HTTP-Status,
  Verbindungsabbruch, Lese-/Schreibfehler oder Timeout).
* ``legacy`` (kein Schlüssel): ``POST {FEEDBACK_SERVER_URL}/v1/bugs`` wie bisher,
  Host gegen ``updater._ALLOWED_UPDATE_HOSTS`` geprüft, ohne Ausweichhost.

``send_report`` wirft nie. Gesamtbudget ``REPORT_TIMEOUT_SECONDS`` als echte
Wanduhr-Frist über den ganzen Versand inklusive Ausweichversuch (Review F8/F11:
httpx-Timeouts gelten je Socket-Operation, ein langsamer Upload lief sonst
beliebig lange): der Versand läuft über ``httpx.AsyncClient`` unter
``anyio.fail_after``; bei Fristablauf wird die Anfrage abgebrochen. Ein 201 ist
endgültig — ist sein Body nicht lesbar (Abbruch, Timeout, Frist), gilt die
Meldung trotzdem als angenommen, ohne ``ref`` (Review F16, wie PZ-R14 im
C#-ReportSender), damit ein erneutes Senden keine Dublette erzeugt.
Protokolliert werden nur Statuscode, Host und Fehlerart — nie
Felder, Schlüssel oder Antworttext. Vertrag: pzweb
``docs/protocols/mrd-report-1/README.md``.
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import anyio
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
_UPDATE_HINT = "bitte PraxisZeit aktualisieren."
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


def _interpret(status: int, content: bytes | None, host: str) -> ReportResult:
    """``content`` None = Body nicht lesbar (nur der Status ist bekannt)."""
    try:
        body = json.loads(content) if content else None
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
    usable = isinstance(detail, str) and detail.strip() and not (key and key in detail)
    if status == 400:
        # Review F9 / README §3: Reaktion allein am Statuscode — 400 heißt, der
        # Server kennt das Protokoll nicht (mehr): „App-Update nötig“.
        detail = (f"{detail.strip()[:200]} – {_UPDATE_HINT}" if usable
                  else _STATUS_DETAIL[400])
    elif not usable:
        detail = _STATUS_DETAIL.get(status, _DEFAULT_DETAIL)
    return _fail(status, detail[:_DETAIL_MAX])


def _should_fall_back(exc: httpx.HTTPError) -> bool:
    """PZ-R7: nur DNS-/TLS-Handshake-Fehler — beide erscheinen als ConnectError.
    Ein TLS-Fehler beim Lesen/Schreiben (Body evtl. schon gesendet) zählt nicht."""
    return isinstance(exc, httpx.ConnectError) and is_dns_or_tls_error(exc)


def _transport() -> httpx.AsyncBaseTransport:
    """Naht für Tests (``httpx.MockTransport``)."""
    return httpx.AsyncHTTPTransport()


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
    """Meldung senden. Wirft nie; Ergebnis für den Router (Task 7).

    Synchron (der Router läuft im Threadpool); intern eine eigene Ereignisschleife,
    damit die Gesamtfrist die laufende Anfrage wirklich abbrechen kann."""
    try:
        return anyio.run(_send, fields, attachment)
    except Exception as exc:  # noqa: BLE001 — Meldeweg darf die App nie stören
        logger.warning("Report send failed unexpectedly (%s)", type(exc).__name__)
        return _fail(None, _UNREACHABLE)


async def _send(fields: dict[str, str], attachment) -> ReportResult:
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

    budget = REPORT_TIMEOUT_SECONDS
    deadline = anyio.current_time() + budget
    async with httpx.AsyncClient(
        transport=_transport(), timeout=httpx.Timeout(budget), follow_redirects=False,
    ) as client:
        resp = None
        host = ""
        try:
            with anyio.fail_after(budget):
                for index, url in enumerate(urls):
                    host = _host(url)
                    try:
                        request = client.build_request("POST", url, files=parts)
                        resp = await client.send(request, stream=True)
                        break
                    except httpx.HTTPError as exc:
                        dns_tls = _should_fall_back(exc)
                        logger.warning(
                            "Report to %s failed (%s%s)", host, type(exc).__name__,
                            ", dns/tls" if dns_tls else "",
                        )
                        if dns_tls and index + 1 < len(urls):
                            continue
                        return _fail(None, _UNREACHABLE)
        except TimeoutError:
            if resp is None:
                logger.warning(
                    "Report to %s failed (total budget of %ss exceeded)", host, budget)
                return _fail(None, _UNREACHABLE)
        if resp is None:
            return _fail(None, _UNREACHABLE)

        # Status steht fest. Den Body nur noch im Restbudget lesen; scheitert das,
        # entscheidet allein der Status (201 = angenommen, ohne ref).
        content = None
        try:
            with anyio.move_on_after(max(0.0, deadline - anyio.current_time())):
                content = await resp.aread()
        except httpx.HTTPError as exc:
            logger.warning(
                "Report to %s: response body unreadable (%s, status %s)",
                host, type(exc).__name__, resp.status_code,
            )
        finally:
            with anyio.CancelScope(shield=True):
                await resp.aclose()
        return _interpret(resp.status_code, content, host)
