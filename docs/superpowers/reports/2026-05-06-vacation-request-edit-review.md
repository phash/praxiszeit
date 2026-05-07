# Vacation Request Edit — Security & DSGVO Review

**Feature-Branch:** `feature/vacation-request-edit`
**Spec:** `docs/superpowers/specs/2026-05-06-vacation-request-edit-design.md`
**Plan:** `docs/superpowers/plans/2026-05-06-vacation-request-edit.md`
**Datum:** 2026-05-06

---

## Implementierungs-Übersicht

| Komponente | Datei | Zeilen |
|------------|-------|--------|
| Pydantic-Schema | `backend/app/schemas/vacation_request.py` | +24 |
| Audit-Helper | `backend/app/routers/vacation_requests.py:45-61` | +17 |
| MA-PATCH-Endpoint | `backend/app/routers/vacation_requests.py:228-360` | +132 |
| Admin-PATCH-Endpoint | `backend/app/routers/admin_vacations.py:249-378` | +130 |
| pytest-Suite | `backend/tests/test_vacation_request_edit.py` | +290 (16 Cases) |
| Modal-Komponente | `frontend/src/components/VacationRequestEditModal.tsx` | +200 |
| Admin-Hookup | `frontend/src/pages/admin/VacationApprovals.tsx` | +18 |
| MA-Hookup | `frontend/src/pages/AbsenceCalendarPage.tsx` | +30 |
| E2E-Admin | `e2e/tests/admin/vacation-approvals.spec.ts` | +56 |
| E2E-MA | `e2e/tests/employee/absences.spec.ts` | +59 |

**Test-Status:** 534/534 backend pytest grün, 116/116 Playwright grün, 0 Regressions.

**Audit-Trail-Verifikation (Prod-DB-Snapshot):**
```
 action |        source         |  old_date  |  new_date  | user_id == changed_by?
--------+-----------------------+------------+------------+------------------------
 update | vacation_request_edit | 2026-06-22 | 2026-06-25 | NEIN (Admin → MA)
 update | vacation_request_edit | 2026-06-23 | 2026-06-23 | JA   (MA-Self-Edit)
 update | vacation_request_edit | 2026-06-22 | 2026-06-25 | NEIN (Admin → MA)
 ... (7 Rows total: 4 MA-Self + 3 Admin-Acting-On-Behalf)
```

---

## Security-Review

### A — Authorization Boundaries

**MA-Endpoint (`PATCH /api/vacation-requests/{id}`):**
- Tenant-Filter im Lookup: `VacationRequest.tenant_id == current_user.tenant_id` (`vacation_requests.py:246-248`) — Cross-Tenant gibt 404 (kein Existenz-Leak).
- Owner-Check: `str(vr.user_id) != str(current_user.id)` → 403 (`:255-256`). String-Vergleich, weil SQLAlchemy UUIDs in unterschiedlichen Repräsentationen liefern kann.
- Status-Gate: nur `pending` editierbar, sonst 400.
- **Test:** `test_edit_foreign_request_forbidden` (employee_a vs employee_b, gleiches Tenant), `test_edit_approved_rejected`, `test_edit_rejected_rejected`, `test_edit_withdrawn_rejected`.

**Admin-Endpoint (`PATCH /api/admin/vacation-requests/{id}`):**
- `Depends(require_admin)` (`admin_vacations.py:254`) — alle Routen im Router haben den Guard via `dependencies=[Depends(require_admin)]` zusätzlich.
- Tenant-Filter: gleicher `tenant_id`-Check. Cross-Tenant gibt 404.
- **Test:** `test_admin_cannot_edit_foreign_tenant` (Admin in Tenant A versucht Edit in Tenant B → 404, nicht 403).

### B — Race Conditions

Beide Endpoints holen die VR-Row mit `with_for_update()` (`vacation_requests.py:251`, `admin_vacations.py:269`).

Szenarien:
- **Concurrent Approve + Edit:** Approve hält denselben Row-Lock (`admin_vacations.py:99`). Erste Tx gewinnt, zweite arbeitet auf bereits-genehmigten Row → 400 ("Antrag wurde bereits bearbeitet" / "Nur offene Anträge können bearbeitet werden").
- **Concurrent Edit + Edit:** Erste Tx gewinnt Lock. Zweite wartet, sieht beim Lesen den neuen State, validiert dagegen, schreibt neue Audit-Row.
- **Concurrent Edit + Withdraw (DELETE):** Pre-existing Gap — `withdraw_vacation_request` fehlt `with_for_update`. Kein neues Risiko durch diese Änderung; Out-of-Scope für PR.

### C — Mass-Assignment

`VacationRequestUpdate` enthält **nur** die fünf editierbaren Felder (`date`, `end_date`, `hours`, `note`, `absence_type`). Insbesondere KEIN:
- `status` → MA kann sich nicht selbst genehmigen
- `reviewed_by` / `reviewed_at` → Approval-Spuren nicht überschreibbar
- `rejection_reason` → kann nicht manipuliert werden
- `user_id` / `tenant_id` → kein Reassignment möglich

### D — Validierung

**Pydantic-Schicht** (`schemas/vacation_request.py:31-53`):
- `absence_type` Whitelist `{vacation, training, overtime, other}` — `sick` wird mit 422 abgelehnt.
- **Test:** `test_edit_invalid_absence_type_rejected`.

**Router-Schicht:**
- Range: `effective_end < new_date` → 400.
- Beschäftigungsfenster (`first_work_day` / `last_work_day`) → 400.
- Pending-Overlap mit ANDEREN pending-Anträgen (Self-Exclusion via `VacationRequest.id != vr.id`) → 409.
- Vacation-Budget für Type=`vacation` (Pro Kalenderjahr).
- **Tests:** `test_edit_invalid_range_rejected`, `test_edit_before_first_work_day_rejected`, `test_edit_overlap_with_other_pending_rejected`, `test_edit_self_overlap_allowed`.

### E — Audit-Trail (Tamper-Resistance)

- Audit-Row wird in **derselben Transaktion** wie das Update geschrieben (`vacation_requests.py:357-358`). Bei Validierungs-Exception → automatischer Rollback → kein State-Drift zwischen DB und Audit.
- Audit-Row enthält: `action="update"`, `source="vacation_request_edit"` (21 chars, fits varchar(40)), `user_id=affected_employee`, `changed_by=acting_principal`, alte+neue Datums-Spalten + alter+neuer Zustand als Format-String in `old_note`/`new_note`, `tenant_id` von der Quell-Row.
- No-op-Edits (gleiche Werte) → KEIN Audit-Row geschrieben (`vacation_requests.py:280-282`). Verhindert Audit-Lärm + falsche Anschuldigungen.
- **Tests:** `test_edit_writes_audit_row` (12 Felder geprüft), `test_edit_noop_writes_no_audit`, `test_admin_edits_employee_pending` (`changed_by=admin`, `user_id=mitarbeiter`).

### F — License-Enforcement

`LicenseReadOnlyMiddleware` (in `main.py`) blockiert PATCH-Methoden bei abgelaufener Lizenz (Methoden-Allowlist). Der neue Endpoint braucht keine Per-Route-Dependency.

### G — Rate-Limiting

Globaler `slowapi`-Limiter ist aktiv (auf Login-/Auth-Routen explizit, andere via Middleware). Edit-Endpoint nicht spezifisch limitiert — nicht attraktiv für Brute-Force, da nur eigene/zugängliche Resourcen betroffen.

### H — XSS / Injection

- Notiz-Feld geht durch Pydantic (Text, kein HTML-Render) → DB-Escape via SQLAlchemy.
- Frontend rendert `vr.note` via React (auto-escape).
- Audit-`old_note`/`new_note` ist Text, niemals serialisiert in HTML-Kontext.

### I — Findings

| Severity | Befund | Status |
|----------|--------|--------|
| Important | `end_date: null` musste explizit als "clear" interpretiert werden (Pydantic v2 `model_fields_set` statt `is not None`) | **Fixed** in commit `3f8d37f` |
| Minor | `withdraw_vacation_request` (DELETE) lacks `with_for_update` (pre-existing) | Out-of-scope, separate Issue |
| Minor | Admin-Endpoint dupliziert ~85% der MA-Endpoint-Logik | Akzeptiert (Lesbarkeit > DRY für 2 Call-Sites mit divergentem `target_user`) |

---

## DSGVO-Review

### Art. 5 Abs. 2 — Rechenschaftspflicht

✅ Jede inhaltliche Änderung wird in `time_entry_audit_logs` dokumentiert mit Wer (changed_by), Wen (user_id), Wann (created_at), Was (old_*/new_* Spalten + Format-String). Belegt in `test_edit_writes_audit_row` und `test_admin_edits_employee_pending`.

### Art. 5 Abs. 1 lit. c — Datenminimierung

✅ Alte und neue Notiz werden im Audit-Format-String auf 200 Zeichen abgeschnitten (`_format_vacation_request_audit_text` in `vacation_requests.py:52`). Verhindert excessive Persistenz langer Notizen, die kein Audit-Zweck rechtfertigt.

### Art. 6 Abs. 1 lit. b — Rechtmäßigkeit (Vertragsdurchführung)

✅ Verarbeitung erfolgt zur Durchführung des Arbeitsvertrags (Urlaubsabwicklung). Editieren eines bereits gestellten Antrags ist Bestandteil der vertraglichen Personalverwaltung. Keine zusätzliche Einwilligung erforderlich.

### Art. 9 — Besondere Kategorien (Gesundheitsdaten)

✅ `absence_type='sick'` ist im Edit-Pfad **technisch verboten** (Pydantic-Validator + DB-Type-Whitelist). Krankmeldungen laufen ausschließlich über `/api/absences` mit Maskierung in der `/calendar`-Response (DSGVO-Konsistenz).

✅ Notiz-Feld trägt UI-Hinweis: *„Bitte keine Gesundheitsangaben oder sensiblen Daten eintragen."* (`VacationRequestEditModal.tsx:200`, gleiches Wording wie Create-Form). Schützt MA vor versehentlichem Hinterlegen sensibler Daten.

### Art. 25 — Privacy by Design

✅ Tenant-Isolation via RLS (Postgres) **plus** App-Layer-Filter (F-026 belt-and-suspenders). Cross-Tenant-Edit gibt 404, nicht 403 — keine Existenz-Auskunft an unautorisierte Anfrage.
✅ Mass-Assignment-Schutz durch minimales Pydantic-Schema.
✅ Audit-Persistenz im selben Transactional-Boundary wie das Update — kein Daten-Drift möglich.

### Art. 30 — Verzeichnis von Verarbeitungstätigkeiten

ℹ️ Edit-Funktion fällt unter den existierenden Verzeichnis-Eintrag *„Arbeitszeit- und Abwesenheitsverwaltung"*. Kein neuer Eintrag erforderlich, da keine neue Verarbeitungs-Kategorie + keine neue Datenkategorie + kein neuer Empfänger.

### Art. 32 — Sicherheit der Verarbeitung

✅ Audit-Logs sind tenant-scoped via RLS-Policy auf `time_entry_audit_logs`. Lesezugriff nur durch Admin-Routen (`/api/admin/audit/*`). PATCH-Endpoints sind authentifiziert (JWT-Cookie + Auth-Middleware) und tenant-scoped.

### Art. 17 — Recht auf Löschung

ℹ️ Kein neuer Persistenz-Pfad. `vacation_requests.tenant_id` und `time_entry_audit_logs.user_id`/`tenant_id` sind durch existierende DSGVO-Lösch-/Anonymisierungs-Pfade in `admin_users.py` (User-Delete) und `superadmin.py` (Tenant-Delete) abgedeckt. Edit-Audit-Rows werden mit-anonymisiert.

### DSGVO-Findings

Keine. Alle relevanten Pflichten sind erfüllt; das Feature **erweitert** keine Verarbeitungs-Surface (gleiche Datenkategorien wie Create), und **verbessert** Art. 5 Abs. 2 (Audit-Trail bei Änderungen statt Delete+Recreate, das den Verlauf durchbrochen hätte).

---

## Manuelles Browser-Smoke-Sheet (für Final-Sign-off)

Diese Schritte wurden via E2E-Tests automatisiert ausgeführt; reproduzierbar manuell:

1. Login als `admin` / `Admin2025!` → `/admin/settings` → Genehmigungspflicht aktivieren ✅ (E2E `toggle approval requirement`)
2. Login als MA → `/absences` → Antrag stellen ✅ (E2E `employee edits own pending vacation request`)
3. Tab "Meine Anträge" → Pencil-Button → Modal → Stunden ändern → Speichern → Toast + Persistenz ✅ (E2E)
4. Re-Login als Admin → `/admin/vacation-approvals` → Card mit MA-Antrag → Bearbeiten → Datum/Notiz anpassen → Speichern → Toast ✅ (E2E `admin edits pending vacation request`)
5. DB-Verify: 7 Rows in `time_entry_audit_logs` mit `source='vacation_request_edit'` (siehe oben).

---

## Empfehlungen für PR-Reviewer

1. **Lesefolge:** Spec → Plan → Diff in Commit-Reihenfolge (`2a11131..41927da`).
2. **Kritische Stellen für manuellen Check:** `model_fields_set`-Pattern in beiden PATCH-Endpoints (Tasks 3 + 5), Tenant-Filter im Lookup, Audit-Row-Felder (insb. `user_id` vs `changed_by`).
3. **Out-of-Scope-Followups (Issue ggf. eröffnen):**
   - `withdraw_vacation_request` mit `with_for_update` nachrüsten
   - Helper extrahieren wenn 3. Call-Site auftaucht
   - `@theme { --z-modal: 10000; }` formalisieren statt ad-hoc `z-10000`-Klasse
