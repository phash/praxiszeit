# Schichtplanung — Design-Spec (Issue #305)

**Status:** approved 2026-06-25 · **Branch:** `feat/305-shift-planning`
**Autor des Wunsches:** Dr. Philip von der Borch (#305) · **Umsetzung:** Manuel/Claude

---

## 1. Ziel & Scope

Schichtplanung als **reines Planungs-Artefakt**: Admins definieren Wochenpläne,
die festlegen *wer wann an welchem Arbeitsplatz* steht. Die Funktion ist
**entkoppelt** von der Zeiterfassung — sie berührt **nicht** Soll/Ist-Stunden,
ArbZG-Validierung, Urlaubs- oder Überstundenkonten. Kein Eingriff ins
Berechnungsmodell.

### In Scope (dieser Durchlauf)
- Milestone 1 komplett:
  - Beliebig viele **Schicht-Wochenpläne** (Name + optionale Beschreibung).
  - **Standorte** (eigene CRUD-Entität) und **Arbeitsplätze** (optional einem
    Standort zugeordnet, sonst global).
  - **Zeitslots** je Plan: Arbeitsplatz × Wochentag × Start–Ende, mit
    optionaler **Mindestbesetzung**.
  - **Mitarbeiter-Zuweisung** zu Slots (mehrere MA pro Slot möglich).
  - **Validierung** der Mindestbesetzung (weiche Warnung, kein Hard-Block).
  - Schichtpläne **bearbeitbar für Admins**, **einsehbar (read-only) für alle**.
  - **Grafischer Drag-&-Drop-Wochen-Editor** (mit zusätzlichem Dialog-/Button-Pfad).
- Einfache Milestone-2-Teile:
  - **Aktivschaltung** eines Plans (`is_active`-Flag; **mehrere aktiv erlaubt**).
  - **Dashboard-Anzeige** der heutigen Einteilung des eingeloggten Users.
- **Feature-Flag** `shift_planning_enabled` (Default **OFF**), per Admin-UI
  schaltbar, mit Hinweisen in Doku/Handbüchern/Website.

### Out of Scope (Milestone 2, später, eigene Issues)
- Automatisches Aktivwerden ab bestimmter KW / Ganzjahresansicht.
- Skill-/Einweisungs-Matrix je Mitarbeiter (kann Arbeitsplatz X, Y nicht Z).
- Automatische Schichtplan-Generierung (Solver mit Fähigkeiten, Stunden,
  Überstunden, Urlaub, Krankheit).

---

## 2. Feature-Flag & Gating (Default OFF)

- Neuer Tenant-Setting-Key `shift_planning_enabled` in `system_settings`
  (Default `"false"`). Kein Eintrag = aus.
- **Drei Sync-Stellen** (wie `onboarding_enabled`):
  1. `admin_settings.py`: in `_ALLOWED_SETTINGS` **und** `_BOOL_SETTINGS`
     aufnehmen → PUT `/api/admin/settings` akzeptiert das Toggle.
  2. `main.py::system_info()`: Wert (Default-Tenant) in die `/api/system/info`-
     Antwort als `shift_planning_enabled` (Lesefehler → `false`, niemals 500).
  3. `frontend/src/stores/systemStore.ts`: Feld + `isShiftPlanningEnabled()`
     (Default **false** solange nicht geladen / Feld fehlt → konservativ aus,
     analog `isBeta`).
- **Backend-Guard:** Dependency `require_shift_planning_enabled(db, current_user)`
  liest `settings_service.get_bool_setting(db, "shift_planning_enabled",
  tenant_id=current_user.tenant_id)`. Wenn aus → **HTTP 404** (Feature existiert
  „nicht"). Auf **allen** Schicht-Endpoints als Router-Dependency. Das Toggle in
  `admin_settings` bleibt unabhängig erreichbar.
- **Frontend:** Nav-Einträge (Admin-Editor + User-Read-only), Routen und das
  Dashboard-Widget rendern nur, wenn `isShiftPlanningEnabled()` true ist. Routen
  selbst zusätzlich serverseitig durch den Guard geschützt (Defense in depth).

---

## 3. Datenmodell

Fünf neue Tabellen, **alle** mit `tenant_id` (FK→tenants, NOT NULL, indiziert)
und RLS-Policy `tenant_isolation` nach dem Muster aus Migration 027
(`_NOT_NULL_TABLES`). Migration: **`053_add_shift_planning`**,
`down_revision = '052_add_absence_half_day'`.

### 3.1 `locations` (Standorte)
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| tenant_id | UUID FK→tenants | NOT NULL, idx |
| name | String(255) | NOT NULL |
| sort_order | Integer | NOT NULL, default 0 |
| created_at / updated_at | timestamptz | func.now() |

Unique `(tenant_id, name)` → `uq_tenant_location_name`.

### 3.2 `workstations` (Arbeitsplätze)
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | NOT NULL, idx |
| location_id | UUID FK→locations | **nullable** (= global) |
| name | String(255) | NOT NULL |
| color | String(7) | nullable, Hex `#RRGGBB` für Grid |
| sort_order | Integer | NOT NULL, default 0 |
| created_at / updated_at | timestamptz | |

Unique `(tenant_id, name)` → `uq_tenant_workstation_name`.
`location_id` FK **ON DELETE RESTRICT** (Löschen eines Standorts mit
Arbeitsplätzen → 409 im Router, sauberer Fehler statt DB-Error).

### 3.3 `shift_plans` (Schicht-Wochenpläne)
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | NOT NULL, idx |
| name | String(255) | NOT NULL |
| description | Text | nullable |
| is_active | Boolean | NOT NULL, default false (**mehrere aktiv erlaubt**) |
| created_by | UUID FK→users | NOT NULL |
| created_at / updated_at | timestamptz | |

Unique `(tenant_id, name)` → `uq_tenant_shift_plan_name`.

### 3.4 `shift_slots` (Zeitslots)
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | NOT NULL, idx |
| shift_plan_id | UUID FK→shift_plans | NOT NULL, **ON DELETE CASCADE** |
| workstation_id | UUID FK→workstations | NOT NULL, **ON DELETE RESTRICT** |
| weekday | SmallInteger | NOT NULL, 0=Montag … 6=Sonntag (`date.weekday()`) |
| start_time | Time | NOT NULL |
| end_time | Time | NOT NULL, muss > start_time |
| min_staff | SmallInteger | NOT NULL, default 0 |
| created_at / updated_at | timestamptz | |

Index `(tenant_id, shift_plan_id, weekday)`. `workstation_id`
ON DELETE RESTRICT → Löschen eines in Slots benutzten Arbeitsplatzes → 409.

### 3.5 `shift_assignments` (MA-Zuweisung)
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | NOT NULL, idx |
| shift_slot_id | UUID FK→shift_slots | NOT NULL, **ON DELETE CASCADE** |
| user_id | UUID FK→users | NOT NULL, **ON DELETE CASCADE** |
| created_at | timestamptz | |

Unique `(tenant_id, shift_slot_id, user_id)` → kein Doppel; mehrere MA/Slot ok.
Löschen eines Users entfernt seine Zuweisungen (kein verwaister Plan-Eintrag).

> **RLS-Hinweis:** Neue `SessionLocal()`-Sessions außerhalb des Request-Flows
> brauchen `set_tenant_context`/`set_superadmin_context` (CLAUDE.md). Alle
> Router laufen im Request-Kontext → Middleware setzt RLS. F-026: zusätzlich in
> **jeder** Query expliziter `Model.tenant_id == current_user.tenant_id`-Filter
> (list, by-id, delete).

---

## 4. Backend-API

Neuer Router `app/routers/shift_planning.py`,
`prefix="/api/shift-planning"`, **Router-Dependency**
`require_shift_planning_enabled` (404 wenn Flag aus). Schreib-Endpoints
zusätzlich `require_admin`; Lese-Endpoints `get_current_user`.
Validierungs-/Status-Logik in `app/services/shift_planning_service.py`.
Pydantic-Schemas mit `float`/`str`-Feldern (kein Decimal); Zeiten als
`"HH:MM"`-Strings.

| Methode & Pfad | Auth | Zweck |
|---|---|---|
| GET `/locations` | user | Standorte (sortiert) |
| POST `/locations` | admin | anlegen |
| PUT `/locations/{id}` | admin | umbenennen/sortieren |
| DELETE `/locations/{id}` | admin | 409 wenn Arbeitsplätze daran hängen |
| GET `/workstations` | user | Arbeitsplätze (+ Standortname) |
| POST `/workstations` | admin | anlegen |
| PUT `/workstations/{id}` | admin | ändern |
| DELETE `/workstations/{id}` | admin | 409 wenn in Slots benutzt |
| GET `/plans` | user | Plan-Liste (id, name, is_active, #Slots, Status) |
| GET `/plans/{id}` | user | voller Plan: Slots + Assignments + Validierung |
| POST `/plans` | admin | Plan anlegen |
| PUT `/plans/{id}` | admin | Name/Beschreibung |
| DELETE `/plans/{id}` | admin | Plan + Slots + Assignments (Cascade) |
| POST `/plans/{id}/activate` | admin | `is_active=true` |
| POST `/plans/{id}/deactivate` | admin | `is_active=false` |
| POST `/plans/{id}/slots` | admin | Slot anlegen (weekday/start/end/ws/min) |
| PUT `/slots/{id}` | admin | Slot ändern (Move/Resize aus dem Editor) |
| DELETE `/slots/{id}` | admin | Slot + Assignments (Cascade) |
| PUT `/slots/{id}/assignments` | admin | MA-Liste eines Slots setzen (idempotent) |
| GET `/my-today` | user | eigene Einteilung **heute** über **alle aktiven Pläne** |

**`my-today`-Auflösung:** Wochentag via `timezone_service`/`now_local()`
(Europe/Berlin, nicht Container-UTC — vgl. CLAUDE.md Mitternachts-Flakes).
Liefert pro aktivem Plan die Slots des heutigen Wochentags, in denen der
eingeloggte User zugewiesen ist (Union über alle aktiven Pläne), mit
Planname, Arbeitsplatz (+Standort) und Zeit.

**Validierungs-Status** (`shift_planning_service`):
- Pro Slot: `understaffed = assignment_count < min_staff` (nur wenn `min_staff>0`).
- Pro Plan: `is_valid = keine understaffed Slots`; Liste der Verstöße.
- **Weich**: blockiert weder Speichern noch Aktivieren; nur Statusfeld + Badge.
- Slot-Constraint hart: `end_time > start_time` → sonst 400.

---

## 5. Frontend

### 5.1 Stores & API
- `systemStore`: `shift_planning_enabled` + `isShiftPlanningEnabled()`.
- Neuer `shiftPlanningStore` (Zustand) für aktuell editierten Plan + Caches,
  oder schlanke API-Helper in `api/shiftPlanning.ts`. (Implementierung wählt das
  einfachere; Tests gegen die API-Helper.)

### 5.2 Routen & Navigation (nur wenn Flag an)
- `App.tsx`: lazy-Route `/admin/shift-planning` (Admin-Editor) und
  `/shift-planning` (User-Read-only). Beide unter den bestehenden
  Protected-Wrappern.
- `Layout.tsx`: Nav-Eintrag „Schichtplan" (User, read-only) und
  „Schichtplanung" (Admin) — nur gerendert wenn `isShiftPlanningEnabled()`.

### 5.3 Admin-Editor (`/admin/shift-planning`)
- **Plan-Verwaltung:** Liste, anlegen, umbenennen, löschen, aktiv/inaktiv
  schalten, Validierungs-Badge.
- **Stammdaten-Tabs:** Standorte (CRUD) und Arbeitsplätze (CRUD, Standort +
  Farbe).
- **Wochen-Editor (Drag & Drop):** Zeitachse (vertikal, z. B. 6–22 Uhr) ×
  Wochentage (Mo–So, horizontal). Slots als farbige Blöcke (Farbe vom
  Arbeitsplatz). Interaktionen:
  - Block **verschieben** (Wochentag/Zeit) und **resizen** (Start/Ende) → `PUT /slots/{id}`.
  - **Mitarbeiter** aus einer Seitenliste per Drag auf einen Block → Assignment.
  - **Neuer Slot** per Klick/Doppelklick auf leere Rasterfläche.
  - Unterbesetzte Slots visuell markiert.
- **Design-Vorgabe (Testbarkeit/A11y/Mobil):** Jede Mutation ist **zusätzlich**
  über einen Klick→**Dialog/Buttons**-Pfad erreichbar (gleiche API-Calls). D&D
  ist Komfort-Layer; der Dialog-Pfad ist der robuste, E2E-getestete Pfad.
  Bibliothek: **`@dnd-kit/core`** (accessible, Keyboard-Support); Resize via
  Pointer-Handler. Dep-Bump beachtet die `npm ci`/Lock-Regeln aus CLAUDE.md.

### 5.4 User-Read-only (`/shift-planning`)
- Aktive Pläne als Wochenraster (gleiche Grid-Darstellung, nicht editierbar).
- Wenn kein aktiver Plan → freundlicher EmptyState.

### 5.5 Dashboard-Widget
- In `Dashboard.tsx`: Karte „Deine Einteilung heute" aus `GET /my-today`.
- Zeigt Arbeitsplatz (+Standort), Zeit, Planname. Mehrere Einträge möglich.
- Ausgeblendet wenn Flag aus **oder** keine Einteilung.

---

## 6. Doku / Handbücher / Website

- **In-App-Hilfe** `frontend/src/components/DocViewer.tsx`: neue Sektionen in
  `handbuchAdminSections` **und** `handbuchMitarbeiterSections` (hardcoded, vgl.
  CLAUDE.md — beides pflegen).
- **Handbücher** `docs/handbuch/HANDBUCH-ADMIN.md`, `HANDBUCH-MITARBEITER.md`,
  `CHEATSHEET-ADMIN.md`, `CHEATSHEET-MITARBEITER.md`.
- **Feature-Doku** neu: `docs/SCHICHTPLANUNG.md` + Link in `CLAUDE.md`-Doc-Tabelle
  und eine kritische Regel zum 3-Stellen-Flag.
- **Admin-Settings-Toggle** trägt den Erklär-Hinweis „Default deaktiviert".
- **Website = `pzweb` (separates Repo):** Text/Abschnitt wird hier als Vorlage
  abgelegt (`docs/SCHICHTPLANUNG.md` Abschnitt „Website-Text"); die eigentliche
  Webseiten-Änderung ist ein **separater Schritt im pzweb-Repo** (anderer
  Release-Zyklus) und wird Manuel explizit als TODO übergeben — **nicht**
  stillschweigend in diesem Repo erledigt.

---

## 7. Tests

- **Backend pytest** (`backend/tests/test_shift_planning.py`):
  - CRUD locations/workstations/plans/slots/assignments.
  - **Flag-Gating:** Endpoints liefern 404 wenn `shift_planning_enabled` aus,
    funktionieren wenn an.
  - **Tenant-Isolation** (cross-tenant, `test_cross_tenant_api.py`-Stil): kein
    Zugriff/Leak über Tenant-Grenzen.
  - Validierung: Mindestbesetzung-Status, `end>start`-Guard.
  - `my-today`-Auflösung inkl. „mehrere aktive Pläne".
  - DELETE-409 bei benutztem Arbeitsplatz/Standort; Cascade bei Plan/Slot.
- **Vitest:** API-Helper/Store + Editor-Dialog-Komponente (Dialog-Pfad).
- **E2E Playwright:** Flag an → Editor sichtbar; Plan/Slot/Assignment **über
  Dialog-Pfad**; Read-only-Sicht; Dashboard-Widget. Fixtures mit Teardown-DELETE
  (Muster `test-data.fixture.ts`). Erhöhte Auth-Rate-Limits beachten.

---

## 8. Migration & Release

- Eine Migration `053_add_shift_planning`: 5 `create_table` + Indizes + Unique
  Constraints + `ENABLE/FORCE ROW LEVEL SECURITY` + Policy `tenant_isolation`
  (NOT-NULL-`tenant_id`-Variante). `downgrade` droppt in umgekehrter Reihenfolge.
- Keine Backfills (Flag default off, keine Bestandsdaten betroffen).
- Kein Eingriff ins Berechnungs-/ArbZG-Modell → risikoarm. Versions-Bump erfolgt
  separat beim Release (`/buildrelease`), nicht Teil dieses Feature-PRs.

---

## 9. Bewusst gewählte Defaults (überstimmbar)

- **(a) Mindestbesetzung = weiche Warnung** (kein Hard-Block) — sonst lassen sich
  unfertige Pläne nicht zwischenspeichern.
- **(b) Dashboard = eigene Einteilung des Users** (Union über alle aktiven
  Pläne), statt eines Standort-Auflösungs-Mechanismus — eindeutig auch bei
  „mehrere aktiv".
- **(c) D&D + zusätzlicher Dialog-Pfad** — D&D allein ist in E2E fragil und
  schlecht a11y/mobil; der Dialog-Pfad sichert Testbarkeit & Barrierefreiheit.
