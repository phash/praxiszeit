# Journal Inline-Editing – Design

**Ziel:** Admin und Mitarbeiter können Zeiteinträge direkt im Monatsjournal bearbeiten, anlegen und löschen.

**Referenz:** Feature-Anfrage nach Issue #44 (Monatsjournal)

---

## Architektur

**Ansatz:** Getrennte Pfade je Rolle, gemeinsame UI-Komponente.

- **Admin**: Direkte Änderungen über bestehende Endpoints (`PUT /api/admin/time-entries/{id}`, `POST /api/admin/users/{userId}/time-entries`, `DELETE /api/admin/time-entries/{id}`). Alle schreiben automatisch in `TimeEntryAuditLog`. Kein neues Backend erforderlich.
- **Mitarbeiter**: Änderungen werden lokal im React-State gesammelt (Draft-State). Beim Absenden öffnet ein Modal mit einem gemeinsamen Begründungsfeld. Dann wird je eine `POST /api/change-requests/` pro Änderung abgesendet.

---

## UI-Verhalten

### Edit-Modus pro Zeile

Jede Zeile (Werktag mit Eintrag) bekommt ein Stift-Icon am Zeilenende:
- Klick → Zeile wechselt in Edit-Modus
- Von/Bis-Zellen → `<input type="time">`
- Pause-Zelle → `<input type="number">` (Minuten)
- Zeile zeigt ✓ (Bestätigen) und ✗ (Abbrechen)
- Trash-Icon zum Löschen des Eintrags

### Leere Werktage

Werktage ohne Eintrag (`type="empty"`) zeigen ein "+" Icon:
- Klick → Zeile wechselt in Create-Modus mit leeren Von/Bis/Pause-Feldern
- ✓ speichert / ✗ bricht ab

### Scope-Einschränkungen

- Nur Vergangenheit (heute und Zukunft nicht editierbar — wie bestehende ChangeRequests)
- Maximal ein Eintrag pro Tag anlegbar (kein Multi-Entry-Create)
- Wochenenden und Feiertage: kein Edit-Icon

---

## Admin-Flow

1. Stift-Icon klicken → Inline-Edit-Modus
2. Werte ändern → ✓ klicken
3. Sofortiger API-Call → optimistisches Update → Journal-Daten neu laden
4. Logging erfolgt automatisch über `TimeEntryAuditLog` (bereits in den Endpoints verdrahtet)

**Endpoints (bestehend):**
- `POST /api/admin/users/{userId}/time-entries` — neuen Eintrag anlegen
- `PUT /api/admin/time-entries/{entryId}` — Eintrag bearbeiten
- `DELETE /api/admin/time-entries/{entryId}` — Eintrag löschen

---

## Mitarbeiter-Flow

1. Stift-Icon klicken → Zeile wechselt in Edit-Modus (Draft)
2. Werte ändern → ✓ klicken → Änderung wird im lokalen Draft-State gespeichert
3. Fixierter Footer erscheint: `"N Änderungen ausstehend [Absenden]"`
4. Klick "Absenden" → Modal öffnet mit gemeinsamer Begründungs-Textarea
5. Submit → POST /api/change-requests/ pro Änderung (create/update/delete)
6. Erfolg → Draft-State leeren, Journal neu laden, Toast-Bestätigung

**Endpoint (bestehend):**
- `POST /api/change-requests/` mit `request_type`, `time_entry_id`, proposed values, `reason`

---

## Tabellenstruktur (angepasst)

| Datum | Tag | Typ | Von–Bis | Pause | Ist | Soll | Saldo | **Aktionen** |
|-------|-----|-----|---------|-------|-----|------|-------|-------------|
| 09.03. | Mo | Arbeitszeit | 08:00–17:00 | 45 min | 8,25h | 8h | +0,25h | ✏️ |
| 11.03. | Mi | – (fehlt) | — | — | 0h | 8h | −8h | ➕ |
| 14.03. | Sa | Wochenende | — | — | — | — | — | — |

---

## Implementierung

### Frontend-Änderungen

- `MonthlyJournal.tsx` — Edit-State, Inline-Inputs, Aktions-Icons, Admin/Employee-Pfade
- Neues `SubmitChangesModal.tsx` — Begründungs-Modal für Mitarbeiter

### Backend

Keine Änderungen notwendig — alle Endpoints bereits vorhanden.

---

## Testing

- Backend: Keine neuen Unit-Tests (bestehende Endpoints bereits getestet)
- E2E: `e2e/tests/admin/journal-editing.spec.ts` + `e2e/tests/employee/journal-editing.spec.ts`
  - Admin: Inline-Edit speichert direkt, Audit-Log enthält Eintrag
  - Mitarbeiter: Änderungen sammeln, Modal öffnet, ChangeRequest wird erstellt
