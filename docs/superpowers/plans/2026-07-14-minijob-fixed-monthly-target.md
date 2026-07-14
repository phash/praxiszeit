# Minijob-Modus „feste Monatsarbeitszeit" (#377 Baustein 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein opt-in-Modus, in dem für MiLoG-Minijobber das Monats-Soll = `agreed_monthly_hours` (fix, pro-rata bei Eintritt/Austritt) gilt statt der schwankenden Per-Tag-Summe; bezahlte Fehltage schreiben geplante Stunden dem Ist gut, unbezahlte mindern das feste Soll.

**Architecture:** Neues Bool `User.use_fixed_monthly_target`. Drei zentrale Lese-Helper in `calculation_service.py` (`fixed_monthly_target`, `fixed_month_credit`, `fixed_month_unpaid_reduction`) sind die EINZIGE Quelle der Modus-Logik; alle vier Akkumulations-Funktionen (`get_range_target`/`get_range_actual`, `get_overtime_account`, `get_ytd_summary`) verzweigen ausschließlich über diese Helper. Byte-identisch für alle Nicht-Modus-MA.

**Tech Stack:** FastAPI/Python 3.12, SQLAlchemy, Alembic, Decimal-Arithmetik, pytest (SQLite conftest); React 18/TS Frontend.

## Global Constraints

- **Frozen §16-Calc:** jede Änderung MUSS für `use_fixed_monthly_target == False` byte-identisch zum Ist-Stand sein. Jede Calc-Task hat einen Vorher/Nachher-Vergleichstest.
- **Decimal, nie float** in der Berechnung; Pydantic-Response-Schemas nutzen `float`.
- **Parallelpfad-Disziplin (Lektion 1.14.3):** `get_range_target`, `get_overtime_account` (Inline-Monatsloop) und `get_ytd_summary` bauen Soll/Ist je eigenständig nach — der Modus MUSS in allen greifen, ausschließlich über die zentralen Helper. Ein Konsistenztest (`get_overtime_account` == Σ Monats-Soll/Ist == `get_ytd_summary`) sichert das ab.
- **Nie blockierend:** die Plausibilitäts-Warnung ist ein transienter Warncode, kein 400.
- **Migration-Revision:** neue Revision `065_fixed_monthly_target`, `down_revision = "064_carryover_vac_prec"`, ID ≤ 32 Zeichen.
- **`UserListResponse` trägt neue Bool-Felder** (sonst Edit-Reset — #376/#377-Latenzbug).
- Tests via `docker run --rm --user root -v "$(pwd)/backend":/app -w /app -e TZ=Europe/Berlin -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" -e DATABASE_URL="sqlite:////tmp/t.db" -e ADMIN_EMAIL=a@b.de -e ADMIN_PASSWORD=Dummy2025X praxiszeit-backend sh -c "rm -f /tmp/t.db test.db; python -m pytest <ziel> -q -p no:cacheprovider"` (Backend-Image gebaut, kein Host-Volume). Branch `feat/377-baustein-2b` (Spec bereits committet).

---

### Task 1: Migration + User-Model-Feld `use_fixed_monthly_target`

**Files:**
- Create: `backend/alembic/versions/2026_07_14_1000-065_fixed_monthly_target.py`
- Modify: `backend/app/models/user.py:58` (nach `agreed_monthly_hours`)

**Interfaces:**
- Produces: `User.use_fixed_monthly_target: bool` (Default False)

- [ ] **Step 1: Migration schreiben**

```python
"""#377 Baustein 2b: users.use_fixed_monthly_target

Revision ID: 065_fixed_monthly_target
Revises: 064_carryover_vac_prec
Create Date: 2026-07-14

Opt-in: festes Monats-Soll (= agreed_monthly_hours) statt Per-Tag-Summe.
Default false → alle Bestands-MA unverändert. users ist bereits tenant-scoped.
"""
from alembic import op
import sqlalchemy as sa

revision = "065_fixed_monthly_target"
down_revision = "064_carryover_vac_prec"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("use_fixed_monthly_target", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade():
    op.drop_column("users", "use_fixed_monthly_target")
```

- [ ] **Step 2: Model-Feld ergänzen**

In `backend/app/models/user.py` direkt nach der `agreed_monthly_hours`-Zeile:

```python
    use_fixed_monthly_target = Column(Boolean, default=False, nullable=False, server_default='false')  # #377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours
```

- [ ] **Step 3: Migration up→down→up gegen Wegwerf-PG18 verifizieren**

Exakt der Migrations-Testablauf aus dem `/buildrelease`-Skill (Phase 6): Wegwerf-`postgres:18-alpine` im eigenen Docker-Netz hochfahren, dann `praxiszeit-backend` mit den 4 Config-Envs INLINE (`DATABASE_URL` gegen die Wegwerf-DB — aus Teilen bauen, damit der Secret-Scanner nicht auslöst; `SECRET_KEY`/`ADMIN_EMAIL`/`ADMIN_PASSWORD`) laufen lassen:

```
alembic upgrade head && alembic downgrade 064_carryover_vac_prec && alembic upgrade head && alembic current
```
Expected: endet auf `065_fixed_monthly_target (head)`, keine Fehler. (⚠️ fish splittet ein `$VAR` mit den `-e …`-Flags nicht → jede `-e` inline übergeben.)

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/2026_07_14_1000-065_fixed_monthly_target.py backend/app/models/user.py
git commit -m "feat(#377-2b): use_fixed_monthly_target Feld + Migration 065"
```

---

### Task 2: Zentrale Helper in `calculation_service.py`

**Files:**
- Modify: `backend/app/services/calculation_service.py` (neue Funktionen nach `get_daily_target_for_date`, ~Zeile 141)
- Test: `backend/tests/test_fixed_monthly_target.py` (Create)

**Interfaces:**
- Consumes: `_within_employment_window(user, d)`, `get_daily_target_for_date(user, d, weekly_hours)`, `get_weekly_hours_for_date(db, user, d, wh_changes)`, `special_days_service.get_special_day_config` + `half_special_day_weight` (#394).
- Produces:
  - `fixed_monthly_target(user, year, month) -> Decimal`
  - `fixed_month_credit(db, user, year, month, up_to_date=None) -> Decimal`
  - `fixed_month_unpaid_reduction(db, user, year, month, up_to_date=None) -> Decimal`
  - Interne Konstante: bezahlte Gutschrift-Typen `{VACATION, PAID_LEAVE}` (Feiertage separat), unbezahlte `{OTHER, UNPAID_FREE}` — UNPAID_FREE existiert NICHT als eigener AbsenceType; #376 mappt `UNPAID_FREE`-Verhalten auf `AbsenceType.OTHER`. → In der Praxis sind unbezahlte Fehltage = `AbsenceType.OTHER`. **Prüfen** (`grep UNPAID_FREE backend/app/models/absence.py`): falls es KEIN eigener Enum-Wert ist (nur ein reason base_behavior), behandelt der Modus `OTHER` als unbezahlt und `PAID_LEAVE` als bezahlt — kein Weg, per-Absence paid/unpaid feiner zu unterscheiden. Das ist akzeptiert (Spec §5).

- [ ] **Step 1: Failing Tests schreiben** (`backend/tests/test_fixed_monthly_target.py`)

```python
"""#377 Baustein 2b: zentrale Fix-Monats-Soll-Helper."""
from datetime import date
from decimal import Decimal
import pytest
from app.models import User, UserRole, Absence, AbsenceType, PublicHoliday
from app.services import calculation_service as cs
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, **kw):
    base = dict(username="fx", email="fx@t.l", password_hash="x", first_name="F",
                last_name="X", role=UserRole.EMPLOYEE, weekly_hours=Decimal("10"),
                work_days_per_week=2, track_hours=True, is_active=True,
                use_daily_schedule=True, use_fixed_monthly_target=True,
                agreed_monthly_hours=Decimal("40"),
                hours_monday=Decimal("3"), hours_wednesday=Decimal("3"),
                tenant_id=DEFAULT_TENANT_ID)
    base.update(kw)
    u = User(**base); db.add(u); db.commit(); db.refresh(u)
    return u


def test_fixed_target_is_flat_across_months(db, default_tenant):
    u = _mk(db)
    # März 2025 (5 Montage) vs Feb 2025 (4 Montage) → beide 40h fix.
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("40.00")
    assert cs.fixed_monthly_target(u, 2025, 2) == Decimal("40.00")


def test_fixed_target_prorata_on_entry(db, default_tenant):
    u = _mk(db, first_work_day=date(2025, 3, 16))  # 16 von 31 Tagen im Fenster
    assert cs.fixed_monthly_target(u, 2025, 3) == (Decimal("40") * 16 / 31).quantize(Decimal("0.01"))


def test_fixed_target_zero_when_flag_off(db, default_tenant):
    u = _mk(db, use_fixed_monthly_target=False)
    assert cs.fixed_monthly_target(u, 2025, 3) == Decimal("0")


def test_credit_holiday_on_planned_day(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Montag
    db.commit()
    # geplante Mo-Stunden = 3 → Gutschrift 3
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_credit_holiday_on_unplanned_day_is_zero(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025, 3, 4), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Dienstag, ungeplant
    db.commit()
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("0.00")


def test_credit_vacation_but_not_sick(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.VACATION, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 12),
                   type=AbsenceType.SICK, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    # NUR VACATION zählt hier (SICK läuft über credited_absences → keine Doppelgutschrift)
    assert cs.fixed_month_credit(db, u, 2025, 3) == Decimal("3.00")


def test_unpaid_other_reduces_soll(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025, 3, 5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))  # Mi geplant
    db.commit()
    assert cs.fixed_month_unpaid_reduction(db, u, 2025, 3) == Decimal("3.00")
```

- [ ] **Step 2: Tests laufen → FAIL** (`AttributeError: module 'calculation_service' has no attribute 'fixed_monthly_target'`)

Run: `… pytest tests/test_fixed_monthly_target.py -q`

- [ ] **Step 3: Helper implementieren** (nach `get_daily_target_for_date`, ~Zeile 141)

```python
def fixed_monthly_target(user: User, year: int, month: int) -> Decimal:
    """#377 Baustein 2b: festes Monats-Soll = agreed_monthly_hours, anteilig bei
    Eintritt/Austritt (Kalendertag-Bruchteil des Beschäftigungsfensters im Monat).
    Gibt 0, wenn der Modus aus ist oder agreed fehlt (Caller → wie Modus aus)."""
    agreed = getattr(user, "agreed_monthly_hours", None)
    if not getattr(user, "use_fixed_monthly_target", False) or not agreed or Decimal(str(agreed)) <= 0:
        return Decimal('0')
    agreed = Decimal(str(agreed))
    days_in_month = monthrange(year, month)[1]
    in_window = sum(
        1 for day in range(1, days_in_month + 1)
        if _within_employment_window(user, date(year, month, day))
    )
    if in_window == 0:
        return Decimal('0')
    if in_window == days_in_month:
        return agreed.quantize(Decimal('0.01'))
    return (agreed * Decimal(in_window) / Decimal(days_in_month)).quantize(Decimal('0.01'))


# #377 Baustein 2b: bezahlte Fehltag-Typen, die im Fix-Modus geplante Stunden dem
# Ist gutschreiben. SICK/TRAINING NICHT hier — die laufen über credited_absences
# (get_range_actual); erneut addieren wäre Doppelgutschrift.
_FIXED_PAID_CREDIT_TYPES = frozenset({AbsenceType.VACATION, AbsenceType.PAID_LEAVE})
# unbezahlt entschuldigt → mindert das feste Soll.
_FIXED_UNPAID_TYPES = frozenset({AbsenceType.OTHER})


def _fixed_planned_hours(db: Session, user: User, d: date, special_cfg: dict) -> Decimal:
    """Geplante Tagesstunden an ``d`` (0 an ungeplanten Tagen/Wochenende), inkl.
    #394-Sondertags-/Halbtags-Faktor. Nur im use_daily_schedule-Sinn sinnvoll."""
    weekly = get_weekly_hours_for_date(db, user, d)
    planned = get_daily_target_for_date(user, d, weekly)
    if planned <= 0:
        return Decimal('0')
    return (planned * half_special_day_weight(d, special_cfg))


def _fixed_month_absence_hours(db, user, year, month, types, up_to_date, include_holidays):
    """Gemeinsame Schleife: Σ geplante Stunden für Tage mit einem passenden
    ganztägigen Absence-Typ (bzw. Feiertag, wenn include_holidays), im Fenster,
    ≤ up_to_date, ohne konkurrierenden TimeEntry (reale Erfassung gewinnt)."""
    days_in_month = monthrange(year, month)[1]
    cfg = special_days_service.get_special_day_config(db, user.tenant_id, year)
    holiday_dates = set()
    if include_holidays:
        holiday_dates = {h.date for h in db.query(PublicHoliday).filter(
            date_in_month(PublicHoliday.date, year, month),
            PublicHoliday.tenant_id == user.tenant_id,
        ).all()}
    absences = {a.date: a for a in db.query(Absence).filter(
        Absence.user_id == user.id, Absence.tenant_id == user.tenant_id,
        date_in_month(Absence.date, year, month),
        Absence.type.in_(list(types)), Absence.start_time.is_(None),  # nur ganztägig
    ).all()}
    entry_dates = {e.date for e in db.query(TimeEntry.date).filter(
        TimeEntry.user_id == user.id, TimeEntry.tenant_id == user.tenant_id,
        date_in_month(TimeEntry.date, year, month),
    ).all()}
    total = Decimal('0')
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if up_to_date is not None and d > up_to_date:
            continue
        if not _within_employment_window(user, d):
            continue
        if d in entry_dates:
            continue  # reale Erfassung gewinnt
        a = absences.get(d)
        is_holiday = include_holidays and d in holiday_dates
        if not a and not is_holiday:
            continue
        planned = _fixed_planned_hours(db, user, d, cfg)
        if a is not None and a.half_day:
            planned = planned * Decimal('0.5')
        total += planned
    return total.quantize(Decimal('0.01'))


def fixed_month_credit(db: Session, user: User, year: int, month: int, up_to_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden, die BEZAHLTE Fehltage (Feiertag +
    VACATION/PAID_LEAVE) dem Ist gutschreiben. SICK/TRAINING NICHT (Doppelguard)."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_PAID_CREDIT_TYPES,
                                      up_to_date, include_holidays=True)


def fixed_month_unpaid_reduction(db: Session, user: User, year: int, month: int, up_to_date: date = None) -> Decimal:
    """#377 Baustein 2b: geplante Stunden UNBEZAHLTER Fehltage (OTHER), die das
    feste Monats-Soll mindern (statt Ist+)."""
    if not getattr(user, "use_fixed_monthly_target", False):
        return Decimal('0')
    return _fixed_month_absence_hours(db, user, year, month, _FIXED_UNPAID_TYPES,
                                      up_to_date, include_holidays=False)
```

(Imports prüfen: `date_in_month`, `TimeEntry`, `half_special_day_weight`, `special_days_service` sind in `calculation_service.py` bereits verfügbar.)

- [ ] **Step 4: Tests laufen → PASS**

Run: `… pytest tests/test_fixed_monthly_target.py -q` → 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calculation_service.py backend/tests/test_fixed_monthly_target.py
git commit -m "feat(#377-2b): zentrale Fix-Monats-Soll-Helper (target/credit/unpaid) + Tests"
```

---

### Task 3: Branch `get_range_target` / `get_monthly_target` (Soll-Seite, Live-Anzeigen)

**Files:**
- Modify: `backend/app/services/calculation_service.py:266` (`get_range_target`)
- Test: `backend/tests/test_fixed_monthly_target.py` (ergänzen)

**Interfaces:**
- Consumes: `fixed_monthly_target`, `fixed_month_unpaid_reduction` (Task 2)
- Produces: `get_monthly_target` liefert für Modus-MA das feste (pro-rata, unpaid-geminderte) Soll.

- [ ] **Step 1: Failing Test**

```python
def test_monthly_target_fixed_mode(db, default_tenant):
    u = _mk(db)
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("40.00")  # nicht Σ Tagesstunden
    assert cs.get_monthly_target(db, u, 2025, 2) == Decimal("40.00")

def test_monthly_target_unpaid_reduces(db, default_tenant):
    u = _mk(db)
    db.add(Absence(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025,3,5),
                   type=AbsenceType.OTHER, hours=Decimal("3"), half_day=False))
    db.commit()
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("37.00")  # 40 − 3 unbezahlt

def test_range_target_non_mode_byte_identical(db, default_tenant):
    u = _mk(db, use_fixed_monthly_target=False, weekly_hours=Decimal("40"), work_days_per_week=5,
            use_daily_schedule=False, agreed_monthly_hours=None)
    # Referenzwert: Σ 8h über die Werktage im März 2025 (21 Werktage) = 168
    assert cs.get_monthly_target(db, u, 2025, 3) == Decimal("168.00")
```

- [ ] **Step 2: Test läuft → FAIL** (Modus-Test liefert die Per-Tag-Summe statt 40)

- [ ] **Step 3: Branch in `get_range_target`** — direkt nach dem `if not user.track_hours or end < start:`-Guard einfügen:

```python
    # #377 Baustein 2b: fester Monats-Soll-Modus — statt der Per-Tag-Summe die
    # (pro-rata + unpaid-geminderten) festen Monats-Solls über die Range summieren.
    if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
        total = Decimal('0')
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            first = date(y, m, 1)
            last = date(y, m, monthrange(y, m)[1])
            month_start = max(first, start)
            month_end = min(last, end if up_to_date is None else min(end, up_to_date))
            if month_end >= month_start:
                mt = fixed_monthly_target(user, y, m)
                mt -= fixed_month_unpaid_reduction(db, user, y, m, up_to_date=month_end)
                # Range-/cutoff-Skalierung: Anteil der in [month_start,month_end] ∩ Fenster
                # liegenden Kalendertage an den Fenster-Tagen des Monats.
                win_days = sum(1 for dd in range(1, monthrange(y, m)[1] + 1)
                               if _within_employment_window(user, date(y, m, dd)))
                in_days = sum(1 for dd in range(month_start.day, month_end.day + 1)
                              if _within_employment_window(user, date(y, m, dd)))
                if win_days > 0 and in_days < win_days:
                    mt = (mt * Decimal(in_days) / Decimal(win_days))
                total += mt
            m += 1
            if m > 12:
                m = 1; y += 1
        return total.quantize(Decimal('0.01'))
```

(Der bestehende Per-Tag-Code bleibt darunter unverändert für Nicht-Modus-MA.)

- [ ] **Step 4: Tests laufen → PASS** (inkl. Byte-Identität non-mode)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calculation_service.py backend/tests/test_fixed_monthly_target.py
git commit -m "feat(#377-2b): get_range_target Fix-Modus-Branch (festes Soll, byte-identisch off)"
```

---

### Task 4: Branch `get_range_actual` / `get_monthly_actual` (Ist-Gutschrift)

**Files:**
- Modify: `backend/app/services/calculation_service.py:352` (`get_range_actual`)
- Test: `backend/tests/test_fixed_monthly_target.py`

**Interfaces:**
- Consumes: `fixed_month_credit` (Task 2)
- Produces: `get_monthly_actual` addiert für Modus-MA die Fix-Gutschrift.

- [ ] **Step 1: Failing Test**

```python
def test_monthly_actual_credits_holiday(db, default_tenant):
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025,3,3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))  # Mo
    db.commit()
    # kein TimeEntry → Ist = 0 + Gutschrift 3 (geplante Mo-Stunden)
    assert cs.get_monthly_actual(db, u, 2025, 3) == Decimal("3.00")
```

- [ ] **Step 2: Test → FAIL** (liefert 0, keine Gutschrift)

- [ ] **Step 3: Branch in `get_range_actual`** — vor dem finalen `return` die Fix-Gutschrift addieren (per Monat, da `fixed_month_credit` monatsweise arbeitet):

```python
    fixed_credit = Decimal('0')
    if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            last = date(y, m, monthrange(y, m)[1])
            month_end = min(last, end if up_to_date is None else min(end, up_to_date))
            fixed_credit += fixed_month_credit(db, user, y, m, up_to_date=month_end)
            m += 1
            if m > 12:
                m = 1; y += 1
    return (Decimal(str(total)) + credited_hours + fixed_credit).quantize(Decimal('0.01'))
```

(Ersetzt das bestehende `return (Decimal(str(total)) + credited_hours)...`.)

- [ ] **Step 4: Tests → PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(#377-2b): get_range_actual Fix-Gutschrift (Feiertag/Urlaub/PAID_LEAVE)"
```

---

### Task 5: Branch `get_overtime_account` (Inline-Monatsloop)

**Files:**
- Modify: `backend/app/services/calculation_service.py:501` (Monatsloop: `monthly_target` + `actual_by_month`)
- Test: `backend/tests/test_fixed_monthly_target.py`

**Interfaces:**
- Consumes: `fixed_monthly_target`, `fixed_month_unpaid_reduction`, `fixed_month_credit`

- [ ] **Step 1: Failing Test**

```python
def test_overtime_account_fixed_mode(db, default_tenant):
    from app.models import TimeEntry
    u = _mk(db)  # agreed 40/Monat
    # März 2025: 30h real erfasst → Konto = 30 − 40 = −10
    db.add(TimeEntry(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, date=date(2025,3,5),
                     start_time=..., end_time=..., ))  # 30h über Einträge; Helper _entry im Test
    db.commit()
    assert cs.get_overtime_account(db, u, 2025, 3) == Decimal("-10.00")
```
(Realer Test: mehrere TimeEntries mit definierten net_hours; Summe 30. `_entry`-Helper analog bestehender calc-Tests nutzen.)

- [ ] **Step 2: Test → FAIL** (nutzt die Inline-Per-Tag-Summe = schwankendes Soll)

- [ ] **Step 3: Im Monatsloop** (am Schleifenanfang, nach `key = (current_year, current_month)`) verzweigen und an die schon modus-korrekten Wrapper (Tasks 3+4) DELEGIEREN — statt `actual_by_month`/`monthly_target` inline neu zu rekonstruieren (kein Risiko, die bestehende SICK/TRAINING-Gutschrift zu verlieren; Single Source):

```python
        if getattr(user, "use_fixed_monthly_target", False) and getattr(user, "agreed_monthly_hours", None):
            # #377 Baustein 2b: get_monthly_target/actual sind bereits modus-korrekt
            # (festes Soll − unpaid bzw. Ist + Gutschrift). Cutoff (#313) im laufenden
            # Monat über up_to_date durchreichen.
            _last = date(current_year, current_month, monthrange(current_year, current_month)[1])
            _upto = min(_last, up_to_date)  # up_to_date ist der Monatsende-/cutoff-Termin oben
            monthly_target = get_monthly_target(db, user, current_year, current_month, up_to_date=_upto)
            monthly_actual = get_monthly_actual(db, user, current_year, current_month, up_to_date=_upto)
            total_balance += monthly_actual - monthly_target
            current_month += 1
            if current_month > 12:
                current_month = 1; current_year += 1
            continue
```

(Die bestehende Per-Tag-`for day`-Schleife + die reguläre Ist-Berechnung bleiben für Nicht-Modus-MA darunter unverändert. Perf: der Wrapper-Aufruf macht pro Monat ein paar Queries — akzeptiert, da Modus = wenige Minijob-Accounts; der schnelle Per-Tag-Pfad für alle anderen MA ist unberührt. `up_to_date` ist im Kontext bereits der cutoff/Monatsende — verifizieren, dass die Variable im Loop den korrekten Obergrenzen-Wert trägt.)

- [ ] **Step 4: Tests → PASS** + Byte-Identität non-mode (bestehende `test_calculations.py`/Overtime-Tests grün).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(#377-2b): get_overtime_account Fix-Modus-Branch im Monatsloop"
```

---

### Task 6: Branch `get_ytd_summary`

**Files:**
- Modify: `backend/app/services/calculation_service.py:862`
- Test: `backend/tests/test_fixed_monthly_target.py`

**Interfaces:** Consumes dieselben drei Helper.

- [ ] **Step 1: Failing Test**

```python
def test_ytd_summary_fixed_mode(db, default_tenant):
    u = _mk(db)
    # ohne Einträge: YTD-Soll bis März = 3×40 = 120 (Jan+Feb+Mär), Ist = Gutschriften
    r = cs.get_ytd_summary(db, u, 2025, cutoff_date=date(2025,3,31))
    assert r["target_hours"] == 120.00
```
(cutoff_date/Signatur an die reale `get_ytd_summary`-Signatur anpassen — Zeile 862 lesen.)

- [ ] **Step 2: Test → FAIL**

- [ ] **Step 3:** In `get_ytd_summary` für Modus-MA früh verzweigen und pro Monat des Jahres (bis `cutoff_date`) an die Wrapper delegieren — `total_target += get_monthly_target(db,user,year,m,up_to_date=_upto)`, `total_actual += get_monthly_actual(db,user,year,m,up_to_date=_upto)` (Single Source, analog Task 5) — statt der `_day_soll_contribution`-Schleife + Inline-Ist. Nicht-Modus-Pfad unverändert. `_upto` = min(Monatsende, cutoff_date).

- [ ] **Step 4: Tests → PASS**

- [ ] **Step 5: Commit** `git commit -am "feat(#377-2b): get_ytd_summary Fix-Modus-Branch"`

---

### Task 7: Parallelpfad-Konsistenztest + Byte-Identitäts-Suite

**Files:** Test: `backend/tests/test_fixed_monthly_target.py`

- [ ] **Step 1: Konsistenztest schreiben** — für einen Modus-MA mit gemischten Monaten (Einträge, Feiertag, Urlaub, unbezahlt) über mehrere Monate:

```python
def test_parallel_paths_consistent(db, default_tenant):
    u = _mk(db)
    # ... Einträge + 1 Feiertag + 1 VACATION + 1 OTHER über Jan–Mär 2025 seeden ...
    # get_overtime_account bis Mär == Σ_(m=1..3) (get_monthly_actual − get_monthly_target)
    acc = cs.get_overtime_account(db, u, 2025, 3)
    manual = sum(cs.get_monthly_actual(db, u, 2025, m) - cs.get_monthly_target(db, u, 2025, m)
                 for m in (1, 2, 3))
    assert acc == manual.quantize(Decimal("0.01"))
    ytd = cs.get_ytd_summary(db, u, 2025, cutoff_date=date(2025,3,31))
    assert Decimal(str(ytd["overtime"])) == acc  # (ggf. Carryover=0 im Test)
```

- [ ] **Step 2: Byte-Identitäts-Test** — ein Nicht-Modus-MA: `get_overtime_account`/`get_ytd_summary`/`get_monthly_target`/`get_monthly_actual` == handberechnete Referenzwerte (wie heute). (Dieselben Referenzwerte, die die bestehenden `test_calculations.py` prüfen — sicherstellen, dass die dortige Suite grün bleibt.)

- [ ] **Step 3: Volle betroffene Suite grün**

Run: `… pytest tests/test_fixed_monthly_target.py tests/test_calculations.py tests/test_milog*.py -q`

- [ ] **Step 4: Commit** `git commit -am "test(#377-2b): Parallelpfad-Konsistenz + Byte-Identität"`

---

### Task 8: `settlement_aging`/`get_overtime_history_detailed`-Kohärenz (#377)

**Files:**
- Verify/Modify: `backend/app/services/calculation_service.py:681` (`get_overtime_history_detailed`)
- Modify (nur falls nötig): `backend/app/services/milog_service.py`
- Test: `backend/tests/test_fixed_monthly_target.py`

**Interfaces:** `get_overtime_history_detailed` liefert je Monat `target`/`actual` — muss im Modus die Fix-Werte tragen (damit `settlement_aging` = actual−target konsistent ist).

- [ ] **Step 1: Failing Test** — ein Modus-MA mit Feiertag/Urlaub darf KEIN Phantom-Defizit im `settlement_aging` erzeugen:

```python
def test_settlement_aging_no_phantom_deficit_fixed_mode(db, default_tenant):
    from app.services import milog_service
    u = _mk(db)
    db.add(PublicHoliday(date=date(2025,3,3), name="X", year=2025, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    aging = milog_service.settlement_aging(db, u, 2025, 3, cutoff=date(2025,3,31))
    # Feiertag ist gutgeschrieben → target==actual im Nur-Feiertag-Monat → kein Defizit-Posten
    assert aging.get("oldest_overdue") in (None, 0) or aging["total_deficit"] <= 0
```
(Reale Assertion an die `settlement_aging`-Rückgabestruktur anpassen — Funktion lesen.)

- [ ] **Step 2: `get_overtime_history_detailed` lesen** (Zeile 681) — nutzt es intern `get_monthly_target`/`get_monthly_actual`? Dann automatisch modus-korrekt (Tasks 3+4) → Test grün ohne Änderung. Baut es die Per-Monat-`target`/`actual` inline nach (wie `get_overtime_account`)? Dann denselben Delegations-Branch wie Task 5 einfügen (`get_monthly_target/actual` mit `up_to_date` pro Monat).

- [ ] **Step 3:** Falls nötig: Delegations-Branch in `get_overtime_history_detailed` (identisch zu Task 5 Step 3). Sicherstellen, dass die `settlement_aging`-Delta-Reihe (`actual − target`) je Monat die Fix-Werte trägt → keine Phantom-Defizite durch gutgeschriebene Feiertage/Urlaub.

- [ ] **Step 4: Tests → PASS**

- [ ] **Step 5: Commit** `git commit -am "feat(#377-2b): settlement_aging/history-Kohärenz im Fix-Modus"`

---

### Task 9: Plausibilitäts-Warnung `MILOG_MONTHLY_EXCEEDED`

**Files:**
- Modify: `backend/app/services/milog_service.py` (neue `monthly_exceeded_check` + `..._warning_text`)
- Modify: `backend/app/routers/dashboard.py` (`get_overtime_account`-Response `milog_warnings`), `backend/app/routers/admin_users.py` (`users_overview`), Push-Flächen `clock_out`/`create_time_entry`/`update_time_entry`
- Test: `backend/tests/test_fixed_monthly_target.py`

**Interfaces:** `monthly_exceeded_check(db, user, year, month, up_to_date=None) -> dict|None` → None wenn Modus aus oder Ist ≤ agreed; sonst `{month_actual, agreed}`.

- [ ] **Step 1: Failing Test**

```python
def test_monthly_exceeded_warning(db, default_tenant):
    from app.services import milog_service
    u = _mk(db, agreed_monthly_hours=Decimal("40"))
    # 45h real erfasst im März → Warnung
    # ... TimeEntries Σ 45 seeden ...
    chk = milog_service.monthly_exceeded_check(db, u, 2025, 3)
    assert chk is not None and chk["month_actual"] > chk["agreed"]
```

- [ ] **Step 2: Test → FAIL**

- [ ] **Step 3: Implementieren** in `milog_service.py`:

```python
def monthly_exceeded_check(db, user, year, month, up_to_date=None):
    """#377 Baustein 2b: weiche Warnung, wenn das Monats-Ist (inkl. Gutschriften)
    die vereinbarte Monatsarbeitszeit übersteigt. None wenn Modus aus."""
    if not getattr(user, "use_fixed_monthly_target", False) or not getattr(user, "track_hours", False):
        return None
    agreed = getattr(user, "agreed_monthly_hours", None)
    if not agreed:
        return None
    agreed = Decimal(str(agreed))
    actual = calculation_service.get_monthly_actual(db, user, year, month, up_to_date=up_to_date)
    if actual > agreed:
        return {"month_actual": float(actual), "agreed": float(agreed), "year": year, "month": month}
    return None


def monthly_exceeded_warning_text(chk: dict) -> str:
    return (f"MILOG_MONTHLY_EXCEEDED: Erfasste Stunden {chk['month_actual']:.1f}h im "
            f"{chk['month']:02d}/{chk['year']} übersteigen die vereinbarte Monatsarbeitszeit "
            f"({chk['agreed']:.1f}h). Bitte prüfen (sofern zur Mindestlohnhöhe vergütet).")
```

- [ ] **Step 4:** In `dashboard.get_overtime_account` (self) + `admin_users.users_overview` (`is_current_year`-gated) den Check anhängen an `milog_warnings`; in `clock_out`/`create_time_entry`/`update_time_entry` an die `warnings`-Response (wie die bestehenden #377-MILOG-Warnungen — dort das Muster kopieren).

- [ ] **Step 5: Tests → PASS**, Leak-Guard-Test `test_deployment_mode.py` grün (Warncode ist kein System-Info-Feld).

- [ ] **Step 6: Commit** `git commit -am "feat(#377-2b): MILOG_MONTHLY_EXCEEDED weiche Warnung + Warnflächen"`

---

### Task 10: Schemas + Validierung

**Files:**
- Modify: `backend/app/schemas/user.py` (`UserCreate`:50, `UserUpdate`:106, `UserListResponse`:175 — `use_fixed_monthly_target` + Validator)
- Test: `backend/tests/test_cross_tenant_api.py` oder neuer `test_user_fixed_mode_validation.py`

**Interfaces:** `use_fixed_monthly_target: bool = False` in Create/List; `Optional[bool]` in Update. Validator: Flag True ⇒ `agreed_monthly_hours > 0` UND `track_hours True`, sonst 422.

- [ ] **Step 1: Failing Test** — POST/PUT User mit `use_fixed_monthly_target=True` ohne `agreed_monthly_hours` → 422; mit agreed + track_hours → 200; `UserListResponse` enthält das Feld.

- [ ] **Step 2: Test → FAIL**

- [ ] **Step 3:** Felder in den drei Schemas ergänzen + `@model_validator(mode="after")` in `UserCreate`/`UserUpdate`:

```python
    use_fixed_monthly_target: bool = False  # #377 Baustein 2b

    @model_validator(mode="after")
    def _fixed_mode_requires_agreed(self):
        if getattr(self, "use_fixed_monthly_target", False):
            if not self.agreed_monthly_hours or self.agreed_monthly_hours <= 0:
                raise ValueError("Fester Monats-Soll braucht eine vereinbarte Monatsarbeitszeit (> 0).")
            if self.track_hours is False:
                raise ValueError("Fester Monats-Soll setzt Stundenzählung (track_hours) voraus.")
        return self
```
(In `UserUpdate` defensiv gegen `None`-Felder — nur prüfen, wenn das Flag im Payload True ist.)

- [ ] **Step 4: Tests → PASS**

- [ ] **Step 5: Commit** `git commit -am "feat(#377-2b): Schema-Felder + Pflicht-Validierung (agreed + track_hours)"`

---

### Task 11: Frontend UserForm

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx` (State :39-47, :90-98, Checkbox-Block :519)
- Test: manuell (vitest optional für die Conditional-Logik)

- [ ] **Step 1:** State-Feld `use_fixed_monthly_target: false` (init + edit-Preload), plus Checkbox „Feste Monatsarbeitszeit" **innerhalb** des `milog_working_time_account`-Blocks (nur sichtbar wenn MiLoG-Konto an).

- [ ] **Step 2:** Wenn `use_fixed_monthly_target`: Wochenzeit-Feld read-only/ausgeblendet, `agreed_monthly_hours` als Pflichtfeld markiert (`required`, `step=0.1`), Tagesstunden-Matrix-Label → „geplante Anwesenheit (für Feiertags-/Fehltags-Gutschrift)". `use_daily_schedule` empfohlen/aktiviert.

- [ ] **Step 3:** `tsc --noEmit` + `npm run build` grün:
```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:20-alpine sh -c "npx tsc --noEmit && npm run build"
```

- [ ] **Step 4: Commit** `git commit -am "feat(#377-2b): UserForm Checkbox Feste Monatsarbeitszeit + Conditional-UI"`

---

### Task 12: Frontend-Warncode + Badges

**Files:**
- Modify: `frontend/src/utils/arbzgWarnings.ts` (Warncode-Katalog: `MILOG_MONTHLY_EXCEEDED`), `frontend/src/pages/Dashboard.tsx` + `frontend/src/pages/admin/Users.tsx` (MiLoG-Badge-Anzeige wie #377)
- ggf. `collectAbsenceWarnings`

- [ ] **Step 1:** `MILOG_MONTHLY_EXCEEDED` in die Warncode-Erkennung/`showArbzgWarnings`-Map aufnehmen (Severity warning, Text aus der Response).

- [ ] **Step 2:** Badge/Hinweis im Dashboard (self) + Benutzerübersicht (Admin) für Modus-MA mit aktiver Warnung — Muster von den #377-`milog_warnings` kopieren.

- [ ] **Step 3:** `tsc --noEmit` + `npm run build` grün.

- [ ] **Step 4: Commit** `git commit -am "feat(#377-2b): Frontend MILOG_MONTHLY_EXCEEDED + Badges"`

---

### Task 13: Doku + CLAUDE.md

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md`, `docs/handbuch/CHEATSHEET-ADMIN.md`, `frontend/src/components/DocViewer.tsx` (In-App-Hilfe — beides pflegen), `CLAUDE.md` (#377-Regel), `docs/BACKEND-ARCHITEKTUR.md` (Berechnungsmodell)
- ggf. `docs/CHANGELOG.md` beim Release

- [ ] **Step 1:** Handbuch + In-App-Hilfe: den Modus „feste Monatsarbeitszeit" beschreiben (fixes Monats-Soll, geplante Tagesstunden = Anwesenheitsmuster + Gutschrift, Feiertags-/Urlaubs-/Krank-Gutschrift, unbezahlt mindert Soll, weiche Ist>Soll-Warnung) + die **Fehlmonat-Grenze** (§5 Spec) explizit.

- [ ] **Step 2:** CLAUDE.md `#377`-Regel um Baustein 2b erweitern: Modus, die drei zentralen Helper, die **vier Parallelpfade** (get_range_target/actual, get_overtime_account, get_ytd_summary, get_overtime_history_detailed) und den Doppelgutschrift-Guard (SICK/TRAINING NICHT in fixed_month_credit). „Aktuelle Version" beim Release bumpen.

- [ ] **Step 3: Commit** `git commit -am "docs(#377-2b): Handbuch + In-App-Hilfe + CLAUDE.md fester Monats-Soll"`

---

## Abschluss (nicht Teil der Tasks, beim Release)

- Voll-Suite grün (`scripts/local-ci.sh` bzw. der Docker-Run aus den Global Constraints über `tests/`).
- Multi-Agent-Release-Review mit dem gezielten Fokus „welche ANDEREN Pfade lesen Soll/Ist?" (Lektion 1.14.3).
- Auslieferung als **MINOR** über `/buildrelease` (neues Feature, Migration 065).
- PR gegen master (branch-protected), Merge = Manuel.
