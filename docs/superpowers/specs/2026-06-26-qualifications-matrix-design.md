# Einweisungs-/Skill-Matrix — Design-Spec (Issue #305, Milestone 2d)

**Status:** approved 2026-06-26 · **Branch:** `feat/qualifications-matrix`

Erweitert die Schichtplanung (#305) um **Einweisungen**: pro Mitarbeiter, für
welche Arbeitsplätze er qualifiziert ist (z. B. Azubi: Empfang + Backoffice, aber
nicht Springer/Labor). Reine Planungs-Metadaten — **entkoppelt** vom
ArbZG-/Berechnungsmodell. Voraussetzung für die spätere Auto-Generierung.

## Entscheidungen
- **Weiche Warnung** beim Zuweisen eines nicht eingewiesenen MA (kein Hard-Block) —
  konsistent mit der Mindestbesetzungs-Warnung.
- Verwaltung über einen **Matrix-Reiter „Einweisungen"** in `/admin/shift-planning`.
- **MA sehen ihre eigenen** Einweisungen (im Profil).

## Datenmodell — 1 neue Tabelle (additiv)
`workstation_qualifications` (Migration `054`):
| Spalte | Typ | Notes |
|---|---|---|
| id | UUID PK | gen_random_uuid() |
| tenant_id | UUID FK→tenants | NOT NULL, idx, RLS |
| user_id | UUID FK→users | NOT NULL, ON DELETE CASCADE, idx |
| workstation_id | UUID FK→workstations | NOT NULL, ON DELETE CASCADE, idx |
| created_at | timestamptz | func.now() |

Unique `(tenant_id, user_id, workstation_id)` → `uq_tenant_user_workstation`.
RLS-Policy `tenant_isolation` (NOT-NULL-Variante, wie `shift_assignments`).
Model `WorkstationQualification` in `app/models/shift_planning.py` (ORM-Cascade,
kein passive_deletes — SQLite-Tests laufen mit FK aus).

## Backend (Erweiterung, hinter `require_shift_planning_enabled`)
- `GET /qualifications` (admin) → `{ workstations:[{id,name,location_name}], users:[{id,first_name,last_name}], qualifications:[{user_id, workstation_id}] }`. Nur aktive, nicht-versteckte MA.
- `PUT /qualifications/{user_id}` (admin, `body {workstation_ids:[...]}`) → ersetzt die Einweisungen des MA (idempotent, dedup, validiert MA + Arbeitsplätze gegen den Tenant, F-026).
- `GET /me/qualifications` (jeder MA) → `{ workstations:[{id,name,location_name}] }` der eigenen Einweisungen.
- **Service** `shift_planning_service.py`:
  - `qualified_user_ids(db, tenant_id, workstation_id) -> set[UUID]`
  - `is_user_qualified(db, tenant_id, user_id, workstation_id) -> bool`
- **Slot-Serialisierung** (`_slot_dict`): jedes Assignment bekommt zusätzlich
  `qualified: bool` (relativ zum Arbeitsplatz des Slots). Plan-Validierung
  (`validation`) bekommt zusätzlich `unqualified_slot_ids` (Slots mit ≥1 nicht
  eingewiesener Person) — weich, blockiert NICHT Aktivierung. Belastung: 1
  Qualifikations-Query je Plan-Detail (kein N+1).

## Frontend
- **`api/shiftPlanning.ts`:** Typen + `getQualifications()`, `setUserQualifications(userId, wsIds)`, `getMyQualifications()`. `ShiftAssignment` + `qualified?: boolean`; `PlanDetail.validation` + `unqualified_slot_ids`.
- **Neuer Tab „Einweisungen"** in `pages/admin/ShiftPlanning.tsx` → Komponente `components/shiftplanning/QualificationMatrix.tsx`: Raster MA (Zeilen) × Arbeitsplätze (Spalten) mit Checkboxen; Toggle speichert die Zeile via `PUT /qualifications/{user_id}` (optimistisch + Toast). Leerstand-EmptyState wenn keine Arbeitsplätze.
- **`SlotDialog.tsx`:** in der MA-Checkliste Badge „nicht eingewiesen" (gelb) neben MA, die für den gewählten Arbeitsplatz nicht qualifiziert sind (lädt `qualified_user_ids` für den Arbeitsplatz). Rein visuell.
- **`WeekGrid.tsx`:** Slot mit `unqualified` (≥1 nicht eingewiesene Person) bekommt einen dezenten Marker (z. B. gestrichelter Rahmen) — optional/leichtgewichtig.
- **MA-Eigenansicht:** Abschnitt „Meine Einweisungen" in `pages/Profile.tsx` aus `GET /me/qualifications` (nur wenn Schichtplanung aktiv; leer → kurzer Hinweis).

## Decoupling / DSGVO
Reine Planungs-Metadaten; kein Zugriff auf Soll/Ist/Urlaub/Überstunden. Tenant-
scoped (RLS + F-026). Einweisungen sind keine sensiblen Daten (Art. 9) — die
MA-Eigenansicht zeigt nur die eigenen.

## Tests
- **Backend** (`test_qualifications.py`): CRUD (`PUT` set/replace/dedup), `GET /qualifications` Matrix-Shape, `GET /me/qualifications`, `qualified`-Flag in Slot-Detail + `unqualified_slot_ids`, Flag-Gating (404 aus), Cross-Tenant (eigene Datei oder im bestehenden Cross-Tenant-Stil), Unknown-User/-Workstation → 404.
- **Vitest:** QualificationMatrix-Toggle + die `qualified`-Badge-Logik.
- **E2E:** Einweisungen-Tab → MA einweisen; im SlotDialog einen nicht eingewiesenen MA wählen → Badge sichtbar; Read-only bleibt unberührt.
- Volle Backend-Suite grün; tsc/build/eslint/vitest grün.

## Doku
`docs/SCHICHTPLANUNG.md` (Abschnitt Einweisungen), In-App-Hilfe (`DocViewer.tsx`
Admin + MA), Handbücher (Admin: Matrix; MA: „Meine Einweisungen"), CLAUDE.md-Regel
(Einweisungen = Teil der Schichtplanung, weiche Warnung, eigene RLS-Tabelle).

## Migration & Release
Migration `054_add_workstation_qualifications` (1 Tabelle + RLS, dem 053-Muster
folgend). Additiv, keine Backfills. Wird mit dem nächsten Release ausgeliefert.
