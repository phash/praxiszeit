# Spec: §18-Ausnahme greift bei manueller Zeiterfassung (Frontend-Fix)

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #141

---

## Überblick

Für leitende Angestellte (`exempt_from_arbzg`, §18 ArbZG) blockiert die client-seitige Pausen-Validierung die manuelle Zeiterfassung trotzdem: bei > 9h wird eine 45-Min-Pause erzwungen. Das Backend respektiert die Ausnahme bereits korrekt — der Fehler liegt rein im Frontend. Grundlage: `feedback/feedback_01.txt`, Punkt 2.

---

## Requirements

### Funktionale Anforderungen

Als **leitender Angestellter (exempt)** möchte ich **Zeiten > 9h ohne erzwungene 45-Min-Pause manuell erfassen können**, damit die **aktivierte §18-Ausnahme auch im Frontend wirkt**.

- [ ] **REQ-1**: Bei `user.exempt_from_arbzg === true` führt die manuelle Zeiterfassung **keine** ArbZG-Pausenprüfung durch (weder 45-Min- noch 30-Min-Regel).
- [ ] **REQ-2**: Für nicht-exempte User bleibt die Validierung unverändert.
- [ ] **REQ-3**: Der Wert `exempt_from_arbzg` ist im Frontend-`User`-Objekt verfügbar.

### Nicht-funktionale Anforderungen

- [ ] Konsistenz: Der Frontend-Check entspricht der Backend-Logik (`exempt` → keine Prüfung).
- [ ] Kein Backend-Change nötig (Feld wird bereits geliefert).

### Out of Scope

- Verhalten nicht-exempter MA bei nicht möglicher Pause → #144.
- Backend-Pausenlogik (bereits korrekt).

---

## Design

### Root-Cause (verifiziert)

Das Backend liefert `exempt_from_arbzg` bereits in **beiden** relevanten Responses:
- `backend/app/schemas/user.py:108` — `UserResponse` (von `GET /auth/me`, `auth.py:314`)
- `backend/app/schemas/user.py:146` — `UserListResponse` (von `POST /auth/login`)

Backend-Pausenprüfung respektiert die Ausnahme auf allen Pfaden (`break_validation_service.py`, aufgerufen mit `if not exempt` in `time_entries.py` und `admin_time_entries.py`). **Reiner Frontend-Fix.**

### Frontend (React/TypeScript)

**Betroffene Dateien:**
- `frontend/src/stores/authStore.ts` — `User`-Interface (Z. 5-28)
- `frontend/src/pages/TimeTracking.tsx` — Validierung (Z. 267-303)

**Änderung 1 — Interface ergänzen:**
```typescript
interface User {
  // ...
  exempt_from_arbzg: boolean;   // §18 ArbZG: leitende Angestellte
}
```

**Änderung 2 — Validierung guarden** (`TimeTracking.tsx:267`):
```typescript
// Client-side break validation (ArbZG §4) — nur für nicht-befreite MA
if (!user?.exempt_from_arbzg) {
    // ... bestehender Block (Z. 267-303) ...
}
```

> Hinweis: `user` kommt aus `useAuthStore()` (in `TimeTracking.tsx` bereits importiert). Nach Login wird das Profil via `/auth/me` gemergt (`authStore.ts:70`), sodass `exempt_from_arbzg` zuverlässig vorhanden ist.

---

## Tasks

### Frontend
- [ ] **T-1**: `exempt_from_arbzg: boolean` ins `User`-Interface (`authStore.ts`).
- [ ] **T-2**: Pausen-Validierungsblock in `TimeTracking.tsx` (267-303) mit `if (!user?.exempt_from_arbzg)` umschließen.

### Tests & Qualität
- [ ] **T-3**: Vitest: exempt-User → keine `break_time`-Fehlermeldung bei >9h ohne Pause; nicht-exempt → weiterhin Fehler.
- [ ] **T-4**: Manueller Test: User mit gesetztem Häkchen (`UserForm.tsx`) erfasst >9h ohne Pause → Speichern gelingt.
- [ ] **T-5**: `npm run build` (tsc) grün.

### Abschluss
- [ ] **T-6**: Spec-Status auf „Done", Commit & Push.

---

## Offene Fragen

_Keine._

---

## Notizen

- Das Häkchen zum Setzen der Ausnahme existiert bereits: `frontend/src/pages/admin/users/UserForm.tsx:287` („ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte)").
- Optionaler Folgecheck: auch andere client-seitige Pausenprüfungen (falls außerhalb `TimeTracking.tsx` dupliziert) auf denselben Guard prüfen.
