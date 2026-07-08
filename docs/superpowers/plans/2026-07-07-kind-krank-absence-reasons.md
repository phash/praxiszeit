# "Kind krank" + Sonderurlaub-Gründe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** „Kind krank" und weitere Sonderurlaubs-Gründe als über die Einstellungen aktivierbare Abwesenheitsgründe abbilden — mit unbezahlt-frei-Verhalten und einer weichen §45-SGB-V-Tageslimit-Warnung.

**Architecture:** Baut auf #312 (Custom Absence Reasons) auf. Neues `base_behavior` `unpaid_free` mappt auf den bestehenden `AbsenceType.OTHER` (Soll→0, Ist+=0, saldo-neutral, kein Urlaub, unbezahlt) — das eingefrorene Calc-Modell bleibt unverändert. Ein Marker-Flag am Grund (`tracks_child_sick_limit`) plus ein per-MA-Anspruchsfeld (`child_sick_days_per_year`) mit Tenant-Default treiben einen tagebasierten Jahres-Zähler, der bei Überschreitung eine weiche (nicht blockierende) Warnung an die Buchungs-Response hängt.

**Tech Stack:** FastAPI (Python 3.12) + SQLAlchemy + Alembic + PostgreSQL 16 (Backend), React 18 + TypeScript + Tailwind (Frontend), pytest / Vitest / Playwright (Tests).

**Spec:** `docs/superpowers/specs/2026-07-07-kind-krank-absence-reasons-design.md`

## Corrections (verified against the real codebase — OVERRIDE any conflicting detail below)

Ein 9-Lens-Adversarial-Review (Verdict: **architektonisch tragfähig, kein Design-Change**) hat die Anker geprüft. Die Task-Details unten waren teils geraten — **diese realen Werte gelten**:

**Test-Auth (Tasks 4/5/6/7/8/9) — Header-Auth ist FIKTION.** `conftest.py` liefert nur: `db`, `default_tenant`, `test_user` (EMPLOYEE, weekly_hours=40, wd=5, DEFAULT_TENANT), `test_admin`, `public_holiday`, `working_hours_change`. **Keine** `client`/`admin_headers`/`employee_headers`/`tenant_user`/`employee_user`. Muster: lokales `_app()` mit `app.dependency_overrides[get_db]/[get_current_user]/[require_admin]` + headerless `TestClient`, Limiter deaktiviert (siehe `test_absence_reasons.py:20-90` → `_client`/`admin_client`, `ADMIN_BASE='/api/admin/absence-reasons'`; `test_endpoints.py:195-233`). **Alle HTTP-Pfade mit `/api`-Prefix.** Jede neue HTTP-Testdatei baut ihr eigenes `_app()` mit genau den nötigen Routern:
- Task 5 → `admin.router` · Pfad `PUT /api/admin/settings/child_sick_days_default`
- Task 7 → `absences.router` + `absence_reasons.admin_router` · `POST /api/absences/`, `POST /api/admin/absence-reasons`
- Task 8 → + `admin.router` + `change_requests.router` · `POST /api/change-requests/` (trailing slash!), `POST /api/admin/change-requests/{id}/review`, `PUT /api/admin/users/{id}`
- Task 9 → `admin.router` · `GET /api/admin/users-overview`
- Task 4 → hängt an `test_absence_reasons.py` an → nutze das vorhandene `admin_client` + `ADMIN_BASE`.
- Task 6 → **reiner Calc-Test, kein app/client**. `tenant_user` → **`test_user`** (Signaturen `(db, test_user)`).

**Task 2 — Migration:** neuester Head ist `revision = '060_impersonation_sessions'` (Datei `2026_07_01_1000-060_add_impersonation_sessions.py` — Rev-ID ≠ Dateiname-Slug!). Neue Migration: `down_revision = '060_impersonation_sessions'`, `revision = '061_child_sick_fields'`, Datei nach Template **`2026_07_08_HHMM-061_child_sick_fields.py`**. Backend evtl. down → Head aus `revision =` der neuesten versions-Datei lesen statt `alembic heads`.

**Task 6 — calc:** `AbsenceReason` fehlt im Modul-Import → an die `from app.models import ...`-Zeile (Zeile 9) anhängen (`date/Decimal/Session/User/Absence` sind da). `child_sick_days_used`-Join zusätzlich `AbsenceReason.tenant_id == user.tenant_id` (F-026).

**Task 7 — create_absence:** endet mit `return created_absences` bei **Zeile 625**; `reason`/`reason_id` im Scope. **`target_user`** existiert dort — Variablenname im Review prüfen; sonst die MA-Variable des Buchungspfads nutzen. **Jahresgrenze:** Warnung pro distinktem Jahr in `created_absences` rechnen (`set(a.date.year for a in created_absences)`), nicht nur `absence_data.date.year`.

**Task 8 — CR-Pfad (KOMPLETT ersetzt, siehe Task unten):** Block **TOP-LEVEL nach Zeile 774** (`cr_response = _enrich_cr_response(cr, db)`), **NICHT** im ArbZG-`proposed_start_time/end_time`-Block (Z780+ wird bei Ganztags-Absence übersprungen → Warnung feuerte nie). Gate: `review.action=='approve' and cr.entry_kind=='absence' and cr.request_type in (ChangeRequestType.CREATE, ChangeRequestType.UPDATE) and cr.proposed_reason_id is not None` (deckt CREATE **und** UPDATE-in-Kind-krank ab). User frisch holen: `cs_user = db.query(User).filter(User.id==cr.user_id, User.tenant_id==cr.tenant_id).first()`. Datum `cr.proposed_date` (guard). Imports: `AbsenceReason` an `from app.models import` (Zeile 8) + `from app.services import calculation_service`. CR-Create-Payload real: `{"entry_kind":"absence","request_type":"create","proposed_date":"<vergangenheit>","proposed_absence_type":"other","proposed_absence_hours":8,"reason_id":<id>,"reason":"Kind krank"}`; Review-Body `{"action":"approve"}`; **4-Augen:** Autor = MA, Genehmiger = separater Admin.

**Task 10/16 — `frontend/src/api/users.ts` existiert NICHT.** Alle Referenzen streichen (File-Structure, Task 10 Step 3, `git add` in 10 & 16). User-CRUD ist inline in `UserForm.tsx` (`apiClient.post('/admin/users', payload)` L206, `apiClient.put('/admin/users/${id}', updateData)` L193); Feld fließt über den `...userFields`-Spread automatisch. Typ NUR in `frontend/src/types/user.ts`.

**Task 11 — bare `render(<AbsenceReasonsManager/>)` wirft** (`useToast()` L18 ohne Provider) → in `<ToastProvider>` wrappen (`useConfirm` L19 = lokaler Hook, braucht keinen Provider).

**Task 12 — Response wird verworfen + dritte Buchungsstelle fehlt.** `AdminAbsences.tsx:219` + `AbsenceCalendarPage.tsx:241` (in `doSubmit`, NICHT `handleSubmit`) machen `await apiClient.post('/absences', …)` ohne `const res =` → `res.data` binden. **`MonthlyJournal.tsx` ist ein DRITTER Kind-krank-fähiger POST** (`handleSave ~L221`, `handleAdminSave ~L286`, `reason_id` gesetzt, Response verworfen; `showArbzgWarnings` schon importiert L9) → mit aufnehmen. Der arbzg-`default:`-Zweig ist `toast.warning(raw)` → der „rote" Test ist NICHT rot; entweder assert, dass der Toast-Text **nicht** den Prefix `CHILD_SICK_LIMIT:` enthält (Default enthält ihn), oder den neuen `case` als kosmetisches Prefix-Stripping framen.

**Task 13 — State ist `formData`/`setFormData` (nicht `form`/`setForm`).** Feld an **BEIDE** Hydrations-Pfade: initiales `useState({...})` (L24, `child_sick_days_per_year: null`) UND den `if (editUser) setFormData({...})`-Effect (L65-102, `child_sick_days_per_year: editUser.child_sick_days_per_year ?? null`) — sonst gehen Edits still verloren.

**Task 14 — MA-Doku ergänzen:** `read_router GET /api/absence-reasons` liefert aktive Gründe an jeden Nutzer; nur VACATION ist approval-gated → MA können „Kind krank" (OTHER) selbst buchen. Also auch `HANDBUCH-MITARBEITER.md` + `handbuchMitarbeiterSections` in `DocViewer.tsx` pflegen.

**By-design (kein Fix):** `unpaid_free` und `paid_free` sind calc-IDENTISCH (Modell hat keine Lohn-Dimension) → Tests dürfen NIE einen Soll/Ist-Unterschied zwischen beiden asserten, nur das Reporting-Label. `journal_service` (SICK-only-Masking) ist außerhalb #376-Scope.

---

## Global Constraints

- **Calc-Modell eingefroren:** `Absence.type` treibt ALLE Berechnung; `reason_id` ist nur Label/Farbe. Kein neuer `AbsenceType`.
- **Tage tagebasiert, NIE `Σh ÷ Tagessoll`** (GLOSSAR-Tagesprinzip §3 BUrlG): `half_day=True` = 0,5, Legacy `half_day=None` = `hours ÷ Tagessoll-des-Tages`, Tagessoll 0 → 0.
- **Multi-Tenant Pflicht:** neue Spalten tenant-scoped über bestehende tenant-scoped Tabellen; alle Queries mit explizitem `Model.tenant_id == current_user.tenant_id` (F-026) zusätzlich zu RLS.
- **Beschäftigungsfenster:** Per-Tag-Zählungen respektieren `calculation_service._within_employment_window(user, d)`.
- **Alembic Rev-ID ≤ 32 Zeichen.** Migration auf Host erstellen + committen VOR Container-Rebuild. Up UND Down.
- **Warnung weich, non-blocking:** niemals 400 wegen Limit — der Fehltag muss erfassbar bleiben.
- **DSGVO:** bereits durch #312 abgedeckt (jede `reason_id` → „absent" in Kollegen-Feeds + Export-Masking). Keine neue Maskier-Arbeit.
- **Backend-Container ist gebaut, kein Host-Volume:** nach Edits `docker compose cp backend/app backend:/app/` VOR `pytest`.
- **Vitest:** `npx vitest run <datei> --pool=threads` (Default-`forks`-Pool hängt auf dieser Maschine).
- **`docker compose cp <dir>` verschachtelt** → doppelte pytest-Collection; einzelne Dateien kopieren oder Image neu bauen.

---

## File Structure

**Backend (modify):**
- `app/models/absence.py` — `UNPAID_FREE` Enum + Map-Eintrag; `AbsenceReason.tracks_child_sick_limit`
- `app/models/user.py` — `child_sick_days_per_year`
- `app/schemas/absence_reason.py` — Flag in Create/Response
- `app/schemas/user.py` — Feld in Base/Update/Response
- `app/schemas/absence.py` — `warnings` in `AbsenceResponse`
- `app/routers/absence_reasons.py` — Flag persistieren (create + update)
- `app/routers/admin_settings.py` — `child_sick_days_default` in `_ALLOWED_SETTINGS` + int-Validierung
- `app/routers/absences.py` — weiche Warnung in `create_absence`
- `app/routers/admin_change_requests.py` — weiche Warnung im CR-Genehmigungspfad
- `app/routers/admin_users.py` — Kind-krank Verbrauch/Cap in `users-overview` (nice-to-have)
- `app/services/settings_service.py` — `get_int_setting`
- `app/services/calculation_service.py` — `child_sick_days_used`, `child_sick_cap`
- `alembic/versions/<neu>.py` — eine Migration

**Frontend (modify):**
- `src/api/absenceReasons.ts` — `unpaid_free` Typ/Labels/Hints, `tracks_child_sick_limit`, Preset-Katalog
- `src/api/users.ts` + `src/types/user.ts` — `child_sick_days_per_year`
- `src/components/AbsenceReasonsManager.tsx` — `unpaid_free` in Dropdown + Preset-Sektion
- `src/pages/admin/Settings.tsx` — `child_sick_days_default` Feld
- `src/pages/admin/users/UserForm.tsx` — `child_sick_days_per_year` Feld
- `src/utils/arbzgWarnings.ts` — `CHILD_SICK_LIMIT` Case
- `src/pages/admin/AdminAbsences.tsx` + `src/pages/AbsenceCalendarPage.tsx` — Warn-Toast nach Buchung

**Docs:**
- `docs/handbuch/HANDBUCH-ADMIN.md`, `frontend/src/components/DocViewer.tsx`, `CLAUDE.md`

---

## Task 1: `unpaid_free → OTHER` Verhalten (Model + Map)

**Files:**
- Modify: `backend/app/models/absence.py`
- Test: `backend/tests/test_absence_reasons.py` (anhängen; existiert aus #312 — sonst neu erstellen)

**Interfaces:**
- Produces: `AbsenceReasonBehavior.UNPAID_FREE = "unpaid_free"`, `BEHAVIOR_TO_ABSENCE_TYPE[AbsenceReasonBehavior.UNPAID_FREE] == AbsenceType.OTHER`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_absence_reasons.py  (Ergänzung; ggf. Datei neu mit den Imports)
from app.models.absence import (
    AbsenceReasonBehavior,
    BEHAVIOR_TO_ABSENCE_TYPE,
    AbsenceType,
)


def test_unpaid_free_behavior_maps_to_other():
    assert AbsenceReasonBehavior.UNPAID_FREE.value == "unpaid_free"
    assert BEHAVIOR_TO_ABSENCE_TYPE[AbsenceReasonBehavior.UNPAID_FREE] == AbsenceType.OTHER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_absence_reasons.py::test_unpaid_free_behavior_maps_to_other -v </dev/null`
Expected: FAIL — `AttributeError: UNPAID_FREE` / `KeyError`.

- [ ] **Step 3: Implement**

In `backend/app/models/absence.py`, `AbsenceReasonBehavior` um einen Wert erweitern:

```python
class AbsenceReasonBehavior(str, enum.Enum):
    WORKED = "worked"            # zählt als gearbeitet (wie Fortbildung, §3)
    PAID_FREE = "paid_free"      # bezahlt frei (wie PAID_LEAVE)
    OVERTIME_COMP = "overtime_comp"  # Überstundenabbau (wie OVERTIME)
    UNPAID_FREE = "unpaid_free"  # #376 entschuldigt UNBEZAHLT (Kind krank, unbez. Sonderurlaub) → OTHER
```

und die Map ergänzen:

```python
BEHAVIOR_TO_ABSENCE_TYPE = {
    AbsenceReasonBehavior.WORKED: AbsenceType.TRAINING,
    AbsenceReasonBehavior.PAID_FREE: AbsenceType.PAID_LEAVE,
    AbsenceReasonBehavior.OVERTIME_COMP: AbsenceType.OVERTIME,
    AbsenceReasonBehavior.UNPAID_FREE: AbsenceType.OTHER,  # #376
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_absence_reasons.py::test_unpaid_free_behavior_maps_to_other -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/absence.py backend/tests/test_absence_reasons.py
git commit -m "feat(#376): unpaid_free absence-reason behavior maps to OTHER"
```

---

## Task 2: DB-Spalten + Migration

**Files:**
- Modify: `backend/app/models/absence.py` (`AbsenceReason.tracks_child_sick_limit`)
- Modify: `backend/app/models/user.py` (`child_sick_days_per_year`)
- Create: `backend/alembic/versions/<rev>_child_sick_fields.py`
- Test: `backend/tests/test_absence_reasons.py`

**Interfaces:**
- Produces: `AbsenceReason.tracks_child_sick_limit` (bool, default False), `User.child_sick_days_per_year` (int | None)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_absence_reasons.py
from app.models.absence import AbsenceReason
from app.models.user import User


def test_new_columns_exist_with_defaults():
    assert "tracks_child_sick_limit" in AbsenceReason.__table__.columns
    assert AbsenceReason.__table__.columns["tracks_child_sick_limit"].nullable is False
    assert "child_sick_days_per_year" in User.__table__.columns
    assert User.__table__.columns["child_sick_days_per_year"].nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_absence_reasons.py::test_new_columns_exist_with_defaults -v </dev/null`
Expected: FAIL — `KeyError` (Spalte fehlt).

- [ ] **Step 3: Implement model columns**

`backend/app/models/absence.py`, in `class AbsenceReason` nach `sort_order`:

```python
    # #376: markiert DEN Kind-krank-Grund → zählt gegen das §45-SGB-V-Jahreslimit.
    # Generisch (v1 nur von "Kind krank" genutzt). Nur ein Label-Flag; die
    # Calc-Mechanik kommt allein aus base_behavior/type.
    tracks_child_sick_limit = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
```

`backend/app/models/user.py`, in `class User` nach `last_work_day`:

```python
    # #376: persönlicher Kind-krank-Jahresanspruch (§45 SGB V). NULL = Tenant-Default
    # (Setting child_sick_days_default, sonst 15). Speichert KEINE Kinderdaten.
    child_sick_days_per_year = Column(Integer, nullable=True)
```

- [ ] **Step 4: Create the migration**

Neueste Revision ermitteln:

Run: `docker compose exec -T backend alembic heads </dev/null`

`backend/alembic/versions/061_child_sick_fields.py` (Rev-ID `061_child_sick_fields` ist 20 Zeichen ✓; `down_revision` = ausgegebener head):

```python
"""#376 Kind-krank: tracks_child_sick_limit + child_sick_days_per_year

Revision ID: 061_child_sick_fields
Revises: <HEAD_AUS_STEP4>
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "061_child_sick_fields"
down_revision = "<HEAD_AUS_STEP4>"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "absence_reasons",
        sa.Column(
            "tracks_child_sick_limit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("child_sick_days_per_year", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("users", "child_sick_days_per_year")
    op.drop_column("absence_reasons", "tracks_child_sick_limit")
```

- [ ] **Step 5: Run the migration + verify tests pass**

```bash
docker compose cp backend/app backend:/app/
docker compose cp backend/alembic backend:/app/alembic
docker compose exec -T backend python -c "from alembic.config import main; main(['upgrade','head'])" </dev/null
docker compose exec -T backend pytest tests/test_absence_reasons.py::test_new_columns_exist_with_defaults -v </dev/null
```
Expected: Migration läuft, Test PASS.

- [ ] **Step 6: Verify up→down→up round-trip**

```bash
docker compose exec -T backend python -c "from alembic.config import main; main(['downgrade','-1'])" </dev/null
docker compose exec -T backend python -c "from alembic.config import main; main(['upgrade','head'])" </dev/null
```
Expected: keine Fehler.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/absence.py backend/app/models/user.py backend/alembic/versions/061_child_sick_fields.py backend/tests/test_absence_reasons.py
git commit -m "feat(#376): DB columns tracks_child_sick_limit + child_sick_days_per_year (migration 061)"
```

---

## Task 3: Schemas (Reason-Flag, User-Feld, Absence-Warnings)

**Files:**
- Modify: `backend/app/schemas/absence_reason.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/schemas/absence.py`
- Test: `backend/tests/test_absence_reasons.py`

**Interfaces:**
- Produces: `AbsenceReasonCreate.tracks_child_sick_limit: bool = False`, `AbsenceReasonResponse.tracks_child_sick_limit: bool`, `UserBase.child_sick_days_per_year: Optional[int]`, `UserUpdate.child_sick_days_per_year: Optional[int]`, `AbsenceResponse.warnings: list[str] = []`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_absence_reasons.py
from app.schemas.absence_reason import AbsenceReasonCreate, AbsenceReasonResponse
from app.schemas.absence import AbsenceResponse


def test_schema_fields_present():
    c = AbsenceReasonCreate(name="Kind krank", base_behavior="unpaid_free", tracks_child_sick_limit=True)
    assert c.tracks_child_sick_limit is True
    assert "tracks_child_sick_limit" in AbsenceReasonResponse.model_fields
    assert "warnings" in AbsenceResponse.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_absence_reasons.py::test_schema_fields_present -v </dev/null`
Expected: FAIL — unbekanntes Feld / fehlt in `model_fields`.

- [ ] **Step 3: Implement**

`backend/app/schemas/absence_reason.py` — `AbsenceReasonCreate` um Feld erweitern:

```python
class AbsenceReasonCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    color: Optional[str] = None
    base_behavior: AbsenceReasonBehavior
    sort_order: int = 0
    tracks_child_sick_limit: bool = False  # #376
```

`AbsenceReasonResponse` um Feld erweitern (nach `sort_order`):

```python
    tracks_child_sick_limit: bool = False  # #376
```

`backend/app/schemas/user.py` — in `UserBase` (nach `department`):

```python
    child_sick_days_per_year: Optional[int] = Field(None, ge=0, le=70)  # #376 §45 SGB V; None = Tenant-Default
```

und in `UserUpdate` (nach `department`):

```python
    child_sick_days_per_year: Optional[int] = Field(None, ge=0, le=70)  # #376
```

`backend/app/schemas/absence.py` — in `AbsenceResponse` (nach `reason_id`):

```python
    warnings: list[str] = Field(default_factory=list)  # #376: weiche, non-blocking Hinweise (z. B. CHILD_SICK_LIMIT)
```

> Hinweis: `AbsenceResponse` nutzt `from_attributes`. GET-Endpoints liefern ORM-Rows ohne `warnings` → der `default_factory` greift. In `create_absence` (Task 7) wird `warnings` als transientes Attribut auf die erzeugte ORM-Row gesetzt.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_absence_reasons.py::test_schema_fields_present -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/absence_reason.py backend/app/schemas/user.py backend/app/schemas/absence.py backend/tests/test_absence_reasons.py
git commit -m "feat(#376): schema fields (reason flag, user cap, absence warnings)"
```

---

## Task 4: `absence_reasons` Router persistiert das Flag

**Files:**
- Modify: `backend/app/routers/absence_reasons.py`
- Test: `backend/tests/test_absence_reasons.py`

**Interfaces:**
- Consumes: `AbsenceReasonCreate.tracks_child_sick_limit`
- Produces: gespeicherter `AbsenceReason.tracks_child_sick_limit`; via `PUT` (`AbsenceReasonUpdate`) NICHT änderbar (v1-Lock, wie `base_behavior`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_absence_reasons.py — nutzt die vorhandene Admin-Client-Fixture (client/admin_headers).
def test_create_reason_persists_child_sick_flag(client, admin_headers):
    resp = client.post(
        "/admin/absence-reasons",
        headers=admin_headers,
        json={"name": "Kind krank", "base_behavior": "unpaid_free", "tracks_child_sick_limit": True},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["tracks_child_sick_limit"] is True
    assert body["base_behavior"] == "unpaid_free"
```

> Fixtures `client` / `admin_headers` aus `backend/tests/conftest.py` (analog zu den anderen #312-Tests in dieser Datei). Falls die #312-Tests andere Namen nutzen (z. B. `admin_client`), diese verwenden.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_absence_reasons.py::test_create_reason_persists_child_sick_flag -v </dev/null`
Expected: FAIL — `tracks_child_sick_limit` bleibt `False` (Router ignoriert das Feld).

- [ ] **Step 3: Implement**

`backend/app/routers/absence_reasons.py`, im `create_reason`, den `AbsenceReason(...)`-Konstruktor erweitern:

```python
    r = AbsenceReason(
        tenant_id=current_user.tenant_id, name=name, color=color,
        base_behavior=data.base_behavior.value, sort_order=data.sort_order, is_active=True,
        tracks_child_sick_limit=data.tracks_child_sick_limit,  # #376
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_absence_reasons.py::test_create_reason_persists_child_sick_flag -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/absence_reasons.py backend/tests/test_absence_reasons.py
git commit -m "feat(#376): persist tracks_child_sick_limit on reason create"
```

---

## Task 5: Settings-int-Getter + `child_sick_days_default` erlaubt

**Files:**
- Modify: `backend/app/services/settings_service.py`
- Modify: `backend/app/routers/admin_settings.py`
- Test: `backend/tests/test_settings.py` (existierend; sonst neu)

**Interfaces:**
- Produces: `settings_service.get_int_setting(db, key, tenant_id, default) -> int`; Setting-Key `child_sick_days_default` erlaubt + int-validiert (≥0)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings.py
def test_child_sick_days_default_setting_accepts_int(client, admin_headers):
    ok = client.put("/admin/settings/child_sick_days_default", headers=admin_headers, json={"value": "20"})
    assert ok.status_code == 200
    bad = client.put("/admin/settings/child_sick_days_default", headers=admin_headers, json={"value": "-3"})
    assert bad.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_settings.py::test_child_sick_days_default_setting_accepts_int -v </dev/null`
Expected: FAIL — 400 „Unbekannte Einstellung".

- [ ] **Step 3: Implement**

`backend/app/services/settings_service.py` anhängen:

```python
def get_int_setting(db: Session, key: str, tenant_id=None, default: int = 0) -> int:
    """#376: int-Wert eines Settings; Default bei fehlend/nicht-parsebar."""
    raw = get_setting(db, key, tenant_id)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
```

`backend/app/routers/admin_settings.py` — `child_sick_days_default` in `_ALLOWED_SETTINGS` aufnehmen:

```python
    "closure_overtime_after_vacation",  # #314 …
    "child_sick_days_default",  # #376 Kind-krank-Default-Anspruch/Jahr (int, Default 15)
} | special_days_service.SETTING_KEYS
```

und im `update_setting` neben der `work_window_grace_minutes`-Validierung eine analoge int-Prüfung ergänzen:

```python
    # #376: child_sick_days_default als nicht-negative Zahl validieren
    if key == "child_sick_days_default":
        try:
            if int(value) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="child_sick_days_default muss eine nicht-negative Zahl sein")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_settings.py::test_child_sick_days_default_setting_accepts_int -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/settings_service.py backend/app/routers/admin_settings.py backend/tests/test_settings.py
git commit -m "feat(#376): child_sick_days_default setting + get_int_setting"
```

---

## Task 6: Zähler + Cap-Helper im `calculation_service`

**Files:**
- Modify: `backend/app/services/calculation_service.py`
- Test: `backend/tests/test_calculation_child_sick.py` (neu)

**Interfaces:**
- Consumes: `settings_service.get_int_setting`, `_within_employment_window`, `get_daily_target*`, `get_weekly_hours_for_date`
- Produces:
  - `child_sick_cap(db, user) -> int` = `user.child_sick_days_per_year` ?? Tenant-`child_sick_days_default` ?? 15
  - `child_sick_days_used(db, user, year) -> Decimal` = tagebasierte Summe der Absencen im Kalenderjahr, deren `reason.tracks_child_sick_limit` True ist

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_calculation_child_sick.py
from datetime import date
from decimal import Decimal

from app.models.absence import Absence, AbsenceReason, AbsenceType
from app.services import calculation_service as calc


def _mk_reason(db, tenant_id, tracks):
    r = AbsenceReason(tenant_id=tenant_id, name="Kind krank" if tracks else "X",
                      base_behavior="unpaid_free", is_active=True, tracks_child_sick_limit=tracks)
    db.add(r); db.flush()
    return r


def test_child_sick_cap_prefers_user_then_setting_then_15(db, tenant_user):
    user = tenant_user  # weekly_hours>0, track_hours True
    assert calc.child_sick_cap(db, user) == 15                # kein Feld, kein Setting → 15
    user.child_sick_days_per_year = 22
    assert calc.child_sick_cap(db, user) == 22                # per-MA schlägt alles


def test_child_sick_days_used_counts_only_flagged_reason_tagebasiert(db, tenant_user):
    user = tenant_user
    flagged = _mk_reason(db, user.tenant_id, True)
    other = _mk_reason(db, user.tenant_id, False)
    dt = calc.get_daily_target_for_date(user, date(2026, 3, 2), None)  # ein Arbeitstag
    db.add(Absence(tenant_id=user.tenant_id, user_id=user.id, date=date(2026, 3, 2),
                   type=AbsenceType.OTHER, hours=dt, half_day=False, reason_id=flagged.id))
    db.add(Absence(tenant_id=user.tenant_id, user_id=user.id, date=date(2026, 3, 3),
                   type=AbsenceType.OTHER, hours=dt, half_day=True, reason_id=flagged.id))
    db.add(Absence(tenant_id=user.tenant_id, user_id=user.id, date=date(2026, 3, 4),
                   type=AbsenceType.OTHER, hours=dt, half_day=False, reason_id=other.id))
    db.flush()
    assert calc.child_sick_days_used(db, user, 2026) == Decimal("1.5")  # 1 + 0.5, other zählt nicht
    assert calc.child_sick_days_used(db, user, 2025) == Decimal("0")    # anderes Jahr
```

> Fixtures `db` / `tenant_user` aus `backend/tests/conftest.py`. Namen an die dort real vorhandenen anpassen (z. B. `db_session`, `sample_user`). Ein `tenant_user` mit `weekly_hours>0`, `work_days_per_week=5`, `track_hours=True` und einem Montag–Freitag-Arbeitstag (2026-03-02..04 sind Mo–Mi).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_calculation_child_sick.py -v </dev/null`
Expected: FAIL — `AttributeError: module 'calculation_service' has no attribute 'child_sick_cap'`.

- [ ] **Step 3: Implement**

`backend/app/services/calculation_service.py` — Imports prüfen (`settings_service` importieren, falls noch nicht: `from app.services import settings_service`). Nach `absence_days` ergänzen:

```python
def child_sick_cap(db: Session, user: User) -> int:
    """#376 §45 SGB V: persönlicher Kind-krank-Jahresanspruch in Tagen.
    per-MA-Feld → Tenant-Setting child_sick_days_default → 15."""
    if user.child_sick_days_per_year is not None:
        return int(user.child_sick_days_per_year)
    return settings_service.get_int_setting(db, "child_sick_days_default", user.tenant_id, 15)


def child_sick_days_used(db: Session, user: User, year: int) -> Decimal:
    """#376: tagebasierte Summe (Tagesprinzip) der Kind-krank-Absencen im
    Kalenderjahr — nur Absencen, deren Grund tracks_child_sick_limit trägt.
    Beschäftigungsfenster wird respektiert. Zählregel identisch zu absence_days."""
    rows = (
        db.query(Absence)
        .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
        .filter(
            Absence.tenant_id == user.tenant_id,          # F-026
            Absence.user_id == user.id,
            AbsenceReason.tracks_child_sick_limit.is_(True),
            Absence.date >= date(year, 1, 1),
            Absence.date <= date(year, 12, 31),
        )
        .all()
    )
    windowed = [a for a in rows if _within_employment_window(user, a.date)]
    return absence_days(db, user, windowed)
```

> `Absence`, `AbsenceReason`, `date`, `Decimal`, `Session`, `User` müssen im Modul importiert sein (die meisten sind es bereits — fehlende oben ergänzen).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_calculation_child_sick.py -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calculation_service.py backend/tests/test_calculation_child_sick.py
git commit -m "feat(#376): child_sick_cap + child_sick_days_used (tagebasiert, employment-window)"
```

---

## Task 7: Weiche Warnung in `create_absence`

**Files:**
- Modify: `backend/app/routers/absences.py`
- Test: `backend/tests/test_child_sick_warning.py` (neu)

**Interfaces:**
- Consumes: `calculation_service.child_sick_cap`, `calculation_service.child_sick_days_used`, die aufgelöste `reason`-Variable in `create_absence`
- Produces: bei Kind-krank-Buchung über Cap → `warnings`-Eintrag `CHILD_SICK_LIMIT: <text>` auf den erzeugten `AbsenceResponse`-Rows; Status bleibt 201

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_child_sick_warning.py
from datetime import date


def _activate_kind_krank(client, admin_headers):
    return client.post("/admin/absence-reasons", headers=admin_headers,
                       json={"name": "Kind krank", "base_behavior": "unpaid_free",
                             "tracks_child_sick_limit": True}).json()["id"]


def test_child_sick_over_cap_warns_but_books(client, admin_headers, employee_user):
    # Cap auf 1 Tag setzen
    client.put(f"/admin/users/{employee_user.id}", headers=admin_headers,
               json={"child_sick_days_per_year": 1})
    reason_id = _activate_kind_krank(client, admin_headers)
    # 1. Tag: unter Cap → keine Warnung
    r1 = client.post("/absences/", headers=admin_headers, json={
        "user_id": str(employee_user.id), "date": "2026-03-02", "type": "other",
        "hours": 8, "reason_id": reason_id})
    assert r1.status_code == 201
    assert not any("CHILD_SICK_LIMIT" in w for a in r1.json() for w in a["warnings"])
    # 2. Tag: über Cap (1) → Warnung, aber gebucht (201)
    r2 = client.post("/absences/", headers=admin_headers, json={
        "user_id": str(employee_user.id), "date": "2026-03-03", "type": "other",
        "hours": 8, "reason_id": reason_id})
    assert r2.status_code == 201
    assert any("CHILD_SICK_LIMIT" in w for a in r2.json() for w in a["warnings"])
```

> Fixtures an conftest anpassen. `employee_user` = MA im selben Tenant wie `admin_headers`, Mo–Fr-Arbeitstage.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_child_sick_warning.py -v </dev/null`
Expected: FAIL — `KeyError: 'warnings'` (Feld leer/nicht gesetzt) bzw. keine Warnung.

- [ ] **Step 3: Implement**

`backend/app/routers/absences.py`:
1. Import ergänzen (oben): `from app.services import calculation_service`.
2. Direkt VOR `return created_absences` (Ende `create_absence`) den Warn-Block einfügen:

```python
    # #376: weiche (nicht blockierende) §45-SGB-V-Warnung. Wenn der aufgelöste
    # Grund gegen das Kind-krank-Limit zählt und die Jahres-Summe (inkl. der eben
    # gebuchten Tage) den persönlichen Cap überschreitet, hänge einen Hinweis an
    # die erzeugten Rows. Die Buchung bleibt bestehen (der Fehltag muss erfassbar
    # sein, auch wenn die Krankenkasse nicht mehr zahlt).
    child_sick_warnings: list[str] = []
    if reason_id is not None and getattr(reason, "tracks_child_sick_limit", False):
        cap = calculation_service.child_sick_cap(db, target_user)
        used = calculation_service.child_sick_days_used(db, target_user, absence_data.date.year)
        if used > cap:
            child_sick_warnings.append(
                f"CHILD_SICK_LIMIT: Kind-krank-Anspruch überschritten "
                f"({used:.1f} von {cap} Tagen {absence_data.date.year} verbraucht, §45 SGB V)."
            )
    for a in created_absences:
        a.warnings = child_sick_warnings

    return created_absences
```

> `reason` und `reason_id` sind aus der #312-Auflösung (Zeile ~307–309) im Scope. `target_user` ist der MA, für den gebucht wird (bei Selbstbuchung == `current_user`). Setzt ein transientes Attribut auf die ORM-Rows; `AbsenceResponse.warnings` (Task 3) serialisiert es. Bei mehreren Tagen im Range trägt jede Row dieselbe (deduplizierte) Warnung — das Frontend dedupt (Task 12).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_child_sick_warning.py -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/absences.py backend/tests/test_child_sick_warning.py
git commit -m "feat(#376): soft child-sick limit warning in create_absence"
```

---

## Task 8: Weiche Warnung im CR-Genehmigungspfad

**Files:**
- Modify: `backend/app/routers/admin_change_requests.py`
- Test: `backend/tests/test_child_sick_warning.py`

**Interfaces:**
- Consumes: `calculation_service.child_sick_cap` / `child_sick_days_used`; `cr.proposed_reason_id`; vorhandene `cr_response.warnings`-Liste
- Produces: `CHILD_SICK_LIMIT`-Eintrag in `cr_response.warnings` bei CR-Genehmigung einer Kind-krank-Absence über Cap

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_child_sick_warning.py (Ergänzung)
def test_child_sick_warning_in_cr_approval(client, admin_headers, employee_headers, employee_user):
    client.put(f"/admin/users/{employee_user.id}", headers=admin_headers,
               json={"child_sick_days_per_year": 0})  # Cap 0 → jede Buchung über Limit
    reason_id = client.post("/admin/absence-reasons", headers=admin_headers,
                            json={"name": "Kind krank", "base_behavior": "unpaid_free",
                                  "tracks_child_sick_limit": True}).json()["id"]
    # MA stellt Absence-Änderungsantrag (entry_kind=absence, CREATE) mit dem Grund
    cr = client.post("/change-requests", headers=employee_headers, json={
        "entry_kind": "absence", "action": "create", "date": "2026-03-02",
        "proposed_type": "other", "proposed_hours": 8, "proposed_reason_id": reason_id,
    }).json()
    resp = client.post(f"/admin/change-requests/{cr['id']}/review", headers=admin_headers,
                       json={"decision": "approved"})
    assert resp.status_code == 200
    assert any("CHILD_SICK_LIMIT" in w for w in resp.json()["warnings"])
```

> Payload-Feldnamen (`entry_kind`, `action`, `proposed_*`, Review-Body) an die realen CR-Schemas/Router anpassen — im Router-Code `admin_change_requests.py` / `change_requests.py` gegenprüfen.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_child_sick_warning.py::test_child_sick_warning_in_cr_approval -v </dev/null`
Expected: FAIL — keine `CHILD_SICK_LIMIT`-Warnung.

- [ ] **Step 3: Implement**

`backend/app/routers/admin_change_requests.py`, im `review_change_request`, im CREATE-Zweig für `entry_kind == "absence"` — nach dem Materialisieren der Absence und dem #314-Resplit-Trigger, VOR `return cr_response` (bei der bestehenden `cr_response.warnings`-Befüllung, ~Zeile 811/827) ergänzen:

```python
        # #376: weiche Kind-krank-Limit-Warnung (spiegelt create_absence)
        if getattr(cr, "proposed_reason_id", None) is not None:
            _cs_reason = db.query(AbsenceReason).filter(
                AbsenceReason.id == cr.proposed_reason_id,
                AbsenceReason.tenant_id == cr.tenant_id,  # F-026
            ).first()
            if _cs_reason is not None and _cs_reason.tracks_child_sick_limit:
                _cap = calculation_service.child_sick_cap(db, target_user)
                _used = calculation_service.child_sick_days_used(db, target_user, cr.date.year)
                if _used > _cap:
                    cr_response.warnings.append(
                        f"CHILD_SICK_LIMIT: Kind-krank-Anspruch überschritten "
                        f"({_used:.1f} von {_cap} Tagen {cr.date.year} verbraucht, §45 SGB V)."
                    )
```

> `AbsenceReason` und `calculation_service` importieren, falls nicht vorhanden. `target_user` = MA des CR (im Review-Code bereits als Variable vorhanden; sonst `db.query(User).filter(User.id == cr.user_id, ...)`). `cr.date` = Zieldatum der Absence (Feldname im CR-Model prüfen, ggf. `cr.proposed_date`/`cr.entry_date`).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_child_sick_warning.py -v </dev/null`
Expected: PASS (beide Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_change_requests.py backend/tests/test_child_sick_warning.py
git commit -m "feat(#376): soft child-sick limit warning in CR approval path"
```

---

## Task 9: `users-overview` zeigt Kind-krank Verbrauch/Cap (nice-to-have)

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`users-overview`-Endpoint)
- Modify: zugehöriges Response-Schema (im selben Router oder `app/schemas/user.py`)
- Test: `backend/tests/test_cross_tenant_api.py` oder `test_users_overview.py`

**Interfaces:**
- Produces: pro MA in der Overview `child_sick_used: float`, `child_sick_cap: int`

- [ ] **Step 1: Write the failing test**

```python
def test_users_overview_includes_child_sick(client, admin_headers, employee_user):
    client.put(f"/admin/users/{employee_user.id}", headers=admin_headers,
               json={"child_sick_days_per_year": 12})
    rows = client.get("/admin/users-overview", headers=admin_headers).json()
    row = next(r for r in rows if r["id"] == str(employee_user.id))
    assert row["child_sick_cap"] == 12
    assert row["child_sick_used"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend pytest tests/test_users_overview.py::test_users_overview_includes_child_sick -v </dev/null`
Expected: FAIL — Keys fehlen.

- [ ] **Step 3: Implement**

Im `users-overview`-Endpoint pro MA ergänzen (nutzt Task-6-Helper; das Response-Schema um `child_sick_used: float` + `child_sick_cap: int` erweitern):

```python
        "child_sick_cap": calculation_service.child_sick_cap(db, u),
        "child_sick_used": float(calculation_service.child_sick_days_used(db, u, today_local().year)),
```

> `today_local` aus dem im Router genutzten Zeit-Helper. Struktur (dict vs. Pydantic-Model) an den bestehenden Overview-Code anpassen.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose cp backend/app backend:/app/ && docker compose exec -T backend pytest tests/test_users_overview.py::test_users_overview_includes_child_sick -v </dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_users.py backend/app/schemas/user.py backend/tests/test_users_overview.py
git commit -m "feat(#376): child-sick used/cap in users-overview"
```

---

## Task 10: Frontend API + Types

**Files:**
- Modify: `frontend/src/api/absenceReasons.ts`
- Modify: `frontend/src/types/user.ts` + `frontend/src/api/users.ts`
- Test: `frontend/src/api/absenceReasons.test.ts` (neu)

**Interfaces:**
- Produces: `AbsenceReasonBehavior` inkl. `'unpaid_free'`; `BEHAVIOR_LABELS`/`BEHAVIOR_HINTS` erweitert; `AbsenceReason.tracks_child_sick_limit`; `createReason`-Body um `tracks_child_sick_limit`; `CHILD_SICK_PRESETS`-Konstante; User-Typ um `child_sick_days_per_year`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/absenceReasons.test.ts
import { describe, it, expect } from 'vitest';
import { BEHAVIOR_LABELS, ABSENCE_REASON_PRESETS } from './absenceReasons';

describe('absence reason presets', () => {
  it('exposes unpaid_free label', () => {
    expect(BEHAVIOR_LABELS.unpaid_free).toBe('Unbezahlt frei');
  });
  it('ships a Kind-krank preset that tracks the limit', () => {
    const kk = ABSENCE_REASON_PRESETS.find((p) => p.name === 'Kind krank');
    expect(kk).toBeTruthy();
    expect(kk!.base_behavior).toBe('unpaid_free');
    expect(kk!.tracks_child_sick_limit).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/absenceReasons.test.ts --pool=threads`
Expected: FAIL — `unpaid_free`/`ABSENCE_REASON_PRESETS` fehlen.

- [ ] **Step 3: Implement**

`frontend/src/api/absenceReasons.ts`:

```ts
export type AbsenceReasonBehavior = 'worked' | 'paid_free' | 'overtime_comp' | 'unpaid_free';

export interface AbsenceReason {
  id: string;
  name: string;
  color: string | null;
  base_behavior: AbsenceReasonBehavior;
  is_active: boolean;
  sort_order: number;
  tracks_child_sick_limit: boolean;   // #376
}

export const BEHAVIOR_LABELS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Zählt als gearbeitet',
  paid_free: 'Bezahlt frei',
  overtime_comp: 'Überstundenabbau',
  unpaid_free: 'Unbezahlt frei',      // #376
};

export const BEHAVIOR_HINTS: Record<AbsenceReasonBehavior, string> = {
  worked: 'Wird als Arbeitszeit gutgeschrieben (z. B. Berufsschule für Azubis) — keine Stundenverluste.',
  paid_free: 'Bezahlt frei: Soll wird auf 0 gesetzt, saldoneutral, kein Urlaubsabzug.',
  overtime_comp: 'Überstundenabbau: das Überstundenkonto sinkt um das Tagessoll.',
  unpaid_free: 'Unbezahlt frei: Soll auf 0, saldoneutral, kein Urlaubsabzug, aber unbezahlt (Lohn gekürzt) — z. B. Kind krank (§45 SGB V).',  // #376
};

export interface AbsenceReasonPreset {
  name: string;
  color: string;
  base_behavior: AbsenceReasonBehavior;
  tracks_child_sick_limit: boolean;
}

// #376: kuratierte Vorlagen zum 1-Klick-Aktivieren (kein DB-Seed). Verhalten
// je Grund im Betrieb frei änderbar — dies sind sinnvolle Defaults.
export const ABSENCE_REASON_PRESETS: AbsenceReasonPreset[] = [
  { name: 'Kind krank', color: '#e67e22', base_behavior: 'unpaid_free', tracks_child_sick_limit: true },
  { name: 'Todesfall naher Angehöriger', color: '#7f8c8d', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Eigene Hochzeit', color: '#d35400', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Geburt eines Kindes', color: '#16a085', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Umzug (betrieblich)', color: '#2980b9', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Arztbesuch (unvermeidbar)', color: '#8e44ad', base_behavior: 'paid_free', tracks_child_sick_limit: false },
  { name: 'Pflege naher Angehöriger', color: '#c0392b', base_behavior: 'unpaid_free', tracks_child_sick_limit: false },
];
```

`createReason`-Body-Typ erweitern:

```ts
export const createReason = (body: {
  name: string;
  color?: string | null;
  base_behavior: AbsenceReasonBehavior;
  sort_order?: number;
  tracks_child_sick_limit?: boolean;   // #376
}) => apiClient.post<AbsenceReason>(ADMIN, body).then((r) => r.data);
```

`frontend/src/types/user.ts` — im User-/UserForm-Typ ergänzen (an vorhandene Optional-Felder anlehnen):

```ts
  child_sick_days_per_year?: number | null;   // #376
```

Sicherstellen, dass `updateUser`/`createUser` in `frontend/src/api/users.ts` das Feld durchreichen (falls die Payload getippt ist, dort ebenfalls ergänzen).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/absenceReasons.test.ts --pool=threads`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/absenceReasons.ts frontend/src/types/user.ts frontend/src/api/users.ts frontend/src/api/absenceReasons.test.ts
git commit -m "feat(#376): frontend api types + reason presets"
```

---

## Task 11: `AbsenceReasonsManager` — Verhalten + Preset-Katalog

**Files:**
- Modify: `frontend/src/components/AbsenceReasonsManager.tsx`
- Test: `frontend/src/components/AbsenceReasonsManager.test.tsx` (neu)

**Interfaces:**
- Consumes: `ABSENCE_REASON_PRESETS`, `BEHAVIORS` inkl. `unpaid_free`, `createReason`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/AbsenceReasonsManager.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AbsenceReasonsManager from './AbsenceReasonsManager';

vi.mock('../api/absenceReasons', async (orig) => {
  const actual = await orig<typeof import('../api/absenceReasons')>();
  return { ...actual, listReasons: vi.fn().mockResolvedValue([]) };
});

describe('AbsenceReasonsManager', () => {
  it('offers the Kind-krank preset', async () => {
    render(<AbsenceReasonsManager />);
    expect(await screen.findByText('Kind krank')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AbsenceReasonsManager.test.tsx --pool=threads`
Expected: FAIL — „Kind krank" nicht im DOM.

- [ ] **Step 3: Implement**

`frontend/src/components/AbsenceReasonsManager.tsx`:
1. `BEHAVIORS` erweitern:

```tsx
const BEHAVIORS: AbsenceReasonBehavior[] = ['worked', 'paid_free', 'overtime_comp', 'unpaid_free'];
```

2. `tracks_child_sick_limit`-State für das Anlege-Formular hinzufügen und im `createReason`-Call mitschicken:

```tsx
  const [tracksChildSick, setTracksChildSick] = useState(false);
  // …im Submit:
  await api.createReason({ name: name.trim(), base_behavior: behavior, color, tracks_child_sick_limit: tracksChildSick });
```

3. Preset-Sektion oberhalb der Liste rendern (bereits aktivierte per Name ausblenden). `reasons` ist der geladene State:

```tsx
import { ABSENCE_REASON_PRESETS } from '../api/absenceReasons';
// …
      <div className="mb-4">
        <p className="text-xs font-medium text-gray-600 mb-1">Vorlagen (1-Klick aktivieren)</p>
        <div className="flex flex-wrap gap-2">
          {ABSENCE_REASON_PRESETS.filter(
            (p) => !reasons.some((r) => r.name === p.name),
          ).map((p) => (
            <button
              key={p.name}
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.createReason({
                    name: p.name, color: p.color, base_behavior: p.base_behavior,
                    tracks_child_sick_limit: p.tracks_child_sick_limit,
                  });
                  await load();   // vorhandener Reload-Callback
                } finally {
                  setBusy(false);
                }
              }}
              className="text-xs px-2 py-1 rounded border"
              style={{ borderColor: p.color, color: p.color }}
            >
              + {p.name}
            </button>
          ))}
        </div>
      </div>
```

> Reload-Funktionsname (`load`) an den in der Komponente vorhandenen anpassen (die `useCallback`/`useEffect`-Ladefunktion). Checkbox für `tracksChildSick` nur zeigen, wenn `behavior === 'unpaid_free'` (kosmetisch).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/AbsenceReasonsManager.test.tsx --pool=threads`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AbsenceReasonsManager.tsx frontend/src/components/AbsenceReasonsManager.test.tsx
git commit -m "feat(#376): reason manager — unpaid_free + preset catalog"
```

---

## Task 12: Warn-Anzeige (arbzgWarnings-Case + Buchungs-Toast)

**Files:**
- Modify: `frontend/src/utils/arbzgWarnings.ts`
- Modify: `frontend/src/pages/admin/AdminAbsences.tsx`
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`
- Test: `frontend/src/utils/arbzgWarnings.test.ts` (existierend erweitern; sonst neu)

**Interfaces:**
- Consumes: `showArbzgWarnings(toast, warnings)`; die `warnings`-Arrays der `POST /absences/`-Response-Rows

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/utils/arbzgWarnings.test.ts
import { describe, it, expect, vi } from 'vitest';
import { showArbzgWarnings } from './arbzgWarnings';

describe('CHILD_SICK_LIMIT warning', () => {
  it('surfaces the detail text', () => {
    const toast = { warning: vi.fn() };
    showArbzgWarnings(toast, ['CHILD_SICK_LIMIT: Kind-krank-Anspruch überschritten (2.0 von 1 Tagen 2026 verbraucht, §45 SGB V).']);
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('Kind-krank-Anspruch überschritten'));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/arbzgWarnings.test.ts --pool=threads`
Expected: FAIL — Default-Case liefert generischen Text statt Detail (bzw. `toContain` schlägt fehl).

- [ ] **Step 3: Implement**

`frontend/src/utils/arbzgWarnings.ts` — im `switch (code)` einen Case ergänzen:

```ts
      case 'CHILD_SICK_LIMIT':
        // #376 §45 SGB V: weiche Warnung — Buchung ist durchgegangen.
        toast.warning(detail ?? 'Kind-krank-Jahresanspruch überschritten (§45 SGB V).');
        break;
```

In `AdminAbsences.tsx` und `AbsenceCalendarPage.tsx` nach erfolgreichem `POST /absences/` die Row-Warnungen sammeln + anzeigen (`res.data` ist das `AbsenceResponse[]`):

```ts
import { showArbzgWarnings } from '../../utils/arbzgWarnings';   // Pfad je Datei
// …nach dem erfolgreichen create:
const warns = [...new Set((res.data ?? []).flatMap((a: { warnings?: string[] }) => a.warnings ?? []))];
showArbzgWarnings(toast, warns);
```

> Import-Pfad zu `arbzgWarnings` je nach Dateitiefe (`../utils/…` in `pages/`, `../../utils/…` in `pages/admin/`). `toast` = vorhandener `useToast()`-Hook der jeweiligen Seite.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/arbzgWarnings.test.ts --pool=threads`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/arbzgWarnings.ts frontend/src/pages/admin/AdminAbsences.tsx frontend/src/pages/AbsenceCalendarPage.tsx frontend/src/utils/arbzgWarnings.test.ts
git commit -m "feat(#376): surface CHILD_SICK_LIMIT warning after booking"
```

---

## Task 13: UserForm — Kind-krank-Tage/Jahr + Settings — Tenant-Default

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx`
- Modify: `frontend/src/pages/admin/Settings.tsx`
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx` (neu oder vorhandenes erweitern)

**Interfaces:**
- Consumes: User-Typ `child_sick_days_per_year`; Setting `child_sick_days_default`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/admin/users/UserForm.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import UserForm from './UserForm';

describe('UserForm', () => {
  it('renders the child-sick days field', () => {
    render(<UserForm /* vorhandene Pflicht-Props/mocks wie in Nachbar-Tests */ />);
    expect(screen.getByLabelText(/Kind-krank-Tage/i)).toBeInTheDocument();
  });
});
```

> Props/Mocks aus vorhandenen UserForm-nahen Tests übernehmen; existiert kein Test, ein minimales Render-Setup nach dem Muster der anderen `pages/admin/users`-Tests bauen.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/admin/users/UserForm.test.tsx --pool=threads`
Expected: FAIL — Feld nicht gefunden.

- [ ] **Step 3: Implement**

`UserForm.tsx` — bei den optionalen Zahlenfeldern (nahe `vacation_days`) ergänzen (Platzhalter = Tenant-Default-Semantik „leer = Standard"):

```tsx
<label className="block text-sm font-medium mb-1" htmlFor="child_sick_days_per_year">
  Kind-krank-Tage/Jahr (§45 SGB V)
</label>
<input
  id="child_sick_days_per_year"
  type="number"
  min={0}
  max={70}
  value={form.child_sick_days_per_year ?? ''}
  placeholder="Standard (Einstellungen)"
  onChange={(e) =>
    setForm({
      ...form,
      child_sick_days_per_year: e.target.value === '' ? null : Number(e.target.value),
    })
  }
  className="w-full border rounded px-2 py-1"
/>
```

> `form`/`setForm` an das reale State-Handling der UserForm anpassen (Feldname im Form-State + im submit-Payload durchreichen).

`Settings.tsx` — beim `child_sick_days_default`-Setting (analog zu `work_window_grace_minutes`) ein Zahlenfeld ergänzen, das per `PUT /admin/settings/child_sick_days_default` speichert. Label: „Kind-krank-Standardanspruch (Tage/Jahr)", Default-Hinweis „15".

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/admin/users/UserForm.test.tsx --pool=threads`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/users/UserForm.tsx frontend/src/pages/admin/Settings.tsx frontend/src/pages/admin/users/UserForm.test.tsx
git commit -m "feat(#376): UserForm child-sick field + Settings tenant default"
```

---

## Task 14: Doku (Handbuch, In-App-Hilfe, CLAUDE.md)

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md`
- Modify: `frontend/src/components/DocViewer.tsx` (hardcoded `handbuchAdminSections`)
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-07-07-kind-krank-absence-reasons-design.md` (Status → implementiert)

- [ ] **Step 1: Handbuch + In-App-Hilfe**

In `HANDBUCH-ADMIN.md` und dem entsprechenden Abschnitt in `DocViewer.tsx` (`handbuchAdminSections`) einen Abschnitt „Kind krank & Sonderurlaub-Gründe" ergänzen: Vorlagen aktivieren, Verhalten (unbezahlt frei = Soll 0, saldoneutral, kein Urlaub, Lohn gekürzt), per-MA-Anspruch + Tenant-Default, weiche §45-Warnung. **Beide Stellen pflegen** (In-App-Hilfe ist hardcoded, nicht aus `docs/` geladen).

- [ ] **Step 2: CLAUDE.md-Regel ergänzen**

Unter „Kritische Regeln" eine Zeile ergänzen (Muster wie #312/#314):

> **#376 Kind krank / unbezahlt-frei-Gründe:** `AbsenceReasonBehavior.UNPAID_FREE → AbsenceType.OTHER` (Soll→0, Ist+=0, saldo-neutral, kein Urlaub, **unbezahlt**). Marker `AbsenceReason.tracks_child_sick_limit` + per-MA `User.child_sick_days_per_year` (Default `child_sick_days_default`-Setting, sonst 15) treiben `calculation_service.child_sick_days_used` (tagebasiert, Beschäftigungsfenster). Weiche `CHILD_SICK_LIMIT`-Warnung in **zwei** Buchungspfaden — `create_absence` UND `admin_change_requests.review_change_request` — NIE blockierend (Fehltag muss erfassbar bleiben). Neue Buchungsflächen → Warnung mitziehen. DSGVO/Masking schon via #312.

- [ ] **Step 3: Commit**

```bash
git add docs/handbuch/HANDBUCH-ADMIN.md frontend/src/components/DocViewer.tsx CLAUDE.md docs/superpowers/specs/2026-07-07-kind-krank-absence-reasons-design.md
git commit -m "docs(#376): Kind-krank handbook, in-app help, CLAUDE.md rule"
```

---

## Task 15: E2E (Playwright)

**Files:**
- Create: `e2e/tests/child-sick.spec.ts`

**Interfaces:**
- Consumes: laufende App; Admin-Login; Fixtures aus `e2e/fixtures/test-data.fixture.ts`

- [ ] **Step 1: Write the E2E test**

```ts
// e2e/tests/child-sick.spec.ts
import { test, expect } from '@playwright/test';
// Login-Helper/Fixtures wie in bestehenden Specs.

test('Kind-krank preset activate → book over cap → soft warning, day booked', async ({ page }) => {
  // 1) als Admin einloggen, Einstellungen → Abwesenheitsgründe
  // 2) Preset "Kind krank" aktivieren (button "+ Kind krank")
  // 3) für einen MA child_sick_days_per_year = 0 setzen (UserForm)
  // 4) Abwesenheit mit Grund "Kind krank" für einen Werktag buchen
  //    (weekdayFromNow(n) aus helpers/date.helper.ts, NICHT daysFromNow)
  // 5) erwarte den weichen Warn-Toast "Kind-krank-Anspruch überschritten"
  // 6) erwarte, dass die Abwesenheit trotzdem in der Liste/Kalender erscheint
  await expect(page.locator('main').getByText(/Kind-krank-Anspruch überschritten/)).toBeVisible();
});
```

> Konkrete Selektoren/Login an die bestehenden Specs anlehnen. Cleanup über die `createAbsence`-Fixture (trackt IDs + teardown-DELETE). Werktag über `weekdayFromNow` (UTC-Rollover-Falle).

- [ ] **Step 2: Run (mit erhöhten Auth-Rate-Limits)**

```bash
# .env: LOGIN_RATE_LIMIT=10000/minute REFRESH_RATE_LIMIT=10000/minute + docker compose up -d backend
cd e2e && npx playwright test child-sick.spec.ts
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add e2e/tests/child-sick.spec.ts
git commit -m "test(#376): e2e child-sick preset + soft limit warning"
```

---

## Task 16: Volle Regression + PR

- [ ] **Step 1: Backend-Suite (TZ + Postgres-Ignores)**

```bash
docker compose cp backend/app backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py -q </dev/null
docker compose exec -T backend pytest tests/test_tenant_rls.py tests/test_cross_tenant_api.py -q </dev/null
```
Expected: grün.

- [ ] **Step 2: Frontend tsc + vitest + build**

```bash
cd frontend
npx tsc --noEmit
npx vitest run --pool=threads
npm run build
```
Expected: grün.

- [ ] **Step 3: Local-CI (optional, Pool ggf. setzen)**

```bash
bash scripts/local-ci.sh
```

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/376-kind-krank
gh pr create --title '#376 "Kind krank" + Sonderurlaub-Gründe' --body-file - <<'EOF'
Schließt #376.

- neues base_behavior `unpaid_free` → AbsenceType.OTHER (unbezahlt frei)
- Preset-Katalog (1-Klick aktivieren; Kind krank, Todesfall, Hochzeit, …)
- Kind-krank-Zähler (tagebasiert, §45 SGB V) + weiche Limit-Warnung in create_absence UND CR-Genehmigung
- per-MA `child_sick_days_per_year` + Tenant-Setting `child_sick_days_default` (Default 15)
- Migration 061; DSGVO-Masking bereits via #312

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

## Self-Review

**Spec-Abdeckung:**
- Neues Verhalten `unpaid_free → OTHER` → Task 1 ✓
- Preset-Katalog → Task 10 (Daten) + Task 11 (UI) ✓
- Zähler tagebasiert → Task 6 ✓
- per-MA-Anspruch + Tenant-Default → Task 2/3/5/13 ✓
- weiche Warnung, beide Buchungspfade → Task 7 (create_absence) + Task 8 (CR) ✓
- UI (Settings/UserForm/Buchung) → Task 11/12/13 ✓
- Admin-Übersicht (nice-to-have) → Task 9 ✓
- Migration → Task 2 ✓
- DSGVO (schon via #312) → keine neue Arbeit (Task 14 dokumentiert) ✓
- Tests (Backend/Vitest/E2E) → über alle Tasks + Task 15/16 ✓

**Placeholder-Scan:** Keine TBD/TODO. Fixture-/Feldnamen-Anpassungen sind explizit als „an conftest/reales Schema anpassen" markiert, mit Code-Anker (Zeilen/Funktionsnamen) statt vager Anweisung.

**Typ-Konsistenz:** `tracks_child_sick_limit` (bool) und `child_sick_days_per_year` (int|None) durchgehend gleich benannt in Model/Schema/API/Frontend; `child_sick_cap`/`child_sick_days_used`/`get_int_setting` konsistent in Producer- (Task 5/6) und Consumer-Tasks (7/8/9); Warncode `CHILD_SICK_LIMIT` identisch in Backend (7/8) und Frontend (12).
