# Review-Findings Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all open findings from the code review, security review, and ArbZG compliance audit of Multi-Tenant Phase 1-3.

**Architecture:** Migration 028 fixes the system_settings PK and adds RLS to tenants. Application-level fixes add tenant_id filtering to holiday_service and superadmin context to DBErrorHandler. All changes are backward-compatible with the existing single-tenant deployment.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL 16, Alembic

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/alembic/versions/2026_03_26_...-028_fix_review_findings.py` | Migration: system_settings composite PK, tenants RLS |
| Modify | `backend/app/models/system_setting.py` | Composite PK (key + tenant_id) |
| Modify | `backend/app/services/holiday_service.py` | tenant_id filter in sync_holidays, delete_all_holidays |
| Modify | `backend/app/services/error_log_service.py` | Superadmin context in DBErrorHandler.emit() |
| Create | `backend/tests/test_review_findings.py` | Tests for all fixes |

---

### Task 1: Migration 028 — system_settings Composite PK + tenants RLS

**Files:**
- Create: `backend/alembic/versions/2026_03_26_1200-028_fix_review_findings.py`

- [ ] **Step 1: Create migration file**

```python
"""Fix review findings: system_settings composite PK, tenants RLS policy

Revision ID: 028_fix_review_findings
Revises: 027_add_multi_tenant
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = '028_fix_review_findings'
down_revision = '027_add_multi_tenant'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Fix system_settings PK: key-only → composite (key, tenant_id)
    #    Backfill NULL tenant_ids to default tenant first
    op.execute(
        "UPDATE system_settings SET tenant_id = '00000000-0000-0000-0000-000000000001' "
        "WHERE tenant_id IS NULL"
    )
    op.drop_constraint('system_settings_pkey', 'system_settings', type_='primary')
    op.create_primary_key('system_settings_pkey', 'system_settings', ['key', 'tenant_id'])

    # 2. Add RLS policy to tenants table
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON tenants
        USING (
            current_setting('app.is_superadmin', true) = 'true'
            OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.is_superadmin', true) = 'true'
            OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)


def downgrade() -> None:
    # Remove tenants RLS
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")

    # Revert system_settings PK to key-only
    op.drop_constraint('system_settings_pkey', 'system_settings', type_='primary')
    op.create_primary_key('system_settings_pkey', 'system_settings', ['key'])
```

- [ ] **Step 2: Run migration locally**

Run: `docker compose exec backend alembic upgrade head`
Expected: "Running upgrade 027_add_multi_tenant -> 028_fix_review_findings"

- [ ] **Step 3: Verify in DB**

```bash
docker compose exec db psql -U praxiszeit -d praxiszeit -c "\d system_settings"
# PK should show (key, tenant_id)

docker compose exec db psql -U praxiszeit -d praxiszeit -c "SELECT polname FROM pg_policy WHERE polrelid = 'tenants'::regclass"
# Should show tenant_isolation
```

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/2026_03_26_1200-028_fix_review_findings.py
git commit -m "fix: migration 028 — system_settings composite PK + tenants RLS"
```

---

### Task 2: Update SystemSetting Model — Composite PK

**Files:**
- Modify: `backend/app/models/system_setting.py`

- [ ] **Step 1: Write failing test**

In `backend/tests/test_review_findings.py`:

```python
"""Tests for review finding fixes."""
import uuid
import pytest
from datetime import date
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TENANT_B_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class TestSystemSettingsMultiTenant:
    """C3: system_settings must support same key for different tenants."""

    def test_two_tenants_same_key(self, db):
        """Two tenants can each have their own 'holiday_state' setting."""
        # Create tenant B
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.commit()

        s1 = SystemSetting(key="holiday_state", value="Bayern", tenant_id=DEFAULT_TENANT_ID)
        s2 = SystemSetting(key="holiday_state", value="Berlin", tenant_id=TENANT_B_ID)
        db.add(s1)
        db.add(s2)
        db.commit()  # Must NOT raise IntegrityError

        result = db.query(SystemSetting).filter(
            SystemSetting.key == "holiday_state"
        ).all()
        assert len(result) == 2
        values = {str(r.tenant_id): r.value for r in result}
        assert values[str(DEFAULT_TENANT_ID)] == "Bayern"
        assert values[str(TENANT_B_ID)] == "Berlin"

        # Cleanup
        db.query(SystemSetting).filter(SystemSetting.key == "holiday_state").delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_review_findings.py::TestSystemSettingsMultiTenant -v`
Expected: FAIL with IntegrityError (duplicate PK on 'holiday_state')

- [ ] **Step 3: Update model**

`backend/app/models/system_setting.py`:

```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class SystemSetting(Base):
    """Key-value store for runtime-configurable application settings."""

    __tablename__ = "system_settings"
    __table_args__ = (
        PrimaryKeyConstraint('key', 'tenant_id'),
    )

    key = Column(String(100), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<SystemSetting(key={self.key}, tenant_id={self.tenant_id}, value={self.value})>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/test_review_findings.py::TestSystemSettingsMultiTenant -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/system_setting.py backend/tests/test_review_findings.py
git commit -m "fix: system_settings composite PK (key, tenant_id) — allows per-tenant settings"
```

---

### Task 3: Fix holiday_service — tenant_id in sync_holidays + delete_all_holidays

**Files:**
- Modify: `backend/app/services/holiday_service.py`
- Modify: `backend/tests/test_review_findings.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_review_findings.py`:

```python
from app.services.holiday_service import sync_holidays, delete_all_holidays
from app.models.public_holiday import PublicHoliday


class TestHolidayServiceTenantIsolation:
    """M1/M2: holiday_service must filter by tenant_id."""

    def test_sync_holidays_does_not_see_other_tenant(self, db):
        """sync_holidays existing-check must filter by tenant_id."""
        # Insert a holiday for tenant A
        h = PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID)
        db.add(h)
        db.commit()

        # Sync for tenant B — should create its OWN Neujahr, not skip it
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.commit()

        count = sync_holidays(db, 2026, "Bayern", tenant_id=TENANT_B_ID)
        db.commit()

        # Both tenants should have holidays
        all_h = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 1, 1)).all()
        tenant_ids = {str(h.tenant_id) for h in all_h}
        assert str(DEFAULT_TENANT_ID) in tenant_ids
        assert str(TENANT_B_ID) in tenant_ids

        # Cleanup
        db.query(PublicHoliday).filter(PublicHoliday.tenant_id == TENANT_B_ID).delete()
        db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == DEFAULT_TENANT_ID,
            PublicHoliday.date == date(2026, 1, 1)
        ).delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()

    def test_delete_all_holidays_scoped_to_tenant(self, db):
        """delete_all_holidays with tenant_id must only delete that tenant's holidays."""
        h1 = PublicHoliday(date=date(2026, 12, 25), name="Weihnachten", year=2026, tenant_id=DEFAULT_TENANT_ID)
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        h2 = PublicHoliday(date=date(2026, 12, 25), name="Weihnachten", year=2026, tenant_id=TENANT_B_ID)
        db.add_all([h1, h2])
        db.commit()

        deleted = delete_all_holidays(db, tenant_id=DEFAULT_TENANT_ID)
        db.commit()

        remaining = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 12, 25)).all()
        assert len(remaining) == 1
        assert remaining[0].tenant_id == TENANT_B_ID

        # Cleanup
        db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 12, 25)).delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_review_findings.py::TestHolidayServiceTenantIsolation -v`
Expected: FAIL — sync_holidays finds other tenant's holiday, delete_all_holidays has no tenant_id param

- [ ] **Step 3: Fix holiday_service.py**

In `sync_holidays()` — add tenant_id to the existing-check (line ~100):

```python
def sync_holidays(db: Session, year: int, state: Optional[str] = None, tenant_id=None) -> int:
    cal = _get_calendar(state)
    holidays = cal.holidays(year)

    count = 0
    for holiday_date, holiday_name in holidays:
        german_name = _translate_name(holiday_name)

        query = db.query(PublicHoliday).filter(PublicHoliday.date == holiday_date)
        if tenant_id is not None:
            query = query.filter(PublicHoliday.tenant_id == tenant_id)
        existing = query.first()

        if not existing:
            holiday = PublicHoliday(
                date=holiday_date,
                name=german_name,
                year=year,
                tenant_id=tenant_id,
            )
            db.add(holiday)
            count += 1
        elif existing.name != german_name:
            existing.name = german_name

    return count
```

In `delete_all_holidays()` — add optional tenant_id param:

```python
def delete_all_holidays(db: Session, tenant_id=None) -> int:
    """Delete holidays from the database. If tenant_id given, only for that tenant."""
    query = db.query(PublicHoliday)
    if tenant_id is not None:
        query = query.filter(PublicHoliday.tenant_id == tenant_id)
    count = query.count()
    query.delete()
    return count
```

Update `admin.py` call site (~line 984):

```python
holiday_service.delete_all_holidays(db, tenant_id=current_user.tenant_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_review_findings.py::TestHolidayServiceTenantIsolation -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `docker compose exec backend pytest tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/holiday_service.py backend/app/routers/admin.py backend/tests/test_review_findings.py
git commit -m "fix: holiday_service tenant isolation — filter by tenant_id in sync + delete"
```

---

### Task 4: Fix DBErrorHandler — Superadmin Context

**Files:**
- Modify: `backend/app/services/error_log_service.py`

- [ ] **Step 1: Add superadmin context to emit()**

```python
def emit(self, record: logging.LogRecord):
    try:
        db: Session = self._factory()
        set_superadmin_context(db)  # Ensure error handler can see all errors for dedup
        tb = None
        if record.exc_info:
            # ... rest unchanged
```

Add import at top of file:

```python
from app.database import set_superadmin_context
```

- [ ] **Step 2: Run existing tests**

Run: `docker compose exec backend pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/error_log_service.py
git commit -m "fix: DBErrorHandler sets superadmin context for error log dedup"
```

---

### Task 5: Full Test Run + Final Commit

- [ ] **Step 1: Rebuild and run all tests**

```bash
docker compose build backend
docker compose up -d
docker compose exec backend pytest tests/ -v
docker compose exec backend pytest tests/test_tenant_rls.py tests/test_tenant_auth.py -v
```

Expected: All pass (including new test_review_findings.py)

- [ ] **Step 2: Final commit if needed**

```bash
git add -A
git commit -m "test: review findings — system_settings PK, holiday isolation, error handler"
```
