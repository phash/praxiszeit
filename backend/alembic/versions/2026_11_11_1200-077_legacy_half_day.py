"""Altzeilen ohne ``half_day`` (gebucht vor #205/1.9.0): volle Tage nachtragen.

Migration 052 hat ``absences.half_day`` bewusst NULLABLE angelegt: Zeilen von
davor behalten NULL und zählen im Urlaubskonto stundenbasiert (``hours ÷
Tagessoll``, ``calculation_service.get_vacation_account`` / ``absence_days``),
die Rückrechnung ``retarget_absence_hours`` überspringt sie (C1). Ändert eine
Arbeitszeit-Änderung später das Tagessoll ihres Datums, driften Urlaubs-
verbrauch und Resturlaub um ``h/neu − 1`` je Tag (Handbuch-Fund 2026-11-11:
Vorschau „Urlaub verbraucht 3 → 3,1" bei 0 betroffenen Abwesenheiten).

Diese Migration setzt NUR ``half_day = false``, und nur wo ``hours`` dem
Tagessoll des Datums laut Vertrags-Snapshot entspricht (Toleranz 0,005 h;
dieselbe Regel wie ``get_schedule_for_date`` + ``get_daily_target_for_date``,
hier in reinem Python nachgebaut, weil Migrationen keine App-Services
importieren).

Streng ergebnis-neutral (Ruling R24): Überall sonst gilt NULL wie ``false`` —
in der Soll-Minderung (``_soll_reducing_absence_half_map``: ``is_half = a.half_day
is True``), in der Deckung des festen Monats-Solls (``fixed_day_covered_hours``)
und im Anwesenheits-Soll; im Urlaubskonto ergibt die Legacy-Formel bei ``hours ==
Tagessoll`` genau 1,0. Ab jetzt bleibt der Wert bei späteren Arbeitszeit-
Änderungen stehen, und die Rückrechnung zieht die Stunden mit.

**Halbtage werden NICHT nachgetragen** (bleiben NULL): ``half_day = true``
halbiert das Soll des Tages, statt es ganz abzuziehen — Soll, Saldo, Journal,
§16-Exporte und abgeschlossene Jahre änderten sich rückwirkend. 1.8.0
(#167/#170) buchte halbe Urlaubstage als ``hours = 0,5 × Tagessoll`` ohne
Kennzeichen, und ein voller Tag unter einem später verdoppelten Tagessoll sähe
genauso aus — die Zuordnung ist nicht eindeutig.

Ebenfalls NULL bleiben: Überstundenausgleich (``OVERTIME`` trägt explizite
Stunden), Abwesenheiten mit Uhrzeit (``start_time``), Zeiträume (``end_date`` ≠
``date``), Wochenenden, Tage ohne Stundenzählung oder mit Tagessoll 0 laut
Snapshot sowie der 24./31.12. und die verkürzten Tage des jeweiligen Mandanten
(``reduced_days``) — dort kostet ein tagebasierter Tag 0,5
(``half_special_day_weight``), die Legacy-Formel zählt ``hours ÷ Tagessoll``.

Mandantenübergreifend: auf PostgreSQL ``SET LOCAL app.is_superadmin`` (FORCE
RLS, Muster 073/075), sonst träfe die Migration als Nicht-Superuser-Eigentümerin
keine Zeile.

Downgrade: bewusst KEINE Rückänderung. Die Migration ergänzt nur Daten, das
Schema bleibt gleich; 052 ff. lesen ``false`` seit 1.9.0. Welche Zeilen 077
gesetzt hat, ist nicht markiert — ein Zurücksetzen auf NULL träfe auch Zeilen,
die eine Buchung seither gesetzt hat, und brächte die Drift zurück.
"""
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "077_legacy_half_day"
down_revision = "076_audit_chain"
branch_labels = None
depends_on = None

TOLERANCE = Decimal("0.005")
CENT = Decimal("0.01")
DAY_COLUMNS = ("hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday", "hours_friday")
SPECIAL_DAYS = {(12, 24), (12, 31)}


def _dec(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _daily_target(snap: dict, weekday: int) -> Decimal:
    """``get_daily_target_for_date`` für einen Werktag (0–4) mit Stundenzählung."""
    if snap["use_daily_schedule"]:
        return _dec(snap[DAY_COLUMNS[weekday]]).quantize(CENT)
    work_days = _dec(snap["work_days_per_week"])
    if work_days == 0:
        return Decimal("0")
    return (_dec(snap["weekly_hours"]) / work_days).quantize(CENT)


def _snapshot(user: dict, changes: list, d) -> dict:
    """``get_schedule_for_date``: jüngste Verlaufszeile ≤ Datum; davor bzw. ohne
    Zeile Stunden/Modus/Tage von der User-Zeile, ``track_hours`` von der ERSTEN
    Verlaufszeile (ohne Zeilen von der User-Zeile)."""
    latest = None
    for change in changes:  # nach effective_from aufsteigend
        if change["effective_from"] <= d:
            latest = change
        else:
            break
    if latest is not None:
        snap = dict(latest)
        if snap["work_days_per_week"] is None:
            snap["work_days_per_week"] = user["work_days_per_week"]
        return snap
    snap = dict(user)
    if changes:
        snap["track_hours"] = changes[0]["track_hours"]
    return snap


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("SET LOCAL app.is_superadmin = 'true'"))

    candidates = conn.execute(sa.text(
        "SELECT id, tenant_id, user_id, date, end_date, hours FROM absences "
        "WHERE half_day IS NULL AND start_time IS NULL AND CAST(type AS VARCHAR) <> 'OVERTIME'"
    )).mappings().all()
    if not candidates:
        print("077: 0 Altzeilen ohne half_day")
        return

    user_cols = ("id", "weekly_hours", "use_daily_schedule", "work_days_per_week", "track_hours") + DAY_COLUMNS
    users = {str(row["id"]): dict(row) for row in conn.execute(sa.text(
        f"SELECT {', '.join(user_cols)} FROM users"
    )).mappings().all()}
    change_cols = ("user_id", "effective_from", "weekly_hours", "use_daily_schedule",
                   "work_days_per_week", "track_hours") + DAY_COLUMNS
    changes: dict = {}
    for row in conn.execute(sa.text(
        f"SELECT {', '.join(change_cols)} FROM working_hours_changes ORDER BY user_id, effective_from"
    )).mappings().all():
        changes.setdefault(str(row["user_id"]), []).append(dict(row))
    reduced = {(str(t), d) for t, d in conn.execute(sa.text("SELECT tenant_id, date FROM reduced_days")).all()}

    full_days = []
    for a in candidates:
        d = a["date"]
        if a["end_date"] is not None and a["end_date"] != d:
            continue
        if d.weekday() >= 5 or (d.month, d.day) in SPECIAL_DAYS or (str(a["tenant_id"]), d) in reduced:
            continue
        user = users.get(str(a["user_id"]))
        if user is None:
            continue
        snap = _snapshot(user, changes.get(str(a["user_id"]), []), d)
        if not snap["track_hours"]:
            continue
        target = _daily_target(snap, d.weekday())
        if target <= 0:
            continue
        hours = _dec(a["hours"])
        # R24: nur der volle Tag — ein Halbtag (hours == Tagessoll/2) bleibt NULL.
        if abs(hours - target) <= TOLERANCE:
            full_days.append(a["id"])

    if full_days:
        conn.execute(
            sa.text("UPDATE absences SET half_day = false WHERE id = :id AND half_day IS NULL"),
            [{"id": i} for i in full_days],
        )

    full = len(full_days)
    print(f"077: {len(candidates)} Altzeilen ohne half_day: {full} als ganztaegig gesetzt, "
          f"{len(candidates) - full} unveraendert")


def downgrade() -> None:
    # Bewusst leer — siehe Modul-Docstring (reine Datenergänzung, nicht markiert).
    pass
