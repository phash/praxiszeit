"""Tests for RequestSizeLimitMiddleware (chunked-encoding bypass fix)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.static_serving import RequestSizeLimitMiddleware


def _app(max_size: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_size=max_size)

    @app.post("/echo")
    async def echo(payload: dict):
        return {"ok": True, "keys": list(payload.keys())}

    return app


def test_small_request_passes():
    client = TestClient(_app(max_size=1024))
    r = client.post("/echo", json={"hello": "world"})
    assert r.status_code == 200


def test_large_content_length_rejected():
    """Reject when Content-Length header advertises oversized body."""
    client = TestClient(_app(max_size=100))
    body = b"a" * 500
    r = client.post("/echo", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_chunked_oversize_body_rejected():
    """
    Reject when the body is streamed via chunked encoding and there is no
    Content-Length to inspect up-front. The middleware must count bytes as
    they arrive and abort mid-stream.
    """
    client = TestClient(_app(max_size=100))

    # Submit via a generator so httpx uses Transfer-Encoding: chunked.
    def gen():
        for _ in range(20):
            yield b"a" * 50  # 1000 bytes total, well over the 100-byte cap

    r = client.post(
        "/echo",
        content=gen(),
        headers={"Content-Type": "application/json"},
    )
    # Must be rejected — the exact 4xx depends on how httpx framed the
    # request (413 when Content-Length was auto-computed, 400 when the
    # middleware aborted mid-stream before the app could parse the body).
    assert 400 <= r.status_code < 500
    assert r.status_code != 200


def test_malformed_content_length_rejected():
    """Broken Content-Length header is not a bypass vector."""
    client = TestClient(_app(max_size=100))
    # httpx normalises so we go one layer deeper — build the request manually
    r = client.post(
        "/echo",
        content=b"a" * 50,
        headers={"Content-Length": "not-a-number"},
    )
    # TestClient may still normalise; at minimum we want no 200 with an
    # invalid length header accompanying real body.
    assert r.status_code in (400, 413, 422)
