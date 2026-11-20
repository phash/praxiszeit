"""Task 5 (#557): payload builder."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core.report_sanitize_pz import sanitize_praxiszeit_text
from app.models.error_log import ErrorLog
from app.services import report_payload as rp
from app.services.report_payload import (
    DESCRIPTION_MAX, ErrorContext, ServerErrorHint, ServerFields, build_fields,
    build_preview, collect_server_fields, compose_description,
    resolve_error_context,
)

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 11, 18, 8, 15, 2, tzinfo=timezone.utc)
SRV = ServerFields("1.24.3", "linux", "stable", "Linux 6.1/x86_64", "docker",
                   "11111111-1111-4111-8111-111111111111", None)


def test_compose_matches_spec_layout():
    d = compose_description("Hallo", server=SRV, now_utc=NOW,
                            error_line="HTTP 500 GET /api/x", log_lines=["a", "b"])
    assert d == (
        "Hallo\n\n---- Kontext (automatisch) ----\n"
        "Produkt: PraxisZeit 1.24.3 (stable)\n"
        "System: Linux 6.1/x86_64, Installationsart: docker\n"
        "Zeit: 2026-11-18T08:15:02Z\n"
        "Fehler: HTTP 500 GET /api/x\n"
        "Protokoll (bereinigt, letzte 2 Zeilen):\na\nb"
    )
    d2 = compose_description("Hallo", server=SRV, now_utc=NOW, error_line=None, log_lines=None)
    assert "Fehler:" not in d2 and "Protokoll" not in d2
    assert d2.endswith("Zeit: 2026-11-18T08:15:02Z")


def test_preview_sanitizes_whole_description_once():
    p = build_preview(title="t", user_text="mail anna@praxis.de", server=SRV, now_utc=NOW,
                      error=None, log_lines=["login user=anna failed"])
    assert "<email>" in p.description and "anna@praxis.de" not in p.description
    assert "user=<user>" in p.description
    assert sanitize_praxiszeit_text(p.description) == p.description
    assert p.log_line_count == 1 and not p.truncated


def test_description_never_exceeds_limit_with_full_extract():
    lines = [f"line{i} " + "x" * 1990 for i in range(200)]
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=None, log_lines=lines)
    assert len(p.description) <= DESCRIPTION_MAX and p.truncated
    assert 0 < p.log_line_count < 200
    assert f"letzte {p.log_line_count} Zeilen" in p.description
    assert "line199" in p.description and "line0 " not in p.description


def test_title_over_limit_after_sanitize_is_cut_to_200():
    p = build_preview(title="  " + "Fehler beim Speichern " * 20 + "  ", user_text="u", server=SRV, now_utc=NOW,
                      error=None, log_lines=None)
    assert len(p.title) == 200 and p.title.endswith("…")


def test_error_detail_lines_come_first():
    e = ErrorContext("HTTP 500 GET /x", "fp", ["tb1", "tb2"])
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=e, log_lines=["l1"])
    assert "Fehler: HTTP 500 GET /x" in p.description
    assert p.description.endswith("tb1\ntb2\nl1") and p.log_line_count == 3
    p2 = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=e, log_lines=None)
    assert p2.log_line_count == 2 and "letzte 2 Zeilen" in p2.description


def test_build_fields_mrd_report_1_has_no_credential_and_omits_empty_optionals():
    f = build_fields(transport="mrd-report-1", kind="bug", title="T", description="D",
                     severity="medium", contact_email=None, error_fingerprint=None, server=SRV)
    assert f == {"protocol": "mrd-report-1", "product": "praxiszeit", "install_id": SRV.install_id,
                 "kind": "bug", "title": "T", "description": "D", "app_version": "1.24.3",
                 "os": "linux", "channel": "stable", "severity": "medium"}
    srv = ServerFields(**{**SRV.__dict__, "license_id": "pz-1"})
    f2 = build_fields(transport="mrd-report-1", kind="crash", title="T", description="D",
                      severity="high", contact_email="a@b.de", error_fingerprint="fp", server=srv)
    assert f2["license_id"] == "pz-1" and f2["contact_email"] == "a@b.de"
    assert f2["error_fingerprint"] == "fp" and "credential" not in f2


def test_build_fields_legacy_shape():
    srv = ServerFields(**{**SRV.__dict__, "license_id": "beta"})
    f = build_fields(transport="legacy", kind="bug", title="T", description="D",
                     severity="low", contact_email="a@b.de", error_fingerprint="fp", server=srv)
    assert f == {"license_id": "beta", "title": "T", "description": "D",
                 "app_version": "1.24.3", "os": "linux", "severity": "low"}


def _row(db, tenant, **kw):
    kw.setdefault("last_seen", NOW - timedelta(minutes=1))
    row = ErrorLog(tenant_id=tenant, level="error", logger="app", message="boom\nmore",
                   fingerprint=kw.pop("fingerprint", "f" * 64), count=2,
                   path=kw.pop("path", "/api/x"), method="GET", status_code=500,
                   traceback="\n".join(f"tb{i}" for i in range(100)), **kw)
    db.add(row)
    db.commit()
    return row


def test_resolve_error_context_by_id_is_tenant_scoped(db, default_tenant):
    row = _row(db, TENANT)
    ctx = resolve_error_context(db, TENANT, error_log_id=row.id, server_error=None, now=NOW)
    assert ctx.fingerprint == "f" * 64 and len(ctx.detail_lines) == 60
    assert ctx.line == "error HTTP 500 GET /api/x — boom (2x, zuletzt 2026-11-18T08:14:02Z)"
    with pytest.raises(LookupError):
        resolve_error_context(db, OTHER, error_log_id=row.id, server_error=None, now=NOW)
    with pytest.raises(LookupError):
        resolve_error_context(db, TENANT, error_log_id=uuid.uuid4(), server_error=None, now=NOW)
    assert resolve_error_context(db, TENANT, error_log_id=None, server_error=None, now=NOW) is None


def test_resolve_server_error_matches_recent_row_by_scrubbed_path(db, default_tenant):
    uid = uuid.uuid4()
    _row(db, TENANT, path="/api/users/<id>/j", fingerprint="old" * 5,
         last_seen=NOW - timedelta(minutes=11))
    hint = ServerErrorHint(500, "GET", f"/api/users/{uid}/j")
    ctx = resolve_error_context(db, TENANT, error_log_id=None, server_error=hint, now=NOW)
    assert ctx.fingerprint is None and ctx.line == "HTTP 500 GET /api/users/<id>/j"
    _row(db, TENANT, path="/api/users/<id>/j", fingerprint="new" * 5)
    ctx = resolve_error_context(db, TENANT, error_log_id=None, server_error=hint, now=NOW)
    assert ctx.fingerprint == "new" * 5 and "boom" in ctx.line


def test_collect_server_fields_beta_and_license(monkeypatch):
    monkeypatch.setattr(rp, "get_or_create_install_id", lambda: "iid")
    monkeypatch.setattr(settings, "BETA_MODE", True)
    monkeypatch.setattr(rp.license_module, "get_current_license", lambda: None)
    assert collect_server_fields().license_id == "beta"
    monkeypatch.setattr(settings, "BETA_MODE", False)
    assert collect_server_fields().license_id is None
    monkeypatch.setattr(rp.license_module, "get_current_license",
                        lambda: SimpleNamespace(customer_id="pz-42"))
    s = collect_server_fields()
    assert s.license_id == "pz-42" and s.install_id == "iid"
    monkeypatch.setattr(settings, "SERVE_FRONTEND", True)
    assert collect_server_fields().install_type == "native"
    monkeypatch.setattr(settings, "SERVE_FRONTEND", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert collect_server_fields().channel == "dev" and collect_server_fields().install_type == "docker"


def test_resolve_by_id_uses_list_scope_null_tenant_and_onprem(db, default_tenant):
    null_row = _row(db, None, fingerprint="n" * 64)
    foreign = _row(db, OTHER, fingerprint="o" * 64)
    assert resolve_error_context(db, TENANT, error_log_id=null_row.id, server_error=None, now=NOW)
    with pytest.raises(LookupError):
        resolve_error_context(db, TENANT, error_log_id=foreign.id, server_error=None, now=NOW)
    # on-prem: tenant_id None = no filter
    assert resolve_error_context(db, None, error_log_id=foreign.id, server_error=None, now=NOW)


def test_block_capped_at_200_lines_total():
    e = ErrorContext("HTTP 500 GET /x", "fp", [f"tb{i}" for i in range(60)])
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=e,
                      log_lines=[f"log{i}" for i in range(200)])
    assert p.log_line_count == 200 and "letzte 200 Zeilen" in p.description
    assert "tb0\n" in p.description and "log59\n" not in p.description and "log199" in p.description


def test_truncation_drops_extract_before_traceback():
    e = ErrorContext("HTTP 500 GET /x", "fp", ["tb-keep-1", "tb-keep-2"])
    lines = [f"log{i} " + "x " * 995 for i in range(100)]
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=e, log_lines=lines)
    assert p.truncated and len(p.description) <= DESCRIPTION_MAX
    assert "tb-keep-1\ntb-keep-2\n" in p.description
    assert f"letzte {p.log_line_count} Zeilen" in p.description and p.log_line_count > 2
    big = ErrorContext("e", "fp", ["T" + str(i) + " " + "y " * 995 for i in range(30)])
    p2 = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=big, log_lines=["only"])
    assert p2.truncated and "only" not in p2.description and len(p2.description) <= DESCRIPTION_MAX
    assert "T29 " in p2.description and "T0 " not in p2.description


# --- Review F22: Installationsart „saas“ (Protokoll §7 docker|native|desktop|saas)

def test_install_type_is_saas_in_saas_mode(monkeypatch):
    monkeypatch.setattr(rp, "get_or_create_install_id", lambda: "iid")
    monkeypatch.setattr(rp.license_module, "get_current_license", lambda: None)
    monkeypatch.setattr(settings, "SERVE_FRONTEND", False)
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "saas")
    assert collect_server_fields().install_type == "saas"
    monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "onprem")
    assert collect_server_fields().install_type == "docker"


# --- Review F14: Fehlerzeilen ohne HTTP-Bezug (DBErrorHandler, Prüfung 03:15)

def test_error_context_without_http_columns_names_the_logger(db, default_tenant):
    row = ErrorLog(tenant_id=TENANT, level="CRITICAL", logger="app.audit_integrity",
                   message="Kette gebrochen", fingerprint="c" * 64, count=1,
                   last_seen=NOW - timedelta(minutes=1))
    db.add(row)
    db.commit()
    ctx = resolve_error_context(db, TENANT, error_log_id=row.id, server_error=None, now=NOW)
    assert "None" not in ctx.line and "HTTP" not in ctx.line
    assert ctx.line == ("CRITICAL app.audit_integrity — Kette gebrochen "
                        "(1x, zuletzt 2026-11-18T08:14:02Z)")


# --- Review F18: Kürzen hält Abschnittsköpfe und die neuesten Fehlerzeilen

def _native_extract(width=140):
    return (["[Fehler-Monitoring]"] + [f"err-new{i}" for i in range(20)]
            + ["[praxiszeit.log]"] + [f"pz-old{i} " + "p" * width for i in range(90)]
            + ["[service-stderr.log]"] + [f"st{i} " + "s" * width for i in range(88)])


def test_room_cut_keeps_headers_and_newest_error_rows():
    e = ErrorContext("HTTP 500 GET /x", "fp", [f"tb{i}" for i in range(10)])
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=e,
                      log_lines=_native_extract(width=10))
    d = p.description
    assert not p.truncated and p.log_line_count == 200
    assert "tb9\n[Fehler-Monitoring]\nerr-new0\n" in d
    assert "[praxiszeit.log]\n" in d and "[service-stderr.log]\n" in d
    assert "pz-old89 " in d and "st87 " in d
    assert "pz-old0 " not in d  # älteste Zeilen der größten Datei zuerst


def test_length_cut_keeps_headers_and_newest_error_rows():
    p = build_preview(title="t", user_text="u", server=SRV, now_utc=NOW, error=None,
                      log_lines=_native_extract())
    d = p.description
    assert p.truncated and len(d) <= DESCRIPTION_MAX
    assert "Zeilen):\n[Fehler-Monitoring]\nerr-new0\n" in d
    assert "err-new19\n" in d
    assert "[praxiszeit.log]\n" in d and "[service-stderr.log]\n" in d
    assert "pz-old89 " in d and "st87 " in d
    assert "pz-old0 " not in d and "st0 " not in d


# --- #557 D3: eine überlange Fehlermeldung sprengt die 20000 Zeichen nicht

def test_overlong_error_message_is_cut_and_description_stays_in_limit(db, default_tenant):
    row = _row(db, TENANT)
    row.message = "x" * 30000
    row.traceback = "tb " + "y" * 30000
    db.commit()
    ctx = resolve_error_context(db, TENANT, error_log_id=row.id, server_error=None, now=NOW)
    p = build_preview(title="t", user_text="u" * 4000, server=SRV, now_utc=NOW,
                      error=ctx, log_lines=None)
    assert len(p.description) <= DESCRIPTION_MAX
    assert len(ctx.line) <= rp.MAX_ERROR_MESSAGE_CHARS + 200
    assert "…" in ctx.line and ctx.line.endswith("(2x, zuletzt 2026-11-18T08:14:02Z)")
    assert all(len(l) <= 2001 for l in ctx.detail_lines)
