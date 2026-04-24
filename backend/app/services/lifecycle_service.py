"""Tenant lifecycle: self-service suspend, deletion-request, anonymization
(Phase 6 / Issue #97).

Flow
----
* **Suspend request** (admin self-service): sets ``scheduled_suspend_at``
  7 days into the future. Cron picks it up and flips
  ``subscription_status`` to ``suspended`` (same read-only behaviour the
  license middleware already knows about).

* **Deletion request** (admin self-service): sets
  ``deletion_requested_at``. Cron runs ``anonymize_tenant()`` 30 days
  later. Tenant rows are NOT hard-deleted — ArbZG §16 mandates 2 years
  retention of working-time records, so we anonymize user PII and
  retain the time-entry / absence history attached to the anonymized
  FKs. A later purge job (out of scope here) can hard-delete once the
  retention window is over.

* **Ownership transfer**: admin hands over billing-email + owner role
  to another admin of the same tenant.

All mutations commit the DB session themselves.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    ChangeRequest,
    SignupAuditLog,
    TimeEntry,
    TimeEntryAuditLog,
    User,
    UserRole,
)
from app.models.tenant import Tenant


SUSPEND_GRACE_DAYS = 7
DELETE_GRACE_DAYS = 30


# ───────────────── Suspend / Deletion lifecycle ──────────────────────

def request_suspend(db: Session, tenant: Tenant, by_user: User) -> datetime:
    if tenant.subscription_status == "suspended":
        raise HTTPException(status_code=400, detail="Bereits gesperrt")
    scheduled = datetime.now(timezone.utc) + timedelta(days=SUSPEND_GRACE_DAYS)
    tenant.scheduled_suspend_at = scheduled
    tenant.scheduled_suspend_by = by_user.id
    db.commit()
    return scheduled


def cancel_suspend(db: Session, tenant: Tenant) -> None:
    tenant.scheduled_suspend_at = None
    tenant.scheduled_suspend_by = None
    db.commit()


def request_deletion(db: Session, tenant: Tenant, by_user: User) -> datetime:
    if tenant.deletion_requested_at is not None:
        raise HTTPException(status_code=400, detail="Löschantrag bereits gestellt")
    now = datetime.now(timezone.utc)
    tenant.deletion_requested_at = now
    tenant.deletion_requested_by = by_user.id
    db.commit()
    return now + timedelta(days=DELETE_GRACE_DAYS)


def cancel_deletion(db: Session, tenant: Tenant) -> None:
    if tenant.deletion_requested_at is None:
        raise HTTPException(status_code=400, detail="Kein offener Löschantrag")
    tenant.deletion_requested_at = None
    tenant.deletion_requested_by = None
    db.commit()


# ───────────────── Ownership transfer ────────────────────────────────

def transfer_ownership(db: Session, current_admin: User, new_owner_id: uuid.UUID) -> User:
    """Hand billing ownership to another admin of the same tenant.

    'Ownership' in the current model is a soft concept: whoever's email
    is ``tenant.billing_email`` receives billing notifications. We keep
    the admin role on both users; the old owner is not demoted
    automatically (the caller can deactivate themselves separately).
    """
    new_owner = db.query(User).filter(
        User.id == new_owner_id,
        User.tenant_id == current_admin.tenant_id,
    ).first()
    if new_owner is None:
        raise HTTPException(status_code=404, detail="Zielbenutzer nicht gefunden")
    if new_owner.role != UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Ziel muss Admin sein")
    tenant = db.query(Tenant).filter(Tenant.id == current_admin.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")
    tenant.billing_email = new_owner.email or tenant.billing_email
    db.commit()
    return new_owner


# ───────────────── Cron: apply scheduled state changes ──────────────

def apply_scheduled_suspends(db: Session) -> int:
    now = datetime.now(timezone.utc)
    q = db.query(Tenant).filter(
        Tenant.scheduled_suspend_at.isnot(None),
        Tenant.scheduled_suspend_at <= now,
        Tenant.subscription_status != "suspended",
    )
    n = 0
    for t in q.all():
        t.subscription_status = "suspended"
        t.scheduled_suspend_at = None
        t.scheduled_suspend_by = None
        n += 1
    if n:
        db.commit()
    return n


def apply_scheduled_deletions(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=DELETE_GRACE_DAYS)
    q = db.query(Tenant).filter(
        Tenant.deletion_requested_at.isnot(None),
        Tenant.anonymized_at.is_(None),
    )
    to_anonymize: list[Tenant] = []
    for t in q.all():
        requested = t.deletion_requested_at
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=timezone.utc)
        if requested <= cutoff:
            to_anonymize.append(t)
    for t in to_anonymize:
        anonymize_tenant(db, t, commit=False)
    if to_anonymize:
        db.commit()
    return len(to_anonymize)


# ───────────────── Anonymization (ArbZG §16-compliant) ───────────────

def anonymize_tenant(db: Session, tenant: Tenant, *, commit: bool = True) -> None:
    """Scrub PII on users + tenant, but keep rows so working-time
    records remain attached during the 2-year retention window.

    - ``users``: username → ``deleted_<hex>``, email → NULL, first/last
      → "Anonymisiert"/"Benutzer", password_hash → unusable sentinel,
      is_active → False
    - ``tenants``: name → "[gelöscht]", company_name/vat_id/country/
      billing_address/billing_email → NULL. Stripe ids retained for
      accounting audit. ``anonymized_at`` marks completion.
    - ``change_requests``, ``signup_audit_log``: notes cleared of email
      / name fragments — best-effort; free-form text fields stay.
    """
    users = db.query(User).filter(User.tenant_id == tenant.id).all()
    for u in users:
        suffix = uuid.uuid4().hex[:8]
        u.username = f"deleted_{suffix}"
        u.email = None
        u.first_name = "Anonymisiert"
        u.last_name = "Benutzer"
        # Force re-hash with an unusable password so no login is possible.
        u.password_hash = "!disabled:" + suffix
        u.is_active = False

    tenant.name = "[gelöscht]"
    tenant.company_name = None
    tenant.vat_id = None
    tenant.country = None
    tenant.billing_address = None
    tenant.billing_email = None
    tenant.is_active = False
    tenant.subscription_status = "canceled"
    tenant.anonymized_at = datetime.now(timezone.utc)

    # Clear PII from the signup audit: DSGVO consent rows stay (we still
    # need to prove consent was given for the legal-retention period),
    # but we scrub email + IP so the row doesn't identify the person.
    for audit in db.query(SignupAuditLog).filter(SignupAuditLog.tenant_id == tenant.id).all():
        audit.email = "[anon]"
        audit.ip_address = None
        audit.user_agent = None

    if commit:
        db.commit()


# ───────────────── Export (self-service + superadmin share this) ─────

def build_tenant_export_payload(db: Session, tenant: Tenant, *, requester: User) -> dict[str, Any]:
    """Assemble the full tenant export used by /api/tenant/export AND
    the superadmin ArbZG export. Keeps both call-sites in sync."""
    users = db.query(User).filter(User.tenant_id == tenant.id).all()
    time_entries = db.query(TimeEntry).filter(TimeEntry.tenant_id == tenant.id).all()
    absences = db.query(Absence).filter(Absence.tenant_id == tenant.id).all()
    change_requests = db.query(ChangeRequest).filter(ChangeRequest.tenant_id == tenant.id).all()
    audit_logs = (
        db.query(TimeEntryAuditLog)
        .filter(TimeEntryAuditLog.tenant_id == tenant.id)
        .order_by(TimeEntryAuditLog.created_at.desc())
        .all()
    )
    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "export_generated_by": str(requester.id),
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan,
            "subscription_status": tenant.subscription_status,
            "is_active": tenant.is_active,
            "mode": tenant.mode,
        },
        "users": [_user_dict(u) for u in users],
        "time_entries": [_time_entry_dict(t) for t in time_entries],
        "absences": [_absence_dict(a) for a in absences],
        "change_requests": [
            {
                "id": str(c.id), "user_id": str(c.user_id), "status": str(c.status),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in change_requests
        ],
        "audit_logs": [
            {
                "id": str(a.id), "action": a.action, "source": a.source,
                "user_id": str(a.user_id) if a.user_id else None,
                "changed_by": str(a.changed_by) if a.changed_by else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "new_note": a.new_note,
            }
            for a in audit_logs
        ],
    }


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "username": u.username,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "role": u.role.value if hasattr(u.role, "value") else str(u.role),
        "weekly_hours": float(u.weekly_hours) if u.weekly_hours is not None else None,
        "is_active": u.is_active,
    }


def _time_entry_dict(te: TimeEntry) -> dict[str, Any]:
    return {
        "id": str(te.id),
        "user_id": str(te.user_id),
        "date": te.date.isoformat() if te.date else None,
        "start_time": str(te.start_time) if te.start_time else None,
        "end_time": str(te.end_time) if te.end_time else None,
        "break_minutes": te.break_minutes,
    }


def _absence_dict(a: Absence) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "date": a.date.isoformat() if a.date else None,
        "type": a.type.value if hasattr(a.type, "value") else str(a.type),
        "hours": float(a.hours) if a.hours is not None else None,
    }


def export_as_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
