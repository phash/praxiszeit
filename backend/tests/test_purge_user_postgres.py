"""Endloeschung nach Art. 17 DSGVO gegen **echtes PostgreSQL**.

Warum diese Datei existiert
===========================
``admin_users.purge_user`` loescht einen Mitarbeiter endgueltig. Vorher muss es
JEDE Beziehung aufloesen, die auf ``users.id`` zeigt — sonst bricht PostgreSQL
den Vorgang mit einer Fremdschluesselverletzung ab (HTTP 500) und das
Loeschbegehren ist **blockiert**: der Betroffene bekommt sein Recht nicht,
der Betreiber hat keinen Weg, es zu erfuellen.

Geprueft wurde das bisher ausschliesslich gegen SQLite — und dort sind
Fremdschluessel **aus** (``conftest.py`` setzt nur ``journal_mode``,
``test_endpoints.py`` schaltet sie sogar ausdruecklich ab). Ein fehlendes
Aufraeumen faellt dort per Konstruktion nie auf; die Kommentare im
Produktivcode sagen das an vier Stellen selbst ("SQLite tests run FK off").
Der Praezedenzfall ist real: ``shift_plans.created_by`` (#305) war NOT NULL
ohne Loeschregel und riss die Erasure auf PostgreSQL auf.

Was diese Datei tut
===================
1. ``TestFremdschluesselInventar`` liest die Beziehungen auf ``users.id``
   **aus ``Base.metadata``** und vergleicht sie mit dem, was die Vorrichtung
   unten tatsaechlich befuellt. Eine neue Tabelle mit Verweis auf einen Nutzer
   macht diesen Test rot und benennt sie — die Abdeckung waechst also mit,
   statt als handgepflegte Liste zu veralten. Zusaetzlich wird die deklarierte
   Loeschregel gegen den **echten PostgreSQL-Katalog** gehalten: ein Modell,
   das ``ondelete="CASCADE"`` behauptet, waehrend die Migration es nie gesetzt
   hat, faellt sonst nirgends auf.
2. ``TestEndloeschung`` legt einen Nutzer mit Daten in **allen** dieser
   Tabellen an und loescht ihn ueber die echte Endpunktfunktion.
3. ``TestProtokollIntegritaet`` prueft, dass die Pruefsumme des
   Aenderungsprotokolls danach noch stimmt. Beim Umhaengen der vom Geloeschten
   verfassten Zeilen auf den handelnden Verwalter ist ``changed_by`` Teil des
   ``row_hash`` (#121): geschieht das per Massen-UPDATE statt ueber die
   Objektschicht, bleibt der gespeicherte Hash stehen und die
   Integritaetspruefung meldet legitime Zeilen anschliessend als manipuliert.

Wo diese Tests laufen
=====================
Nur mit erreichbarem PostgreSQL (sonst modulweiter Skip wie
``test_concurrency.py``). Eingehaengt in ``scripts/local-ci.sh`` Schritt 2 und
in den PostgreSQL-Schritt von ``.github/workflows/cross-tenant-ci.yml`` — eine
PostgreSQL-Datei, die in keinem Lauf vorkommt, waere wertlos.

Die Vorrichtung arbeitet auf der Migrations-/Eigentuemerverbindung
(``DATABASE_URL_MIGRATIONS``): RLS greift dort nicht, Fremdschluessel dagegen
voll — und genau die sind der Pruefgegenstand. Alle Zeilen haengen an einem
eigenen Mandanten mit fester UUID und werden am Ende restlos entfernt.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_DB_URL:
    pytest.skip(
        "test_purge_user_postgres.py braucht DATABASE_URL_MIGRATIONS "
        "(oder ADMIN_DB_URL); Aufruf mit `docker compose exec backend pytest …`.",
        allow_module_level=True,
    )

from app.core import audit_integrity
from app.database import Base
from app.models import (
    Absence,
    AbsenceType,
    CompanyClosure,
    ImpersonationSession,
    SignupToken,
    TimeEntry,
    TimeEntryAuditLog,
    User,
    UserRole,
    WorkingHoursChange,
)
from app.models.change_request import (
    ChangeRequest,
    ChangeRequestStatus,
    ChangeRequestType,
)
from app.models.error_log import ErrorLog
from app.models.shift_planning import (
    Location,
    ShiftAssignment,
    ShiftPlan,
    ShiftSlot,
    Workstation,
    WorkstationQualification,
)
from app.models.tenant import Tenant
from app.models.vacation_request import VacationRequest
from app.models.year_carryover import YearCarryover
from app.routers import admin_users

TENANT_ID = uuid.UUID("eeee0000-0000-4000-8000-000000000001")
VICTIM_ID = uuid.UUID("eeee0000-0000-4000-8000-000000000101")
ADMIN_ID = uuid.UUID("eeee0000-0000-4000-8000-000000000102")

# ArbZG §16: die Endloeschung ist erst nach 730 Tagen erlaubt. Ein fest
# verdrahtetes altes Datum haelt den Test unabhaengig vom Laufdatum.
LONG_AGO = date(2019, 3, 4)

# ---------------------------------------------------------------------------
# Was die Vorrichtung befuellt. Die Gegenprobe dazu steht in
# TestFremdschluesselInventar: diese Menge MUSS deckungsgleich mit dem sein,
# was ``Base.metadata`` an Verweisen auf ``users.id`` kennt.
# ---------------------------------------------------------------------------
SEEDED_USER_FK_COLUMNS = frozenset({
    ("absences", "user_id"),
    ("change_requests", "reviewed_by"),
    ("change_requests", "user_id"),
    ("company_closures", "created_by"),
    ("error_logs", "resolved_by"),
    ("error_logs", "user_id"),
    ("impersonation_sessions", "impersonator_id"),
    ("impersonation_sessions", "target_id"),
    ("shift_assignments", "user_id"),
    ("shift_plans", "created_by"),
    ("signup_tokens", "user_id"),
    ("time_entries", "user_id"),
    ("time_entry_audit_logs", "changed_by"),
    ("time_entry_audit_logs", "user_id"),
    ("vacation_requests", "last_modified_by"),
    ("vacation_requests", "reviewed_by"),
    ("vacation_requests", "user_id"),
    ("working_hours_changes", "user_id"),
    ("workstation_qualifications", "user_id"),
    ("year_carryovers", "user_id"),
})

# Loeschregel laut Modell → Kennbuchstabe in ``pg_constraint.confdeltype``.
_ONDELETE_TO_PG = {None: "a", "NO ACTION": "a", "CASCADE": "c", "SET NULL": "n",
                   "RESTRICT": "r", "SET DEFAULT": "d"}


def discovered_user_fk_columns() -> set[tuple[str, str]]:
    """Alle Spalten mit Fremdschluessel auf ``users.id`` — aus den Metadaten
    der Objektschicht, nicht aus einer gepflegten Liste."""
    found: set[tuple[str, str]] = set()
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "users":
                    found.add((table.name, column.name))
    return found


def declared_ondelete() -> dict[tuple[str, str], str | None]:
    out: dict[tuple[str, str], str | None] = {}
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "users":
                    out[(table.name, column.name)] = fk.ondelete
    return out


# ---------------------------------------------------------------------------
# Vorrichtung
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(ADMIN_DB_URL)
    yield engine
    engine.dispose()


def _wipe(engine):
    """Restlos alles zu diesem Mandanten entfernen — auch nach einem
    abgebrochenen Vorlauf. Reihenfolge: Kinder vor Eltern."""
    order = [
        "shift_assignments", "shift_slots", "workstation_qualifications",
        "shift_plans", "workstations", "locations",
        "time_entry_audit_logs", "change_requests", "vacation_requests",
        "absences", "time_entries", "working_hours_changes", "year_carryovers",
        "company_closures", "signup_tokens", "impersonation_sessions",
    ]
    with engine.connect() as conn:
        for table in order:
            conn.execute(text(f'DELETE FROM "{table}" WHERE tenant_id = :t'),
                         {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM error_logs WHERE tenant_id = :t"),
                     {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM users WHERE tenant_id = :t"),
                     {"t": str(TENANT_ID)})
        conn.execute(text("DELETE FROM tenants WHERE id = :t"),
                     {"t": str(TENANT_ID)})
        conn.commit()


@pytest.fixture(scope="function")
def welt(pg_engine):
    """Ein Mandant mit Verwalter und zu loeschendem Mitarbeiter — und je einer
    Zeile in JEDER Tabelle, die auf ``users.id`` verweist."""
    _wipe(pg_engine)
    Session = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    db = Session()

    db.add(Tenant(id=TENANT_ID, name="Purge PG", slug="purge-pg-test",
                  is_active=True, mode="multi"))
    db.flush()

    def _user(uid, username, role, active):
        return User(
            id=uid, tenant_id=TENANT_ID, username=username,
            email=f"{username}@purge.invalid", password_hash="nicht-echt",
            first_name="P", last_name="G", role=role, weekly_hours=40.0,
            vacation_days=30, work_days_per_week=5, is_active=active,
        )

    victim = _user(VICTIM_ID, "purge_victim", UserRole.EMPLOYEE, False)
    admin = _user(ADMIN_ID, "purge_admin", UserRole.ADMIN, True)
    db.add_all([victim, admin])
    db.flush()

    # ── §16-pflichtige Aufzeichnungen (alt genug fuer die 730-Tage-Frist) ──
    db.add(TimeEntry(tenant_id=TENANT_ID, user_id=VICTIM_ID, date=LONG_AGO,
                     start_time=time(8, 0), end_time=time(16, 0), break_minutes=30))
    db.add(Absence(tenant_id=TENANT_ID, user_id=VICTIM_ID,
                   date=LONG_AGO + timedelta(days=1),
                   type=AbsenceType.VACATION, hours=8.0))

    # ── Aenderungsprotokoll: die drei Faelle, die purge_user unterscheidet ──
    own = TimeEntryAuditLog(
        tenant_id=TENANT_ID, user_id=VICTIM_ID, changed_by=VICTIM_ID,
        action="create", source="manual", new_note="eigene Zeile")
    authored = TimeEntryAuditLog(
        tenant_id=TENANT_ID, user_id=ADMIN_ID, changed_by=VICTIM_ID,
        action="update", source="manual", new_note="vom Geloeschten verfasst")
    foreign = TimeEntryAuditLog(
        tenant_id=TENANT_ID, user_id=ADMIN_ID, changed_by=ADMIN_ID,
        action="update", source="manual", new_note="unbeteiligte Zeile")
    db.add_all([own, authored, foreign])

    # ── Antraege: eigene + fremde, die der Geloeschte beschieden hat ──
    db.add(ChangeRequest(
        tenant_id=TENANT_ID, user_id=VICTIM_ID,
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        reason="eigener Antrag"))
    db.add(ChangeRequest(
        tenant_id=TENANT_ID, user_id=ADMIN_ID, reviewed_by=VICTIM_ID,
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.APPROVED,
        reason="fremder Antrag, vom Geloeschten beschieden"))
    db.add(VacationRequest(
        tenant_id=TENANT_ID, user_id=VICTIM_ID, date=LONG_AGO, hours=8.0,
        absence_type="vacation", status="pending"))
    db.add(VacationRequest(
        tenant_id=TENANT_ID, user_id=ADMIN_ID, date=LONG_AGO, hours=8.0,
        absence_type="vacation", status="approved",
        reviewed_by=VICTIM_ID, last_modified_by=VICTIM_ID))

    # ── Vertrags-/Kontodaten ──
    db.add(WorkingHoursChange(
        tenant_id=TENANT_ID, user_id=VICTIM_ID, weekly_hours=20.0,
        effective_from=LONG_AGO))
    db.add(YearCarryover(
        tenant_id=TENANT_ID, user_id=VICTIM_ID, year=LONG_AGO.year + 1,
        overtime_hours=3.5, vacation_days=2.0, source="year_closing"))

    # ── Vom Geloeschten angelegte Objekte (NOT NULL ohne Loeschregel) ──
    db.add(CompanyClosure(
        tenant_id=TENANT_ID, name="Betriebsferien", start_date=LONG_AGO,
        end_date=LONG_AGO + timedelta(days=3), created_by=VICTIM_ID))
    location = Location(tenant_id=TENANT_ID, name="Standort")
    db.add(location)
    db.flush()
    workstation = Workstation(tenant_id=TENANT_ID, location_id=location.id,
                              name="Arbeitsplatz")
    db.add(workstation)
    plan = ShiftPlan(tenant_id=TENANT_ID, name="Plan", created_by=VICTIM_ID)
    db.add(plan)
    db.flush()
    slot = ShiftSlot(tenant_id=TENANT_ID, shift_plan_id=plan.id,
                     workstation_id=workstation.id, weekday=0,
                     start_time=time(8, 0), end_time=time(12, 0))
    db.add(slot)
    db.flush()
    db.add(ShiftAssignment(tenant_id=TENANT_ID, shift_slot_id=slot.id,
                           user_id=VICTIM_ID))
    db.add(WorkstationQualification(tenant_id=TENANT_ID, user_id=VICTIM_ID,
                                    workstation_id=workstation.id))

    # ── Anmeldeeinladung + Impersonation (beide Richtungen) ──
    db.add(SignupToken(tenant_id=TENANT_ID, user_id=VICTIM_ID,
                       token_hash="hash-" + uuid.uuid4().hex,
                       expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    db.add(ImpersonationSession(tenant_id=TENANT_ID, impersonator_id=ADMIN_ID,
                                target_id=VICTIM_ID))
    db.add(ImpersonationSession(tenant_id=TENANT_ID, impersonator_id=VICTIM_ID,
                                target_id=ADMIN_ID))

    # ── Fehlerprotokoll: haengt allein an der Loeschregel SET NULL ──
    db.add(ErrorLog(tenant_id=TENANT_ID, level="ERROR", logger="test",
                    message="Fehler", fingerprint="purge-pg-" + uuid.uuid4().hex,
                    user_id=VICTIM_ID, resolved_by=VICTIM_ID, status="open"))

    db.commit()

    try:
        yield db, victim, admin
    finally:
        db.close()
        _wipe(pg_engine)


def _count(db, model, **filters):
    q = db.query(model)
    for key, value in filters.items():
        q = q.filter(getattr(model, key) == value)
    return q.count()


# ---------------------------------------------------------------------------
# 1. Das Inventar — waechst von selbst mit
# ---------------------------------------------------------------------------

class TestFremdschluesselInventar:

    def test_vorrichtung_deckt_alle_verweise_auf_nutzer_ab(self):
        """Eine neue Tabelle mit Verweis auf ``users.id`` macht diesen Test rot
        und benennt sie — dann gehoert eine Zeile dafuer in ``welt`` und eine
        Zusicherung in ``TestEndloeschung``. Ohne das faellt das naechste
        ``shift_plans.created_by`` erst in Produktion auf."""
        discovered = discovered_user_fk_columns()
        fehlt_in_vorrichtung = sorted(discovered - SEEDED_USER_FK_COLUMNS)
        veraltet = sorted(SEEDED_USER_FK_COLUMNS - discovered)
        assert not fehlt_in_vorrichtung, (
            "Neue Beziehung(en) auf users.id ohne Abdeckung in dieser Datei: "
            f"{fehlt_in_vorrichtung}. Zeile in der Vorrichtung `welt` anlegen "
            "und in SEEDED_USER_FK_COLUMNS eintragen."
        )
        assert not veraltet, f"nicht mehr vorhandene Beziehung(en): {veraltet}"

    def test_modell_und_datenbank_nennen_dieselbe_loeschregel(self, pg_engine):
        """Drift zwischen Modell und Migration.

        ``purge_user`` verlaesst sich an mehreren Stellen darauf, dass die
        Datenbank selbst aufraeumt (``year_carryovers`` CASCADE,
        ``error_logs``/``vacation_requests.last_modified_by`` SET NULL) — es
        gibt dafuer keine Zeile im Produktivcode. Behauptet das Modell eine
        Regel, die in der Datenbank nie gesetzt wurde, bricht die Erasure,
        ohne dass irgendein Modelltest etwas merkt.
        """
        rows = pg_engine.connect().execute(text("""
            SELECT src.relname AS tabelle,
                   att.attname  AS spalte,
                   con.confdeltype AS regel
            FROM pg_constraint con
            JOIN pg_class src   ON src.oid = con.conrelid
            JOIN pg_class dst   ON dst.oid = con.confrelid
            JOIN unnest(con.conkey) AS k(attnum) ON true
            JOIN pg_attribute att ON att.attrelid = con.conrelid
                                 AND att.attnum = k.attnum
            WHERE con.contype = 'f' AND dst.relname = 'users'
        """)).all()
        tatsaechlich = {(r.tabelle, r.spalte): r.regel for r in rows}
        assert tatsaechlich, "keine Fremdschluessel auf users gefunden — falsche DB?"

        abweichungen = []
        for key, ondelete in declared_ondelete().items():
            if key not in tatsaechlich:
                continue  # Tabelle existiert in der DB (noch) nicht — anderer Test
            erwartet = _ONDELETE_TO_PG[ondelete]
            if tatsaechlich[key] != erwartet:
                abweichungen.append(
                    f"{key[0]}.{key[1]}: Modell={ondelete or 'NO ACTION'} "
                    f"DB={tatsaechlich[key]}")
        assert not abweichungen, "; ".join(abweichungen)


# ---------------------------------------------------------------------------
# 2. Die Loeschung selbst
# ---------------------------------------------------------------------------

class TestEndloeschung:

    def test_loeschung_laeuft_mit_scharfen_fremdschluesseln_durch(self, welt):
        """Der Kern: mit erzwungenen Fremdschluesseln und Daten in allen 20
        verweisenden Spalten muss die Erasure durchgehen. Fehlt eine
        Aufraeumung, wirft PostgreSQL ``ForeignKeyViolation`` → HTTP 500 →
        das Loeschbegehren ist nicht erfuellbar."""
        db, victim, admin = welt
        result = admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        assert "endgültig gelöscht" in result["message"]
        assert _count(db, User, id=VICTIM_ID) == 0

    def test_eigene_daten_des_geloeschten_sind_weg(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        for model in (TimeEntry, Absence, WorkingHoursChange, YearCarryover,
                      ChangeRequest, VacationRequest, SignupToken,
                      ShiftAssignment, WorkstationQualification):
            assert _count(db, model, user_id=VICTIM_ID) == 0, model.__name__

    def test_datenbankseitige_loeschregeln_greifen(self, welt):
        """Diese drei raeumt ``purge_user`` NICHT selbst auf — hier arbeitet
        allein die Loeschregel der Datenbank. Unter SQLite mit abgeschalteten
        Fremdschluesseln bliebe stattdessen ein verwaister Verweis stehen, ohne
        dass ein Test etwas merkte."""
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)

        # year_carryovers: ON DELETE CASCADE
        assert db.query(YearCarryover).filter(
            YearCarryover.tenant_id == TENANT_ID).count() == 0
        # error_logs: ON DELETE SET NULL auf beiden Spalten
        error = db.query(ErrorLog).filter(ErrorLog.tenant_id == TENANT_ID).one()
        assert error.user_id is None
        assert error.resolved_by is None
        # vacation_requests.last_modified_by: ON DELETE SET NULL
        fremd = db.query(VacationRequest).filter(
            VacationRequest.user_id == ADMIN_ID).one()
        assert fremd.last_modified_by is None

    def test_fremde_objekte_werden_umgehaengt_statt_geloescht(self, welt):
        """``created_by`` ist NOT NULL: die Objekte muessen dem handelnden
        Verwalter zugeschlagen werden, nicht mitgeloescht — sonst verschwaende
        die Endloeschung eines Mitarbeiters die Betriebsferien des Betriebs."""
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)

        closure = db.query(CompanyClosure).filter(
            CompanyClosure.tenant_id == TENANT_ID).one()
        assert closure.created_by == ADMIN_ID
        plan = db.query(ShiftPlan).filter(ShiftPlan.tenant_id == TENANT_ID).one()
        assert plan.created_by == ADMIN_ID

    def test_fremde_antraege_bleiben_ohne_pruefer_stehen(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        fremd = db.query(ChangeRequest).filter(
            ChangeRequest.user_id == ADMIN_ID).one()
        assert fremd.reviewed_by is None
        fremd_urlaub = db.query(VacationRequest).filter(
            VacationRequest.user_id == ADMIN_ID).one()
        assert fremd_urlaub.reviewed_by is None

    def test_impersonation_in_beide_richtungen_entfernt(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        assert db.query(ImpersonationSession).filter(
            ImpersonationSession.tenant_id == TENANT_ID).count() == 0

    def test_loeschung_wird_protokolliert_ohne_klarnamen(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        marker = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.action == "dsgvo_purge",
            TimeEntryAuditLog.tenant_id == TENANT_ID).one()
        assert str(VICTIM_ID) in marker.old_note
        assert marker.changed_by == ADMIN_ID
        # Der Zweck der Loeschung ist gerade die Namensloeschung.
        assert "purge_victim" not in (marker.old_note or "")


# ---------------------------------------------------------------------------
# 3. Das Aenderungsprotokoll bleibt beweiskraeftig
# ---------------------------------------------------------------------------

class TestProtokollIntegritaet:

    def test_umgehaengte_zeilen_bleiben_unbeanstandet(self, welt):
        """``changed_by`` geht in den ``row_hash`` (#121) ein. Wird es per
        Massen-UPDATE umgehaengt, umgeht das den Hash-Hook, der gespeicherte
        Hash wird ungueltig — und ``verify-integrity`` meldet die Zeile nach
        JEDER Endloeschung als manipuliert. Ein falscher Manipulationsalarm im
        §16-Nachweis ist schlimmer als kein Alarm."""
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        db.expire_all()

        rows = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.tenant_id == TENANT_ID,
            TimeEntryAuditLog.row_hash.isnot(None)).all()
        assert rows, "keine hashbaren Protokollzeilen uebrig"
        beanstandet = [r.new_note or r.old_note for r in rows
                       if not audit_integrity.verify_row(r)]
        assert not beanstandet, f"faelschlich als manipuliert gemeldet: {beanstandet}"

    def test_verfasste_zeile_haengt_am_handelnden_verwalter(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        db.expire_all()
        row = db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.new_note == "vom Geloeschten verfasst").one()
        assert row.changed_by == ADMIN_ID
        assert audit_integrity.verify_row(row)

    def test_eigene_protokollzeilen_des_geloeschten_sind_entfernt(self, welt):
        db, victim, admin = welt
        admin_users.purge_user(str(VICTIM_ID), db=db, current_user=admin)
        assert db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.new_note == "eigene Zeile").count() == 0
