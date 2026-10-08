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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

from app.services.error_log_service import _scrub_path, _scrub_pii

INVALID_TEXT_REPRESENTATION = "22P02"

logger = logging.getLogger(__name__)

# Die erste Zeile der Datenbankmeldung nennt den abgelehnten Wert; mehr
# braucht die Diagnose nicht.
_MAX_DB_MESSAGE = 200


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
    return _scrub_pii(text)[:_MAX_DB_MESSAGE]


def _route_of(request) -> str:
    """Route-Vorlage (``/api/absences/{absence_id}``) statt Rohpfad — sonst
    der um UUIDs bereinigte Pfad."""
    if request is None:
        return "-"
    try:
        path = getattr(request.scope.get("route"), "path", None)
        return path or _scrub_path(request.url.path) or "-"
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


def register_db_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DataError, invalid_text_representation_handler)
