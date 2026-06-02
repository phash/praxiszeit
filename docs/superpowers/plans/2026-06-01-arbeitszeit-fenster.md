# Arbeitszeit-Fenster (Frühstart-/Spät-Ende-Kappung) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pro Mitarbeiter:in ein optionales Soll-Arbeitszeit-Fenster (Beginn+Ende) je Wochentag; gestempelte/eingetragene Zeit außerhalb von `[Soll-Beginn − Puffer, Soll-Ende + Puffer]` wird nicht angerechnet, der Rohstempel bleibt erhalten.

**Architecture:** Neue (nullable) Soll-Zeit-Spalten am User + `raw_start_time`/`raw_end_time` am TimeEntry + tenant-Setting `work_window_grace_minutes`. Ein zentraler `work_window_service.clamp()` kappt beim Schreiben an allen Eintrags-Pfaden; `net_hours` und alle Salden bleiben unverändert (sie rechnen mit der gekappten Zeit). Opt-in: ohne gesetzte Soll-Zeiten ändert sich nichts.

**Tech Stack:** FastAPI / SQLAlchemy / Alembic (Python 3.12), React 18 + TypeScript, Pytest (SQLite), Vitest. Backend-Container: nach Edit `docker compose cp <file> backend:/app/<path>` vor `pytest`.

**Spec:** `docs/superpowers/specs/2026-06-01-arbeitszeit-fenster-design.md`

---

## File Structure

**Backend**
- `backend/app/models/user.py` — 10 neue `Time`-Spalten (scheduled_start/end_<weekday>).
- `backend/app/models/time_entry.py` — `raw_start_time`, `raw_end_time`.
- `backend/alembic/versions/2026_06_01_1000-048_add_work_window.py` — Migration (NEU).
- `backend/app/services/work_window_service.py` — `get_scheduled_window`, `clamp`, `get_grace_minutes` (NEU).
- `backend/app/routers/admin_settings.py` — `work_window_grace_minutes` in Whitelist + int-Validierung.
- `backend/app/routers/time_entries.py` — clamp in `clock_in`, `clock_out`, `create_time_entry`, `update_time_entry`.
- `backend/app/routers/admin_time_entries.py` — clamp in create + update.
- `backend/app/services/xls_import_service.py` — clamp beim Import.
- `backend/app/routers/admin_change_requests.py` — clamp bei Eintrags-Materialisierung.
- `backend/app/schemas/user.py` — neue Felder in `UserBase`, `UserUpdate`, `UserListResponse`.
- `backend/app/routers/admin_users.py` — `create_user` setzt die neuen Felder.
- `backend/app/schemas/time_entry.py` — `raw_start_time`/`raw_end_time` in der Response.

**Backend Tests**
- `backend/tests/test_work_window_service.py` (NEU)
- `backend/tests/test_work_window_integration.py` (NEU — clock_in/out/create)

**Frontend**
- `frontend/src/pages/admin/users/UserForm.tsx` — Soll-Zeiten je Wochentag.
- `frontend/src/pages/admin/Users.tsx` — `User`-Interface erweitern (Prop-Typ).
- `frontend/src/pages/admin/Settings.tsx` — Puffer-Eingabe.
- `frontend/src/components/MonthlyJournal.tsx`, `frontend/src/pages/TimeTracking.tsx` — „angerechnet"-Hinweis.
- `frontend/src/components/StampWidget.tsx` — Frühstart-Hinweis.

**Docs**
- `CLAUDE.md`, `docs/BACKEND-ARCHITEKTUR.md`, `docs/handbuch/HANDBUCH-ADMIN.md`, `frontend/src/components/DocViewer.tsx`.

---

## Task 1: DB-Spalten (Model + Migration)

**Files:**
- Modify: `backend/app/models/user.py` (nach `hours_friday`)
- Modify: `backend/app/models/time_entry.py`
- Create: `backend/alembic/versions/2026_06_01_1000-048_add_work_window.py`

- [ ] **Step 1: User-Model-Spalten ergänzen**

In `backend/app/models/user.py` direkt nach der Zeile `hours_friday = Column(...)`:

```python
    # #201: optionales Soll-Arbeitszeit-Fenster je Wochentag (Mo–Fr). NULL =
    # kein Fenster an dem Tag → keine Kappung. Kappt nur das Ist, nicht das Soll.
    scheduled_start_monday = Column(Time, nullable=True)
    scheduled_end_monday = Column(Time, nullable=True)
    scheduled_start_tuesday = Column(Time, nullable=True)
    scheduled_end_tuesday = Column(Time, nullable=True)
    scheduled_start_wednesday = Column(Time, nullable=True)
    scheduled_end_wednesday = Column(Time, nullable=True)
    scheduled_start_thursday = Column(Time, nullable=True)
    scheduled_end_thursday = Column(Time, nullable=True)
    scheduled_start_friday = Column(Time, nullable=True)
    scheduled_end_friday = Column(Time, nullable=True)
```

Sicherstellen, dass `Time` importiert ist (Zeile 1: `from sqlalchemy import Column, String, Boolean, Numeric, Integer, BigInteger, Enum, DateTime, Date, Text, ForeignKey` → `Time` ergänzen).

- [ ] **Step 2: TimeEntry-Model-Spalten ergänzen**

In `backend/app/models/time_entry.py` bei den Spalten (nach `break_minutes`):

```python
    # #201: tatsächlich gestempelte/eingegebene Zeit, falls die Soll-Fenster-
    # Kappung die jeweilige Seite verändert hat (sonst NULL = nicht gekappt).
    raw_start_time = Column(Time, nullable=True)
    raw_end_time = Column(Time, nullable=True)
```

`Time` im Import von `time_entry.py` sicherstellen.

- [ ] **Step 3: Migration schreiben**

Create `backend/alembic/versions/2026_06_01_1000-048_add_work_window.py`:

```python
"""Add work-window columns (#201): users scheduled_start/end_<weekday>,
time_entries raw_start/end_time.

Alle nullable, kein Backfill → volle Abwärtskompatibilität (kein gesetztes
Fenster = kein Verhaltenswechsel). users ist tenant-scoped, keine RLS-Änderung.

Revision ID: 048_add_work_window
Revises: 047_add_receives_closures
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = '048_add_work_window'
down_revision = '047_add_receives_closures'
branch_labels = None
depends_on = None

_WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')


def upgrade() -> None:
    for wd in _WEEKDAYS:
        op.add_column('users', sa.Column(f'scheduled_start_{wd}', sa.Time(), nullable=True))
        op.add_column('users', sa.Column(f'scheduled_end_{wd}', sa.Time(), nullable=True))
    op.add_column('time_entries', sa.Column('raw_start_time', sa.Time(), nullable=True))
    op.add_column('time_entries', sa.Column('raw_end_time', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('time_entries', 'raw_end_time')
    op.drop_column('time_entries', 'raw_start_time')
    for wd in _WEEKDAYS:
        op.drop_column('users', f'scheduled_end_{wd}')
        op.drop_column('users', f'scheduled_start_{wd}')
```

- [ ] **Step 4: Migration anwenden + Spalten prüfen**

```bash
docker cp backend/alembic/versions/2026_06_01_1000-048_add_work_window.py praxiszeit-backend-1:/app/alembic/versions/
docker cp backend/app/models/user.py praxiszeit-backend-1:/app/app/models/user.py
docker cp backend/app/models/time_entry.py praxiszeit-backend-1:/app/app/models/time_entry.py
docker compose exec -T backend sh -c "cd /app && alembic upgrade head"
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d users" | grep scheduled_
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d time_entries" | grep raw_
```
Expected: 10 `scheduled_*` + 2 `raw_*` Spalten gelistet, `alembic upgrade` läuft auf `048_add_work_window`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/models/time_entry.py backend/alembic/versions/2026_06_01_1000-048_add_work_window.py
git commit -m "feat(#201): DB-Spalten für Soll-Arbeitszeit-Fenster + Rohstempel"
```

---

## Task 2: `work_window_service` (Kapp-Logik)

**Files:**
- Create: `backend/app/services/work_window_service.py`
- Test: `backend/tests/test_work_window_service.py`

- [ ] **Step 1: Failing test schreiben**

Create `backend/tests/test_work_window_service.py`:

```python
from datetime import date, time
from app.models import User, UserRole
from app.services import work_window_service as wws


def _user(**kw):
    defaults = dict(
        username="w", email="w@x.de", password_hash="h", first_name="W", last_name="W",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
        track_hours=True,
    )
    defaults.update(kw)
    return User(**defaults)

MON = date(2026, 6, 1)  # Montag


def test_no_window_no_clamp():
    u = _user()  # keine Soll-Zeiten
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(7, 0), time(17, 0), 15)
    assert (eff_s, eff_e, raw_s, raw_e) == (time(7, 0), time(17, 0), None, None)


def test_early_start_capped():
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, eff_e, raw_s, raw_e = wws.clamp(u, MON, time(7, 0), time(16, 0), 15)
    assert eff_s == time(7, 45)   # 08:00 − 15min
    assert raw_s == time(7, 0)
    assert eff_e == time(16, 0) and raw_e is None  # kein Soll-Ende


def test_within_grace_not_capped():
    u = _user(scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(u, MON, time(7, 50), time(16, 0), 15)
    assert eff_s == time(7, 50) and raw_s is None  # 07:50 ≥ 07:45


def test_late_end_capped():
    u = _user(scheduled_end_monday=time(17, 0))
    _, eff_e, _, raw_e = wws.clamp(u, MON, time(8, 0), time(18, 30), 15)
    assert eff_e == time(17, 15) and raw_e == time(18, 30)


def test_track_hours_false_skips():
    u = _user(track_hours=False, scheduled_start_monday=time(8, 0))
    eff_s, _, raw_s, _ = wws.clamp(u, MON, time(6, 0), time(16, 0), 15)
    assert eff_s == time(6, 0) and raw_s is None


def test_open_end_none_passthrough():
    u = _user(scheduled_start_monday=time(8, 0), scheduled_end_monday=time(17, 0))
    eff_s, eff_e, _, raw_e = wws.clamp(u, MON, time(6, 0), None, 15)
    assert eff_e is None and raw_e is None  # offener Eintrag (clock_in)


def test_grace_shift_clamps_to_day_bounds():
    u = _user(scheduled_end_monday=time(23, 50))
    _, eff_e, _, _ = wws.clamp(u, MON, time(8, 0), time(23, 59), 15)
    assert eff_e == time(23, 59)  # 23:50 + 15min würde überlaufen → 23:59-Deckel
```

- [ ] **Step 2: Run → fail**

```bash
docker cp backend/tests/test_work_window_service.py praxiszeit-backend-1:/app/tests/
docker compose exec -T backend pytest tests/test_work_window_service.py -q
```
Expected: FAIL (`ModuleNotFoundError: app.services.work_window_service`).

- [ ] **Step 3: Service implementieren**

Create `backend/app/services/work_window_service.py`:

```python
"""#201: Soll-Arbeitszeit-Fenster — kappt das Ist beim Schreiben.

Pro User je Wochentag (Mo–Fr) ein optionales Fenster [Soll-Beginn, Soll-Ende].
Gestempelte/eingetragene Zeit außerhalb von [Beginn − Puffer, Ende + Puffer]
wird gekappt; der Rohstempel wird separat bewahrt. Opt-in: NULL = keine Kappung.
"""
from datetime import date, time, timedelta, datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting

_WEEKDAY_ATTR = {
    0: ("scheduled_start_monday", "scheduled_end_monday"),
    1: ("scheduled_start_tuesday", "scheduled_end_tuesday"),
    2: ("scheduled_start_wednesday", "scheduled_end_wednesday"),
    3: ("scheduled_start_thursday", "scheduled_end_thursday"),
    4: ("scheduled_start_friday", "scheduled_end_friday"),
}

DEFAULT_GRACE_MINUTES = 15


def get_grace_minutes(db: Session, tenant_id) -> int:
    """work_window_grace_minutes aus system_settings (Default 15, >= 0)."""
    s = db.query(SystemSetting).filter(
        SystemSetting.key == "work_window_grace_minutes",
        SystemSetting.tenant_id == tenant_id,
    ).first()
    if not s:
        return DEFAULT_GRACE_MINUTES
    try:
        return max(0, int(s.value))
    except (TypeError, ValueError):
        return DEFAULT_GRACE_MINUTES


def get_scheduled_window(user, d: date) -> Tuple[Optional[time], Optional[time]]:
    attrs = _WEEKDAY_ATTR.get(d.weekday())
    if attrs is None:  # Wochenende
        return (None, None)
    return (getattr(user, attrs[0], None), getattr(user, attrs[1], None))


def _shift(t: time, minutes: int) -> time:
    """t um minutes verschieben, auf [00:00, 23:59] des Tages begrenzt."""
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)


def clamp(
    user, d: date, start: Optional[time], end: Optional[time], grace_minutes: int,
) -> Tuple[Optional[time], Optional[time], Optional[time], Optional[time]]:
    """Gibt (eff_start, eff_end, raw_start, raw_end) zurück.

    raw_* ist nur gesetzt, wenn die jeweilige Seite tatsächlich gekappt wurde.
    Übersprungen bei track_hours=False (kein Ist relevant).
    """
    if not getattr(user, "track_hours", True):
        return (start, end, None, None)

    soll_start, soll_end = get_scheduled_window(user, d)
    eff_start, eff_end = start, end
    raw_start = raw_end = None

    if soll_start is not None and start is not None:
        floor = _shift(soll_start, -grace_minutes)
        if start < floor:
            eff_start, raw_start = floor, start

    if soll_end is not None and end is not None:
        ceil = _shift(soll_end, grace_minutes)
        if end > ceil:
            eff_end, raw_end = ceil, end

    return (eff_start, eff_end, raw_start, raw_end)
```

- [ ] **Step 4: Run → pass**

```bash
docker cp backend/app/services/work_window_service.py praxiszeit-backend-1:/app/app/services/
docker compose exec -T backend pytest tests/test_work_window_service.py -q
```
Expected: PASS (7 Tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_window_service.py backend/tests/test_work_window_service.py
git commit -m "feat(#201): work_window_service (clamp + grace)"
```

---

## Task 3: Setting `work_window_grace_minutes`

**Files:**
- Modify: `backend/app/routers/admin_settings.py`

- [ ] **Step 1: Whitelist + Validierung ergänzen**

In `admin_settings.py` `_ALLOWED_SETTINGS` den Key aufnehmen:

```python
_ALLOWED_SETTINGS = {
    "vacation_approval_required",
    "holiday_state",
    "break_exception_requires_approval",
    "work_window_grace_minutes",  # #201
} | special_days_service.SETTING_KEYS
```

In `update_setting` (PUT `/settings/{key}`), bei der key-spezifischen Validierung einen int-Check für den neuen Key ergänzen (nach den bestehenden Validierungen, vor dem Speichern):

```python
    if key == "work_window_grace_minutes":
        try:
            if int(body.value) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="work_window_grace_minutes muss eine nicht-negative Zahl sein")
```

- [ ] **Step 2: Test (vorhandenes admin_settings-Testmuster nutzen)**

In `backend/tests/test_endpoints.py` (Klasse zu Admin-Settings; falls keine vorhanden, neue Mini-Klasse) — PUT mit gültigem + ungültigem Wert:

```python
    def test_set_work_window_grace_minutes(self, admin_client):
        ok = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "20"})
        assert ok.status_code == 200, ok.text
        bad = admin_client.put("/api/admin/settings/work_window_grace_minutes", json={"value": "-5"})
        assert bad.status_code == 400
```

- [ ] **Step 3: Run**

```bash
docker cp backend/app/routers/admin_settings.py praxiszeit-backend-1:/app/app/routers/admin_settings.py
docker cp backend/tests/test_endpoints.py praxiszeit-backend-1:/app/tests/test_endpoints.py
docker compose exec -T backend pytest "tests/test_endpoints.py::TestAdminSettings::test_set_work_window_grace_minutes" -q
```
Expected: PASS. (Klassenname an die tatsächliche Test-Datei anpassen.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/admin_settings.py backend/tests/test_endpoints.py
git commit -m "feat(#201): work_window_grace_minutes Setting + Validierung"
```

---

## Task 4: Clamp in `clock_in` (nur Start)

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`clock_in`)
- Test: `backend/tests/test_work_window_integration.py`

- [ ] **Step 1: Failing integration test**

Create `backend/tests/test_work_window_integration.py` mit dem App-/Client-Setup analog `tests/test_break_waiver.py` (FastAPI-Test-App mit `time_entries`-Router, `db`/`employee`/`employee_client`-Fixtures). Erster Test:

```python
def test_clock_in_caps_early_start(db, employee, employee_client, monkeypatch):
    # Montag-Soll-Beginn 08:00, Puffer 15 → Einstempeln 07:00 wird auf 07:45 gekappt.
    employee.scheduled_start_monday = __import__("datetime").time(8, 0)
    db.commit()
    # _now_local auf einen Montag 07:00 fixieren:
    import app.routers.time_entries as te
    monkeypatch.setattr(te, "_now_local", lambda: __import__("datetime").datetime(2026, 6, 1, 7, 0))
    resp = employee_client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code in (200, 201), resp.text
    from app.models import TimeEntry
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == __import__("datetime").time(7, 45)
    assert entry.raw_start_time == __import__("datetime").time(7, 0)
```

(Falls die clock_in-Zeitquelle anders heißt als `_now_local`, im Code prüfen und den `monkeypatch`-Namen anpassen.)

- [ ] **Step 2: Run → fail**

```bash
docker cp backend/tests/test_work_window_integration.py praxiszeit-backend-1:/app/tests/
docker compose exec -T backend pytest tests/test_work_window_integration.py::test_clock_in_caps_early_start -q
```
Expected: FAIL (start_time 07:00, raw_start_time None).

- [ ] **Step 3: clock_in anpassen**

In `clock_in` (`time_entries.py`), wo `TimeEntry(... start_time=now.time()...)` gebaut wird: vorher den Start kappen.

```python
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    start_t = now.time().replace(second=0, microsecond=0)
    eff_start, _eff_end, raw_start, _raw_end = work_window_service.clamp(
        current_user, now.date(), start_t, None, grace,
    )
```
und im `TimeEntry(...)`-Konstruktor `start_time=eff_start, raw_start_time=raw_start` setzen (statt `start_time=now.time()...`).

- [ ] **Step 4: Run → pass**

```bash
docker cp backend/app/routers/time_entries.py praxiszeit-backend-1:/app/app/routers/time_entries.py
docker compose exec -T backend pytest tests/test_work_window_integration.py::test_clock_in_caps_early_start -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/time_entries.py backend/tests/test_work_window_integration.py
git commit -m "feat(#201): clock_in kappt Frühstart"
```

---

## Task 5: Clamp in `clock_out` (Ende)

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`clock_out`)
- Test: `backend/tests/test_work_window_integration.py`

- [ ] **Step 1: Failing test**

```python
def test_clock_out_caps_late_end(db, employee, employee_client, monkeypatch):
    import datetime as dt
    employee.scheduled_end_monday = dt.time(17, 0)
    db.commit()
    import app.routers.time_entries as te
    # offenen Eintrag um 08:00 anlegen
    from app.models import TimeEntry
    db.add(TimeEntry(user_id=employee.id, tenant_id=employee.tenant_id,
                     date=dt.date(2026, 6, 1), start_time=dt.time(8, 0), end_time=None, break_minutes=0))
    db.commit()
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 18, 30))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.end_time == dt.time(17, 15)   # 17:00 + 15min
    assert entry.raw_end_time == dt.time(18, 30)
```

- [ ] **Step 2: Run → fail**

```bash
docker compose exec -T backend pytest tests/test_work_window_integration.py::test_clock_out_caps_late_end -q
```
Expected: FAIL (end_time 18:30, raw_end_time None).

- [ ] **Step 3: clock_out anpassen**

In `clock_out`, wo das offene Entry mit `end_time = now.time()` geschlossen wird: vorher kappen.

```python
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    end_t = now.time().replace(second=0, microsecond=0)
    _eff_start, eff_end, _raw_start, raw_end = work_window_service.clamp(
        current_user, entry.date, entry.start_time, end_t, grace,
    )
    entry.end_time = eff_end
    entry.raw_end_time = raw_end
```
(`entry` = das offene Entry; vor dem bestehenden `db.commit()`.)

- [ ] **Step 4: Run → pass**

```bash
docker cp backend/app/routers/time_entries.py praxiszeit-backend-1:/app/app/routers/time_entries.py
docker compose exec -T backend pytest tests/test_work_window_integration.py -q
```
Expected: PASS (beide Integrationstests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/time_entries.py backend/tests/test_work_window_integration.py
git commit -m "feat(#201): clock_out kappt spätes Ende"
```

---

## Task 6: Clamp in `create_time_entry` + `update_time_entry`

**Files:**
- Modify: `backend/app/routers/time_entries.py`
- Test: `backend/tests/test_work_window_integration.py`

- [ ] **Step 1: Failing test**

```python
def test_manual_create_caps_both_ends(db, employee, employee_client):
    import datetime as dt
    employee.scheduled_start_monday = dt.time(8, 0)
    employee.scheduled_end_monday = dt.time(17, 0)
    db.commit()
    resp = employee_client.post("/api/time-entries", json={
        "date": "2026-06-01", "start_time": "07:00", "end_time": "18:00", "break_minutes": 30,
    })
    assert resp.status_code == 201, resp.text
    from app.models import TimeEntry
    entry = db.query(TimeEntry).filter(TimeEntry.user_id == employee.id).one()
    assert entry.start_time == dt.time(7, 45) and entry.raw_start_time == dt.time(7, 0)
    assert entry.end_time == dt.time(17, 15) and entry.raw_end_time == dt.time(18, 0)
```

- [ ] **Step 2: Run → fail**

```bash
docker compose exec -T backend pytest tests/test_work_window_integration.py::test_manual_create_caps_both_ends -q
```
Expected: FAIL.

- [ ] **Step 3: create + update anpassen**

In `create_time_entry`: nach Validierung, vor dem `TimeEntry(...)`-Bau, beide Enden kappen (analog Task 4/5) und `start_time/end_time/raw_start_time/raw_end_time` aus dem Clamp setzen. Identisch in `update_time_entry` (wo Start/Ende des bestehenden Entries gesetzt werden) — `raw_*` bei jedem Update neu berechnen (auch auf `None` zurücksetzen, wenn nicht mehr gekappt).

```python
    from app.services import work_window_service
    grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
    eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
        current_user, entry_data.date, entry_data.start_time, entry_data.end_time, grace,
    )
    # … TimeEntry(..., start_time=eff_start, end_time=eff_end,
    #              raw_start_time=raw_start, raw_end_time=raw_end)
```

⚠️ Reihenfolge zur ArbZG-§4-Pausenprüfung: Die Pausen-/§3-Prüfung soll auf der **gekappten** (angerechneten) Zeit laufen → Clamp **vor** `validate_daily_break`/`_calculate_daily_net_hours` durchführen und die gekappten Werte dort verwenden.

- [ ] **Step 4: Run → pass**

```bash
docker cp backend/app/routers/time_entries.py praxiszeit-backend-1:/app/app/routers/time_entries.py
docker compose exec -T backend pytest tests/test_work_window_integration.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/time_entries.py backend/tests/test_work_window_integration.py
git commit -m "feat(#201): manueller Eintrag (create/update) kappt Soll-Fenster"
```

---

## Task 7: Clamp in `admin_time_entries` (create + update)

**Files:**
- Modify: `backend/app/routers/admin_time_entries.py`
- Test: `backend/tests/test_work_window_integration.py`

- [ ] **Step 1: Failing test** — analog Task 6, aber über `admin_client` und `POST /api/admin/users/{id}/time-entries` bzw. `PUT /api/admin/time-entries/{id}`; `affected_user.scheduled_*` setzen. Assert gekappte `start_time/end_time` + `raw_*`.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3:** In `admin_create_time_entry` und `admin_update_time_entry` den Clamp **vor** der §4/§3-Prüfung einsetzen (User ist hier `user`/`affected_user`, NICHT `current_user`!), die gekappten Werte für die Prüfung verwenden und am Entry `start_time/end_time/raw_start_time/raw_end_time` setzen:

```python
from app.services import work_window_service
grace = work_window_service.get_grace_minutes(db, current_user.tenant_id)
eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
    user, update_date, update_start_time, update_end_time, grace,  # create: entry_data.date/start/end + `user`
)
# danach validate_daily_break/_calculate_daily_net_hours mit eff_start/eff_end;
# TimeEntry(..., start_time=eff_start, end_time=eff_end, raw_start_time=raw_start, raw_end_time=raw_end)
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** `feat(#201): Admin-Eintrag kappt Soll-Fenster`.

---

## Task 8: Clamp im XLS-Import

**Files:**
- Modify: `backend/app/services/xls_import_service.py`
- Test: `backend/tests/test_xls_import_service.py` (vorhandenes Setup nutzen)

- [ ] **Step 1: Failing test** — Import-Zeile mit Start/Ende außerhalb des Soll-Fensters eines Users → erzeugter Eintrag hat gekappte Zeiten + `raw_*`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3:** An der Stelle, wo `TimeEntry` aus der Import-Zeile gebaut wird, vor dem Konstruktor kappen (grace einmal pro Import laden):

```python
from app.services import work_window_service
grace = work_window_service.get_grace_minutes(db, user.tenant_id)  # einmal vor der Zeilen-Schleife
eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(user, row_date, start, end, grace)
# TimeEntry(..., start_time=eff_start, end_time=eff_end, raw_start_time=raw_start, raw_end_time=raw_end)
```
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(#201): XLS-Import kappt Soll-Fenster`.

---

## Task 9: Clamp bei Änderungsantrag-Genehmigung

**Files:**
- Modify: `backend/app/routers/admin_change_requests.py`
- Test: `backend/tests/test_work_window_integration.py`

- [ ] **Step 1: Failing test** — CR (create/update) mit proposed-Zeiten außerhalb des Fensters → nach `approve` hat der materialisierte `TimeEntry` gekappte Zeiten + `raw_*`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3:** An JEDER Stelle, wo aus `cr.proposed_*` ein `TimeEntry` materialisiert wird (mehrere — per `grep "proposed_start_time" admin_change_requests.py` alle finden), vor dem Konstruktor kappen (`cr_user` = der MA des CR, z. B. via `cr.user_id`):

```python
from app.services import work_window_service
grace = work_window_service.get_grace_minutes(db, cr.tenant_id)
eff_start, eff_end, raw_start, raw_end = work_window_service.clamp(
    cr_user, cr.proposed_date, cr.proposed_start_time, cr.proposed_end_time, grace,
)
# TimeEntry(..., start_time=eff_start, end_time=eff_end, raw_start_time=raw_start, raw_end_time=raw_end)
```
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(#201): CR-Genehmigung kappt Soll-Fenster`.

---

## Task 10: Schemas + User-CRUD für Soll-Zeiten

**Files:**
- Modify: `backend/app/schemas/user.py` (`UserBase`, `UserUpdate`, `UserListResponse`)
- Modify: `backend/app/routers/admin_users.py` (`create_user`)
- Modify: `backend/app/schemas/time_entry.py` (Response: `raw_start_time`/`raw_end_time`)
- Test: `backend/tests/test_endpoints.py`

- [ ] **Step 1: Failing test** — `POST /api/admin/users` mit `scheduled_start_monday: "08:00"` etc. persistiert die Werte; `GET /api/admin/users` liefert sie zurück; `PUT` aktualisiert sie. Außerdem: TimeEntry-Response enthält `raw_start_time`/`raw_end_time`.

```python
    def test_user_scheduled_window_roundtrip(self, admin_client, _db_session):
        resp = admin_client.post("/api/admin/users", json={
            "username": "win", "first_name": "Win", "last_name": "Dow",
            "weekly_hours": 40.0, "vacation_days": 30, "work_days_per_week": 5,
            "password": "WindowPass2025!",
            "scheduled_start_monday": "08:00", "scheduled_end_monday": "17:00",
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["scheduled_start_monday"] == "08:00:00"
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3:** In `schemas/user.py`:
  - `UserBase`: 10 Felder `scheduled_start_monday: Optional[time] = None` … (import `time` from datetime ist vorhanden).
  - `UserUpdate`: dieselben 10 als `Optional[time] = None`.
  - `UserListResponse`: dieselben 10 (damit das Admin-Frontend sie vorbefüllen kann).
  In `admin_users.py` `create_user`: die 10 Felder am `User(...)` setzen (`scheduled_start_monday=user_data.scheduled_start_monday`, …). `update_user` nutzt `model_dump(exclude_unset=True)` + `setattr` → automatisch abgedeckt.
  In `schemas/time_entry.py` Response-Modell: `raw_start_time: Optional[time] = None`, `raw_end_time: Optional[time] = None`.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** `feat(#201): Soll-Zeit-Felder in User-Schemas + raw_* in TimeEntry-Response`.

---

## Task 11: Frontend — UserForm Soll-Zeiten je Wochentag

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx`
- Modify: `frontend/src/pages/admin/Users.tsx` (`User`-Interface um die 10 Felder ergänzen, Typ `string | null`)

- [ ] **Step 1: Interface + State**

In `UserForm.tsx` das lokale `User`-Interface + `formData` um die 10 Felder erweitern (`scheduled_start_monday: string` … Default `''`), in `useEffect(editUser)` aus `editUser.scheduled_*` vorbefüllen (`?.substring(0,5) || ''`). In `Users.tsx` das `User`-Interface um `scheduled_start_monday: string | null` … ergänzen (sonst tsc-Fehler beim `editUser`-Prop).

- [ ] **Step 2: UI**

Beim Tagesplan-Bereich (dort wo `hours_monday..` editiert werden) je Wochentag zwei `<input type="time">` „Soll-Beginn"/„Soll-Ende" (optional). Werte leer → beim Submit als `null` senden.

- [ ] **Step 3: Payload**

Im `handleSubmit`-Payload die 10 Felder mitsenden: leere Strings → `null` (`formData.scheduled_start_monday || null`).

- [ ] **Step 4: Verify**

```bash
cd frontend && docker run --rm -v "$(pwd)":/app -w /app node:20-alpine sh -c "npx tsc --noEmit && npm run build >/dev/null 2>&1 && echo OK"
```
Expected: `OK`. Danach manuell: User mit Soll-Mo 08:00–17:00 anlegen, in der Liste erneut öffnen → Werte vorbefüllt.

- [ ] **Step 5: Commit** `feat(#201): UserForm Soll-Zeiten je Wochentag`.

---

## Task 12: Frontend — Settings Puffer

**Files:**
- Modify: `frontend/src/pages/admin/Settings.tsx`

- [ ] **Step 1:** Number-Input „Puffer für Soll-Fenster (Min.)" laden via `GET /api/admin/settings` (Wert `work_window_grace_minutes`, Default 15) und via `PUT /api/admin/settings/work_window_grace_minutes` speichern (Muster wie `vacation_approval_required`/Sondertage in derselben Datei).
- [ ] **Step 2: Verify** tsc + build `OK`; manuell Wert setzen → bleibt nach Reload.
- [ ] **Step 3: Commit** `feat(#201): Settings — Soll-Fenster-Puffer`.

---

## Task 13: Frontend — „angerechnet"-Hinweis bei gekappten Einträgen

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`, `frontend/src/pages/TimeTracking.tsx`

- [ ] **Step 1:** TimeEntry-Typ um `raw_start_time?: string | null`, `raw_end_time?: string | null` erweitern. Wo Einträge gelistet werden: bei gesetztem `raw_start_time`/`raw_end_time` ein dezenter Hinweis „gestempelt {raw} · angerechnet {eff}".
- [ ] **Step 2: Verify** tsc + build `OK`.
- [ ] **Step 3: Commit** `feat(#201): Hinweis auf gekappte Anrechnung im Eintrag`.

---

## Task 14: Frontend — StampWidget Frühstart-Hinweis

**Files:**
- Modify: `frontend/src/components/StampWidget.tsx`

- [ ] **Step 1:** Die Soll-Startzeit des aktuellen Tages ist im Frontend nicht zwingend vorhanden → einfachste Variante: nach dem Einstempeln zeigt die clock_in-Response (falls Backend eine `warnings`-Meldung `EARLY_START` ergänzt) den Hinweis via `showArbzgWarnings`. **Optional/aufschiebbar.** Falls umgesetzt: in `clock_in` (Backend) bei gesetztem `raw_start_time` `warnings.append("EARLY_START: angerechnet ab HH:MM")` und Mapping in `frontend/src/utils/arbzgWarnings.ts` ergänzen.
- [ ] **Step 2: Verify** tsc + build `OK`.
- [ ] **Step 3: Commit** `feat(#201): Frühstart-Hinweis beim Einstempeln` (oder als Folge-Issue zurückstellen).

---

## Task 15: Doku

**Files:**
- Modify: `CLAUDE.md`, `docs/BACKEND-ARCHITEKTUR.md`, `docs/handbuch/HANDBUCH-ADMIN.md`, `frontend/src/components/DocViewer.tsx`

- [ ] **Step 1:** CLAUDE.md (Kritische Regeln): neue Regel — „Soll-Arbeitszeit-Fenster (#201): `work_window_service.clamp` an allen Schreibpfaden; `raw_*` bewahrt Rohstempel; `track_hours=False` übersprungen; net_hours rechnet mit gekappter Zeit".
- [ ] **Step 2:** BACKEND-ARCHITEKTUR: Abschnitt „Arbeitszeit-Fenster" (Datenmodell, clamp, Schreibpfade).
- [ ] **Step 3:** HANDBUCH-ADMIN + DocViewer (synchron, CLAUDE.md-Regel): Soll-Zeiten je Wochentag + Puffer + „angerechnet"-Hinweis erklären; rechtlicher Hinweis (Rohstempel dokumentiert).
- [ ] **Step 4: Commit** `docs(#201): Soll-Arbeitszeit-Fenster dokumentieren`.

---

## Abschluss

- [ ] **Volle Suite (stabile Reihenfolge):**

```bash
docker compose exec -T backend pytest tests/ --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py -q -p no:randomly
cd frontend && docker run --rm -v "$(pwd)":/app -w /app node:20-alpine sh -c "npx tsc --noEmit && npx vitest run && npm run build"
```
Expected: alle grün, tsc/vitest/build sauber.

- [ ] **PR** gegen master, `Closes #201`, mit Verifikations-Evidenz. Hinweis: das `-docker`/Native-Release zieht das Feature über die normale Versions-/Update-Auslieferung (kein manueller Deploy).

---

## Hinweise für die Umsetzung

- **Backend-Container ist gebaut** (kein Host-Volume): nach jedem Edit `docker cp <host-file> praxiszeit-backend-1:/app/<path>` vor `pytest`. Für Migrationen `alembic upgrade head` im Container.
- **`pytest tests/` ist reihenfolgeabhängig** (shared-SQLite-Pollution) → mit `-p no:randomly` oder gezielten Dateien testen; Einzeldateien sind in Isolation verlässlich.
- **§4/§3-Prüfung auf gekappter Zeit:** in create/admin/CR den Clamp VOR `validate_daily_break`/`_calculate_daily_net_hours` ausführen und die gekappten Werte verwenden (sonst Inkonsistenz Anrechnung ↔ Pausenprüfung).
- **Alle 6 Schreibpfade** müssen den Helper nutzen (Tasks 4–9). Eine vergessene Stelle = Lücke.
- **Migration gegen Prod-DB-Kopie testen**, keine Bestandsdaten ändern (alles NULL → kein Verhaltenswechsel).
