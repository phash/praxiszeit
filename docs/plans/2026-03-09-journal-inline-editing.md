# Journal Inline-Editing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Admin und Mitarbeiter können Zeiteinträge direkt im Monatsjournal bearbeiten, anlegen und löschen — Admin sofort mit Audit-Log, Mitarbeiter gesammelt als Änderungsantrag.

**Architecture:** Rein frontend-seitig. Die bestehenden Admin-Endpoints (`POST/PUT/DELETE /api/admin/…/time-entries`) und der Employee-Endpoint (`POST /api/change-requests/`) werden direkt genutzt. `MonthlyJournal.tsx` erhält Edit-State, Inline-Inputs und rollenspezifische Save-Logik. Ein neues `SubmitChangesModal.tsx` sammelt die Employee-Änderungen und sendet sie gebündelt.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Lucide React, axios (apiClient), date-fns

---

## Referenzen

- Design-Doc: `docs/plans/2026-03-09-journal-inline-editing-design.md`
- Zu modifizierende Hauptkomponente: `frontend/src/components/MonthlyJournal.tsx`
- Admin-Endpoints (bestehend, mit Audit-Logging):
  - `POST /api/admin/users/{userId}/time-entries` — neuen Eintrag anlegen
  - `PUT /api/admin/time-entries/{entryId}` — Eintrag bearbeiten
  - `DELETE /api/admin/time-entries/{entryId}` — Eintrag löschen
- Employee-Endpoint: `POST /api/change-requests/` mit `request_type` (create/update/delete), `time_entry_id`, proposed values, `reason`
- Toast-System: `import { useToast } from '../contexts/ToastContext'` → `toast.success/error()`
- Bestehende Schemas: `TimeEntryCreate` hat `date`, `start_time`, `end_time`, `break_minutes`; `ChangeRequestCreate` hat `request_type`, `time_entry_id?`, `proposed_date?`, `proposed_start_time?`, `proposed_end_time?`, `proposed_break_minutes?`, `reason`

---

## Task 1: Edit-State + Aktionen-Spalte + Inline-Inputs

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`

Dieser Task fügt den Edit-Modus hinzu. Noch kein API-Aufruf — nur die UI. Am Ende sieht man das Stift-/Plus-Icon pro Zeile und kann eine Zeile in den Edit-Modus schalten.

### Step 1: Imports und neue Interfaces ergänzen

Am Anfang von `MonthlyJournal.tsx`, die bestehende Importzeile ersetzen:

```tsx
import { useState, useEffect } from 'react';
import { format, parseISO, isBefore, startOfDay } from 'date-fns';
import { de } from 'date-fns/locale';
import { Pencil, Plus, Trash2, Check, X } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { useToast } from '../contexts/ToastContext';
import MonthSelector from './MonthSelector';
import LoadingSpinner from './LoadingSpinner';
```

Nach den bestehenden Interfaces (`JournalData` etc.) folgende neue Interfaces einfügen:

```tsx
interface EditState {
  startTime: string;   // "HH:mm"
  endTime: string;     // "HH:mm"
  breakMinutes: string; // string for <input> binding
}

export interface DraftChange {
  type: 'create' | 'update' | 'delete';
  date: string;           // "YYYY-MM-DD"
  entryId?: string;       // for update/delete
  startTime?: string;     // for create/update
  endTime?: string;       // for create/update
  breakMinutes?: number;  // for create/update
}
```

### Step 2: Neue State-Variablen im Komponenten-Body hinzufügen

Direkt nach den bestehenden State-Variablen (`data`, `loading`, `error`):

```tsx
const toast = useToast();
const [editingDate, setEditingDate] = useState<string | null>(null);
const [editState, setEditState] = useState<EditState>({ startTime: '', endTime: '', breakMinutes: '0' });
const [saving, setSaving] = useState(false);
// Employee draft
const [draftChanges, setDraftChanges] = useState<DraftChange[]>([]);
const [showSubmitModal, setShowSubmitModal] = useState(false);
```

### Step 3: Hilfsfunktionen ergänzen

Nach den bestehenden `formatHours`/`formatHoursSimple` Funktionen:

```tsx
function isPastDay(dateStr: string): boolean {
  return isBefore(parseISO(dateStr), startOfDay(new Date()));
}

function startEdit(day: JournalDay) {
  const entry = day.time_entries[0] ?? null;
  setEditingDate(day.date);
  setEditState({
    startTime: entry?.start_time ?? '',
    endTime: entry?.end_time ?? '',
    breakMinutes: String(entry?.break_minutes ?? 0),
  });
}

function cancelEdit() {
  setEditingDate(null);
}
```

### Step 4: Tabellen-Header – Aktionen-Spalte ergänzen

In der `<thead>`, nach der letzten `<th>` (Saldo):

```tsx
<th className="px-3 py-2 text-right w-16"></th>
```

### Step 5: Zeilen-Rendering anpassen

Im `data.days.map(...)` Block, die bestehende Return-Zeile anpassen. Das Grundmuster:

- Vorher: `<tr key={day.date} className={...}>` mit 8 `<td>` Zellen
- Nachher: Die bestehenden Zellen bleiben, nur diese zwei ändern sich:
  1. **Von–Bis-Zelle** (4. `<td>`): im Edit-Modus zwei `<input type="time">`
  2. **Pause-Zelle** (5. `<td>`): im Edit-Modus ein `<input type="number">`
  3. **Neue Aktionen-Zelle** (9. `<td>`): am Ende

Ersetze die Von–Bis-Zelle:
```tsx
<td className="px-3 py-2 hidden md:table-cell text-gray-600 whitespace-nowrap">
  {isGray ? '–' : editingDate === day.date ? (
    <div className="flex items-center gap-1">
      <input
        type="time"
        value={editState.startTime}
        onChange={(e) => setEditState(s => ({ ...s, startTime: e.target.value }))}
        className="w-[5.5rem] border border-gray-300 rounded px-1 py-0.5 text-sm"
      />
      <span className="text-gray-400">–</span>
      <input
        type="time"
        value={editState.endTime}
        onChange={(e) => setEditState(s => ({ ...s, endTime: e.target.value }))}
        className="w-[5.5rem] border border-gray-300 rounded px-1 py-0.5 text-sm"
      />
    </div>
  ) : vonBis}
</td>
```

Ersetze die Pause-Zelle:
```tsx
<td className="px-3 py-2 hidden md:table-cell text-right text-gray-500">
  {isGray ? '' : editingDate === day.date ? (
    <input
      type="number"
      min={0}
      max={480}
      value={editState.breakMinutes}
      onChange={(e) => setEditState(s => ({ ...s, breakMinutes: e.target.value }))}
      className="w-16 border border-gray-300 rounded px-1 py-0.5 text-sm text-right"
    />
  ) : pause}
</td>
```

Füge die Aktionen-Zelle als letzte `<td>` ein:
```tsx
<td className="px-3 py-2 text-right whitespace-nowrap">
  {editingDate === day.date ? (
    <div className="flex items-center justify-end gap-1">
      <button
        onClick={() => { /* TODO Task 2/3 */ cancelEdit(); }}
        disabled={saving}
        className="p-1 text-green-600 hover:text-green-800 disabled:opacity-50"
        title="Speichern"
      >
        <Check size={15} />
      </button>
      <button
        onClick={cancelEdit}
        disabled={saving}
        className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
        title="Abbrechen"
      >
        <X size={15} />
      </button>
      {day.time_entries.length > 0 && (
        <button
          onClick={() => { /* TODO Task 2/3 */ cancelEdit(); }}
          disabled={saving}
          className="p-1 text-red-400 hover:text-red-600 disabled:opacity-50"
          title="Löschen"
        >
          <Trash2 size={15} />
        </button>
      )}
    </div>
  ) : !isGray && isPastDay(day.date) ? (
    day.time_entries.length > 0 ? (
      <button
        onClick={() => startEdit(day)}
        className="p-1 text-gray-400 hover:text-gray-600"
        title="Bearbeiten"
      >
        <Pencil size={14} />
      </button>
    ) : (
      <button
        onClick={() => startEdit(day)}
        className="p-1 text-blue-400 hover:text-blue-600"
        title="Eintrag anlegen"
      >
        <Plus size={14} />
      </button>
    )
  ) : null}
</td>
```

### Step 6: TypeScript-Check

```bash
cd /e/claude/zeiterfassung/praxiszeit/frontend && npx tsc --noEmit 2>&1 | head -20
```

Erwartet: Nur das bekannte `qrcode.react`-Error, keine neuen Fehler.

### Step 7: Commit

```bash
cd /e/claude/zeiterfassung/praxiszeit
git add frontend/src/components/MonthlyJournal.tsx
git commit -m "feat(journal): add edit state, actions column, and inline inputs"
```

---

## Task 2: Admin Save (direkte API-Calls)

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`

Die `TODO`-Platzhalter im Check-Button und Trash-Button werden durch echte API-Calls ersetzt.

### Step 1: `handleAdminSave` Funktion einfügen

Nach der `cancelEdit()` Funktion:

```tsx
async function handleAdminSave(day: JournalDay) {
  const start = editState.startTime;
  const end = editState.endTime;
  if (!start || !end) {
    toast.error('Von und Bis sind Pflichtfelder');
    return;
  }
  setSaving(true);
  try {
    const payload = {
      start_time: start,
      end_time: end,
      break_minutes: parseInt(editState.breakMinutes, 10) || 0,
    };
    const existing = day.time_entries[0];
    if (existing) {
      await apiClient.put(`/admin/time-entries/${existing.id}`, payload);
    } else {
      await apiClient.post(`/admin/users/${userId}/time-entries`, {
        date: day.date,
        ...payload,
      });
    }
    toast.success('Gespeichert');
    cancelEdit();
    // Reload journal
    setData(null);
    setLoading(true);
  } catch (err) {
    toast.error(getErrorMessage(err, 'Fehler beim Speichern'));
  } finally {
    setSaving(false);
  }
}

async function handleAdminDelete(day: JournalDay) {
  const entry = day.time_entries[0];
  if (!entry) return;
  setSaving(true);
  try {
    await apiClient.delete(`/admin/time-entries/${entry.id}`);
    toast.success('Eintrag gelöscht');
    cancelEdit();
    setData(null);
    setLoading(true);
  } catch (err) {
    toast.error(getErrorMessage(err, 'Fehler beim Löschen'));
  } finally {
    setSaving(false);
  }
}
```

**Hinweis:** `setData(null); setLoading(true)` triggert den `useEffect` neu, da `selectedMonth` unverändert bleibt. Damit der Reload passiert, brauchen wir einen separaten Reload-Trigger. Füge zu den State-Variablen hinzu:

```tsx
const [reloadKey, setReloadKey] = useState(0);
```

Ändere den `useEffect`-Dependency-Array:
```tsx
}, [selectedMonth, userId, isAdminView, reloadKey]);
```

Ersetze `setData(null); setLoading(true)` in beiden Funktionen durch:
```tsx
setReloadKey(k => k + 1);
```

### Step 2: TODOs in den Aktions-Buttons ersetzen

Im Check-Button (✓), den `onClick`-Handler:
```tsx
onClick={() => isAdminView ? handleAdminSave(day) : cancelEdit()}
```

Im Trash-Button:
```tsx
onClick={() => isAdminView ? handleAdminDelete(day) : cancelEdit()}
```

### Step 3: TypeScript-Check

```bash
cd /e/claude/zeiterfassung/praxiszeit/frontend && npx tsc --noEmit 2>&1 | head -20
```

### Step 4: Manuell testen (Docker läuft)

1. Als Admin einloggen → `/admin/users` → Journal eines Mitarbeiters öffnen
2. Vergangenen leeren Werktag → `+` klicken → Von/Bis eingeben → ✓
3. Ergebnis: Eintrag erscheint in der Tabelle, Toast "Gespeichert"
4. Pencil-Icon → Zeiten ändern → ✓ → Tabelle aktualisiert sich
5. Trash-Icon → Eintrag verschwindet

### Step 5: Commit

```bash
cd /e/claude/zeiterfassung/praxiszeit
git add frontend/src/components/MonthlyJournal.tsx
git commit -m "feat(journal): admin direct save with audit logging via existing endpoints"
```

---

## Task 3: Employee Draft State + SubmitChangesModal

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`
- Create: `frontend/src/components/SubmitChangesModal.tsx`

### Step 1: `SubmitChangesModal.tsx` anlegen

```tsx
// frontend/src/components/SubmitChangesModal.tsx
import { useState } from 'react';
import { X } from 'lucide-react';
import apiClient from '../api/client';
import { getErrorMessage } from '../utils/errorMessage';
import { useToast } from '../contexts/ToastContext';
import type { DraftChange } from './MonthlyJournal';

const TYPE_LABEL: Record<DraftChange['type'], string> = {
  create: 'Neu anlegen',
  update: 'Ändern',
  delete: 'Löschen',
};

interface Props {
  changes: DraftChange[];
  onSuccess: () => void;
  onClose: () => void;
}

export default function SubmitChangesModal({ changes, onSuccess, onClose }: Props) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!reason.trim()) {
      toast.error('Bitte eine Begründung angeben');
      return;
    }
    setSubmitting(true);
    try {
      for (const change of changes) {
        const payload: Record<string, unknown> = {
          request_type: change.type,
          reason: reason.trim(),
        };
        if (change.entryId) payload.time_entry_id = change.entryId;
        if (change.type !== 'delete') {
          payload.proposed_date = change.date;
          payload.proposed_start_time = change.startTime;
          payload.proposed_end_time = change.endTime;
          payload.proposed_break_minutes = change.breakMinutes ?? 0;
        }
        await apiClient.post('/change-requests/', payload);
      }
      toast.success(`${changes.length} Änderungsantrag${changes.length > 1 ? 'anträge' : ''} eingereicht`);
      onSuccess();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Fehler beim Einreichen'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Änderungsanträge einreichen</h2>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Summary of changes */}
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-700">{changes.length} Änderung(en):</p>
            <ul className="text-sm text-gray-600 space-y-0.5">
              {changes.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-gray-400">{c.date}</span>
                  <span>{TYPE_LABEL[c.type]}</span>
                  {c.startTime && c.endTime && (
                    <span className="text-gray-500">{c.startTime}–{c.endTime}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {/* Reason */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Begründung <span className="text-red-500">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Warum müssen diese Zeiten angepasst werden?"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-gray-700 border rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !reason.trim()}
            className="px-4 py-2 text-sm bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50"
          >
            {submitting ? 'Wird eingereicht…' : 'Absenden'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### Step 2: Employee-Funktionen in MonthlyJournal.tsx ergänzen

Import hinzufügen (am Anfang der Datei):
```tsx
import SubmitChangesModal from './SubmitChangesModal';
```

Nach `handleAdminDelete` die Employee-Funktionen einfügen:

```tsx
function handleEmployeeSave(day: JournalDay) {
  const start = editState.startTime;
  const end = editState.endTime;
  if (!start || !end) {
    toast.error('Von und Bis sind Pflichtfelder');
    return;
  }
  const existing = day.time_entries[0];
  const change: DraftChange = {
    type: existing ? 'update' : 'create',
    date: day.date,
    entryId: existing?.id,
    startTime: start,
    endTime: end,
    breakMinutes: parseInt(editState.breakMinutes, 10) || 0,
  };
  setDraftChanges(prev => {
    // Replace existing draft for same date
    const filtered = prev.filter(c => c.date !== day.date);
    return [...filtered, change];
  });
  cancelEdit();
}

function handleEmployeeDelete(day: JournalDay) {
  const entry = day.time_entries[0];
  if (!entry) return;
  const change: DraftChange = {
    type: 'delete',
    date: day.date,
    entryId: entry.id,
  };
  setDraftChanges(prev => {
    const filtered = prev.filter(c => c.date !== day.date);
    return [...filtered, change];
  });
  cancelEdit();
}
```

### Step 3: Check-/Trash-Buttons auf Employee-Pfad erweitern

Ersetze die onClick-Handler:
```tsx
// Check-Button (Speichern):
onClick={() => isAdminView ? handleAdminSave(day) : handleEmployeeSave(day)}

// Trash-Button (Löschen):
onClick={() => isAdminView ? handleAdminDelete(day) : handleEmployeeDelete(day)}
```

### Step 4: Pending-Footer und Modal einbinden

Direkt nach dem schließenden `</>` der `{data && !loading && (` Section (also nach den Aggregate-Kacheln, innerhalb des `<div className="space-y-4">`):

```tsx
{/* Employee: pending changes footer */}
{!isAdminView && draftChanges.length > 0 && (
  <div className="sticky bottom-4 bg-amber-50 border border-amber-200 rounded-lg shadow-md p-3 flex items-center justify-between">
    <span className="text-sm text-amber-800">
      <strong>{draftChanges.length}</strong> Änderung{draftChanges.length > 1 ? 'en' : ''} ausstehend
    </span>
    <div className="flex gap-2">
      <button
        onClick={() => setDraftChanges([])}
        className="text-sm text-amber-700 hover:text-amber-900 underline"
      >
        Verwerfen
      </button>
      <button
        onClick={() => setShowSubmitModal(true)}
        className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700"
      >
        Absenden
      </button>
    </div>
  </div>
)}

{/* Employee: submit modal */}
{showSubmitModal && (
  <SubmitChangesModal
    changes={draftChanges}
    onSuccess={() => {
      setShowSubmitModal(false);
      setDraftChanges([]);
      setReloadKey(k => k + 1);
    }}
    onClose={() => setShowSubmitModal(false)}
  />
)}
```

### Step 5: Draft-Anzeige in der Tabelle (visual indicator)

Im `data.days.map(...)` Block, vor dem `return (`:

```tsx
const draft = draftChanges.find(c => c.date === day.date);
const isDraft = !!draft;
const isDraftDelete = draft?.type === 'delete';
```

Passe `rowClass` an:
```tsx
const rowClass = isGray
  ? 'bg-gray-50 text-gray-400'
  : isDraft
  ? 'bg-amber-50'
  : 'bg-white';
```

Zeige in der Von–Bis-Zelle (im non-edit, non-gray Fall) Draft-Werte:
```tsx
{isGray ? '–' : editingDate === day.date ? (
  /* inputs ... */
) : isDraft && draft.type !== 'delete' ? (
  <span className="text-amber-700">{draft.startTime}–{draft.endTime}</span>
) : isDraftDelete ? (
  <span className="line-through text-gray-400">{vonBis}</span>
) : vonBis}
```

### Step 6: TypeScript-Check

```bash
cd /e/claude/zeiterfassung/praxiszeit/frontend && npx tsc --noEmit 2>&1 | head -20
```

Erwartet: Nur das bekannte `qrcode.react`-Error.

### Step 7: Manuell testen

1. Als Mitarbeiter einloggen → `/journal`
2. Vergangenen leeren Werktag → `+` → Von 09:00, Bis 17:00 → ✓
   - Zeile wird amber hinterlegt mit "09:00–17:00"
   - Footer: "1 Änderung ausstehend [Absenden]"
3. Weiteren Tag bearbeiten → ✓ → "2 Änderungen ausstehend"
4. "Absenden" → Modal öffnet → Begründung eingeben → "Absenden"
   - Toast: "2 Änderungsanträge eingereicht"
   - Journal lädt neu, Footer verschwindet
5. Im ChangeRequests-Tab: zwei neue PENDING-Anträge sichtbar

### Step 8: Commit

```bash
cd /e/claude/zeiterfassung/praxiszeit
git add frontend/src/components/MonthlyJournal.tsx frontend/src/components/SubmitChangesModal.tsx
git commit -m "feat(journal): employee draft changes with SubmitChangesModal"
```

---

## Task 4: E2E Tests

**Files:**
- Create: `e2e/tests/admin/journal-editing.spec.ts`
- Create: `e2e/tests/employee/journal-editing.spec.ts`

### Step 1: Admin-Tests anlegen

```typescript
// e2e/tests/admin/journal-editing.spec.ts
import { test, expect } from '../../fixtures/base.fixture';

test.describe('Admin Journal Editing', () => {
  test.slow();

  test('Admin kann vergangenen leeren Tag anlegen', async ({ adminPage, testEmployee }) => {
    const today = new Date();
    // Find a past weekday: go back to last Monday
    const d = new Date(today);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7); // last Monday
    const year = d.getFullYear();
    const month = d.getMonth() + 1;

    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);

    // Navigate to the correct month if needed
    const monthStr = `${year}-${String(month).padStart(2, '0')}`;
    // MonthSelector shows current month by default – navigate if needed
    // For simplicity, use current month's past empty day
    const dayStr = String(d.getDate()).padStart(2, '0') + '.' + String(month).padStart(2, '0') + '.';

    // Find the row for that day and click the + button
    const row = adminPage.locator('table tbody tr').filter({ hasText: dayStr });
    const plusBtn = row.locator('button[title="Eintrag anlegen"]');
    // Only proceed if the + button exists (day must be empty and past)
    const hasPlusBtn = await plusBtn.count() > 0;
    test.skip(!hasPlusBtn, 'No empty past weekday found in current month');

    await plusBtn.click();

    // Fill in times
    await row.locator('input[type="time"]').first().fill('08:00');
    await row.locator('input[type="time"]').last().fill('16:30');

    // Save
    await row.locator('button[title="Speichern"]').click();

    // Row should now show the entry
    await expect(row).toContainText('08:00', { timeout: 5000 });
  });

  test('Admin kann bestehenden Eintrag bearbeiten', async ({ adminPage, testEmployee, createTimeEntry }) => {
    const today = new Date();
    // Use last Monday
    const d = new Date(today);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7);
    const dateStr = d.toISOString().split('T')[0];
    await createTimeEntry(testEmployee.id, {
      date: dateStr,
      start_time: '08:00',
      end_time: '16:00',
      break_minutes: 30,
    });

    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);

    const dayStr = String(d.getDate()).padStart(2, '0') + '.' + String(month).padStart(2, '0') + '.';
    const row = adminPage.locator('table tbody tr').filter({ hasText: dayStr });

    await row.locator('button[title="Bearbeiten"]').click();

    // Change end time
    await row.locator('input[type="time"]').last().fill('17:00');
    await row.locator('button[title="Speichern"]').click();

    // Row should show updated time
    await expect(row).toContainText('17:00', { timeout: 5000 });
  });

  test('Heutiger Tag hat kein Bearbeiten-Icon', async ({ adminPage, testEmployee }) => {
    await adminPage.goto(`/admin/users/${testEmployee.id}/journal`);
    const today = new Date();
    const dayStr = String(today.getDate()).padStart(2, '0') + '.' +
      String(today.getMonth() + 1).padStart(2, '0') + '.';
    const row = adminPage.locator('table tbody tr').filter({ hasText: dayStr });
    await expect(row.locator('button[title="Bearbeiten"]')).toHaveCount(0);
    await expect(row.locator('button[title="Eintrag anlegen"]')).toHaveCount(0);
  });
});
```

### Step 2: Employee-Tests anlegen

```typescript
// e2e/tests/employee/journal-editing.spec.ts
import { test, expect } from '../../fixtures/base.fixture';

test.describe('Employee Journal Editing (Change Requests)', () => {
  test.slow();

  test('Employee kann Änderungsantrag über Journal stellen', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    // Find a past empty weekday
    const plusBtn = employeePage.locator('button[title="Eintrag anlegen"]').first();
    const hasPlusBtn = await plusBtn.count() > 0;
    test.skip(!hasPlusBtn, 'No empty past weekday in current month');

    await plusBtn.click();

    // Fill in times
    const editRow = employeePage.locator('input[type="time"]').first().locator('../..'); // parent tr
    await employeePage.locator('input[type="time"]').first().fill('09:00');
    await employeePage.locator('input[type="time"]').last().fill('17:00');
    await employeePage.locator('button[title="Speichern"]').click();

    // Footer should appear
    await expect(employeePage.getByText('ausstehend')).toBeVisible({ timeout: 3000 });

    // Click Absenden
    await employeePage.getByRole('button', { name: 'Absenden' }).click();

    // Modal opens
    await expect(employeePage.getByRole('heading', { name: 'Änderungsanträge einreichen' })).toBeVisible();

    // Enter reason
    await employeePage.locator('textarea').fill('Nachträgliche Zeiterfassung');

    // Submit
    await employeePage.getByRole('button', { name: 'Absenden' }).last().click();

    // Success toast
    await expect(employeePage.getByText('eingereicht')).toBeVisible({ timeout: 5000 });

    // Footer gone
    await expect(employeePage.getByText('ausstehend')).toHaveCount(0, { timeout: 3000 });
  });

  test('Employee pending footer zeigt korrekte Anzahl', async ({ employeePage }) => {
    await employeePage.goto('/journal');
    await expect(employeePage.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    const plusBtns = employeePage.locator('button[title="Eintrag anlegen"]');
    const count = await plusBtns.count();
    test.skip(count < 2, 'Need at least 2 empty past days');

    // Add first change
    await plusBtns.first().click();
    await employeePage.locator('input[type="time"]').first().fill('08:00');
    await employeePage.locator('input[type="time"]').last().fill('16:00');
    await employeePage.locator('button[title="Speichern"]').click();
    await expect(employeePage.getByText('1 Änderung ausstehend')).toBeVisible();

    // Add second change
    await plusBtns.nth(1).click();
    await employeePage.locator('input[type="time"]').first().fill('08:00');
    await employeePage.locator('input[type="time"]').last().fill('16:00');
    await employeePage.locator('button[title="Speichern"]').click();
    await expect(employeePage.getByText('2 Änderungen ausstehend')).toBeVisible();

    // Verwerfen
    await employeePage.getByRole('button', { name: 'Verwerfen' }).click();
    await expect(employeePage.getByText('ausstehend')).toHaveCount(0);
  });
});
```

### Step 3: Tests ausführen

```bash
cd /e/claude/zeiterfassung/praxiszeit/e2e
npx playwright test tests/admin/journal-editing.spec.ts tests/employee/journal-editing.spec.ts --project=chromium 2>&1
```

Erwartet: Alle Tests grün (oder einzelne `test.skip` wenn kein passender Tag im aktuellen Monat).

### Step 4: Commit

```bash
cd /e/claude/zeiterfassung/praxiszeit
git add e2e/tests/admin/journal-editing.spec.ts e2e/tests/employee/journal-editing.spec.ts
git commit -m "test(e2e): add journal inline-editing E2E tests"
```

### Step 5: Push

```bash
git push origin master
```

---

## Erfolgskriterien

- [ ] Admin: Pencil-Icon öffnet Inline-Edit → ✓ speichert direkt → Journal lädt neu
- [ ] Admin: Plus-Icon auf leerem Werktag → Von/Bis → ✓ → neuer Eintrag
- [ ] Admin: Trash-Icon löscht Eintrag → Journal lädt neu
- [ ] Heute und Zukunft: kein Edit-Icon
- [ ] Mitarbeiter: Änderungen sammeln → Footer "N Änderungen ausstehend"
- [ ] Mitarbeiter: "Absenden" → Modal → Begründung → ChangeRequests erstellt
- [ ] Mitarbeiter: "Verwerfen" → Draft gelöscht, keine API-Calls
- [ ] E2E: Tests grün, keine Regressionen
