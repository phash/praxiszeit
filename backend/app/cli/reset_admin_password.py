"""#425: Admin-Passwort lokal auf der Maschine zuruecksetzen.

Verliert die Betreiberin einer **nativen** Installation ihr Admin-Passwort, gab
es bisher keinen unterstuetzten Weg zurueck: ``praxiszeit-server.py`` kannte
kein passendes Kommando, und der in ``config/praxiszeit.conf`` hinterlegte
``[admin] password`` ist nur der Startwert der Erstinstallation und nach dem
ersten Wechsel schlicht falsch.

Der Zugang zur Datenbank ist entgegen der urspruenglichen Annahme NICHT
versperrt (``config/.db-credentials`` haelt beide Rollenpasswoerter, siehe
``praxiszeit-server.py``) — es fehlte ein unterstuetzter, protokollierter Weg.
Dieses Modul ist er.

Aufruf ueber den Prozessmanager::

    # nativ (der volle Pfad ist noetig: nicht im PATH, und die App-Abhaengigkeiten
    # liegen nur im mitgelieferten Interpreter):
    sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 \\
         /opt/praxiszeit/praxiszeit-server.py reset-admin-password [--username admin] [--disable-2fa] [--reactivate]

    # unter Docker steckt dasselbe Werkzeug im Backend-Abbild:
    docker compose exec backend python -m app.cli.reset_admin_password [--disable-2fa] [--reactivate]

Eigenschaften:

* Das Passwort wird **interaktiv** abgefragt (zweimal), nie als Argument — ein
  Argument stuende in der Shell-History und in der Prozessliste.
* ``token_version`` wird erhoeht: alle bestehenden Sitzungen des Kontos werden
  ungueltig.
* ``--disable-2fa`` raeumt zusaetzlich das TOTP-Geheimnis. Ohne das loest der
  Reset den Hauptfall nicht: ist auch der Authenticator verloren, verlangt der
  Login nach dem neuen Passwort weiterhin einen Code. Bewusst eine eigene,
  ausdrueckliche Option — ein Passwort-Reset soll den zweiten Faktor nicht
  stillschweigend abschalten.
* ``--reactivate`` (#489) holt ein deaktiviertes Konto zurueck. Realfall: das
  Admin-Konto war deaktiviert, der Reset setzte das Passwort, der Login
  scheiterte trotzdem — der einzige Weg zurueck war ein Eingriff von Hand in
  die Datenbank, ohne Protokollzeile. Wie ``--disable-2fa`` bewusst eine
  ausdrueckliche Option: ein Passwort-Reset soll ein absichtlich deaktiviertes
  Konto nicht stillschweigend wieder oeffnen. Das Sitzplatz-Limit (SaaS) prueft
  das Werkzeug bewusst NICHT — es ist der Notausgang, kein Verwaltungsweg.
* Jeder Vorgang schreibt eine Zeile nach ``security_events`` (Art. 5 Abs. 2
  DSGVO). Nicht nach ``time_entry_audit_logs``: das ist die §16-Domaene und
  ueber ``row_hash`` (#121) manipulationsgeschuetzt.
"""
from __future__ import annotations

import argparse
import getpass
import os
import socket
import sys


def _fail(msg: str) -> None:
    print(f"FEHLER: {msg}", file=sys.stderr)
    sys.exit(1)


def _actor() -> str:
    """Wer hat gehandelt? Beim Kommandozeilen-Weg gibt es kein Anwendungskonto —
    festgehalten wird das Betriebssystem-Konto und der Rechner."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 — ohne Login-Namen (Dienstkontext) trotzdem protokollieren
        user = f"uid={getattr(os, 'geteuid', lambda: '?')()}"
    try:
        host = socket.gethostname()
    except Exception:  # noqa: BLE001
        host = "?"
    return f"cli:{user}@{host}"[:200]


def _prompt_password() -> str:
    """Zweimal abfragen und gegen dieselbe Regel pruefen wie die Anwendung."""
    from app.schemas.user import _validate_password_complexity

    for _ in range(3):
        first = getpass.getpass("Neues Passwort: ")
        second = getpass.getpass("Wiederholen:    ")
        if first != second:
            print("Die Eingaben stimmen nicht ueberein.", file=sys.stderr)
            continue
        try:
            return _validate_password_complexity(first)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
    _fail("Zu viele Fehlversuche.")
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reset-admin-password",
        description="Setzt das Passwort eines Kontos direkt in der Datenbank neu.",
    )
    parser.add_argument(
        "--username", default=os.environ.get("ADMIN_USERNAME") or "admin",
        help="Benutzername (Vorgabe: admin bzw. ADMIN_USERNAME aus der Konfiguration)",
    )
    parser.add_argument(
        "--disable-2fa", action="store_true",
        help="Zusaetzlich die Zwei-Faktor-Anmeldung des Kontos abschalten "
             "(noetig, wenn auch der Authenticator verloren ist)",
    )
    parser.add_argument(
        "--reactivate", action="store_true",
        help="Ein deaktiviertes Konto zusaetzlich wieder aktivieren "
             "(noetig, wenn das Konto in der Benutzerverwaltung deaktiviert wurde)",
    )
    args = parser.parse_args(argv)

    # Erst hier importieren: die Anwendung liest beim Import ihre Konfiguration,
    # und ein Fehler daraus soll die --help-Ausgabe nicht verhindern.
    from app.database import SessionLocal, set_superadmin_context
    from app.models import User
    from sqlalchemy import func

    from app.models.security_event import (
        EVENT_ADMIN_PASSWORD_RESET,
        EVENT_TOTP_DISABLED,
        EVENT_USER_REACTIVATED_CLI,
        SecurityEvent,
    )
    from app.services import auth_service

    db = SessionLocal()
    try:
        # Kein Mandantenkontext vorhanden — das Kommando laeuft ohne Anmeldung.
        # Im On-Prem-Betrieb gibt es genau einen Mandanten; der Superadmin-
        # Kontext ist hier der einzige Weg, die Zeile ueberhaupt zu sehen.
        set_superadmin_context(db)

        # #489: ohne Gross-/Kleinschreibung — genau wie der Login. Sonst meldet das
        # Werkzeug "kein Benutzer", obwohl die Anmeldung mit diesem Namen geht.
        matches = db.query(User).filter(func.lower(User.username) == args.username.lower()).all()
        if not matches:
            _fail(f"Kein Benutzer mit dem Namen {args.username!r} gefunden.")
        if len(matches) > 1:
            # Mehrmandanten-Installation: der Name ist dort nicht eindeutig.
            _fail(
                f"Der Name {args.username!r} existiert in mehreren Mandanten "
                f"({len(matches)}x) — hier nicht eindeutig aufloesbar."
            )
        user = matches[0]

        print(f"Konto: {user.username} ({user.first_name} {user.last_name}, Rolle {user.role})")
        if not user.is_active and not args.reactivate:
            print(
                "Hinweis: Das Konto ist derzeit deaktiviert und bleibt es auch — "
                "eine Anmeldung ist damit weiterhin nicht moeglich. Zum Reaktivieren "
                "den Befehl mit --reactivate wiederholen."
            )

        password = _prompt_password()

        user.password_hash = auth_service.hash_password(password)
        # Alle bestehenden Zugangs-Token entwerten.
        user.token_version = (user.token_version or 0) + 1

        actor = _actor()
        db.add(SecurityEvent(
            tenant_id=user.tenant_id,
            event=EVENT_ADMIN_PASSWORD_RESET,
            subject_user_id=user.id,
            actor=actor,
            detail=f"Passwort ueber die Kommandozeile neu gesetzt (Konto {user.username})",
        ))

        reactivated = False
        if args.reactivate and not user.is_active:
            user.is_active = True
            user.deactivated_at = None
            reactivated = True
            db.add(SecurityEvent(
                tenant_id=user.tenant_id,
                event=EVENT_USER_REACTIVATED_CLI,
                subject_user_id=user.id,
                actor=actor,
                detail=f"Konto ueber die Kommandozeile reaktiviert (Konto {user.username})",
            ))

        if args.disable_2fa:
            had_2fa = bool(user.totp_enabled or user.totp_secret)
            user.totp_secret = None
            user.totp_enabled = False
            user.last_totp_counter = None
            db.add(SecurityEvent(
                tenant_id=user.tenant_id,
                event=EVENT_TOTP_DISABLED,
                subject_user_id=user.id,
                actor=actor,
                detail=(
                    f"Zwei-Faktor-Anmeldung ueber die Kommandozeile abgeschaltet "
                    f"(Konto {user.username}, war {'aktiv' if had_2fa else 'nicht aktiv'})"
                ),
            ))

        db.commit()
    finally:
        db.close()

    print("Passwort gesetzt. Alle bestehenden Sitzungen dieses Kontos sind ungueltig.")
    if reactivated:
        print("Konto reaktiviert — die Anmeldung ist wieder moeglich.")
    elif args.reactivate:
        print("Das Konto war bereits aktiv.")
    if args.disable_2fa:
        print("Zwei-Faktor-Anmeldung abgeschaltet — im Profil neu einrichten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
