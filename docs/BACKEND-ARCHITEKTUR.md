# Backend-Architektur – PraxisZeit

## Router-Struktur

Der Admin-Router wurde aus einer 1244-Zeilen God-File in 7 Sub-Router aufgeteilt:

| Router | Datei | Zweck |
|--------|-------|-------|
| **Admin (Koordinator)** | `admin.py` | Inkludiert alle Sub-Router |
| Admin Users | `admin_users.py` | CRUD Benutzer, Stundenänderungen, Anonymisierung |
| Admin Time Entries | `admin_time_entries.py` | Zeit-Einträge verwalten, Audit-Log |
| Admin Change Requests | `admin_change_requests.py` | Korrekturanträge prüfen/genehmigen |
| Admin Vacations | `admin_vacations.py` | Urlaubsanträge genehmigen |
| Admin Carryovers | `admin_carryovers.py` | Jahresabschluss + Vorjahresübernahmen |
| Admin Settings | `admin_settings.py` | System-Einstellungen (Key-Value) |
| Admin Helpers | `admin_helpers.py` | Geteilte Hilfsfunktionen, Audit-Logging |

### User-facing Router

| Router | Datei | Zweck |
|--------|-------|-------|
| Auth | `auth.py` | Login, Logout, Refresh, Profil, TOTP 2FA |
| Dashboard | `dashboard.py` | Überstundenkonto, Urlaubskonto, fehlende Buchungen |
| Time Entries | `time_entries.py` | Stempeln, Zeiteinträge CRUD |
| Absences | `absences.py` | Abwesenheiten (Urlaub, Krank, Fortbildung) |
| Vacation Requests | `vacation_requests.py` | Urlaubsanträge stellen |
| Change Requests | `change_requests.py` | Korrekturanträge stellen |
| Journal | `journal.py` | Monatsjournal |
| Reports | `reports.py` | Berichte (Monats-/Jahresreport, ArbZG, PDF/ODS) |
| Holidays | `holidays.py` | Feiertage nach Bundesland |
| Company Closures | `company_closures.py` | Betriebsferien |
| Import XLS | `import_xls.py` | Bulk-Import aus Excel |
| Error Logs | `error_logs.py` | Fehler-Monitoring (Admin) |

## Services

| Service | Datei | Zweck |
|---------|-------|-------|
| `calculation_service.py` | Stunden-Berechnung | Soll/Ist, Überstundenkonto, Jahresabschluss, Urlaubskonto |
| `auth_service.py` | Authentifizierung | Passwort-Hashing, JWT, Token-Validierung |
| `journal_service.py` | Monatsjournal | Tages-Details mit Soll/Ist/Pausen |
| `holiday_service.py` | Feiertage | Feiertags-Berechnung nach Bundesland |
| `timezone_service.py` | Zeitzonen | `today_local()` für korrekte Datumsgrenzen |
| `xls_import_service.py` | Excel-Import | Parsing + ArbZG-Validierung |
| `break_validation_service.py` | Pausenvalidierung | ArbZG §4 Pausenregeln |

## Berechnungsmodell (calculation_service.py)

### Absence-Typ-Matrix

| Absence-Typ | Reduziert Soll? | Zählt als Ist? | Urlaubsabzug? | Zweck |
|---|---|---|---|---|
| **VACATION** | Ja | Nein | Ja | Urlaub |
| **SICK** | Nein | Ja | Nein | Krankheit (§3 EntgFG) |
| **TRAINING** | Nein | Ja | Nein | Fortbildung (außer Haus) |
| **OVERTIME** | Nein | Nein | Nein | Überstundenausgleich |
| **OTHER** | Ja | Nein | Nein | Sonstiges (UNbezahlt) |
| **PAID_LEAVE** | Ja | Nein | Nein | Bezahlte Freistellung (#145, z.B. Betriebsferien wie Feiertag) |

> **PAID_LEAVE vs. OTHER:** rechen-mechanisch identisch (Soll↓, Ist=0, bilanzneutral, kein Urlaubsabzug). Unterschied ist nur die Reporting-Kategorie — PAID_LEAVE ist *bezahlt*, OTHER ist *unbezahlt*. Beide fallen durch den `notin_([TRAINING, SICK, OVERTIME])`-Filter im `calculation_service`; `get_vacation_account` summiert ausschließlich VACATION, daher bleibt das Urlaubskonto bei PAID_LEAVE unberührt.

**Fester Monats-Soll-Modus (Minijob, #377 Baustein 2b):** Opt-in `User.use_fixed_monthly_target` (Migration `065`, Vorbedingung `agreed_monthly_hours > 0` + `track_hours` + `milog_working_time_account`) überschreibt für den betroffenen MA die obige Tages-Summe: das Monats-Soll ist `agreed_monthly_hours` (flach, kalendertag-pro-rata bei Ein-/Austritt) statt der Per-Tag-Summe. Die Absence-Typ-Matrix wird dafür NICHT verändert, sondern per-Modus umgangen: VACATION/PAID_LEAVE und Feiertage schreiben auf einem geplanten Tag (`hours_<wd>`) die geplanten Stunden dem **Ist** gut statt das Soll zu senken (`fixed_month_credit`); OTHER mindert stattdessen das feste **Soll** (`fixed_month_unpaid_reduction`); SICK/TRAINING bleiben unverändert über `credited_absences` (Doppelgutschrift-Guard). Für Nicht-Modus-MA bleibt die Tabelle oben unverändert (byte-identisch). Details: `calculation_service.fixed_monthly_target/fixed_month_credit/fixed_month_unpaid_reduction` + CLAUDE.md `#377`-Regel.

**Eigene Abwesenheitsgründe (`reason_id`, #312):** `Absence.reason_id` (nullable FK → `absence_reasons`) ist ein reines **Label-/Farb-Overlay**. Die Berechnung läuft **ausschließlich** auf `Absence.type`; dieser wird beim Buchen aus dem `base_behavior` des Grundes gesetzt (`BEHAVIOR_TO_ABSENCE_TYPE` in `models/absence.py`: `worked→TRAINING`, `paid_free→PAID_LEAVE`, `overtime_comp→OVERTIME`). Das Calc-Modell bleibt damit eingefroren — **kein** neuer Filter in `get_monthly_target`/`get_overtime_account`/`get_vacation_account`/Exporten/Journal. Reports, die nach `type` aggregieren, zählen einen eigenen Grund in seinen Basis-Typ (v1-Limitierung). **DSGVO Art. 9:** jede Absence mit `reason_id` wird in **beiden** Kollegen-Feeds (`/absences/calendar`, `/absences/team/upcoming`) für Nicht-Admins als `"absent"` maskiert (ein eigener Grund kann sensibel sein, z. B. „Reha") — zusätzlich zu `_MASKED_ABSENCE_TYPES = {SICK, OTHER, PAID_LEAVE}`; Admins/Eigentümer sehen das echte Label.

> **`half_day`-Sondertage bei Betriebsferien (#394):** Fällt ein als `half_day` konfigurierter Sondertag (24./31.12.) in eine Schließung, bucht `_create_closure_absences` nur einen **halben** Tag: `hours = 0,5 × Tagessoll`, `half_day=False` (das Tagessoll wird voll auf 0 gesetzt → kein Rest-Defizit), und der #314-Split verbraucht 0,5 statt 1,0. Die **0,5-Tage-Kosten** kommen zentral über `calculation_service.half_special_day_weight()` in `get_vacation_account.used_days`, `absence_days`, dem `closure_split_service`-Re-Split UND den Urlaubs-Budget-Pre-Checks (absences/admin_vacations/vacation_requests/admin_change_requests) — **eine** Quelle, damit die Regel nie zwischen den Buchungspfaden divergiert. **Byte-identisch** für alle Nicht-Halbtags-Sondertage (Faktor ×1,0). (Direkt-Buchungs-`hours` in `create_absence` sind an einem Halbtags-Sondertag noch nicht faktoriert — rein kosmetisch, der Tage-Count stimmt über den Faktor.)

**Überstundenausgleich-Logik:** An einem Ausgleichstag bleibt das Soll bestehen (z.B. 8h), die Ist-Stunden sind 0h. Dadurch sinkt das kumulative Überstundenkonto um das Tagessoll. Beispiel: 10 Arbeitstage à 9h mit 1 Tag Ausgleich → Soll 80h, Ist 81h, Bilanz +1h.

### Sondertage 24./31.12. (#146, `special_days_service.py`)

24.12. und 31.12. sind pro Praxis (tenant-scoped, in `system_settings`) unabhängig konfigurierbar als `working_day` (Default, abwärtskompatibel) | `half_day` | `free`. Vier Keys: `special_day_dec24_mode`, `special_day_dec24_counts_as_vacation`, `special_day_dec31_mode`, `special_day_dec31_counts_as_vacation` (Bool nur bei `free` relevant). **Keine neue Tabelle/Migration** — der bestehende `system_setting`-Store wird wiederverwendet (Muster wie `holiday_state`).

Die Soll-Berechnung wendet die Regel in allen drei Tages-Schleifen an (`get_monthly_target`, `get_overtime_account`, `get_ytd_summary`), und zwar **nach** Wochenend-/Feiertags-/Absence-Skip (kein Doppelhandling, falls 24./31.12. auf ein Wochenende oder einen Feiertag fällt):
- `working_day` → keine Änderung.
- `half_day` → Tagessoll × 0,5 (über `get_daily_target_for_date()` mit dem per-Tag-Stundenlookup).
- `free` → Tagessoll = 0 (wie ein Feiertag).

**Urlaubsanrechnung bei `free`:**
- `free` + `counts_as_vacation=false` (bezahlte Freistellung): Soll 0, **kein** Urlaubsabzug — allein durch die Soll-Reduktion erledigt.
- `free` + `counts_as_vacation=true` (Urlaub): Soll 0 **und** ein Urlaubstag wird verbraucht. Der Abzug erfolgt nicht-invasiv in `get_vacation_account` (kein generierter Absence-Datensatz): das Tagessoll jedes solchen Datums wird zum verbrauchten Urlaub addiert — außer der MA hat bereits eine echte VACATION-Absence an dem Tag (kein Doppelzählen) oder der Tag liegt außerhalb des Beschäftigungszeitraums; Wochenenden/Feiertage werden in `vacation_deduction_dates_for_year` ausgeschlossen.

### Beschäftigungszeitraum (Eintritt/Austritt, #193)

`_within_employment_window(user, d)` schließt Tage **vor `first_work_day`** und **nach `last_work_day`** vom **Soll** aus — Guard in denselben drei Tages-Schleifen (`get_monthly_target`, `get_overtime_account`, `get_ytd_summary`), konsistent zum Pro-Rata des Urlaubsbudgets. Vor Eintritt / nach Austritt entsteht so kein Stundensoll (vorher wurde ab Jahresbeginn gerechnet → falsches Defizit, Admin- und MA-Ansicht).

Die **Ist-Seite** (`TimeEntry` + gutgeschriebene SICK/TRAINING) wird **ebenfalls** gefenstert (#195): `get_monthly_actual`, `get_overtime_account` und `get_ytd_summary` zählen Stunden nur innerhalb des Beschäftigungszeitraums → ein Eintrag außerhalb (Rehire/Import/nachträglich gesetztes Datum) trägt weder Soll noch Ist bei (`Σ get_monthly_balance == get_overtime_account` bleibt konsistent). Optionaler Tech-Debt: gemeinsamer Per-Tag-Helper, der Soll **und** Ist mit derselben „zählt dieser Tag?"-Entscheidung filtert (löst zugleich die Dreifach-Duplikation der Tages-Schleifen).

### Gemischte Tage (Mixed Days)

Wenn an einem Tag sowohl TimeEntries als auch Absences existieren:
- `day_type = "mixed"`
- `actual_hours = time_hours + credited_sum` (TRAINING/SICK werden gutgeschrieben)
- `target_hours = daily_target - target_reducing_sum` (VACATION/OTHER/PAID_LEAVE reduzieren Soll; OVERTIME lässt Soll bestehen)

### Jahresabschluss (create_year_closing)

1. Berechnet Überstundenkonto zum 31.12. via `get_overtime_account(year, 12)`
2. Berechnet Resturlaub via `get_vacation_account(year)['remaining_days']`
3. Erstellt/überschreibt `YearCarryover(year=year+1)` als Startbilanz fürs Folgejahr
4. Idempotent — mehrmaliges Ausführen liefert gleiche Ergebnisse

### Überstundenkonto (get_overtime_account)

1. Sucht neuesten `YearCarryover` ≤ Berechnungsjahr als Startbilanz
2. Iteriert alle Monate vom Start bis zum Zielmonat
3. Pro Monat: `cumulative += monthly_actual - monthly_target`
4. Carryover wird nur als Startpunkt verwendet, nicht doppelt addiert

### Urlaubskonto (get_vacation_account)

- Budget = `user.vacation_days` + Übertrag (YearCarryover)
- Pro-Rata bei Eintritt/Austritt im laufenden Jahr
- Verbrauch = Summe aller VACATION-Absences im Jahr (PAID_LEAVE wird NICHT mitgezählt, #145) **+** Sondertage 24./31.12. mit `free`+`counts_as_vacation` (#146, nicht-invasiv ohne Absence-Datensatz)
- Konvertierung Tage ↔ Stunden via aktuellem `daily_target`
- **`track_hours=False` (Mitarbeitende ohne Stundenzählung, #191):** `daily_target == 0`, daher **reine Tageszählung** — jede ganztägige VACATION-Absence = 1 Tag, `half_day=True` = 0,5 (#205), ein Halbtags-Sondertag zusätzlich × `half_special_day_weight` (#394), jeder `free`+`counts_as_vacation`-Sondertag = 1 Tag; alle Stunden-Felder bleiben 0, `budget_days` behält Pro-Rata + Carryover. Ersetzt die alte F-046-„nicht anwendbar"-Rückgabe (0 verbraucht / voller Rest), die den tagebasierten Budget-Check aushebelte. Edit-Pfad-Budget-Check tagebasiert (#196 behoben). Offen: Jahresabschluss-Carryover für untracked (#191).

### Arbeitszeit-Blöcke und Kappung (work_window_service.py, ab 1.20.0)

**Datenmodell (Migration 073, ersetzt #201):** Blöcke sind Teil des datierten Vertrags-Snapshots: `working_hours_changes.blocks` (JSON/JSONB, nullable) und `users.work_blocks` (Rückfall nur vor der ersten Verlaufszeile, sonst Spiegel der jüngsten Zeile ≤ heute). Form: Liste aus genau 5 Tagen (Mo–Fr), je `{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int|null}`, höchstens 3 Blöcke, Raster 5 Min. NULL in einer Verlaufszeile = keine Blöcke (nie Rückfall); fünf leere Tage ≡ NULL; `pause_minutes` NULL = Altfenster aus 073 (nur Kappung, „Arbeitszeit-Fenster (Altbestand, nur Kappung)"; ein Ende 23:59 ist dort der Platzhalter eines halboffenen Fensters und kappt nicht). `time_entries` trägt `uncredited_minutes` (INT, Default 0), `credit_override` (BOOL), `auto_closed` (BOOL) und `clamp_grace_minutes` (INT NULL); `change_requests` trägt `request_credit_override` und `original_uncredited_minutes`. Die Spalten `users.scheduled_*` sind entfallen (Guard-Test `test_no_scheduled_columns.py`). Tenant-Setting `work_window_grace_minutes` (Default 15) in `system_settings` bleibt der Puffer.

**Soll:** Neue Blöcke materialisieren beim Speichern `hours_*`, `weekly_hours`, `work_days_per_week`, `use_daily_schedule=True` (`work_blocks_service.derive_targets`); `calculation_service` liest für das Soll nie Blöcke. Blöcke liest ausschließlich `calculation_service.get_schedule_for_date` (`Schedule.blocks`, `Schedule.block_pauses`) → `work_window_service.credit_blocks(db, user, d)` bzw. `get_scheduled_blocks(db, user, d)` (Guard-Test `test_no_live_work_blocks_read.py`). `credit_blocks` unterscheidet die zwei Bedeutungen von „keine Blöcke“: `None` = der Tag wird nicht gekappt (Wochenende, Feiertag, `free`-Sondertag, keine Blöcke im Snapshot, Altzeile aus Migration 073), `[]` = Werktag ohne Blöcke in einer Woche des Blockmodells (laut Vertrag frei, 0 h bis zur Anerkennung; bis 1.20.3 zählte Arbeit dort voll). `get_scheduled_blocks` liefert für beide Fälle `[]` und dient nur der Anzeige und den Lückentexten – Kappungsentscheidungen lesen `credit_blocks`.

**Clamp (`clamp(db, user, d, start, end, grace, *, credit_override, wh_changes=None, soll_free_dates=None)` → `ClampResult(eff_start, eff_end, raw_start, raw_end, uncredited_minutes, grace_minutes)`):**
1. `credit_blocks` → `None` (Wochenende, Feiertag, `free`-Sondertag, keine Blöcke im Snapshot, Altzeile aus 073), `track_hours=False` oder `credit_override` → unverändert, `uncredited_minutes` 0, `grace_minutes` None.
   `credit_blocks` → `[]` (Werktag ohne Blöcke in einer Woche des Blockmodells) → geschlossener Eintrag kollabiert auf den Beginn (Beginn = Ende, 0 h, Rohstempel bleiben), `grace_minutes` gesetzt; ein offener Eintrag behält seinen Beginn. Angerechnet wird erst mit `credit_override`.
2. Hülle `[erster Block − g, letzter Block + g]`: Beginn/Ende außerhalb werden verschoben, die Rohwerte stehen in `raw_start_time`/`raw_end_time` (§16); ganz außerhalb → Kollaps auf 0 h.
3. Lücken zwischen den Blöcken, um g an beiden Rändern geschrumpft (`credit_gaps`); ihre Überlappung mit dem Eintrag ist `uncredited_minutes` (je Lücke: `gap_segments`). Ein Beginn in der Lücke wird nie verschoben. Offene Einträge tragen 0 (Lücken zählen erst mit dem Ende).
4. `net_hours` = max(0, Ende − Beginn − Pause − `uncredited_minutes`) (Hybrid-Property, Python und SQL).

`clamp_applies` (XLS-Gate) fragt, ob `clamp` an einem Tag überhaupt kappt; `not_credited_minutes`/`presence_minutes` liefern „nicht angerechnet" (Lücke **plus** an der Hülle abgeschnittene Zeit) und die Anwesenheit laut Stempel. Ein automatisch geschlossener Eintrag (`auto_closed`) trägt das synthetische Rohende 23:59 (`AUTO_CLOSE_RAW_END`): Anwesenheit zählt nur bis zum wirksamen Ende, die Endseite zählt nicht als „nicht angerechnet", und anerkennen lässt er sich erst, wenn ein tatsächliches Ende eingetragen ist. Jedes eingetragene Ende, das vom wirksamen Ende abweicht – auch 23:59 –, ist ein tatsächliches Ende und hebt das Kennzeichen auf (`end_is_correction`); nur wo das wirksame Ende selbst 23:59 ist (nicht gekappt), bleibt ein zurückgeschicktes 23:59 ein Echo. Bei der Genehmigung eines Antrags ist zusätzlich das wirksame Ende zum Zeitpunkt des Antrags (`change_requests.original_end_time`) ein Echo, auch wenn eine Neukappung das wirksame Ende seither geändert hat: `work_window_service.request_end_for_approval` bildet es vor Vorprüfung (`lacks_actual_end`), `end_input_for` und `end_is_correction` auf das aktuelle wirksame Ende ab.

**Puffer-Herkunft:** Neuanlage → `get_grace_minutes(db, tenant_id)`; Einzel-Neukappung eines gespeicherten Eintrags → `grace_for_entry(db, entry)` (gespeicherter `clamp_grace_minutes`, sonst aktueller Puffer); Massen-Neukappung → aktueller Puffer, neu geschrieben. Jede schreibende Stelle setzt `clamp_grace_minutes = r.grace_minutes`, wenn nicht None.

**Schreibpfade (vollständig; jeder Pfad, der Einträge anlegt, ändert oder anerkennt, nimmt `lock_user_row` als erste Sperre – Löschen kappt nicht und ist ausgenommen, `create_change_request` schreibt keinen Eintrag):**

| Pfad | Wo gekappt |
|------|-----------|
| `clock_in` | Beginn (Hülle); Hinweis bei Einstempeln in der Lücke |
| `clock_out` | Ende, `uncredited_minutes`, Puffer des offenen Eintrags (`grace_for_entry`) |
| `_close_stale_entry` (Auto-Close) | Ende 23:59 über `clamp`, `auto_closed=True`; der Aufrufer hält die Sperre |
| `create_time_entry` / `update_time_entry` | MA-CRUD; `update` kappt auch bei Datumswechsel neu (Datum ändern nur die Verwaltung, #502); anerkannter Eintrag → 409 für Mitarbeitende; fremde/unbekannte ID → 404 vor jeder Sperre |
| `admin_time_entries` create + update | Admin-CRUD; `credit_override` bleibt |
| `xls_import_service` | Vorschau + Ausführung (`clamp_applies`; Auto-Pause je Tag nur für den von Lücken und Abständen ungedeckten §4-Rest, je Zeile höchstens deren angerechnete Minuten, `_day_break_minutes`; §3/§4/§5 und Tages-Anwesenheitshinweise der Vorschau je Tag, §5 auch bis zu einem nur vom Bestand getragenen Folgetag; Zeilen mit Ende ≤ Beginn ersetzen keinen Bestand; abweichende Pause ohne „überschreiben" → Ergebnis-Hinweis) |
| `admin_change_requests.review_change_request` | CR-Genehmigung (CREATE/UPDATE, auch Bulk), „Genehmigen und anerkennen" (`grant_credit_override`) |
| `change_requests.create_change_request` | prüft mit `clamp` (Puffer des Eintrags bzw. aktueller Puffer), speichert den Vorschlag roh und schreibt keinen Eintrag; `request_credit_override`, `original_uncredited_minutes` |
| `work_window_service.reclamp_time_entries` | Massen-Neukappung einer Arbeitszeit-Änderung (über `wh_change_service.run_change`, Router `admin_users`); flusht jeden neuen Beginn sofort (Unique-Index `uq_tenant_user_date_start` ist nicht verzögerbar) |
| `POST /api/admin/time-entries/{id}/credit-override` | Anerkennen (`credit_override_service.apply_credit_override`): Rohzeiten werden wirksam, keine Kappung mehr; offen oder `auto_closed` → 400, Beginn schon belegt → 409 |

**Ausnahmen:** `track_hours=False` → kein Clamp; `exempt_from_arbzg` (§18) → Clamp greift trotzdem; `credit_override` → nie gekappt, überlebt jede Neuberechnung.

**ArbZG:** §3/§4 hart auf angerechneter Zeit (`validate_daily_break(…, uncredited_segments=…, tenant_id=…)`, Lückensegmente ≥ 15 Min zählen als Pausenabschnitt); weiche `PRESENCE_DAILY_HOURS`/`PRESENCE_BREAK`/`PRESENCE_WEEKLY_HOURS` auf `presence_minutes`, dazu `BREAK_IN_GAP` (`presence_service.py`); §5 auf den Rohstempeln.

**Rückwirkung:** `POST /api/admin/users/{id}/working-hours-changes` (dazu `…/preview`, `…/{change_id}/delete-preview`, `DELETE …/{change_id}`) läuft in einer Transaktion unter `lock_user_row` (`wh_change_service.run_change`, ein Rechenpfad für Anlegen, Löschen und beide Vorschauen): offene Alteinträge schließen, `reclamp_time_entries` (nur geänderte Wochentage, ab Rohstempel), `retarget_absence_hours` (mit F1-Klemmung), Klassifikation Verlängerung/Verkürzung (Eintrag, Saldo, Gutschrift), Schutzpaket (`retroactive_reason_type`, `retroactive_reason_text`, `wage_risk_confirmed`, bei „sonstiges" zusätzlich `other_reason_risk_confirmed`; in abgeschlossene Jahre gesperrt), Protokoll `wh_reclamp` je Eintrag plus Sammelzeile (`reclamp_audit.summary_note`/`parse_summary_note`). Die Vorschau rollt zurück und protokolliert nie. Notiz und Begründung landen zusammen in `working_hours_changes.note` (höchstens 500 Zeichen, `reclamp_audit.NOTE_MAX_LENGTH`; bei der Anonymisierung geleert).

**Löschen und Zurücksetzen:** Die Oberfläche bietet das Löschen nur an der jüngsten Verlaufszeile an; serverseitig ist die früheste Zeile gesperrt, solange spätere existieren (`_earliest_row_lock_detail`). Verkürzt das Löschen, nennt die `delete-preview` einen `reset_body` („ab ‹Datum› auf den vorherigen Stand zurücksetzen", angelegt als neue Zeile mit `reset_of_change_id`) oder verlangt das Schutzpaket im Body des DELETE (rückwirkendes Löschen). Liegt inzwischen eine Zeile zwischen der zurückgesetzten Zeile und dem Rücksetzungsdatum oder passt der Body nicht mehr zum Vorgänger-Snapshot, antwortet das Anlegen mit 409 `RESET_CONFLICT_DETAIL` („Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.").

**Mitarbeitende:** `GET /api/auth/me/work-schedule` (`work_schedule_service`) zeigt die heute gültigen Blöcke und den Verlauf; das Dashboard trägt `schedule_change_notices` (`reclamp_audit.schedule_change_notices`: jede Sammelzeile der letzten 30 Tage, ohne Bestätigungstabelle) — ein Hinweis zu jeder Arbeitszeit-Änderung.

**Services-Einträge:**

| Service | Datei | Zweck |
|---------|-------|-------|
| `work_window_service.py` | Arbeitszeit-Blöcke | `clamp()`, Lücken, Puffer je Eintrag, „nicht angerechnet", Anwesenheit, Neukappung |
| `work_blocks_service.py` | Arbeitszeit-Blöcke | JSON-Form parsen/serialisieren, `derive_targets` |
| `wh_change_service.py` | Rückwirkung | `run_change`: Schritte 2–7 für Anlegen, Löschen und Vorschauen; Klassifikation, Schutzpaket-Prüfung |
| `credit_override_service.py` | Anerkennen | `apply_credit_override` für die Admin-Aktion und „Genehmigen und anerkennen"; weiche Warnungen danach |
| `presence_service.py` | ArbZG | weiche Anwesenheits-Warnungen `PRESENCE_*`, `BREAK_IN_GAP` |
| `reclamp_audit.py` | Protokoll | Sammelzeile schreiben/lesen, Grundtypen `REASON_TYPES`, Dashboard-Hinweise |
| `work_schedule_service.py` | Profil | eigene Arbeitszeit (heute + Verlauf) für Mitarbeitende |

## Wichtige Patterns

- **`get_weekly_hours_for_date(db, user, date)`** — Immer pro Tag aufrufen, nie `user.weekly_hours` direkt (historische Änderungen!)
- **`get_schedule_for_date(db, user, date)`** (#431) — DIE Auflösung des vollständigen Vertrags-Snapshots (Wochenstunden, Modus, Tageswerte, Arbeitstage, ab 1.20.0 auch Blöcke und Pause innerhalb der Blöcke) für ein Datum; `get_weekly_hours_for_date` ist nur noch ein dünner Wrapper darüber. `get_daily_target_for_date(user, date, schedule)` verlangt diesen Snapshot als Pflichtparameter — nie `user.use_daily_schedule`/`user.hours_monday…friday` live lesen. **Benannte Ausnahme (Fix-Welle 4 #6):** die „tägl. Std:"-Ecke des KLASSISCHEN Jahresberichts (`export_service._create_employee_classic_sheet`, ausdrücklich als Legacy-Format geführt) liest dort bewusst live — eine informative Ecke, kein Soll/Ist-Wert; bei Moduswechsel im Berichtsjahr zeigt sie den heutigen statt den historischen Tagesplan (akzeptiert, kommentiert im Code). Keine weiteren Ausnahmen.
- **Zeiteintrag schreiben (ab 1.20.0):** `lock_user_row` zuerst, dann `clamp(…, credit_override=…)` mit dem richtigen Puffer (`get_grace_minutes` bei Neuanlage, `grace_for_entry` bei gespeicherten Einträgen), `uncredited_minutes`/`clamp_grace_minutes` übernehmen, Netto-Helfer (`_calculate_daily/weekly_net_hours`) und `validate_daily_break` mit den Lückenwerten. Nie `users.work_blocks` oder Altfelder `scheduled_*` lesen.
- **Pydantic Response-Schemas:** `float` statt `Decimal` (JSON-Serialisierung)
- **RLS-Kontext:** Bei neuen Endpoints immer `set_tenant_context(db, tid)` aufrufen
- **Bulk-Deletes:** `synchronize_session=False` + expliziter `tenant_id`-Filter

## Änderungsanträge (Change Requests)

### Approval-Reihenfolge (admin_change_requests.py)

1. **Precondition-Checks** (VOR Status-Änderung):
   - CREATE: Duplikat-Prüfung (user + date + start_time)
   - UPDATE: Entry-Existenz + Unique-Constraint bei Datumsänderung
   - DELETE: Entry-Existenz
2. **Status auf APPROVED setzen** (nur wenn alle Checks bestanden)
3. **Änderung anwenden** (Entry erstellen/updaten/löschen + Audit-Log)
4. **db.commit()**

### Validierung (change_requests.py)

- CREATE/UPDATE: Nur vergangene Tage, Endzeit > Startzeit
- Arbeitszeitraum-Prüfung (first/last_work_day)
- ArbZG §4 Pausenvalidierung, §3 Tagesarbeitszeit-Limit
