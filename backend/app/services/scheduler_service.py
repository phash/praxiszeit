"""Autonomous daily background jobs for tenant lifecycle + DSGVO
retention (Issue #126).

Why an in-process scheduler?
----------------------------
The lifecycle / vacation-audit-purge functions were exposed as a
superadmin POST /cron/trial-check endpoint that an external cron had
to call. On-prem installations and the SaaS instance in practice never
got a real cron wired up, so:

* ``purge_expired_vacation_audit_logs`` (DSGVO Art. 5 (1) e —
  Speicherbegrenzung) never ran.
* ``apply_scheduled_suspends`` / ``apply_scheduled_deletions``
  (Issue #97 Phase 6 — self-service suspend & delete) silently
  drifted into "queued forever" state.

We pull the schedule into the FastAPI process via APScheduler 3.x's
``BackgroundScheduler``. Pros:

* One source of truth — the same artefact runs on-prem (no
  systemd-timer required) and on SaaS (no Kubernetes CronJob).
* Failure isolation per job: each job opens its own ``SessionLocal``
  with ``set_superadmin_context`` (RLS bypass for tenant-wide queries)
  and catches its own exceptions so a single failing job doesn't take
  down the others.
* Test-time isolation via ``PYTEST_CURRENT_TEST`` guard — we never
  start the scheduler against a SQLite test DB.

The manual cron endpoint stays in place for ops to trigger ad-hoc.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI

from app.database import SessionLocal, set_superadmin_context

logger = logging.getLogger(__name__)

# Module-level so start_scheduler / stop_scheduler can share state.
_scheduler = None  # type: Optional[object]


# ───────────────── Job wrappers ──────────────────────────────────────
#
# Each job opens its own DB session and sets a superadmin RLS context.
# The lifecycle queries span tenants (e.g. all tenants whose
# scheduled_suspend_at is due) so a per-tenant context would short-
# circuit the result set to zero rows.

def _run_vacation_audit_purge() -> None:
    from app.services.lifecycle_service import purge_expired_vacation_audit_logs
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        deleted = purge_expired_vacation_audit_logs(db)
        if deleted:
            logger.info(
                "scheduler: purged %d expired vacation-audit rows", deleted
            )
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: purge_expired_vacation_audit_logs failed")
    finally:
        db.close()


def _run_apply_scheduled_suspends() -> None:
    from app.services.lifecycle_service import apply_scheduled_suspends
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        n = apply_scheduled_suspends(db)
        if n:
            logger.info("scheduler: suspended %d tenants", n)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: apply_scheduled_suspends failed")
    finally:
        db.close()


def _run_apply_scheduled_deletions() -> None:
    from app.services.lifecycle_service import apply_scheduled_deletions
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        n = apply_scheduled_deletions(db)
        if n:
            logger.info("scheduler: anonymized %d tenants", n)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: apply_scheduled_deletions failed")
    finally:
        db.close()


def _run_cleanup_old_errors() -> None:
    """DSGVO Art. 5 Abs. 1 lit. e Speicherbegrenzung: purge resolved/ignored
    error-log rows older than 90 days on a daily schedule.

    Startup-only cleanup (main.py step 5) only ran on (re)start; this daily job
    ensures the table doesn't accumulate unbounded over months without restarts.
    Note: only resolved/ignored rows are purged (same policy as the startup
    cleanup). 'open' rows are intentionally retained for triage — see the DSGVO
    recommendation to actively resolve/ignore them organisationally.
    """
    from app.services.error_log_service import cleanup_old_errors
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        # resolved/ignored: 90 days (same as startup cleanup)
        deleted = cleanup_old_errors(db, max_age_days=90)
        if deleted:
            logger.info("scheduler: purged %d resolved/ignored error-log rows (>90d)", deleted)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: cleanup_old_errors failed")
    finally:
        db.close()


def _run_suspend_expired_trials() -> None:
    """Fix #4: flip tenants whose free trial has ended (and who have no Stripe
    subscription) to ``subscription_status='suspended'``. SaaS billing
    enforcement — previously only reachable via the manual superadmin cron."""
    from app.services.signup_service import suspend_expired_trials
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        n = suspend_expired_trials(db)
        if n:
            logger.info("scheduler: suspended %d expired-trial tenants", n)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: suspend_expired_trials failed")
    finally:
        db.close()


def _run_suspend_canceled_after_grace() -> None:
    """Fix #4: flip tenants whose Stripe subscription has been canceled for
    longer than the grace period to ``subscription_status='suspended'``."""
    from app.services.stripe_service import suspend_canceled_after_grace
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        n = suspend_canceled_after_grace(db)
        if n:
            logger.info("scheduler: suspended %d canceled-after-grace tenants", n)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: suspend_canceled_after_grace failed")
    finally:
        db.close()


def _run_scheduled_backup() -> None:
    """#213: erstellt zur vom Admin konfigurierten Stunde ein DB-Backup, sofern
    aktiviert. Stuendlich getriggert (:30); der Job vergleicht die aktuelle
    Europe/Berlin-Stunde mit der Soll-Stunde -> feuert genau einmal pro Tag.
    Tz-explizit (zoneinfo), unabhaengig von der Container-TZ."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.config import settings
    from app.services import backup_service
    # Nativ (SERVE_FRONTEND=True): der systemd-/launchd-Backup-Timer ist der
    # Out-of-Box-Auto-Backup (laeuft unabhaengig von der App-/uvicorn-Uptime). Der
    # In-App-Scheduler wuerde sonst DOPPELT sichern (Review 2026-06-23) -> hier
    # ueberspringen. Manueller Trigger + Liste + Aufbewahrung gelten weiter; die
    # In-App-Zeitplan-Konfiguration steuert die Docker-Deployments.
    if getattr(settings, "SERVE_FRONTEND", False):
        return
    db = SessionLocal()
    try:
        set_superadmin_context(db)
        cfg = backup_service.get_config(db)
        if not cfg.enabled:
            return
        if datetime.now(ZoneInfo("Europe/Berlin")).hour != cfg.hour:
            return
        result = backup_service.create_backup(db)
        removed = backup_service.prune_old_backups(db)
        logger.info(
            "scheduler: backup %s (%d bytes), pruned %d old",
            result.filename, result.size_bytes, removed,
        )
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: scheduled_backup failed")
    finally:
        db.close()


# ───────────────── Public API (start / stop) ─────────────────────────

# Job-ID constants — tests assert against these names so the cron-trigger
# wiring is locked down.
JOB_VACATION_AUDIT_PURGE = "vacation_audit_purge"
JOB_APPLY_SCHEDULED_SUSPENDS = "apply_scheduled_suspends"
JOB_APPLY_SCHEDULED_DELETIONS = "apply_scheduled_deletions"
JOB_CLEANUP_OLD_ERRORS = "cleanup_old_errors"
JOB_SCHEDULED_BACKUP = "scheduled_backup"  # #213
JOB_SUSPEND_EXPIRED_TRIALS = "suspend_expired_trials"  # Fix #4 (saas only)
JOB_SUSPEND_CANCELED_AFTER_GRACE = "suspend_canceled_after_grace"  # Fix #4 (saas only)

# Daily run at 03:00 local time. Avoids the midnight rollover bookkeeping
# rush + leaves the cutoff math (``datetime.now() - timedelta(days=...)``)
# trivially correct.
DAILY_HOUR = 3
DAILY_MINUTE = 0


def _is_pytest_mode() -> bool:
    """Detect that we're inside a pytest run.

    ``PYTEST_CURRENT_TEST`` is set by pytest itself for every test item.
    It's not present during collection, so we additionally check the
    well-known ``PYTEST_VERSION`` env var pytest>=8 exports during the
    whole session, and ``sys.modules`` for the ``pytest`` import as a
    last resort (pytest is in our dev requirements, so the module being
    importable isn't enough on its own — must be actually loaded).
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if os.environ.get("PYTEST_VERSION"):
        return True
    import sys
    return "pytest" in sys.modules


def start_scheduler(app: FastAPI):  # noqa: ARG001  (kept for future use)
    """Build + start the background scheduler. Idempotent.

    Returns the scheduler instance (or ``None`` when skipped, e.g. in
    pytest). Stores it on the module so ``stop_scheduler`` can find it.
    """
    global _scheduler

    if _is_pytest_mode():
        logger.info("scheduler: pytest mode detected — not starting")
        return None

    if _scheduler is not None:
        logger.debug("scheduler: already started, returning existing instance")
        return _scheduler

    # Lazy import: keeps APScheduler off the dependency graph for
    # callers that just want to introspect the module (e.g. tests
    # mocking the scheduler).
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="Europe/Berlin")

    scheduler.add_job(
        _run_vacation_audit_purge,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
        id=JOB_VACATION_AUDIT_PURGE,
        name="DSGVO Art.5(1)(e): purge vacation-request audit rows >730d",
        replace_existing=True,
        coalesce=True,  # if missed (downtime), run once instead of catching up
        max_instances=1,
    )
    scheduler.add_job(
        _run_apply_scheduled_suspends,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
        id=JOB_APPLY_SCHEDULED_SUSPENDS,
        name="Lifecycle: flip tenants past scheduled_suspend_at to 'suspended'",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_apply_scheduled_deletions,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
        id=JOB_APPLY_SCHEDULED_DELETIONS,
        name="Lifecycle: anonymize tenants past deletion grace period",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_cleanup_old_errors,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
        id=JOB_CLEANUP_OLD_ERRORS,
        name="DSGVO Art.5(1)(e): purge resolved/ignored error-log rows >90d",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        _run_scheduled_backup,
        trigger=CronTrigger(minute=30),  # jede Stunde :30; Job prueft die Soll-Stunde
        id=JOB_SCHEDULED_BACKUP,
        name="#213: DB-Backup zur konfigurierten Stunde (wenn aktiviert)",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Fix #4: SaaS billing enforcement — these flip tenants to 'suspended' based
    # on Stripe/trial state and must NOT run on-prem (would suspend the single
    # on-prem tenant). Only registered in saas mode.
    from app.core.deployment import is_saas
    if is_saas():
        scheduler.add_job(
            _run_suspend_expired_trials,
            trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
            id=JOB_SUSPEND_EXPIRED_TRIALS,
            name="Billing: suspend tenants whose free trial has ended (no subscription)",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler.add_job(
            _run_suspend_canceled_after_grace,
            trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
            id=JOB_SUSPEND_CANCELED_AFTER_GRACE,
            name="Billing: suspend tenants canceled past the grace period",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler: started — %d jobs registered (daily %02d:%02d Europe/Berlin)",
        len(scheduler.get_jobs()),
        DAILY_HOUR,
        DAILY_MINUTE,
    )
    return scheduler


def stop_scheduler() -> None:
    """Graceful shutdown for FastAPI lifespan exit."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler: shut down")
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: shutdown failed")
    finally:
        _scheduler = None


def get_scheduler():
    """Test/debug accessor — returns the live scheduler or ``None``."""
    return _scheduler
