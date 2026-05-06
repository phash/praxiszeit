# Bearbeitung offener Urlaubsanträge — Design & Spec

## Context

Mitarbeiter und Admins können heute offene (`pending`) Urlaubsanträge nur **anlegen, sehen, genehmigen, ablehnen oder zurückziehen** — aber nicht editieren. Wenn ein Mitarbeiter einen Tippfehler im Datum macht oder ein anderer Tag passender ist, bleibt nur "Antrag zurückziehen + neu stellen". Das verliert den `created_at`-Stempel und sieht für den Admin nach Spam aus.

Diese Spec ergänzt **In-place Edit für `pending` Urlaubsanträge** für beide Rollen, mit Re-Validation, sauberem Audit-Log-Eintrag, RLS- und Tenant-Isolation, sowie E2E-Verifikation.

**Scope-Klemmung:** Nur `pending`. Bei `approved` existieren bereits `Absence`-Rows; das ist Storno-Territorium und unverändert. Bei `rejected`/`withdrawn` ist Edit semantisch sinnlos.

---

## 1. Backend

### 1.1 Neue Pydantic-Schemas

`backend/app/schemas/vacation_request.py`:

```python
class VacationRequestUpdate(BaseModel):
    date: Optional[date] = None
    end_date: Optional[date] = None
    hours: Optional[float] = None
    note: Optional[str] = None
    absence_type: Optional[str] = None

    @field_validator('absence_type')
    @classmethod
    def validate_absence_type(cls, v):
        if v is None:
            return v
        allowed = {"vacation", "training", "overtime", "other"}
        if v not in allowed:
            raise ValueError(f'absence_type muss einer von {allowed} sein')
        return v
```

Begründung: alle Felder optional → partielle Updates. `sick` ist als `absence_type` weiter ausgeschlossen (analog zu Create), da Krankheit nicht über Anträge läuft.

### 1.2 Mitarbeiter-Endpoint

`PATCH /api/vacation-requests/{request_id}` in `backend/app/routers/vacation_requests.py`:

- **Auth:** `current_user` muss Owner sein (`vr.user_id == current_user.id`), sonst 403
- **Status:** muss `pending` sein, sonst 400 (`"Nur offene Anträge können bearbeitet werden"`)
- **Tenant:** Filter auf `tenant_id == current_user.tenant_id`
- **Lock:** `with_for_update()` (Race-Condition mit gleichzeitigem Approve)
- **Re-Validation:** identisch zu `create_vacation_request`:
  - Range-Sanity (`end_date >= start_date`)
  - `first_work_day` / `last_work_day`
  - **Vacation-Budget** (für `vacation`-Typ): `get_vacation_account` summiert nur `Absence`-Rows (kommen erst nach Approve). Pending-Anträge zählen also nicht im Budget mit → Edit muss **nichts** self-excluden. Logik = identisch zu Create.
  - **Pending-Overlap-Check** muss **diesen Antrag selbst ausschließen** (`VacationRequest.id != request_id`), sonst rejecten alle Edits gegen sich selbst.
- **Audit:** `TimeEntryAuditLog` mit `time_entry_id=NULL`, `action="update"`, `source="vacation_request_edit"` (21 chars, fits 40), `old_note`/`new_note` als kompakter String:
  ```
  vacation_request <uuid> | <date>..<end_date|date> | <type> | <hours>h | <note or "">
  ```
- **Response:** der enrichte `VacationRequestResponse` (mit `days`, Namen)

### 1.3 Admin-Endpoint

`PATCH /api/admin/vacation-requests/{request_id}` in `backend/app/routers/admin_vacations.py`:

- **Auth:** `require_admin`
- Sonst identische Logik, aber: `target_user = vr.user_id` (Admin editiert für jemand anderen)
- Tenant-Isolation: `vr.tenant_id == current_user.tenant_id`
- Audit: `user_id=vr.user_id` (betroffener MA), `changed_by=current_user.id` (Admin)
- Budget-Check gegen den **Owner** des Antrags, nicht den Admin

### 1.4 Audit-Format-Helper

Eine kleine Helper-Funktion `_format_vacation_request_audit_text(vr)` in `vacation_requests.py`, damit Old/New denselben Format-Code teilen:

```python
def _format_vacation_request_audit_text(vr: VacationRequest) -> str:
    end = vr.end_date if vr.end_date else vr.date
    note = (vr.note or "").replace("\n", " ").strip()[:200]
    return (
        f"vacation_request {vr.id} | "
        f"{vr.date}..{end} | "
        f"{vr.absence_type or 'vacation'} | "
        f"{float(vr.hours):.2f}h"
        + (f" | {note}" if note else "")
    )
```

Note-Truncation auf 200 chars — `old_note`/`new_note` sind `Text` (kein Limit), aber sehr lange Notizen verhageln Reports.

### 1.5 RLS / Tenant

Der `RLSMiddleware` setzt `app.current_tenant_id` bereits per Request. Beide neuen Endpoints filtern explizit zusätzlich auf `VacationRequest.tenant_id == current_user.tenant_id` (belt-and-suspenders pro F-026). Audit-Insert nutzt `tenant_id=current_user.tenant_id`.

---

## 2. Frontend

### 2.1 Neue Komponente: `VacationRequestEditModal`

`frontend/src/components/VacationRequestEditModal.tsx` — wiederverwendbar für beide Pages.

**Props:**
- `request: VacationRequest` (Initialwerte)
- `mode: 'self' | 'admin'` (entscheidet API-Pfad)
- `onClose: () => void`
- `onSaved: () => void`

**Form-Felder:**
- "Zeitraum (mehrere Tage)"-Checkbox (auto-aktiv wenn `end_date` gesetzt)
- Datum / Datum-Bis (date-pickers)
- Typ-Dropdown (`vacation`, `training`, `overtime`, `other` — kein `sick`)
- Stunden (`number`, `step=0.5`)
- Notiz (`text`)
- Footer: Abbrechen + Speichern

**Verhalten:**
- Submit → `apiClient.patch(<endpoint>, payload)` mit `endpoint = mode === 'admin' ? \`/admin/vacation-requests/${id}\` : \`/vacation-requests/${id}\``
- Toast Success/Error via `useToast` + `getErrorMessage`
- Modal schließt nur bei Erfolg
- Disable Submit während Request läuft

### 2.2 UI-Hookup

**`frontend/src/pages/admin/VacationApprovals.tsx`**: Neuer "Bearbeiten"-Button (Pencil-Icon) auf jeder `pending`-Karte, neben Genehmigen/Ablehnen. Klick öffnet Modal mit `mode='admin'`.

**`frontend/src/pages/AbsenceCalendarPage.tsx`** (MA-Sicht, Tab "Meine Anträge"): Edit-Button (Pencil) nur auf `pending`-Karten, neben dem Trash-Button. Klick öffnet Modal mit `mode='self'`.

Kein Whole-Card-Click — vermeidet Accident-Klicks während des Lesens.

### 2.3 Refresh

Nach `onSaved`: Liste neu laden (existing `fetchRequests` / `fetchMyVacationRequests`).

---

## 3. Audit-Verhalten

Beim Edit wird **eine** `TimeEntryAuditLog`-Row geschrieben:

| Spalte | Wert |
|--------|------|
| `time_entry_id` | NULL |
| `tenant_id` | `current_user.tenant_id` |
| `user_id` | `vr.user_id` (betroffener MA) |
| `changed_by` | `current_user.id` (MA selbst oder Admin) |
| `action` | `"update"` |
| `source` | `"vacation_request_edit"` |
| `old_note` | Format-Helper auf altem `vr` (vor Update) |
| `new_note` | Format-Helper auf neuem `vr` (nach Update, vor Commit) |
| `old_date` / `new_date` | `vr.date` Vor/Nach (für SQL-Filter & Reports) |
| `old_break_minutes` / `new_break_minutes` | NULL (irrelevant) |

Kein Eintrag wenn keiner der Felder sich tatsächlich ändert (No-op-Edit) → 200 mit Response, aber keine Audit-Row und kein DB-Update. Spart Lärm im Audit.

---

## 4. Backend-Tests (pytest)

`backend/tests/test_vacation_request_edit.py`:

1. Edit own pending → 200, Felder geändert, Audit-Row exists mit korrektem Source/User
2. Edit foreign pending (other user) → 403
3. Edit approved → 400 (nicht erlaubt)
4. Edit rejected → 400
5. Admin edit foreign user pending → 200, `changed_by=admin.id`, `user_id=mitarbeiter.id`
6. Admin edit pending in foreign tenant → 404 (nicht 403, um Existenz nicht zu leaken)
7. Re-Validation: `end_date < date` → 400
8. Re-Validation: Datum vor `first_work_day` → 400
9. Vacation-Budget-Check schließt eigenen Antrag aus (Edit darf nicht sich-selbst-doppelt-zählen)
10. Pending-Overlap-Check schließt eigenen Antrag aus
11. No-op edit (gleiche Werte) → 200, keine Audit-Row geschrieben
12. Cross-Tenant-Audit: Audit-Row landet im richtigen Tenant
13. `absence_type='sick'` im Update wird abgelehnt (Validator)

## 5. E2E-Tests (Playwright)

`e2e/tests/admin/vacation-approvals.spec.ts` (neuer Block) + `e2e/tests/employee/absences.spec.ts` (neuer Block):

1. **Admin editiert MA-Antrag**: setup via `createVacationRequest`-Fixture mit `unique-note`, navigiere zu Vacation-Approvals, klick Bearbeiten-Button auf der Card, ändere Datum, speichern → Toast sichtbar, Card zeigt neues Datum, Approval-Setting wird sauber abgeräumt.
2. **MA editiert eigenen Antrag**: ähnlich, in `AbsenceCalendarPage` → "Meine Anträge"-Tab → Bearbeiten → Stunden ändern → Toast.
3. **Modal zeigt Initialwerte**: nach Klick öffnet das Modal mit korrektem Datum/Stunden/Notiz prefilled.

Cleanup nutzt die existierende `createVacationRequest`-Fixture (Issue: nach Edit ist `request.id` nicht mehr identisch → Fixture-Teardown muss fehlertolerant DELETE machen, das tut sie bereits).

---

## 6. Security-Review (eigener Abschnitt im Bericht)

- **AuthZ Self vs Admin-Endpoint:** MA-Endpoint prüft Owner via `str(vr.user_id) == str(current_user.id)`. Admin-Endpoint via `require_admin` Dependency. Keine Vermischung.
- **Tenant-Isolation:** beide Endpoints filtern `tenant_id`-Spalte zusätzlich zur RLS (F-026 belt-and-suspenders).
- **Race Condition Approve-vs-Edit:** beide Pfade nutzen `with_for_update()` auf der `vacation_requests`-Row. Approve liest `status==pending`, Edit auch. Das gewinnende Lock entscheidet. Kein verlorenes Update-Window.
- **Mass-Assignment:** Pydantic-Schema enthält **kein** `status`/`reviewed_by`/`reviewed_at` — also kein Weg, einen Antrag durch Edit zu auto-genehmigen.
- **Validierung:** `absence_type`-Whitelist, `end_date >= date`, Budget-Check, first/last_work_day. Wenn Frontend `sick` schickt → Pydantic 422.
- **Audit:** kann nicht umgangen werden, da inline im Endpoint vor `commit`. Bei Exception → Rollback, kein partieller State.
- **License-Middleware:** `LicenseReadOnlyMiddleware` blockt PATCH wenn Lizenz abgelaufen — automatisch durch Methoden-Allowlist.
- **Rate-Limit:** keiner explizit für Edit; vorhandene globale Auth-Middleware/Cookies reichen, da Antrags-Edit nicht für Brute-Force-Vektoren attraktiv ist.

## 7. DSGVO-Review (eigener Abschnitt im Bericht)

- **Art. 5 Abs. 2 (Rechenschaftspflicht):** Audit-Row dokumentiert die Änderung mit Wer/Wann/Was/Vorher/Nachher.
- **Art. 6 (Rechtmäßigkeit):** Verarbeitung des Notiz-Felds erfolgt zur Vertragsdurchführung (Arbeitszeit-Abwicklung). Hinweis-Text "Bitte keine Gesundheitsangaben" steht im Modal-Form.
- **Art. 9 (besondere Kategorien):** `absence_type='sick'` ist im Edit nicht zulässig (Validator). Für Krankheit gibt es den separaten `/absences`-Pfad mit Maskierung im Calendar-Endpoint. Edit kann also keine Krankheits-Info versehentlich offen legen.
- **Art. 5 Abs. 1 lit. c (Datenminimierung):** alte+neue Notiz wird nur in `old_note`/`new_note` (Text-Felder, tenant-scoped) abgelegt. Truncation auf 200 chars verhindert excessive payloads.
- **Art. 32 (Sicherheit):** Audit-Logs sind tenant-scoped via RLS-Policy und nur durch Admin-Routen einsehbar. Login + JWT-Auth ist für alle PATCH-Calls Pflicht.
- **Art. 17 (Recht auf Löschung):** wenn ein User gelöscht wird, ist das ein laufender DSGVO-Pfad in `admin_users.py` (cascade/anonymize). Diese Spec macht keine neue Persistenzkategorie auf — `vacation_requests` cascade ist FK-bestimmt; Audit-Log wird im DSGVO-Pfad bereits anonymisiert.
- **Art. 30 (Verzeichnis):** Verarbeitung "Urlaubsanträge bearbeiten" fällt unter den existierenden Eintrag "Arbeitszeit-/Abwesenheitsverwaltung". Kein neuer Eintrag nötig.

---

## 8. Reihenfolge der Umsetzung

1. Backend-Schema + MA-PATCH-Endpoint + pytest-Tests
2. Backend Admin-PATCH-Endpoint + pytest-Tests (Cross-Tenant-Cases)
3. Frontend `VacationRequestEditModal`-Komponente
4. Hookup in `VacationApprovals.tsx` + `AbsenceCalendarPage.tsx`
5. E2E-Tests (Admin + MA)
6. Security/DSGVO-Berichte schreiben (eigene Sektion in Commit-Body / PR-Description)

## 9. Out of Scope

- Edit von approved/rejected/withdrawn Anträgen
- Edit von Audit-Log selbst
- Bulk-Edit
- Änderungs-Historie als UI (Audit-Page existiert getrennt)
- Email-Notification an Admin/MA bei Edit
