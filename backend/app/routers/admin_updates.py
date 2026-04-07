"""Admin sub-router: Update Management (native installations only)."""

from fastapi import APIRouter, Depends, HTTPException
from app.models import User
from app.middleware.auth import require_admin
from app.config import settings
from app.core.updater import check_for_updates, get_update_status, get_app_version
from app.core.license import get_current_license

router = APIRouter(
    prefix="/api/admin/updates",
    tags=["admin-updates"],
    dependencies=[Depends(require_admin)],
)


@router.get("/status")
def update_status(current_user: User = Depends(require_admin)):
    """Get current update status and version info."""
    return get_update_status()


@router.post("/check")
def trigger_update_check(current_user: User = Depends(require_admin)):
    """Manually trigger an update check against the update server."""
    if not settings.UPDATE_SERVER_URL:
        raise HTTPException(
            status_code=404,
            detail="Update-Server nicht konfiguriert (UPDATE_SERVER_URL).",
        )

    license_info = get_current_license()
    license_id = license_info.customer_id if license_info else ""

    update = check_for_updates(settings.UPDATE_SERVER_URL, license_id)

    if update:
        return {
            "update_available": True,
            "update": update.to_dict(),
        }
    return {
        "update_available": False,
        "current_version": get_app_version(),
        "message": "Keine Updates verfuegbar.",
    }
