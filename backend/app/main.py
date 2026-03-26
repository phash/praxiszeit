from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
from contextlib import asynccontextmanager
import os
import sys
import logging
import traceback
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.database import engine, SessionLocal, set_tenant_context
from app.config import settings
from app.models import User, UserRole
from app.services import auth_service, holiday_service
from app.services.error_log_service import DBErrorHandler, cleanup_old_errors
from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests, journal, import_xls


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events for the application.
    """
    # Startup
    print("🚀 Starting PraxisZeit backend...")

    # 1. Check database connection
    try:
        with engine.connect() as conn:
            print("✅ Database connection established")
    except OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print("⏳ Waiting for database to be ready...")
        sys.exit(1)

    # 2. Migrations are handled by Dockerfile CMD (alembic upgrade head)

    # 3. Ensure default tenant exists
    from app.models.tenant import Tenant
    from app.database import set_tenant_context, set_superadmin_context
    import uuid as _uuid
    db = SessionLocal()
    try:
        # Startup runs as non-superuser — need superadmin context to bypass RLS
        set_superadmin_context(db)
        default_tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        if not default_tenant:
            print("🏢 Creating default tenant...")
            default_tenant = Tenant(
                id=_uuid.UUID("00000000-0000-0000-0000-000000000001"),
                name="Default",
                slug="default",
                is_active=True,
                mode="single",
            )
            db.add(default_tenant)
            db.commit()
            print("✅ Default tenant created")
        default_tenant_id = default_tenant.id
    finally:
        db.close()

    # 4. Create admin user if it doesn't exist
    db = SessionLocal()
    try:
        set_tenant_context(db, str(default_tenant_id))
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
                tenant_id=default_tenant_id,
            )
            db.add(admin)
            db.commit()
            print(f"✅ Admin user created")
        else:
            print(f"✅ Admin user already exists: {settings.ADMIN_USERNAME}")

        # Security warning: check if admin still uses default credentials
        if settings.ADMIN_USERNAME == "admin" and auth_service.verify_password(
            settings.ADMIN_PASSWORD, admin.password_hash
        ):
            weak_passwords = ["Admin2025!", "admin123", "password", "admin"]
            if settings.ADMIN_PASSWORD in weak_passwords or len(settings.ADMIN_PASSWORD) < 12:
                msg = "SECURITY: Admin account uses a weak/default password! Set a strong ADMIN_PASSWORD in .env."
                if settings.ENVIRONMENT == "production":
                    raise RuntimeError(msg)
                print(f"⚠️  {msg}")
    finally:
        db.close()

    # 5. DSGVO F-007: Clean up old error logs (>90 days resolved/ignored)
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        deleted = cleanup_old_errors(db, max_age_days=90)
        if deleted:
            print(f"🗑️  Cleaned up {deleted} old error log entries (>90 days)")
    finally:
        db.close()

    # 6. Sync public holidays for current and next year
    print("📅 Syncing public holidays...")
    db = SessionLocal()
    try:
        set_tenant_context(db, '00000000-0000-0000-0000-000000000001')
        state = holiday_service.get_holiday_state(db)
        result = holiday_service.sync_current_and_next_year(db, state=state, tenant_id=default_tenant_id)
        print(f"✅ Holidays synced for {result['state']}: {result['current_year']}({result['current_count']}), "
              f"{result['next_year']}({result['next_count']})")
    finally:
        db.close()

    # Configuration sanity checks
    if settings.COOKIE_SECURE and settings.ENVIRONMENT != "production":
        print("⚠️  COOKIE_SECURE=True but ENVIRONMENT is not 'production'. "
              "The refresh-token cookie will NOT be sent over HTTP — set COOKIE_SECURE=false in .env for local development.")

    print("✅ PraxisZeit backend ready!")

    yield

    # Shutdown
    print("👋 Shutting down PraxisZeit backend...")


# Create FastAPI app (disable docs in production)
_is_production = settings.ENVIRONMENT == "production"
app = FastAPI(
    title="PraxisZeit API",
    description="Zeiterfassungssystem für Arztpraxen",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Rate limiter (shared instance from app.core.limiter)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus metrics – DSGVO F-014: group_paths=True prevents UUIDs in metric labels
Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
    should_group_untemplated=True,
).instrument(app).expose(app)

# Configure CORS
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
_cors_is_wildcard = cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not _cors_is_wildcard,  # Disable credentials with wildcard origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Cookie"],
)

# Attach DB error logging handler (captures WARNING+ logs to error_logs table)
# DSGVO F-007: sqlalchemy.engine intentionally NOT attached (SQL queries can contain PII)
_db_error_handler = DBErrorHandler(SessionLocal)
_db_error_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger('uvicorn.error').addHandler(_db_error_handler)
logging.getLogger('fastapi').addHandler(_db_error_handler)

# Register routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(time_entries.router)
app.include_router(absences.router)
app.include_router(dashboard.router)
app.include_router(holidays.router)
app.include_router(reports.router)
app.include_router(change_requests.router)
app.include_router(company_closures.router)
app.include_router(error_logs.router)
app.include_router(vacation_requests.router)
app.include_router(journal.router)
app.include_router(import_xls.router)


@app.middleware("http")
async def capture_errors_middleware(request: Request, call_next):
    """Capture 5xx errors and log them to the error_logs table."""
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            db = SessionLocal()
            try:
                from app.services.error_log_service import log_error
                from app.database import set_superadmin_context as _set_sa
                _set_sa(db)  # Error logging needs to bypass RLS
                log_error(
                    db=db,
                    level='error',
                    logger_name='http',
                    message=f"HTTP {response.status_code} {request.method} {request.url.path}",
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                )
            finally:
                db.close()
        return response
    except Exception as exc:
        db = SessionLocal()
        try:
            from app.services.error_log_service import log_error
            from app.database import set_superadmin_context as _set_sa
            _set_sa(db)  # Error logging needs to bypass RLS
            tb = traceback.format_exc()
            log_error(
                db=db,
                level='critical',
                logger_name='http',
                message=str(exc),
                traceback_str=tb,  # truncation applied inside log_error
                path=request.url.path,
                method=request.method,
                status_code=500,
            )
        finally:
            db.close()
        raise


@app.get("/")
def root():
    """Root endpoint."""
    # DSGVO F-015: don't expose /docs URL in production
    response = {"message": "PraxisZeit API", "version": "1.0.0"}
    if not _is_production:
        response["docs"] = "/docs"
    return response


@app.get("/api/settings")
def get_public_settings():
    """Public endpoint returning runtime-configurable UI settings (no auth required)."""
    from app.models.system_setting import SystemSetting
    from app.database import set_superadmin_context as _set_sa
    db = SessionLocal()
    try:
        _set_sa(db)  # Public endpoint needs to read global settings
        def _get(key, default="false"):
            s = db.query(SystemSetting).filter(
                SystemSetting.key == key,
                SystemSetting.tenant_id.is_(None)  # Only global settings
            ).first()
            return s.value if s else default
        return {
            "vacation_approval_required": _get("vacation_approval_required", "false").lower() == "true"
        }
    finally:
        db.close()


@app.get("/api/health")
def health_check():
    """Health check endpoint with database connectivity test."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"}
        )
    finally:
        db.close()
