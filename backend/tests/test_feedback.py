"""Tests für die In-App-Meldung (#136, #557): /api/feedback/preview + /send.

Der ausgehende Call (``report_client._transport``) wird immer gestubbt — kein
echter Meldeserver in Tests. Verifiziert: Vorschau = gesendet, kein Schlüssel in
Antworten, Admin-Sperren, Mandantenbezug der Fehlereinträge, 502-Mapping,
Anhangprüfung, Nur-Lese-Lizenz und der Altweg ohne Lizenz.
"""

import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.core import license as license_module
from app.models.error_log import ErrorLog
from app.services.report_payload import BOARD_URL

REPORT_KEY = "mrk_praxiszeit_" + "Tok" + "en123456789abcdef"
INSTALL_ID = "11111111-1111-4111-8111-111111111111"
TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32

BASE_PREVIEW = {"kind": "bug", "title": "Es hakt", "text": "Beim Stempeln passiert X",
                "severity": "high"}


def _create_test_app() -> FastAPI:
    from app.routers import feedback
    from app.core.limiter import limiter
    from app.middleware.license import LicenseReadOnlyMiddleware
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI(title="PraxisZeit Feedback Test")
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(LicenseReadOnlyMiddleware)
    app.include_router(feedback.router)
    return app


_app = _create_test_app()


def _patch_post(monkeypatch, response=None, exc=None):
    from tests.report_transport_stub import install
    return install(monkeypatch, exc if exc is not None else response)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.services import report_payload
    monkeypatch.setattr(report_payload, "get_or_create_install_id", lambda: INSTALL_ID)
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    monkeypatch.setattr(settings, "BETA_MODE", True)
    monkeypatch.setattr(settings, "SERVE_FRONTEND", False)
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", REPORT_KEY)
    monkeypatch.setattr(license_module, "get_current_license", lambda: None)
    yield


def _client_for(db, user):
    from app.database import get_db
    from app.middleware.auth import get_current_user
    _app.dependency_overrides[get_db] = lambda: db
    _app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(_app)


@pytest.fixture
def admin_client(db, test_admin):
    yield _client_for(db, test_admin)
    _app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, test_user):
    yield _client_for(db, test_user)
    _app.dependency_overrides.clear()


def _send(client, payload, attachment=None):
    files = {"attachment": attachment} if attachment is not None else None
    return client.post("/api/feedback/send", data={"payload": json.dumps(payload)}, files=files)


def _send_body(preview, **extra):
    body = {"kind": "bug", "title": preview["title"], "description": preview["description"],
            "severity": "high"}
    body.update(extra)
    return body


def _error_row(db, tenant, **kw):
    row = ErrorLog(tenant_id=tenant, level="error", logger="app", message="boom",
                   fingerprint=kw.pop("fingerprint", "a" * 64), count=1, path="/api/x",
                   method="GET", status_code=500, traceback="tb1\ntb2",
                   last_seen=datetime.now(timezone.utc), **kw)
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------- preview

def test_preview_returns_exact_fields_without_credential(admin_client):
    resp = admin_client.post("/api/feedback/preview",
                             json={**BASE_PREVIEW, "contact_email": "a@example.com"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transport"] == "mrd-report-1"
    assert body["credential_note"] == "mrk_praxiszeit_… (nicht angezeigt)"
    assert body["board_url"] == BOARD_URL
    assert body["contact_email_dropped"] is False
    f = body["fields"]
    assert "credential" not in f
    assert REPORT_KEY not in resp.text
    assert f["title"] == body["title"] == "Es hakt"
    assert f["description"] == body["description"]
    assert body["description"].startswith("Beim Stempeln passiert X\n\n---- Kontext (automatisch) ----")
    assert f["protocol"] == "mrd-report-1" and f["product"] == "praxiszeit"
    assert f["install_id"] == INSTALL_ID and f["kind"] == "bug" and f["severity"] == "high"
    assert f["contact_email"] == "a@example.com"
    # Review F15: Lizenzkennung nie in Vorschau/Datei, erst beim Senden ergänzt
    assert "license_id" not in f
    assert body["license_note"] == "Lizenzkennung der Praxis (wird beim Senden ergänzt, nicht angezeigt)"
    assert body["log_line_count"] == 0 and body["truncated"] is False


def test_preview_reports_legacy_transport_without_key(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    resp = admin_client.post("/api/feedback/preview",
                             json={**BASE_PREVIEW, "contact_email": "a@example.com"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transport"] == "legacy"
    assert body["credential_note"] is None
    assert body["contact_email_dropped"] is True
    assert set(body["fields"]) == {"title", "description", "app_version", "os", "severity"}


def test_preview_rejects_user_text_over_4000(admin_client):
    resp = admin_client.post("/api/feedback/preview", json={**BASE_PREVIEW, "text": "x" * 4001})
    assert resp.status_code == 422


def test_preview_rejects_server_error_path_outside_api(admin_client):
    resp = admin_client.post("/api/feedback/preview", json={
        **BASE_PREVIEW, "kind": "crash",
        "server_error": {"status": 500, "method": "GET", "path": "/etc/passwd"}})
    assert resp.status_code == 422


def test_preview_log_extract_masks_names_and_notes(admin_client, monkeypatch, tmp_path):
    # Review F5: Ausnahmetexte und Importdateinamen landen in service-stderr.log
    (tmp_path / "service-stderr.log").write_text("\n".join([
        "2026-11-18 08:20:00 ERROR app.services.xls_import_service: XLS-Import fehlgeschlagen "
        "(Datei Zeiten Anna Schmidt.xls)",
        "Traceback (most recent call last):",
        '  File "/app/app/services/xls_import_service.py", line 3, in parse',
        "KeyError: 'Weber'",
        "ValueError: invalid literal for int() with base 10: 'Anna Schmidt'",
        "sqlalchemy.exc.DataError: (psycopg.errors.InvalidTextRepresentation) Lisa Braun",
        "praxis_name = Praxis Dr. Weber",
    ]) + "\n", encoding="utf-8")
    (tmp_path / "praxiszeit.log").write_text("\n".join([
        "2026-11-18 08:15:02 WARNING praxiszeit.security: AUTH login_failed user=anna.schmidt "
        "reason=bad_password ip=192.168.178.20",
        "2026-11-18 08:16:00 INFO:     192.168.178.20:51234 - \"GET /api/admin/users?search="
        "Schmidt&include_inactive=true HTTP/1.1\" 200",
        "  String should have at most 500 characters [type=string_too_long, input_value="
        "'Arzttermin bei Dr. Weber wegen Rücken', input_type=str]",
        "{'type': 'string_too_long', 'loc': ('body', 'note'), 'msg': 'String should have at "
        "most 500 characters', 'input': 'Kind krank, Schule angerufen'}",
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(settings, "SERVE_FRONTEND", True)
    monkeypatch.setattr(settings, "REPORT_LOG_DIR", str(tmp_path))
    resp = admin_client.post("/api/feedback/preview", json={**BASE_PREVIEW, "include_log": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    desc = body["description"]
    assert "[praxiszeit.log]" in desc and body["log_line_count"] > 0
    for needle in ("anna.schmidt", "Arzttermin", "Schmidt", "Kind krank", "Anna", "Weber",
                   "Lisa Braun"):
        assert needle not in desc, needle
    assert "XLS-Import fehlgeschlagen (Datei <text>)" in desc
    assert "KeyError: <text>" in desc and "Traceback (most recent call last):" in desc


def test_employee_cannot_include_log_or_send_crash(employee_client, db):
    for extra in ({"include_log": True}, {"kind": "crash"},
                  {"error_log_id": str(uuid.uuid4())},
                  {"server_error": {"status": 500, "method": "GET", "path": "/api/x"}}):
        resp = employee_client.post("/api/feedback/preview", json={**BASE_PREVIEW, **extra})
        assert resp.status_code == 403, extra
        assert resp.json()["detail"] == "Nur für Administratoren."
    resp = _send(employee_client, {"kind": "crash", "title": "T", "description": "D"})
    assert resp.status_code == 403
    # a plain bug report stays allowed for employees
    assert employee_client.post("/api/feedback/preview", json=BASE_PREVIEW).status_code == 200


def test_error_log_id_of_other_tenant_is_404(admin_client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    foreign = _error_row(db, OTHER)
    resp = admin_client.post("/api/feedback/preview",
                             json={**BASE_PREVIEW, "kind": "crash", "error_log_id": str(foreign.id)})
    assert resp.status_code == 404
    unknown = admin_client.post("/api/feedback/preview",
                                json={**BASE_PREVIEW, "kind": "crash",
                                      "error_log_id": str(uuid.uuid4())})
    assert unknown.status_code == 404
    own = _error_row(db, TENANT, fingerprint="b" * 64)
    ok = admin_client.post("/api/feedback/preview",
                           json={**BASE_PREVIEW, "kind": "crash", "error_log_id": str(own.id)})
    assert ok.status_code == 200
    assert ok.json()["fields"]["error_fingerprint"] == "b" * 64


def test_error_log_id_onprem_finds_null_tenant_row(admin_client, db):
    row = _error_row(db, None, fingerprint="c" * 64)
    resp = admin_client.post("/api/feedback/preview",
                             json={**BASE_PREVIEW, "kind": "crash", "error_log_id": str(row.id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"]["error_fingerprint"] == "c" * 64
    assert "Fehler: error HTTP 500 GET /api/x — boom" in body["description"]


def test_preview_server_error_hint_matches_own_tenant_row(admin_client, db):
    _error_row(db, TENANT, fingerprint="d" * 64)
    resp = admin_client.post("/api/feedback/preview", json={
        **BASE_PREVIEW, "kind": "crash",
        "server_error": {"status": 500, "method": "GET", "path": "/api/x"}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["fields"]["error_fingerprint"] == "d" * 64


# ---------------------------------------------------------------- send

def test_send_forwards_exactly_previewed_title_and_description(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(
        201, json={"id": "r-1", "ref": "PZ-42", "status": "received"}))
    preview = admin_client.post("/api/feedback/preview", json={
        **BASE_PREVIEW, "title": "Fehler bei anna@example.org", "contact_email": "a@example.com"}).json()
    assert "anna@example.org" not in preview["title"]
    resp = _send(admin_client, _send_body(preview, contact_email="a@example.com"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "received", "ref": "PZ-42", "id": "r-1",
                           "board_url": BOARD_URL}
    assert len(rec.calls) == 1
    assert rec.calls[0]["url"] == "https://report.mr-development.de/v1/reports"
    # Vorschau = Gesendetes, plus die serverseitig ergänzten Zugangsdaten
    # (Schlüssel, Lizenzkennung — Review F15), die nur als Hinweis sichtbar sind.
    assert rec.fields() == {**preview["fields"], "credential": REPORT_KEY, "license_id": "beta"}
    assert preview["license_note"] and preview["credential_note"]
    assert REPORT_KEY not in resp.text


def test_send_round_trip_long_title_with_email_is_byte_identical(admin_client, monkeypatch):
    """PZ-R9: preview -> send with the returned strings -> outbound byte-identical.
    The preview schema caps the title at 200 (brief), so a 250-char title is
    422; the round trip uses the longest accepted title (200 chars + e-mail)."""
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    long_title = "Fehler bei anna.schmidt@example.org " + "x" * 250
    too_long = admin_client.post("/api/feedback/preview",
                                 json={**BASE_PREVIEW, "title": long_title[:250]})
    assert too_long.status_code == 422
    preview = admin_client.post("/api/feedback/preview", json={
        **BASE_PREVIEW, "title": long_title[:200],
        "text": "Kontakt anna.schmidt@example.org, Ä ö ü ß – „Zitat“ " + "z" * 3900}).json()
    assert "anna.schmidt@example.org" not in preview["title"]
    assert "anna.schmidt@example.org" not in preview["description"]
    resp = _send(admin_client, _send_body(preview))
    assert resp.status_code == 200, resp.text
    sent = rec.fields()
    assert sent["title"].encode() == preview["title"].encode()
    assert sent["description"].encode() == preview["description"].encode()


def test_send_drops_error_fingerprint_for_non_admin(employee_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    body = {"kind": "bug", "title": "T", "description": "D", "error_fingerprint": "a" * 64}
    assert _send(employee_client, body).status_code == 200
    assert "error_fingerprint" not in rec.fields(0)


def test_send_keeps_error_fingerprint_for_admin(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    body = {"kind": "crash", "title": "T", "description": "D", "error_fingerprint": "a" * 64}
    assert _send(admin_client, body).status_code == 200
    assert rec.fields()["error_fingerprint"] == "a" * 64


def test_send_maps_upstream_failure_to_502_with_status(admin_client, monkeypatch):
    _patch_post(monkeypatch, response=httpx.Response(429, json={"detail": "slow down"}))
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D"})
    assert resp.status_code == 502
    assert resp.json() == {"detail": "slow down", "upstream_status": 429}


def test_send_offline_returns_502_without_upstream_status(admin_client, monkeypatch):
    _patch_post(monkeypatch, exc=httpx.ConnectTimeout("timeout"))
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["upstream_status"] is None and body["detail"]


def test_send_misconfigured_legacy_host_is_502(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    monkeypatch.setattr(settings, "FEEDBACK_SERVER_URL", "https://evil.example.com")
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D"})
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Meldeserver ist nicht korrekt konfiguriert.",
                           "upstream_status": None}
    assert rec.calls == []


def test_send_rejects_non_image_attachment(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    body = {"kind": "bug", "title": "T", "description": "D"}
    for att in (("a.txt", b"hello", "text/plain"),
                ("a.png", b"GIF89a....", "image/png"),          # wrong magic bytes
                ("a.jpg", PNG, "image/jpeg"),                     # magic of the other type
                ("a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024), "image/png")):
        resp = _send(admin_client, body, attachment=att)
        assert resp.status_code == 422, att[0]
        assert resp.json()["detail"] == "Nur PNG- oder JPEG-Bilder bis 5 MB."
    assert rec.calls == []


def test_send_renames_png_attachment(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x", "ref": "R"}))
    body = {"kind": "bug", "title": "T", "description": "D"}
    resp = _send(admin_client, body, attachment=("Mein Bild (Anna).png", PNG, "image/png"))
    assert resp.status_code == 200, resp.text
    assert rec.attachment() == ("screenshot.png", PNG, "image/png")
    resp = _send(admin_client, body, attachment=("x.jpeg", JPEG, "image/jpeg"))
    assert resp.status_code == 200
    assert rec.attachment(1) == ("screenshot.jpg", JPEG, "image/jpeg")


def test_send_resanitizes_tampered_text(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = _send(admin_client, {"kind": "bug", "title": "Mail anna@example.org",
                                "description": "Login user=anna.schmidt ip=192.168.178.20"})
    assert resp.status_code == 200
    sent = rec.fields()
    assert "anna@example.org" not in sent["title"]
    assert "192.168.178.20" not in sent["description"]


def test_send_rejects_invalid_payload_json(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = admin_client.post("/api/feedback/send", data={"payload": "{nope"})
    assert resp.status_code == 422
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D",
                                "error_fingerprint": "XYZ"})
    assert resp.status_code == 422
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "x" * 20001})
    assert resp.status_code == 422
    assert rec.calls == []


def test_feedback_routes_work_in_read_only_mode(admin_client, monkeypatch):
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x", "ref": "R"}))
    license_module.set_license_state(None, read_only=True)
    try:
        assert license_module.is_read_only()
        preview = admin_client.post("/api/feedback/preview", json=BASE_PREVIEW)
        assert preview.status_code == 200, preview.text
        resp = _send(admin_client, _send_body(preview.json()))
        assert resp.status_code == 200, resp.text
        assert len(rec.calls) == 1
    finally:
        license_module.set_license_state(None, read_only=False)


def test_legacy_no_license_non_beta_returns_400_without_upstream_call(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    monkeypatch.setattr(settings, "BETA_MODE", False)
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    preview = admin_client.post("/api/feedback/preview", json=BASE_PREVIEW)
    assert preview.status_code == 200 and preview.json()["transport"] == "legacy"
    resp = _send(admin_client, _send_body(preview.json()))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Ohne hinterlegte Lizenz ist keine Bug-Meldung möglich."
    assert rec.calls == []


def test_legacy_beta_sends_license_id_beta_to_v1_bugs(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "b-1"}))
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == "b-1" and resp.json()["ref"] is None
    assert rec.calls[0]["url"].endswith("/v1/bugs")
    assert rec.fields()["license_id"] == "beta"
    assert "credential" not in rec.fields()


def test_mrd_report_1_without_license_outside_beta_still_sends(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "BETA_MODE", False)
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x"}))
    resp = _send(admin_client, {"kind": "bug", "title": "T", "description": "D"})
    assert resp.status_code == 200
    assert "license_id" not in rec.fields()


def test_old_report_route_is_gone(admin_client):
    resp = admin_client.post("/api/feedback/report",
                             json={"title": "T", "description": "D", "severity": "low"})
    assert resp.status_code == 404


# --- Review F15: Lizenzkennung (Altweg: Zugangsdatum) nie ans Frontend --------

class _Lic:
    customer_id = "pz-0f0e0d0c-geheim"


@pytest.mark.parametrize("key", ["", REPORT_KEY])
def test_license_customer_id_never_reaches_the_client_but_is_sent(
    employee_client, monkeypatch, key
):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", key)
    monkeypatch.setattr(settings, "BETA_MODE", False)
    monkeypatch.setattr(license_module, "get_current_license", lambda: _Lic())
    preview = employee_client.post("/api/feedback/preview", json=BASE_PREVIEW)
    assert preview.status_code == 200, preview.text
    assert _Lic.customer_id not in preview.text
    assert "license_id" not in preview.json()["fields"]
    assert preview.json()["license_note"]
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "x", "ref": "R"}))
    resp = _send(employee_client, _send_body(preview.json()))
    assert resp.status_code == 200, resp.text
    assert _Lic.customer_id not in resp.text
    assert rec.fields()["license_id"] == _Lic.customer_id


def test_preview_without_any_license_has_no_license_note(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "BETA_MODE", False)
    body = admin_client.post("/api/feedback/preview", json=BASE_PREVIEW).json()
    assert body["license_note"] is None and "license_id" not in body["fields"]


# --- Review F21: Altweg kennt kein ``kind`` — die Art steht im Kontextblock ----

@pytest.mark.parametrize("kind,label", [("feedback", "Feedback"),
                                        ("crash", "Programmfehler (vom Programm vorgeschlagen)")])
def test_legacy_keeps_the_kind_in_the_description(admin_client, monkeypatch, kind, label):
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    body = admin_client.post("/api/feedback/preview",
                             json={**BASE_PREVIEW, "kind": kind}).json()
    assert body["description"].endswith(f"\nMeldungsart: {label}")
    rec = _patch_post(monkeypatch, response=httpx.Response(201, json={"id": "b"}))
    _send(admin_client, _send_body(body, kind=kind))
    assert f"Meldungsart: {label}" in rec.fields()["description"]


def test_kind_line_only_on_legacy_and_not_for_bug(admin_client, monkeypatch):
    mrd = admin_client.post("/api/feedback/preview",
                            json={**BASE_PREVIEW, "kind": "feedback"}).json()
    assert "Meldungsart" not in mrd["description"] and mrd["fields"]["kind"] == "feedback"
    monkeypatch.setattr(settings, "FEEDBACK_REPORT_KEY", "")
    bug = admin_client.post("/api/feedback/preview", json=BASE_PREVIEW).json()
    assert "Meldungsart" not in bug["description"]
