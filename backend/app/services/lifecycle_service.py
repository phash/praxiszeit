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
import logging
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
    VacationRequest,
    WorkingHoursChange,
)
from app.models.shift_planning import ShiftSlot
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


SUSPEND_GRACE_DAYS = 7
DELETE_GRACE_DAYS = 30

# DSGVO Art. 5(1)(e) Speicherbegrenzung — vacation-request edit/cancel audit
# rows reference an approval workflow, not the ArbZG-mandatory time-record
# itself. We purge them after 730 days (gleichlauf mit ArbZG §16-Frist) so
# the request-level history doesn't accumulate forever. Time-entry audits
# (sources: manual / import / change_request) are NOT touched here.
VACATION_AUDIT_RETENTION_DAYS = 730
VACATION_AUDIT_SOURCES = (
    "vacation_request_edit",
    "vacation_request_cancel",
    # #208 / Art. 5(1)(e): auch die Abwesenheits-Buchungs-/Genehmigungs-Audits
    # dokumentieren den Antrags-Workflow (nicht die ArbZG-§16-Zeitaufzeichnung)
    # und werden nach 730 Tagen mitgepurged, statt unbegrenzt zu akkumulieren.
    "absence_creation",
    "absence_request_approval",
)


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
    try:
        from app.services.alerting import alert_deletion_requested
        alert_deletion_requested(tenant.name)
    except Exception:  # noqa: BLE001
        # Best-effort alert after the commit — log instead of swallowing silently.
        logger.warning("alert_deletion_requested failed", exc_info=True)
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


def purge_expired_vacation_audit_logs(db: Session) -> int:
    """Delete vacation-request edit/cancel audit rows older than the
    retention window (DSGVO Art. 5 Abs. 1 lit. e).

    Returns number of deleted rows. Tenant-scoped via WHERE on the model;
    safe to run in a superadmin RLS context (the query carries no user
    context). Time-entry audits (manual / import / change_request) are
    intentionally excluded — those are bound to the ArbZG §16
    record-retention obligation and must outlive this purge.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=VACATION_AUDIT_RETENTION_DAYS)
    deleted = (
        db.query(TimeEntryAuditLog)
        .filter(
            TimeEntryAuditLog.source.in_(VACATION_AUDIT_SOURCES),
            TimeEntryAuditLog.created_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()
    return int(deleted or 0)


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
      is_active → False, profile_picture / totp_secret / department → NULL
    - ``working_hours_changes``: ``note`` → NULL (die Zeilen selbst bleiben,
      sie tragen das historische Soll fuer die §16-Aufbewahrung)
    - ``time_entry_audit_logs``: ``old_note``/``new_note`` → NULL, ``row_hash``
      neu berechnet (#121). Die Zeilen bleiben — Datum/Uhrzeit/Pause und "wer
      hat wann was geaendert" sind der §16-relevante Teil, der Freitext nicht,
      und er traegt E-Mail-Adressen + Benutzernamen im Klartext.
    - ``tenants``: name → "[gelöscht]", company_name/vat_id/country/
      billing_address/billing_email → NULL. Stripe ids retained for
      accounting audit. ``anonymized_at`` marks completion.
    - ``signup_audit_log``: email / IP / User-Agent scrubbed, consent row kept.
    - ``shift_slots``: ``note`` -> NULL (#443; Admin-Freitext ohne
      Aufbewahrungspflicht, kann Personenbezug tragen).

    Abwesenheiten und Zeiteintraege bleiben bewusst stehen (Modul-Docstring:
    Aufbewahrung an anonymisierten FKs) — anders als beim Einzel-Nutzer-Pfad
    ``admin_users.anonymize_user``, der ohne Mandantenaufloesung arbeitet.
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
        # Gleichlauf mit dem Einzel-Nutzer-Pfad ``admin_users.anonymize_user``:
        # ohne diese vier Felder setzt ``anonymized_at`` die Anonymisierung als
        # erledigt, waehrend ein Base64-Lichtbild (Art. 4 Nr. 1 — identifiziert
        # die Person unmittelbar), das TOTP-Geheimnis und die Abteilungs-
        # zuordnung unveraendert in der Zeile stehen. Die Pseudonymisierung
        # waere damit faktisch aufgehoben.
        u.profile_picture = None
        u.totp_secret = None
        u.totp_enabled = False
        u.last_totp_counter = None
        u.department = None

    # #431: die Vertragshistorie bleibt (historisches Soll, §16), ihr freier
    # ``note``-Text ist aber Admin-Prosa ohne Aufbewahrungspflicht und kann
    # Klarnamen enthalten ("Rueckkehr Frau Meier nach Elternzeit").
    db.query(WorkingHoursChange).filter(
        WorkingHoursChange.tenant_id == tenant.id,
        WorkingHoursChange.note.isnot(None),
    ).update({WorkingHoursChange.note: None}, synchronize_session=False)

    # #443/#440: Der Hinweis je Schicht-Einteilung ist Admin-Freitext und kann
    # Personenbezug tragen ("Einarbeitung Frau Meier"). Ein Bulk-UPDATE ist hier
    # zulaessig — anders als bei time_entry_audit_logs traegt shift_slots keinen
    # row_hash (#121), den ein Umgehen der Objektschicht stale werden liesse.
    db.query(ShiftSlot).filter(
        ShiftSlot.tenant_id == tenant.id,  # F-026
        ShiftSlot.note.isnot(None),
    ).update({ShiftSlot.note: None}, synchronize_session=False)

    # Release-Review 1.18.1: dieselbe Klasse im Aenderungsprotokoll. Die
    # Freitext-Notizen tragen DIREKTE Identifikatoren, nicht nur Prosa:
    # ``auth.py`` schreibt bei jedem Selbstbedienungs-E-Mail-Wechsel die alte
    # und die neue Adresse nach ``old_note``; ``reports.py``/``journal.py``
    # schreiben bei jedem Zugriff auf Gesundheitsdaten den Benutzernamen nach
    # ``new_note`` — also genau die Werte, die oben auf der ``users``-Zeile zu
    # ``deleted_<hex>`` / NULL werden. Ohne diesen Schritt meldet
    # ``anonymized_at`` die Loeschung als erledigt, waehrend E-Mail-Adresse und
    # Benutzername im Klartext in der Datenbank stehen und ueber den
    # Superadmin-§16-Export (``_audit_dict`` gibt beide Notizfelder aus, auch
    # fuer deaktivierte Mandanten) lesbar bleiben. Einen zweiten Durchlauf gibt
    # es nicht (``apply_scheduled_deletions`` filtert ``anonymized_at IS NULL``),
    # und ``purge_expired_vacation_audit_logs`` deckt nur vier Antrags-Quellen —
    # ``self_service``/``dsgvo`` gehoeren nicht dazu.
    #
    # Die ZEILEN bleiben stehen (wie ``working_hours_changes``): sie belegen,
    # wer wann was an einer Zeitaufzeichnung geaendert hat, und tragen mit
    # ``old_*``/``new_*`` Datum, Uhrzeit und Pause weiterhin vollstaendig — das
    # ist der §16-relevante Teil. Der Freitext ist es nicht.
    #
    # #121: ``old_note``/``new_note`` sind Teil des ``row_hash``. Deshalb ORM-
    # Objekte laden und den Hash neu berechnen (Muster aus
    # ``admin_users.purge_user``) — ein Bulk-UPDATE umginge den
    # ``before_insert``-Hook, liesse den gespeicherten Hash schal und
    # ``verify-integrity`` meldete danach jede dieser legitimen Zeilen als
    # manipuliert. Nur Zeilen MIT Notiz werden angefasst, alle anderen behalten
    # ihren Hash unveraendert.
    from app.core import audit_integrity
    for row in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == tenant.id,
        (TimeEntryAuditLog.old_note.isnot(None))
        | (TimeEntryAuditLog.new_note.isnot(None)),
    ).all():
        row.old_note = None
        row.new_note = None
        row.row_hash = audit_integrity.compute_row_hash(row)

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
        "users": [_user_dict(db, u) for u in users],
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


def _user_dict(db: Session, u: User) -> dict[str, Any]:
    # DSGVO Art. 15: vollstaendige Auskunft. Whitelist (statt Blacklist) — neue
    # Felder im User-Model erscheinen nicht automatisch im Export, das ist Absicht
    # (verhindert versehentliches Leaken von z.B. password_hash, totp_secret,
    # last_totp_counter).
    #
    # #431: die Stundenhistorie ist ein vollstaendiger Vertrags-Snapshot je
    # Wirkungsdatum (Soll-relevant) und gehoert damit in den Art.-15-Export.
    # F-026 (belt-and-suspenders, RLS greift hier zusaetzlich): tenant_id
    # explizit mitfiltern. Chronologisch aufsteigend wie die anderen
    # Sammlungen in diesem Export (time_entries/absences/change_requests).
    history = (
        db.query(WorkingHoursChange)
        .filter(
            WorkingHoursChange.user_id == u.id,
            WorkingHoursChange.tenant_id == u.tenant_id,
        )
        .order_by(WorkingHoursChange.effective_from.asc())
        .all()
    )
    return {
        "id": str(u.id),
        "username": u.username,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "role": u.role.value if hasattr(u.role, "value") else str(u.role),
        "weekly_hours": float(u.weekly_hours) if u.weekly_hours is not None else None,
        # #408: vacation_days ist jetzt Numeric(4,1) → Decimal. json.dumps (unten,
        # export_as_json_bytes) kann Decimal nicht serialisieren → float casten
        # (wie weekly_hours darüber). Vorher Integer, daher kein Cast nötig.
        "vacation_days": float(u.vacation_days) if u.vacation_days is not None else None,
        "work_days_per_week": u.work_days_per_week,
        "track_hours": u.track_hours,
        "calendar_color": u.calendar_color,
        "vacation_carryover_deadline": (
            u.vacation_carryover_deadline.isoformat() if u.vacation_carryover_deadline else None
        ),
        "use_daily_schedule": u.use_daily_schedule,
        "hours_monday": float(u.hours_monday) if u.hours_monday is not None else None,
        "hours_tuesday": float(u.hours_tuesday) if u.hours_tuesday is not None else None,
        "hours_wednesday": float(u.hours_wednesday) if u.hours_wednesday is not None else None,
        "hours_thursday": float(u.hours_thursday) if u.hours_thursday is not None else None,
        "hours_friday": float(u.hours_friday) if u.hours_friday is not None else None,
        "is_active": u.is_active,
        "is_hidden": u.is_hidden,
        # Art-9-analog (Nachtarbeiter-Status loest § 6 ArbZG-Sonderregeln aus)
        "is_night_worker": u.is_night_worker,
        # § 18 ArbZG-Status — Pflichtbestandteil der Aufzeichnung
        "exempt_from_arbzg": u.exempt_from_arbzg,
        "first_work_day": u.first_work_day.isoformat() if u.first_work_day else None,
        "last_work_day": u.last_work_day.isoformat() if u.last_work_day else None,
        # Lichtbild = personenbezogenes Datum (Art. 4 Nr. 1)
        "profile_picture": u.profile_picture,
        # Sicherheits-Status (TOTP-Aktivierung ist eine Tatsache ueber den Nutzer,
        # totp_secret + last_totp_counter natuerlich NICHT)
        "totp_enabled": u.totp_enabled,
        "deactivated_at": u.deactivated_at.isoformat() if u.deactivated_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        # #431: Vertrags-Snapshots ueber die Zeit — Numeric(4,2)-Felder MUESSEN
        # float()-gecastet werden (Decimal-Leak-Klasse #383/#408: dieser Export
        # laeuft ueber rohes json.dumps, nicht jsonable_encoder).
        "working_hours_changes": [
            {
                "id": str(h.id),
                "effective_from": h.effective_from.isoformat() if h.effective_from else None,
                "weekly_hours": float(h.weekly_hours) if h.weekly_hours is not None else None,
                "use_daily_schedule": h.use_daily_schedule,
                "hours_monday": float(h.hours_monday) if h.hours_monday is not None else None,
                "hours_tuesday": float(h.hours_tuesday) if h.hours_tuesday is not None else None,
                "hours_wednesday": float(h.hours_wednesday) if h.hours_wednesday is not None else None,
                "hours_thursday": float(h.hours_thursday) if h.hours_thursday is not None else None,
                "hours_friday": float(h.hours_friday) if h.hours_friday is not None else None,
                "work_days_per_week": h.work_days_per_week,
                "note": h.note,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ],
    }


def _time_entry_dict(te: TimeEntry) -> dict[str, Any]:
    return {
        "id": str(te.id),
        "user_id": str(te.user_id),
        "date": te.date.isoformat() if te.date else None,
        "start_time": str(te.start_time) if te.start_time else None,
        "end_time": str(te.end_time) if te.end_time else None,
        # §16 ArbZG (Review 2026-06-23): die ungekappten Rohstempel sind die
        # eigentliche Arbeitszeitaufzeichnung vor der Work-Window-Kappung (#201)
        # und gehoeren in den Pflicht-/Auskunfts-Export (wie im MA-Self-Export).
        "raw_start_time": str(te.raw_start_time) if getattr(te, "raw_start_time", None) else None,
        "raw_end_time": str(te.raw_end_time) if getattr(te, "raw_end_time", None) else None,
        "break_minutes": te.break_minutes,
        "note": te.note,
        # §10 ArbZG: Begruendung fuer Sonn-/Feiertagsarbeit — Pflichtbestandteil
        # der Arbeitszeitaufzeichnung, gehoert in jeden Auskunfts-Export
        "sunday_exception_reason": getattr(te, "sunday_exception_reason", None),
        "created_at": te.created_at.isoformat() if te.created_at else None,
    }


def _absence_dict(a: Absence) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "date": a.date.isoformat() if a.date else None,
        "end_date": a.end_date.isoformat() if getattr(a, "end_date", None) else None,
        "type": a.type.value if hasattr(a.type, "value") else str(a.type),
        # #312: eigener Abwesenheitsgrund (Klartextname via reason_names im Payload).
        "reason_id": str(a.reason_id) if getattr(a, "reason_id", None) else None,
        "hours": float(a.hours) if a.hours is not None else None,
        # Task 15: der beim Buchen festgeschriebene Rohwert (Art. 15 —
        # Auskunft ueber ALLE gespeicherten Daten). ``float()``-Cast wie
        # ``hours``: die Spalte ist ``Numeric`` und liefert beim Lesen
        # ``Decimal``, und dieser Export laeuft ueber rohes ``json.dumps``
        # (Fehlerklasse #383/#408 — dort war es ein HTTP 500 fuer JEDEN Nutzer).
        # Bestandszeilen vor Migration 068 koennen NULL tragen.
        "raw_hours": float(a.raw_hours) if getattr(a, "raw_hours", None) is not None else None,
        "start_time": str(a.start_time) if getattr(a, "start_time", None) else None,
        "end_time": str(a.end_time) if getattr(a, "end_time", None) else None,
        "note": getattr(a, "note", None),
        "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else None,
    }


def export_as_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# ───────────────── Self-Service Export (DSGVO Art. 15, Issue #119) ─────

def build_self_export_payload(db: Session, user: User) -> dict[str, Any]:
    """Build a DSGVO Art. 15 self-service data export for a single employee.

    Returns ONLY the requester's own data. Tenant-scoped via RLS plus
    explicit F-026 belt-and-suspenders filters on every query.

    Includes audit rows where the user appears either as data subject
    (``user_id``) or as actor (``changed_by``) — covers both "what the
    system stored about me" and "what I myself did".
    """
    tid = user.tenant_id

    own_entries = (
        db.query(TimeEntry)
        .filter(TimeEntry.user_id == user.id, TimeEntry.tenant_id == tid)
        .order_by(TimeEntry.date.asc())
        .all()
    )
    own_absences = (
        db.query(Absence)
        .filter(Absence.user_id == user.id, Absence.tenant_id == tid)
        .order_by(Absence.date.asc())
        .all()
    )
    own_vacation_requests = (
        db.query(VacationRequest)
        .filter(VacationRequest.user_id == user.id, VacationRequest.tenant_id == tid)
        .order_by(VacationRequest.date.asc())
        .all()
    )
    own_change_requests = (
        db.query(ChangeRequest)
        .filter(ChangeRequest.user_id == user.id, ChangeRequest.tenant_id == tid)
        .order_by(ChangeRequest.created_at.asc())
        .all()
    )
    own_audit_logs = (
        db.query(TimeEntryAuditLog)
        .filter(
            TimeEntryAuditLog.tenant_id == tid,
            (TimeEntryAuditLog.user_id == user.id)
            | (TimeEntryAuditLog.changed_by == user.id),
        )
        .order_by(TimeEntryAuditLog.created_at.desc())
        .all()
    )

    # DSGVO Art. 12 Abs. 1 "in verstaendlicher Form" + Art. 15 (1)(c)
    # (Empfaenger-Information): UUIDs in reviewed_by / last_modified_by /
    # changed_by sind fuer den MA nutzlos. Wir reichern den Export deshalb
    # um ein 'user_directory' an, das alle vorkommenden Reviewer-/Editor-
    # UUIDs auf Klartext-Namen abbildet. Bewusste Design-Entscheidung:
    # ein zentrales Verzeichnis (statt _by_name-Felder pro Helper), weil
    #   1) weniger Diff (Helper-Signaturen unveraendert),
    #   2) Konsumenten genau EIN Lookup-Schema bedienen,
    #   3) max. 1 Extra-Query pro Export — unabhaengig von der Reviewer-Zahl.
    # F-026 Tenant-Filter: Reviewer aus FREMDEM Tenant werden bewusst NICHT
    # aufgeloest (Cross-Tenant-Schutz), die UUID bleibt dann opaque.
    reviewer_ids: set[uuid.UUID] = set()
    for vr in own_vacation_requests:
        if vr.reviewed_by:
            reviewer_ids.add(vr.reviewed_by)
        last_mod = getattr(vr, "last_modified_by", None)
        if last_mod:
            reviewer_ids.add(last_mod)
    for cr in own_change_requests:
        if cr.reviewed_by:
            reviewer_ids.add(cr.reviewed_by)
    for al in own_audit_logs:
        if al.changed_by:
            reviewer_ids.add(al.changed_by)

    if reviewer_ids:
        reviewers = (
            db.query(User)
            .filter(User.id.in_(reviewer_ids), User.tenant_id == tid)
            .all()
        )
    else:
        reviewers = []
    user_directory = {
        str(u.id): f"{u.first_name or ''} {u.last_name or ''}".strip() or (u.username or str(u.id))
        for u in reviewers
    }

    # MS-06: Schichtplanungs-Daten des MA (DSGVO Art. 15) — eigene Einteilungen +
    # Einweisungen sind personenbezogen. Nur wenn das Feature aktiv ist.
    from app.services import settings_service
    own_shift_assignments_data: list[dict[str, Any]] = []
    own_qualifications_data: list[dict[str, Any]] = []
    if settings_service.get_bool_setting(db, "shift_planning_enabled", tid, False):
        from app.models.shift_planning import (
            ShiftAssignment, ShiftSlot, ShiftPlan, Workstation, WorkstationQualification,
        )
        _WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        for a, sl, pl, ws in (
            db.query(ShiftAssignment, ShiftSlot, ShiftPlan, Workstation)
            .join(ShiftSlot, ShiftAssignment.shift_slot_id == ShiftSlot.id)
            .join(ShiftPlan, ShiftSlot.shift_plan_id == ShiftPlan.id)
            .outerjoin(Workstation, ShiftSlot.workstation_id == Workstation.id)
            .filter(ShiftAssignment.user_id == user.id, ShiftAssignment.tenant_id == tid)
            .all()
        ):
            own_shift_assignments_data.append({
                "plan": pl.name,
                "weekday": _WD[sl.weekday] if 0 <= sl.weekday < 7 else sl.weekday,
                "start_time": sl.start_time.strftime("%H:%M") if sl.start_time else None,
                "end_time": sl.end_time.strftime("%H:%M") if sl.end_time else None,
                "workstation": ws.name if ws else None,
                # Minor (Prüfrunde 2): der Hinweis wird MIT exportiert, nicht
                # ausgelassen. anonymize_tenant leert shift_slots.note bei
                # Anonymisierung, weil der Freitext Personenbezug tragen KANN
                # ("Einarbeitung Frau Meier") — das ist eine Löschpflicht nach
                # dem Ausscheiden, kein Grund, ihn einem aktiven Mitarbeitenden
                # in der eigenen Art.-15-Auskunft über die eigene Einteilung
                # vorzuenthalten. Der Hinweis ist ohnehin schon breiter sichtbar
                # als jede Selbstauskunft: er steht am Bildschirm für alle mit
                # Plansicht UND auf dem PDF-Aushang am Schwarzen Brett (laut
                # docs/SCHICHTPLANUNG.md teils sogar für Patientinnen und
                # Patienten einsehbar) — ihn hier zurückzuhalten wäre
                # widersprüchlich zu dieser bewussten öffentlichen Sichtbarkeit.
                "note": sl.note,
            })
        for q, ws in (
            db.query(WorkstationQualification, Workstation)
            .outerjoin(Workstation, WorkstationQualification.workstation_id == Workstation.id)
            .filter(WorkstationQualification.user_id == user.id, WorkstationQualification.tenant_id == tid)
            .all()
        ):
            own_qualifications_data.append({"workstation": ws.name if ws else str(q.workstation_id)})

    # #312: Klartextnamen der eigenen Abwesenheitsgründe (DSGVO Art. 12 — verständliche
    # Form; reason_id allein ist für den MA nutzlos). Tenant-scoped, inkl. inaktiver.
    reason_ids = {a.reason_id for a in own_absences if getattr(a, "reason_id", None)}
    reason_names: dict[str, str] = {}
    if reason_ids:
        from app.models import AbsenceReason
        for rsn in (
            db.query(AbsenceReason)
            .filter(AbsenceReason.id.in_(reason_ids), AbsenceReason.tenant_id == tid)
            .all()
        ):
            reason_names[str(rsn.id)] = rsn.name

    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "export_type": "self_service_dsgvo_art15",
        # DSGVO Art. 15 Abs. 1 lit. a-h Pflichtangaben — werden zusaetzlich
        # zur Datenkopie (Abs. 3) geliefert. Texte basieren auf dem VVT
        # (docs/specs/dsgvo/verarbeitungsverzeichnis.md).
        "art15_meta": _build_art15_meta(),
        "subject": _user_dict(db, user),
        "time_entries": [_time_entry_dict(t) for t in own_entries],
        "absences": [_absence_dict(a) for a in own_absences],
        # #312: id → Klartextname für reason_id in 'absences' (Art. 12).
        "reason_names": reason_names,
        "vacation_requests": [_vacation_request_dict(v) for v in own_vacation_requests],
        "change_requests": [_change_request_dict(c) for c in own_change_requests],
        "audit_logs": [_audit_log_dict(a) for a in own_audit_logs],
        # MS-06: eigene Schichteinteilungen + Einweisungen (leer, wenn Feature aus).
        "shift_assignments": own_shift_assignments_data,
        "qualifications": own_qualifications_data,
        # Klartext-Aufloesung fuer reviewed_by / last_modified_by / changed_by
        # (siehe Kommentar oben). Schluessel = UUID-String, Wert = "First Last".
        "user_directory": user_directory,
        "counts": {
            "time_entries": len(own_entries),
            "absences": len(own_absences),
            "vacation_requests": len(own_vacation_requests),
            "change_requests": len(own_change_requests),
            "audit_logs": len(own_audit_logs),
            "shift_assignments": len(own_shift_assignments_data),
            "qualifications": len(own_qualifications_data),
        },
    }


def _build_art15_meta() -> dict[str, Any]:
    """DSGVO Art. 15 Abs. 1 (a-h) Pflichtangaben zur Verarbeitung."""
    return {
        "a_zwecke": (
            "Arbeitszeiterfassung nach ArbZG §16, Urlaubs- und Abwesenheits-"
            "verwaltung, Lohnabrechnung-Vorbereitung, gesetzlich vorgeschriebene "
            "Reports (Nachtarbeit §6, Ruhezeit §5, Sonntagsruhe §9-11)."
        ),
        "b_datenkategorien": [
            "Stammdaten (Name, E-Mail, Rolle)",
            "Vertragsdaten (Wochenstunden, Urlaubsanspruch, Arbeitstage)",
            "Zeiteintraege (Datum, Beginn, Ende, Pausen, Notiz)",
            "Abwesenheiten (Urlaub, Krank, Sonderurlaub, Ueberstunden)",
            "Aenderungs- und Urlaubsantraege inkl. Begruendungen",
            "Audit-Log (Wer hat wann was geaendert)",
            "Authentifizierung (Passwort-Hash, ggf. TOTP-Status)",
            "Schichtplanung (Einteilungen, Einweisungen) — sofern aktiviert",
        ],
        "c_empfaenger": (
            "Praxis-Administrator (zur Genehmigung/Korrektur), ggf. Lohnbuchhaltung "
            "(Excel-/PDF-Export), ggf. Steuerberater (AVV oder Berufsgeheimnis). "
            "Bei deutscher On-Prem-Installation keine Drittlandsuebermittlung. "
            "Bei SaaS-Hosting: Auftragsverarbeiter gemaess AVV."
        ),
        "d_speicherdauer": (
            "Arbeitszeitaufzeichnungen: 2 Jahre (§ 16 Abs. 2 ArbZG). "
            "Lohn-/Steuer-relevante Daten: 6-10 Jahre (AO § 147, HGB § 257). "
            "Aenderungs-/Urlaubs-Antrags-Audit-Spuren: 730 Tage (Art. 5 (1)(e) "
            "DSGVO). Nach Beschaeftigungsende: Anonymisierung der PII unter "
            "Erhaltung der pseudonymisierten Arbeitszeit-Historie."
        ),
        "e_rechte": {
            "berichtigung": (
                "Art. 16 DSGVO — Stammdaten ueber Profil-Seite, Zeiteintraege "
                "ueber Aenderungsantrag (Admin-Genehmigung erforderlich)."
            ),
            "loeschung": (
                "Art. 17 DSGVO — auf Anfrage beim Praxis-Admin. Pseudonymisierung "
                "ist Standard, da ArbZG-Aufbewahrung dem Recht auf Loeschung "
                "vorgeht (Art. 17 Abs. 3 lit. b)."
            ),
            "einschraenkung": "Art. 18 DSGVO — auf Anfrage, Account-Deaktivierung.",
            "widerspruch": "Art. 21 DSGVO — an Praxis-Admin zu richten.",
            "datenportabilitaet": (
                "Art. 20 DSGVO — dieser Export ist maschinenlesbar (JSON) und "
                "uebertragbar."
            ),
        },
        "f_beschwerderecht": (
            "Sie haben das Recht, sich bei einer Datenschutz-Aufsichtsbehoerde zu "
            "beschweren — i.d.R. die Landes-Datenschutzbeauftragten des Bundeslands, "
            "in dem die Praxis ihren Sitz hat. Eine Liste aller Behoerden findet "
            "sich auf https://www.bfdi.bund.de/DE/Service/Anschriften/Laender/Laender-node.html"
        ),
        "g_quelle": (
            "Alle Daten wurden direkt bei Ihnen oder im Rahmen Ihrer Beschaeftigung "
            "erhoben (Stempelungen, Antraege, Stammdaten-Eingabe durch Sie oder "
            "den Admin). Keine externe Datenquelle."
        ),
        "h_automatisierte_entscheidung": (
            "Es findet KEINE automatisierte Entscheidung im Sinne von Art. 22 "
            "DSGVO statt. Genehmigungen von Antraegen erfolgen ausschliesslich "
            "durch einen menschlichen Admin."
        ),
        "hinweis_audit_log": (
            "Dieser Auskunfts-Export wird selbst im Audit-Log festgehalten "
            "(source='self_data_export'). Der Eintrag erscheint erst im naechsten "
            "Export, da er nach dem Build dieses Payloads geschrieben wird."
        ),
    }


def _vacation_request_dict(v: VacationRequest) -> dict[str, Any]:
    # last_modified_by ist erst nach Migration vorhanden — getattr defensiv,
    # damit aeltere Bestandsinstanzen ohne diese Spalte den Export noch fahren.
    last_mod = getattr(v, "last_modified_by", None)
    return {
        "id": str(v.id),
        "date": v.date.isoformat() if v.date else None,
        "end_date": v.end_date.isoformat() if v.end_date else None,
        "hours": float(v.hours) if v.hours is not None else None,
        "absence_type": v.absence_type,
        "note": v.note,
        "status": v.status,
        "rejection_reason": v.rejection_reason,
        "reviewed_by": str(v.reviewed_by) if v.reviewed_by else None,
        "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
        "last_modified_by": str(last_mod) if last_mod else None,
    }


def _change_request_dict(c: ChangeRequest) -> dict[str, Any]:
    # DSGVO Art. 15: vollstaendige Auskunft, inkl. Begruendung des MA selbst
    # und der vorgeschlagenen + originalen Werte. Vorher war der Export
    # praktisch inhaltsleer (nur id/status/created_at).
    return {
        "id": str(c.id),
        "request_type": (
            c.request_type.value if hasattr(c.request_type, "value") else str(c.request_type)
        ),
        "status": (
            c.status.value if hasattr(c.status, "value") else str(c.status)
        ),
        "entry_kind": c.entry_kind,
        "change_type": getattr(c, "change_type", None),
        "time_entry_id": str(c.time_entry_id) if c.time_entry_id else None,
        "absence_id": str(c.absence_id) if c.absence_id else None,
        # Vorgeschlagene Werte (Zeiteintrag)
        "proposed_date": c.proposed_date.isoformat() if c.proposed_date else None,
        "proposed_start_time": str(c.proposed_start_time) if c.proposed_start_time else None,
        "proposed_end_time": str(c.proposed_end_time) if c.proposed_end_time else None,
        "proposed_break_minutes": c.proposed_break_minutes,
        "proposed_note": c.proposed_note,
        # Vorgeschlagene Werte (Abwesenheit)
        "proposed_absence_type": c.proposed_absence_type,
        "proposed_absence_hours": (
            float(c.proposed_absence_hours) if c.proposed_absence_hours is not None else None
        ),
        # Original-Werte (Zeiteintrag)
        "original_date": c.original_date.isoformat() if c.original_date else None,
        "original_start_time": str(c.original_start_time) if c.original_start_time else None,
        "original_end_time": str(c.original_end_time) if c.original_end_time else None,
        "original_break_minutes": c.original_break_minutes,
        "original_note": c.original_note,
        # Original-Werte (Abwesenheit)
        "original_absence_type": c.original_absence_type,
        "original_absence_hours": (
            float(c.original_absence_hours) if c.original_absence_hours is not None else None
        ),
        # Begruendung des MA — Art. 15 absolut zwingend, das ist Eigentext des MA
        "reason": c.reason,
        "reviewed_by": str(c.reviewed_by) if c.reviewed_by else None,
        "reviewed_at": c.reviewed_at.isoformat() if getattr(c, "reviewed_at", None) else None,
        "rejection_reason": getattr(c, "rejection_reason", None),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _audit_log_dict(a: TimeEntryAuditLog) -> dict[str, Any]:
    # DSGVO Art. 15: vollstaendige Auskunft umfasst Aenderungshistorie. Ohne
    # old_*/new_* sieht der MA nur "es gab eine Aenderung" aber nicht WAS
    # geaendert wurde — das ist die Substanz des Audit-Logs.
    return {
        "id": str(a.id),
        "action": a.action,
        "source": a.source,
        "user_id": str(a.user_id) if a.user_id else None,
        "changed_by": str(a.changed_by) if a.changed_by else None,
        "time_entry_id": str(a.time_entry_id) if a.time_entry_id else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        # Vorher-Zustand
        "old_date": a.old_date.isoformat() if a.old_date else None,
        "old_start_time": str(a.old_start_time) if a.old_start_time else None,
        "old_end_time": str(a.old_end_time) if a.old_end_time else None,
        "old_break_minutes": a.old_break_minutes,
        "old_note": a.old_note,
        # Nachher-Zustand
        "new_date": a.new_date.isoformat() if a.new_date else None,
        "new_start_time": str(a.new_start_time) if a.new_start_time else None,
        "new_end_time": str(a.new_end_time) if a.new_end_time else None,
        "new_break_minutes": a.new_break_minutes,
        "new_note": a.new_note,
    }
