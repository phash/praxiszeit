from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
from app.middleware.static_serving import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    SPAFallbackMiddleware,
)
from app.middleware.csrf import CSRFMiddleware
from app.middleware.license import LicenseReadOnlyMiddleware
from contextlib import asynccontextmanager
import os
import sys
import logging
import uuid
import traceback
from typing import Optional
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.database import engine, SessionLocal, set_tenant_context
from app.config import settings
from app.models import User, UserRole
from app.services import auth_service, holiday_service
from app.services.error_log_service import DBErrorHandler, cleanup_old_errors
from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests, journal, import_xls, superadmin, tenant_billing, public_signup, billing, me, feedback

# Used by the startup bootstrap to warn/abort when the initial admin still
# uses a throwaway password. Kept at module level so git diffs that re-indent
# the bootstrap block (e.g. adding a deployment-mode guard) don't re-flag
# these strings as "newly introduced secrets" in GitGuardian.
_WEAK_ADMIN_PASSWORDS = frozenset({"Admin2025!", "admin123", "password", "admin"})  # noqa: S105 (not a real secret; used to DETECT weak ones)


# M6: License-Read-Only-Audit-Marker. 16 Zeichen, klar unter dem 40-Char-Limit
# aus Migration 037 (time_entry_audit_logs.source = varchar(40)).
LICENSE_AUDIT_SOURCE = "license_startup"
assert len(LICENSE_AUDIT_SOURCE) < 40, (
    f"LICENSE_AUDIT_SOURCE '{LICENSE_AUDIT_SOURCE}' "
    f"({len(LICENSE_AUDIT_SOURCE)} chars) sprengt das 40-Char-Limit "
    "von time_entry_audit_logs.source (Migration 037)."
)


def audit_license_readonly_event(
    reason: str,
    default_tenant_id=None,
):
    """Persist einen strukturierten Audit-Log-Eintrag, wenn der License-Check
    beim Startup in den Read-Only-Modus geht.

    Hintergrund (M6 / DSGVO Art. 32 / ArbZG §16):
    Bisher wurde nur ``print("LIZENZ-PROBLEM: ...")`` aufgerufen. Ohne
    strukturierte Persistenz gibt es kein durchsuchbares Event fuer
    Compliance-Audits. Diese Funktion schreibt analog zu Health-Data-Reads
    + vacation_request_edit eine Zeile in ``time_entry_audit_logs``.

    Verhalten:
    - On-Prem ohne Default-Tenant oder ohne Admin-User: Skip mit Print-Hinweis
      (kein Crash).
    - SaaS-Modus (default_tenant_id=None): Skip — der License-Check ist im
      SaaS-Kontext global und nicht tenant-gebunden, ein Audit-Eintrag in
      einem beliebigen Tenant waere irrefuehrend.
    - DB-Fehler (z.B. Migration nicht durch, RLS-Glitch): try/except, der
      Startup darf NICHT durch einen Audit-Write blockiert werden.

    Idempotenz: bewusst Option A — jeder Restart erzeugt einen Eintrag.
    Audit-Logs sollen vollstaendig sein, Restart-Haeufigkeit ist informativ.

    Args:
        reason: Kurze, persistierbare Begruendung
            (z.B. "Lizenz abgelaufen", "Ungueltige Signatur",
            "Demo-Frist ueberschritten").
        default_tenant_id: tenant_id fuer den Eintrag. None -> Skip
            (SaaS-Modus oder Default-Tenant existiert noch nicht).
    """
    if default_tenant_id is None:
        print("AUDIT: License-Read-Only-Event ohne default_tenant_id "
              "uebersprungen (SaaS-Modus oder Default-Tenant fehlt).")
        return

    from app.database import set_superadmin_context as _set_sa
    from app.models import User, UserRole, TimeEntryAuditLog

    db = SessionLocal()
    try:
        # Audit braucht Superadmin-Context: RLS-Policy auf time_entry_audit_logs
        # blockt sonst INSERTs ohne aktiven Tenant.
        _set_sa(db)

        # NOT-NULL-Constraint auf user_id + changed_by -> wir muessen einen
        # bestehenden User referenzieren. Den (Bootstrap-)Admin nehmen, der
        # in Schritt 4 garantiert angelegt wurde (License-Check ist nach
        # Schritt 6 → Admin existiert).
        admin = (
            db.query(User)
            .filter(
                User.tenant_id == default_tenant_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
            .order_by(User.created_at.asc())
            .first()
        )
        if admin is None:
            # Kein Admin -> Audit-Write nicht moeglich (FK-Violation).
            # Print-Hinweis statt Crash: License-State ist bereits korrekt
            # gesetzt, der Audit-Log ist „nur" zusaetzliche Compliance-Spur.
            print(f"AUDIT: License-Read-Only-Event ('{reason}') konnte nicht "
                  "persistiert werden — kein aktiver Admin im Default-Tenant.")
            return

        # Hinweis-Note unter 255-Char-Limit (Text-Spalte hat technisch kein
        # Limit, aber die Note ist UI-sichtbar und soll lesbar bleiben).
        note = f"READ-ONLY: {reason}"

        db.add(
            TimeEntryAuditLog(
                tenant_id=default_tenant_id,
                user_id=admin.id,
                changed_by=admin.id,
                action="license_readonly_mode_entered",
                source=LICENSE_AUDIT_SOURCE,
                new_note=note,
            )
        )
        db.commit()
        print(f"AUDIT: License-Read-Only-Event persistiert "
              f"(source={LICENSE_AUDIT_SOURCE}, reason='{reason}').")
    except Exception as exc:  # noqa: BLE001
        # Startup darf NICHT scheitern, wenn der Audit-Write hakt
        # (z.B. Migration noch nicht durch, DB-Lock). Read-Only-State
        # ist bereits gesetzt, sysadmin sieht den Print-Hinweis.
        print(f"AUDIT WARN: License-Read-Only-Event ('{reason}') konnte "
              f"nicht in time_entry_audit_logs geschrieben werden: {exc}")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


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

    # 3. Ensure default tenant exists (onprem only — SaaS provisions per signup)
    from app.models.tenant import Tenant
    from app.database import set_tenant_context, set_superadmin_context
    from app.core.deployment import is_saas, is_onprem
    import uuid as _uuid
    default_tenant_id = None
    if is_onprem():
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
    else:
        print("☁️  SaaS mode: skipping default-tenant bootstrap")

    # 4. Create admin user if it doesn't exist (onprem only)
    if is_onprem() and default_tenant_id is not None:
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
                    # Bootstrap-Admin ist ein technisches Konto, kein zeiterfasster
                    # Mitarbeiter -> aus der Zeitzaehlung nehmen (keine "Buchung
                    # fehlt"-Warnungen, nicht im Team-Fehlbuchungs-Widget).
                    # Per Benutzerverwaltung jederzeit umstellbar.
                    track_hours=False,
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
                if settings.ADMIN_PASSWORD in _WEAK_ADMIN_PASSWORDS or len(settings.ADMIN_PASSWORD) < 12:
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

    # 6. Sync public holidays for current and next year (onprem default tenant)
    if is_onprem() and default_tenant_id is not None:
        print("📅 Syncing public holidays...")
        db = SessionLocal()
        try:
            set_tenant_context(db, '00000000-0000-0000-0000-000000000001')
            state = holiday_service.get_holiday_state(db, tenant_id=default_tenant_id)
            result = holiday_service.sync_current_and_next_year(db, state=state, tenant_id=default_tenant_id)
            print(f"✅ Holidays synced for {result['state']}: {result['current_year']}({result['current_count']}), "
                  f"{result['next_year']}({result['next_count']})")
        finally:
            db.close()

    # 7. License validation (native installations only). Drei Modi:
    #    a) LICENSE_KEY_PATH gesetzt + Datei existiert → echte Lizenz validieren
    #    b) LICENSE_DEMO_EXPIRES_AT gesetzt (vom Setup-Wizard) → Demo-Mode bis dahin
    #    c) keins von beiden → klassisch ohne Lizenz (Docker-Dev / SaaS)
    if settings.LICENSE_KEY_PATH and Path(settings.LICENSE_KEY_PATH).is_file():
        from app.core.license import (
            validate_license, validate_license_quiet,
            set_license_state, LicenseError, LicenseExpiredError,
        )
        license_path = Path(settings.LICENSE_KEY_PATH)
        try:
            license_info = validate_license(license_path)
            set_license_state(license_info, read_only=False)
            days_left = license_info.days_until_expiry
            print(f"License: {license_info.customer_name} "
                  f"(max {license_info.max_employees} MA, "
                  f"{days_left} days remaining)")
        except LicenseExpiredError as e:
            # Expired: read-only mode (ArbZG-compliant — data still accessible)
            license_info = validate_license_quiet(license_path)
            set_license_state(license_info, read_only=True)
            print(f"WARNING: {e}")
            print("App running in READ-ONLY mode.")
            # M6: structured audit-log fuer DSGVO Art. 32 / ArbZG §16
            audit_license_readonly_event(
                reason="Lizenz abgelaufen",
                default_tenant_id=default_tenant_id,
            )
        except LicenseError as e:
            # Eine ungueltige/nicht verifizierbare Lizenz darf den Dienst NICHT
            # abschiessen (frueher: sys.exit(1) -> Totalausfall, niemand kommt
            # rein). Stattdessen Read-Only-Modus: Login, Ansicht und Export
            # bleiben moeglich; nur Schreibvorgaenge (Stempeln, Antraege stellen/
            # genehmigen) sind gesperrt (LicenseReadOnlyMiddleware).
            print(f"LIZENZ-PROBLEM: {e}")
            print("-> PraxisZeit laeuft im READ-ONLY-Modus: Anmeldung und "
                  "Daten-Export funktionieren, Stempeln und Antraege sind "
                  "gesperrt. Bitte eine gueltige Lizenz im Shop "
                  "(praxiszeit.mr-development.de) holen und unter "
                  "config\\license.key ablegen.")
            set_license_state(None, read_only=True)
            # M6: structured audit-log fuer DSGVO Art. 32 / ArbZG §16
            audit_license_readonly_event(
                reason="Ungueltige Signatur",
                default_tenant_id=default_tenant_id,
            )
    elif settings.LICENSE_DEMO_EXPIRES_AT:
        # Demo-Mode (vom Setup-Wizard gesetzt). Volle Funktion bis zum Datum,
        # danach Read-Only. Wir exportieren KEINE LicenseInfo (es gibt
        # keine Kundenangaben), aber die License-Middleware respektiert
        # den read_only-Flag.
        from app.core.license import set_license_state
        try:
            from datetime import date as _date
            demo_until = _date.fromisoformat(settings.LICENSE_DEMO_EXPIRES_AT.strip())
        except ValueError:
            print(f"LICENSE ERROR: ungueltiges LICENSE_DEMO_EXPIRES_AT "
                  f"'{settings.LICENSE_DEMO_EXPIRES_AT}' (erwartet YYYY-MM-DD)")
            sys.exit(1)
        from datetime import date
        today = date.today()
        if today > demo_until:
            print(f"WARNING: Demo-Lizenz abgelaufen am {demo_until.isoformat()}.")
            print("App running in READ-ONLY mode.")
            set_license_state(None, read_only=True)
            # M6: structured audit-log fuer DSGVO Art. 32 / ArbZG §16
            audit_license_readonly_event(
                reason="Demo-Frist ueberschritten",
                default_tenant_id=default_tenant_id,
            )
        else:
            days_left = (demo_until - today).days
            print(f"License: 30-Tage-Demo (laeuft am {demo_until.isoformat()} "
                  f"ab, noch {days_left} Tage)")
            set_license_state(None, read_only=False)

    # Configuration sanity checks
    if settings.COOKIE_SECURE and settings.ENVIRONMENT != "production":
        print("COOKIE_SECURE=True but ENVIRONMENT is not 'production'. "
              "The refresh-token cookie will NOT be sent over HTTP — set COOKIE_SECURE=false in .env for local development.")

    # 8. Issue #126: Start in-process scheduler for autonomous daily jobs
    #    (vacation-audit purge + tenant lifecycle). No-op in pytest mode.
    from app.services.scheduler_service import start_scheduler, stop_scheduler
    start_scheduler(app)

    print("PraxisZeit backend ready!")

    yield

    # Shutdown
    print("👋 Shutting down PraxisZeit backend...")
    stop_scheduler()


# Create FastAPI app (disable docs in production)
from app.core.updater import APP_VERSION
_is_production = settings.ENVIRONMENT == "production"
app = FastAPI(
    title="PraxisZeit API",
    description="Zeiterfassungssystem für Arztpraxen",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Rate limiter (shared instance from app.core.limiter)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus metrics – DSGVO F-014: group_paths=True prevents UUIDs in metric labels
# In native mode (SERVE_FRONTEND=True), don't expose metrics endpoint (no nginx to block it)
_instrumentator = Instrumentator(
    should_instrument_requests_inprogress=True,
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
    should_group_untemplated=True,
)
_instrumentator.instrument(app)
if not settings.SERVE_FRONTEND:
    _instrumentator.expose(app)

# Configure CORS
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
_cors_is_wildcard = cors_origins == ["*"]
# F-024 audit: ``Cookie`` is a forbidden header name in browsers (JS cannot
# set it), so listing it in allow_headers is both pointless and misleading.
# ``X-CSRF-Token`` is the double-submit header the frontend mirrors the
# csrf_token cookie into — it must be allowlisted for cross-origin use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not _cors_is_wildcard,  # Disable credentials with wildcard origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Requires-TOTP"],
)

# F-024: CSRF double-submit cookie enforcement on unsafe methods.
# Must be added AFTER CORSMiddleware so that preflight requests handled by
# CORS are still processed (OPTIONS is not an unsafe method anyway).
app.add_middleware(CSRFMiddleware)

# License read-only enforcement for native installs (no-op when no license
# is loaded). Auth endpoints stay writable so admins can still sign in and
# export §16-required records from an expired-license install.
app.add_middleware(LicenseReadOnlyMiddleware)

# GZip compression (replaces nginx gzip in native mode, harmless behind nginx)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Native mode middleware (replaces nginx features). Request-size guard is
# attached unconditionally — defence-in-depth against a missing/misconfigured
# nginx `client_max_body_size` when running behind a reverse proxy.
app.add_middleware(RequestSizeLimitMiddleware, max_size=2 * 1024 * 1024)  # 2MB
# M-SEC2: attach unconditionally (was gated on SERVE_FRONTEND). It only *sets*
# response headers, so it is harmless behind nginx (which sets the identical
# CSP) and provides a baseline CSP / anti-clickjacking guarantee if the reverse
# proxy is ever misconfigured, replaced (e.g. Caddy), or bypassed. HSTS inside
# the middleware is still gated on HTTPS.
app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(superadmin.router)
app.include_router(tenant_billing.router)
app.include_router(me.router)
app.include_router(feedback.router)
app.include_router(public_signup.router)
app.include_router(billing.router)
app.include_router(billing.webhook_router)


@app.middleware("http")
async def tenant_metrics_middleware(request: Request, call_next):
    """Increment per-tenant HTTP counter before handing off to the route.
    Only adds a label lookup per request — cheap enough for the hot path."""
    tid = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from app.services.auth_service import decode_token
            payload = decode_token(auth.split(" ", 1)[1]) or {}
            tid = payload.get("tid")
        except Exception:  # noqa: BLE001
            tid = None
    from app.services.tenant_metrics import record_request
    record_request(tid, request.method)
    return await call_next(request)


def _tenant_from_request(request: Request) -> Optional[str]:
    """Best-effort extraction of the caller's tenant_id for error attribution.

    Priority:
      1. ``request.state.tenant_id`` — set by ``get_current_user`` after a
         successful auth dependency. Always preferred (DB-truth).
      2. JWT ``tid`` claim from the bearer token — used as a fallback when
         the auth dependency itself raised (e.g. revoked token producing a
         500 in some downstream hook) so we still record a tenant.
      3. ``None`` — anonymous endpoints, missing/malformed bearer token, or
         infrastructure failures unrelated to a tenant. See
         ``error_log_service._scope_to_tenant`` for how NULL rows surface.
    """
    tid = getattr(request.state, "tenant_id", None)
    if tid:
        return tid
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from app.services.auth_service import decode_token
            payload = decode_token(auth.split(" ", 1)[1]) or {}
            return payload.get("tid")
        except Exception:  # noqa: BLE001
            return None
    return None


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
                    tenant_id=_tenant_from_request(request),
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
                tenant_id=_tenant_from_request(request),
            )
        finally:
            db.close()
        raise


# Root endpoint: only register when NOT serving frontend (Docker mode)
# In native mode (SERVE_FRONTEND=True), the SPA fallback serves index.html at /
if not settings.SERVE_FRONTEND:
    @app.get("/")
    def root():
        """Root endpoint."""
        # DSGVO F-015: don't expose /docs URL in production
        response = {"message": "PraxisZeit API", "version": APP_VERSION}
        if not _is_production:
            response["docs"] = "/docs"
        return response


@app.get("/api/settings")
def get_public_settings():
    """Public endpoint returning runtime-configurable UI settings (no auth required)."""
    from app.models.system_setting import SystemSetting
    from app.database import set_superadmin_context as _set_sa
    from app.core.license import get_current_license, is_read_only
    db = SessionLocal()
    try:
        _set_sa(db)  # Public endpoint needs to read global settings
        def _get(key, default="false"):
            s = db.query(SystemSetting).filter(
                SystemSetting.key == key,
                SystemSetting.tenant_id == uuid.UUID("00000000-0000-0000-0000-000000000001")
            ).first()
            return s.value if s else default

        result = {
            "vacation_approval_required": _get("vacation_approval_required", "false").lower() == "true",
            # #144 §4 ArbZG: whether a documented break-exception needs admin approval.
            "break_exception_requires_approval": _get("break_exception_requires_approval", "false").lower() == "true",
        }

        # License info (for native installations)
        license_info = get_current_license()
        if license_info is not None:
            result["license"] = {
                "customer_name": license_info.customer_name,
                "max_employees": license_info.max_employees,
                "days_until_expiry": license_info.days_until_expiry,
                "is_expired": license_info.is_expired,
                "read_only": is_read_only(),
            }

        return result
    finally:
        db.close()


@app.get("/api/status")
def public_status():
    """Public service-status aggregator used by the external status-page
    (Phase 8, Issue #99). Minimal surface — only reveals boolean health
    of each dependency so we don't leak operational details."""
    db_ok = False
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        db_ok = False

    try:
        from app.services.stripe_service import is_configured as stripe_ok_configured
        stripe_ok = stripe_ok_configured()
    except Exception:  # noqa: BLE001
        stripe_ok = False

    try:
        from app.services.mail_service import is_configured as mail_ok_configured
        mail_ok = mail_ok_configured()
    except Exception:  # noqa: BLE001
        mail_ok = False

    components = {
        "api": True,  # we're answering, so the API is up
        "database": db_ok,
        "stripe_configured": stripe_ok,
        "mail_configured": mail_ok,
    }
    healthy = all(v for k, v in components.items() if k in {"api", "database"})
    return {"status": "ok" if healthy else "degraded", "components": components}


@app.get("/api/system/info")
def system_info():
    """Public system info — lets the frontend branch on deployment mode
    without a login. Intentionally minimal: exposes only deployment_mode +
    version so we don't leak operational details to unauthenticated users."""
    return {
        "deployment_mode": settings.DEPLOYMENT_MODE,
        "version": APP_VERSION,
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


# --- Native mode: serve frontend static files directly from FastAPI ---
if settings.SERVE_FRONTEND:
    _frontend_dir = Path(settings.FRONTEND_DIR)
    if not _frontend_dir.is_absolute():
        _frontend_dir = Path(__file__).resolve().parent.parent / settings.FRONTEND_DIR
    _frontend_dir = _frontend_dir.resolve()

    @app.get("/sw.js")
    async def service_worker():
        """Service worker must not be cached."""
        sw_path = _frontend_dir / "sw.js"
        if sw_path.is_file():
            return FileResponse(
                str(sw_path),
                media_type="application/javascript",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @app.get("/manifest.webmanifest")
    async def manifest():
        """PWA manifest."""
        manifest_path = _frontend_dir / "manifest.webmanifest"
        if manifest_path.is_file():
            return FileResponse(
                str(manifest_path),
                media_type="application/manifest+json",
                headers={"Cache-Control": "no-cache"},
            )
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    # SPA fallback middleware: serves frontend for non-API GET requests that
    # don't match a static file. Replaces nginx try_files $uri $uri/ /index.html.
    # Using middleware instead of a catch-all route avoids 405 errors for
    # POST/PUT/DELETE to API paths.
    _index_path = _frontend_dir / "index.html"
    _index_html = _index_path.read_bytes() if _index_path.is_file() else b""
    app.add_middleware(
        SPAFallbackMiddleware,
        frontend_dir=_frontend_dir,
        index_html=_index_html,
    )

    # Mount hashed assets with long cache (before middleware, so they're served directly)
    _assets_dir = _frontend_dir / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static_assets")
