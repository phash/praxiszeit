"""Tests for the in-process daily job scheduler (Issue #126).

Hard requirement: the scheduler must NEVER start during a pytest run
(it would race against the SQLite test DB + the rotating per-test
fixtures). We patch ``_is_pytest_mode`` for the positive cases so we
can exercise the real ``start_scheduler`` path without contaminating
the rest of the suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import scheduler_service


@pytest.fixture(autouse=True)
def _reset_scheduler_module():
    """Ensure each test starts with a clean module-level scheduler."""
    scheduler_service._scheduler = None
    yield
    if scheduler_service._scheduler is not None:
        try:
            scheduler_service._scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        scheduler_service._scheduler = None


def test_start_scheduler_skipped_in_pytest_mode():
    """PYTEST_CURRENT_TEST is set by pytest itself → start_scheduler is a no-op.

    This is the safety guard the rest of the test suite relies on:
    nothing should be racing against SessionLocal once pytest hands
    control to FastAPI's TestClient lifespan.
    """
    result = scheduler_service.start_scheduler(app=MagicMock())
    assert result is None
    assert scheduler_service.get_scheduler() is None


def test_start_scheduler_registers_four_daily_cron_jobs():
    """Outside pytest mode, four cron-triggered jobs are registered."""
    with patch.object(scheduler_service, "_is_pytest_mode", return_value=False):
        sched = scheduler_service.start_scheduler(app=MagicMock())

    assert sched is not None
    try:
        jobs = sched.get_jobs()
        assert len(jobs) == 4

        job_ids = {j.id for j in jobs}
        assert job_ids == {
            scheduler_service.JOB_VACATION_AUDIT_PURGE,
            scheduler_service.JOB_APPLY_SCHEDULED_SUSPENDS,
            scheduler_service.JOB_APPLY_SCHEDULED_DELETIONS,
            scheduler_service.JOB_CLEANUP_OLD_ERRORS,
        }

        # Every job must be a daily cron at the documented time. We
        # introspect the CronTrigger's per-field representation rather
        # than touching private attributes — the public ``fields`` API
        # is APScheduler's stable contract.
        for job in jobs:
            trigger = job.trigger
            # CronTrigger exposes `.fields` as an ordered list of
            # BaseField objects; we look up by name to be position-safe.
            fields = {f.name: str(f) for f in trigger.fields}
            assert fields["hour"] == str(scheduler_service.DAILY_HOUR)
            assert fields["minute"] == str(scheduler_service.DAILY_MINUTE)
    finally:
        sched.shutdown(wait=False)


def test_start_scheduler_is_idempotent():
    """Calling twice returns the same instance (no duplicate jobs)."""
    with patch.object(scheduler_service, "_is_pytest_mode", return_value=False):
        first = scheduler_service.start_scheduler(app=MagicMock())
        second = scheduler_service.start_scheduler(app=MagicMock())

    try:
        assert first is second
        assert len(first.get_jobs()) == 4
    finally:
        first.shutdown(wait=False)


def test_vacation_audit_purge_job_calls_lifecycle_service():
    """The wrapper opens a DB session, sets superadmin context, and
    delegates to ``purge_expired_vacation_audit_logs``."""
    with patch.object(scheduler_service, "SessionLocal") as mock_session_cls, \
         patch.object(scheduler_service, "set_superadmin_context") as mock_set_ctx, \
         patch("app.services.lifecycle_service.purge_expired_vacation_audit_logs") as mock_purge:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_purge.return_value = 7

        scheduler_service._run_vacation_audit_purge()

        mock_session_cls.assert_called_once()
        mock_set_ctx.assert_called_once_with(mock_db)
        mock_purge.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()


def test_apply_scheduled_suspends_job_calls_lifecycle_service():
    with patch.object(scheduler_service, "SessionLocal") as mock_session_cls, \
         patch.object(scheduler_service, "set_superadmin_context") as mock_set_ctx, \
         patch("app.services.lifecycle_service.apply_scheduled_suspends") as mock_suspend:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_suspend.return_value = 2

        scheduler_service._run_apply_scheduled_suspends()

        mock_set_ctx.assert_called_once_with(mock_db)
        mock_suspend.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()


def test_apply_scheduled_deletions_job_calls_lifecycle_service():
    with patch.object(scheduler_service, "SessionLocal") as mock_session_cls, \
         patch.object(scheduler_service, "set_superadmin_context") as mock_set_ctx, \
         patch("app.services.lifecycle_service.apply_scheduled_deletions") as mock_delete:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_delete.return_value = 1

        scheduler_service._run_apply_scheduled_deletions()

        mock_set_ctx.assert_called_once_with(mock_db)
        mock_delete.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()


def test_cleanup_old_errors_job_calls_error_log_service():
    """The wrapper opens a DB session, sets superadmin context, and delegates
    to ``cleanup_old_errors`` with the 90-day cutoff (DSGVO Art. 5(1)(e))."""
    with patch.object(scheduler_service, "SessionLocal") as mock_session_cls, \
         patch.object(scheduler_service, "set_superadmin_context") as mock_set_ctx, \
         patch("app.services.error_log_service.cleanup_old_errors") as mock_cleanup:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_cleanup.return_value = 3

        scheduler_service._run_cleanup_old_errors()

        mock_set_ctx.assert_called_once_with(mock_db)
        mock_cleanup.assert_called_once_with(mock_db, max_age_days=90)
        mock_db.close.assert_called_once()


def test_job_swallows_exceptions_and_still_closes_session():
    """One failing job must not crash the scheduler thread — verify
    the wrapper logs + still releases the DB session."""
    with patch.object(scheduler_service, "SessionLocal") as mock_session_cls, \
         patch.object(scheduler_service, "set_superadmin_context"), \
         patch(
             "app.services.lifecycle_service.purge_expired_vacation_audit_logs",
             side_effect=RuntimeError("simulated DB blip"),
         ):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # Must not raise.
        scheduler_service._run_vacation_audit_purge()

        mock_db.close.assert_called_once()


def test_stop_scheduler_handles_unstarted_scheduler():
    """No scheduler running → stop is a graceful no-op."""
    scheduler_service._scheduler = None
    scheduler_service.stop_scheduler()  # must not raise
    assert scheduler_service.get_scheduler() is None


def test_stop_scheduler_shuts_down_running_scheduler():
    with patch.object(scheduler_service, "_is_pytest_mode", return_value=False):
        sched = scheduler_service.start_scheduler(app=MagicMock())

    assert sched is not None
    scheduler_service.stop_scheduler()
    assert scheduler_service.get_scheduler() is None
