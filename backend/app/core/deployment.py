"""Deployment-mode helpers.

One codebase runs as either:
- ``onprem`` — single-tenant, license-gated (existing installations)
- ``saas`` — multi-tenant, public signup, Stripe-billed

Routes and startup hooks branch on ``is_saas()`` / ``is_onprem()`` instead of
reading the env var directly so tests can monkeypatch cleanly.
"""

from app.config import settings


def is_saas() -> bool:
    return settings.DEPLOYMENT_MODE == "saas"


def is_onprem() -> bool:
    return settings.DEPLOYMENT_MODE == "onprem"
