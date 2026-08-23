# Schichtplan-Darstellung, Freigabe und Druck (#443) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Admin kann einen Schichtplan für Mitarbeitende freigeben, bevor er gilt, ihn als PDF-Aushang drucken, je Einteilung einen Hinweis hinterlegen — und das Wochenraster bricht Namen um, statt sie abzuschneiden.

**Architecture:** Zwei neue Spalten (`shift_plans.visible_to_employees`, `shift_slots.note`) über Migration 070. Die Sichtbarkeitsregel zieht aus zwei Inline-Kopien in **einen** Service-Helfer. Der PDF-Export ist ein eigenes Modul, das ausschließlich das Dict von `_build_plan_detail` rendert und keinen Datenbankzugriff hat. Im Frontend wächst der Slot-Block über `minHeight` im Browser; eine reine Schätzfunktion steuert nur die Markierung „reicht über das Zeitfenster hinaus".

**Tech Stack:** FastAPI / SQLAlchemy / Alembic / reportlab (Backend, Python 3.12) · React 18 + TypeScript + Tailwind, vitest + React Testing Library (Frontend) · Playwright (E2E) · PostgreSQL 18 in Docker

**Spec:** `docs/superpowers/specs/2026-08-23-443-schichtplan-darstellung-design.md`

## Global Constraints

Diese Regeln gelten für **jede** Aufgabe. Sie stehen so in `CLAUDE.md`.

- **Branch:** `feat/443-schichtplan-darstellung` ist bereits angelegt und ausgecheckt. NICHT nach `master` committen, NICHT pushen, KEINEN PR öffnen — das macht der Mensch.
- **Backend-Container ist gebaut, kein Host-Volume.** Vor jedem `pytest` den Code hineinkopieren, sonst läuft der alte Stand:
  ```bash
  cd /home/manuel/claude/praxiszeit
  docker compose cp backend/app backend:/app/
  docker compose cp backend/tests backend:/app/
  ```
  `docker compose cp` verlangt den **Service**-Namen (`backend:`), nicht den Container-Namen, und löst Host-Pfade **relativ zum cwd** auf — deshalb immer aus dem Repo-Wurzelverzeichnis.
- **Backend-Test ausführen:**
  ```bash
  docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/<datei> -q </dev/null
  ```
  `-e TZ=Europe/Berlin` verhindert die Mitternachts-Flakes, `</dev/null` verhindert, dass ein Heredoc-stdin gefressen wird. **Einen laufenden `docker compose exec` NICHT abbrechen** — der Prozess im Container läuft weiter und zwei pytest-Läufe teilen sich `/app/test.db`. Bei Verdacht: `pgrep -af pytest`, Reste killen, `docker compose exec -T backend rm -f /app/test.db </dev/null`.
- **Volle Backend-Suite** (nur wo unten ausdrücklich verlangt):
  ```bash
  docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
    --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py </dev/null
  ```
  Ohne beide `--ignore` vergiften die Postgres-Dateien die geteilte SQLite-Engine (~26 Folgefehler).
- **Frontend:** `cd frontend && npx vitest run <datei> --pool=threads` — der Default-`forks`-Pool hängt auf dieser Maschine (60-s-Timeout, „no tests"). Typprüfung: `cd frontend && npx tsc --noEmit`. `npm install` ist NICHT nötig (node_modules liegt vor und ist root-owned).
- **F-026:** Jede Query auf eine mandantenbezogene Tabelle trägt zusätzlich zu RLS einen expliziten `Model.tenant_id == <tid>`-Filter. Die SQLite-Testsuite hat kein RLS — der explizite Filter ist dort die einzige Trennung.
- **Alembic:** Revision-IDs maximal 32 Zeichen. Migration auf dem Host anlegen und committen, **bevor** der Container neu startet. NICHT `python -m alembic` (cwd-Shadowing durch `app/backend/alembic/`).
- **Feature-Flag:** Die gesamte Schichtplanung hängt an der Router-Dependency `require_shift_planning_enabled` (Tenant-Setting `shift_planning_enabled`, Default aus) → jeder neue Endpunkt erbt automatisch 404, wenn das Feature aus ist. Kein eigener Gate-Code nötig.
- **Commits:** Deutsch, aussagekräftig, am Ende jeweils:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
  Sonderzeichen (Klammern, Umlaute, →) brechen bei inline `-m` → immer `git commit -F -` mit Heredoc.
- **Der Pre-Commit-Secret-Scanner** lehnt Datenbank-URLs mit Inline-Passwort ab, auch in Tests und Kommentaren. `--no-verify` ist nicht erlaubt.

---

### Task 1: Migration 070 und Modellspalten

**Files:**
- Create: `backend/alembic/versions/2026_08_23_1200-070_shift_plan_vis_note.py`
- Modify: `backend/app/models/shift_planning.py` (Klasse `ShiftPlan`, Klasse `ShiftSlot`)
- Test: `backend/tests/test_shift_plan_visibility.py` (neu)

**Interfaces:**
- Consumes: nichts (erste Aufgabe)
- Produces:
  - `ShiftPlan.visible_to_employees` — `Column(Boolean, nullable=False, default=False, server_default="false")`
  - `ShiftSlot.note` — `Column(Text, nullable=True)`
  - Alembic-Revision `"070_shift_plan_vis_note"`, `down_revision = "069_weekly_hours_precision"`

- [ ] **Step 1: Write the failing test**

Neue Datei `backend/tests/test_shift_plan_visibility.py`:

```python
"""#443: Freigabe eines Schichtplans für Mitarbeitende (visible_to_employees)
und der Hinweistext je Slot (shift_slots.note).

Die Regel selbst lebt in ``shift_planning_service.is_plan_visible_to`` und wird
von ``list_plans`` und ``get_plan`` gemeinsam genutzt — vor #443 hatte jede der
beiden Stellen ihre eigene Inline-Kopie.
"""
from datetime import time

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan, ShiftSlot, Workstation
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="F", last_name="L", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, creator, name, *, active=False, visible=False):
    p = ShiftPlan(
        tenant_id=DEFAULT_TENANT_ID, name=name, is_active=active,
        visible_to_employees=visible, created_by=creator.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _workstation(db, name):
    w = Workstation(tenant_id=DEFAULT_TENANT_ID, name=name)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def test_plan_defaults_to_not_visible(db, default_tenant):
    """Bestandsverhalten: ohne ausdrückliche Freigabe bleibt ein Plan intern."""
    admin = _user(db, "vis_admin_default", role=UserRole.ADMIN)
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name="Ohne Angabe", created_by=admin.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.visible_to_employees is False


def test_slot_note_is_optional_and_stored(db, default_tenant):
    admin = _user(db, "vis_admin_note", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Plan mit Hinweis")
    ws = _workstation(db, "Tresen")

    without = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
    )
    db.add(without)
    db.commit()
    db.refresh(without)
    assert without.note is None

    with_note = ShiftSlot(
        tenant_id=DEFAULT_TENANT_ID, shift_plan_id=plan.id, workstation_id=ws.id,
        weekday=1, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        note="Einarbeitung Azubi",
    )
    db.add(with_note)
    db.commit()
    db.refresh(with_note)
    assert with_note.note == "Einarbeitung Azubi"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py -q </dev/null
```
Erwartet: FAIL mit `TypeError: 'visible_to_employees' is an invalid keyword argument for ShiftPlan`.

- [ ] **Step 3: Modellspalten ergänzen**

In `backend/app/models/shift_planning.py`, Klasse `ShiftPlan`, direkt unter `active_until_date`:

```python
    # #443: ausdrückliche Freigabe für Mitarbeitende. Ein künftiger Plan (etwa
    # der ab September geltende) soll angekündigt werden können, ohne schon zu
    # gelten. Default False hält das Bestandsverhalten unverändert — dort
    # entscheidet weiterhin allein "heute aktiv".
    visible_to_employees = Column(Boolean, nullable=False, default=False, server_default="false")
```

In derselben Datei, Klasse `ShiftSlot`, direkt unter `min_staff`:

```python
    # #443: freier Hinweistext je Einteilung ("Einarbeitung Azubi", "nur
    # Notfall"). Reines Anzeigefeld — es fließt in keine Prüfung und in keine
    # Berechnung ein.
    note = Column(Text, nullable=True)
```

`Boolean` und `Text` sind in dieser Datei bereits importiert.

- [ ] **Step 4: Migration anlegen**

Neue Datei `backend/alembic/versions/2026_08_23_1200-070_shift_plan_vis_note.py`:

```python
"""#443: Schichtplan-Freigabe fuer Mitarbeitende + Hinweistext je Einteilung

``shift_plans.visible_to_employees``
    Bis hierher sahen Mitarbeitende ausschliesslich Plaene, die HEUTE gelten
    (``is_active`` oder das Datumsfenster deckt heute ab). Ein kuenftiger Plan
    liess sich damit nicht ankuendigen. Die Spalte ist die ausdrueckliche
    Freigabe: sie wirkt unabhaengig davon, ob der Plan schon gilt.

    Default ``false``: bestehende Installationen verhalten sich unveraendert,
    ein Entwurf wird nie durch die Migration oeffentlich.

``shift_slots.note``
    Freier Hinweistext je Einteilung ("Einarbeitung Azubi"). Reines
    Anzeigefeld — es fliesst in keine Pruefung und in keine Berechnung ein.
    ``Text`` statt ``String(n)``: der Text steht in keiner Spaltenbreite und
    eine Laengengrenze wuerde ohnehin am Rand (Pydantic ``max_length=500``)
    durchgesetzt, nicht in der Datenbank.

Beide Tabellen sind bereits mandantenbezogen mit RLS-Policy (Migration 053) —
reine Spalten-Ergaenzungen, keine Policy-Aenderung noetig.
"""
from alembic import op
import sqlalchemy as sa

revision = "070_shift_plan_vis_note"
down_revision = "069_weekly_hours_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shift_plans",
        sa.Column(
            "visible_to_employees",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("shift_slots", sa.Column("note", sa.Text(), nullable=True))


def downgrade():
    """Verlustfrei fuer alles, was das Alt-Modell kannte. Verloren gehen nur die
    Freigabe-Flags und die Hinweistexte — beides gab es vor dieser Migration
    nicht."""
    op.drop_column("shift_slots", "note")
    op.drop_column("shift_plans", "visible_to_employees")
```

Die Revision-ID ist 25 Zeichen und bleibt damit unter der 32-Zeichen-Grenze von `version_num`.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py -q </dev/null
```
Erwartet: 2 passed.

- [ ] **Step 6: Migration gegen echtes PostgreSQL fahren**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/alembic backend:/app/
docker compose restart backend
sleep 15
docker compose logs backend --tail 40 | grep -i "070\|alembic\|error"
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d shift_plans" </dev/null | grep visible_to_employees
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d shift_slots" </dev/null | grep note
```
Erwartet: beide Spalten vorhanden, keine Fehler im Log. SQLite versteckt Spaltentypen — dieser Schritt darf nicht übersprungen werden.

- [ ] **Step 7: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/alembic/versions/2026_08_23_1200-070_shift_plan_vis_note.py \
        backend/app/models/shift_planning.py backend/tests/test_shift_plan_visibility.py
git commit -F - <<'EOF'
feat(#443): Migration 070 — Plan-Freigabe und Hinweistext je Einteilung

shift_plans.visible_to_employees (Default false) macht die ausdrueckliche
Freigabe eines noch nicht geltenden Plans moeglich; shift_slots.note nimmt
den freien Hinweis je Einteilung auf. Beide Spalten sind reine Anzeige- bzw.
Sichtbarkeitsfelder und fliessen in keine Berechnung ein.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Sichtbarkeitsregel in einen gemeinsamen Helfer ziehen

**Files:**
- Modify: `backend/app/services/shift_planning_service.py` (neue Funktion nach `is_plan_active_on`)
- Modify: `backend/app/routers/shift_planning.py` (`list_plans`, `get_plan`)
- Test: `backend/tests/test_shift_plan_visibility.py` (erweitern)

**Interfaces:**
- Consumes: `ShiftPlan.visible_to_employees` aus Task 1
- Produces: `shift_planning_service.is_plan_visible_to(plan, d: date, is_admin: bool) -> bool`

- [ ] **Step 1: Write the failing test**

An `backend/tests/test_shift_plan_visibility.py` anhängen:

```python
import pytest
from fastapi import HTTPException

from app.routers.shift_planning import get_plan, list_plans
from app.services import shift_planning_service
from app.services.timezone_service import today_local


def test_helper_admin_sees_everything(db, default_tenant):
    admin = _user(db, "vis_helper_admin", role=UserRole.ADMIN)
    draft = _plan(db, admin, "Reiner Entwurf")
    assert shift_planning_service.is_plan_visible_to(draft, today_local(), True) is True


def test_helper_released_plan_is_visible_without_being_active(db, default_tenant):
    admin = _user(db, "vis_helper_rel", role=UserRole.ADMIN)
    released = _plan(db, admin, "Ab September", visible=True)
    assert shift_planning_service.is_plan_active_on(released, today_local()) is False
    assert shift_planning_service.is_plan_visible_to(released, today_local(), False) is True


def test_helper_draft_stays_hidden(db, default_tenant):
    admin = _user(db, "vis_helper_draft", role=UserRole.ADMIN)
    draft = _plan(db, admin, "Nicht freigegeben")
    assert shift_planning_service.is_plan_visible_to(draft, today_local(), False) is False


def test_list_plans_shows_released_future_plan_to_employee(db, default_tenant):
    admin = _user(db, "vis_list_admin", role=UserRole.ADMIN)
    emp = _user(db, "vis_list_emp")
    _plan(db, admin, "Freigegeben", visible=True)
    _plan(db, admin, "Entwurf bleibt weg")

    names = {p["name"] for p in list_plans(db=db, current_user=emp)}
    assert "Freigegeben" in names
    assert "Entwurf bleibt weg" not in names


def test_get_plan_opens_released_plan_for_employee(db, default_tenant):
    admin = _user(db, "vis_get_admin", role=UserRole.ADMIN)
    emp = _user(db, "vis_get_emp")
    released = _plan(db, admin, "Freigegeben zum Oeffnen", visible=True)
    draft = _plan(db, admin, "Entwurf zum Oeffnen")

    assert get_plan(released.id, db=db, current_user=emp)["name"] == "Freigegeben zum Oeffnen"

    with pytest.raises(HTTPException) as exc:
        get_plan(draft.id, db=db, current_user=emp)
    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py -q </dev/null
```
Erwartet: FAIL mit `AttributeError: module 'app.services.shift_planning_service' has no attribute 'is_plan_visible_to'`.

- [ ] **Step 3: Helfer schreiben**

In `backend/app/services/shift_planning_service.py`, direkt **unter** `is_plan_active_on`:

```python
def is_plan_visible_to(plan, d, is_admin: bool) -> bool:
    """#443: Darf dieser Nutzer den Plan sehen?

    Admins sehen jeden Plan ihres Mandanten. Für alle anderen gilt: der Plan ist
    an ``d`` aktiv ODER er wurde ausdrücklich für Mitarbeitende freigegeben.

    Diese Funktion ist die EINZIGE Quelle der Regel. ``list_plans`` und
    ``get_plan`` hatten bis #443 je eine eigene Inline-Kopie — genau das Muster,
    das im Projekt schon mehrfach auseinandergelaufen ist (CR-Genehmigung,
    Feiertags-Guard). Eine neue Lesefläche ruft diesen Helfer, sie baut die
    Bedingung nicht nach.
    """
    if is_admin:
        return True
    return is_plan_active_on(plan, d) or bool(plan.visible_to_employees)
```

- [ ] **Step 4: Beide Aufrufstellen umstellen**

In `backend/app/routers/shift_planning.py`, in `list_plans`, den Block

```python
        active_today = shift_planning_service.is_plan_active_on(p, today)
        if not is_admin and not active_today:
            continue
```

ersetzen durch

```python
        active_today = shift_planning_service.is_plan_active_on(p, today)
        # Fix #7 + #443: Nicht-Admins sehen nur, was heute gilt ODER ausdrücklich
        # freigegeben ist. Die Regel lebt in EINEM Helfer (siehe get_plan).
        if not shift_planning_service.is_plan_visible_to(p, today, is_admin):
            continue
```

`active_today` bleibt stehen — es wird weiterhin in das Antwort-Dict geschrieben.

In `get_plan` den Block

```python
    if not is_admin and not shift_planning_service.is_plan_active_on(plan, today_local()):
        raise HTTPException(status_code=404, detail="Schichtplan nicht gefunden")
```

ersetzen durch

```python
    # Fix #7 + #443: ein für den Nutzer unsichtbarer Plan "existiert" nicht
    # (404, deckungsgleich mit dem Filter in list_plans).
    if not shift_planning_service.is_plan_visible_to(plan, today_local(), is_admin):
        raise HTTPException(status_code=404, detail="Schichtplan nicht gefunden")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py tests/test_fix7_shift_plan_read_gating.py -q </dev/null
```
Erwartet: alle passed — insbesondere die beiden Fix-#7-Tests, die das unveränderte Bestandsverhalten absichern.

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/services/shift_planning_service.py backend/app/routers/shift_planning.py \
        backend/tests/test_shift_plan_visibility.py
git commit -F - <<'EOF'
feat(#443): Sichtbarkeitsregel in is_plan_visible_to zusammenfuehren

list_plans und get_plan pruefen die Sichtbarkeit eines Plans nicht mehr je
selbst, sondern ueber einen gemeinsamen Helfer im Service. Damit wirkt die
neue Freigabe an beiden Stellen zwangslaeufig gleich; zwei Inline-Kopien
derselben Regel waren die Vorlage fuer die naechste Divergenz.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Freigabe über die API schreib- und lesbar machen

**Files:**
- Modify: `backend/app/routers/shift_planning.py` (`PlanIn`, `list_plans`-Antwort, `_plan_summary`, `_build_plan_detail`, `create_plan`, `update_plan`, `duplicate_plan`)
- Test: `backend/tests/test_shift_plan_visibility.py` (erweitern)

**Interfaces:**
- Consumes: `is_plan_visible_to` aus Task 2, `ShiftPlan.visible_to_employees` aus Task 1
- Produces: Das Feld `visible_to_employees` (bool) in **drei** Antwortformen: dem Inline-Dict von `list_plans`, `_plan_summary(plan)` und `_build_plan_detail(...)`. `PlanIn.visible_to_employees: bool = False`.

- [ ] **Step 1: Write the failing test**

An `backend/tests/test_shift_plan_visibility.py` anhängen:

```python
from uuid import UUID as _UUID

from app.routers.shift_planning import (
    PlanDuplicateIn,
    PlanIn,
    create_plan,
    duplicate_plan,
    update_plan,
)

# Die Endpunkte werden hier als gewoehnliche Funktionen gerufen, nicht ueber
# HTTP — FastAPI wandelt den Pfadparameter also NICHT um. Die Antwort-Dicts
# tragen die Kennung als str, die Signaturen erwarten UUID.


def test_create_and_update_carry_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_api_admin", role=UserRole.ADMIN)

    created = create_plan(PlanIn(name="Herbstplan", visible_to_employees=True), db=db, current_user=admin)
    assert created["visible_to_employees"] is True

    updated = update_plan(
        _UUID(created["id"]),
        PlanIn(name="Herbstplan", visible_to_employees=False),
        db=db,
        current_user=admin,
    )
    assert updated["visible_to_employees"] is False


def test_plan_detail_exposes_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_detail_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Detailplan", visible=True)
    detail = get_plan(plan.id, db=db, current_user=admin)
    assert detail["visible_to_employees"] is True


def test_list_plans_exposes_the_release_flag(db, default_tenant):
    admin = _user(db, "vis_listflag_admin", role=UserRole.ADMIN)
    _plan(db, admin, "Listenplan", visible=True)
    row = next(p for p in list_plans(db=db, current_user=admin) if p["name"] == "Listenplan")
    assert row["visible_to_employees"] is True


def test_duplicate_does_not_inherit_the_release(db, default_tenant):
    """Eine Kopie ist ein Entwurf — sie darf nicht mit der Freigabe des
    Originals ins Leben treten (wie schon is_active und das Datumsfenster)."""
    admin = _user(db, "vis_dup_admin", role=UserRole.ADMIN)
    src = _plan(db, admin, "Original freigegeben", visible=True)

    copy = duplicate_plan(src.id, PlanDuplicateIn(name="Original freigegeben (Kopie)"), db=db, current_user=admin)
    assert copy["visible_to_employees"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py -q </dev/null
```
Erwartet: FAIL — `PlanIn` kennt das Feld nicht (Pydantic ignoriert bzw. `KeyError: 'visible_to_employees'`).

- [ ] **Step 3: Schema und die drei Antwortformen ergänzen**

In `backend/app/routers/shift_planning.py`:

`PlanIn` erweitern:

```python
class PlanIn(BaseModel):
    name: str
    description: Optional[str] = None
    active_from_date: Optional[date] = None
    active_until_date: Optional[date] = None
    # #443: ausdrückliche Freigabe für Mitarbeitende. PUT ist wie bei den
    # übrigen Feldern ein Vollersatz — ein Aufruf ohne das Feld nimmt die
    # Freigabe also zurück. Das Frontend sendet es immer mit.
    visible_to_employees: bool = False
```

In `_plan_summary` die Rückgabe um eine Zeile ergänzen:

```python
        "visible_to_employees": plan.visible_to_employees,
```

In `list_plans` im `result.append({...})` dieselbe Zeile ergänzen (**dieses Dict wird nicht über `_plan_summary` gebaut** — beide Stellen brauchen die Ergänzung):

```python
            "visible_to_employees": p.visible_to_employees,
```

In `_build_plan_detail` in der Rückgabe, unter `"active_today"`:

```python
        "visible_to_employees": plan.visible_to_employees,
```

In `create_plan` beim Anlegen des `ShiftPlan`:

```python
        visible_to_employees=data.visible_to_employees,
```

In `update_plan` neben den anderen Zuweisungen:

```python
    plan.visible_to_employees = data.visible_to_employees
```

In `duplicate_plan` beim Anlegen von `new_plan` **ausdrücklich** auf `False`, mit Begründung:

```python
        # #443: Die Kopie erbt die Freigabe NICHT — sie ist ein Entwurf, genau
        # wie sie is_active und das Datumsfenster nicht erbt.
        visible_to_employees=False,
```

Den Docstring von `duplicate_plan` um den Halbsatz ergänzen: `… INAKTIVER Entwurf OHNE Aktiv-Datumsfenster und OHNE Freigabe für Mitarbeitende (#443) …`

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_visibility.py -q </dev/null
```
Erwartet: alle passed.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/routers/shift_planning.py backend/tests/test_shift_plan_visibility.py
git commit -F - <<'EOF'
feat(#443): Freigabe ueber die Plan-API schreib- und lesbar

PlanIn nimmt visible_to_employees entgegen, create/update schreiben es, und
alle drei Antwortformen (Listen-Dict, Plan-Summary, Plan-Detail) geben es
aus. Das Duplizieren uebertraegt die Freigabe ausdruecklich nicht — eine
Kopie ist ein Entwurf.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Hinweistext je Einteilung über die API

**Files:**
- Modify: `backend/app/routers/shift_planning.py` (`SlotIn`, `_slot_dict`, `create_slot`, `update_slot`, `duplicate_plan`)
- Test: `backend/tests/test_shift_slot_note.py` (neu)

**Interfaces:**
- Consumes: `ShiftSlot.note` aus Task 1
- Produces: `SlotIn.note: Optional[str]` (max_length 500); `_slot_dict(...)["note"]` — `str | None`, leerer/nur-Leerzeichen-Text wird zu `None` normalisiert

- [ ] **Step 1: Write the failing test**

Neue Datei `backend/tests/test_shift_slot_note.py`:

```python
"""#443: Hinweistext je Einteilung (shift_slots.note).

Reines Anzeigefeld — es fließt in keine Prüfung und in keine Berechnung ein.
Leereingaben werden am Rand zu NULL normalisiert, damit die Anzeige nicht
zwischen "kein Hinweis" und "Hinweis aus Leerzeichen" unterscheiden muss.
"""
from datetime import time
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan, Workstation
from app.routers.shift_planning import (
    PlanDuplicateIn,
    SlotIn,
    create_slot,
    duplicate_plan,
    get_plan,
    update_slot,
)
from tests.conftest import DEFAULT_TENANT_ID


def _admin(db, username):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="A", last_name="D", role=UserRole.ADMIN, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, admin, name):
    p = ShiftPlan(tenant_id=DEFAULT_TENANT_ID, name=name, created_by=admin.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _ws(db, name):
    w = Workstation(tenant_id=DEFAULT_TENANT_ID, name=name)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def _slot_in(ws_id, **over):
    base = dict(
        workstation_id=ws_id, weekday=0,
        start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
    )
    base.update(over)
    return SlotIn(**base)


def test_create_slot_stores_and_returns_the_note(db, default_tenant):
    admin = _admin(db, "note_create_admin")
    plan = _plan(db, admin, "Notizplan")
    ws = _ws(db, "Tresen Notiz")

    out = create_slot(plan.id, _slot_in(ws.id, note="Einarbeitung Azubi"), db=db, current_user=admin)
    assert out["note"] == "Einarbeitung Azubi"


def test_slot_without_note_returns_none(db, default_tenant):
    admin = _admin(db, "note_none_admin")
    plan = _plan(db, admin, "Notizplan ohne")
    ws = _ws(db, "Tresen ohne")

    out = create_slot(plan.id, _slot_in(ws.id), db=db, current_user=admin)
    assert out["note"] is None


def test_blank_note_is_normalised_to_none(db, default_tenant):
    admin = _admin(db, "note_blank_admin")
    plan = _plan(db, admin, "Notizplan blank")
    ws = _ws(db, "Tresen blank")

    out = create_slot(plan.id, _slot_in(ws.id, note="   "), db=db, current_user=admin)
    assert out["note"] is None


def test_update_slot_changes_and_clears_the_note(db, default_tenant):
    admin = _admin(db, "note_update_admin")
    plan = _plan(db, admin, "Notizplan update")
    ws = _ws(db, "Tresen update")

    created = create_slot(plan.id, _slot_in(ws.id, note="alt"), db=db, current_user=admin)
    # Direktaufruf statt HTTP: FastAPI wandelt den Pfadparameter nicht um.
    slot_id = UUID(created["id"])
    changed = update_slot(slot_id, _slot_in(ws.id, note="neu"), db=db, current_user=admin)
    assert changed["note"] == "neu"

    cleared = update_slot(slot_id, _slot_in(ws.id), db=db, current_user=admin)
    assert cleared["note"] is None


def test_note_longer_than_500_chars_is_rejected(db, default_tenant):
    ws_id = "00000000-0000-0000-0000-000000000009"
    with pytest.raises(ValidationError):
        _slot_in(ws_id, note="x" * 501)


def test_duplicate_plan_copies_slot_notes(db, default_tenant):
    admin = _admin(db, "note_dup_admin")
    plan = _plan(db, admin, "Notizplan Original")
    ws = _ws(db, "Tresen dup")
    create_slot(plan.id, _slot_in(ws.id, note="Einarbeitung Azubi"), db=db, current_user=admin)

    copy = duplicate_plan(plan.id, PlanDuplicateIn(name="Notizplan Kopie"), db=db, current_user=admin)
    detail = get_plan(UUID(copy["id"]), db=db, current_user=admin)
    assert [s["note"] for s in detail["slots"]] == ["Einarbeitung Azubi"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_slot_note.py -q </dev/null
```
Erwartet: FAIL — `SlotIn` kennt `note` nicht, `_slot_dict` gibt keinen Schlüssel `note` zurück.

- [ ] **Step 3: Schema, Serializer und beide Schreibpfade ergänzen**

In `backend/app/routers/shift_planning.py`:

Import ergänzen (`Field` fehlt bisher):

```python
from pydantic import BaseModel, Field, field_validator
```

`SlotIn` erweitern — Feld plus Normalisierung:

```python
class SlotIn(BaseModel):
    workstation_id: UUID
    weekday: int
    start_time: time
    end_time: time
    min_staff: int = 0
    # #443: freier Hinweis je Einteilung ("Einarbeitung Azubi"). Die Spalte ist
    # TEXT, die Grenze steht am Rand — 500 Zeichen sind reichlich für einen
    # Hinweis und halten Zelle und PDF lesbar.
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("note")
    @classmethod
    def _note_blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Leereingabe → NULL, damit die Anzeige nicht zwischen "kein Hinweis"
        und "Hinweis aus Leerzeichen" unterscheiden muss."""
        if v is None:
            return None
        v = v.strip()
        return v or None
```

Die bestehenden Validatoren `_weekday_range` und `_min_staff_nonneg` bleiben unverändert.

In `_slot_dict` die Rückgabe um eine Zeile ergänzen, unter `"min_staff"`:

```python
        # #443: reiner Anzeigetext, keine Prüfung, keine Berechnung.
        "note": slot.note,
```

In `create_slot` beim Anlegen des `ShiftSlot`:

```python
        note=data.note,
```

In `update_slot` neben den anderen Zuweisungen:

```python
    slot.note = data.note
```

In `duplicate_plan` beim Anlegen von `ns` (dem kopierten Slot):

```python
            note=s.note,
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_slot_note.py -q </dev/null
```
Erwartet: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/routers/shift_planning.py backend/tests/test_shift_slot_note.py
git commit -F - <<'EOF'
feat(#443): Hinweistext je Einteilung ueber die Slot-API

SlotIn nimmt note entgegen (max. 500 Zeichen, Leereingabe wird zu NULL),
create/update schreiben es, _slot_dict gibt es aus und das Duplizieren eines
Plans zieht die Hinweise mit. Reines Anzeigefeld ohne Einfluss auf Pruefung
oder Berechnung.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: PDF-Renderer (reines Modul, ohne Datenbankzugriff)

**Files:**
- Create: `backend/app/services/shift_plan_export_service.py`
- Test: `backend/tests/test_shift_plan_pdf.py` (neu)

**Interfaces:**
- Consumes: die Dict-Form von `_build_plan_detail` (Schlüssel: `name`, `description`, `active_from_date`, `active_until_date`, `slots` mit je `workstation_name`, `weekday`, `start_time`, `end_time`, `note`, `assignments[].user_name`)
- Produces:
  ```python
  def generate_plan_pdf(
      detail: dict,
      *,
      weekdays: list[int],
      workstation_order: list[str],
      practice_name: str | None,
      generated_on: date,
  ) -> BytesIO
  ```

- [ ] **Step 1: Write the failing test**

Neue Datei `backend/tests/test_shift_plan_pdf.py`:

```python
"""#443: PDF-Aushang eines Schichtplans.

Der Renderer ist bewusst eine reine Funktion: er bekommt das fertige Dict von
``_build_plan_detail`` und hat KEINEN Datenbankzugriff. Damit kann das PDF nicht
zu einem zweiten Abfragepfad auswachsen, der dem Bildschirm davonläuft — genau
das ist im Berechnungsmodell dieses Projekts mehrfach passiert.
"""
from datetime import date

from app.services import shift_plan_export_service


def _detail(**over):
    base = {
        "name": "Normalzustand",
        "description": "Regelbesetzung",
        "active_from_date": "2026-09-01",
        "active_until_date": None,
        "slots": [
            {
                "id": "s1",
                "workstation_name": "Tresen",
                "weekday": 0,
                "start_time": "08:00",
                "end_time": "12:00",
                "note": "Einarbeitung Azubi",
                "assignments": [{"user_name": "Anna Meier"}, {"user_name": "Carla Dorn"}],
            },
            {
                "id": "s2",
                "workstation_name": "Labor",
                "weekday": 1,
                "start_time": "09:00",
                "end_time": "17:00",
                "note": None,
                "assignments": [{"user_name": "Dana Stein"}],
            },
        ],
    }
    base.update(over)
    return base


def _render(**over):
    return shift_plan_export_service.generate_plan_pdf(
        _detail(**over),
        weekdays=[0, 1, 2, 3, 4],
        workstation_order=["Tresen", "Labor"],
        practice_name="Praxis Beispiel",
        generated_on=date(2026, 8, 23),
    )


def test_renders_a_pdf():
    buf = _render()
    data = buf.getvalue()
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


def test_plan_without_slots_still_renders():
    """Ein leerer Plan darf kein 500 werden — reportlab wirft bei einer
    Tabelle ohne Datenzeilen."""
    buf = _render(slots=[])
    assert buf.getvalue()[:4] == b"%PDF"


def test_markup_in_user_text_does_not_break_the_render():
    """reportlab parst innerhalb eines Paragraphen eine XML-ähnliche
    Mini-Auszeichnung. Ein Hinweis mit < oder & muss escaped werden, sonst
    bricht der Aufbau — oder schlimmer: er wird als Auszeichnung gedeutet."""
    slots = _detail()["slots"]
    slots[0]["note"] = "<b>Achtung</b> Meier & Sohn"
    slots[0]["assignments"] = [{"user_name": "Anna <script> Meier"}]
    buf = _render(slots=slots)
    assert buf.getvalue()[:4] == b"%PDF"


def test_disabled_weekdays_are_not_rendered():
    """#371: ein abgeschalteter Wochentag ist keine Planfläche — er darf auch
    im Ausdruck keine Spalte bekommen."""
    small = shift_plan_export_service.generate_plan_pdf(
        _detail(), weekdays=[0], workstation_order=["Tresen", "Labor"],
        practice_name=None, generated_on=date(2026, 8, 23),
    )
    wide = _render()
    assert len(small.getvalue()) < len(wide.getvalue())


def test_unknown_workstation_still_appears():
    """Ein Arbeitsplatz, der nicht in workstation_order steht (etwa weil er
    zwischen Abfrage und Rendern umbenannt wurde), darf nicht verschwinden."""
    slots = _detail()["slots"]
    slots.append({
        "id": "s3", "workstation_name": "Springer", "weekday": 2,
        "start_time": "10:00", "end_time": "14:00", "note": None,
        "assignments": [{"user_name": "Eva Ross"}],
    })
    buf = shift_plan_export_service.generate_plan_pdf(
        _detail(slots=slots), weekdays=[0, 1, 2, 3, 4],
        workstation_order=["Tresen", "Labor"],
        practice_name=None, generated_on=date(2026, 8, 23),
    )
    assert buf.getvalue()[:4] == b"%PDF"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_pdf.py -q </dev/null
```
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'app.services.shift_plan_export_service'`.

- [ ] **Step 3: Renderer schreiben**

Neue Datei `backend/app/services/shift_plan_export_service.py`:

```python
"""PDF-Aushang für einen Schichtplan (#443).

Bewusst ein eigenes Modul und **nicht** Teil von ``export_service``: dort liegt
die §16-/berechnungsgekoppelte Exportfläche, während die Schichtplanung (#305)
von der Berechnung entkoppelt ist. Ein eigenes Modul hält die Trennung sichtbar.

``generate_plan_pdf`` ist eine **reine** Funktion: sie bekommt das fertige Dict
von ``_build_plan_detail`` und hat keinen Datenbankzugriff. Damit kann das PDF
nicht zu einem zweiten Abfragepfad auswachsen, der dem Bildschirm davonläuft —
im Berechnungsmodell dieses Projekts ist genau das mehrfach passiert.

Aus ``export_service`` wird nur ``escape_pdf_text`` geliehen: eine reine
Textfunktion, kein Berechnungspfad.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.export_service import escape_pdf_text

WEEKDAY_LABELS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

_TITLE = ParagraphStyle("PlanTitle", fontName="Helvetica-Bold", fontSize=14, leading=17)
_META = ParagraphStyle("PlanMeta", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#4b5563"))
_HEAD = ParagraphStyle("PlanHead", fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=TA_CENTER)
_CELL = ParagraphStyle("PlanCell", fontName="Helvetica", fontSize=8, leading=10)
_ROWHEAD = ParagraphStyle("PlanRowHead", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)


def _fmt_date(iso: Optional[str]) -> str:
    """ISO-Datum → TT.MM.JJJJ. Unlesbare Eingaben werden unverändert
    durchgereicht statt eine Ausnahme zu werfen — ein Kopfzeilendetail darf
    keinen Ausdruck verhindern."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(iso)


def _validity_text(detail: dict) -> str:
    frm, until = _fmt_date(detail.get("active_from_date")), _fmt_date(detail.get("active_until_date"))
    if frm and until:
        return f"Gültig {frm} – {until}"
    if frm:
        return f"Gültig ab {frm}"
    if until:
        return f"Gültig bis {until}"
    return ""


def _cell_paragraph(slots_of_cell: list[dict]) -> Paragraph:
    """Eine Tabellenzelle: alle Einteilungen dieses Arbeitsplatzes an diesem Tag.

    Mehrere Einteilungen (z. B. Vormittag und Nachmittag) stapeln untereinander,
    getrennt durch eine Leerzeile.
    """
    if not slots_of_cell:
        return Paragraph("—", _CELL)
    blocks = []
    for s in sorted(slots_of_cell, key=lambda x: x.get("start_time") or ""):
        lines = [f"<b>{escape_pdf_text(s.get('start_time'))}–{escape_pdf_text(s.get('end_time'))}</b>"]
        names = [escape_pdf_text(a.get("user_name")) for a in (s.get("assignments") or [])]
        lines.append(", ".join(names) if names else "<i>nicht besetzt</i>")
        note = s.get("note")
        if note:
            lines.append(f"↳ {escape_pdf_text(note)}")
        blocks.append("<br/>".join(lines))
    return Paragraph("<br/><br/>".join(blocks), _CELL)


def generate_plan_pdf(
    detail: dict,
    *,
    weekdays: list,
    workstation_order: list,
    practice_name: Optional[str],
    generated_on: date,
) -> BytesIO:
    """Rendert einen Schichtplan als PDF-Aushang im Querformat A4.

    ``detail``            Das Dict von ``_build_plan_detail``.
    ``weekdays``          Freigeschaltete Planungstage (0=Mo … 6=So), #371 —
                          ein abgeschalteter Tag bekommt keine Spalte.
    ``workstation_order`` Arbeitsplatznamen in der gewünschten Zeilenreihenfolge.
                          Ein Name, der hier fehlt, wird hinten angehängt statt
                          verworfen.
    ``practice_name``     Praxisname für die Kopfzeile, optional.
    ``generated_on``      Das „Stand"-Datum. Wird hereingereicht statt intern
                          ermittelt, damit die Funktion rein und prüfbar bleibt.
    """
    days = sorted(d for d in weekdays if 0 <= d <= 6)
    if not days:
        days = [0, 1, 2, 3, 4]

    slots = [s for s in (detail.get("slots") or []) if s.get("weekday") in days]

    # Zeilen: erst die vorgegebene Reihenfolge, dann alles, was nur in den Slots
    # vorkommt (umbenannt, gelöscht, zwischenzeitlich verschoben).
    present = []
    for s in slots:
        nm = s.get("workstation_name") or "(ohne Arbeitsplatz)"
        if nm not in present:
            present.append(nm)
    rows_order = [n for n in workstation_order if n in present]
    rows_order += [n for n in present if n not in rows_order]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Schichtplan {detail.get('name') or ''}".strip(),
    )

    story = [Paragraph(escape_pdf_text(detail.get("name") or "Schichtplan"), _TITLE)]
    meta_bits = [b for b in (
        escape_pdf_text(practice_name) if practice_name else "",
        escape_pdf_text(detail.get("description") or ""),
        escape_pdf_text(_validity_text(detail)),
        f"Stand: {generated_on.strftime('%d.%m.%Y')}",
    ) if b]
    story.append(Paragraph(" · ".join(meta_bits), _META))
    story.append(Spacer(1, 5 * mm))

    header = [Paragraph("Arbeitsplatz", _HEAD)] + [Paragraph(WEEKDAY_LABELS[d], _HEAD) for d in days]
    table_data = [header]
    for ws_name in rows_order:
        row = [Paragraph(escape_pdf_text(ws_name), _ROWHEAD)]
        for d in days:
            row.append(_cell_paragraph([
                s for s in slots
                if (s.get("workstation_name") or "(ohne Arbeitsplatz)") == ws_name and s.get("weekday") == d
            ]))
        table_data.append(row)

    if len(table_data) == 1:
        # Kein einziger Slot auf einem freigeschalteten Tag. reportlab wirft bei
        # einer Tabelle ohne Datenzeile — stattdessen eine ehrliche Zeile.
        story.append(Paragraph("Für diesen Plan sind keine Einteilungen hinterlegt.", _CELL))
    else:
        usable = landscape(A4)[0] - 24 * mm
        first = 38 * mm
        col_widths = [first] + [(usable - first) / len(days)] * len(days)
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    doc.build(story)
    buf.seek(0)
    return buf
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_pdf.py -q </dev/null
```
Erwartet: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/services/shift_plan_export_service.py backend/tests/test_shift_plan_pdf.py
git commit -F - <<'EOF'
feat(#443): PDF-Renderer fuer den Schichtplan-Aushang

Eigenes Modul, reine Funktion ohne Datenbankzugriff: sie rendert das fertige
Dict von _build_plan_detail als Querformat-A4-Tabelle Arbeitsplatz x
Wochentag. Damit kann der Ausdruck nicht zu einem zweiten Abfragepfad
auswachsen, der dem Bildschirm davonlaeuft. Alle Nutzertexte laufen durch
escape_pdf_text, weil reportlab innerhalb eines Paragraphen Auszeichnung
parst.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 6: PDF-Endpunkt

**Files:**
- Modify: `backend/app/routers/shift_planning.py` (Imports, neuer Endpunkt nach `get_plan`)
- Test: `backend/tests/test_shift_plan_pdf.py` (erweitern)

**Interfaces:**
- Consumes: `generate_plan_pdf` aus Task 5, `is_plan_visible_to` aus Task 2, `_build_plan_detail` (bestehend)
- Produces: `GET /api/shift-planning/plans/{plan_id}/export.pdf` → `StreamingResponse`, `media_type="application/pdf"`

- [ ] **Step 1: Write the failing test**

An `backend/tests/test_shift_plan_pdf.py` anhängen:

```python
import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.models.shift_planning import ShiftPlan
from app.routers.shift_planning import export_plan_pdf
from tests.conftest import DEFAULT_TENANT_ID


def _user(db, username, role=UserRole.EMPLOYEE):
    u = User(
        username=username, email=f"{username}@t.de", password_hash="h",
        first_name="F", last_name="L", role=role, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan(db, creator, name, *, active=False, visible=False):
    p = ShiftPlan(
        tenant_id=DEFAULT_TENANT_ID, name=name, is_active=active,
        visible_to_employees=visible, created_by=creator.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _body(response) -> bytes:
    return b"".join(response.body_iterator)


def test_admin_can_export_a_draft(db, default_tenant):
    admin = _user(db, "pdf_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, "Entwurf zum Drucken")

    resp = export_plan_pdf(plan.id, db=db, current_user=admin)
    assert resp.media_type == "application/pdf"
    assert _body(resp)[:4] == b"%PDF"
    assert "attachment" in resp.headers["content-disposition"]


def test_employee_can_export_a_released_plan(db, default_tenant):
    """Der Mitarbeitende druckt nur, was er ohnehin am Bildschirm liest."""
    admin = _user(db, "pdf_rel_admin", role=UserRole.ADMIN)
    emp = _user(db, "pdf_rel_emp")
    plan = _plan(db, admin, "Freigegeben zum Drucken", visible=True)

    assert _body(export_plan_pdf(plan.id, db=db, current_user=emp))[:4] == b"%PDF"


def test_employee_cannot_export_an_invisible_plan(db, default_tenant):
    admin = _user(db, "pdf_hidden_admin", role=UserRole.ADMIN)
    emp = _user(db, "pdf_hidden_emp")
    plan = _plan(db, admin, "Entwurf bleibt zu")

    with pytest.raises(HTTPException) as exc:
        export_plan_pdf(plan.id, db=db, current_user=emp)
    assert exc.value.status_code == 404


def test_filename_is_sanitised(db, default_tenant):
    admin = _user(db, "pdf_name_admin", role=UserRole.ADMIN)
    plan = _plan(db, admin, 'Plan "Sommer"/2026')

    cd = export_plan_pdf(plan.id, db=db, current_user=admin).headers["content-disposition"]
    assert '"' not in cd.split("filename=")[1].split(";")[0].strip('"')
    assert "/" not in cd.split("filename=")[1].split(";")[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_pdf.py -q </dev/null
```
Erwartet: FAIL mit `ImportError: cannot import name 'export_plan_pdf'`.

- [ ] **Step 3: Endpunkt schreiben**

In `backend/app/routers/shift_planning.py` die Imports ergänzen:

```python
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from app.services import shift_plan_export_service
from app.services.timezone_service import today_local
```

(`today_local` ist bereits importiert — die Zeile nicht doppeln. `settings_service` ebenfalls bereits vorhanden.)

Direkt **nach** `get_plan` einfügen:

```python
# Dateinamen-Bereinigung: alles außer Buchstaben/Ziffern/Bindestrich wird zu "_".
# Ein Plan darf "Sommer 2026 (KW 30/31)" heißen — im Dateinamen hat weder der
# Schrägstrich noch das Anführungszeichen etwas verloren.
_FILENAME_SAFE_RE = re.compile(r"[^\w\-]+", re.UNICODE)


@router.get("/plans/{plan_id}/export.pdf")
def export_plan_pdf(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """#443: Schichtplan als PDF-Aushang (Querformat A4).

    Zugang über dieselbe Sichtbarkeitsregel wie ``get_plan`` und **nicht** über
    ``require_admin``: ein Mitarbeitender druckt damit nur, was er ohnehin am
    Bildschirm liest. Die Einweisungs-Flags (``qualified``/``unqualified``) sind
    weiterhin admin-only und stehen im PDF grundsätzlich nicht.

    Der Renderer bekommt das Dict von ``_build_plan_detail`` und stellt keine
    eigenen Abfragen — so erbt der Ausdruck den #371-Wochentagsfilter und die
    Unterbesetzungslage automatisch statt sie nachzubauen.
    """
    tid = current_user.tenant_id
    plan = _plan_or_404(db, tid, plan_id)
    is_admin = current_user.role == UserRole.ADMIN
    if not shift_planning_service.is_plan_visible_to(plan, today_local(), is_admin):
        raise HTTPException(status_code=404, detail="Schichtplan nicht gefunden")

    detail = _build_plan_detail(db, tid, plan, is_admin)
    weekdays = shift_planning_service.get_planning_weekdays(db, tid)
    ws_order = [
        w.name
        for w in db.query(Workstation)
        .filter(Workstation.tenant_id == tid)  # F-026
        .order_by(Workstation.sort_order, Workstation.name)
        .all()
    ]
    practice_name = settings_service.get_setting(db, "practice_name", tenant_id=tid, default=None)
    generated_on = today_local()

    pdf = shift_plan_export_service.generate_plan_pdf(
        detail,
        weekdays=weekdays,
        workstation_order=ws_order,
        practice_name=practice_name,
        generated_on=generated_on,
    )
    db.close()  # F-053: Pool-Verbindung vor dem Streamen freigeben
    safe = _FILENAME_SAFE_RE.sub("_", plan.name).strip("_") or "Schichtplan"
    filename = f"Schichtplan_{safe}_{generated_on.isoformat()}.pdf"
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
```

**Hinweis:** `practice_name` ist ein Tenant-Setting. Existiert der Schlüssel nicht, liefert `settings_service.get_setting` den Default `None` — die Kopfzeile lässt den Praxisnamen dann weg. Vor dem Schreiben prüfen, ob der Schlüssel im Projekt anders heißt:
```bash
grep -rn "practice_name\|praxis_name" backend/app/routers/admin_settings.py | head -5
```
Heißt er anders, den Schlüssel hier anpassen (und den Kommentar ebenfalls).

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_plan_pdf.py -q </dev/null
```
Erwartet: 9 passed.

- [ ] **Step 5: Feature-Flag-Gate am laufenden Server prüfen**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose restart backend && sleep 12
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/shift-planning/plans/00000000-0000-0000-0000-000000000000/export.pdf"
```
Erwartet: `401` oder `403` (nicht angemeldet) — **kein** `404 Not Found` wegen fehlender Route und **kein** `500`. Die Route existiert damit und hängt hinter der Authentifizierung.

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/routers/shift_planning.py backend/tests/test_shift_plan_pdf.py
git commit -F - <<'EOF'
feat(#443): Endpunkt fuer den PDF-Aushang eines Schichtplans

GET /plans/{id}/export.pdf hinter derselben Sichtbarkeitsregel wie get_plan,
nicht hinter require_admin: der Mitarbeitende druckt nur, was er ohnehin am
Bildschirm liest. Der Renderer bekommt ausschliesslich das Dict von
_build_plan_detail; die Wochentags- und Arbeitsplatz-Reihenfolge reicht der
Endpunkt hinein, damit die Renderfunktion ohne Datenbank auskommt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 7: #450 — Bedienkonflikt als 409 und Längengrenzen

**Files:**
- Modify: `backend/app/routers/shift_planning.py` (`set_user_qualifications`, `LocationIn`, `WorkstationIn`, `PlanIn`, `PlanDuplicateIn`)
- Test: `backend/tests/test_shift_planning_limits.py` (neu)

**Interfaces:**
- Consumes: `_commit_or_conflict` (bestehend), `Field` (in Task 4 importiert)
- Produces: keine neuen Signaturen — nur strengere Eingangsprüfung und eine saubere 409

- [ ] **Step 1: Write the failing test**

Neue Datei `backend/tests/test_shift_planning_limits.py`:

```python
"""#450: Zwei kleine Funde aus dem Release-Review 1.18.2.

1. ``set_user_qualifications`` committete ohne Übersetzung eines
   Eindeutigkeits-Konflikts → HTTP 500 mit Traceback für einen reinen
   Bedienkonflikt (zwei Admins, zwei Browser-Tabs).
2. Die Namensfelder hatten keine Längengrenze gegen ``String(255)``-Spalten →
   ein zu langer Name bricht auf PostgreSQL beim COMMIT ab (500 statt 422).
   Die Suite läuft gegen SQLite, das varchar-Längen ignoriert — deshalb prüfen
   diese Tests am Rand (Pydantic), nicht in der Datenbank.
"""
import pytest
from pydantic import ValidationError

from app.routers.shift_planning import LocationIn, PlanDuplicateIn, PlanIn, WorkstationIn

_TOO_LONG = "x" * 256


def test_location_name_length_is_bounded():
    LocationIn(name="x" * 255)
    with pytest.raises(ValidationError):
        LocationIn(name=_TOO_LONG)


def test_workstation_name_length_is_bounded():
    WorkstationIn(name="x" * 255)
    with pytest.raises(ValidationError):
        WorkstationIn(name=_TOO_LONG)


def test_plan_name_length_is_bounded():
    PlanIn(name="x" * 255)
    with pytest.raises(ValidationError):
        PlanIn(name=_TOO_LONG)


def test_duplicate_name_length_is_bounded():
    PlanDuplicateIn(name="x" * 255)
    with pytest.raises(ValidationError):
        PlanDuplicateIn(name=_TOO_LONG)


@pytest.mark.parametrize("model", [LocationIn, WorkstationIn, PlanIn, PlanDuplicateIn])
def test_empty_name_is_rejected_at_the_edge(model):
    with pytest.raises(ValidationError):
        model(name="")


def test_qualification_conflict_becomes_409(db, default_tenant, monkeypatch):
    """Verliert ein zweiter Schreiber das Rennen auf uq_tenant_user_workstation,
    muss das ein 409 sein — kein 500 mit Traceback im Fehlerprotokoll."""
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.models import User, UserRole
    from app.routers import shift_planning as sp
    from tests.conftest import DEFAULT_TENANT_ID

    admin = User(
        username="lim_admin", email="lim_admin@t.de", password_hash="h",
        first_name="A", last_name="D", role=UserRole.ADMIN, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    target = User(
        username="lim_target", email="lim_target@t.de", password_hash="h",
        first_name="T", last_name="G", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    def _boom():
        raise IntegrityError("INSERT", {}, Exception("uq_tenant_user_workstation"))

    monkeypatch.setattr(db, "commit", _boom)

    with pytest.raises(HTTPException) as exc:
        sp.set_user_qualifications(
            target.id, sp.QualificationsIn(workstation_ids=[]), db=db, current_user=admin,
        )
    assert exc.value.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_planning_limits.py -q </dev/null
```
Erwartet: FAIL — die Längentests laufen durch ohne Ausnahme, der Konflikttest endet in `IntegrityError` statt `HTTPException`.

- [ ] **Step 3: Grenzen setzen und den Konflikt übersetzen**

In `backend/app/routers/shift_planning.py` die vier Schemata anpassen. Der begründende Kommentar steht einmal, beim ersten Vorkommen:

```python
class LocationIn(BaseModel):
    # #450: Die Spalten sind String(255). Ohne Grenze bricht ein längerer Name
    # auf PostgreSQL erst beim COMMIT ab (StringDataRightTruncation → 500)
    # statt am Rand mit 422 und Feldhinweis. Die SQLite-Suite ignoriert
    # varchar-Längen und fängt das nie — dasselbe Muster wie bei
    # time_entry_audit_logs.source.
    name: str = Field(..., min_length=1, max_length=255)
    sort_order: int = 0


class WorkstationIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)  # #450
    location_id: Optional[UUID] = None
    color: Optional[str] = None
    sort_order: int = 0
```

(Der `_hex_color`-Validator von `WorkstationIn` bleibt unverändert.)

```python
class PlanIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)  # #450
    ...


class PlanDuplicateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)  # #338 Name der Kopie, #450 Grenze
```

Die bestehenden `if not name: 400`-Prüfungen in den Endpunkten bleiben stehen — sie fangen weiterhin einen Namen aus reinen Leerzeichen ab, den `min_length` durchlässt.

In `set_user_qualifications` das nackte `db.commit()` ersetzen:

```python
    # #450: Zwei Admins (oder zwei Browser-Tabs) auf derselben Zeile laufen
    # sonst in uq_tenant_user_workstation und bekommen ein 500 mit Traceback
    # für einen reinen Bedienkonflikt.
    _commit_or_conflict(db, "Die Einweisungen wurden zwischenzeitlich geändert, bitte erneut versuchen")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_shift_planning_limits.py -q </dev/null
```
Erwartet: alle passed.

- [ ] **Step 5: Bestehende Schichtplanungs-Tests gegenprüfen**

```bash
docker compose exec -T -e TZ=Europe/Berlin backend pytest \
  tests/test_shift_planning.py tests/test_shift_planning_cross_tenant.py \
  tests/test_shift_weekdays.py tests/test_shift_plan_generator.py \
  tests/test_shift_plan_schedule.py tests/test_fix7_shift_plan_read_gating.py -q </dev/null
```
Erwartet: alle passed. Die neue `min_length=1` könnte einen Test treffen, der bisher einen leeren Namen auf 400 geprüft hat — dann erwartet er jetzt 422. In diesem Fall den Test anpassen und die Änderung im Commit erwähnen.

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/routers/shift_planning.py backend/tests/test_shift_planning_limits.py
git commit -F - <<'EOF'
fix(#450): Bedienkonflikt bei Einweisungen als 409, Namen mit Laengengrenze

set_user_qualifications uebersetzt einen Eindeutigkeits-Konflikt jetzt ueber
_commit_or_conflict in ein 409, statt ein 500 samt Traceback fuer einen
reinen Bedienkonflikt zu schreiben. Die vier Namensfelder tragen
min_length/max_length gegen ihre String(255)-Spalten — auf PostgreSQL brach
ein zu langer Name bisher erst beim COMMIT ab.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Der neue Hinweistext überlebt die Anonymisierung nicht

**Files:**
- Modify: `backend/app/services/lifecycle_service.py` (`anonymize_tenant`)
- Modify: `backend/tests/test_tenant_anonymization.py`

**Interfaces:**
- Consumes: `ShiftSlot.note` aus Task 1
- Produces: keine neue Signatur — `anonymize_tenant` setzt zusätzlich `shift_slots.note = NULL` für den Mandanten

**Wie diese Testdatei gebaut ist (wichtig):** Sie prüft nicht „die Funktion läuft
durch", sondern „nichts Personenbezogenes ist danach noch auffindbar". Jedes
Feld bekommt eine eindeutige Zeichenfolge aus dem `PII`-Dict, und nach dem Lauf
wird die **gesamte** Datenbank — jede Tabelle aus `Base.metadata`, jede Spalte,
jede Zeile — danach durchsucht. Es ist also **kein** eigener Testfall nötig: Saat
in die `mandant`-Fixture legen, Eintrag in `PII` ergänzen, fertig. Die vorhandene
Suche erledigt den Rest.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_tenant_anonymization.py`:

Import ergänzen (bei den übrigen Modell-Importen):

```python
from app.models.shift_planning import ShiftPlan, ShiftSlot, Workstation
```

Im `PII`-Dict, hinter `"audit_benutzername"`, ergänzen:

```python
    # #443: der Hinweis je Schicht-Einteilung ist Admin-Freitext und traegt
    # regelmaessig Personenbezug ("Einarbeitung Frau Meier"). Ein neues
    # Freitextfeld, das die Anonymisierung ueberlebt, verlaengert die Restliste
    # aus #440 — deshalb hier gleich mit gesaet.
    "shift_note": "PIISCHICHTNOTIZAAA",
```

In der `mandant`-Fixture, hinter den beiden `TimeEntryAuditLog`-Zeilen und **vor**
dem abschließenden Commit der Fixture, ergänzen:

```python
    plan = ShiftPlan(tenant_id=TID, name="Normalzustand", created_by=user.id)
    _db_session.add(plan)
    workstation = Workstation(tenant_id=TID, name="Tresen")
    _db_session.add(workstation)
    _db_session.commit()
    _db_session.refresh(plan)
    _db_session.refresh(workstation)
    _db_session.add(ShiftSlot(
        tenant_id=TID, shift_plan_id=plan.id, workstation_id=workstation.id,
        weekday=0, start_time=time(8, 0), end_time=time(12, 0), min_staff=1,
        note=PII["shift_note"],
    ))
```

`time` ist am Kopf der Datei bereits importiert.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_tenant_anonymization.py -q </dev/null
```
Erwartet: FAIL — die Ganz-Datenbank-Suche findet `PIISCHICHTNOTIZAAA` in
`shift_slots.note` und meldet die Fundstelle mit Tabelle und Spalte.

- [ ] **Step 3: Scrub ergänzen**

In `backend/app/services/lifecycle_service.py`, in `anonymize_tenant`, unmittelbar
neben dem bestehenden `WorkingHoursChange.note`-Scrub:

```python
    # #443/#440: Der Hinweis je Schicht-Einteilung ist Admin-Freitext und kann
    # Personenbezug tragen ("Einarbeitung Frau Meier"). Ein Bulk-UPDATE ist hier
    # zulaessig — anders als bei time_entry_audit_logs traegt shift_slots keinen
    # row_hash (#121), den ein Umgehen der Objektschicht stale werden liesse.
    db.query(ShiftSlot).filter(
        ShiftSlot.tenant_id == tenant.id,  # F-026
        ShiftSlot.note.isnot(None),
    ).update({ShiftSlot.note: None}, synchronize_session=False)
```

Den Import am Kopf der Datei ergänzen (zuerst prüfen, ob
`app.models.shift_planning` dort schon importiert wird):

```python
from app.models.shift_planning import ShiftSlot
```

Den Docstring von `anonymize_tenant` in der Aufzählung der bearbeiteten Tabellen
ergänzen:

```
    - ``shift_slots``: ``note`` -> NULL (#443; Admin-Freitext ohne
      Aufbewahrungspflicht, kann Personenbezug tragen).
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_tenant_anonymization.py -q </dev/null
```
Erwartet: alle passed. Insbesondere darf `TestAufbewahrungBleibt` nicht kippen —
`time_entries` und `absences` bleiben absichtlich stehen (§16 ArbZG).

- [ ] **Step 5: Den Geschwisterpfad prüfen**

`admin_users.anonymize_user` (Einzelperson) ist ein **anderer** Pfad. Ein
Schicht-Hinweis hängt jedoch an einer Einteilung, nicht an einer Person — er wird
dort bewusst **nicht** geleert (die Einteilung bleibt für die übrigen
Mitarbeitenden bestehen). Diese Entscheidung im Docstring von `anonymize_user`
festhalten:

```python
    # #443: shift_slots.note bleibt hier stehen — der Hinweis haengt an der
    # Einteilung, nicht an einer Person, und die Einteilung besteht fuer die
    # uebrigen Mitarbeitenden fort. Im Mandantenpfad (anonymize_tenant) wird er
    # geleert, weil dort der ganze Mandant verschwindet.
```

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add backend/app/services/lifecycle_service.py backend/tests/test_tenant_anonymization.py         backend/app/routers/admin_users.py
git commit -F - <<'EOF'
feat(#443): Hinweistext je Einteilung ueberlebt die Anonymisierung nicht

Der neue Freitext wird in anonymize_tenant mit geleert, statt die Restliste
aus #440 zu verlaengern; die Saat liegt im PII-Dict, die vorhandene
Ganz-Datenbank-Suche der Testdatei deckt ihn damit von selbst ab. Im
Einzelpersonen-Pfad bleibt er bewusst stehen — der Hinweis haengt an der
Einteilung, nicht an einer Person.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Frontend-API — Typen und PDF-Download

**Files:**
- Modify: `frontend/src/api/shiftPlanning.ts`
- Test: `frontend/src/api/shiftPlanning.test.ts` (neu)

**Interfaces:**
- Consumes: die Backend-Antworten aus Tasks 3, 4, 6
- Produces:
  - `ShiftSlot.note: string | null`
  - `PlanSummary.visible_to_employees: boolean`, `PlanDetail.visible_to_employees: boolean`
  - `SlotInput.note?: string | null`
  - `PlanUpdateBody.visible_to_employees?: boolean`
  - `downloadPlanPdf(id: string, planName: string): Promise<void>`

- [ ] **Step 1: Write the failing test**

Neue Datei `frontend/src/api/shiftPlanning.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Beide Nachbarmodule ersetzen, NICHT per vi.spyOn auf den Namensraum: ein
// ES-Modul-Export ist nicht schreibbar, und der Import in shiftPlanning.ts ist
// bereits gebunden — ein Spion darauf griffe nie.
vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock('../utils/downloadBlob', () => ({ downloadBlob: vi.fn() }));

import apiClient from './client';
import { downloadBlob } from '../utils/downloadBlob';
import { downloadPlanPdf } from './shiftPlanning';

const getMock = apiClient.get as ReturnType<typeof vi.fn>;
const dlMock = downloadBlob as ReturnType<typeof vi.fn>;

describe('downloadPlanPdf', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fordert den Plan als Blob an und stoesst den Download an', async () => {
    getMock.mockResolvedValue({ data: new Blob(['%PDF-1.4'], { type: 'application/pdf' }) });

    await downloadPlanPdf('plan-1', 'Normalzustand');

    expect(getMock).toHaveBeenCalledWith('/shift-planning/plans/plan-1/export.pdf', {
      responseType: 'blob',
    });
    expect(dlMock).toHaveBeenCalledTimes(1);
    expect(dlMock.mock.calls[0][1]).toContain('Normalzustand');
    expect(dlMock.mock.calls[0][1]).toMatch(/\.pdf$/);
    expect(dlMock.mock.calls[0][2]).toBe('application/pdf');
  });

  it('bereinigt Sonderzeichen im Dateinamen', async () => {
    getMock.mockResolvedValue({ data: new Blob([]) });

    await downloadPlanPdf('plan-2', 'Sommer "2026"/KW30');

    const filename = dlMock.mock.calls[0][1] as string;
    expect(filename).not.toContain('/');
    expect(filename).not.toContain('"');
    expect(filename).toContain('Sommer');
  });

  it('faellt auf einen Ersatznamen zurueck, wenn nichts uebrig bleibt', async () => {
    getMock.mockResolvedValue({ data: new Blob([]) });

    await downloadPlanPdf('plan-3', '///');

    expect(dlMock.mock.calls[0][1]).toBe('Schichtplan_Schichtplan.pdf');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/api/shiftPlanning.test.ts --pool=threads
```
Erwartet: FAIL — `downloadPlanPdf` ist kein Export von `./shiftPlanning`.

- [ ] **Step 3: Typen und Download-Funktion ergänzen**

In `frontend/src/api/shiftPlanning.ts`:

Import am Kopf ergänzen:

```ts
import { downloadBlob } from '../utils/downloadBlob';
```

`ShiftSlot` erweitern (unter `min_staff`):

```ts
  note: string | null; // #443: Hinweis je Einteilung ("Einarbeitung Azubi")
```

`PlanSummary` und `PlanDetail` je um dieselbe Zeile erweitern (unter `active_today`):

```ts
  visible_to_employees: boolean; // #443: ausdrücklich für Mitarbeitende freigegeben
```

`SlotInput` erweitern:

```ts
  note?: string | null; // #443
```

`PlanUpdateBody` erweitern:

```ts
  visible_to_employees?: boolean; // #443
```

In `updatePlan` das Feld mitsenden (der PUT ist ein Vollersatz — fehlt es, nimmt der Server die Freigabe zurück):

```ts
      visible_to_employees: body.visible_to_employees ?? false,
```

Am Ende des Plan-Abschnitts die Download-Funktion ergänzen:

```ts
// #443: PDF-Aushang. Der Dateiname wird hier nochmals bereinigt — der Server
// setzt zwar Content-Disposition, aber downloadBlob nutzt den übergebenen
// Namen, und ein Plan darf "Sommer 2026 (KW 30/31)" heißen.
export const downloadPlanPdf = async (id: string, planName: string): Promise<void> => {
  const res = await apiClient.get(`${BASE}/plans/${id}/export.pdf`, { responseType: 'blob' });
  const safe = planName.replace(/[^\p{L}\p{N}\-_]+/gu, '_').replace(/^_+|_+$/g, '') || 'Schichtplan';
  downloadBlob(res.data, `Schichtplan_${safe}.pdf`, 'application/pdf');
};
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/api/shiftPlanning.test.ts --pool=threads
npx tsc --noEmit
```
Erwartet: 3 passed.

`tsconfig.json` schließt `src/**/*.test.ts(x)` aus — Testdateien lösen also **keine**
`tsc`-Fehler aus. Wohl aber Produktionscode, der ein `ShiftSlot`- oder
`PlanSummary`-Objekt selbst zusammenbaut und die neuen Pflichtfelder nicht setzt.
Solche Stellen hier beheben; die gemeldeten Dateien notieren.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/api/shiftPlanning.ts frontend/src/api/shiftPlanning.test.ts
git commit -F - <<'EOF'
feat(#443): Frontend-API um Freigabe, Hinweis und PDF-Download erweitert

ShiftSlot.note, visible_to_employees an Summary und Detail, note in SlotInput
und downloadPlanPdf. updatePlan sendet die Freigabe immer mit, weil der PUT
ein Vollersatz ist und ein Auslassen sie zuruecknehmen wuerde.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 10: Layout-Rechnung — Inhaltshöhe schätzen

**Files:**
- Modify: `frontend/src/components/shiftplanning/weekGridUtils.ts`
- Test: `frontend/src/components/shiftplanning/weekGridUtils.test.ts` (erweitern)

**Interfaces:**
- Consumes: nichts aus früheren Tasks (reine Rechnung)
- Produces:
  - `SlotLike` trägt zusätzlich `assignments?: unknown[]` und `note?: string | null`
  - `SlotBox` trägt zusätzlich `contentHeight: number` und `grown: boolean`
  - `estimateContentHeight(slot: SlotLike): number`
  - Konstanten `LINE_PX = 14`, `BLOCK_PADDING_PX = 8`, `NOTE_CHARS_PER_LINE = 20`

- [ ] **Step 1: Write the failing test**

An `frontend/src/components/shiftplanning/weekGridUtils.test.ts` anhängen (die bestehenden Importe der Datei entsprechend erweitern):

```ts
import { estimateContentHeight, computeWeekLayout, HOUR_PX } from './weekGridUtils';

const slot = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  weekday: 0,
  start_time: '08:00',
  end_time: '12:00',
  assignments: [],
  note: null,
  ...over,
});

describe('estimateContentHeight', () => {
  it('rechnet Kopfzeile, Zeitzeile und eine Namenszeile', () => {
    // 3 Zeilen à 14px + 8px Innenabstand
    expect(estimateContentHeight(slot())).toBe(3 * 14 + 8);
  });

  it('rechnet eine Zeile je zugewiesener Person', () => {
    const s = slot({ assignments: [{}, {}, {}] });
    expect(estimateContentHeight(s)).toBe((2 + 3) * 14 + 8);
  });

  it('rechnet den Hinweis in 20-Zeichen-Zeilen', () => {
    const short = slot({ note: 'Einarbeitung' });          // 1 Zeile
    const long = slot({ note: 'x'.repeat(45) });            // 3 Zeilen
    expect(estimateContentHeight(short)).toBe((3 + 1) * 14 + 8);
    expect(estimateContentHeight(long)).toBe((3 + 3) * 14 + 8);
  });

  it('ignoriert einen Hinweis aus Leerzeichen', () => {
    expect(estimateContentHeight(slot({ note: '   ' }))).toBe(estimateContentHeight(slot()));
  });
});

describe('computeWeekLayout: grown', () => {
  it('markiert einen kurzen Slot mit vielen Namen als gewachsen', () => {
    // 30 Minuten = 24px zeitproportional, Inhalt braucht (2+4)*14+8 = 92px
    const s = slot({ start_time: '08:00', end_time: '08:30', assignments: [{}, {}, {}, {}] });
    const layout = computeWeekLayout([s]);
    expect(layout.boxes.s1.grown).toBe(true);
    expect(layout.boxes.s1.contentHeight).toBe(92);
  });

  it('markiert einen ausreichend langen Slot NICHT als gewachsen', () => {
    // 4 Stunden = 192px, Inhalt braucht (2+2)*14+8 = 64px
    const s = slot({ start_time: '08:00', end_time: '12:00', assignments: [{}, {}] });
    const layout = computeWeekLayout([s]);
    expect(layout.boxes.s1.grown).toBe(false);
    expect(layout.boxes.s1.height).toBe(4 * HOUR_PX);
  });

  it('lässt die zeitproportionale Höhe unberührt', () => {
    const s = slot({ start_time: '08:00', end_time: '08:30', assignments: [{}, {}, {}, {}] });
    const layout = computeWeekLayout([s]);
    // height bleibt die Zeitdauer (Untergrenze 18px) — das Wachsen macht das CSS
    expect(layout.boxes.s1.height).toBe(24);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/weekGridUtils.test.ts --pool=threads
```
Erwartet: FAIL — `estimateContentHeight` ist kein Export.

- [ ] **Step 3: Rechnung ergänzen**

In `frontend/src/components/shiftplanning/weekGridUtils.ts`:

Konstanten unter `SNAP_MINUTES` ergänzen:

```ts
// #443: Grundlage der Schätzung, wie hoch ein Block seinem INHALT nach wäre.
// Sie steuert ausschließlich die Markierung "reicht über das Zeitfenster
// hinaus" — das tatsächliche Wachsen erledigt das CSS (minHeight statt height).
// Deshalb ist eine Schätzung hier ausreichend und einer DOM-Messung vorzuziehen:
// die Funktion bleibt rein, prüfbar und über alle Browser gleich.
export const LINE_PX = 14;
export const BLOCK_PADDING_PX = 8; // p-1 oben + unten
export const NOTE_CHARS_PER_LINE = 20;
```

`SlotLike` erweitern:

```ts
export interface SlotLike {
  id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  // #443: für die Inhaltsschätzung. Optional, damit die reinen Zeit-Tests und
  // ältere Aufrufer unverändert weiterlaufen.
  assignments?: unknown[];
  note?: string | null;
}
```

`SlotBox` erweitern:

```ts
export interface SlotBox {
  top: number;
  height: number; // zeitproportional — bleibt die Aussage über die Uhrzeit
  leftPct: number; // 0..100
  widthPct: number; // 0..100
  // #443
  contentHeight: number;
  grown: boolean; // contentHeight > height → Blockhöhe meint nicht mehr die Uhrzeit
}
```

Die Schätzfunktion vor `computeWeekLayout` einfügen:

```ts
/**
 * Geschätzte Höhe, die der INHALT eines Blocks braucht (#443).
 *
 * Gezählt werden: die Kopfzeile (Arbeitsplatz), die Zeitzeile, eine Zeile je
 * zugewiesener Person — mindestens eine, weil dort sonst "0/2" oder "—" steht —
 * und der Hinweis in Zeilen zu ``NOTE_CHARS_PER_LINE`` Zeichen.
 *
 * Das Ergebnis ist eine **Untergrenze**: bricht ein langer Name in einer sehr
 * schmalen Spur auf zwei Zeilen um, wächst der Block korrekt, bleibt aber
 * womöglich ohne Markierung. Das ist hingenommen — die Markierung ist ein
 * Hinweis, keine Zusicherung. Der umgekehrte Fehler (Markierung ohne Wachstum)
 * kann nicht auftreten.
 */
export function estimateContentHeight(slot: SlotLike): number {
  const nameLines = Math.max(1, slot.assignments?.length ?? 0);
  const note = (slot.note ?? '').trim();
  const noteLines = note ? Math.ceil(note.length / NOTE_CHARS_PER_LINE) : 0;
  const lines = 1 /* Arbeitsplatz */ + 1 /* Zeit */ + nameLines + noteLines;
  return lines * LINE_PX + BLOCK_PADDING_PX;
}
```

In `computeWeekLayout`, im `flush()`, die beiden Felder ergänzen. `height` bleibt **unverändert** zeitproportional:

```ts
    const flush = () => {
      const lanes = Math.max(1, laneEnds.length);
      for (const item of group) {
        const height = Math.max(18, ((item.end - item.start) / 60) * HOUR_PX);
        const contentHeight = estimateContentHeight(item.s);
        boxes[item.s.id] = {
          top: ((item.start - startHour * 60) / 60) * HOUR_PX,
          height,
          leftPct: (item.lane / lanes) * 100,
          widthPct: (1 / lanes) * 100,
          contentHeight,
          grown: contentHeight > height,
        };
      }
      group = [];
      laneEnds = [];
      groupMaxEnd = -1;
    };
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/weekGridUtils.test.ts --pool=threads
```
Erwartet: alle passed, einschließlich der bestehenden Layout-Tests der Datei.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/components/shiftplanning/weekGridUtils.ts \
        frontend/src/components/shiftplanning/weekGridUtils.test.ts
git commit -F - <<'EOF'
feat(#443): Inhaltshoehe eines Slot-Blocks schaetzen

estimateContentHeight zaehlt Kopfzeile, Zeitzeile, eine Zeile je Person und
den Hinweis; computeWeekLayout traegt das Ergebnis als contentHeight/grown an
jeder Box. Die zeitproportionale height bleibt unberuehrt — sie ist weiterhin
die Aussage ueber die Uhrzeit. Die Schaetzung steuert nur die Markierung.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 11: WeekGrid — Umbruch, Wachstum, Hinweis

**Files:**
- Modify: `frontend/src/components/shiftplanning/WeekGrid.tsx`
- Test: `frontend/src/components/shiftplanning/WeekGrid.test.tsx` (neu)

**Interfaces:**
- Consumes: `SlotBox.contentHeight`/`grown` aus Task 10, `ShiftSlot.note` aus Task 9
- Produces: keine neuen Signaturen — reine Darstellung

- [ ] **Step 1: Write the failing test**

Neue Datei `frontend/src/components/shiftplanning/WeekGrid.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import WeekGrid from './WeekGrid';
import type { ShiftSlot } from '../../api/shiftPlanning';

const slot = (over: Partial<ShiftSlot> = {}): ShiftSlot => ({
  id: 's1',
  workstation_id: 'w1',
  workstation_name: 'Anmeldung und Tresen',
  color: '#2563eb',
  weekday: 0,
  start_time: '08:00',
  end_time: '12:00',
  min_staff: 1,
  understaffed: false,
  note: null,
  assignments: [
    { id: 'a1', user_id: 'u1', user_name: 'Annemarie Kettenhofen' },
    { id: 'a2', user_id: 'u2', user_name: 'Carla Dornbusch' },
  ],
  ...over,
});

describe('WeekGrid', () => {
  it('zeigt den vollen Arbeitsplatznamen ohne truncate-Klasse', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    const label = screen.getByText('Anmeldung und Tresen');
    expect(label.className).not.toContain('truncate');
  });

  it('zeigt alle zugewiesenen Namen', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByText(/Annemarie Kettenhofen/)).toBeInTheDocument();
    expect(screen.getByText(/Carla Dornbusch/)).toBeInTheDocument();
  });

  it('zeigt den Hinweis, wenn einer gesetzt ist', () => {
    render(<WeekGrid slots={[slot({ note: 'Einarbeitung Azubi' })]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByText(/Einarbeitung Azubi/)).toBeInTheDocument();
  });

  it('zeigt keine Hinweiszeile ohne Hinweis', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.queryByText(/↳/)).not.toBeInTheDocument();
  });

  it('markiert einen Block, dessen Inhalt über das Zeitfenster reicht', () => {
    const tight = slot({
      start_time: '08:00',
      end_time: '08:30',
      assignments: [
        { id: 'a1', user_id: 'u1', user_name: 'Eins' },
        { id: 'a2', user_id: 'u2', user_name: 'Zwei' },
        { id: 'a3', user_id: 'u3', user_name: 'Drei' },
        { id: 'a4', user_id: 'u4', user_name: 'Vier' },
      ],
    });
    render(<WeekGrid slots={[tight]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.getByTitle(/über das Zeitfenster hinaus/i)).toBeInTheDocument();
  });

  it('markiert einen ausreichend langen Block nicht', () => {
    render(<WeekGrid slots={[slot()]} weekdays={[0, 1, 2, 3, 4]} />);
    expect(screen.queryByTitle(/über das Zeitfenster hinaus/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/WeekGrid.test.tsx --pool=threads
```
Erwartet: FAIL — der Name trägt noch `truncate`, es gibt keine Hinweiszeile und kein `title`-Attribut.

- [ ] **Step 3: Darstellung anpassen**

In `frontend/src/components/shiftplanning/WeekGrid.tsx`:

`SlotBody` ersetzen:

```tsx
function SlotBody({ slot }: { slot: ShiftSlot }) {
  const names = slot.assignments.map((a) => a.user_name).join(', ');
  return (
    <>
      <div className="flex items-start justify-between gap-1">
        {/* #443: kein truncate mehr — der Name bricht um. Bei mehreren parallelen
            Slots wird die Spur schmal, vertikal ist aber Platz. */}
        <span className="font-semibold break-words">{slot.workstation_name}</span>
        {slot.understaffed && <AlertTriangle size={12} className="shrink-0 mt-0.5" aria-label="Unterbesetzt" />}
      </div>
      <div className="opacity-90">
        {slot.start_time}–{slot.end_time}
      </div>
      <div className="flex items-start gap-1 opacity-90">
        <Users size={11} className="shrink-0 mt-0.5" />
        <span className="break-words">{names || (slot.min_staff > 0 ? `0/${slot.min_staff}` : '—')}</span>
      </div>
      {slot.note && (
        <div className="opacity-80 italic break-words">↳ {slot.note}</div>
      )}
    </>
  );
}
```

`blockStyle` ersetzen — `height` wird zu `minHeight`, und die gestrichelte Unterkante kommt dazu:

```tsx
function blockStyle(slot: ShiftSlot, box: SlotBox): React.CSSProperties {
  const color = slot.color || '#2563eb';
  return {
    top: box.top,
    // #443: minHeight statt height — der Block wächst mit seinem Inhalt, statt
    // ihn abzuschneiden. Die zeitproportionale Höhe bleibt die Untergrenze.
    minHeight: box.height,
    left: `calc(${box.leftPct}% + 2px)`,
    width: `calc(${box.widthPct}% - 4px)`,
    backgroundColor: `${color}1a`, // ~10% alpha
    borderLeft: `3px solid ${color}`,
    // #443: sagt an, dass die Blockhöhe hier nicht mehr die Uhrzeit meint.
    borderBottom: box.grown ? `1px dashed ${color}` : undefined,
    // #305 M2d: dashed amber outline when ≥1 assigned person is not trained.
    outline: slot.unqualified ? '1px dashed #d97706' : undefined,
    outlineOffset: slot.unqualified ? '-2px' : undefined,
  };
}
```

In `DraggableBlock` und `StaticBlock` jeweils `overflow-hidden` aus der Klassenliste **entfernen** (es würde das Wachsen wieder zunichtemachen) und das `title`-Attribut ergänzen. In `DraggableBlock`:

```tsx
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800 cursor-grab touch-none"
      title={box.grown ? 'Anzeige reicht über das Zeitfenster hinaus' : undefined}
```

In `StaticBlock`:

```tsx
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800"
      title={box.grown ? 'Anzeige reicht über das Zeitfenster hinaus' : undefined}
```

**Achtung:** `DayColumn` hat auf seinem inneren `div` ebenfalls `overflow-hidden`. Das begrenzt das Wachstum am unteren Rand der Spalte. Dort `overflow-hidden` durch `overflow-visible` ersetzen:

```tsx
    <div
      className={`relative overflow-visible ${isOver && editable ? 'bg-primary/5' : ''}`}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/WeekGrid.test.tsx src/components/shiftplanning/weekGridUtils.test.ts --pool=threads
```
Erwartet: alle passed.

- [ ] **Step 5: Am laufenden Bild prüfen**

```bash
cd /home/manuel/claude/praxiszeit
docker compose build frontend && docker compose up -d frontend
```
Dann `http://localhost` im Browser öffnen, als `admin` / `Admin2025!` anmelden, Schichtplanung öffnen (falls das Feature-Flag aus ist: Einstellungen → Schichtplanung aktivieren) und einen Plan mit mehreren parallelen Slots ansehen. Erwartet: Namen brechen um statt abgeschnitten zu werden.

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/components/shiftplanning/WeekGrid.tsx \
        frontend/src/components/shiftplanning/WeekGrid.test.tsx
git commit -F - <<'EOF'
feat(#443): Wochenraster bricht um statt abzuschneiden

Der Block gibt seine Zeitdauer als minHeight vor und waechst mit dem Inhalt;
truncate und overflow-hidden fallen weg, sonst waere das Wachsen wirkungslos.
Der Hinweis je Einteilung erscheint als eigene Zeile. Waechst ein Block ueber
sein Zeitfenster hinaus, zeigt eine gestrichelte Unterkante samt title an,
dass die Hoehe dort nicht mehr die Uhrzeit meint.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 12: SlotDialog — Hinweisfeld

**Files:**
- Modify: `frontend/src/components/shiftplanning/SlotDialog.tsx`
- Modify: `frontend/src/pages/admin/ShiftPlanning.tsx` (Slot-Dialog-Zustand und Handler)
- Test: `frontend/src/components/shiftplanning/SlotDialog.test.tsx` (erweitern)

**Interfaces:**
- Consumes: `SlotInput.note` aus Task 9
- Produces: `SlotDialogInitial` trägt zusätzlich `note: string` (leerer String = kein Hinweis)

- [ ] **Step 1: Write the failing test**

In `frontend/src/components/shiftplanning/SlotDialog.test.tsx`:

Die vorhandene Importzeile erweitern (die Datei importiert bisher nur `render` und `screen`):

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
```

Das vorhandene `baseProps.initial` um das neue Pflichtfeld ergänzen, sonst brechen
die beiden bestehenden #371-Tests:

```tsx
    userIds: [] as string[],
    note: '',
```

Dann die neuen Fälle anhängen:

```tsx
it('lädt einen vorhandenen Hinweis und gibt ihn beim Speichern weiter', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <SlotDialog
      isOpen
      mode="edit"
      workstations={[{ id: 'w1', name: 'Tresen', location_id: null, location_name: null, color: null, sort_order: 0 }]}
      employees={[]}
      initial={{
        workstation_id: 'w1',
        weekday: 0,
        start_time: '08:00',
        end_time: '12:00',
        min_staff: 1,
        userIds: [],
        note: 'Einarbeitung Azubi',
      }}
      onSubmit={onSubmit}
      onClose={() => {}}
    />,
  );

  const field = screen.getByLabelText(/Hinweis/i) as HTMLTextAreaElement;
  expect(field.value).toBe('Einarbeitung Azubi');

  fireEvent.change(field, { target: { value: 'Nur Notfall' } });
  fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect(onSubmit.mock.calls[0][0]).toMatchObject({ note: 'Nur Notfall' });
});

it('sendet einen leeren Hinweis als null', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <SlotDialog
      isOpen
      mode="create"
      workstations={[{ id: 'w1', name: 'Tresen', location_id: null, location_name: null, color: null, sort_order: 0 }]}
      employees={[]}
      initial={{
        workstation_id: 'w1', weekday: 0, start_time: '08:00', end_time: '12:00',
        min_staff: 1, userIds: [], note: '',
      }}
      onSubmit={onSubmit}
      onClose={() => {}}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect(onSubmit.mock.calls[0][0]).toMatchObject({ note: null });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/SlotDialog.test.tsx --pool=threads
```
Erwartet: FAIL — es gibt kein Feld mit der Beschriftung „Hinweis".

- [ ] **Step 3: Feld ergänzen**

In `frontend/src/components/shiftplanning/SlotDialog.tsx`:

Import ergänzen:

```tsx
import FormTextarea from '../FormTextarea';
```

`SlotDialogInitial` erweitern:

```tsx
export interface SlotDialogInitial {
  workstation_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  min_staff: number;
  userIds: string[];
  note: string; // #443: leerer String = kein Hinweis
}
```

Zustand ergänzen (neben `minStaff`):

```tsx
  const [note, setNote] = useState(initial.note ?? '');
```

Im Mount-Effekt neben den übrigen `set…`-Aufrufen:

```tsx
      setNote(initial.note ?? '');
```

Eine gemeinsame Hilfsfunktion für das Zusammenbauen der Felder anlegen (direkt vor `handleCopy`) — damit `handleCopy` und `handleSubmit` nicht auseinanderlaufen:

```tsx
  // #443: eine Quelle für beide Absender (Speichern UND Kopieren). Ein leerer
  // Hinweis geht als null hinaus, damit die Anzeige nicht zwischen "kein
  // Hinweis" und "Hinweis aus Leerzeichen" unterscheiden muss.
  const currentFields = (): SlotInput => ({
    workstation_id: workstationId,
    weekday,
    start_time: start,
    end_time: end,
    min_staff: minStaff,
    note: note.trim() || null,
  });
```

`handleCopy` und `handleSubmit` auf `currentFields()` umstellen:

```tsx
      await onCopy(copyDays, currentFields(), userIds);
```
```tsx
      await onSubmit(currentFields(), userIds);
```

Das Feld selbst direkt **unter** dem Mindestbesetzungs-Feld einfügen:

```tsx
            <FormTextarea
              label="Hinweis (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={500}
              helperText="Erscheint im Plan und im Ausdruck, z. B. „Einarbeitung Azubi"."
            />
```

`FormTextarea` trägt bereits `helperText` als eigene Eigenschaft und reicht über
`TextareaHTMLAttributes` alle nativen Attribute durch — `maxLength` wirkt also
ohne Anpassung. Die Beschriftung wird über `htmlFor`/`id` mit dem Feld verbunden,
`getByLabelText(/Hinweis/i)` findet es deshalb.

In `frontend/src/pages/admin/ShiftPlanning.tsx`:

In `openCreateSlot` das Feld im `initial`-Objekt ergänzen:

```tsx
        note: '',
```

In `openEditSlot` (die Funktion, die aus einem `ShiftSlot` das `initial` baut) ergänzen:

```tsx
        note: slot.note ?? '',
```

Die Handler, die `api.createSlot` / `api.updateSlot` mit `fields` aufrufen, reichen `note` bereits durch, weil es Teil von `SlotInput` ist — dort ist nichts zu ändern. Falls die Handler die Felder einzeln aufzählen statt `fields` weiterzureichen, `note: fields.note` ergänzen.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/SlotDialog.test.tsx --pool=threads
npx tsc --noEmit
```
Erwartet: alle passed; `tsc` meldet zu diesen beiden Dateien nichts mehr.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/components/shiftplanning/SlotDialog.tsx \
        frontend/src/components/shiftplanning/SlotDialog.test.tsx \
        frontend/src/pages/admin/ShiftPlanning.tsx
git commit -F - <<'EOF'
feat(#443): Hinweisfeld im Slot-Dialog

Der Dialog laedt und speichert den Hinweis je Einteilung. Speichern und
"Auf Wochentage kopieren" bauen ihre Felder ueber eine gemeinsame Funktion
zusammen, damit die beiden Absender nicht auseinanderlaufen. Ein leerer
Hinweis geht als null hinaus.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 13: PlanSettingsDialog — Freigabe-Schalter

**Files:**
- Modify: `frontend/src/components/shiftplanning/PlanSettingsDialog.tsx`
- Test: `frontend/src/components/shiftplanning/PlanSettingsDialog.test.tsx` (neu)

**Interfaces:**
- Consumes: `PlanDetail.visible_to_employees` und `PlanUpdateBody.visible_to_employees` aus Task 9
- Produces: keine neuen Signaturen

- [ ] **Step 1: Write the failing test**

Neue Datei `frontend/src/components/shiftplanning/PlanSettingsDialog.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/shiftPlanning', () => ({ updatePlan: vi.fn() }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import * as api from '../../api/shiftPlanning';
import PlanSettingsDialog from './PlanSettingsDialog';
import type { PlanDetail } from '../../api/shiftPlanning';

const plan: PlanDetail = {
  id: 'p1',
  name: 'Herbstplan',
  description: null,
  is_active: false,
  active_from_date: '2026-09-01',
  active_until_date: null,
  active_today: false,
  visible_to_employees: false,
  slots: [],
  validation: { is_valid: true, understaffed_slot_ids: [] },
};

describe('PlanSettingsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.updatePlan as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it('spiegelt den aktuellen Freigabe-Zustand', () => {
    render(
      <PlanSettingsDialog isOpen plan={{ ...plan, visible_to_employees: true }} onSaved={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByLabelText(/Für Mitarbeitende sichtbar/i)).toBeChecked();
  });

  it('sendet die eingeschaltete Freigabe mit', async () => {
    render(<PlanSettingsDialog isOpen plan={plan} onSaved={() => {}} onClose={() => {}} />);

    fireEvent.click(screen.getByLabelText(/Für Mitarbeitende sichtbar/i));
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(api.updatePlan).toHaveBeenCalled());
    expect((api.updatePlan as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({
      visible_to_employees: true,
    });
  });

  it('sendet die Freigabe auch dann mit, wenn sie unverändert aus bleibt', async () => {
    render(<PlanSettingsDialog isOpen plan={plan} onSaved={() => {}} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));

    await waitFor(() => expect(api.updatePlan).toHaveBeenCalled());
    expect((api.updatePlan as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({
      visible_to_employees: false,
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/PlanSettingsDialog.test.tsx --pool=threads
```
Erwartet: FAIL — es gibt kein Element mit der Beschriftung „Für Mitarbeitende sichtbar".

- [ ] **Step 3: Schalter ergänzen**

In `frontend/src/components/shiftplanning/PlanSettingsDialog.tsx`:

Zustand ergänzen (neben `until`):

```tsx
  const [visible, setVisible] = useState(plan.visible_to_employees);
```

Im Mount-Effekt:

```tsx
      setVisible(plan.visible_to_employees);
```

Im `save`-Aufruf mitsenden:

```tsx
        visible_to_employees: visible,
```

Den Schalter nach dem Datumsfenster-Block einfügen:

```tsx
            <div className="rounded-lg border border-gray-200 p-3">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={(e) => setVisible(e.target.checked)}
                  className="mt-0.5 rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">
                  Für Mitarbeitende sichtbar
                  <span className="mt-1 block text-xs text-gray-400">
                    Der Plan erscheint dann in der Mitarbeiteransicht, auch wenn er heute noch nicht gilt —
                    etwa um einen ab September geltenden Plan vorab bekannt zu machen. Ein heute aktiver Plan
                    ist ohnehin sichtbar.
                  </span>
                </span>
              </label>
            </div>
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/components/shiftplanning/PlanSettingsDialog.test.tsx --pool=threads
```
Erwartet: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/components/shiftplanning/PlanSettingsDialog.tsx \
        frontend/src/components/shiftplanning/PlanSettingsDialog.test.tsx
git commit -F - <<'EOF'
feat(#443): Freigabe-Schalter in den Plan-Einstellungen

Ein Admin gibt einen Plan damit ausdruecklich fuer Mitarbeitende frei, auch
wenn er heute noch nicht gilt. Der Schalter wird bei jedem Speichern
mitgesendet, weil der PUT ein Vollersatz ist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 14: PDF-Knopf in der Admin-Werkzeugleiste

**Files:**
- Modify: `frontend/src/pages/admin/ShiftPlanning.tsx`
- Test: manuelle Prüfung (Schritt 4) — die Seite hat keinen Komponententest, und einen für einen einzelnen Knopf aufzusetzen wäre mehr Gerüst als Nutzen

**Interfaces:**
- Consumes: `downloadPlanPdf` aus Task 9
- Produces: keine

- [ ] **Step 1: Knopf ergänzen**

In `frontend/src/pages/admin/ShiftPlanning.tsx`:

Das Icon zum bestehenden `lucide-react`-Import hinzufügen (`Printer`).

Handler neben den übrigen Plan-Aktionen anlegen:

```tsx
  // #443: PDF-Aushang des offenen Plans.
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const downloadPdf = async () => {
    if (!planDetail || downloadingPdf) return;
    setDownloadingPdf(true);
    try {
      await api.downloadPlanPdf(planDetail.id, planDetail.name);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Erstellen des PDF'));
    } finally {
      setDownloadingPdf(false);
    }
  };
```

In der Werkzeugleiste, zwischen „Bearbeiten" und „Duplizieren":

```tsx
                    <Button variant="secondary" icon={Printer} loading={downloadingPdf} onClick={downloadPdf}>
                      PDF
                    </Button>
```

- [ ] **Step 2: Typprüfung**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx tsc --noEmit
```
Erwartet: keine Fehler in `src/pages/admin/ShiftPlanning.tsx`.

- [ ] **Step 3: Volle Frontend-Suite**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run --pool=threads
```
Erwartet: alle passed. Meldet ein Test ein fehlendes `note`/`visible_to_employees` in einem selbstgebauten Objekt, das Feld dort ergänzen.

- [ ] **Step 4: Am laufenden Bild prüfen**

```bash
cd /home/manuel/claude/praxiszeit
docker compose build frontend && docker compose up -d frontend
```
Als `admin` / `Admin2025!` anmelden, Schichtplanung öffnen, einen Plan wählen, „PDF" klicken. Erwartet: eine PDF-Datei wird heruntergeladen und lässt sich öffnen; Kopfzeile, Wochentagsspalten, Namen und ein etwaiger Hinweis stehen darin.

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/pages/admin/ShiftPlanning.tsx
git commit -F - <<'EOF'
feat(#443): PDF-Knopf in der Schichtplan-Werkzeugleiste

Laedt den offenen Plan als Aushang herunter.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 15: Mitarbeiteransicht — Auswahl statt Filter

**Files:**
- Modify: `frontend/src/pages/ShiftPlanning.tsx`
- Test: `frontend/src/pages/ShiftPlanning.test.tsx` (neu)

**Interfaces:**
- Consumes: `listPlans`/`getPlan`/`downloadPlanPdf` aus Task 9, die serverseitige Filterung aus Task 2
- Produces: keine

**Der entscheidende Punkt:** Die Seite filtert heute clientseitig `summaries.filter(p => p.active_today)`. Bleibt dieser Filter stehen, wirft er den freigegebenen Zukunftsplan wieder weg — das Feature wäre serverseitig fertig und am Bildschirm unsichtbar. Der Filter **muss** verschwinden.

- [ ] **Step 1: Write the failing test**

Neue Datei `frontend/src/pages/ShiftPlanning.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/shiftPlanning', async () => {
  const actual = await vi.importActual<typeof import('../api/shiftPlanning')>('../api/shiftPlanning');
  return { ...actual, listPlans: vi.fn(), getPlan: vi.fn(), downloadPlanPdf: vi.fn() };
});
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('../stores/systemStore', () => ({
  useSystemStore: (sel: (s: unknown) => unknown) =>
    sel({ getShiftPlanningWeekdays: () => [0, 1, 2, 3, 4] }),
}));

import * as api from '../api/shiftPlanning';
import ShiftPlanning from './ShiftPlanning';

const summary = (over: Record<string, unknown> = {}) => ({
  id: 'p1', name: 'Aktueller Plan', description: null, is_active: true,
  active_from_date: null, active_until_date: null, active_today: true,
  visible_to_employees: false, slot_count: 1, is_valid: true, ...over,
});

const detail = (over: Record<string, unknown> = {}) => ({
  ...summary(), slots: [],
  validation: { is_valid: true, understaffed_slot_ids: [] }, ...over,
});

describe('Mitarbeiteransicht Schichtplan', () => {
  beforeEach(() => vi.clearAllMocks());

  it('zeigt einen freigegebenen Zukunftsplan, der heute NICHT gilt', async () => {
    const future = summary({
      id: 'p2', name: 'Ab September', is_active: false, active_today: false,
      visible_to_employees: true, active_from_date: '2026-09-01',
    });
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([future]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail(future));

    render(<ShiftPlanning />);

    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p2'));
    expect(screen.getByText('Ab September')).toBeInTheDocument();
  });

  it('bietet eine Auswahl, sobald mehr als ein Plan sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary(),
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getByRole('option', { name: /Ab September/ })).toBeInTheDocument();
  });

  it('wählt den heute geltenden Plan vor', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary({ id: 'p2', name: 'Ab September', is_active: false, active_today: false, visible_to_employees: true }),
      summary({ id: 'p1', name: 'Aktueller Plan', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalledWith('p1'));
  });

  it('lädt nur den gewählten Plan, nicht alle', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([
      summary(), summary({ id: 'p2', name: 'Zweiter', active_today: true }),
      summary({ id: 'p3', name: 'Dritter', active_today: true }),
    ]);
    (api.getPlan as ReturnType<typeof vi.fn>).mockResolvedValue(detail());

    render(<ShiftPlanning />);
    await waitFor(() => expect(api.getPlan).toHaveBeenCalled());
    expect((api.getPlan as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
  });

  it('zeigt den leeren Zustand, wenn nichts sichtbar ist', async () => {
    (api.listPlans as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<ShiftPlanning />);
    await waitFor(() => expect(screen.getByText(/Kein Schichtplan/i)).toBeInTheDocument());
    expect(api.getPlan).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/pages/ShiftPlanning.test.tsx --pool=threads
```
Erwartet: FAIL — die Seite filtert `active_today` weg und lädt alle Pläne parallel.

- [ ] **Step 3: Seite umbauen**

`frontend/src/pages/ShiftPlanning.tsx` vollständig ersetzen:

```tsx
import { useEffect, useState } from 'react';
import { CalendarDays, Printer } from 'lucide-react';
import Button from '../components/Button';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import WeekGrid from '../components/shiftplanning/WeekGrid';
import { useToast } from '../contexts/ToastContext';
import { getErrorMessage } from '../utils/errorMessage';
import { useSystemStore } from '../stores/systemStore';
import * as api from '../api/shiftPlanning';
import type { PlanDetail, PlanSummary } from '../api/shiftPlanning';

/** Vermerk neben dem Plannamen in der Auswahl: gilt er heute, oder ab wann? */
function planHint(p: PlanSummary): string {
  if (p.active_today) return 'Aktuell';
  if (p.active_from_date) {
    const d = new Date(`${p.active_from_date}T00:00:00`);
    return `Ab ${d.toLocaleDateString('de-DE')}`;
  }
  return 'Vorschau';
}

export default function ShiftPlanning() {
  const toast = useToast();
  const weekdays = useSystemStore((s) => s.getShiftPlanningWeekdays());
  const [loading, setLoading] = useState(true);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PlanDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // #443: NICHT mehr clientseitig auf active_today filtern. Der Server
        // liefert Mitarbeitenden ohnehin nur Sichtbares (heute gültig ODER
        // ausdrücklich freigegeben) — ein Filter hier würde genau die
        // freigegebenen Zukunftspläne wieder wegwerfen, um die es geht.
        const summaries = await api.listPlans();
        if (cancelled) return;
        setPlans(summaries);
        const preferred = summaries.find((p) => p.active_today) ?? summaries[0];
        setSelectedId(preferred ? preferred.id : null);
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden der Schichtpläne'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Einmalig beim Mounten. `toast` ist eine stabile Referenz und wird nur im
    // catch-Zweig genutzt (vgl. Dashboard.tsx).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    api
      .getPlan(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) toast.error(getErrorMessage(err, 'Fehler beim Laden des Schichtplans'));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const downloadPdf = async () => {
    if (!detail || downloading) return;
    setDownloading(true);
    try {
      await api.downloadPlanPdf(detail.id, detail.name);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Erstellen des PDF'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Schichtplan</h1>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : plans.length === 0 ? (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-6">
          <EmptyState
            icon={CalendarDays}
            title="Kein Schichtplan verfügbar"
            description="Sobald ein Administrator einen Plan aktiv schaltet oder für Mitarbeitende freigibt, erscheint er hier."
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            {plans.length > 1 ? (
              <select
                aria-label="Schichtplan wählen"
                value={selectedId ?? ''}
                onChange={(e) => setSelectedId(e.target.value)}
                className="rounded-lg border-gray-300 text-sm py-1"
              >
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {planHint(p)}
                  </option>
                ))}
              </select>
            ) : (
              <h2 className="text-xl font-semibold text-gray-900">{plans[0].name}</h2>
            )}
            {detail && (
              <Button variant="secondary" icon={Printer} loading={downloading} onClick={downloadPdf}>
                PDF
              </Button>
            )}
          </div>

          {detailLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : detail ? (
            <>
              {detail.description && <p className="text-sm text-gray-500 mb-3">{detail.description}</p>}
              {!detail.active_today && (
                <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
                  Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben.
                </p>
              )}
              <WeekGrid slots={detail.slots} weekdays={weekdays} />
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run src/pages/ShiftPlanning.test.tsx --pool=threads
npx tsc --noEmit
```
Erwartet: 5 passed, keine Typfehler.

- [ ] **Step 5: Volle Frontend-Suite**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx vitest run --pool=threads
```
Erwartet: alle passed.

- [ ] **Step 6: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add frontend/src/pages/ShiftPlanning.tsx frontend/src/pages/ShiftPlanning.test.tsx
git commit -F - <<'EOF'
feat(#443): Mitarbeiteransicht zeigt freigegebene Plaene zur Auswahl

Der clientseitige active_today-Filter faellt weg — er haette genau die
freigegebenen Zukunftsplaene wieder weggeworfen, um die es geht; der Server
filtert bereits. Bei mehreren sichtbaren Plaenen gibt es eine Auswahl,
vorbelegt mit dem heute geltenden, und geladen wird nur der gewaehlte statt
aller. Ein noch nicht geltender Plan ist als Vorschau gekennzeichnet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 16: E2E — Freigabe wird beim Mitarbeitenden sichtbar

**Files:**
- Create: `e2e/tests/admin/shift-planning-visibility.spec.ts`

**Interfaces:**
- Consumes: alle vorherigen Tasks (durchgehender Pfad)
- Produces: keine

**Warum ausgerechnet dieser Test:** Die Mitarbeiterseite filterte vor #443
clientseitig auf „heute aktiv". Bliebe der Filter stehen, wären sämtliche
Backend-Tests grün und das Feature am Bildschirm trotzdem unsichtbar. Kein
anderer Test in dieser Arbeit deckt genau diese Naht ab.

**Fixtures:** `e2e/fixtures/base.fixture.ts` exportiert `test`; verfügbar sind
unter anderem `adminPage`, `adminApi`, `employeePage`, `employeeApi` und
`testEmployee`. Wichtig: `employeePage` ist eine **eigene** Sitzung eines
Mitarbeiter-Kontos — die vorhandene `shift-planning.spec.ts` prüft die
Mitarbeiteransicht über `adminPage`, was hier **nicht** taugt: ein Admin sieht
ohnehin jeden Plan, der Test würde also nichts belegen.

- [ ] **Step 1: Test schreiben**

Neue Datei `e2e/tests/admin/shift-planning-visibility.spec.ts`:

```ts
import { test, expect } from '../../fixtures/base.fixture';

/**
 * #443: Ein Admin gibt einen noch nicht geltenden Plan für Mitarbeitende frei;
 * der Mitarbeitende findet ihn daraufhin in seiner Ansicht.
 *
 * Der Plan wird über die API angelegt statt über die Oberfläche — der Weg
 * "Plan anlegen per Dialog" ist bereits in shift-planning.spec.ts abgedeckt,
 * und dieser Test soll die Sichtbarkeitsnaht prüfen, nicht sie wiederholen.
 * Die Freigabe selbst läuft bewusst über die Oberfläche: der Schalter im
 * Einstellungsdialog ist Teil dessen, was hier belegt werden soll.
 */
test.describe('Schichtplan-Freigabe (#443)', () => {
  const unique = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const releasedName = `E2E-Freigegeben-${unique}`;
  const draftName = `E2E-Entwurf-${unique}`;

  test.afterAll(async ({ adminApi }) => {
    try {
      const plans = await adminApi.get('/shift-planning/plans');
      for (const p of plans) {
        if (p.name === releasedName || p.name === draftName) {
          await adminApi.delete(`/shift-planning/plans/${p.id}`);
        }
      }
    } catch {
      /* ignore */
    }
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'false' });
  });

  test('ein freigegebener, noch nicht geltender Plan erscheint beim Mitarbeitenden', async ({
    adminPage,
    adminApi,
    employeePage,
  }) => {
    await adminApi.put('/admin/settings/shift_planning_enabled', { value: 'true' });

    // Zwei Pläne, beide inaktiv und ohne Datumsfenster — beide gelten heute nicht.
    const released = await adminApi.post('/shift-planning/plans', { name: releasedName });
    await adminApi.post('/shift-planning/plans', { name: draftName });

    // Gegenprobe VOR der Freigabe: der Mitarbeitende sieht keinen der beiden.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.getByRole('heading', { name: 'Schichtplan' })).toBeVisible();
    // In `main` scopen: die Hilfe-Seitenleiste dupliziert Texte und löst sonst
    // strict-mode-Verstöße aus.
    await expect(employeePage.locator('main').getByText(releasedName)).toHaveCount(0);
    await expect(employeePage.locator('main').getByText(draftName)).toHaveCount(0);

    // Freigabe über die Oberfläche: Plan öffnen, Einstellungen, Schalter, speichern.
    await adminPage.goto('/admin/shift-planning');
    await adminPage.locator('main').getByText(releasedName).first().click();
    await expect(adminPage.getByRole('heading', { name: releasedName })).toBeVisible();
    await adminPage.getByRole('button', { name: 'Bearbeiten' }).click();

    const modal = adminPage.locator('div.fixed.inset-0').filter({ hasText: 'Plan-Einstellungen' });
    await expect(modal.getByRole('heading', { name: 'Plan-Einstellungen' })).toBeVisible();
    await modal.getByLabel(/Für Mitarbeitende sichtbar/i).check();

    const save = adminPage.waitForResponse(
      (r) => r.url().includes(`/api/shift-planning/plans/${released.id}`) && r.request().method() === 'PUT',
    );
    await modal.getByRole('button', { name: 'Speichern' }).click();
    await save;

    // Jetzt sieht der Mitarbeitende den freigegebenen Plan — den Entwurf aber nicht.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.locator('main').getByText(releasedName).first()).toBeVisible();
    await expect(employeePage.locator('main').getByText(draftName)).toHaveCount(0);

    // Und er ist als noch nicht geltend gekennzeichnet.
    await expect(employeePage.locator('main').getByText(/gilt noch nicht/i)).toBeVisible();
  });

  test('der PDF-Knopf liefert dem Mitarbeitenden eine Datei', async ({ employeePage }) => {
    // Läuft nach dem ersten Test: der freigegebene Plan steht noch.
    await employeePage.goto('/shift-planning');
    await expect(employeePage.locator('main').getByText(releasedName).first()).toBeVisible();

    const download = employeePage.waitForEvent('download');
    await employeePage.getByRole('button', { name: 'PDF' }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  });
});
```

**Hinweis zur Reihenfolge:** Der zweite Test setzt auf dem Zustand des ersten auf.
Läuft die Datei mit mehreren Arbeitern parallel, ist das nicht zugesichert. Falls
Playwright hier parallelisiert, oben ergänzen:

```ts
test.describe.configure({ mode: 'serial' });
```

Vorher prüfen, wie die vorhandenen Shift-Specs das halten:
```bash
grep -rn "describe.configure\|fullyParallel\|workers" /home/manuel/claude/praxiszeit/e2e/tests/admin/shift-planning*.spec.ts /home/manuel/claude/praxiszeit/e2e/playwright.config.ts
```

- [ ] **Step 2: Rate-Limits hochsetzen und Test fahren**

```bash
cd /home/manuel/claude/praxiszeit
grep -q "LOGIN_RATE_LIMIT" .env || printf '\nLOGIN_RATE_LIMIT=10000/minute\nREFRESH_RATE_LIMIT=10000/minute\n' >> .env
docker compose up -d backend
cd e2e && npx playwright test tests/admin/shift-planning-visibility.spec.ts --output=/tmp/pw-443
```
Ohne erhöhte Limits läuft die Suite in einen HTTP-429-Sturm (gemessen: 19 failed /
40 flaky / 208× 429). `--output=/tmp/...` umgeht ein `test-results/`, das aus
früheren Docker-Läufen root-owned sein kann.

Erwartet: 2 passed.

- [ ] **Step 3: Die übrigen Schichtplanungs-E2E gegenprüfen**

```bash
cd /home/manuel/claude/praxiszeit/e2e
npx playwright test tests/admin/shift-planning.spec.ts tests/admin/shift-planning-m2.spec.ts \
  tests/admin/shift-planning-followups.spec.ts --output=/tmp/pw-443
```
Erwartet: alle passed. Achtung: `shift-planning.spec.ts` prüft die
Mitarbeiteransicht über `adminPage` und erwartet dort genau **einen** Plan im
Bild — legt dieser neue Test parallel weitere an, kann das kollidieren. Tritt das
auf, im neuen Test eindeutigere Namen verwenden (sie tragen bereits Zeitstempel
und Zufallszahl) und den Locator im **alten** Test **nicht** anfassen.

- [ ] **Step 4: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add e2e/tests/admin/shift-planning-visibility.spec.ts
git commit -F - <<'EOF'
test(#443): E2E fuer die Freigabe eines Schichtplans

Deckt die Naht ab, an der das Feature am leisesten kaputtgehen kann: die
Mitarbeiterseite filterte frueher clientseitig auf "heute aktiv". Bliebe der
Filter stehen, waeren alle Backend-Tests gruen und das Feature am Bildschirm
trotzdem unsichtbar. Mit Gegenprobe vor der Freigabe, Gegenprobe fuer den
nicht freigegebenen Entwurf und einem Durchlauf des PDF-Knopfs. Geprueft wird
ueber employeePage, nicht ueber adminPage — ein Admin sieht ohnehin jeden Plan.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 17: Dokumentation über alle fünf Flächen

**Files:**
- Modify: `docs/SCHICHTPLANUNG.md`
- Modify: `frontend/src/components/DocViewer.tsx` (`handbuchAdminSections` **und** `handbuchMitarbeiterSections`)
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md`, `docs/handbuch/HANDBUCH-MITARBEITER.md`
- Modify: `frontend/public/help/HANDBUCH-ADMIN.md`, `frontend/public/help/HANDBUCH-MITARBEITER.md` (byte-identische Spiegel)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: das fertige Verhalten aus Tasks 1–16
- Produces: keine

- [ ] **Step 1: Betroffene Stellen finden**

```bash
cd /home/manuel/claude/praxiszeit
grep -n "Schichtplan" docs/handbuch/HANDBUCH-ADMIN.md | head -20
grep -n "Schichtplan" docs/handbuch/HANDBUCH-MITARBEITER.md | head -20
grep -n "Schichtplan\|shiftplan" frontend/src/components/DocViewer.tsx | head -20
ls docs/handbuch/ frontend/public/help/
```

- [ ] **Step 2: Die drei neuen Punkte überall beschreiben**

Inhaltlich in jeder Fläche unterbringen, im Ton der jeweiligen Umgebung:

1. **Freigabe** (Admin-Handbuch): In den Plan-Einstellungen gibt es „Für Mitarbeitende sichtbar". Damit erscheint ein Plan in der Mitarbeiteransicht, auch wenn er heute noch nicht gilt — gedacht, um einen künftigen Plan vorab bekannt zu machen. Ein heute geltender Plan ist ohnehin sichtbar. Eine Kopie erbt die Freigabe nicht.
2. **Hinweis je Einteilung** (beide Handbücher): Im Slot-Dialog gibt es „Hinweis (optional)", höchstens 500 Zeichen, sichtbar im Plan und im Ausdruck. Beispiel: „Einarbeitung Azubi".
3. **PDF-Ausdruck** (beide Handbücher): Der Knopf „PDF" erzeugt einen Aushang im Querformat mit einer Tabelle Arbeitsplatz × Wochentag. Mitarbeitende können den Plan drucken, den sie sehen.

Im **Mitarbeiter**-Handbuch zusätzlich: Sind mehrere Pläne freigegeben, steht oben eine Auswahl; ein noch nicht geltender Plan ist als Vorschau gekennzeichnet.

- [ ] **Step 3: Spiegel abgleichen**

```bash
cd /home/manuel/claude/praxiszeit
cp docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
cp docs/handbuch/HANDBUCH-MITARBEITER.md frontend/public/help/HANDBUCH-MITARBEITER.md
diff -q docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
diff -q docs/handbuch/HANDBUCH-MITARBEITER.md frontend/public/help/HANDBUCH-MITARBEITER.md
```
Erwartet: `diff -q` gibt nichts aus. Vor dem Kopieren prüfen, ob im `public/help`-Spiegel weitere Dateien liegen, die ebenfalls betroffen sind.

- [ ] **Step 4: CLAUDE.md ergänzen**

Im Abschnitt „Kritische Regeln", bei den Schichtplanungs-Einträgen, anfügen:

```markdown
- **Schichtplan-Freigabe + PDF-Aushang (#443):** `shift_plans.visible_to_employees` (Bool, Default **false**, Migration `070`) gibt einen Plan ausdrücklich für Mitarbeitende frei, unabhängig von „gilt heute". Die Regel lebt in **`shift_planning_service.is_plan_visible_to(plan, d, is_admin)`** — `list_plans` und `get_plan` hatten je eine Inline-Kopie, jede neue Lesefläche ruft den Helfer. `duplicate_plan` erbt die Freigabe **nicht** (Kopie = Entwurf). ⚠️ **Die Mitarbeiterseite darf NICHT clientseitig auf `active_today` filtern** — genau das tat sie vor #443 und hätte die Freigabe unsichtbar gemacht, obwohl das Backend fertig ist (E2E `shift-planning-visibility.spec.ts` sichert das ab). `shift_slots.note` (TEXT, max. 500 am Rand) ist der Hinweis je Einteilung, reines Anzeigefeld ohne Berechnungswirkung; er wird in `lifecycle_service.anonymize_tenant` geleert. **PDF:** `GET /plans/{id}/export.pdf` → `app/services/shift_plan_export_service.py`, bewusst NICHT in `export_service.py` (dort liegt die §16-/Calc-Fläche). Der Renderer ist eine **reine** Funktion über dem Dict von `_build_plan_detail` — kein `db`-Zugriff, damit der Ausdruck nicht zu einem zweiten Abfragepfad auswächst. Zugang über `is_plan_visible_to`, nicht `require_admin` (MA druckt nur, was er ohnehin sieht); Einweisungs-Flags stehen nie im PDF. Alle Nutzertexte durch `escape_pdf_text`.
```

- [ ] **Step 5: Commit**

```bash
cd /home/manuel/claude/praxiszeit
git add docs/ frontend/public/help/ frontend/src/components/DocViewer.tsx CLAUDE.md
git commit -F - <<'EOF'
docs(#443): Freigabe, Hinweisfeld und PDF-Aushang dokumentiert

Alle fuenf Nutzer-Doku-Flaechen: SCHICHTPLANUNG.md, beide Handbuecher, der
byte-identische public/help-Spiegel und die In-App-Hilfe im DocViewer. Dazu
der Eintrag in CLAUDE.md mit der Warnung, dass die Mitarbeiterseite nicht
wieder clientseitig auf "heute aktiv" filtern darf.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 18: Abschluss — volle Prüfung

**Files:** keine Änderung erwartet; was auffällt, wird hier behoben.

- [ ] **Step 1: Volle Backend-Suite**

```bash
cd /home/manuel/claude/praxiszeit
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T backend rm -f /app/test.db </dev/null
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py </dev/null 2>&1 | tail -25
```
Erwartet: keine neuen Fehlschläge. Bekannt vorbelastet sind einige `shift_planning`-MyToday-Tests (datumsabhängig, schlagen auch auf `master` fehl) — vor dem Melden mit `git stash && <Lauf> && git stash pop` gegen `master` gegenprüfen, ob ein Fehlschlag wirklich neu ist.

- [ ] **Step 2: RLS-Tests gegen PostgreSQL**

```bash
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_tenant_rls.py -q </dev/null 2>&1 | tail -10
```
Erwartet: alle passed. Die beiden neuen Spalten liegen auf bereits RLS-geschützten Tabellen; dieser Lauf belegt, dass Migration 070 die Policies nicht angefasst hat.

- [ ] **Step 3: Volle Frontend-Prüfung**

```bash
cd /home/manuel/claude/praxiszeit/frontend
npx tsc --noEmit && npx vitest run --pool=threads && npx eslint src --max-warnings 0 && npm run build
```
Erwartet: alles sauber.

- [ ] **Step 4: Volle E2E-Suite**

```bash
cd /home/manuel/claude/praxiszeit
docker compose build frontend && docker compose up -d
cd e2e && npx playwright test --output=/tmp/pw-443-full 2>&1 | tail -20
```
Erwartet: keine neuen Fehlschläge gegenüber dem Stand vor der Arbeit.

- [ ] **Step 5: Migration hin und zurück**

```bash
cd /home/manuel/claude/praxiszeit
docker compose exec -T backend python -c "from alembic.config import main; main(['downgrade','-1'])" </dev/null
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d shift_slots" </dev/null | grep -c note || echo "Spalte weg — richtig"
docker compose exec -T backend python -c "from alembic.config import main; main(['upgrade','head'])" </dev/null
docker compose exec -T db psql -U praxiszeit -d praxiszeit -c "\d shift_slots" </dev/null | grep note
```
Erwartet: das Herabstufen entfernt beide Spalten, das Heraufstufen legt sie wieder an. Nicht `python -m alembic` verwenden (cwd-Shadowing).

- [ ] **Step 6: Stand melden**

Zusammenfassen: was umgesetzt ist, welche Prüfungen mit welchem Ergebnis liefen, was offen blieb. Keinen Push, keinen PR — das entscheidet der Mensch.
