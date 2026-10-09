"""Arbeitszeit-Bloecke (Spec 2026-10-08, Abschnitt 5): Fenster -> Bloecke.

#201 hatte je Wochentag EIN Soll-Fenster direkt auf der User-Zeile
(``users.scheduled_*``): nicht historisiert, einteilig, ohne Soll-Wirkung. Ab
hier leben die Bloecke im datierten Vertrags-Snapshot
(``working_hours_changes.blocks``, Rueckfall ``users.work_blocks``).

Upgrade (Spec 5.2):

* neue Spalten (Bloecke, ``uncredited_minutes``, ``credit_override``,
  ``auto_closed``, ``clamp_grace_minutes``, Antragsfelder);
* Backfill IN PYTHON: jedes Fenster wird ein Einblock-Tag mit
  ``pause_minutes`` NULL ("Altfenster": kappt, treibt kein Soll), auf
  ``users.work_blocks`` UND auf JEDE Verlaufszeile der Person - die Fenster
  wirkten live, also bleibt das Verhalten byte-identisch (Prinzip wie 067);
* Bestandsfallen (halboffen, Beginn >= Ende, Sekunden) brechen NICHT ab,
  sondern stehen namentlich in der Diagnose (Spec 5.3/5.4) - ein Update eines
  Kundensystems darf nicht haengen;
* ``auto_closed`` fuer Eintraege, die der Auto-Close auf 23:59 geschlossen hat
  (Ende ODER Rohende 23:59, siehe ``backfill_auto_closed``);
* die zehn ``scheduled_*``-Spalten werden geloescht (E23, kein Expand/Contract).

KEINE Neukappung: ``uncredited_minutes`` bleibt 0, ``clamp_grace_minutes``
NULL ("unbekannt -> aktueller Puffer"), ``hours_*``/``weekly_hours`` unberuehrt
- ``net_hours``, Soll und Saldo bleiben byte-identisch (E22).

Downgrade (Spec 5.5, entschieden 2026-10-08): das 072-Fenster entsteht aus der
HUELLE der Bloecke (Beginn des ersten bis Ende des letzten Blocks), nicht aus
dem ersten Block. Verlustbehaftet; die Diagnose nennt die Betroffenen.

Die reinen Helfer (``build_week``, ``window_from_week``, ``upgrade_report``,
``downgrade_report``) sind ohne Datenbank testbar, ``backfill_auto_closed``
gegen die SQLite-Test-DB (``tests/test_073_work_blocks_migration.py``); der
Lauf gegen echtes PostgreSQL steht in ``tests/test_073_migration_pg.py``.
"""
import json
import sys
from datetime import time

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073_work_blocks"
down_revision = "072_cr_sunday_reason"
branch_labels = None
depends_on = None

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
LABELS = ("Mo", "Di", "Mi", "Do", "Fr")
WINDOW_COLUMNS = tuple(
    f"scheduled_{kind}_{day}" for day in DAYS for kind in ("start", "end")
)
PLACEHOLDER_START = "00:00"
PLACEHOLDER_END = "23:59"


def _hhmm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _hms(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"


def _parse_hhmm(value: str) -> time:
    return time(int(value[:2]), int(value[3:5]))


def _emit(text: str) -> None:
    """Diagnose ausgeben, ohne an der Kodierung der Ausgabe zu scheitern.

    Die Texte enthalten "→" (U+2192), das cp1252 nicht kennt. Nativ unter
    Windows ist stdout dieser Migration eine Pipe in der ANSI-Codepage, sobald
    PYTHONUTF8 nicht gesetzt ist (etwa beim Konsolenstart des Prozessmanagers);
    ein nacktes ``print`` wuerfe dann UnicodeEncodeError, alembic rollte die
    Migration zurueck und der Dienst startete nicht - genau das, was E21
    ausschliesst. Rueckfall: "→" als "->", alles Uebrige, was die Kodierung
    nicht kennt (etwa ein Benutzername mit "ł"), als "?". Mit UTF-8 bleibt der
    Wortlaut der Spec unveraendert."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.replace("→", "->").encode(enc, "replace").decode(enc))


def tenant_label(tenant_id) -> str:
    """Kurzform wie in der Spec (``0000…0001``)."""
    text = str(tenant_id)
    return f"{text[:4]}…{text[-4:]}" if len(text) > 8 else text


def build_week(window) -> tuple:
    """072-Fenster (Mapping mit ``scheduled_start_monday`` …) -> kanonische
    Altzeilen-Woche (Spec 3.1/5.3).

    Rueckgabe ``(woche, hinweise)``. ``woche`` ist ``None``, wenn kein Tag
    einen Block bekommt (Spec 3.3: fuenf leere Tage == NULL, geschrieben wird
    dann nichts)."""
    week, notes = [], []
    for day, label in zip(DAYS, LABELS):
        start = window.get(f"scheduled_start_{day}")
        end = window.get(f"scheduled_end_{day}")
        if start is None and end is None:
            week.append({"blocks": [], "pause_minutes": None})
            continue
        for value in (start, end):
            if value is not None and (value.second or value.microsecond):
                notes.append(
                    f"Sekunden abgeschnitten: {label} {_hms(value)} → {_hhmm(value)}"
                )
        s = _hhmm(start) if start is not None else None
        e = _hhmm(end) if end is not None else None
        if e is None:
            notes.append(
                f"halboffen: {label} ab {s} → Ende {PLACEHOLDER_END} (Kappung unverändert)"
            )
            e = PLACEHOLDER_END
        elif s is None:
            notes.append(
                f"halboffen: {label} bis {e} → Beginn {PLACEHOLDER_START} (Kappung unverändert)"
            )
            s = PLACEHOLDER_START
        if s >= e:  # "HH:MM" ist nullgepolstert -> Stringvergleich == Zeitvergleich
            notes.append(
                f"nicht übernommen: {label} {s}–{e} (Beginn nicht vor Ende); "
                "Einträge an diesem Wochentag werden künftig nicht mehr gekappt"
            )
            week.append({"blocks": [], "pause_minutes": None})
            continue
        week.append({"blocks": [{"start": s, "end": e}], "pause_minutes": None})
    if not any(day["blocks"] for day in week):
        return None, notes
    return week, notes


def window_from_week(week) -> tuple:
    """Downgrade (Spec 5.5): 072-Fenster je Tag aus der HUELLE der Bloecke.

    Rueckgabe ``(spalten, mehrblock_hinweise)``. Platzhalter ``00:00`` als
    Beginn und ``23:59`` als Ende werden wieder NULL (Round-Trip der
    halboffenen Fenster)."""
    values = {column: None for column in WINDOW_COLUMNS}
    notes = []
    for idx, (day, label) in enumerate(zip(DAYS, LABELS)):
        if not week or idx >= len(week):
            continue
        blocks = sorted((week[idx] or {}).get("blocks") or [], key=lambda b: b["start"])
        if not blocks:
            continue
        start = blocks[0]["start"]
        end = max(block["end"] for block in blocks)
        if len(blocks) > 1:
            spans = " + ".join(f"{b['start']}–{b['end']}" for b in blocks)
            gaps = ", ".join(f"{a['end']}–{b['start']}" for a, b in zip(blocks, blocks[1:]))
            notes.append(
                f"{label} {spans} → Fenster {start}–{end} "
                f"(wieder angerechnete Lücken: {gaps})"
            )
        values[f"scheduled_start_{day}"] = None if start == PLACEHOLDER_START else _parse_hhmm(start)
        values[f"scheduled_end_{day}"] = None if end == PLACEHOLDER_END else _parse_hhmm(end)
    return values, notes


def upgrade_report(accounts: int, history_rows: int, notes) -> str:
    """Diagnose-Ausgabe (Spec 5.4) - ausgegeben ueber ``_emit`` (``print`` wie
    067, mit Rueckfall fuer Nicht-UTF-8-Ausgaben), landet im Update-Log (nativ)
    bzw. im Container-Log (Docker)."""
    lines = [
        "",
        "*** HINWEIS (Migration 073) ***",
        "Arbeitszeit-Fenster wurden in Arbeitszeit-Blöcke übernommen: "
        f"{accounts} Konten, {history_rows} Verlaufszeilen.",
    ]
    if notes:
        lines.append("Besonderheiten (bitte im Dialog „Arbeitszeit anpassen…“ prüfen):")
        lines.extend(f"  - {note}" for note in notes)
    lines.append("*** ENDE HINWEIS ***")
    return "\n".join(lines) + "\n"


def _hours_de(minutes: int) -> str:
    return f"{minutes / 60:.2f}".replace(".", ",")


def downgrade_report(multi_block, uncredited, overrides, open_requests: int) -> str:
    """Diagnose des Downgrades (Spec 5.5 Schritt 3).

    ``multi_block``: fertige Zeilen ``"<wer>: <Tag> …"``; ``uncredited``:
    ``(wer, anzahl, minuten)``; ``overrides``: ``(wer, anzahl)``."""
    lines = [
        "",
        "*** HINWEIS (Migration 073, Downgrade) ***",
        "Arbeitszeit-Blöcke wurden auf ein Fenster je Wochentag zurückgeführt "
        "(Hülle: Beginn des ersten bis Ende des letzten Blocks).",
    ]
    if multi_block:
        lines.append(
            "Mehrere Blöcke an einem Tag – das Fenster kappt nur noch an der Hülle, "
            "Zeit zwischen den Blöcken wird bei künftigen Schreibvorgängen wieder angerechnet:"
        )
        lines.extend(f"  - {note}" for note in multi_block)
    if uncredited:
        lines.append(
            "Einträge mit nicht angerechneter Zeit – ihre angerechnete Zeit steigt "
            "mit dem Downgrade sofort um diese Summe:"
        )
        lines.extend(
            f"  - {who}: {count} Einträge, zusammen {_hours_de(minutes)} h"
            for who, count, minutes in uncredited
        )
    if overrides:
        lines.append("Anerkannte Einträge (das Kennzeichen entfällt):")
        lines.extend(f"  - {who}: {count} Einträge" for who, count in overrides)
    if open_requests:
        lines.append(
            f"{open_requests} offene Anträge „Anrechnung beantragen“ werden nach dem "
            "Downgrade wie gewöhnliche Änderungsanträge genehmigt, also wieder gekappt."
        )
    lines.append("*** ENDE HINWEIS ***")
    return "\n".join(lines) + "\n"


def _json_type():
    # JSONB auf PostgreSQL, JSON sonst - wie das Modell (Spec E8). Das
    # ``none_as_null`` des Modells betrifft nur die Python-Seite (None ->
    # SQL-NULL beim Schreiben ueber das ORM), nicht die DDL.
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _superadmin(conn) -> bool:
    """FORCE RLS (Spec 5.2 Schritt 2): ist die Migrationsrolle Eigentuemerin,
    aber kein Superuser, traefe der Backfill sonst still 0 Zeilen."""
    if conn.dialect.name != "postgresql":
        return False
    conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))
    return True


def backfill_auto_closed(conn) -> int:
    """P18: vor 073 kappte der Auto-Close nie - ein Eintrag mit Ende 23:59 UND
    Protokollzeile auto_close ist der Auto-Close. Reines Kennzeichen, net_hours
    unveraendert. Rueckgabe: Anzahl gekennzeichneter Eintraege.

    ``raw_end_time = 23:59`` gehoert dazu: unter 072 kappte ein spaeteres
    Speichern des ganzen Formulars (etwa nur die Pause ergaenzt, Ende 23:59
    unveraendert - ``unclamp_input`` reicht es mangels Rohwert durch) die
    synthetischen 23:59 auf das Fensterende und hielt 23:59 als ``raw_end_time``
    fest. Das ist genau die Form, die der neue Auto-Close mit
    ``auto_closed = true`` schreibt; ohne Kennzeichen zaehlte P19 die Strecke bis
    23:59 als "nicht angerechnet", und Anerkennen rechnete bis 23:59 an.

    Kein Fehltreffer: ein echt korrigiertes Ende laesst ``raw_end_time`` NULL
    (im Fenster) oder traegt den echten Wert (ausserhalb), nie 23:59. Offen
    bleibt nur ein echtes Ende um genau 23:59 - dieselbe Mehrdeutigkeit, die die
    Spec fuer ``end_time = 23:59`` schon hinnimmt."""
    return conn.execute(sa.text(
        "UPDATE time_entries SET auto_closed = true "
        "WHERE (end_time = :t OR raw_end_time = :t) AND EXISTS ("
        "  SELECT 1 FROM time_entry_audit_logs a "
        "  WHERE a.time_entry_id = time_entries.id AND a.source = 'auto_close')"
    ).bindparams(sa.bindparam("t", time(23, 59), type_=sa.Time()))).rowcount


def upgrade():
    op.add_column("users", sa.Column("work_blocks", _json_type(), nullable=True))
    op.add_column("working_hours_changes", sa.Column("blocks", _json_type(), nullable=True))
    op.add_column("time_entries", sa.Column(
        "uncredited_minutes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("time_entries", sa.Column(
        "credit_override", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("time_entries", sa.Column(
        "auto_closed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("time_entries", sa.Column("clamp_grace_minutes", sa.Integer(), nullable=True))
    op.add_column("change_requests", sa.Column(
        "request_credit_override", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("change_requests", sa.Column(
        "original_uncredited_minutes", sa.Integer(), nullable=True))

    conn = op.get_bind()
    pg = _superadmin(conn)
    as_json = "CAST(:j AS JSONB)" if pg else ":j"

    columns = ", ".join(WINDOW_COLUMNS)
    any_window = " OR ".join(f"{c} IS NOT NULL" for c in WINDOW_COLUMNS)
    rows = conn.execute(sa.text(
        f"SELECT id, tenant_id, username, {columns} FROM users "
        f"WHERE {any_window} ORDER BY tenant_id, username"
    )).mappings().all()

    notes, expected, accounts, history_rows = [], 0, 0, 0
    for row in rows:
        week, day_notes = build_week(row)
        who = f"{row['username']} (Mandant {tenant_label(row['tenant_id'])})"
        notes.extend(f"{who}: {note}" for note in day_notes)
        if week is None:
            continue
        expected += 1
        payload = json.dumps(week)
        accounts += conn.execute(
            sa.text(f"UPDATE users SET work_blocks = {as_json} WHERE id = :id"),
            {"j": payload, "id": row["id"]},
        ).rowcount
        history_rows += conn.execute(
            sa.text(f"UPDATE working_hours_changes SET blocks = {as_json} WHERE user_id = :id"),
            {"j": payload, "id": row["id"]},
        ).rowcount
    if accounts != expected:
        notes.append(
            f"Abweichung: {expected} Konten erwartet, {accounts} aktualisiert (RLS?)"
        )

    backfill_auto_closed(conn)

    _emit(upgrade_report(accounts, history_rows, notes))

    for column in WINDOW_COLUMNS:
        op.drop_column("users", column)


def downgrade():
    for column in WINDOW_COLUMNS:
        op.add_column("users", sa.Column(column, sa.Time(), nullable=True))

    conn = op.get_bind()
    _superadmin(conn)

    multi_block = []
    rows = conn.execute(sa.text(
        "SELECT id, tenant_id, username, work_blocks FROM users "
        "WHERE work_blocks IS NOT NULL ORDER BY tenant_id, username"
    )).mappings().all()
    assignments = ", ".join(f"{c} = :{c}" for c in WINDOW_COLUMNS)
    for row in rows:
        week = row["work_blocks"]
        if isinstance(week, str):  # SQLite liefert JSON als Text
            week = json.loads(week)
        values, notes = window_from_week(week)
        who = f"{row['username']} (Mandant {tenant_label(row['tenant_id'])})"
        multi_block.extend(f"{who}: {note}" for note in notes)
        conn.execute(
            sa.text(f"UPDATE users SET {assignments} WHERE id = :id"),
            {**values, "id": row["id"]},
        )

    uncredited = [
        (f"{r['username']} (Mandant {tenant_label(r['tenant_id'])})", int(r["n"]), int(r["m"]))
        for r in conn.execute(sa.text(
            "SELECT u.username, u.tenant_id, COUNT(*) AS n, SUM(e.uncredited_minutes) AS m "
            "FROM time_entries e JOIN users u ON u.id = e.user_id "
            "WHERE e.uncredited_minutes > 0 "
            "GROUP BY u.username, u.tenant_id ORDER BY u.tenant_id, u.username"
        )).mappings().all()
    ]
    overrides = [
        (f"{r['username']} (Mandant {tenant_label(r['tenant_id'])})", int(r["n"]))
        for r in conn.execute(sa.text(
            "SELECT u.username, u.tenant_id, COUNT(*) AS n "
            "FROM time_entries e JOIN users u ON u.id = e.user_id "
            "WHERE e.credit_override "
            "GROUP BY u.username, u.tenant_id ORDER BY u.tenant_id, u.username"
        )).mappings().all()
    ]
    open_requests = conn.execute(sa.text(
        "SELECT COUNT(*) FROM change_requests "
        "WHERE request_credit_override AND status = 'pending'"
    )).scalar() or 0

    _emit(downgrade_report(multi_block, uncredited, overrides, int(open_requests)))

    op.drop_column("change_requests", "original_uncredited_minutes")
    op.drop_column("change_requests", "request_credit_override")
    op.drop_column("time_entries", "clamp_grace_minutes")
    op.drop_column("time_entries", "auto_closed")
    op.drop_column("time_entries", "credit_override")
    op.drop_column("time_entries", "uncredited_minutes")
    op.drop_column("working_hours_changes", "blocks")
    op.drop_column("users", "work_blocks")
