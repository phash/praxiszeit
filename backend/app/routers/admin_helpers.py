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
    """Add user names to the change request response (single item)."""
    return _enrich_cr_responses([cr], db)[0]


def _enrich_cr_responses(crs: list, db: Session) -> list[ChangeRequestResponse]:
    """Add user names to change request responses (batch, single query)."""
    if not crs:
        return []
    user_ids = set()
    for cr in crs:
        user_ids.add(cr.user_id)
        if cr.reviewed_by:
            user_ids.add(cr.reviewed_by)
    user_ids.discard(None)
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u for u in users}

    results = []
    for cr in crs:
        response = ChangeRequestResponse.model_validate(cr)
        user = user_map.get(cr.user_id)
        if user:
            response.user_first_name = user.first_name
            response.user_last_name = user.last_name
        if cr.reviewed_by:
            reviewer = user_map.get(cr.reviewed_by)
            if reviewer:
                response.reviewer_first_name = reviewer.first_name
                response.reviewer_last_name = reviewer.last_name
        results.append(response)
    return results


def _enrich_audit_response(log: TimeEntryAuditLog, db: Session) -> AuditLogResponse:
    """Add user names to the audit log response (single item)."""
    return _enrich_audit_responses([log], db)[0]


def _enrich_audit_responses(logs: list, db: Session) -> list[AuditLogResponse]:
    """Add user names to audit log responses (batch, single query)."""
    if not logs:
        return []
    user_ids = set()
    for log in logs:
        user_ids.add(log.user_id)
        if log.changed_by:
            user_ids.add(log.changed_by)
    user_ids.discard(None)
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: u for u in users}

    results = []
    for log in logs:
        response = AuditLogResponse.model_validate(log)
        user = user_map.get(log.user_id)
        if user:
            response.user_first_name = user.first_name
            response.user_last_name = user.last_name
        changer = user_map.get(log.changed_by)
        if changer:
            response.changed_by_first_name = changer.first_name
            response.changed_by_last_name = changer.last_name
        results.append(response)
    return results


class SettingUpdate(BaseModel):
    value: str
