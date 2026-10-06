"""#483: Datenbankfehler, die eine falsche Eingabe sind, als 422 beantworten.

Viele Endpunkte nehmen eine ID als freien ``str`` an (Pfad oder Query) und
geben sie ungeprueft in eine Abfrage auf eine UUID-Spalte. PostgreSQL lehnt
einen Nicht-UUID-String dann mit SQLSTATE ``22P02``
(``invalid_text_representation``) ab — ohne Handler ein HTTP 500 und ein Eintrag
in ``error_logs``, der auf der Admin-Fehlerseite wie ein Serverfehler aussieht.

Bewusst NUR ``22P02``: andere ``DataError``-Faelle (``22001`` String zu lang,
``22003`` Zahlenueberlauf, …) entstehen aus Werten, die der Server selbst
gebaut hat, und bleiben 500 — sie sind Fehler im Programm, nicht in der Eingabe.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

INVALID_TEXT_REPRESENTATION = "22P02"


async def invalid_text_representation_handler(request: Request, exc: DataError):
    if getattr(exc.orig, "pgcode", None) != INVALID_TEXT_REPRESENTATION:
        # Kein Eingabefehler: weiterreichen, damit capture_errors_middleware ihn
        # protokolliert und der Aufrufer wie bisher 500 bekommt.
        raise exc
    return JSONResponse(
        status_code=422,
        content={"detail": "Ungültige ID oder ungültiger Wert in der Anfrage."},
    )


def register_db_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DataError, invalid_text_representation_handler)
