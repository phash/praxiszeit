"""Shared helpers used by admin sub-routers."""

from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import User, ChangeRequest, TimeEntryAuditLog
from app.schemas.change_request import ChangeRequestResponse
from app.schemas.time_entry_audit_log import AuditLogResponse


def _get_field(entry, field: str):
    """Get a field from either an ORM object or a dict."""
    return getattr(entry, field, None) if hasattr(entry, field) else entry.get(field)


def _create_audit_log(
    db: Session,
    time_entry_id,
    user_id,
    changed_by,
    action: str,
    old_entry=None,
    new_entry=None,
    source: str = "manual",
    change_request_id=None,
    tenant_id=None,
):
    """Create an audit log entry for a time entry change."""
    log = TimeEntryAuditLog(
        time_entry_id=time_entry_id,
        user_id=user_id,
        changed_by=changed_by,
        action=action,
        source=source,
        change_request_id=change_request_id,
        tenant_id=tenant_id,
    )
    if old_entry:
        log.old_date = _get_field(old_entry, 'date')
        log.old_start_time = _get_field(old_entry, 'start_time')
        log.old_end_time = _get_field(old_entry, 'end_time')
        log.old_break_minutes = _get_field(old_entry, 'break_minutes')
        log.old_note = _get_field(old_entry, 'note')
    if new_entry:
        log.new_date = _get_field(new_entry, 'date')
        log.new_start_time = _get_field(new_entry, 'start_time')
        log.new_end_time = _get_field(new_entry, 'end_time')
        log.new_break_minutes = _get_field(new_entry, 'break_minutes')
        log.new_note = _get_field(new_entry, 'note')
    db.add(log)
    return log


def _enrich_cr_response(cr: ChangeRequest, db: Session) -> ChangeRequestResponse:
    """Add user names to the change request response."""
    response = ChangeRequestResponse.model_validate(cr)
    user = db.query(User).filter(User.id == cr.user_id).first()
    if user:
        response.user_first_name = user.first_name
        response.user_last_name = user.last_name
    if cr.reviewed_by:
        reviewer = db.query(User).filter(User.id == cr.reviewed_by).first()
        if reviewer:
            response.reviewer_first_name = reviewer.first_name
            response.reviewer_last_name = reviewer.last_name
    return response


def _enrich_audit_response(log: TimeEntryAuditLog, db: Session) -> AuditLogResponse:
    """Add user names to the audit log response."""
    response = AuditLogResponse.model_validate(log)
    user = db.query(User).filter(User.id == log.user_id).first()
    if user:
        response.user_first_name = user.first_name
        response.user_last_name = user.last_name
    changer = db.query(User).filter(User.id == log.changed_by).first()
    if changer:
        response.changed_by_first_name = changer.first_name
        response.changed_by_last_name = changer.last_name
    return response


class SettingUpdate(BaseModel):
    value: str
