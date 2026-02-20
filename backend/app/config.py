import warnings
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    ENVIRONMENT: str = "development"  # "development" or "production"

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost,http://localhost:5173"

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
