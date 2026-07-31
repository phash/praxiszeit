# Tagesplan-Historie (#431) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mitarbeitende mit individuellem Tagesplan bekommen dieselbe datierte Stundenhistorie wie alle anderen — Tageswerte, Modus und Arbeitstage werden pro Wirkungsdatum historisiert statt still rückwirkend überschrieben.

**Architecture:** Die bestehende Tabelle `working_hours_changes` wird zur **Snapshot-Zeile**: jede Zeile trägt den vollständigen Vertragszustand ab ihrem Datum (`weekly_hours`, `use_daily_schedule`, `hours_monday…friday`, `work_days_per_week`). Ein neuer Resolver `get_schedule_for_date` löst diesen Snapshot pro Datum auf — mit Query-Pfad und In-Memory-Preload-Pfad, exakt nach dem Vorbild von `get_weekly_hours_for_date`. `get_daily_target_for_date` bekommt den aufgelösten Snapshot als **Pflichtparameter**, damit keine Call-Site still auf dem aktuellen Plan stehenbleibt.

**Tech Stack:** FastAPI (Python 3.12) · SQLAlchemy + Alembic · PostgreSQL 16/18 (Tests: SQLite) · React 18 + TypeScript · Vitest/RTL · Playwright

## Global Constraints

- Repo-Root: `/home/manuel/claude/praxiszeit`. Branch: `feat/431-tagesplan-historie` (existiert bereits, Spec ist dort committet).
- Spec: `docs/superpowers/specs/2026-07-29-tagesplan-historie-design.md` — bei Widerspruch gilt die Spec.
- **Byte-Identität**: für Mitarbeitende ohne `use_daily_schedule` und ohne neue Zeilen darf sich **kein** berechneter Wert ändern. Jede Task, die Calc anfasst, endet mit einem grünen Lauf der Referenz-Suiten.
- Backend-Tests laufen im Container: `docker compose exec -T backend pytest …`. Der Container ist **gebaut**, kein Host-Volume → vor jedem Lauf `docker compose cp backend/app backend:/app/` und `docker compose cp backend/tests backend:/app/`.
- Nacktes `pytest tests/` **nie** ohne `--ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py` (vergiftet sonst die geteilte SQLite-Engine, ~26 Folgefehler).
- Vitest auf dieser Maschine nur mit `--pool=threads` (`npx vitest run --pool=threads`).
- Frontend-Kommandos ohne `npm install` (Host-`node_modules` ist vorhanden, root-owned): `npx tsc --noEmit`, `npm run build`, `npx vitest run --pool=threads`.
- Alembic-Revision-IDs ≤ 32 Zeichen. HEAD ist `066_vacation_days_decimal`.
- Migrationen **nicht** via `python -m alembic` (cwd-Shadowing) — programmatisch: `python -c "from alembic.config import main; main([...])"`.
- F-026: jede `db.query(...)` auf tenant-scoped Tabellen zusätzlich mit `Model.tenant_id == …` filtern.
- Pydantic Response-Schemas: `float`, nie `Decimal`. Rohe `json.dumps`/`JSONResponse`-Pfade brauchen `float()`-Casts.
- Commits: deutsche Nachricht, Body erklärt das *Warum*, `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. Commit-Text immer via `git commit -F -` mit Heredoc (Sonderzeichen brechen `-m`).
- Kein `--no-verify`; der Pre-Commit-Secret-Scanner darf nicht umgangen werden.

## File Structure

| Datei | Rolle nach dem Umbau |
|---|---|
| `backend/app/models/working_hours_change.py` | Snapshot-Zeile: + `use_daily_schedule`, `hours_monday…friday`, `work_days_per_week` |
| `backend/alembic/versions/…-067_schedule_history.py` | **neu** — Spalten + Backfill aus `users` |
| `backend/app/services/calculation_service.py` | `Schedule` + `get_schedule_for_date` (neu), `get_daily_target_for_date` mit Pflichtparameter, alle Per-Tag-Schleifen, `weekly_hours_segments` → Snapshot-Segmente |
| `backend/app/schemas/working_hours_change.py` | Create/Response/Preview tragen Modus + Tageswerte + Arbeitstage; Preview zusätzlich 5 Soll-Paare und Saldo/Urlaub vorher-nachher |
| `backend/app/routers/admin_users.py` | create/preview/delete ohne Tagesplan-Sperre; `PUT` sperrt die drei neuen Felder |
| `backend/app/services/export_service.py`, `ods_export_service.py`, `journal_service.py` | Per-Tag-Soll über den Resolver; #415-Kopfzeilen mit Tagesmuster |
| `frontend/src/pages/admin/users/WorkingHoursModal.tsx` | Modus-Umschalter + 5 Tagesfelder + erweiterte Auswirkungs-Box |
| `frontend/src/pages/admin/users/UserForm.tsx` | Tagesstunden/Arbeitstage/Modus beim Bearbeiten read-only + Button |
| `frontend/src/utils/formatters.ts` | `formatWeeklyHoursChanges` — wortgleicher Zwilling zu `export_service.format_weekly_hours_history` |

---

### Task 1: Snapshot-Spalten + Migration 067

**Files:**
- Modify: `backend/app/models/working_hours_change.py:16-25`
- Create: `backend/alembic/versions/2026_07_29_1200-067_schedule_history.py`
- Test: `backend/tests/test_schedule_history_model.py` (neu)

**Interfaces:**
- Produces: `WorkingHoursChange.use_daily_schedule: bool`, `.hours_monday|tuesday|wednesday|thursday|friday: Optional[Decimal]`, `.work_days_per_week: Optional[int]`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_schedule_history_model.py`:

```python
"""#431: die WorkingHoursChange-Zeile ist ein vollstaendiger Vertrags-Snapshot."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange


def test_row_carries_full_snapshot(db_session, test_user):
    row = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1),
        weekly_hours=Decimal("17.0"),
        use_daily_schedule=True,
        hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"),
        hours_wednesday=Decimal("4.0"),
        hours_thursday=None,
        hours_friday=None,
        work_days_per_week=3,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.use_daily_schedule is True
    assert Decimal(str(row.hours_monday)) == Decimal("8.0")
    assert row.hours_thursday is None
    assert row.work_days_per_week == 3


def test_defaults_are_weekly_mode(db_session, test_user):
    """Eine Zeile ohne Tagesangaben ist eine gleichmaessige Zeile — das ist der
    Zustand aller Bestandszeilen von Nicht-Tagesplan-Mitarbeitenden."""
    row = WorkingHoursChange(
        user_id=test_user.id,
        tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1),
        weekly_hours=Decimal("40.0"),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.use_daily_schedule is False
    assert row.hours_monday is None
    assert row.work_days_per_week is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_schedule_history_model.py -v
```
Erwartet: FAIL — `TypeError: 'use_daily_schedule' is an invalid keyword argument for WorkingHoursChange`.

- [ ] **Step 3: Modell erweitern**

In `backend/app/models/working_hours_change.py` nach `weekly_hours` einfügen (Import `Boolean, Integer` aus sqlalchemy ergänzen):

```python
    # #431: die Zeile ist ein vollstaendiger Vertrags-Snapshot ab
    # ``effective_from`` — nicht nur die Wochenstunden. Damit ist „die naechste
    # Zeile" immer die richtige Fenstergrenze, egal WELCHER Soll-Treiber sich
    # geaendert hat (Modus, Tageswerte, Arbeitstage, Wochenstunden).
    use_daily_schedule = Column(Boolean, nullable=False, default=False, server_default='false')
    hours_monday = Column(Numeric(4, 2), nullable=True)
    hours_tuesday = Column(Numeric(4, 2), nullable=True)
    hours_wednesday = Column(Numeric(4, 2), nullable=True)
    hours_thursday = Column(Numeric(4, 2), nullable=True)
    hours_friday = Column(Numeric(4, 2), nullable=True)
    # NULL = Rueckfall auf user.work_days_per_week (Bestandszeilen vor #431
    # tragen den Backfill-Wert, neue Zeilen setzen ihn immer).
    work_days_per_week = Column(Integer, nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose cp backend/app backend:/app/ && \
docker compose exec -T backend pytest tests/test_schedule_history_model.py -v
```
Erwartet: 2 passed.

- [ ] **Step 5: Migration schreiben**

`backend/alembic/versions/2026_07_29_1200-067_schedule_history.py`:

```python
"""#431: working_hours_changes wird ein vollstaendiger Vertrags-Snapshot

Mitarbeitende mit individuellem Tagesplan hatten bisher keine Stundenhistorie —
ihr Tagessoll kam live aus users.hours_monday…friday, jede Aenderung verschob
still das Soll der gesamten Vergangenheit. Die Historien-Zeile traegt jetzt
Modus, Tageswerte und Arbeitstage mit.

Backfill: jede BESTEHENDE Zeile bekommt den heutigen Zustand ihres Users. Damit
bleibt das Verhalten nach der Migration byte-identisch — insbesondere im
Mischfall (Tagesplan-MA mit Alt-Zeilen aus der Zeit davor: diese Zeilen sind
heute wirkungslos und wuerden ohne Backfill schlagartig als gleichmaessige
Zeilen scharf geschaltet).
"""
from alembic import op
import sqlalchemy as sa

revision = "067_schedule_history"
down_revision = "066_vacation_days_decimal"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("working_hours_changes", sa.Column(
        "use_daily_schedule", sa.Boolean(), nullable=False, server_default="false"))
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        op.add_column("working_hours_changes", sa.Column(
            f"hours_{day}", sa.Numeric(4, 2), nullable=True))
    op.add_column("working_hours_changes", sa.Column(
        "work_days_per_week", sa.Integer(), nullable=True))

    # Backfill aus der zugehoerigen User-Zeile.
    op.execute("""
        UPDATE working_hours_changes AS w
        SET use_daily_schedule = u.use_daily_schedule,
            hours_monday = CASE WHEN u.use_daily_schedule THEN u.hours_monday END,
            hours_tuesday = CASE WHEN u.use_daily_schedule THEN u.hours_tuesday END,
            hours_wednesday = CASE WHEN u.use_daily_schedule THEN u.hours_wednesday END,
            hours_thursday = CASE WHEN u.use_daily_schedule THEN u.hours_thursday END,
            hours_friday = CASE WHEN u.use_daily_schedule THEN u.hours_friday END,
            work_days_per_week = u.work_days_per_week
        FROM users AS u
        WHERE w.user_id = u.id
    """)

    op.create_index(
        "ix_whc_user_effective_from",
        "working_hours_changes", ["user_id", "effective_from"],
    )


def downgrade():
    op.drop_index("ix_whc_user_effective_from", table_name="working_hours_changes")
    op.drop_column("working_hours_changes", "work_days_per_week")
    for day in ("friday", "thursday", "wednesday", "tuesday", "monday"):
        op.drop_column("working_hours_changes", f"hours_{day}")
    op.drop_column("working_hours_changes", "use_daily_schedule")
```

- [ ] **Step 6: Migration gegen echtes Postgres testen**

Wegwerf-PG hochfahren und up→down→up fahren (SQLite kann `ALTER … USING` und `UPDATE … FROM` nicht abbilden, und Numeric-Präzision ist dort unsichtbar):

Die Verbindungs-URL wird aus Teilen gebaut — der Pre-Commit-Secret-Scanner lehnt
ein zusammenhängendes `schema://user:passwort@host`-Literal ab, auch in
Kommandos und Kommentaren:

```bash
docker run -d --rm --name pz-mig-test -e POSTGRES_PASSWORD=devpw \
  -e POSTGRES_USER=praxiszeit -e POSTGRES_DB=praxiszeit -p 55432:5432 postgres:18-alpine
sleep 5
SCHEME="postgres"; SCHEME="${SCHEME}ql://"
DBURL="${SCHEME}praxiszeit:devpw@host.docker.internal:55432/praxiszeit"
for STEP in "upgrade head" "downgrade 066_vacation_days_decimal" "upgrade head"; do
  docker compose exec -T -e DATABASE_URL="$DBURL" backend \
    python -c "import sys;from alembic.config import main;main(sys.argv[1:])" $STEP
done
docker rm -f pz-mig-test
```
Erwartet: alle drei Läufe ohne Fehler. Schlägt `host.docker.internal` fehl, stattdessen `--network host` beim Testcontainer und `localhost:55432`. (In fish keine mehrzeilige `for`-Schleife im Tool-Eval — dann die drei Aufrufe einzeln absetzen.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/working_hours_change.py backend/alembic/versions/2026_07_29_1200-067_schedule_history.py backend/tests/test_schedule_history_model.py
git commit -F - <<'EOF'
feat(#431): Stundenhistorie traegt den vollstaendigen Vertrags-Snapshot

Migration 067 ergaenzt working_hours_changes um Modus, die fuenf Tageswerte und
die Arbeitstage. Der Backfill stempelt jede bestehende Zeile mit dem heutigen
Zustand ihres Users — ohne ihn wuerden Alt-Zeilen eines nachtraeglich auf
Tagesplan umgestellten Mitarbeiters schlagartig als gleichmaessige Zeilen
wirksam und das Soll der Vergangenheit verschieben.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: Resolver `get_schedule_for_date`

**Files:**
- Modify: `backend/app/services/calculation_service.py:13-64` (Resolver daneben, `get_weekly_hours_for_date` delegiert)
- Test: `backend/tests/test_schedule_resolver.py` (neu)

**Interfaces:**
- Produces:
  ```python
  class Schedule(NamedTuple):
      weekly_hours: Decimal
      use_daily_schedule: bool
      day_hours: tuple  # (Mo, Di, Mi, Do, Fr), je Optional[Decimal]
      work_days_per_week: int

  def get_schedule_for_date(db, user, target_date, wh_changes=None) -> Schedule
  ```
- Consumes: `WorkingHoursChange`-Snapshot-Spalten aus Task 1.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_schedule_resolver.py`:

```python
"""#431: der Snapshot-Resolver — Query-Pfad, Preload-Pfad, Rueckfall."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from app.services import calculation_service as cs


def _row(user, day, **kw):
    return WorkingHoursChange(
        user_id=user.id, tenant_id=user.tenant_id, effective_from=day, **kw)


def test_fallback_to_user_when_no_history(db_session, test_user):
    test_user.weekly_hours = Decimal("40.0")
    test_user.work_days_per_week = 5
    test_user.use_daily_schedule = False
    db_session.commit()

    s = cs.get_schedule_for_date(db_session, test_user, date(2026, 5, 4))

    assert s.weekly_hours == Decimal("40.0")
    assert s.use_daily_schedule is False
    assert s.work_days_per_week == 5


def test_resolves_day_plan_snapshot(db_session, test_user):
    db_session.add(_row(
        test_user, date(2026, 3, 1),
        weekly_hours=Decimal("17.0"), use_daily_schedule=True,
        hours_monday=Decimal("8.0"), hours_tuesday=Decimal("5.0"),
        hours_wednesday=Decimal("4.0"), work_days_per_week=3,
    ))
    db_session.commit()

    before = cs.get_schedule_for_date(db_session, test_user, date(2026, 2, 28))
    after = cs.get_schedule_for_date(db_session, test_user, date(2026, 3, 2))

    assert before.use_daily_schedule is False
    assert after.use_daily_schedule is True
    assert after.day_hours[0] == Decimal("8.0")
    assert after.day_hours[3] is None
    assert after.work_days_per_week == 3


def test_preload_path_matches_query_path(db_session, test_user):
    db_session.add(_row(test_user, date(2026, 1, 1), weekly_hours=Decimal("40.0")))
    db_session.add(_row(
        test_user, date(2026, 3, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=3))
    db_session.commit()
    preload = db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == test_user.id).all()

    for d in (date(2026, 1, 15), date(2026, 2, 28), date(2026, 3, 1), date(2026, 12, 31)):
        assert cs.get_schedule_for_date(db_session, test_user, d) == \
               cs.get_schedule_for_date(db_session, test_user, d, wh_changes=preload)


def test_weekly_hours_helper_still_matches_resolver(db_session, test_user):
    """get_weekly_hours_for_date bleibt die oeffentliche Wochenstunden-Quelle und
    darf nie vom Resolver abweichen."""
    db_session.add(_row(test_user, date(2026, 3, 1), weekly_hours=Decimal("17.0")))
    db_session.commit()

    for d in (date(2026, 2, 1), date(2026, 3, 1), date(2026, 6, 1)):
        assert cs.get_weekly_hours_for_date(db_session, test_user, d) == \
               cs.get_schedule_for_date(db_session, test_user, d).weekly_hours


def test_work_days_falls_back_when_row_has_none(db_session, test_user):
    """Bestandszeilen ohne Backfill (theoretisch) fallen auf den User-Wert."""
    test_user.work_days_per_week = 4
    db_session.add(_row(test_user, date(2026, 3, 1), weekly_hours=Decimal("20.0")))
    db_session.commit()

    s = cs.get_schedule_for_date(db_session, test_user, date(2026, 4, 1))
    assert s.work_days_per_week == 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_schedule_resolver.py -v
```
Erwartet: FAIL — `AttributeError: module 'app.services.calculation_service' has no attribute 'get_schedule_for_date'`.

- [ ] **Step 3: Resolver implementieren**

In `calculation_service.py` **vor** `get_weekly_hours_for_date` einfügen:

```python
class Schedule(NamedTuple):
    """#431: der vollstaendige Vertrags-Snapshot fuer EIN Datum.

    Aufgeloest aus der jeweils juengsten ``WorkingHoursChange`` mit
    ``effective_from <= target_date``; gibt es keine, aus den aktuellen
    User-Feldern (der Rueckfallwert fuer die Zeit vor der ersten erfassten
    Aenderung — dieselbe Semantik wie ``user.weekly_hours`` seit #415).
    """

    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple          # (Mo, Di, Mi, Do, Fr), je Optional[Decimal]
    work_days_per_week: int


def _latest_change(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Optional[WorkingHoursChange]:
    """Juengste Aenderung mit ``effective_from <= target_date``. Query-Pfad und
    In-Memory-Pfad mit identischer Semantik (``ORDER BY effective_from DESC
    LIMIT 1``)."""
    if wh_changes is None:
        return db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == user.id,
            WorkingHoursChange.tenant_id == user.tenant_id,  # F-026
            WorkingHoursChange.effective_from <= target_date,
        ).order_by(WorkingHoursChange.effective_from.desc()).first()
    change = None
    for c in wh_changes:
        if c.effective_from <= target_date and (
            change is None or c.effective_from > change.effective_from
        ):
            change = c
    return change


def _dec_or_none(value) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


def get_schedule_for_date(
    db: Session,
    user: User,
    target_date: date,
    wh_changes: Optional[List[WorkingHoursChange]] = None,
) -> Schedule:
    """#431: DIE eine Aufloesung des Vertragszustands zu einem Datum.

    Vor #431 war nur ``weekly_hours`` historisiert; Modus, Tageswerte und
    Arbeitstage kamen live von der User-Zeile — jede Aenderung verschob damit
    still das Soll der gesamten Vergangenheit. Alle vier Werte stecken jetzt in
    derselben Snapshot-Zeile, deshalb genuegt EIN Lookup (und der bereits
    vorhandene ``wh_changes``-Preload der Hot-Loops).
    """
    change = _latest_change(db, user, target_date, wh_changes)
    if change is not None:
        return Schedule(
            weekly_hours=Decimal(str(change.weekly_hours)),
            use_daily_schedule=bool(change.use_daily_schedule),
            day_hours=(
                _dec_or_none(change.hours_monday),
                _dec_or_none(change.hours_tuesday),
                _dec_or_none(change.hours_wednesday),
                _dec_or_none(change.hours_thursday),
                _dec_or_none(change.hours_friday),
            ),
            work_days_per_week=int(
                change.work_days_per_week
                if change.work_days_per_week is not None
                else user.work_days_per_week
            ),
        )
    # Kein Eintrag → aktuelle User-Felder. Dies ist die EINZIGE Stelle im Code,
    # die user.weekly_hours / user.hours_* / user.work_days_per_week direkt
    # lesen darf.
    return Schedule(
        weekly_hours=Decimal(str(user.weekly_hours)),
        use_daily_schedule=bool(getattr(user, 'use_daily_schedule', False)),
        day_hours=(
            _dec_or_none(user.hours_monday),
            _dec_or_none(user.hours_tuesday),
            _dec_or_none(user.hours_wednesday),
            _dec_or_none(user.hours_thursday),
            _dec_or_none(user.hours_friday),
        ),
        work_days_per_week=int(user.work_days_per_week),
    )
```

`get_weekly_hours_for_date` wird zum dünnen Wrapper (Body ersetzen, Docstring behalten und um einen Satz ergänzen):

```python
    return get_schedule_for_date(db, user, target_date, wh_changes).weekly_hours
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose cp backend/app backend:/app/ && \
docker compose exec -T backend pytest tests/test_schedule_resolver.py tests/test_calc_preload.py -v
```
Erwartet: alle passed.

- [ ] **Step 5: Referenz-Suiten prüfen (Byte-Identität)**

```bash
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
```
Erwartet: identisches Ergebnis wie vor der Task (Anzahl passed/failed notieren; bekannte Vor-Ausfälle in `test_shift_planning*` sind zulässig).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/calculation_service.py backend/tests/test_schedule_resolver.py
git commit -F - <<'EOF'
feat(#431): Resolver fuer den Vertrags-Snapshot je Datum

get_schedule_for_date loest Modus, Tageswerte, Arbeitstage und Wochenstunden aus
derselben Snapshot-Zeile auf — Query-Pfad und Preload-Pfad wie beim Vorbild
get_weekly_hours_for_date, das jetzt ein duenner Wrapper darauf ist. Damit kann
Darstellung und Berechnung nicht auseinanderlaufen.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: `get_daily_target_for_date` bekommt den Snapshot als Pflichtparameter

**Files:**
- Modify: `backend/app/services/calculation_service.py:364-402` (Signatur), `:589-622` (`_day_soll_contribution`), `:304-305`, `:433-440`, `:950-986`, `:1639`, `:1738`
- Modify (Call-Sites): `backend/app/routers/{absences,admin_vacations,vacation_requests,admin_change_requests,company_closures,dashboard,reports,admin_users}.py`, `backend/app/services/{export_service,ods_export_service,journal_service,closure_split_service}.py`
- Test: `backend/tests/test_day_plan_history_target.py` (neu)

**Interfaces:**
- Consumes: `Schedule`, `get_schedule_for_date` (Task 2)
- Produces: `get_daily_target_for_date(user, target_date, schedule: Schedule) -> Decimal` — dritter Parameter ist **positional required**.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_day_plan_history_target.py`:

```python
"""#431: das Tagessoll folgt dem historischen Tagesplan, nicht dem aktuellen."""
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from app.services import calculation_service as cs


def test_day_plan_target_is_date_aware(db_session, test_user):
    """Kern von #431: ein Mittwoch im Februar rechnet mit dem Februar-Plan,
    obwohl der Mitarbeiter heute einen anderen Plan hat."""
    test_user.use_daily_schedule = True
    test_user.hours_monday = Decimal("4.0")
    test_user.hours_wednesday = Decimal("2.0")
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3,
    ))
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("6.0"),
        use_daily_schedule=True, hours_monday=Decimal("4.0"),
        hours_wednesday=Decimal("2.0"), work_days_per_week=2,
    ))
    db_session.commit()

    feb_wed = date(2026, 2, 4)   # Mittwoch
    apr_wed = date(2026, 4, 1)   # Mittwoch
    assert cs.get_daily_target_for_date(
        test_user, feb_wed, cs.get_schedule_for_date(db_session, test_user, feb_wed)
    ) == Decimal("4.00")
    assert cs.get_daily_target_for_date(
        test_user, apr_wed, cs.get_schedule_for_date(db_session, test_user, apr_wed)
    ) == Decimal("2.00")


def test_weekly_mode_uses_historical_work_days(db_session, test_user):
    """Arbeitstage sind ebenfalls historisiert: 20 h auf 4 Tage = 5 h/Tag,
    danach 20 h auf 5 Tage = 4 h/Tag."""
    test_user.use_daily_schedule = False
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("20.0"),
        work_days_per_week=4,
    ))
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 6, 1), weekly_hours=Decimal("20.0"),
        work_days_per_week=5,
    ))
    db_session.commit()

    d1, d2 = date(2026, 2, 3), date(2026, 7, 7)
    assert cs.get_daily_target_for_date(
        test_user, d1, cs.get_schedule_for_date(db_session, test_user, d1)) == Decimal("5.00")
    assert cs.get_daily_target_for_date(
        test_user, d2, cs.get_schedule_for_date(db_session, test_user, d2)) == Decimal("4.00")


def test_untracked_user_still_zero(db_session, test_user):
    test_user.track_hours = False
    db_session.commit()
    d = date(2026, 4, 1)
    assert cs.get_daily_target_for_date(
        test_user, d, cs.get_schedule_for_date(db_session, test_user, d)) == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_day_plan_history_target.py -v
```
Erwartet: FAIL — das Tagessoll liest weiter die aktuellen User-Spalten (Februar-Mittwoch liefert 2.00 statt 4.00).

- [ ] **Step 3: Signatur umstellen**

`calculation_service.py:364-402` ersetzen durch:

```python
def get_daily_target_for_date(user: User, target_date: date, schedule: 'Schedule') -> Decimal:
    """Tagessoll fuer ein konkretes Datum aus dem aufgeloesten Vertrags-Snapshot.

    ``schedule`` ist PFLICHT (#431): frueher las der Tagesplan-Zweig live
    ``user.hours_monday…friday`` und verwarf dabei das datumsaufgeloeste
    ``weekly_hours`` — eine Historien-Zeile hatte fuer Tagesplan-Mitarbeitende
    also keinerlei Wirkung aufs Soll. Ohne Pflichtparameter bliebe eine
    uebersehene Call-Site lautlos auf dem AKTUELLEN Plan stehen und erzeugte ein
    halb-historisches §16-Dokument (Abwesenheitstage historisch gerechnet,
    regulaere Arbeitstage nicht). Den Snapshot liefert
    ``get_schedule_for_date`` — in Tagesschleifen mit dem vorhandenen
    ``wh_changes``-Preload.

    Wochenende ist immer 0; ``track_hours=False`` ebenfalls.
    """
    if not user.track_hours:
        return Decimal('0')

    weekday = target_date.weekday()  # 0=Mo, 4=Fr, 5=Sa, 6=So
    if weekday >= 5:
        return Decimal('0')

    if schedule.use_daily_schedule:
        day_hours = schedule.day_hours[weekday]
        if day_hours is None:
            return Decimal('0')
        return Decimal(str(day_hours)).quantize(Decimal('0.01'))

    work_days = Decimal(str(schedule.work_days_per_week))
    if work_days == 0:
        return Decimal('0')
    return (schedule.weekly_hours / work_days).quantize(Decimal('0.01'))
```

`get_daily_target(user, weekly_hours)` (`:328-361`) bleibt unverändert — es ist die datumslose Variante mit vier Aufrufern und liest weiterhin `user.work_days_per_week`. Ergänze dort einen Docstring-Satz: *„#431: kennt keinen Tagesplan und keine Historie. Für alles Datumsbezogene `get_daily_target_for_date` mit `get_schedule_for_date` nutzen."*

- [ ] **Step 4: `_day_soll_contribution` umstellen**

In `:615-616`:

```python
    schedule = get_schedule_for_date(db, user, d, wh_changes=wh_changes)
    daily_target = get_daily_target_for_date(user, d, schedule)
```

- [ ] **Step 5: Alle übrigen Call-Sites umstellen**

Muster überall identisch — wo bisher stand:

```python
weekly = calculation_service.get_weekly_hours_for_date(db, user, d)          # ggf. mit wh_changes=…
target = calculation_service.get_daily_target_for_date(user, d, weekly)
```

steht künftig:

```python
schedule = calculation_service.get_schedule_for_date(db, user, d)            # ggf. mit wh_changes=…
target = calculation_service.get_daily_target_for_date(user, d, schedule)
```

Vollständige Liste finden und **jede** Stelle abarbeiten:

```bash
grep -rn "get_daily_target_for_date" backend/app
```

Besonderheiten:
- `calculation_service.py:304-305` (`retarget_absence_hours`): nutzt bereits einen `wh_changes`-Preload → durchreichen.
- `calculation_service.py:433-440` (`_fixed_planned_hours`, #377-2b): bekommt einen `wh_changes`-Parameter, den die Aufrufer (`fixed_month_credit`, `fixed_month_unpaid_reduction`, `future_freizeitausgleich_impact`) durchreichen. Ohne das schriebe der Fix-Modus einem vergangenen Urlaubs-/Feiertag die **heutigen** Planstunden gut.
- `calculation_service.py:950-986` (`get_gross_monthly_target`, klassischer Jahresbericht): eigene Inline-Schleife ohne `_day_soll_contribution` → dort einen `wh_changes`-Preload ergänzen (Muster: `:813-816`) und den Resolver nutzen.
- `calculation_service.py:1639` / `:1738` (`absence_days`, `get_vacation_account`): rufen die datumslose `get_daily_target` — **nicht** anfassen; sie ist unverändert.
- `admin_users.py:229-252` (`users_overview`): der vorhandene `_wh_by_user`-Preload trägt den Snapshot bereits mit — nichts zusätzlich zu laden.

- [ ] **Step 6: Run tests**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && \
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
```
Erwartet: `test_day_plan_history_target.py` grün; **keine** zusätzlichen Fehler gegenüber dem Referenzlauf aus Task 2 Step 5. Ein `TypeError: get_daily_target_for_date() missing 1 required positional argument` zeigt eine vergessene Call-Site — beheben, nicht unterdrücken.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests/test_day_plan_history_target.py
git commit -F - <<'EOF'
feat(#431): Tagessoll rechnet gegen den historischen Vertrags-Snapshot

get_daily_target_for_date bekommt den aufgeloesten Snapshot als Pflichtparameter
und alle Call-Sites reichen ihn durch. Der Pflichtparameter ist Absicht: eine
uebersehene Stelle schlaegt sofort fehl, statt lautlos den heutigen Plan zu
verwenden und ein halb-historisches §16-Dokument zu erzeugen.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: Rückrechnung der Abwesenheits-Stunden für Tagesplan-MA

**Files:**
- Modify: `backend/app/services/calculation_service.py:207-325` (`retarget_absence_hours` — nur Doku/Verhalten prüfen)
- Test: `backend/tests/test_retarget_day_plan.py` (neu)

**Interfaces:**
- Consumes: Task 3.

Nach Task 3 rechnet `retarget_absence_hours` bereits mit dem historischen Tagesplan. Diese Task **beweist** das Verhalten und schließt den Sonderfall „nur ein Wochentag geändert" ab: die bestehende Gleichheitsprüfung (`:316-317`) überspringt Tage, deren Soll sich nicht ändert — es braucht keinen zusätzlichen Wochentagsfilter.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_retarget_day_plan.py`:

```python
"""#431: Rueckrechnung gebuchter Abwesenheits-Stunden bei Tagesplan-Aenderung."""
from datetime import date
from decimal import Decimal

from app.models import Absence, AbsenceType, WorkingHoursChange
from app.services import calculation_service as cs


def _absence(user, day, hours):
    return Absence(
        user_id=user.id, tenant_id=user.tenant_id, date=day,
        type=AbsenceType.SICK, hours=hours, half_day=False)


def test_only_changed_weekday_is_retargeted(db_session, test_user):
    test_user.use_daily_schedule = True
    test_user.track_hours = True
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("12.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_wednesday=Decimal("4.0"), work_days_per_week=2))
    mon, wed = date(2026, 3, 2), date(2026, 3, 4)
    db_session.add(_absence(test_user, mon, 8.0))
    db_session.add(_absence(test_user, wed, 4.0))
    db_session.commit()

    # Nur der Mittwoch aendert sich: 4 h -> 6 h.
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("14.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_wednesday=Decimal("6.0"), work_days_per_week=2))
    db_session.commit()

    changed = cs.retarget_absence_hours(db_session, test_user, date(2026, 3, 1), date(2026, 3, 31))
    db_session.commit()

    rows = {a.date: Decimal(str(a.hours)) for a in db_session.query(Absence).filter(
        Absence.user_id == test_user.id).all()}
    assert changed == 1
    assert rows[mon] == Decimal("8.00")   # unveraendert
    assert rows[wed] == Decimal("6.00")   # nachgezogen


def test_free_weekday_is_skipped_not_zeroed(db_session, test_user):
    """Ein Tag ohne Soll im Plan wird uebersprungen, nicht auf 0 gesetzt."""
    test_user.use_daily_schedule = True
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 1, 1), weekly_hours=Decimal("8.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=1))
    fri = date(2026, 3, 6)
    db_session.add(_absence(test_user, fri, 3.0))
    db_session.commit()

    changed = cs.retarget_absence_hours(db_session, test_user, date(2026, 3, 1), date(2026, 3, 31))
    row = db_session.query(Absence).filter(Absence.date == fri).first()

    assert changed == 0
    assert Decimal(str(row.hours)) == Decimal("3.0")
```

- [ ] **Step 2: Run test to verify it passes or fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_retarget_day_plan.py -v
```
Erwartet nach Task 3: PASS. Falls FAIL → in `retarget_absence_hours` ist eine Call-Site aus Task 3 übersehen worden; dort beheben.

- [ ] **Step 3: Docstring nachziehen**

In `retarget_absence_hours` den Absatz „Bewusst ausgenommen" um einen Satz ergänzen:

```
    * #431: Tagesplan-Mitarbeitende sind NICHT mehr ausgenommen. Ihr Tagessoll
      kommt jetzt ebenfalls aus der Historien-Zeile; aendert eine Aenderung nur
      einen Wochentag, ueberspringt die Gleichheitspruefung die uebrigen Tage
      von selbst — es braucht keinen Wochentagsfilter.
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/calculation_service.py backend/tests/test_retarget_day_plan.py
git commit -F - <<'EOF'
test(#431): Rueckrechnung folgt dem historischen Tagesplan

Belegt, dass eine Aenderung nur die Wochentage anfasst, deren Soll sich
tatsaechlich verschiebt, und einen planfreien Wochentag ueberspringt statt ihn
auf 0 zu setzen.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 5: Schema + POST — Snapshot anlegen, Sperre entfernen

**Files:**
- Modify: `backend/app/schemas/working_hours_change.py:8-34`
- Modify: `backend/app/routers/admin_users.py:914-1094`
- Test: `backend/tests/test_wh_change_day_plan_create.py` (neu), `backend/tests/test_fix2_whchange_daily_schedule.py:36-56` (umschreiben)

**Interfaces:**
- Produces: `WorkingHoursChangeCreate` mit `use_daily_schedule: bool = False`, `hours_monday…friday: Optional[float]`, `work_days_per_week: Optional[int]`; `weekly_hours: Optional[float]` (im Tagesplan-Modus serverseitig als Summe gesetzt).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_wh_change_day_plan_create.py`:

```python
"""#431: Tagesplan-Aenderungen ueber den Stundenverlauf-Endpoint."""
from datetime import date, timedelta
from decimal import Decimal

from app.models import WorkingHoursChange


def test_creates_day_plan_row(client, admin_headers, day_plan_user):
    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={
            "effective_from": str(date.today() + timedelta(days=30)),
            "use_daily_schedule": True,
            "hours_monday": 8.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
            "work_days_per_week": 3,
            "note": "Teilzeit",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["use_daily_schedule"] is True
    assert body["hours_monday"] == 8.0
    assert body["weekly_hours"] == 17.0        # serverseitig als Summe gesetzt


def test_rejects_day_plan_without_any_hours(client, admin_headers, day_plan_user):
    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={"effective_from": str(date.today()), "use_daily_schedule": True},
    )
    assert r.status_code == 422


def test_baseline_row_freezes_the_day_plan_past(client, admin_headers, db_session, day_plan_user):
    """Die erste Aenderung eines Tagesplan-MA legt eine Basis-Zeile mit dem
    BISHERIGEN Plan an — sonst gaelte der neue Plan rueckwirkend fuer die
    gesamte Vergangenheit."""
    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={
            "effective_from": str(date.today()),
            "use_daily_schedule": True,
            "hours_monday": 4.0, "hours_wednesday": 2.0, "work_days_per_week": 2,
        },
    )
    assert r.status_code == 201, r.text

    rows = db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == day_plan_user.id
    ).order_by(WorkingHoursChange.effective_from).all()
    assert len(rows) == 2
    baseline = rows[0]
    assert baseline.effective_from < date.today()
    assert baseline.use_daily_schedule is True
    assert Decimal(str(baseline.hours_monday)) == Decimal("8.00")   # alter Plan
    assert "Ausgangswert" in (baseline.note or "")


def test_mode_switch_to_weekly(client, admin_headers, db_session, day_plan_user):
    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={
            "effective_from": str(date.today()),
            "use_daily_schedule": False,
            "weekly_hours": 20.0, "work_days_per_week": 5,
        },
    )
    assert r.status_code == 201, r.text
    db_session.refresh(day_plan_user)
    assert day_plan_user.use_daily_schedule is False
    assert Decimal(str(day_plan_user.weekly_hours)) == Decimal("20.0")
    assert day_plan_user.hours_monday is None
```

Fixture `day_plan_user` in `backend/tests/conftest.py` ergänzen (Mo 8 / Di 5 / Mi 4, `use_daily_schedule=True`, `work_days_per_week=3`, `weekly_hours=17`, `track_hours=True`) — Muster von `test_user` übernehmen.

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_day_plan_create.py -v
```
Erwartet: FAIL mit HTTP 400 „Für Mitarbeitende mit individuellem Tagesplan wird die Stunden-Historie nicht unterstützt".

- [ ] **Step 3: Schema erweitern**

`backend/app/schemas/working_hours_change.py`:

```python
class WorkingHoursChangeBase(BaseModel):
    effective_from: date
    # #431: im Tagesplan-Modus serverseitig als Summe der Tageswerte gesetzt —
    # der Client schickt dort keinen eigenen Wert.
    weekly_hours: Optional[float] = Field(None, ge=0, le=60)
    use_daily_schedule: bool = False
    hours_monday: Optional[float] = Field(None, ge=0, le=24)
    hours_tuesday: Optional[float] = Field(None, ge=0, le=24)
    hours_wednesday: Optional[float] = Field(None, ge=0, le=24)
    hours_thursday: Optional[float] = Field(None, ge=0, le=24)
    hours_friday: Optional[float] = Field(None, ge=0, le=24)
    work_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    note: Optional[str] = None

    @model_validator(mode='after')
    def check_mode(self):
        days = [self.hours_monday, self.hours_tuesday, self.hours_wednesday,
                self.hours_thursday, self.hours_friday]
        if self.use_daily_schedule:
            if not any(d for d in days if d):
                raise ValueError("Im Tagesplan-Modus muss mindestens ein Wochentag Stunden haben.")
            total = sum(d or 0 for d in days)
            if total > 60:
                raise ValueError("Die Summe der Tagesstunden darf 60 nicht überschreiten.")
            self.weekly_hours = round(total, 2)
        else:
            if self.weekly_hours is None:
                raise ValueError("Wochenstunden sind im gleichmäßigen Modus Pflicht.")
            for d in days:
                if d is not None:
                    raise ValueError("Tagesstunden gehören zum Tagesplan-Modus.")
        return self
```

`WorkingHoursChangeResponse` erbt die Felder automatisch; `model_config = ConfigDict(from_attributes=True)` bleibt. Import `model_validator` ergänzen.

- [ ] **Step 4: POST-Endpoint umbauen**

`admin_users.py:914-1094`:

1. Den Block `:925-939` (Tagesplan-400) **ersatzlos entfernen**.
2. Basis-Zeile (`:986-1015`): Vergleich auf den vollständigen Snapshot umstellen und alle Snapshot-Felder mitschreiben:

```python
    _current = calculation_service.get_schedule_for_date(
        db, user, change_data.effective_from - timedelta(days=1))
    _incoming = (
        Decimal(str(change_data.weekly_hours)),
        bool(change_data.use_daily_schedule),
        tuple(None if v is None else Decimal(str(v)) for v in (
            change_data.hours_monday, change_data.hours_tuesday,
            change_data.hours_wednesday, change_data.hours_thursday,
            change_data.hours_friday)),
        int(change_data.work_days_per_week or user.work_days_per_week),
    )
    if not _has_history and tuple(_current) != _incoming:
        …  # Datumsermittlung unveraendert
        db.add(WorkingHoursChange(
            user_id=user_id,
            tenant_id=current_user.tenant_id,
            effective_from=_baseline_date,
            weekly_hours=_current.weekly_hours,
            use_daily_schedule=_current.use_daily_schedule,
            hours_monday=_current.day_hours[0],
            hours_tuesday=_current.day_hours[1],
            hours_wednesday=_current.day_hours[2],
            hours_thursday=_current.day_hours[3],
            hours_friday=_current.day_hours[4],
            work_days_per_week=_current.work_days_per_week,
            note="Automatisch erfasster Ausgangswert vor der ersten Stundenänderung",
        ))
```

3. Die neue Zeile (`:1017-1023`) trägt alle Snapshot-Felder.
4. Der Resync (`:1035-1042`) schreibt den vollständigen Snapshot auf die User-Zeile zurück:

```python
        if most_recent:
            user.weekly_hours = most_recent.weekly_hours
            user.use_daily_schedule = bool(most_recent.use_daily_schedule)
            user.hours_monday = most_recent.hours_monday
            user.hours_tuesday = most_recent.hours_tuesday
            user.hours_wednesday = most_recent.hours_wednesday
            user.hours_thursday = most_recent.hours_thursday
            user.hours_friday = most_recent.hours_friday
            if most_recent.work_days_per_week is not None:
                user.work_days_per_week = most_recent.work_days_per_week
```

5. Retarget/Warnung (`:1066-1088`) bleiben unverändert.

- [ ] **Step 5: Bestehenden Sperr-Test umschreiben**

`backend/tests/test_fix2_whchange_daily_schedule.py` behält seinen Namen und seine Begründung, kehrt aber die Erwartung um: statt HTTP 400 wird jetzt geprüft, dass die Zeile angelegt wird **und** dass sie das Soll des Tagesplan-MA tatsächlich verschiebt (das war der ursprüngliche Grund für die Sperre). Docstring entsprechend umschreiben — der Vorfall bleibt dokumentiert.

- [ ] **Step 6: Run tests**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && \
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_wh_change_day_plan_create.py \
  tests/test_fix2_whchange_daily_schedule.py tests/test_wh_change_retroactive.py -v
```
Erwartet: alle passed (Tests in `test_wh_change_retroactive.py:518-580` und `:1021-1105`, die den alten Ausschluss festschreiben, mit umschreiben).

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests
git commit -F - <<'EOF'
feat(#431): Stundenverlauf nimmt Tagesplan-Aenderungen an

Der Endpoint schreibt jetzt den vollstaendigen Snapshot inklusive Modus,
Tageswerten und Arbeitstagen; die Basis-Zeile friert den bisherigen Plan ein und
der Resync zieht die User-Zeile nach. Die 400-Sperre entfaellt — sie existierte
nur, solange eine solche Zeile ohne Wirkung aufs Soll geblieben waere.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 6: DELETE — Rückrechnung auch für Tagesplan-MA

**Files:**
- Modify: `backend/app/routers/admin_users.py:1322-1365`
- Test: `backend/tests/test_wh_change_day_plan_delete.py` (neu)

- [ ] **Step 1: Write the failing test**

```python
"""#431: Loeschen einer Tagesplan-Aenderung rechnet symmetrisch zurueck."""
from datetime import date, timedelta
from decimal import Decimal

from app.models import Absence, AbsenceType, WorkingHoursChange


def test_delete_pulls_absence_hours_back(client, admin_headers, db_session, day_plan_user):
    past = date.today() - timedelta(days=20)
    db_session.add(WorkingHoursChange(
        user_id=day_plan_user.id, tenant_id=day_plan_user.tenant_id,
        effective_from=past - timedelta(days=200), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3))
    db_session.commit()

    r = client.post(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes",
        headers=admin_headers,
        json={"effective_from": str(past), "use_daily_schedule": True,
              "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
              "work_days_per_week": 3})
    assert r.status_code == 201, r.text
    change_id = r.json()["id"]

    monday = past + timedelta(days=(7 - past.weekday()) % 7)
    db_session.add(Absence(
        user_id=day_plan_user.id, tenant_id=day_plan_user.tenant_id, date=monday,
        type=AbsenceType.SICK, hours=4.0, half_day=False))
    db_session.commit()

    d = client.delete(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/{change_id}",
        headers=admin_headers)
    assert d.status_code in (200, 204), d.text

    row = db_session.query(Absence).filter(Absence.date == monday).first()
    db_session.refresh(row)
    assert Decimal(str(row.hours)) == Decimal("8.00")   # zurueck auf den alten Plan
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_day_plan_delete.py -v
```
Erwartet: FAIL — die Stunden bleiben bei 4.0, weil `_uses_daily_schedule` das Retarget überspringt.

- [ ] **Step 3: Skip entfernen**

In `admin_users.py` den Block `:1338-1341` durch den unbedingten Pfad ersetzen (Einrückung der folgenden Zeilen anpassen) und den I1-Kommentarabsatz (`:1322-1337`) durch die neue Begründung ersetzen:

```python
    # #431: Tagesplan-Mitarbeitende sind NICHT mehr ausgenommen. Ihr Tagessoll
    # kommt jetzt ebenfalls aus dieser Zeile — das Loeschen muss deshalb genauso
    # symmetrisch zurueckrechnen wie bei gleichmaessigen Wochenstunden. Der
    # frueher noetige Skip (I1) hatte den umgekehrten Grund: damals konnte eine
    # solche Zeile ihr Soll gar nicht setzen, das Retarget schrieb ihnen aber
    # trotzdem die gebuchten Stunden um.
    window = calculation_service.retarget_window(db, user, deleted_effective_from)
    adjusted_absences = 0
    warning = None
    if window.has_absences:
        …
```

Auch der Resync beim Löschen (`:1300-1301`) schreibt den vollständigen Snapshot zurück — dieselben Zeilen wie in Task 5 Step 4.4.

- [ ] **Step 4: Run tests**

```bash
docker compose cp backend/app backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_day_plan_delete.py tests/test_wh_change_retroactive.py -v
```
Erwartet: alle passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin_users.py backend/tests/test_wh_change_day_plan_delete.py
git commit -F - <<'EOF'
feat(#431): Loeschen rechnet auch bei Tagesplan zurueck

Symmetrie zum Anlegen: da die Zeile jetzt das Soll treibt, muss ihre Ruecknahme
die gebuchten Abwesenheits-Stunden auf den davor gueltigen Plan zurueckrechnen —
inklusive der Jahresabschluss-Warnung, die fuer diese Gruppe bisher mit ausfiel.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 7: `PUT /admin/users` sperrt die historisierten Felder

**Files:**
- Modify: `backend/app/routers/admin_users.py:696-731`
- Test: `backend/tests/test_wh_change_retroactive.py` (Abschnitt „PUT-Sperre", umschreiben) + neue Fälle

- [ ] **Step 1: Write the failing test**

Ergänze in `backend/tests/test_wh_change_retroactive.py` (bestehende Klasse für die PUT-Sperre):

```python
def test_put_rejects_day_plan_fields(client, admin_headers, day_plan_user):
    for payload in (
        {"hours_monday": 6.0},
        {"use_daily_schedule": False},
        {"work_days_per_week": 4},
    ):
        r = client.put(f"/api/admin/users/{day_plan_user.id}",
                       headers=admin_headers, json=payload)
        assert r.status_code == 400, f"{payload} -> {r.status_code}"
        assert "Wirkungsdatum" in r.json()["detail"]


def test_put_still_allows_unrelated_fields(client, admin_headers, day_plan_user):
    r = client.put(f"/api/admin/users/{day_plan_user.id}",
                   headers=admin_headers, json={"first_name": "Neu"})
    assert r.status_code == 200, r.text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_retroactive.py -k put -v
```
Erwartet: FAIL — die Felder gehen heute ungebremst durch `setattr`.

- [ ] **Step 3: Sperre erweitern**

`admin_users.py`, den `weekly_hours`-Block (`:719-731`) ersetzen:

```python
    # #431: ALLE Soll-Treiber laufen ueber den Stundenverlauf mit Wirkungsdatum.
    # Frueher war nur `weekly_hours` gesperrt (und selbst das mit einer Ausnahme
    # fuer Tagesplan-Mitarbeitende, weil es fuer sie keinen Schreibweg gab).
    # Tagesplan, Modus und Arbeitstage waren dagegen voellig offen — jede
    # Aenderung verschob still das Soll der gesamten Vergangenheit. Genau diese
    # Luecke ist #431.
    _HISTORISED_FIELDS = (
        'weekly_hours', 'use_daily_schedule', 'work_days_per_week',
        'hours_monday', 'hours_tuesday', 'hours_wednesday',
        'hours_thursday', 'hours_friday',
    )
    if any(f in update_data for f in _HISTORISED_FIELDS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Wochenstunden, Tagesstunden und Arbeitstage werden über "
                "„Wochenstunden anpassen“ mit Wirkungsdatum geändert, damit "
                "Historie und Soll vergangener Monate korrekt bleiben."
            ),
        )
```

`POST /admin/users` (`create_user`) bleibt unverändert — dort existiert noch keine Historie.

- [ ] **Step 4: Frontend-Payload prüfen**

`frontend/src/pages/admin/users/UserForm.tsx:248-249` entfernt bisher nur `weekly_hours` aus dem Update-Payload. Erweitere den Ausschluss um die sieben weiteren Felder, sonst scheitert **jedes** Speichern am neuen 400:

```typescript
        const {
          password, weekly_hours, use_daily_schedule, work_days_per_week,
          hours_monday, hours_tuesday, hours_wednesday, hours_thursday, hours_friday,
          ...rest
        } = payload;
        const updateData = rest;
```

- [ ] **Step 5: Run tests**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && \
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
cd frontend && npx vitest run --pool=threads src/pages/admin/users
```
Erwartet: Backend grün (Tests, die per PUT Tagesstunden setzen, auf die Fixture/den neuen Endpoint umstellen); Frontend grün.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin_users.py backend/tests frontend/src/pages/admin/users/UserForm.tsx
git commit -F - <<'EOF'
feat(#431): Tagesplan, Modus und Arbeitstage nur noch mit Wirkungsdatum

PUT /admin/users lehnt alle historisierten Soll-Treiber ab. Bisher war nur
weekly_hours gesperrt; Tagesstunden, Modus und Arbeitstage gingen ungebremst
durch das generische setattr und verschoben das Soll der Vergangenheit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 8: Vorschau — 5 Tagessoll-Paare + Saldo/Urlaub vorher-nachher

**Files:**
- Modify: `backend/app/schemas/working_hours_change.py:37-78`
- Modify: `backend/app/routers/admin_users.py:1097-1222`
- Test: `backend/tests/test_wh_change_preview.py` (erweitern, `:201-207` umschreiben)

**Interfaces:**
- Produces: `WorkingHoursChangePreview` zusätzlich mit
  `day_targets_current: List[float]` (5), `day_targets_new: List[float]` (5),
  `overtime_before: float`, `overtime_after: float`,
  `vacation_days_before: float`, `vacation_days_after: float`.
  `current_daily_target`/`new_daily_target` bleiben erhalten (Mittelwert der geplanten Tage) — sie sind Teil der bestehenden API.

- [ ] **Step 1: Write the failing test**

```python
def test_preview_returns_five_day_pairs_for_day_plan(client, admin_headers, day_plan_user):
    r = client.get(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/preview",
        headers=admin_headers,
        params={
            "effective_from": str(date.today()),
            "use_daily_schedule": True,
            "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
            "work_days_per_week": 3,
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["blocked_reason"] is None          # frueher: Tagesplan-Sperre
    assert body["day_targets_current"] == [8.0, 5.0, 4.0, 0.0, 0.0]
    assert body["day_targets_new"] == [4.0, 5.0, 4.0, 0.0, 0.0]
    assert "overtime_before" in body and "overtime_after" in body
    assert "vacation_days_before" in body and "vacation_days_after" in body


def test_preview_overtime_reflects_the_hypothetical_change(client, admin_headers, day_plan_user, db_session):
    """Halbiertes Montags-Soll rueckwirkend => hoeherer Ueberstundensaldo."""
    r = client.get(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/preview",
        headers=admin_headers,
        params={
            "effective_from": str(date(date.today().year, 1, 1)),
            "use_daily_schedule": True,
            "hours_monday": 4.0, "hours_tuesday": 5.0, "hours_wednesday": 4.0,
            "work_days_per_week": 3,
        })
    body = r.json()
    assert body["overtime_after"] > body["overtime_before"]


def test_preview_writes_nothing(client, admin_headers, day_plan_user, db_session):
    before = db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == day_plan_user.id).count()
    client.get(
        f"/api/admin/users/{day_plan_user.id}/working-hours-changes/preview",
        headers=admin_headers,
        params={"effective_from": str(date.today()), "use_daily_schedule": True,
                "hours_monday": 4.0, "work_days_per_week": 1})
    db_session.expire_all()
    assert db_session.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == day_plan_user.id).count() == before
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_preview.py -v
```
Erwartet: FAIL — der Endpoint kennt die neuen Query-Parameter nicht (422) bzw. liefert `blocked_reason`.

- [ ] **Step 3: Preview-Endpoint umbauen**

1. Signatur: `weekly_hours: Optional[float] = Query(None, ge=0, le=60)` plus
   `use_daily_schedule: bool = Query(False)`, `hours_monday…hours_friday: Optional[float] = Query(None, ge=0, le=24)`,
   `work_days_per_week: Optional[int] = Query(None, ge=1, le=7)`.
   Im Tagesplan-Modus `weekly_hours` als Summe berechnen (dieselbe Regel wie im Schema — als Helper `_normalise_schedule_input(...)` in `admin_users.py` auslagern und von POST *und* Preview nutzen, damit beide nicht divergieren).
2. `blocked_reason`: den Tagesplan-Zweig (`:1158-1163`) entfernen; der Duplikat-Zweig bleibt.
3. Tagessoll: statt eines repräsentativen Tages die fünf Wochentage durchrechnen.

```python
    _week_monday = effective_from - timedelta(days=effective_from.weekday())
    _current_sched = calculation_service.get_schedule_for_date(db, user, effective_from)
    _new_sched = calculation_service.Schedule(
        weekly_hours=Decimal(str(norm.weekly_hours)),
        use_daily_schedule=norm.use_daily_schedule,
        day_hours=norm.day_hours,
        work_days_per_week=norm.work_days_per_week or user.work_days_per_week,
    )
    day_targets_current = [
        float(calculation_service.get_daily_target_for_date(
            user, _week_monday + timedelta(days=i), _current_sched))
        for i in range(5)
    ]
    day_targets_new = [
        float(calculation_service.get_daily_target_for_date(
            user, _week_monday + timedelta(days=i), _new_sched))
        for i in range(5)
    ]
```

`current_daily_target` / `new_daily_target` = Mittel der Tage mit Soll > 0 (0.0, wenn keiner) — die Felder bleiben für Bestandsclients erhalten.

4. Saldo/Urlaub vorher-nachher im **selben** Dry-Run-Block wie `affected_absences` (`:1188-1201`), damit nur einmal geflusht und einmal zurückgerollt wird:

```python
    _year = period_start.year
    overtime_before = float(calculation_service.get_overtime_account(
        db, user, cutoff_date=calculation_service.get_soll_cutoff_date(db, user)
    )["balance"])
    vacation_before = float(calculation_service.get_vacation_account(db, user, _year)["used_days"])
    overtime_after, vacation_after = overtime_before, vacation_before
    if not blocked_reason:
        temp_change = WorkingHoursChange(
            user_id=user.id,
            tenant_id=current_user.tenant_id,
            effective_from=effective_from,
            weekly_hours=norm.weekly_hours,
            use_daily_schedule=norm.use_daily_schedule,
            hours_monday=norm.day_hours[0], hours_tuesday=norm.day_hours[1],
            hours_wednesday=norm.day_hours[2], hours_thursday=norm.day_hours[3],
            hours_friday=norm.day_hours[4],
            work_days_per_week=norm.work_days_per_week,
        )
        db.add(temp_change)
        db.flush()
        try:
            if window.has_absences:
                affected_absences = calculation_service.retarget_absence_hours(
                    db, user, period_start, period_end, dry_run=True)
            overtime_after = float(calculation_service.get_overtime_account(
                db, user, cutoff_date=calculation_service.get_soll_cutoff_date(db, user)
            )["balance"])
            vacation_after = float(
                calculation_service.get_vacation_account(db, user, _year)["used_days"])
        finally:
            db.rollback()
```

**Wichtig:** `get_overtime_account`/`get_vacation_account` dürfen im Dry-Run **keinen** Preload mitbekommen — sonst sehen sie die geflushte Zeile nicht. Den genauen Signatur-Namen (`cutoff_date`, Rückgabeschlüssel `balance` / `used_days`) vor dem Schreiben in `calculation_service.py` verifizieren und exakt übernehmen.

5. Response um die sechs neuen Felder ergänzen; Schema-Docstring um deren Bedeutung erweitern.

- [ ] **Step 4: Run tests**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_wh_change_preview.py -v
```
Erwartet: alle passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_wh_change_preview.py
git commit -F - <<'EOF'
feat(#431): Vorschau zeigt Tagessoll je Wochentag und Saldo/Urlaub vorher-nachher

Ein Skalar bildet einen Tagesplan nicht ab (Mo 8 / Di 0 / Mi 4), und die
Bestaetigungs-Checkbox stand bisher unter einer Zahl, die den Vorgang nicht
beschreibt. Saldo und Urlaubstage kommen aus demselben Dry-Run wie die
betroffenen Abwesenheiten — ein Flush, ein Rollback, kein zweiter Rechenpfad.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 9: #415-Berichtsköpfe zeigen den Tagesplan

**Files:**
- Modify: `backend/app/services/calculation_service.py:67-124` (`weekly_hours_segments`)
- Modify: `backend/app/services/export_service.py:132-149` (`format_weekly_hours_history`), `:257`, `:658`, `:810`, `:1469`
- Modify: `backend/app/services/ods_export_service.py:162`, `:438`, `:524`
- Modify: `backend/app/routers/reports.py:138-172`, `:285-313`
- Modify: `backend/app/schemas/reports.py:78-110`
- Test: `backend/tests/test_415_working_hours_history_reports.py` (erweitern)

- [ ] **Step 1: Write the failing test**

```python
def test_segments_carry_day_plan(db_session, test_user):
    test_user.use_daily_schedule = True
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"),
        hours_tuesday=Decimal("5.0"), hours_wednesday=Decimal("4.0"),
        work_days_per_week=3))
    db_session.commit()

    segs = calculation_service.weekly_hours_segments(
        db_session, test_user, date(2026, 1, 1), date(2026, 12, 31))

    assert len(segs) == 2
    assert segs[1].use_daily_schedule is True
    assert segs[1].day_hours[0] == Decimal("8.0")


def test_format_names_the_weekdays():
    text = export_service.format_weekly_hours_history([
        calculation_service.ScheduleSegment(
            start=date(2026, 1, 1), end=date(2026, 2, 28),
            weekly_hours=Decimal("40.0"), use_daily_schedule=False,
            day_hours=(None,) * 5, work_days_per_week=5),
        calculation_service.ScheduleSegment(
            start=date(2026, 3, 1), end=date(2026, 12, 31),
            weekly_hours=Decimal("17.0"), use_daily_schedule=True,
            day_hours=(Decimal("8.0"), Decimal("5.0"), Decimal("4.0"), None, None),
            work_days_per_week=3),
    ])
    assert "ab 01.03.2026" in text
    assert "Mo 8,0" in text and "Mi 4,0" in text
    assert "17,0" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_415_working_hours_history_reports.py -v
```
Erwartet: FAIL — Segmente sind heute 3er-Tupel ohne Tagesangaben.

- [ ] **Step 3: Segmente auf ein NamedTuple heben**

```python
class ScheduleSegment(NamedTuple):
    """#415/#431: ein Zeitraum konstanten Vertragszustands."""
    start: date
    end: date
    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple
    work_days_per_week: int
```

`weekly_hours_segments` bildet Grenzen weiterhin aus `effective_from`, holt die Werte aber über `get_schedule_for_date` und verschmilzt zwei Segmente nur, wenn der **vollständige** Snapshot gleich ist (nicht nur die Wochenstunden). Rückwärtskompatibilität: `ScheduleSegment` ist ein Tupel — bestehende Entpackungen `for (start, end, hours) in segments` brechen. **Alle** Aufrufer entsprechend anpassen; `grep -rn "weekly_hours_segments" backend/app`.

- [ ] **Step 4: Formatter erweitern**

`export_service.format_weekly_hours_history`: im Tagesplan-Modus
`ab TT.MM.JJJJ: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche`, sonst der bisherige Text unverändert. Deutsche Dezimalkommas, Wochentage nur mit gesetztem Wert.

- [ ] **Step 5: Frontend-Zwilling wortgleich nachziehen**

`frontend/src/utils/formatters.ts::formatWeeklyHoursChanges` erzeugt denselben Text; `frontend/src/utils/formatters.test.ts:94-125` nagelt die Wortgleichheit — dort einen Tagesplan-Fall ergänzen. `backend/app/schemas/reports.py::WeeklyHoursChangeInPeriod` trägt die neuen Felder, damit das Frontend sie bekommt.

- [ ] **Step 6: Run tests**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/ && \
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
cd frontend && npx vitest run --pool=threads src/utils
```
Erwartet: beide grün.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests frontend/src/utils
git commit -F - <<'EOF'
feat(#431): Berichtskoepfe weisen den Tagesplan aus

weekly_hours_segments traegt den vollstaendigen Snapshot; zwei Segmente
verschmelzen nur noch bei identischem Vertragszustand. Sonst zeigte ein
Tagesplan-Mitarbeiter in allen sechs §16-Flaechen eine Zahl, die nichts steuert,
und eine Aenderungsspalte, die nie fuellt.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 10: Dialog — Modus-Umschalter und fünf Tagesfelder

**Files:**
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx`
- Modify: `frontend/src/pages/admin/Users.tsx:640-646`, `:820-827`, `:910-917`
- Test: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx` (erweitern, `:215-234` umschreiben)

- [ ] **Step 1: Write the failing test**

```typescript
it('zeigt fünf Tagesfelder, wenn der Tagesplan-Modus gewählt ist', async () => {
  renderModal({ currentUseDailySchedule: true });
  expect(await screen.findByLabelText('Montag')).toBeInTheDocument();
  expect(screen.getByLabelText('Freitag')).toBeInTheDocument();
  expect(screen.queryByLabelText('Wochenstunden')).not.toBeInTheDocument();
});

it('berechnet die Wochenstunden als Summe der Tageswerte', async () => {
  renderModal({ currentUseDailySchedule: true });
  fireEvent.change(await screen.findByLabelText('Montag'), { target: { value: '8' } });
  fireEvent.change(screen.getByLabelText('Mittwoch'), { target: { value: '4' } });
  expect(screen.getByText(/12,0 h\/Woche/)).toBeInTheDocument();
});

it('schickt den Tagesplan an den Endpoint', async () => {
  renderModal({ currentUseDailySchedule: true });
  fireEvent.change(await screen.findByLabelText('Montag'), { target: { value: '8' } });
  fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/ }));
  await waitFor(() => {
    const call = (apiClient.post as Mock).mock.calls.at(-1);
    expect(call![1]).toMatchObject({ use_daily_schedule: true, hours_monday: 8 });
  });
});

it('zeigt Saldo und Urlaub vorher/nachher aus der Vorschau', async () => {
  mockPreview({ overtime_before: 89, overtime_after: 41.5,
                vacation_days_before: 18, vacation_days_after: 18,
                day_targets_current: [8, 5, 4, 0, 0], day_targets_new: [6, 5, 4, 0, 0],
                affected_absences: 12, is_retroactive: true });
  renderModal({ currentUseDailySchedule: true });
  expect(await screen.findByText(/Überstunden/)).toBeInTheDocument();
  expect(screen.getByText(/−47,5/)).toBeInTheDocument();
});
```

`renderModal` und `mockPreview` sind lokale Helfer der bestehenden Testdatei — dort ergänzen, Props `currentUseDailySchedule`, `currentDayHours`, `currentWorkDays`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run --pool=threads src/pages/admin/users/WorkingHoursModal.test.tsx
```
Erwartet: FAIL — die Felder existieren nicht.

- [ ] **Step 3: Dialog umbauen**

- `WorkingHoursModalProps` um `currentUseDailySchedule: boolean`, `currentDayHours: (number|null)[]`, `currentWorkDays: number` erweitern; `Users.tsx:910-917` gibt sie aus dem `hoursModalUser` mit.
- `formData` trägt `use_daily_schedule`, `hours_monday…friday`, `work_days_per_week`.
- Radio-Gruppe „Gleichmäßig / Nach Tagen"; im Tagesplan-Zweig fünf `<input type="number" step="0.5" min="0" max="24">` mit `<label>` **Montag**…**Freitag** plus der berechneten Summe als Text.
- `activeWeeklyHoursFromHistory` wird zu `activeScheduleFromHistory` und liefert den vollständigen Snapshot für Kopfzeile und Reset nach dem Speichern.
- Preview-Effekt: Dependency-Liste um die neuen Felder erweitern; Query-Parameter entsprechend senden. Der 400-ms-Debounce bleibt.
- Auswirkungs-Box: Tagessoll-Zeile aus `day_targets_current/new` (nur Tage, an denen einer der beiden Werte > 0 ist), darunter die Tabelle Überstunden/Urlaub mit Δ.
- `saveDisabled` zusätzlich, wenn der eingegebene Snapshot dem aktuell gültigen entspricht (nichts zu speichern).
- Verlaufszeile rendert im Tagesplan-Modus `Ab … bis …: Mo 8 / Di 5 / Mi 4 = 17,0 Std/Woche`, sonst unverändert.
- Titel „Wochenstunden & Tagesplan"; `title`/`aria-label` der Uhr-Buttons in `Users.tsx` entsprechend.

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run --pool=threads src/pages/admin && npx tsc --noEmit
```
Erwartet: grün.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin
git commit -F - <<'EOF'
feat(#431): Stundenverlauf-Dialog kennt Tagesplan und Modus-Wechsel

Fuenf Tagesfelder mit automatischer Wochensumme, Umschalter zwischen
gleichmaessigen Wochenstunden und Tagesplan, und eine Auswirkungs-Box, die das
Tagessoll je Wochentag sowie Saldo und Urlaub vorher/nachher gegenueberstellt.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 11: UserForm — Tagesplan beim Bearbeiten read-only

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx:376-438`, `:757-814`
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx:233-305` (umschreiben)

- [ ] **Step 1: Write the failing test**

```typescript
it('zeigt den Button auch bei individuellem Tagesplan', () => {
  renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true } });
  expect(screen.getByRole('button', { name: /Wochenstunden anpassen/i })).toBeInTheDocument();
});

it('zeigt Tagesstunden beim Bearbeiten nur als Anzeige', () => {
  renderForm({ editUser: { ...baseEditUser, use_daily_schedule: true, hours_monday: 8 } });
  expect(screen.queryByLabelText('Stunden Montag')).not.toBeInTheDocument();
  expect(screen.getByText(/Mo 8,0/)).toBeInTheDocument();
});

it('sendet keine historisierten Felder beim Update', async () => {
  renderForm({ editUser: baseEditUser });
  fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
  await waitFor(() => {
    const call = (apiClient.put as Mock).mock.calls.at(-1);
    for (const f of ['weekly_hours', 'use_daily_schedule', 'work_days_per_week',
                     'hours_monday', 'hours_tuesday', 'hours_wednesday',
                     'hours_thursday', 'hours_friday']) {
      expect(call![1]).not.toHaveProperty(f);
    }
  });
});

it('erlaubt alle Felder beim Anlegen', () => {
  renderForm({ editUser: null });
  expect(screen.getByLabelText('Wochenstunden')).toBeEnabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run --pool=threads src/pages/admin/users/UserForm.test.tsx
```
Erwartet: FAIL — der Button fehlt bei `use_daily_schedule: true`.

- [ ] **Step 3: Formular umbauen**

- Gating `editUser && !formData.use_daily_schedule` (`:378`) → `editUser` allein; im Tagesplan-Fall zeigt die read-only-Box `Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche`, sonst wie bisher `40,0 h/Woche`.
- Hinweistext `:423-430` entfernen (sachlich überholt).
- Tagesstunden-Block `:757-814`, Haken „Individuelle Tagesstunden" und „Arbeitstage pro Woche" beim **Bearbeiten** als Anzeige rendern, mit dem Hinweis „Änderung über „Wochenstunden anpassen…" mit Wirkungsdatum". Beim **Anlegen** unverändert Eingabefelder.
- Der Update-Payload-Ausschluss aus Task 7 Step 4 ist bereits gesetzt.

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run --pool=threads && npx tsc --noEmit && npm run build
```
Erwartet: alles grün.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/users
git commit -F - <<'EOF'
feat(#431): Tagesplan im Bearbeiten-Formular als Anzeige mit Dialog-Button

Der Button fehlte genau fuer die Gruppe, die ihn am dringendsten braucht. Alle
Soll-Treiber laufen jetzt ueber denselben Weg; das Formular zeigt sie nur noch.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 12: DSGVO-Export

**Files:**
- Modify: `backend/app/services/lifecycle_service.py:323-330`
- Modify: `backend/app/routers/auth.py` (`/me/export`)
- Test: `backend/tests/test_dsgvo_export_schedule.py` (neu)

- [ ] **Step 1: Write the failing test**

```python
"""#431: die Stundenhistorie gehoert in den Art.-15/20-Export — und zwar
JSON-serialisierbar (Decimal-Leak-Klasse #383/#408)."""
import json
from datetime import date
from decimal import Decimal

from app.models import WorkingHoursChange
from app.services import lifecycle_service


def test_export_contains_schedule_history_and_is_json_safe(db_session, test_user):
    db_session.add(WorkingHoursChange(
        user_id=test_user.id, tenant_id=test_user.tenant_id,
        effective_from=date(2026, 3, 1), weekly_hours=Decimal("17.0"),
        use_daily_schedule=True, hours_monday=Decimal("8.0"), work_days_per_week=3))
    db_session.commit()

    data = lifecycle_service._user_dict(db_session, test_user)
    dumped = json.dumps(data)          # darf NICHT werfen

    assert "working_hours_changes" in data
    assert data["working_hours_changes"][0]["hours_monday"] == 8.0
    assert "8.0" in dumped or "8" in dumped
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose cp backend/tests backend:/app/ && \
docker compose exec -T backend pytest tests/test_dsgvo_export_schedule.py -v
```
Erwartet: FAIL — `working_hours_changes` fehlt im Export.

- [ ] **Step 3: Export ergänzen**

In `lifecycle_service._user_dict` einen Block ergänzen, der die Historie des Users tenant-gefiltert lädt und **jedes** `Numeric`-Feld mit `float()` castet (rohe `json.dumps`-Fläche → `Decimal` wirft dort). Dasselbe in `auth.py`'s `/me/export`. Exakte Signatur von `_user_dict` vor dem Schreiben prüfen.

- [ ] **Step 4: Run tests**

```bash
docker compose cp backend/app backend:/app/ && \
docker compose exec -T backend pytest tests/test_dsgvo_export_schedule.py tests/ -q -k "export or dsgvo" \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
```
Erwartet: grün.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_dsgvo_export_schedule.py
git commit -F - <<'EOF'
feat(#431): Stundenhistorie im DSGVO-Export

Die Historie ist jetzt vertragsrelevant und gehoert damit in Art. 15/20. Die
Numeric-Felder werden gecastet — der Export laeuft ueber rohes json.dumps, das
Decimal nicht serialisieren kann (Fehlerklasse #383/#408).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 13: Dokumentation über alle fünf Sync-Flächen

**Files:**
- Modify: `docs/BERECHNUNGEN.md:59`, `:95ff`, `:432`, `:828-849`, `:929`, `:951`, `:966-971`
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md:255`, `:496`, `:861`, `:959`; `docs/handbuch/CHEATSHEET-ADMIN.md:58`; `docs/handbuch/SCHNELLSTART.md:37`; `docs/GLOSSAR.md:9`
- Modify: `frontend/public/help/{HANDBUCH-ADMIN,CHEATSHEET-ADMIN,SCHNELLSTART}.md` (byte-identischer Mirror)
- Modify: `frontend/src/components/DocViewer.tsx:196`, `:410`, `:577`
- Modify: `CLAUDE.md` (Abschnitt #415 erweitern)

- [ ] **Step 1: Falschaussagen finden**

```bash
grep -rn "kein Stundenverlauf\|Tagesplan" docs/ frontend/public/help/ frontend/src/components/DocViewer.tsx
```
`HANDBUCH-ADMIN.md:255` behauptet explizit, für Tagesplan-MA gebe es keinen Stundenverlauf — das ist ab jetzt falsch.

- [ ] **Step 2: Texte nachziehen**

Überall dieselbe Aussage: Wochenstunden, Tagesstunden, Modus und Arbeitstage werden ausschließlich über „Wochenstunden anpassen…" mit Wirkungsdatum geändert; rückwirkende Änderungen zeigen vorher Tagessoll je Wochentag sowie Saldo und Urlaub vorher/nachher und ziehen gebuchte Abwesenheits-Stunden nach; abgeschlossene Jahre werden nur gemeldet.

- [ ] **Step 3: Mirror verifizieren**

```bash
for f in HANDBUCH-ADMIN CHEATSHEET-ADMIN SCHNELLSTART; do
  diff -q docs/handbuch/$f.md frontend/public/help/$f.md || echo "DRIFT: $f"
done
```
Erwartet: keine Ausgabe.

- [ ] **Step 4: CLAUDE.md ergänzen**

Den #415-Absatz um die #431-Regel erweitern: die Historien-Zeile ist ein vollständiger Vertrags-Snapshot; `get_daily_target_for_date` verlangt den aufgelösten `Schedule`; `PUT /admin/users` lehnt alle acht historisierten Felder ab; bei neuen Soll-Treibern gehören sie in den Snapshot statt auf die User-Zeile.

- [ ] **Step 5: Commit**

```bash
git add docs frontend/public/help frontend/src/components/DocViewer.tsx CLAUDE.md
git commit -F - <<'EOF'
docs(#431): Tagesplan-Historie in allen fuenf Sync-Flaechen

Das Admin-Handbuch behauptete ausdruecklich, fuer Mitarbeitende mit
individuellem Tagesplan gebe es keinen Stundenverlauf.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 14: E2E + Abschlussverifikation

**Files:**
- Modify: `e2e/tests/admin/user-management.spec.ts`
- Test: voller Lauf

- [ ] **Step 1: E2E-Fall ergänzen**

Ein Test, der einen Tagesplan-MA anlegt, den Dialog über den Formular-Button öffnet, eine rückwirkende Tagesplan-Änderung mit Bestätigung speichert und die neue Verlaufszeile prüft. Muster und Fixtures aus der bestehenden Datei übernehmen (`weekdayFromNow`, Cleanup-Fixtures, `page.locator('main')`-Scoping).

- [ ] **Step 2: Volle Suite**

```bash
docker compose cp backend/app backend:/app/ && docker compose cp backend/tests backend:/app/
docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/ -q \
  --ignore=tests/test_tenant_rls.py --ignore=tests/test_concurrency.py
docker compose exec -T backend pytest tests/test_tenant_rls.py tests/test_cross_tenant_api.py -v
cd frontend && npx vitest run --pool=threads && npx tsc --noEmit && npm run build
```

- [ ] **Step 3: E2E**

`.env` auf `LOGIN_RATE_LIMIT=10000/minute REFRESH_RATE_LIMIT=10000/minute` setzen, `docker compose up -d backend`, dann:

```bash
cd e2e && npx playwright test
```

- [ ] **Step 4: Postgres-Verifikation**

Migration up→down→up gegen Wegwerf-PG (Kommando aus Task 1 Step 6) plus ein `purge_user`-Durchlauf gegen dieselbe DB — FK-Verletzungen sind auf SQLite unsichtbar.

- [ ] **Step 5: Commit + Push**

```bash
git add e2e
git commit -F - <<'EOF'
test(#431): E2E fuer die Tagesplan-Aenderung ueber den Dialog

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
git push -u origin feat/431-tagesplan-historie
```

---

## Self-Review

**Spec-Abdeckung:** Datenmodell → Task 1 · Resolver → Task 2 · Pflichtparameter + Call-Sites → Task 3 · Rückrechnung → Task 4 · POST/Sperre → Task 5 · DELETE → Task 6 · PUT-400 → Task 7 · Vorschau → Task 8 · #415 → Task 9 · Dialog → Task 10 · UserForm → Task 11 · DSGVO → Task 12 · Doku → Task 13 · Tests/PG → Task 14.

**Abweichungen von der Spec, bewusst:**
- `UNIQUE (tenant_id, user_id, effective_from)` ist **nicht** in Migration 067. Eine Bestandsdatenbank mit (theoretisch unmöglichen) Duplikaten würde sonst beim Kundenupdate hart abbrechen; der App-seitige Duplikat-Check bleibt. Als eigenes Issue nachziehen.
- Der wochentagsscharfe Retarget-Filter entfällt: die vorhandene Gleichheitsprüfung erledigt das bereits (Task 4 belegt es).

**Typkonsistenz:** `Schedule` (Task 2) wird in Task 3, 8 und 9 verwendet; `ScheduleSegment` (Task 9) ist ein eigener Typ und wird nicht mit `Schedule` vermischt. Feldnamen `day_hours`, `work_days_per_week`, `use_daily_schedule` durchgängig identisch. Preview-Felder `day_targets_current`/`day_targets_new`/`overtime_before`/`overtime_after`/`vacation_days_before`/`vacation_days_after` sind in Task 8 definiert und in Task 10 konsumiert.
