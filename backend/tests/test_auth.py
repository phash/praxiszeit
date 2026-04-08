"""Tests for authentication service."""
import pytest
from app.services import auth_service


def test_hash_password():
    """Prüft dass Passwort-Hashing einen vom Klartext verschiedenen, nicht-leeren Hash erzeugt."""
    password = "securepassword123"
    hashed = auth_service.hash_password(password)
    
    assert hashed is not None
    assert hashed != password
    assert len(hashed) > 0


def test_verify_password():
    """Prüft dass korrektes Passwort verifiziert und falsches abgelehnt wird."""
    password = "securepassword123"
    hashed = auth_service.hash_password(password)
    
    # Correct password should verify
    assert auth_service.verify_password(password, hashed) is True
    
    # Wrong password should not verify
    assert auth_service.verify_password("wrongpassword", hashed) is False


def test_create_access_token():
    """Prüft dass ein gültiger JWT-Access-Token mit user_id und Rolle erzeugt wird."""
    user_id = "test-user-id-123"
    role = "employee"
    
    token = auth_service.create_access_token(user_id, role)
    
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_refresh_token():
    """Prüft dass ein gültiger JWT-Refresh-Token für Token-Erneuerung erzeugt wird."""
    user_id = "test-user-id-123"
    
    token = auth_service.create_refresh_token(user_id)
    
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_valid_access_token():
    """Prüft dass Access-Token korrekt decodiert wird und sub, role, type enthält."""
    user_id = "test-user-id-123"
    role = "employee"
    
    token = auth_service.create_access_token(user_id, role)
    payload = auth_service.decode_token(token)
    
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["role"] == role
    assert payload["type"] == "access"


def test_decode_valid_refresh_token():
    """Prüft dass Refresh-Token korrekt decodiert wird und type=refresh enthält."""
    user_id = "test-user-id-123"
    
    token = auth_service.create_refresh_token(user_id)
    payload = auth_service.decode_token(token)
    
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_decode_invalid_token():
    """Prüft dass ein ungültiger Token None zurückgibt statt zu crashen — wichtig für Sicherheit."""
    invalid_token = "invalid.token.here"
    
    payload = auth_service.decode_token(invalid_token)
    
    assert payload is None


def test_password_truncation():
    """Prüft dass überlange Passwörter korrekt behandelt werden — bcrypt schneidet bei 72 Bytes ab."""
    long_password = "a" * 100  # 100 characters
    hashed = auth_service.hash_password(long_password)
    
    # Should successfully hash and verify
    assert auth_service.verify_password(long_password, hashed) is True
    
    # First 72 chars should also verify (bcrypt limitation)
    assert auth_service.verify_password("a" * 72, hashed) is True
