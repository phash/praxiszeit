"""Nutzer ohne Soll/Ist-Zeiterfassung (track_hours=False) — z.B. das technische
Bootstrap-Admin-Konto — duerfen NICHT in der Missing-Bookings-Logik auftauchen
(keine "Buchung fehlt"-Warnungen auf dem eigenen Dashboard).

Regression-Guard fuer das Feature "Bootstrap-Admin ausserhalb der Zeitzaehlung".
Der track_hours-Guard greift VOR jedem DB-Zugriff, daher reicht ein In-Memory-
User ohne Session. Teil A: der Guard liest den Snapshot von heute; mit dem
(leeren) Verlaufs-Preload ``wh_changes=[]`` faellt er ohne Query auf die
User-Zeile zurueck.
"""
from app.models.user import User, UserRole
from app.routers.dashboard import _get_missing_bookings_for_user


def _make_admin(track_hours: bool) -> User:
    return User(
        username="admin",
        email="admin@praxis.local",
        password_hash="x",
        first_name="Admin",
        last_name="DerAdmin",
        role=UserRole.ADMIN,
        weekly_hours=40,
        work_days_per_week=5,
        vacation_days=30,
        track_hours=track_hours,
        milog_working_time_account=False,
        use_fixed_monthly_target=False,
    )


def test_non_tracking_user_has_no_missing_bookings():
    # track_hours=False short-circuitet vor jedem DB-Query -> db darf None sein
    # (leerer Verlaufs-Preload: Snapshot = User-Zeile, keine Query).
    admin = _make_admin(track_hours=False)
    assert _get_missing_bookings_for_user(None, admin, wh_changes=[]) == []
