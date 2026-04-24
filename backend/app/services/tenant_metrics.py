"""Per-tenant Prometheus metrics (Phase 7 / Issue #98).

Exposed as the standard Prometheus metric objects so the existing
``prometheus_fastapi_instrumentator`` endpoint picks them up without
any additional wiring.

We use labels {tenant_id} sparingly — Prometheus cardinality guidance
is to keep label values in the low thousands. Since each PraxisZeit
tenant is a paying customer, that's inherently bounded.
"""

from prometheus_client import Counter, Gauge


# Per-tenant API request counter. Labelled by tenant_id + route template
# (the instrumentator already groups paths, we add the tenant dimension
# via a middleware below).
praxiszeit_tenant_api_requests_total = Counter(
    "praxiszeit_tenant_api_requests_total",
    "HTTP requests handled by API, per tenant.",
    ["tenant_id", "method"],
)

praxiszeit_tenant_dau = Gauge(
    "praxiszeit_tenant_dau",
    "Daily active users per tenant (unique users in the last 24 h).",
    ["tenant_id"],
)

praxiszeit_tenant_employees = Gauge(
    "praxiszeit_tenant_employees",
    "Active employees per tenant right now.",
    ["tenant_id"],
)

praxiszeit_tenant_storage_bytes = Gauge(
    "praxiszeit_tenant_storage_bytes",
    "Approximate storage used per tenant (bytes).",
    ["tenant_id"],
)

# Billing KPIs — tenant-agnostic but updated by the same refresh job.
praxiszeit_mrr_cents = Gauge(
    "praxiszeit_mrr_cents",
    "Monthly recurring revenue in cents across all active subscriptions.",
)

praxiszeit_active_tenants = Gauge(
    "praxiszeit_active_tenants",
    "Number of tenants with subscription_status='active'.",
)

praxiszeit_trial_tenants = Gauge(
    "praxiszeit_trial_tenants",
    "Number of tenants currently on the trial plan.",
)


def record_request(tenant_id: str | None, method: str) -> None:
    """Increment the per-tenant request counter. ``None`` tenant_id means
    the request was unauthenticated (public signup, health, webhook);
    we record it under the literal ``"none"`` label so the metric is
    still queryable."""
    praxiszeit_tenant_api_requests_total.labels(
        tenant_id=tenant_id or "none",
        method=method,
    ).inc()
