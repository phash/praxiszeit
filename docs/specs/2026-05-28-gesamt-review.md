# Gesamt-Review PraxisZeit (v1.6.0, master)

**Datum:** 2026-05-28
**Methode:** 4 parallele Spezial-Audits (Security/Appsec, ArbZG-Konformität, Backend+API, Frontend), read-only gegen `master` (Stand nach #140–#146).
**Status:** Review abgeschlossen. Fixes für Critical/High siehe Spalte „Aktion".

---

## Executive Summary

Die Anwendung ist insgesamt **reif und solide gebaut**. Über alle vier Audits hinweg: **1 Critical, 7 High, ~10 Medium, ~10 Low**. Kein Cross-Tenant-Datenleck mit Auth-Bypass, keine Datenkorruption, kein Token-Leak (F-023 hält). Die ArbZG-Engine, das Absence-Berechnungsmodell, die Concurrency-Primitive (`with_for_update`), die RLS-Belt-and-Suspenders und die API-Schema-Disziplin wurden ausdrücklich als korrekt verifiziert.

Der **einzige Critical** ist eine echte ArbZG-Lücke: der Genehmigungs-Pfad von Änderungsanträgen prüft den §3-10h-Cap nicht erneut (TOCTOU).

---

## Findings nach Schweregrad

Legende Aktion: **FIX** = jetzt behoben · **ISSUE** = als GitHub-Issue verfolgt (Design/Aufwand) · **TRACKED** = bereits als Issue offen.

### CRITICAL

| ID | Bereich | Finding | Datei | Aktion |
|----|---------|---------|-------|--------|
| C-1 | ArbZG §3/§4 | CR-Genehmigung materialisiert Zeiteintrag **ohne** erneute §3-10h-/§4-Prüfung. §3 wird nur bei CR-Erstellung gegen den damaligen DB-Stand geprüft; zwischen Erstellung und Genehmigung kann der Tag >10h wachsen → Genehmigung persistiert ihn. | `routers/admin_change_requests.py` `review_change_request` | **FIX** |

### HIGH

| ID | Bereich | Finding | Datei | Aktion |
|----|---------|---------|-------|--------|
| S-H01 | Security F-026 | DELETE-Lookup ohne `tenant_id`-Filter (einziger Admin-Endpoint ohne F-026) | `routers/admin_time_entries.py:236` | **FIX** |
| S-H02 | Security F-026 | `create_absence` Feiertags-Query ohne `PublicHoliday.tenant_id` → zieht tenant-fremde Feiertage | `routers/absences.py:250` | **FIX** |
| B-H1 | Backend | `clock_out` Auto-Close eines Vortags-Eintrags wird **nicht committet** vor `raise` → Eintrag bleibt für immer offen | `routers/time_entries.py:316-321` | **FIX** |
| B-H2 | Backend/API | Unbeschränkte List-Endpoints auf Hochvolumen-Tabellen (kein skip/limit) | `time_entries`, `absences`, `change_requests`, `vacation_requests`, `company_closures` | **FIX** |
| F-H1 | Frontend | Doppel-Submit-Guard fehlt auf ~6 Formularen (Doppelklick → Dubletten) | `AbsenceCalendarPage`, `AdminAbsences`, `UserForm`, `WorkingHoursModal`, `Profile` | **FIX** |
| F-H2 | Frontend | `window.confirm` für die destruktivsten Aktionen (Tenant suspend/delete) statt `useConfirm` | `pages/admin/Billing.tsx:234,248` | **FIX** |
| F-H3 | Frontend Perf | Kein Code-Splitting → ein 745 KB Bundle; alle Admin-Seiten laden für jeden MA | `App.tsx` (statische Imports) | **ISSUE** |
| A-H1 | ArbZG §3/§6 | Nachtschichten (über Mitternacht) werden mit 0h unterbewertet; `TimeEntry` hat kein End-Datum → Nachtarbeit nicht ehrlich abbildbar | `models/time_entry.py`, `routers/time_entries.py:49` | **ISSUE** |
| A-H2 | ArbZG §3 | Kein Report für das 8h→10h-Ausgleichsfenster (24 Wochen) | `calculation_service.py:168` | **ISSUE** |

### MEDIUM

| ID | Bereich | Finding | Datei | Aktion |
|----|---------|---------|-------|--------|
| S-M01 | Security | Verifikations-/Signup-Links aus `Origin`-Header gebaut (Host-Header-Injection) → kanonische `SAAS_APP_URL`-Einstellung | `routers/public_signup.py:80,125` | **FIX** |
| S-M04 | Security | `admin_delete_time_entry` Lookup ohne `with_for_update()` (Race, inkonsistent zum Update-Pfad) | `routers/admin_time_entries.py:229` | **FIX** |
| A-M2 | ArbZG §4 | Sub-15-Min-Deklarationspausen bestehender Tageseinträge werden ohne Pro-Segment-Filter summiert | `services/break_validation_service.py:62` | **FIX** |
| A-M1 | ArbZG §4 | Break-Waiver: §4-Pausen sind rechtlich **nicht** vom AN abdingbar → Feature dokumentiert einen Verstoß als Beweis, keine Erlaubnis. UI/Spec-Wording klarstellen | `TimeTracking.tsx`, Spec | **FIX** (Wording) |
| B-M1 | Backend/Test | `test_native_mode.py` License-Tests assertieren englische Strings, Code liefert deutsche → Tests veraltet (3-4 der „pre-existing failures") | `tests/test_native_mode.py` | **FIX** |
| B-M2 | Backend F-026 | `PublicHoliday`-Queries in `calculation_service` (4 Stellen) ohne expliziten `tenant_id`-Filter (nur RLS) — verletzt dokumentiertes Invariant | `calculation_service.py:202,408,500,712` | **FIX** |
| B-M3 | Backend Perf | O(n²) in Overtime-Dashboard + N+1 in Monatsreport (`get_overtime_account` pro Monat neu) | `dashboard.py:154`, `reports.py:76` | **ISSUE** |
| F-M | Frontend | `User`-Typ dreifach definiert + driftet (authStore schmaler als UserForm/Users) → ein gemeinsamer `types/user.ts` | `stores/authStore.ts`, `UserForm.tsx`, `Users.tsx` | **ISSUE** |
| A-M3 | ArbZG §16 | Audit-Log nicht manipulationssicher (kein Hash-Chain/Signatur) | `models/time_entry_audit_log.py` | **TRACKED (#121)** |

### LOW (Auswahl)

| ID | Finding | Datei | Aktion |
|----|---------|-------|--------|
| S-L03 | `totp_disable` ohne `token_version += 1` (Session-Invalidierung inkonsistent) | `routers/auth.py` | **FIX** |
| A-L2 | Irreführende „§14"-Zitate in Warntexten (korrekt: §3) | `admin_time_entries.py:76,180`, `admin_change_requests.py:410` | **FIX** |
| B-L4 | Dublette-Zeiteintrag liefert 400, andere Dubletten 409 → vereinheitlichen | `time_entries.py:494` | **FIX** |
| B-L3 | „Enddatum muss **nach** dem Startdatum liegen", Check erlaubt aber gleich | `absences.py:219` | **FIX** |
| B-L2 | `date.today()` statt `today_local()` in 2 Business-Pfaden | `reports.py:719`, `main.py:325` | **ISSUE** |
| F-L | Admin-Nav hardcoded grays statt Theme-Tokens; Polling pausiert nicht bei Hidden-Tab; redundanter Double-Fetch in AdminAbsences | div. | **ISSUE** |

---

## Verifiziert korrekt (Auszug)

- **ArbZG §4-Schwellen + Segment-Regel** (360/540, 30/45, ≥15min) — Client und Server identisch.
- **§18-Ausnahme** auf **allen** Schreibpfaden honoriert (clock-out, manual, admin, CR-create, CR-approval-warnings, XLS-Import, Frontend) — konsistente, dokumentierte Breit-Auslegung.
- **§3-10h-Hardcap** auf allen **direkten** Pfaden (422); nur der CR-Approval-Pfad ist die Lücke (C-1).
- **Absence-Typ-Matrix** über alle Berechnungsfunktionen konsistent; PAID_LEAVE/OTHER fallen identisch durch; `get_weekly_hours_for_date` überall pro Tag.
- **Concurrency**: clock_in/out + CR-Approval + Absence-Dublette unter `with_for_update`.
- **Migrations**: ein Head `043_break_waiver`, 43 Revisionen, kein Drift.
- **Frontend**: F-023 (Token nur im Memory), Single-Flight-Refresh + CSRF + 401-Retry, solide a11y-Basis, `formatHoursHM`/`showArbzgWarnings`/`useConfirm` konsistent (außer Billing).

---

## Empfohlene Reihenfolge der Fixes

1. **C-1** (ArbZG §3 auf CR-Approval) — Critical, vor inspektionsrelevantem Deployment.
2. **F-026-Lecks** (S-H01, S-H02, B-M2) — Multi-Tenant-Härtung.
3. **B-H1** (clock_out commit), **B-H2** (Pagination) — Backend-Korrektheit/Perf.
4. **F-H1/F-H2** (Doppel-Submit-Guards, Billing-Confirm) — Frontend.
5. Cheap-Safe: S-M01, S-M04, S-L03, A-M2, A-L2, B-M1, B-L3, B-L4, A-M1-Wording.
6. **ISSUEs** (Design/Aufwand): F-H3 Code-Splitting, A-H1 Nachtschicht, A-H2 §3-Ausgleichsreport, B-M3 Perf, F-M User-Typ, diverse Low.
