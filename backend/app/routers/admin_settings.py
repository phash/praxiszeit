"""Admin sub-router: System Settings."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TimeEntry, User
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.middleware.auth import require_admin
from app.routers.admin_helpers import SettingUpdate
from app.services import calculation_service, special_days_service, type_colors_service, work_window_service
from typing import Dict
from app.services.settings_service import (
    SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD,
    SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# #146: the four special-day keys (24./31.12. mode + counts_as_vacation) are
# managed through this router too. They are added to the whitelist so the
# generic PUT accepts them; mode keys are validated against the allowed modes.
# #144: break_exception_requires_approval steuert die Pflicht-Pause-Ausnahme.
_ALLOWED_SETTINGS = {
    "vacation_approval_required",
    "holiday_state",
    "break_exception_requires_approval",  # #144 §4 ArbZG: Pflicht-Pause-Ausnahme
    "break_exception_allowed",  # #499 §4-Ausnahme „Pause war nicht möglich" an/aus (Default an)
    "work_window_grace_minutes",  # #201 Arbeitszeit-Fenster: Pufferzeit in Minuten
    "onboarding_enabled",  # Erst-Login-Willkommens-Tour an/aus (Default an)
    "shift_planning_enabled",  # #305 Schichtplanung aktivieren (Default aus)
    "shift_planning_weekdays",  # #371 konfigurierbare Wochentage (CSV 0=Mo…6=So, Default Mo–Fr)
    "closure_overtime_after_vacation",  # #314 Betriebsferien > Urlaub → Überstundenabbau (Default aus)
    "child_sick_days_default",  # #376 Kind-krank-Default-Anspruch/Jahr (int, Default 15)
    SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD,
    SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD,
} | special_days_service.SETTING_KEYS

# Settings whose value must be a boolean ("true"/"false").
_BOOL_SETTINGS = {"vacation_approval_required", "break_exception_requires_approval", "break_exception_allowed", "onboarding_enabled", "shift_planning_enabled", "closure_overtime_after_vacation", SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, }


@router.get("/settings")
def list_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all system settings."""
    rows = db.query(SystemSetting).filter(SystemSetting.tenant_id == current_user.tenant_id).all()
    return [{"key": r.key, "value": r.value, "description": r.description, "updated_at": r.updated_at} for r in rows]


def _tenant_holiday_dates(db: Session, tenant_id) -> set:
    """Alle Feiertagsdaten des Mandanten (alle Quellen, F-026)."""
    return {
        d for (d,) in db.query(PublicHoliday.date).filter(
            PublicHoliday.tenant_id == tenant_id
        ).all()
    }


def _tenant_entry_years(db: Session, tenant_id) -> range:
    """Jahre vom ersten bis zum letzten Zeiteintrag des Mandanten (F-026)."""
    lo, hi = db.query(func.min(TimeEntry.date), func.max(TimeEntry.date)).filter(
        TimeEntry.tenant_id == tenant_id
    ).one()
    if lo is None:
        return range(0)
    return range(lo.year, hi.year + 1)


@router.get("/settings/special-days")
def get_special_days(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return the resolved special-day configuration (24./31.12.) for the tenant.

    Always returns all four keys with their effective value (defaults applied
    when no row exists), so the UI has the complete state without having to
    know the per-key defaults itself.
    """
    return special_days_service.get_special_day_settings(db, current_user.tenant_id)


# #157: Typ-Farben. MUSS vor der generischen ``PUT /settings/{key}``-Route
# stehen, sonst fängt ``{key}`` das literal ``type-colors`` ab.
@router.get("/settings/type-colors")
def get_type_colors_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Effektive Typ-Farben (konfiguriert über Defaults gemerged)."""
    return type_colors_service.get_type_colors(db, current_user.tenant_id)


def _resave_closures_after_special_day_change(db, current_user, before, after, closed_years) -> None:
    """Teil B: Betriebsferien an Tagen mit geändertem Sondertag-Zustand neu
    buchen. Keine Warnung: abgeschlossene Jahre bleiben unangetastet, deren
    Hinweis liefert ``closed_year_warning_text`` im Aufrufer."""
    from app.routers import company_closures

    years = company_closures.closure_years(db, current_user.tenant_id)
    changed = special_days_service.changed_dates(
        special_days_service.setting_states(before, years),
        special_days_service.setting_states(after, years),
    )
    if changed:
        company_closures.resave_closures_for_dates(
            db, current_user, changed, closed_years=closed_years
        )


@router.put("/settings/type-colors")
def update_type_colors_setting(
    colors: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Setzt (partiell) Typ-Farben. Body: {typ: '#RRGGBB'}."""
    try:
        return type_colors_service.set_type_colors(db, current_user.tenant_id, colors)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/settings/{key}")
def update_setting(
    key: str,
    body: SettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a system setting value."""
    from app.services import holiday_service

    if key not in _ALLOWED_SETTINGS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Einstellung: {key}")
    value = body.value

    # #201: work_window_grace_minutes als ganze Zahl von 0 bis 1439 (ein ganzer
    # Tag, Gesamtreview 1.20 Fund 11) — mehr kappt nicht anders, sprengte aber
    # die int4-Spalte time_entries.clamp_grace_minutes (500 bei jedem Stempeln).
    if key == "work_window_grace_minutes":
        try:
            if not 0 <= int(value) <= work_window_service.MAX_GRACE_MINUTES:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Der Puffer muss eine ganze Zahl zwischen 0 und "
                    f"{work_window_service.MAX_GRACE_MINUTES} Minuten sein."
                ),
            )

    # #376: validate child_sick_days_default as a non-negative integer
    if key == "child_sick_days_default":
        try:
            if int(value) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="child_sick_days_default muss eine nicht-negative Zahl sein")

    # #371: validate + normalise shift_planning_weekdays (CSV of 0..6, 0=Mo).
    # At least one day; unique; stored sorted/deduped. Reject garbage with 400
    # (NOT the silent default the read-side helper applies) so the admin gets
    # feedback instead of a silently-ignored value.
    if key == "shift_planning_weekdays":
        parts = [p.strip() for p in str(value).split(",") if p.strip()]
        days = []
        for p in parts:
            try:
                n = int(p)
            except ValueError:
                raise HTTPException(status_code=400, detail="shift_planning_weekdays: nur Zahlen 0–6 (0=Montag) erlaubt")
            if not 0 <= n <= 6:
                raise HTTPException(status_code=400, detail="shift_planning_weekdays: Werte müssen zwischen 0 (Montag) und 6 (Sonntag) liegen")
            days.append(n)
        if not days:
            raise HTTPException(status_code=400, detail="shift_planning_weekdays: mindestens ein Wochentag muss aktiv sein")
        value = ",".join(str(n) for n in sorted(set(days)))

    # Validate holiday_state against supported states
    if key == "holiday_state":
        if value not in holiday_service.SUPPORTED_STATES:
            raise HTTPException(status_code=400, detail=f"Ungültiges Bundesland: {value}")

    # #146: validate the special-day settings.
    if key in special_days_service.MODE_KEYS:
        if value not in special_days_service.VALID_MODES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ungültiger Modus: {value}. "
                    f"Erlaubt: {', '.join(sorted(special_days_service.VALID_MODES))}"
                ),
            )
    if key in special_days_service.MAX_HOURS_KEYS:
        # Teil B: Stundenzahl am verkürzten 24./31.12. (0,25–12 in 0,25-Schritten).
        try:
            value = str(special_days_service.parse_max_hours(value))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=special_days_service.MAX_HOURS_ERROR
            )
    if key in special_days_service.VACATION_FLAG_KEYS:
        # Normalise to a canonical "true"/"false" string.
        if str(value).strip().lower() not in {"true", "false"}:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültiger Wert (true/false erwartet): {value}",
            )
        value = "true" if str(value).strip().lower() == "true" else "false"

    # #144: normalise boolean settings (vacation_approval_required,
    # break_exception_requires_approval) to canonical "true"/"false".
    if key in _BOOL_SETTINGS:
        if str(value).lower() not in ("true", "false"):
            raise HTTPException(status_code=400, detail=f"Ungültiger Wert für {key}: true/false erwartet")
        value = str(value).lower()

    # Gesamtreview: die Sondertag-Einstellungen wirken ohne Jahresgrenze, also
    # auch in abgeschlossenen Jahren — Zustand vor der Änderung festhalten.
    special_before = None
    if key in special_days_service.SETTING_KEYS:
        # Erst sperren, dann den Vorher-Zustand lesen: ein paralleler Wechsel
        # rechnete sonst gegen einen veralteten Stand und buchte nichts neu.
        special_days_service.lock_special_day_changes(db, current_user.tenant_id)
        special_before = special_days_service.get_special_day_settings(
            db, current_user.tenant_id
        )

    s = db.query(SystemSetting).filter(
        SystemSetting.key == key,
        SystemSetting.tenant_id == current_user.tenant_id
    ).first()
    old_value = s.value if s else None
    if not s:
        s = SystemSetting(key=key, value=str(value), description=key, tenant_id=current_user.tenant_id)
        db.add(s)
    else:
        s.value = str(value)
    # #537 (A2-5): dauerhafte, gehashte Spur (wer, wann, alt → neu) — der
    # Puffer, die Pausen-Ausnahme, Sondertage usw. bewegen Ist und Saldo.
    from app.services import admin_change_audit
    admin_change_audit.log_setting(
        db, current_user=current_user, key=key, old_value=old_value, new_value=s.value,
    )
    if key in special_days_service.MODE_KEYS or key in special_days_service.MAX_HOURS_KEYS:
        # F103: Nachvollziehbarkeit wie reduced_days._log_change — Akteur
        # ``user:<id>``, nie Klarname; ohne DB-Tabelle (Spec B2).
        logger.info(
            "special_day_setting changed by user:%s tenant:%s: %s %s -> %s",
            current_user.id, current_user.tenant_id, key, old_value, s.value,
        )

    warning = None
    if key == "holiday_state":
        # Atomarer Delete + Sync: alles in einer Transaktion (C2, I5)
        # #143: nur workalendar-Feiertage neu generieren; admin-gepflegte
        # Custom-Feiertage (source='admin') überstehen den Bundesland-Resync.
        # Gesamtreview 1.20 (B9): ALLE Jahre mit gesetzlichen Feiertagen neu
        # erzeugen, nicht nur das laufende und das nächste (frühere Jahre
        # standen sonst ohne Feiertage da) — siehe holiday_service.resync_state.
        holidays_before = _tenant_holiday_dates(db, current_user.tenant_id)
        try:
            changed_years = holiday_service.resync_state(
                db, str(value), tenant_id=current_user.tenant_id
            )  # commitet am Ende
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Einstellung gespeichert, aber Feiertage konnten nicht synchronisiert werden: {e}"
            )
        # Fix #5: geänderte Feiertage in einem abgeschlossenen Jahr machen dessen
        # Übertrag veraltet — melden, nie automatisch neu berechnen.
        warning = work_window_service.join_warnings(
            calculation_service.stale_year_closing_warning(
                db, current_user.tenant_id, changed_years
            ),
            # Gesamtreview 1.20: weggefallene bzw. neue Feiertage ändern, ob
            # gekappt wird (E35) — bestehende Einträge dort nur nennen.
            work_window_service.stale_clamp_hint(
                db, current_user.tenant_id,
                holidays_before ^ _tenant_holiday_dates(db, current_user.tenant_id),
            ),
        )
    else:
        if special_before is not None:
            db.flush()
            # Fix #5 auch hier: ändert der Wechsel Soll, Gutschrift oder
            # Urlaubsverbrauch des 24./31.12. in einem abgeschlossenen Jahr, ist
            # dessen Übertrag veraltet — melden, nie automatisch neu berechnen.
            special_after = special_days_service.get_special_day_settings(
                db, current_user.tenant_id
            )
            closed = calculation_service.all_closed_years(db, current_user.tenant_id)
            affected = special_days_service.years_affected_by_change(
                db,
                current_user.tenant_id,
                special_days_service.setting_states(special_before, closed),
                special_days_service.setting_states(special_after, closed),
            )
            entry_years = _tenant_entry_years(db, current_user.tenant_id)
            # Gesamtreview 1.20: „frei" ↔ Arbeitstag ändert, ob gekappt wird
            # (E35) — bestehende Einträge an diesen Tagen nur nennen.
            warning = work_window_service.join_warnings(
                calculation_service.closed_year_warning_text(affected),
                work_window_service.stale_clamp_hint(
                    db, current_user.tenant_id,
                    special_days_service.free_state_changed_dates(
                        special_days_service.setting_states(special_before, entry_years),
                        special_days_service.setting_states(special_after, entry_years),
                    ),
                ),
            )
            # Teil B: Betriebsferien an Tagen mit geändertem Zustand neu
            # buchen (gleiche Transaktion, committet erst unten). Import
            # lokal: Router untereinander nicht auf Modulebene verketten.
            _resave_closures_after_special_day_change(
                db, current_user, special_before, special_after, closed
            )
        db.commit()

    db.refresh(s)
    result = {"key": s.key, "value": s.value, "updated_at": s.updated_at}
    if warning:
        result["warning"] = warning
    return result
