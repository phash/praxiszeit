# Absences mit Start-/Endzeit + Änderungsanträge für Abwesenheiten

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absences bekommen optionale Start-/Endzeit (statt nur Stunden), und Mitarbeiter können Abwesenheiten per Änderungsantrag beantragen.

**Architecture:** Zwei zusammenhängende Features in einer Migration: (1) Absence-Model um `start_time`/`end_time` erweitern — beide NULL = "ganzer Tag" mit Tagessoll. (2) ChangeRequest-Model um `entry_kind` ("time_entry"/"absence") und Absence-Felder erweitern. Bestehende CR-Logik (create/update/delete) wird für beide Typen wiederverwendet.

**Tech Stack:** Alembic Migration, SQLAlchemy Models, Pydantic Schemas, FastAPI Router, React+TypeScript Frontend

---

## Dateistruktur

| Aktion | Datei | Verantwortung |
|--------|-------|---------------|
| Neu | `backend/alembic/versions/2026_04_01_2200-030_absence_times_and_cr_absences.py` | Migration |
| Mod | `backend/app/models/absence.py` | `start_time`, `end_time` Spalten |
| Mod | `backend/app/models/change_request.py` | `entry_kind`, `absence_id`, `proposed_absence_*`, `original_absence_*` |
| Mod | `backend/app/schemas/absence.py` | Start/End-Zeit in Schemas |
| Mod | `backend/app/schemas/change_request.py` | Absence-Felder in Create/Response |
| Mod | `backend/app/routers/absences.py` | Start/End-Zeit bei Erstellung/Anzeige |
| Mod | `backend/app/routers/change_requests.py` | Absence-CR-Erstellung + Validierung |
| Mod | `backend/app/routers/admin_change_requests.py` | Absence-CR-Approval |
| Mod | `backend/app/services/journal_service.py` | Absence-Zeiten in Journal-Response |
| Mod | `frontend/src/components/MonthlyJournal.tsx` | Absence-Zeiten anzeigen, Absence-CRs erstellen |
| Mod | `frontend/src/pages/ChangeRequests.tsx` | Absence-CRs anzeigen (MA-Sicht) |
| Mod | `frontend/src/pages/admin/ChangeRequests.tsx` | Absence-CRs anzeigen (Admin-Sicht) |
| Neu | `backend/tests/test_absence_cr.py` | Tests für Absence-CRs |

---

### Task 1: Migration — Neue Spalten

**Files:**
- Create: `backend/alembic/versions/2026_04_01_2200-030_absence_times_and_cr_absences.py`

- [ ] **Step 1: Migration erstellen**

```python
"""Add start_time/end_time to absences and absence fields to change_requests."""
from alembic import op
import sqlalchemy as sa

revision = '030_absence_times_cr'
down_revision = '029_add_vacation_request_absence_type'

def upgrade():
    # Absences: optionale Start-/Endzeit
    op.add_column('absences', sa.Column('start_time', sa.Time(), nullable=True))
    op.add_column('absences', sa.Column('end_time', sa.Time(), nullable=True))

    # ChangeRequests: Unterscheidung time_entry vs absence
    op.add_column('change_requests', sa.Column('entry_kind', sa.String(20), nullable=True, server_default='time_entry'))
    op.add_column('change_requests', sa.Column('absence_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('change_requests', sa.Column('proposed_absence_type', sa.String(20), nullable=True))
    op.add_column('change_requests', sa.Column('proposed_absence_hours', sa.Numeric(4, 2), nullable=True))
    op.add_column('change_requests', sa.Column('original_absence_type', sa.String(20), nullable=True))
    op.add_column('change_requests', sa.Column('original_absence_hours', sa.Numeric(4, 2), nullable=True))

    # FK + Index
    op.create_foreign_key('fk_cr_absence_id', 'change_requests', 'absences', ['absence_id'], ['id'])
    op.create_index('ix_change_requests_absence_id', 'change_requests', ['absence_id'])

    # Backfill entry_kind for existing records
    op.execute("UPDATE change_requests SET entry_kind = 'time_entry' WHERE entry_kind IS NULL")

def downgrade():
    op.drop_index('ix_change_requests_absence_id')
    op.drop_constraint('fk_cr_absence_id', 'change_requests', type_='foreignkey')
    op.drop_column('change_requests', 'original_absence_hours')
    op.drop_column('change_requests', 'original_absence_type')
    op.drop_column('change_requests', 'proposed_absence_hours')
    op.drop_column('change_requests', 'proposed_absence_type')
    op.drop_column('change_requests', 'absence_id')
    op.drop_column('change_requests', 'entry_kind')
    op.drop_column('absences', 'end_time')
    op.drop_column('absences', 'start_time')
```

- [ ] **Step 2: Migration auf Host committen**

```bash
git add backend/alembic/versions/2026_04_01_2200-030_absence_times_and_cr_absences.py
git commit -m "migration: 030 — absence start/end time + CR absence fields"
```

---

### Task 2: Backend Models updaten

**Files:**
- Modify: `backend/app/models/absence.py`
- Modify: `backend/app/models/change_request.py`

- [ ] **Step 1: Absence Model — start_time/end_time hinzufügen**

In `backend/app/models/absence.py`, nach `hours = Column(...)`:

```python
start_time = Column(Time, nullable=True)  # NULL = ganzer Tag
end_time = Column(Time, nullable=True)    # NULL = ganzer Tag
```

- [ ] **Step 2: ChangeRequest Model — Absence-Felder hinzufügen**

In `backend/app/models/change_request.py`, neue Spalten nach `time_entry_id`:

```python
entry_kind = Column(String(20), nullable=False, server_default='time_entry')  # 'time_entry' | 'absence'
absence_id = Column(UUID(as_uuid=True), ForeignKey("absences.id"), nullable=True, index=True)
proposed_absence_type = Column(String(20), nullable=True)
proposed_absence_hours = Column(Numeric(4, 2), nullable=True)
original_absence_type = Column(String(20), nullable=True)
original_absence_hours = Column(Numeric(4, 2), nullable=True)
```

Imports: `from sqlalchemy import String, Numeric` (falls nicht vorhanden)

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/absence.py backend/app/models/change_request.py
git commit -m "model: Absence start/end time + ChangeRequest absence fields"
```

---

### Task 3: Backend Schemas updaten

**Files:**
- Modify: `backend/app/schemas/absence.py`
- Modify: `backend/app/schemas/change_request.py`

- [ ] **Step 1: Absence Schemas — start_time/end_time**

In `AbsenceBase`:
```python
from datetime import date, datetime, time as dt_time

class AbsenceBase(BaseModel):
    date: date
    end_date: Optional[date] = None
    type: AbsenceType
    hours: float = Field(..., ge=0, le=24)
    start_time: Optional[dt_time] = None   # NEU
    end_time: Optional[dt_time] = None     # NEU
    note: Optional[str] = None
```

In `AbsenceResponse`, `start_time`/`end_time` Serializer analog zu bestehenden Feldern hinzufügen.

- [ ] **Step 2: ChangeRequest Schemas — Absence-Felder**

In `ChangeRequestCreate`:
```python
entry_kind: str = "time_entry"  # "time_entry" | "absence"
absence_id: Optional[str] = None
proposed_absence_type: Optional[str] = None
proposed_absence_hours: Optional[float] = None
```

In `ChangeRequestResponse`:
```python
entry_kind: str = "time_entry"
absence_id: Optional[UUID] = None
proposed_absence_type: Optional[str] = None
proposed_absence_hours: Optional[float] = None
original_absence_type: Optional[str] = None
original_absence_hours: Optional[float] = None
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/absence.py backend/app/schemas/change_request.py
git commit -m "schema: Absence start/end time + CR absence fields"
```

---

### Task 4: Tests für Absence-CRs schreiben

**Files:**
- Create: `backend/tests/test_absence_cr.py`

- [ ] **Step 1: Test-Datei erstellen**

```python
"""Tests für Änderungsanträge mit Absence-Typen."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    ChangeRequest, ChangeRequestType, ChangeRequestStatus,
)
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username="cr_user", email="cr@test.de", **kwargs):
    defaults = dict(
        password_hash="hash", first_name="CR", last_name="User",
        role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(username=username, email=email, **defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_absence(db, user, d, absence_type, hours, start_t=None, end_t=None):
    absence = Absence(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=d, type=absence_type, hours=hours,
        start_time=start_t, end_time=end_t,
    )
    db.add(absence)
    db.commit()
    return absence


def _make_absence_cr(db, user, request_type="create", **kwargs):
    defaults = dict(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        request_type=request_type, entry_kind="absence",
        status=ChangeRequestStatus.PENDING,
        reason="Testantrag",
    )
    defaults.update(kwargs)
    cr = ChangeRequest(**defaults)
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


class TestAbsenceCRModel:
    """Absence-CR Model-Tests."""

    def test_create_absence_cr_pending(self, db, test_user):
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
        )
        assert cr.entry_kind == "absence"
        assert cr.status == ChangeRequestStatus.PENDING
        assert cr.proposed_absence_type == "sick"

    def test_absence_cr_with_times(self, db, test_user):
        cr = _make_absence_cr(db, test_user,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="training",
            proposed_absence_hours=3.0,
            proposed_start_time=time(14, 0),
            proposed_end_time=time(17, 0),
        )
        assert cr.proposed_start_time == time(14, 0)
        assert cr.proposed_end_time == time(17, 0)

    def test_absence_cr_update_snapshots_original(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10), AbsenceType.VACATION, 8.0)
        cr = _make_absence_cr(db, test_user,
            request_type="update",
            absence_id=absence.id,
            proposed_date=date(2026, 3, 10),
            proposed_absence_type="sick",
            proposed_absence_hours=8.0,
            original_absence_type="vacation",
            original_absence_hours=8.0,
        )
        assert cr.original_absence_type == "vacation"
        assert str(cr.absence_id) == str(absence.id)

    def test_entry_kind_default_is_time_entry(self, db, test_user):
        cr = ChangeRequest(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID,
            request_type="create", status=ChangeRequestStatus.PENDING,
            reason="Test", proposed_date=date(2026, 3, 10),
            proposed_start_time=time(8, 0), proposed_end_time=time(16, 0),
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        assert cr.entry_kind == "time_entry"


class TestAbsenceStartEndTime:
    """Absence mit Start-/Endzeit."""

    def test_absence_with_times(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.TRAINING, 3.0,
            start_t=time(14, 0), end_t=time(17, 0))
        assert absence.start_time == time(14, 0)
        assert absence.end_time == time(17, 0)

    def test_absence_whole_day_no_times(self, db, test_user):
        absence = _make_absence(db, test_user, date(2026, 3, 10),
            AbsenceType.VACATION, 8.0)
        assert absence.start_time is None
        assert absence.end_time is None
```

- [ ] **Step 2: Tests laufen lassen — müssen bestehen (Model-Änderungen aus Task 2)**

Run: `docker compose build backend && docker compose up -d backend && sleep 5 && docker compose exec backend pytest tests/test_absence_cr.py -v`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_absence_cr.py
git commit -m "test: Absence-CR Model-Tests + Absence Start/End Time"
```

---

### Task 5: Absence-Router — Start-/Endzeit unterstützen

**Files:**
- Modify: `backend/app/routers/absences.py`
- Modify: `backend/app/services/journal_service.py`

- [ ] **Step 1: Absences-Router — start_time/end_time bei Erstellung speichern**

In `create_absence()` (absences.py), beim Erstellen des Absence-Objekts die neuen Felder mitgeben:

```python
absence = Absence(
    user_id=target_user.id,
    tenant_id=current_user.tenant_id,
    date=date,
    end_date=end_date if absence_data.end_date else None,
    type=absence_data.type,
    hours=hours_for_day,
    start_time=absence_data.start_time,  # NEU
    end_time=absence_data.end_time,      # NEU
    note=absence_data.note,
)
```

- [ ] **Step 2: Journal-Service — Absence-Zeiten in Response aufnehmen**

In `journal_service.py`, in der Absences-Liste des Journal-Response:

```python
"absences": [
    {
        "id": str(a.id),
        "type": a.type.value,
        "hours": float(Decimal(str(a.hours)).quantize(Decimal("0.01"))),
        "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,  # NEU
        "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,        # NEU
    }
    for a in day_absences
],
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/absences.py backend/app/services/journal_service.py
git commit -m "feat: Absence start/end time in Erstellung + Journal"
```

---

### Task 6: CR-Router — Absence-Anträge erstellen

**Files:**
- Modify: `backend/app/routers/change_requests.py`

- [ ] **Step 1: Absence-CR-Erstellung implementieren**

In `create_change_request()`, nach den bestehenden TimeEntry-Validierungen, neuen Block für `entry_kind == "absence"`:

```python
if data.entry_kind == "absence":
    # Absence CRs: validate absence-specific fields
    if data.request_type in ("update", "delete"):
        if not data.absence_id:
            raise HTTPException(status_code=400, detail="absence_id erforderlich für Absence-Änderung/Löschung")
        absence = db.query(Absence).filter(Absence.id == data.absence_id).first()
        if not absence:
            raise HTTPException(status_code=404, detail="Abwesenheit nicht gefunden")
        if absence.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Zugriff verweigert")

    if data.request_type in ("create", "update"):
        if not data.proposed_absence_type:
            raise HTTPException(status_code=400, detail="Abwesenheitstyp erforderlich")
        if not data.proposed_date:
            raise HTTPException(status_code=400, detail="Datum erforderlich")
        if data.proposed_date >= today_local():
            raise HTTPException(status_code=400, detail="Änderungsanträge sind nur für vergangene Tage möglich")
        if data.proposed_absence_hours is None and not (data.proposed_start_time and data.proposed_end_time):
            raise HTTPException(status_code=400, detail="Stunden oder Start-/Endzeit erforderlich")
        if data.proposed_start_time and data.proposed_end_time:
            if data.proposed_start_time >= data.proposed_end_time:
                raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")

    # Create the CR
    cr = ChangeRequest(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        request_type=data.request_type,
        entry_kind="absence",
        absence_id=data.absence_id if data.request_type in ("update", "delete") else None,
        proposed_date=data.proposed_date,
        proposed_start_time=data.proposed_start_time,
        proposed_end_time=data.proposed_end_time,
        proposed_absence_type=data.proposed_absence_type,
        proposed_absence_hours=data.proposed_absence_hours,
        reason=data.reason,
    )

    # Snapshot original values for update/delete
    if data.request_type in ("update", "delete") and absence:
        cr.original_date = absence.date
        cr.original_absence_type = absence.type.value
        cr.original_absence_hours = absence.hours
        cr.original_start_time = absence.start_time
        cr.original_end_time = absence.end_time

    db.add(cr)
    db.commit()
    db.refresh(cr)
    return _enrich_response(cr, db)
```

Bestehenden TimeEntry-Code in `elif data.entry_kind == "time_entry":` Block wrappen (oder `entry_kind` Default "time_entry" nutzen).

- [ ] **Step 2: Tests ergänzen und laufen lassen**

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/change_requests.py
git commit -m "feat: Absence-CR-Erstellung mit Validierung"
```

---

### Task 7: Admin-CR-Router — Absence-Anträge genehmigen

**Files:**
- Modify: `backend/app/routers/admin_change_requests.py`

- [ ] **Step 1: Absence-CR-Approval implementieren**

In `review_change_request()`, nach den TimeEntry-Precondition-Checks, Absence-Checks hinzufügen:

```python
if cr.entry_kind == "absence":
    if cr.request_type in (ChangeRequestType.UPDATE, ChangeRequestType.DELETE):
        absence = db.query(Absence).filter(Absence.id == cr.absence_id).first()
        if not absence:
            raise HTTPException(status_code=404, detail="Abwesenheit nicht mehr vorhanden")
```

Nach dem Status-Update, Absence-Actions:

```python
if cr.entry_kind == "absence":
    if cr.request_type == ChangeRequestType.CREATE:
        absence = Absence(
            user_id=cr.user_id,
            tenant_id=current_user.tenant_id,
            date=cr.proposed_date,
            type=AbsenceType(cr.proposed_absence_type),
            hours=cr.proposed_absence_hours or 0,
            start_time=cr.proposed_start_time,
            end_time=cr.proposed_end_time,
        )
        db.add(absence)
        db.flush()
        cr.absence_id = absence.id

    elif cr.request_type == ChangeRequestType.UPDATE:
        # absence already fetched in precondition check
        absence.type = AbsenceType(cr.proposed_absence_type) if cr.proposed_absence_type else absence.type
        absence.hours = cr.proposed_absence_hours if cr.proposed_absence_hours is not None else absence.hours
        absence.date = cr.proposed_date if cr.proposed_date else absence.date
        absence.start_time = cr.proposed_start_time
        absence.end_time = cr.proposed_end_time

    elif cr.request_type == ChangeRequestType.DELETE:
        db.delete(absence)
```

- [ ] **Step 2: Tests laufen lassen**

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/admin_change_requests.py
git commit -m "feat: Absence-CR-Approval — CREATE/UPDATE/DELETE"
```

---

### Task 8: Frontend — Journal Absence-Zeiten anzeigen

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`

- [ ] **Step 1: AbsenceItem Interface erweitern**

```typescript
interface AbsenceItem {
  id: string;
  type: string;
  hours: number;
  start_time: string | null;  // NEU
  end_time: string | null;    // NEU
}
```

- [ ] **Step 2: Von-Bis Spalte — Absence-Zeiten statt nur Stunden**

In der Mixed-Day Von-Bis Anzeige, statt `formatHoursSimple(a.hours)`:

```typescript
{day.type === 'mixed' && day.absences.map((a, i) => (
  <div key={`a${i}`} className="text-gray-400">
    {a.start_time && a.end_time
      ? `${a.start_time}–${a.end_time}`
      : `ganzer Tag`}
  </div>
))}
```

Auch bei reinen Absence-Tagen (kein mixed): statt `'–'` die Zeiten anzeigen falls vorhanden.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MonthlyJournal.tsx
git commit -m "feat: Absence-Zeiten im Journal anzeigen"
```

---

### Task 9: Frontend — Mitarbeiter-Änderungsanträge für Absences

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`

- [ ] **Step 1: Employee-Submit für Absences**

In `confirmEmployeeSubmit()`, abhängig von `editState.entryType`:

```typescript
if (editState.entryType === 'work') {
  // bestehende TimeEntry-CR-Logik
  payload = { request_type: ..., entry_kind: 'time_entry', ... };
} else {
  // Absence-CR
  const existingAbsence = day.absences.find(a => a.type === editState.entryType);
  payload = {
    request_type: existingAbsence ? 'update' : 'create',
    entry_kind: 'absence',
    reason: submitReason.trim(),
    proposed_date: day.date,
    proposed_absence_type: editState.entryType,
    proposed_absence_hours: parseFloat(editState.absenceHours) || 0,
  };
  if (existingAbsence) payload.absence_id = existingAbsence.id;
}
```

- [ ] **Step 2: startEmployeeSubmit — auch für Absences erlauben**

`startEmployeeSubmit` aktuell prüft `startTime`/`endTime` — für Absences nicht nötig:

```typescript
function startEmployeeSubmit(day: JournalDay) {
  if (editState.entryType === 'work') {
    if (!editState.startTime || !editState.endTime) {
      toast.error('Von und Bis sind Pflichtfelder');
      return;
    }
  }
  setSubmittingDate(day.date);
  setSubmitReason('');
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MonthlyJournal.tsx
git commit -m "feat: Mitarbeiter können Absence-CRs aus Journal einreichen"
```

---

### Task 10: Frontend — CR-Anzeige für Absences (MA + Admin)

**Files:**
- Modify: `frontend/src/pages/ChangeRequests.tsx`
- Modify: `frontend/src/pages/admin/ChangeRequests.tsx`

- [ ] **Step 1: ChangeRequest Interface erweitern (beide Dateien)**

```typescript
interface ChangeRequest {
  // ... bestehende Felder ...
  entry_kind?: string;  // "time_entry" | "absence"
  absence_id?: string;
  proposed_absence_type?: string;
  proposed_absence_hours?: number;
  original_absence_type?: string;
  original_absence_hours?: number;
}
```

- [ ] **Step 2: Anzeige-Logik — Absence-CRs darstellen**

In der Values-Comparison-Section, bedingte Anzeige:

```typescript
{cr.entry_kind === 'absence' ? (
  // Absence-CR Anzeige
  <div className="text-sm space-y-1">
    <p>Typ: <span className="font-medium">{ABSENCE_TYPE_LABELS[cr.proposed_absence_type || ''] || cr.proposed_absence_type}</span></p>
    <p>Datum: <span className="font-medium">{formatDateDE(cr.proposed_date!)}</span></p>
    <p>Stunden: <span className="font-medium">{cr.proposed_absence_hours}h</span></p>
    {cr.proposed_start_time && cr.proposed_end_time && (
      <p>Zeit: <span className="font-medium">{cr.proposed_start_time?.substring(0, 5)} – {cr.proposed_end_time?.substring(0, 5)}</span></p>
    )}
  </div>
) : (
  // bestehende TimeEntry-CR Anzeige
  ...
)}
```

Import `ABSENCE_TYPE_LABELS` aus `constants/absenceTypes`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChangeRequests.tsx frontend/src/pages/admin/ChangeRequests.tsx
git commit -m "feat: Absence-CRs in MA- und Admin-Ansicht anzeigen"
```

---

### Task 11: Integrationstests + Full Test Suite

**Files:**
- Modify: `backend/tests/test_absence_cr.py`
- Modify: `backend/tests/test_edge_cases.py`

- [ ] **Step 1: Approval-Tests hinzufügen**

```python
class TestAbsenceCRApproval:
    def test_approve_create_absence_cr(self, db, test_user, test_admin):
        """Genehmigung eines Absence-Create-CR erstellt die Absence."""
        # ... CR erstellen, genehmigen, prüfen dass Absence existiert

    def test_approve_update_absence_cr(self, db, test_user, test_admin):
        """Genehmigung eines Absence-Update-CR ändert die Absence."""

    def test_approve_delete_absence_cr(self, db, test_user, test_admin):
        """Genehmigung eines Absence-Delete-CR löscht die Absence."""

    def test_absence_cr_does_not_delete_time_entries(self, db, test_user, test_admin):
        """Absence-CR-Approval löscht keine bestehenden TimeEntries."""
```

- [ ] **Step 2: Absence-Zeiten-Tests**

```python
class TestAbsenceTimesInJournal:
    def test_absence_with_times_shows_in_journal(self, db, test_user):
        """Absence mit Start-/Endzeit zeigt Zeiten im Journal."""

    def test_absence_whole_day_shows_ganzer_tag(self, db, test_user):
        """Ganztages-Absence ohne Zeiten zeigt 'ganzer Tag'."""
```

- [ ] **Step 3: Full Test Suite laufen lassen**

Run: `docker compose exec backend pytest tests/ -v --tb=short`
Expected: Alle Tests bestanden

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: Absence-CR Approval + Journal-Zeiten Tests"
```

---

### Task 12: Frontend Build + Manueller UI-Test

- [ ] **Step 1: TypeScript Check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Keine Fehler

- [ ] **Step 2: Frontend Build ohne Cache**

Run: `docker compose build --no-cache frontend && docker compose up -d frontend`

- [ ] **Step 3: Manueller Test via Playwright**

1. Als Admin einloggen → Journal eines Mitarbeiters öffnen
2. Mixed-Day: Arbeitszeit + Fortbildung mit Zeiten (14:00-17:00) hinzufügen
3. Prüfen: Typ-Spalte zeigt "Arbeitszeit" + "Fortbildung", Von-Bis zeigt Zeiten
4. Als Mitarbeiter einloggen → Journal → vergangenen Tag editieren → Typ auf "Krank" stellen → Antrag einreichen
5. Als Admin → Änderungsanträge → Absence-CR sichtbar mit Typ-Badge + Stunden
6. Genehmigen → Prüfen: Absence wurde erstellt

- [ ] **Step 4: Final Commit + Push**

```bash
git push origin master
```

---

## Verifikation

1. **Backend-Tests:** `docker compose exec backend pytest tests/ -v` — alle bestanden
2. **TypeScript:** `cd frontend && npx tsc --noEmit` — keine Fehler
3. **UI-Test:** Mixed-Day mit Absence-Zeiten korrekt angezeigt
4. **CR-Workflow:** MA reicht Absence-CR ein → Admin genehmigt → Absence erstellt
5. **Bestehende Funktionalität:** TimeEntry-CRs funktionieren weiterhin unverändert
