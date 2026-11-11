"""Altzeilen ohne ``half_day`` (gebucht vor #205/1.9.0) eindeutig nachtragen.

Migration 052 hat ``absences.half_day`` bewusst NULLABLE angelegt: Zeilen von
davor behalten NULL und zählen weiter stundenbasiert (``hours ÷ Tagessoll``,
``calculation_service.get_vacation_account`` / ``absence_days``), die
Rückrechnung ``retarget_absence_hours`` überspringt sie (C1). Ändert eine
Arbeitszeit-Änderung später das Tagessoll ihres Datums, driften der Urlaubs-
verbrauch und der Resturlaub um ``h/neu − 1`` je Tag (Handbuch-Fund
2026-11-11: Vorschau „Urlaub verbraucht 3 → 3,1" bei 0 betroffenen
Abwesenheiten).

Diese Migration setzt ``half_day`` NUR dort, wo die Zuordnung eindeutig ist —
gemessen am Tagessoll des Datums laut Vertrags-Snapshot (dieselbe Regel wie
``calculation_service.get_schedule_for_date`` + ``get_daily_target_for_date``,
hier in reinem Python nachgebaut, weil Migrationen keine App-Services importieren):

* ``hours == Tagessoll``     → ``False`` (voller Tag)
* ``hours == Tagessoll / 2`` → ``True``  (Halbtag)
* sonst                      → bleibt NULL (Legacy-Formel wie bisher)

Toleranz 0,005 h (``hours`` ist ``Numeric(4,2)``; ein Halbtag bei ungeradem
Cent-Tagessoll, z. B. 7,25 / 2 = 3,625, steht als 3,62 oder 3,63 da).

Nicht angefasst (bleiben NULL): Überstundenausgleich (``OVERTIME`` trägt
explizite Stunden), Abwesenheiten mit Uhrzeit (``start_time``), Zeiträume
(``end_date`` ≠ ``date``), Wochenenden, Tage ohne Stundenzählung oder mit
Tagessoll 0 laut Snapshot sowie der 24./31.12. und die verkürzten Tage des
Mandanten (``reduced_days``) — dort kostet ein tagebasierter Tag 0,5
(``half_special_day_weight``), die Legacy-Formel zählt dagegen ``hours ÷
Tagessoll``; ein Nachtrag dort würde den heutigen Verbrauch verändern.

Ergebnis-neutral: für jede nachgetragene Zeile liefert die tagebasierte Zählung
heute denselben Wert wie die Legacy-Formel (1,0 bzw. 0,5). Ab jetzt bleibt er
bei späteren Arbeitszeit-Änderungen stehen, und ``retarget_absence_hours``
zieht die Stunden mit.

Mandantenübergreifend: auf PostgreSQL ``SET LOCAL app.is_superadmin`` (FORCE
RLS, Muster 073/075), sonst träfe die Migration als Nicht-Superuser-Eigentümerin
keine Zeile.

Downgrade: bewusst KEINE Rückänderung. Die Migration ergänzt nur Daten, das
Schema bleibt gleich; 052 ff. lesen ``True``/``False`` seit 1.9.0. Welche Zeilen
077 gesetzt hat, ist nicht markiert — ein Zurücksetzen auf NULL träfe auch
Zeilen, die eine Buchung seither gesetzt hat, und brächte die Drift zurück.
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

    updates = {True: [], False: []}
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
        if abs(hours - target) <= TOLERANCE:
            updates[False].append(a["id"])
        elif abs(hours - target / 2) <= TOLERANCE:
            updates[True].append(a["id"])

    stmt = sa.text("UPDATE absences SET half_day = :v WHERE id = :id AND half_day IS NULL")
    for value, ids in updates.items():
        if ids:
            conn.execute(stmt, [{"v": value, "id": i} for i in ids])

    full, half = len(updates[False]), len(updates[True])
    rest = len(candidates) - full - half
    print(f"077: {len(candidates)} Altzeilen ohne half_day: {full} ganztaegig, {half} halbtaegig, "
          f"{rest} unveraendert (nicht eindeutig)")


def downgrade() -> None:
    # Bewusst leer — siehe Modul-Docstring (reine Datenergänzung, nicht markiert).
    pass
