"""Tests for tenant_id (tid) claim in JWT tokens."""
import pytest
from app.services import auth_service

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
USER_ID = "test-user-id-123"
ROLE = "employee"


def test_access_token_contains_tid():
    """Access token created with tenant_id should contain 'tid' claim."""
    token = auth_service.create_access_token(USER_ID, ROLE, tenant_id=TENANT_ID)
    payload = auth_service.decode_token(token)

    assert payload is not None
    assert payload.get("tid") == TENANT_ID


def test_access_token_no_tid_for_superadmin():
    """Access token created without tenant_id (superadmin) must NOT contain 'tid'."""
    token = auth_service.create_access_token(USER_ID, ROLE)
    payload = auth_service.decode_token(token)

    assert payload is not None
    assert "tid" not in payload


def test_refresh_token_contains_tid():
    """Refresh token created with tenant_id should contain 'tid' claim."""
    token = auth_service.create_refresh_token(USER_ID, tenant_id=TENANT_ID)
    payload = auth_service.decode_token(token)

    assert payload is not None
    assert payload.get("tid") == TENANT_ID


def test_refresh_token_no_tid_for_superadmin():
    """Refresh token created without tenant_id (superadmin) must NOT contain 'tid'."""
    token = auth_service.create_refresh_token(USER_ID)
    payload = auth_service.decode_token(token)

    assert payload is not None
    assert "tid" not in payload


def test_backward_compat_no_tenant_id_param():
    """Calling token functions without tenant_id param works as before (no 'tid')."""
    access_token = auth_service.create_access_token(USER_ID, ROLE, 0)
    refresh_token = auth_service.create_refresh_token(USER_ID, 0)

    access_payload = auth_service.decode_token(access_token)
    refresh_payload = auth_service.decode_token(refresh_token)

    assert access_payload is not None
    assert "tid" not in access_payload
    assert access_payload["sub"] == USER_ID
    assert access_payload["role"] == ROLE
    assert access_payload["type"] == "access"

    assert refresh_payload is not None
    assert "tid" not in refresh_payload
    assert refresh_payload["sub"] == USER_ID
    assert refresh_payload["type"] == "refresh"
