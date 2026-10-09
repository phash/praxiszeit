"""Spec 6.1 / 17.3 (Postgres-only): SQL-Ausdruck von net_hours folgt dem
Python-Hybrid inkl. uncredited_minutes — bis auf n × 0,005 h (keine Rundung je
Zeile in SQL, sonst bräche die Byte-Identität bestehender Summen)."""
import os
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

ADMIN_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_URL or not ADMIN_URL.startswith("postgresql"):
    pytest.skip("braucht Postgres (ADMIN_DB_URL / DATABASE_URL_MIGRATIONS)", allow_module_level=True)

from app.models import TimeEntry, User, UserRole  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

TENANT_ID = uuid.UUID("07300000-0000-4000-8000-0000000000aa")


@pytest.fixture
def session():
    engine = create_engine(ADMIN_URL)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.rollback()
        s.execute(text("DELETE FROM time_entries WHERE tenant_id = :t"), {"t": TENANT_ID})
        s.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": TENANT_ID})
        s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": TENANT_ID})
        s.commit()
        s.close()
        engine.dispose()


def test_sql_sum_matches_python_sum(session):
    session.add(Tenant(id=TENANT_ID, name="Parität 073", slug=f"paritaet-{uuid.uuid4().hex[:8]}",
                       is_active=True, mode="multi"))
    user = User(id=uuid.uuid4(), tenant_id=TENANT_ID, username="paritaet", password_hash="x",
                first_name="P", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40,
                vacation_days=30, work_days_per_week=5)
    session.add(user)
    session.flush()
    rows = [  # (start, end, pause, uncredited) — K1, K4, K3, K7 (gespeichert), K9, offen
        (time(8, 0), time(18, 0), 0, 150),
        (time(8, 0), time(12, 5), 0, 0),
        (time(12, 30), time(14, 30), 0, 120),
        (time(7, 45), time(18, 15), 0, 150),
        (time(8, 0), time(18, 0), 30, 150),
        (time(9, 0), None, 0, 0),
    ]
    for i, (start, end, brk, unc) in enumerate(rows):
        session.add(TimeEntry(tenant_id=TENANT_ID, user_id=user.id, date=date(2026, 6, 1 + i),
                              start_time=start, end_time=end, break_minutes=brk,
                              uncredited_minutes=unc))
    session.flush()
    entries = session.query(TimeEntry).filter(TimeEntry.tenant_id == TENANT_ID).all()
    py_sum = sum((e.net_hours for e in entries), Decimal("0"))
    sql_sum = session.query(func.sum(TimeEntry.net_hours)).filter(TimeEntry.tenant_id == TENANT_ID).scalar()
    closed = sum(1 for e in entries if e.end_time is not None)
    assert abs(Decimal(str(sql_sum)) - py_sum) <= Decimal("0.005") * closed
