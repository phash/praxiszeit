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
- **`track_hours=False` (Mitarbeitende ohne Stundenzählung, #191):** `daily_target == 0`, daher **reine Tageszählung** — jede VACATION-Absence = 1 Tag, jeder `free`+`counts_as_vacation`-Sondertag = 1 Tag; alle Stunden-Felder bleiben 0, `budget_days` behält Pro-Rata + Carryover. Ersetzt die alte F-046-„nicht anwendbar"-Rückgabe (0 verbraucht / voller Rest), die den tagebasierten Budget-Check aushebelte. Halbtage sind ohne Stundenzählung nicht erkennbar → zählen als voller Tag. Edit-Pfad-Budget-Check tagebasiert (#196 behoben). Offen: Jahresabschluss-Carryover für untracked (#191).

## Wichtige Patterns

- **`get_weekly_hours_for_date(db, user, date)`** — Immer pro Tag aufrufen, nie `user.weekly_hours` direkt (historische Änderungen!)
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
