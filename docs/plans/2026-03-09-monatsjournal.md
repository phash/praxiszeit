# Monatsjournal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Tagesgenaues Monatsjournal für Admin (pro Mitarbeiter) und Mitarbeiter (eigene Ansicht) — Zeittabelle mit Ist/Soll/Saldo pro Tag plus monatliche und jährliche Aggregate.

**Architecture:** Neuer `journal_service.py` berechnet alle Tages-Objekte server-seitig (nutzt bestehende `calculation_service`-Logik). Neuer `journal.py`-Router mit zwei Endpoints (`/api/admin/users/{id}/journal` und `/api/journal/me`). Gemeinsame Frontend-Komponente `MonthlyJournal.tsx` wird in zwei neuen Seiten (`UserJournal.tsx` für Admin, `Journal.tsx` für Mitarbeiter) verwendet.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite (Tests), React 18, TypeScript, Tailwind CSS, Lucide React, date-fns

---

## Referenzen

- Design-Doc: `docs/plans/2026-03-09-monatsjournal-design.md`
- Verwandte Services: `backend/app/services/calculation_service.py` (Soll/Ist-Berechnungen)
- Bestehende Router-Patterns: `backend/app/routers/dashboard.py` (ähnliche Struktur)
- Bestehende Auth-Deps: `get_current_user`, `require_admin` aus `backend/app/middleware/auth.py`
- Frontend-Komponenten: `MonthSelector` (`src/components/MonthSelector.tsx`), `apiClient` (`src/api/client.ts`)
- Test-Fixtures: `backend/tests/conftest.py` (db, test_user, test_admin, public_holiday)

---

## Task 1: Backend Journal Service

**Files:**
- Create: `backend/app/services/journal_service.py`
- Test: `backend/tests/test_journal_service.py`

### Step 1: Testdatei anlegen und erste Tests schreiben

```python
# backend/tests/test_journal_service.py
"""Tests für journal_service."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import journal_service


def _make_entry(db, user, d, start_h, end_h, break_min=0):
    entry = TimeEntry(
        user_id=user.id,
        date=d,
        start_time=time(start_h, 0),
        end_time=time(end_h, 0),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_absence(db, user, d, atype, hours=8.0):
    absence = Absence(
        user_id=user.id,
        date=d,
        type=atype,
        hours=hours,
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return absence


def test_journal_returns_correct_day_count(db, test_user):
    """März 2026 hat 31 Tage → journal enthält 31 Tage."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert len(result["days"]) == 31


def test_journal_work_day_has_correct_type(db, test_user):
    """Montag mit Zeiteintrag → type='work'."""
    monday = date(2026, 3, 9)
    _make_entry(db, test_user, monday, 8, 17, break_min=60)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert day["type"] == "work"
    assert day["actual_hours"] == pytest.approx(8.0)


def test_journal_weekend_has_weekend_type(db, test_user):
    """Samstag → type='weekend', keine Stunden."""
    saturday = date(2026, 3, 14)  # Samstag
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-14")
    assert day["type"] == "weekend"
    assert day["actual_hours"] == 0.0
    assert day["target_hours"] == 0.0


def test_journal_holiday_has_holiday_type(db, test_user):
    """Feiertag → type='holiday'."""
    h = PublicHoliday(date=date(2026, 3, 11), name="Testfeiertag", year=2026)
    db.add(h)
    db.commit()
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-11")
    assert day["type"] == "holiday"
    assert day["holiday_name"] == "Testfeiertag"
    assert day["target_hours"] == 0.0


def test_journal_vacation_day(db, test_user):
    """Urlaubstag → type='vacation', target=0, balance=0."""
    tuesday = date(2026, 3, 10)
    _make_absence(db, test_user, tuesday, AbsenceType.VACATION, hours=8.0)
    result = journal_service.get_journal(db, test_user, 2026, 3)
    day = next(d for d in result["days"] if d["date"] == "2026-03-10")
    assert day["type"] == "vacation"
    assert day["target_hours"] == 0.0
    assert day["balance"] == 0.0


def test_journal_empty_work_day_is_deficit(db, test_user):
    """Werktag ohne Eintrag → type='empty', Saldo negativ."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    monday = next(d for d in result["days"] if d["date"] == "2026-03-09")
    assert monday["type"] == "empty"
    assert monday["actual_hours"] == 0.0
    assert monday["target_hours"] == pytest.approx(8.0)
    assert monday["balance"] == pytest.approx(-8.0)


def test_journal_monthly_summary(db, test_user):
    """monthly_summary stimmt mit calculation_service überein."""
    from app.services import calculation_service
    result = journal_service.get_journal(db, test_user, 2026, 3)
    expected_target = float(calculation_service.get_monthly_target(db, test_user, 2026, 3))
    assert result["monthly_summary"]["target_hours"] == pytest.approx(expected_target)


def test_journal_yearly_overtime_zero_without_entries(db, test_user):
    """Kein Eintrag → yearly_overtime = 0.0."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["yearly_overtime"] == 0.0


def test_journal_user_info_included(db, test_user):
    """Benutzerinfo im Response enthalten."""
    result = journal_service.get_journal(db, test_user, 2026, 3)
    assert result["user"]["first_name"] == test_user.first_name
    assert result["user"]["last_name"] == test_user.last_name
```

### Step 2: Tests ausführen – müssen FEHLSCHLAGEN

```bash
docker-compose exec backend pytest tests/test_journal_service.py -v
```

Erwartet: `ModuleNotFoundError: No module named 'app.services.journal_service'`

### Step 3: `journal_service.py` implementieren

```python
# backend/app/services/journal_service.py
"""Monatsjournal-Service: Tagesgenaue Übersicht über Zeit- und Abwesenheitseinträge."""
from datetime import date
from calendar import monthrange
from decimal import Decimal
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType
from app.services import calculation_service


# Mapping von AbsenceType auf Journal-Typ-String
_ABSENCE_TYPE_MAP = {
    AbsenceType.VACATION: "vacation",
    AbsenceType.SICK: "sick",
    AbsenceType.TRAINING: "training",
    AbsenceType.OVERTIME: "overtime",
    AbsenceType.OTHER: "other",
}


def get_journal(db: Session, user: User, year: int, month: int) -> Dict[str, Any]:
    """
    Berechnet das Monatsjournal für einen Benutzer.

    Gibt ein Dict mit:
    - user: Kurzinfo (id, first_name, last_name)
    - year, month
    - days: Liste von Tages-Objekten (31 für März etc.)
    - monthly_summary: Ist/Soll/Saldo für den Monat
    - yearly_overtime: kumulierter Überstundensaldo bis Ende des Monats

    Tages-Objekte enthalten:
    - date (ISO), weekday, type, is_holiday, holiday_name
    - time_entries[], absences[]
    - actual_hours, target_hours, balance
    """
    _, last_day = monthrange(year, month)

    # Zeiteinträge des Monats laden
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract("year", TimeEntry.date) == year,
        extract("month", TimeEntry.date) == month,
    ).order_by(TimeEntry.date, TimeEntry.start_time).all()

    entries_by_date: Dict[date, List[TimeEntry]] = {}
    for e in entries:
        entries_by_date.setdefault(e.date, []).append(e)

    # Abwesenheiten des Monats laden
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract("year", Absence.date) == year,
        extract("month", Absence.date) == month,
    ).all()

    absences_by_date: Dict[date, List[Absence]] = {}
    for a in absences:
        absences_by_date.setdefault(a.date, []).append(a)

    # Feiertage des Monats laden
    holidays = db.query(PublicHoliday).filter(
        extract("year", PublicHoliday.date) == year,
        extract("month", PublicHoliday.date) == month,
    ).all()
    holiday_map: Dict[date, str] = {h.date: h.name for h in holidays}

    # Tage aufbauen
    days = []
    for day_num in range(1, last_day + 1):
        d = date(year, month, day_num)
        weekday = d.weekday()  # 0=Mo, 6=So
        is_weekend = weekday >= 5
        is_holiday_day = d in holiday_map

        day_entries = entries_by_date.get(d, [])
        day_absences = absences_by_date.get(d, [])

        # Tages-Typ bestimmen (Priorität: Wochenende > Feiertag > Abwesenheit > Arbeit > Leer)
        if is_weekend:
            day_type = "weekend"
        elif is_holiday_day:
            day_type = "holiday"
        elif day_absences:
            day_type = _ABSENCE_TYPE_MAP.get(day_absences[0].type, "other")
        elif day_entries:
            day_type = "work"
        else:
            day_type = "empty"

        # Stunden berechnen
        # actual_hours: Summe der Nettoarbeitsstunden aus Zeiteinträgen
        actual_hours = Decimal(str(sum(e.net_hours for e in day_entries)))

        # target_hours: Soll-Stunden für diesen Tag
        # Wochenende/Feiertag/Abwesenheit (außer TRAINING) → target=0
        if is_weekend or is_holiday_day or (day_absences and day_absences[0].type != AbsenceType.TRAINING):
            target_hours = Decimal("0")
        else:
            weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, d)
            target_hours = calculation_service.get_daily_target_for_date(user, d, weekly_hours)

        balance = actual_hours - target_hours

        days.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "type": day_type,
            "is_holiday": is_holiday_day,
            "holiday_name": holiday_map.get(d),
            "time_entries": [
                {
                    "id": str(e.id),
                    "start_time": e.start_time.strftime("%H:%M") if e.start_time else None,
                    "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
                    "break_minutes": e.break_minutes,
                    "net_hours": float(Decimal(str(e.net_hours)).quantize(Decimal("0.01"))),
                }
                for e in day_entries
            ],
            "absences": [
                {
                    "id": str(a.id),
                    "type": a.type.value,
                    "hours": float(a.hours),
                }
                for a in day_absences
            ],
            "actual_hours": float(actual_hours.quantize(Decimal("0.01"))),
            "target_hours": float(target_hours.quantize(Decimal("0.01"))),
            "balance": float(balance.quantize(Decimal("0.01"))),
        })

    # Monats-Aggregat (aus calculation_service – konsistente Berechnung)
    monthly_actual = calculation_service.get_monthly_actual(db, user, year, month)
    monthly_target = calculation_service.get_monthly_target(db, user, year, month)
    monthly_balance = monthly_actual - monthly_target

    # Jahres-Überstundensaldo bis zum Ende des angegebenen Monats
    yearly_overtime = calculation_service.get_overtime_account(db, user, year, month)

    return {
        "user": {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        "year": year,
        "month": month,
        "days": days,
        "monthly_summary": {
            "actual_hours": float(monthly_actual.quantize(Decimal("0.01"))),
            "target_hours": float(monthly_target.quantize(Decimal("0.01"))),
            "balance": float(monthly_balance.quantize(Decimal("0.01"))),
        },
        "yearly_overtime": float(yearly_overtime.quantize(Decimal("0.01"))),
    }
```

### Step 4: Tests ausführen – müssen GRÜN sein

```bash
docker-compose exec backend pytest tests/test_journal_service.py -v
```

Erwartet: `9 passed`

### Step 5: Commit

```bash
git add backend/app/services/journal_service.py backend/tests/test_journal_service.py
git commit -m "feat: add journal_service with day-by-day monthly journal logic"
```

---

## Task 2: Backend Journal Router

**Files:**
- Create: `backend/app/routers/journal.py`
- Modify: `backend/app/main.py` (Router registrieren)

### Step 1: `journal.py` anlegen

```python
# backend/app/routers/journal.py
"""Journal-Router: Monatsjournal für Admin und Mitarbeiter."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import User
from app.middleware.auth import get_current_user, require_admin
from app.services import journal_service

router = APIRouter(prefix="/api", tags=["journal"])


@router.get("/admin/users/{user_id}/journal")
def get_user_journal(
    user_id: str,
    year: int = Query(default=None, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, description="Monat 1-12 (Standard: aktuell)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Monatsjournal eines Mitarbeiters (Admin-Zugriff)."""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    return journal_service.get_journal(db, user, year, month)


@router.get("/journal/me")
def get_my_journal(
    year: int = Query(default=None, description="Jahr (Standard: aktuell)"),
    month: int = Query(default=None, description="Monat 1-12 (Standard: aktuell)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Monatsjournal des aktuell eingeloggten Mitarbeiters."""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    return journal_service.get_journal(db, current_user, year, month)
```

### Step 2: Router in `main.py` registrieren

Datei: `backend/app/main.py`

Zeile ~19 (Import):
```python
# Vorher:
from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests

# Nachher:
from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests, journal
```

Zeile ~156 (Register):
```python
# Nach vacation_requests hinzufügen:
app.include_router(journal.router)
```

### Step 3: Manuell testen (Docker-Container neu starten)

```bash
docker-compose restart backend
curl "http://localhost:8000/api/journal/me?year=2026&month=3" \
  -H "Authorization: Bearer <token>"
```

Erwartet: JSON mit `days`, `monthly_summary`, `yearly_overtime`

### Step 4: Commit

```bash
git add backend/app/routers/journal.py backend/app/main.py
git commit -m "feat: add journal API endpoints (/admin/users/{id}/journal, /journal/me)"
```

---

## Task 3: Frontend MonthlyJournal Komponente

**Files:**
- Create: `frontend/src/components/MonthlyJournal.tsx`

Diese Komponente ist der Kern des Features und wird in Task 4+5 wiederverwendet.

### Step 1: Komponente anlegen

```tsx
// frontend/src/components/MonthlyJournal.tsx
import { useState, useEffect } from 'react';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import apiClient from '../api/client';
import MonthSelector from './MonthSelector';
import LoadingSpinner from './LoadingSpinner';

// ---- Typen ----------------------------------------------------------------

interface TimeEntryItem {
  id: string;
  start_time: string | null;
  end_time: string | null;
  break_minutes: number;
  net_hours: number;
}

interface AbsenceItem {
  id: string;
  type: string;
  hours: number;
}

interface JournalDay {
  date: string;
  weekday: string;
  type: 'work' | 'vacation' | 'sick' | 'overtime' | 'training' | 'other' | 'holiday' | 'weekend' | 'empty';
  is_holiday: boolean;
  holiday_name: string | null;
  time_entries: TimeEntryItem[];
  absences: AbsenceItem[];
  actual_hours: number;
  target_hours: number;
  balance: number;
}

interface JournalData {
  user: { id: string; first_name: string; last_name: string };
  year: number;
  month: number;
  days: JournalDay[];
  monthly_summary: { actual_hours: number; target_hours: number; balance: number };
  yearly_overtime: number;
}

// ---- Hilfsfunktionen -------------------------------------------------------

const TYPE_LABELS: Record<string, string> = {
  work: 'Arbeitszeit',
  vacation: 'Urlaub',
  sick: 'Krank',
  overtime: 'Überstundenausgleich',
  training: 'Fortbildung',
  other: 'Sonstiges',
  holiday: 'Feiertag',
  weekend: '',
  empty: '–',
};

const TYPE_COLORS: Record<string, string> = {
  work: 'text-gray-900',
  vacation: 'text-blue-600',
  sick: 'text-orange-600',
  overtime: 'text-purple-600',
  training: 'text-green-600',
  other: 'text-gray-600',
  holiday: 'text-red-600',
  weekend: 'text-gray-400',
  empty: 'text-gray-400',
};

function formatHours(h: number): string {
  if (h === 0) return '–';
  const sign = h < 0 ? '-' : '+';
  const abs = Math.abs(h);
  const hours = Math.floor(abs);
  const mins = Math.round((abs - hours) * 60);
  return mins > 0 ? `${sign}${hours}h ${mins}min` : `${sign}${hours}h`;
}

function formatHoursSimple(h: number): string {
  if (h === 0) return '–';
  const hours = Math.floor(h);
  const mins = Math.round((h - hours) * 60);
  return mins > 0 ? `${hours}h ${mins}min` : `${hours}h`;
}

// ---- Hauptkomponente -------------------------------------------------------

interface MonthlyJournalProps {
  /** User-ID, für die das Journal geladen wird. */
  userId: string;
  /** API-Endpoint-Prefix: '/admin/users' oder '' für /journal/me */
  isAdminView: boolean;
}

export default function MonthlyJournal({ userId, isAdminView }: MonthlyJournalProps) {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(
    format(now, 'yyyy-MM')
  );
  const [data, setData] = useState<JournalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const [year, month] = selectedMonth.split('-').map(Number);
    const url = isAdminView
      ? `/admin/users/${userId}/journal?year=${year}&month=${month}`
      : `/journal/me?year=${year}&month=${month}`;

    setLoading(true);
    setError(null);

    apiClient
      .get(url)
      .then((res) => setData(res.data))
      .catch(() => setError('Journal konnte nicht geladen werden.'))
      .finally(() => setLoading(false));
  }, [selectedMonth, userId, isAdminView]);

  const isNonWorkDay = (day: JournalDay) =>
    day.type === 'weekend' || day.type === 'holiday';

  return (
    <div className="space-y-4">
      {/* Monat-Navigation */}
      <MonthSelector value={selectedMonth} onChange={setSelectedMonth} />

      {loading && <LoadingSpinner />}
      {error && <p className="text-red-600">{error}</p>}

      {data && !loading && (
        <>
          {/* Tabelle */}
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-2 text-left">Datum</th>
                  <th className="px-3 py-2 text-left hidden sm:table-cell">Tag</th>
                  <th className="px-3 py-2 text-left">Typ</th>
                  <th className="px-3 py-2 text-left hidden md:table-cell">Von–Bis</th>
                  <th className="px-3 py-2 text-right hidden md:table-cell">Pause</th>
                  <th className="px-3 py-2 text-right">Ist</th>
                  <th className="px-3 py-2 text-right">Soll</th>
                  <th className="px-3 py-2 text-right">Saldo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.days.map((day) => {
                  const dateObj = parseISO(day.date);
                  const isGray = isNonWorkDay(day);
                  const rowClass = isGray ? 'bg-gray-50 text-gray-400' : 'bg-white';

                  const entry = day.time_entries[0] ?? null;
                  const vonBis =
                    entry && entry.start_time && entry.end_time
                      ? `${entry.start_time}–${entry.end_time}`
                      : '–';
                  const pause =
                    entry && entry.break_minutes > 0
                      ? `${entry.break_minutes} min`
                      : '–';

                  // Mehrere Einträge am selben Tag?
                  const multiEntry = day.time_entries.length > 1;

                  const balanceColor =
                    isGray || day.type === 'empty'
                      ? 'text-gray-400'
                      : day.balance > 0
                      ? 'text-green-600 font-medium'
                      : day.balance < 0
                      ? 'text-red-600 font-medium'
                      : 'text-gray-600';

                  return (
                    <tr key={day.date} className={`${rowClass} hover:bg-gray-50 transition-colors`}>
                      {/* Datum */}
                      <td className="px-3 py-2 font-medium whitespace-nowrap">
                        {format(dateObj, 'dd.MM.', { locale: de })}
                      </td>
                      {/* Wochentag */}
                      <td className="px-3 py-2 hidden sm:table-cell">
                        {format(dateObj, 'EEE', { locale: de })}
                      </td>
                      {/* Typ */}
                      <td className={`px-3 py-2 ${TYPE_COLORS[day.type]}`}>
                        {day.is_holiday && day.holiday_name
                          ? day.holiday_name
                          : TYPE_LABELS[day.type] ?? day.type}
                        {multiEntry && (
                          <span className="ml-1 text-xs text-gray-400">
                            ({day.time_entries.length}×)
                          </span>
                        )}
                      </td>
                      {/* Von–Bis */}
                      <td className="px-3 py-2 hidden md:table-cell text-gray-600 whitespace-nowrap">
                        {isGray ? '–' : vonBis}
                      </td>
                      {/* Pause */}
                      <td className="px-3 py-2 hidden md:table-cell text-right text-gray-500">
                        {isGray ? '' : pause}
                      </td>
                      {/* Ist */}
                      <td className="px-3 py-2 text-right text-gray-700">
                        {isGray ? '' : formatHoursSimple(day.actual_hours)}
                      </td>
                      {/* Soll */}
                      <td className="px-3 py-2 text-right text-gray-500">
                        {isGray ? '' : formatHoursSimple(day.target_hours)}
                      </td>
                      {/* Saldo */}
                      <td className={`px-3 py-2 text-right ${balanceColor}`}>
                        {isGray ? '' : formatHours(day.balance)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Aggregate */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Ist (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.actual_hours)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Soll (Monat)</p>
              <p className="text-lg font-semibold text-gray-800">
                {formatHoursSimple(data.monthly_summary.target_hours)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.monthly_summary.balance >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Saldo (Monat)</p>
              <p className={`text-lg font-semibold ${data.monthly_summary.balance >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                {formatHours(data.monthly_summary.balance)}
              </p>
            </div>
            <div className={`rounded-lg p-3 ${data.yearly_overtime >= 0 ? 'bg-blue-50' : 'bg-orange-50'}`}>
              <p className="text-xs text-gray-500 mb-1">Überstunden (kumuliert)</p>
              <p className={`text-lg font-semibold ${data.yearly_overtime >= 0 ? 'text-blue-700' : 'text-orange-700'}`}>
                {formatHours(data.yearly_overtime)}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

### Step 2: Visuell prüfen (nach Task 4/5 möglich — hier nur Syntaxcheck)

```bash
cd frontend && npm run type-check 2>&1 | head -20
```

Erwartet: Keine Fehler (oder nur Fehler für noch nicht existierende Seiten)

### Step 3: Commit

```bash
git add frontend/src/components/MonthlyJournal.tsx
git commit -m "feat: add MonthlyJournal shared component"
```

---

## Task 4: Admin Journal Seite + Route + Icon

**Files:**
- Create: `frontend/src/pages/admin/UserJournal.tsx`
- Modify: `frontend/src/pages/admin/Users.tsx` (Icon-Button hinzufügen)
- Modify: `frontend/src/App.tsx` (Route hinzufügen)

### Step 1: `UserJournal.tsx` anlegen

```tsx
// frontend/src/pages/admin/UserJournal.tsx
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import MonthlyJournal from '../../components/MonthlyJournal';

export default function UserJournal() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();

  if (!userId) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/admin/users')}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
          aria-label="Zurück zur Benutzerverwaltung"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Monatsjournal</h1>
          <p className="text-sm text-gray-500">Zeitteinträge und Abwesenheiten im Überblick</p>
        </div>
      </div>

      <MonthlyJournal userId={userId} isAdminView={true} />
    </div>
  );
}
```

### Step 2: Icon-Button in `Users.tsx` hinzufügen

Datei: `frontend/src/pages/admin/Users.tsx`

**Import-Zeile erweitern** (Zeile ~4):
```tsx
// Vorher:
import { Plus, Edit2, Key, UserX, UserCheck, Save, X, Clock, Trash2, ArrowUp, ArrowDown, Search, Eye, EyeOff, UserMinus } from 'lucide-react';

// Nachher – BookOpen hinzufügen:
import { Plus, Edit2, Key, UserX, UserCheck, Save, X, Clock, Trash2, ArrowUp, ArrowDown, Search, Eye, EyeOff, UserMinus, BookOpen } from 'lucide-react';
```

**`useNavigate` importieren** (falls noch nicht vorhanden, Zeile ~1):
```tsx
import { useNavigate } from 'react-router-dom';
```

**Im Funktionskörper** nach den bestehenden `const`-Deklarationen:
```tsx
const navigate = useNavigate();
```

**Icon-Button in der Desktop-Tabellen-Zeile pro User:**

In der User-Tabelle gibt es pro Zeile Aktions-Buttons (Edit, Key, Deactivate etc.). Suche nach dem Muster `{/* Actions */}` oder dem Edit-Button. Füge den Journal-Button als ersten Button ein:

```tsx
{/* Journal-Button */}
<button
  type="button"
  onClick={() => navigate(`/admin/users/${user.id}/journal`)}
  className="p-1.5 rounded hover:bg-blue-50 text-blue-500 hover:text-blue-700 transition-colors"
  title="Monatsjournal anzeigen"
>
  <BookOpen className="w-4 h-4" />
</button>
```

**Tipp zum Finden der richtigen Stelle:** Suche nach `Edit2` im JSX-Teil der Komponente (nicht im Import). Der `<button>` mit `Edit2`-Icon ist der Edit-Button pro User. Füge den Journal-Button unmittelbar davor ein.

### Step 3: Route in `App.tsx` registrieren

Datei: `frontend/src/App.tsx`

**Import hinzufügen** (bei den anderen Admin-Page-Imports):
```tsx
import UserJournal from './pages/admin/UserJournal';
```

**Route hinzufügen** (nach der `users`-Route):
```tsx
// Vorher:
<Route path="users" element={<Users />} />

// Nachher:
<Route path="users" element={<Users />} />
<Route path="users/:userId/journal" element={<UserJournal />} />
```

### Step 4: Manuell testen

1. `http://localhost` → Admin-Login
2. `/admin/users` → Journal-Icon bei einem Benutzer anklicken
3. Journal-Seite lädt → Tabelle mit Tagen, Monatsselector, Aggregate sichtbar

### Step 5: Commit

```bash
git add frontend/src/pages/admin/UserJournal.tsx frontend/src/pages/admin/Users.tsx frontend/src/App.tsx
git commit -m "feat: add admin user journal page at /admin/users/:userId/journal"
```

---

## Task 5: Mitarbeiter Journal Seite + Route + Nav

**Files:**
- Create: `frontend/src/pages/Journal.tsx`
- Modify: `frontend/src/components/Layout.tsx` (Nav-Eintrag)
- Modify: `frontend/src/App.tsx` (Route hinzufügen)

### Step 1: `Journal.tsx` anlegen

Die Mitarbeiter-Seite ist einfacher als die Admin-Seite, weil die userId aus dem Auth-Kontext kommt.

```tsx
// frontend/src/pages/Journal.tsx
import { useAuthStore } from '../stores/authStore';
import MonthlyJournal from '../components/MonthlyJournal';

export default function Journal() {
  const user = useAuthStore((s) => s.user);

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Mein Journal</h1>
        <p className="text-sm text-gray-500">Zeiteinträge und Abwesenheiten im Überblick</p>
      </div>
      <MonthlyJournal userId={user.id} isAdminView={false} />
    </div>
  );
}
```

**Hinweis:** `useAuthStore` exportiert den Zustand aus `frontend/src/stores/authStore.ts`. Prüfe den genauen Hook-Namen dort:
```bash
grep -n "export\|useAuth\|authStore" frontend/src/stores/authStore.ts | head -10
```

### Step 2: Nav-Eintrag in `Layout.tsx` hinzufügen

Datei: `frontend/src/components/Layout.tsx`

**Import erweitern** – `BookOpen` hinzufügen (bereits bei anderen Lucide-Icons):
```tsx
// Suche die Zeile mit dem Lucide-Import und füge BookOpen hinzu:
import { ..., BookOpen } from 'lucide-react';
```

**`navItems`-Array erweitern** (nach `change-requests` und vor `absences` oder nach `absences`):
```tsx
const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/time-tracking', label: 'Zeiterfassung', icon: Clock },
  { path: '/change-requests', label: 'Änderungsanträge', icon: FileEdit },
  { path: '/absences', label: 'Abwesenheiten', icon: Calendar },
  { path: '/journal', label: 'Journal', icon: BookOpen },  // NEU
  { path: '/profile', label: 'Profil', icon: User },
  { path: '/help', label: 'Hilfe', icon: HelpCircle },
];
```

### Step 3: Route in `App.tsx` registrieren

**Import hinzufügen:**
```tsx
import Journal from './pages/Journal';
```

**Route hinzufügen** (nach der `absences`-Route im Employee-Block):
```tsx
// Vorher:
<Route path="absences" element={<AbsenceCalendarPage />} />

// Nachher:
<Route path="absences" element={<AbsenceCalendarPage />} />
<Route path="journal" element={<Journal />} />
```

### Step 4: `useAuthStore` prüfen

```bash
grep -n "export\|user\b" frontend/src/stores/authStore.ts | head -15
```

Falls der Store `user` anders exportiert (z.B. als `useAuth().user`), `Journal.tsx` entsprechend anpassen.

### Step 5: Manuell testen

1. Als Mitarbeiter einloggen
2. Sidebar → "Journal" anklicken
3. `/journal` → Eigene Zeiteinträge und Abwesenheiten sichtbar

### Step 6: Commit

```bash
git add frontend/src/pages/Journal.tsx frontend/src/components/Layout.tsx frontend/src/App.tsx
git commit -m "feat: add employee journal page at /journal with sidebar nav entry"
```

---

## Task 6: E2E Tests

**Files:**
- Create: `e2e/tests/admin/user-journal.spec.ts`
- Create: `e2e/tests/employee/journal.spec.ts`

### Step 1: Admin-Journal-Tests anlegen

```typescript
// e2e/tests/admin/user-journal.spec.ts
import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin User Journal', () => {
  test('öffnet Journal über Icon-Button in User-Liste', async ({ adminPage, testEmployee }) => {
    await adminPage.goto('/admin/users');
    // Journal-Icon des Test-Mitarbeiters anklicken
    // Das Icon ist ein button mit title="Monatsjournal anzeigen"
    const journalBtn = adminPage
      .locator('table tbody tr')
      .filter({ hasText: testEmployee.last_name })
      .locator('button[title="Monatsjournal anzeigen"]')
      .first();
    await journalBtn.click();
    await expect(adminPage).toHaveURL(new RegExp(`/admin/users/.+/journal`));
    await expect(adminPage.locator('h1')).toContainText('Monatsjournal');
  });

  test('Journal-Seite zeigt Tabelle mit Tagen', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    // Tabelle mit Tages-Zeilen sichtbar
    const rows = adminPage.locator('table tbody tr');
    await expect(rows).toHaveCount(
      new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate()
    );
  });

  test('Monatsnavigation wechselt Monat', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    // Zurück-Button im MonthSelector klicken
    await adminPage.locator('button[aria-label*="Vorheriger"]').click();
    // URL oder Anzeige ändert sich (Tabelle wird neu geladen)
    await expect(adminPage.locator('table tbody tr').first()).toBeVisible();
  });

  test('Tag mit Zeiteintrag zeigt Arbeitszeit', async ({
    adminPage,
    adminApi,
    testEmployee,
    createTimeEntry,
  }) => {
    const today = new Date();
    const dateStr = today.toISOString().split('T')[0];
    await createTimeEntry(testEmployee.id, {
      date: dateStr,
      start_time: '08:00',
      end_time: '16:00',
      break_minutes: 30,
    });

    const year = today.getFullYear();
    const month = today.getMonth() + 1;
    await adminPage.goto(
      `/admin/users/${testEmployee.id}/journal?year=${year}&month=${month}`
    );

    // Die Zeile für heute zeigt "Arbeitszeit"
    const dayStr = String(today.getDate()).padStart(2, '0') + '.' +
      String(month).padStart(2, '0') + '.';
    const row = adminPage.locator('table tbody tr').filter({ hasText: dayStr });
    await expect(row).toContainText('Arbeitszeit');
  });

  test('Aggregate-Kacheln sind sichtbar', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    await expect(adminPage.getByText('Ist (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Soll (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Saldo (Monat)')).toBeVisible();
    await expect(adminPage.getByText('Überstunden (kumuliert)')).toBeVisible();
  });
});
```

### Step 2: Mitarbeiter-Journal-Tests anlegen

```typescript
// e2e/tests/employee/journal.spec.ts
import { test, expect } from '../../fixtures/base.fixture';

test.describe('Employee Journal', () => {
  test('Journal-Seite erreichbar über Sidebar', async ({ employeePage }) => {
    await employeePage.goto('/');
    await employeePage.locator('nav').getByRole('link', { name: 'Journal' }).click();
    await expect(employeePage).toHaveURL('/journal');
    await expect(employeePage.locator('h1')).toContainText('Journal');
  });

  test('Journal zeigt Tages-Tabelle', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    const rows = employeePage.locator('table tbody tr');
    await expect(rows).toHaveCount(
      new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate()
    );
  });

  test('Aggregate-Kacheln sichtbar', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.getByText('Ist (Monat)')).toBeVisible();
    await expect(employeePage.getByText('Saldo (Monat)')).toBeVisible();
    await expect(employeePage.getByText('Überstunden (kumuliert)')).toBeVisible();
  });
});
```

### Step 3: E2E-Tests ausführen

```bash
cd e2e && npx playwright test tests/admin/user-journal.spec.ts tests/employee/journal.spec.ts --project=chromium
```

Erwartet: `7 passed` (oder ggf. einzelne flaky durch Rate-Limit → Retry klärt das)

### Step 4: Gesamte Suite prüfen (keine Regressionen)

```bash
cd e2e && npx playwright test --project=chromium 2>&1 | tail -5
```

Erwartet: ≥96 passed, ≤4 skipped, 0 neue Fehler

### Step 5: Commit

```bash
git add e2e/tests/admin/user-journal.spec.ts e2e/tests/employee/journal.spec.ts
git commit -m "test(e2e): add journal page E2E tests (admin + employee, #44)"
```

### Step 6: Push

```bash
git push origin master
```

---

## Erfolgskriterien

- [ ] `pytest tests/test_journal_service.py` → 9 passed
- [ ] `GET /api/journal/me?year=2026&month=3` → JSON mit 31 Tagen
- [ ] `GET /api/admin/users/{id}/journal` → korrekte Daten für anderen User
- [ ] Admin: Icon-Button in User-Liste → öffnet Journal-Seite
- [ ] Mitarbeiter: "Journal" in Sidebar → `/journal` mit eigenen Daten
- [ ] E2E: 7 neue Tests grün, keine Regressionen
