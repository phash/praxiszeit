# Vertragsverlauf für Urlaub und Minijob-Felder · Verkürzte Tage

Stand: 2026-11-03 · Ziel-Release: **1.22.0** (MINOR, zwei Migrationen) · muss **vor dem 24.12.2026** beim Kunden sein.

Zwei unabhängige Teile, je ein eigener PR, gemeinsam ausgeliefert:

- **Teil A — Vertragsverlauf:** Urlaubsanspruch, „Stundenzählung aktiv“ und die drei Minijob-Felder bekommen ein Gültigkeitsdatum. Sie werden im Dialog „Arbeitszeit ändern“ mit Wirkungsdatum geändert.
- **Teil B — Verkürzte Tage:** Die Admin legt für den 24./31.12. und für frei gewählte Daten fest, dass das Soll an diesem Tag höchstens X Stunden beträgt.

Reihenfolge: **Teil B zuerst** (fester Termin Weihnachten, kleiner). Danach Teil A. Ist Teil A bis Mitte Dezember nicht fertig, geht Teil B allein als 1.22.0 raus (nur Migration 074), Teil A folgt als 1.23.0 mit dann 075 **(Entwurf)**.

Entscheidungen, die Manuel getroffen hat, sind als **(Manuel)** markiert. Entscheidungen des Designs, die er noch prüfen soll, als **(Entwurf)**.

---

## 1. Anlass

**Kundenfall Urlaub (2026-11-03):** Eine Mitarbeiterin arbeitet ab 01.11.2026 fünf statt vier Tage pro Woche, bei gleicher Wochenstundenzahl. Erwartet: 2026 ein Tag mehr Urlaub (24 → 25), ab 2027 sechs Tage mehr (30). Heute gibt es nur einen Anspruch je Person (`users.vacation_days`) ohne Datum. Er gilt für jedes Jahr rückwirkend. Setzt die Admin 30, erhält die Mitarbeiterin auch 2026 volle 30. Lässt sie 24, fehlt der eine Tag. Die Mitarbeiterin sieht deshalb keine Änderung.

**Gleiche Fehlerklasse an weiteren Feldern** (Codeerfassung 2026-11-03):

| Feld | Was heute rückwirkend passiert |
|---|---|
| `agreed_monthly_hours` | Im Modus „festes Monats-Soll“ ändert eine Anhebung (z. B. neuer Mindestlohn ab 01.01.2027) das Soll von Januar bis heute mit. Das Überstundenkonto, `settlement_aging` und die §16-Exporte verschieben sich. |
| `use_fixed_monthly_target` | Einschalten mitten im Jahr schaltet die ganze Vergangenheit auf festes Monats-Soll um. |
| `milog_working_time_account` | Einschalten macht 50-%-Prüfung und Fälligkeit auch für Monate ohne Arbeitszeitkonto. |
| `track_hours` | Ausschalten löscht Soll und Ist aller vergangenen Monate und Jahre; Einschalten erzeugt Soll für Monate ohne Einträge (großes Minus). |

**Kundenwunsch verkürzte Tage:** Am 24. und 31.12. soll das Soll auf 4 Stunden gekürzt werden. Wer länger Soll hätte, geht nach 4 Stunden. Wer ohnehin weniger Soll hat, hat keinen Vorteil (Manuel: „wer weniger arbeitet, hat leider Pech“).

## 2. Ziele

1. Ein Wechsel von Arbeitstagen ändert den Urlaubsanspruch im selben Dialog. Das Programm **schlägt den neuen Jahresanspruch vor**, die Admin kann ihn **überschreiben** **(Manuel)**. Das laufende Jahr wird **anteilig** gerechnet: Kundenfall 2026 = 25, 2027 = 30.
2. `track_hours`, `milog_working_time_account`, `agreed_monthly_hours`, `use_fixed_monthly_target` wirken ab ihrem Wirkungsdatum, nie rückwirkend über das Datum hinaus **(Manuel: „auch mit aufnehmen“)**.
3. Ein verkürzter Tag setzt das Soll auf `min(Tagessoll, X)`. X stellt die Admin ein. Gilt für 24./31.12. **und** für frei gewählte Daten **(Manuel)**.

## 3. Nicht-Ziele

- Keine Verlaufsführung für `exempt_from_arbzg`, `is_night_worker`, `child_sick_days_per_year`, `receives_company_closures` (selten, Folgen bleiben in Berichten bzw. Warnungen).
- `vacation_carryover_deadline` bleibt ein absolutes Datum. Dass es für jedes Jahr gilt, ist ein eigener Fund, nicht Teil hiervon.
- Kein Scheduler für zukunftsdatierte Zeilen (bleibt wie heute: Spiegel auf die Benutzerzeile beim nächsten Schreiben, Spec 9.8 von 1.20).
- Verkürzte Tage nur mandantenweit, nicht je Person.
- An verkürzten Tagen wird die **angerechnete Zeit nicht gekappt**. Wer länger bleibt, bekommt Überstunden **(Manuel: „ja genau so“)**.
- Keine Neuberechnung abgeschlossener Jahre (Fix #5 bleibt: nur warnen).

## 4. Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch läuft)

- **Eine Migration ändert irgendein Ergebnis eines vergangenen Jahres** (Saldo, Urlaubskonto, Export). Nach Migration 074/075 müssen alle Konten bitgleich sein, solange niemand etwas ändert.
- **Zwei Schreibwege für ein verlaufsgeführtes Feld**: ein Weg mit Datum (Dialog) und einer ohne (`PUT /admin/users`). Das war die Ursache von #415/#431.
- **„NULL heißt: lies den Live-Wert der Benutzerzeile“** in einer Verlaufszeile. Die Codeprüfung hat genau das als größtes Risiko gefunden: Die Spiegelung schreibt den neuen Wert auf `users`, und jede Zeile mit NULL würde dann rückwirkend den neuen Wert lesen.
- Das Benutzerformular scheitert bei jedem Speichern mit 400, weil es ein verlaufsgeführtes Feld mitschickt.

---

## Teil A — Vertragsverlauf

### A1. Datenmodell

Migration **075** (nach 074 aus Teil B): neue Spalten in `working_hours_changes`:

| Spalte | Typ | wie heute auf `users` |
|---|---|---|
| `vacation_days` | `Numeric(4,1)` | `users.vacation_days` |
| `track_hours` | `Boolean` | `users.track_hours` |
| `milog_working_time_account` | `Boolean` | `users.milog_working_time_account` |
| `agreed_monthly_hours` | `Numeric(5,1)`, nullable (NULL = aus `weekly_hours` abgeleitet, wie heute) | `users.agreed_monthly_hours` |
| `use_fixed_monthly_target` | `Boolean` | `users.use_fixed_monthly_target` |

- **Backfill:** Jede bestehende Zeile bekommt die heutigen Werte ihrer Benutzerzeile. Das ist genau der Wert, mit dem heute jedes vergangene Datum rechnet. So bleibt jedes Ergebnis gleich (Anti-Ziel 1).
- Nach dem Backfill sind die vier nicht-optionalen Spalten **NOT NULL**. `agreed_monthly_hours` bleibt nullable, aber NULL bedeutet dort fachlich „abgeleitet“, nie „lies die Benutzerzeile“.
- RLS besteht für die Tabelle schon. Downgrade entfernt die Spalten.
- Migrationstest up → down → up auf Wegwerf-PG 18 plus Probe auf einer Kopie der Prod-Sicherung: alle Urlaubskonten und Überstundenkonten aller Personen und Jahre vor und nach 075 identisch.

### A2. Auflösung nach Datum

- `Schedule` (`calculation_service.py:16`) bekommt die fünf Felder. `get_schedule_for_date` füllt sie aus der Zeile. Alle Konstruktoren (auch Vorschau `admin_users.py` ~:2238 und die Tests `test_reclamp_audit.py`, `test_wh_change_legacy_blocks.py`, `test_wh_change_service.py`) werden mitgezogen. `Schedule` behält keine Vorgabewerte, damit ein übersehener Konstruktor laut scheitert.
- **Vor der ersten Verlaufszeile** einer Person gilt für die fünf neuen Felder die Benutzerzeile — aber nur, solange es überhaupt keine Zeile gibt. Gibt es Zeilen, gelten für Daten vor der ersten Zeile **die Werte der ersten Zeile** **(Entwurf)**. Grund: Die Basiszeile beginnt erst bei `_soll_coverage_start`, also eventuell mitten im Jahr. Ein anteiliger Jahresanspruch braucht aber einen Wert ab 01.01.
- Die **Basiszeile** (`_frozen_row`, `_insert_change_rows`) friert die fünf Felder mit ein. `_comparable_snapshot` (Backend) und `comparableSnapshot` (Frontend) vergleichen die fünf Felder mit. Damit:
  - löst eine reine Urlaubsänderung eine Basiszeile aus,
  - gilt „Snapshot unverändert“ nicht mehr, wenn nur der Anspruch geändert wurde,
  - prüft `_reset_matches` die Felder mit.
- `wh_change_service.reset_body` setzt die fünf Felder **vor** dem frühen Rücksprung im Blockmodus (`:458-479`).
- `_sync_user_from_change` spiegelt die fünf Felder auf die Benutzerzeile, wie die Stunden.

### A3. Lesen in der Berechnung

**Grundregel:** Kein Rechenpfad liest die fünf Felder mehr von `users`, nur noch aus dem Snapshot zum Datum. Ein Guard-Test (Muster `test_no_live_work_blocks_read.py`) prüft per Quelltextsuche, dass `user.vacation_days`, `user.track_hours`, `user.milog_working_time_account`, `user.agreed_monthly_hours`, `user.use_fixed_monthly_target` in `app/services` und `app/routers` nur noch an erlaubten Stellen vorkommen (Anlegen, Spiegel, Rohexporte `auth.py:762`, `lifecycle_service.py:540`, Benutzerantwort).

**Urlaubsanspruch (`get_vacation_account`, einzige Rechenstelle, `:2993-3037`):**

```
Für Jahr J:
  Segmente = Abschnitte des Jahres mit gleichem vacation_days laut Verlauf,
             geschnitten mit dem Beschäftigungsfenster (first_work_day/last_work_day)
  budget_days(J) = Σ  vacation_days(Segment) × Monatsanteil(Segment) / 12
  Monatsanteil  = ganze Monate + angebrochene Monate taggenau (Tage im Segment ÷ Tage im Monat)
                  — dieselbe Bruchrechnung wie heute bei Ein-/Austritt
  Rundung       = auf 0,1 (wie heute im Ein-/Austrittsjahr)
  Ausnahme      = ein Jahr mit genau einem Segment über das ganze Jahr: unverändert der Wert, ohne Rundung
  + YearCarryover(J).vacation_days (wie heute, nicht anteilig)
```

- Kundenfall: 24 × 10/12 + 30 × 2/12 = 20 + 5 = **25,0**. 2027: 30.
- Die Ein-/Austrittsregeln und Fix #1 (Jahr ganz außerhalb → 0, kein Übertrag) bleiben; sie sind dann der Sonderfall „Segment ist durch das Fenster beschnitten“.
- Alle Verbraucher (Budgetprüfungen, Betriebsferien-Split #314, Jahresabschluss, Berichte, Exporte, Dashboard, `users-overview`) bekommen den neuen Wert automatisch, weil sie nur über `get_vacation_account` lesen (Codeerfassung bestätigt).
- `budget_hours` bleibt informativ: `budget_days × Referenz-Tagessoll` wie heute.
- Der veraltete Docstring (`:2958`, „Uses CURRENT weekly hours“) wird korrigiert.

**`track_hours`:** je **Tag** aus dem Snapshot. Betrifft alle Stellen aus der Codeerfassung (u. a. `retarget_absence_hours`, `counts_vacation_by_day_only`, `get_daily_target(_for_date)`, `absence_booking_dates`, `get_day_presence_target`, `get_range_target`, `get_gross_monthly_target`, Überstundenkonto, `get_overtime_history_detailed`, `get_ytd_summary`, `_vacation_reference_daily_target`, `work_window_service.clamp_applies` / `reclamp_time_entries`, `company_closures` Split, `closure_split_service`, `milog_service`, `dashboard`, `reports`). Ein Jahr mit Wechsel rechnet die Tage vor dem Wechsel im alten, die Tage danach im neuen Modus. Urlaubsverbrauch ist ohnehin tagebasiert; im Mischjahr zählt jeder Tag nach seinem eigenen Modus.

**Rückwirkende Umstellung von `track_hours` rechnet den Wirkungszeitraum neu (Manuel: Variante A):** Wie bei einer Stundenänderung läuft alles über `wh_change_service.run_change` — Anlegen, Löschen und beide Vorschauen in einem Rechenpfad.
- **Geänderte Wochentage:** Ein Wechsel von `track_hours` gilt als Änderung **aller** Wochentage (`changed_weekdays` liefert dann Mo–Fr).
- **Abwesenheiten:** `retarget_absence_hours` zieht die `hours` im Fenster auf das neue Tagessoll — von 0 auf das Tagessoll laut Snapshot beim Einschalten, auf 0 beim Ausschalten. Urlaubs**tage** bleiben. Der heutige frühe Rücksprung für `track_hours=False` (`:653`) prüft den Snapshot des jeweiligen Tages, nicht die Benutzerzeile.
- **Zeiteinträge:** Beim Einschalten werden die Einträge im Fenster aus den Rohstempeln neu gekappt (`reclamp_time_entries`, `:853` prüft den Snapshot je Tag). Beim Ausschalten wird die Kappung aufgehoben: wirksame Zeiten = Rohstempel, `uncredited_minutes` = 0 (`credit_override`-Einträge bleiben, wie immer).
- **Klassifikation, Schutzpaket, Protokoll:** unverändert über Saldo- und Eintragsvergleich; rückwirkende Verkürzung nur mit Grund. Protokoll `wh_reclamp` je Eintrag, Abwesenheitszeilen über `_log_wh_change_retarget`, Sammelzeile wie immer.
- Test: `track_hours` False → True ab 01.06. (rückwirkend): Urlaub im Juni bekommt Tagessoll-Stunden, Einträge im Juni gekappt, Saldo Juni neu, Januar–Mai unverändert; Rücknahme (Löschen) stellt den Ausgangszustand bitgleich her.

**Minijob-Felder (`agreed_monthly_hours`, `use_fixed_monthly_target`, `milog_working_time_account`):** wirken **monatsweise**. Ein Wechsel dieser drei Felder ist nur **zum Monatsersten** erlaubt; sonst 422 „Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.“ **(Entwurf)**. Grund: festes Monats-Soll, 50-%-Prüfung und Fälligkeit sind Monatsgrößen; ein Wechsel am 15. hätte keine sinnvolle Bedeutung. Wird gleichzeitig mit den Stunden zu einem anderen Datum geändert, muss die Admin zwei Änderungen anlegen.
- `milog_service.agreed_monthly_hours(user, ref_date)` liest den Snapshot zum Monat (heute ignoriert es `ref_date`, wenn ein expliziter Wert gesetzt ist, `:38-40`).
- Alle Verzweigungen „festes Monats-Soll“ (`calculation_service.py:1094, 1255, 1267, 1645/1646, 1731, 1895, 2116, 2523, 2657`, `journal_service.py:111-112`, `work_schedule_service.py:48-55`, `team_schedule.py:68`, `milog_service.py:105`) prüfen den Modus je Monat, nicht einmal je Person.
- Die heutigen Zulässigkeitsregeln (`use_fixed_monthly_target` nur mit `agreed_monthly_hours > 0`, `track_hours=True`, `milog_working_time_account=True`; `admin_users.py:1322`) gelten für den **Snapshot** der neuen Zeile und werden in `WorkingHoursChangeCreate` geprüft (400 wie heute).

### A4. Schreiben und Oberfläche

**`PUT /admin/users/{id}`:** Die fünf Felder kommen in `_HISTORISED_FIELDS` → 400 wie bei den Stunden. `POST /admin/users` setzt sie weiter beim Anlegen.

**Benutzerformular (`UserForm.tsx`):**
- Beim Anlegen unverändert editierbar (inkl. Vorschlag `30 × Arbeitstage ÷ 5`).
- Beim Bearbeiten nur Anzeige des heute gültigen Werts mit Verweis „Ändern über ‚Arbeitszeit anpassen…‘“. Das Formular schickt die fünf Felder beim Bearbeiten **nicht** mehr mit (heute schickt es `vacation_days` immer, `:300-306`).

**Dialog „Arbeitszeit ändern“ (`WorkingHoursModal.tsx`):** neuer Abschnitt „Urlaub und Abrechnung“ unter den Stunden:
- **Urlaubsanspruch pro Jahr ab diesem Datum** — Zahlfeld, Schritt 0,1, 0–50.
  - **Vorschlag**, sobald sich die Zahl der Arbeitstage ändert: `alter Anspruch × neue Arbeitstage ÷ alte Arbeitstage`, auf 0,1 gerundet **(Entwurf)**. Kundenfall: 24 × 5 ÷ 4 = 30. Ein praxisindividueller Anspruch (z. B. 28 bei 5 Tagen) bleibt so im Verhältnis erhalten; `30 × Tage ÷ 5` würde ihn überschreiben.
  - Das Feld übernimmt den Vorschlag automatisch, solange die Admin es nicht selbst geändert hat. Danach bleibt ihr Wert stehen; ein Link „Vorschlag übernehmen (30)“ bleibt sichtbar **(Manuel: vorschlagen, überschreibbar)**.
- **Stundenzählung aktiv**, **MiLoG-Arbeitszeitkonto**, **vereinbarte Monatsstunden**, **festes Monats-Soll** — dieselben Steuerelemente und Abhängigkeiten wie heute im Benutzerformular.
- Alle fünf gehören in `scheduleBody` und damit in Vorschau-Schlüssel und Anlege-Body.

**Vorschau (`POST …/preview`, `…/delete-preview`, `WhImpactBox.tsx`):**
- Neue Felder `vacation_entitlement` je Jahr: **laufendes Jahr des Wirkungsdatums und Folgejahr**, jeweils bisher → neu (`budget_days` ohne Übertrag). Kundenfall: „Urlaubsanspruch 2026: 24 → 25 · 2027: 24 → 30“.
- Die bestehende Zeile „Urlaub“ (verbrauchte Tage) heißt künftig „Urlaub verbraucht“, damit beide nicht verwechselt werden.

**Verkürzung / Schutzpaket:** Sinkt durch eine **rückwirkende** Änderung (`effective_from < heute`) der Anspruch eines Jahres, ist das ein neuer Verkürzungsgrund `vacation_entitlement` (Schema-Literal, `ShorteningReason`, `criteria_text`) — Grund, Begründung und Bestätigung sind dann Pflicht wie bei den anderen Gründen **(Entwurf)**. Eine Senkung ab heute oder in der Zukunft ist kein Verkürzungsgrund: Der schon erworbene Anteil bleibt durch die anteilige Rechnung erhalten.
- Änderungen an `track_hours` und den Minijob-Feldern laufen über die bestehende Saldo-Klassifikation (`run_change` vergleicht den Saldo vorher/nachher).

**Abgeschlossene Jahre:** `stale_year_closing_warning` über das Wirkungsfenster wie heute. Liegt das Wirkungsdatum in einem abgeschlossenen Jahr, kommt die Warnung; nichts wird neu gerechnet.

**Protokoll:** `reclamp_audit.contract_text` nennt die fünf Felder im Teil nach „Vertrag:“ (nur dort, wird nie geparst; `_HEAD`/`_RESET` bleiben unberührt). Beispiel: „Vertrag: 40 h · 4 Tage · Urlaub 24 → 40 h · 5 Tage · Urlaub 30“.

**Verlauf im Dialog:** Jede Karte zeigt zusätzlich „Urlaub 30 Tage/Jahr“ und, falls gesetzt, Minijob-Angaben und „ohne Stundenzählung“.

**Löschen einer Änderung:** gleicher Pfad wie heute (`delete-preview`, Rücksetzung, Lückenzeile über `_frozen_row`). Die Vorschau zeigt den Anspruch bisher → neu. Die Sperre der frühesten Zeile bleibt.

**Falsch erfasster Wert für alle Jahre korrigieren:** Die Admin legt im Dialog eine Änderung **zum Datum der ersten Verlaufszeile** an. Gibt es dort schon eine Zeile (Basiszeile), ersetzt die neue Zeile sie, statt mit „Datum schon belegt“ abgelehnt zu werden — nur für die früheste Zeile, mit Vorschau, Protokoll und Schutzpaket wie jede Änderung. Ein zweiter Schreibweg ohne Datum entsteht so nicht **(Entwurf)**.

### A5. Fehlerfälle, die Tests abdecken müssen

- Migration: alle Konten aller Personen und Jahre vor/nach 075 bitgleich (SQLite-Suite **und** PG-Round-Trip auf Prod-Kopie).
- Kundenfall 4 → 5 Tage ab 01.11.2026: 2026 = 25,0, 2027 = 30, Vorschau zeigt beides, `users.vacation_days` = 30 nach dem Speichern, 2025 unverändert.
- Wechsel am 15.11.: taggenaue Bruchrechnung.
- Wechsel im Eintrittsjahr (Eintritt 01.04., Wechsel 01.09.): Segmente mit dem Fenster beschnitten.
- Person ohne Verlaufszeile: unverändert wie heute.
- Erste Änderung bei Person ohne `first_work_day` und ohne Buchungen: Werte vor der ersten Zeile = erste Zeile, nicht die neue Benutzerzeile.
- Reine Urlaubsänderung ohne neue Stunden ist speicherbar.
- `PUT /admin/users` mit einem der fünf Felder → 400; `UserForm`-Bearbeiten ohne die Felder → 200.
- `track_hours` False ab 01.07.: Saldo Januar–Juni unverändert, ab Juli 0.
- `agreed_monthly_hours` 43,3 → 45 ab 01.01.2027 im Fix-Modus: Soll 2026 unverändert.
- Minijob-Feld zum 15. → 422.
- Rücksetzung im Blockmodus behält den Anspruch.
- Rückwirkende Senkung → Verkürzungsgrund `vacation_entitlement`, ohne Grund 400.
- `users-overview` ohne N+1 (Preload `wh_changes` nutzen).

---

## Teil B — Verkürzte Tage

### B1. Regel

An einem verkürzten Tag gilt: **Tagessoll = min(Tagessoll laut Snapshot, X)**. X in Stunden, Schritt 0,25, 0,25–12.

- Wer 8 h Soll hätte, hat 4 h. Wer 3 h hätte, behält 3 h. Wer an dem Tag kein Soll hat, bleibt bei 0 **(Manuel)**.
- Angerechnete Zeit wird **nicht** gekappt. Zeit über X ist Überstunde **(Manuel)**.
- **Urlaub** an einem verkürzten Tag kostet **0,5 Tage**, für alle, wie heute am halben Feiertag **(Manuel bestätigt)**.
- **Krank / Fortbildung** an einem verkürzten Tag werden mit dem verkürzten Soll gutgeschrieben (Ist-Gutschrift folgt der Soll-Struktur, Regel „Fund K“).
- Betriebsferien an einem verkürzten Tag buchen `hours = verkürztes Soll`, `half_day = False`, Verbrauch 0,5 (Muster #394).
- **Arbeitszeit-Blöcke und Kappung bleiben unverändert** (wie heute beim halben Feiertag, #484). Wer nach 4 h geht, wird nicht „nicht angerechnet“; wer länger bleibt, wird innerhalb seiner Blöcke voll angerechnet.
- Feiertag schlägt verkürzten Tag (Soll 0). Wochenende: keine Wirkung.

### B2. Wo die Admin es einstellt

**24./31.12. (Einstellungen → Sondertage):** Die bestehende Auswahl „Arbeitstag / halber Feiertag / frei“ bekommt einen vierten Modus **„verkürzt auf X Stunden“** mit Zahlfeld. Neue Einstellungsschlüssel `special_day_dec24_max_hours` / `special_day_dec31_max_hours` in `admin_settings._ALLOWED_SETTINGS` (Wert in Stunden, Validierung wie B1); Modus-Wert `max_hours`.

**Eigene Daten (neuer Abschnitt „Verkürzte Tage“ auf derselben Seite):** Liste mit Datum, Bezeichnung (z. B. „Rosenmontag“), X Stunden; anlegen, ändern, löschen. Eigene Daten kennen **nur** „verkürzt auf X Stunden“ — ganz frei = Feiertag anlegen (gibt es schon), Pflichturlaub = Betriebsferien **(Entwurf)**. Ein eigenes Datum am 24. oder 31.12. → 400 „Für den 24. und 31.12. bitte die Einstellung Sondertage verwenden.“; doppeltes Datum → 409.

Migration **074**: Tabelle `reduced_days` (`id`, `tenant_id` FK + RLS-Policy + F-026, `date` unique je Mandant, `label` `String(100)`, `max_hours` `Numeric(4,2)`, `created_at`, `created_by` FK `users.id` `ON DELETE SET NULL`). `purge_user()` braucht damit keine Sonderbehandlung.

### B3. Rechenstelle

- `special_days_service.get_special_day_config(db, tid, year)` bleibt die eine Quelle und behält ihre datumsbasierte Rückgabe `{date: {...}}`. Sie liefert zusätzlich die eigenen Daten des Jahres und für Modus `max_hours` den Wert `max_hours`.
- **Eine neue Hilfsfunktion** `special_day_target(d, daily_target, cfg) -> Decimal` liefert das Soll des Tages nach Sondertagsregel (half_day: × 0,5, free: 0, max_hours: min(daily_target, X), sonst daily_target). **Jede** Stelle, die heute `daily_target × factor` rechnet, nutzt sie:
  - `_day_soll_contribution` (`:1527`), `get_gross_monthly_target` (`:1979`), `_fixed_planned_hours` (`:1132`)
  - Exporte: `export_service.py:826, 1458, 2244`; `ods_export_service.py:343, 682`; `journal_service._eff_daily_target` (`:130`)
  - `company_closures._create_closure_absences` (`:370-377`)
  - `absences.get_daily_target_for_date_endpoint` (`:83-90`) — heute ohne Sondertagsfaktor; wird mitgezogen, damit Formulare den richtigen Wert zeigen.
- `credit_day_weight` wird zu einer soll-bewussten Gutschrift: für `max_hours` ist das Gewicht `min(t, X) ÷ t` (bei `t = 0`: 0). Alle fünf Gutschrift-Flächen bleiben über den Helfer verbunden.
- `half_special_day_weight` liefert 0,5 für `half_day` **und** `max_hours` (Urlaubskosten). Alle bekannten Stellen (`get_vacation_account :3113/3145`, `absence_days :2823`, `vacation_day_cost_by_year :3307`, `closure_split_service._wt :118`, `admin_change_requests._vacation_day_contribution :65`, `company_closures :377`) laufen schon darüber.
- `free_state_changed_dates` / `years_affected_by_change` vergleichen künftig Datumsmengen (alt ∪ neu), nicht feste (Monat, Tag).
- `/api/settings` (öffentlich) liefert die eigenen Daten mit; `frontend/src/utils/specialDays.ts::getSpecialDayInfo` sucht nach Datum statt nach `'MM-DD'`. Kalender und Stempelkarte zeigen „verkürzter Tag (max. 4 h)“.
- Stempelkarte „x von y h heute“ (`get_day_presence_target`) zeigt das verkürzte Soll.

### B4. Nachträgliches Anlegen, Ändern, Löschen

- Soll und Saldo werden ohnehin beim Lesen berechnet — die Änderung wirkt sofort auf alle Ansichten, Exporte und das Journal dieses Jahres.
- Liegt der Tag in einem abgeschlossenen Jahr → `stale_year_closing_warning` in der Antwort, keine Neuberechnung (Fix #5).
- Gespeicherte Abwesenheits-`hours` bleiben (Faktor wirkt lesend). Ausnahme Betriebsferien: deren Zeilen tragen das verkürzte Soll. Anlegen, Ändern und Löschen eines verkürzten Tags (und eine Änderung der Einstellung 24./31.12.) speichert **betroffene Betriebsferien automatisch neu** — derselbe Pfad wie `update_closure` (Neubuchung + #314-Split), in derselben Transaktion **(Entwurf)**. Kundenfall: Betriebsferien über Weihnachten 2026 sind oft schon gebucht.
- Keine Neukappung von Zeiteinträgen (Blöcke unverändert).

### B5. Tests

- 24.12. Modus 4 h: 8-h-Person Soll 4, 3-h-Person Soll 3, Person ohne Donnerstag Soll 0; 6 h gearbeitet → +2 h.
- Eigenes Datum: gleiche Fälle; Feiertag am selben Tag → Soll 0.
- Urlaub am verkürzten Tag kostet 0,5 in allen drei Buchungspfaden und im CR-Pfad; Budgetprüfung entsprechend.
- Krank am verkürzten Tag: Gutschrift = verkürztes Soll.
- Betriebsferien über den verkürzten Tag: `hours` = verkürztes Soll, Verbrauch 0,5; #314-Split konsistent.
- Fix-Modus (festes Monats-Soll) über einen verkürzten Tag: das **Monats-Soll bleibt unverändert** (vertraglich fester Betrag, wie bei Feiertagen); nur `_fixed_planned_hours` für eine Abwesenheit an dem Tag nimmt `min(geplante Stunden, X)` — **nicht** `half_special_day_weight` (sonst würde ein 3-h-Tag zu 1,5 h) **(Entwurf)**.
- Exporte XLSX/ODS/PDF und Journal: Tages-Soll und Summen = `calculation_service` (Paritätstest wie `test_audit_20260731_export_ist.py`).
- Abgeschlossenes Jahr → Warnung.
- RLS/F-026 für `reduced_days` (Cross-Tenant-Test), Migration 074 up → down → up.
- Frontend: Einstellungsseite, Kalenderlabel, `getSpecialDayInfo` nach Datum.

---

## 5. Doku (5 Sync-Flächen)

Für beide Teile: `docs/BERECHNUNGEN.md` (§8.1 Urlaubsanspruch anteilig je Segment, veraltete Aussagen zu `get_daily_target` und #191-Übertrag mitkorrigieren; Sondertage), `docs/GLOSSAR.md` (Begriff „verkürzter Tag“), `docs/handbuch/HANDBUCH-ADMIN.md` + Cheatsheet, `DocViewer.tsx` + `helpContent.tsx`, Spiegel `frontend/public/help/`, pzweb-Anleitung, `SchnellstartAdmin`. `scripts/check-doc-sync.sh all` grün. CLAUDE.md: Regel „Neuer Soll-Treiber → Snapshot“ um die fünf Felder ergänzen; Sondertags-Regeln auf `special_day_target` umstellen.

Bekannter Doku-Fehler nebenbei: `AdminDashboard.tsx:249` behauptet, manuelle Überträge gingen beim Löschen des Jahresabschlusses verloren — das Backend behält sie. Mitkorrigieren.

## 6. Dem Umsetzer überlassen

- Namen von Hilfsfunktionen, Schemafeldern und Komponenten (außer den genannten Einstellungsschlüsseln, die Teil der Datenhaltung sind).
- Aufteilung der Tasks und Reihenfolge innerhalb eines Teils.
- Genaues Layout des neuen Dialogabschnitts und der Einstellungsliste (bestehende Muster der Seiten nutzen).
- Ob `special_day_target` in `special_days_service` oder `calculation_service` liegt.
- Performance: Verlauf je Person einmal laden (Preload wie `wh_changes` in `users-overview`), keine Abfrage je Tag.

## 7. Für den Kunden bis zur Auslieferung

Umweg (Kundenmail noch offen): Anspruch bei 24 lassen, Übertrag in 2026 um 1 erhöhen; nach Auslieferung von 1.22.0 den Wechsel im Dialog ab 01.11.2026 mit Anspruch 30 nachtragen und den manuellen +1 wieder entfernen.
