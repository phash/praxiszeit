"""#483 gegen **echtes PostgreSQL**: eine ungueltige ID wird zu 422, nicht 500.

SQLite nimmt einen Nicht-UUID-String in einer UUID-Spalte an — der Fehler
existiert dort nicht. Diese Datei belegt, dass PostgreSQL genau den SQLSTATE
liefert, auf den ``app.core.db_errors`` reagiert, und dass der Handler die
echte Ausnahme in eine 422 uebersetzt.

Laeuft nur mit erreichbarem PostgreSQL (modulweiter Skip wie
``test_concurrency.py``). Eingehaengt in ``scripts/local-ci.sh`` Schritt 2 und
in den PostgreSQL-Schritt von ``.github/workflows/cross-tenant-ci.yml``.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DataError
from sqlalchemy.orm import sessionmaker

ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_DB_URL:
    pytest.skip(
        "test_invalid_uuid_postgres.py braucht DATABASE_URL_MIGRATIONS "
        "(oder ADMIN_DB_URL); Aufruf mit `docker compose exec backend pytest …`.",
        allow_module_level=True,
    )

from app.core.db_errors import INVALID_TEXT_REPRESENTATION, invalid_text_representation_handler
from app.models import User


@pytest.fixture(scope="module")
def session():
    eng = create_engine(ADMIN_DB_URL)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()
    eng.dispose()


def _raise_for_malformed_id(session) -> DataError:
    with pytest.raises(DataError) as info:
        session.query(User).filter(User.id == "xyz").first()
    session.rollback()
    return info.value


def test_postgres_reports_invalid_text_representation(session):
    exc = _raise_for_malformed_id(session)
    assert getattr(exc.orig, "pgcode", None) == INVALID_TEXT_REPRESENTATION


def test_handler_turns_the_real_error_into_422(session):
    exc = _raise_for_malformed_id(session)
    response = asyncio.run(invalid_text_representation_handler(None, exc))
    assert response.status_code == 422
    assert "Ungültige ID" in json.loads(response.body)["detail"]
