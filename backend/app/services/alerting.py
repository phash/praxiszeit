"""Operator alerts (Slack webhook, optional — Phase 7 / Issue #98).

Fire-and-forget JSON POST to the configured Slack-incoming-webhook URL.
When ``SLACK_WEBHOOK_URL`` is unset, each call is a no-op so CI / local
work without a Slack workspace.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Optional

from app.config import settings


logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "SLACK_WEBHOOK_URL", None))


def alert(text: str, *, channel: Optional[str] = None) -> bool:
    """Post ``text`` to Slack. Returns True on success / dry-run."""
    url = getattr(settings, "SLACK_WEBHOOK_URL", None)
    if not url:
        logger.info("alerting (no Slack webhook configured): %s", text)
        return True

    payload: dict = {"text": text}
    if channel:
        payload["channel"] = channel
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.warning("alerting: Slack webhook failed: %s", exc)
        return False


# ───────────────── Convenience wrappers ─────────────────

def alert_new_signup(tenant_name: str) -> None:
    # M-DSG2: do NOT include the admin's email — Slack is an undisclosed
    # sub-processor (not in the AVV/VVT/DSFA), so no data-subject PII may leave
    # the instance. The practice name (business data) is sufficient signal.
    alert(f":tada: Neuer Signup: *{tenant_name}*")


def alert_plan_upgrade(tenant_name: str, new_plan: str) -> None:
    alert(f":rocket: Plan-Upgrade: *{tenant_name}* → {new_plan}")


def alert_past_due(tenant_name: str, days: int) -> None:
    alert(f":warning: Zahlung überfällig ({days} Tage): *{tenant_name}*")


def alert_deletion_requested(tenant_name: str) -> None:
    alert(f":wastebasket: Löschantrag: *{tenant_name}*")
