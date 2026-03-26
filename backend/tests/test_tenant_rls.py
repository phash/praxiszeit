"""
RLS Tenant Isolation Integration Tests

These tests verify that PostgreSQL Row-Level Security policies correctly
isolate tenant data. They run against the real Docker PostgreSQL instance.

Requirements:
    - Docker stack running: docker compose up -d
    - Migration 027 applied (multi-tenant RLS policies exist)

Run with:
    docker compose exec backend pytest tests/test_tenant_rls.py -v

The tests create two ephemeral tenants (TENANT_A, TENANT_B) with associated
users, time_entries, absences, public_holidays, and system_settings.  All
test data is cleaned up after the module finishes, leaving the production
database untouched.
"""
import uuid
import pytest
from datetime import date, time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Connection strings (inside Docker network, host = "db")
# ---------------------------------------------------------------------------
APP_DB_URL = "postgresql://praxiszeit_app:praxiszeit_app@db:5432/praxiszeit"
ADMIN_DB_URL = "postgresql://praxiszeit:praxiszeit_dev_2026@db:5432/praxiszeit"

# ---------------------------------------------------------------------------
# Deterministic UUIDs for test tenants -- will never collide with real data
# ---------------------------------------------------------------------------
TENANT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

# UUIDs for test users
USER_A1_ID = uuid.UUID("aa000000-0000-0000-0000-000000000001")
USER_A2_ID = uuid.UUID("aa000000-0000-0000-0000-000000000002")
USER_B1_ID = uuid.UUID("bb000000-0000-0000-0000-000000000001")

# UUIDs for other test entities
TIME_ENTRY_A_ID = uuid.UUID("aa100000-0000-0000-0000-000000000001")
TIME_ENTRY_B_ID = uuid.UUID("bb100000-0000-0000-0000-000000000001")
ABSENCE_A_ID = uuid.UUID("aa200000-0000-0000-0000-000000000001")
ABSENCE_B_ID = uuid.UUID("bb200000-0000-0000-0000-000000000001")
HOLIDAY_A_ID = uuid.UUID("aa300000-0000-0000-0000-000000000001")
HOLIDAY_B_ID = uuid.UUID("bb300000-0000-0000-0000-000000000001")


# ===== Fixtures =============================================================

@pytest.fixture(scope="module")
def admin_engine():
    """Superuser engine -- bypasses RLS (table owner). Used for setup/teardown."""
    eng = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def app_engine():
    """App-user engine -- RLS enforced. Used for the actual tests."""
    eng = create_engine(APP_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def seed_data(admin_engine):
    """Create test tenants and associated data. Cleans up after module.

    Runs as superuser so RLS does not interfere with setup/teardown.
    The fixture uses raw SQL to avoid any ORM/session tenant-context issues.
    """
    conn = admin_engine.connect()

    # ---- Pre-cleanup: remove any stale data from previous failed runs ----
    _test_tids = {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)}
    conn.execute(text("DELETE FROM system_settings WHERE key LIKE 'rls_test_%'"))
    conn.execute(text("DELETE FROM time_entries WHERE tenant_id IN (:a, :b)"), _test_tids)
    conn.execute(text("DELETE FROM absences WHERE tenant_id IN (:a, :b)"), _test_tids)
    conn.execute(text("DELETE FROM public_holidays WHERE tenant_id IN (:a, :b)"), _test_tids)
    conn.execute(text("DELETE FROM users WHERE tenant_id IN (:a, :b)"), _test_tids)
    conn.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), _test_tids)

    # ---- Create tenants ----
    conn.execute(text("""
        INSERT INTO tenants (id, name, slug, is_active, mode)
        VALUES (:id, :name, :slug, true, 'multi')
    """), {"id": str(TENANT_A_ID), "name": "Test Tenant A", "slug": "test-tenant-a"})

    conn.execute(text("""
        INSERT INTO tenants (id, name, slug, is_active, mode)
        VALUES (:id, :name, :slug, true, 'multi')
    """), {"id": str(TENANT_B_ID), "name": "Test Tenant B", "slug": "test-tenant-b"})

    # ---- Create users ----
    _insert_user = text("""
        INSERT INTO users (id, tenant_id, username, email, password_hash,
                           first_name, last_name, role, weekly_hours,
                           vacation_days, work_days_per_week, is_active)
        VALUES (:id, :tid, :username, :email, 'not-a-real-hash',
                :first, :last, :role, 40, 30, 5, true)
    """)
    conn.execute(_insert_user, {
        "id": str(USER_A1_ID), "tid": str(TENANT_A_ID),
        "username": "rls_test_a1", "email": "a1@test-rls.local",
        "first": "Alice", "last": "Alpha", "role": "EMPLOYEE",
    })
    conn.execute(_insert_user, {
        "id": str(USER_A2_ID), "tid": str(TENANT_A_ID),
        "username": "rls_test_a2", "email": "a2@test-rls.local",
        "first": "Adam", "last": "Alpha", "role": "ADMIN",
    })
    conn.execute(_insert_user, {
        "id": str(USER_B1_ID), "tid": str(TENANT_B_ID),
        "username": "rls_test_b1", "email": "b1@test-rls.local",
        "first": "Bob", "last": "Beta", "role": "EMPLOYEE",
    })

    # ---- Create time_entries ----
    _insert_te = text("""
        INSERT INTO time_entries (id, tenant_id, user_id, date, start_time, end_time, break_minutes)
        VALUES (:id, :tid, :uid, :dt, :st, :et, :brk)
    """)
    conn.execute(_insert_te, {
        "id": str(TIME_ENTRY_A_ID), "tid": str(TENANT_A_ID), "uid": str(USER_A1_ID),
        "dt": "2099-01-15", "st": "08:00", "et": "16:30", "brk": 30,
    })
    conn.execute(_insert_te, {
        "id": str(TIME_ENTRY_B_ID), "tid": str(TENANT_B_ID), "uid": str(USER_B1_ID),
        "dt": "2099-01-15", "st": "09:00", "et": "17:00", "brk": 30,
    })

    # ---- Create absences ----
    _insert_abs = text("""
        INSERT INTO absences (id, tenant_id, user_id, date, type, hours)
        VALUES (:id, :tid, :uid, :dt, :typ, :hrs)
    """)
    conn.execute(_insert_abs, {
        "id": str(ABSENCE_A_ID), "tid": str(TENANT_A_ID), "uid": str(USER_A1_ID),
        "dt": "2099-02-01", "typ": "VACATION", "hrs": 8,
    })
    conn.execute(_insert_abs, {
        "id": str(ABSENCE_B_ID), "tid": str(TENANT_B_ID), "uid": str(USER_B1_ID),
        "dt": "2099-02-01", "typ": "SICK", "hrs": 8,
    })

    # ---- Create public_holidays ----
    _insert_ph = text("""
        INSERT INTO public_holidays (id, tenant_id, date, name, year)
        VALUES (:id, :tid, :dt, :name, :yr)
    """)
    conn.execute(_insert_ph, {
        "id": str(HOLIDAY_A_ID), "tid": str(TENANT_A_ID),
        "dt": "2099-12-25", "name": "RLS Test Christmas A", "yr": 2099,
    })
    conn.execute(_insert_ph, {
        "id": str(HOLIDAY_B_ID), "tid": str(TENANT_B_ID),
        "dt": "2099-12-25", "name": "RLS Test Christmas B", "yr": 2099,
    })

    # ---- Create system_settings ----
    # Global setting (tenant_id IS NULL)
    conn.execute(text("""
        INSERT INTO system_settings (key, tenant_id, value, description)
        VALUES (:key, NULL, :val, :desc)
    """), {"key": "rls_test_global", "val": "global_value", "desc": "RLS test global setting"})

    # Tenant A setting
    conn.execute(text("""
        INSERT INTO system_settings (key, tenant_id, value, description)
        VALUES (:key, :tid, :val, :desc)
    """), {
        "key": "rls_test_setting_a", "tid": str(TENANT_A_ID),
        "val": "value_a", "desc": "RLS test setting for Tenant A",
    })

    # Tenant B setting
    conn.execute(text("""
        INSERT INTO system_settings (key, tenant_id, value, description)
        VALUES (:key, :tid, :val, :desc)
    """), {
        "key": "rls_test_setting_b", "tid": str(TENANT_B_ID),
        "val": "value_b", "desc": "RLS test setting for Tenant B",
    })

    yield  # ---- run tests ----

    # ---- Teardown: delete everything in reverse dependency order ----
    conn.execute(text("DELETE FROM system_settings WHERE key LIKE 'rls_test_%'"))
    conn.execute(text(
        "DELETE FROM time_entries WHERE tenant_id IN (:a, :b)"
    ), {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)})
    conn.execute(text(
        "DELETE FROM absences WHERE tenant_id IN (:a, :b)"
    ), {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)})
    conn.execute(text(
        "DELETE FROM public_holidays WHERE tenant_id IN (:a, :b)"
    ), {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)})
    conn.execute(text(
        "DELETE FROM users WHERE tenant_id IN (:a, :b)"
    ), {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)})
    conn.execute(text(
        "DELETE FROM tenants WHERE id IN (:a, :b)"
    ), {"a": str(TENANT_A_ID), "b": str(TENANT_B_ID)})
    conn.close()


# Helper: create a new connection with SET LOCAL inside a transaction
def _tenant_session(app_engine, tenant_id):
    """Return a (connection, transaction) pair with tenant context set via SET LOCAL."""
    conn = app_engine.connect()
    trans = conn.begin()
    conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
    return conn, trans


def _superadmin_session(app_engine):
    """Return a (connection, transaction) pair with superadmin context."""
    conn = app_engine.connect()
    trans = conn.begin()
    conn.execute(text("SET LOCAL app.is_superadmin = 'true'"))
    return conn, trans


def _no_context_session(app_engine):
    """Return a (connection, transaction) pair with NO tenant/superadmin context."""
    conn = app_engine.connect()
    trans = conn.begin()
    return conn, trans


# ===== Tests: Tenant Isolation (core) =======================================

class TestTenantIsolation:
    """Verify that each tenant sees only its own data."""

    def test_tenant_a_sees_only_own_users(self, app_engine, seed_data):
        """1. Tenant A session sees only Tenant A users."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            rows = conn.execute(text(
                "SELECT id FROM users WHERE tenant_id = :tid"
            ), {"tid": str(TENANT_A_ID)}).fetchall()
            user_ids = {row[0] for row in rows}
            assert USER_A1_ID in user_ids
            assert USER_A2_ID in user_ids
            assert USER_B1_ID not in user_ids

            # Also verify no Tenant B users appear at all (even without WHERE)
            all_rows = conn.execute(text("SELECT id, tenant_id FROM users")).fetchall()
            visible_tenant_ids = {row[1] for row in all_rows}
            assert TENANT_B_ID not in visible_tenant_ids
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_b_sees_only_own_users(self, app_engine, seed_data):
        """2. Tenant B session sees only Tenant B users."""
        conn, trans = _tenant_session(app_engine, TENANT_B_ID)
        try:
            rows = conn.execute(text("SELECT id FROM users")).fetchall()
            user_ids = {row[0] for row in rows}
            assert USER_B1_ID in user_ids
            assert USER_A1_ID not in user_ids
            assert USER_A2_ID not in user_ids
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_a_sees_only_own_time_entries(self, app_engine, seed_data):
        """3. Tenant A session sees only own time_entries."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            rows = conn.execute(text("SELECT id FROM time_entries")).fetchall()
            te_ids = {row[0] for row in rows}
            assert TIME_ENTRY_A_ID in te_ids
            assert TIME_ENTRY_B_ID not in te_ids
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_b_sees_only_own_time_entries(self, app_engine, seed_data):
        """4. Tenant B session sees only own time_entries."""
        conn, trans = _tenant_session(app_engine, TENANT_B_ID)
        try:
            rows = conn.execute(text("SELECT id FROM time_entries")).fetchall()
            te_ids = {row[0] for row in rows}
            assert TIME_ENTRY_B_ID in te_ids
            assert TIME_ENTRY_A_ID not in te_ids
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_a_sees_only_own_absences(self, app_engine, seed_data):
        """5. Tenant A session sees only own absences."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            rows = conn.execute(text("SELECT id FROM absences")).fetchall()
            abs_ids = {row[0] for row in rows}
            assert ABSENCE_A_ID in abs_ids
            assert ABSENCE_B_ID not in abs_ids
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_a_sees_only_own_public_holidays(self, app_engine, seed_data):
        """6. Tenant A session sees only own public_holidays."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            rows = conn.execute(text("SELECT id FROM public_holidays")).fetchall()
            ph_ids = {row[0] for row in rows}
            assert HOLIDAY_A_ID in ph_ids
            assert HOLIDAY_B_ID not in ph_ids
        finally:
            trans.rollback()
            conn.close()


# ===== Tests: Cross-tenant write protection =================================

class TestCrossTenantWriteProtection:
    """Verify that RLS WITH CHECK prevents cross-tenant writes."""

    def test_tenant_a_cannot_insert_user_in_tenant_b(self, app_engine, seed_data):
        """7. Tenant A cannot INSERT a user with Tenant B's tenant_id.

        The WITH CHECK clause should raise a new_row_violates_row_level_security
        error (SQLSTATE 42501).
        """
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            with pytest.raises(Exception) as exc_info:
                conn.execute(text("""
                    INSERT INTO users (id, tenant_id, username, email, password_hash,
                                       first_name, last_name, role, weekly_hours,
                                       vacation_days, work_days_per_week, is_active)
                    VALUES (:id, :tid, 'rls_hacker', 'hacker@evil.local', 'x',
                            'Evil', 'Hacker', 'EMPLOYEE', 40, 30, 5, true)
                """), {"id": str(uuid.uuid4()), "tid": str(TENANT_B_ID)})
            # The error should mention row-level security policy violation
            error_msg = str(exc_info.value).lower()
            assert "row-level security" in error_msg or "policy" in error_msg or "permission" in error_msg
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_a_cannot_update_tenant_b_user(self, app_engine, seed_data):
        """8. Tenant A cannot UPDATE a Tenant B user's data.

        The UPDATE should affect 0 rows because the USING clause hides
        Tenant B rows from Tenant A entirely.
        """
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            result = conn.execute(text("""
                UPDATE users SET first_name = 'Hacked'
                WHERE id = :uid
            """), {"uid": str(USER_B1_ID)})
            assert result.rowcount == 0, (
                "Tenant A should not be able to update Tenant B's user "
                f"(rowcount={result.rowcount})"
            )
        finally:
            trans.rollback()
            conn.close()


# ===== Tests: Superadmin bypass =============================================

class TestSuperadminBypass:
    """Verify that is_superadmin flag allows cross-tenant access."""

    def test_superadmin_sees_all_users(self, app_engine, seed_data):
        """9. Session with app.is_superadmin = 'true' sees all tenants' users."""
        conn, trans = _superadmin_session(app_engine)
        try:
            rows = conn.execute(text("SELECT id, tenant_id FROM users")).fetchall()
            user_ids = {row[0] for row in rows}
            # Must see both tenants' test users
            assert USER_A1_ID in user_ids
            assert USER_A2_ID in user_ids
            assert USER_B1_ID in user_ids
        finally:
            trans.rollback()
            conn.close()

    def test_superadmin_sees_all_time_entries(self, app_engine, seed_data):
        """10. Session with app.is_superadmin = 'true' sees all time_entries."""
        conn, trans = _superadmin_session(app_engine)
        try:
            rows = conn.execute(text("SELECT id FROM time_entries")).fetchall()
            te_ids = {row[0] for row in rows}
            assert TIME_ENTRY_A_ID in te_ids
            assert TIME_ENTRY_B_ID in te_ids
        finally:
            trans.rollback()
            conn.close()


# ===== Tests: System Settings (nullable tenant_id) ==========================

class TestSystemSettingsIsolation:
    """Verify that system_settings with nullable tenant_id behaves correctly.

    The policy: tenant sees own settings + global (tenant_id IS NULL).
    """

    def test_tenant_a_sees_own_and_global_settings(self, app_engine, seed_data):
        """11. Tenant A sees own settings + global settings (tenant_id IS NULL)."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            rows = conn.execute(text(
                "SELECT key, tenant_id FROM system_settings WHERE key LIKE 'rls_test_%'"
            )).fetchall()
            keys = {row[0] for row in rows}
            # Should see its own setting
            assert "rls_test_setting_a" in keys
            # Should see global setting (tenant_id IS NULL)
            assert "rls_test_global" in keys
            # Should NOT see Tenant B's setting
            assert "rls_test_setting_b" not in keys
        finally:
            trans.rollback()
            conn.close()

    def test_tenant_a_does_not_see_tenant_b_settings(self, app_engine, seed_data):
        """12. Tenant A does NOT see Tenant B's settings."""
        conn, trans = _tenant_session(app_engine, TENANT_A_ID)
        try:
            row = conn.execute(text(
                "SELECT COUNT(*) FROM system_settings WHERE key = 'rls_test_setting_b'"
            )).scalar()
            assert row == 0, "Tenant A should not see Tenant B's system_settings"
        finally:
            trans.rollback()
            conn.close()


# ===== Tests: No context = no data ==========================================

class TestNoContextSecurity:
    """Verify that a session without any tenant/superadmin context sees nothing."""

    def test_no_context_sees_no_users(self, app_engine, seed_data):
        """13. Session WITHOUT any context set sees NO user rows.

        For the users table, the policy allows tenant_id IS NULL rows too,
        so this test checks that without context, only NULL-tenant users
        (if any) are visible -- certainly NOT our test tenant users.

        For NOT NULL tables (time_entries), no rows should be visible at all.
        """
        conn, trans = _no_context_session(app_engine)
        try:
            # Users table (nullable tenant_id): check our test users are NOT visible
            rows = conn.execute(text("SELECT id FROM users")).fetchall()
            user_ids = {row[0] for row in rows}
            assert USER_A1_ID not in user_ids, "Test user A1 should not be visible without context"
            assert USER_A2_ID not in user_ids, "Test user A2 should not be visible without context"
            assert USER_B1_ID not in user_ids, "Test user B1 should not be visible without context"

            # Time entries table (NOT NULL tenant_id): should see 0 rows
            # because NULLIF('', '')::uuid is NULL, which never matches NOT NULL tenant_id
            te_count = conn.execute(text("SELECT COUNT(*) FROM time_entries")).scalar()
            assert te_count == 0, (
                f"Expected 0 time_entries without context, got {te_count}"
            )

            # Absences (NOT NULL tenant_id): same logic
            abs_count = conn.execute(text("SELECT COUNT(*) FROM absences")).scalar()
            assert abs_count == 0, (
                f"Expected 0 absences without context, got {abs_count}"
            )
        finally:
            trans.rollback()
            conn.close()
