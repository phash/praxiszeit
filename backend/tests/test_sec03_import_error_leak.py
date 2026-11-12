"""SEC-03: unerwartete Fehler im XLS-Import dürfen keinen SQL-/Constraint-Text ausliefern."""
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.routers import import_xls
from app.services import xls_import_service as svc
from app.models import TimeEntryAuditLog


def _run(db, user, admin):
    body = import_xls.ConfirmRequest(user_id=user.id, entries=[], overwrite=False)
    with pytest.raises(HTTPException) as ei:
        import_xls.confirm_import(body=body, db=db, current_admin=admin)
    return ei.value


def test_integrity_error_text_is_not_leaked(db, test_user, test_admin, monkeypatch):
    def boom(**kw):
        raise IntegrityError("INSERT INTO time_entries (secret_col) VALUES (%s)", {}, Exception("uq_tenant_user_date_start"))
    monkeypatch.setattr(svc, "_execute_import_inner", boom)
    err = _run(db, test_user, test_admin)
    assert err.status_code == 400
    assert "INSERT" not in err.detail and "uq_tenant" not in err.detail and "secret_col" not in err.detail
    assert err.detail == svc.IMPORT_FAILED_DETAIL
    # Audit-Zeile behält die Details
    row = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.source == "import").first()
    assert row is not None and "FEHLGESCHLAGEN" in row.new_note and "IntegrityError" in row.new_note


def test_runtime_error_text_is_not_leaked(db, test_user, test_admin, monkeypatch):
    def boom(**kw):
        raise RuntimeError("connection to server at 10.0.0.5 failed")
    monkeypatch.setattr(svc, "_execute_import_inner", boom)
    assert _run(db, test_user, test_admin).detail == svc.IMPORT_FAILED_DETAIL


def test_domain_value_error_passes_through(db, test_user, test_admin, monkeypatch):
    def boom(**kw):
        raise ValueError("Die Pause nach § 4 ArbZG fehlt")
    monkeypatch.setattr(svc, "_execute_import_inner", boom)
    assert _run(db, test_user, test_admin).detail == "Die Pause nach § 4 ArbZG fehlt"
