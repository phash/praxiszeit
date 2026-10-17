"""Ultrareview 1.20 (Fund 4): die Direktbuchung (``absences.create_absence``)
ermittelt ihre Kandidaten-Tage über ``calculation_service.request_workday_candidates``
— dieselbe Regel wie die Antragspfade (#496) statt einer eigenen Inline-Fassung
(Mo–Fr minus Feiertage des Mandanten minus 'free'-Sondertage, AC-11)."""
import uuid
from datetime import date

from app.models import Absence, PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_round2_fixes import _client, _clear, _mk_employee  # noqa: F401


def _holiday(db, d, tenant_id=DEFAULT_TENANT_ID):
    db.add(PublicHoliday(id=uuid.uuid4(), tenant_id=tenant_id, date=d, name="Feiertag",
                         year=d.year))


def test_direct_booking_skips_weekends_holidays_and_free_special_days(db):
    emp = _mk_employee(db)
    for d in (date(2025, 12, 25), date(2025, 12, 26), date(2026, 1, 1)):
        _holiday(db, d)
    db.add(SystemSetting(key="special_day_dec24_mode", tenant_id=DEFAULT_TENANT_ID, value="free"))
    db.add(SystemSetting(key="special_day_dec31_mode", tenant_id=DEFAULT_TENANT_ID, value="free"))
    db.commit()
    resp = _client(db, emp).post("/api/absences", json={
        "date": "2025-12-22", "end_date": "2026-01-02", "type": "sick", "hours": 8,
    })
    assert resp.status_code == 201, resp.text
    booked = sorted(a.date for a in db.query(Absence).filter(Absence.user_id == emp.id))
    assert booked == [date(2025, 12, 22), date(2025, 12, 23), date(2025, 12, 29),
                      date(2025, 12, 30), date(2026, 1, 2)]


def test_direct_booking_uses_the_shared_candidate_helper(db, monkeypatch):
    emp = _mk_employee(db)
    calls = []
    real = calculation_service.request_workday_candidates

    def _spy(db_, tenant_id, start, end, year_cache=None):
        calls.append((tenant_id, start, end, year_cache is not None))
        return real(db_, tenant_id, start, end, year_cache=year_cache)

    monkeypatch.setattr(calculation_service, "request_workday_candidates", _spy)
    resp = _client(db, emp).post("/api/absences", json={
        "date": "2025-03-03", "end_date": "2025-03-04", "type": "vacation", "hours": 8,
    })
    assert resp.status_code == 201, resp.text
    assert calls == [(emp.tenant_id, date(2025, 3, 3), date(2025, 3, 4), True)]
