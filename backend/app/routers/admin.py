"""Admin router coordinator — includes all admin sub-routers."""

from fastapi import APIRouter
from app.routers.admin_users import router as users_router
from app.routers.admin_change_requests import router as change_requests_router
from app.routers.admin_time_entries import router as time_entries_router
from app.routers.admin_settings import router as settings_router
from app.routers.admin_vacations import router as vacations_router
from app.routers.admin_carryovers import router as carryovers_router

# Re-export a combined router for backward compatibility with main.py
router = APIRouter()
router.include_router(users_router)
router.include_router(change_requests_router)
router.include_router(time_entries_router)
router.include_router(settings_router)
router.include_router(vacations_router)
router.include_router(carryovers_router)
