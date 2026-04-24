"""Schemas for /api/public/signup + /verify-email (Phase 3 / Issue #94)."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    practice_name: str = Field(..., min_length=2, max_length=255)
    admin_email: EmailStr
    admin_first_name: str = Field(..., min_length=1, max_length=100)
    admin_last_name: str = Field(..., min_length=1, max_length=100)
    # Mirrors auth_service.hash_password policy: min 8 chars. Full strength
    # check happens on first login; here we only block trivially short PW.
    admin_password: str = Field(..., min_length=8, max_length=128)
    accept_terms: bool
    accept_privacy: bool
    country: str = Field(..., min_length=2, max_length=2)

    @field_validator("accept_terms", "accept_privacy")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("AGB und Datenschutz müssen akzeptiert werden")
        return v

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


class SignupResponse(BaseModel):
    tenant_id: str
    message: str = "Bitte bestätige deine E-Mail-Adresse über den Link, den wir dir gerade gesendet haben."


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyResponse(BaseModel):
    tenant_id: str
    message: str = "E-Mail-Adresse bestätigt. Du kannst dich jetzt einloggen."
