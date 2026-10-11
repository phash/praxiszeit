"""Admin sub-router: User Management + Working Hours Changes."""

import copy
import logging
import uuid
from collections import Counter
from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Annotated, Any, List, NamedTuple, Optional
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from pydantic import ValidationError
from app.services.timezone_service import today_local
from app.database import get_db
from app.models import User, TimeEntry, Absence, AbsenceReason, WorkingHoursChange, ChangeRequest, VacationRequest, TimeEntryAuditLog, UserRole, PublicHoliday, YearCarryover
from app.models.security_event import (
    EVENT_ADMIN_SET_PASSWORD,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_REACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    SecurityEvent,
)
from app.schemas.security_event import SecurityEventResponse
from app.routers.admin_helpers import (
    lock_active_admin_ids, lock_active_admins_and_user, lock_user_row,
)
from app.services.date_filters import date_in_year
from app.middleware.auth import require_admin
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword, UserListResponse
from app.schemas.working_hours_change import (
    EFFECTIVE_FROM_RANGE_DETAIL, WorkingHoursChangeCreate, WorkingHoursChangeDelete, WorkingHoursChangePreview,
    WorkingHoursChangeResponse, effective_from_plausible,
)
from app.schemas.reports import AdminUserOverview, VacationAccount, YtdOvertime
from app.services import (
    auth_service, calculation_service, lifecycle_service, milog_service, reclamp_audit, settings_service,
    wh_change_service, work_blocks_service, work_window_service,
)
# Task 15: dieselbe Zahl- und Label-Schreibweise wie die §16-Exporte — das
# Aenderungsprotokoll darf die Stunden nicht anders schreiben als der Beleg.
from app.services.export_service import ABSENCE_TYPE_LABELS_DE, format_hours_de
# #448: gleiche Single Source of Truth wie absences.py/admin_vacations.py/
# vacation_requests.py/admin_change_requests.py — direkt aus dem Service
# importiert (kein Router-Zirkelimport).
from app.services.closure_split_service import resplit_year_closures
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
    adjusted: List[calculation_service.AbsenceRetarget],
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
    ``if adjusted:`` guard of their own.

    Task 15: geschrieben werden ZWEI Ebenen —

    * die **Sammelzeile** (unveraendert, ``old_date``/``new_date`` leer): sie
      fasst den Vorgang zusammen.
    * je tatsaechlich geaenderter Abwesenheit eine **Einzelzeile** mit dem Datum
      in ``old_date``/``new_date`` (maschinell auswertbar) und den Stunden im
      Klartext in ``old_note``/``new_note``. Vorher stand nur die Summe im
      Protokoll — WELCHE Zeile von WELCHEM Wert auf WELCHEN ging, war nirgends
      nachlesbar, und genau das braucht man, wenn sich eine Rueckrechnung als
      falsch herausstellt.

    Bewusst KEINE stille Obergrenze (CLAUDE.md „no silent caps"): beruehrt ein
    Vorgang 300 Abwesenheiten, stehen 300 Zeilen im Protokoll.

    Die Zeilen entstehen hier im ROUTER, nicht in ``retarget_absence_hours``:
    die Vorschau ruft dieselbe Rueckrechnung und rollt danach zurueck — sie darf
    nichts protokollieren, sonst schriebe jeder Tastendruck im Dialog eine
    Aenderung fest, die nie stattfand.

    Alle Audit-Zeilen entstehen per ORM (``db.add``), damit der
    ``before_insert``-Hook den ``row_hash`` (#121) berechnet.

    ``source="wh_change"`` is 9 characters, well under the
    ``varchar(40)`` column limit (CLAUDE.md).
    """
    if not adjusted:
        return
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=user.id,
        changed_by=admin.id,
        action="update",
        source="wh_change",
        new_note=(
            f"{prefix} zum {effective_from.isoformat()}: "
            f"{len(adjusted)} Abwesenheit(en) im Zeitraum "
            f"{effective_from.isoformat()}–{period_end.isoformat()} {suffix}"
        ),
        tenant_id=tenant_id,
    ))

    # Der Ausloeser im Klartext, identisch auf jeder Einzelzeile.
    trigger = f"{prefix} ab {effective_from.strftime('%d.%m.%Y')}"
    for rec in adjusted:
        # Nur der eingebaute TYP, nie der Name eines eigenen Grundes (#312):
        # der kann gesundheitsbezogen sein ("Reha"), und den Typ treibt ohnehin
        # die Berechnung, um die es hier geht.
        label = ABSENCE_TYPE_LABELS_DE.get(
            rec.absence_type.value, rec.absence_type.value
        )
        db.add(TimeEntryAuditLog(
            time_entry_id=None,
            user_id=user.id,
            changed_by=admin.id,
            action="update",
            source="wh_change",
            # Das Datum der Abwesenheit — auf beiden Seiten gleich (die
            # Rueckrechnung verschiebt nie den Tag, nur die Stunden), damit die
            # Zeile in der Vorher/Nachher-Darstellung des Protokolls nicht wie
            # eine Verschiebung aussieht.
            old_date=rec.date,
            new_date=rec.date,
            old_note=f"{label} {format_hours_de(rec.old_hours)} h",
            new_note=f"{label} {format_hours_de(rec.new_hours)} h — {trigger}",
            tenant_id=tenant_id,
        ))


def _comparable_snapshot(weekly_hours, use_daily_schedule, day_hours, work_days_per_week,
                         blocks, block_pauses):
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

    Spec 2026-10-08 (3.3/11.3): Blöcke und Pausen gehören ebenfalls zum
    Snapshot — sie treiben die Kappung, und eine Änderung allein an ihnen
    (PR3: reine Blockänderung) braucht genauso eine Basis-Zeile, die die
    Vergangenheit einfriert.
    """
    use_daily_schedule = bool(use_daily_schedule)
    return (
        Decimal(str(weekly_hours)),
        use_daily_schedule,
        tuple(
            None if v is None else Decimal(str(v)) for v in day_hours
        ) if use_daily_schedule else (None,) * 5,
        int(work_days_per_week),
        # Spec 2026-10-08 (3.3/11.3): Blöcke und Pausen gehören zum Snapshot.
        # Beide kommen im Schedule-Format (bereits normalisiert: None == fünf
        # leere Tage), Pausen nur, wenn es Blöcke gibt.
        blocks,
        block_pauses if blocks is not None else None,
    )


def _carried_blocks(predecessor: "calculation_service.Schedule") -> tuple:
    """P2/P24: welche Blöcke eine NEUE Verlaufszeile erbt, solange der Dialog
    keine Blöcke kennt — aus dem VOR der Änderung für ``effective_from``
    gültigen Snapshot (Vorgängerzeile bzw. Rückfall ``users.work_blocks``).

    Ein Altfenster (``pause_minutes`` NULL) läuft weiter; ohne diese Übernahme
    schaltete jede Wochenstunden-Änderung die Kappung still ab. Neue Blöcke
    (Pause gesetzt) enden mit einem Wechsel nach „Gleichmäßig"/„Nach Tagen".
    Rückgabe ``(blocks, block_pauses)`` im Schedule-Format."""
    parsed = (
        None if predecessor.blocks is None
        else work_blocks_service.ParsedWeek(predecessor.blocks, predecessor.block_pauses)
    )
    if work_blocks_service.is_legacy_week(parsed):
        return predecessor.blocks, predecessor.block_pauses
    return None, None


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
    # Spec E9: Spiegel der jüngsten Zeile ≤ heute — als KOPIE (eine geteilte
    # Liste würde eine spätere In-place-Änderung in beide Zeilen tragen).
    user.work_blocks = copy.deepcopy(most_recent.blocks)


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

    #448: the closures query below has NO ``ORDER BY`` — ``_create_closure_absences``
    only balances the VACATION/OVERTIME split against the remaining budget WITHIN
    one closure (``sorted(workdays)`` is per-closure), so across SEVERAL closures
    the split followed the DB delivery order, not the calendar (e.g. December
    enrolled before June could book December as VACATION and June, the earlier
    one, as OVERTIME). Every OTHER closure-writing/private-vacation path
    (create/update/delete_closure, absences.create/delete_absence,
    admin_vacations.review_vacation_request, admin_change_requests, both
    withdraw/cancel paths) re-classifies via
    ``closure_split_service.resplit_year_closures`` afterwards — this was the one
    path that didn't. Fixed by re-splitting every YEAR TOUCHED by a vacation
    closure this call actually booked, in calendar order, same as
    create_closure/update_closure (toggle-gated). Kept INSIDE the surrounding
    try/except: the re-split is part of the same best-effort enrolment contract
    — a failure here must roll back the (uncommitted) partial enrolment, not the
    already-committed user create/update, and not raise a second, differently-
    shaped failure mode for what is still the same "closure catch-up" step.
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
        # #448: years touched by a vacation closure this call actually booked
        # workdays for — a closure can straddle a year boundary (e.g. 29.12.-
        # 02.01.), so BOTH years it spans count as touched, exactly like the
        # `range(start.year, end.year + 1)` loops in create_closure/update_closure.
        resplit_years: set = set()
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
                if closure.counts_as_vacation:
                    resplit_years.update(range(closure.start_date.year, closure.end_date.year + 1))

        # #448: re-classify the touched years in CALENDAR order, exactly like
        # create_closure/update_closure/delete_closure — toggle-gated, the
        # per-closure db.flush() above already made every booking from this
        # call visible to the budget snapshot.
        if resplit_years and settings_service.get_bool_setting(
            db, "closure_overtime_after_vacation", current_user.tenant_id, False
        ):
            for yr in sorted(resplit_years):
                resplit_year_closures(db, current_user.tenant_id, yr, current_user)
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


# ── #489: Schutz vor Aussperrung + Protokoll der Kontovorgaenge ────────────
# Realfall: eine Praxis kam nicht mehr in ihre Verwaltung — das Admin-Konto war
# deaktiviert, wer das getan hatte, stand nirgends.

_ROLE_LABELS_DE = {UserRole.ADMIN: "Admin", UserRole.EMPLOYEE: "Mitarbeitende"}


def _role_label(role) -> str:
    role = UserRole(role)
    return _ROLE_LABELS_DE.get(role, role.value)


# Spec 11.4 (E26): ein gecachtes altes Frontend schickt die entfallenen
# Fensterfelder bei jedem Speichern mit.
LEGACY_WINDOW_FIELDS_DETAIL = (
    "Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) "
    "wurden durch Arbeitszeit-Blöcke ersetzt."
)


LAST_ADMIN_DETAIL = (
    "Das ist das letzte aktive Admin-Konto dieser Praxis. Legen Sie zuerst ein "
    "weiteres Admin-Konto an oder ernennen Sie jemanden zum Admin – sonst kommt "
    "niemand mehr in die Verwaltung."
)


def _is_last_active_admin(db: Session, user: User) -> bool:
    """Ist ``user`` das einzige aktive Admin-Konto seines Mandanten?

    Sperrt alle aktiven Admin-Zeilen ueber ``lock_active_admin_ids`` (sortiert,
    ``FOR NO KEY UPDATE`` — die Projektregel fuer Anker-Sperren auf ``users``):
    deaktivieren sich zwei Admins gleichzeitig gegenseitig, wartet die zweite
    Transaktion und sieht danach die erste Deaktivierung. Ohne die Sperre
    stuenden am Ende beide Konten deaktiviert da.
    """
    if user.role != UserRole.ADMIN or not user.is_active:
        return False
    return lock_active_admin_ids(db, user.tenant_id) == [user.id]


def _lock_and_reload(db: Session, current_user: User, user: User) -> None:
    """#491 API-2: Anker-Sperre auf der Zielzeile, danach ihren Stand neu lesen.

    ``_get_user_in_tenant`` liest ungesperrt — bei einem gleichzeitigen,
    noch nicht committeten Umschalten also den ALTEN Stand. Auf diesem Stand
    entschieden Deaktivieren/Reaktivieren bisher, ob eine Protokollzeile
    entsteht: zwei parallele Deaktivierungen schrieben zwei Zeilen; trafen
    Reaktivierung und Deaktivierung aufeinander, fehlte die Zeile der zweiten —
    und weil das ORM einen „unveraenderten" Wert nicht schreibt, blieb das Konto
    sogar im Zustand der ersten stehen, obwohl die zweite erfolgreich meldete.

    Die Sperre wartet auf die Gegenseite; ``refresh`` holt danach deren Stand.
    Dieselbe Falle hat jede Arbeitszeit-Änderung (E52/P5) — auch sie sperrt
    über diesen Helfer, nie über ein nacktes ``lock_user_row``.
    Reihenfolge: NACH ``_is_last_active_admin`` (das ggf. alle aktiven
    Admin-Zeilen sortiert sperrt) — erst die Admin-Menge, dann die Zielzeile,
    sonst verklemmen sich zwei gleichzeitige Admin-Deaktivierungen ueber Kreuz.
    """
    lock_user_row(db, current_user.tenant_id, user.id)
    db.refresh(user)


def _log_account_event(db: Session, current_user: User, event: str, subject: User,
                       detail: Optional[str] = None) -> None:
    """Eine Zeile nach ``security_events`` — in DERSELBEN Transaktion wie der
    Vorgang selbst, damit es keinen Vorgang ohne Nachweis gibt. ``actor`` traegt
    die Konto-ID statt des Namens: wird die handelnde Person spaeter
    anonymisiert, bleibt in der Zeile kein Klarname stehen."""
    db.add(SecurityEvent(
        tenant_id=current_user.tenant_id,
        event=event,
        subject_user_id=subject.id,
        actor=f"user:{current_user.id}",
        detail=detail,
    ))


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
    # Spec 11.1: EIN Preload der Verlaufszeilen für alle gelisteten Personen.
    calculation_service.attach_work_blocks_today(db, users, today_local())
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


def _scrub_audit_log_notes(
    db: Session, tenant_id, user_id, old_username: str, old_email: Optional[str],
    pseudonym: str,
) -> int:
    """DSGVO Art. 17: Klarnamen der anonymisierten Person aus den Freitext-
    Notizen des Aenderungsprotokolls entfernen (Release-Review 1.18.1, Nachzug
    zum Mandanten-Pfad ``lifecycle_service.anonymize_tenant``).

    Der Protokoll-Freitext traegt direkte Identifikatoren, die die
    Anonymisierung auf der ``users``-Zeile gerade ueberschreibt:

    * ``auth.py`` schreibt bei JEDEM Selbstbedienungs-E-Mail-Wechsel die alte
      UND die neue Adresse nach ``old_note``,
    * ``reports.py`` (10 Stellen) den Benutzernamen des handelnden Admins nach
      ``new_note``,
    * ``journal.py`` zusaetzlich den Benutzernamen der BETROFFENEN — dort auf
      einer Zeile, deren ``user_id`` UND ``changed_by`` der Admin ist. Genau
      deshalb geht die Suche ueber den INHALT und nicht nur ueber die
      Zuordnung: ein reiner ``user_id``/``changed_by``-Filter sieht diese Zeile
      nie.

    Zwei Behandlungen, bewusst unterschiedlich:

    * **Eigene Zeilen** (``user_id`` = die Betroffene) → beide Notizen NULL.
      Sie sind ueber sie gefuehrt; hier stehen neben dem Namen auch die
      Art.-9-Spuren (``"absence:sick:8.0h"``), die den Loeschlauf ihrer
      Abwesenheiten sonst ueberleben, und HISTORISCHE E-Mail-Adressen, die
      keine Suche nach dem heutigen Wert findet. Die Zeile selbst bleibt: wer
      wann was an einer Zeitaufzeichnung geaendert hat, samt
      ``old_*``/``new_*`` fuer Datum, Uhrzeit und Pause, ist der
      §16-relevante Teil (gleiche Abwaegung wie ``working_hours_changes.note``).
    * **Fremde Zeilen**, in deren Text sie vorkommt → nur die Fundstelle wird
      ersetzt (Benutzername → Pseudonym, E-Mail → ``[anonymisiert]``). Die
      Notiz gehoert dort zum Datensatz eines ANDEREN Beschaeftigten; sie
      komplett zu leeren waere fremde §16-Prosa.

    #121: ``old_note``/``new_note`` gehen in den ``row_hash`` ein → ORM-Objekte
    laden und den Hash neu berechnen (Muster aus ``purge_user``). Ein
    Bulk-``UPDATE`` umginge den ``before_insert``-Hook und liesse
    ``verify-integrity`` jede geaenderte Zeile als manipuliert melden.

    Grenze (bewusst): gefunden werden die maschinell erzeugten Identifikatoren
    Benutzername und aktuelle E-Mail. Freie Prosa, die die Person mit Vor-/
    Nachnamen nennt ("Vertretung fuer Frau Schulz"), ist nicht zuverlaessig
    auffindbar — das gilt fuer den Mandanten-Pfad genauso.

    Gibt die Zahl der geaenderten Zeilen zurueck. F-026: tenant-gefiltert.
    """
    from app.core import audit_integrity

    needles = [n for n in (old_email, old_username) if n]
    conditions = [TimeEntryAuditLog.user_id == user_id]
    for needle in needles:
        # ``contains(..., autoescape=True)`` maskiert %/_ im Wert. Die Suche darf
        # ruhig zu VIEL laden (dann aendert die Schleife unten nichts) — sie darf
        # nur nichts uebersehen.
        conditions.append(TimeEntryAuditLog.old_note.contains(needle, autoescape=True))
        conditions.append(TimeEntryAuditLog.new_note.contains(needle, autoescape=True))

    def _mask(text: Optional[str]) -> Optional[str]:
        if not text:
            return text
        out = text
        # E-Mail ZUERST: der Benutzername ist oft ihr lokaler Teil
        # ("maria.schulz" in "maria.schulz@…") — andersherum bliebe die Domain
        # als Rest stehen.
        if old_email:
            out = out.replace(old_email, "[anonymisiert]")
        if old_username:
            out = out.replace(old_username, pseudonym)
        return out

    touched = 0
    for row in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.tenant_id == tenant_id,  # F-026
        or_(*conditions),
    ).all():
        if row.user_id == user_id:
            new_old, new_new = None, None
        else:
            new_old, new_new = _mask(row.old_note), _mask(row.new_note)
        if new_old == row.old_note and new_new == row.new_note:
            continue  # nichts zu tun → Hash bleibt unangetastet
        row.old_note = new_old
        row.new_note = new_new
        row.row_hash = audit_integrity.compute_row_hash(row)
        touched += 1
    return touched


@router.post("/users/{user_id}/anonymize")
def anonymize_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """DSGVO Art. 17: Anonymize an inactive user in-place. Keeps time entries (ArbZG SS16 -- 2-year retention), deletes absences.

    #443: shift_slots.note bleibt hier unveraendert stehen. Die Einteilung
    besteht fuer die uebrigen eingeteilten Mitarbeitenden fort — ein
    pauschales Leeren wuerde deren Hinweise mitloeschen, nicht nur den der
    anonymisierten Person. Ein inhaltsbasierter Namens-Scrub (der Hinweistext
    traegt regelmaessig Personenbezug, z. B. "Vertretung fuer Frau Schmidt")
    ist neue Mechanik und offen als #440, nicht Teil dieser Aenderung. Im
    Mandantenpfad (``lifecycle_service.anonymize_tenant``) wird das Feld
    dagegen komplett geleert, weil dort der ganze Mandant und damit jede
    betroffene Einteilung verschwindet.
    """
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

    # Vor dem Ueberschreiben sichern — der Protokoll-Scrub unten sucht nach
    # diesen beiden Werten (Release-Review 1.18.1).
    _old_username = user.username
    _old_email = user.email

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

    # Fund F (Abschluss-Review #431): die #415/#431-Vertragshistorie
    # (``working_hours_changes``) bleibt bewusst stehen — sie traegt das
    # historische SOLL fuer die §16-Aufbewahrung, genau wie die TimeEntries
    # oben im Docstring. Ihr freier ``note``-Text (bis 500 Zeichen, vom
    # Dialog angeboten und im Verlauf wieder angezeigt) ist aber Admin-
    # Freitext OHNE Aufbewahrungspflicht — z. B. "Rückkehr nach Elternzeit"
    # oder ein Klarname in Prosa. Scrubben wie die anderen personenbezogenen
    # Felder oben (``department`` etc.), NICHT die Zeilen selbst loeschen.
    db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.note.isnot(None),
    ).update({WorkingHoursChange.note: None}, synchronize_session=False)

    # Release-Review 1.19.0: ``security_events.detail`` nennt das Konto im
    # Klartext ("... (Konto admin)"). Die ZEILE bleibt (Art.-5(2)-Nachweis, wer
    # wann dieses Konto uebernommen hat), der Freitext geht — Ereignis,
    # handelndes Betriebssystem-Konto und Zeitpunkt tragen den Nachweis auch
    # ohne den Namen.
    db.query(SecurityEvent).filter(
        SecurityEvent.subject_user_id == user.id,
        SecurityEvent.tenant_id == current_user.tenant_id,  # F-026
        SecurityEvent.detail.isnot(None),
    ).update({SecurityEvent.detail: None}, synchronize_session=False)

    # #440 A/B: Die Antraege dieser Person tragen ihre eigene Prosa —
    # ``change_requests.reason`` ist NOT NULL und regelmaessig gesundheits- oder
    # adressnah ("Arzttermin wegen ...", "Kind in der Kita abgeholt"), dazu die
    # Notizen beider Antragsarten und die Ablehnungsbegruendungen der
    # Verwaltung. Die ZEILEN bleiben stehen (wer hat wann was beantragt und wer
    # hat entschieden), nur der Freitext geht. ``reason`` bekommt wegen NOT NULL
    # einen Platzhalter.
    #
    # Der Filter ueber ``user_id`` genuegt hier — anders als beim
    # Aenderungsprotokoll (siehe ``_scrub_audit_log_notes``), wo eine Zeile ueber
    # die BETROFFENE schreibt, waehrend beide Kennungen auf die handelnde Admin
    # zeigen. Antraege haengen immer an der antragstellenden Person.
    #
    # Bleibt als grundsaetzliche Grenze: Prosa DRITTER, die diese Person beim
    # Namen nennt ("Vertretung fuer Frau Meier" im Antrag einer Kollegin), ist
    # ueber ein Feld nicht auffindbar (#440, im Modul-Docstring von
    # lifecycle_service festgehalten).
    db.query(ChangeRequest).filter(
        ChangeRequest.user_id == user.id,
        ChangeRequest.tenant_id == current_user.tenant_id,  # F-026
    ).update(
        {
            ChangeRequest.reason: lifecycle_service.ANONYMIZED_TEXT,
            ChangeRequest.proposed_note: None,
            ChangeRequest.original_note: None,
            ChangeRequest.break_waiver_reason: None,
            ChangeRequest.proposed_sunday_exception_reason: None,  # #485
            ChangeRequest.rejection_reason: None,
        },
        synchronize_session=False,
    )

    db.query(VacationRequest).filter(
        VacationRequest.user_id == user.id,
        VacationRequest.tenant_id == current_user.tenant_id,  # F-026
    ).update(
        {VacationRequest.note: None, VacationRequest.rejection_reason: None},
        synchronize_session=False,
    )

    # Release-Review 1.18.1: derselbe Nachzug wie im Mandanten-Pfad — der
    # Freitext des Aenderungsprotokolls traegt E-Mail-Adresse und Benutzernamen
    # im Klartext. Vor dem Anlegen der Protokollzeile unten, damit diese (sie
    # nennt den HANDELNDEN Admin) nicht mitgescannt wird. Begruendung, Auswahl
    # und die #121-Hash-Neuberechnung: siehe ``_scrub_audit_log_notes``.
    _scrub_audit_log_notes(
        db, current_user.tenant_id, user.id, _old_username, _old_email,
        user.username,  # bereits das Pseudonym deleted_<id8>
    )

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
    # Release-Review 1.19.0: ``security_events.subject_user_id`` ist ON DELETE
    # SET NULL — die Zeile ueberlebt den Hard-Delete also (so gewollt: sie
    # belegt, wer wann dieses Konto uebernommen hat). Ihr ``detail`` nennt aber
    # den Benutzernamen im Klartext, und den soll die Endloeschung gerade
    # entfernen. Vor dem Loeschen schrubben, solange die Zuordnung noch steht.
    db.query(SecurityEvent).filter(
        SecurityEvent.subject_user_id == user.id,
        SecurityEvent.tenant_id == current_user.tenant_id,  # F-026
        SecurityEvent.detail.isnot(None),
    ).update({SecurityEvent.detail: None}, synchronize_session=False)
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
    user = _get_user_in_tenant(db, user_id, current_user)
    calculation_service.attach_work_blocks_today(db, [user], today_local())
    return user


def _parse_user_create_body(raw) -> UserCreate:
    """Spec 3.4/11.4: Verstöße gegen die Blockregeln beim Anlegen als 422 mit
    deutschem ``detail`` — derselbe Text wie im Verlaufs-Endpunkt
    (``_labelled_input_error``: Regeltexte ohne Pydantics „Value error, ",
    Typfehler in den Blöcken als „Mo, Block 1, Beginn: ungültiger Wert.",
    Feld-Labels wie „Die Wochenstunden …"). Das gilt zugleich für die übrigen
    ``UserCreate``-Regeltexte (Passwort, fester Monats-Soll, Tagesplan).

    Gibt es keinen deutschen Text (z. B. fehlender Vorname), bleibt es bei
    FastAPIs Standard-422 mit ``loc`` — ein pauschales „Ungültige Eingabe."
    verlöre die Angabe, welches Feld fehlt. Ein bereits gebautes Schema
    (Direktaufruf in Tests) geht unverändert durch."""
    if isinstance(raw, UserCreate):
        return raw
    try:
        return UserCreate.model_validate(raw)
    except ValidationError as exc:
        detail = _labelled_input_error(exc)
        if not detail:
            # Form wie FastAPIs eigene Body-Prüfung: ``loc`` beginnt mit "body".
            raise RequestValidationError([
                {**err, "loc": ("body", *err["loc"])} for err in exc.errors(include_url=False)
            ]) from None
        raise HTTPException(status_code=422, detail=detail) from None


@router.post("/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: Annotated[Any, Body()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new user (admin only).

    Der Body kommt roh herein und wird in ``_parse_user_create_body`` gegen
    ``UserCreate`` geprüft (Spec 3.4/11.4: deutsche 422 statt FastAPIs
    Standardmeldung) — dasselbe Muster wie der Verlaufs-Endpunkt."""
    user_data = _parse_user_create_body(user_data)
    if user_data.legacy_window_fields_sent:
        raise HTTPException(status_code=400, detail=LEGACY_WINDOW_FIELDS_DETAIL)
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
        # Spec E28: Startvertrag — kanonische JSON-Woche (Strings, nie time).
        # Soll (use_daily_schedule/hours_*/weekly_hours/work_days_per_week) hat
        # UserCreate.derive_from_work_blocks bereits daraus abgeleitet.
        work_blocks=(
            [d.model_dump() for d in user_data.work_blocks]
            if user_data.work_blocks is not None else None
        ),
        tenant_id=current_user.tenant_id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # #290: enrol the new participant into existing current/future closures now,
    # so the admin never needs the data-destroying closure re-save workaround.
    _enroll_user_in_open_closures(db, new_user, current_user)
    db.commit()

    calculation_service.attach_work_blocks_today(db, [new_user], today_local())
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
    if user_data.legacy_window_fields_sent:
        raise HTTPException(status_code=400, detail=LEGACY_WINDOW_FIELDS_DETAIL)
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
        # Spec E27: Blöcke gehören zum Vertrags-Snapshot.
        'work_blocks',
    )
    if any(f in update_data for f in _HISTORISED_FIELDS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Wochenstunden, Tagesstunden, Arbeitstage und Arbeitszeit-Blöcke "
                "werden über „Arbeitszeit anpassen…“ mit Wirkungsdatum geändert, "
                "damit Historie und Soll vergangener Monate korrekt bleiben."
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

    # Release-Review 1.16.0: Beschäftigungsfenster ebenfalls
    # gegen den EFFEKTIVEN Zustand prüfen, nicht nur gegen den Payload.
    # `validate_employment_order` im Schema sieht nur die mitgeschickten
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

    # VULN-010: invalidate existing JWTs when role is changed
    role_changed = False
    old_role = user.role
    if 'role' in update_data:
        # #491 API-2 (Nachzug): ``user.role`` stammt aus dem UNGESPERRTEN Lesen
        # von ``_get_user_in_tenant``. Stellte eine parallele, noch nicht
        # committete Anfrage die Rolle gerade um, hielt diese Anfrage ihren
        # Wechsel fuer wirkungslos — keine Protokollzeile, kein
        # token_version-Bump, und das ORM schrieb die „unveraenderte" Rolle
        # nicht: das Konto blieb im Zustand der anderen Anfrage, obwohl diese
        # hier 200 meldete. Deshalb IMMER (nicht nur, wenn die veraltete Rolle
        # ADMIN ist — die veraltete Rolle ist genau das Problem) Admin-Menge
        # UND Zielzeile sperren, erst danach lesen. Beides in EINER nach ID
        # sortierten Anweisung: zwei Anweisungen (erst Admin-Menge, dann Ziel)
        # verklemmten sich mit der sortierten Mehrzeilen-Sperre der
        # Betriebsferien-Buchung, sobald die Ziel-ID vor einer Admin-ID liegt
        # (test_concurrency.py). Die Letzter-Admin-Pruefung laeuft gegen die
        # dabei gesperrte ID-Liste — kein zweites Sperren danach.
        admin_ids = lock_active_admins_and_user(db, current_user.tenant_id, user.id)
        db.refresh(user)
        old_role = user.role
        role_changed = update_data['role'] != old_role
        # Konservativ: auch eine leere Liste (kein anderer aktiver Admin
        # gesperrt) blockiert die Herabstufung eines aktiven Admins.
        if (role_changed and old_role == UserRole.ADMIN and user.is_active
                and not any(aid != user.id for aid in admin_ids)):
            raise HTTPException(status_code=400, detail=LAST_ADMIN_DETAIL)
    # #290: did this update turn closure participation ON? Then enrol below.
    closures_enabled = (
        update_data.get('receives_company_closures') is True
        and not user.receives_company_closures
    )

    for field, value in update_data.items():
        setattr(user, field, value)

    if role_changed:
        user.token_version = (user.token_version or 0) + 1
        _log_account_event(
            db, current_user, EVENT_USER_ROLE_CHANGED, user,
            detail=f"Rolle {_role_label(old_role)} → {_role_label(user.role)}",
        )

    db.commit()
    db.refresh(user)

    # #290: a user newly toggled into Betriebsferien-participation is enrolled
    # into current/future closures here (never deletes logged work), so no
    # closure re-save is needed.
    if closures_enabled:
        _enroll_user_in_open_closures(db, user, current_user)
        db.commit()
    calculation_service.attach_work_blocks_today(db, [user], today_local())
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
    _log_account_event(db, current_user, EVENT_ADMIN_SET_PASSWORD, user,
                       detail="Passwort durch die Verwaltung neu gesetzt")
    db.commit()

    return {"message": f"Passwort für {user.first_name} {user.last_name} wurde gesetzt"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Deactivate a user (soft delete, admin only)."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Sie können sich nicht selbst deaktivieren")

    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)

    # #489: sonst kommt niemand mehr in die Verwaltung.
    if _is_last_active_admin(db, user):
        raise HTTPException(status_code=400, detail=LAST_ADMIN_DETAIL)

    _lock_and_reload(db, current_user, user)  # #491 API-2
    was_active = user.is_active
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.token_version += 1  # Invalidate all existing tokens
    if was_active:
        _log_account_event(db, current_user, EVENT_USER_DEACTIVATED, user,
                           detail=f"Konto deaktiviert (Rolle {_role_label(user.role)})")
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

    _lock_and_reload(db, current_user, user)  # #491 API-2
    was_inactive = not user.is_active
    user.is_active = True
    user.deactivated_at = None
    if was_inactive:
        _log_account_event(db, current_user, EVENT_USER_REACTIVATED, user,
                           detail="Konto reaktiviert")
    db.commit()
    db.refresh(user)
    return user


@router.get("/security-events", response_model=List[SecurityEventResponse])
def list_security_events(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#489: Kontovorgaenge des eigenen Mandanten, neueste zuerst — wer hat wen
    deaktiviert, reaktiviert, umgestuft, wessen Passwort neu gesetzt; dazu die
    Kommandozeilen-Vorgaenge aus #425."""
    rows = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.tenant_id == current_user.tenant_id)  # F-026
        .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
        .limit(limit)
        .all()
    )
    ids = {r.subject_user_id for r in rows if r.subject_user_id}
    for r in rows:
        if r.actor.startswith("user:"):
            try:
                ids.add(uuid.UUID(r.actor[len("user:"):]))
            except ValueError:
                pass
    names = {}
    if ids:
        for u in db.query(User).filter(User.id.in_(ids), User.tenant_id == current_user.tenant_id):
            names[str(u.id)] = f"{u.first_name} {u.last_name}"

    def _actor_name(actor: str) -> str:
        if actor.startswith("user:"):
            return names.get(actor[len("user:"):], "unbekanntes Konto")
        if actor.startswith("cli:"):
            return f"Kommandozeile ({actor[len('cli:'):]})"
        return actor

    return [
        SecurityEventResponse(
            id=r.id, created_at=r.created_at, event=r.event,
            subject_user_id=r.subject_user_id,
            subject_name=names.get(str(r.subject_user_id)) if r.subject_user_id else None,
            actor=r.actor, actor_name=_actor_name(r.actor), detail=r.detail,
        )
        for r in rows
    ]


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


_CHANGE_NOT_FOUND = "Stundenänderung nicht gefunden"
RESET_CONFLICT_DETAIL = "Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."


def _parse_change_body(raw) -> WorkingHoursChangeCreate:
    """Spec 11.1/3.4: Anlegen und Vorschau prüfen den Body mit DERSELBEN Regel;
    ein Verstoß wird deutscher Klartext (``_schedule_input_error``) — beim
    Speichern als 422, in der Vorschau als ``blocked_reason``. Ein bereits
    gebautes Schema (Direktaufruf in Tests) geht unverändert durch."""
    if isinstance(raw, WorkingHoursChangeCreate):
        return raw
    try:
        return WorkingHoursChangeCreate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_schedule_input_error(exc)) from None


def _reset_target(db: Session, user: User, current_user: User, change_data: WorkingHoursChangeCreate):
    """P13: (zurückgesetzte Zeile, ihr Vorgänger-Snapshot) — 404, wenn die Zeile
    nicht im Mandanten bzw. nicht bei dieser Person existiert."""
    if change_data.reset_of_change_id is None:
        return None
    row = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_data.reset_of_change_id,
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=_CHANGE_NOT_FOUND)
    return row, calculation_service.get_schedule_for_date(db, user, row.effective_from - timedelta(days=1))


def _target_blocks(db: Session, user: User, change_data: WorkingHoursChangeCreate, reset_schedule) -> tuple:
    """Welche Blöcke die neue Zeile trägt (Schedule-Format):
    Rücksetzung → die des Vorgängers (auch ein Altfenster, das der Schreibweg
    sonst nie annimmt); Block-Modus → die gesendeten; ``remove_legacy_window``
    → keine; sonst P2/P24 (``_carried_blocks``: Altfenster läuft weiter, neue
    Blöcke enden mit einem Moduswechsel). Aufgelöst VOR dem Anlegen der neuen
    Zeile — P2 meint den vor der Änderung für ``effective_from`` gültigen
    Snapshot."""
    if reset_schedule is not None:
        return reset_schedule.blocks, reset_schedule.block_pauses
    if change_data.blocks is not None:
        parsed = work_blocks_service.parse_week_blocks(change_data.blocks_json())
        return (parsed.blocks, parsed.pauses) if parsed else (None, None)
    if change_data.remove_legacy_window:
        return None, None
    return _carried_blocks(calculation_service.get_schedule_for_date(db, user, change_data.effective_from))


def _reset_matches(change_data: WorkingHoursChangeCreate, norm, reset_schedule) -> bool:
    """P13/11.2: entspricht der Body noch dem Vorgänger-Snapshot der
    zurückgesetzten Zeile? Ein Altfenster ist im Body nicht darstellbar und wird
    deshalb nicht verglichen (der Server übernimmt es selbst)."""
    body = (work_blocks_service.parse_week_blocks(change_data.blocks_json())
            if change_data.blocks is not None else None)
    target = (None if reset_schedule.blocks is None
              else work_blocks_service.ParsedWeek(reset_schedule.blocks, reset_schedule.block_pauses))
    expected = None if work_blocks_service.is_legacy_week(target) else target
    return _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule, norm.day_hours, norm.work_days_per_week,
        body.blocks if body else None, body.pauses if body else None,
    ) == _comparable_snapshot(
        reset_schedule.weekly_hours, reset_schedule.use_daily_schedule, reset_schedule.day_hours,
        reset_schedule.work_days_per_week,
        expected.blocks if expected else None, expected.pauses if expected else None,
    )


BASELINE_ROW_NOTE = "Automatisch erfasster Ausgangswert vor der ersten Stundenänderung"


def _soll_coverage_start(db: Session, user: User, tenant_id) -> Optional[date]:
    """Frühester Tag, dessen Soll in einem Saldo zählt (2. Review Task 10);
    ``None`` = es gibt keinen (weder Buchung noch Jahresübertrag).

    Mit ``first_work_day`` zählt davor kein Soll (Beschäftigungsfenster, #193) —
    dazu, wie bisher bei der Basis-Zeile, die älteste Buchung. Ohne
    ``first_work_day`` der 01.01. des frühesten Jahrs aus ältestem Eintrag,
    ältester Abwesenheit und frühestem Jahresübertrag: das Überstundenkonto zählt
    ab dem 01.01. des Übertragsjahrs bzw. dem Monatsersten des ältesten Eintrags,
    der Jahressaldo (``get_ytd_summary``, Dashboard) ab dem 01.01., der
    Urlaubsverbrauch je Abwesenheitstag — der 01.01. deckt alle zugleich."""
    oldest_entry = db.query(func.min(TimeEntry.date)).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == tenant_id,  # F-026
    ).scalar()
    oldest_absence = db.query(func.min(Absence.date)).filter(
        Absence.user_id == user.id, Absence.tenant_id == tenant_id,  # F-026
    ).scalar()
    candidates = [d for d in (oldest_entry, oldest_absence) if d]
    if user.first_work_day:
        candidates.append(user.first_work_day)
    else:
        years = [d.year for d in candidates]
        oldest_carryover = db.query(func.min(YearCarryover.year)).filter(
            YearCarryover.user_id == user.id, YearCarryover.tenant_id == tenant_id,  # F-026
        ).scalar()
        if oldest_carryover:
            years.append(oldest_carryover)
        if years:
            candidates.append(date(min(years), 1, 1))
    return min(candidates) if candidates else None


def _frozen_row(user: User, tenant_id, effective_from: date, schedule) -> WorkingHoursChange:
    """Verlaufszeile, die den bisher aufgelösten Snapshot UNVERÄNDERT fortschreibt
    — die Rechnung der gedeckten Tage bleibt byte-identisch."""
    return WorkingHoursChange(
        user_id=user.id, tenant_id=tenant_id, effective_from=effective_from,
        weekly_hours=schedule.weekly_hours, use_daily_schedule=schedule.use_daily_schedule,
        hours_monday=schedule.day_hours[0], hours_tuesday=schedule.day_hours[1],
        hours_wednesday=schedule.day_hours[2], hours_thursday=schedule.day_hours[3],
        hours_friday=schedule.day_hours[4], work_days_per_week=schedule.work_days_per_week,
        # E8: die Zeile friert auch die Blöcke der Vergangenheit ein.
        blocks=work_blocks_service.week_blocks_to_json(schedule.blocks, schedule.block_pauses),
        note=BASELINE_ROW_NOTE,
    )


def _freeze_gap_before(db: Session, user: User, tenant_id, first_row: date, coverage: Optional[date]) -> None:
    """Lückenzeile (2. Review Task 10): beginnt die früheste Verlaufszeile
    (``first_row``) nach ``_soll_coverage_start``, deckt eine Zeile ab dort die
    Lücke mit dem bisher aufgelösten Vertrag — vor der frühesten Zeile gibt es
    keine, aufgelöst wird die User-Zeile. Jeder Schreibweg, der die User-Zeile
    danach spiegelt, ruft das VOR dem Spiegel (Anlegen: ``_insert_change_rows``;
    Löschen: ``_delete_change_row``)."""
    if coverage and coverage < first_row:
        current = calculation_service.get_schedule_for_date(db, user, first_row - timedelta(days=1))
        db.add(_frozen_row(user, tenant_id, coverage, current))


def _insert_change_rows(db: Session, user: User, current_user: User, change_data: WorkingHoursChangeCreate,
                        norm, new_blocks, new_pauses) -> WorkingHoursChange:
    """Spec 9.3 Schritt 4 — Basis-Zeile bzw. Lückenzeile, neue Zeile, flush. Die
    Logik ist die bisherige von ``create_working_hours_change``; neu sind die
    Blöcke und die Lückenzeile. Den Spiegel der User-Zeile (E9) macht der
    Schreibpfad erst in Schritt 10 (``_sync_user_to_current_change``) — Review
    Task 10: hier, VOR der Klassifikation, rechnete das Speichern Tage vor der
    Basis-Zeile schon gegen den NEUEN Vertrag, die Vorschau aber nicht; beide
    klassifizierten dieselbe Eingabe verschieden.

    Hintergrund (Release-Review 1.16.0, #415-Folgefund): ``get_schedule_for_date``
    fällt für jeden Tag VOR der ersten Verlaufszeile auf die User-Zeile zurück —
    und genau die überschreibt der Spiegel. Was dort zählt, muss deshalb VORHER
    eine Verlaufszeile decken, die den bisher aufgelösten Snapshot UNVERÄNDERT
    fortschreibt (byte-identisch eingefroren). „Was zählt" beginnt bei
    ``_soll_coverage_start``.

    - Ohne Verlauf (Basis-Zeile): nur, wenn sich der Snapshot tatsächlich ändert
      (#431: der VOLLSTÄNDIGE Snapshot samt Tagesverteilung, Modus und — Spec E8
      — Blöcken; eine reine Blockänderung zählt also). Sie deckt mindestens den
      Vortag der Änderung (I5, Abschluss-Review: ``first_work_day`` ist oft leer)
      und ohne ``first_work_day`` auch dessen Monatsersten (Review Task 10).
    - Mit Verlauf (Lückenzeile, 2. Review Task 10): liegt die älteste Zeile — bzw.
      die neue, wenn sie früher liegt — nach dem Beginn, deckt eine Zeile die
      Lücke davor. Ohne sie verschob der Commit das Soll dieser Tage (Konto,
      Jahressaldo, Urlaubsverbrauch), ohne dass Vorschau, Schutzpaket oder
      Protokoll es sahen (nachgewiesen: Konto −2:00 h bei Vorschau-Saldo 0;
      Realfall der Prod-Kopie: älteste Zeile 12.01., Übertrag 2026, die Tage
      01.–11.01. hingen an der User-Zeile). Bedingungslos: welche Zeile der
      Spiegel wählt, steht erst nach Schritt 10 fest, und eine Zeile mit dem
      bereits gültigen Snapshot ändert keine Rechnung."""
    tenant_id = current_user.tenant_id
    oldest_row = db.query(func.min(WorkingHoursChange.effective_from)).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == tenant_id,  # F-026
    ).scalar()
    coverage = _soll_coverage_start(db, user, tenant_id)
    if oldest_row is None:
        current = calculation_service.get_schedule_for_date(
            db, user, change_data.effective_from - timedelta(days=1))
        if _comparable_snapshot(
            current.weekly_hours, current.use_daily_schedule, current.day_hours,
            current.work_days_per_week, current.blocks, current.block_pauses,
        ) != _comparable_snapshot(
            norm.weekly_hours, norm.use_daily_schedule, norm.day_hours,
            norm.work_days_per_week, new_blocks, new_pauses,
        ):
            candidates = [change_data.effective_from - timedelta(days=1)]
            if coverage:
                candidates.append(coverage)
            if not user.first_work_day:
                candidates.append(change_data.effective_from.replace(day=1))  # erster Monat der Saldo-Prüfung
            db.add(_frozen_row(user, tenant_id, min(candidates), current))
    else:
        _freeze_gap_before(db, user, tenant_id, min(oldest_row, change_data.effective_from), coverage)
    change = WorkingHoursChange(
        user_id=user.id, tenant_id=tenant_id, effective_from=change_data.effective_from,
        weekly_hours=norm.weekly_hours, use_daily_schedule=norm.use_daily_schedule,
        hours_monday=norm.day_hours[0], hours_tuesday=norm.day_hours[1],
        hours_wednesday=norm.day_hours[2], hours_thursday=norm.day_hours[3],
        hours_friday=norm.day_hours[4],
        # NULL hieße „Rückfall auf die (jederzeit änderbare) User-Zeile" — der
        # Rückfall steckt in _normalise_schedule_input, gemeinsam mit der Vorschau.
        work_days_per_week=norm.work_days_per_week,
        blocks=work_blocks_service.week_blocks_to_json(new_blocks, new_pauses),
        note=change_data.note,
    )
    db.add(change)
    # Finding 4 (Review 2026-07-14): autoflush=False — ohne flush sähen die
    # folgenden Abfragen (Rechenpfad) die neue Zeile nicht.
    db.flush()
    return change


def _sync_user_to_current_change(db: Session, user: User, tenant_id) -> None:
    """Spec 9.3 Schritt 10 (E9): die User-Zeile spiegelt die jüngste Zeile mit
    Datum ≤ heute. Erst NACH Klassifikation, Schutzpaket und Protokoll — sonst
    rechnet das Speichern einen anderen Zustand als die Vorschau (Review Task 10).
    Die Abfrage statt der gerade angelegten Zeile: eine spätere, bereits gültige
    Zeile gewinnt."""
    most_recent = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == tenant_id,  # F-026
        WorkingHoursChange.effective_from <= today_local(),
    ).order_by(WorkingHoursChange.effective_from.desc()).first()
    if most_recent:
        # #431: der VOLLSTÄNDIGE Snapshot wandert zurück auf die User-Zeile —
        # _sync_user_from_change ist DIE eine Stelle dafür (create und delete).
        _sync_user_from_change(user, most_recent)


def _log_reclamp(db: Session, *, user: User, admin: User, impact, effective_from: date, deleted: bool,
                 reason_type: Optional[str], reason_text: Optional[str], reset_of: Optional[date]) -> None:
    """Spec 10.1/10.2 — je neu gekapptem Eintrag eine Zeile und IMMER genau eine
    Sammelzeile (P20: auch ohne Einträge, auch zukunftsdatiert). Per ``db.add``
    (row_hash, #121), kein Bulk-UPDATE; die Vorschau ruft das nie (10.3)."""
    shortening = impact.is_shortening
    changed = impact.reclamp.changed
    entries = {}
    if changed:
        entries = {e.id: e for e in db.query(TimeEntry).filter(
            TimeEntry.id.in_([c.entry_id for c in changed]),
            TimeEntry.tenant_id == user.tenant_id,  # F-026
        ).all()}
    for c in changed:
        e = entries[c.entry_id]
        db.add(TimeEntryAuditLog(
            time_entry_id=e.id, user_id=user.id, changed_by=admin.id, action="update",
            source=reclamp_audit.AUDIT_SOURCE, old_date=e.date, new_date=e.date,
            old_start_time=c.old_start, old_end_time=c.old_end,
            new_start_time=c.new_start, new_end_time=c.new_end,
            old_break_minutes=e.break_minutes, new_break_minutes=e.break_minutes,
            old_note=work_window_service.credit_summary_text(impact.entries_before[c.entry_id]),
            new_note=reclamp_audit.entry_new_note(
                work_window_service.credit_summary_text(e), effective_from=effective_from, deleted=deleted,
                old_grace=c.old_grace, grace=impact.grace, shortening=shortening,
                reason_type=reason_type, reason_text_value=reason_text),
            tenant_id=user.tenant_id,
        ))
    db.add(TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=admin.id, action="update",
        source=reclamp_audit.AUDIT_SOURCE,
        new_note=reclamp_audit.summary_note(
            effective_from=effective_from, deleted=deleted, count=len(changed),
            delta_minutes=int(round(sum(float(c.new_net - c.old_net) for c in changed) * 60)),
            saldo_delta_minutes=int(round(float(impact.saldo_delta) * 60)),
            skipped=dict(Counter(s.reason for s in impact.reclamp.skipped)),
            grace=impact.grace, credit_reductions=len(impact.credit_reductions), reset_of=reset_of,
            shortening=shortening, reason_type=reason_type, reason_text_value=reason_text,
            contract_before=reclamp_audit.contract_text(impact.old_schedule, compact=True),
            contract_after=reclamp_audit.contract_text(impact.new_schedule, compact=True),
        ),
        tenant_id=user.tenant_id,
    ))


@router.post("/users/{user_id}/working-hours-changes", response_model=WorkingHoursChangeResponse, status_code=status.HTTP_201_CREATED)
def create_working_hours_change(
    user_id: str,
    change_data: Annotated[Any, Body()],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Arbeitszeit-Änderung anlegen (Spec 9.3) — eine Transaktion unter der
    Ankersperre: Rechenpfad ``wh_change_service.run_change`` (P23-Schließen,
    Neukappung, F1-Rückrechnung, Klassifikation), Schutzpaket (9.5), Protokoll
    (10), Jahresabschluss-Warnung, commit. Ein Verstoß rollt ALLES zurück.

    Der Body wird untypisiert angenommen und über ``_parse_change_body`` geprüft
    — dieselbe Regel und derselbe deutsche Text wie in der Vorschau (11.1).

    Fix #2/#431: Tagesplan-Mitarbeitende sind hier seit #431 zugelassen — die
    Zeile trägt den VOLLSTÄNDIGEN Vertrags-Snapshot, und das Tagessoll rechnet
    gegen den datumsaufgelösten Snapshot (Test
    test_wh_change_day_plan_create.py::test_change_actually_moves_the_daily_target)."""
    change_data = _parse_change_body(change_data)
    user = _get_user_in_tenant(db, user_id, current_user)
    # E52/P5: Ankersperre ZUERST — vor Snapshot, clamp und jeder Zeilensperre;
    # parallele Schreiber warten und lösen danach den neuen Snapshot auf. Das
    # setzt das Neuladen voraus (#491 API-2): ``_get_user_in_tenant`` las
    # ungesperrt, und die Sperre allein überschreibt die geladenen Attribute
    # nicht — Neukappung (track_hours, Beschäftigungsfenster), Normalisierung
    # und ``_sync_user_from_change`` rechneten sonst auf dem Stand VOR einer
    # gerade committeten Gegenseite (E9: User-Zeile ≠ jüngste Zeile ≤ heute).
    _lock_and_reload(db, current_user, user)

    if db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from == change_data.effective_from,
    ).first():
        raise HTTPException(
            status_code=400,
            detail=f"Eine Stundenänderung für den {change_data.effective_from.strftime('%d.%m.%Y')} existiert bereits",
        )

    reset = _reset_target(db, user, current_user, change_data)
    reset_row, reset_schedule = reset if reset else (None, None)
    # #431: die Eingabe wird ab hier ausschließlich über ``norm`` gelesen —
    # dieselbe Normalisierung wie in der Vorschau.
    norm = _normalise_schedule_input(change_data, user)
    if reset_schedule is not None and not _reset_matches(change_data, norm, reset_schedule):
        raise HTTPException(status_code=409, detail=RESET_CONFLICT_DETAIL)
    new_blocks, new_pauses = _target_blocks(db, user, change_data, reset_schedule)

    created = {}

    def _apply():
        created["row"] = _insert_change_rows(db, user, current_user, change_data, norm, new_blocks, new_pauses)

    impact = wh_change_service.run_change(
        db, user, admin_id=current_user.id, effective_from=change_data.effective_from, apply=_apply)
    error = wh_change_service.protection_error(impact, change_data, deleting=False, reset_offered=False)
    if error:
        db.rollback()  # verwirft Schritte 2–6 (9.3 Schritt 7)
        raise HTTPException(status_code=400, detail=error)

    change = created["row"]
    reason_type = change_data.retroactive_reason_type if impact.is_shortening else None
    change.note = reclamp_audit.compose_change_note(
        change_data.note, reason_type, change_data.retroactive_reason_text)
    _log_reclamp(db, user=user, admin=current_user, impact=impact, effective_from=change_data.effective_from,
                 deleted=False, reason_type=reason_type, reason_text=change_data.retroactive_reason_text,
                 reset_of=reset_row.effective_from if reset_row else None)
    _log_wh_change_retarget(
        db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
        effective_from=impact.window.start, period_end=impact.window.end, adjusted=impact.absences,
        prefix="Arbeitszeit-Änderung", suffix="auf neues Tagessoll nachgezogen",
    )
    # Fix #5: abgeschlossenes Jahr im Wirkungsbereich → nur melden, nie neu
    # rechnen (könnte manuelle Anpassungen überschreiben). Bewusst unabhängig von
    # der Rückrechnung: die Änderung verschiebt das Soll jedes Arbeitstags im
    # Wirkungsbereich, nicht nur das der Abwesenheitstage.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id, range(impact.window.start.year, impact.window.end.year + 1))
    if change_data.effective_from <= today_local():
        _sync_user_to_current_change(db, user, current_user.tenant_id)  # Schritt 10
    db.commit()
    db.refresh(change)
    # Die API-Zusage bleibt je eine ZAHL — die Einzelheiten stehen im Protokoll.
    change.adjusted_absences = len(impact.absences)
    change.adjusted_time_entries = len(impact.reclamp.changed)
    change.skipped_time_entries = len(impact.reclamp.skipped)
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


_SCHEDULE_FIELD_LABELS = {
    "weekly_hours": "Die Wochenstunden",
    "hours_monday": "Die Stunden für Montag",
    "hours_tuesday": "Die Stunden für Dienstag",
    "hours_wednesday": "Die Stunden für Mittwoch",
    "hours_thursday": "Die Stunden für Donnerstag",
    "hours_friday": "Die Stunden für Freitag",
    "work_days_per_week": "Die Arbeitstage pro Woche",
    "retroactive_reason_text": "Die Begründung",
}

_BLOCK_FIELD_LABELS = {"start": "Beginn", "end": "Ende"}


# Spec 3.4: Wurzel der Wochen-Liste in ``WorkingHoursChangeCreate`` (``blocks``)
# und ``UserCreate`` (``work_blocks``) — darunter dieselbe Form ``DayBlocksIn``.
_BLOCK_ROOTS = frozenset({"blocks", "work_blocks"})


def _nested_block_label(loc: tuple) -> Optional[str]:
    """Spec 3.4: ``("blocks", 0, "blocks", 1, "start")`` → „Mo, Block 2, Beginn",
    ``("blocks", 0, "pause_minutes")`` → „Mo, Pause"; dieselben Pfade unter
    ``work_blocks`` (Anlegen, ``UserCreate``). Unerwartete Form → ``None``
    (der Aufrufer fällt auf den generischen Text zurück — nie IndexError/500)."""
    if len(loc) < 2 or loc[0] not in _BLOCK_ROOTS or not isinstance(loc[1], int) or not 0 <= loc[1] < 5:
        return None
    label = work_blocks_service.WEEKDAY_LABELS[loc[1]]
    rest = loc[2:]
    if not rest:
        return label
    if rest[0] == "pause_minutes":
        return f"{label}, Pause"
    if rest[0] == "blocks" and len(rest) >= 2 and isinstance(rest[1], int):
        text = f"{label}, Block {rest[1] + 1}"
        if len(rest) >= 3 and rest[2] in _BLOCK_FIELD_LABELS:
            text += f", {_BLOCK_FIELD_LABELS[rest[2]]}"
        return text
    if rest[0] == "blocks":
        return label
    return None


def _block_root_error(loc: tuple) -> Optional[str]:
    """Spec 3.4, Regel „genau 5 Einträge": ein Verstoß an der Wurzel der Woche,
    den Pydantic VOR ``validate_week_blocks`` abfängt — ``blocks``/``work_blocks``
    als String oder Objekt (``list_type`` an ``("work_blocks",)``) oder ein
    Typfehler ab dem sechsten Tag (``("work_blocks", 5, …)``). Beides heißt „keine
    Woche aus fünf Tagen" und bekommt denselben Text, den die Regel bei ``[]``
    oder sechs gültigen Tagen liefert; ohne diesen Zweig kam beim Anlegen FastAPIs
    englische Standard-422, in der Vorschau „Ungültige Eingabe.".

    Mo–Fr (Index 0–4) gehören dem Tageslabel (``_nested_block_label``) → ``None``."""
    if not loc or loc[0] not in _BLOCK_ROOTS:
        return None
    if len(loc) == 1 or (isinstance(loc[1], int) and not 0 <= loc[1] < 5):
        return work_blocks_service.WEEK_SHAPE_TEXT
    return None


def _schedule_input_error(exc: ValidationError) -> str:
    """Ein Verstoß gegen die Snapshot-Regeln als deutscher Klartext für
    ``blocked_reason``.

    Deckt BEIDE Regel-Ebenen von ``WorkingHoursChangeCreate`` ab: die
    Feldgrenzen aus ``WorkingHoursChangeBase`` (``ge``/``le``) und den
    ``check_mode``-Validator (dessen Meldung schon ein fertiger deutscher Satz
    ist, dem Pydantic nur ``Value error, `` voranstellt).

    Review-Fund 2 (Fix-Runde 1): Die Grenzen standen zusätzlich an den
    ``Query(...)``-Parametern der Vorschau. Das war doppelt gepflegt (Drift
    sobald eine Grenze im Schema wandert — genau die Fehlerklasse, gegen die der
    gemeinsame Pfad gebaut ist) UND es unterlief die Entscheidung „blocked_reason
    statt 4xx": FastAPI lehnte vor dem Handler mit 422 ab, und der Admin, der auf
    dem Weg zu „44,4" kurz „444" stehen hat, bekam mitten im Tippen einen harten
    Fehler statt eines Hinweises. Die Grenzen leben jetzt nur noch im Schema.

    Der Leer-Fallback ist kein toter Code-Schmuck: dieser Endpoint läuft bei
    JEDER Eingabe im Dialog (debounced), ein IndexError hier wäre ein HTTP 500
    mitten im Tippen.

    Den Kern (``_labelled_input_error``) teilt sich das Anlegen
    (``_parse_user_create_body``, Spec 3.4 gilt für beide Schreibschemas).
    """
    return _labelled_input_error(exc) or "Ungültige Eingabe."


def _labelled_input_error(exc: ValidationError) -> Optional[str]:
    """Kern von ``_schedule_input_error``: der deutsche Text zum ERSTEN Verstoß,
    oder ``None``, wenn es keinen gibt (kein Regeltext, kein Feld-Label).

    ``None`` statt „Ungültige Eingabe.", damit ``_parse_user_create_body`` dann
    bei FastAPIs Standard-422 bleiben kann — die nennt wenigstens das Feld."""
    errors = exc.errors()
    if not errors:
        return None
    err = errors[0]
    if err.get("type") == "value_error":
        return str(err.get("msg", "Ungültige Eingabe.")).removeprefix("Value error, ")
    loc = tuple(err.get("loc") or ())
    root = _block_root_error(loc)
    if root is not None:
        return root
    # Spec 3.4: Typfehler in den verschachtelten Blöcken (z. B. Beginn als Zahl)
    # bekommen „Mo, Block 2, Beginn" als Label; die Regeltexte selbst kommen als
    # value_error aus ``validate_week_blocks`` (Zweig darüber).
    nested = _nested_block_label(loc)
    if nested is not None:
        return f"{nested}: ungültiger Wert."
    label = next(
        (_SCHEDULE_FIELD_LABELS[p] for p in (err.get("loc") or ())
         if p in _SCHEDULE_FIELD_LABELS),
        None,
    )
    if label is None:
        return None
    ctx = err.get("ctx") or {}
    # P15: Länge der Begründung (10–400 Zeichen).
    if "min_length" in ctx:
        return f"{label} muss mindestens {ctx['min_length']} Zeichen lang sein."
    if "max_length" in ctx:
        return f"{label} darf höchstens {ctx['max_length']} Zeichen lang sein."
    # Die Begründung ist das einzige Label im Singular (und das einzige Textfeld):
    # der Plural-Ausweichtext unten ergäbe „Die Begründung sind kein gültiger Wert."
    # Erreichbar über einen selbst gebauten Body (POST-Vorschau, 422 beim Anlegen).
    if "retroactive_reason_text" in (err.get("loc") or ()):
        return "Die Begründung muss ein Text sein."
    if "le" in ctx:
        return f"{label} dürfen höchstens {_limit_de(ctx['le'])} betragen."
    if "ge" in ctx:
        return f"{label} dürfen nicht kleiner als {_limit_de(ctx['ge'])} sein."
    return f"{label} sind kein gültiger Wert."


def _limit_de(value) -> str:
    """Feldgrenze im deutschen Zahlenformat: Pydantic liefert sie bei
    ``float``-Feldern als ``60.0`` — „höchstens 60.0" wäre im deutschen Satz
    falsch. ``60.0`` → „60", ``7.5`` → „7,5"; Nicht-Zahlen unverändert."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}".replace(".", ",")
    return str(value)


PREVIEW_DATE_MISSING = "Bitte ein gültiges Wirkungsdatum angeben."


def _week_day_targets(user: User, effective_from: date, schedule) -> List[float]:
    """Tagessoll je Wochentag Mo…Fr des übergebenen Snapshots (Vorschaufelder
    ``day_targets_current``/``day_targets_new``; Anlegen- und Lösch-Vorschau).

    Fund 3 (Release-Review 1.17.0), #431 erweitert: je WOCHENTAG statt für den
    Stichtag — ``get_daily_target_for_date`` liefert am Wochenende hart 0 (das
    Wirkungsdatum ist oft ein Monatserster, 4 der 12 Monatsersten 2026 fallen
    aufs Wochenende), und ein Einzelwert bildet einen Tagesplan nicht ab. Nur
    der Wochentag geht in die Rechnung ein (der Snapshot ist explizit
    übergeben) — der Montag der Woche des Wirkungsdatums genügt als Träger."""
    week_monday = effective_from - timedelta(days=effective_from.weekday())
    return [float(calculation_service.get_daily_target_for_date(user, week_monday + timedelta(days=i), schedule))
            for i in range(5)]


@router.post("/users/{user_id}/working-hours-changes/preview", response_model=WorkingHoursChangePreview)
def preview_working_hours_change(
    user_id: str,
    body: Annotated[Any, Body()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Spec 11.1/11.3 — strikt lesende Vorschau VOR dem Speichern. Body wie beim
    Speichern, aber UNTYPISIERT entgegengenommen und intern mit DERSELBEN Regel
    geprüft (``WorkingHoursChangeCreate`` + ``_normalise_schedule_input``): ein
    Verstoß ist ``blocked_reason`` (``_schedule_input_error``), nie ein hartes 422
    mitten im Tippen — auch nicht bei unfertigen Blöcken (leeres Feld, Pause
    leer, ``08:07``). Ebenso als ``blocked_reason``: fehlendes/ungültiges
    Wirkungsdatum, eine fremde oder nicht mehr passende Rücksetzung (P13) und
    ein bereits belegtes Datum — der Dialog läuft so nie erst in einen 400/409.

    Führt dieselben Schritte 2–7 wie das Speichern (``wh_change_service.run_change``:
    P23-Schließen, Neukappung, F1-Rückrechnung, Klassifikation) in EINEM
    flush/Rollback-Lauf aus und rollt IMMER zurück — auch im Fehlerfall: nichts
    wird geschrieben, nichts protokolliert, keine Ankersperre (9.3). Der offene
    Eintrag von heute bleibt unangetastet (``clock_out`` wartet nicht).

    Das alte ``GET …/preview`` entfällt (ein gecachtes Frontend bekommt 405)."""
    # _get_user_in_tenant raises 404 itself (never returns None) — see get_user.
    user = _get_user_in_tenant(db, user_id, current_user)
    today = today_local()
    raw = body if isinstance(body, dict) else {}
    value = raw.get("effective_from")
    try:
        effective_from = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        effective_from = None
    date_error = None
    if effective_from is None:
        date_error = PREVIEW_DATE_MISSING
    elif not effective_from_plausible(effective_from):
        # Review Task 10: Zwischenwerte beim Tippen der Jahreszahl (``0202-09-01``)
        # liest ``fromisoformat`` als echtes Datum — gerechnet würde über
        # Jahrhunderte. Weder Fenster noch Rechenpfad; der Text ist derselbe wie
        # beim Speichern (2. Review Task 10) — der Dialog sperrt Speichern,
        # solange ``blocked_reason`` steht, die Admin muss die Grenze also hier
        # erfahren.
        date_error = EFFECTIVE_FROM_RANGE_DETAIL
    if date_error is not None:
        # Ohne (plausibles) Datum gibt es keinen Wirkungsbereich — gerechnet wird
        # nichts, die Kopfwerte beziehen sich auf heute.
        effective_from, raw = today, {}

    # Bedeutung von ``is_retroactive`` unverändert: „das Wirkungsdatum liegt VOR
    # heute". Der Zeitraum (period_start/period_end) ist dagegen der echte
    # Wirkungsbereich (``retarget_window``), der auch in der Zukunft liegen kann
    # (Release-Review 1.17.0).
    window = calculation_service.retarget_window(db, user, effective_from)
    current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    input_error = date_error
    change_data = norm = reset_schedule = None
    if input_error is None:
        try:
            change_data = WorkingHoursChangeCreate.model_validate(raw)
            norm = _normalise_schedule_input(change_data, user)
        except ValidationError as exc:
            # ``date.fromisoformat`` nimmt auch Formen an, die das Speichern
            # (Pydantic) ablehnt (``20260901``, ``2026-W36-2``) — dort ist das
            # Datum ebenso ungültig, und der Dialog soll denselben Satz zeigen
            # wie bei einem fehlenden Datum, nicht „Ungültige Eingabe.".
            date_invalid = any(tuple(e.get("loc") or ())[:1] == ("effective_from",) for e in exc.errors())
            input_error = PREVIEW_DATE_MISSING if date_invalid else _schedule_input_error(exc)
    if change_data is not None and input_error is None and change_data.reset_of_change_id is not None:
        try:
            reset_schedule = _reset_target(db, user, current_user, change_data)[1]
            if not _reset_matches(change_data, norm, reset_schedule):
                input_error = RESET_CONFLICT_DETAIL
        except HTTPException as exc:
            input_error = str(exc.detail)

    # Verletzt die Eingabe eine Regel, gibt es keinen Snapshot zum Vorrechnen —
    # „neu" bleibt gleich „aktuell" (lieber gar keine Änderung anzeigen als eine
    # erfundene).
    new_schedule = current_schedule
    new_blocks, new_pauses = current_schedule.blocks, current_schedule.block_pauses
    if norm is not None and input_error is None:
        new_blocks, new_pauses = _target_blocks(db, user, change_data, reset_schedule)
        new_schedule = calculation_service.Schedule(
            weekly_hours=Decimal(str(norm.weekly_hours)),
            use_daily_schedule=norm.use_daily_schedule,
            day_hours=tuple(None if v is None else Decimal(str(v)) for v in norm.day_hours),
            work_days_per_week=norm.work_days_per_week,
            blocks=new_blocks,
            block_pauses=new_pauses,
        )
    day_targets_current = _week_day_targets(user, effective_from, current_schedule)
    day_targets_new = _week_day_targets(user, effective_from, new_schedule)

    # Gleiche Ablehnungsgründe wie das Speichern: ungültige Eingabe zuerst, dann
    # Datum bereits belegt. Ein Insert mit belegtem Datum ergäbe zudem zwei
    # Zeilen mit identischem ``effective_from`` — die Auflösung wählte dann
    # reproduzierbar die BESTEHENDE, gerechnet würde gegen den falschen Vertrag.
    blocked_reason = input_error
    if not blocked_reason and db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
        WorkingHoursChange.effective_from == effective_from,
    ).first():
        blocked_reason = f"Eine Stundenänderung für den {effective_from.strftime('%d.%m.%Y')} existiert bereits"

    # Kurzschluss „Snapshot unverändert" (Review-Fund 1, Fix-Runde 1) — der
    # häufigste Fall (der Dialog ist vorbefüllt) und fachlich exakt: eine Zeile
    # mit identischem Snapshot verschiebt im Wirkungsbereich kein Tagessoll und
    # kappt nichts neu. Spec 11.3: der Vergleich schließt kanonische Blöcke und
    # Pausen ein — eine reine Blockänderung IST eine Änderung.
    snapshot_unchanged = norm is not None and not blocked_reason and _comparable_snapshot(
        current_schedule.weekly_hours, current_schedule.use_daily_schedule,
        current_schedule.day_hours, current_schedule.work_days_per_week,
        current_schedule.blocks, current_schedule.block_pauses,
    ) == _comparable_snapshot(
        norm.weekly_hours, norm.use_daily_schedule, norm.day_hours, norm.work_days_per_week,
        new_blocks, new_pauses,
    )

    # Saldo und Urlaub im IST-Zustand — vor dem Lauf, damit sie die hypothetische
    # Zeile garantiert nicht sehen. Review-Fund 4 (Fix-Runde 1): Monatsobergrenze
    # = heute wie in den Live-Anzeigen (``dashboard.get_overtime_account``,
    # ``users_overview``), getrimmt über den Stichtag (#313).
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    vacation_year = window.start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, today.year, today.month, cutoff_date=cutoff))
    vacation_before = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before
    fields: dict = {"affected_absences": 0}
    if not blocked_reason and not snapshot_unchanged:
        # EIN flush/Rollback-Lauf für alles (Spec 11.3): ``overtime_after`` und
        # alle Δ-Felder stammen aus dem Zustand, in dem Neukappung und
        # Rückrechnung AUSGEFÜHRT wurden. ``run_change`` liegt komplett im
        # ``try`` (Review-Fund 3, Fix-Runde 1): auch ein Fehler schon beim Insert
        # läuft durch das ``finally`` — es gibt keinen Pfad an der
        # Rollback-Garantie vorbei. Protokolliert wird nie (10.3).
        try:
            impact = wh_change_service.run_change(
                db, user, admin_id=current_user.id, effective_from=effective_from,
                apply=lambda: _insert_change_rows(db, user, current_user, change_data, norm,
                                                  new_blocks, new_pauses),
            )
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, today.year, today.month, cutoff_date=cutoff))
            vacation_after = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
            fields = wh_change_service.preview_fields(impact, user)
        finally:
            db.rollback()

    # closed_years: ALLE im Zeitraum berührten abgeschlossenen Jahre;
    # closed_year_warning der fertige Text für das früheste.
    closed_years = calculation_service.closed_years_in_range(
        db, current_user.tenant_id, range(window.start.year, window.end.year + 1))
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    notices = []
    if change_data is not None and change_data.blocks is not None and input_error is None:
        # P9: nicht blockierende Plan-Hinweise aus dem gesendeten Tagesplan.
        notices = work_blocks_service.block_break_notices(
            change_data.blocks_json(), grace, exempt=bool(getattr(user, "exempt_from_arbzg", False)))

    return WorkingHoursChangePreview(
        is_retroactive=effective_from < today,
        period_start=window.start,
        period_end=window.end,
        current_daily_target=_planned_day_mean(day_targets_current),
        new_daily_target=_planned_day_mean(day_targets_new),
        day_targets_current=day_targets_current,
        day_targets_new=day_targets_new,
        overtime_before=overtime_before,
        overtime_after=overtime_after,
        vacation_days_before=vacation_before,
        vacation_days_after=vacation_after,
        blocked_reason=blocked_reason,
        closed_years=closed_years,
        closed_year_warning=calculation_service.closed_year_warning_text(closed_years),
        grace_minutes=grace,
        blocks_current=work_blocks_service.week_blocks_to_json(current_schedule.blocks, current_schedule.block_pauses),
        blocks_new=work_blocks_service.week_blocks_to_json(new_blocks, new_pauses),
        block_break_notices=notices,
        **fields,
    )


def _change_in_tenant(db: Session, user_id: str, change_id, current_user: User) -> WorkingHoursChange:
    """F-026: Verlaufszeile der Person im Mandanten, sonst 404 — vor jeder
    Sperre (eine fremde oder unbekannte ID verrät nichts und wartet auf nichts)."""
    change = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.id == change_id,
        WorkingHoursChange.user_id == user_id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,
    ).first()
    if not change:
        raise HTTPException(status_code=404, detail=_CHANGE_NOT_FOUND)
    return change


EARLIEST_ROW_LOCK_DETAIL = (
    "Dies ist die früheste erfasste Stundenänderung dieses "
    "Mitarbeiters — sie verankert den davor gültigen Wert, der "
    "sonst nirgends mehr gespeichert ist. Bitte zuerst die "
    "späteren Änderungen löschen, wenn die Historie komplett "
    "zurückgesetzt werden soll."
)


def _earliest_row_lock_detail(db: Session, user: User, current_user: User,
                              change: WorkingHoursChange) -> Optional[str]:
    """Critical fix (Review-Fund, bestehende Regel): die früheste Zeile verankert
    den davor gültigen Wert — gesperrt, solange spätere existieren.

    Hintergrund: für jeden Tag VOR der frühesten Zeile fällt
    ``get_schedule_for_date`` auf die User-Zeile zurück, die der Spiegel nach
    dem Löschen mit dem Wert einer SPÄTEREN Zeile überschreibt. Realfall: 40-h-
    Basis-Zeile + spätere 20-h-Änderung; das Löschen der Basis halbierte eine
    korrekt mit 8 h gebuchte Abwesenheit. Die einzige Zeile darf weiter gelöscht
    werden (die User-Zeile ist dann wieder die alleinige Quelle)."""
    rows = db.query(WorkingHoursChange.id).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
    ).order_by(WorkingHoursChange.effective_from.asc()).limit(2).all()
    if len(rows) > 1 and rows[0].id == change.id:
        return EARLIEST_ROW_LOCK_DETAIL
    return None


def _delete_change_row(db: Session, user: User, current_user: User, change: WorkingHoursChange) -> None:
    """Spec 9.7 — Schritt 4 beim Löschen (Gegenstück zu ``_insert_change_rows``),
    für Löschen UND Lösch-Vorschau: Lückenzeile, Zeile löschen, flush.

    Nachtrag Review Task 10: Tage vor der ältesten verbleibenden Zeile lösen über
    die User-Zeile auf, und deren Spiegel nach dem Löschen (Schritt 10) verschöbe
    ihr Soll an Konto, Jahressaldo und Urlaubsverbrauch vorbei — ohne dass
    Vorschau, Schutzpaket oder Protokoll es sahen (Realfall MMK der Prod-Kopie,
    beim Anlegen nachgewiesen). ``_freeze_gap_before`` deckt die Lücke deshalb
    VOR dem Spiegel mit dem bisher aufgelösten Vertrag. Entfällt nur, wenn die
    gelöschte Zeile die einzige ist (keine Zeile, vor der eine Lücke läge —
    Bestandsverhalten). Die früheste Zeile ist bei mehreren gesperrt
    (``_earliest_row_lock_detail``), die älteste verbleibende also die älteste."""
    tenant_id = current_user.tenant_id
    oldest_remaining = db.query(func.min(WorkingHoursChange.effective_from)).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == tenant_id,  # F-026
        WorkingHoursChange.id != change.id,
    ).scalar()
    if oldest_remaining is not None:
        _freeze_gap_before(db, user, tenant_id, oldest_remaining, _soll_coverage_start(db, user, tenant_id))
    db.delete(change)
    # autoflush=False — ohne flush sähen die folgenden Abfragen des Rechenpfads
    # die Zeile noch (Finding 4, Review 2026-07-14).
    db.flush()


def _parse_delete_body(raw) -> Optional[WorkingHoursChangeDelete]:
    """Spec 9.7/P8: optionaler DELETE-Body (Schutzpaket). Untypisiert angenommen
    und mit DERSELBEN Regel und demselben deutschen Text geprüft wie der
    Anlege-Body (``_parse_change_body``) — z. B. „Die Begründung muss mindestens
    10 Zeichen lang sein." statt FastAPIs englischer Standard-422. Kein Body →
    ``None``; ein gebautes Schema (Direktaufruf in Tests) geht unverändert
    durch."""
    if raw is None or isinstance(raw, WorkingHoursChangeDelete):
        return raw
    try:
        return WorkingHoursChangeDelete.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_schedule_input_error(exc)) from None


@router.post("/users/{user_id}/working-hours-changes/{change_id}/delete-preview",
             response_model=WorkingHoursChangePreview)
def delete_preview_working_hours_change(
    user_id: str,
    change_id: str,
    body: Annotated[Any, Body()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Spec 9.7/P8 — Vorschau des Löschens (gleiche Antwortform wie die
    Vorschau, 11.3): dieselben Schritte 2–7 wie das Löschen
    (``wh_change_service.run_change`` mit ``_delete_change_row``) in EINEM
    flush/Rollback-Lauf, der IMMER zurückrollt — nichts wird geschrieben,
    nichts protokolliert, keine Ankersperre (9.3). Klassifikation nach 9.5
    (a)–(c), bezogen auf den Wechsel zum Vorgänger-Snapshot.

    ``reset_body`` (P13): fertiger Anlege-Body „ab ‹Datum› auf den vorherigen
    Stand zurücksetzen" — nur, wenn das Löschen verkürzt und das früheste
    verlustfreie Datum nach dem Wirkungsdatum der Zeile liegt (vor der nächsten
    Änderung, P25: sonst ist es ``null``). Die früheste Zeile → ``blocked_reason``.
    Der Body wird nicht gebraucht und nie geprüft (11.1: untypisiert)."""
    change = _change_in_tenant(db, user_id, change_id, current_user)
    user = _get_user_in_tenant(db, user_id, current_user)
    today = today_local()
    effective_from = change.effective_from
    row_id = change.id
    window = calculation_service.retarget_window(db, user, effective_from)
    current_schedule = calculation_service.get_schedule_for_date(db, user, effective_from)
    # Nach dem Löschen gilt ab ``effective_from`` der Snapshot des Vortags.
    predecessor = calculation_service.get_schedule_for_date(db, user, effective_from - timedelta(days=1))
    blocked_reason = _earliest_row_lock_detail(db, user, current_user, change)
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    vacation_year = window.start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, today.year, today.month, cutoff_date=cutoff))
    vacation_before = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before
    fields: dict = {"affected_absences": 0}
    reset = None
    if not blocked_reason:
        # Wie die Anlege-Vorschau: ``run_change`` komplett im ``try`` — kein Pfad
        # an der Rollback-Garantie vorbei.
        try:
            impact = wh_change_service.run_change(
                db, user, admin_id=current_user.id, effective_from=effective_from,
                apply=lambda: _delete_change_row(db, user, current_user, change),
            )
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, today.year, today.month, cutoff_date=cutoff))
            vacation_after = float(calculation_service.get_vacation_account(db, user, vacation_year)["used_days"])
            fields = wh_change_service.preview_fields(impact, user)
            earliest = impact.earliest_lossless_date
            if impact.is_shortening and earliest is not None and earliest > effective_from:
                reset = wh_change_service.reset_body(predecessor, earliest, row_id)
        finally:
            db.rollback()
    closed_years = calculation_service.closed_years_in_range(
        db, current_user.tenant_id, range(window.start.year, window.end.year + 1))
    day_targets_current = _week_day_targets(user, effective_from, current_schedule)
    day_targets_new = _week_day_targets(user, effective_from, predecessor)
    return WorkingHoursChangePreview(
        is_retroactive=effective_from < today,
        period_start=window.start,
        period_end=window.end,
        current_daily_target=_planned_day_mean(day_targets_current),
        new_daily_target=_planned_day_mean(day_targets_new),
        day_targets_current=day_targets_current,
        day_targets_new=day_targets_new,
        overtime_before=overtime_before,
        overtime_after=overtime_after,
        vacation_days_before=vacation_before,
        vacation_days_after=vacation_after,
        blocked_reason=blocked_reason,
        closed_years=closed_years,
        closed_year_warning=calculation_service.closed_year_warning_text(closed_years),
        grace_minutes=work_window_service.get_grace_minutes(db, current_user.tenant_id),
        blocks_current=work_blocks_service.week_blocks_to_json(current_schedule.blocks, current_schedule.block_pauses),
        blocks_new=work_blocks_service.week_blocks_to_json(predecessor.blocks, predecessor.block_pauses),
        reset_body=reset,
        **fields,
    )


@router.delete("/users/{user_id}/working-hours-changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_working_hours_change(
    user_id: str,
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    body: Annotated[Any, Body()] = None,
):
    """Spec 9.7 — symmetrisches Löschen: dieselbe Transaktion wie das Anlegen
    (Ankersperre, P23, Neukappung gegen den Vorgänger-Snapshot, F1-Rückrechnung,
    Klassifikation, Protokoll inkl. Sammelzeile „… gelöscht", Jahreswarnung,
    Spiegel, commit). Verkürzt das Löschen, braucht es das Schutzpaket im
    optionalen Body (P8); der verlustfreie Weg ist die Rücksetzung per
    ``reset_body`` aus der Lösch-Vorschau (P13). Ein Verstoß rollt ALLES zurück.

    Antwort: 200 mit ``{adjusted_absences, adjusted_time_entries,
    skipped_time_entries, warning}``, sobald etwas angepasst oder gewarnt wurde,
    sonst 204 (Muster ``delete_closure``)."""
    reason = _parse_delete_body(body)
    change = _change_in_tenant(db, user_id, change_id, current_user)
    user = _get_user_in_tenant(db, user_id, current_user)
    # E52/P5: Ankersperre vor Snapshot, clamp und jeder Zeilensperre — über
    # ``_lock_and_reload`` wie das Anlegen (#491 API-2: die User-Zeile danach
    # neu lesen, sonst rechnete der Pfad auf dem Stand vor einer gerade
    # committeten Gegenseite).
    _lock_and_reload(db, current_user, user)
    # Nach der Sperre erneut: ein paralleles Löschen derselben Zeile hat sie
    # inzwischen vielleicht entfernt → 404. Ohne das Neulesen meldete auch das
    # zweite Löschen Erfolg (SQLAlchemy warnt bei 0 gelöschten Zeilen nur) und
    # schriebe eine zweite Sammelzeile „… gelöscht" — auf PostgreSQL nachgewiesen.
    change = _change_in_tenant(db, user_id, change_id, current_user)
    lock_detail = _earliest_row_lock_detail(db, user, current_user, change)
    if lock_detail:
        raise HTTPException(status_code=400, detail=lock_detail)
    effective_from = change.effective_from

    impact = wh_change_service.run_change(
        db, user, admin_id=current_user.id, effective_from=effective_from,
        apply=lambda: _delete_change_row(db, user, current_user, change))
    earliest = impact.earliest_lossless_date
    error = wh_change_service.protection_error(
        impact, reason, deleting=True, reset_offered=earliest is not None and earliest > effective_from)
    if error:
        db.rollback()  # verwirft Schritte 2–6 (9.3 Schritt 7)
        raise HTTPException(status_code=400, detail=error)

    reason_type = reason.retroactive_reason_type if (reason is not None and impact.is_shortening) else None
    _log_reclamp(db, user=user, admin=current_user, impact=impact, effective_from=effective_from, deleted=True,
                 reason_type=reason_type, reason_text=reason.retroactive_reason_text if reason_type else None,
                 reset_of=None)
    _log_wh_change_retarget(
        db, user=user, admin=current_user, tenant_id=current_user.tenant_id,
        effective_from=impact.window.start, period_end=impact.window.end, adjusted=impact.absences,
        prefix="Löschung der Arbeitszeit-Änderung", suffix="auf den davor gültigen Wert zurückgerechnet",
    )
    # I3 (Abschluss-Review) / Fix #5: dasselbe Fenster wie beim Anlegen — ein
    # abgeschlossenes Jahr nur melden, nie automatisch neu rechnen.
    warning = calculation_service.stale_year_closing_warning(
        db, current_user.tenant_id, range(impact.window.start.year, impact.window.end.year + 1))
    # Schritt 10 (E9) wie beim Anlegen: der Spiegel erst NACH Klassifikation und
    # Protokoll (Review Task 10) — #431: derselbe vollständige Snapshot-Resync.
    # Ohne verbleibende Zeile bleibt die User-Zeile die alleinige Quelle.
    _sync_user_to_current_change(db, user, current_user.tenant_id)
    db.commit()
    if impact.absences or impact.reclamp.changed or warning:
        return JSONResponse(status_code=200, content={
            "adjusted_absences": len(impact.absences),
            "adjusted_time_entries": len(impact.reclamp.changed),
            "skipped_time_entries": len(impact.reclamp.skipped),
            "warning": warning,
        })
    return None
