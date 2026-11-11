"""Code-Review 2026-11-11 (ops-01, ops-17)."""
import pytest
from fastapi import HTTPException

from app.routers import import_xls


def test_confirm_import_translates_value_error_to_400(db, test_user, test_admin, monkeypatch):
    """ops-01: ValueError aus execute_import -> HTTP 400 mit detail, nicht 500."""
    def boom(**kwargs):
        raise ValueError("Import fehlgeschlagen: Sperre")

    monkeypatch.setattr(import_xls, "execute_import", boom)
    body = import_xls.ConfirmRequest(user_id=test_user.id, entries=[], overwrite=False)
    with pytest.raises(HTTPException) as ei:
        import_xls.confirm_import(body=body, db=db, current_admin=test_admin)
    assert ei.value.status_code == 400
    assert "Import fehlgeschlagen" in ei.value.detail
