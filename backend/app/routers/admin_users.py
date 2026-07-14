"""Admin sub-router: User Management + Working Hours Changes."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timezone, timedelta
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, TimeEntry, Absence, AbsenceReason, WorkingHoursChange, ChangeRequest, TimeEntryAuditLog, UserRole, PublicHoliday
from app.services.date_filters import date_in_year
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword, UserListResponse
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeResponse
from app.schemas.reports import AdminUserOverview, VacationAccount, YtdOvertime
from app.services import auth_service, calculation_service, milog_service, settings_service
from app.core.license import check_employee_limit

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

logger = logging.getLogger(__name__)


def _get_user_in_tenant(db: Session, user_id: str, current_user: User) -> User:
    """
    F-026: Look up a user by id, guaranteeing they belong to the caller's
    tenant. Raises 404 on not-found or cross-tenant access (indistinguishable
    from the outside so we don't leak tenant membership).

    Every admin endpoint that accepts a ``user_id`` path parameter must use
    this helper instead of a raw ``db.query(User).filter(User.id == …)``.
    RLS catches cross-tenant access already, but CLAUDE.md explicitly
    requires belt-and-suspenders tenant scoping on bulk ops and lookups.
    """
    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == current_user.tenant_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    return user


def _enroll_user_in_open_closures(db: Session, user: User, current_user: User) -> None:
    """#290: fold a newly participating employee into CURRENT + FUTURE company
    closures so admins never have to re-save a closure (the re-save was the
    documented #290 workaround and silently deleted logged work).

    - Only closures whose end_date is today or later (PAST closures are NOT
      backfilled — an employee hired after a closure ended must not get
      retroactive absences, consistent with #193 _within_employment_window).
    - Only covered workdays within the employee's employment window: this
      function pre-filters on first_work_day, and the booking in
      _create_closure_absences additionally enforces first_work_day AND
      last_work_day per workday via _within_employment_window (#193/#195/#298).
    - delete_time_entries=False: never destroys logged work on those days.
    Best-effort: a failure here must not abort user creation (the closure
    enrolment can be repaired by re-saving the closure).
    """
    if not (user.receives_company_closures and user.is_active):
        return
    from app.models import CompanyClosure
    from app.routers.company_closures import _get_holidays_for_range, _get_workdays, _create_closure_absences

    # Honour the best-effort contract: a failure here must NOT abort the (already
    # committed) user create/update. Roll back the partial enrolment and log;
    # the gap can be repaired by re-saving the closure.
    try:
        today = today_local()
        closures = db.query(CompanyClosure).filter(
            CompanyClosure.tenant_id == current_user.tenant_id,  # F-026
            CompanyClosure.end_date >= today,
        ).all()
        for closure in closures:
            holidays = _get_holidays_for_range(
                db, closure.start_date, closure.end_date, current_user.tenant_id
            )
            workdays = _get_workdays(closure.start_date, closure.end_date, holidays)
            if user.first_work_day:
                workdays = [d for d in workdays if d >= user.first_work_day]
            if workdays:
                _create_closure_absences(
                    db, closure, workdays, [user], current_user, delete_time_entries=False
                )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("closure auto-enrollment failed for user %s", user.id, exc_info=True)


def _filtered_user_list_query(db: Session, current_user: User, include_inactive: bool, include_hidden: bool):
    """#219: shared user-list query for list_users + users_overview (#194 keeps them
    in sync). Returns the UNEXECUTED query so callers add their own .offset/.limit/.all.
    F-026: explicit tenant filter on top of RLS; active+visible by default."""
    query = db.query(User).filter(User.tenant_id == current_user.tenant_id)
    if not include_inactive:
        query = query.filter(User.is_active == True)  # noqa: E712
    if not include_hidden:
        query = query.filter(User.is_hidden == False)  # noqa: E712
    return query.order_by(User.last_name, User.first_name)


def _tenant_has_other_active_admin(db: Session, current_user: User) -> bool:
    """Audit A01 (4-Augen-Prinzip): does the caller's tenant have ANOTHER
    active admin besides ``current_user``?

    Used to gate self-approval of one's own change/vacation requests. A medical
    practice frequently runs with a single admin who legitimately must approve
    their own corrections — blocking that would lock them out. So the 4-eyes
    rule only bites when independent oversight is actually possible: a second
    active admin exists in the SAME tenant. F-026: explicit tenant scope.
    """
    return (
        db.query(User)
        .filter(
            User.tenant_id == current_user.tenant_id,
            User.role == UserRole.ADMIN,
            User.is_active == True,
            User.id != current_user.id,
        )
        .first()
        is not None
    )


# ── User Management ──────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserListResponse])
def list_users(
    include_inactive: bool = False,
    include_hidden: bool = False,
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List users (admin only). By default only active, visible users."""
    # F-026: belt-and-suspenders — RLS already scopes by tenant, but every
    # list endpoint must add the explicit filter so a missing GUC cannot
    # leak cross-tenant rows. (#219: shared with users_overview.)
    users = _filtered_user_list_query(
        db, current_user, include_inactive, include_hidden
    ).offset(skip).limit(limit).all()
    return users


@router.get("/users-overview", response_model=List[AdminUserOverview])
def users_overview(
    include_inactive: bool = False,
    include_hidden: bool = False,
    year: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#194: bulk vacation account + YTD overtime per user for the admin list.

    Same filtering as list_users (active + visible by default). Replaces the
    former per-user N+1 vacation fetch in the frontend with a single request.
    F-026: explicit tenant filter on top of RLS.
    """
    year = year or today_local().year
    users = _filtered_user_list_query(
        db, current_user, include_inactive, include_hidden
    ).all()

    is_current_year = (year == today_local().year)
    # #376 N+1-Vermeidung: der Tenant-Default wird EINMAL aufgelöst; die
    # per-User Absence⋈AbsenceReason-Verbrauchsquery entfällt komplett, solange
    # der Tenant keinen Grund mit tracks_child_sick_limit führt (der Regelfall).
    _cs_default = settings_service.get_int_setting(
        db, "child_sick_days_default", current_user.tenant_id, 15
    )
    _cs_tenant_tracks = db.query(AbsenceReason.id).filter(
        AbsenceReason.tenant_id == current_user.tenant_id,  # F-026
        AbsenceReason.tracks_child_sick_limit.is_(True),
    ).first() is not None
    # #204: Referenzdaten EINMAL vorladen statt pro User (× ~9 Queries) — Feiertage
    # (tenant+year, geteilt) + alle WorkingHoursChange (tenant, nach user_id
    # gruppiert) → an die Calc-Helfer durchreichen (Default-None-Pfad byte-identisch).
    # date_in_year (DATE-basiert, wie get_vacation_account/get_ytd_summary intern)
    # statt PublicHoliday.year — garantiert byte-identisch, unabhängig von der
    # year-Spalte.
    _holidays = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.tenant_id == current_user.tenant_id,  # F-026
        date_in_year(PublicHoliday.date, year),
    ).all()}
    _wh_by_user: dict = {}
    for _c in db.query(WorkingHoursChange).filter(
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from).all():
        _wh_by_user.setdefault(_c.user_id, []).append(_c)
    result = []
    for u in users:
        _uwh = _wh_by_user.get(u.id, [])
        vac = calculation_service.get_vacation_account(db, u, year, holidays=_holidays, wh_changes=_uwh)
        # #313: YTD-Überstunden bis zum letzten abgeschlossenen Arbeitstag — der
        # Stichtag ist nur im LAUFENDEN Jahr relevant; für vergangene Jahre voller
        # Jahresumfang (spart die per-User-Stichtag-Query). (round-2 N+1-Fix)
        cutoff = calculation_service.get_soll_cutoff_date(db, u) if is_current_year else None
        ytd = calculation_service.get_ytd_summary(db, u, year, cutoff_date=cutoff, holidays=_holidays, wh_changes=_uwh)
        # #377 § 2 Abs. 2 MiLoG: weiche Warnungen je MA. Nur in der LAUFENDEN-Jahr-
        # Ansicht (die Prüfung ist immer aktueller Monat / Aging bis heute). Perf:
        # EIN Overtime-Pass je Flag-MA — beide Signale aus demselben `detailed`.
        _milog_w: list[str] = []
        if is_current_year and u.milog_working_time_account and u.track_hours:
            _t = today_local()
            # #313 Saldo-Stichtag: den Stichtag durchreichen (Parität zum
            # MA-Dashboard, dashboard.py). Ohne cutoff trägt der laufende Monat
            # ein VOLLES Monats-Soll gegen einen nur monats-bis-heute-Ist → ein
            # Phantom-Defizit, das im FIFO die älteste (überfällige) Einlage
            # aufzehrt und die MILOG_SETTLEMENT_DUE-Warnung unterdrückt.
            _detailed = calculation_service.get_overtime_history_detailed(
                db, u, _t.year, _t.month, cutoff_date=cutoff
            )
            if _detailed:
                _cur = _detailed.get((_t.year, _t.month))
                _actual = _cur.actual if _cur is not None else 0.0
                _chk = milog_service.milog_50_check(db, u, _t.year, _t.month, monthly_actual=_actual)
                if _chk:
                    _milog_w.append(milog_service.milog_50_warning_text(_chk))
                _aging = milog_service.settlement_aging(db, u, _t, detailed=_detailed)
                if _aging and (_aging["overdue"] or _aging["due_soon"] or _aging.get("incomplete")):
                    _milog_w.append(milog_service.settlement_warning_text(_aging))
            # #377 Baustein 2b: weiche Plausibilitäts-Warnung für Fix-Modus-MA
            # (gleicher Saldo-Stichtag wie oben, #313-Parität zum MA-Dashboard).
            _exceeded = milog_service.monthly_exceeded_check(db, u, _t.year, _t.month, up_to_date=cutoff)
            if _exceeded:
                _milog_w.append(milog_service.monthly_exceeded_warning_text(_exceeded))
        result.append(AdminUserOverview(
            user_id=str(u.id),
            first_name=u.first_name,
            last_name=u.last_name,
            track_hours=u.track_hours,
            vacation=VacationAccount(
                year=year,
                budget_hours=vac["budget_hours"],
                budget_days=vac["budget_days"],
                used_hours=vac["used_hours"],
                used_days=vac["used_days"],
                remaining_hours=vac["remaining_hours"],
                remaining_days=vac["remaining_days"],
            ),
            overtime=YtdOvertime(year=year, **ytd),
            child_sick_used=(
                float(calculation_service.child_sick_days_used(db, u, year, wh_changes=_uwh))
                if _cs_tenant_tracks else 0.0
            ),  # #376
            child_sick_cap=(
                int(u.child_sick_days_per_year)
                if u.child_sick_days_per_year is not None else _cs_default
            ),  # #376
            milog_warnings=_milog_w,  # #377
        ))
    return result


@router.get("/users/deletion-candidates")
def get_deletion_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: List inactive users with anonymization/purge eligibility.

    F-055: Bulk-fetch the last entry date for all inactive users in a
    single GROUP BY instead of N+1 per-user lookups.
    """
    inactive_users = db.query(User).filter(
        User.is_active == False,
        User.tenant_id == current_user.tenant_id,  # F-026: explicit scope
    ).order_by(User.last_name, User.first_name).all()

    if not inactive_users:
        return []

    user_ids = [u.id for u in inactive_users]
    # One GROUP BY query — Postgres uses the (tenant_id, user_id, date)
    # composite index from migration 031 to answer this in O(log n).
    last_entry_rows = db.query(
        TimeEntry.user_id,
        func.max(TimeEntry.date).label("last_date"),
    ).filter(
        TimeEntry.tenant_id == current_user.tenant_id,
        TimeEntry.user_id.in_(user_ids),
    ).group_by(TimeEntry.user_id).all()
    last_entry_by_user = {row.user_id: row.last_date for row in last_entry_rows}

    today = today_local()
    result = []

    for user in inactive_users:
        last_entry_date = last_entry_by_user.get(user.id)
        days_since = (today - last_entry_date).days if last_entry_date else None
        is_anonymized = user.username.startswith("deleted_")

        # Grace-Period-Berechnung (14 Tage nach Deaktivierung)
        grace_period_remaining = None
        grace_period_ends = None
        in_grace_period = False
        if user.deactivated_at is not None:
            days_deactivated = (today - user.deactivated_at.date()).days
            if days_deactivated < 14:
                grace_period_remaining = 14 - days_deactivated
                grace_period_ends = (user.deactivated_at + timedelta(days=14)).date().isoformat()
                in_grace_period = True

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "is_anonymized": is_anonymized,
            "deactivated_at": user.deactivated_at.isoformat() if user.deactivated_at else None,
            "grace_period_ends": grace_period_ends,
            "grace_period_remaining_days": grace_period_remaining,
            "in_grace_period": in_grace_period,
            "last_entry_date": last_entry_date.isoformat() if last_entry_date else None,
            "days_since_last_entry": days_since,
            "can_anonymize": not is_anonymized and not in_grace_period,
            "can_purge": last_entry_date is None or (days_since is not None and days_since >= 730),
        })

    return result


@router.post("/users/{user_id}/anonymize")
def anonymize_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: Anonymize an inactive user in-place. Keeps time entries (ArbZG SS16 -- 2-year retention), deletes absences."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Benutzer muss zuerst deaktiviert werden (Art. 17 DSGVO)")
    if user.username.startswith("deleted_"):
        raise HTTPException(status_code=400, detail="Benutzer wurde bereits anonymisiert")

    # 14-Tage-Grace-Period: Anonymisierung erst nach Ablauf der Frist erlaubt
    if user.deactivated_at is not None:
        days_since_deactivation = (datetime.now(timezone.utc).date() - user.deactivated_at.date()).days
        if days_since_deactivation < 14:
            remaining = 14 - days_since_deactivation
            grace_end = (user.deactivated_at + timedelta(days=14)).strftime('%d.%m.%Y')
            raise HTTPException(
                status_code=400,
                detail=f"Sperrfrist läuft noch {remaining} Tag(e). Anonymisierung frühestens am {grace_end} möglich."
            )
    # If deactivated_at is None but user is inactive: allow anonymization (legacy user).
    # Der is_active-Fall ist bereits oben (vor der Grace-Period-Prüfung) abgefangen.

    user.first_name = "Gelöschter"
    user.last_name = "Benutzer"
    user.username = f"deleted_{str(user.id)[:8]}"
    user.email = None
    user.calendar_color = "#9CA3AF"
    # DSGVO Art. 17: clear biometric-equivalent data and security secrets
    user.profile_picture = None          # Base64-Lichtbild löschen (Art. 4 Nr. 1)
    user.totp_secret = None              # TOTP-Secret enthält kryptogr. Geheimnis
    user.totp_enabled = False
    user.last_totp_counter = None
    user.department = None               # Org-Zuordnung ist PII
    # Invalidate all sessions so the deactivated account cannot be re-entered
    user.token_version = (user.token_version or 0) + 1

    # Delete absences (no statutory retention requirement)
    db.query(Absence).filter(Absence.user_id == user.id, Absence.tenant_id == current_user.tenant_id).delete()

    log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user.id,
        changed_by=current_user.id,
        action="dsgvo_anonymize",
        source="dsgvo",
        new_note=f"DSGVO-Anonymisierung durch Admin {current_user.username}",
        tenant_id=current_user.tenant_id,
    )
    db.add(log)
    db.commit()

    return {"message": "Benutzer erfolgreich anonymisiert (Art. 17 DSGVO). Zeiteinträge bleiben für ArbZG §16 erhalten."}


@router.delete("/users/{user_id}/purge")
def purge_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: Permanently delete a user and all data. Only allowed after ArbZG SS16 retention period (730 days)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if user.is_active:
        raise HTTPException(status_code=400, detail="Benutzer muss zuerst deaktiviert werden")

    # ArbZG §16: 730-Tage-Aufbewahrung. Die jüngste aufbewahrungspflichtige
    # Aufzeichnung kann ein Zeiteintrag ODER eine Abwesenheit sein (z. B. Urlaub/
    # Krank nach dem letzten Stempel). Beide müssen die Frist überdauern, sonst
    # löscht der Purge noch pflichtige Daten vorzeitig (DSGVO-Audit M).
    last_te = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == current_user.tenant_id
    ).order_by(TimeEntry.date.desc()).first()
    last_abs = db.query(Absence).filter(
        Absence.user_id == user.id, Absence.tenant_id == current_user.tenant_id
    ).order_by(Absence.date.desc()).first()
    candidate_dates = [r.date for r in (last_te, last_abs) if r]
    if candidate_dates:
        latest = max(candidate_dates)
        days_since = (today_local() - latest).days
        if days_since < 730:
            raise HTTPException(
                status_code=409,
                detail=f"Aufbewahrungsfrist noch nicht abgelaufen. Jüngste Aufzeichnung: {latest.strftime('%d.%m.%Y')} ({days_since} Tage, Pflicht: 730 Tage gem. ArbZG §16)."
            )

    # Remove FK dependencies before deleting user.
    # changed_by is NOT NULL (migration 008) → we must NOT SET NULL (that raises a
    # NOT NULL IntegrityError and aborts the whole Art.17 erasure for any user who
    # has ever clocked out, since each clock_out writes an audit row with
    # changed_by = the employee's own id). Reassign other users' audit rows to the
    # acting admin instead — preserves the audit trail.
    # F-026: explicit tenant_id filter on every bulk op (CLAUDE.md rule —
    # RLS is belt-and-suspenders but the filter must be present in the query).
    # Delete the purged user's OWN audit log entries first (user_id == user.id).
    db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    db.flush()
    # Reassign the REMAINING rows this user authored on OTHER employees to the
    # acting admin. changed_by is part of the #121 tamper-evidence row_hash — a
    # bulk UPDATE bypasses the before_insert hook and leaves the stored hash stale,
    # so verify-integrity would wrongly flag these legitimate rows as 'tampered'
    # after every Art.17 purge of an editing admin. Load as ORM objects and
    # recompute the hash. SQLite-Tests fangen das NICHT (kein verify-after-purge).
    from app.core import audit_integrity
    for row in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.changed_by == user.id,
        TimeEntryAuditLog.tenant_id == current_user.tenant_id,
    ).all():
        row.changed_by = current_user.id
        row.row_hash = audit_integrity.compute_row_hash(row)

    # Audit after cleaning up the user's logs (use admin's own ID since target will be deleted)
    log = TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="dsgvo_purge",
        source="dsgvo",
        # DSGVO: KEIN Klarname im Audit-Log — der Zweck der Purge ist gerade die
        # Namenslöschung; ein Klarname hier konservierte ihn über die Aufbewahrungs-
        # frist hinaus. User-ID + Zeitstempel belegen die Compliance ausreichend.
        old_note=f"Endgültige Löschung von User-ID {user_id} durch Admin {current_user.username}",
        tenant_id=current_user.tenant_id,
    )
    db.add(log)
    db.flush()
    # Clean up vacation requests (F-026: explicit tenant scoping)
    from app.models.vacation_request import VacationRequest
    db.query(VacationRequest).filter(
        VacationRequest.user_id == user.id,
        VacationRequest.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    # Nullify reviewed_by references
    db.query(VacationRequest).filter(
        VacationRequest.reviewed_by == user.id,
        VacationRequest.tenant_id == current_user.tenant_id,
    ).update({"reviewed_by": None}, synchronize_session=False)
    db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == user.id, WorkingHoursChange.tenant_id == current_user.tenant_id).delete(synchronize_session=False)
    db.query(ChangeRequest).filter(ChangeRequest.user_id == user.id, ChangeRequest.tenant_id == current_user.tenant_id).delete(synchronize_session=False)
    # Nullify reviewed_by on OTHER users' change requests (nullable, no ON DELETE
    # rule → a raw user delete FK-violates on Postgres). Mirrors the
    # VacationRequest.reviewed_by nullify above.
    db.query(ChangeRequest).filter(
        ChangeRequest.reviewed_by == user.id,
        ChangeRequest.tenant_id == current_user.tenant_id,
    ).update({ChangeRequest.reviewed_by: None}, synchronize_session=False)
    db.query(TimeEntry).filter(TimeEntry.user_id == user.id, TimeEntry.tenant_id == current_user.tenant_id).delete(synchronize_session=False)
    db.query(Absence).filter(Absence.user_id == user.id, Absence.tenant_id == current_user.tenant_id).delete(synchronize_session=False)
    # #305 Schichtplanung: shift_plans.created_by is NOT NULL with no ON DELETE
    # rule → a raw user delete FK-violates on Postgres (SQLite tests run with FK
    # off, so this is Postgres-only). Reassign the user's plans to the acting
    # admin (preserves ownership/audit trail) and drop their assignments
    # explicitly (shift_assignments.user_id is ON DELETE CASCADE on Postgres, but
    # be explicit for SQLite). Both F-026 tenant-scoped.
    from app.models.shift_planning import ShiftPlan, ShiftAssignment, WorkstationQualification
    db.query(ShiftPlan).filter(
        ShiftPlan.created_by == user.id,
        ShiftPlan.tenant_id == current_user.tenant_id,
    ).update({ShiftPlan.created_by: current_user.id}, synchronize_session=False)
    db.query(ShiftAssignment).filter(
        ShiftAssignment.user_id == user.id,
        ShiftAssignment.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    # #305 M2d: workstation_qualifications.user_id is ON DELETE CASCADE on
    # Postgres, but delete explicitly for SQLite tests (FK off) + consistency.
    db.query(WorkstationQualification).filter(
        WorkstationQualification.user_id == user.id,
        WorkstationQualification.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    # company_closure.created_by is NOT NULL with no ON DELETE rule → reassign the
    # user's Betriebsferien to the acting admin (Postgres FK; SQLite tests run FK off).
    from app.models import CompanyClosure
    db.query(CompanyClosure).filter(
        CompanyClosure.created_by == user.id,
        CompanyClosure.tenant_id == current_user.tenant_id,
    ).update({CompanyClosure.created_by: current_user.id}, synchronize_session=False)
    # signup_tokens.user_id is NOT NULL with no ON DELETE rule and tokens are never
    # deleted by the signup flow (only consumed_at is set) → delete the purged
    # user's tokens explicitly. F-026 tenant-scoped.
    from app.models import SignupToken
    db.query(SignupToken).filter(
        SignupToken.user_id == user.id,
        SignupToken.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    # #370: impersonation_sessions has two users.id FKs (impersonator_id + target_id),
    # both ON DELETE CASCADE on Postgres. Delete explicitly for SQLite (FK off) and
    # to keep the erasure self-documenting. F-026 tenant-scoped.
    from app.models import ImpersonationSession
    db.query(ImpersonationSession).filter(
        (ImpersonationSession.impersonator_id == user.id)
        | (ImpersonationSession.target_id == user.id),
        ImpersonationSession.tenant_id == current_user.tenant_id,
    ).delete(synchronize_session=False)
    db.delete(user)
    db.commit()

    return {"message": "Benutzer und alle zugehörigen Daten wurden endgültig gelöscht (Art. 17 DSGVO)."}


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Get a specific user by ID (admin only)."""
    # _get_user_in_tenant raises 404 itself (never returns None) — the former
    # `if not user` guard here was dead code; the tenant scope is already enforced.
    return _get_user_in_tenant(db, user_id, current_user)


@router.post("/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create a new user (admin only)."""
    # F-026: usernames are unique per (tenant_id, username) — scope the
    # uniqueness probe to the caller's tenant so the same username can exist in
    # different tenants, and so the check does not silently depend on RLS.
    existing_user = db.query(User).filter(
        func.lower(User.username) == user_data.username.lower(),
        User.tenant_id == current_user.tenant_id,
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    # License: block creation when active-user count would exceed max_employees.
    # No-op when no license is loaded (SaaS / dev mode).
    active_count = (
        db.query(User)
        .filter(
            User.tenant_id == current_user.tenant_id,
            User.is_active == True,  # noqa: E712
        )
        .count()
    )
    check_employee_limit(active_count)

    # SaaS: plan-based seat limit. Onprem Default-Tenant has plan=enterprise
    # → unlimited, so this is effectively a no-op for on-prem installs.
    from app.models.tenant import Tenant
    from app.services.plan_enforcement import check_seat_limit
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is not None:
        check_seat_limit(db, tenant)

    new_user = User(
        username=user_data.username.lower(),
        email=user_data.email or None,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=user_data.role,
        weekly_hours=user_data.weekly_hours,
        vacation_days=user_data.vacation_days,
        work_days_per_week=user_data.work_days_per_week,
        track_hours=user_data.track_hours,
        calendar_color=user_data.calendar_color,
        use_daily_schedule=user_data.use_daily_schedule,
        hours_monday=user_data.hours_monday,
        hours_tuesday=user_data.hours_tuesday,
        hours_wednesday=user_data.hours_wednesday,
        hours_thursday=user_data.hours_thursday,
        hours_friday=user_data.hours_friday,
        password_hash=auth_service.hash_password(user_data.password),
        is_active=True,
        exempt_from_arbzg=user_data.exempt_from_arbzg,
        is_night_worker=user_data.is_night_worker,
        receives_company_closures=user_data.receives_company_closures,
        first_work_day=user_data.first_work_day,
        last_work_day=user_data.last_work_day,
        department=user_data.department,
        child_sick_days_per_year=user_data.child_sick_days_per_year,  # #376
        milog_working_time_account=user_data.milog_working_time_account,  # #377
        agreed_monthly_hours=user_data.agreed_monthly_hours,  # #377 Baustein 2a
        scheduled_start_monday=user_data.scheduled_start_monday,
        scheduled_end_monday=user_data.scheduled_end_monday,
        scheduled_start_tuesday=user_data.scheduled_start_tuesday,
        scheduled_end_tuesday=user_data.scheduled_end_tuesday,
        scheduled_start_wednesday=user_data.scheduled_start_wednesday,
        scheduled_end_wednesday=user_data.scheduled_end_wednesday,
        scheduled_start_thursday=user_data.scheduled_start_thursday,
        scheduled_end_thursday=user_data.scheduled_end_thursday,
        scheduled_start_friday=user_data.scheduled_start_friday,
        scheduled_end_friday=user_data.scheduled_end_friday,
        tenant_id=current_user.tenant_id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # #290: enrol the new participant into existing current/future closures now,
    # so the admin never needs the data-destroying closure re-save workaround.
    _enroll_user_in_open_closures(db, new_user, current_user)
    db.commit()

    return UserCreateResponse(
        user=UserResponse.model_validate(new_user)
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user data (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if user_data.username and user_data.username.lower() != user.username.lower():
        # F-026: scope the uniqueness probe to the tenant (parity with
        # create_user) — usernames are unique per tenant, not globally.
        existing = db.query(User).filter(
            func.lower(User.username) == user_data.username.lower(),
            User.tenant_id == current_user.tenant_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    update_data = user_data.model_dump(exclude_unset=True)
    update_data.pop('is_active', None)  # Prevent bypassing the dedicated deactivate endpoint

    # VULN-010: invalidate existing JWTs when role is changed
    role_changed = 'role' in update_data and update_data['role'] != user.role
    # #290: did this update turn closure participation ON? Then enrol below.
    closures_enabled = (
        update_data.get('receives_company_closures') is True
        and not user.receives_company_closures
    )

    for field, value in update_data.items():
        setattr(user, field, value)

    if role_changed:
        user.token_version = (user.token_version or 0) + 1

    db.commit()
    db.refresh(user)

    # #290: a user newly toggled into Betriebsferien-participation is enrolled
    # into current/future closures here (never deletes logged work), so no
    # closure re-save is needed.
    if closures_enabled:
        _enroll_user_in_open_closures(db, user, current_user)
        db.commit()
    return user


@router.post("/users/{user_id}/set-password")
def set_password(
    user_id: str,
    body: AdminSetPassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Set a new password for a user (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.password_hash = auth_service.hash_password(body.password)
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()

    return {"message": f"Passwort für {user.first_name} {user.last_name} wurde gesetzt"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Deactivate a user (soft delete, admin only)."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst deaktivieren")

    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()
    return None


@router.post("/users/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Reactivate a previously deactivated user (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Seat-limit enforcement: a reactivation is logically a seat add.
    from app.models.tenant import Tenant
    from app.services.plan_enforcement import check_seat_limit
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is not None:
        check_seat_limit(db, tenant)

    user.is_active = True
    user.deactivated_at = None
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/toggle-hidden", response_model=UserResponse)
def toggle_hidden_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Toggle the is_hidden flag for a user (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.is_hidden = not user.is_hidden
    db.commit()
    db.refresh(user)
    return user


# ── Working Hours Changes ────────────────────────────────────────────────

@router.get("/users/{user_id}/working-hours-changes", response_model=List[WorkingHoursChangeResponse])
def list_working_hours_changes(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get working hours change history for a user (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from.desc()).all()
    return changes


@router.post("/users/{user_id}/working-hours-changes", response_model=WorkingHoursChangeResponse, status_code=status.HTTP_201_CREATED)
def create_working_hours_change(
    user_id: str,
    change_data: WorkingHoursChangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new working hours change for a user (admin only)."""
    user = _get_user_in_tenant(db, user_id, current_user)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Fix #2: a WorkingHoursChange only feeds get_weekly_hours_for_date, which
    # get_daily_target_for_date IGNORES when use_daily_schedule=True (it reads
    # hours_monday…friday instead). Writing such a row would have NO effect on
    # the Soll while the UI still showed the new value → silently wrong §16
    # records. Reject it instead of historising the per-weekday columns (which
    # would be a separate, larger feature).
    if getattr(user, "use_daily_schedule", False):
        raise HTTPException(
            status_code=400,
            detail=(
                "Für Mitarbeitende mit individuellem Tagesplan wird die "
                "Stunden-Historie nicht unterstützt — bitte die Tagesstunden "
                "direkt im Mitarbeiter-Profil ändern."
            ),
        )

    existing = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from == change_data.effective_from
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Eine Stundenänderung für den {change_data.effective_from.strftime('%d.%m.%Y')} existiert bereits"
        )

    change = WorkingHoursChange(
        user_id=user_id,
        tenant_id=current_user.tenant_id,
        effective_from=change_data.effective_from,
        weekly_hours=change_data.weekly_hours,
        note=change_data.note
    )
    db.add(change)

    if change_data.effective_from <= today_local():
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= today_local()
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        if most_recent:
            user.weekly_hours = most_recent.weekly_hours

    db.commit()
    db.refresh(change)
    return change


@router.delete("/users/{user_id}/working-hours-changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_working_hours_change(
    user_id: str,
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a working hours change (admin only)."""
    # F-026: explicit tenant filter on the .delete() lookup (it runs before the
    # _get_user_in_tenant validation below, so RLS would be the only guard).
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_id,
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,
    ).first()

    if not change:
        raise HTTPException(status_code=404, detail="Stundenänderung nicht gefunden")

    user = _get_user_in_tenant(db, user_id, current_user)
    db.delete(change)
    db.commit()

    most_recent = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from <= today_local()
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if most_recent:
        user.weekly_hours = most_recent.weekly_hours
        db.commit()

    return None
