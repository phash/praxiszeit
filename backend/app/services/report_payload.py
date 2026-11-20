"""Payload builder for the mrd-report-1 client (#557): context block, limits, fields."""
from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.core import license as license_module
from app.core.deployment import is_saas
from app.core.report_sanitize_pz import sanitize_praxiszeit_text
from app.core.updater import APP_VERSION
from app.models.error_log import ErrorLog
from app.services.error_log_service import _scope_to_tenant, _scrub_path
from app.services.report_log_extract import MAX_EXTRACT_LINES, trim_extract
from app.services.report_install_id import get_or_create_install_id

PRODUCT = "praxiszeit"
PRODUCT_NAME = "PraxisZeit"
BOARD_URL = "https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit"
TITLE_MAX = 200
DESCRIPTION_MAX = 20000
USER_TEXT_MAX = 4000
MAX_DETAIL_LINES = 60
SERVER_ERROR_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True)
class ServerFields:
    app_version: str
    os: str
    channel: str
    system: str
    install_type: str
    install_id: str
    license_id: str | None


@dataclass(frozen=True)
class ServerErrorHint:
    status: int
    method: str
    path: str


@dataclass(frozen=True)
class ErrorContext:
    line: str
    fingerprint: str | None
    detail_lines: list[str]


@dataclass(frozen=True)
class ReportPreview:
    title: str
    description: str
    log_line_count: int
    truncated: bool


def collect_server_fields() -> ServerFields:
    if settings.ENVIRONMENT == "development":
        channel = "dev"
    elif settings.BETA_MODE:
        channel = "beta"
    else:
        channel = "stable"
    lic = license_module.get_current_license()
    license_id = (getattr(lic, "customer_id", "") if lic else "") or None
    if not license_id and settings.BETA_MODE:
        license_id = "beta"
    return ServerFields(
        app_version=APP_VERSION,
        os=platform.system().lower()[:32],
        channel=channel,
        system=f"{platform.system()} {platform.release()}/{platform.machine()}",
        # Protokoll §7: docker|native|desktop|saas (Review F22)
        install_type="saas" if is_saas() else ("native" if settings.SERVE_FRONTEND else "docker"),
        install_id=get_or_create_install_id(),
        license_id=license_id,
    )


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def resolve_error_context(
    db: Session, tenant_id: UUID | None, *, error_log_id: UUID | None,
    server_error: ServerErrorHint | None, now: datetime,
) -> ErrorContext | None:
    row = None
    if error_log_id is not None:
        # Same scope as the Fehler-Monitoring list: None = on-prem (no filter),
        # tenant id = own rows plus NULL-tenant infrastructure rows.
        row = (
            _scope_to_tenant(db.query(ErrorLog), tenant_id)
            .filter(ErrorLog.id == error_log_id)
            .first()
        )
        if row is None:
            raise LookupError("error log not found")
    elif server_error is not None:
        path = _scrub_path(server_error.path)
        row = (
            db.query(ErrorLog)
            .filter(
                ErrorLog.tenant_id == tenant_id,
                ErrorLog.method == server_error.method,
                ErrorLog.status_code == server_error.status,
                ErrorLog.path == path,
                ErrorLog.last_seen >= _utc(now) - SERVER_ERROR_WINDOW,
            )
            .order_by(ErrorLog.last_seen.desc())
            .first()
        )
        if row is None:
            return ErrorContext(
                f"HTTP {server_error.status} {server_error.method} {path}", None, [])
    else:
        return None
    msg = (row.message or "").strip()
    first = msg.splitlines()[0] if msg else ""
    # Review F14: Zeilen ohne HTTP-Bezug (DBErrorHandler, Integritätsprüfung)
    # nennen den Logger statt „HTTP None None None“.
    http = " ".join(str(v) for v in (row.status_code, row.method, row.path) if v)
    origin = f"HTTP {http}" if http else (row.logger or "-")
    line = (
        f"{row.level} {origin} — {first} "
        f"({row.count}x, zuletzt {_utc(row.last_seen):%Y-%m-%dT%H:%M:%SZ})"
    )
    tb = (row.traceback or "").splitlines()[-MAX_DETAIL_LINES:]
    return ErrorContext(line, (row.fingerprint or None) and row.fingerprint[:64], tb)


KIND_LABELS = {"feedback": "Feedback", "crash": "Programmfehler (vom Programm vorgeschlagen)"}


def legacy_kind_label(transport: str, kind: str) -> str | None:
    """Review F21: ``/v1/bugs`` hat kein Feld ``kind`` (speichert alles als Bug).
    Auf dem Altweg steht die Art deshalb als Zeile im Kontextblock — Vorschau =
    Gesendetes; „Fehler“ (bug) braucht keine Zeile."""
    return KIND_LABELS.get(kind) if transport == "legacy" else None


def compose_description(
    user_text: str, *, server: ServerFields, now_utc: datetime,
    error_line: str | None, log_lines: list[str] | None, kind_label: str | None = None,
) -> str:
    parts = [
        f"{user_text}\n\n---- Kontext (automatisch) ----",
        f"Produkt: {PRODUCT_NAME} {server.app_version} ({server.channel})",
        f"System: {server.system}, Installationsart: {server.install_type}",
        f"Zeit: {_utc(now_utc):%Y-%m-%dT%H:%M:%SZ}",
    ]
    if kind_label:
        parts.append(f"Meldungsart: {kind_label}")
    if error_line:
        parts.append(f"Fehler: {error_line}")
    if log_lines is not None:
        parts.append(f"Protokoll (bereinigt, letzte {len(log_lines)} Zeilen):")
        parts.extend(log_lines)
    return "\n".join(parts)


def build_preview(
    *, title: str, user_text: str, server: ServerFields, now_utc: datetime,
    error: ErrorContext | None, log_lines: list[str] | None, kind_label: str | None = None,
) -> ReportPreview:
    detail = list(error.detail_lines) if error is not None else []
    extract = list(log_lines) if log_lines is not None else None
    has_block = bool(detail) or extract is not None
    if extract is not None:
        # Ruling PZ-R5: whole block <= MAX_EXTRACT_LINES, newest extract lines win
        # (section-aware, Review F18: headers and newest error rows stay).
        room = max(0, MAX_EXTRACT_LINES - len(detail))
        extract = trim_extract(extract, room)
    error_line = error.line if error else None

    def render(det, ext):
        ls = (det + (ext or [])) if has_block else None
        return sanitize_praxiszeit_text(compose_description(
            user_text, server=server, now_utc=now_utc, error_line=error_line, log_lines=ls,
            kind_label=kind_label))

    detail = detail[-MAX_EXTRACT_LINES:]
    description = render(detail, extract)
    truncated = False
    while len(description) > DESCRIPTION_MAX and (extract or detail):
        if extract:
            extract = trim_extract(extract, len(extract) - max(1, len(extract) // 4))
        else:
            detail = detail[max(1, len(detail) // 4):]
        truncated = True
        description = render(detail, extract)
    t = sanitize_praxiszeit_text(title.strip())
    if len(t) > TITLE_MAX:
        t = sanitize_praxiszeit_text(t[:TITLE_MAX - 1] + "…")
        t = t[:TITLE_MAX]
    count = len(detail) + len(extract or []) if has_block else 0
    return ReportPreview(t, description, count, truncated)


def build_fields(
    *, transport: Literal["mrd-report-1", "legacy"], kind: str, title: str, description: str,
    severity: str, contact_email: str | None, error_fingerprint: str | None,
    server: ServerFields, include_license: bool = True,
) -> dict[str, str]:
    """``include_license=False`` für die Vorschau (Review F15): die Lizenzkennung
    (``customer_id``, auf dem Altweg das Zugangsdatum) geht nie ans Frontend und
    nie in eine gespeicherte Datei; ``/send`` ergänzt sie serverseitig."""
    if transport == "legacy":
        fields = {
            "title": title,
            "description": description,
            "app_version": server.app_version,
            "os": server.os,
            "severity": severity,
        }
        if include_license:
            fields = {"license_id": server.license_id or "", **fields}
        return fields
    fields = {
        "protocol": "mrd-report-1",
        "product": PRODUCT,
        "install_id": server.install_id,
        "kind": kind,
        "title": title,
        "description": description,
        "app_version": server.app_version,
        "os": server.os,
        "channel": server.channel,
        "severity": severity,
    }
    if include_license and server.license_id:
        fields["license_id"] = server.license_id
    if contact_email:
        fields["contact_email"] = contact_email
    if error_fingerprint:
        fields["error_fingerprint"] = error_fingerprint
    return fields
