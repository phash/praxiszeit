"""Log-Audit 2026-11-15 (Punkt 17, NET-3): ``frontend/src/utils/apiPaths.ts``
fuehrt die Basis-Routen, die das Backend mit ``"/"`` registriert; der
Request-Interceptor haengt dort den Schraegstrich an (sonst 307 + zweite
Anfrage). Dieser Abgleich faellt, sobald ein Router eine Basis-Route von ``"/"``
auf ``""`` umstellt oder eine neue ``"/"``-Route dazukommt, ohne die Liste
nachzuziehen.

Laeuft nur mit Quelltext des Frontends (Repo-Mount, GH-CI); im gebauten
Backend-Image fehlt ``frontend/`` -> skip.
"""
import re
from pathlib import Path

import pytest

from app.main import app

_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "apiPaths.ts"


def _frontend_routes() -> set[str]:
    text = _TS.read_text(encoding="utf-8")
    block = re.search(r"COLLECTION_ROUTES[^=]*=\s*new Set\(\[(.*?)\]\)", text, re.S)
    assert block, "COLLECTION_ROUTES nicht gefunden"
    return set(re.findall(r"'([^']+)'", block.group(1)))


def _backend_routes() -> set[str]:
    # Ueber das OpenAPI-Schema: app.routes enthaelt seit fastapi 0.138
    # verschachtelte _IncludedRouter statt flacher APIRoutes.
    out = set()
    for path in app.openapi()["paths"]:
        if path.startswith("/api/") and path.endswith("/") and "{" not in path:
            out.add(path[len("/api"):-1])
    return out


@pytest.mark.skipif(not _TS.is_file(), reason="Frontend-Quelltext nicht vorhanden")
def test_collection_routes_match_backend():
    assert _frontend_routes() == _backend_routes()
