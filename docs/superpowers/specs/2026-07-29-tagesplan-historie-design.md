# Tagesplan-Historie (#431) — Design

**Datum:** 2026-07-29
**Status:** Entwurf
**Ziel-Version:** 1.18.0 (MINOR)
**Issue:** [#431](https://github.com/phash/praxiszeit/issues/431) — „Änderung der Wochenstunden"

## Problem

Im Bearbeiten-Formular fehlt für einen Teil der Mitarbeitenden der Button
„Wochenstunden anpassen…". Betroffen sind genau die mit **individuellem Tagesplan**
(`use_daily_schedule = true`): dort rendert das Formular weiterhin ein direktes
Eingabefeld, der Dialog ist nicht erreichbar
(`frontend/src/pages/admin/users/UserForm.tsx:378`), und der Endpoint lehnt eine
Historien-Zeile für sie mit 400 ab (`backend/app/routers/admin_users.py:931-939`).

Der Ausschluss war in 1.17.0 bewusst gesetzt und technisch korrekt begründet:
`calculation_service.get_daily_target_for_date` (`:364-402`) **verwirft** bei
`use_daily_schedule = true` das übergebene, datumsaufgelöste `weekly_hours` und liest
stattdessen live `user.hours_monday…friday`. Eine Historien-Zeile hätte für diese
Mitarbeitenden also keinerlei Wirkung auf das Soll, während die Oberfläche einen neuen
Wert angezeigt hätte — ein still falscher §16-Beleg.

Die Lücke dahinter ist größer als der fehlende Button. Für Tagesplan-Mitarbeitende sind
**alle** Soll-Treiber historienlos:

| Feld | heute änderbar über | Wirkung |
|---|---|---|
| `hours_monday…friday` | Formular, direkt | rückwirkend für die **gesamte** Vergangenheit |
| `use_daily_schedule` | Formular, direkt (`admin_users.py:811` generisches `setattr`) | wechselt schlagartig die Soll-Quelle aller Altmonate |
| `work_days_per_week` | Formular, direkt | Tagessoll = Wochenstunden ÷ Arbeitstage → gilt auch für **gleichmäßige** MA |

Damit verschiebt jede Vertragsänderung das Soll bereits abgeschlossener Monate, ohne
Protokoll, ohne Rückrechnung der gebuchten Abwesenheits-Stunden und ohne
Jahresabschluss-Warnung — genau das Problem, das #415/#423 für die Wochenstunden
behoben haben.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Was erfasst der Dialog bei Tagesplan? | **5 Tagesfelder (Mo–Fr) + Wirkungsdatum.** Wochenstunden = Summe, read-only. Keine proportionale Skalierung. |
| Modus-Wechsel (`use_daily_schedule`) | **Läuft ebenfalls über den Dialog**, mit Wirkungsdatum. Der Haken im Formular wird Anzeige. |
| `work_days_per_week` | **Mit historisiert** (gleicher Soll-Treiber, gleiche Lücke). |
| Datenmodell | **Eine Tabelle, Snapshot-Semantik.** `working_hours_changes` trägt je Zeile den vollständigen Vertragszustand ab dem Datum. |
| Rückfallwert `user.hours_*` etc. | Bleibt „aktuell gültiger Wert" **und** Rückfall für Tage vor der ersten Zeile — wie `user.weekly_hours` heute. Basis-Zeilen-Logik friert die Vergangenheit ein. |
| `weekly_hours` bei Tagesplan | **Abgeleitet** (Σ der Tageswerte). Betrifft Berichtsköpfe und die MiLoG-Basis. |
| Vorschau | **Erweitert:** 5 Tagessoll-Paare + Überstundensaldo und Urlaubstage vorher/nachher. |
| Direktes Setzen per API | `PUT /users/{id}` lehnt `hours_*`, `use_daily_schedule`, `work_days_per_week` mit 400 ab — wie schon `weekly_hours`. Anlegen (`POST`) bleibt frei. |
| Umsetzung | Ein Branch, ein Release. Die Sperren fallen erst, wenn der Resolver überall greift. |

## Datenmodell

Migration `067` erweitert `working_hours_changes` (HEAD ist `066_vacation_days_decimal`):

| Spalte | Typ | Bedeutung |
|---|---|---|
| `use_daily_schedule` | `BOOLEAN NOT NULL DEFAULT false` | Modus ab diesem Datum |
| `hours_monday` … `hours_friday` | `NUMERIC(4,2) NULL` | Tageswerte, nur im Tagesplan-Modus gesetzt |
| `work_days_per_week` | `INTEGER NULL` | `NULL` = Rückfall auf `user.work_days_per_week` |

`weekly_hours` bleibt `NOT NULL` — im Tagesplan-Modus steht dort die Summe der
Tageswerte. Damit entfällt ein Nullable-Umbau der bestehenden Spalte, und alle
vorhandenen Leser (u. a. `weekly_hours_segments`, Berichtsköpfe) bleiben gültig.

Zusätzlich in derselben Migration: `UNIQUE (tenant_id, user_id, effective_from)` — heute
nur als App-Check vorhanden (`admin_users.py:941-951`).

**Snapshot-Semantik.** Jede Zeile beschreibt den vollständigen Zustand ab ihrem Datum,
nicht ein Delta. Folgen:

- „Die nächste Zeile" ist immer die richtige Fenstergrenze — unabhängig davon, ob sich
  Modus, Tageswerte oder Wochenstunden geändert haben.
- Die Verankerungsregel „früheste Zeile nicht löschbar" (`admin_users.py:1262-1281`)
  bleibt eindeutig.
- Der Duplikat-Check „ein Datum = eine Zeile" bleibt gültig.

**Backfill.** Jede bestehende Zeile bekommt `use_daily_schedule`, `hours_*` und
`work_days_per_week` **des jeweiligen Users**. Damit ist das Verhalten nach der
Migration byte-identisch:

- Gleichmäßiger MA: Zeilen behalten ihre `weekly_hours`, Modus false, Tageswerte NULL.
- Tagesplan-MA: die Zeilen tragen die aktuellen Tageswerte — also exakt das, was heute
  live gelesen wird.
- **Mischfall** (Tagesplan-MA mit Alt-Zeilen aus einer Zeit vor dem Umschalten): die
  Alt-Zeilen sind heute wirkungslos; nach dem Backfill tragen sie den Tagesplan und
  bleiben wirkungsgleich. Ohne diesen Backfill würden sie schlagartig scharf geschaltet
  und das Soll der Vergangenheit verschieben.

## Resolver

Weil Modus, Tageswerte, Wochenstunden und Arbeitstage in **derselben** Zeile liegen,
braucht es keinen zweiten Preload und keine zweite Query. Der vorhandene
`wh_changes`-Preload trägt alles.

```python
@dataclass(frozen=True)
class Schedule:
    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple[Optional[Decimal], ...]   # Mo … Fr
    work_days_per_week: int

def get_schedule_for_date(db, user, d, wh_changes=None) -> Schedule
```

Gleiche Struktur wie `get_weekly_hours_for_date` (`:13-64`): Query-Pfad,
In-Memory-Pfad über eine vorgeladene Liste, F-026-Tenant-Filter, Rückfall auf die
User-Spalten, wenn keine Zeile greift. `get_weekly_hours_for_date` bleibt bestehen und
liest künftig aus demselben Resolver — genau eine Auflösungsstelle.

```python
def get_daily_target_for_date(user, d, schedule) -> Decimal
```

`schedule` ist **verpflichtend**. Ohne Pflichtparameter bliebe eine übersehene
Call-Site lautlos auf dem aktuellen Plan stehen und erzeugte ein halb-historisches
§16-Dokument — Abwesenheitstage historisch gerechnet, reguläre Arbeitstage nicht. Mit
Pflichtparameter schlägt jede übersehene Stelle sofort fehl.

**Betroffene Stellen** (~31 Call-Sites in 13 Dateien, alle mit `db` im Scope):

- Kern: `_day_soll_contribution` (`:589-622`) — deckt die 4 Soll-Schleifen und
  `export_service.absence_day_target` in einem Schritt ab.
- Eigene Per-Tag-Schleifen mit eigenem Preload: `get_range_target` (`:813`),
  `get_overtime_account` (`:1139`), `get_overtime_history_detailed` (`:1330`),
  `get_ytd_summary` (`:1547`, öffentlicher Parameter → `admin_users.py:252` mitgeben),
  `future_freizeitausgleich_impact` (`:704`), `retarget_absence_hours` (`:268`).
- Eigener Parallelpfad ohne `_day_soll_contribution`: `get_gross_monthly_target`
  (`:950-986`, klassischer Jahresbericht) — wird mitgezogen, sonst widerspricht der
  Jahresbericht dem Monatsbericht.
- `_fixed_planned_hours` (`:433-440`, #377-2b): definiert die „geplante Anwesenheit"
  als `hours_<wd>` → ohne Resolver schriebe `fixed_month_credit` einem vergangenen
  Urlaubs-/Feiertag die **heutigen** Planstunden gut.
- Anzeigeflächen mit eigener Werktags-/Tagessoll-Logik: `journal_service:88-112`,
  `dashboard.py:90-97`, `reports.py:1029-1037` (ArbZG-§3-Nenner),
  die 3 Export-Detailgrids in `export_service` / `ods_export_service`.

## Endpoints

### `POST /admin/users/{id}/working-hours-changes`

- Die Tagesplan-Sperre (`:931-939`) entfällt. Der Request trägt entweder
  `weekly_hours` (gleichmäßig) oder die 5 Tageswerte (Tagesplan) plus optional
  `work_days_per_week`; `use_daily_schedule` ergibt sich aus dem gewählten Modus.
  Bei Tagesplan wird `weekly_hours` serverseitig als Summe gesetzt — der Client schickt
  keinen abweichenden Wert.
- Validierung: im Tagesplan-Modus mindestens ein Tageswert > 0; jeder Wert ≥ 0 und
  ≤ 24; Summe ≤ 60 (Grenze wie beim bestehenden Feld).
- **Basis-Zeile** (`:982-1015`) wird 5-Werte-fähig: Vergleich nicht mehr skalar,
  sondern über den vollständigen Snapshot. Datum unverändert = frühestes aus
  `first_work_day`, ältester Buchung und Vortag der Änderung.
- **Resync** auf die User-Zeile (`:1035-1042`) schreibt bei `effective_from <= heute`
  zusätzlich `hours_*`, `use_daily_schedule` und `work_days_per_week` zurück, damit die
  „aktuell gültigen" Felder (und die drei Frontend-Duplikate der Tagessoll-Logik) stimmen.
- `retarget_absence_hours` (`:207-325`) läuft künftig **auch** für Tagesplan-MA. Das
  Fenster ist dabei tages-scharf: ändert sich nur der Mittwochswert, dürfen nur
  Mittwochs-Abwesenheiten umgerechnet werden.
- Jahresabschluss-Warnung (`stale_year_closing_warning`) unverändert: melden, nicht
  neu rechnen.

### `GET …/working-hours-changes/preview`

- `blocked_reason` „individueller Tagesplan" entfällt.
- Statt der Skalare `current_daily_target` / `new_daily_target` (die für Tagesplan-MA
  heute degeneriert identisch sind) fünf Paare Mo–Fr.
- Neu: `overtime_before` / `overtime_after` und `vacation_days_before` /
  `vacation_days_after` für den betroffenen Zeitraum. Berechnung als Dry-Run über
  `flush` + `rollback` — das Muster steht bereits in `preview` (`:1188-1201`).
  Urlaub ist tagebasiert (§3 BUrlG) und ändert sich in aller Regel nicht; die
  Gegenüberstellung macht genau das sichtbar.

### `DELETE …/working-hours-changes/{id}`

Der Tagesplan-Skip (`:1338-1341`) wird invertiert — das Löschen rechnet die
Abwesenheits-Stunden symmetrisch zurück und liefert die Jahresabschluss-Warnung
(`:1362-1365`), die heute für Tagesplan-MA mit ausfällt.

### `PUT /admin/users/{id}`

Lehnt zusätzlich `hours_monday…friday`, `use_daily_schedule` und
`work_days_per_week` mit 400 ab. Die bisherige I2-Ausnahme („`weekly_hours` per PUT
erlaubt, wenn `use_daily_schedule`", `:719-731`) entfällt — sie existierte nur, weil
diese Gruppe sonst gar keinen Schreibweg hatte.

## Berichte (#415)

`weekly_hours_segments` (`:67-124`) liefert für Tagesplan-MA heute genau ein Segment mit
einem Wert, der nichts steuert. Künftig trägt ein Segment den vollständigen Snapshot;
`format_weekly_hours_history` schreibt im Tagesplan-Modus:

```
ab 01.03.2026: Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche
```

Zu pflegen sind die bekannten 6 Flächen (XLSX-Monatsblatt, XLSX-Jahresübersicht,
XLSX-Jahres-Mitarbeiterblatt, ODS-Pendants, PDF-Meta, `/admin/reports/monthly|weekly`)
plus der **wortgleiche** Frontend-Zwilling `utils/formatters.ts::formatWeeklyHoursChanges`.
Neue Spalten werden angehängt, nie eingeschoben. Die PDF-Meta ist ein Inline-Absatz in
Schriftgröße 8 → dort die Kurzform (`Mo 8 / Di 5 / Mi 4`).

## Oberfläche

### WorkingHoursModal

```
Neue Stundenänderung
─────────────────────────────────────────────
Gültig ab  [01.03.2026]

( ) Gleichmäßig   Wochenstunden [20,0]  Arbeitstage [5]
(•) Nach Tagen    Mo[8,0] Di[5,0] Mi[4,0] Do[0,0] Fr[0,0]
                  → 17,0 h/Woche · 3 Arbeitstage

Notiz [Teilzeitänderung]

⚠ Rückwirkend: 01.03.2026 – 29.07.2026
   Tagessoll   Mo 8,0→6,0 · Di 5,0→5,0 · Mi 4,0→4,0 · Do – · Fr –
   12 Abwesenheit(en) betroffen

               bisher      neu        Δ
   Überstunden  +89,0 h    +41,5 h    −47,5 h
   Urlaub        18,0 T     18,0 T      0,0 T

   ☐ Ich habe die Auswirkungen geprüft und möchte trotzdem speichern

               [ + Hinzufügen ]

Verlauf
   Ab 01.01.2026 bis 28.02.2026: 40,0 Std/Woche (gleichmäßig, 5 Tage)
   Ab 01.03.2026 bis heute:      Mo 8 / Di 5 / Mi 4 = 17,0 Std/Woche
```

Der Titel wird „Wochenstunden & Tagesplan"; das Uhr-Symbol in Liste und Karte heißt
entsprechend. Die Bestätigungspflicht bleibt an „schreibt bereits gebuchte Zeilen um"
geknüpft, nicht am Datum allein — ein zukünftiges Wirkungsdatum kann genehmigten Urlaub
und Betriebsferien treffen.

Die Vorschau hängt künftig an bis zu 8 Formularwerten. Der bestehende
400-ms-Debounce bleibt; zusätzlich wird „Hinzufügen" gesperrt, solange sich gegenüber
dem aktuell gültigen Zustand **nichts** geändert hat.

### UserForm

Der Tagesstunden-Block (`:757-814`), der Haken „Individuelle Tagesstunden" und
„Arbeitstage pro Woche" werden beim **Bearbeiten** Anzeige — mit demselben Button
daneben, der schon für die Wochenstunden existiert. Beim **Anlegen** bleiben alle Felder
normale Eingabefelder.

Der heutige Hinweistext („werden direkt gepflegt, nicht über die
Wochenstunden-Historie", `:423-430`) wird durch diese Änderung sachlich falsch und
entfällt.

## Testkonzept

TDD, Reihenfolge wie unten. Kern der Absicherung sind zwei Klassen:

1. **Byte-Identität für alle Nicht-Tagesplan-MA ohne neue Zeilen** — Kontrolltests
   analog `test_special_days.py::test_normal_day_vacation_still_costs_full`. Rund 15
   bestehende Suiten dürfen sich nicht ändern (u. a. `test_calculations_extended`,
   `test_closure_overtime_split`, `test_fixed_monthly_target`, `test_export_service`,
   `test_ods_export_service`, `test_vacation_day_principle`, `test_edge_cases`).
2. **Umschreiben statt löschen**: `test_fix2_whchange_daily_schedule.py` (erwartet den
   400), `test_wh_change_retroactive.py:518-580` und `:1021-1105`,
   `test_wh_change_preview.py:201-207`, frontend `UserForm.test.tsx:283-298` und
   `WorkingHoursModal.test.tsx:215-234` kodieren jeweils einen realen Vorfall — sie
   werden auf das neue Verhalten umgeschrieben, nicht entfernt.

Weitere Pflichtprüfungen:

- Preload-Parität (`test_calc_preload.py`-Zwilling): Query-Pfad und In-Memory-Pfad
  liefern identische Ergebnisse.
- `get_overtime_history` bitgleich zu `get_overtime_account` unter Stichtag.
- Die 3 Urlaubs-Buchungspfade und die 5 Budget-Pre-Checks lösen denselben historischen
  Plan auf wie `get_vacation_account` (Fehlerklasse #394/1.14.3).
- #314-Re-Split (`closure_split_service`) und `_create_closure_absences` lösen identisch
  auf — der Re-Split läuft danach und überschreibt.
- **Gegen echtes Postgres**: Migration up→down→up, RLS-Policy, `purge_user`
  (FK-Violation ist auf SQLite unsichtbar), `Numeric`-Round-Trip.
- DSGVO: `lifecycle_service._user_dict` und `auth /me/export` casten die neuen
  `Numeric`-Felder mit `float()` (Decimal-Leak-Klasse #383/#408); `WorkingHoursChange`
  fehlt im Art.-15-Export bisher ganz und wird ergänzt.

## Reihenfolge

Die Sperren fallen zuletzt — ein Zwischenstand mit offenem Endpoint und halb
umgestelltem Resolver schriebe gebuchte Abwesenheits-Stunden falsch um
(belegt durch `test_wh_change_retroactive.py:544-580`).

1. Migration `067` + Modell + Backfill + RLS + `purge_user` + DSGVO-Export
2. Resolver + Preload-Zwilling + Byte-Identitäts-Tests
3. `get_daily_target_for_date` auf Pflichtparameter umstellen → alle Call-Sites + Preloads
4. `retarget_window` / `retarget_absence_hours` snapshot- und wochentags-bewusst
5. Basis-Zeile + Resync + 400 im `PUT`
6. Preview-Schema (5 Paare + Saldo/Urlaub) + Dialog + UserForm
7. **Erst jetzt**: die drei Sperren öffnen
8. #415-Anzeige: Segmente + Formatter + 6 Flächen + wortgleicher Frontend-Zwilling
9. Doku über alle 5 Sync-Flächen

## Nicht im Scope

- **Client-seitige Duplikate der Tagessoll-Logik** (`TimeTracking.tsx:42-70`,
  `Dashboard.tsx:189-198`, `AbsenceCalendarPage.tsx:77-96`) rechnen weiter mit den
  aktuellen Feldern. Sie zeigen Gegenwart und Zukunft, wo der aktuelle Plan gilt. Die
  Vergangenheitsansichten (Journal, Berichte, Exporte) kommen vollständig vom Server.
  Wird beim Abschluss-Review nochmals gegengeprüft.
- **Historisierung weiterer Vertragsfelder** (Urlaubstage, `track_hours`) — eigene
  Themen.
- **Schichtplanung** (#305) bleibt entkoppelt; sie liest keine Soll-Stunden.
