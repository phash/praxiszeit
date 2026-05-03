import os
import warnings
from pathlib import Path
from typing import Literal, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- TOML Config Loader (native installations) ---
# If a praxiszeit.conf TOML file exists, load its values as environment
# variables before Pydantic Settings initializes. Environment variables
# and .env take precedence (Pydantic's default priority).

_TOML_CONFIG_PATHS = [
    Path("config/praxiszeit.conf"),        # Relative (native install layout)
    Path("/opt/praxiszeit/config/praxiszeit.conf"),  # Linux absolute
]

# Mapping from TOML sections+keys to environment variable names
_TOML_KEY_MAP = {
    ("server", "port"): "SERVER_PORT",
    ("server", "ssl_cert"): "SSL_CERT_PATH",
    ("server", "ssl_key"): "SSL_KEY_PATH",
    ("database", "data_dir"): "PG_DATA_DIR",
    ("practice", "name"): "PRACTICE_NAME",
    ("practice", "address"): "PRACTICE_ADDRESS",
    ("practice", "holiday_state"): "HOLIDAY_STATE",
    ("admin", "username"): "ADMIN_USERNAME",
    ("admin", "email"): "ADMIN_EMAIL",
    ("admin", "password"): "ADMIN_PASSWORD",
    ("admin", "first_name"): "ADMIN_FIRST_NAME",
    ("admin", "last_name"): "ADMIN_LAST_NAME",
    ("security", "secret_key"): "SECRET_KEY",
    ("security", "login_rate_limit"): "LOGIN_RATE_LIMIT",
    ("security", "cookie_secure"): "COOKIE_SECURE",
    ("license", "key_file"): "LICENSE_KEY_PATH",
    ("license", "demo_expires_at"): "LICENSE_DEMO_EXPIRES_AT",
    ("server", "port"): "SERVER_PORT",
    ("server", "http_redirect_port"): "SERVER_HTTP_REDIRECT_PORT",
    ("updates", "check_enabled"): "UPDATE_CHECK_ENABLED",
    ("updates", "server_url"): "UPDATE_SERVER_URL",
    ("updates", "check_interval_hours"): "UPDATE_CHECK_INTERVAL_HOURS",
    ("backup", "enabled"): "BACKUP_ENABLED",
    ("backup", "schedule"): "BACKUP_SCHEDULE",
    ("backup", "retention_days"): "BACKUP_RETENTION_DAYS",
}


def _load_toml_config():
    """Load praxiszeit.conf (TOML) and set values as env vars if not already set."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # Python < 3.11 fallback
        except ImportError:
            return

    for config_path in _TOML_CONFIG_PATHS:
        if config_path.is_file():
            with open(config_path, "rb") as f:
                toml_data = tomllib.load(f)

            for (section, key), env_name in _TOML_KEY_MAP.items():
                if env_name in os.environ:
                    continue  # Env vars take precedence
                if section in toml_data and key in toml_data[section]:
                    value = toml_data[section][key]
                    os.environ[env_name] = str(value).lower() if isinstance(value, bool) else str(value)

            # SERVE_FRONTEND is implicitly true when loaded from TOML config
            if "SERVE_FRONTEND" not in os.environ:
                os.environ["SERVE_FRONTEND"] = "true"

            break  # Only load the first config file found


_load_toml_config()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    ENVIRONMENT: str = "development"  # "development" or "production"

    # Deployment mode — steers which features are enabled at runtime:
    # - onprem (default, safe for existing installations): Single-tenant,
    #   license middleware active, self-service signup disabled, no billing UI.
    # - saas: Multi-tenant, public signup, Stripe billing, license middleware
    #   repurposed for per-tenant suspend.
    # Default = onprem so existing Docker + native installs upgrade without
    # any env changes.
    DEPLOYMENT_MODE: Literal["saas", "onprem"] = "onprem"

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost,http://localhost:5173"

    # Cookie security (set COOKIE_SECURE=false only for local HTTP development)
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"

    # TOTP 2FA issuer name shown in authenticator apps
    TOTP_ISSUER: str = "PraxisZeit"

    # Rate limiting (increase for E2E test environments)
    LOGIN_RATE_LIMIT: str = "5/minute"
    # F-063: refresh rate limit — also needs to be raised for E2E where
    # every test mount triggers one /auth/refresh call via hydrate().
    REFRESH_RATE_LIMIT: str = "10/minute"

    # Native mode: serve frontend static files directly from FastAPI (no nginx)
    SERVE_FRONTEND: bool = False
    FRONTEND_DIR: str = "../frontend/dist"

    # License key file path (native installations only)
    LICENSE_KEY_PATH: Optional[str] = None

    # Demo-Mode (Native): wenn keine LICENSE_KEY_PATH und LICENSE_DEMO_EXPIRES_AT
    # gesetzt ist, laeuft die App bis zum genannten Datum mit voller
    # Funktionalitaet, danach Read-Only. Format ISO-Date YYYY-MM-DD.
    # Wird vom Setup-Wizard auf Install-Datum + 30 Tage gesetzt; im
    # Production-Install bleibt es leer und der Lizenz-Pfad ist gesetzt.
    LICENSE_DEMO_EXPIRES_AT: Optional[str] = None

    # Native-mode: HTTP / HTTPS-Listener-Ports (vom Wizard konfigurierbar).
    # Default 443 / 80 — Backend rendert sie auch in keinen externen
    # URLs ausser im Update-Banner; primaer fuer den Service-Wrapper, der
    # uvicorn mit --port startet.
    SERVER_PORT: int = 443
    SERVER_HTTP_REDIRECT_PORT: int = 80

    # Update server URL (native installations only)
    UPDATE_SERVER_URL: Optional[str] = None
    UPDATE_CHECK_INTERVAL_HOURS: int = 12

    # SMTP — used by the self-service signup flow (Phase 3). If MAIL_HOST is
    # unset, mail_service.send() logs the email body and returns True; in
    # production (DEPLOYMENT_MODE=saas) these MUST be configured.
    MAIL_HOST: Optional[str] = None
    MAIL_PORT: int = 587
    MAIL_USER: Optional[str] = None
    MAIL_PASS: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_STARTTLS: bool = True

    # Stripe — used by /api/billing/* and /api/webhooks/stripe (Phase 4).
    # All optional; when STRIPE_SECRET_KEY is unset the billing router
    # returns 503 ("Zahlungsabwicklung nicht konfiguriert") so an admin
    # can still see their plan via /api/tenant/billing while Stripe setup
    # is pending.
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_STARTER_MONTHLY: Optional[str] = None
    STRIPE_PRICE_STARTER_YEARLY: Optional[str] = None
    STRIPE_PRICE_PRO_MONTHLY: Optional[str] = None
    STRIPE_PRICE_PRO_YEARLY: Optional[str] = None
    # Grace period before a canceled subscription flips to 'suspended'.
    STRIPE_CANCEL_GRACE_DAYS: int = 30

    # Optional — operator alerts (Phase 7). Unset → alerts are logged only.
    SLACK_WEBHOOK_URL: Optional[str] = None

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        weak_indicators = ["change", "secret", "default", "example", "12345", "password"]
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(64))\""
            )
        if any(word in v.lower() for word in weak_indicators):
            raise ValueError(
                "SECRET_KEY appears to be a default/weak value. "
                "Generate a secure one with: python -c \"import secrets; print(secrets.token_hex(64))\""
            )
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        if v.strip() == "*":
            warnings.warn(
                "CORS_ORIGINS is set to '*' (all origins). "
                "This is insecure for production! Set specific origins in .env, e.g.: "
                "CORS_ORIGINS=https://praxis.example.com",
                stacklevel=2,
            )
        return v

    # Organisation / DSGVO F-016: configurable practice info for Excel exports
    PRACTICE_NAME: str = "Praxis"
    PRACTICE_ADDRESS: str = ""

    # Holidays
    HOLIDAY_STATE: str = "Bayern"  # German state for public holidays

    # Initial Admin
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    ADMIN_FIRST_NAME: str = "Admin"
    ADMIN_LAST_NAME: str = "Praxis"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
