"""Handbuch „So rechnet PraxisZeit": jede Zahl der Rechenbeispiele wird nachgerechnet.

``frontend/src/handbuch/content/rechenbeispiele.json`` ist die gemeinsame Quelle
der Beispielzahlen. Die Tabellen in ``so-rechnet.ts`` und die Diagramm-Konstanten
in ``diagrams/values.ts`` werden vom vitest-Fall ``rechenbeispiele.test.ts`` gegen
dieselbe Datei geprüft; hier rechnet der echte Berechnungscode jeden Eintrag nach
(``calculation_service``, ``work_window_service.clamp``, ``work_blocks_service``,
``milog_service``, Betriebsferien über die API). Abschnittsnummern der Fälle:
``docs/BERECHNUNGEN.md``.

Die Datei liegt im Repo-Teil ``frontend/`` — wie ``test_frontend_dockerignore.py``
überspringt sich der Test im reinen Backend-Container (nur ``backend/`` gemountet)
und läuft in GitHub-CI und ``scripts/local-ci.sh`` (Repo gemountet).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, PublicHoliday, TimeEntry, User, UserRole
from app.models.system_setting import SystemSetting
from app.models.year_carryover import YearCarryover
from app.services import auth_service, calculation_service, milog_service, special_days_service
from app.services import work_blocks_service
from app.services import work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from app.core.minimum_wage import minimum_wage_for
from tests.conftest import DEFAULT_TENANT_ID
from tests.setting_helpers import set_setting
from tests.work_blocks_fixtures import K_BLOCKS, block_week

JSON_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "handbuch" / "content" / "rechenbeispiele.json"

pytestmark = pytest.mark.skipif(
    not JSON_PATH.is_file(),
    reason=f"{JSON_PATH} nicht erreichbar (Backend-Container ohne Repo; läuft in CI und local-ci.sh)",
)

DATA = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.is_file() else {"cases": []}
CASES = {c["id"]: c for c in DATA["cases"]}
_NUM = re.compile(r"[−+-]?\d+(?:[.,]\d+)?")
_HM = re.compile(r"^(\d+):(\d{2})\b")


def _text_number(text: str) -> float:
    """Erste Zahl eines Anzeigetexts: „5,00 h" → 5,0; „−8,00 h" → −8,0; „4:25 h" → 4,4167."""
    t = text.replace("±", "").strip()
    m = _HM.match(t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    m = _NUM.search(t)
    assert m, f"keine Zahl in {text!r}"
    return float(m.group(0).replace("−", "-").replace(",", "."))


def check(case_id: str, **actual):
    """Vergleicht die nachgerechneten Werte mit dem JSON-Eintrag (Zahl UND Anzeigetext)."""
    case = CASES[case_id]
    spec = case["values"]
    assert set(spec) == set(actual), f"{case_id}: Schlüssel {sorted(spec)} != {sorted(actual)}"
    row = " | ".join(case["row"]) if case.get("row") else None
    for key, got in actual.items():
        exp = spec[key]
        if isinstance(got, (int, float, Decimal)):
            assert float(got) == pytest.approx(exp["v"], abs=0.005), f"{case_id}.{key}: {got} != {exp['v']}"
            # Anzeigetext und Zahl müssen zusammenpassen (z. B. 4,08 für 4,0833).
            assert _text_number(exp["text"]) == pytest.approx(exp["v"], abs=0.0051), f"{case_id}.{key} Text/Zahl"
        else:
            assert got == exp["v"], f"{case_id}.{key}: {got!r} != {exp['v']!r}"
        if row is not None:
            assert exp["text"] in row, f"{case_id}.{key}: {exp['text']!r} fehlt in der Zeile {row!r}"


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def _user(db, name="hb", weekly=40.0, days=5, vacation=30, **kw):
    u = User(
        username=name, email=f"{name}@x.de", password_hash=auth_service.hash_password("test123"),
        first_name=name, last_name="T", role=kw.pop("role", UserRole.EMPLOYEE), weekly_hours=weekly,
        vacation_days=vacation, work_days_per_week=days, is_active=True, track_hours=True,
        tenant_id=DEFAULT_TENANT_ID, **kw,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _entry(db, user, d, start, end, pause=0):
    e = TimeEntry(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, start_time=start, end_time=end,
                  break_minutes=pause)
    db.add(e); db.commit()
    return e


def _absence(db, user, d, typ, hours=8.0):
    a = Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d, type=typ, hours=hours, half_day=False)
    db.add(a); db.commit()
    return a


def _weekdays(year, month):
    d, out = date(year, month, 1), []
    while d.month == month:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _hh(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@pytest.fixture
def holidays_clean(db, default_tenant):
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


def _schedule(db, user, d):
    return calculation_service.get_schedule_for_date(db, user, d)


# ---------------------------------------------------------------------------
# 2. Tagessoll (BERECHNUNGEN 3.1–3.3)
# ---------------------------------------------------------------------------

MON = date(2026, 6, 1)  # Montag


@pytest.mark.parametrize("case_id, weekly, days", [
    ("tagessoll-vollzeit", 40.0, 5),
    ("tagessoll-teilzeit", 25.0, 5),
    ("tagessoll-3-tage", 24.0, 3),
])
def test_tagessoll_gleichmaessig(db, default_tenant, case_id, weekly, days):
    u = _user(db, weekly=weekly, days=days)
    got = calculation_service.get_daily_target_for_date(u, MON, _schedule(db, u, MON))
    check(case_id, daily_target=got)


def test_tagessoll_tagesplan(db, default_tenant):
    u = _user(db, weekly=24.0, days=3, use_daily_schedule=True,
              hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0, hours_thursday=0.0, hours_friday=0.0)
    day = lambda n: calculation_service.get_daily_target_for_date(u, MON + timedelta(days=n), _schedule(db, u, MON + timedelta(days=n)))  # noqa: E731
    check("tagessoll-tagesplan", mo=day(0), mi=day(2), do=day(3), fr=day(4))


@pytest.mark.parametrize("case_id, blocks, pause", [
    ("tagessoll-bloecke", [("08:00", "12:00"), ("15:00", "18:00")], 30),
    ("tagessoll-bloecke-4-08", [("08:00", "12:05")], 0),
])
def test_tagessoll_aus_bloecken(case_id, blocks, pause):
    week = block_week(pause=pause, mon=blocks)
    check(case_id, daily_target=work_blocks_service.derive_targets(week)["hours_monday"])


# ---------------------------------------------------------------------------
# 3. Ist und Pausen (BERECHNUNGEN 4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_id, start, end, pause", [
    ("ist-pause-30", time(8), time(16, 30), 30),
    ("ist-ohne-pause", time(8), time(12, 5), 0),
    ("ist-boden-null", time(8), time(8, 20), 30),
])
def test_ist_net_hours(case_id, start, end, pause):
    e = TimeEntry(date=MON, start_time=start, end_time=end, break_minutes=pause, uncredited_minutes=0)
    check(case_id, net_hours=e.net_hours)


# ---------------------------------------------------------------------------
# 4. Blöcke und Kappung (BERECHNUNGEN 4.1; Tabelle Mo 08–12 + 15–18, Puffer 15)
# ---------------------------------------------------------------------------

def _clamp_user(blocks):
    return User(username="k", email="k@x.de", password_hash="h", first_name="K", last_name="K",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
                track_hours=True, tenant_id=DEFAULT_TENANT_ID, work_blocks=blocks)


def _clamped(db, blocks, day, start, end, pause=0, grace=15):
    r = wws.clamp(db, _clamp_user(blocks), day, start, end, grace, credit_override=False)
    e = TimeEntry(date=day, start_time=r.eff_start, end_time=r.eff_end, raw_start_time=r.raw_start,
                  raw_end_time=r.raw_end, break_minutes=pause, uncredited_minutes=r.uncredited_minutes)
    return r, e


@pytest.mark.parametrize("case_id, start, end, pause", [
    ("kappung-durchgestempelt", time(8), time(18), 0),
    ("kappung-ausstempeln-12-05", time(8), time(12, 5), 0),
    ("kappung-in-luecke", time(12, 30), time(14, 30), 0),
    ("kappung-huelle-und-luecke", time(7), time(19), 0),
    ("kappung-vor-huelle", time(5), time(7), 0),
    ("kappung-pause-30", time(8), time(18), 30),
])
def test_kappung_tabelle(db, default_tenant, holidays_clean, case_id, start, end, pause):
    r, e = _clamped(db, K_BLOCKS, MON, start, end, pause)
    check(case_id, stored=f"{r.eff_start:%H:%M}–{r.eff_end:%H:%M}", uncredited=r.uncredited_minutes,
          net_hours=e.net_hours, not_credited=wws.not_credited_minutes(e))


def test_kappung_werktag_ohne_block(db, default_tenant, holidays_clean):
    tue = MON + timedelta(days=1)
    r, e = _clamped(db, block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")]), tue, time(9), time(12))
    assert r.eff_start == r.eff_end  # auf 0 h zusammengezogen
    check("kappung-werktag-ohne-block", net_hours=e.net_hours, not_credited=wws.not_credited_minutes(e))


def test_kappung_puffer_beispiel_07_30(db, default_tenant, holidays_clean):
    """Brief: 07:30 → 07:45 bei Block 08:00 und Puffer 15 min (Hülle = erster Block − Puffer)."""
    blocks = block_week(mon=[("08:00", "12:00"), ("15:00", "16:00")])
    r = wws.clamp(db, _clamp_user(blocks), MON, time(7, 30), time(12), 15, credit_override=False)
    check("kappung-puffer-07-30", eff_start=f"{r.eff_start:%H:%M}", raw_start=f"{r.raw_start:%H:%M}")


DIAGRAM_BLOCKS = block_week(mon=[("08:00", "12:00"), ("15:00", "16:00")])


@pytest.mark.parametrize("case_id, start, end", [
    ("diagram-eintrag-a", time(7, 30), time(12, 10)),
    ("diagram-eintrag-b", time(13), time(16, 30)),
])
def test_diagram_zeitstrahl(db, default_tenant, holidays_clean, case_id, start, end):
    r, e = _clamped(db, DIAGRAM_BLOCKS, MON, start, end)
    check(case_id, eff_start=f"{r.eff_start:%H:%M}", eff_end=f"{r.eff_end:%H:%M}",
          uncredited=r.uncredited_minutes, net_hours=e.net_hours, not_credited=wws.not_credited_minutes(e))


def test_diagram_huelle_und_luecke(db, default_tenant, holidays_clean):
    """Hülle 07:45–16:15; die Lücke 12:00–15:00 schrumpft um 15 min je Rand auf 12:15–14:45 (150 min)."""
    blocks = DIAGRAM_BLOCKS
    r = wws.clamp(db, _clamp_user(blocks), MON, time(7), time(17), 15, credit_override=False)
    segs = wws.gap_segments(db, _clamp_user(blocks), MON, time(7), time(17), 15, credit_override=False)
    check("diagram-huelle-luecke", hull_start=f"{r.eff_start:%H:%M}", hull_end=f"{r.eff_end:%H:%M}",
          gap_min=sum(segs))
    # Eine Lücke ≤ 2 × Puffer verschwindet (2g = 30 min, 2g + 1 = 31 min bleibt 1 min).
    short = block_week(mon=[("08:00", "12:00"), ("12:30", "16:00")])
    none = wws.gap_segments(db, _clamp_user(short), MON, time(8), time(16), 15, credit_override=False)
    assert sum(none) == 0
    one_over = block_week(mon=[("08:00", "12:00"), ("12:31", "16:00")])
    assert sum(wws.gap_segments(db, _clamp_user(one_over), MON, time(8), time(16), 15, credit_override=False)) == 1


# ---------------------------------------------------------------------------
# 5. Monatssoll, Saldo, Stichtag (BERECHNUNGEN 5, 7, 13.1, 13.3)
# ---------------------------------------------------------------------------

@pytest.fixture
def jan_feb(db, default_tenant, holidays_clean):
    """Jan 2026: 22 Werktage, 1 Feiertag, 4 Urlaubstage, 14 × 8,00 h + 3 × 8,50 h gearbeitet (13.1).
    Feb 2026: 20 Werktage, 19 × 8,00 h gearbeitet + 1 Tag Überstundenausgleich (13.3)."""
    u = _user(db)
    holiday = date(2026, 1, 6)
    db.add(PublicHoliday(date=holiday, name="Feiertag", year=2026, tenant_id=DEFAULT_TENANT_ID)); db.commit()
    invalidate_holiday_cache()
    jan = _weekdays(2026, 1)
    assert len(jan) == 22
    vacation = [date(2026, 1, 12), date(2026, 1, 13), date(2026, 1, 14), date(2026, 1, 15)]
    for d in vacation:
        _absence(db, u, d, AbsenceType.VACATION)
    working = [d for d in jan if d != holiday and d not in vacation]
    assert len(working) == 17
    for i, d in enumerate(working):
        _entry(db, u, d, time(8), time(16, 30) if i >= 14 else time(16))
    feb = _weekdays(2026, 2)
    assert len(feb) == 20
    off = date(2026, 2, 10)
    _absence(db, u, off, AbsenceType.OVERTIME)
    for d in feb:
        if d != off:
            _entry(db, u, d, time(8), time(16))
    return u


def test_monatssaldo_januar(db, jan_feb):
    soll = calculation_service.get_monthly_target(db, jan_feb, 2026, 1)
    ist = calculation_service.get_monthly_actual(db, jan_feb, 2026, 1)
    assert soll == Decimal("136.00") and 17 * Decimal(8) == soll
    check("monat-soll", soll_days=22 - 1 - 4, soll=soll)
    check("monat-ist", ist=ist)
    check("monat-saldo", saldo=ist - soll)


def test_monatssaldo_februar_und_konto(db, jan_feb):
    saldo = calculation_service.get_monthly_balance(db, jan_feb, 2026, 2)
    check("monat-ueberstundenausgleich", saldo=saldo)
    konto_jan = calculation_service.get_overtime_account(db, jan_feb, 2026, 1)
    konto_feb = calculation_service.get_overtime_account(db, jan_feb, 2026, 2)
    check("monat-konto", jan=konto_jan, feb=konto_feb)


def test_beispielmonate_maerz_april_sind_summen():
    """Mär/Apr sind erfundene Beispielwerte (im Handbuch als „Beispiel" benannt); das Konto ist Σ Monatssalden."""
    months = DATA["diagram_months"]
    konto = 0.0
    for m in months:
        konto += m["saldo"]
        assert konto == pytest.approx(m["konto"])
    assert [m["name"] for m in months] == ["Jan.", "Feb.", "Mär.", "Apr."]
    assert months[0]["saldo"] == pytest.approx(float(CASES["monat-saldo"]["values"]["saldo"]["v"]))
    assert months[1]["saldo"] == pytest.approx(float(CASES["monat-ueberstundenausgleich"]["values"]["saldo"]["v"]))


def test_stichtag_bis_heute(db, default_tenant):
    u = _user(db)
    today = date(2026, 3, 11)
    without = calculation_service.get_soll_cutoff_date(db, u, today=today)
    _entry(db, u, today, time(8), time(16))
    with_entry = calculation_service.get_soll_cutoff_date(db, u, today=today)
    check("monat-stichtag-ausgestempelt", cutoff=f"{with_entry:%d.%m.}")
    check("monat-stichtag-nicht", cutoff=f"{without:%d.%m.}")


# ---------------------------------------------------------------------------
# 6. Abwesenheiten-Matrix (BERECHNUNGEN 6; 8-h-Tag, Mo 12.01.2026)
# ---------------------------------------------------------------------------

_LABELS = {AbsenceType.VACATION: "abw-urlaub", AbsenceType.SICK: "abw-krank", AbsenceType.TRAINING: "abw-fortbildung",
           AbsenceType.PAID_LEAVE: "abw-freistellung", AbsenceType.OTHER: "abw-sonstige",
           AbsenceType.OVERTIME: "abw-ueberstundenausgleich"}


@pytest.mark.parametrize("typ", list(_LABELS))
def test_abwesenheiten_matrix(db, default_tenant, holidays_clean, typ):
    u = _user(db)
    d = date(2026, 1, 12)
    _absence(db, u, d, typ)
    soll = calculation_service.get_range_target(db, u, d, d)
    ist = calculation_service.get_range_actual(db, u, d, d)
    used = calculation_service.get_vacation_account(db, u, 2026)["used_days"]
    check(_LABELS[typ], soll=soll, ist=ist, saldo=ist - soll, vacation_days=used)


# ---------------------------------------------------------------------------
# 7. Urlaubskonto (BERECHNUNGEN 8, 13.4)
# ---------------------------------------------------------------------------

def _four_vacation_days(db, u):
    for d in (date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 12)):
        _absence(db, u, d, AbsenceType.VACATION)


def test_urlaubskonto_ohne_uebertrag(db, default_tenant, holidays_clean):
    u = _user(db)
    _four_vacation_days(db, u)
    acct = calculation_service.get_vacation_account(db, u, 2026)
    check("urlaub-ohne-uebertrag", budget=acct["budget_days"], used=acct["used_days"], rest=acct["remaining_days"])


def test_urlaubskonto_mit_uebertrag_diagramm(db, default_tenant, holidays_clean):
    u = _user(db)
    db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026, overtime_hours=0,
                         vacation_days=2, source="manual")); db.commit()
    _four_vacation_days(db, u)
    acct = calculation_service.get_vacation_account(db, u, 2026)
    check("urlaub-mit-uebertrag", entitlement=acct["entitlement_days"], carryover=2, budget=acct["budget_days"],
          used=acct["used_days"], rest=acct["remaining_days"])


def test_urlaub_anspruch_nach_arbeitstagen(db, default_tenant):
    assert 30 * 3 / 5 == 18  # Empfehlung 30 × Arbeitstage ÷ 5
    u = _user(db, weekly=24.0, days=3, vacation=18)
    acct = calculation_service.get_vacation_account(db, u, 2026)
    check("urlaub-anspruch-3-tage", entitlement=30 * 3 / 5, budget=acct["budget_days"])


def test_urlaub_halbtags_sondertag(db, default_tenant, holidays_clean):
    u = _user(db)
    set_setting(db, "special_day_dec24_mode", "half_day")
    a = _absence(db, u, date(2025, 12, 24), AbsenceType.VACATION)
    check("urlaub-halber-feiertag", used=calculation_service.get_vacation_account(db, u, 2025)["used_days"],
          report=calculation_service.absence_days(db, u, [a]))


def test_urlaub_anteilig_bei_eintritt(db, default_tenant, holidays_clean):
    u = _user(db, first_work_day=date(2026, 4, 15))
    acct = calculation_service.get_vacation_account(db, u, 2026)
    check("urlaub-eintritt-15-04", budget=round(float(acct["budget_days"]), 1))


def test_urlaub_frist(db, default_tenant):
    u = _user(db)
    check("urlaub-frist", deadline=f"{calculation_service.vacation_carryover_deadline(u, 2026):%d.%m.%Y}")


def test_urlaub_teilzeit_woche_kostet_drei_tage(db, default_tenant, holidays_clean):
    """Teilzeit Mo–Mi (Tagesplan): eine ganze Urlaubswoche bucht nur die 3 Tage mit Soll."""
    u = _user(db, weekly=24.0, days=3, use_daily_schedule=True,
              hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0, hours_thursday=0.0, hours_friday=0.0)
    week = [date(2026, 6, 1) + timedelta(days=i) for i in range(5)]
    billable = [d for d in week if calculation_service.is_vacation_billable_day(db, u, d)]
    check("urlaub-teilzeit-woche", days=len(billable))


# ---------------------------------------------------------------------------
# 8. Betriebsferien (BERECHNUNGEN 9.4, #314) über die API
# ---------------------------------------------------------------------------

CMON, CFRI = date(2025, 3, 10), date(2025, 3, 14)   # Mo–Fr, keine Feiertage
_DE = {AbsenceType.VACATION: "Urlaub", AbsenceType.OVERTIME: "Überstundenausgleich"}


def _closure_app():
    from app.routers import company_closures
    from app.core.limiter import limiter
    app = FastAPI()
    limiter.enabled = False
    app.include_router(company_closures.router)
    return app


@pytest.fixture
def closure_client(db, default_tenant, holidays_clean):
    app = _closure_app()
    admin = _user(db, "admin1", role=UserRole.ADMIN, vacation=0)
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin
    yield TestClient(app)
    app.dependency_overrides.clear()


def _closure(client):
    r = client.post("/api/company-closures/", json={"name": "BF", "start_date": CMON.isoformat(),
                                                    "end_date": CFRI.isoformat(), "counts_as_vacation": True})
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


def _types(db, user, cid):
    return [a.type for a in db.query(Absence).filter(Absence.user_id == user.id, Absence.closure_id == cid)
            .order_by(Absence.date).all()]


def test_betriebsferien_split_mit_einstellung(db, closure_client):
    emp = _user(db, "emp", vacation=3)
    db.add(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID, value="true")); db.commit()
    rest_before = calculation_service.get_vacation_account(db, emp, 2025)["remaining_days"]
    cid = _closure(closure_client)
    types = _types(db, emp, cid)
    rest = float(rest_before)
    for label, typ in zip(("mo", "di", "mi", "do", "fr"), types):
        before = rest
        if typ == AbsenceType.VACATION:
            rest -= 1
        check(f"betriebsferien-{label}", rest_before=before, buchung=_DE[typ], rest_after=rest)
    soll = calculation_service.get_range_target(db, emp, CMON, CFRI)
    ist = calculation_service.get_range_actual(db, emp, CMON, CFRI)
    check("betriebsferien-konto", konto=ist - soll)
    assert calculation_service.get_vacation_account(db, emp, 2025)["remaining_days"] == 0


def test_betriebsferien_ohne_einstellung_minus_urlaub(db, closure_client):
    emp = _user(db, "emp2", vacation=3)
    cid = _closure(closure_client)
    assert _types(db, emp, cid) == [AbsenceType.VACATION] * 5
    check("betriebsferien-aus", vacation_days=5, rest=calculation_service.get_vacation_account(db, emp, 2025)["remaining_days"])


# ---------------------------------------------------------------------------
# 9. Sondertage und verkürzte Tage (BERECHNUNGEN 12.2); 24.12.2025 = Mittwoch
# ---------------------------------------------------------------------------

DEC24 = date(2025, 12, 24)


@pytest.mark.parametrize("case_id, mode, extra", [
    ("sondertag-arbeitstag", "working_day", {}),
    ("sondertag-halb", "half_day", {}),
    ("sondertag-frei", "free", {"special_day_dec24_counts_as_vacation": "true"}),
    ("sondertag-verkuerzt", "max_hours", {"special_day_dec24_max_hours": "4"}),
])
def test_sondertag_modi(db, default_tenant, holidays_clean, case_id, mode, extra):
    u = _user(db)
    set_setting(db, "special_day_dec24_mode", mode)
    for k, v in extra.items():
        set_setting(db, k, v)
    soll = calculation_service.get_range_target(db, u, DEC24, DEC24)
    if mode == "free":
        # frei: kein Urlaubstag nötig — mit „Zählt als Urlaub" bucht das Konto 1 Tag automatisch.
        cost = calculation_service.get_vacation_account(db, u, 2025)["used_days"]
    else:
        a = _absence(db, u, DEC24, AbsenceType.VACATION)
        cost = calculation_service.get_vacation_account(db, u, 2025)["used_days"]
        assert calculation_service.absence_days(db, u, [a]) == cost
    check(case_id, soll=soll, vacation_cost=cost)


def test_sondertag_frei_ohne_urlaubswertung(db, default_tenant, holidays_clean):
    u = _user(db)
    set_setting(db, "special_day_dec24_mode", "free")
    set_setting(db, "special_day_dec24_counts_as_vacation", "false")
    check("sondertag-frei-ohne-urlaub", vacation_cost=calculation_service.get_vacation_account(db, u, 2025)["used_days"])


def test_sondertag_krank_am_verkuerzten_tag(db, default_tenant, holidays_clean):
    u = _user(db)
    set_setting(db, "special_day_dec24_mode", "max_hours")
    set_setting(db, "special_day_dec24_max_hours", "4")
    _absence(db, u, DEC24, AbsenceType.SICK)
    soll = calculation_service.get_range_target(db, u, DEC24, DEC24)
    ist = calculation_service.get_range_actual(db, u, DEC24, DEC24)
    check("sondertag-krank-verkuerzt", soll=soll, ist=ist, saldo=ist - soll)


def test_sondertag_verkuerzt_bei_kleinem_soll(db, default_tenant, holidays_clean):
    u = _user(db, weekly=15.0, days=5)  # 3 h pro Tag
    set_setting(db, "special_day_dec24_mode", "max_hours")
    set_setting(db, "special_day_dec24_max_hours", "4")
    check("sondertag-verkuerzt-3h", soll=calculation_service.get_range_target(db, u, DEC24, DEC24))


# ---------------------------------------------------------------------------
# 10. Minijob / MiLoG (BERECHNUNGEN 10)
# ---------------------------------------------------------------------------

def test_minijob_50_prozent(db, default_tenant, holidays_clean):
    u = _user(db, weekly=10.0, days=5, milog_working_time_account=True)
    agreed = milog_service.agreed_monthly_hours(db, u, date(2026, 3, 1))
    chk = milog_service.milog_50_check(db, u, 2026, 3, monthly_actual=Decimal("66"))
    assert chk is not None  # Warnung MILOG_ACCOUNT_50
    check("minijob-50", agreed=agreed, cap=chk["cap"], account=chk["account_hours"], warning="ja")
    below = milog_service.milog_50_check(db, u, 2026, 3, monthly_actual=Decimal("60"))
    assert below is None


def test_minijob_mindestlohn():
    check("minijob-mindestlohn-2026", wage=minimum_wage_for(date(2026, 1, 1)))
    check("minijob-mindestlohn-2027", wage=minimum_wage_for(date(2027, 1, 1)))


# ---------------------------------------------------------------------------
# 11. Jahresabschluss (BERECHNUNGEN 11)
# ---------------------------------------------------------------------------

def test_jahresabschluss(db, default_tenant, holidays_clean):
    u = _user(db)
    for d in (date(2025, 12, 25), date(2025, 12, 26)):
        db.add(PublicHoliday(date=d, name="Feiertag", year=2025, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    dec = _weekdays(2025, 12)
    vac = dec[:4]
    for d in vac:
        _absence(db, u, d, AbsenceType.VACATION)
    working = [d for d in dec if d not in vac and d not in (date(2025, 12, 25), date(2025, 12, 26))]
    assert len(working) == 17
    entries = [_entry(db, u, d, time(8), time(17) if i == 0 else time(16)) for i, d in enumerate(working)]
    calculation_service.create_year_closing(db, 2025, [u], changed_by=u.id)
    co = db.query(YearCarryover).filter(YearCarryover.user_id == u.id, YearCarryover.year == 2026).one()
    # Danach ändert sich das Jahr (+1 h an einem Tag); der Übertrag bleibt eingefroren …
    entries[1].end_time = time(17); db.commit()
    db.refresh(co)
    frozen = float(co.overtime_hours)
    check("abschluss-erster-lauf", overtime=frozen, vacation=float(co.vacation_days))
    # … bis der Jahresabschluss erneut läuft und ihn überschreibt.
    calculation_service.create_year_closing(db, 2025, [u], changed_by=u.id)
    rows = db.query(YearCarryover).filter(YearCarryover.user_id == u.id, YearCarryover.year == 2026).all()
    assert len(rows) == 1
    db.refresh(rows[0])
    check("abschluss-zweiter-lauf", overtime=float(rows[0].overtime_hours), vacation=float(rows[0].vacation_days))


# ---------------------------------------------------------------------------
# Wächter: jeder JSON-Fall wird irgendwo oben geprüft
# ---------------------------------------------------------------------------

def test_jeder_fall_hat_eine_nachrechnung():
    source = Path(__file__).read_text(encoding="utf-8")
    checked = set(re.findall(r'check\(\s*(?:f)?"([a-z0-9-{}_]+)"', source))
    # parametrisierte ids (case_id-Variablen) stehen in den Parametrisierungen:
    checked |= set(re.findall(r'\("([a-z0-9-]+)",', source))
    checked |= {f"betriebsferien-{t}" for t in ("mo", "di", "mi", "do", "fr")}
    checked |= set(_LABELS.values())
    case_ids = {c["id"] for c in DATA["cases"]}
    assert case_ids <= checked, f"ohne Nachrechnung: {sorted(case_ids - checked)}"
    assert len(case_ids) == len(DATA["cases"]), "doppelte ids im JSON"
