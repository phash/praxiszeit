# Schichtplanung M2: KW-Planung + Auto-Generierung — Design-Spec (#305)

**Status:** approved 2026-06-26 · **Branch:** `feat/m2-scheduling-autogen`

Zwei Milestone-2-Erweiterungen der Schichtplanung. Beide **entkoppelt** vom
ArbZG-/Berechnungsmodell (nur **lesender** Zugriff), tenant-scoped (RLS + F-026),
hinter dem Feature-Flag.

---

## A) KW-/Ganzjahres-Planung (Datums-Fenster je Plan) — Aufwand M

**Datenmodell:** `shift_plans` + `active_from_date` (Date, nullable) +
`active_until_date` (Date, nullable). Migration `055_add_shift_plan_schedule`.
Additiv, kein Backfill.

**„Aktiv heute"-Auflösung** (in `shift_planning_service`):
Ein Plan zählt für ein Datum `d` als aktiv, wenn
`is_active == true` **ODER** (`active_from_date` ist NULL oder `<= d`) **UND**
(`active_until_date` ist NULL oder `>= d`) — wobei das Datums-Fenster nur greift,
wenn mindestens eine der beiden Datumsgrenzen gesetzt ist (sonst wäre jeder
nicht-aktive Plan dauerhaft aktiv). Präzise:
`active = is_active OR (has_window AND from<=d<=until)`.
`is_active` bleibt der manuelle „immer an"-Override. `get_my_today` filtert
darüber (Datum via `today_local()`).

**API:** `PUT /plans/{id}` nimmt zusätzlich `active_from_date`/`active_until_date`
(ISO-Date-Strings oder null) entgegen; `_plan_summary`/Detail geben sie zurück.
Validierung: `from <= until` (400 sonst).

**Frontend:** im Plan-Editor zwei Datumsfelder „aktiv von/bis" (optional) + ein
kompakter **Jahres-Zeitstrahl** (read-only) über `components/shiftplanning/YearTimeline.tsx`,
der je ISO-KW zeigt, welche Pläne laufen (Plan-Farbe/Name). ISO-Wochen via
`date-fns` (`getISOWeek`, `startOfISOWeek`). `api/shiftPlanning.ts`-Typen +
`PlanSummary/PlanDetail.active_from_date?/active_until_date?`.

---

## B) Auto-Generierung (Greedy, zielwochen-bewusst) — Aufwand L

**Kein neues Datenmodell.** Der Generator füllt die (wochentagsbasierten) Slots
eines bestehenden Plans mit Zuweisungen; der Admin reviewt/editiert danach. Der
Plan wird **nicht** automatisch aktiv.

**API:** `POST /plans/{id}/generate` (admin), Body:
`{ target_monday: "YYYY-MM-DD", mode: "replace" | "fill_gaps" }`.
`target_monday` = Montag der Zielwoche (das Frontend liefert es; Validierung: ist
ein Montag, sonst auf den Wochenanfang normalisiert). Antwort = das aktualisierte
Plan-Detail (wie `GET /plans/{id}`) **plus** `generation: { filled, unfilled_slot_ids,
skipped_no_candidate }` für die UI-Rückmeldung.

**Service** `app/services/shift_planning_generator.py` (eigene, testbare Datei):
Für jeden Slot (Wochentag → konkretes Datum = `target_monday + weekday`):
- **Zielbesetzung** je Slot = `max(1, min_staff)`.
- **`mode=fill_gaps`:** vorhandene Zuweisungen bleiben, nur bis zur Zielbesetzung auffüllen.
  **`mode=replace`:** alle Zuweisungen des Plans werden vorab entfernt, komplett neu gefüllt.
- **Harte Constraints** je Kandidat:
  - **Qualifiziert** für den Arbeitsplatz des Slots (Skill-Matrix `workstation_qualifications`).
  - **Nicht abwesend** am Slot-Datum (`Absence` mit `date<=d<=COALESCE(end_date,date)`, ganztägig; read-only).
  - **Nicht doppelt belegt**: nicht bereits einem zeitlich **überlappenden** Slot in diesem Plan zugewiesen.
  - Aktiv + `_within_employment_window` (kein MA außerhalb Eintritt/Austritt).
- **Weiche Reihenfolge** (welche qualifizierten/verfügbaren MA zuerst):
  1. wenigste **bisher in diesem Lauf zugeteilte Minuten** (Last-Balance),
  2. geringere **Auslastung** = zugeteilte Minuten ÷ (`weekly_hours`·60),
  3. niedrigeres **Überstundenkonto** (`calculation_service.get_overtime_account`, read-only),
  4. stabiler Tie-Break per `user_id`.
- Slots ohne genug Kandidaten → in `unfilled_slot_ids`; der Slot bleibt unter-/unbesetzt.

**Decoupling:** liest `Absence`, `weekly_hours`, `get_overtime_account`,
`_within_employment_window` — schreibt ausschließlich `shift_assignments`.
Keine Mutation am Berechnungs-/ArbZG-Modell.

**Frontend:** Button „Automatisch füllen" im Plan-Editor → `GenerateDialog.tsx`
(Zielwoche-Datepicker [Montag], Modus replace/fill_gaps) → nach Erfolg Plan neu
laden + Toast „X Slots besetzt, Y unbesetzt"; unbesetzte Slots werden im
Wochenraster bereits über `understaffed`/`min_staff` markiert.

---

## Tests
- **Backend** (`test_shift_plan_schedule.py`): Datums-Fenster-Auflösung in `my-today`
  (innerhalb/außerhalb Fenster, NULL-Grenzen, Jahresgrenze), PUT-Validierung from<=until.
- **Backend** (`test_shift_plan_generator.py`): Generator-Logik — Qualifikation hart,
  Abwesenheit am Zieldatum schließt aus, keine Doppelbelegung überlappender Slots,
  Last-Balance verteilt gleichmäßig, `replace` vs `fill_gaps`, `unfilled_slot_ids`
  bei zu wenig Kandidaten, `max(1,min_staff)`-Zielbesetzung. Plus Endpoint-Test
  (admin-only 403/Flag-404) + Cross-Tenant.
- **Vitest:** YearTimeline-Berechnung (KW→Plan-Mapping) + GenerateDialog.
- **E2E:** Plan mit Datumsfenster + „Automatisch füllen" über den Dialog.
- Volle Backend-Suite grün; tsc/build/eslint/vitest grün; Migration `055` auf
  echtem Postgres verifiziert.

## Doku
`docs/SCHICHTPLANUNG.md` (KW-Planung + Auto-Generierung), In-App-Hilfe + Handbücher,
CLAUDE.md-Regel.

## Reihenfolge
1. KW-Planung (A) komplett (Migration 055 + Auflösung + UI + Tests).
2. Auto-Generierung (B) komplett (Generator-Service + Endpoint + UI + Tests).
3. Integrations- + Security-Review (Workflow), Fixes ≤ medium.
