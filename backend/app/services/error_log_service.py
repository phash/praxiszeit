"""
Error logging service: captures, deduplicates, and stores application errors.
Uses SHA256 fingerprinting to aggregate repeated errors.
"""
import hashlib
import logging
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.error_log import ErrorLog

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


def get_errors(db: Session, status: Optional[str] = None, limit: int = 100):
    """List errors, ordered by last_seen desc."""
    query = db.query(ErrorLog)
    if status:
        query = query.filter(ErrorLog.status == status)
    return query.order_by(ErrorLog.last_seen.desc()).limit(limit).all()


def update_status(db: Session, error_id: str, new_status: str, admin_user_id: Optional[str] = None) -> Optional[ErrorLog]:
    """Set status to 'open', 'ignored', or 'resolved'."""
    entry = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
    if not entry:
        return None
    entry.status = new_status
    if new_status == 'resolved':
        entry.resolved_at = datetime.now(timezone.utc)
        entry.resolved_by = admin_user_id
    db.commit()
    db.refresh(entry)
    return entry


def delete_error(db: Session, error_id: str) -> bool:
    """Permanently delete an error log entry."""
    entry = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
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


def set_github_url(db: Session, error_id: str, url: str) -> Optional[ErrorLog]:
    """Store a GitHub issue URL for an error."""
    entry = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
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
