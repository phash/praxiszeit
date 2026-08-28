"""``lifecycle_service.anonymize_tenant`` — bleibt danach personenbezogenes uebrig?

Warum diese Datei existiert
===========================
``anonymize_tenant`` ist der Pfad, der einen ganzen Mandanten 30 Tage nach
seinem Loeschantrag entpersonalisiert (Cron, taeglich 03:00). Er setzt am Ende
``tenant.anonymized_at`` — und markiert die Loeschung damit gegenueber Aufsicht
und Betroffenen als **erledigt**. Was hier stehenbleibt, bleibt fuer immer
stehen: einen zweiten Durchlauf gibt es nicht.

Die bisherige Abdeckung (``test_tenant_lifecycle.py::test_cron_anonymizes_after_grace``)
prueft acht namentlich genannte Felder — genau die acht, die die Funktion auch
anfasst. Sie kann per Konstruktion nicht auffallen, wenn ein personenbezogenes
Feld gar nicht erst angefasst wird. Genau das war der Fall: der
Geschwisterpfad ``admin_users.anonymize_user`` scrubbt zusaetzlich
``profile_picture`` (Base64-Lichtbild, Art. 4 Nr. 1 DSGVO — identifiziert die
Person unmittelbar), ``totp_secret``, ``department`` und
``WorkingHoursChange.note``; im Mandantenpfad fehlten alle vier.

Diese Datei prueft deshalb nicht "die Funktion laeuft durch", sondern
**"nichts Personenbezogenes ist danach noch auffindbar"**: jedes gesaete Feld
traegt eine eindeutige Zeichenfolge, und nach dem Lauf wird die **gesamte
Datenbank** — jede Tabelle aus ``Base.metadata``, jede Spalte, jede Zeile —
danach durchsucht. Eine kuenftige Tabelle, in der eine dieser Zeichenfolgen
landet, faellt damit von selbst auf, ohne dass jemand diese Datei pflegt.

Bewusst NICHT geprueft (beides ist so gewollt, siehe Modul-Docstring von
``lifecycle_service``):

* ``time_entries``/``absences`` bleiben stehen — ArbZG §16 verlangt zwei Jahre
  Aufbewahrung, sie haengen danach an anonymisierten Fremdschluesseln.
  ``TestAufbewahrungBleibt`` nagelt genau das als gewollt fest.
* ``token_version`` wird nicht hochgezaehlt — ``auth.py`` sperrt bereits ueber
  ``is_active``.

#435 (behoben): ``tenants.slug`` wurde aus dem Praxisnamen abgeleitet
(``signup_service._slug_from_name``) und blieb bislang ungeschrubbt, waehrend
``tenants.name`` geschrubbt wurde — der Klarname stand danach weiter in einer
eindeutigen, extern sichtbaren Kennung. ``anonymize_tenant`` ersetzt den Slug
jetzt durch ``anon-<tenant_id>`` (eindeutig, kollidiert nicht an der
Unique-Constraint) — ausser beim On-Prem-Default-Mandanten
(``slug == "default"``), den ``main.py`` beim Bootstrap ueber genau diesen
Slug sucht. ``slug`` steht deshalb jetzt in ``PII`` statt in ``KEPT``;
``TestSlugEindeutigkeit`` deckt den Unique-Fall bei zwei anonymisierten
Mandanten ab.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import Base
from app.core import audit_integrity
from app.models import (
    Absence,
    AbsenceType,
    SignupAuditLog,
    TimeEntry,
    TimeEntryAuditLog,
    User,
    UserRole,
    WorkingHoursChange,
)
from app.models.shift_planning import ShiftPlan, ShiftSlot, Workstation
from app.models.tenant import Tenant
from app.services import auth_service, lifecycle_service, signup_service
from tests.conftest import TestingSessionLocal, engine

TID = uuid.UUID("cccccccc-0000-4000-8000-00000000000c")
OTHER_TID = uuid.UUID("dddddddd-0000-4000-8000-00000000000d")

# ---------------------------------------------------------------------------
# Die gesaeten Zeichenfolgen. Jede steht fuer genau ein personenbezogenes Feld
# und kommt sonst nirgends im System vor — die Suche unten kann also keine
# Fehlalarme durch Beschriftungen oder Vorgabewerte erzeugen.
# ---------------------------------------------------------------------------
PII = {
    "username": "PIIUSERNAMEAAA",
    "email": "PIIMAILAAA@praxis.invalid",
    "first_name": "PIIVORNAMEAAA",
    "last_name": "PIINACHNAMEAAA",
    "department": "PIIABTEILUNGAAA",
    "profile_picture": "data:image/png;base64,PIILICHTBILDAAA",
    "totp_secret": "PIITOTPGEHEIMNISAAA",
    "wh_note": "PIIVERTRAGSNOTIZAAA",
    "tenant_name": "PIIPRAXISNAMEAAA",
    # #435: der Slug wird beim Signup real aus dem Praxisnamen abgeleitet
    # (``signup_service._slug_from_name``) — hier ueber dieselbe Funktion
    # berechnet, damit der Fixture-Wert exakt das simuliert, was in Produktion
    # tatsaechlich in ``tenants.slug`` landet.
    "tenant_slug": signup_service._slug_from_name("PIIPRAXISNAMEAAA", set()),
    "company_name": "PIIFIRMAAAA",
    "vat_id": "PIIUSTIDAAA",
    "billing_email": "PIIRECHNUNGAAA@praxis.invalid",
    "billing_street": "PIISTRASSEAAA",
    "signup_email": "PIIANMELDUNGAAA@praxis.invalid",
    "signup_ip": "203.0.113.77",
    "signup_agent": "PIIBROWSERAAA",
    # Release-Review 1.18.1: die Freitext-Notizen des Aenderungsprotokolls.
    # ``auth.py`` schreibt bei JEDEM Selbstbedienungs-E-Mail-Wechsel die alte
    # UND die neue Adresse im Klartext nach ``old_note``; ``reports.py`` und
    # ``journal.py`` schreiben bei jedem Zugriff auf Gesundheitsdaten den
    # Benutzernamen nach ``new_note``. Beides sind direkte Identifikatoren —
    # genau die Werte, die die Anonymisierung auf der ``users``-Zeile
    # ueberschreibt.
    "audit_alte_mail": "PIIAUDITMAILAAA@praxis.invalid",
    "audit_benutzername": "PIIAUDITADMINAAA",
    # #443: der Hinweis je Schicht-Einteilung ist Admin-Freitext und traegt
    # regelmaessig Personenbezug ("Einarbeitung Frau Meier"). Ein neues
    # Freitextfeld, das die Anonymisierung ueberlebt, verlaengert die Restliste
    # aus #440 — deshalb hier gleich mit gesaet.
    "shift_note": "PIISCHICHTNOTIZAAA",
    # #461 K-4: dieselbe Begruendung wie beim Hinweis je Einteilung gilt woertlich
    # fuer Name und Beschreibung eines Schichtplans ("Vertretungsplan Frau Meier").
    "shift_plan_name": "PIIPLANNAMEAAA",
    "shift_plan_description": "PIIPLANBESCHREIBUNGAAA",
}

# Diese bleiben absichtlich stehen und duerfen die Suche nicht ausloesen.
KEPT = {
    "stripe_customer": "cus_PIIWIRDBEHALTEN",
}


@pytest.fixture(scope="function")
def _db_session():
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.commit()
        Base.metadata.drop_all(bind=engine, checkfirst=True)


@pytest.fixture(scope="function")
def mandant(_db_session):
    """Ein Mandant, dessen personenbezogene Felder alle belegt sind."""
    tenant = Tenant(
        id=TID,
        name=PII["tenant_name"],
        slug=PII["tenant_slug"],
        is_active=True,
        mode="multi",
        plan="trial",
        subscription_status="active",
        company_name=PII["company_name"],
        vat_id=PII["vat_id"],
        country="DE",
        billing_email=PII["billing_email"],
        billing_address={"street": PII["billing_street"], "city": "Musterstadt"},
        stripe_customer_id=KEPT["stripe_customer"],
        stripe_subscription_id="sub_behalten",
    )
    _db_session.add(tenant)
    _db_session.commit()

    user = User(
        username=PII["username"],
        email=PII["email"],
        password_hash=auth_service.hash_password("Anonym2026!Test"),
        first_name=PII["first_name"],
        last_name=PII["last_name"],
        department=PII["department"],
        profile_picture=PII["profile_picture"],
        totp_secret=PII["totp_secret"],
        totp_enabled=True,
        last_totp_counter=4711,
        role=UserRole.ADMIN,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
        tenant_id=TID,
    )
    _db_session.add(user)
    _db_session.commit()
    _db_session.refresh(user)

    _db_session.add(WorkingHoursChange(
        user_id=user.id, tenant_id=TID, weekly_hours=20.0,
        effective_from=date(2026, 3, 1), note=PII["wh_note"],
    ))
    _db_session.add(SignupAuditLog(
        tenant_id=TID, email=PII["signup_email"], event="signup_requested",
        ip_address=PII["signup_ip"], user_agent=PII["signup_agent"],
        accepted_terms=True, accepted_privacy=True,
    ))
    _db_session.add(TimeEntry(
        user_id=user.id, tenant_id=TID, date=date(2026, 3, 2),
        start_time=time(8, 0), end_time=time(16, 0), break_minutes=30,
    ))
    _db_session.add(Absence(
        user_id=user.id, tenant_id=TID, date=date(2026, 3, 3),
        type=AbsenceType.VACATION, hours=8.0,
    ))
    # Zwei Protokollzeilen, wortgleich zu dem, was die Anwendung schreibt.
    _db_session.add(TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=user.id,
        action="update", source="self_service",
        old_note=f"E-Mail geändert: {PII['audit_alte_mail']} → neu@praxis.invalid",
        tenant_id=TID,
    ))
    _db_session.add(TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=user.id,
        action="health_data_access", source="dsgvo",
        new_note=("Monatsreport 2026-03 (inkl. Krankheitsstunden) gelesen von "
                  f"Admin: {PII['audit_benutzername']}"),
        tenant_id=TID,
    ))
    # Eine Zeile OHNE Freitext — sie darf der Lauf nicht anfassen (Kontrolle
    # fuer die Byte-Identitaet des #121-row_hash).
    _db_session.add(TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=user.id,
        action="create", source="manual",
        old_date=date(2026, 3, 2), new_date=date(2026, 3, 2),
        new_break_minutes=30, tenant_id=TID,
    ))
    plan = ShiftPlan(
        tenant_id=TID,
        name=PII["shift_plan_name"],
        description=PII["shift_plan_description"],
        created_by=user.id,
    )
    _db_session.add(plan)
    workstation = Workstation(tenant_id=TID, name="Tresen")
    _db_session.add(workstation)
    _db_session.commit()
    _db_session.refresh(plan)
    _db_session.refresh(workstation)
    _db_session.add(ShiftSlot(
        tenant_id=TID, shift_plan_id=plan.id, workstation_id=workstation.id,
        weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        note=PII["shift_note"],
    ))
    _db_session.commit()
    return {"tenant": tenant, "user_id": user.id}


def _sweep(db) -> dict[str, list[str]]:
    """Durchsucht JEDE Tabelle, JEDE Spalte, JEDE Zeile nach den gesaeten
    Zeichenfolgen und liefert ``{zeichenfolge: [fundstellen]}``.

    Ueber ``Base.metadata`` — nicht ueber eine handgepflegte Liste. Eine neue
    Tabelle, in der eines der Felder landet, wird damit ohne Pflege dieser
    Datei erfasst.
    """
    hits: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(text(f'SELECT * FROM "{table.name}"')).mappings().all()
        for row in rows:
            for column, value in row.items():
                if value is None:
                    continue
                haystack = str(value)
                for label, needle in PII.items():
                    if needle in haystack:
                        hits.setdefault(label, []).append(
                            f"{table.name}.{column}")
    return hits


class TestVorrichtung:
    """Selbstkontrolle: VOR der Anonymisierung muss die Suche alles finden.

    Ohne diesen Test koennte die Suche unten auch dann gruen sein, wenn sie
    schlicht nichts findet (falsche Tabellen, leere Datenbank, kaputtes SQL).
    """

    def test_alle_gesaeten_felder_sind_vor_dem_lauf_auffindbar(self, _db_session, mandant):
        hits = _sweep(_db_session)
        fehlend = sorted(set(PII) - set(hits))
        assert not fehlend, f"nicht gesaet oder nicht gefunden: {fehlend}"


class TestKeinePersonenbezogenenDatenMehr:

    def test_sweep_findet_nach_der_anonymisierung_nichts_mehr(self, _db_session, mandant):
        """Der Kern: nach ``anonymize_tenant`` darf KEINE der gesaeten
        Zeichenfolgen irgendwo in der Datenbank stehen."""
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()

        hits = _sweep(_db_session)
        assert hits == {}, "personenbezogene Reste: " + "; ".join(
            f"{k} in {v}" for k, v in sorted(hits.items()))

    def test_lichtbild_und_zweiter_faktor_sind_weg(self, _db_session, mandant):
        """Namentlich, damit ein Fehlschlag sofort sagt, WELCHE Regel fiel.

        Das Base64-Lichtbild identifiziert die Person unmittelbar (Art. 4
        Nr. 1) — mit ihm im Bestand ist die Pseudonymisierung wirkungslos,
        egal wie der Anzeigename lautet.
        """
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        user = _db_session.query(User).filter(User.id == mandant["user_id"]).one()
        assert user.profile_picture is None
        assert user.totp_secret is None
        assert user.totp_enabled is False
        assert user.last_totp_counter is None
        assert user.department is None

    def test_vertragsnotiz_geleert_zeile_bleibt(self, _db_session, mandant):
        """#431: die Vertragshistorie traegt das historische Soll (§16) und
        bleibt deshalb stehen — ihr freier Notiztext ist aber Admin-Prosa ohne
        Aufbewahrungspflicht und muss weg."""
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        changes = _db_session.query(WorkingHoursChange).filter(
            WorkingHoursChange.tenant_id == TID).all()
        assert len(changes) == 1, "die Zeile selbst darf nicht verschwinden"
        assert changes[0].note is None
        assert float(changes[0].weekly_hours) == 20.0

    def test_protokollnotizen_geleert_zeilen_bleiben(self, _db_session, mandant):
        """Release-Review 1.18.1: die Freitext-Notizen des Aenderungsprotokolls
        tragen E-Mail-Adresse und Benutzernamen im Klartext. Die Zeilen selbst
        bleiben (sie belegen, WER WANN WAS an einer Zeitaufzeichnung geaendert
        hat — §16-relevant); ihre Prosa muss weg."""
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        rows = _db_session.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == TID).all()
        assert len(rows) == 3, "die Zeilen selbst duerfen nicht verschwinden"
        assert all(r.old_note is None and r.new_note is None for r in rows)
        # Die strukturierte Aussage der Zeile bleibt vollstaendig erhalten.
        strukturiert = [r for r in rows if r.source == "manual"][0]
        assert strukturiert.action == "create"
        assert strukturiert.old_date == date(2026, 3, 2)
        assert strukturiert.new_break_minutes == 30

    def test_manipulationsschutz_bleibt_nach_dem_lauf_gueltig(self, _db_session, mandant):
        """#121: ``row_hash`` deckt ``old_note``/``new_note`` mit ab. Wird die
        Notiz per Bulk-UPDATE geleert, umgeht das den ``before_insert``-Hook,
        der gespeicherte Hash wird schal und ``verify-integrity`` meldet danach
        JEDE dieser legitimen Zeilen als manipuliert."""
        vorher = {
            r.id: r.row_hash
            for r in _db_session.query(TimeEntryAuditLog).filter(
                TimeEntryAuditLog.tenant_id == TID).all()
        }
        assert all(h for h in vorher.values()), "Vorrichtung: alle Zeilen tragen einen Hash"

        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()

        rows = _db_session.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == TID).all()
        schal = [r.id for r in rows if not audit_integrity.verify_row(r)]
        assert not schal, f"row_hash nach der Anonymisierung nicht mehr gueltig: {schal}"
        # Die unberuehrte Zeile behaelt ihren Hash unveraendert.
        unberuehrt = [r for r in rows if r.source == "manual"][0]
        assert unberuehrt.row_hash == vorher[unberuehrt.id]

    def test_kein_login_mehr_moeglich(self, _db_session, mandant):
        """Der Passwort-Hash wird durch einen unbrauchbaren Platzhalter
        ersetzt — sonst bliebe das Konto trotz Anonymisierung betretbar."""
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        user = _db_session.query(User).filter(User.id == mandant["user_id"]).one()
        assert user.is_active is False
        assert user.password_hash.startswith("!disabled:")
        assert auth_service.verify_password("Anonym2026!Test", user.password_hash) is False

    def test_anmelde_protokoll_bleibt_ohne_personenbezug(self, _db_session, mandant):
        """Die Einwilligungszeile muss bleiben (Nachweis der Einwilligung),
        ihr Personenbezug nicht."""
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        rows = _db_session.query(SignupAuditLog).filter(
            SignupAuditLog.tenant_id == TID).all()
        assert len(rows) == 1
        assert rows[0].accepted_terms is True
        assert rows[0].accepted_privacy is True
        assert rows[0].email == "[anon]"
        assert rows[0].ip_address is None
        assert rows[0].user_agent is None

    def test_mandant_ist_markiert_und_stillgelegt(self, _db_session, mandant):
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        tenant = _db_session.query(Tenant).filter(Tenant.id == TID).one()
        assert tenant.anonymized_at is not None
        assert tenant.is_active is False
        assert tenant.subscription_status == "canceled"
        assert tenant.name == "[gelöscht]"
        assert tenant.billing_address is None
        # #435: der Slug trug den Praxisnamen weiter, obwohl name geschrubbt
        # wurde. Der Ersatzwert ist an die Tenant-ID gebunden statt konstant
        # (siehe TestSlugEindeutigkeit) und traegt selbst keinen Personenbezug.
        assert tenant.slug == f"anon-{TID}"


class TestAufbewahrungBleibt:
    """Was bewusst stehenbleibt — damit ein spaeterer "Aufraeum"-Beitrag nicht
    versehentlich die §16-Aufbewahrung mitloescht."""

    def test_zeiteintraege_und_abwesenheiten_bleiben(self, _db_session, mandant):
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        assert _db_session.query(TimeEntry).filter(
            TimeEntry.tenant_id == TID).count() == 1
        assert _db_session.query(Absence).filter(
            Absence.tenant_id == TID).count() == 1
        # Sie haengen weiter an der (jetzt anonymen) Benutzerzeile.
        assert _db_session.query(User).filter(User.id == mandant["user_id"]).count() == 1

    def test_stripe_kennungen_bleiben_fuer_die_buchhaltung(self, _db_session, mandant):
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()
        tenant = _db_session.query(Tenant).filter(Tenant.id == TID).one()
        assert tenant.stripe_customer_id == KEPT["stripe_customer"]
        assert tenant.stripe_subscription_id == "sub_behalten"


class TestFremderMandantUnberuehrt:

    def test_anonymisierung_greift_nur_den_eigenen_mandanten(self, _db_session, mandant):
        """Ein Bulk-UPDATE ohne Mandantenfilter wuerde hier auffallen — der
        Notiztext des Nachbarn ueberlebt den Lauf."""
        _db_session.add(Tenant(id=OTHER_TID, name="Nachbar", slug="nachbar",
                               is_active=True, mode="multi"))
        _db_session.commit()
        other = User(
            username="nachbar_admin", email="nachbar@praxis.invalid",
            password_hash=auth_service.hash_password("Nachbar2026!Test"),
            first_name="Nach", last_name="Bar", department="Empfang",
            profile_picture="data:image/png;base64,NACHBARBILD",
            totp_secret="NACHBARTOTP", totp_enabled=True,
            role=UserRole.ADMIN, weekly_hours=40.0, vacation_days=30,
            work_days_per_week=5, is_active=True, tenant_id=OTHER_TID,
        )
        _db_session.add(other)
        _db_session.commit()
        _db_session.refresh(other)
        _db_session.add(WorkingHoursChange(
            user_id=other.id, tenant_id=OTHER_TID, weekly_hours=30.0,
            effective_from=date(2026, 2, 1), note="Nachbarnotiz bleibt",
        ))
        _db_session.add(TimeEntryAuditLog(
            time_entry_id=None, user_id=other.id, changed_by=other.id,
            action="update", source="self_service",
            old_note="E-Mail geändert: alt@nachbar.invalid → neu@nachbar.invalid",
            tenant_id=OTHER_TID,
        ))
        _db_session.commit()

        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        _db_session.expire_all()

        kept = _db_session.query(User).filter(User.id == other.id).one()
        assert kept.username == "nachbar_admin"
        assert kept.email == "nachbar@praxis.invalid"
        assert kept.profile_picture == "data:image/png;base64,NACHBARBILD"
        assert kept.totp_secret == "NACHBARTOTP"
        assert kept.department == "Empfang"
        assert kept.is_active is True
        note = _db_session.query(WorkingHoursChange).filter(
            WorkingHoursChange.tenant_id == OTHER_TID).one().note
        assert note == "Nachbarnotiz bleibt"
        fremd_log = _db_session.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == OTHER_TID).one()
        assert fremd_log.old_note == (
            "E-Mail geändert: alt@nachbar.invalid → neu@nachbar.invalid")
        assert audit_integrity.verify_row(fremd_log) is True


class TestUeberDenCronPfad:
    """Derselbe Lauf, wie ihn der taegliche Scheduler ausloest
    (``apply_scheduled_deletions`` → ``anonymize_tenant(commit=False)``)."""

    def test_cron_hinterlaesst_ebenfalls_nichts(self, _db_session, mandant):
        mandant["tenant"].deletion_requested_at = (
            datetime.now(timezone.utc) - timedelta(days=35))
        _db_session.commit()

        assert lifecycle_service.apply_scheduled_deletions(_db_session) == 1
        _db_session.expire_all()

        hits = _sweep(_db_session)
        assert hits == {}, "personenbezogene Reste nach dem Cron-Lauf: " + "; ".join(
            f"{k} in {v}" for k, v in sorted(hits.items()))


class TestSlugEindeutigkeit:
    """#435: ``slug`` ist unique. Ein konstanter Ersatzwert (z.B. schlicht
    "geloescht") wuerde beim zweiten anonymisierten Mandanten mit einem
    ``IntegrityError`` kollidieren — genau der Fallstrick, den das Ticket
    benennt. Der gewaehlte Ersatzwert (``anon-<tenant_id>``) haengt an der
    Tenant-ID und ist damit von Natur aus eindeutig."""

    def test_zwei_anonymisierte_mandanten_kollidieren_nicht(self, _db_session, mandant):
        zweiter = Tenant(
            id=OTHER_TID, name="Zweite Praxis", slug="zweite-praxis-slug",
            is_active=True, mode="multi",
        )
        _db_session.add(zweiter)
        _db_session.commit()

        # Beide Laeufe committen selbst (Default `commit=True`) — kollidiert
        # der Ersatzwert, schlaegt der zweite Aufruf mit IntegrityError fehl.
        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        lifecycle_service.anonymize_tenant(_db_session, zweiter)

        _db_session.expire_all()
        erster = _db_session.query(Tenant).filter(Tenant.id == TID).one()
        zweiter_db = _db_session.query(Tenant).filter(Tenant.id == OTHER_TID).one()
        assert erster.slug == f"anon-{TID}"
        assert zweiter_db.slug == f"anon-{OTHER_TID}"
        assert erster.slug != zweiter_db.slug

    def test_gleicher_ausgangs_slug_kollidiert_ebenfalls_nicht(self, _db_session, mandant):
        """Selbst wenn zwei Mandanten (Kollisions-Suffix aus
        ``_slug_from_name``, z.B. "praxis-mueller"/"praxis-mueller-2")
        zufaellig denselben Ausgangs-Slug-Stamm teilen, entscheidet am Ende
        die Tenant-ID — nicht der alte Slug-Wert."""
        zweiter = Tenant(
            id=OTHER_TID, name="Andere Praxis", slug=PII["tenant_slug"] + "-2",
            is_active=True, mode="multi",
        )
        _db_session.add(zweiter)
        _db_session.commit()

        lifecycle_service.anonymize_tenant(_db_session, mandant["tenant"])
        lifecycle_service.anonymize_tenant(_db_session, zweiter)

        _db_session.expire_all()
        slugs = {
            t.slug for t in _db_session.query(Tenant).filter(
                Tenant.id.in_([TID, OTHER_TID])).all()
        }
        assert len(slugs) == 2


class TestDefaultMandantSlugBleibt:
    """#435: ``main.py`` sucht den On-Prem-Default-Mandanten beim Bootstrap
    ueber ``Tenant.slug == "default"``. Ein Selbstbedienungs-Loeschantrag ist
    zwar als SaaS-Pfad gedacht, aber technisch nicht auf ``is_saas()``
    gegated — ein On-Prem-Admin kann ihn fuer den eigenen (Default-)Mandanten
    ausloesen. Ein umgeschriebener Slug faende den Default-Mandanten beim
    naechsten Start nicht mehr (Totalausfall)."""

    def test_default_slug_wird_nicht_umgeschrieben(self, _db_session):
        default = Tenant(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Default", slug="default", is_active=True, mode="single",
        )
        _db_session.add(default)
        _db_session.commit()

        lifecycle_service.anonymize_tenant(_db_session, default)
        _db_session.expire_all()

        tenant = _db_session.query(Tenant).filter(Tenant.slug == "default").first()
        assert tenant is not None, (
            "main.py-Bootstrap faende den Default-Mandanten nicht mehr")
        assert tenant.name == "[gelöscht]", "name wird trotzdem geschrubbt"
