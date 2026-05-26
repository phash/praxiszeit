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
_NAME_IN_PATH_RE = re.compile(r'(?<=/users/)[0-9a-f-]{36}')

def _scrub_pii(text: str) -> str:
    """Replace UUIDs and email addresses in log messages with placeholders."""
    if not text:
        return text
    text = _UUID_RE.sub('<uuid>', text)
    text = _EMAIL_RE.sub('<email>', text)
    return text


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
    if traceback_str:
        traceback_str = _scrub_pii(traceback_str)
        # VULN-012: store only first 2000 chars to avoid leaking full stack frames
        if len(traceback_str) > 2000:
            traceback_str = traceback_str[:2000] + '\n... [truncated]'

    fingerprint = _make_fingerprint(level, logger_name, message, path)
    now = datetime.now(timezone.utc)

    existing = db.query(ErrorLog).filter(
        ErrorLog.fingerprint == fingerprint,
        ErrorLog.status.in_(['open', 'ignored'])
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
            if record.exc_info:
                tb = ''.join(traceback.format_exception(*record.exc_info))
                # VULN-012: limit traceback size before storing
                if tb and len(tb) > 2000:
                    tb = tb[:2000] + '\n... [truncated]'
            level = record.levelname.lower()
            log_error(
                db=db,
                level=level,
                logger_name=record.name,
                message=self.format(record),
                traceback_str=tb,
            )
        except Exception:
            pass  # Never let logging break the application
        finally:
            try:
                db.close()
            except Exception:
                pass
