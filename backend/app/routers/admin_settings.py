"""Admin sub-router: System Settings."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.models.system_setting import SystemSetting
from app.middleware.auth import require_admin
from app.routers.admin_helpers import SettingUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _get_setting(db: Session, key: str, default: str = "", tenant_id=None) -> str:
    """Retrieve a value from system_settings."""
    q = db.query(SystemSetting).filter(SystemSetting.key == key)
    if tenant_id is not None:
        q = q.filter(SystemSetting.tenant_id == tenant_id)
    s = q.first()
    return s.value if s else default


_ALLOWED_SETTINGS = {"vacation_approval_required", "holiday_state"}


@router.get("/settings")
def list_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all system settings."""
    rows = db.query(SystemSetting).filter(SystemSetting.tenant_id == current_user.tenant_id).all()
    return [{"key": r.key, "value": r.value, "description": r.description, "updated_at": r.updated_at} for r in rows]


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

    # Validate holiday_state against supported states
    if key == "holiday_state":
        if value not in holiday_service.SUPPORTED_STATES:
            raise HTTPException(status_code=400, detail=f"Ungültiges Bundesland: {value}")

    s = db.query(SystemSetting).filter(
        SystemSetting.key == key,
        SystemSetting.tenant_id == current_user.tenant_id
    ).first()
    if not s:
        s = SystemSetting(key=key, value=str(value), description=key, tenant_id=current_user.tenant_id)
        db.add(s)
    else:
        s.value = str(value)

    if key == "holiday_state":
        # Atomarer Delete + Sync: alles in einer Transaktion (C2, I5)
        try:
            holiday_service.delete_all_holidays(db, tenant_id=current_user.tenant_id)   # kein commit
            holiday_service.sync_current_and_next_year(db, state=str(value), tenant_id=current_user.tenant_id)  # commitet am Ende
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Einstellung gespeichert, aber Feiertage konnten nicht synchronisiert werden: {e}"
            )
    else:
        db.commit()

    db.refresh(s)
    return {"key": s.key, "value": s.value, "updated_at": s.updated_at}
