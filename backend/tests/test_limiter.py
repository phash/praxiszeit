"""Rate-limit client-IP resolution (H2, Review 2026-05-29).

In native mode the app is directly exposed; a client can spoof X-Real-IP /
X-Forwarded-For to rotate rate-limit buckets and defeat the login limit. The
key function must therefore ignore those headers unless a trusted reverse proxy
fronts the app.
"""
from types import SimpleNamespace

import pytest

from app.core.limiter import _get_real_ip


def _req(headers: dict, peer: str = "203.0.113.9"):
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=peer),
    )


def test_trusts_x_real_ip_when_behind_proxy(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(type(cfg.settings), "trust_proxy_headers", property(lambda self: True))
    req = _req({"X-Real-IP": "10.0.0.5"}, peer="172.18.0.2")
    assert _get_real_ip(req) == "10.0.0.5"


def test_ignores_spoofed_headers_in_native_mode(monkeypatch):
    """trust_proxy_headers=False → spoofed X-Forwarded-For / X-Real-IP are
    ignored and the real socket peer is used, so spoofing can't rotate buckets."""
    import app.config as cfg
    monkeypatch.setattr(type(cfg.settings), "trust_proxy_headers", property(lambda self: False))
    spoofed = _req(
        {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"},
        peer="203.0.113.9",
    )
    assert _get_real_ip(spoofed) == "203.0.113.9"
