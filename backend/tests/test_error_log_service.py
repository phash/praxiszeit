"""Tests for error log service (PII scrubbing, fingerprinting)."""
import pytest
from app.services.error_log_service import _scrub_pii, _make_fingerprint


class TestScrubPii:
    """Test _scrub_pii() for DSGVO F-007 compliance."""

    def test_uuid_is_scrubbed(self):
        """UUIDs in text should be replaced with <uuid>."""
        text = "user 550e8400-e29b-41d4-a716-446655440000 failed"
        result = _scrub_pii(text)
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "<uuid>" in result
        assert "user" in result
        assert "failed" in result

    def test_email_is_scrubbed(self):
        """Email addresses in text should be replaced with <email>."""
        text = "user test@example.com failed"
        result = _scrub_pii(text)
        assert "test@example.com" not in result
        assert "<email>" in result
        assert "user" in result

    def test_mixed_uuid_and_email(self):
        """Both UUIDs and emails should be scrubbed in the same string."""
        text = "user 550e8400-e29b-41d4-a716-446655440000 with email admin@praxis.de error"
        result = _scrub_pii(text)
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "admin@praxis.de" not in result
        assert "<uuid>" in result
        assert "<email>" in result

    def test_no_pii_unchanged(self):
        """Strings without PII should pass through unchanged."""
        text = "simple error message without PII"
        result = _scrub_pii(text)
        assert result == text

    def test_empty_string(self):
        """Empty string should return empty string."""
        result = _scrub_pii("")
        assert result == ""

    def test_none_returns_none(self):
        """None input should return falsy value (None or empty)."""
        result = _scrub_pii(None)
        assert not result

    def test_multiple_uuids(self):
        """Multiple UUIDs should all be scrubbed."""
        text = "from 550e8400-e29b-41d4-a716-446655440000 to 12345678-1234-1234-1234-123456789abc"
        result = _scrub_pii(text)
        assert "550e8400" not in result
        assert "12345678-1234" not in result
        assert result.count("<uuid>") == 2

    def test_complex_email_formats(self):
        """Various email formats should be scrubbed."""
        text = "emails: user.name+tag@sub.example.co.uk and test@test.de"
        result = _scrub_pii(text)
        assert "user.name+tag@sub.example.co.uk" not in result
        assert "test@test.de" not in result


class TestMakeFingerprint:
    """Test _make_fingerprint() for error deduplication."""

    def test_same_input_same_hash(self):
        """Identical inputs must produce the same fingerprint."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        assert fp1 == fp2

    def test_different_message_different_hash(self):
        """Different messages must produce different fingerprints."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("error", "app.main", "timeout error", "/api/test")
        assert fp1 != fp2

    def test_different_level_different_hash(self):
        """Different levels must produce different fingerprints."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("warning", "app.main", "connection failed", "/api/test")
        assert fp1 != fp2

    def test_different_path_different_hash(self):
        """Different paths must produce different fingerprints."""
        fp1 = _make_fingerprint("error", "app.main", "failed", "/api/a")
        fp2 = _make_fingerprint("error", "app.main", "failed", "/api/b")
        assert fp1 != fp2

    def test_deterministic(self):
        """Fingerprint must be deterministic across multiple calls."""
        results = set()
        for _ in range(10):
            results.add(_make_fingerprint("error", "logger", "msg", "/path"))
        assert len(results) == 1

    def test_returns_hex_string(self):
        """Fingerprint should be a hex-encoded SHA256 (64 chars)."""
        fp = _make_fingerprint("error", "app.main", "test", "/api")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_none_path_handled(self):
        """None path should be handled gracefully."""
        fp = _make_fingerprint("error", "app.main", "test", None)
        assert isinstance(fp, str)
        assert len(fp) == 64
