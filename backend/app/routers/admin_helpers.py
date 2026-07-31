"""Shared helpers used by the router layer (admin sub-routers + Buchungspfade)."""

from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import User, ChangeRequest, TimeEntryAuditLog
from app.models.vacation_request import VacationRequest
from app.schemas.change_request import ChangeRequestResponse
from app.schemas.time_entry_audit_log import AuditLogResponse
from app.schemas.vacation_request import VacationRequestResponse
from app.services.calculation_service import count_workdays


# ── Anker-Sperre auf Benutzerzeilen ──────────────────────────────────────────
#
# DIE EINE REGEL (Audit 2026-07-31, Restklasse Kreuz-Sperren):
#
#   Jede Sperre auf einer ``users``-Zeile, die als ANKER dient (also nur
#   serialisieren, nicht die Zeile selbst ändern soll), läuft über
#   ``lock_user_rows`` / ``lock_user_row`` und ist damit ``FOR NO KEY UPDATE``.
#   Ein nacktes ``db.query(User)…with_for_update()`` gehört NICHT mehr in einen
#   Router — ``tests/test_concurrency.py::test_no_router_locks_user_rows_directly``
#   hält das fest.
#
# WARUM NICHT ``FOR UPDATE``:
#   Jede Zeile mit einem Fremdschlüssel auf ``users`` (``absences.user_id``,
#   ``time_entries.user_id``, ``company_closures.created_by`` und vor allem
#   ``time_entry_audit_logs.user_id``/``changed_by``) nimmt beim INSERT über den
#   RI-Trigger ein ``FOR KEY SHARE`` auf der referenzierten Benutzerzeile —
#   implizit, bis zum Commit gehalten, und in einer Reihenfolge, die wir NICHT
#   bestimmen können (mehrere Fremdschlüssel je Zeile, Trigger-Reihenfolge,
#   Flush-Reihenfolge der Session). Gemessene Konfliktmatrix (Postgres 18,
#   eigene Messung gegen die Projekt-DB):
#
#     gehalten \ angefordert   KEY SHARE  SHARE     NO KEY UPDATE  UPDATE
#     FOR KEY SHARE            frei       frei      frei           KONFLIKT
#     FOR SHARE                frei       frei      KONFLIKT       KONFLIKT
#     FOR NO KEY UPDATE        frei       KONFLIKT  KONFLIKT       KONFLIKT
#     FOR UPDATE               KONFLIKT   KONFLIKT  KONFLIKT       KONFLIKT
#
#   Mit ``FOR UPDATE`` (Zeile 4, Spalte 1) wird also JEDER dieser impliziten
#   FK-Sperrversuche zu einer möglichen Wartekante gegen einen Anker — und
#   damit zur Ecke eines Sperr-Zyklus. Zwei real reproduzierte Fälle:
#
#     (1) ``create_absence`` hält die MA-Zeile und schreibt eine Audit-Zeile mit
#         ``changed_by = handelnder Admin`` → ``KEY SHARE`` auf einer ZWEITEN
#         Benutzerzeile. Die Betriebsferien halten die Admin-Zeile (sortiert
#         zuerst) und wollen die MA-Zeile → Zyklus.
#     (2) ``admin_time_entries`` hält die ZEITEINTRAGS-Zeile und will
#         ``KEY SHARE`` auf der Benutzerzeile; die Betriebsferien halten die
#         Benutzerzeile und wollen den Zeiteintrag → Zyklus über nur EINE
#         Benutzerzeile.
#
#   ``FOR NO KEY UPDATE`` (Zeile 3) entfernt genau diese Kante (Spalte 1 =
#   frei) und behält alles, wofür der Anker da ist: er schließt sich weiterhin
#   gegen sich selbst aus (Spalte 3) sowie gegen ``FOR SHARE``/``FOR UPDATE``
#   und gegen jedes echte ``UPDATE users`` — alle Buchungspfade serialisieren
#   also unverändert pro Mitarbeiterin. Aufgegeben wird nur die INZIDENTELLE
#   Nebenwirkung, auch fremde, nicht geankerte Kind-INSERTs zu blockieren; die
#   war nie eine Zusicherung, sondern die Ursache der Zyklen.
#
# WARUM NICHT „beide Zeilen sperren" (Ziel + Handelnder, sortiert):
#   Das schließt den Zyklus nur, wenn BEIDE Beteiligten ankern. Zeilen mit
#   Benutzer-Fremdschlüsseln entstehen aber an ~30 Stellen, darunter reine
#   Lese-/Protokollpfade ohne jeden Anker (``reports.py``-Exportvermerke,
#   ``journal.py``, ``me.py``, ``auth.py``, ``superadmin.py``,
#   ``admin_users.py``, XLS-Import) und der Fehler-Middleware-Pfad, der gar
#   keine ``FOR UPDATE``-Sperre auf Benutzerzeilen nehmen darf. Mehrere davon
#   schreiben ZWEI Benutzer-Fremdschlüssel in EINEM INSERT, dessen interne
#   Sperrreihenfolge nicht steuerbar ist. Zusätzlich würde das Mitsperren der
#   Admin-Zeile jede Buchung desselben Admins für VERSCHIEDENE Mitarbeiter
#   gegeneinander serialisieren (die Admin-Zeile wird zum Flaschenhals).
#
# Die projektweite Reihenfolge „Benutzerzeile zuerst, dann die abhängige Zeile"
# bleibt unverändert gültig und ist weiterhin einzuhalten — sie regelt die
# EXPLIZITEN Sperren. ``FOR NO KEY UPDATE`` macht zusätzlich die IMPLIZITEN,
# nicht sortierbaren FK-Sperren harmlos.


def lock_user_rows(db: Session, tenant_id, user_ids) -> list:
    """Anker-Sperre auf mehreren Benutzerzeilen — sortiert, in EINER Anweisung.

    Sortiert nach ``User.id``, damit zwei gleichzeitige Vorgänge die Sperren in
    identischer Reihenfolge erwerben und sich nicht über Kreuz verklemmen.
    ``FOR NO KEY UPDATE`` statt ``FOR UPDATE`` — Begründung siehe oben.

    F-026: der Lock-Read wird zusätzlich am Mandanten gefiltert.
    Gibt die gesperrten Zeilen zurück (leer, wenn keine passt).
    """
    ids = sorted({uid for uid in user_ids if uid is not None}, key=str)
    if not ids:
        return []
    return (
        db.query(User)
        .filter(User.id.in_(ids), User.tenant_id == tenant_id)
        .order_by(User.id)
        .with_for_update(key_share=True)
        .all()
    )


def lock_user_row(db: Session, tenant_id, user_id):
    """Anker-Sperre auf EINER Benutzerzeile (siehe ``lock_user_rows``).

    Gibt die gesperrte Zeile zurück oder ``None`` (unbekannt / fremder Mandant).
    """
    rows = lock_user_rows(db, tenant_id, [user_id])
    return rows[0] if rows else None


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
    # F-026: scope referenced users (incl. reviewed_by) to the tenants of the
    # requests they belong to — sonst könnte ein reviewed_by/user_id aus einem
    # fremden Tenant durchsickern. Mirrors _enrich_vr_responses.
    tenant_ids = {cr.tenant_id for cr in crs}
    users = (
        db.query(User)
        .filter(User.id.in_(user_ids), User.tenant_id.in_(tenant_ids))
        .all()
        if user_ids
        else []
    )
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


def _enrich_vr_response(vr: VacationRequest, db: Session) -> VacationRequestResponse:
    """Add user names + workdays to a vacation request response (single item)."""
    return _enrich_vr_responses([vr], db)[0]


def _enrich_vr_responses(vrs: list, db: Session) -> list[VacationRequestResponse]:
    """#219: single shared enricher for vacation requests (was duplicated in
    admin_vacations._enrich_vr_responses + vacation_requests._enrich, the latter
    doing 3 DB queries PER item). Batch: one user query for the whole list."""
    if not vrs:
        return []
    user_ids = set()
    for vr in vrs:
        user_ids.add(vr.user_id)
        if vr.reviewed_by:
            user_ids.add(vr.reviewed_by)
        if vr.last_modified_by:
            user_ids.add(vr.last_modified_by)
    user_ids.discard(None)
    # F-026: scope referenced users to the tenants of the requests they belong to.
    tenant_ids = {vr.tenant_id for vr in vrs}
    users = (
        db.query(User)
        .filter(User.id.in_(user_ids), User.tenant_id.in_(tenant_ids))
        .all()
        if user_ids
        else []
    )
    user_map = {u.id: u for u in users}

    results = []
    for vr in vrs:
        resp = VacationRequestResponse.model_validate(vr)
        user = user_map.get(vr.user_id)
        if user:
            resp.user_first_name = user.first_name
            resp.user_last_name = user.last_name
        if vr.reviewed_by:
            reviewer = user_map.get(vr.reviewed_by)
            if reviewer:
                resp.reviewer_first_name = reviewer.first_name
                resp.reviewer_last_name = reviewer.last_name
        if vr.last_modified_by:
            modifier = user_map.get(vr.last_modified_by)
            if modifier:
                resp.last_modifier_first_name = modifier.first_name
                resp.last_modifier_last_name = modifier.last_name
        end = vr.end_date if vr.end_date else vr.date
        resp.days = count_workdays(db, vr.date, end, tenant_id=vr.tenant_id)
        results.append(resp)
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
    # F-026: scope referenced users (incl. changed_by) to the tenants of the
    # audit rows they belong to — sonst könnte ein changed_by/user_id aus einem
    # fremden Tenant durchsickern. Mirrors _enrich_vr_responses.
    tenant_ids = {log.tenant_id for log in logs}
    users = (
        db.query(User)
        .filter(User.id.in_(user_ids), User.tenant_id.in_(tenant_ids))
        .all()
        if user_ids
        else []
    )
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
