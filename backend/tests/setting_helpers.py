"""Gemeinsamer Baustein für Suiten, die eine Mandanten-Einstellung anlegen."""
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID


def set_setting(db, key: str, value: str, tenant_id=DEFAULT_TENANT_ID):
    db.add(SystemSetting(key=key, value=value, description=key, tenant_id=tenant_id))
    db.commit()
