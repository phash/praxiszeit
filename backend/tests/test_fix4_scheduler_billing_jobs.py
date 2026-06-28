"""Fix #4: the background scheduler must register the SaaS billing-enforcement
jobs (suspend expired trials / canceled-after-grace) — and only in saas mode.
"""
import app.core.deployment as deployment
from app.services import scheduler_service
from app.services.scheduler_service import (
    start_scheduler, stop_scheduler,
    JOB_SUSPEND_EXPIRED_TRIALS, JOB_SUSPEND_CANCELED_AFTER_GRACE,
    JOB_VACATION_AUDIT_PURGE,
)


def _job_ids(sched):
    return {j.id for j in sched.get_jobs()}


def test_billing_jobs_registered_in_saas(monkeypatch):
    monkeypatch.setattr(scheduler_service, "_is_pytest_mode", lambda: False)
    monkeypatch.setattr(deployment, "is_saas", lambda: True)
    scheduler_service._scheduler = None
    try:
        sched = start_scheduler(None)
        ids = _job_ids(sched)
        assert JOB_SUSPEND_EXPIRED_TRIALS in ids
        assert JOB_SUSPEND_CANCELED_AFTER_GRACE in ids
        # base lifecycle jobs still present
        assert JOB_VACATION_AUDIT_PURGE in ids
    finally:
        stop_scheduler()


def test_billing_jobs_absent_in_onprem(monkeypatch):
    monkeypatch.setattr(scheduler_service, "_is_pytest_mode", lambda: False)
    monkeypatch.setattr(deployment, "is_saas", lambda: False)
    scheduler_service._scheduler = None
    try:
        sched = start_scheduler(None)
        ids = _job_ids(sched)
        assert JOB_SUSPEND_EXPIRED_TRIALS not in ids
        assert JOB_SUSPEND_CANCELED_AFTER_GRACE not in ids
        # base lifecycle jobs unaffected
        assert JOB_VACATION_AUDIT_PURGE in ids
    finally:
        stop_scheduler()
