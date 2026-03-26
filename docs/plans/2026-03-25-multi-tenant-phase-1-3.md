# Multi-Tenant Phase 1-3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-tenant support to PraxisZeit with a `tenants` table, `tenant_id` on all 12 existing tables, JWT tenant claim, tenant-aware middleware, and PostgreSQL Row-Level Security — without breaking anything for the existing production instance.

**Architecture:** Single shared PostgreSQL database with `tenant_id` column on every table. RLS policies enforce isolation at the DB level. Middleware reads `tenant_id` from JWT and sets `app.tenant_id` session variable. Superadmin users have `tenant_id = NULL` and bypass RLS.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL 16 (RLS), PyJWT, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-multi-tenant-phase-1-3-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/models/tenant.py` | Tenant SQLAlchemy model |
| `backend/alembic/versions/2026_03_25_2000-027_add_multi_tenant.py` | Big-bang migration |
| `backend/tests/test_tenant_migration.py` | Migration integrity tests |
| `backend/tests/test_tenant_rls.py` | RLS isolation tests |
| `backend/tests/test_tenant_auth.py` | JWT + middleware tenant tests |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Export `Tenant` |
| `backend/app/models/user.py` | Add `tenant_id` FK column |
| `backend/app/models/time_entry.py` | Add `tenant_id` FK column, update unique constraint |
| `backend/app/models/absence.py` | Add `tenant_id` FK column, update unique constraint |
| `backend/app/models/vacation_request.py` | Add `tenant_id` FK column |
| `backend/app/models/change_request.py` | Add `tenant_id` FK column |
| `backend/app/models/time_entry_audit_log.py` | Add `tenant_id` FK column |
| `backend/app/models/working_hours_change.py` | Add `tenant_id` FK column |
| `backend/app/models/year_carryover.py` | Add `tenant_id` FK column |
| `backend/app/models/public_holiday.py` | Add `tenant_id` FK column, update unique constraint |
| `backend/app/models/company_closure.py` | Add `tenant_id` FK column |
| `backend/app/models/error_log.py` | Add `tenant_id` FK column |
| `backend/app/models/system_setting.py` | Add `tenant_id` FK column (nullable), update PK |
| `backend/app/services/auth_service.py` | Add `tenant_id` param to token creation |
| `backend/app/middleware/auth.py` | Set `app.tenant_id` on DB session |
| `backend/app/database.py` | Add `get_db_with_tenant` helper |
| `backend/app/routers/auth.py` | Pass `tenant_id` when creating tokens |
| `backend/app/main.py` | Tenant-aware admin creation, holiday sync |
| `backend/alembic/env.py` | Import Tenant model |
| `backend/tests/conftest.py` | Add tenant fixtures, switch to PostgreSQL for RLS tests |

---

## Task 1: Create Tenant Model

**Files:**
- Create: `backend/app/models/tenant.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the Tenant model**

```python
# backend/app/models/tenant.py
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Tenant(Base):
    """Tenant model for multi-tenant isolation."""

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    mode = Column(String(20), default="multi", nullable=False)  # 'single' | 'multi'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"
```

- [ ] **Step 2: Export Tenant from models/__init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.tenant import Tenant
```

And add `"Tenant"` to `__all__`.

- [ ] **Step 3: Import Tenant in alembic env.py**

Add to the import line in `backend/alembic/env.py:10`:

```python
from app.models import User, TimeEntry, Absence, PublicHoliday, ChangeRequest, TimeEntryAuditLog, Tenant
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/tenant.py backend/app/models/__init__.py backend/alembic/env.py
git commit -m "feat: add Tenant model"
```

---

## Task 2: Add tenant_id to All Existing Models

**Files:**
- Modify: all 12 model files in `backend/app/models/`

For every model, add a `tenant_id` column. The pattern differs slightly:

**Nullable tenant_id (Superadmin / global settings):**
- `user.py` — `tenant_id` nullable (NULL = superadmin)
- `system_setting.py` — `tenant_id` nullable (NULL = global setting)

**NOT NULL tenant_id (all others):**
- `time_entry.py`, `absence.py`, `vacation_request.py`, `change_request.py`, `time_entry_audit_log.py`, `working_hours_change.py`, `year_carryover.py`, `public_holiday.py`, `company_closure.py`, `error_log.py`

- [ ] **Step 1: Add tenant_id to User model**

In `backend/app/models/user.py`, add import and column:

```python
# Add ForeignKey to imports (line 1):
from sqlalchemy import Column, String, Boolean, Numeric, Integer, Enum, DateTime, Date, Text, ForeignKey

# Add after id column (after line 20):
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
```

Replace the username unique constraint. Change line 21:
```python
    username = Column(String(100), nullable=False, index=True)  # unique within tenant (enforced by DB constraint)
```

- [ ] **Step 2: Add tenant_id to TimeEntry model**

In `backend/app/models/time_entry.py`, add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

Update `__table_args__` (replace existing):
```python
    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'date', 'start_time', name='uq_tenant_user_date_start'),
    )
```

- [ ] **Step 3: Add tenant_id to Absence model**

In `backend/app/models/absence.py`, add `ForeignKey` to imports and add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

Update `__table_args__`:
```python
    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'date', 'type', name='uq_tenant_user_date_type'),
    )
```

- [ ] **Step 4: Add tenant_id to VacationRequest model**

In `backend/app/models/vacation_request.py`, add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 5: Add tenant_id to ChangeRequest model**

In `backend/app/models/change_request.py`, add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 6: Add tenant_id to TimeEntryAuditLog model**

In `backend/app/models/time_entry_audit_log.py`, add `ForeignKey` to imports and add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 7: Add tenant_id to WorkingHoursChange model**

In `backend/app/models/working_hours_change.py`, add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 8: Add tenant_id to YearCarryover model**

In `backend/app/models/year_carryover.py`, add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 9: Add tenant_id to PublicHoliday model**

In `backend/app/models/public_holiday.py`, add `ForeignKey` to imports and add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

Change `date` column — remove `unique=True` (uniqueness is now per tenant, enforced by migration constraint):
```python
    date = Column(Date, nullable=False, index=True)
```

- [ ] **Step 10: Add tenant_id to CompanyClosure model**

In `backend/app/models/company_closure.py`, add `ForeignKey` to imports and add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 11: Add tenant_id to ErrorLog model**

In `backend/app/models/error_log.py`, add `ForeignKey` to imports and add after `id` column:

```python
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

- [ ] **Step 12: Add tenant_id to SystemSetting model**

In `backend/app/models/system_setting.py`, add imports and tenant_id:

```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

# Add after key column:
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
```

- [ ] **Step 13: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add tenant_id column to all 12 models"
```

---

## Task 3: Write the Big-Bang Migration (027)

**Files:**
- Create: `backend/alembic/versions/2026_03_25_2000-027_add_multi_tenant.py`

- [ ] **Step 1: Write migration file**

```python
"""Add multi-tenant support: tenants table, tenant_id on all tables, updated constraints

Revision ID: 027_add_multi_tenant
Revises: 026_add_year_carryovers
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '027_add_multi_tenant'
down_revision = '026_add_year_carryovers'
branch_labels = None
depends_on = None

# All tables that get a NOT NULL tenant_id
_NOT_NULL_TABLES = [
    'time_entries',
    'absences',
    'vacation_requests',
    'change_requests',
    'time_entry_audit_logs',
    'working_hours_changes',
    'year_carryovers',
    'public_holidays',
    'company_closures',
    'error_logs',
]

# Tables with nullable tenant_id
_NULLABLE_TABLES = [
    'users',
    'system_settings',
]


def upgrade() -> None:
    # 1. Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('mode', sa.String(20), nullable=False, server_default='multi'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # 2. Insert default tenant
    default_tenant_id = op.inline_literal("'00000000-0000-0000-0000-000000000001'")
    op.execute(
        "INSERT INTO tenants (id, name, slug, is_active, mode) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'Default', 'default', true, 'single')"
    )

    # 3. Add tenant_id to NOT NULL tables
    for table in _NOT_NULL_TABLES:
        op.add_column(table, sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '00000000-0000-0000-0000-000000000001'")
        op.alter_column(table, 'tenant_id', nullable=False)
        op.create_foreign_key(f'fk_{table}_tenant_id', table, 'tenants', ['tenant_id'], ['id'])
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])

    # 4. Add tenant_id to nullable tables (users, system_settings)
    for table in _NULLABLE_TABLES:
        op.add_column(table, sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = '00000000-0000-0000-0000-000000000001'")
        # Keep nullable — NULL = superadmin / global setting
        op.create_foreign_key(f'fk_{table}_tenant_id', table, 'tenants', ['tenant_id'], ['id'])
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])

    # 5. Drop old unique constraints and create new tenant-scoped ones

    # users: username was unique globally
    op.drop_constraint('users_username_key', 'users', type_='unique')
    op.create_unique_constraint('uq_tenant_username', 'users', ['tenant_id', 'username'])

    # users: email (if unique constraint exists — email is nullable, check)
    # Email had no unique constraint in schema, skip

    # time_entries: (user_id, date, start_time) -> (tenant_id, user_id, date, start_time)
    op.drop_constraint('uq_user_date_start', 'time_entries', type_='unique')
    op.create_unique_constraint('uq_tenant_user_date_start', 'time_entries',
                                ['tenant_id', 'user_id', 'date', 'start_time'])

    # absences: (user_id, date, type) -> (tenant_id, user_id, date, type)
    op.drop_constraint('uq_user_date_type', 'absences', type_='unique')
    op.create_unique_constraint('uq_tenant_user_date_type', 'absences',
                                ['tenant_id', 'user_id', 'date', 'type'])

    # public_holidays: date was unique globally -> (tenant_id, date)
    op.drop_constraint('public_holidays_date_key', 'public_holidays', type_='unique')
    op.create_unique_constraint('uq_tenant_holiday_date', 'public_holidays',
                                ['tenant_id', 'date'])

    # year_carryovers: (user_id, year) -> (tenant_id, user_id, year)
    op.drop_constraint('uq_year_carryover_user_year', 'year_carryovers', type_='unique')
    op.create_unique_constraint('uq_tenant_year_carryover_user_year', 'year_carryovers',
                                ['tenant_id', 'user_id', 'year'])


def downgrade() -> None:
    # Reverse unique constraints
    op.drop_constraint('uq_tenant_year_carryover_user_year', 'year_carryovers', type_='unique')
    op.create_unique_constraint('uq_year_carryover_user_year', 'year_carryovers',
                                ['user_id', 'year'])

    op.drop_constraint('uq_tenant_holiday_date', 'public_holidays', type_='unique')
    op.create_unique_constraint('public_holidays_date_key', 'public_holidays', ['date'])

    op.drop_constraint('uq_tenant_user_date_type', 'absences', type_='unique')
    op.create_unique_constraint('uq_user_date_type', 'absences',
                                ['user_id', 'date', 'type'])

    op.drop_constraint('uq_tenant_user_date_start', 'time_entries', type_='unique')
    op.create_unique_constraint('uq_user_date_start', 'time_entries',
                                ['user_id', 'date', 'start_time'])

    op.drop_constraint('uq_tenant_username', 'users', type_='unique')
    op.create_unique_constraint('users_username_key', 'users', ['username'])

    # Drop tenant_id from all tables
    all_tables = _NULLABLE_TABLES + _NOT_NULL_TABLES
    for table in all_tables:
        op.drop_index(f'ix_{table}_tenant_id', table)
        op.drop_constraint(f'fk_{table}_tenant_id', table, type_='foreignkey')
        op.drop_column(table, 'tenant_id')

    # Drop tenants table
    op.drop_table('tenants')
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/2026_03_25_2000-027_add_multi_tenant.py
git commit -m "feat: add migration 027 — multi-tenant big-bang"
```

---

## Task 4: Update Auth Service — JWT with tenant_id

**Files:**
- Modify: `backend/app/services/auth_service.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_tenant_auth.py`:

```python
import pytest
from app.services import auth_service


def test_access_token_contains_tid():
    """Access token should include tid claim when tenant_id is provided."""
    token = auth_service.create_access_token(
        user_id="user-123",
        role="admin",
        token_version=0,
        tenant_id="tenant-456",
    )
    payload = auth_service.decode_token(token)
    assert payload["tid"] == "tenant-456"


def test_access_token_no_tid_for_superadmin():
    """Access token should omit tid when tenant_id is None (superadmin)."""
    token = auth_service.create_access_token(
        user_id="user-123",
        role="admin",
        token_version=0,
        tenant_id=None,
    )
    payload = auth_service.decode_token(token)
    assert "tid" not in payload


def test_refresh_token_contains_tid():
    """Refresh token should include tid claim when tenant_id is provided."""
    token = auth_service.create_refresh_token(
        user_id="user-123",
        token_version=0,
        tenant_id="tenant-456",
    )
    payload = auth_service.decode_token(token)
    assert payload["tid"] == "tenant-456"


def test_refresh_token_no_tid_for_superadmin():
    """Refresh token should omit tid when tenant_id is None."""
    token = auth_service.create_refresh_token(
        user_id="user-123",
        token_version=0,
        tenant_id=None,
    )
    payload = auth_service.decode_token(token)
    assert "tid" not in payload


def test_backward_compat_no_tenant_id_param():
    """Calling without tenant_id param should still work (backward compat)."""
    token = auth_service.create_access_token(
        user_id="user-123",
        role="admin",
        token_version=0,
    )
    payload = auth_service.decode_token(token)
    assert "tid" not in payload
    assert payload["sub"] == "user-123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tenant_auth.py -v`
Expected: FAIL — `create_access_token` doesn't accept `tenant_id` param yet.

- [ ] **Step 3: Update auth_service.py**

In `backend/app/services/auth_service.py`, modify `create_access_token` (line 30):

```python
def create_access_token(user_id: str, role: str, token_version: int = 0, tenant_id: str = None) -> str:
    """
    Create JWT access token with 30 minutes expiry.

    Args:
        user_id: User UUID as string
        role: User role (admin or employee)
        token_version: Current token version for revocation support
        tenant_id: Tenant UUID as string (None for superadmin)

    Returns:
        Encoded JWT token
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "tv": token_version,
        "exp": expire
    }
    if tenant_id is not None:
        payload["tid"] = tenant_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
```

Modify `create_refresh_token` (line 53):

```python
def create_refresh_token(user_id: str, token_version: int = 0, tenant_id: str = None) -> str:
    """
    Create JWT refresh token with 7 days expiry.

    Args:
        user_id: User UUID as string
        token_version: Current token version for revocation support
        tenant_id: Tenant UUID as string (None for superadmin)

    Returns:
        Encoded JWT token
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "tv": token_version,
        "exp": expire
    }
    if tenant_id is not None:
        payload["tid"] = tenant_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tenant_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_tenant_auth.py
git commit -m "feat: add tenant_id (tid) claim to JWT tokens"
```

---

## Task 5: Update Auth Middleware — Set app.tenant_id on DB Session

**Files:**
- Modify: `backend/app/middleware/auth.py`
- Modify: `backend/app/database.py`

- [ ] **Step 1: Add set_tenant_context helper to database.py**

Add to `backend/app/database.py` after `get_db()`:

```python
from sqlalchemy import text


def set_tenant_context(db, tenant_id: str):
    """Set PostgreSQL session variable for RLS. Must be called within a transaction."""
    db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
```

- [ ] **Step 2: Update get_current_user in middleware/auth.py**

Replace the entire file `backend/app/middleware/auth.py`:

```python
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db, set_tenant_context
from app.models import User, UserRole
from app.services import auth_service

# HTTP Bearer token security scheme
security = HTTPBearer()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    Sets app.tenant_id on the DB session for RLS enforcement.
    """
    token = credentials.credentials

    # Decode token
    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token"
        )

    # Get user from database (before RLS is set — user lookup must work)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden oder deaktiviert"
        )

    # Validate token version (revocation check)
    token_version = payload.get("tv", 0)
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wurde widerrufen. Bitte erneut anmelden."
        )

    # Set tenant context for RLS
    # tid from JWT, fallback to user.tenant_id (backward compat for old tokens)
    tenant_id = payload.get("tid") or (str(user.tenant_id) if user.tenant_id else None)
    if tenant_id:
        set_tenant_context(db, tenant_id)
        request.state.tenant_id = tenant_id
    else:
        # Superadmin — no tenant context, RLS bypassed
        request.state.tenant_id = None

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert: Admin-Rechte erforderlich"
        )

    return current_user
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/middleware/auth.py backend/app/database.py
git commit -m "feat: tenant-aware middleware sets app.tenant_id for RLS"
```

---

## Task 6: Update Auth Router — Pass tenant_id to Token Creation

**Files:**
- Modify: `backend/app/routers/auth.py`

- [ ] **Step 1: Update login endpoint**

In `backend/app/routers/auth.py`, update the token creation in `login()` (around line 104-105):

```python
    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
    refresh_token = auth_service.create_refresh_token(str(user.id), user.token_version, tenant_id_str)
```

- [ ] **Step 2: Update refresh endpoint**

In `refresh_token()` (around line 158):

```python
    tenant_id_str = str(user.tenant_id) if user.tenant_id else None
    access_token = auth_service.create_access_token(str(user.id), user.role.value, user.token_version, tenant_id_str)
```

- [ ] **Step 3: Update change-password endpoint**

In `change_password()` (around line 211-213):

```python
    tenant_id_str = str(current_user.tenant_id) if current_user.tenant_id else None
    new_access_token = auth_service.create_access_token(
        str(current_user.id), current_user.role.value, current_user.token_version, tenant_id_str
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/auth.py
git commit -m "feat: pass tenant_id when creating JWT tokens"
```

---

## Task 7: Update main.py — Tenant-Aware Startup

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Update admin user creation in lifespan**

The admin user created at startup needs a `tenant_id`. Update `main.py` lifespan (around line 42-60):

```python
    # 3. Ensure default tenant exists
    from app.models.tenant import Tenant
    db = SessionLocal()
    try:
        default_tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        if not default_tenant:
            print("🏢 Creating default tenant...")
            default_tenant = Tenant(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                name="Default",
                slug="default",
                is_active=True,
                mode="single",
            )
            db.add(default_tenant)
            db.commit()
            print("✅ Default tenant created")

        # 4. Create admin user if it doesn't exist
        admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not admin:
            print(f"👤 Creating admin user: {settings.ADMIN_USERNAME}")
            admin = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                password_hash=auth_service.hash_password(settings.ADMIN_PASSWORD),
                first_name=settings.ADMIN_FIRST_NAME,
                last_name=settings.ADMIN_LAST_NAME,
                role=UserRole.ADMIN,
                weekly_hours=40.0,
                vacation_days=30,
                is_active=True,
                tenant_id=default_tenant.id,
            )
            db.add(admin)
            db.commit()
            print(f"✅ Admin user created")
        else:
            print(f"✅ Admin user already exists: {settings.ADMIN_USERNAME}")
```

Add `import uuid` at the top if not already present.

- [ ] **Step 2: Update holiday sync to be tenant-aware**

The holiday sync in lifespan (around line 87-95) queries `PublicHoliday` which now has `tenant_id`. Since RLS is not active during startup (no `app.tenant_id` set), this works as-is. But new holidays created by `sync_current_and_next_year` need a `tenant_id`. This requires updating the holiday_service — but that's a service-level change. For now, add a `SET LOCAL` before the holiday sync:

```python
    # 5. Sync public holidays for current and next year
    print("📅 Syncing public holidays...")
    db = SessionLocal()
    try:
        # Set tenant context for holiday sync (all tenants if superadmin-style)
        db.execute(text("SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000001'"))
        state = holiday_service.get_holiday_state(db)
        result = holiday_service.sync_current_and_next_year(db, state=state)
        print(f"✅ Holidays synced for {result['state']}: {result['current_year']}({result['current_count']}), "
              f"{result['next_year']}({result['next_count']})")
    finally:
        db.close()
```

Note: `holiday_service.sync_current_and_next_year` will also need to set `tenant_id` when creating new holidays. Check and update in Task 8.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: tenant-aware startup — default tenant + admin user"
```

---

## Task 8: Update Holiday Service — Tenant-Aware Holiday Sync

**Files:**
- Modify: `backend/app/services/holiday_service.py` (needs reading first)

- [ ] **Step 1: Read the holiday service**

Read `backend/app/services/holiday_service.py` to understand how holidays are created.

- [ ] **Step 2: Update holiday creation to include tenant_id**

Wherever `PublicHoliday(...)` is created, add `tenant_id` parameter. The tenant_id should come from:
- A parameter passed to the sync function, OR
- The current `app.tenant_id` session setting

The simplest approach: add a `tenant_id` parameter to `sync_current_and_next_year` and pass it through. The caller in `main.py` passes the default tenant ID.

- [ ] **Step 3: Run existing holiday tests**

Run: `cd backend && python -m pytest tests/test_holiday_service.py -v`
Expected: Tests may need updating to pass `tenant_id`.

- [ ] **Step 4: Fix any failing tests**

Update test fixtures to include `tenant_id` where needed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/holiday_service.py backend/tests/test_holiday_service.py
git commit -m "feat: tenant-aware holiday sync"
```

---

## Task 9: Add RLS Policies to Migration

**Files:**
- Modify: `backend/alembic/versions/2026_03_25_2000-027_add_multi_tenant.py`

- [ ] **Step 1: Add RLS setup to the upgrade function**

Append to the `upgrade()` function in migration 027, after the constraint changes:

```python
    # 6. Enable RLS on all tables with tenant_id
    all_tables = _NOT_NULL_TABLES + ['users', 'system_settings']
    for table in all_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # 7. Create RLS policies — standard tables (NOT NULL tenant_id)
    for table in _NOT_NULL_TABLES:
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
            )
            WITH CHECK (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
            )
        """)

    # 8. Create RLS policies — nullable tenant_id tables (users, system_settings)
    #    These also show rows where tenant_id IS NULL (superadmin / global settings)
    for table in ['users', 'system_settings']:
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
                OR tenant_id IS NULL
            )
            WITH CHECK (
                current_setting('app.tenant_id', true) IS NULL
                OR tenant_id = current_setting('app.tenant_id')::uuid
                OR tenant_id IS NULL
            )
        """)
```

- [ ] **Step 2: Add RLS teardown to the downgrade function**

Prepend to `downgrade()`, before the constraint reversals:

```python
    # Remove RLS policies and disable RLS
    all_tables = _NOT_NULL_TABLES + ['users', 'system_settings']
    for table in all_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/2026_03_25_2000-027_add_multi_tenant.py
git commit -m "feat: add RLS policies to migration 027"
```

---

## Task 10: Update Test Conftest — Tenant Fixtures

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Update conftest.py with tenant fixtures**

The existing tests use SQLite which doesn't support RLS. For model-level tests, we add a default tenant fixture. RLS-specific tests (Task 11) will use PostgreSQL.

Update `backend/tests/conftest.py`:

```python
import pytest
import uuid
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, UserRole
from app.models.tenant import Tenant
from app.services import auth_service


# Test database URL
TEST_DATABASE_URL = "sqlite:///./test.db"

# Create test engine
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fixed UUID for default test tenant
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def default_tenant(db):
    """Create the default tenant for tests."""
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Test Tenant",
        slug="test",
        is_active=True,
        mode="single",
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.fixture(scope="function")
def test_user(db, default_tenant):
    """Create a test employee user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=auth_service.hash_password("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=default_tenant.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_admin(db, default_tenant):
    """Create a test admin user."""
    admin = User(
        username="adminuser",
        email="admin@example.com",
        password_hash=auth_service.hash_password("adminpassword123"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=default_tenant.id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@pytest.fixture(scope="function")
def public_holiday(db, default_tenant):
    """Ein Feiertag (Neujahr 2026) für Tests."""
    from app.models.public_holiday import PublicHoliday
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
        tenant_id=default_tenant.id,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@pytest.fixture(scope="function")
def working_hours_change(db, test_user, default_tenant):
    """Historische Arbeitsstunden-Änderung (20h ab 2026-01-01) für test_user."""
    from app.models import WorkingHoursChange
    change = WorkingHoursChange(
        user_id=test_user.id,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
        tenant_id=default_tenant.id,
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change
```

- [ ] **Step 2: Run existing tests to verify they still pass**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All existing tests pass (with updated fixtures).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "feat: add tenant fixtures to test conftest"
```

---

## Task 11: Write RLS Isolation Tests

**Files:**
- Create: `backend/tests/test_tenant_rls.py`

These tests require PostgreSQL (SQLite doesn't support RLS). They use the Docker PostgreSQL instance.

- [ ] **Step 1: Write RLS test file**

```python
"""
RLS isolation tests — require a running PostgreSQL instance.
Run with: pytest tests/test_tenant_rls.py -v

These tests verify that Row-Level Security policies correctly isolate
tenant data. They create two tenants and verify cross-tenant access
is blocked at the DB level.
"""
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.time_entry import TimeEntry
from app.models.absence import Absence, AbsenceType
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import auth_service
from datetime import date, time

# Use the Docker PostgreSQL — same as docker-compose.yml
PG_URL = "postgresql://postgres:postgres@localhost:5432/praxiszeit_test"

TENANT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture(scope="module")
def pg_engine():
    """Create PostgreSQL engine for RLS tests. Creates/drops test DB."""
    # Connect to default 'postgres' DB to create test DB
    admin_engine = create_engine("postgresql://postgres:postgres@localhost:5432/postgres")
    with admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("DROP DATABASE IF EXISTS praxiszeit_test"))
        conn.execute(text("CREATE DATABASE praxiszeit_test"))
    admin_engine.dispose()

    engine = create_engine(PG_URL)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Run RLS setup (same SQL as migration 027)
    with engine.connect() as conn:
        tables_not_null = [
            'time_entries', 'absences', 'vacation_requests', 'change_requests',
            'time_entry_audit_logs', 'working_hours_changes', 'year_carryovers',
            'public_holidays', 'company_closures', 'error_logs',
        ]
        tables_nullable = ['users', 'system_settings']

        for table in tables_not_null + tables_nullable:
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

        for table in tables_not_null:
            conn.execute(text(f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (
                    current_setting('app.tenant_id', true) IS NULL
                    OR tenant_id = current_setting('app.tenant_id')::uuid
                )
                WITH CHECK (
                    current_setting('app.tenant_id', true) IS NULL
                    OR tenant_id = current_setting('app.tenant_id')::uuid
                )
            """))

        for table in tables_nullable:
            conn.execute(text(f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (
                    current_setting('app.tenant_id', true) IS NULL
                    OR tenant_id = current_setting('app.tenant_id')::uuid
                    OR tenant_id IS NULL
                )
                WITH CHECK (
                    current_setting('app.tenant_id', true) IS NULL
                    OR tenant_id = current_setting('app.tenant_id')::uuid
                    OR tenant_id IS NULL
                )
            """))

        # Create a non-superuser role for the app (RLS doesn't apply to superusers)
        conn.execute(text("CREATE ROLE app_user LOGIN PASSWORD 'app_user'"))
        conn.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO app_user"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO app_user"))
        conn.commit()

    yield engine

    engine.dispose()
    # Cleanup
    admin_engine = create_engine("postgresql://postgres:postgres@localhost:5432/postgres")
    with admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("DROP DATABASE IF EXISTS praxiszeit_test"))
    admin_engine.dispose()


@pytest.fixture(scope="module")
def app_engine(pg_engine):
    """Engine using the non-superuser role (RLS enforced)."""
    return create_engine("postgresql://app_user:app_user@localhost:5432/praxiszeit_test")


@pytest.fixture(scope="module")
def seed_data(pg_engine):
    """Seed two tenants with users and data."""
    Session = sessionmaker(bind=pg_engine)
    db = Session()

    # Create tenants
    tenant_a = Tenant(id=TENANT_A_ID, name="Praxis A", slug="praxis-a")
    tenant_b = Tenant(id=TENANT_B_ID, name="Praxis B", slug="praxis-b")
    db.add_all([tenant_a, tenant_b])
    db.commit()

    # Create users
    user_a = User(
        username="user_a", email="a@test.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="User", last_name="A", role=UserRole.EMPLOYEE,
        weekly_hours=40, vacation_days=30, tenant_id=TENANT_A_ID,
    )
    user_b = User(
        username="user_b", email="b@test.com",
        password_hash=auth_service.hash_password("test123"),
        first_name="User", last_name="B", role=UserRole.EMPLOYEE,
        weekly_hours=40, vacation_days=30, tenant_id=TENANT_B_ID,
    )
    db.add_all([user_a, user_b])
    db.commit()

    # Create time entries
    te_a = TimeEntry(
        user_id=user_a.id, tenant_id=TENANT_A_ID,
        date=date(2026, 3, 25), start_time=time(8, 0), end_time=time(16, 0),
    )
    te_b = TimeEntry(
        user_id=user_b.id, tenant_id=TENANT_B_ID,
        date=date(2026, 3, 25), start_time=time(9, 0), end_time=time(17, 0),
    )
    db.add_all([te_a, te_b])

    # Create holidays
    holiday_a = PublicHoliday(
        date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=TENANT_A_ID,
    )
    holiday_b = PublicHoliday(
        date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=TENANT_B_ID,
    )
    db.add_all([holiday_a, holiday_b])

    # Global system setting (tenant_id = NULL)
    global_setting = SystemSetting(key="tenant_mode", value="multi", tenant_id=None)
    # Tenant-specific setting
    setting_a = SystemSetting(key="holiday_state_a", value="Bayern", tenant_id=TENANT_A_ID)
    setting_b = SystemSetting(key="holiday_state_b", value="NRW", tenant_id=TENANT_B_ID)
    db.add_all([global_setting, setting_a, setting_b])

    db.commit()
    db.close()

    return {"user_a_id": user_a.id, "user_b_id": user_b.id}


class TestRLSTenantIsolation:
    """Test that RLS policies enforce tenant isolation."""

    def _session_with_tenant(self, app_engine, tenant_id):
        """Create a session with tenant context set."""
        Session = sessionmaker(bind=app_engine)
        db = Session()
        db.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        return db

    def test_tenant_a_sees_only_own_users(self, app_engine, seed_data):
        db = self._session_with_tenant(app_engine, TENANT_A_ID)
        users = db.query(User).all()
        assert len(users) == 1
        assert users[0].username == "user_a"
        db.close()

    def test_tenant_b_sees_only_own_users(self, app_engine, seed_data):
        db = self._session_with_tenant(app_engine, TENANT_B_ID)
        users = db.query(User).all()
        assert len(users) == 1
        assert users[0].username == "user_b"
        db.close()

    def test_tenant_a_sees_only_own_time_entries(self, app_engine, seed_data):
        db = self._session_with_tenant(app_engine, TENANT_A_ID)
        entries = db.query(TimeEntry).all()
        assert len(entries) == 1
        assert entries[0].start_time == time(8, 0)
        db.close()

    def test_tenant_b_sees_only_own_time_entries(self, app_engine, seed_data):
        db = self._session_with_tenant(app_engine, TENANT_B_ID)
        entries = db.query(TimeEntry).all()
        assert len(entries) == 1
        assert entries[0].start_time == time(9, 0)
        db.close()

    def test_tenant_a_sees_only_own_holidays(self, app_engine, seed_data):
        db = self._session_with_tenant(app_engine, TENANT_A_ID)
        holidays = db.query(PublicHoliday).all()
        assert len(holidays) == 1
        db.close()

    def test_system_settings_global_visible_to_all(self, app_engine, seed_data):
        """Global settings (tenant_id=NULL) should be visible to any tenant."""
        db = self._session_with_tenant(app_engine, TENANT_A_ID)
        settings = db.query(SystemSetting).all()
        keys = {s.key for s in settings}
        assert "tenant_mode" in keys  # global
        assert "holiday_state_a" in keys  # own
        assert "holiday_state_b" not in keys  # other tenant
        db.close()

    def test_superadmin_no_tenant_context_sees_all(self, app_engine, seed_data):
        """Without app.tenant_id set, all rows should be visible (superadmin)."""
        Session = sessionmaker(bind=app_engine)
        db = Session()
        # Don't set app.tenant_id
        users = db.query(User).all()
        assert len(users) == 2
        entries = db.query(TimeEntry).all()
        assert len(entries) == 2
        db.close()
```

- [ ] **Step 2: Run RLS tests (requires Docker PostgreSQL running)**

Run: `cd backend && python -m pytest tests/test_tenant_rls.py -v`
Expected: All tests pass (or skip if no PG available).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_tenant_rls.py
git commit -m "test: add RLS tenant isolation tests"
```

---

## Task 12: Write Migration Integrity Tests

**Files:**
- Create: `backend/tests/test_tenant_migration.py`

- [ ] **Step 1: Write migration test file**

```python
"""
Migration integrity tests — verify migration 027 runs cleanly
against a copy of the production DB.

Run with: pytest tests/test_tenant_migration.py -v
Requires: PostgreSQL running, prod DB dump loaded into praxiszeit_migration_test
"""
import pytest
from sqlalchemy import create_engine, text, inspect
from alembic.config import Config
from alembic import command

PG_URL = "postgresql://postgres:postgres@localhost:5432/praxiszeit_migration_test"


@pytest.fixture(scope="module")
def migration_engine():
    """Engine for migration testing. Assumes DB exists with prod data loaded."""
    admin_engine = create_engine("postgresql://postgres:postgres@localhost:5432/postgres")
    with admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        # Drop and recreate to start fresh
        conn.execute(text("DROP DATABASE IF EXISTS praxiszeit_migration_test"))
        conn.execute(text("CREATE DATABASE praxiszeit_migration_test"))
    admin_engine.dispose()

    engine = create_engine(PG_URL)
    yield engine
    engine.dispose()


def _run_alembic(url, target):
    """Run alembic upgrade/downgrade to target revision."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    if target == "head":
        command.upgrade(alembic_cfg, "head")
    else:
        command.downgrade(alembic_cfg, target)


class TestMigrationIntegrity:
    """Tests that migration 027 runs correctly."""

    def test_upgrade_creates_tenants_table(self, migration_engine):
        """After upgrade, tenants table should exist."""
        _run_alembic(PG_URL, "head")
        inspector = inspect(migration_engine)
        assert "tenants" in inspector.get_table_names()

    def test_default_tenant_exists(self, migration_engine):
        """Default tenant should be created."""
        with migration_engine.connect() as conn:
            result = conn.execute(text("SELECT name, slug, mode FROM tenants WHERE slug = 'default'"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Default"
            assert row[2] == "single"

    def test_all_tables_have_tenant_id(self, migration_engine):
        """All 12 tables should have a tenant_id column."""
        tables = [
            'users', 'time_entries', 'absences', 'vacation_requests',
            'change_requests', 'time_entry_audit_logs', 'working_hours_changes',
            'year_carryovers', 'public_holidays', 'company_closures',
            'error_logs', 'system_settings',
        ]
        inspector = inspect(migration_engine)
        for table in tables:
            columns = {c['name'] for c in inspector.get_columns(table)}
            assert 'tenant_id' in columns, f"tenant_id missing from {table}"

    def test_all_rows_have_default_tenant(self, migration_engine):
        """All existing rows should be assigned to default tenant."""
        default_id = "00000000-0000-0000-0000-000000000001"
        tables_not_null = [
            'time_entries', 'absences', 'vacation_requests', 'change_requests',
            'time_entry_audit_logs', 'working_hours_changes', 'year_carryovers',
            'public_holidays', 'company_closures', 'error_logs',
        ]
        with migration_engine.connect() as conn:
            for table in tables_not_null:
                result = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id != '{default_id}'"
                ))
                count = result.scalar()
                assert count == 0, f"{table} has {count} rows without default tenant"

            # users + system_settings: all should have default tenant
            for table in ['users', 'system_settings']:
                result = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id != '{default_id}' AND tenant_id IS NOT NULL"
                ))
                count = result.scalar()
                assert count == 0, f"{table} has {count} rows with unexpected tenant"

    def test_rls_enabled_on_all_tables(self, migration_engine):
        """RLS should be enabled on all tenant tables."""
        with migration_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname IN ("
                "'users','time_entries','absences','vacation_requests',"
                "'change_requests','time_entry_audit_logs','working_hours_changes',"
                "'year_carryovers','public_holidays','company_closures',"
                "'error_logs','system_settings')"
            ))
            for row in result:
                assert row[1] is True, f"RLS not enabled on {row[0]}"
                assert row[2] is True, f"RLS not forced on {row[0]}"

    def test_unique_constraints_updated(self, migration_engine):
        """New tenant-scoped unique constraints should exist."""
        inspector = inspect(migration_engine)

        # Check users has tenant_username constraint
        user_constraints = inspector.get_unique_constraints('users')
        constraint_names = {c['name'] for c in user_constraints}
        assert 'uq_tenant_username' in constraint_names

        # Check time_entries
        te_constraints = inspector.get_unique_constraints('time_entries')
        te_names = {c['name'] for c in te_constraints}
        assert 'uq_tenant_user_date_start' in te_names

    def test_downgrade_restores_schema(self, migration_engine):
        """Downgrade should restore original schema."""
        _run_alembic(PG_URL, "026_add_year_carryovers")

        inspector = inspect(migration_engine)
        assert "tenants" not in inspector.get_table_names()

        # tenant_id should be gone from users
        user_columns = {c['name'] for c in inspector.get_columns('users')}
        assert 'tenant_id' not in user_columns

        # Original constraints restored
        user_constraints = inspector.get_unique_constraints('users')
        constraint_names = {c['name'] for c in user_constraints}
        assert 'users_username_key' in constraint_names

        # Upgrade again for other tests
        _run_alembic(PG_URL, "head")
```

- [ ] **Step 2: Run migration tests**

Run: `cd backend && python -m pytest tests/test_tenant_migration.py -v`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_tenant_migration.py
git commit -m "test: add migration integrity tests for 027"
```

---

## Task 13: Update Remaining Services That Create Records

**Files:**
- Multiple service and router files that INSERT new records need `tenant_id`

- [ ] **Step 1: Search for all places that create model instances**

Search across all routers and services for patterns like:
- `TimeEntry(` — needs `tenant_id`
- `Absence(` — needs `tenant_id`
- `PublicHoliday(` — needs `tenant_id`
- `CompanyClosure(` — needs `tenant_id`
- `ChangeRequest(` — needs `tenant_id`
- `VacationRequest(` — needs `tenant_id`
- `TimeEntryAuditLog(` — needs `tenant_id`
- `WorkingHoursChange(` — needs `tenant_id`
- `YearCarryover(` — needs `tenant_id`
- `ErrorLog(` — needs `tenant_id`
- `SystemSetting(` — needs `tenant_id`
- `User(` — needs `tenant_id`

For each: add `tenant_id=current_user.tenant_id` (or `request.state.tenant_id`).

This is a broad search-and-update task. The pattern is the same everywhere:
```python
# Before:
entry = TimeEntry(user_id=current_user.id, date=data.date, ...)

# After:
entry = TimeEntry(user_id=current_user.id, tenant_id=current_user.tenant_id, date=data.date, ...)
```

- [ ] **Step 2: Update each router file**

For each router, add `tenant_id=current_user.tenant_id` to every model constructor. Key files:
- `routers/time_entries.py` — TimeEntry creation
- `routers/absences.py` — Absence creation
- `routers/admin.py` — User, TimeEntry, Absence creation
- `routers/change_requests.py` — ChangeRequest creation
- `routers/vacation_requests.py` — VacationRequest creation
- `routers/company_closures.py` — CompanyClosure creation
- `routers/import_xls.py` — bulk TimeEntry creation

For services:
- `services/error_log_service.py` — ErrorLog creation (may not have user context; use tenant_id from error context or NULL)

- [ ] **Step 3: Run all existing tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/ backend/app/services/
git commit -m "feat: pass tenant_id when creating all model instances"
```

---

## Task 14: Create Non-Superuser DB Role for App (RLS Enforcement)

RLS policies do NOT apply to PostgreSQL superusers. The current setup uses `postgres` (superuser) for the app. We need a separate `praxiszeit_app` role.

**Files:**
- Modify: `docker-compose.yml`
- Create: `backend/init-db-user.sql`

- [ ] **Step 1: Create init SQL script**

Create `backend/init-db-user.sql`:

```sql
-- Create app role (non-superuser) for RLS enforcement
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'praxiszeit_app') THEN
        CREATE ROLE praxiszeit_app LOGIN PASSWORD 'praxiszeit_app';
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE praxiszeit TO praxiszeit_app;
GRANT USAGE ON SCHEMA public TO praxiszeit_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO praxiszeit_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO praxiszeit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO praxiszeit_app;
```

- [ ] **Step 2: Mount init script in docker-compose.yml**

Add to the `db` service volumes:

```yaml
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/init-db-user.sql:/docker-entrypoint-initdb.d/init-db-user.sql
```

- [ ] **Step 3: Update backend DATABASE_URL**

In `docker-compose.yml`, change the backend's `DATABASE_URL` environment variable to use the non-superuser:

```yaml
DATABASE_URL=postgresql://praxiszeit_app:praxiszeit_app@db:5432/praxiszeit
```

Keep the original superuser URL for Alembic migrations (Dockerfile CMD or separate env var):

```yaml
DATABASE_URL_MIGRATIONS=postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/praxiszeit
```

- [ ] **Step 4: Update alembic to use migration URL**

In `backend/alembic/env.py`, prefer `DATABASE_URL_MIGRATIONS` over `DATABASE_URL`:

```python
import os
db_url = os.environ.get("DATABASE_URL_MIGRATIONS", settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", db_url)
```

- [ ] **Step 5: Commit**

```bash
git add backend/init-db-user.sql docker-compose.yml backend/alembic/env.py
git commit -m "feat: add non-superuser DB role for RLS enforcement"
```

---

## Task 15: Run Full Migration Against Prod DB Copy (Integration Test)

- [ ] **Step 1: Load prod DB dump into Docker PostgreSQL**

```bash
gunzip -k praxiszeit_20260325_194750.sql.gz
docker exec -i $(docker-compose ps -q db) psql -U postgres -d praxiszeit < praxiszeit_20260325_194750.sql
```

- [ ] **Step 2: Run migration**

```bash
docker-compose exec backend alembic upgrade head
```

Expected: Migration 027 runs without errors.

- [ ] **Step 3: Verify data integrity**

```bash
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import User
from app.models.tenant import Tenant
db = SessionLocal()
tenant = db.query(Tenant).first()
print(f'Tenant: {tenant.name} ({tenant.slug})')
users = db.query(User).all()
print(f'Users: {len(users)}')
for u in users:
    print(f'  {u.username} tenant_id={u.tenant_id}')
db.close()
"
```

- [ ] **Step 4: Verify login still works**

Open browser, go to `localhost`, login with existing credentials. Verify dashboard loads correctly.

- [ ] **Step 5: Run E2E tests**

```bash
cd e2e && npx playwright test
```

Expected: All 112 E2E tests pass.

---

## Task 16: Final Review and Branch Commit

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -v
```

- [ ] **Step 2: Run linting if available**

```bash
cd backend && python -m flake8 app/ --max-line-length=120 || true
```

- [ ] **Step 3: Review all changes**

```bash
git diff master --stat
```

Verify no unintended changes.

- [ ] **Step 4: Final commit if needed**

Any last fixes get committed with appropriate messages.
