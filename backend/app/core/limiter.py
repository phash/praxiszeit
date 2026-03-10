from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    """
    Extract the real client IP for rate limiting.

    Prefers X-Real-IP (set by nginx: `proxy_set_header X-Real-IP $remote_addr`)
    over X-Forwarded-For, because X-Forwarded-For can be spoofed by clients and
    contains the nginx container IP when running behind Docker Compose — which would
    make all users share a single rate-limit bucket.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Fallback: first entry of X-Forwarded-For (may be spoofable without proper proxy config)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    # Last resort: direct connection IP
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip)
