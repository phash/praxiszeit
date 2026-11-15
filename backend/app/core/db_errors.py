"""#483: Datenbankfehler, die eine falsche Eingabe sind, als 422 beantworten.

Viele Endpunkte nehmen eine ID als freien ``str`` an (Pfad oder Query) und
geben sie ungeprueft in eine Abfrage auf eine UUID-Spalte. PostgreSQL lehnt
einen Nicht-UUID-String dann mit SQLSTATE ``22P02``
(``invalid_text_representation``) ab — ohne Handler ein HTTP 500 und ein Eintrag
in ``error_logs``, der auf der Admin-Fehlerseite wie ein Serverfehler aussieht.

Bewusst NUR ``22P02``: andere ``DataError``-Faelle (``22001`` String zu lang,
``22003`` Zahlenueberlauf, …) entstehen aus Werten, die der Server selbst
gebaut hat, und bleiben 500 — sie sind Fehler im Programm, nicht in der Eingabe.

#491 (API-1): Auch ein ``22P02`` kann aus dem Programm stammen — etwa ein
falscher Enum-Wert, den der Server selbst einsetzt. Der Handler kann das nicht
unterscheiden (woher ein Wert aus dem Request-Rumpf kam, ist hier nicht mehr
lesbar). Deshalb bleibt die Antwort 422, aber jeder Fall wird als WARNING in das
Anwendungsprotokoll geschrieben (Docker: ``docker compose logs backend``,
nativ: die Dienstprotokolle) — mit Methode, Route und der ersten Zeile der
Datenbankmeldung, damit ein Programmfehler auffindbar bleibt.

Bewusst NICHT nach ``error_logs``: der Logger ``app.core.db_errors`` haengt
nicht am ``DBErrorHandler`` (der lauscht nur auf ``uvicorn.error``/``fastapi``).
Sonst kaemen genau die Eintraege zurueck, die #483 von der Admin-Fehlerseite
genommen hat — jede vertippte oder von einem Scanner geratene ID.
"""
import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, DBAPIError, InterfaceError, OperationalError

from app.services.error_log_service import _scrub_path, _scrub_pii

INVALID_TEXT_REPRESENTATION = "22P02"

logger = logging.getLogger(__name__)

# Die erste Zeile der Datenbankmeldung nennt den abgelehnten Wert; mehr
# braucht die Diagnose nicht.
_MAX_DB_MESSAGE = 200

# Steuerzeichen (C0, DEL, C1) und die Unicode-Zeilentrenner. PostgreSQL zitiert
# die abgelehnte Eingabe ROH in der Hauptmeldung — ein ``%0A`` im Pfadparameter
# (von FastAPI zu ``\n`` dekodiert) schriebe sonst eine eigene, gefaelschte
# Zeile ins Container-/Dienstprotokoll (#491 API-1, Nachzug).
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def _db_message(exc: DataError) -> str:
    """Nur die Hauptmeldung (``invalid input syntax for type uuid: "xyz"``).

    Die Folgezeilen eines psycopg2-Fehlers (``LINE 1: …``) zitieren das SQL
    samt eingesetzter Werte — die gehoeren nicht ins Protokoll (DSGVO F-007,
    derselbe Grund, aus dem ``sqlalchemy.engine`` nicht mitprotokolliert wird).
    """
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    text = primary or (str(orig).strip().splitlines() or [""])[0]
    # Fuer BEIDE Zweige: ``message_primary`` ist einzeilig gemeint, enthaelt
    # aber den Eingabewert ungefiltert.
    text = _CONTROL_CHARS.sub(" ", text)
    return _scrub_pii(text)[:_MAX_DB_MESSAGE]


def _route_of(request) -> str:
    """Route-Vorlage (``/api/absences/{absence_id}``) statt Rohpfad — sonst
    der um UUIDs bereinigte Pfad."""
    if request is None:
        return "-"
    try:
        path = getattr(request.scope.get("route"), "path", None)
        # Der Rohpfad (Rueckfall ohne Route) ist dekodiert — gleiche Einebnung.
        return _CONTROL_CHARS.sub(" ", path or _scrub_path(request.url.path) or "-")
    except Exception:  # noqa: BLE001 — Protokollieren darf die Antwort nie kippen
        return "-"


async def invalid_text_representation_handler(request: Request, exc: DataError):
    if getattr(exc.orig, "pgcode", None) != INVALID_TEXT_REPRESENTATION:
        # Kein Eingabefehler: weiterreichen, damit capture_errors_middleware ihn
        # protokolliert und der Aufrufer wie bisher 500 bekommt.
        raise exc
    logger.warning(
        "22P02 als 422 beantwortet: %s %s — %s",
        getattr(request, "method", None) or "-",
        _route_of(request),
        _db_message(exc),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Ungültige ID oder ungültiger Wert in der Anfrage."},
    )


# ---------------------------------------------------------------------------
# Kundenfall 2026-11-15, Log-Audit Punkt 10 (RT-4): Verbindungsverlust → 503.
#
# Laeuft eine Anfrage, waehrend PostgreSQL neu startet (Wachhund, Update,
# Herunterfahren), kam ein nacktes HTTP 500 samt ``error_logs``-Zeile — ein
# Betriebszustand von wenigen Sekunden sah aus wie ein Programmfehler. Jetzt
# 503 mit ``Retry-After``; das Frontend wiederholt GET-Anfragen selbst.
#
# Bewusst eng: nur SQLSTATE-Klasse 08 (connection exception), 57P01/57P02/
# 57P03 (admin/crash shutdown, cannot connect now), eine von SQLAlchemy als
# ungueltig markierte Verbindung und die psycopg2-Texte, die ohne SQLSTATE
# kommen (der Server ist weg, bevor er einen Code schicken kann). Alles andere
# (Deadlock 40P01, zu viele Verbindungen 53300, IntegrityError …) bleibt 500.
#
# Eigener Logger, NICHT nach ``error_logs`` (gleicher Grund wie oben): waehrend
# die Datenbank weg ist, scheitert der Eintrag ohnehin, und danach stuenden auf
# der Admin-Fehlerseite lauter Zeilen fuer einen erwarteten Neustart.
# ---------------------------------------------------------------------------
DB_UNAVAILABLE_DETAIL = "Datenbank kurz nicht erreichbar – bitte in ein paar Sekunden erneut versuchen."
DB_UNAVAILABLE_RETRY_AFTER = "5"
_CONNECTION_LOSS_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})
_CONNECTION_LOSS_TEXTS = (
    "server closed the connection unexpectedly",
    "connection already closed",
    "could not connect to server",
    "ssl connection has been closed unexpectedly",
    "terminating connection due to administrator command",
)

# Review-Fund (Kundenfall 2026-11-15): Konfigurationsfehler beim Verbinden kommen
# bei psycopg2 ebenfalls ohne SQLSTATE und mit 'connection to server … failed'.
# Sie sind KEIN kurzer Ausfall (falsches App-Passwort nach Reparatur/Portwechsel,
# fehlende Datenbank, Verbindungsgrenze) und bleiben 500 mit Traceback und
# error_logs-Zeile — sonst stuende die Ursache in keinem Protokoll.
_PERMANENT_CONNECT_TEXTS = (
    "password authentication failed",
    "authentication failed",
    "does not exist",
    "too many clients",
    "remaining connection slots are reserved",
    "no pg_hba.conf entry",
)
_CAUSE_EXCERPT_MAX = 200

connection_logger = logging.getLogger("app.core.db_connection")


def _cause_excerpt(exc: BaseException) -> str:
    """Erste Zeile der Treibermeldung, ohne Steuerzeichen, gekuerzt.

    Verbindungsmeldungen nennen Host, Port und DB-Benutzer, keine Fachdaten."""
    text = str(getattr(exc, "orig", None) or exc or "").strip()
    first = text.splitlines()[0] if text else "-"
    return _CONTROL_CHARS.sub(" ", first)[:_CAUSE_EXCERPT_MAX]


def is_connection_loss(exc: BaseException) -> bool:
    """True, wenn ``exc`` ein Abbruch/Fehlen der Datenbankverbindung ist."""
    if not isinstance(exc, DBAPIError):
        return False
    if getattr(exc, "connection_invalidated", False):
        return True
    if not isinstance(exc, (OperationalError, InterfaceError)):
        return False
    code = getattr(exc.orig, "pgcode", None) or ""
    if code.startswith("08") or code in _CONNECTION_LOSS_SQLSTATES:
        return True
    text = str(exc.orig or "").lower()
    if any(t in text for t in _PERMANENT_CONNECT_TEXTS):
        return False
    if any(t in text for t in _CONNECTION_LOSS_TEXTS):
        return True
    # psycopg2 >= 2.9 / libpq 14+: 'connection to server at "…", port … failed: …'
    return "connection to server" in text and "failed" in text


async def db_unavailable_handler(request: Request, exc: DBAPIError):
    if not is_connection_loss(exc):
        # Kein Verbindungsverlust: wie bisher 500 + error_logs (capture_errors_middleware).
        raise exc
    code = getattr(exc.orig, "pgcode", None) or "-"
    connection_logger.warning(
        "Datenbank nicht erreichbar (SQLSTATE %s), 503 an %s %s: %s",
        code, getattr(request, "method", None) or "-", _route_of(request), _cause_excerpt(exc),
    )
    try:
        # capture_errors_middleware schreibt fuer diese 503 keine error_logs-Zeile.
        request.state.db_unavailable = True
    except Exception:  # noqa: BLE001 — Markierung darf die Antwort nie kippen
        pass
    return JSONResponse(
        status_code=503,
        content={"detail": DB_UNAVAILABLE_DETAIL},
        headers={"Retry-After": DB_UNAVAILABLE_RETRY_AFTER},
    )


def register_db_error_handlers(app: FastAPI) -> None:
    # DataError (Unterklasse von DBAPIError) behaelt seinen eigenen Handler —
    # Starlette waehlt den Handler der naechsten Klasse in der MRO.
    app.add_exception_handler(DataError, invalid_text_representation_handler)
    app.add_exception_handler(DBAPIError, db_unavailable_handler)
