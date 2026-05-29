"""Tests for error log service (PII scrubbing, fingerprinting)."""
import pytest
from app.services.error_log_service import _scrub_pii, _make_fingerprint


class TestScrubPii:
    """Test _scrub_pii() for DSGVO F-007 compliance."""

    def test_uuid_is_scrubbed(self):
        """Prüft dass UUIDs aus Fehlermeldungen entfernt werden — DSGVO Art.9, keine Personen-IDs in Logs."""
        text = "user 550e8400-e29b-41d4-a716-446655440000 failed"
        result = _scrub_pii(text)
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "<uuid>" in result
        assert "user" in result
        assert "failed" in result

    def test_email_is_scrubbed(self):
        """Prüft dass E-Mail-Adressen aus Fehlermeldungen entfernt werden — DSGVO, keine personenbezogenen Daten in Logs."""
        text = "user test@example.com failed"
        result = _scrub_pii(text)
        assert "test@example.com" not in result
        assert "<email>" in result
        assert "user" in result

    def test_mixed_uuid_and_email(self):
        """Prüft dass UUIDs und E-Mails gleichzeitig im selben String bereinigt werden — realistisches Szenario."""
        text = "user 550e8400-e29b-41d4-a716-446655440000 with email admin@praxis.de error"
        result = _scrub_pii(text)
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "admin@praxis.de" not in result
        assert "<uuid>" in result
        assert "<email>" in result

    def test_no_pii_unchanged(self):
        """Prüft dass Texte ohne personenbezogene Daten unverändert bleiben — kein Over-Scrubbing."""
        text = "simple error message without PII"
        result = _scrub_pii(text)
        assert result == text

    def test_empty_string(self):
        """Prüft dass ein leerer String ohne Fehler verarbeitet wird — Edge-Case Robustheit."""
        result = _scrub_pii("")
        assert result == ""

    def test_none_returns_none(self):
        """Prüft dass None-Input ohne Exception verarbeitet wird — Fehlermeldungen können optional sein."""
        result = _scrub_pii(None)
        assert not result

    def test_multiple_uuids(self):
        """Prüft dass mehrere UUIDs im selben Text alle bereinigt werden — z.B. bei Beziehungs-Fehlern."""
        text = "from 550e8400-e29b-41d4-a716-446655440000 to 12345678-1234-1234-1234-123456789abc"
        result = _scrub_pii(text)
        assert "550e8400" not in result
        assert "12345678-1234" not in result
        assert result.count("<uuid>") == 2

    def test_complex_email_formats(self):
        """Prüft dass auch komplexe E-Mail-Formate (Subdomains, Tags) zuverlässig bereinigt werden."""
        text = "emails: user.name+tag@sub.example.co.uk and test@test.de"
        result = _scrub_pii(text)
        assert "user.name+tag@sub.example.co.uk" not in result
        assert "test@test.de" not in result


class TestMakeFingerprint:
    """Test _make_fingerprint() for error deduplication."""

    def test_same_input_same_hash(self):
        """Prüft dass identische Fehler denselben Fingerprint erzeugen — Basis für Deduplizierung."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        assert fp1 == fp2

    def test_different_message_different_hash(self):
        """Prüft dass unterschiedliche Fehlermeldungen verschiedene Fingerprints erzeugen — keine Kollisionen."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("error", "app.main", "timeout error", "/api/test")
        assert fp1 != fp2

    def test_different_level_different_hash(self):
        """Prüft dass verschiedene Log-Level verschiedene Fingerprints erzeugen — error vs. warning unterscheidbar."""
        fp1 = _make_fingerprint("error", "app.main", "connection failed", "/api/test")
        fp2 = _make_fingerprint("warning", "app.main", "connection failed", "/api/test")
        assert fp1 != fp2

    def test_different_path_different_hash(self):
        """Prüft dass verschiedene API-Pfade verschiedene Fingerprints erzeugen — Fehler pro Endpoint trennbar."""
        fp1 = _make_fingerprint("error", "app.main", "failed", "/api/a")
        fp2 = _make_fingerprint("error", "app.main", "failed", "/api/b")
        assert fp1 != fp2

    def test_deterministic(self):
        """Prüft dass der Fingerprint über mehrere Aufrufe deterministisch bleibt — keine Zufallskomponente."""
        results = set()
        for _ in range(10):
            results.add(_make_fingerprint("error", "logger", "msg", "/path"))
        assert len(results) == 1

    def test_returns_hex_string(self):
        """Prüft dass der Fingerprint ein 64-Zeichen Hex-String (SHA256) ist — konsistentes Format für DB-Speicherung."""
        fp = _make_fingerprint("error", "app.main", "test", "/api")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_none_path_handled(self):
        """Prüft dass None als Pfad ohne Exception verarbeitet wird — Fehler ohne Request-Kontext möglich."""
        fp = _make_fingerprint("error", "app.main", "test", None)
        assert isinstance(fp, str)
        assert len(fp) == 64


class TestScrubPath:
    """M-DSG4 (Review 2026-05-29): request paths must not persist raw UUIDs —
    the pseudonymous identifier the scrubber strips from message/traceback was
    leaking via the dedicated `path` column."""

    def test_uuid_in_path_is_scrubbed(self):
        import uuid
        from app.services.error_log_service import _scrub_path
        uid = str(uuid.uuid4())
        scrubbed = _scrub_path(f"/api/absences/{uid}")
        assert uid not in scrubbed
        assert "<id>" in scrubbed

    def test_path_without_uuid_unchanged(self):
        from app.services.error_log_service import _scrub_path
        assert _scrub_path("/api/health") == "/api/health"

    def test_none_path(self):
        from app.services.error_log_service import _scrub_path
        assert _scrub_path(None) is None

    def test_log_error_stores_scrubbed_path(self, db):
        import uuid
        from app.services.error_log_service import log_error
        uid = str(uuid.uuid4())
        entry = log_error(
            db, level="error", logger_name="test",
            message="boom", path=f"/api/admin/users/{uid}/journal",
        )
        assert uid not in (entry.path or "")
        assert "<id>" in entry.path
