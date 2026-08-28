"""#440 A/B: der Freitext der Antraege ueberlebt die Einzel-Anonymisierung nicht.

``change_requests.reason`` ist NOT NULL und traegt reine Prosa der Beschaeftigten
— haeufig gesundheits- oder adressnah ("Arzttermin wegen ...", "Kind in der Kita
abgeholt"). Dazu ``proposed_note``, ``original_note``, ``break_waiver_reason``,
``rejection_reason`` und bei den Urlaubsantraegen ``note``/``rejection_reason``.
Nach Art. 17 ist eine Anonymisierung, die diese Saetze stehen laesst, keine.

Die ZEILEN bleiben stehen — "wer hat wann was beantragt und wer hat es
entschieden" ist der belegende Teil. Ein Scrub, der die Antraege stattdessen
loescht, waere ebenfalls falsch; die Tests pruefen darum beides.

Der Mandanten-Pfad ist in ``test_tenant_anonymization.py`` abgedeckt (Suchlauf
ueber jede Tabelle + gezielte Zusicherungen). Diese Datei nimmt den ungleich
haeufigeren Weg: eine ausgeschiedene Person macht ihr Recht auf Loeschung
geltend.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import (
    ChangeRequest,
    ChangeRequestStatus,
    ChangeRequestType,
    User,
    UserRole,
    VacationRequest,
)
from app.services import lifecycle_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

REASON = "Arzttermin wegen Rueckenbeschwerden"
PROPOSED_NOTE = "Kind aus der Kita abgeholt"
ORIGINAL_NOTE = "urspruengliche Notiz mit Klarnamen"
WAIVER = "Pause war wegen Notfall nicht moeglich"
REJECTION = "abgelehnt, weil Frau Schulz an dem Tag Dienst hatte"
VR_NOTE = "Kur in Bad Nauheim"
VR_REJECTION = "abgelehnt wegen Personalengpass"


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _deactivated_user(db, name="anna.meier"):
    """Ohne ``deactivated_at`` → Legacy-Zweig, keine 14-Tage-Sperrfrist."""
    u = User(
        username=name, email=f"{name}@praxis.invalid", password_hash="x",
        first_name="Anna", last_name="Meier", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=False, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _cr(db, user, **over):
    row = ChangeRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE,
        status=ChangeRequestStatus.REJECTED,
        reason=REASON, proposed_note=PROPOSED_NOTE, original_note=ORIGINAL_NOTE,
        break_waiver_reason=WAIVER, rejection_reason=REJECTION,
        proposed_date=date(2026, 5, 4),
        **over,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _vr(db, user):
    row = VacationRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=date(2026, 6, 1),
        hours=8.0, note=VR_NOTE, status="rejected", rejection_reason=VR_REJECTION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _reload(db, model, row_id):
    db.expire_all()
    return db.query(model).filter(model.id == row_id).one()


class TestAenderungsantrag:
    def test_prosa_ist_weg(self, admin_client, db):
        u = _deactivated_user(db)
        cr = _cr(db, u)

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        row = _reload(db, ChangeRequest, cr.id)
        assert row.reason == lifecycle_service.ANONYMIZED_TEXT
        assert row.proposed_note is None
        assert row.original_note is None
        assert row.break_waiver_reason is None
        assert row.rejection_reason is None

    def test_der_antrag_selbst_bleibt_stehen(self, admin_client, db):
        """Nur der Freitext geht — der Vorgang bleibt nachweisbar."""
        u = _deactivated_user(db)
        cr = _cr(db, u)

        admin_client.post(f"/api/admin/users/{u.id}/anonymize")

        row = _reload(db, ChangeRequest, cr.id)
        assert row.user_id == u.id
        assert row.status == ChangeRequestStatus.REJECTED
        assert row.proposed_date == date(2026, 5, 4)

    def test_fremder_antrag_bleibt_unberuehrt(self, admin_client, db):
        """Der Scrub greift ueber ``user_id`` — der Antrag einer Kollegin
        behaelt seine eigene Prosa. (Prosa DRITTER, die die anonymisierte
        Person beim Namen nennt, ist die dokumentierte Grenze aus #440.)"""
        u = _deactivated_user(db)
        other = _deactivated_user(db, name="bea.kern")
        fremd = _cr(db, other)

        admin_client.post(f"/api/admin/users/{u.id}/anonymize")

        assert _reload(db, ChangeRequest, fremd.id).reason == REASON


class TestUrlaubsantrag:
    def test_notiz_und_ablehnungsgrund_sind_weg(self, admin_client, db):
        u = _deactivated_user(db)
        vr = _vr(db, u)

        assert admin_client.post(f"/api/admin/users/{u.id}/anonymize").status_code == 200

        row = _reload(db, VacationRequest, vr.id)
        assert row.note is None
        assert row.rejection_reason is None

    def test_datum_und_status_bleiben(self, admin_client, db):
        u = _deactivated_user(db)
        vr = _vr(db, u)

        admin_client.post(f"/api/admin/users/{u.id}/anonymize")

        row = _reload(db, VacationRequest, vr.id)
        assert row.date == date(2026, 6, 1)
        assert row.status == "rejected"
