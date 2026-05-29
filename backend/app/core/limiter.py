from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """
    Extract the real client IP for rate limiting.

    Prefers X-Real-IP (set by nginx: `proxy_set_header X-Real-IP $remote_addr`)
    over X-Forwarded-For, because X-Forwarded-For can be spoofed by clients and
    contains the nginx container IP when running behind Docker Compose — which would
    make all users share a single rate-limit bucket.

    H2: client-supplied X-Real-IP / X-Forwarded-For are ONLY trusted when a
    reverse proxy we control fronts the app (``settings.trust_proxy_headers``).
    In native mode the app is directly exposed, so an attacker could otherwise
    spoof these headers to get a fresh per-IP bucket on every request and defeat
    the login rate limit — there we key on the real socket peer instead.
    """
    # Import here (not at module load) so tests can monkeypatch the setting.
    from app.config import settings

    if settings.trust_proxy_headers:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        # Fallback: first entry of X-Forwarded-For (proxy-controlled here).
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    # Native/direct (or no proxy header): trust only the real connection IP.
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip)
