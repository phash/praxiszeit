from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.services.timezone_service import now_local, today_local
from app.database import get_db
from app.models import (
    User, TimeEntry, ChangeRequest, ChangeRequestType, ChangeRequestStatus, UserRole, Absence, AbsenceType,
    AbsenceReason, AbsenceReasonBehavior, BEHAVIOR_TO_ABSENCE_TYPE,
)
from app.middleware.auth import get_current_user
from app.schemas.change_request import ChangeRequestCreate, ChangeRequestResponse
from app.services.break_validation_service import validate_daily_break, break_waiver_rejection
from app.routers.time_entries import (
    _calculate_daily_net_hours, _calculate_weekly_net_hours,
    MAX_DAILY_HOURS_HARD, MAX_NIGHT_WORKER_DAILY_WARN, MAX_WEEKLY_HOURS_WARN,
)
from app.services.arbzg_utils import is_night_work
from app.services import credit_override_service, work_window_service
# #219: single shared CR-enricher (was duplicated per-item here vs the batch in
# admin_helpers). _enrich_cr_response wraps the batch _enrich_cr_responses([cr]).
from app.routers.admin_helpers import (
    _enrich_cr_response as _enrich_response, _enrich_cr_responses,
)

router = APIRouter(prefix="/api/change-requests", tags=["change-requests"])

# Spec 2026-10-08, 11.4 / P21 (wörtlich).
CREDIT_REQUEST_REJECTED_DETAIL = "Für diesen Eintrag kann keine Anrechnung beantragt werden."
# Gesamtreview PR2 (Fund 1): heute beantragbar, aber nur für bereits vergangene Zeit.
CREDIT_REQUEST_FUTURE_END_DETAIL = (
    "Das Ende liegt in der Zukunft – die Anrechnung kann erst nach Arbeitsende beantragt werden."
)


@router.post("/", response_model=ChangeRequestResponse, status_code=status.HTTP_201_CREATED)
def create_change_request(
    data: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employee creates a change request for a past day (Anrechnung beantragen:
    auch für den heutigen, geschlossenen Eintrag — Gesamtreview PR2, Fund 1)."""

    # Validate request_type
    if data.request_type not in ("create", "update", "delete"):
        raise HTTPException(status_code=400, detail="Ungültiger Antragstyp")

    # Validate entry_kind
    if data.entry_kind not in ("time_entry", "absence"):
        raise HTTPException(status_code=400, detail="Ungültiger Antragstyp (entry_kind)")

    # Spec 2026-10-08 P21: „Anrechnung beantragen" gibt es nur für Zeiteinträge.
    if data.request_credit_override and data.entry_kind != "time_entry":
        raise HTTPException(status_code=400, detail=CREDIT_REQUEST_REJECTED_DETAIL)

    # --- Absence CR branch ---
    if data.entry_kind == "absence":
        # For UPDATE/DELETE: absence_id required, fetch and validate ownership
        absence = None
        if data.request_type in ("update", "delete"):
            if not data.absence_id:
                raise HTTPException(status_code=400, detail="absence_id erforderlich für Absence-Änderung/Löschung")
            absence = db.query(Absence).filter(Absence.id == data.absence_id, Absence.tenant_id == current_user.tenant_id).first()
            if not absence:
                raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")
            if absence.user_id != current_user.id:
                # #120: 404 statt 403 — kein Existenz-Leak fremder Abwesenheiten.
                raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")

        # For CREATE/UPDATE: validate required fields
        if data.request_type in ("create", "update"):
            if not data.proposed_absence_type:
                raise HTTPException(status_code=400, detail="Abwesenheitstyp erforderlich")
            if not data.proposed_date:
                raise HTTPException(status_code=400, detail="Datum erforderlich")
            if data.proposed_date >= today_local():
                raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
            # Validate absence type is valid
            try:
                AbsenceType(data.proposed_absence_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Ungültiger Abwesenheitstyp: {data.proposed_absence_type}")
            # Need either hours or start/end time — runs for EVERY absence CR, not
            # only custom-reason ones (round-2 fix: this had regressed into the
            # reason_id block below).
            if data.proposed_absence_hours is None and not (data.proposed_start_time and data.proposed_end_time):
                raise HTTPException(status_code=400, detail="Stunden oder Start-/Endzeit erforderlich")
            if data.proposed_start_time and data.proposed_end_time:
                if data.proposed_start_time >= data.proposed_end_time:
                    raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

        # #312: a custom absence reason overrides the proposed type via its
        # behaviour and is carried to approval (resolved tenant-scoped + active).
        resolved_reason_id = None
        if data.entry_kind == "absence" and data.request_type in ("create", "update") and data.reason_id:
            reason = db.query(AbsenceReason).filter(
                AbsenceReason.id == data.reason_id,
                AbsenceReason.tenant_id == current_user.tenant_id,  # F-026
                AbsenceReason.is_active.is_(True),
            ).first()
            if not reason:
                raise HTTPException(status_code=404, detail="Abwesenheitsgrund nicht gefunden oder inaktiv")
            data.proposed_absence_type = BEHAVIOR_TO_ABSENCE_TYPE[AbsenceReasonBehavior(reason.base_behavior)].value
            resolved_reason_id = data.reason_id

        # For DELETE: validate absence exists (already fetched above)
        if data.request_type == "delete" and absence:
            if absence.date >= today_local():
                raise HTTPException(status_code=400, detail="Heutige Einträge können direkt gelöscht werden")

        # Check for duplicate pending absence requests
        if data.request_type == "create" and data.proposed_date:
            existing_pending = db.query(ChangeRequest).filter(
                ChangeRequest.tenant_id == current_user.tenant_id,
                ChangeRequest.user_id == current_user.id,
                ChangeRequest.status == ChangeRequestStatus.PENDING,
                ChangeRequest.entry_kind == "absence",
                ChangeRequest.request_type == ChangeRequestType.CREATE,
                ChangeRequest.proposed_date == data.proposed_date,
                ChangeRequest.proposed_absence_type == data.proposed_absence_type,
            ).first()
            if existing_pending:
                raise HTTPException(status_code=400, detail="Es existiert bereits ein offener Antrag für dieses Datum und diesen Typ")
        elif data.request_type in ("update", "delete") and data.absence_id:
            existing_pending = db.query(ChangeRequest).filter(
                ChangeRequest.tenant_id == current_user.tenant_id,
                ChangeRequest.user_id == current_user.id,
                ChangeRequest.status == ChangeRequestStatus.PENDING,
                ChangeRequest.absence_id == data.absence_id,
            ).first()
            if existing_pending:
                raise HTTPException(status_code=400, detail="Es existiert bereits ein offener Antrag für diese Abwesenheit")

        # Create the CR
        cr = ChangeRequest(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            request_type=data.request_type,
            entry_kind="absence",
            absence_id=data.absence_id if data.request_type in ("update", "delete") else None,
            proposed_date=data.proposed_date,
            proposed_start_time=data.proposed_start_time,
            proposed_end_time=data.proposed_end_time,
            proposed_absence_type=data.proposed_absence_type,
            proposed_absence_hours=data.proposed_absence_hours,
            proposed_reason_id=resolved_reason_id,  # #312
            reason=data.reason,
        )

        # Snapshot original values for update/delete
        if data.request_type in ("update", "delete") and absence:
            cr.original_date = absence.date
            cr.original_absence_type = absence.type.value
            cr.original_absence_hours = float(absence.hours)
            cr.original_start_time = absence.start_time
            cr.original_end_time = absence.end_time

        db.add(cr)
        db.commit()
        db.refresh(cr)
        return _enrich_response(cr, db)

    # --- TimeEntry CR branch (existing logic) ---

    # For UPDATE and DELETE, time_entry_id is required
    entry = None
    if data.request_type in ("update", "delete"):
        if not data.time_entry_id:
            raise HTTPException(status_code=400, detail="time_entry_id erforderlich für Änderung/Löschung")
        entry = db.query(TimeEntry).filter(TimeEntry.id == data.time_entry_id, TimeEntry.tenant_id == current_user.tenant_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
        if entry.user_id != current_user.id:
            # #120: 404 statt 403 — kein Existenz-Leak fremder Zeiteintraege.
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")

    # For CREATE, proposed values are required
    if data.request_type == "create":
        if not all([data.proposed_date, data.proposed_start_time, data.proposed_end_time]):
            raise HTTPException(status_code=400, detail="Datum, Von und Bis sind für neue Einträge erforderlich")
        # Must be for a past day
        if data.proposed_date >= today_local():
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
        # Arbeitszeitraum-Prüfung (I1)
        if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt vor dem ersten Arbeitstag")
        if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt nach dem letzten Arbeitstag")

    # Gesamtreview PR2 (Fund 1): „Anrechnung beantragen" auch für den HEUTIGEN,
    # geschlossenen Eintrag — der Lückentext an clock_out/create/update (für
    # Mitarbeitende immer heute) verweist genau darauf, und Spec 14 kennt keine
    # Tagesgrenze. Nur bei gleichbleibendem Datum (heute → heute, wie #502);
    # gewöhnliche Änderungen des heutigen Eintrags laufen weiter direkt.
    _credit_today = bool(
        data.request_credit_override
        and entry is not None
        and entry.date == today_local()
        and data.proposed_date == entry.date
    )

    # For UPDATE, proposed values required and must be for past day
    if data.request_type == "update":
        if not all([data.proposed_date, data.proposed_start_time, data.proposed_end_time]):
            raise HTTPException(status_code=400, detail="Datum, Von und Bis sind erforderlich")
        if data.proposed_date >= today_local() and not _credit_today:
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
        # Arbeitszeitraum-Prüfung (I1)
        if data.proposed_date:
            if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt vor dem ersten Arbeitstag")
            if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datum liegt nach dem letzten Arbeitstag")

    # Spec 2026-10-08 P21: nur als Änderung (UPDATE) an einem eigenen (die
    # Eigentümerprüfung oben antwortet für fremde Einträge wie für unbekannte
    # mit 404, #120), geschlossenen, noch nicht anerkannten Eintrag mit nicht
    # angerechneter Zeit (P19: Lücke und Hülle). Ein automatisch geschlossener
    # Eintrag braucht das TATSÄCHLICHE Ende im selben Antrag (P18): 23:59 ist
    # kein Stempel, und das gekappte Ende liefe bei der Genehmigung über
    # unclamp_input wieder auf 23:59 hinaus.
    if data.request_credit_override:
        if (
            data.request_type != "update"
            or entry is None
            or entry.end_time is None
            or entry.credit_override
            or work_window_service.not_credited_minutes(entry) <= 0
            # Gesamtreview PR2 (Fund 3): Nicht-Anrechnung und Begründung gehören
            # zum Tag des Eintrags. Ein anderes Datum kappte die Genehmigung gegen
            # die Blöcke des Zieltags und erkennte die Zeiten DORT an.
            or data.proposed_date != entry.date
        ):
            raise HTTPException(status_code=400, detail=CREDIT_REQUEST_REJECTED_DETAIL)
        if credit_override_service.lacks_actual_end(entry, data.proposed_end_time):
            raise HTTPException(status_code=400, detail=credit_override_service.AUTO_CLOSED_DETAIL)
        # Heute lässt das Anlegen ein späteres Ende zu (time_entries.create_time_entry);
        # anerkannt würde dauerhaft (P11) noch nicht gearbeitete Zeit.
        if _credit_today and data.proposed_end_time > now_local().time():
            raise HTTPException(status_code=400, detail=CREDIT_REQUEST_FUTURE_END_DETAIL)

    # Time range validation for CREATE and UPDATE
    if data.request_type in ("create", "update") and data.proposed_start_time and data.proposed_end_time:
        if data.proposed_start_time >= data.proposed_end_time:
            raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # For DELETE, entry must be from past
    if data.request_type == "delete" and entry:
        if entry.date >= today_local():
            raise HTTPException(status_code=400, detail="Heutige Einträge können direkt gelöscht werden")

    # #499-Review (F4): die Begründung wird nur dann am Antrag gespeichert, wenn
    # sie eine §4-Ausnahme tatsächlich trägt. Eine überflüssige Begründung ließ
    # die Genehmigung die §4-Neuprüfung überspringen (admin_change_requests:
    # ``if waiver_reason is None``) — ein inzwischen entstandener Tagesverstoß
    # wäre dann ungeprüft als 'break_waiver' gebucht worden.
    waiver_needed = False

    # E40 (Spec 2026-10-08): der Antrag prüft §3/§4/§6/48 h auf der
    # ANGERECHNETEN Zeit — wie die Genehmigung. Gespeichert werden weiter die
    # ROHEN Vorschläge (die Genehmigung kappt genau einmal, admin_change_requests).
    _cr_clamp = None
    _cr_segs: list = []
    if (data.request_type in ("create", "update")
            and data.proposed_date and data.proposed_start_time and data.proposed_end_time):
        _in_start, _in_end = data.proposed_start_time, data.proposed_end_time
        _override = bool(entry is not None and entry.credit_override)
        if entry is not None:
            # Das Antragsformular belegt die Zeiten mit der angerechneten Zeit vor
            # (Release-Review 1.19.3 F1) — derselbe Rohwert-Rückgriff wie bei der
            # Genehmigung, sonst zählte eine reine Pausen-Korrektur gekappt.
            _in_start = work_window_service.unclamp_input(_in_start, entry.start_time, entry.raw_start_time)
            # PR1-Review F1 (P18): ein automatisch geschlossener Eintrag, der nur auf einen
            # anderen Tag wandert, rechnet mit dem wirksamen Ende statt 23:59.
            _in_end = work_window_service.end_input_for(
                _in_end, entry.end_time, entry.raw_end_time,
                auto_closed=entry.auto_closed, prev_date=entry.date,
                target_date=data.proposed_date,
            )
            # E80: UPDATE-Prüfung mit dem gespeicherten Puffer des Eintrags,
            # CREATE-Prüfung mit dem aktuellen Mandanten-Puffer — dieselbe
            # Herkunft wie der Schreibzweig der Genehmigung.
            _cr_grace = work_window_service.grace_for_entry(db, entry)
        else:
            _cr_grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
        # Die Prüfung oben sah den rohen Vorschlag; ``end_input_for`` kann das Ende
        # davor legen (verschobener Auto-Close-Eintrag, späterer Beginn).
        _order_error = work_window_service.input_order_error(
            _in_start, _in_end, auto_closed=bool(entry is not None and entry.auto_closed),
        )
        if _order_error:
            raise HTTPException(status_code=400, detail=_order_error)
        _cr_clamp = work_window_service.clamp(
            db, current_user, data.proposed_date, _in_start, _in_end, _cr_grace,
            credit_override=_override,
        )
        # Spec 8.2: Lückensegmente aus DENSELBEN Eingaben wie ``clamp`` für §4.
        _cr_segs = work_window_service.gap_segments(
            db, current_user, data.proposed_date, _in_start, _in_end, _cr_grace,
            credit_override=_override,
        )
    _chk_start = _cr_clamp.eff_start if _cr_clamp else data.proposed_start_time
    _chk_end = _cr_clamp.eff_end if _cr_clamp else data.proposed_end_time
    _chk_unc = _cr_clamp.uncredited_minutes if _cr_clamp else 0

    # Break validation for CREATE and UPDATE (§18-Ausnahme: exempt_from_arbzg überspringt §3/§4)
    if not current_user.exempt_from_arbzg and data.request_type in ("create", "update") and data.proposed_date:
        break_error = validate_daily_break(
            db=db,
            user=current_user,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_segments=_cr_segs,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
        # #200: §4-Pausen-Ausnahme — bei dokumentierter Begründung den §4-Block
        # NICHT hart werfen, sondern den Antrag mit break_waiver_reason anlegen
        # (admin_change_requests honoriert ihn beim Genehmigen). Der §3-10h-Cap
        # unten bleibt unabhängig davon hart. #499: ist die Ausnahme im
        # Mandanten abgeschaltet, bleibt der §4-Block auch mit Begründung.
        if break_error:
            rejection = break_waiver_rejection(
                db, current_user.tenant_id, break_error, data.break_waiver_reason,
            )
            if rejection:
                raise HTTPException(status_code=400, detail=rejection)
            waiver_needed = True

        # §3 ArbZG: daily hours hard limit
        daily_hours = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
        if daily_hours > MAX_DAILY_HOURS_HARD:
            raise HTTPException(
                status_code=422,
                detail=f"Tagesarbeitszeit würde {daily_hours:.1f}h betragen und überschreitet die gesetzliche Höchstgrenze von {MAX_DAILY_HOURS_HARD:.0f}h (§3 ArbZG).",
            )

    # Check for duplicate pending requests
    existing_pending = db.query(ChangeRequest).filter(
        ChangeRequest.tenant_id == current_user.tenant_id,
        ChangeRequest.user_id == current_user.id,
        ChangeRequest.status == ChangeRequestStatus.PENDING,
    )
    if data.time_entry_id:
        existing_pending = existing_pending.filter(
            ChangeRequest.time_entry_id == data.time_entry_id
        )
    if data.request_type == "create" and data.proposed_date:
        existing_pending = existing_pending.filter(
            ChangeRequest.request_type == ChangeRequestType.CREATE,
            ChangeRequest.proposed_date == data.proposed_date,
        )
    existing = existing_pending.first()
    if existing:
        raise HTTPException(status_code=400, detail="Es existiert bereits ein offener Antrag für diesen Eintrag")

    # Create the change request
    cr = ChangeRequest(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        request_type=data.request_type,
        time_entry_id=data.time_entry_id,
        proposed_date=data.proposed_date,
        proposed_start_time=data.proposed_start_time,
        proposed_end_time=data.proposed_end_time,
        proposed_break_minutes=data.proposed_break_minutes,
        proposed_note=data.proposed_note,
        reason=data.reason,
        break_waiver_reason=(
            data.break_waiver_reason.strip()
            if waiver_needed and data.break_waiver_reason and data.break_waiver_reason.strip()
            else None
        ),
        # #485 §10 ArbZG: Ausnahmegrund fuer Sonn-/Feiertagsarbeit.
        proposed_sunday_exception_reason=(
            (data.proposed_sunday_exception_reason or "").strip() or None
        ),
        request_credit_override=bool(data.request_credit_override),  # P21
    )

    # Snapshot original values
    if entry:
        cr.original_date = entry.date
        cr.original_start_time = entry.start_time
        cr.original_end_time = entry.end_time
        cr.original_break_minutes = entry.break_minutes
        cr.original_note = entry.note
        cr.original_uncredited_minutes = entry.uncredited_minutes  # P28

    db.add(cr)
    db.commit()
    db.refresh(cr)

    response = _enrich_response(cr, db)

    # §6 Abs. 2 ArbZG: Warnung für Nachtarbeitnehmer (§18-Ausnahme beachten)
    if (
        not current_user.exempt_from_arbzg
        and data.request_type in ("create", "update")
        and data.proposed_start_time
        and data.proposed_end_time
    ):
        daily_hours_check = _calculate_daily_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
        if (
            current_user.is_night_worker
            and is_night_work(_chk_start, _chk_end)
            and daily_hours_check > MAX_NIGHT_WORKER_DAILY_WARN
        ):
            response.warnings.append(
                f"§6 ArbZG: Nachtarbeitnehmer – Tageslimit 8h überschritten ({daily_hours_check:.1f}h). "
                "Verlängerung auf 10h nur mit 1-Monats-Ausgleich zulässig."
            )

        # Audit R3 (§3/§14 ArbZG): Wochen-48h-Warnung — fehlte bisher im
        # Mitarbeiter-CR-Pfad (in time_entries.create + admin_change_requests
        # bereits vorhanden), damit der Antrag schon bei Einreichung den
        # Wochenüberschreitungs-Hinweis trägt.
        weekly_hours_check = _calculate_weekly_net_hours(
            db=db,
            user_id=current_user.id,
            entry_date=data.proposed_date,
            start_time=_chk_start,
            end_time=_chk_end,
            break_minutes=data.proposed_break_minutes or 0,
            uncredited_minutes=_chk_unc,
            exclude_entry_id=entry.id if entry else None,
            tenant_id=current_user.tenant_id,
        )
        if weekly_hours_check > MAX_WEEKLY_HOURS_WARN:
            response.warnings.append("WEEKLY_HOURS_WARNING")

    return response


@router.get("/", response_model=List[ChangeRequestResponse])
def list_change_requests(
    request_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List own change requests (employee view)."""
    query = db.query(ChangeRequest).filter(
        ChangeRequest.user_id == current_user.id,
        ChangeRequest.tenant_id == current_user.tenant_id,  # F-026
    )

    if request_status:
        try:
            status_enum = ChangeRequestStatus(request_status)
            query = query.filter(ChangeRequest.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {request_status}"
            )

    requests = query.order_by(ChangeRequest.created_at.desc()).offset(skip).limit(limit).all()
    # Batch wie admin_change_requests.list_all_change_requests: EIN User- und EIN
    # Eintrags-Query für die ganze Liste (bis 500 Anträge), nicht je Antrag.
    return _enrich_cr_responses(requests, db)


@router.get("/{request_id}", response_model=ChangeRequestResponse)
def get_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific change request."""
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == request_id, ChangeRequest.tenant_id == current_user.tenant_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        # #120: 404 statt 403 — kein Existenz-Leak fremder Antraege.
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    return _enrich_response(cr, db)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_change_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Withdraw a pending change request."""
    # Audit 2026-07-31 (A3): die Antragszeile MUSS GESPERRT gelesen werden, bevor
    # der Status geprüft wird — wortgleich zu
    # ``vacation_requests.withdraw_vacation_request``. Ohne Sperre prüft das
    # Zurückziehen ein veraltetes Abbild: genehmigt der Admin zeitgleich
    # (``admin_change_requests.review_change_request`` hält die Zeile per
    # ``with_for_update``), setzt dieses ``DELETE … WHERE id = :id`` ab und
    # wartet nur auf die Zeilensperre; nach dem Commit des Genehmigers
    # qualifiziert Postgres die Bedingung unter READ COMMITTED neu
    # (EvalPlanQual) — sie nennt ausschließlich die ``id``, der inzwischen
    # GENEHMIGTE Antrag wird also gelöscht, während seine Seiteneffekte
    # (gebuchte Zeit, Abwesenheit) bestehen bleiben.
    # Zusatzschaden: ``time_entry_audit_logs.change_request_id`` hängt per
    # ``ON DELETE SET NULL`` an dieser Zeile und ist Teil des #121-``row_hash``;
    # das FK-Nullen schreibt am ``before_insert``-Hook vorbei → der gespeicherte
    # Hash wird stale und ``verify-integrity`` meldet eine völlig legitime Zeile
    # als manipuliert.
    # Mit der Sperre liefert Postgres nach dem Warten die AKTUELLE Zeilenversion
    # → die Statusprüfung unten sieht APPROVED und lehnt mit 400 ab.
    cr = (
        db.query(ChangeRequest)
        .filter(
            ChangeRequest.id == request_id,
            ChangeRequest.tenant_id == current_user.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not cr:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.user_id != current_user.id:
        # #120: 404 statt 403 — kein Existenz-Leak fremder Antraege.
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")
    if cr.status != ChangeRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Nur offene Anträge können zurückgezogen werden")

    db.delete(cr)
    db.commit()
    return None
