"""Zentrale Lese-Helfer für ``system_settings`` (#219 Dedup).

Vorher lag dieselbe Query 3× vor (``vacation_requests.get_setting``,
``admin_settings._get_setting`` [tot], ``backup_service._get_setting``) plus
diverse Inline-Reads. Diese Helfer bündeln die Lese-Logik; Schreiber bleiben
bei den jeweiligen Routern/Services.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting


def get_setting(db: Session, key: str, tenant_id=None, default: Optional[str] = None) -> Optional[str]:
    """Lies den Roh-Wert eines ``system_settings``-Eintrags.

    ``tenant_id=None`` filtert NICHT nach Tenant (RLS scoped ohnehin); ein
    übergebenes ``tenant_id`` filtert zusätzlich explizit (F-026 belt-and-
    suspenders). Fehlt der Schlüssel, wird ``default`` zurückgegeben.
    """
    q = db.query(SystemSetting).filter(SystemSetting.key == key)
    if tenant_id is not None:
        q = q.filter(SystemSetting.tenant_id == tenant_id)
    s = q.first()
    return s.value if s else default


def get_bool_setting(db: Session, key: str, tenant_id=None, default: bool = False) -> bool:
    """Boolean-Setting (``'true'``/``'false'``, case-insensitive). Fehlt der
    Schlüssel, wird ``default`` zurückgegeben."""
    raw = get_setting(db, key, tenant_id=tenant_id, default=None)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def get_int_setting(db: Session, key: str, tenant_id=None, default: int = 0) -> int:
    """#376: int-Wert eines Settings; Default bei fehlend/nicht-parsebar."""
    raw = get_setting(db, key, tenant_id=tenant_id, default=None)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


SHOW_YEAR_END_OVERTIME_EMPLOYEE_DASHBOARD = (
    "show_year_end_overtime_employee_dashboard"
)

SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD = (
    "show_year_end_overtime_admin_dashboard"
)

