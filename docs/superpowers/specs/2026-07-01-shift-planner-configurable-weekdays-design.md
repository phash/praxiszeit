# Design: Konfigurierbare Wochentage im Schichtplaner (#371)

**Datum:** 2026-07-01
**Issue:** [#371](https://github.com/phash/praxiszeit/issues/371)
**Status:** freigegeben, Umsetzung offen

## Problem

Die Wochenansicht des Schichtplaners zeigt hart Mo–So. Für >95 % der Zielgruppe
(Arztpraxen) sind Sa/So irrelevant; Teilzeitpraxen haben ggf. einzelne Wochentage
geschlossen (z. B. Do). Gewünscht: pro Tenant konfigurierbare Wochentage, Default
Mo–Fr, jeder Wochentag einzeln zu-/abschaltbar.

**Entscheidung (User):** Die Konfiguration wirkt auf die **gesamte Planungsfläche**
— ein deaktivierter Tag verschwindet aus der Wochenansicht UND wird von
Slot-Anlage und Auto-Generierung ausgeschlossen. Er „existiert" für die Planung
nicht.

## Speicherung

- Neues Tenant-Setting `shift_planning_weekdays` in der bestehenden Key-Value-Tabelle
  `SystemSetting` (pro Tenant).
- Wert = kommaseparierte Wochentag-Indizes in der **App-Konvention `0=Montag … 6=Sonntag`**
  (identisch zu `ShiftSlot.weekday` und `WeekGrid`). Beispiel Mo–Fr: `"0,1,2,3,4"`.
- **Default wenn ungesetzt:** `"0,1,2,3,4"` (Mo–Fr). Der Default wird an genau einer
  Stelle als Konstante gehalten (`shift_planning_service.DEFAULT_WEEKDAYS = [0,1,2,3,4]`)
  und von Backend-Lesern + system_info genutzt.

## Backend

### admin_settings.py
- `shift_planning_weekdays` in `_ALLOWED_SETTINGS` aufnehmen (NICHT `_BOOL_SETTINGS`).
- Eigener Validator im generischen `PUT /settings/{key}`:
  - Wert wird als CSV geparst; jeder Eintrag muss int in `0..6` sein.
  - Mindestens 1 Tag; keine Duplikate.
  - Normalisiert gespeichert: sortiert, dedupliziert, als `"0,1,2,3,4"`.
  - Ungültig → `400` mit klarer Meldung.

### shift_planning_service.py
- `DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4]`.
- Helper `get_planning_weekdays(db, tenant_id) -> list[int]`: liest das Setting,
  parst es, fällt auf `DEFAULT_WEEKDAYS` zurück wenn ungesetzt/leer/kaputt.
- Helper `is_weekday_enabled(db, tenant_id, weekday) -> bool`.

### shift_planning.py (Slot-Endpoints)
- `POST /workstations/{id}/slots` (create) und der Slot-`PUT` (update): wenn
  `weekday ∉ get_planning_weekdays(...)` → `400`
  („Wochentag ist im Schichtplaner deaktiviert").
- `POST /plans/{id}/duplicate`: dupliziert weiterhin alle Quell-Slots (kein Filter —
  Duplikat soll 1:1 sein; deaktivierte Tage rendern/generieren einfach nicht).

### shift_planning_generator.py
- Beim Iterieren der Plan-Slots die auf einem deaktivierten Wochentag liegenden
  Slots **überspringen** (kein Assignment erzeugen). Ein einziger Filter über
  `get_planning_weekdays(...)`.

### main.py::system_info()
- `shift_planning_weekdays` (Array von ints) analog `shift_planning_enabled`
  ausliefern (Default-Tenant, wie der bestehende Flag). Default `[0,1,2,3,4]`,
  **nie 500** (bei kaputtem Setting still auf Default).
- Gleicher SaaS-Cutover-Vorbehalt wie beim bestehenden Default-Tenant-Read (#100).

## Frontend

### systemStore.ts
- Typ `SystemInfo.shift_planning_weekdays?: number[]`.
- Selector `getShiftPlanningWeekdays(): number[]` → Default `[0,1,2,3,4]`.

### WeekGrid.tsx
- Zeile ~154: statt hartem `[0,1,2,3,4,5,6]` die konfigurierten Tage nutzen
  (aufsteigend sortiert). Tagesansicht (`singleDay`, #321) bleibt unverändert.
- Nur konfigurierte Tage bekommen Spalten + „+"-Button.

### Settings.tsx
- Im Schichtplaner-Abschnitt (nur sichtbar wenn `isShiftPlanningEnabled()`):
  Wochentag-Checkbox-Gruppe Mo–So.
- Mindestens 1 Tag muss aktiv bleiben (Client-Guard + Backend-400 als Absicherung).
- Speichern per `PUT /api/admin/settings/shift_planning_weekdays` mit CSV-Wert.

## Bestandsdaten

Slots auf einem nachträglich deaktivierten Wochentag bleiben in der DB erhalten,
werden nur nicht mehr gerendert/generiert. Kein Datenverlust, keine Migration nötig.
Reaktivierung des Tages bringt sie zurück.

## Tests

**Backend (pytest):**
- Setting-Validierung: gültige CSV akzeptiert + normalisiert; leer, out-of-range
  (`7`, `-1`), nicht-numerisch, Duplikate → 400.
- Slot-Create auf deaktiviertem Wochentag → 400; auf aktivem → 201.
- Generator: Slot auf deaktiviertem Tag erzeugt kein Assignment.
- `GET /api/system/info` liefert `shift_planning_weekdays` als Array; Default Mo–Fr
  wenn ungesetzt.

**Frontend (vitest):**
- WeekGrid rendert nur die konfigurierten Spalten (z. B. `[0,1,2,3,4]` → 5 Spalten).
- Settings-Wochentag-Gruppe: Toggle sendet korrekten CSV-PUT; letzter aktiver Tag
  nicht abwählbar.

## Nicht im Scope (YAGNI)

- Kein Per-Plan-Override (Setting gilt tenant-weit).
- Keine Rückwirkung auf ArbZG/Soll-Ist (Schichtplaner ist entkoppelt, #305).
- Keine Migration bestehender Slots.
