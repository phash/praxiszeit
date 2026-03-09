# Monatsjournal – Design

**Ziel:** Admin und Mitarbeiter können ein tagesgenaues Journal der Zeiteinträge und Abwesenheiten pro Monat einsehen, mit monatlichen und jährlichen Aggregaten.

**Referenz:** GitHub Issue #44

---

## Architektur

**Ansatz:** Dedizierter Backend-Endpoint (server-seitige Aggregation). Der Endpoint gibt pro Tag ein strukturiertes Objekt zurück – inklusive Zeiteinträgen, Abwesenheiten, Ist-/Soll-Stunden und Tagessaldo. Monatliche und jährliche Aggregate werden im gleichen Response mitgeliefert.

**Warum nicht client-seitige Aggregation:** Die Berechnungslogik (Soll-Stunden, Feiertage, historische Arbeitsstunden) liegt bereits im Backend und ist vollständig getestet. Client-seitige Duplizierung wäre fehleranfällig.

---

## Routen

| Rolle | URL | Beschreibung |
|-------|-----|--------------|
| Admin | `/admin/users/:userId/journal` | Journal eines beliebigen Mitarbeiters |
| Mitarbeiter | `/journal` | Eigenes Journal |

Der Admin erreicht die Seite über ein Icon-Button in der User-Tabelle (`/admin/users`).

---

## Backend

### Endpoints

```
GET /admin/users/{user_id}/journal?year=2026&month=3
GET /journal/me?year=2026&month=3
```

### Response-Struktur

```json
{
  "user": { "id": 1, "name": "Max Mustermann" },
  "year": 2026,
  "month": 3,
  "days": [
    {
      "date": "2026-03-09",
      "weekday": "Monday",
      "type": "work",
      "is_holiday": false,
      "holiday_name": null,
      "time_entries": [
        {
          "id": 1,
          "start_time": "08:00",
          "end_time": "17:00",
          "break_minutes": 45,
          "net_hours": 8.25
        }
      ],
      "absences": [],
      "actual_hours": 8.25,
      "target_hours": 8.0,
      "balance": 0.25
    },
    {
      "date": "2026-03-10",
      "weekday": "Tuesday",
      "type": "vacation",
      "is_holiday": false,
      "holiday_name": null,
      "time_entries": [],
      "absences": [{ "type": "VACATION", "hours": 8.0 }],
      "actual_hours": 8.0,
      "target_hours": 8.0,
      "balance": 0.0
    }
  ],
  "monthly_summary": {
    "actual_hours": 165.5,
    "target_hours": 176.0,
    "balance": -10.5
  },
  "yearly_overtime": -3.25
}
```

### Tages-Typen (`type`)

| Wert | Bedeutung |
|------|-----------|
| `work` | Zeiteinträge vorhanden |
| `vacation` | Urlaub |
| `sick` | Krank |
| `overtime` | Überstundenausgleich |
| `training` | Fortbildung |
| `holiday` | Feiertag |
| `weekend` | Wochenende |
| `empty` | Werktag ohne Eintrag (zählt als Defizit) |

### Implementierung

- Neuer Router: `backend/app/routers/journal.py`
- Nutzt bestehende Services: `calculation_service`, `holiday_service`
- Iteriert durch alle Tage des Monats (analog `get_monthly_target`)
- Für den jährlichen Überstundensaldo: `get_overtime_account(db, user, year, month)`

---

## Frontend

### Gemeinsame Komponente: `MonthlyJournal.tsx`

Props: `userId: number`, `isAdminView: boolean`

Enthält: MonthSelector (bestehende Komponente), Tabelle, Aggregate-Footer.

### Tabellenstruktur

| Datum | Wochentag | Typ | Von–Bis | Pause | Ist | Soll | Saldo |
|-------|-----------|-----|---------|-------|-----|------|-------|
| 09.03. | Mo | Arbeitszeit | 08:00–17:00 | 45 min | 8,25h | 8,00h | +0,25h |
| 10.03. | Di | Urlaub | — | — | 8,00h | 8,00h | 0,00h |
| 11.03. | Mi | — (fehlt) | — | — | 0,00h | 8,00h | -8,00h |
| 14.03. | Sa | Wochenende | — | — | — | — | — |

**Farbkodierung:**
- Grau: Wochenenden, Feiertage
- Grün: Tage mit positivem Saldo
- Rot: Tage mit negativem Saldo (fehlende Einträge)
- Blau: Abwesenheiten (Urlaub, Krank, etc.)

**Aggregate am Tabellenende:**
- Monat: Summe Ist / Summe Soll / Monatssaldo
- Jahr: Kumulierter Überstundensaldo

### Neue Seiten

- `frontend/src/pages/admin/UserJournal.tsx` (Admin-Route)
- `frontend/src/pages/Journal.tsx` (Mitarbeiter-Route)

### Neue Routen (App.tsx)

```tsx
// Admin
<Route path="users/:userId/journal" element={<UserJournal />} />

// Mitarbeiter
<Route path="journal" element={<Journal />} />
```

### Navigation

- **Admin**: Icon-Button (z.B. `📋`) in der User-Tabelle, verlinkt auf `/admin/users/:id/journal`
- **Mitarbeiter**: Neuer Menüpunkt "Journal" in der Sidebar

---

## Testing

- Backend: Unit-Tests für den neuen Journal-Service (analog `test_calculations_extended.py`)
- E2E: `tests/admin/user-journal.spec.ts` + `tests/employee/journal.spec.ts`
  - Journal-Seite lädt
  - Monatsnavigation wechselt korrekt
  - Tage mit Einträgen zeigen korrekte Werte
  - Aggregate stimmen
