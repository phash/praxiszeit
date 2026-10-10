"""Test-Bausteine für PR3 (Spec 9–12): eingefrorenes „heute", Verlaufszeilen,
Einträge, Abwesenheiten. Eine Quelle für alle Neukappungs-Suiten, damit „heute",
Puffer und Verlaufszeilen überall gleich gebaut werden."""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, TimeEntry, TimeEntryAuditLog, WorkingHoursChange
from app.models.system_setting import SystemSetting
from app.services import timezone_service, work_blocks_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.work_blocks_fixtures import block_week

TODAY = date(2026, 10, 8)      # Donnerstag — Beispiel aus Spec 12.1
EFF = date(2026, 9, 1)         # Dienstag
MONDAYS = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28), date(2026, 10, 5))

# Ein vollständiges Schutzpaket (Spec 9.5) für Suiten, die die Rückrechnung
# prüfen und nicht das Schutzpaket selbst.
RETRO_REASON = {
    "retroactive_reason_type": "erfassungsfehler",
    "retroactive_reason_text": "Hinterlegte Arbeitszeit war falsch erfasst",
    "wage_risk_confirmed": True,
}

# Spec 12.1: Anna — Mo 08–12 + 15–18, Di 08–12, Do 08–12, Pause 0 → 15 h/Woche.
ANNA_WEEK = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                       thu=[("08:00", "12:00")])

_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri")


def t(h: int, m: int = 0) -> time:
    return time(h, m)


def freeze(monkeypatch, d: date = TODAY, at: time = time(10, 0)) -> None:
    """„Heute"/„jetzt" für ALLE Aufrufer: ``today_local`` löst ``now_local`` zur
    Laufzeit über die Modulglobalen von ``timezone_service`` auf."""
    monkeypatch.setattr(timezone_service, "now_local",
                        lambda: datetime.combine(d, at, tzinfo=timezone_service.LOCAL_TZ))


def with_pauses(week: list, **pauses: int) -> list:
    """Kopie der Woche mit Pausen je Tag (``mon=60``) — ``block_week`` setzt eine
    Pause für alle Tage mit Blöcken."""
    out = [dict(day, blocks=[dict(b) for b in day["blocks"]]) for day in week]
    for key, minutes in pauses.items():
        out[_DAY_KEYS.index(key)]["pause_minutes"] = minutes
    return out


def change_row(user, effective_from: date, *, week=None, weekly_hours=None, day_hours=None,
               blocks=None, note=None) -> WorkingHoursChange:
    """Ungespeicherte Verlaufszeile: NEUE Blöcke (``week``, Soll materialisiert wie
    der Dialog), Tagesplan (``day_hours``) oder gleichmäßig (``weekly_hours``);
    ``blocks`` setzt bei den beiden letzten ein Altfenster."""
    common = dict(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, effective_from=effective_from, note=note)
    if week is not None:
        d = work_blocks_service.derive_targets(week)
        return WorkingHoursChange(
            **common, weekly_hours=d["weekly_hours"], use_daily_schedule=True,
            **{f: d[f] for f in work_blocks_service.HOURS_FIELDS},
            work_days_per_week=d["work_days_per_week"], blocks=week,
        )
    if day_hours is not None:
        values = [Decimal(str(v)) if v else None for v in day_hours]
        return WorkingHoursChange(
            **common, weekly_hours=sum((v for v in values if v), Decimal("0")), use_daily_schedule=True,
            **dict(zip(work_blocks_service.HOURS_FIELDS, values)),
            work_days_per_week=sum(1 for v in values if v), blocks=blocks,
        )
    return WorkingHoursChange(**common, weekly_hours=Decimal(str(weekly_hours)), use_daily_schedule=False,
                              work_days_per_week=5, blocks=blocks)


def add_row(db, user, effective_from: date, **kwargs) -> WorkingHoursChange:
    row = change_row(user, effective_from, **kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def entry(db, user, d: date, start: time, end: Optional[time], *, raw_start=None, raw_end=None,
          uncredited: int = 0, grace: Optional[int] = 15, brk: int = 0, credit_override: bool = False,
          auto_closed: bool = False) -> TimeEntry:
    e = TimeEntry(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=d, start_time=start, end_time=end,
        raw_start_time=raw_start, raw_end_time=raw_end, break_minutes=brk, uncredited_minutes=uncredited,
        clamp_grace_minutes=grace, credit_override=credit_override, auto_closed=auto_closed,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def absence(db, user, d: date, typ=AbsenceType.SICK, hours: float = 8.0, half_day: bool = False) -> Absence:
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=typ, hours=hours, half_day=half_day)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def set_grace(db, minutes: int) -> None:
    db.add(SystemSetting(key="work_window_grace_minutes", value=str(minutes), tenant_id=DEFAULT_TENANT_ID))
    db.commit()


def admin_client(db, admin) -> TestClient:
    """TestClient mit überschriebener DB/Auth — der Aufrufer räumt per
    ``test_app.dependency_overrides.clear()`` auf (Fixture-Teardown)."""
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


def reclamp_logs(db, user, *, summary: Optional[bool] = None) -> list:
    """``wh_reclamp``-Zeilen der Person; ``summary=True`` nur Sammelzeilen,
    ``False`` nur Einzelzeilen."""
    q = db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
        TimeEntryAuditLog.source == "wh_reclamp",
    )
    if summary is True:
        q = q.filter(TimeEntryAuditLog.time_entry_id.is_(None), TimeEntryAuditLog.old_date.is_(None))
    elif summary is False:
        q = q.filter(TimeEntryAuditLog.time_entry_id.isnot(None))
    return q.order_by(TimeEntryAuditLog.created_at).all()
