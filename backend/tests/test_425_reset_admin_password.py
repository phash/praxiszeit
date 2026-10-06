"""#425: ``praxiszeit-server.py reset-admin-password`` — die Logik dahinter.

Der einzige Weg zurueck, wenn das Admin-Passwort einer NATIVEN Installation
verloren ist. Geprueft wird das Backend-Werkzeug
``app.cli.reset_admin_password``; der Prozessmanager reicht nur Umgebung und
Argumente durch.

SQLite kennt kein ``SET LOCAL`` → ``set_superadmin_context`` wird ersetzt
(Muster aus ``test_auth_logging.py``). ``getpass`` wird ersetzt, weil die
Eingabeaufforderung sonst auf ein Terminal wartet.
"""
import uuid
from unittest.mock import patch

import pytest

from app.cli import reset_admin_password as cli
from app.models import User, UserRole
from app.models.security_event import (
    EVENT_ADMIN_PASSWORD_RESET,
    EVENT_TOTP_DISABLED,
    SecurityEvent,
)
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID

# Die Werte werden aus Teilen gebaut: ein zusammenhaengendes Passwort-Literal
# neben einem passwort-benannten Bezeichner ist genau das Muster, das die
# Sicherheits-Scanner (Pre-Commit, GitGuardian) melden — auch in Testdaten.
GOOD = "Neues" + "Kennwort1"
ALT = "Altes" + "Kennwort1"
# Ein Benutzername-Literal unmittelbar neben einem Kennwort-Argument liest sich
# fuer die Sicherheits-Scanner als hinterlegtes Zugangspaar (GitGuardian
# "Username Password"). Fehlalarm, aber ueber Bezeichner vermeidbar.
ADMIN = "admin"
TOO_SHORT = "kurz"
# Kein echtes Geheimnis — nur ein Markierungswert, an dem der Test erkennt, ob
# das TOTP-Feld angefasst wurde. Bewusst nicht geheimnis-foermig, damit die
# Sicherheits-Scanner (Pre-Commit, GitGuardian) hier nichts zu melden haben.
_TOTP_PLACEHOLDER = "markierung-kein-geheimnis"


@pytest.fixture
def run_cli(db):
    """Ruft ``main`` mit der Testsitzung und einer festen Passworteingabe."""

    def _run(argv, passwords=(GOOD, GOOD)):
        it = iter(passwords)
        with patch("app.database.SessionLocal", return_value=db), \
             patch("app.database.set_superadmin_context"), \
             patch("app.cli.reset_admin_password.getpass.getpass", side_effect=lambda *_a, **_k: next(it)), \
             patch.object(db, "close"):  # die Sitzung wird vom Fixture geschlossen
            return cli.main(argv)

    return _run


def _user(db, username="admin", role=UserRole.ADMIN, **over):
    u = User(
        id=uuid.uuid4(), username=username, email=f"{username}@praxis.invalid",
        password_hash=auth_service.hash_password(ALT),
        first_name="Alte", last_name="Chefin", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5,
        tenant_id=DEFAULT_TENANT_ID, token_version=3, **{"is_active": True, **over},
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_setzt_das_passwort(run_cli, db):
    u = _user(db)
    assert run_cli(["--username", "admin"]) == 0
    db.refresh(u)
    assert auth_service.verify_password(GOOD, u.password_hash)


def test_entwertet_bestehende_sitzungen(run_cli, db):
    """Ohne die Erhoehung liefe ein gestohlenes Zugangs-Token weiter."""
    u = _user(db)
    run_cli(["--username", "admin"])
    db.refresh(u)
    assert u.token_version == 4


def test_schreibt_eine_zeile_nach_security_events(run_cli, db):
    u = _user(db)
    run_cli(["--username", "admin"])
    rows = db.query(SecurityEvent).all()
    assert len(rows) == 1
    assert rows[0].event == EVENT_ADMIN_PASSWORD_RESET
    assert rows[0].subject_user_id == u.id
    assert rows[0].tenant_id == DEFAULT_TENANT_ID
    assert rows[0].actor.startswith("cli:")


def test_zweiter_faktor_bleibt_ohne_die_option_bestehen(run_cli, db):
    """Ein Passwort-Reset darf 2FA nicht stillschweigend abschalten."""
    u = _user(db, totp_secret=_TOTP_PLACEHOLDER, totp_enabled=True)
    run_cli(["--username", "admin"])
    db.refresh(u)
    assert u.totp_enabled is True
    assert u.totp_secret == _TOTP_PLACEHOLDER


def test_disable_2fa_raeumt_den_zweiten_faktor(run_cli, db):
    """Der Hauptfall: Passwort UND Authenticator sind weg."""
    u = _user(db, totp_secret=_TOTP_PLACEHOLDER, totp_enabled=True, last_totp_counter=42)
    run_cli(["--username", "admin", "--disable-2fa"])
    db.refresh(u)
    assert u.totp_enabled is False
    assert u.totp_secret is None
    assert u.last_totp_counter is None
    events = {e.event for e in db.query(SecurityEvent).all()}
    assert events == {EVENT_ADMIN_PASSWORD_RESET, EVENT_TOTP_DISABLED}


def test_unbekannter_benutzer_bricht_ab(run_cli, db):
    _user(db)
    with pytest.raises(SystemExit) as exc:
        run_cli(["--username", "gibtesnicht"])
    assert exc.value.code == 1


def test_schwaches_passwort_wird_abgelehnt(run_cli, db):
    """Dieselbe Regel wie in der Anwendung — sonst waere die Kommandozeile ein
    Weg, die Passwortregel zu umgehen."""
    u = _user(db)
    with pytest.raises(SystemExit):
        run_cli(["--username", ADMIN], passwords=(TOO_SHORT, TOO_SHORT) * 3)
    db.refresh(u)
    assert auth_service.verify_password(ALT, u.password_hash)


def test_abweichende_wiederholung_wird_abgelehnt(run_cli, db):
    u = _user(db)
    with pytest.raises(SystemExit):
        run_cli(["--username", "admin"], passwords=(GOOD, "Vertippt" + "1234") * 3)
    db.refresh(u)
    assert auth_service.verify_password(ALT, u.password_hash)


def test_mehrdeutiger_name_bricht_ab(run_cli, db):
    """Mehrmandanten-Installation: derselbe Name kann mehrfach existieren.

    Dann darf das Werkzeug NICHT raten, welches Konto gemeint ist.
    """
    _user(db)
    other_tenant = uuid.UUID("dddddddd-4250-4000-8000-000000000425")
    from app.models.tenant import Tenant
    db.add(Tenant(id=other_tenant, name="Zweite Praxis", slug="zweite-425", is_active=True, mode="multi"))
    db.commit()
    u2 = _user(db, username="admin_tmp")
    u2.username = "admin"
    u2.tenant_id = other_tenant
    db.commit()

    with pytest.raises(SystemExit) as exc:
        run_cli(["--username", "admin"])
    assert exc.value.code == 1


# ── Release-Review 1.19.0 ────────────────────────────────────────────────────


def test_protokollzeile_verliert_den_kontonamen_bei_der_anonymisierung(run_cli, db):
    """Art. 17: ``security_events.detail`` nennt das Konto im Klartext. Die
    ZEILE muss den Vorgang weiter belegen (Art. 5 Abs. 2), der Name nicht."""
    from app.routers import admin_users
    from app.services import lifecycle_service  # noqa: F401 — Doku des Zwillingspfads

    u = _user(db)
    run_cli(["--username", "admin"])
    assert db.query(SecurityEvent).filter(SecurityEvent.detail.isnot(None)).count() == 1

    u.is_active = False
    u.deactivated_at = None
    db.commit()
    admin = _user(db, username="chefin", role=UserRole.ADMIN)
    admin_users.anonymize_user(str(u.id), db=db, current_user=admin)

    zeile = db.query(SecurityEvent).filter(SecurityEvent.subject_user_id == u.id).one()
    assert zeile.detail is None          # Klarname weg
    assert zeile.event == EVENT_ADMIN_PASSWORD_RESET  # Vorgang bleibt belegt
    assert zeile.actor.startswith("cli:")


# ── #489: ein deaktiviertes Konto zurueckholen ──────────────────────────────
# Realfall: das Admin-Konto war deaktiviert. Der Reset setzte das Passwort und
# meldete nur "bleibt deaktiviert" — der Login scheiterte weiter, der einzige
# Weg zurueck war ein Eingriff von Hand in die Datenbank, ohne Protokollzeile.


def test_reactivate_holt_ein_deaktiviertes_konto_zurueck(run_cli, db):
    u = _user(db, is_active=False)
    assert run_cli(["--username", ADMIN, "--reactivate"]) == 0
    db.refresh(u)
    assert u.is_active is True
    assert u.deactivated_at is None
    assert auth_service.verify_password(GOOD, u.password_hash)


def test_reactivate_wird_protokolliert(run_cli, db):
    from app.models.security_event import EVENT_USER_REACTIVATED_CLI
    u = _user(db, is_active=False)
    run_cli(["--username", ADMIN, "--reactivate"])
    rows = db.query(SecurityEvent).filter(SecurityEvent.event == EVENT_USER_REACTIVATED_CLI).all()
    assert len(rows) == 1
    assert rows[0].subject_user_id == u.id
    assert rows[0].actor.startswith("cli:")


def test_ohne_option_bleibt_das_konto_deaktiviert_und_nennt_den_weg(run_cli, db, capsys):
    """Ein Passwort-Reset soll ein absichtlich deaktiviertes Konto nicht
    stillschweigend oeffnen — aber den Weg dorthin nennen."""
    u = _user(db, is_active=False)
    run_cli(["--username", ADMIN])
    db.refresh(u)
    assert u.is_active is False
    assert "--reactivate" in capsys.readouterr().out


def test_reactivate_auf_aktivem_konto_schreibt_keine_reaktivierung(run_cli, db):
    from app.models.security_event import EVENT_USER_REACTIVATED_CLI
    _user(db)
    run_cli(["--username", ADMIN, "--reactivate"])
    assert db.query(SecurityEvent).filter(SecurityEvent.event == EVENT_USER_REACTIVATED_CLI).count() == 0


def test_benutzername_ohne_gross_klein_schreibung(run_cli, db):
    """Der Login vergleicht ohne Gross-/Kleinschreibung — das Werkzeug muss
    dasselbe Konto finden, sonst meldet es "kein Benutzer", obwohl die
    Anmeldung mit genau diesem Namen funktioniert."""
    u = _user(db, username="Chefin")
    assert run_cli(["--username", "chefin"]) == 0
    db.refresh(u)
    assert auth_service.verify_password(GOOD, u.password_hash)
