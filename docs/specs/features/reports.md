# Spec: Berichte & Export

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #13

---

## Überblick

Admins können Zeiterfassungsdaten als Excel-Dateien exportieren (Monatsreport, Jahresreport in zwei Formaten) und die gesetzliche Mindestruhezeit (§5 ArbZG) für alle Mitarbeiter prüfen.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich Berichte exportieren, um Daten an die Lohnbuchhaltung weiterzugeben.

- [x] **REQ-1**: Monatsreport als Excel (ein Sheet pro MA, tägliche Einträge + Monatszusammenfassung)
- [x] **REQ-2**: Jahresreport Classic (kompakt: Monate als Spalten, ein Sheet pro MA)
- [x] **REQ-3**: Jahresreport Detailliert (365 Tage pro MA, alle Zeiteinträge)
- [x] **REQ-4**: Excel enthält: Datum, Von, Bis, Pause, Netto, Soll, Saldo, Abwesenheiten
- [x] **REQ-5**: Bayerische Feiertage markiert, Wochenenden grau hinterlegt
- [x] **REQ-6**: Historische Stundenänderungen korrekt berücksichtigt

Als **Admin** möchte ich Ruhezeitverstöße prüfen.

- [x] **REQ-7**: Prüfung ob ≥ 11h Ruhezeit zwischen zwei Arbeitstagen (§5 ArbZG)
- [x] **REQ-8**: Filterbar nach Jahr und optional Monat
- [x] **REQ-9**: Mindestruhezeit konfigurierbar (Standard: 11h)
- [x] **REQ-10**: Ergebnisse expandierbar pro Mitarbeiter (Tag 1 Ende, Tag 2 Start, Ruhezeit, Fehlend)

### Nicht-funktionale Anforderungen

- [x] Monatsexport: < 1s
- [x] Jahresexport Classic: < 3s
- [x] Jahresexport Detailliert: < 10s (Loading-State im Frontend)

---

## Design

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/admin/reports/monthly` | Admin | JSON Monatsbericht |
| `GET` | `/api/admin/reports/export` | Admin | Excel Monatsexport |
| `GET` | `/api/admin/reports/export-yearly` | Admin | Excel Jahresexport (detailliert) |
| `GET` | `/api/admin/reports/export-yearly-classic` | Admin | Excel Jahresexport (classic) |
| `GET` | `/api/admin/reports/yearly-absences` | Admin | JSON Jahres-Abwesenheiten |
| `GET` | `/api/admin/reports/rest-time-violations` | Admin | Ruhezeitverstöße |

**Betroffene Dateien:**
- `backend/app/routers/reports.py`
- `backend/app/services/export_service.py`
- `backend/app/services/rest_time_service.py`
- `backend/app/schemas/reports.py`

**Rest-Time Service:**
```python
DEFAULT_MIN_REST_HOURS = 11.0

def check_rest_time_violations(db, user, year, month=None, min_rest_hours=None):
    # Lädt alle Zeiteinträge, prüft Abstände zwischen Arbeitstagen
    # Ein Verstoß = Abstand zwischen end_time[Tag i] und start_time[Tag i+1] < min_rest_hours
    ...
```

### Frontend (React/TypeScript)

**Betroffene Seiten:**
- `frontend/src/pages/admin/Reports.tsx`

---

## Tasks

- [x] **T-1**: Export Service (Monats-, Jahresreport Classic/Detailliert)
- [x] **T-2**: Reports Router (export endpoints)
- [x] **T-3**: Rest Time Service (`rest_time_service.py`)
- [x] **T-4**: Rest-Time-Violations Endpunkt
- [x] **T-5**: Frontend Reports-Seite mit allen Export-Buttons
- [x] **T-6**: Frontend Ruhezeitprüfung UI
