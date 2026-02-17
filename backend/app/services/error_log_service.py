"""
Error logging service: captures, deduplicates, and stores application errors.
Uses SHA256 fingerprinting to aggregate repeated errors.
"""
import hashlib
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.error_log import ErrorLog


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
            existing.traceback = traceback_str
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
