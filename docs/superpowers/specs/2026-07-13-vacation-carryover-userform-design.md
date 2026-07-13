# Design: „Übertrag Urlaubstage" im UserForm (#383)

**Datum:** 2026-07-13
**Issue:** [#383](https://github.com/phash/praxiszeit/issues/383) — „Neben ‚Anfangssaldo Überstunden' auch ‚Übertrag Urlaubstage'"
**Typ:** Feature (klein, fast reiner Frontend-Change)

## Problem

Beim Wechsel auf PraxisZeit werden Mitarbeitende oft „zum Stichtag eingestellt"
(Kundenfall: `first_work_day = 1.6.2026`). `get_vacation_account` rechnet den
Jahresanspruch dann **anteilig** für die Beschäftigungsmonate (Jun–Dez = 7/12).
Resturlaub aus dem laufenden Jahr **vor** dem Stichtag (Jan–Mai) oder aus dem
Vorjahr geht so verloren — der Admin kann ihn nicht bequem nachtragen.

Für **Überstunden** existiert dafür das Feld **„Anfangssaldo Überstunden"** in den
Mitarbeitereigenschaften (UserForm). Ein **gleichwertiges Feld für Urlaubstage**
fehlt an dieser Stelle. Vacation-Carryover ist heute nur über den separaten
`CarryoverModal` (pro Jahr) setzbar — der Kunde wünscht es **neben** dem
Überstunden-Feld im UserForm.

## Bestehende Mechanik (Ausgangslage)

Das Backend unterstützt Urlaubs-Carryover bereits vollständig:

- **`YearCarryover`** (pro `(tenant_id, user_id, year)`) trägt `overtime_hours`
  **und** `vacation_days`, plus `source` (`manual` | `year_closing`, Migration
  058/Fix #7 — `manual` überlebt das Rückgängigmachen eines Jahresabschlusses).
- **`upsert_carryover`** (`PUT /admin/users/{id}/carryovers/{year}`,
  `admin_carryovers.py`) setzt beide Felder, `source=manual`.
- **`get_vacation_account`** (`calculation_service.py`) addiert
  `carryover.vacation_days` des Jahres auf das (ggf. anteilige) Budget.

Das UserForm-Feld **„Anfangssaldo Überstunden"** (`overtime_carryover`) ist
**kein** User-Feld:

- **State:** `overtime_carryover: 0` (UserForm-lokal).
- **Startjahr:** `first_work_day.year`, Fallback aktuelles Jahr
  (`new Date().getFullYear()`).
- **Prefill (Edit):** lädt die Carryover-Liste, findet die Startjahr-Zeile, setzt
  `overtime_carryover = row.overtime_hours`, `hadCarryover = true`.
- **Save (`writeCarryover`):** re-fetcht die Startjahr-Zeile, um `vacation_days`
  **zu erhalten**, und schreibt `PUT /carryovers/{startYear}` mit
  `{ overtime_hours: overtime_carryover, vacation_days: <erhalten> }`.
- **Schreib-Gate:** nur wenn `overtime_carryover !== 0 || hadCarryover`
  (verhindert leere 0/0-Zeilen für unberührte User).

## Lösung

Ein **paralleles Feld „Übertrag Urlaubstage"** im UserForm, das
`YearCarryover.vacation_days` desselben Startjahres schreibt — exakt gespiegelt
zum Überstunden-Feld.

### Frontend (`frontend/src/pages/admin/users/UserForm.tsx`) — der gesamte Change

1. **State:** neu `vacation_carryover: 0` neben `overtime_carryover` (im
   `formData`-Init und im Reset-Pfad).
2. **Prefill (Edit):** im bestehenden Carryover-`useEffect` zusätzlich
   `vacation_carryover = row.vacation_days` aus derselben Startjahr-Zeile setzen.
3. **Save (`writeCarryover`):** schreibt **beide** Werte aus dem Formular:
   `PUT /carryovers/{startYear}` mit
   `{ overtime_hours: overtime_carryover, vacation_days: vacation_carryover }`.
   Die bisherige „`vacation_days` per Re-Fetch erhalten"-Logik **entfällt** — das
   UserForm ist jetzt die Autorität für den Startjahr-Carryover (beide Felder).
   `vacation_carryover` wird — wie `overtime_carryover` — via Destructuring aus
   dem User-Payload ausgeschlossen (kein User-Feld).
4. **Schreib-Gate:** erweitert auf
   `overtime_carryover !== 0 || vacation_carryover !== 0 || hadCarryover`
   (create-Pfad analog: schreiben, wenn einer der beiden ≠ 0).
5. **Render:** zweites Number-Input **„Übertrag Urlaubstage"** direkt neben
   „Anfangssaldo Überstunden":
   - `type="number"`, `step="0.5"`, **kein `min`** (negativ erlaubt),
     `onChange` via `parseFloat(e.target.value) || 0`.
   - Hilfetext: „Alt-/Vorjahres-Resturlaub, der dem Urlaubsbudget des Startjahres
     ({startYear}) zugerechnet wird. Minus und Kommastellen möglich."

### Backend

**Keine Änderung.** `upsert_carryover` akzeptiert `vacation_days` bereits,
`get_vacation_account` addiert es aufs Budget, `source=manual` bleibt.
**Keine Migration.**

### Semantik / Randfälle

- **Jahr-Bindung:** identisch zum Überstunden-Feld — Startjahr
  (`first_work_day.year`, sonst aktuelles Jahr). Deckt den Kundenfall (Eintritt
  1.6., Jan–Mai-Resturlaub) exakt ab.
- **Negativ/Kommastellen:** ausdrücklich erlaubt (Kundenwunsch); `parseFloat`,
  Backend-Schema akzeptiert Float. Keine Ober-/Untergrenze.
- **CarryoverModal-Overlap:** `CarryoverModal` bleibt für Nicht-Startjahre /
  Power-User. Der Startjahr-Overlap besteht **schon heute** für Überstunden; das
  UserForm prefillt beim Öffnen frisch aus der DB, daher kein Datenverlust,
  solange nicht beide UIs gleichzeitig offen sind. Neu ist lediglich, dass das
  UserForm nun auch `vacation_days` des Startjahres **überschreibt** statt es zu
  erhalten — gewollt, da das Feld genau dieses Wertes Herr wird.
- **DSGVO / §16:** unberührt — Carryover ist bereits ein bestehendes,
  admin-gesetztes Feld; keine neuen Daten.

## Tests (Vitest, `UserForm.test.tsx`)

1. Feld **rendert** (Label „Übertrag Urlaubstage") und **prefillt** aus der
   Startjahr-`vacation_days` beim Edit.
2. **Save** schickt `vacation_days` (aus dem Feld) an
   `PUT /admin/users/{id}/carryovers/{startYear}` (zusammen mit `overtime_hours`).
3. **Startjahr-Fallback**: ohne `first_work_day` bindet der Save aufs aktuelle
   Jahr.
4. **Gate**: unberührtes Feld (0/0, kein bestehender Carryover) schreibt **keine**
   Carryover-Zeile.

## Bewusst NICHT dabei (YAGNI)

- Kein Jahr-Dropdown im UserForm (Nicht-Startjahre → CarryoverModal).
- Kein neues User-DB-Feld, keine Migration.
- Keine Änderung an `get_vacation_account`, Export, Journal.

## Betroffene Dateien

- `frontend/src/pages/admin/users/UserForm.tsx` (Feld + State + Prefill + Save).
- `frontend/src/pages/admin/users/UserForm.test.tsx` (Tests).
- Ggf. gemeinsamer Handbuch-Hinweis (`docs/handbuch/HANDBUCH-ADMIN.md` +
  `DocViewer.tsx`) an der Stelle, die „Anfangssaldo Überstunden" erklärt — beide
  synchron.
