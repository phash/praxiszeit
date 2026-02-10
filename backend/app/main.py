from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import subprocess
import sys
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.database import engine, SessionLocal
from app.config import settings
from app.models import User, UserRole
from app.services import auth_service, holiday_service
from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports


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

    # 2. Run Alembic migrations
    print("🔄 Running database migrations...")
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Database migrations completed")
        else:
            print(f"⚠️  Migration warning: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Could not run migrations automatically: {e}")

    # 3. Create admin user if it doesn't exist
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if not admin:
            print(f"👤 Creating admin user: {settings.ADMIN_EMAIL}")
            admin = User(
                email=settings.ADMIN_EMAIL,
                password_hash=auth_service.hash_password(settings.ADMIN_PASSWORD),
                first_name=settings.ADMIN_FIRST_NAME,
                last_name=settings.ADMIN_LAST_NAME,
                role=UserRole.ADMIN,
                weekly_hours=40.0,
                vacation_days=30,
                is_active=True
            )
            db.add(admin)
            db.commit()
            print(f"✅ Admin user created")
        else:
            print(f"✅ Admin user already exists: {settings.ADMIN_EMAIL}")
    finally:
        db.close()

    # 4. Sync public holidays for current and next year
    print("📅 Syncing public holidays...")
    db = SessionLocal()
    try:
        result = holiday_service.sync_current_and_next_year(db)
        print(f"✅ Holidays synced: {result['current_year']}({result['current_count']}), "
              f"{result['next_year']}({result['next_count']})")
    finally:
        db.close()

    print("✅ PraxisZeit backend ready!")

    yield

    # Shutdown
    print("👋 Shutting down PraxisZeit backend...")


# Create FastAPI app
app = FastAPI(
    title="PraxisZeit API",
    description="Zeiterfassungssystem für Arztpraxen",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(time_entries.router)
app.include_router(absences.router)
app.include_router(dashboard.router)
app.include_router(holidays.router)
app.include_router(reports.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "PraxisZeit API",
        "version": "1.0.0",
        "docs": "/docs"
    }


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
