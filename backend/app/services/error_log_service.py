"""
Error logging service: captures, deduplicates, and stores application errors.
Uses SHA256 fingerprinting to aggregate repeated errors.
"""
import hashlib
import logging
import re
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.error_log import ErrorLog
from app.database import set_superadmin_context

# DSGVO F-007: Regex patterns for PII scrubbing
_UUID_RE = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')

def _scrub_pii(text: str) -> str:
    """Replace UUIDs and email addresses in log messages with placeholders."""
    if not text:
        return text
    text = _UUID_RE.sub('<uuid>', text)
    text = _EMAIL_RE.sub('<email>', text)
    return text


def exception_summary(exc: BaseException) -> str:
    """Audit 2026-11-07 (S2-1): Meldung einer unbehandelten Ausnahme fuer
    ``error_logs`` — nur Typ und, bei Datenbankfehlern, SQLSTATE und Name der
    verletzten Bedingung. Nie ``str(exc)``: das enthielt bei einem
    ``DBAPIError`` das Statement mit allen Werten und PostgreSQLs
    ``DETAIL: Key (…)=(…)``, bei anderen Ausnahmen beliebige Eingaben."""
    name = type(exc).__name__
    orig = getattr(exc, "orig", None)
    if orig is None:
        return name
    parts = []
    code = getattr(orig, "pgcode", None)
    if code:
        parts.append(f"SQLSTATE {code}")
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag is not None else None
    if constraint:
        parts.append(f"constraint {constraint}")
    table = getattr(diag, "table_name", None) if diag is not None else None
    if table:
        parts.append(f"table {table}")
    inner = type(orig).__name__
    return f"{name} ({inner}{': ' + ', '.join(parts) if parts else ''})"


def exception_frames(exc: BaseException) -> str:
    """S2-1: Stapel der Ausnahme OHNE ihre Meldung (Dateien, Zeilen, Code) plus
    ``exception_summary`` — ``traceback.format_exc()`` haengt die volle
    Meldung (mit Werten) an."""
    frames = "".join(traceback.format_tb(exc.__traceback__))
    return f"{frames}{exception_summary(exc)}"


def _is_db_exception(exc: Optional[BaseException]) -> bool:
    """Datenbankfehler (SQLAlchemy ``DBAPIError`` oder Treiberfehler mit
    ``pgcode``) irgendwo in der Kette ``exc → __cause__/__context__``."""
    from sqlalchemy.exc import DBAPIError
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, DBAPIError) or hasattr(exc, "pgcode"):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


class DBErrorRedactionFilter(logging.Filter):
    """Audit 2026-11-07 (S2-1) Fix-Runde: Datenbankfehler in Container-Log und
    ``logs/praxiszeit.log`` ohne Werte.

    Eine an uvicorn weitergereichte Ausnahme („Exception in ASGI application")
    und Log-Aufrufe mit der Ausnahme als Argument schrieben ``str(exc)`` —
    bei einem ``DBAPIError`` PostgreSQLs ``DETAIL: Key (…)=(…)``. Der Filter
    ersetzt den Traceback-Text durch ``exception_frames`` (Stapel + Typ,
    SQLSTATE, Bedingung) und Ausnahme-Argumente durch ``exception_summary``.
    Andere Ausnahmen bleiben unveraendert. Haengt an den HANDLERN
    (``install_db_error_redaction``) — ein Logger-Filter saehe weitergereichte
    Records von Kind-Loggern nicht."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None and _is_db_exception(exc):
            record.exc_text = "Traceback (most recent call last):\n" + exception_frames(exc)
        if isinstance(record.msg, BaseException) and _is_db_exception(record.msg):
            record.msg = exception_summary(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    exception_summary(a) if isinstance(a, BaseException) and _is_db_exception(a) else a
                    for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: exception_summary(v) if isinstance(v, BaseException) and _is_db_exception(v) else v
                    for k, v in record.args.items()
                }
        return True


_REDACTION_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "app")


def install_db_error_redaction(logger_names=_REDACTION_LOGGERS) -> int:
    """Haengt ``DBErrorRedactionFilter`` an jeden Handler der genannten Logger
    (idempotent). uvicorn richtet seine Handler vor dem Import der App ein,
    ``app.main`` ruft das deshalb beim Import auf. Gibt die Zahl neu
    versehener Handler zurueck."""
    added = 0
    for name in logger_names:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, DBErrorRedactionFilter) for f in handler.filters):
                handler.addFilter(DBErrorRedactionFilter())
                added += 1
    return added


def _scrub_path(path: Optional[str]) -> Optional[str]:
    """M-DSG4: strip resource UUIDs from request paths before they are stored.

    Many paths embed a user/resource UUID (``/api/admin/users/<uuid>/journal``,
    ``/api/absences/<uuid>``) — the pseudonymous identifier the scrubber removes
    from message/traceback would otherwise persist verbatim in the ``path``
    column. Replacing every UUID with ``<id>`` also improves dedup (the same
    error on different ids aggregates to one fingerprint)."""
    if not path:
        return path
    return _UUID_RE.sub('<id>', path)


def _make_fingerprint(level: str, logger: str, message: str, path: Optional[str]) -> str:
    """Create a stable fingerprint for error deduplication."""
    key = f"{level}:{logger}:{message[:200]}:{path or ''}"
    return hashlib.sha256(key.encode()).hexdigest()


def log_error(
    db: Session,
    level: str,
    logger_name: str,
    message: str,
    traceback_str: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> ErrorLog:
    """
    Record an error, aggregating repeated occurrences (same fingerprint).
    """
    # DSGVO F-007: scrub PII before storing
    message = _scrub_pii(message)
    # M-DSG4: scrub UUIDs out of the path before it is stored AND fingerprinted.
    path = _scrub_path(path)
    if traceback_str:
        traceback_str = _scrub_pii(traceback_str)
        # VULN-012: store only first 2000 chars to avoid leaking full stack frames
        if len(traceback_str) > 2000:
            traceback_str = traceback_str[:2000] + '\n... [truncated]'

    fingerprint = _make_fingerprint(level, logger_name, message, path)
    now = datetime.now(timezone.utc)

    # Security-Review 2026-07-25: die Dedup-Suche MUSS tenant-gescoped sein.
    # log_error läuft bewusst im Superadmin-RLS-Kontext (die Middleware schreibt
    # auch Fehler unauthentifizierter Requests) — RLS filtert hier also NICHT.
    # Ohne diesen Filter fasste der Fingerprint (level+logger+message+path, ohne
    # Tenant) dieselbe Exception aus zwei Mandanten zu EINER Zeile zusammen: der
    # zweite überschrieb Traceback + last_seen des ersten, dessen Admin über das
    # (seit #127 tenant-gefilterte) GET /api/admin/errors dann einen fremden
    # Traceback las — während die eigenen Fehler unter fremder tenant_id
    # unsichtbar blieben.
    #
    # Bewusst über den Filter statt über die Fingerprint-Formel gelöst: der
    # Fingerprint bleibt stabil, bestehende Zeilen aggregieren also weiter (kein
    # UNIQUE auf fingerprint, mehrere Tenants dürfen denselben Wert tragen).
    # tenant_id IS NULL (Infrastruktur-/Anonym-Fehler) bildet einen eigenen
    # Aggregations-Topf — `is_(None)` statt `== None`, damit SQL IS NULL und
    # nicht `= NULL` (immer unbekannt) entsteht.
    existing = db.query(ErrorLog).filter(
        ErrorLog.fingerprint == fingerprint,
        ErrorLog.status.in_(['open', 'ignored']),
        ErrorLog.tenant_id == tenant_id if tenant_id is not None else ErrorLog.tenant_id.is_(None),
    ).first()

    if existing:
        existing.count += 1
        existing.last_seen = now
        if traceback_str:
            existing.traceback = traceback_str  # already truncated above
        db.commit()
        return existing

    entry = ErrorLog(
        level=level,
        logger=logger_name,
        message=message[:2000],
        traceback=traceback_str,
        path=path,
        method=method,
        status_code=status_code,
        user_id=user_id,
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        count=1,
        first_seen=now,
        last_seen=now,
        status='open',
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _scope_to_tenant(query, tenant_id: Optional[uuid.UUID]):
    """Apply the SaaS tenant-scope filter to an ``ErrorLog`` query.

    Design (Issue #127 follow-up — H1 regression fix):

    * SaaS mode (``tenant_id`` is set): the caller must see
        - rows belonging to *their* tenant, **and**
        - rows with ``tenant_id IS NULL`` — i.e. infrastructure errors
          captured outside any request context (``DBErrorHandler.emit``,
          startup failures, request-validation 5xx that aborted before the
          auth dependency could populate ``request.state.tenant_id``).

      Hiding NULL-tenant rows from tenant-admins would silently swallow
      operationally relevant errors. Cross-tenant contamination is impossible
      because foreign rows still carry a non-matching tenant_id and are
      excluded by the equality branch.

    * On-prem mode (``tenant_id is None``): no filter — the legacy
      (single-tenant) full aggregate is returned.
    """
    if tenant_id is None:
        return query
    return query.filter(
        (ErrorLog.tenant_id == tenant_id) | (ErrorLog.tenant_id.is_(None))
    )


def get_errors(
    db: Session,
    status: Optional[str] = None,
    limit: int = 100,
    tenant_id: Optional[uuid.UUID] = None,
):
    """List errors, ordered by last_seen desc.

    F-026 (belt-and-suspenders): when ``tenant_id`` is provided (SaaS mode),
    rows are explicitly filtered to that tenant (plus NULL-tenant infra
    errors, see :func:`_scope_to_tenant`) on top of RLS. In onprem mode
    callers pass ``tenant_id=None`` and the (single-tenant) full set is
    returned — matching legacy behaviour.
    """
    query = _scope_to_tenant(db.query(ErrorLog), tenant_id)
    if status:
        query = query.filter(ErrorLog.status == status)
    return query.order_by(ErrorLog.last_seen.desc()).limit(limit).all()


def get_error_summary(
    db: Session,
    tenant_id: Optional[uuid.UUID] = None,
) -> dict[str, int]:
    """Return counts of error logs grouped by status.

    F-026: filters explicitly on ``tenant_id`` when set (SaaS — plus
    NULL-tenant infra errors, see :func:`_scope_to_tenant`); returns the
    untouched aggregate for ``None`` (onprem).
    """
    query = _scope_to_tenant(
        db.query(ErrorLog.status, func.count(ErrorLog.id)), tenant_id
    )
    counts = query.group_by(ErrorLog.status).all()
    return {status: count for status, count in counts}


def _scope_write_to_tenant(query, tenant_id: Optional[uuid.UUID]):
    """Apply the SaaS *write*-scope filter to an ``ErrorLog`` query.

    Design (Issue #127 / M1 follow-up — write-path belt-and-suspenders):

    * SaaS mode (``tenant_id`` is set): equality match **only** on
      ``ErrorLog.tenant_id == tenant_id``. Unlike the *read*-scope filter
      (:func:`_scope_to_tenant`) the NULL-tenant branch is intentionally
      omitted: tenant-admins must not be able to mutate or delete
      infrastructure errors that belong to no tenant — those rows are
      visible to all tenant-admins for operational awareness, but writing
      them would either (a) silently drop an infra-wide alert for *all*
      tenants, or (b) let any tenant suppress evidence of a system-level
      problem. Editing NULL-tenant rows is therefore reserved for the
      superadmin (separate endpoint, out of scope for this fix).

    * On-prem mode (``tenant_id is None``): no filter — legacy
      (single-tenant) behaviour, all rows are writable by any admin.
    """
    if tenant_id is None:
        return query
    return query.filter(ErrorLog.tenant_id == tenant_id)


def update_status(
    db: Session,
    error_id: str,
    new_status: str,
    admin_user_id: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
) -> Optional[ErrorLog]:
    """Set status to 'open', 'ignored', or 'resolved'.

    F-026 (belt-and-suspenders): when ``tenant_id`` is provided (SaaS mode),
    the row must belong to that tenant — NULL-tenant infra rows are *not*
    writable via this code path (see :func:`_scope_write_to_tenant`).
    In onprem mode callers pass ``tenant_id=None`` and any row matching
    ``error_id`` is mutated.
    """
    query = _scope_write_to_tenant(db.query(ErrorLog), tenant_id)
    entry = query.filter(ErrorLog.id == error_id).first()
    if not entry:
        return None
    entry.status = new_status
    if new_status == 'resolved':
        entry.resolved_at = datetime.now(timezone.utc)
        entry.resolved_by = admin_user_id
    db.commit()
    db.refresh(entry)
    return entry


def delete_error(
    db: Session,
    error_id: str,
    tenant_id: Optional[uuid.UUID] = None,
) -> bool:
    """Permanently delete an error log entry.

    F-026: when ``tenant_id`` is set (SaaS), only rows belonging to that
    tenant can be deleted. NULL-tenant infra rows are *not* deletable via
    this code path (see :func:`_scope_write_to_tenant`).
    """
    query = _scope_write_to_tenant(db.query(ErrorLog), tenant_id)
    entry = query.filter(ErrorLog.id == error_id).first()
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


def cleanup_old_errors(db: Session, max_age_days: int = 90) -> int:
    """DSGVO F-007: Delete resolved/ignored error logs older than max_age_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    deleted = (
        db.query(ErrorLog)
        .filter(
            ErrorLog.last_seen < cutoff,
            ErrorLog.status.in_(['resolved', 'ignored'])
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def set_github_url(
    db: Session,
    error_id: str,
    url: str,
    tenant_id: Optional[uuid.UUID] = None,
) -> Optional[ErrorLog]:
    """Store a GitHub issue URL for an error.

    F-026: when ``tenant_id`` is set (SaaS), only rows belonging to that
    tenant are addressable. NULL-tenant infra rows are *not* annotatable via
    this code path (see :func:`_scope_write_to_tenant`).
    """
    query = _scope_write_to_tenant(db.query(ErrorLog), tenant_id)
    entry = query.filter(ErrorLog.id == error_id).first()
    if not entry:
        return None
    entry.github_issue_url = url
    db.commit()
    db.refresh(entry)
    return entry


class DBErrorHandler(logging.Handler):
    """
    Python logging handler that writes WARNING+ records to the error_logs table.
    Attach to root logger or specific loggers in main.py.
    """

    def __init__(self, db_session_factory):
        super().__init__(level=logging.WARNING)
        self._factory = db_session_factory

    def emit(self, record: logging.LogRecord):
        try:
            db: Session = self._factory()
            set_superadmin_context(db)  # RLS: see all errors for dedup
            tb = None
            if record.exc_info and record.exc_info[1] is not None:
                # Audit 2026-11-07 (S2-1): Stapel ohne Ausnahme-Meldung (die trug
                # bei Datenbankfehlern Statement-Werte und PG-DETAIL).
                tb = exception_frames(record.exc_info[1])
                # VULN-012: limit traceback size before storing
                if tb and len(tb) > 2000:
                    tb = tb[:2000] + '\n... [truncated]'
            level = record.levelname.lower()
            log_error(
                db=db,
                level=level,
                logger_name=record.name,
                # S2-1: nur die Meldung selbst — ``self.format`` haengt bei
                # ``exc_info`` den vollen Traceback samt Ausnahme-Text an.
                message=record.getMessage(),
                traceback_str=tb,
            )
        except Exception:
            # Never let logging break the application — but don't go fully silent.
            # Write to stderr (NOT via the logging module → no recursion into this
            # handler) so a broken DB-logger is still visible in container logs.
            try:
                import sys
                sys.stderr.write("DBErrorHandler.emit failed:\n" + traceback.format_exc())
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass
