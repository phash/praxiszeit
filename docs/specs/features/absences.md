# Spec: Abwesenheitsverwaltung

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #8, #12, #16

---

## Überblick

Mitarbeiter erfassen Abwesenheiten (Urlaub, Krank, Fortbildung, Sonstiges) als einzelne Tage oder Zeiträume. Admins können Abwesenheiten für alle Mitarbeiter verwalten. Krankheit während Urlaub kann den Urlaubsanspruch zurückerstatten.

---

## Requirements

### Funktionale Anforderungen

Als **Mitarbeiter** möchte ich Abwesenheiten eintragen, damit mein Urlaubskonto und Soll-Stunden korrekt berechnet werden.

- [x] **REQ-1**: Abwesenheitstypen: Urlaub, Krank, Fortbildung, Sonstiges
- [x] **REQ-2**: Einzeltag oder Zeitraum (Start–Ende) eintragen
- [x] **REQ-3**: Bei Zeitraum: nur Werktage (Mo–Fr), keine Wochenenden, keine Feiertage
- [x] **REQ-4**: Abwesenheitskalender zeigt alle Teammitglieder farbcodiert
- [x] **REQ-5**: Monatsnavigation im Kalender
- [x] **REQ-6**: Kalenderklick füllt Datum im Formular vor
- [x] **REQ-7**: Korrekte Wochenstart-Ausrichtung (Montag = erste Spalte)

Als **Admin** möchte ich Abwesenheiten für Mitarbeiter verwalten.

- [x] **REQ-8**: Admin kann Abwesenheit für beliebigen Mitarbeiter anlegen (`user_id` in POST)
- [x] **REQ-9**: Admin sieht Abwesenheitsübersicht pro Mitarbeiter
- [x] **REQ-10**: Admin kann Abwesenheiten löschen

Als **Mitarbeiter** möchte ich bei Krankheit während Urlaub die Urlaubstage zurückbekommen.

- [x] **REQ-11**: Wenn Krankheit und gleichzeitig Urlaub: Option zum Erstatten
- [x] **REQ-12**: Checkbox "Urlaubstage erstatten" erscheint nur wenn Überschneidung erkannt wird
- [x] **REQ-13**: Bestätigungsdialog vor Erstattung

Als **Admin** möchte ich Betriebsferien (Betriebsurlaub) für alle Mitarbeiter gleichzeitig eintragen.

- [x] **REQ-14**: Betriebsferien mit Name, Start- und End-Datum anlegen
- [x] **REQ-15**: Beim Anlegen: automatisch Urlaubs-Einträge für alle aktiven Mitarbeiter
- [x] **REQ-16**: Beim Löschen: automatisch zugehörige Urlaubs-Einträge entfernen

### Nicht-funktionale Anforderungen

- [x] Urlaubsstunden basieren auf individuellem Tagessoll (`weekly_hours / work_days_per_week`)
- [x] Feiertage werden beim Zeitraum automatisch ausgeschlossen

### Out of Scope

- Urlaubsantrags-Workflow (Beantragen → Genehmigen)
- Halbtages-Abwesenheiten

---

## Design

### Datenbank

```sql
CREATE TABLE absences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    date DATE NOT NULL,
    end_date DATE,              -- NULL = Einzeltag, gesetzt = Zeitraum
    type VARCHAR(20) NOT NULL,  -- 'vacation' | 'sick' | 'training' | 'other'
    hours DECIMAL(4,2) NOT NULL,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- Indexes: user_id, date, type, (user_id, date)

CREATE TABLE company_closures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Migrationen:**
- `003_end_date` – end_date für Zeiträume
- `012_add_company_closures` – Betriebsferien-Tabelle

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/absences` | Employee | Liste (filter: user_id, month) |
| `POST` | `/api/absences` | Employee | Neu (admin: user_id optional) |
| `DELETE` | `/api/absences/{id}` | Employee | Löschen |
| `GET` | `/api/absences/calendar` | Employee | Kalender alle MA (year, month) |
| `GET` | `/api/company-closures` | Employee | Betriebsferien-Liste |
| `POST` | `/api/company-closures` | Admin | Betriebsferien anlegen |
| `DELETE` | `/api/company-closures/{id}` | Admin | Betriebsferien löschen |

**Betroffene Dateien:**
- `backend/app/models/absence.py`, `company_closure.py`
- `backend/app/schemas/absence.py`
- `backend/app/routers/absences.py`, `company_closures.py`

**Schema (AbsenceCreate):**
```python
class AbsenceCreate(BaseModel):
    date: date
    end_date: Optional[date] = None
    type: AbsenceType
    hours: float
    notes: Optional[str] = None
    user_id: Optional[str] = None    # Admin: für anderen Benutzer
    refund_vacation: bool = False    # Krank während Urlaub
```

### Frontend (React/TypeScript)

**Betroffene Seiten:**
- `frontend/src/pages/AbsenceCalendarPage.tsx` – MA-Kalenderansicht + Formular
- `frontend/src/pages/admin/AdminAbsences.tsx` – Admin-Verwaltung (2 Tabs)

**Kalender-Offset-Berechnung (Bug #8):**
```typescript
// Montag als erster Wochentag (getDay(): 0=So, 1=Mo, ..., 6=Sa)
const firstDayOffset = (monthStart.getDay() + 6) % 7;
// Ergebnis: 0=Mo, 1=Di, ..., 6=So
```

---

## Tasks

- [x] **T-1**: Absence Model + Migration (001, 003)
- [x] **T-2**: Absences Router (CRUD + Kalender)
- [x] **T-3**: Company Closures Model + Migration (012) + Router
- [x] **T-4**: Abwesenheitskalender (Frontend) – Bug #8 behoben
- [x] **T-5**: Admin Abwesenheitsverwaltung (AdminAbsences.tsx)
- [x] **T-6**: Vacation-Refund-Logik (sick during vacation)
