"""Release-Review 1.18.1 (Fund 1): der #314-Re-Split muss dieselbe Menge zaehlen
wie das Urlaubskonto — inklusive #193-Beschaeftigungsfenster.

Warum diese Datei existiert
===========================
``a1cdc250`` (Audit 2026-07-31, Fund B) hat das Beschaeftigungsfenster auf der
BUDGET-Seite nachgezogen: ``get_vacation_account`` zaehlt einen Urlaubstag
ausserhalb von ``first_work_day``/``last_work_day`` seither mit 0, und der
Re-Split filtert den privaten Urlaub genauso. Die WALK-Schleife ueber die
Betriebsferien-Zeilen blieb ungefiltert — begruendet damit, die Zeilen seien
"bereits gefenstert (#298)".

Das ist ein Guard zum BUCHUNGS-Zeitpunkt, keine Invariante:
``PUT /api/admin/users/{id}`` setzt ``first_work_day``/``last_work_day``
beliebig und raeumt KEINE Abwesenheiten ab (genau die Begruendung, mit der
a1cdc250 seinen eigenen Fund belegt). Danach zaehlen Budget-Seite (gefenstert)
und Walk-Seite (ungefiltert) verschiedene Mengen — und weil der Re-Split die
Klassifizierung des Buchungspfads UEBERSCHREIBT, kippen echte Schliesstage auf
Ueberstundenausgleich, waehrend das Urlaubskonto daneben Resturlaub meldet.

Der Re-Split laeuft aus neun Urlaubs-Schreibpfaden (``absences``,
``admin_vacations``, ``vacation_requests``, ``admin_change_requests``, …) — es
braucht also KEINE Bearbeitung der Betriebsferien, damit der Fehler eintritt.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.database import Base
from app.models import User, UserRole, Absence, AbsenceType, CompanyClosure
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.services import auth_service, calculation_service, closure_split_service
from tests.conftest import DEFAULT_TENANT_ID, engine, TestingSessionLocal


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def default_tenant(db):
    t = Tenant(id=DEFAULT_TENANT_ID, name="Default", slug="default", is_active=True, mode="single")
    db.add(t)
    db.commit()
    return t


def _make_user(db, username, role=UserRole.EMPLOYEE, vacation_days=30, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash=auth_service.hash_password("t"),
        first_name=username, last_name="T", role=role, weekly_hours=40.0,
        vacation_days=vacation_days, work_days_per_week=5, is_active=True,
        track_hours=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _set_toggle(db, on=True):
    db.merge(SystemSetting(key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
                           value="true" if on else "false"))
    db.commit()


def _weekdays(start: date, end: date):
    out, c = [], start
    while c <= end:
        if c.weekday() < 5:
            out.append(c)
        c += timedelta(days=1)
    return out


def _closure_with_absences(db, admin, emp, name, start, end):
    """Legt eine Betriebsferien-Zeile + ihre Tages-Absencen an — so, wie
    ``_create_closure_absences`` sie zum BUCHUNGS-Zeitpunkt erzeugt haette
    (also bevor der Admin das Beschaeftigungsfenster verschoben hat)."""
    closure = CompanyClosure(
        name=name, start_date=start, end_date=end, counts_as_vacation=True,
        tenant_id=DEFAULT_TENANT_ID, created_by=admin.id,
    )
    db.add(closure)
    db.commit()
    db.refresh(closure)
    for d in _weekdays(start, end):
        db.add(Absence(
            user_id=emp.id, tenant_id=DEFAULT_TENANT_ID, date=d, end_date=None,
            type=AbsenceType.VACATION, hours=8.0, half_day=False,
            note=f"Betriebsferien: {name}", closure_id=closure.id,
        ))
    db.commit()
    return closure


def _types(db, emp, closure):
    return [a.type for a in db.query(Absence).filter(
        Absence.user_id == emp.id, Absence.closure_id == closure.id,
    ).order_by(Absence.date).all()]


# 2026: 05.–09.01. = Mo–Fr (5 Arbeitstage), 07.–11.12. = Mo–Fr (5 Arbeitstage).
JAN_START, JAN_END = date(2026, 1, 5), date(2026, 1, 9)
DEC_START, DEC_END = date(2026, 12, 7), date(2026, 12, 11)


def test_vorrichtung_beide_zeitraeume_haben_fuenf_arbeitstage():
    """Selbstkontrolle: die Aussagen unten haengen an diesen Tageszahlen."""
    assert len(_weekdays(JAN_START, JAN_END)) == 5
    assert len(_weekdays(DEC_START, DEC_END)) == 5


class TestEintrittNachtraeglichVorwaertsGeschoben:
    """Der schaedliche Fall: ``first_work_day`` wird nach vorne gesetzt, die
    Januar-Zeilen liegen danach VOR dem Eintritt."""

    def test_januar_zeilen_vor_eintritt_verbrauchen_kein_budget(self, db, default_tenant):
        admin = _make_user(db, "admin_fenster", role=UserRole.ADMIN)
        # vacation_days=6, Eintritt 01.03. → Budget 6 × 10/12 = 5,0 Tage.
        emp = _make_user(db, "emp_fenster", vacation_days=6)
        _set_toggle(db)

        jan = _closure_with_absences(db, admin, emp, "Winter", JAN_START, JAN_END)
        dec = _closure_with_absences(db, admin, emp, "Weihnachten", DEC_START, DEC_END)

        # Datenkorrektur/Rehire im April: der Admin setzt das Eintrittsdatum.
        # Bestehende Abwesenheiten werden dabei NICHT aufgeraeumt.
        emp.first_work_day = date(2026, 3, 1)
        db.commit()

        account = calculation_service.get_vacation_account(db, emp, 2026)
        assert account["budget_days"] == 5.0
        # Das Urlaubskonto zaehlt die Januar-Zeilen seit a1cdc250 mit 0.
        assert account["used_days"] == 5.0, "nur die Dezember-Tage zaehlen"

        closure_split_service.resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()

        # Die Dezember-Tage sind vom Budget gedeckt (5,0 Tage Rest ohne die
        # Januar-Zeilen) → sie muessen VACATION bleiben. Vor dem Fix zehrten die
        # fuenf Januar-Zeilen das Budget auf und alle fuenf Dezember-Tage kippten
        # auf OVERTIME: 40 h zulasten des Ueberstundenkontos, waehrend
        # get_vacation_account fuer denselben MA Resturlaub meldet.
        assert _types(db, emp, dec) == [AbsenceType.VACATION] * 5
        # Die fensterfremden Januar-Zeilen tragen den Basistyp der Schliessung
        # (wie der bestehende Tagessoll-0-Zweig) und kosten nichts.
        assert _types(db, emp, jan) == [AbsenceType.VACATION] * 5

    def test_urlaubskonto_und_split_zaehlen_dieselbe_menge(self, db, default_tenant):
        """Die eigentliche Invariante: nach dem Re-Split darf das Konto keinen
        Resturlaub mehr melden, wenn Tage auf OVERTIME gekippt wurden."""
        admin = _make_user(db, "admin_inv", role=UserRole.ADMIN)
        emp = _make_user(db, "emp_inv", vacation_days=6)
        _set_toggle(db)

        _closure_with_absences(db, admin, emp, "Winter", JAN_START, JAN_END)
        dec = _closure_with_absences(db, admin, emp, "Weihnachten", DEC_START, DEC_END)
        emp.first_work_day = date(2026, 3, 1)
        db.commit()

        closure_split_service.resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()

        account = calculation_service.get_vacation_account(db, emp, 2026)
        gekippt = [t for t in _types(db, emp, dec) if t == AbsenceType.OVERTIME]
        assert not (gekippt and account["remaining_days"] > 0), (
            f"{len(gekippt)} Tage auf Ueberstundenausgleich, "
            f"aber {account['remaining_days']} Resturlaub uebrig"
        )


class TestAustrittsfallNormalisiert:
    """Der harmlose Fall (die fensterfremden Zeilen liegen kalendarisch HINTER
    allen echten) — er darf nach dem Fix keine OVERTIME-Zeilen mehr erzeugen."""

    def test_zeilen_nach_austritt_kosten_nichts(self, db, default_tenant):
        admin = _make_user(db, "admin_aus", role=UserRole.ADMIN)
        # Austritt 30.06. → Budget 6 × 6/12 = 3,0 Tage.
        emp = _make_user(db, "emp_aus", vacation_days=6, last_work_day=date(2026, 6, 30))
        _set_toggle(db)

        jan = _closure_with_absences(db, admin, emp, "Winter", JAN_START, JAN_END)
        dec = _closure_with_absences(db, admin, emp, "Weihnachten", DEC_START, DEC_END)

        closure_split_service.resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()

        # Januar liegt im Fenster: 3,0 Tage Budget decken drei Tage, die
        # restlichen zwei werden Ueberstundenausgleich (unveraendert).
        assert _types(db, emp, jan) == [AbsenceType.VACATION] * 3 + [AbsenceType.OVERTIME] * 2
        # Dezember liegt komplett nach dem Austritt → kostenneutral, Basistyp.
        assert _types(db, emp, dec) == [AbsenceType.VACATION] * 5


class TestOhneFensterUnveraendert:
    """Kontrolltest: ohne gesetztes Beschaeftigungsfenster (der Regelfall) muss
    der Re-Split bitgleich zu vorher entscheiden."""

    def test_kalenderreihenfolge_und_ueberschuss_unveraendert(self, db, default_tenant):
        admin = _make_user(db, "admin_ctrl", role=UserRole.ADMIN)
        emp = _make_user(db, "emp_ctrl", vacation_days=6)  # Budget 6,0, kein Fenster
        _set_toggle(db)

        jan = _closure_with_absences(db, admin, emp, "Winter", JAN_START, JAN_END)
        dec = _closure_with_absences(db, admin, emp, "Weihnachten", DEC_START, DEC_END)

        closure_split_service.resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()

        # 6,0 Tage Budget, Kalenderreihenfolge: Januar (5) voll, Dezember nimmt
        # den sechsten Tag, die uebrigen vier werden Ueberstundenausgleich.
        assert _types(db, emp, jan) == [AbsenceType.VACATION] * 5
        assert _types(db, emp, dec) == [AbsenceType.VACATION] + [AbsenceType.OVERTIME] * 4

    def test_eintritt_im_vorjahr_aendert_nichts(self, db, default_tenant):
        """Ein Fenster, das das ganze Jahr umschliesst, darf keinen Unterschied
        machen (kein versehentlicher Kurzschluss ueber ``first_work_day``)."""
        admin = _make_user(db, "admin_ctrl2", role=UserRole.ADMIN)
        emp = _make_user(db, "emp_ctrl2", vacation_days=6,
                         first_work_day=date(2020, 1, 1), last_work_day=date(2030, 12, 31))
        _set_toggle(db)

        jan = _closure_with_absences(db, admin, emp, "Winter", JAN_START, JAN_END)
        dec = _closure_with_absences(db, admin, emp, "Weihnachten", DEC_START, DEC_END)

        closure_split_service.resplit_year_closures(db, DEFAULT_TENANT_ID, 2026)
        db.commit()

        assert _types(db, emp, jan) == [AbsenceType.VACATION] * 5
        assert _types(db, emp, dec) == [AbsenceType.VACATION] + [AbsenceType.OVERTIME] * 4
