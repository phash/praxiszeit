# Minijob-Compliance (Mindestlohn + § 2 Abs. 2 MiLoG) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Minijob-/Arbeitszeitkonto-MA gesetzeskonform begleiten — aktuellen Mindestlohn anzeigen und die § 2 Abs. 2 MiLoG-Grenzen (50 % Konto-Stunden/Monat + 12-Monats-Ausgleichsfrist) als weiche Warnungen prüfen, opt-in pro MA, ohne Lohndaten.

**Architecture:** Neues Opt-in-Flag `User.milog_working_time_account`. Mindestlohn als datumsabhängige Code-Konstante (`app/core/minimum_wage.py`), ausgeliefert über `/api/system/info`. Prüf-Logik in `app/services/milog_service.py` (vereinbarte Monatszeit = `weekly_hours × 13/3`, 50-%-Check gegen `get_monthly_balance`, FIFO-Aging über die Monats-Deltas von `get_overtime_history_detailed`). Warnungen über das bestehende `warnings`-Muster (wie ArbZG) beim Ausstempeln + im Monatsreport/Überstundenkonto. Kein Eingriff ins eingefrorene Calc-Modell.

**Tech Stack:** FastAPI (Python 3.12) + SQLAlchemy + Alembic + PostgreSQL 16, React 18 + TS + Tailwind, pytest / Vitest / Playwright.

**Spec:** `docs/superpowers/specs/2026-07-08-minijob-milog-design.md`

## Global Constraints

- **Calc-Modell eingefroren** — nur LESEN (`get_monthly_balance`, `get_overtime_history_detailed`, `get_weekly_hours_for_date`); keine Änderung der Berechnung.
- **Weiche Warnungen, NIE blockierend** (wie ArbZG). Nur für MA mit `milog_working_time_account=True`.
- **Keine Lohndaten** (einfache Variante). Vereinbarte Monatszeit = `weekly_hours × 13/3`.
- **Mindestlohn NIE raten** — nur die gesetzlich beschlossenen Stufen in `minimum_wage.py`; neue Stufe ergänzen, wenn beschlossen.
- **`/api/system/info` darf NIE 500** — `minimum_wage` ist rein statisch (kein DB-Zugriff), aber defensiv halten.
- **Kein `date.today()`** — `timezone_service.today_local()` (Europe/Berlin), reinreichen für Testbarkeit.
- **Alembic Rev-ID ≤ 32 Zeichen**, Migration auf Host + committen VOR Container-Rebuild, up UND down.
- **Backend-Container gebaut, kein Volume:** nach Edits `docker compose cp backend/app backend:/app/` VOR pytest; **live-Server nach Enum/Route-Änderung neu starten** (`docker compose restart backend`) — cp reloadet uvicorn nicht.
- **Vitest:** node_modules root-owned → `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npx vitest run … --pool=threads"`.
- **F-026/Multi-Tenant:** `User` ist tenant-scoped; das neue Flag braucht keine Extra-Policy, aber `create_user`-Persistenz nicht vergessen (Muster wie #376 `child_sick_days_per_year`).

---

## File Structure

**Backend:** `app/core/minimum_wage.py` (neu) · `app/services/milog_service.py` (neu) · `app/models/user.py` (+Flag) · `app/schemas/user.py` (Base/Update/Response) · `app/routers/admin_users.py` (create_user + users-overview) · `app/schemas/reports.py` (AdminUserOverview + milog_warnings) · `app/main.py` (system_info → minimum_wage) · `app/routers/time_entries.py` (clock_out) · `alembic/versions/…` (Migration).

**Frontend:** `src/stores/systemStore.ts` · `src/utils/arbzgWarnings.ts` · `src/types/user.ts` · `src/pages/admin/users/UserForm.tsx` · `src/pages/admin/Settings.tsx` · die Admin-Übersicht/Überstundenkonto-Komponente (Badges) · `src/components/DocViewer.tsx`.

**Docs:** `docs/handbuch/HANDBUCH-ADMIN.md` · `CLAUDE.md`.

---

## Task 1: Mindestlohn-Modul

**Files:**
- Create: `backend/app/core/minimum_wage.py`
- Test: `backend/tests/test_minimum_wage.py`

**Interfaces:**
- Produces: `minimum_wage_for(d: date) -> Decimal`, `minimum_wage_info(today: date) -> dict` (`{current: float, since: str, next: {value,from}|None}`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_minimum_wage.py
from datetime import date
from decimal import Decimal
from app.core import minimum_wage as mw


def test_minimum_wage_for_boundaries():
    assert mw.minimum_wage_for(date(2025, 12, 31)) == Decimal("12.82")
    assert mw.minimum_wage_for(date(2026, 1, 1)) == Decimal("13.90")
    assert mw.minimum_wage_for(date(2026, 7, 8)) == Decimal("13.90")
    assert mw.minimum_wage_for(date(2027, 1, 1)) == Decimal("14.60")


def test_minimum_wage_info_current_and_next():
    info = mw.minimum_wage_info(date(2026, 7, 8))
    assert info["current"] == 13.90
    assert info["since"] == "2026-01-01"
    assert info["next"] == {"value": 14.60, "from": "2027-01-01"}
    # kein Next mehr, wenn letzte Stufe erreicht
    assert mw.minimum_wage_info(date(2027, 6, 1))["next"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_minimum_wage.py -v </dev/null`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# backend/app/core/minimum_wage.py
"""#377 Gesetzlicher Mindestlohn (§ 1 MiLoG) als datumsabhängige Konstante.

Quelle: Mindestlohnkommission / BMAS. NEUE Stufe VORNE/chronologisch ergänzen,
sobald beschlossen — Werte NIE raten. Rein statisch (kein DB/Netz)."""
from datetime import date
from decimal import Decimal

# (Wirksam-ab, €/h) aufsteigend sortiert.
_MINIMUM_WAGE_STEPS = [
    (date(2025, 1, 1), Decimal("12.82")),
    (date(2026, 1, 1), Decimal("13.90")),
    (date(2027, 1, 1), Decimal("14.60")),
]


def minimum_wage_for(d: date) -> Decimal:
    """Gültiger gesetzlicher Mindestlohn (€/h) zum Datum d."""
    applicable = _MINIMUM_WAGE_STEPS[0][1]
    for eff, val in _MINIMUM_WAGE_STEPS:
        if d >= eff:
            applicable = val
    return applicable


def minimum_wage_info(today: date) -> dict:
    """{current, since, next|None} für die Anzeige."""
    current, since = _MINIMUM_WAGE_STEPS[0][1], _MINIMUM_WAGE_STEPS[0][0]
    nxt = None
    for eff, val in _MINIMUM_WAGE_STEPS:
        if today >= eff:
            current, since = val, eff
        elif nxt is None:
            nxt = {"value": float(val), "from": eff.isoformat()}
    return {"current": float(current), "since": since.isoformat(), "next": nxt}
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && docker compose exec -T backend pytest tests/test_minimum_wage.py -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/minimum_wage.py backend/tests/test_minimum_wage.py
git commit -m "feat(#377): minimum wage constant (§1 MiLoG, date-based)"
```

---

## Task 2: `/api/system/info` liefert `minimum_wage`

**Files:**
- Modify: `backend/app/main.py` (`system_info`)
- Test: `backend/tests/test_minimum_wage.py`

**Interfaces:**
- Consumes: `minimum_wage.minimum_wage_info`, `timezone_service.today_local`
- Produces: `/api/system/info` JSON enthält `minimum_wage: {current, since, next}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_minimum_wage.py
def test_system_info_exposes_minimum_wage():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    body = c.get("/api/system/info").json()
    assert "minimum_wage" in body
    assert body["minimum_wage"]["current"] > 0
    assert "since" in body["minimum_wage"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_minimum_wage.py::test_system_info_exposes_minimum_wage -v </dev/null`
Expected: FAIL — key missing.

- [ ] **Step 3: Implement**

In `backend/app/main.py`, im `system_info()`-Return-Dict (ab Zeile ~750) ergänzen. Import oben: `from app.core import minimum_wage as _mw` und `from app.services.timezone_service import today_local` (falls nicht vorhanden). Ins Return-Dict:

```python
        "minimum_wage": _mw.minimum_wage_info(today_local()),
```

> Exaktes Return-Dict in Task-Zeit lesen (`main.py:750`) und den Key konsistent einfügen.

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_minimum_wage.py::test_system_info_exposes_minimum_wage -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_minimum_wage.py
git commit -m "feat(#377): expose minimum_wage on /api/system/info"
```

---

## Task 3: User-Flag `milog_working_time_account` (Model + Migration + Schema + create_user)

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/schemas/user.py`, `backend/app/routers/admin_users.py`
- Create: `backend/alembic/versions/<rev>_milog_flag.py`
- Test: `backend/tests/test_milog.py` (neu)

**Interfaces:**
- Produces: `User.milog_working_time_account` (bool, default False); `UserBase/UserUpdate.milog_working_time_account: bool|Optional[bool]`; persistiert in create_user + update_user

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_milog.py — Harness wie backend/tests/test_child_sick.py
# (lokales _app() mit admin.router, dependency_overrides, /api-Pfade, admin+_user Fixtures).
def test_milog_flag_persisted_on_create_and_update(db, admin, default_tenant):
    client = _client_as(db, admin, admin)
    uid = client.post(USERS, json={
        "username": "mj", "first_name": "M", "last_name": "J", "password": "E2ePass1234!",
        "role": "employee", "weekly_hours": 7.62, "vacation_days": 30, "work_days_per_week": 5,
        "milog_working_time_account": True,
    }).json()["user"]["id"]
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is True
    client.put(f"{USERS}/{uid}", json={"milog_working_time_account": False})
    assert client.get(f"{USERS}/{uid}").json()["milog_working_time_account"] is False
    app.dependency_overrides.clear()
```

> `USERS="/api/admin/users"`. Harness-Boilerplate 1:1 aus `test_child_sick.py` übernehmen (`_app()` mit `admin.router`, `_client_as`, `admin`, `_user`, `default_tenant`).

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_milog.py::test_milog_flag_persisted_on_create_and_update -v </dev/null`
Expected: FAIL — unbekanntes Feld / Spalte fehlt.

- [ ] **Step 3: Implement**

`app/models/user.py` (nach `is_night_worker`):

```python
    milog_working_time_account = Column(Boolean, default=False, nullable=False, server_default='false')  # #377 §2 Abs.2 MiLoG: Arbeitszeitkonto-Prüfungen
```

`app/schemas/user.py` — `UserBase` (nach `is_night_worker`):

```python
    milog_working_time_account: bool = False  # #377 §2 Abs.2 MiLoG
```

`UserUpdate` (nach `is_night_worker`):

```python
    milog_working_time_account: Optional[bool] = None  # #377
```

`app/routers/admin_users.py` — `create_user` `new_user = User(...)` (bei `is_night_worker=`):

```python
        milog_working_time_account=user_data.milog_working_time_account,  # #377
```

Und im `update_user` (falls dort ein Whitelist-/setattr-Muster existiert, das neue Feld aufnehmen; sonst analog zu `is_night_worker` explizit setzen). In Task-Zeit `update_user` prüfen.

Migration `2026_07_08_HHMM-062_milog_flag.py` (down_revision = aktueller Head — in Task-Zeit `revision =` der neuesten versions-Datei lesen; nach #376 ist das `061_child_sick_fields`):

```python
revision = "062_milog_flag"
down_revision = "061_child_sick_fields"

def upgrade():
    op.add_column("users", sa.Column("milog_working_time_account", sa.Boolean(),
                  nullable=False, server_default=sa.text("false")))

def downgrade():
    op.drop_column("users", "milog_working_time_account")
```

- [ ] **Step 4: Run migration + test**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/alembic backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T backend python -c "from alembic.config import main; main(['upgrade','head'])" </dev/null
docker compose exec -T backend pytest tests/test_milog.py::test_milog_flag_persisted_on_create_and_update -v </dev/null
```
Expected: Migration ok, PASS. Danach up/down/up prüfen (downgrade -1 / upgrade head).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py backend/app/schemas/user.py backend/app/routers/admin_users.py backend/alembic/versions/2026_07_08_HHMM-062_milog_flag.py backend/tests/test_milog.py
git commit -m "feat(#377): milog_working_time_account opt-in flag (migration 062)"
```

---

## Task 4: `milog_service` — vereinbarte Monatszeit + 50-%-Check

**Files:**
- Create: `backend/app/services/milog_service.py`
- Test: `backend/tests/test_milog.py`

**Interfaces:**
- Consumes: `calculation_service.get_weekly_hours_for_date`, `calculation_service.get_monthly_balance`
- Produces:
  - `agreed_monthly_hours(db, user, ref_date) -> Decimal`
  - `account_hours_in_month(db, user, year, month, up_to_date=None) -> Decimal`
  - `milog_50_check(db, user, year, month, up_to_date=None) -> dict|None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_milog.py
from datetime import date
from decimal import Decimal
from app.services import milog_service


def test_agreed_monthly_hours_from_weekly(db, employee):
    employee.weekly_hours = Decimal("7.62")  # ~33 h/Monat
    db.commit()
    got = milog_service.agreed_monthly_hours(db, employee, date(2026, 3, 1))
    assert Decimal("32.5") < got < Decimal("33.5")


def test_milog_50_check_only_when_flag_and_over(db, employee, monkeypatch):
    employee.weekly_hours = Decimal("7.62"); employee.milog_working_time_account = False
    db.commit()
    # Flag aus → None, egal wie hoch
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_balance",
                        lambda *a, **k: Decimal("99"))
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
    # Flag an, Konto-Plus 99h > 16,5h-Cap → dict
    employee.milog_working_time_account = True; db.commit()
    res = milog_service.milog_50_check(db, employee, 2026, 3)
    assert res is not None and res["cap"] < res["account_hours"]
    # Flag an, unter Cap → None
    monkeypatch.setattr(milog_service.calculation_service, "get_monthly_balance",
                        lambda *a, **k: Decimal("2"))
    assert milog_service.milog_50_check(db, employee, 2026, 3) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_milog.py -k "agreed or 50_check" -v </dev/null`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# backend/app/services/milog_service.py
"""#377 § 2 Abs. 2 MiLoG: Arbeitszeitkonto-Prüfungen (50 % + 12-Monats-Ausgleich).

Reine LESE-Schicht über calculation_service. Vereinbarte Monatszeit ohne
Baustein 2 aus den Wochenstunden abgeleitet (× 13/3). Weiche Warnungen — nichts
blockiert. Alle Funktionen liefern None, wenn das Opt-in-Flag aus ist."""
from datetime import date
from decimal import Decimal

from app.services import calculation_service

AGREED_MONTHLY_FACTOR = Decimal(13) / Decimal(3)  # 52 Wochen / 12 Monate


def agreed_monthly_hours(db, user, ref_date: date) -> Decimal:
    weekly = calculation_service.get_weekly_hours_for_date(db, user, ref_date)
    return (Decimal(str(weekly)) * AGREED_MONTHLY_FACTOR)


def account_hours_in_month(db, user, year: int, month: int, up_to_date: date = None) -> Decimal:
    bal = calculation_service.get_monthly_balance(db, user, year, month, up_to_date=up_to_date)
    bal = Decimal(str(bal))
    return bal if bal > 0 else Decimal("0")


def milog_50_check(db, user, year: int, month: int, up_to_date: date = None):
    """None, wenn Flag aus oder Konto-Plusstunden ≤ 50 % der vereinbarten
    Monatszeit. Sonst {account_hours, cap, agreed_monthly} (floats)."""
    if not user.milog_working_time_account:
        return None
    agreed = agreed_monthly_hours(db, user, date(year, month, 1))
    cap = agreed / 2
    account = account_hours_in_month(db, user, year, month, up_to_date=up_to_date)
    if account > cap:
        return {"account_hours": float(account), "cap": float(cap), "agreed_monthly": float(agreed)}
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_milog.py -k "agreed or 50_check" -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/milog_service.py backend/tests/test_milog.py
git commit -m "feat(#377): milog_service agreed_monthly_hours + 50% check"
```

---

## Task 5: `milog_service.settlement_aging` (12-Monats-FIFO)

**Files:**
- Modify: `backend/app/services/milog_service.py`
- Test: `backend/tests/test_milog.py`

**Interfaces:**
- Consumes: `calculation_service.get_overtime_history_detailed` (`{(y,m): MonthlyOvertime(target, actual, cumulative)}`)
- Produces: `settlement_aging(db, user, as_of) -> dict|None` (`{oldest_year, oldest_month, age_months, hours, overdue, due_soon}`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_milog.py
class _MO:
    def __init__(self, target, actual):
        self.target = Decimal(str(target)); self.actual = Decimal(str(actual))
        self.cumulative = Decimal("0")


def test_settlement_aging_fifo_and_overdue(db, employee, monkeypatch):
    employee.milog_working_time_account = True; db.commit()
    # +10h in 2025-01, dann -4h in 2025-06 (verbraucht Teil), Rest 6h altert
    hist = {(2025, 1): _MO(0, 10), (2025, 6): _MO(4, 0)}
    monkeypatch.setattr(milog_service.calculation_service,
                        "get_overtime_history_detailed", lambda *a, **k: hist)
    res = milog_service.settlement_aging(db, employee, date(2026, 3, 1))
    assert res["oldest_year"] == 2025 and res["oldest_month"] == 1
    assert abs(res["hours"] - 6.0) < 0.01
    assert res["age_months"] == 14 and res["overdue"] is True
    # Flag aus → None
    employee.milog_working_time_account = False; db.commit()
    assert milog_service.settlement_aging(db, employee, date(2026, 3, 1)) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_milog.py -k settlement -v </dev/null`
Expected: FAIL — attribute missing.

- [ ] **Step 3: Implement** (an `milog_service.py` anhängen)

```python
def settlement_aging(db, user, as_of: date):
    """FIFO über die Monats-Deltas (actual − target) des Kontos: Plus =
    Einzahlung (monatsstamped), Minus = Ausgleich (verbraucht älteste zuerst).
    Liefert den ältesten offenen Posten + Alter. None, wenn Flag aus / kein
    offener Posten."""
    if not user.milog_working_time_account:
        return None
    detailed = calculation_service.get_overtime_history_detailed(
        db, user, as_of.year, as_of.month
    )
    deposits = []  # [[year, month, remaining]]
    for (y, m) in sorted(detailed.keys()):
        mo = detailed[(y, m)]
        delta = Decimal(str(mo.actual)) - Decimal(str(mo.target))
        if delta > 0:
            deposits.append([y, m, delta])
        elif delta < 0:
            owe = -delta
            while owe > 0 and deposits:
                if deposits[0][2] <= owe:
                    owe -= deposits[0][2]; deposits.pop(0)
                else:
                    deposits[0][2] -= owe; owe = Decimal("0")
    if not deposits:
        return None
    oy, om, rem = deposits[0]
    age = (as_of.year - oy) * 12 + (as_of.month - om)
    return {"oldest_year": oy, "oldest_month": om, "age_months": age,
            "hours": float(rem), "overdue": age >= 12, "due_soon": 10 <= age < 12}
```

> Reales `MonthlyOvertime`-Attribut in Task-Zeit prüfen (`calculation_service.py:681`, `.target`/`.actual`); Rückgabe ist ein Dict `{(y,m): MonthlyOvertime}`.

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_milog.py -k settlement -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/milog_service.py backend/tests/test_milog.py
git commit -m "feat(#377): milog_service settlement_aging (12-month FIFO)"
```

---

## Task 6: `clock_out` → `MILOG_ACCOUNT_50` (month-to-date)

**Files:**
- Modify: `backend/app/routers/time_entries.py` (`clock_out`)
- Test: `backend/tests/test_milog.py`

**Interfaces:**
- Consumes: `milog_service.milog_50_check`, `today_local`
- Produces: `clock_out`-Response-`warnings` enthält `MILOG_ACCOUNT_50: …` nur bei Flag + Überschreitung

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_milog.py — nutzt einen _app() mit time_entries.router + clock-in/out.
# Einfachste robuste Form: milog_service.milog_50_check monkeypatchen, damit der
# Test unabhängig vom echten Monatssaldo ist, und prüfen, dass clock_out den Code
# NUR bei Flag durchreicht.
def test_clock_out_emits_milog_account_50(db, employee, monkeypatch):
    # ... employee einloggen, einstempeln, milog_50_check → dict patchen,
    # ausstempeln, response.warnings enthält "MILOG_ACCOUNT_50".
    # Flag aus → Code NICHT enthalten.
    ...
```

> Konkreten clock-in/out-Testaufbau aus vorhandenen `time_entries`-Tests übernehmen (`tests/test_time_entries*.py` / `test_endpoints.py`). `milog_service.milog_50_check` patchen (Rückgabe dict/None) statt echte Salden aufzubauen.

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_milog.py -k clock_out -v </dev/null`
Expected: FAIL — Code nicht in warnings.

- [ ] **Step 3: Implement**

In `backend/app/routers/time_entries.py`, `clock_out`, direkt VOR `response = TimeEntryResponse.model_validate(open_entry)` (nach dem `if not exempt:`-Block, unabhängig von `exempt` — die MiLoG-Konto-Grenze ist keine ArbZG-§18-Frage):

```python
    # #377 § 2 Abs. 2 MiLoG: weiche Warnung, wenn die Konto-Plusstunden des
    # laufenden Monats (month-to-date) 50 % der vereinbarten Monatszeit reißen.
    if current_user.milog_working_time_account:
        _milog = milog_service.milog_50_check(
            db, current_user, open_entry.date.year, open_entry.date.month,
            up_to_date=open_entry.date,
        )
        if _milog:
            clock_out_warnings.append(
                f"MILOG_ACCOUNT_50: Konto-Plusstunden dieses Monats "
                f"({_milog['account_hours']:.1f}h) über 50 % der vereinbarten "
                f"Monatszeit (Grenze {_milog['cap']:.1f}h, § 2 Abs. 2 MiLoG)."
            )
```

Import oben ergänzen: `from app.services import milog_service`.

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_milog.py -k clock_out -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/time_entries.py backend/tests/test_milog.py
git commit -m "feat(#377): clock_out emits MILOG_ACCOUNT_50 (month-to-date)"
```

---

## Task 7: `users-overview` → `milog_warnings` (50 % + Ausgleichsfrist)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`users_overview`), `backend/app/schemas/reports.py` (`AdminUserOverview`)
- Test: `backend/tests/test_milog.py`

**Interfaces:**
- Produces: `AdminUserOverview.milog_warnings: list[str]` (leer, wenn Flag aus / nichts überschritten)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_milog.py
def test_users_overview_milog_warnings(db, admin, employee, monkeypatch):
    employee.milog_working_time_account = True; employee.weekly_hours = Decimal("7.62"); db.commit()
    monkeypatch.setattr("app.services.milog_service.milog_50_check",
                        lambda *a, **k: {"account_hours": 20.0, "cap": 16.5, "agreed_monthly": 33.0})
    monkeypatch.setattr("app.services.milog_service.settlement_aging", lambda *a, **k: None)
    client = _client_as(db, admin, admin)
    rows = client.get(f"{USERS}-overview").json()
    row = next(r for r in rows if r["user_id"] == str(employee.id))
    assert any("MILOG_ACCOUNT_50" in w for w in row["milog_warnings"])
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_milog.py -k overview -v </dev/null`
Expected: FAIL — Key/Feld fehlt.

- [ ] **Step 3: Implement**

`app/schemas/reports.py` — `AdminUserOverview` (nach `child_sick_cap`):

```python
    milog_warnings: list[str] = []   # #377 §2 Abs.2 MiLoG (leer, wenn Flag aus)
```

`app/routers/admin_users.py` — im `users_overview`-Loop pro `u` (nutzt `today_local()` für den laufenden Monat):

```python
        _milog_w: list[str] = []
        if u.milog_working_time_account:
            _t = today_local()
            _c = milog_service.milog_50_check(db, u, _t.year, _t.month)
            if _c:
                _milog_w.append(
                    f"MILOG_ACCOUNT_50: Konto-Plusstunden {_c['account_hours']:.1f}h "
                    f"über Grenze {_c['cap']:.1f}h (§ 2 Abs. 2 MiLoG)."
                )
            _a = milog_service.settlement_aging(db, u, _t)
            if _a and (_a["overdue"] or _a["due_soon"]):
                _milog_w.append(
                    f"MILOG_SETTLEMENT_DUE: Konto-Stunden aus {_a['oldest_month']:02d}/{_a['oldest_year']} "
                    f"({_a['hours']:.1f}h) {'überfällig' if _a['overdue'] else 'bald fällig'} "
                    f"(§ 2 Abs. 2 MiLoG, 12-Monats-Ausgleich)."
                )
        # ... im AdminUserOverview(...) ergänzen:
        #     milog_warnings=_milog_w,
```

Import `from app.services import milog_service` + `AdminUserOverview(...)`-Konstruktor um `milog_warnings=_milog_w` erweitern. In Task-Zeit den realen `users_overview`-Loop lesen.

- [ ] **Step 4: Run to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_milog.py -k overview -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_users.py backend/app/schemas/reports.py backend/tests/test_milog.py
git commit -m "feat(#377): users-overview milog_warnings (50% + settlement)"
```

---

## Task 8: Frontend — systemStore `minimum_wage` + arbzgWarnings-Codes

**Files:**
- Modify: `frontend/src/stores/systemStore.ts`, `frontend/src/utils/arbzgWarnings.ts`
- Test: `frontend/src/utils/arbzgWarnings.test.ts`

**Interfaces:**
- Produces: `SystemInfo.minimum_wage?: {current, since, next}`; `useSystemStore().getMinimumWage()`; `showArbzgWarnings` behandelt `MILOG_ACCOUNT_50` + `MILOG_SETTLEMENT_DUE`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/utils/arbzgWarnings.test.ts (anhängen)
it('#377 shows MILOG detail without the code prefix', () => {
  const toast = { warning: vi.fn() };
  showArbzgWarnings(toast, ['MILOG_ACCOUNT_50: Konto-Plusstunden 20.0h über 50 % (Grenze 16.5h, § 2 Abs. 2 MiLoG).']);
  const msg = toast.warning.mock.calls[0][0];
  expect(msg).toContain('§ 2 Abs. 2 MiLoG');
  expect(msg).not.toContain('MILOG_ACCOUNT_50');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npx vitest run src/utils/arbzgWarnings.test.ts --pool=threads"`
Expected: FAIL (default hält Prefix).

- [ ] **Step 3: Implement**

`arbzgWarnings.ts` — im `switch` (nach `CHILD_SICK_LIMIT`):

```ts
      case 'MILOG_ACCOUNT_50':
        toast.warning(detail ?? 'Arbeitszeitkonto: 50 %-Grenze überschritten (§ 2 Abs. 2 MiLoG).');
        break;
      case 'MILOG_SETTLEMENT_DUE':
        toast.warning(detail ?? 'Arbeitszeitkonto: 12-Monats-Ausgleichsfrist beachten (§ 2 Abs. 2 MiLoG).');
        break;
```

`systemStore.ts` — `SystemInfo` erweitern:

```ts
  minimum_wage?: { current: number; since: string; next: { value: number; from: string } | null };
```

und einen Getter im Store:

```ts
  getMinimumWage: () => get().info?.minimum_wage ?? null,
```

(Getter im `SystemState`-Interface deklarieren.)

- [ ] **Step 4: Run to verify it passes**

Run: `docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine sh -c "npx vitest run src/utils/arbzgWarnings.test.ts --pool=threads"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/systemStore.ts frontend/src/utils/arbzgWarnings.ts frontend/src/utils/arbzgWarnings.test.ts
git commit -m "feat(#377): frontend minimum_wage store + MILOG warning cases"
```

---

## Task 9: Frontend — UserForm-Checkbox + Mindestlohn-Infozeile

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx`, `frontend/src/types/user.ts`
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx` (neu oder vorhandenes erweitern)

**Interfaces:**
- Consumes: User-Typ `milog_working_time_account`; `useSystemStore().getMinimumWage()`

- [ ] **Step 1: Write the failing test**

```tsx
// minimaler Render-Test: die Checkbox „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)" ist da.
it('renders the MiLoG working-time-account checkbox', () => {
  render(/* UserForm mit vorhandenen Props/Mocks wie Nachbar-Tests */);
  expect(screen.getByLabelText(/Arbeitszeitkonto/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails** → Checkbox fehlt.

- [ ] **Step 3: Implement**

`types/user.ts` (nach `child_sick_days_per_year`):

```ts
  milog_working_time_account?: boolean; // #377
```

`UserForm.tsx`:
- initiales `useState({...})`: `milog_working_time_account: false,`
- `editUser`-Reset `setFormData({...})`: `milog_working_time_account: editUser.milog_working_time_account ?? false,`
- JSX (bei den Checkboxen `exempt_from_arbzg`/`is_night_worker`): eine Checkbox „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) — 50 %-Prüfung & 12-Monats-Frist"; darunter, wenn aktiv, eine Infozeile aus `getMinimumWage()`:
  „Aktueller Mindestlohn: {current} €/h (seit {since}). Vereinbarte Monatszeit ≈ {weekly×13/3} h → max. Konto {…/2} h/Monat."

> `formData`/`setFormData`-Muster + Checkbox-Block der Nachbar-Flags 1:1 spiegeln (BEIDE Hydrations-Pfade wie bei #376).

- [ ] **Step 4: Run to verify it passes** (vitest, node:20-Container)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/users/UserForm.tsx frontend/src/types/user.ts frontend/src/pages/admin/users/UserForm.test.tsx
git commit -m "feat(#377): UserForm MiLoG flag + minimum-wage info line"
```

---

## Task 10: Frontend — Settings-Compliance-Karte + Übersicht-Badges

**Files:**
- Modify: `frontend/src/pages/admin/Settings.tsx`
- Modify: die Admin-Übersicht-/Überstundenkonto-Komponente, die `users-overview` rendert (in Task-Zeit lokalisieren: sucht `child_sick`/`overtime`-Rendering)
- Test: (Rendering wird über tsc + bestehende Vitest abgedeckt; optionaler gezielter Test)

**Interfaces:**
- Consumes: `getMinimumWage()`, `AdminUserOverview.milog_warnings`

- [ ] **Step 1: Implement Settings-Karte**

In `Settings.tsx` eine Info-Karte „Gesetzlicher Mindestlohn": aktueller Wert + „seit …" + (falls `next`) „ab {from}: {value} €/h". Rein informativ (kein Speichern).

- [ ] **Step 2: Implement Übersicht-Badges**

In der Komponente, die `users-overview` rendert, pro MA die `milog_warnings` als kleines Warn-Badge/Tooltip anzeigen (nur wenn nicht leer). Text über `showArbzgWarnings`-Codes bzw. direkt anzeigen.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit` → sauber. Vitest-Suite grün (node:20-Container).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/admin/Settings.tsx frontend/src/<overview-komponente>
git commit -m "feat(#377): Settings minimum-wage card + overview MiLoG badges"
```

---

## Task 11: Doku (Handbuch, In-App-Hilfe, CLAUDE.md)

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md`, `frontend/src/components/DocViewer.tsx` (`handbuchAdminSections`), `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-07-08-minijob-milog-design.md` (Status → implementiert)

- [ ] **Step 1: Handbuch + In-App-Hilfe**

Abschnitt „Minijob / Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)": Flag setzen, aktueller Mindestlohn (13,90 €), 50-%-Regel (Konto-Stunden ≤ 50 % der vereinbarten Monatszeit), 12-Monats-Ausgleich, weiche Warnungen (nicht blockierend), Hinweis: keine Verdienst-/603-€-Prüfung (kein Lohn hinterlegt), Baustein Monatsstunden folgt. **DocViewer-Admin-Sektion mitpflegen** (hardcoded).

- [ ] **Step 2: CLAUDE.md-Regel**

Unter „Kritische Regeln":

> **#377 Minijob/MiLoG (§ 2 Abs. 2):** Opt-in `User.milog_working_time_account` (Migration 062). `app/core/minimum_wage.py` = datumsabhängige Mindestlohn-Konstante (13,90 ab 2026, 14,60 ab 2027) → `/api/system/info`. `app/services/milog_service.py`: `agreed_monthly_hours` (= `weekly_hours × 13/3`), `milog_50_check` (Konto-Plus > 50 % → weiche `MILOG_ACCOUNT_50`), `settlement_aging` (FIFO über `get_overtime_history_detailed`-Deltas → `MILOG_SETTLEMENT_DUE` ab 12 Mon.). Nur LESE-Schicht, Calc eingefroren. Warnungen NIE blockierend, nur bei Flag. Surfaces: `clock_out` (month-to-date 50 %) + `users-overview.milog_warnings`. **Baustein 2 (Monatsmodus) offen** — dann `agreed_monthly_hours` auf echte Monatszahl umstellen. Kein 603-€-/Lohn-Check (bewusst).

- [ ] **Step 3: Commit**

```bash
git add docs/handbuch/HANDBUCH-ADMIN.md frontend/src/components/DocViewer.tsx CLAUDE.md docs/superpowers/specs/2026-07-08-minijob-milog-design.md
git commit -m "docs(#377): MiLoG handbook, in-app help, CLAUDE.md rule"
```

---

## Task 12: E2E (Playwright, API-driven, self-cleaning)

**Files:**
- Create: `e2e/tests/admin/minijob-milog.spec.ts`

**Interfaces:**
- Consumes: `authTest`/`adminApi`; `/api/system/info`, `/api/admin/users`, `/api/admin/users-overview`

- [ ] **Step 1: Write the E2E test**

```ts
// e2e/tests/admin/minijob-milog.spec.ts — Muster wie tests/admin/child-sick.spec.ts.
// 1) GET /api/system/info → minimum_wage.current > 0.
// 2) ephemeren MA mit milog_working_time_account=true + weekly_hours 7.62 anlegen.
// 3) genügend TimeEntries im laufenden Monat buchen, dass Ist−Soll > 50 % (>16,5h).
// 4) GET /api/admin/users-overview → row.milog_warnings enthält MILOG_ACCOUNT_50.
// 5) Flag aus (PUT) → milog_warnings leer.
// finally: MA + TimeEntries löschen.
```

> Zeit-Einträge über die vorhandenen Test-Data-Fixtures/`adminApi` anlegen; Datumsfenster im laufenden Monat, Werktage (`weekdayFromNow`). Falls das Aufbauen echter Salden zu sperrig ist: den 50-%-Pfad über genügend Ist-Stunden erzeugen (Soll klein bei 7,62 h/Woche).

- [ ] **Step 2: Run** (Frontend-/API-Proxy auf erreichbarem Port; erhöhte Auth-Limits)

```bash
E2E_API_BASE=http://localhost:8080/api E2E_BASE_URL=http://localhost:8080 \
  npx playwright test tests/admin/minijob-milog.spec.ts --reporter=list --output=<scratch>
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add e2e/tests/admin/minijob-milog.spec.ts
git commit -m "test(#377): e2e minijob MiLoG minimum-wage + 50% warning"
```

---

## Task 13: Volle Regression + PR

- [ ] **Step 1: Backend-Suite (TZ + Postgres-Ignores)**

```bash
docker compose cp backend/app backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py -q </dev/null
docker compose exec -T backend pytest tests/test_tenant_rls.py tests/test_cross_tenant_api.py -q </dev/null
```
Expected: grün.

- [ ] **Step 2: Frontend tsc + vitest + build** (node:20-Container, `--pool=threads`)

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/377-minijob-milog
gh pr create --base master --title '#377 Minijob-Compliance: Mindestlohn + § 2 Abs. 2 MiLoG (Baustein 1+3)' --body-file - <<'EOF'
… (Zusammenfassung: Mindestlohn-Anzeige, 50%-Check, 12-Monats-Aging, Opt-in-Flag,
keine Lohndaten; Baustein 2 Monatsmodus folgt separat)
🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

## Self-Review

**Spec-Abdeckung:**
- Mindestlohn-Konstante + Anzeige → Task 1/2/8/10 ✓
- Opt-in-Flag → Task 3 ✓
- 50-%-Check + clock_out + Übersicht → Task 4/6/7 ✓
- 12-Monats-Aging → Task 5/7 ✓
- UI (UserForm/Settings/Badges) → Task 9/10 ✓
- Doku → Task 11 ✓
- Tests (Backend/Vitest/E2E) → alle Tasks + 12/13 ✓
- DSGVO (keine Lohndaten) → keine neue Arbeit, in Doku vermerkt ✓

**Placeholder-Scan:** Anker mit „in Task-Zeit prüfen" sind explizite Verifikationspunkte (reale Signaturen `get_monthly_balance`/`get_overtime_history_detailed`/`system_info`-Dict/`users_overview`-Loop/UI-Komponentennamen) — bewusst, mit Datei:Zeile.

**Typ-Konsistenz:** `milog_working_time_account` (bool) durchgängig; `milog_50_check`→dict `{account_hours,cap,agreed_monthly}`; `settlement_aging`→dict `{oldest_year,oldest_month,age_months,hours,overdue,due_soon}`; Warncodes `MILOG_ACCOUNT_50`/`MILOG_SETTLEMENT_DUE` in Backend (6/7) und Frontend (8) identisch.
