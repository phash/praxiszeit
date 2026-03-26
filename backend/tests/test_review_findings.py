"""Tests for review finding fixes."""
import uuid
import pytest
from datetime import date
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.public_holiday import PublicHoliday
from app.services.holiday_service import sync_holidays, delete_all_holidays
from tests.conftest import DEFAULT_TENANT_ID

TENANT_B_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class TestSystemSettingsMultiTenant:
    """C3: system_settings must support same key for different tenants."""

    def test_two_tenants_same_key(self, db, default_tenant):
        """Two tenants can each have their own 'holiday_state' setting."""
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.commit()

        s1 = SystemSetting(key="test_holiday_state", value="Bayern", tenant_id=DEFAULT_TENANT_ID)
        s2 = SystemSetting(key="test_holiday_state", value="Berlin", tenant_id=TENANT_B_ID)
        db.add(s1)
        db.add(s2)
        db.commit()

        result = db.query(SystemSetting).filter(
            SystemSetting.key == "test_holiday_state"
        ).all()
        assert len(result) == 2
        values = {str(r.tenant_id): r.value for r in result}
        assert values[str(DEFAULT_TENANT_ID)] == "Bayern"
        assert values[str(TENANT_B_ID)] == "Berlin"

        # Cleanup
        db.query(SystemSetting).filter(SystemSetting.key == "test_holiday_state").delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()


class TestHolidayServiceTenantIsolation:
    """M1/M2: holiday_service must filter by tenant_id."""

    def test_sync_holidays_does_not_see_other_tenant(self, db, default_tenant):
        """sync_holidays existing-check must filter by tenant_id."""
        h = PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026, tenant_id=DEFAULT_TENANT_ID)
        db.add(h)
        db.commit()

        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.commit()

        count = sync_holidays(db, 2026, "Bayern", tenant_id=TENANT_B_ID)
        db.commit()

        all_h = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 1, 1)).all()
        tenant_ids = {str(h.tenant_id) for h in all_h}
        assert str(DEFAULT_TENANT_ID) in tenant_ids
        assert str(TENANT_B_ID) in tenant_ids

        # Cleanup
        db.query(PublicHoliday).filter(PublicHoliday.tenant_id.in_([DEFAULT_TENANT_ID, TENANT_B_ID])).delete()
        db.query(Tenant).filter(Tenant.id == TENANT_B_ID).delete()
        db.commit()

    def test_delete_all_holidays_scoped_to_tenant(self, db, default_tenant):
        """delete_all_holidays with tenant_id must only delete that tenant's holidays."""
        tenant_b = Tenant(id=TENANT_B_ID, name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        h1 = PublicHoliday(date=date(2026, 12, 25), name="Weihnachten", year=2026, tenant_id=DEFAULT_TENANT_ID)
        h2 = PublicHoliday(date=date(2026, 12, 25), name="Weihnachten", year=2026, tenant_id=TENANT_B_ID)
        db.add_all([tenant_b, h1, h2])
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
