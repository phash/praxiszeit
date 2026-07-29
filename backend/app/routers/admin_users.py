"""Admin sub-router: User Management + Working Hours Changes."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, NamedTuple, Optional
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from pydantic import ValidationError
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, TimeEntry, Absence, AbsenceReason, WorkingHoursChange, ChangeRequest, TimeEntryAuditLog, UserRole, PublicHoliday
from app.services.date_filters import date_in_year
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword, UserListResponse
from app.schemas.working_hours_change import WorkingHoursChangeCreate, WorkingHoursChangeResponse, WorkingHoursChangePreview
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


def _log_wh_change_retarget(
    db: Session,
    *,
    user: User,
    admin: User,
    tenant_id,
    effective_from: date,
    period_end: date,
    adjusted_absences: int,
    prefix: str,
    suffix: str,
) -> None:
    """Minor 1 (Review-Fund): shared ``TimeEntryAuditLog`` builder for the two
    ``retarget_absence_hours``-triggered audit rows in
    ``create_working_hours_change`` and ``delete_working_hours_change`` — the
    two call sites only differ in the German note wording (``prefix``/
    ``suffix``), everything else (action, source, actor/subject wiring) was
    duplicated near-verbatim before. No-op when nothing was actually
    adjusted, so callers can call this unconditionally without an
    ``if adjusted_absences:`` guard of their own.

    ``source="wh_change"`` is 9 characters, well under the
    ``varchar(40)`` column limit (CLAUDE.md).
    """
    if not adjusted_absences:
        return
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user.id,
        changed_by=admin.id,
        action="update",
        source="wh_change",
        new_note=(
            f"{prefix} zum {effective_from.isoformat()}: "
            f"{adjusted_absences} Abwesenheit(en) im Zeitraum "
            f"{effective_from.isoformat()}–{period_end.isoformat()} {suffix}"
        ),
        tenant_id=tenant_id,
    ))


def _comparable_snapshot(weekly_hours, use_daily_schedule, day_hours, work_days_per_week):
    """#431: der Vertrags-Snapshot als vergleichbares Tupel.

    Verglichen wird, was das SOLL treibt. Im gleichmaessigen Modus sind die
    Tageswerte inert — ``get_daily_target_for_date`` liest sie dort gar nicht.
    Sie werden deshalb ausgeblendet: ``update_user`` raeumt sie beim Abschalten
    des Tagesplans nicht ab, und ein solcher Rest darf keine Basis-Zeile
    ausloesen, wo vor #431 keine entstanden waere (Byte-Identitaet fuer
    Mitarbeitende ohne Tagesplan).

    ``work_days_per_week`` bleibt immer im Vergleich: es treibt im
    gleichmaessigen Modus das Tagessoll und in beiden Modi den
    Urlaubsanspruch.
    """
    use_daily_schedule = bool(use_daily_schedule)
    return (
        Decimal(str(weekly_hours)),
        use_daily_schedule,
        tuple(
            None if v is None else Decimal(str(v)) for v in day_hours
        ) if use_daily_schedule else (None,) * 5,
        int(work_days_per_week),
    )


class _NormalisedSchedule(NamedTuple):
    """#431: die fertig normalisierte Snapshot-Eingabe — genau die vier Werte,
    die eine ``WorkingHoursChange``-Zeile ausmachen."""

    weekly_hours: float
    use_daily_schedule: bool
    day_hours: tuple          # (Mo, Di, Mi, Do, Fr), je Optional[float]
    work_days_per_week: int


def _normalise_schedule_input(
    change_data: WorkingHoursChangeCreate, user: User
) -> _NormalisedSchedule:
    """#431: DIE eine Normalisierung der Snapshot-Eingabe — genutzt vom
    Schreibpfad ``create_working_hours_change`` UND von der Vorschau.

    Die fachliche REGEL selbst (Modi schließen einander aus, im Tagesplan-Modus
    ist ``weekly_hours`` die Summe der Tageswerte) lebt unverändert in
    ``WorkingHoursChangeCreate.check_mode`` — deshalb nimmt dieser Helfer ein
    bereits validiertes Create-Schema entgegen. Die Vorschau baut sich eins aus
    ihren Query-Parametern, statt die Regel ein zweites Mal zu formulieren: zwei
    Implementierungen derselben Regel divergieren garantiert (#394/1.14.3 hat
    dieses Projekt genau diese Fehlerklasse schon einmal gekostet — dort wich
    ein Vorab-Check von der Buchung ab und lehnte gültige Eingaben mit 400 ab).

    Hier lebt der eine Teil, den das Schema NICHT abdecken kann, weil er den
    Mitarbeitenden kennen muss: der Rückfall von ``work_days_per_week`` auf die
    User-Zeile. NULL hieße „Rückfall auf die (jederzeit änderbare) User-Zeile" —
    der Snapshot wäre dann unvollständig. Vorher stand dieser Rückfall zweimal
    wörtlich im Schreibpfad und hätte in der Vorschau ein drittes Mal
    entstehen müssen.
    """
    return _NormalisedSchedule(
        weekly_hours=change_data.weekly_hours,
        use_daily_schedule=bool(change_data.use_daily_schedule),
        day_hours=(
            change_data.hours_monday,
            change_data.hours_tuesday,
            change_data.hours_wednesday,
            change_data.hours_thursday,
            change_data.hours_friday,
        ),
        work_days_per_week=int(
            change_data.work_days_per_week or user.work_days_per_week
        ),
    )


def _sync_user_from_change(user: User, most_recent: WorkingHoursChange) -> None:
    """#431: den VOLLSTÄNDIGEN Vertrags-Snapshot einer ``WorkingHoursChange``
    auf die User-Zeile zurückspiegeln.

    Gemeinsam genutzt von ``create_working_hours_change`` (nach dem Anlegen
    der neuen Zeile) und ``delete_working_hours_change`` (Task 6, nach dem
    Entfernen einer Zeile): beide Schreibpfade müssen denselben vollständigen
    Snapshot zurückschreiben. Nur `weekly_hours` nachzuziehen kippte den
    Mitarbeitenden still in den jeweils anderen Modus: eine Tagesplan-Zeile
    ließe `use_daily_schedule=False` stehen (Soll käme aus
    weekly_hours/work_days_per_week statt aus den Wochentagen), eine
    gleichmäßige Zeile ließe die alten Tageswerte stehen (Soll käme weiter aus
    ihnen).

    Die Spiegelung ist BEWUSST bedingungslos — auch bei einem Mitarbeitenden,
    der nie einen Tagesplan hatte. `update_user` räumt `hours_*` beim
    Abschalten des Tagesplans nicht ab, solche Reste sind im gleichmäßigen
    Modus rechnerisch inert (das Tagessoll liest sie dort nicht), aber sie
    widersprechen dem Snapshot der aktuell gültigen Zeile. Eine „nur im
    Tagesplan-Modus schreiben"-Variante ließe die User-Zeile in einem Zustand
    zurück, den keine Historien-Zeile deckt — und genau daraus entstand der
    #431-Bug.
    """
    user.weekly_hours = most_recent.weekly_hours
    user.use_daily_schedule = bool(most_recent.use_daily_schedule)
    user.hours_monday = most_recent.hours_monday
    user.hours_tuesday = most_recent.hours_tuesday
    user.hours_wednesday = most_recent.hours_wednesday
    user.hours_thursday = most_recent.hours_thursday
    user.hours_friday = most_recent.hours_friday
    # Bestandszeilen von vor #431 können hier NULL tragen —
    # `users.work_days_per_week` ist NOT NULL und darf das nicht erben.
    if most_recent.work_days_per_week is not None:
        user.work_days_per_week = most_recent.work_days_per_week


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
                # Nach JEDER Schliessung flushen: `_create_closure_absences` laedt die
                # bereits belegten Tage per Query. Ohne Flush sieht der naechste
                # Durchlauf die eben angelegten Zeilen nicht, und bei zwei
                # UEBERLAPPENDEN Betriebsferien landeten zwei VACATION-Zeilen auf
                # demselben Tag im selben Insert-Batch -> uq_tenant_user_date_type
                # -> HTTP 500 beim Anlegen eines Mitarbeiters. Reproduzierbar von der
                # E2E-Suite ausgeloest, die mehrere ueberlappende Schliessungen anlegt.
                db.flush()
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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)
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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)
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
        use_fixed_monthly_target=user_data.use_fixed_monthly_target,  # #377 Baustein 2b
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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    update_data = user_data.model_dump(exclude_unset=True)

    # #431: ALLE Soll-Treiber laufen ueber den Stundenverlauf mit Wirkungsdatum.
    # Frueher war nur `weekly_hours` gesperrt (und selbst das mit einer Ausnahme
    # fuer Tagesplan-Mitarbeitende, weil es fuer sie keinen Schreibweg gab).
    # Tagesplan, Modus und Arbeitstage waren dagegen voellig offen — jede
    # Aenderung verschob still das Soll der gesamten Vergangenheit. Genau diese
    # Luecke ist #431.
    #
    # Task 5 (Wochenstunden-Anpassen): weekly_hours hat genau EINEN Schreibweg
    # — "Wochenstunden anpassen" mit Wirkungsdatum (create_working_hours_change),
    # das eine Historie-Zeile anlegt. user.weekly_hours ist zugleich der
    # Rückfallwert für ALLE Tage vor der ersten erfassten Änderung
    # (get_weekly_hours_for_date); ein direktes PUT würde das Feld still
    # überschreiben und damit rückwirkend das Soll bereits abgeschlossener
    # Monate verschieben, ohne Historie/Absence-Retarget. Muss VOR jedem
    # Schreibzugriff greifen (kein setattr, kein commit vorher) — deshalb hier,
    # ganz am Anfang. POST /api/admin/users (create_user) bleibt unverändert:
    # dort existiert noch keine Historie, die verletzt werden könnte.
    #
    # Task 7: die I2-Ausnahme ("weekly_hours per PUT erlaubt, wenn
    # use_daily_schedule") entfällt ersatzlos. Sie existierte nur, weil es für
    # Tagesplan-Mitarbeitende bis Task 6 keinen anderen Schreibweg gab — seit
    # Task 6 nimmt der Stundenverlauf-Endpoint auch ihre Änderungen an
    # (vollständiger Vertrags-Snapshot). Damit gilt für sie dieselbe Sperre wie
    # für alle anderen, und die Sperre wird auf die übrigen sieben
    # historisierten Felder ausgeweitet (use_daily_schedule, work_days_per_week,
    # hours_monday…friday) — sonst kippte ein PUT still den Modus oder die
    # Tagesverteilung, ohne Historien-Zeile und ohne Absence-Retarget.
    _HISTORISED_FIELDS = (
        'weekly_hours', 'use_daily_schedule', 'work_days_per_week',
        'hours_monday', 'hours_tuesday', 'hours_wednesday',
        'hours_thursday', 'hours_friday',
    )
    if any(f in update_data for f in _HISTORISED_FIELDS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Wochenstunden, Tagesstunden und Arbeitstage werden über "
                "„Wochenstunden anpassen“ mit Wirkungsdatum geändert, damit "
                "Historie und Soll vergangener Monate korrekt bleiben."
            ),
        )

    if user_data.username and user_data.username.lower() != user.username.lower():
        # F-026: scope the uniqueness probe to the tenant (parity with
        # create_user) — usernames are unique per tenant, not globally.
        existing = db.query(User).filter(
            func.lower(User.username) == user_data.username.lower(),
            User.tenant_id == current_user.tenant_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")

    update_data.pop('is_active', None)  # Prevent bypassing the dedicated deactivate endpoint

    # #377 Baustein 2b (Release-Review 1.15.0): the UserUpdate schema validator
    # (check_fixed_monthly_target_requirements) only sees THIS payload, not the
    # persisted row — a partial PUT that isolates e.g.
    # {"milog_working_time_account": false} leaves use_fixed_monthly_target
    # absent from the payload (None → skipped by the schema validator) while
    # the DB row still has it True. That silently produces an INVALID row
    # (fixed Soll active but its prerequisites off), so we must check the
    # EFFECTIVE post-update state here (payload value if present, else the
    # current DB value) — mirrors the schema validator's requirement logic 1:1
    # so create and update agree.
    eff_fixed = update_data.get('use_fixed_monthly_target', user.use_fixed_monthly_target)
    if eff_fixed:
        eff_milog = update_data.get('milog_working_time_account', user.milog_working_time_account)
        eff_track_hours = update_data.get('track_hours', user.track_hours)
        eff_agreed = update_data.get('agreed_monthly_hours', user.agreed_monthly_hours)
        if not eff_agreed or eff_agreed <= 0:
            raise HTTPException(
                status_code=400,
                detail="Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0)."
            )
        if eff_track_hours is not True:
            raise HTTPException(
                status_code=400,
                detail="Fester Monats-Soll setzt Stundenzählung (track_hours) voraus."
            )
        if eff_milog is not True:
            raise HTTPException(
                status_code=400,
                detail="Fester Monats-Soll setzt das MiLoG-Arbeitszeitkonto voraus."
            )

    # Release-Review 1.16.0: Beschäftigungsfenster und Soll-Zeit-Fenster ebenfalls
    # gegen den EFFEKTIVEN Zustand prüfen, nicht nur gegen den Payload.
    # `validate_employment_and_window_order` im Schema sieht nur die mitgeschickten
    # Felder: ein Partial-PUT mit ausschliesslich `last_work_day` kommt an ihm vorbei
    # (first_work_day ist dort None) und schreibt first > last in die DB. Danach
    # wirft der `UserResponse`-Validator beim SERIALISIEREN — also erst in der
    # Antwort und anschliessend bei jedem weiteren Endpoint, der den Nutzer
    # ausliefert (500, Benutzerliste unbenutzbar). Gleiches Muster wie beim
    # eff_fixed-Block oben.
    _eff = lambda name: update_data.get(name, getattr(user, name, None))  # noqa: E731
    _eff_first, _eff_last = _eff('first_work_day'), _eff('last_work_day')
    if _eff_first and _eff_last and _eff_first > _eff_last:
        raise HTTPException(
            status_code=400,
            detail="Erster Arbeitstag darf nicht nach dem letzten Arbeitstag liegen.",
        )
    for _wd, _label in (
        ('monday', 'Montag'), ('tuesday', 'Dienstag'), ('wednesday', 'Mittwoch'),
        ('thursday', 'Donnerstag'), ('friday', 'Freitag'),
    ):
        _s, _e = _eff(f'scheduled_start_{_wd}'), _eff(f'scheduled_end_{_wd}')
        if _s and _e and _s >= _e:
            raise HTTPException(
                status_code=400,
                detail=f"{_label}: Soll-Beginn muss vor dem Soll-Ende liegen.",
            )

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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    user.password_hash = auth_service.hash_password(body.password)
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()

    return {"message": f"Passwort für {user.first_name} {user.last_name} wurde gesetzt"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Deactivate a user (soft delete, admin only)."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst deaktivieren")

    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.token_version += 1  # Invalidate all existing tokens
    db.commit()
    return None


@router.post("/users/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Reactivate a previously deactivated user (admin only)."""
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

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
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    # Fix #2 — die frueher hier stehende 400-Sperre fuer Tagesplan-Mitarbeitende
    # ist mit #431 ENTFALLEN.
    #
    # Sie existierte, weil eine WorkingHoursChange nur get_weekly_hours_for_date
    # speiste und das Tagessoll die bei use_daily_schedule=True komplett
    # ignorierte (es las live hours_monday…friday): die Zeile war fuers Soll
    # wirkungslos, waehrend die UI den neuen Wert zeigte → still falscher
    # §16-Beleg. Lieber gar keine Historie als eine wirkungslose.
    #
    # Seit #431 traegt die Zeile den VOLLSTAENDIGEN Vertrags-Snapshot
    # (use_daily_schedule + hours_monday…friday + work_days_per_week), dieser
    # Endpoint schreibt ihn (siehe unten), und get_daily_target_for_date rechnet
    # gegen den datumsaufgeloesten Snapshot — die Zeile verschiebt das Soll
    # dieser Gruppe also nachweislich (Test
    # test_wh_change_day_plan_create.py::test_change_actually_moves_the_daily_target).
    # Damit ist die Begruendung der Sperre weg.

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

    # #431: die Eingabe wird ab hier ausschliesslich ueber `norm` gelesen —
    # dieselbe Normalisierung, die auch die Vorschau benutzt. Sonst muesste der
    # `work_days_per_week`-Rueckfall an drei Stellen wortgleich stehen (zweimal
    # hier, einmal dort) und wuerde irgendwann auseinanderlaufen.
    norm = _normalise_schedule_input(change_data, user)

    # Release-Review 1.16.0 (#415-Folgefund): Bevor die ERSTE Änderung eines
    # Mitarbeiters gespeichert wird, den bisherigen Vertragswert als Basis-Zeile
    # festhalten.
    #
    # Hintergrund: `get_weekly_hours_for_date` fällt für jeden Tag VOR der ersten
    # erfassten Änderung auf `user.weekly_hours` zurück. Genau dieses Feld wird
    # weiter unten überschrieben, sobald das Wirkungsdatum <= heute liegt — und
    # das ist der Default des Stundenverlauf-Dialogs. Ohne Basis-Zeile galt der
    # NEUE Wert damit rückwirkend für die gesamte Vergangenheit: das Per-Tag-Soll
    # bereits abgeschlossener Monate verschob sich still, und #415 konnte die
    # Änderung nicht ausweisen (beide Segmente trugen denselben Wert und wurden
    # verschmolzen). Die Basis-Zeile friert die Vergangenheit auf dem alten Wert
    # ein und macht die Änderung im Bericht sichtbar.
    #
    # Datum: das FRÜHESTE aus `first_work_day`, der ältesten vorhandenen
    # Buchung (TimeEntry/Absence) und dem Vortag der Änderung — die Basis-Zeile
    # muss die gesamte erfassbare Vergangenheit abdecken.
    #
    # I5 (Abschluss-Review): vorher stand hier nur
    # `first_work_day or (effective_from - 1 Tag)`. `first_work_day` ist nullable
    # und in der Praxis oft leer — dann deckte die Basis-Zeile GENAU EINEN Tag
    # ab, und alles davor fiel wieder auf `user.weekly_hours` zurück, das
    # derselbe Request gleich darunter auf den NEUEN Wert setzt. Das Soll aller
    # früheren Monate verschob sich damit still: exakt der Bug, den die
    # Basis-Zeile verhindern soll.
    #
    # Nur wenn sich der Wert tatsächlich ändert (sonst entstünde eine
    # Pseudo-Änderung, die weekly_hours_segments ohnehin wieder verschmelzen
    # würde).
    #
    # #431: verglichen wird der VOLLSTÄNDIGE Snapshot, nicht mehr nur
    # `weekly_hours`. Bei einem Tagesplan-Mitarbeitenden kann die Wochensumme
    # gleich bleiben, während sich die Verteilung über die Wochentage (oder der
    # Modus selbst) ändert — ohne Basis-Zeile gälte die neue Verteilung
    # rückwirkend für die gesamte Vergangenheit.
    _has_history = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).first() is not None
    _current = None
    if not _has_history:
        # Ohne Historie liefert der Resolver zwangslaeufig die User-Felder —
        # wir gehen trotzdem ueber ihn, damit die eingefrorene Vergangenheit
        # per Konstruktion das ist, was er selbst aufloesen wuerde.
        _current = calculation_service.get_schedule_for_date(
            db, user, change_data.effective_from - timedelta(days=1)
        )
    if _current is not None and _comparable_snapshot(
        _current.weekly_hours, _current.use_daily_schedule,
        _current.day_hours, _current.work_days_per_week,
    ) != _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule,
        norm.day_hours, norm.work_days_per_week,
    ):
        # Der Vortag ist immer dabei → das Ergebnis liegt garantiert VOR
        # `effective_from` (die frühere Zusatz-Klemme ist damit überflüssig).
        _baseline_candidates = [change_data.effective_from - timedelta(days=1)]
        if user.first_work_day:
            _baseline_candidates.append(user.first_work_day)
        _oldest_entry = db.query(func.min(TimeEntry.date)).filter(
            TimeEntry.user_id == user_id,
            TimeEntry.tenant_id == current_user.tenant_id,  # F-026
        ).scalar()
        if _oldest_entry:
            _baseline_candidates.append(_oldest_entry)
        _oldest_absence = db.query(func.min(Absence.date)).filter(
            Absence.user_id == user_id,
            Absence.tenant_id == current_user.tenant_id,  # F-026
        ).scalar()
        if _oldest_absence:
            _baseline_candidates.append(_oldest_absence)
        _baseline_date = min(_baseline_candidates)
        # Die Basis-Zeile schreibt `_current` UNVERÄNDERT fort — also exakt das,
        # was `get_schedule_for_date` für die Vergangenheit bisher aufgelöst hat.
        # Nur so bleibt die Vergangenheit byte-identisch eingefroren.
        db.add(WorkingHoursChange(
            user_id=user_id,
            tenant_id=current_user.tenant_id,
            effective_from=_baseline_date,
            weekly_hours=_current.weekly_hours,
            use_daily_schedule=_current.use_daily_schedule,
            hours_monday=_current.day_hours[0],
            hours_tuesday=_current.day_hours[1],
            hours_wednesday=_current.day_hours[2],
            hours_thursday=_current.day_hours[3],
            hours_friday=_current.day_hours[4],
            work_days_per_week=_current.work_days_per_week,
            note="Automatisch erfasster Ausgangswert vor der ersten Stundenänderung",
        ))

    change = WorkingHoursChange(
        user_id=user_id,
        tenant_id=current_user.tenant_id,
        effective_from=change_data.effective_from,
        weekly_hours=norm.weekly_hours,
        use_daily_schedule=norm.use_daily_schedule,
        hours_monday=norm.day_hours[0],
        hours_tuesday=norm.day_hours[1],
        hours_wednesday=norm.day_hours[2],
        hours_thursday=norm.day_hours[3],
        hours_friday=norm.day_hours[4],
        # NULL hieße „Rückfall auf die (jederzeit änderbare) User-Zeile" — das
        # Modell verlangt für neue Zeilen einen gesetzten Wert, damit der
        # Snapshot vollständig ist (der Rückfall steckt in
        # _normalise_schedule_input, gemeinsam mit der Vorschau).
        work_days_per_week=norm.work_days_per_week,
        note=change_data.note
    )
    db.add(change)
    # Finding 4 (Review 2026-07-14): the session is autoflush=False. Without an
    # explicit flush here, the most-recent self-query below (which also filters
    # on WorkingHoursChange) would not see the row just added — the first
    # past-dated change would leave user.weekly_hours unchanged, and a second,
    # superseding past-dated change would pick up the PREVIOUS committed row
    # instead of itself. delete_working_hours_change already commits before its
    # analogous re-query; flush gives create the same guarantee without an
    # early partial commit.
    db.flush()

    if change_data.effective_from <= today_local():
        most_recent = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= today_local()
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
        if most_recent:
            # #431: der VOLLSTÄNDIGE Snapshot wandert zurück auf die User-Zeile
            # — _sync_user_from_change (dort ausführlich begründet) ist DIE eine
            # Stelle dafür, damit create und delete garantiert denselben
            # Zustand herstellen. Der Vergleich für die Basis-Zeile ignoriert
            # etwaige Tagesplan-Reste trotzdem (_comparable_snapshot), damit
            # hier keine Pseudo-Änderung entsteht.
            _sync_user_from_change(user, most_recent)

    # Task 3 (#Wochenstunden-Dialog): eine Änderung muss die bereits gebuchten
    # Abwesenheits-Stunden mitziehen — sonst schreibt z. B. ein Krankentag
    # weiterhin die ALTEN Stunden dem Ist gut, während das Soll desselben Tages
    # sich durch die eben gespeicherte Änderung schon verschoben hat.
    # retarget_absence_hours ist DIE eine Stelle dafür (siehe dortige
    # Docstring-Begründung), retarget_window DIE eine Stelle für das Fenster —
    # kein zweiter Rechenpfad hier.
    #
    # retarget_absence_hours liest das neue Tagessoll über
    # get_weekly_hours_for_date, die ihrerseits die WorkingHoursChange-Zeile aus
    # der DB liest — der `db.flush()` weiter oben macht die eben angelegte Zeile
    # (und ggf. die Basis-Zeile) für diese Abfrage sichtbar, bevor hier
    # gerechnet wird.
    #
    # Release-Review 1.17.0: Hier stand früher „nur rückwirkend (effective_from
    # < heute); ein Datum ab heute betrifft ausschließlich künftige, noch nicht
    # gebuchte Tage." Das war sachlich FALSCH — `create_absence` hat keine
    # Zukunftssperre, genehmigte Urlaubsanträge, Betriebsferien und geplante
    # Fortbildungen werden routinemäßig im Voraus gebucht, und ein Wirkungsdatum
    # in der Zukunft ist der Regelfall dieses Dialogs. Auslöser ist deshalb
    # nicht mehr das Datum, sondern „es gibt eine betroffene Abwesenheit im
    # Wirkungsbereich".
    window = calculation_service.retarget_window(db, user, change_data.effective_from)
    adjusted_absences = 0
    if window.has_absences:
        adjusted_absences = calculation_service.retarget_absence_hours(
            db, user, window.start, window.end
        )
        _log_wh_change_retarget(
            db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
            effective_from=window.start, period_end=window.end,
            adjusted_absences=adjusted_absences,
            prefix="Wochenstunden-Änderung",
            suffix="auf neues Tagessoll nachgezogen",
        )
    # Fix #5-Warnung (nicht-blockierend): berührt der Wirkungsbereich ein Jahr,
    # dessen Jahresabschluss bereits lief, ist der eingefrorene Carryover des
    # Folgejahres jetzt veraltet — wir rechnen ihn NICHT automatisch neu (könnte
    # manuelle Anpassungen überschreiben), sondern melden es nur. Bewusst
    # UNABHÄNGIG vom Retarget: die Änderung verschiebt das Per-Tag-SOLL jedes
    # Arbeitstags im Wirkungsbereich, nicht nur das der Abwesenheitstage.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id,
        range(window.start.year, window.end.year + 1),
    )

    db.commit()
    db.refresh(change)
    change.adjusted_absences = adjusted_absences
    change.warning = warning
    return change


def _planned_day_mean(day_targets: List[float]) -> float:
    """#431: Mittel der Tage mit Soll > 0 (``0.0``, wenn keiner).

    Der eine Skalar bleibt Teil der API (``current_daily_target`` /
    ``new_daily_target``). Bewusst NICHT der Mittelwert über alle fünf
    Wochentage: bei einem Tagesplan Mo 8 / Di 5 / Mi 4 zöge ein freier
    Donnerstag/Freitag die Zahl auf 3,4 h herunter — ein Wert, den kein
    Arbeitstag dieser Woche hat.
    """
    planned = [t for t in day_targets if t > 0]
    if not planned:
        return 0.0
    return round(sum(planned) / len(planned), 2)


def _schedule_input_error(exc: ValidationError) -> str:
    """Die Meldung des ``check_mode``-Validators als Klartext für
    ``blocked_reason`` (Pydantic stellt ``Value error, `` voran).

    Der Fallback ist kein toter Code-Schmuck: dieser Endpoint läuft bei JEDER
    Eingabe im Dialog (debounced), ein IndexError hier wäre ein HTTP 500 mitten
    im Tippen.
    """
    errors = exc.errors()
    if not errors:
        return "Ungültige Eingabe"
    return str(errors[0].get("msg", "Ungültige Eingabe")).removeprefix("Value error, ")


@router.get("/users/{user_id}/working-hours-changes/preview", response_model=WorkingHoursChangePreview)
def preview_working_hours_change(
    user_id: str,
    effective_from: date,
    weekly_hours: Optional[float] = Query(None, ge=0, le=60),
    use_daily_schedule: bool = Query(False),
    hours_monday: Optional[float] = Query(None, ge=0, le=24),
    hours_tuesday: Optional[float] = Query(None, ge=0, le=24),
    hours_wednesday: Optional[float] = Query(None, ge=0, le=24),
    hours_thursday: Optional[float] = Query(None, ge=0, le=24),
    hours_friday: Optional[float] = Query(None, ge=0, le=24),
    work_days_per_week: Optional[int] = Query(None, ge=1, le=7),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Task 2 (#Wochenstunden-Dialog): strikt lesende Vorschau VOR dem Speichern
    einer Wochenstunden-Änderung — zeigt Zeitraum, Tagessoll je Wochentag,
    Anzahl betroffener Abwesenheiten, Saldo und Urlaub vorher/nachher und ob ein
    abgeschlossenes Jahr berührt wird. Kennt zusätzlich die Ablehnungsgründe des
    POST-Endpoints (Eingabe verletzt die Modus-Regel, Datum bereits belegt),
    damit der Dialog den Nutzer nicht erst in einen 400 laufen lässt.

    #431: Die Eingabe ist der VOLLSTÄNDIGE Snapshot (Modus, fünf Tageswerte,
    Arbeitstage), nicht mehr nur ``weekly_hours`` — genau das, was der POST seit
    Task 5 annimmt. Die Normalisierung (Summe als ``weekly_hours``,
    ``work_days_per_week``-Rückfall) läuft über dieselbe Regel wie dort:
    ``WorkingHoursChangeCreate.check_mode`` + ``_normalise_schedule_input``.
    Der frühere Tagesplan-Ablehnungsgrund ist damit weg — er widerspräche dem
    Schreibpfad.

    Schreibt NICHTS — kein ``db.commit()``. Um ``retarget_absence_hours`` und
    die Konto-Funktionen für den noch gar nicht gespeicherten Snapshot befragen
    zu können, wird die hypothetische Änderung in der laufenden Transaktion
    ge-flusht (damit deren eigene ``WorkingHoursChange``-Abfragen sie sehen) und
    danach IMMER per ``db.rollback()`` verworfen — auch im Fehlerfall.
    """
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    today = today_local()
    # Bedeutung unverändert: „das Wirkungsdatum liegt VOR heute" — genau die
    # Aussage, die der Admin im Warnhinweis liest. Der ZEITRAUM
    # (period_start/period_end) und affected_absences bilden dagegen den echten
    # Wirkungsbereich ab, der auch in der Zukunft liegen kann (Release-Review
    # 1.17.0): sonst korrigiert das Speichern still Daten, die die Vorschau nie
    # angekündigt hat.
    is_retroactive = effective_from < today
    window = calculation_service.retarget_window(db, user, effective_from)
    period_start = window.start
    period_end = window.end

    # #431: die Eingabe durch DIESELBE Regel schicken wie der Schreibpfad —
    # `check_mode` (Modi schließen einander aus; im Tagesplan-Modus ist
    # weekly_hours die Summe der Tageswerte) plus `_normalise_schedule_input`
    # (work_days_per_week-Rückfall auf die User-Zeile). Eine zweite Formulierung
    # derselben Regel würde divergieren — #394/1.14.3 ist genau daran
    # aufgelaufen (ein Vorab-Check wich von der Buchung ab).
    #
    # Verletzt die Eingabe die Regel, gibt es keinen Snapshot, den man
    # vorrechnen könnte: das wird ein blocked_reason (der POST lehnte dieselbe
    # Eingabe ab), und „neu" bleibt gleich „aktuell" — lieber gar keine Änderung
    # anzeigen als eine erfundene.
    current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    input_error = None
    try:
        norm = _normalise_schedule_input(
            WorkingHoursChangeCreate(
                effective_from=effective_from,
                weekly_hours=weekly_hours,
                use_daily_schedule=use_daily_schedule,
                hours_monday=hours_monday,
                hours_tuesday=hours_tuesday,
                hours_wednesday=hours_wednesday,
                hours_thursday=hours_thursday,
                hours_friday=hours_friday,
                work_days_per_week=work_days_per_week,
            ),
            user,
        )
        new_schedule = calculation_service.Schedule(
            weekly_hours=Decimal(str(norm.weekly_hours)),
            use_daily_schedule=norm.use_daily_schedule,
            day_hours=tuple(
                None if v is None else Decimal(str(v)) for v in norm.day_hours
            ),
            work_days_per_week=norm.work_days_per_week,
        )
    except ValidationError as exc:
        input_error = _schedule_input_error(exc)
        norm = None
        new_schedule = current_schedule

    # Fund 3 (Release-Review 1.17.0), #431 erweitert: das Tagessoll je WOCHENTAG
    # ausweisen, nicht für den Stichtag.
    #
    # Zwei Gründe. (1) get_daily_target_for_date liefert am Wochenende hart 0 —
    # und das Wirkungsdatum ist typischerweise ein Monatserster (4 der 12
    # Monatsersten 2026 fallen auf ein Wochenende). Der Dialog zeigte dann
    # „Tagessoll 0.0h → 0.0h" NEBEN „N Abwesenheit(en) betroffen": zwei Zahlen,
    # die sich widersprechen. (2) Ein einzelner Wert bildet einen individuellen
    # Tagesplan überhaupt nicht ab (Mo 8 / Di 0 / Mi 4). Die Zählung war nie
    # betroffen (das Retarget rechnet pro Tag), es ist reine Anzeige.
    #
    # Nur der WOCHENTAG des Datums geht in die Rechnung ein (die Snapshots sind
    # explizit übergeben) — deshalb genügt der Montag der Woche des
    # Wirkungsdatums als Träger für Mo…Fr.
    week_monday = effective_from - timedelta(days=effective_from.weekday())
    day_targets_current = [
        float(calculation_service.get_daily_target_for_date(
            user, week_monday + timedelta(days=i), current_schedule))
        for i in range(5)
    ]
    day_targets_new = [
        float(calculation_service.get_daily_target_for_date(
            user, week_monday + timedelta(days=i), new_schedule))
        for i in range(5)
    ]

    # Gleiche Ablehnungsgründe wie create_working_hours_change: ungültige
    # Eingabe zuerst (ohne gültigen Snapshot gibt es nichts zu prüfen), dann
    # Datum bereits belegt. Der frühere Tagesplan-Zweig ist mit Task 5 entfallen.
    blocked_reason = input_error
    if not blocked_reason:
        existing = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
            WorkingHoursChange.effective_from == effective_from
        ).first()
        if existing:
            blocked_reason = (
                f"Eine Stundenänderung für den {effective_from.strftime('%d.%m.%Y')} "
                "existiert bereits"
            )

    # #431: Saldo und Urlaub im IST-Zustand — vor dem Dry-Run, damit sie die
    # hypothetische Zeile garantiert nicht sehen. Der Stichtag ist derselbe wie
    # in allen Live-Anzeigen (#313, `get_soll_cutoff_date`); das Urlaubsjahr ist
    # das von `period_start` — das Jahr, dessen Budget die Änderung bewegt.
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    vacation_year = period_start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, cutoff.year, cutoff.month, cutoff_date=cutoff))
    vacation_before = float(
        calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before

    affected_absences = 0
    if not blocked_reason:
        # Wäre die Änderung ohnehin blockiert (z. B. Duplikat-Datum), gibt es
        # nichts zu simulieren — UND ein Insert würde eine zweite Zeile mit
        # identischem effective_from erzeugen. Die Snapshot-Auflösung hat keine
        # Sekundärsortierung und würde dann reproduzierbar die BESTEHENDE Zeile
        # wählen, nicht die hypothetische — gerechnet würde gegen den falschen
        # Vertrag. Also nur bei nicht-blockierten Änderungen.
        #
        # EIN Flush, EIN Rollback für alles: die hypothetische Zeile geht nur in
        # die laufende Transaktion (NICHT committen), damit die
        # WorkingHoursChange-Abfragen von retarget_absence_hours,
        # get_overtime_account und get_vacation_account sie sehen — danach immer
        # zurückrollen, egal ob die Berechnung erfolgreich war.
        temp_change = WorkingHoursChange(
            user_id=user.id,
            tenant_id=current_user.tenant_id,
            effective_from=effective_from,
            weekly_hours=norm.weekly_hours,
            use_daily_schedule=norm.use_daily_schedule,
            hours_monday=norm.day_hours[0],
            hours_tuesday=norm.day_hours[1],
            hours_wednesday=norm.day_hours[2],
            hours_thursday=norm.day_hours[3],
            hours_friday=norm.day_hours[4],
            work_days_per_week=norm.work_days_per_week,
        )
        db.add(temp_change)
        db.flush()
        try:
            # Das Retarget läuft hier BEWUSST nicht im dry_run: der Saldo
            # „nachher" muss gegen die nachgezogenen Abwesenheits-Stunden
            # gerechnet werden. Sonst schriebe ein Krankentag im Fenster
            # weiterhin die ALTEN Stunden dem Ist gut, während das Soll
            # desselben Tages schon der neuen Zeile folgt — ein Phantom-Plus,
            # das nach dem Speichern wieder verschwindet. Genau diese Zahl steht
            # im Dialog über der Bestätigungs-Checkbox. Geschrieben wird dabei
            # nichts: retarget_absence_hours flusht nur, der Rollback unten
            # verwirft beides (Test test_simulated_retarget_is_rolled_back).
            # Der Rückgabewert ist derselbe wie mit dry_run=True.
            if window.has_absences:
                affected_absences = calculation_service.retarget_absence_hours(
                    db, user, period_start, period_end
                )
            # Kein wh_changes-Preload durchreichen — die Funktionen müssen die
            # eben geflushte Zeile selbst nachladen.
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, cutoff.year, cutoff.month, cutoff_date=cutoff))
            vacation_after = float(
                calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
        finally:
            db.rollback()

    # closed_years: ALLE im Zeitraum berührten abgeschlossenen Jahre (Spec:
    # docs/superpowers/specs/2026-07-26-wochenstunden-anpassen-design.md), nicht
    # nur das früheste — closed_year_warning bleibt der fertige Anzeigetext für
    # das früheste (gleiche Definition, eine Query statt zwei).
    closed_years = calculation_service.closed_years_in_range(
        db, current_user.tenant_id, range(period_start.year, period_end.year + 1)
    )
    closed_year_warning = calculation_service.closed_year_warning_text(closed_years)

    return WorkingHoursChangePreview(
        is_retroactive=is_retroactive,
        period_start=period_start,
        period_end=period_end,
        current_daily_target=_planned_day_mean(day_targets_current),
        new_daily_target=_planned_day_mean(day_targets_new),
        day_targets_current=day_targets_current,
        day_targets_new=day_targets_new,
        overtime_before=overtime_before,
        overtime_after=overtime_after,
        vacation_days_before=vacation_before,
        vacation_days_after=vacation_after,
        affected_absences=affected_absences,
        blocked_reason=blocked_reason,
        closed_years=closed_years,
        closed_year_warning=closed_year_warning,
    )


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

    # Critical fix (Review-Fund): reject deleting the EARLIEST row while later
    # rows still exist. That earliest row is the only place the value that
    # applied BEFORE the very first recorded change lives — it is either the
    # #415 auto-baseline or the admin's first-ever manual entry. Delete it and
    # get_weekly_hours_for_date has nothing left to fall back to for any date
    # before the (now-earliest) remaining row except user.weekly_hours — which
    # the resync a few lines below is about to overwrite with a LATER row's
    # value. The result: retarget_absence_hours would silently recompute
    # already-booked absences before that window against the WRONG daily
    # target (a real incident: a 40h baseline + a later 20h change, deleting
    # the baseline resynced weekly_hours to 20h and then halved an absence
    # that was correctly booked at 8h under the old 40h contract). There is no
    # way to recompute this correctly once the row is gone — reject instead of
    # guessing. Deleting the ONLY row is still fine (user.weekly_hours is then
    # the sole source of truth again, nothing else to fall back to), and
    # deleting any non-earliest row is unaffected.
    _sibling_count = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).count()
    if _sibling_count > 1:
        _earliest = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user_id,
            WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        ).order_by(WorkingHoursChange.effective_from.asc()).first()
        if _earliest is not None and _earliest.id == change.id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dies ist die früheste erfasste Stundenänderung dieses "
                    "Mitarbeiters — sie verankert den davor gültigen Wert, der "
                    "sonst nirgends mehr gespeichert ist. Bitte zuerst die "
                    "späteren Änderungen löschen, wenn die Historie komplett "
                    "zurückgesetzt werden soll."
                ),
            )

    # Capture before delete/expire — the ORM instance is expired after the
    # flush below, and any attribute access on a deleted, expired row would
    # try to re-SELECT it and fail.
    deleted_effective_from = change.effective_from
    db.delete(change)
    # Task 4: flush (not commit) so the following re-queries within THIS
    # transaction already see the row as gone — retarget_absence_hours below
    # must compute against the remaining valid value, not the one just
    # deleted (same reasoning as the flush() in create_working_hours_change).
    db.flush()

    most_recent = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from <= today_local()
    ).order_by(WorkingHoursChange.effective_from.desc()).first()

    if most_recent:
        # #431 (Task 6): derselbe vollständige Snapshot-Resync wie beim
        # Anlegen — _sync_user_from_change ist DIE eine Stelle dafür. Nur
        # `weekly_hours` zurückzuschreiben ließe nach dem Löschen einer
        # Modus-Wechsel-Zeile einen halb aktualisierten Zustand auf der
        # User-Zeile stehen (z. B. `use_daily_schedule` weiter auf dem Wert
        # der gerade gelöschten Zeile, während `weekly_hours` schon den
        # davor gültigen Wert trägt).
        _sync_user_from_change(user, most_recent)

    # Task 4 (Wochenstunden-Änderung löschen rechnet zurück): removing a
    # change makes the previously-valid value apply to its window again —
    # the absence hours that create_working_hours_change adjusted forward
    # must be pulled back the same way. retarget_absence_hours is DIE eine
    # Stelle dafür (kein zweiter Rechenpfad); it reads the new/remaining
    # daily target via get_weekly_hours_for_date, which in turn sees the
    # just-deleted row (and the just-updated user.weekly_hours) because of
    # the flush above.
    #
    # Release-Review 1.17.0: Hier stand früher „only retroactive: a change whose
    # effective_from lies in the future never touched any already-booked
    # absence". Das stimmte nicht — Abwesenheiten werden routinemäßig im Voraus
    # gebucht (genehmigter Urlaub, Betriebsferien, geplante Fortbildung), und
    # seit das Anlegen sie auch bei zukunftsdatiertem Wirkungsdatum nachzieht,
    # MUSS das Löschen symmetrisch zurückrechnen. Fenster und Auslöser kommen
    # aus derselben Quelle wie beim Anlegen: calculation_service.retarget_window
    # (bis zum Tag vor der nächsten Änderung, sonst offen) plus „es gibt eine
    # betroffene Abwesenheit".
    #
    # #431 (Task 6): Mitarbeitende mit individuellem Tagesplan sind NICHT mehr
    # ausgenommen. Ihr Tagessoll kommt jetzt ebenfalls aus dieser Zeile — das
    # Löschen muss deshalb genauso symmetrisch zurückrechnen wie bei
    # gleichmäßigen Wochenstunden. Der früher hier stehende Skip (I1) hatte den
    # umgekehrten Grund: damals konnte eine solche Zeile ihr Soll gar nicht
    # setzen (die LIVE-Felder hours_monday…friday trieben es), das Retarget
    # schrieb ihnen aber trotzdem die gebuchten Stunden um (real: 8 h → 6 h) —
    # eine stille Änderung an §16-Belegen ohne Bezug zur ausgelösten Aktion.
    # Seit die Zeile den vollständigen Vertrags-Snapshot trägt und das Soll
    # dieser Gruppe tatsächlich treibt, gilt das Gegenteil: OHNE Rückrechnung
    # verschöbe das Löschen das Tagesplan-Soll, ohne die Abwesenheitsstunden
    # zurückzuziehen und ohne stale_year_closing_warning zu melden — dieselbe
    # stille §16-Drift, nur andersherum.
    window = calculation_service.retarget_window(db, user, deleted_effective_from)
    adjusted_absences = 0
    warning = None
    if window.has_absences:
        adjusted_absences = calculation_service.retarget_absence_hours(
            db, user, window.start, window.end
        )
        _log_wh_change_retarget(
            db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
            effective_from=window.start, period_end=window.end,
            adjusted_absences=adjusted_absences,
            prefix="Löschung der Wochenstunden-Änderung",
            suffix="auf den davor gültigen Wert zurückgerechnet",
        )
    # I3 (Abschluss-Review): Das Anlegen liefert diesen Hinweis bereits; das
    # Löschen rechnet dasselbe Fenster zurück und kann denselben eingefrorenen
    # Carryover entwerten, meldete aber nichts. Fix #5 gilt hier genauso: NICHT
    # automatisch neu rechnen (überschriebe manuelle Carryover-Anpassungen),
    # nur melden. Wie beim Anlegen unabhängig vom Retarget: die Rücknahme
    # verschiebt das Per-Tag-Soll jedes Arbeitstags im Wirkungsbereich.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id,
        range(window.start.year, window.end.year + 1),
    )

    db.commit()
    # Muster von delete_closure / cancel_vacation_request_as_admin: mit Warnung
    # 200 + Body, ohne Warnung weiterhin 204 No Content.
    if warning:
        return JSONResponse(status_code=200, content={"warning": warning})
    return None
