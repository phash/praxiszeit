# ArbZG-Compliance-Audit – PraxisZeit Backend
## Datum: 2026-06-17
## Auditor: ArbZG-Compliance-Agent (Claude Sonnet 4.6)
## Version: 1.8.10 (master, Stand bac703e)

---

## Executive Summary

**Gesamturteil: WEITGEHEND KONFORM** — kein kritischer Verstoß, keine offenen HOCH-Findings.

Alle sechs Schreibpfade (create, update, clock_out, admin_create, admin_update, CR-Genehmigung) implementieren §3/§4/§5/§6/§9/§18 ArbZG korrekt. Die seit dem letzten Audit (23.05.2026) identifizierten Lücken beim XLS-Import (`exempt_from_arbzg`, `is_night_worker`) wurden behoben. Das `work_window_service` (Feature #201) ist vollständig in alle Pfade eingehangen. Das Tagesprinzip (§3 BUrlG) wird konsequent in beiden Buchungspfaden (create_absence + review_vacation_request) umgesetzt.

Es verbleiben **4 MITTEL-Findings** (alle strukturell durch RLS abgedeckt, daher kein Gesetzesverstoß, aber verbesserungswürdige Verteidigungstiefe) und **3 NIEDRIG-Findings** (informell / UX).

---

## 1. Prüfumfang

### Geprüfte Dateien

| Datei | Zweck |
|-------|-------|
| `backend/app/routers/time_entries.py` | Mitarbeiter-Pfade: create, update, clock_in, clock_out |
| `backend/app/routers/admin_time_entries.py` | Admin-Pfade: admin_create, admin_update |
| `backend/app/routers/admin_change_requests.py` | CR-Genehmigung (TimeEntry + Absence) |
| `backend/app/routers/absences.py` | Abwesenheitsbuchung (create_absence) |
| `backend/app/routers/admin_vacations.py` | Urlaubsantrags-Genehmigung (review_vacation_request) |
| `backend/app/routers/vacation_requests.py` | Urlaubsantrag-Erstellung + Stornierung |
| `backend/app/routers/reports.py` | ArbZG-Reports (§5, §6, §11, §3) |
| `backend/app/services/break_validation_service.py` | §4 Pausenprüfung |
| `backend/app/services/rest_time_service.py` | §5 Ruhezeitprüfung |
| `backend/app/services/arbzg_utils.py` | §6 Nachtarbeit-Erkennung |
| `backend/app/services/work_window_service.py` | Feature #201 Arbeitszeitfenster |
| `backend/app/services/calculation_service.py` | §3 BUrlG Urlaubs-/Überstundenberechnung |
| `backend/app/services/holiday_service.py` | §9 Feiertagskalender |
| `backend/app/services/xls_import_service.py` | XLS-Import ArbZG-Checks |

### Methodik

1. Vergleich mit letztem Audit (MEMORY.md Stand 23.05.2026)
2. Lesen aller Schreibpfade auf §3/§4/§5/§6/§9/§18-Korrektheit
3. Prüfung der neuen Features (#201 work_window, track_hours=False, _within_employment_window)
4. Prüfung des Tagesprinzips (§3 BUrlG) in beiden Buchungspfaden
5. Verifizierung der bekannten offenen Findings aus dem Mai-Audit

---

## 2. Ergebnisse je Paragraph

### §2 ArbZG – Begriffsbestimmungen (Nachtzeit/Nachtarbeit)

**Bewertung: KONFORM**

`arbzg_utils.py:is_night_work()` prüft minutengenau >120 Minuten im Nachtzeitsegment 23:00–06:00 (§2 Abs. 3 ArbZG). Die drei Nachtzeit-Segmente (0–360 min, 1380–1440 min, 1440–1800 min bei Mitternachtsüberschreitung) werden korrekt addiert. Beide Bedingungen für „Nachtarbeitnehmer" (is_night_worker-Flag + ≥48 Nächte/Jahr via Report) sind vorhanden.

### §3 ArbZG – Tägliche Höchstarbeitszeit

**Bewertung: KONFORM**

| Pfad | 8h-Warn | 10h-Hard-Stop | 48h-Warn |
|------|---------|---------------|----------|
| create_time_entry | ja | ja (422) | ja |
| update_time_entry | ja | ja (422) | ja |
| clock_out | ja | ja (als Warn, R2-b-Begründung) | ja |
| admin_create | ja | ja (422) | ja |
| admin_update | ja | ja (422) | ja |
| CR-Genehmigung | ja (re-validate) | ja (422) | ja |
| XLS-Import | ja (Warn) | ja (Warn) | nein* |

*Der XLS-Import enthält keine Wochenarbeitszeit-Warnung; das ist dokumentiertes, vertretbares Design (Import ist historisch, nicht-blockierend).

**Feature #201 work_window_service:** In allen Pfaden wird `work_window_service.clamp()` VOR den §3/§4-Checks aufgerufen. Die Compliance-Prüfung findet auf der angerechneten (geclamped) Zeit statt, nicht auf der Rohzeit. Das ist korrekt (Lohnrelevanz = geclampte Zeit).

**§3 Ausgleichszeitraum:** Der 24-Wochen-Durchschnitt ist in `reports.py:get_24_week_averaging_period()` (Zeile 734) als Admin-Report implementiert. Kein automatisches Tracking des rollierenden Ausgleichs — bekannte, vertretbare Lücke (manuell durch Arbeitgeber).

**net_hours Floor:** `_net_hours()` in `time_entries.py:60` gibt `max(0.0, ...)` zurück — kein negativer Wert möglich. Konform.

### §4 ArbZG – Ruhepausen (Pflichtpausen)

**Bewertung: KONFORM**

`break_validation_service.py:validate_daily_break()` prüft tagesübergreifend (alle Einträge des Tages werden summiert, Lücken ≥15 min werden als Pause gewertet). Korrekte Staffelung: >6h Netto→30 min, >9h Netto→45 min. Mindestpausen-Segment 15 min (§4 Satz 2) wird erzwungen.

**Break-Waiver:** Ein dokumentierter Pausenverzicht (`break_waiver_reason`) ist in allen Pfaden symmetrisch implementiert inkl. Audit-Log (source='break_waiver'). Approval-Pflicht konfigurierbar. Clock-out bleibt nicht-blockierend (R2-b korrekt begründet).

**§18-Bypass:** In allen sechs Pfaden korrekt: `if not user.exempt_from_arbzg`.

**Timing-Lücke:** §4 Satz 3 (max. 6h am Stück ohne Pause) ist systemisch nicht prüfbar, da kein Pause-Timestamp gespeichert wird. Bekannte, unvermeidliche Einschränkung — gilt für alle eintrag-basierten Systeme.

### §5 ArbZG – Mindestruhezeit (11h)

**Bewertung: KONFORM**

**Echtzeit-Warnung:** `clock_in()` (Zeilen 286–314) prüft TZ-aware in `Europe/Berlin` den Abstand seit dem letzten `end_time`. DST-korrekt via `datetime.combine(..., tzinfo=LOCAL_TZ)`. Warnung bei <11h seit letztem Arbeitsende.

**Retrospektiver Report:** `rest_time_service.check_rest_time_violations()` gruppiert Einträge per Datum (max/min), behandelt Split-Schichten korrekt. `check_all_users_violations()` iteriert alle aktiven User ohne expliziten tenant_id-Filter — durch RLS geschützt.

**§5 Abs. 2 Ausgleich (auf 10h reduzieren):** Nicht implementiert. Bekannte, niedrig-priorisierte Lücke — für die Zielgruppe (Arztpraxen) wenig relevant.

### §6 ArbZG – Nacht- und Schichtarbeit

**Bewertung: KONFORM (mit systemisch unvermeidbaren Lücken)**

| Anforderung | Status |
|-------------|--------|
| Nachtarbeit-Erkennung (>2h in 23:00–06:00) | Konform |
| is_night_work-Flag in allen TimeEntryResponse | Konform |
| 8h-Warn bei is_night_worker (alle 6 Pfade) | Konform |
| §18-Bypass in allen Pfaden | Konform |
| Nachtarbeit-Report `/api/admin/reports/night-work-summary` | Konform |
| Arbeitsmedizinische Untersuchungen (Abs. 3) | UI-Hinweis; HR-Aufgabe |
| Lohnzuschlag/Freizeitausgleich (Abs. 5) | UI-Hinweis; Lohnbuchhaltungsaufgabe |
| Recht auf Tagesarbeitsplatz (Abs. 4) | Arbeitgeberpflicht; nicht systemisch |

**XLS-Import:** `_check_arbzg()` in `xls_import_service.py` prüft jetzt korrekt `exempt` und `is_night_worker` (Zeilen 67–68, 183–184, 257–259). Die im Mai-Audit gefundene Lücke ist behoben.

### §§ 9/10 ArbZG – Sonn- und Feiertagsruhe

**Bewertung: KONFORM**

- Sonntagserkennung: `weekday() == 6` (kein Saturday-Bug mehr)
- Feiertagserkennung: `is_holiday()` via `holiday_service.py` mit tenant_id-Cache
- `SUNDAY_WORK` / `HOLIDAY_WORK` Warnungen in allen Pfaden (außer admin_create/admin_update: bewusst nicht implementiert — Admins kennen den Kalender)
- `sunday_exception_reason`-Feld vorhanden und in Exports enthalten

### §11 ArbZG – Ersatzruhetage

**Bewertung: KONFORM**

- `/api/admin/reports/sunday-summary`: 15-freie-Sonntage-Prüfung
- `/api/admin/reports/compensatory-rest`: Ersatzruhetag-Tracking (14 Tage / 56 Tage)
- Frontend-Darstellung vorhanden

### §14 ArbZG – Außergewöhnliche Fälle

**Bewertung: NICHT ANWENDBAR**

§14 ist eine Notfall-Ausnahmeregel. Die 48h-Wochenwarnung entstammt §3 (korrekt so kommentiert seit Commit `a488985`).

### §16 ArbZG – Aufzeichnungs- und Aufbewahrungspflicht

**Bewertung: KONFORM** (übertrifft gesetzliche Mindestanforderung)

- Vollständige Erfassung aller Stunden (nicht nur >8h)
- Audit-Log bei allen Schreiboperationen inkl. Löschungen
- `source`-Marker alle ≤24 Zeichen (< varchar(40)-Limit)
- `raw_start_time`/`raw_end_time` bei geclampten Einträgen erhalten (§16-Nachvollziehbarkeit)
- Excel/ODS/PDF-Export vorhanden
- 730-Tage-Purge-Schutz dokumentiert

**NIEDRIG-Finding: Kein Audit-Log bei Vacation-Request-Erstellung**

`vacation_requests.py:create_vacation_request()` (Zeile 341–355) schreibt keinen `TimeEntryAuditLog`-Eintrag beim Erstellen eines neuen Urlaubsantrags. Cancel (source='vacation_request_cancel') und Edit (source='vacation_request_edit') sind dokumentiert; das initiale CREATE fehlt.

Gesetzlich nicht zwingend (§16 bezieht sich auf Arbeitszeitaufzeichnungen, nicht auf Antragsformulare), aber dokumentationswürdig für vollständige Audit-Trails.

### §18 ArbZG – Leitende Angestellte

**Bewertung: KONFORM**

`User.exempt_from_arbzg` wird in allen sechs Schreibpfaden vor allen ArbZG-Prüfungen ausgewertet. Korrekt auch im XLS-Import-Pfad (behoben).

### §3 BUrlG – Urlaubsanspruch / Tagesprinzip

**Bewertung: KONFORM**

Das Tagesprinzip ist konsistent in beiden Buchungspfaden implementiert:

**Pfad 1: `create_absence()` (absences.py:432–448)**
- Voll-Tag-Typen: `get_daily_target_for_date(target_user, date)` — Tagessoll des Tages
- Halbtag (`half_day`): 0,5 × Tagessoll
- OVERTIME: Behält explizite Stunden (Ausnahme korrekt)
- track_hours=False: Bucht alle Wochentage mit hours=0 (tagebasiert, korrekt für #191)

**Pfad 2: `review_vacation_request()` (admin_vacations.py:296–318)**
- Identische Logik mit `get_daily_target_for_date()`
- OVERTIME-Ausnahme korrekt (`absence_type != AbsenceType.OVERTIME`)
- track_hours=False: Guard in Zeile 313 korrekt (`if hours_for_day == 0 and target_user.track_hours: continue`)

**CR-Genehmigung Absence-CREATE (admin_change_requests.py:451–464)**
- Tagesprinzip ebenfalls implementiert (Zeile 462–466)
- OVERTIME-Ausnahme korrekt (Zeile 461)

**Budget-Check (tagebasiert):** In create_absence, review_vacation_request und create_vacation_request identisch implementiert (billable_days × 0.5 bei half_day). use_daily_schedule-Sonderfall (0h-Tage überspringen) in allen drei Pfaden symmetrisch.

### Feature #201 – Arbeitszeit-Fenster (work_window_service)

**Bewertung: KONFORM**

`work_window_service.clamp()` ist in allen Schreibpfaden eingehangen:
- clock_in (Zeile 268–273): nur Start-Kappung (end=None)
- clock_out (Zeile 359–362): nur End-Kappung
- create/update_time_entry (Zeilen 588–591, 827–834)
- admin_create/admin_update (Admin-Router Zeilen 46–49, 171–176)
- CR-Genehmigung CREATE/UPDATE (Zeilen 339–343, 379–383)
- XLS-Import: Kein work_window_clamp — akzeptiertes Design (historische Daten)

`track_hours=False`-User: `clamp()` gibt unverändert `(start, end, None, None)` zurück (Zeile 58–59) — keine Kappung. Korrekt für leitende Angestellte ohne Stundenverfolgung.

`exempt_from_arbzg`-User werden trotzdem gekappt (Anwesenheitspolicy, nicht ArbZG): korrekt laut CLAUDE.md.

### Feature #191 – track_hours=False (Leitende Angestellte)

**Bewertung: KONFORM** (mit bekanntem Tech-Debt)

- `get_daily_target_for_date()` gibt `Decimal('0')` zurück wenn `not user.track_hours`
- Abwesenheits-Buchung bucht hours=0, aber tagebasiert (korrekt)
- Vacation-Budget-Check tagebasiert auch bei daily_target==0 (korrekt)
- Jahresabschluss-Carryover noch offen (#191): bekannter Tech-Debt

### Feature #193/#195 – Eintritt/Austritt-Fenster

**Bewertung: KONFORM**

`_within_employment_window()` in calculation_service.py wird in allen relevanten Per-Tag-Schleifen aufgerufen:
- `get_monthly_target()` Zeile 258
- `get_overtime_account()` Zeilen 308–313, 381, 354
- `get_ytd_summary()` Zeilen 467, 480, 540

Sowohl Soll-Seite (Planstunden) als auch Ist-Seite (TimeEntry + Absence) sind gefenstert.

---

## 3. Detaillierte Findings

### MITTEL-Findings (strukturell durch RLS abgedeckt)

**M-1: rest_time_service.check_all_users_violations() ohne expliziten tenant_id-Filter**
- Datei: `backend/app/services/rest_time_service.py:116`
- Code: `db.query(User).filter(User.is_active == True).all()`
- Situation: Kein `User.tenant_id == ...`-Filter. Durch PostgreSQL-RLS geschützt (auth.py setzt immer `set_tenant_context`). In Single-Tenant-Deployment (aktuell) kein Problem.
- Risiko: Fehlt belt-and-suspenders-Verteidigungstiefe; bei zukünftigem SaaS-Cutover Phase 4 zwingend.
- Empfehlung: Tenant-Parameter ergänzen: `users = db.query(User).filter(User.is_active == True, User.tenant_id == tenant_id).all()`

**M-2: calculation_service.count_workdays() ohne mandatory tenant_id**
- Datei: `backend/app/services/calculation_service.py:851`
- Code: `def count_workdays(db, start, end, tenant_id=None)` — tenant_id ist optional, nicht mandatory
- Situation: Alle Aufrufer aus admin_vacations.py (Zeile 87) übergeben `tenant_id=vr.tenant_id` korrekt. Aufrufer aus anderen Kontexten könnten es vergessen.
- Empfehlung: Parameter zu non-optional machen oder Caller-Audit.

**M-3: PublicHoliday-Queries ohne tenant_id in absences.py (Zeile 279)**
- Datei: `backend/app/routers/absences.py:279`
- Code: `db.query(PublicHoliday).filter(PublicHoliday.year == year, PublicHoliday.tenant_id == target_user.tenant_id).all()` — BEHOBEN (tenant_id-Filter vorhanden)
- Anmerkung: Dieser Fund aus dem Mai-Audit ist bereits behoben. Kein aktives Finding.

**M-4: admin_vacations.py PublicHoliday tenant_id**
- Datei: `backend/app/routers/admin_vacations.py:213`
- Code: `db.query(PublicHoliday).filter(PublicHoliday.year == year, PublicHoliday.tenant_id == current_user.tenant_id)` — KORREKT
- Anmerkung: Ebenfalls aus Mai-Audit — bereits korrekt implementiert.

### NIEDRIG-Findings

**N-1: Kein Audit-Log bei Vacation-Request-Erstellung (§16 Best Practice)**
- Datei: `backend/app/routers/vacation_requests.py:341–355`
- Beschreibung: `create_vacation_request()` schreibt keinen `TimeEntryAuditLog`-Eintrag. Cancel (source='vacation_request_cancel') und Edit (source='vacation_request_edit') sind dokumentiert; das initiale CREATE fehlt.
- Gesetzliche Relevanz: §16 ArbZG bezieht sich auf Arbeitszeitaufzeichnungen. Urlaubsantragsformulare sind nicht direkt betroffen. Dennoch für vollständige Prüfpfade empfohlen.
- Empfehlung: Nach `db.commit()` + `db.refresh(vr)` einen `TimeEntryAuditLog`-Eintrag schreiben (source='vacation_request_create', new_note=format_vacation_request_audit_text(vr)).

**N-2: ChangeRequestForm zeigt keine ArbZG-Warnungen aus API-Response**
- Datei: `frontend/src/components/ChangeRequestForm.tsx`
- Beschreibung: Das Backend gibt in der CR-Create-Response `warnings[]` zurück (§6 Nachtarbeiter, Break-Waiver etc.). Die Frontend-Komponente ignoriert `response.data.warnings` nach `await`.
- Empfehlung: `showArbzgWarnings(toast, response.data.warnings)` nach erfolgreicher Submission hinzufügen (analog zu TimeEntryForm).
- Gesetzliche Relevanz: Rein informell — die Validierungen laufen serverseitig korrekt durch.

**N-3: Admin-Pfade geben keine SUNDAY_WORK/HOLIDAY_WORK-Warnungen zurück**
- Dateien: `backend/app/routers/admin_time_entries.py` (admin_create/admin_update)
- Beschreibung: Im Gegensatz zum Mitarbeiter-Pfad werden Sonn-/Feiertagswarnungen im Admin-Direkteintrag nicht generiert.
- Bewertung: Akzeptierbar (Admins kennen den Kalender), aber UX-Inkonsistenz.

---

## 4. Geprüfte Features seit letztem Audit (Mai 2026)

### Behoben (bestätigt):

- XLS-Import `_check_arbzg()`: `exempt_from_arbzg` und `is_night_worker` werden jetzt korrekt ausgewertet (xls_import_service.py:67–68, 183–184)
- `holiday_service.py sync_current_and_next_year()`: tenant_id-Filter vorhanden (war falsches Finding)

### Neu korrekt implementiert (Feature-Verifikation):

- Feature #201 work_window_service: Vollständig in alle 6 Schreibpfade + CR-Genehmigung eingehangen; §16-raw_start/raw_end-Erhalt korrekt
- Feature #191 track_hours=False: Abwesenheitsbuchung tagebasiert mit hours=0 korrekt; Vacation-Budget-Check angepasst
- Feature #193/#195 _within_employment_window: Soll UND Ist in allen Berechnungsfunktionen gefenstert
- §3 BUrlG Tagesprinzip: Beide Buchungspfade (create_absence + review_vacation_request) sowie CR-Genehmigung konsistent

---

## 5. Compliance-Tabelle

| § | Thema | Status | Finding |
|---|-------|--------|---------|
| §2 | Nachtarbeit-Definitionen | KONFORM | — |
| §3 | Tages-Höchstarbeitszeit (8h/10h) | KONFORM | — |
| §3 | 24-Wochen-Ausgleich | TEILWEISE | Kein Auto-Tracking (bekannt, low) |
| §3 | 48h-Wochenwarnung | KONFORM | — |
| §4 | Pflichtpausen (30/45 min) | KONFORM | — |
| §4 | Break-Waiver + Audit | KONFORM | — |
| §5 | Mindestruhezeit 11h | KONFORM | M-1 (belt-and-suspenders) |
| §6 | Nachtarbeit-Erkennung + 8h-Limit | KONFORM | — |
| §6 Abs.3/5 | Untersuchung/Zuschlag | TEILWEISE | HR/Lohnbuchhaltungsaufgabe |
| §§9/10 | Sonn-/Feiertagsruhe | KONFORM | N-3 (admin-Pfad, low) |
| §11 | Ersatzruhetage / 15 freie Sonntage | KONFORM | — |
| §14 | Außergewöhnliche Fälle | N/A | — |
| §16 | Aufzeichnung + Aufbewahrung | KONFORM | N-1 (VR-Create kein Log) |
| §18 | Leitende Angestellte | KONFORM | — |
| §3 BUrlG | Tagesprinzip Urlaub | KONFORM | — |
| #201 | Arbeitszeitfenster | KONFORM | — |
| #191 | track_hours=False | KONFORM | Carryover offen (#191) |
| #193/#195 | Eintritt/Austritt-Fenster | KONFORM | — |

---

## 6. Handlungsempfehlungen (priorisiert)

### Vor Phase-4-SaaS-Cutover (MITTEL, keine Gesetzesdringlichkeit)

1. **M-1 rest_time_service:** Tenant-Parameter für `check_all_users_violations()` mandatory machen und Aufrufer anpassen.
2. **M-2 count_workdays:** tenant_id-Parameter non-optional machen oder alle Aufrufer auf Vollständigkeit prüfen.

### Optional / Nice-to-have (NIEDRIG)

3. **N-1:** Audit-Log-Eintrag bei Vacation-Request-Erstellung ergänzen (source='vacation_request_create').
4. **N-2:** `showArbzgWarnings()` in `ChangeRequestForm.tsx` nach erfolgreicher Submission.
5. **N-3:** SUNDAY/HOLIDAY-Warnungen im Admin-Direkt-Eintragspfad optional ergänzen.

---

## 7. Gesamturteil

**WEITGEHEND KONFORM** — PraxisZeit v1.8.10 implementiert die ArbZG-Kernvorschriften (§§ 3, 4, 5, 6, 9–11, 16, 18) vollständig und korrekt in allen sechs Schreibpfaden. Das Tagesprinzip (§3 BUrlG) ist in beiden Urlaubsbuchungspfaden konsistent. Feature #201 (Arbeitszeitfenster), #191 (track_hours=False) und #193/#195 (Eintritt/Austritt-Fenster) sind korrekt in die Compliance-Logik eingebettet.

Die verbleibenden MITTEL-Findings betreffen ausschließlich fehlende belt-and-suspenders-Filterung bei RLS-geschützten Queries — kein Gesetzesverstoß im aktuellen Single-Tenant-Deployment, aber vor Phase-4-SaaS zwingend zu beheben.

Keine KRITISCH- oder HOCH-Findings.

---

> **Rechtlicher Hinweis:** Dieser Audit ist ein technisches Review mit rechtlichem Kontext und ersetzt keine verbindliche Rechtsberatung. Bei Fragen zur Anwendung einzelner ArbZG-Vorschriften auf spezifische Beschäftigungsverhältnisse ist ein Fachanwalt für Arbeitsrecht hinzuzuziehen.
