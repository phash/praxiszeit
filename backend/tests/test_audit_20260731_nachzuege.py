"""Audit 2026-07-31 — Nachzuege aus Fund K (Ist-Gutschrift folgt der Soll-Struktur).

Beim Schliessen von Fund K fielen drei Dinge auf, die ausserhalb des damaligen
Auftrags lagen. Dieses Modul pinnt zwei davon (der dritte, die fehlende
Gutschrift in den Datei-Exporten, wird in ``test_audit_20260731_export_ist.py``
geprueft):

**N1 — fehlender Mandantenfilter auf den vier Gutschrift-Abfragen.**
``get_range_actual``, ``get_overtime_account``, ``get_overtime_history_detailed``
und ``get_ytd_summary`` laden die ist-gutgeschriebenen Abwesenheiten
(TRAINING/SICK) nach Benutzer und Zeitraum — aber ohne
``Absence.tenant_id == user.tenant_id``. Die Projektregel F-026 verlangt den
Filter ZUSAETZLICH zur RLS-Richtlinie, weil RLS in
``set_superadmin_context``-Pfaden nicht greift. Die Nachbar-Abfragen derselben
Funktionen (Feiertage, Vertragshistorie, soll-reduzierende Abwesenheiten) tragen
ihn laengst; nur die Gutschrift-Abfragen fielen durch.

Der Testaufbau ist genau die Konstellation, gegen die der Filter schuetzt: eine
Absence-Zeile, die auf denselben ``user_id`` zeigt, aber die ``tenant_id`` eines
FREMDEN Mandanten traegt. Solche Zeilen entstehen nicht im Normalbetrieb — genau
deshalb ist der Filter Guertel UND Hosentraeger: er haelt die Rechnung auch dann
korrekt, wenn ein Schreibpfad die ``tenant_id`` falsch setzt oder die Abfrage in
einem Kontext ohne RLS laeuft. Die SQLite-Testsuite kennt ueberhaupt keine RLS,
sie zeigt den Fehler also unverstellt.

**N3 — fehlender Feiertags-Guard im UPDATE-Zweig der Aenderungsantrags-Genehmigung.**
Der CREATE-Zweig sperrt seit dem Release-Review 1.16.0 gesetzliche Feiertage; der
UPDATE-Zweig verschob das Datum einer bestehenden Abwesenheit voellig
ungeprueft. Ein Mitarbeiter konnte seine Krankmeldung per Aenderungsantrag auf
den 25.12. legen lassen. Der einzige Datums-Check dort (soll-freier Sondertag)
ist hart auf VACATION gegated, ein Kranktag rutschte also frei durch. Genau ueber
diesen Weg war der Feiertagsfall von Fund K im laufenden Betrieb erreichbar.

Beide Zweige teilen sich jetzt EINEN Helper
(``admin_change_requests._assert_absence_date_bookable``) — die Regel existiert
im Projekt ohnehin schon in vier Fassungen, eine fuenfte waere die naechste
Divergenz. Wochenenden bleiben bewusst offen (Entscheidung des CREATE-Zweigs:
Praxen mit Samstagsdienst buchen dort reale Abwesenheiten).
"""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models import (
    Absence, AbsenceType, ChangeRequest, ChangeRequestStatus, ChangeRequestType,
    PublicHoliday, TimeEntry, User, UserRole,
)
from app.models.tenant import Tenant
from app.routers.admin_change_requests import review_change_request
from app.schemas.change_request import ChangeRequestReview
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID

# Maerz 2026: 02.03. = Montag, 10.03. = Dienstag. Beide regulaere Werktage.
MONDAY = date(2026, 3, 2)
TUESDAY = date(2026, 3, 10)
# Ein Werktag, der als Feiertag angelegt wird (Karfreitag 2026 = Freitag).
HOLIDAY = date(2026, 4, 3)

FOREIGN_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")


# --------------------------------------------------------------------------
# Gemeinsame Helfer
# --------------------------------------------------------------------------

def _make_user(db, username, role=UserRole.EMPLOYEE, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash="h", first_name=username,
        last_name="T", role=role, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, track_hours=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_absence(db, user, d, absence_type, hours=8.0, tenant_id=DEFAULT_TENANT_ID):
    a = Absence(
        user_id=user.id, tenant_id=tenant_id, date=d,
        type=absence_type, hours=hours,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# --------------------------------------------------------------------------
# N1 — Mandantenfilter auf den Gutschrift-Abfragen
# --------------------------------------------------------------------------

@pytest.fixture
def foreign_tenant(db, default_tenant):
    """Ein zweiter Mandant, damit die Fremd-Absence eine gueltige FK hat."""
    t = Tenant(
        id=FOREIGN_TENANT_ID, name="Fremd GmbH", slug="fremd",
        is_active=True, mode="multi",
    )
    db.add(t)
    db.commit()
    return t


def _make_entry(db, user, d, start_h=9, end_h=17):
    """Ein reguraerer 8-h-Zeiteintrag.

    ``get_overtime_account`` und ``get_overtime_history_detailed`` steigen ohne
    Zeiteintrag und ohne Carryover sofort aus (Startpunkt unbestimmt) — ohne
    diesen Anker liefen die Tests dort in einen leeren Rueckgabewert und waeren
    vakuum-gruen.
    """
    from datetime import time
    e = TimeEntry(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
        start_time=time(start_h, 0), end_time=time(end_h, 0), break_minutes=0,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _user_with_foreign_credited_absence(db, username):
    """MA mit einem echten 8-h-Tag PLUS einer TRAINING-Absence, die faelschlich
    am fremden Mandanten haengt.

    Fachlich existiert fuer diesen MA im eigenen Mandanten KEINE gutgeschriebene
    Abwesenheit — die Ist-Seite darf die 8 h der Fremdzeile also nicht sehen und
    muss bei den 8 h des Zeiteintrags bleiben.
    """
    user = _make_user(db, username)
    _make_entry(db, user, MONDAY)
    _make_absence(db, user, TUESDAY, AbsenceType.TRAINING,
                  hours=8.0, tenant_id=FOREIGN_TENANT_ID)
    return user


def test_range_actual_ignores_foreign_tenant_credit(db, foreign_tenant):
    """get_range_actual (und damit get_monthly_actual) zaehlt nur den eigenen Mandanten."""
    user = _user_with_foreign_credited_absence(db, "n1_range")
    actual = calculation_service.get_range_actual(db, user, MONDAY, date(2026, 3, 31))
    assert actual == 8, (
        "Eine Absence eines FREMDEN Mandanten darf nicht ins Ist einfliessen "
        f"(erwartet 8 = nur der Zeiteintrag, erhalten {actual})"
    )


def test_monthly_actual_ignores_foreign_tenant_credit(db, foreign_tenant):
    """Der Wrapper, den Dashboard/Berichte/Exporte tatsaechlich aufrufen."""
    user = _user_with_foreign_credited_absence(db, "n1_monthly")
    assert calculation_service.get_monthly_actual(db, user, 2026, 3) == 8


def test_overtime_account_ignores_foreign_tenant_credit(db, foreign_tenant):
    """Das Ueberstundenkonto darf die fremde Gutschrift nicht als Ist buchen.

    ``get_overtime_account`` liefert nur den Saldo, kein Ist. Verglichen wird
    deshalb gegen einen baugleichen MA OHNE die Fremdzeile: beide Salden muessen
    identisch sein. Das ist zugleich der schaerfste Test — er faellt auch dann,
    wenn die Fremdzeile den Saldo nur um einen Bruchteil verschoebe.
    """
    user = _user_with_foreign_credited_absence(db, "n1_account")
    control = _make_user(db, "n1_account_ctl")
    _make_entry(db, control, MONDAY)

    assert (calculation_service.get_overtime_account(db, user, 2026, 3)
            == calculation_service.get_overtime_account(db, control, 2026, 3))


def test_overtime_history_detailed_ignores_foreign_tenant_credit(db, foreign_tenant):
    """Speist die MiLoG-Faelligkeit (settlement_aging) — eine fremde Gutschrift
    verschoebe dort die FIFO-Alterung echter Einlagen."""
    user = _user_with_foreign_credited_absence(db, "n1_history")
    hist = calculation_service.get_overtime_history_detailed(db, user, 2026, 3)
    assert (2026, 3) in hist, "Maerz 2026 muss in der Historie stehen"
    assert hist[(2026, 3)].actual == 8


def test_ytd_summary_ignores_foreign_tenant_credit(db, foreign_tenant):
    """Jahresuebersicht (Dashboard + Benutzeruebersicht)."""
    user = _user_with_foreign_credited_absence(db, "n1_ytd")
    summary = calculation_service.get_ytd_summary(db, user, 2026)
    assert summary["actual_hours"] == 8


def test_own_tenant_credit_still_counts(db, foreign_tenant):
    """Byte-Identitaets-Kontrolle: die EIGENE Gutschrift zaehlt unveraendert.

    Ohne diesen Test wuerde ein zu scharfer Filter (z. B. Vergleich gegen den
    falschen tenant_id-Wert) von den Tests oben nicht bemerkt — sie wuerden
    gruen bleiben, weil sie nur den Zeiteintrag sehen wollen.
    """
    user = _make_user(db, "n1_own")
    _make_entry(db, user, MONDAY)
    _make_absence(db, user, TUESDAY, AbsenceType.TRAINING, hours=8.0)

    assert calculation_service.get_monthly_actual(db, user, 2026, 3) == 16
    assert calculation_service.get_ytd_summary(db, user, 2026)["actual_hours"] == 16
    hist = calculation_service.get_overtime_history_detailed(db, user, 2026, 3)
    assert hist[(2026, 3)].actual == 16


# --------------------------------------------------------------------------
# N3 — Feiertags-Guard im UPDATE-Zweig der CR-Genehmigung
# --------------------------------------------------------------------------

def _make_update_cr(db, user, absence, **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.UPDATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Testantrag",
        absence_id=absence.id,
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


@pytest.fixture
def holiday(db, default_tenant):
    h = PublicHoliday(
        date=HOLIDAY, name="Karfreitag", year=HOLIDAY.year,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(h)
    db.commit()
    return h


def test_cr_update_onto_holiday_rejected(db, holiday):
    """Der gemeldete Weg: eine Krankmeldung per CR auf einen Feiertag verschieben.

    Genau ueber diese Luecke war der Feiertagsfall aus Fund K im laufenden
    Betrieb erreichbar — dort haette der Tag 0 Soll getragen, die Gutschrift aber
    (vor Fund K) volle 8 h Ist. Jetzt sperrt bereits die Genehmigung.
    """
    admin = _make_user(db, "n3_admin", role=UserRole.ADMIN)
    emp = _make_user(db, "n3_emp")
    sick = _make_absence(db, emp, TUESDAY, AbsenceType.SICK)
    cr = _make_update_cr(db, emp, sick, proposed_date=HOLIDAY)

    with pytest.raises(HTTPException) as exc:
        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )
    assert exc.value.status_code == 400
    assert "Feiertag" in exc.value.detail
    assert "Karfreitag" in exc.value.detail

    db.rollback()
    db.refresh(sick)
    # Die Mutation darf NICHT teilweise durchgelaufen sein.
    assert sick.date == TUESDAY


def test_cr_update_onto_holiday_rejected_for_vacation_too(db, holiday):
    """Typ-agnostisch: auch Urlaub. Der bisherige Sondertag-Check deckte nur
    VACATION ab und kannte ueberdies nur 24./31.12., keine Feiertage."""
    admin = _make_user(db, "n3_admin_v", role=UserRole.ADMIN)
    emp = _make_user(db, "n3_emp_v")
    vac = _make_absence(db, emp, TUESDAY, AbsenceType.VACATION)
    cr = _make_update_cr(db, emp, vac, proposed_date=HOLIDAY)

    with pytest.raises(HTTPException) as exc:
        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )
    assert exc.value.status_code == 400
    assert "Feiertag" in exc.value.detail


def test_cr_update_onto_workday_still_ok(db, holiday):
    """Byte-Identitaets-Kontrolle: eine Verschiebung auf einen normalen Werktag
    laeuft unveraendert durch — inklusive der bestehenden H-1-Neuberechnung der
    Stunden auf das Tagessoll des ZIELtags."""
    admin = _make_user(db, "n3_admin_ok", role=UserRole.ADMIN)
    emp = _make_user(db, "n3_emp_ok")
    sick = _make_absence(db, emp, TUESDAY, AbsenceType.SICK)
    cr = _make_update_cr(db, emp, sick, proposed_date=MONDAY)

    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )
    db.refresh(sick)
    assert sick.date == MONDAY
    assert float(sick.hours) == 8.0


def test_cr_update_without_proposed_date_not_blocked(db, holiday):
    """Bewusste Grenze: ein Antrag OHNE Datum (reiner Zeit-/Typ-Edit) laeuft auch
    dann durch, wenn die Abwesenheit selbst auf einem Feiertag liegt.

    Solche Zeilen gibt es real — aus Altdaten vor dem 1.16.0-Guard oder weil ein
    Feiertag nachtraeglich gepflegt wurde (``holidays.py`` prueft beim Anlegen
    nicht auf bestehende Abwesenheiten). Wuerde der Guard auch hier greifen,
    waeren sie unreparierbar eingefroren. Der CREATE-Zweig zieht dieselbe Grenze
    (``if cr.proposed_date and cr_user``).
    """
    admin = _make_user(db, "n3_admin_legacy", role=UserRole.ADMIN)
    emp = _make_user(db, "n3_emp_legacy")
    legacy = _make_absence(db, emp, HOLIDAY, AbsenceType.SICK)
    cr = _make_update_cr(db, emp, legacy, proposed_absence_type="training")

    review_change_request(
        request_id=str(cr.id),
        review=ChangeRequestReview(action="approve"),
        db=db, current_user=admin,
    )
    db.refresh(legacy)
    assert legacy.type == AbsenceType.TRAINING
    assert legacy.date == HOLIDAY


def test_cr_create_onto_holiday_still_rejected(db, holiday):
    """Regressionsschutz fuer den CREATE-Zweig: er wurde auf den gemeinsamen
    Helper umgestellt und muss sich exakt wie vorher verhalten — gleicher Code,
    gleiche Meldung."""
    admin = _make_user(db, "n3_admin_c", role=UserRole.ADMIN)
    emp = _make_user(db, "n3_emp_c")
    cr = ChangeRequest(
        user_id=emp.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=ChangeRequestType.CREATE, entry_kind="absence",
        status=ChangeRequestStatus.PENDING, reason="Testantrag",
        proposed_date=HOLIDAY, proposed_absence_type="sick",
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)

    with pytest.raises(HTTPException) as exc:
        review_change_request(
            request_id=str(cr.id),
            review=ChangeRequestReview(action="approve"),
            db=db, current_user=admin,
        )
    assert exc.value.status_code == 400
    assert "Feiertag" in exc.value.detail
    assert "Karfreitag" in exc.value.detail
