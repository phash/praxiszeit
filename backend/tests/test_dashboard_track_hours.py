"""Nutzer ohne Soll/Ist-Zeiterfassung (track_hours=False) — z.B. das technische
Bootstrap-Admin-Konto — duerfen NICHT in der Missing-Bookings-Logik auftauchen
(keine "Buchung fehlt"-Warnungen auf dem eigenen Dashboard).

Regression-Guard fuer das Feature "Bootstrap-Admin ausserhalb der Zeitzaehlung".
Der track_hours-Guard greift VOR jedem DB-Zugriff, daher reicht ein In-Memory-
User ohne Session.
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
        track_hours=track_hours,
    )


def test_non_tracking_user_has_no_missing_bookings():
    # track_hours=False short-circuitet vor jedem DB-Query -> db darf None sein.
    admin = _make_admin(track_hours=False)
    assert _get_missing_bookings_for_user(None, admin) == []
