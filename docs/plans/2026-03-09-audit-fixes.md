# Audit Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all Critical, Important und Minor issues aus dem Code-Review-Audit vom 2026-03-09.

**Architecture:** Reine Backend/Frontend-Bugfixes ohne neue Features. Alle Änderungen sind rückwärtskompatibel. Kein neues Schema-Migration nötig.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 (Backend), React + TypeScript + Tailwind (Frontend)

---

## Übersicht der Tasks

| Task | Issues | Dateien |
|------|--------|---------|
| 1 | C1 + M6 | `backend/app/routers/auth.py` |
| 2 | C2 + I5 | `backend/app/services/holiday_service.py` + `backend/app/routers/admin.py` |
| 3 | I1 | `backend/app/routers/change_requests.py` |
| 4 | I2 | `backend/app/routers/absences.py` |
| 5 | I3 | `backend/app/services/calculation_service.py` |
| 6 | I4 | `backend/app/services/calculation_service.py` + `routers/vacation_requests.py` + `routers/admin.py` |
| 7 | I6 | `backend/app/schemas/user.py` + `backend/app/routers/admin.py` |
| 8 | M2 + M3 + M5 | `change_requests.py` + `schemas/user.py` + `models/user.py` |
| 9 | M4 | `frontend/src/pages/admin/Users.tsx` |

---

## Task 1: C1 + M6 – Magic Bytes + Rate Limit für Profilbild-Upload

**Problem:** `file.content_type` kommt vom Client → angreifer-kontrolliert. Kein Rate-Limit.

**Files:**
- Modify: `backend/app/routers/auth.py`

**Step 1: Lese die Datei**

```bash
# Überprüfe den aktuellen Stand von update_profile_picture (Zeile ~292-309)
```

**Step 2: Ersetze `update_profile_picture` komplett**

In `backend/app/routers/auth.py`, ersetze die Funktion `update_profile_picture`:

```python
@router.put("/profile-picture", response_model=UserResponse)
@limiter.limit("20/minute")
async def update_profile_picture(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload profile picture. Max 500KB, JPEG or PNG only. Magic bytes verified."""
    contents = await file.read()
    if len(contents) > 512_000:
        raise HTTPException(status_code=400, detail="Bild zu groß (max. 500 KB)")

    # Magic bytes check – client-controlled Content-Type not trusted (C1)
    _JPEG_MAGIC = b'\xff\xd8\xff'
    _PNG_MAGIC  = b'\x89PNG'
    if contents[:3] == _JPEG_MAGIC:
        mime = "image/jpeg"
    elif contents[:4] == _PNG_MAGIC:
        mime = "image/png"
    else:
        raise HTTPException(status_code=400, detail="Nur JPEG oder PNG erlaubt")

    data_uri = f"data:{mime};base64,{base64.b64encode(contents).decode()}"
    current_user.profile_picture = data_uri
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)
```

**Step 3: Verifikation**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose exec backend python -c "
from app.routers.auth import update_profile_picture
print('OK – function importiert')
"
```

Expected: `OK – function importiert`

**Step 4: Commit**

```bash
git add backend/app/routers/auth.py
git commit -m "fix: magic bytes validation + rate limit on profile picture upload (C1, M6)"
```

---

## Task 2: C2 + I5 – Atomare Feiertag-Synchronisation

**Problem:** `delete_all_holidays` committed → kurzes Fenster ohne Feiertage. Bei Exception bleibt DB dauerhaft leer.

**Files:**
- Modify: `backend/app/services/holiday_service.py`
- Modify: `backend/app/routers/admin.py`

**Step 1: `holiday_service.py` – Commits aus Teilfunktionen entfernen**

Ersetze `delete_all_holidays` (entfernt `db.commit()`):

```python
def delete_all_holidays(db: Session) -> int:
    """Delete all holidays from the database. Caller is responsible for committing."""
    count = db.query(PublicHoliday).count()
    db.query(PublicHoliday).delete()
    # No commit – let the caller manage the transaction
    return count
```

Ersetze `sync_holidays` (entfernt `db.commit()`):

```python
def sync_holidays(db: Session, year: int, state: Optional[str] = None) -> int:
    """
    Synchronize public holidays for a given year into the database.
    Caller is responsible for committing.
    Returns number of holidays added.
    """
    cal = _get_calendar(state)
    holidays = cal.holidays(year)

    count = 0
    for holiday_date, holiday_name in holidays:
        german_name = _translate_name(holiday_name)

        existing = db.query(PublicHoliday).filter(
            PublicHoliday.date == holiday_date
        ).first()

        if not existing:
            holiday = PublicHoliday(
                date=holiday_date,
                name=german_name,
                year=year
            )
            db.add(holiday)
            count += 1
        elif existing.name != german_name:
            existing.name = german_name

    # No commit – let the caller manage the transaction
    return count
```

Ersetze `sync_current_and_next_year` (ein einziger Commit am Ende):

```python
def sync_current_and_next_year(db: Session, state: Optional[str] = None) -> dict:
    """
    Sync holidays for current and next year.
    Called during application startup and when Bundesland changes.
    Performs a single commit at the end.
    """
    if state is None:
        state = get_holiday_state(db)

    current_year = datetime.now().year
    next_year = current_year + 1

    # Force-update names of all existing holidays to German
    all_holidays = db.query(PublicHoliday).all()
    for h in all_holidays:
        german_name = _translate_name(h.name)
        if german_name != h.name:
            h.name = german_name

    current_count = sync_holidays(db, current_year, state)
    next_count = sync_holidays(db, next_year, state)

    db.commit()  # Single commit for the entire operation

    return {
        "current_year": current_year,
        "current_count": current_count,
        "next_year": next_year,
        "next_count": next_count,
        "state": state,
    }
```

**Step 2: `admin.py` – `update_setting` atomarisieren**

Finde die `update_setting` Funktion (ca. Zeile 903–938). Ersetze den letzten Teil der Funktion (ab `s = db.query(SystemSetting)...`):

```python
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s:
        s = SystemSetting(key=key, value=str(value), description=key)
        db.add(s)
    else:
        s.value = str(value)

    if key == "holiday_state":
        # Atomarer Delete + Sync: alles in einer Transaktion (C2, I5)
        try:
            holiday_service.delete_all_holidays(db)   # kein commit
            holiday_service.sync_current_and_next_year(db, state=str(value))  # commitet am Ende
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Einstellung gespeichert, aber Feiertage konnten nicht synchronisiert werden: {e}"
            )
    else:
        db.commit()

    db.refresh(s)
    return {"key": s.key, "value": s.value, "updated_at": s.updated_at}
```

**Wichtig:** Die Zeile `db.commit()` + `db.refresh(s)` die vorher nach dem `if not s` Block stand, muss entfernt werden. Der neue Code macht commit nur einmal (entweder via `sync_current_and_next_year` oder direkt).

**Step 3: Verifikation**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose exec backend python -c "
from app.services.holiday_service import delete_all_holidays, sync_holidays, sync_current_and_next_year
import inspect
src_delete = inspect.getsource(delete_all_holidays)
src_sync = inspect.getsource(sync_holidays)
assert 'db.commit()' not in src_delete, 'delete_all_holidays sollte kein commit enthalten'
assert 'db.commit()' not in src_sync, 'sync_holidays sollte kein commit enthalten'
print('OK – keine Zwischen-Commits in delete_all_holidays und sync_holidays')
"
```

Expected: `OK – keine Zwischen-Commits in delete_all_holidays und sync_holidays`

**Step 4: Commit**

```bash
git add backend/app/services/holiday_service.py backend/app/routers/admin.py
git commit -m "fix: atomare Feiertag-Synchronisation – kein Holiday-Window, Rollback bei Fehler (C2, I5)"
```

---

## Task 3: I1 – first/last_work_day in Change Requests prüfen

**Problem:** Mitarbeiter kann Änderungsantrag für Datum außerhalb seines Beschäftigungszeitraums stellen.

**Files:**
- Modify: `backend/app/routers/change_requests.py`

**Step 1: Füge Datumsgrenzen-Check nach dem "For CREATE" Block hinzu**

In `create_change_request`, nach Zeile ~65 (`if data.proposed_date >= date.today():`), ergänze direkt darunter:

```python
        # Arbeitszeitraum-Prüfung
        if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
            raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
        if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
            raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")
```

**Step 2: Füge Check für UPDATE hinzu**

Nach Zeile ~70 (`if not all([data.proposed_date, ...]):` für UPDATE), ergänze:

```python
        if data.proposed_date:
            if current_user.first_work_day and data.proposed_date < current_user.first_work_day:
                raise HTTPException(status_code=400, detail="Datum liegt vor dem ersten Arbeitstag")
            if current_user.last_work_day and data.proposed_date > current_user.last_work_day:
                raise HTTPException(status_code=400, detail="Datum liegt nach dem letzten Arbeitstag")
```

**Step 3: Commit**

```bash
git add backend/app/routers/change_requests.py
git commit -m "fix: first/last_work_day Grenzprüfung in change_requests (I1)"
```

---

## Task 4: I2 – first/last_work_day in Abwesenheiten prüfen

**Problem:** Urlaub/Abwesenheit kann vor `first_work_day` oder nach `last_work_day` gebucht werden.

**Files:**
- Modify: `backend/app/routers/absences.py`

**Step 1: Füge Check in `create_absence` nach `target_user`-Bestimmung ein**

Nach Zeile ~193 (`if not target_user: raise HTTPException(404, ...)`), vor der Datumsbereichs-Validierung, füge ein:

```python
    # Arbeitszeitraum-Prüfung (I2)
    if target_user.first_work_day and start_date < target_user.first_work_day:
        raise HTTPException(
            status_code=400,
            detail=f"Datum liegt vor dem ersten Arbeitstag ({target_user.first_work_day.strftime('%d.%m.%Y')})"
        )
    if target_user.last_work_day and end_date > target_user.last_work_day:
        raise HTTPException(
            status_code=400,
            detail=f"Datum liegt nach dem letzten Arbeitstag ({target_user.last_work_day.strftime('%d.%m.%Y')})"
        )
```

Hinweis: `end_date` wird in `create_absence` weiter unten gesetzt (`end_date = absence_data.end_date if absence_data.end_date else absence_data.date`). Der Check muss NACH dieser Zeile stehen.

**Step 2: Commit**

```bash
git add backend/app/routers/absences.py
git commit -m "fix: first/last_work_day Grenzprüfung in absences (I2)"
```

---

## Task 5: I3 – Pro-rata Urlaubsformel auf tagesgenaue Berechnung

**Problem:** `months_remaining = 12 - month + 1` rundet auf ganzen Monat statt tagesgenaue Berechnung.

**Files:**
- Modify: `backend/app/services/calculation_service.py`

**Aktueller Code** in `get_vacation_account` (Zeile ~325-331):
```python
    if user.first_work_day and user.first_work_day.year == year:
        months_remaining = Decimal(str(12 - user.first_work_day.month + 1))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    if user.last_work_day and user.last_work_day.year == year:
        months_worked = Decimal(str(user.last_work_day.month))
        budget_days_last = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
        budget_days = min(budget_days, budget_days_last)
```

**Ersetze mit** (tagesgenaue Berechnung, `monthrange` ist bereits importiert):
```python
    if user.first_work_day and user.first_work_day.year == year:
        fwd = user.first_work_day
        days_in_month = monthrange(fwd.year, fwd.month)[1]
        days_remaining = days_in_month - fwd.day + 1  # inklusive Starttag
        # Vollständige Monate nach dem Startmonat + Anteil des Startmonats
        months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
        budget_days = (Decimal(str(user.vacation_days)) * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
    if user.last_work_day and user.last_work_day.year == year:
        lwd = user.last_work_day
        days_in_month = monthrange(lwd.year, lwd.month)[1]
        days_worked = lwd.day  # inklusive letzten Tag
        # Vollständige Monate vor dem Endmonat + Anteil des Endmonats
        months_worked = Decimal(str(lwd.month - 1)) + Decimal(str(days_worked)) / Decimal(str(days_in_month))
        budget_days_last = (Decimal(str(user.vacation_days)) * months_worked / Decimal('12')).quantize(Decimal('0.1'))
        budget_days = min(budget_days, budget_days_last)
```

**Step 3: Verifikation**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose exec backend python -c "
from decimal import Decimal
from calendar import monthrange
from datetime import date

# Simulation: Mitarbeiter startet 15. März
year = 2026
fwd = date(2026, 3, 15)
vacation_days = Decimal('30')
days_in_month = monthrange(fwd.year, fwd.month)[1]  # 31
days_remaining = days_in_month - fwd.day + 1  # 17
months_remaining = Decimal(str(12 - fwd.month)) + Decimal(str(days_remaining)) / Decimal(str(days_in_month))
# = 9 + 17/31 ≈ 9.548
budget = (vacation_days * months_remaining / Decimal('12')).quantize(Decimal('0.1'))
print(f'Budget für Start 15.03: {budget} Tage (erwartet ca. 23.9)')
assert 23 < float(budget) < 25, f'Wert außerhalb Erwartungsbereich: {budget}'

# Alt-Formel zum Vergleich
old_months = Decimal(str(12 - fwd.month + 1))  # = 10
old_budget = (vacation_days * old_months / Decimal('12')).quantize(Decimal('0.1'))
print(f'Alt-Formel: {old_budget} Tage (zu großzügig wegen ganzer Monat)')
print('OK')
"
```

Expected: Budget ca. 23.9 Tage, Alt-Formel 25.0 Tage

**Step 4: Commit**

```bash
git add backend/app/services/calculation_service.py
git commit -m "fix: tagesgenaue Pro-rata Urlaubsberechnung statt ganzer Monate (I3)"
```

---

## Task 6: I4 – `_count_workdays` in calculation_service auslagern

**Problem:** Identische Funktion in `vacation_requests.py` (`_count_workdays`) und `admin.py` (`_count_workdays_for_vr`) – doppelter Code, Wartungsrisiko.

**Files:**
- Modify: `backend/app/services/calculation_service.py`
- Modify: `backend/app/routers/vacation_requests.py`
- Modify: `backend/app/routers/admin.py`

**Step 1: `timedelta` Import zu calculation_service hinzufügen**

In `calculation_service.py`, ergänze `timedelta` zum bestehenden Import:
```python
from datetime import date, datetime, timedelta
```

**Step 2: `count_workdays` Funktion am Ende von `calculation_service.py` hinzufügen**

```python
def count_workdays(db: Session, start: date, end: date) -> int:
    """Count weekdays (Mon-Fri) excluding public holidays between start and end (inclusive)."""
    years: set = set()
    cur = start
    while cur <= end:
        years.add(cur.year)
        cur += timedelta(days=1)

    holidays: set = set()
    for year in years:
        year_holidays = db.query(PublicHoliday).filter(PublicHoliday.year == year).all()
        holidays.update(h.date for h in year_holidays)

    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur += timedelta(days=1)
    return count
```

**Step 3: `vacation_requests.py` – lokale Funktion ersetzen**

1. Füge Import hinzu (ganz oben bei den imports):
   ```python
   from app.services.calculation_service import count_workdays
   ```

2. Lösche die lokale `_count_workdays` Funktion (Zeile ~22-44).

3. Ersetze den Aufruf `_count_workdays(vr.date, end, db)` mit `count_workdays(db, vr.date, end)`.

**Wichtig:** Die Signatur hat sich geändert – `db` ist jetzt der erste Parameter.

**Step 4: `admin.py` – lokale Funktion ersetzen**

1. Füge Import hinzu (bei den anderen Imports aus `app.schemas.user`):
   ```python
   from app.services.calculation_service import count_workdays
   ```

2. Lösche die lokale `_count_workdays_for_vr` Funktion (ca. Zeile 943-958).

3. Ersetze den Aufruf `_count_workdays_for_vr(vr.date, end, db)` mit `count_workdays(db, vr.date, end)`.

**Step 5: Verifikation**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose exec backend python -c "
from app.services.calculation_service import count_workdays
print('count_workdays importierbar:', count_workdays)
from app.routers.vacation_requests import router as vr_router
from app.routers.admin import router as admin_router
print('OK – beide Router laden ohne Fehler')
"
```

Expected: Beide Router ohne ImportError

**Step 6: Commit**

```bash
git add backend/app/services/calculation_service.py backend/app/routers/vacation_requests.py backend/app/routers/admin.py
git commit -m "refactor: _count_workdays in calculation_service zentralisiert (I4)"
```

---

## Task 7: I6 – `UserListResponse` ohne `profile_picture` für Listen-Endpunkte

**Problem:** `GET /admin/users` gibt bis zu 34 MB JSON zurück wegen Base64-Profilbildern in jedem User-Objekt.

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/admin.py`

**Step 1: `UserListResponse` Schema hinzufügen**

In `backend/app/schemas/user.py`, nach der `UserResponse`-Klasse (Zeile ~107) einfügen:

```python
class UserListResponse(BaseModel):
    """Lightweight user response for list endpoints – excludes profile_picture blob."""
    id: UUID
    role: UserRole
    username: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    weekly_hours: float
    vacation_days: int
    work_days_per_week: int
    track_hours: bool
    is_active: bool
    is_hidden: bool = False
    calendar_color: str = '#93C5FD'
    use_daily_schedule: bool = False
    hours_monday: Optional[float] = None
    hours_tuesday: Optional[float] = None
    hours_wednesday: Optional[float] = None
    hours_thursday: Optional[float] = None
    hours_friday: Optional[float] = None
    exempt_from_arbzg: bool = False
    is_night_worker: bool = False
    first_work_day: Optional[date] = None
    last_work_day: Optional[date] = None
    totp_enabled: bool = False
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    suggested_vacation_days: int
    vacation_carryover_deadline: Optional[date] = None

    @field_serializer('id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)

    class Config:
        from_attributes = True
```

**Step 2: `admin.py` – `GET /users` auf `UserListResponse` umstellen**

1. Ergänze den Import in `admin.py`:
   ```python
   from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserCreateResponse, AdminSetPassword, UserListResponse
   ```

2. Ändere den Response-Model des `list_users` Endpoints (ca. Zeile 99):
   ```python
   @router.get("/users", response_model=List[UserListResponse])
   ```

**Step 3: Verifikation**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose exec backend python -c "
from app.schemas.user import UserListResponse
assert not hasattr(UserListResponse.model_fields.get('profile_picture', None), 'default'), 'profile_picture sollte nicht in UserListResponse sein'
assert 'profile_picture' not in UserListResponse.model_fields, 'profile_picture muss aus UserListResponse fehlen'
print('OK – profile_picture nicht in UserListResponse')
"
```

Expected: `OK – profile_picture nicht in UserListResponse`

**Step 4: Commit**

```bash
git add backend/app/schemas/user.py backend/app/routers/admin.py
git commit -m "fix: UserListResponse ohne profile_picture – verhindert 34MB JSON bei GET /admin/users (I6)"
```

---

## Task 8: M2 + M3 + M5 – Kleinere Backend-Fixes

**Files:**
- Modify: `backend/app/routers/change_requests.py` (M2)
- Modify: `backend/app/schemas/user.py` (M3)
- Modify: `backend/app/models/user.py` (M5)

**Step 1: M2 – Ungültiger Status-Filter gibt 400 statt silent ignore**

In `change_requests.py`, in der `list_change_requests` Funktion (ca. Zeile 192-195):

Aktuell:
```python
        try:
            status_enum = ChangeRequestStatus(request_status)
            query = query.filter(ChangeRequest.status == status_enum)
        except ValueError:
            pass
```

Ersetze mit:
```python
        try:
            status_enum = ChangeRequestStatus(request_status)
            query = query.filter(ChangeRequest.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültiger Status: {request_status}")
```

**Step 2: M3 – Cross-field Validator `first_work_day < last_work_day`**

In `schemas/user.py`, ergänze `model_validator` zum Import (Zeile 2):
```python
from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator
```

Füge Validator zu `UserBase` hinzu (nach den Felddefinitionen, vor class-Ende):
```python
    @model_validator(mode='after')
    def check_work_day_order(self):
        if self.first_work_day and self.last_work_day:
            if self.first_work_day >= self.last_work_day:
                raise ValueError("Erster Arbeitstag muss vor dem letzten Arbeitstag liegen")
        return self
```

Füge denselben Validator zu `UserUpdate` hinzu (am Ende der Klasse):
```python
    @model_validator(mode='after')
    def check_work_day_order(self):
        if self.first_work_day and self.last_work_day:
            if self.first_work_day >= self.last_work_day:
                raise ValueError("Erster Arbeitstag muss vor dem letzten Arbeitstag liegen")
        return self
```

**Step 3: M5 – `suggested_vacation_days` negative Werte abfangen**

In `backend/app/models/user.py`, ersetze die Property:

Aktuell:
```python
        return round(30 * (self.work_days_per_week or 5) / 5)
```

Ersetze mit:
```python
        return max(0, round(30 * (self.work_days_per_week or 5) / 5))
```

**Step 4: Commit**

```bash
git add backend/app/routers/change_requests.py backend/app/schemas/user.py backend/app/models/user.py
git commit -m "fix: invalid status filter 400, work-day-order validator, suggested_vacation_days guard (M2, M3, M5)"
```

---

## Task 9: M4 – Datums-Anzeige Off-by-One in Users.tsx

**Problem:** `new Date("2026-03-01")` wird als UTC-Mitternacht geparst → in CET+1 Browser zeigt `28.02.2026`.

**Fix:** `T00:00:00` anhängen erzwingt lokale Zeitzone.

**Files:**
- Modify: `frontend/src/pages/admin/Users.tsx`

**Step 1: Alle 4 Vorkommen ersetzen**

Grep bestätigt 4 Stellen:
- Zeile 866: `new Date(user.first_work_day)` (Tabellen-Zeile)
- Zeile 868: `new Date(user.last_work_day)` (Tabellen-Zeile)
- Zeile 1076: `new Date(user.first_work_day)` (Detail-Ansicht)
- Zeile 1082: `new Date(user.last_work_day)` (Detail-Ansicht)

Führe `replace_all` durch:
- `new Date(user.first_work_day)` → `new Date(user.first_work_day + 'T00:00:00')`
- `new Date(user.last_work_day)` → `new Date(user.last_work_day + 'T00:00:00')`

**Step 2: Verifikation im Browser**

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose up -d --build frontend
# Öffne http://localhost/admin/users
# Prüfe: Datumsanzeige korrekt (nicht einen Tag zu früh)
```

**Step 3: Commit**

```bash
git add frontend/src/pages/admin/Users.tsx
git commit -m "fix: Datums-Timezone Off-by-one in Users.tsx – T00:00:00 erzwingt lokale Zeit (M4)"
```

---

## Abschluss: Migrationen anwenden + Docker rebuild

Nach allen Commits:

```bash
cd /e/claude/zeiterfassung/praxiszeit
docker-compose up -d --build
docker-compose exec backend alembic upgrade head
docker-compose logs -f backend  # Auf Fehler prüfen
```

Prüfe API-Health:
```bash
curl http://localhost:8000/api/health
# Expected: {"status": "healthy", ...}
```
