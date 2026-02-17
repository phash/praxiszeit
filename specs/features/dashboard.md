# Spec: Dashboard

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #15

---

## Überblick

Das Mitarbeiter-Dashboard zeigt die wichtigsten Kennzahlen auf einen Blick: aktuellen Monat (Ist/Soll/Saldo), Überstunden-Konto, Urlaubskonto mit Resturlaub-Warnung, und eine Überstunden-Verlaufsgrafik. Das Admin-Dashboard zeigt alle Mitarbeiter mit ihren Stundensalden.

---

## Requirements

### Funktionale Anforderungen

Als **Mitarbeiter** möchte ich auf dem Dashboard sofort sehen, wie meine aktuelle Arbeitssituation ist.

- [x] **REQ-1**: Aktueller Monat: Ist-Stunden, Soll-Stunden, Monatssaldo
- [x] **REQ-2**: Überstunden-Konto (kumuliert seit Jahresbeginn)
- [x] **REQ-3**: Urlaubskonto: Budget, verbraucht, verbleibend
- [x] **REQ-4**: Urlaubskonto-Ampel: Grün (≥50% verbleibend), Gelb (≥25%), Rot (<25%)
- [x] **REQ-5**: Überstunden-Verlauf (letzte 6 Monate) als Balkendiagramm
- [x] **REQ-6**: Stempeluhr: Einloggen/Ausloggen per Knopfdruck (erstellt Zeiteintrag)
- [x] **REQ-7**: Warnung wenn Resturlaub > 0 und Monat ≥ Oktober (Jahresende naht)
- [x] **REQ-8**: Konfigurierbare Verfallsfrist für Urlaubsübertrag (per Benutzer)

Als **Admin** möchte ich eine Teamübersicht aller Mitarbeiter sehen.

- [x] **REQ-9**: Tabelle: MA-Name, Wochenstunden, Monats-Soll/Ist/Saldo, kumulierte Überstunden
- [x] **REQ-10**: Jahreswechsel-Warnung im Q4: Liste der MAs mit offenen Urlaubstagen
- [x] **REQ-11**: Jährliche Abwesenheitsübersicht (Urlaub, Krank, Fortbildung, Sonstiges in Tagen)

### Nicht-funktionale Anforderungen

- [x] Dashboard-Daten in einem API-Call (kein Waterfall)
- [x] Resturlaub-Warnung nur im Q4 (Oktober–Dezember) des aktuellen Jahres

---

## Design

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/dashboard` | Employee | MA-Dashboard Stats |
| `GET` | `/api/dashboard/overtime` | Employee | Überstunden-Verlauf (months=6) |
| `GET` | `/api/dashboard/vacation` | Employee | Urlaubskonto (year) |
| `GET` | `/api/admin/dashboard` | Admin | Team-Übersicht |

**Vacation Account Schema:**
```python
class VacationAccount(BaseModel):
    year: int
    budget_days: float
    used_days: float
    remaining_days: float
    color: str               # 'green' | 'yellow' | 'red'
    carryover_deadline: Optional[date]
    has_carryover_warning: bool  # True wenn Q4 und remaining > 0
```

**Betroffene Dateien:**
- `backend/app/routers/dashboard.py`
- `backend/app/services/calculation_service.py`

### Frontend (React/TypeScript)

**Betroffene Seiten:**
- `frontend/src/pages/Dashboard.tsx` – Mitarbeiter-Dashboard
- `frontend/src/pages/admin/AdminDashboard.tsx` – Admin-Übersicht

**Karryover-Warnung (Q4):**
```tsx
{vacationAccount.has_carryover_warning && (
  <div className="p-2 bg-amber-50 border border-amber-200 rounded-lg">
    <p>⚠️ Noch {remaining} Urlaubstage offen!</p>
    <p>Verfallsfrist: {deadline}</p>
  </div>
)}
```

---

## Tasks

- [x] **T-1**: Dashboard Router + Berechnung
- [x] **T-2**: Urlaubskonto-Berechnung mit Ampel
- [x] **T-3**: Überstunden-Verlauf (letzte N Monate)
- [x] **T-4**: Stempeluhr (StampWidget)
- [x] **T-5**: vacation_carryover_deadline Migration (011)
- [x] **T-6**: Carryover-Warnung Backend (has_carryover_warning)
- [x] **T-7**: Carryover-Warnung Frontend (amber box)
- [x] **T-8**: Admin Q4-Jahresend-Banner
