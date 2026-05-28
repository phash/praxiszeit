# Feedback-01 Umsetzungs-Roadmap (#140–#146)

> **For agentic workers:** Diese Roadmap sequenziert 7 Issues mit je eigener Spec
> (`docs/specs/2026-05-28-*.md`). Pro Phase wird die zugehörige Spec zur
> Detail-Task-Liste herangezogen. Zum Ausführen einer Phase: superpowers:writing-plans
> auf die jeweilige Spec anwenden (bite-sized TDD-Plan erzeugen), dann
> superpowers:subagent-driven-development oder superpowers:executing-plans.

**Goal:** Die 7 Punkte aus dem ersten Anwenderfeedback (`feedback/feedback_01.txt`) in dependency-korrekter, risikoarmer Reihenfolge umsetzen.

**Architektur-Ansatz:** Erst die zwei Bugs (sofortiger Nutzen, geringes Risiko), dann die Kalender-/Abwesenheits-Features entlang ihrer Abhängigkeitskette, zuletzt das komplexeste Compliance-Feature. Geteilte Fundamente (`closure_id`-FK, `AbsenceType.PAID_LEAVE`) werden bewusst zuerst gebaut, damit darauf aufbauende Features sie wiederverwenden.

**Tech-Stack:** React 18 + TS + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16 (RLS, Multi-Tenant) / Alembic / Pytest + Vitest + Playwright.

---

## Abhängigkeiten & kritischer Pfad

```
#141 (Frontend-Bug) ───────────────► #144 (Pause-Ausnahme, komplex)
#140 (Badge-Bug)    (unabhängig)
#143 (Custom Holidays) (unabhängig)
#142 (Closures editable + closure_id-FK) ──► #145 (PAID_LEAVE + Flag) ──► #146 (24./31.12.)
                                                    └── kritischer Pfad ──┘
```

- **Kritischer Pfad:** #142 → #145 → #146 (je dependent, müssen seriell laufen).
- **Parallelisierbar** (bei mehreren Entwicklern): die Kette #141 → #144 sowie #140 und #143 sind vom kritischen Pfad unabhängig.
- **Empfohlene serielle Reihenfolge (ein Entwickler):** #141 → #140 → #142 → #143 → #145 → #146 → #144.

**Begründung der Reihenfolge:**
1. Bugs zuerst — Anwender erleben sie aktiv; #141 ist frontend-only (schnellster Win).
2. #142 vor #145, weil #145 den `closure_id`-FK + die Absence-Re-Sync-Logik aus #142 wiederverwendet.
3. #146 nach #145, weil es den `PAID_LEAVE`-Typ + `counts_as_vacation`-Mechanik aus #145 nutzt.
4. #143 ist eigenständig — als zusammenhängendes Feature nach den Closure-Arbeiten eingeschoben.
5. #144 zuletzt: höchste Komplexität (Compliance, Antrags-/Genehmigungslogik), konzeptionell nach dem Pausen-Fix #141.

**Querschnitt-Regeln (für alle Phasen, aus CLAUDE.md):**
- Migrationen auf Host erstellen + committen **vor** Container-Rebuild; Revision-ID ≤ 32 Zeichen.
- Jede tenant-scoped Query mit explizitem `Model.tenant_id == current_user.tenant_id` (F-026), zusätzlich zu RLS.
- Backend-Container ist gebaut (kein Host-Volume): nach Edits `docker compose cp` vor `pytest`, oder `docker compose build backend`.
- Stunden-Anzeige `formatHoursHM()`; ArbZG-Warnungen über `showArbzgWarnings()`.
- Tests: `docker compose exec backend pytest tests/ -v`, `cd frontend && npm test`, `cd e2e && npx playwright test`, All-in-one `bash scripts/local-ci.sh`.

---

## Phase 1 — Bug: §18-Ausnahme bei manueller Zeiterfassung (#141)

- **Spec:** `docs/specs/2026-05-28-arbzg-exemption-frontend-fix.md`
- **Abhängigkeit:** keine. **Aufwand:** S (frontend-only). **Risiko:** sehr gering.
- **Warum zuerst:** kein Backend-/DB-Change, sofortiger Nutzen für leitende Angestellte.

**Aufgaben (geordnet):**
- [ ] `exempt_from_arbzg: boolean` ins `User`-Interface in `frontend/src/stores/authStore.ts:5-28`.
- [ ] Pausen-Validierungsblock `frontend/src/pages/TimeTracking.tsx:267-303` mit `if (!user?.exempt_from_arbzg) { … }` umschließen.
- [ ] Vitest-Test: exempt-User → keine `break_time`-Fehlermeldung bei >9h ohne Pause; nicht-exempt → weiterhin Fehler.
- [ ] Manuell im Browser: User mit Häkchen (`UserForm.tsx:287`) erfasst >9h ohne 45-Min-Pause → Speichern gelingt.
- [ ] `cd frontend && npm run build` (tsc) grün.

**Definition of Done:** REQ-1..3 der Spec erfüllt; Vitest grün; manuell verifiziert.
**Commit:** `fix(arbzg): §18-Ausnahme bei manueller Zeiterfassung im Frontend respektieren (#141)`

---

## Phase 2 — Bug: Urlaubsanträge-Badge im Admin-Dashboard (#140)

- **Spec:** `docs/specs/2026-05-28-vacation-request-badge-design.md`
- **Abhängigkeit:** keine. **Aufwand:** S. **Risiko:** gering.

**Aufgaben (geordnet):**
- [ ] Backend: `GET /api/admin/vacation-requests/pending-count` in `backend/app/routers/admin_vacations.py` (tenant-scoped, `status == PENDING`), Vorlage `admin_change_requests.py:30`.
- [ ] Backend-Test (tenant-isoliert, nur pending) analog `test_cross_tenant_api.py`.
- [ ] Frontend `Layout.tsx`: State `pendingVRCount` + Polling-`useEffect` (60 s, `role==='admin'`) analog Z. 48/52-64.
- [ ] Frontend `Layout.tsx:170`: `badge: pendingVRCount` statt `badge: 0`.
- [ ] Manuell: Urlaubsantrag stellen → Badge erscheint; genehmigen → Badge weg.
- [ ] `npm run build` + Backend-Test grün.

**Definition of Done:** Badge erscheint bei >0 offenen Urlaubsanträgen, identisch zu Änderungsanträgen.
**Commit:** `feat(dashboard): rote Badge für offene Urlaubsanträge (#140)`

---

## Phase 3 — Betriebsferien bearbeitbar + closure_id-FK (#142)

- **Spec:** `docs/specs/2026-05-28-company-closures-editable-design.md`
- **Abhängigkeit:** keine. **Aufwand:** M. **Risiko:** mittel (Migration + Datenkonsistenz). **Fundament für #145.**

**Aufgaben (geordnet):**
- [ ] Migration `add_closure_id_to_absences`: Spalte `closure_id UUID NULL REFERENCES company_closures(id) ON DELETE SET NULL` + Index + Backfill (Note-Pattern → FK). Auf Host erstellen + committen.
- [ ] `backend/app/models/absence.py`: `closure_id`-Spalte ergänzen.
- [ ] `company_closures.py`: `create_closure` (Z. 147-160) erzeugt Absences mit `closure_id`; `delete_closure` (Z. 190-203) löscht über `Absence.closure_id == closure_id` statt Note-Match.
- [ ] F-026-Cleanup: `_get_holidays_for_range` (Z. 50) + `list_closures` (Z. 61) mit `tenant_id`-Filter.
- [ ] `CompanyClosureUpdate`-Schema + `PUT /api/company-closures/{id}` mit Re-Sync-Logik (Diff: neue Arbeitstage anlegen, entfallene löschen, Fremd-Absences via Skip-Logik unberührt).
- [ ] Backend-Tests: PUT verlängert/verkürzt Zeitraum → Absences korrekt; Löschen via FK trifft genau die zugehörigen (auch nach Namensänderung); Fremd-Absences unberührt.
- [ ] Frontend `AdminAbsences.tsx`: Edit-Button + vorbefülltes `closureForm` → `PUT`.
- [ ] E2E: anlegen → bearbeiten → Liste/Absences stimmen.
- [ ] `bash scripts/local-ci.sh` grün.

**Definition of Done:** REQ-1..3; Note-String-Matching vollständig durch FK ersetzt; Tenant-Lecks geschlossen.
**Commits:** Migration + Model separat; dann `feat(closures): Betriebsferien bearbeitbar via PUT + closure_id-FK, F-026-Härtung (#142)`

---

## Phase 4 — Lokale/regionale Feiertage (#143)

- **Spec:** `docs/specs/2026-05-28-custom-regional-holidays-design.md`
- **Abhängigkeit:** keine. **Aufwand:** M. **Risiko:** mittel (Resync-Schutz).

**Aufgaben (geordnet):**
- [ ] Migration `add_custom_holiday_fields`: `is_custom BOOLEAN DEFAULT false`, `source VARCHAR(20) DEFAULT 'workalendar'`.
- [ ] `models/public_holiday.py` + Schemas (`HolidayCreate/Update/Response`) erweitern.
- [ ] `routers/holidays.py`: `POST`/`PUT`/`DELETE` (Admin, tenant-scoped, nur `is_custom=true`; Standard → 403).
- [ ] Resync-Schutz in `holiday_service.py`/`admin_settings.py`: Bundesland-Wechsel löscht nur `source='workalendar'`.
- [ ] Verifizieren: `calculation_service` zählt Custom-Feiertage in der Sollzeit (kein `source`-Filter schließt sie aus).
- [ ] Backend-Tests: Custom anlegen → Soll reduziert; Standard nicht löschbar; Resync behält Custom.
- [ ] Frontend: Feiertags-Verwaltungs-UI (Liste + CRUD für Custom; Standard read-only).
- [ ] E2E + `local-ci.sh` grün.

**Definition of Done:** REQ-1..4; Resync zerstört keine Custom-Feiertage.
**Commit:** `feat(holidays): admin-pflegbare lokale Feiertage (#143)`

---

## Phase 5 — Bezahlte Freistellung: PAID_LEAVE + Closure-Flag (#145)

- **Spec:** `docs/specs/2026-05-28-paid-leave-special-days-design.md`
- **Abhängigkeit:** **#142** (closure_id-FK + Re-Sync). **Aufwand:** M-L. **Risiko:** mittel (Enum-Migration, Berechnungslogik).

**Aufgaben (geordnet):**
- [ ] Migration `add_paid_leave_absence_type`: Enum-Wert `paid_leave` (Postgres `ALTER TYPE … ADD VALUE` ggf. außerhalb Transaktion; SQLite-Testsuite-Kompatibilität prüfen).
- [ ] `models/absence.py`: `AbsenceType.PAID_LEAVE` + Docstring-Matrix; `docs/BACKEND-ARCHITEKTUR.md` Absence-Typ-Matrix ergänzen.
- [ ] `calculation_service` (`get_monthly_target`/`get_monthly_actual`): `PAID_LEAVE` = Soll↓, Ist=0, balance-neutral, **kein** Urlaubsabzug (Mechanik wie OTHER, aber bezahlte Kategorie); Urlaubskonto-Auswertung zählt es **nicht** als Urlaub.
- [ ] Migration `add_counts_as_vacation_to_closures`: `counts_as_vacation BOOLEAN DEFAULT true`.
- [ ] `company_closures.py` + Schemas: `POST`/`PUT` akzeptieren `counts_as_vacation`; bei `false` → `PAID_LEAVE`- statt `VACATION`-Absences.
- [ ] Backend-Tests: `counts_as_vacation=false` → Urlaubsbudget unverändert, Soll der Tage = 0, Balance-neutral.
- [ ] Frontend `AdminAbsences.tsx`: Auswahl „als Urlaub werten" vs. „bezahlte Freistellung"; `PAID_LEAVE`-Label/Farbe in Kalender/Reports.
- [ ] E2E + `local-ci.sh` grün (inkl. SQLite-Enum-Kompatibilität).

**Definition of Done:** REQ-1, REQ-2, REQ-4 der Paid-Leave-Spec; Urlaubskonto getrennt ausgewiesen.
**Commits:** Enum-Migration + calc separat; dann `feat(closures): Urlaub vs. bezahlte Freistellung wählbar, neuer PAID_LEAVE-Typ (#145)`

---

## Phase 6 — Konfigurierbare Sondertage 24./31.12. (#146)

- **Spec:** `docs/specs/2026-05-28-paid-leave-special-days-design.md`
- **Abhängigkeit:** **#145** (PAID_LEAVE + counts_as_vacation). **Aufwand:** M. **Risiko:** mittel.

**Aufgaben (geordnet):**
- [ ] Modellierung final fixieren (Spec „Offene Frage 1"): Empfehlung — `free`-Sondertage über 1-Tages-Closure-Mechanismus (#142/#145 wiederverwenden), `half_day` als reine Soll-Reduktion ohne Absence.
- [ ] Settings in `admin_settings.py`: `special_day_dec24_mode`/`_vacation`, `special_day_dec31_mode`/`_vacation` (Modi `working_day|half_day|free`, Default `working_day`).
- [ ] `calculation_service`: Anwendung je Modus — `working_day` = unverändert; `half_day` = Soll = `get_daily_target_for_date/2`; `free` = wie Feiertag/Closure (Urlaub oder PAID_LEAVE je `_vacation`).
- [ ] Backend-Tests: alle 3 Modi × (Urlaub|Freistellung) auf Soll + Urlaubskonto; `half_day` = halbe Sollzeit.
- [ ] Frontend: 24./31.12.-Konfiguration in Settings (Dropdown + bei „frei" Urlaub/Freistellung).
- [ ] E2E + `local-ci.sh` grün.

**Definition of Done:** REQ-3, REQ-5 der Paid-Leave-Spec; Default = bisheriges Verhalten (abwärtskompatibel).
**Commit:** `feat(calendar): konfigurierbare Behandlung 24./31.12. inkl. Halbtag (#146)`

---

## Phase 7 — „Pflicht-Pause nicht möglich" + Genehmigungsworkflow (#144)

- **Spec:** `docs/specs/2026-05-28-break-exception-workflow-design.md`
- **Abhängigkeit:** konzeptionell nach **#141**. **Aufwand:** L. **Risiko:** höher (Compliance + Antragsfluss). **Zuletzt — höchste Komplexität.**

**Aufgaben (geordnet):**
- [ ] Migration `add_break_waiver_reason`: `time_entries.break_waiver_reason TEXT NULL`; Setting-Key `break_exception_requires_approval` (Default `false`).
- [ ] `time_entries`-Model/Schema + Audit-Source-Marker `break_waiver` (<40 Zeichen).
- [ ] Setting-Read/Write in `admin_settings.py`.
- [ ] Validierungs-/Einreichungslogik in Time-Entry-Endpunkten + `break_validation_service`: bei Pausen-Fehlschlag + gültiger Begründung → `requires_approval=false`: Eintrag mit Begründung + ArbZG-Warnung; `=true`: als `ChangeRequest` (`CREATE`, `entry_kind="time_entry"`, `reason`) anlegen, bei Genehmigung Eintrag materialisieren.
- [ ] Backend-Tests beide Konfigurationen (ohne Begründung → Fehler; CR-Pfad pending→approved materialisiert).
- [ ] Frontend `TimeTracking.tsx`: „Pause war nicht möglich"-Option + Pflicht-Begründungsfeld statt hartem Block; Hinweis bei `requires_approval=true`.
- [ ] Frontend Settings-Toggle; Genehmigung im Änderungsanträge-Bereich sichtbar.
- [ ] E2E beide Konfigurationen + `local-ci.sh` grün.

**Definition of Done:** REQ-1..4 der Break-Exception-Spec; Begründung backend-erzwungen; Audit-Trail vollständig.
**Commits:** Migration separat; dann `feat(arbzg): Pflicht-Pause-Ausnahme mit konfigurierbarem Genehmigungsworkflow (#144)`

---

## Self-Review (Spec-Abdeckung)

- #140 → Phase 2 ✓ · #141 → Phase 1 ✓ · #142 → Phase 3 ✓ · #143 → Phase 4 ✓ · #144 → Phase 7 ✓ · #145 → Phase 5 ✓ · #146 → Phase 6 ✓
- Abhängigkeiten konsistent: #142(P3) vor #145(P5) vor #146(P6); #141(P1) vor #144(P7). ✓
- Geteilte Fundamente vor Konsumenten gebaut: `closure_id`-FK (P3) vor Closure-Flag (P5); `PAID_LEAVE` (P5) vor Sondertagen (P6). ✓
- Keine Platzhalter; jede Phase nennt Dateien, Tasks, DoD, Commit. Bite-sized TDD-Schritte je Phase entstehen beim Ausführen aus der jeweiligen Spec.

---

## Nächster Schritt / Ausführung

Pro Phase beim Start: superpowers:writing-plans auf die Phasen-Spec anwenden → bite-sized TDD-Plan, dann ausführen via superpowers:subagent-driven-development (empfohlen) oder superpowers:executing-plans. Implementierung idealerweise in isoliertem Worktree pro Phase.
