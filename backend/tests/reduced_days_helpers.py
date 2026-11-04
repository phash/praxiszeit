"""Gemeinsame Bausteine der Teil-B-Suiten ``test_reduced_days_*``."""
from decimal import Decimal

from app.models import ReducedDay, User, UserRole
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID


def reduce_day(db, d, hours, label="Rosenmontag") -> None:
    """Verkürzt den Tag ``d`` auf ``hours``: 24./31.12. über die Sondertage-Einstellung,
    jedes andere Datum über einen eigenen ``ReducedDay``."""
    if (d.month, d.day) in ((12, 24), (12, 31)):
        prefix = "special_day_dec24" if d.day == 24 else "special_day_dec31"
        for k, v in ((f"{prefix}_mode", "max_hours"), (f"{prefix}_max_hours", str(hours))):
            db.add(SystemSetting(key=k, value=v, description=k, tenant_id=DEFAULT_TENANT_ID))
    else:
        db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=d, label=label,
                          max_hours=Decimal(str(hours))))
    db.commit()


def make_user_3h(db, **kw) -> User:
    """Mitarbeiter mit 15 h/Woche an 5 Tagen (3 h Tagessoll); ``kw`` überschreibt Felder."""
    base = dict(username="u3", email="u3@t.l", password_hash="x", first_name="U",
                last_name="3", role=UserRole.EMPLOYEE, weekly_hours=Decimal("15"),
                work_days_per_week=5, vacation_days=30, track_hours=True, is_active=True,
                tenant_id=DEFAULT_TENANT_ID)
    base.update(kw)
    u = User(**base)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u
