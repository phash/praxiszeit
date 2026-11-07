"""Audit 2026-11-07 (S2-1, Art. 9 DSGVO): kein Statement-Text im PostgreSQL-Log.

psycopg2 bindet Parameter clientseitig — ein gescheitertes Statement steht mit
allen Werten (Namen, Notizen, Abwesenheitstyp) im Server-Log, solange
``log_min_error_statement`` auf dem Standard ``error`` steht; ``DETAIL``
(``log_error_verbosity`` ``default``) nennt zusaetzlich die Schluesselwerte.

Docker setzt beides im ``db``-Kommando, ``pg_init`` schreibt es in die
postgresql.conf neuer nativer Cluster. Bestandsinstallationen (nativ) behalten
ihre postgresql.conf — deshalb setzt jeder Migrationslauf (``alembic/env.py``,
laeuft bei jedem Start/Update als Superuser) die Werte zusaetzlich auf
Datenbank-Ebene (``ALTER DATABASE … SET``). Das wirkt fuer jede neue Sitzung
jeder Rolle in dieser Datenbank, auch ``praxiszeit_app``; keine Migration noetig.
"""
from __future__ import annotations

from sqlalchemy import text

# Werte fest im Code (kein Nutzereingang) — sie stehen deshalb direkt im SQL.
LOG_PRIVACY_SETTINGS: dict[str, str] = {
    "log_min_error_statement": "panic",
    "log_error_verbosity": "terse",
}


def apply_log_privacy_settings(connection) -> bool:
    """``ALTER DATABASE <aktuelle DB> SET`` fuer ``LOG_PRIVACY_SETTINGS``.

    Nur auf PostgreSQL und nur, wenn die Verbindung als Superuser laeuft (beide
    Parameter sind ``superuser``-Kontext; ein Nicht-Superuser bekaeme einen
    Fehler, der die Migrations-Transaktion abbraeche — deshalb vorher pruefen,
    nie ``try/except``). True, wenn gesetzt wurde."""
    if connection.dialect.name != "postgresql":
        return False
    is_super = connection.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if not is_super:
        return False
    db_name = connection.execute(text("SELECT current_database()")).scalar()
    ident = connection.dialect.identifier_preparer.quote(db_name)
    for name, value in LOG_PRIVACY_SETTINGS.items():
        connection.execute(text(f"ALTER DATABASE {ident} SET {name} = '{value}'"))
    return True
