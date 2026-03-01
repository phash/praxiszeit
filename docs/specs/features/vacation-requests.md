# Spec: Urlaubsantrag-Workflow

**Status:** Done
**Erstellt:** 2026-03-01
**Zuletzt aktualisiert:** 2026-03-01
**Migrationen:** 021 (system_settings), 022 (vacation_requests)

---

## Überblick

Admin-konfigurierbarer Genehmigungsworkflow für Urlaubsbuchungen. Über eine Einstellung
(`vacation_approval_required`) kann umgeschaltet werden zwischen:

- **false** (Standard): Mitarbeiter buchen Urlaub direkt in `absences` (bisheriges Verhalten)
- **true**: Mitarbeiter stellen Urlaubsanträge → landen als `pending` bei Admin → nach Genehmigung werden `absences`-Einträge erstellt

Nur Abwesenheitstyp **vacation** ist genehmigungspflichtig. Krank/Fortbildung/Sonstiges
werden weiterhin direkt gebucht.

---

## Requirements

### Funktionale Anforderungen

- [x] **REQ-1**: Admin kann Genehmigungspflicht per Toggle ein-/ausschalten (laufzeitänderbar, kein Restart)
- [x] **REQ-2**: Bei `vacation_approval_required=true`: Urlaubsformular sendet `POST /api/vacation-requests/` statt `POST /api/absences/`
- [x] **REQ-3**: Mitarbeiter sieht eigene Anträge mit Status (pending/approved/rejected) im Tab „Meine Anträge"
- [x] **REQ-4**: Mitarbeiter kann eigene `pending`-Anträge zurückziehen (DELETE)
- [x] **REQ-5**: Bei `rejected`: Mitarbeiter sieht Ablehnungsgrund
- [x] **REQ-6**: Admin sieht alle Anträge, filterbar nach Status und Mitarbeiter
- [x] **REQ-7**: Admin genehmigt → erstellt `absences`-Einträge für alle Werktage im Zeitraum (Feiertage ausgeschlossen)
- [x] **REQ-8**: Bei Genehmigung: Urlaubsbudget-Check (wie bei direkter Buchung)
- [x] **REQ-9**: Bei Genehmigung: `use_daily_schedule` wird berücksichtigt (Stunden pro Tag)
- [x] **REQ-10**: Admin lehnt ab → optionaler Ablehnungsgrund, Status `rejected`
- [x] **REQ-11**: Öffentlicher Endpoint `GET /api/settings` liefert aktuellen Toggle-Wert (kein Auth)
- [x] **REQ-12**: Pending-Count-Badge im Tab „Meine Anträge"

### Nicht-funktionale Anforderungen

- [x] Toggle sofort wirksam (kein Cache, direktes DB-Read)
- [x] Rückwärtskompatibel: Default `false` → kein Verhaltenswechsel für bestehende Instanzen

---

## Design

### Datenbank

```sql
-- Migration 021
CREATE TABLE system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO system_settings VALUES
    ('vacation_approval_required', 'false', 'Urlaubsantraege erfordern Admin-Genehmigung', now());

-- Migration 022
CREATE TABLE vacation_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    date DATE NOT NULL,
    end_date DATE,
    hours NUMERIC(5,2) NOT NULL,
    note TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|withdrawn
    rejection_reason TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_vacation_requests_user_id ON vacation_requests(user_id);
CREATE INDEX ix_vacation_requests_status  ON vacation_requests(status);
CREATE INDEX ix_vacation_requests_date    ON vacation_requests(date);
```

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/settings` | — | Öffentlich: `{vacation_approval_required: bool}` |
| `POST` | `/api/vacation-requests/` | Employee | Urlaubsantrag stellen |
| `GET` | `/api/vacation-requests/` | Employee | Eigene Anträge (?year, ?status) |
| `DELETE` | `/api/vacation-requests/{id}` | Employee | Antrag zurückziehen (nur pending) |
| `GET` | `/api/admin/vacation-requests` | Admin | Alle Anträge (?status, ?user_id) |
| `POST` | `/api/admin/vacation-requests/{id}/review` | Admin | Genehmigen/Ablehnen |
| `GET` | `/api/admin/settings` | Admin | Alle system_settings |
| `PUT` | `/api/admin/settings/{key}` | Admin | Einstellung aktualisieren |

**Betroffene Dateien:**
- `backend/app/models/vacation_request.py` – `VacationRequest`, `VacationRequestStatus`
- `backend/app/models/system_setting.py` – `SystemSetting`
- `backend/app/schemas/vacation_request.py` – Create/Review/Response
- `backend/app/routers/vacation_requests.py` – Mitarbeiter-Endpunkte
- `backend/app/routers/admin.py` – Admin-Endpunkte (vacation-requests + settings)
- `backend/app/main.py` – `/api/settings` + Router-Registrierung

**Approve-Logik** (identisch mit `create_absence()`):
1. Werktage im Zeitraum bestimmen (Feiertage via `PublicHoliday` ausschließen)
2. Auf doppelte vacation-Einträge prüfen
3. Urlaubsbudget prüfen (`calculation_service.get_vacation_account()`)
4. `use_daily_schedule`-Stunden pro Tag berücksichtigen
5. `Absence`-Einträge erstellen, `VacationRequest.status = approved`

### Frontend (React/TypeScript)

**Betroffene Dateien:**
- `frontend/src/pages/admin/VacationApprovals.tsx` – Neue Admin-Seite
- `frontend/src/pages/AbsenceCalendarPage.tsx` – Tab + konditionaler Submit
- `frontend/src/App.tsx` – Route `/admin/vacation-approvals`
- `frontend/src/components/Layout.tsx` – Nav-Eintrag + Icon

**AbsenceCalendarPage – Tab-Logik:**
```tsx
// Beim Laden
const res = await apiClient.get('/settings');
setVacationApprovalRequired(res.data.vacation_approval_required);

// Submit
if (formData.type === 'vacation' && vacationApprovalRequired) {
  await apiClient.post('/vacation-requests', { ... });
  toast.success('Urlaubsantrag gestellt – wartet auf Genehmigung');
  setActiveTab('requests');
} else {
  await apiClient.post('/absences', { ... }); // bisheriges Verhalten
}
```

---

## Tasks

- [x] **T-1**: Migration 021 – system_settings
- [x] **T-2**: Migration 022 – vacation_requests
- [x] **T-3**: Models `vacation_request.py` + `system_setting.py`
- [x] **T-4**: Schema `vacation_request.py`
- [x] **T-5**: Router `vacation_requests.py` (Mitarbeiter-Endpunkte)
- [x] **T-6**: `admin.py` – vacation-requests + settings Endpunkte
- [x] **T-7**: `main.py` – `/api/settings` + Router
- [x] **T-8**: Frontend `VacationApprovals.tsx`
- [x] **T-9**: Frontend `AbsenceCalendarPage.tsx` – Tab + konditionaler Submit
- [x] **T-10**: `App.tsx` + `Layout.tsx` – Route + Navigation
