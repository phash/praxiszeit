"""
Tests for SPAFallbackMiddleware — the middleware that replaces nginx's
``try_files $uri $uri/ /index.html`` in native (SERVE_FRONTEND=True) mode.

The middleware must distinguish "navigation requests" (where falling back to
``index.html`` is correct) from "asset requests" (where falling back to HTML
breaks the page on stale-Service-Worker clients — a CSS link that resolves to
``text/html`` is rejected by the browser, leaving every navigation unstyled
until the user manually unregisters the SW).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from app.middleware.static_serving import (
    SecurityHeadersMiddleware,
    SPAFallbackMiddleware,
)


@pytest.fixture
def native_app(tmp_path):
    """Mini FastAPI app wired up like native mode: SecurityHeaders +
    SPAFallback middleware, /assets static mount, frontend dir on disk."""
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    index_html = b"<!doctype html><html><body><div id='root'></div></body></html>"
    (frontend_dir / "index.html").write_bytes(index_html)
    (frontend_dir / "favicon.ico").write_bytes(b"\x00\x00ICON")
    (frontend_dir / "manifest.webmanifest").write_text('{"name":"x"}')

    assets_dir = frontend_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "index-NEWHASH.css").write_text("body{color:red}")
    (assets_dir / "index-NEWHASH.js").write_text("console.log(1)")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    # Order matches main.py: SecurityHeaders added first, SPAFallback last
    # — Starlette wraps later-added middleware on the OUTSIDE, so SPAFallback
    # runs first on incoming, with SecurityHeaders below it in the stack.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        SPAFallbackMiddleware,
        frontend_dir=frontend_dir,
        index_html=index_html,
    )

    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    return TestClient(app)


# ---------------------------------------------------------------------------
# Asset 404 behaviour — root-cause fix for stale-Service-Worker breakage.
# ---------------------------------------------------------------------------

def test_missing_asset_in_assets_dir_returns_404(native_app):
    """Stale SW requests an old hashed CSS that no longer exists on disk.

    Must return a real 404, NOT index.html with text/html — otherwise the
    browser would receive HTML for a stylesheet request and silently fail to
    apply any styles, leaving the page unstyled until the SW is unregistered.
    """
    r = native_app.get(
        "/assets/index-OLDHASH123.css",
        headers={"accept": "text/css,*/*;q=0.1"},
    )
    assert r.status_code == 404, (
        f"Expected 404 for missing asset, got {r.status_code} "
        f"with Content-Type {r.headers.get('content-type')!r}"
    )
    assert "text/html" not in r.headers.get("content-type", "")


def test_missing_top_level_asset_with_extension_returns_404(native_app):
    """Top-level files with extensions (sw.js, robots.txt, foo.png) should
    surface 404 if missing — same reasoning: no HTML disguised as asset."""
    r = native_app.get("/some-bundle.js", headers={"accept": "*/*"})
    assert r.status_code == 404


def test_missing_asset_in_assets_dir_returns_404_even_without_accept(native_app):
    """Some HTTP clients send no Accept header; /assets/* paths must still
    short-circuit to 404 regardless — those URLs are reserved for hashed
    bundles and clients should never navigate to them."""
    r = native_app.get("/assets/missing.css")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Navigation behaviour — preserve the legitimate use of the SPA fallback.
# ---------------------------------------------------------------------------

def test_navigation_returns_index_html(native_app):
    """A real SPA navigation (Accept: text/html, no extension) must still
    return index.html so React Router can resolve the route on hard reload."""
    r = native_app.get(
        "/login",
        headers={"accept": "text/html,application/xhtml+xml"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert b"<div id='root'>" in r.content


def test_navigation_response_carries_security_headers(native_app):
    """The SPA fallback constructs its own Response inside dispatch() — it
    must still carry CSP/HSTS/X-Frame-Options, otherwise SPA pages ship
    without security headers while /assets/* pages have them. Defence-in-
    depth + parity with what nginx does in Docker mode."""
    r = native_app.get(
        "/login",
        headers={"accept": "text/html"},
    )
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers.get("content-security-policy", "")
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_existing_top_level_static_file_is_served(native_app):
    """favicon.ico / manifest.webmanifest live in the frontend root, not
    /assets/, and reach the middleware as 404 from the inner stack. They
    must be served from disk — that's the whole point of the file-on-disk
    branch in the middleware."""
    r = native_app.get("/favicon.ico")
    assert r.status_code == 200
    assert r.content == b"\x00\x00ICON"


def test_existing_assets_pass_through_unchanged(native_app):
    """Sanity: assets that DO exist are served by the StaticFiles mount
    and the middleware doesn't interfere."""
    r = native_app.get("/assets/index-NEWHASH.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert r.text == "body{color:red}"


def test_api_404_passes_through(native_app):
    """A 404 from /api/* must be returned as-is — falling back to
    index.html for missing API endpoints would mask backend bugs and
    confuse the frontend's error handling."""
    r = native_app.get("/api/does-not-exist")
    assert r.status_code == 404


def test_post_to_api_passes_through(native_app):
    """The middleware must only intercept GET — POST/PUT/DELETE to
    unknown paths should return Starlette's default 405/404 response,
    never index.html. Regression guard for the issue noted in CLAUDE.md
    ("SPA-Fallback: Middleware statt catch-all Route!")."""
    r = native_app.post("/some-route", json={})
    assert r.status_code in (404, 405)
    assert "text/html" not in r.headers.get("content-type", "")


def test_spa_route_with_dot_in_segment_falls_back_to_html(native_app):
    """Edge case: SPA routes can legitimately contain a dot
    (``/users/john.doe``). When the client sends Accept: text/html, the
    middleware must still serve index.html — the dot alone shouldn't
    disqualify it as a navigation target."""
    r = native_app.get(
        "/users/john.doe",
        headers={"accept": "text/html,application/xhtml+xml"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
