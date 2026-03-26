# UX Quick Wins + Simple-First Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the mobile-first employee UX of PraxisZeit with 11 targeted changes — 8 quick wins and 3 Simple-First principle fixes.

**Architecture:** Pure frontend changes in the React/TypeScript/Tailwind stack. No backend changes needed. All work happens in the worktree at `E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend/src/`.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, date-fns, lucide-react, React Router v6

---

## File Map

| File | Modified by Tasks |
|------|-------------------|
| `frontend/src/components/StampWidget.tsx` | Task 2, Task 4 |
| `frontend/src/pages/TimeTracking.tsx` | Task 1, Task 4, Task 8, Task 9, Task 11 |
| `frontend/src/pages/ChangeRequests.tsx` | Task 1, Task 5 |
| `frontend/src/pages/Journal.tsx` | Task 6 |
| `frontend/src/pages/Dashboard.tsx` | Task 7, Task 10 |
| `frontend/src/pages/AbsenceCalendarPage.tsx` | Task 3, Task 4, Task 9 |
| `frontend/src/components/Layout.tsx` | Task 3, Task 11 |
| `frontend/src/components/MonthlyJournal.tsx` | Task 3, Task 4 |
| `frontend/src/components/MonthSelector.tsx` | Task 3 |
| `frontend/src/App.tsx` | Task 11 |

---

## Chunk 1: Quick Wins A — Button Adoption, StampWidget Hero, Touch Targets, inputMode

### Task 1: Adopt Button.tsx in TimeTracking and ChangeRequests

Replace all inline-styled primary/danger/secondary/amber buttons in employee-facing pages with the shared `Button` component. No behavior change — only markup.

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx`
- Modify: `frontend/src/pages/ChangeRequests.tsx`

**Current state in TimeTracking.tsx:**
```tsx
// Line ~265 — "Antrag" button (amber, inline styled)
<button
  onClick={openCreateChangeRequest}
  className="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
>
  <FileEdit size={20} />
  <span className="hidden sm:inline">Antrag</span>
</button>

// Line ~274 — "Neuer Eintrag" button (primary, inline styled)
<button
  onClick={() => setShowForm(!showForm)}
  className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg flex items-center space-x-2 transition"
>
  {showForm ? <X size={20} /> : <Plus size={20} />}
  <span>{showForm ? 'Abbrechen' : 'Neuer Eintrag'}</span>
</button>
```

**Current state in ChangeRequests.tsx (filter buttons, withdraw button) — find via search.**

- [ ] **Step 1: Find all inline-styled buttons in TimeTracking.tsx**

  Read `frontend/src/pages/TimeTracking.tsx` fully. List every `<button` element with inline Tailwind classes.

- [ ] **Step 2: Replace buttons in TimeTracking.tsx**

  Add `import Button from '../components/Button';` at the top.

  Replace the "Antrag" button with:
  ```tsx
  <Button
    variant="secondary"
    size="md"
    icon={FileEdit}
    onClick={openCreateChangeRequest}
    title="Antrag für vergangenen Tag stellen"
    className="bg-amber-500 hover:bg-amber-600 text-white focus:ring-amber-400"
  >
    <span className="hidden sm:inline">Antrag</span>
    <span className="sm:hidden sr-only">Antrag</span>
  </Button>
  ```

  Replace the "Neuer Eintrag / Abbrechen" button with:
  ```tsx
  <Button
    variant={showForm ? 'secondary' : 'primary'}
    size="md"
    icon={showForm ? X : Plus}
    onClick={() => setShowForm(!showForm)}
  >
    {showForm ? 'Abbrechen' : 'Neuer Eintrag'}
  </Button>
  ```

  Find and replace the "Speichern" / "Erstellen" form submit button (currently inline `bg-primary`) with:
  ```tsx
  <Button type="submit" variant="primary" size="md">
    {editingId ? 'Speichern' : 'Erstellen'}
  </Button>
  ```

  Find and replace cancel/reset button with:
  ```tsx
  <Button type="button" variant="ghost" size="md" onClick={resetForm}>
    Abbrechen
  </Button>
  ```

  Find all delete/edit icon buttons in the entry list — read the JSX first, then replace with Button variant="ghost" or leave as-is if they are icon-only (icon-only buttons are OK as-is since Button.tsx requires `children`).

- [ ] **Step 3: Replace buttons in ChangeRequests.tsx**

  Add `import Button from '../components/Button';` at the top.

  Find the "Zurückziehen" (withdraw) button and replace with:
  ```tsx
  <Button variant="danger" size="sm" icon={Trash2} onClick={() => handleWithdraw(cr.id)}>
    Zurückziehen
  </Button>
  ```

  The filter tab buttons (Alle/Offen/Genehmigt/Abgelehnt) are functional filter tabs, not semantic buttons in the Button design sense — leave those with their existing inline styles.

- [ ] **Step 4: Verify build passes**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend
  npm run build 2>&1 | tail -20
  ```
  Expected: no TypeScript errors.

- [ ] **Step 5: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/TimeTracking.tsx frontend/src/pages/ChangeRequests.tsx
  git commit -m "feat: adopt Button component in TimeTracking and ChangeRequests"
  ```

---

### Task 2: StampWidget as Visual Hero

Make the stamp button bigger (`py-4`) and the container more visually prominent as the primary action on the page.

**Files:**
- Modify: `frontend/src/components/StampWidget.tsx`

**Current state (lines 154–172 in StampWidget.tsx):**
```tsx
// Clock-out button
className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 ..."

// Clock-in button
className="flex items-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 ..."
```

- [ ] **Step 1: Increase button padding and font size**

  In `frontend/src/components/StampWidget.tsx`:
  - Change both buttons from `px-6 py-3` to `px-8 py-4`
  - Change `text-lg` to `text-xl` on both buttons
  - Change icon size from `size={22}` to `size={24}` on both buttons
  - Make elapsed time text bigger: `text-2xl` → `text-3xl` on the font-bold span

- [ ] **Step 2: Strengthen the clocked-in background**

  Change the container class when clocked in from `bg-green-50 border-green-200` to `bg-green-100 border-green-300` for stronger visual emphasis:
  ```tsx
  // Before:
  isClockedIn ? 'bg-green-50 border-green-200' : 'bg-white border-gray-200'
  // After:
  isClockedIn ? 'bg-green-100 border-green-300' : 'bg-gray-50 border-gray-200'
  ```

- [ ] **Step 3: Verify build**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 4: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/components/StampWidget.tsx
  git commit -m "feat: make StampWidget button larger and more visually prominent"
  ```

---

### Task 3: Increase Touch Targets

Increase padding on small icon buttons and interactive elements for better mobile usability.

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`
- Modify: `frontend/src/components/MonthSelector.tsx`
- Modify: `frontend/src/components/Layout.tsx` (mobile hamburger already fine, check close button)

**Targets:**
- Journal icon buttons: `p-1` → `p-2.5` (Edit, Trash2 icons in MonthlyJournal)
- MonthSelector arrows: `p-2` → `p-2.5`
- Absence delete buttons: `p-2` → `p-3`

- [ ] **Step 1: Read MonthlyJournal.tsx fully** to locate all icon buttons with `p-1` or `p-2`

- [ ] **Step 2: Fix touch targets in MonthlyJournal.tsx**

  Search for `p-1` on icon buttons and replace with `p-2.5`. Typical pattern:
  ```tsx
  // Before:
  className="p-1 text-gray-400 hover:text-blue-600 rounded transition"
  // After:
  className="p-2.5 text-gray-400 hover:text-blue-600 rounded transition"
  ```

  Search for `p-2` on delete/action buttons in the journal entry rows and replace with `p-3`.

- [ ] **Step 3: Fix touch targets in MonthSelector.tsx**

  Read the file. Find the prev/next arrow buttons. Change their padding:
  ```tsx
  // Before: p-2
  // After: p-2.5
  ```

- [ ] **Step 4: Fix touch targets in AbsenceCalendarPage.tsx**

  Read the file. Find absence delete/edit icon buttons. Change `p-2` → `p-3` on those buttons.

- [ ] **Step 5: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 6: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/components/MonthlyJournal.tsx frontend/src/components/MonthSelector.tsx frontend/src/pages/AbsenceCalendarPage.tsx
  git commit -m "feat: increase touch target sizes for icon buttons to 44px minimum"
  ```

---

### Task 4: Add inputMode="numeric" to All Number Inputs

Mobile keyboards should show numeric keypad for all `type="number"` inputs.

**Files:**
- Modify: `frontend/src/components/StampWidget.tsx`
- Modify: `frontend/src/pages/TimeTracking.tsx`
- Modify: `frontend/src/components/MonthlyJournal.tsx`
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`

**Pattern to apply everywhere:**
```tsx
// Before:
<input type="number" ... />
// After:
<input type="number" inputMode="numeric" ... />
```

- [ ] **Step 1: Add inputMode to StampWidget break input**

  In `StampWidget.tsx` at the break minutes input (lines ~135-143):
  ```tsx
  <input
    type="number"
    inputMode="numeric"
    min="0"
    max="480"
    ...
  />
  ```

- [ ] **Step 2: Add inputMode to TimeTracking form**

  In `TimeTracking.tsx`, find the `break_minutes` input. Add `inputMode="numeric"`.

- [ ] **Step 3: Add inputMode to MonthlyJournal**

  Read `MonthlyJournal.tsx`. Find any `type="number"` inputs and add `inputMode="numeric"`.

- [ ] **Step 4: Add inputMode to AbsenceCalendarPage**

  Read `AbsenceCalendarPage.tsx`. Find `type="number"` inputs (hours field) and add `inputMode="numeric"`.

- [ ] **Step 5: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 6: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/components/StampWidget.tsx frontend/src/pages/TimeTracking.tsx frontend/src/components/MonthlyJournal.tsx frontend/src/pages/AbsenceCalendarPage.tsx
  git commit -m "feat: add inputMode=numeric to all number inputs for mobile keyboard"
  ```

---

## Chunk 2: Quick Wins B — ISO Date Fix, Journal Heading, Welcome Box, Smart Break

### Task 5: Fix ISO Date Display in ChangeRequests

Dates like `cr.original_date` and `cr.proposed_date` arrive as `"2026-03-10"` (ISO string). Without the `T00:00:00` suffix, `new Date("2026-03-10")` parses as UTC midnight, which renders one day off in some timezones when formatted with `toLocaleDateString`.

**Files:**
- Modify: `frontend/src/pages/ChangeRequests.tsx`

**Current problematic patterns (find by reading the file's JSX section):**
```tsx
// Any usage like:
new Date(cr.original_date)
new Date(cr.proposed_date)
format(new Date(cr.original_date), ...)
```

**Fix:** Append `T00:00:00` when constructing the Date:
```tsx
// Before:
format(new Date(cr.original_date), 'dd.MM.yyyy')
// After:
format(new Date(cr.original_date + 'T00:00:00'), 'dd.MM.yyyy')
```

- [ ] **Step 1: Read ChangeRequests.tsx JSX section fully** (lines 85 onward) to find all date usages

- [ ] **Step 2: Fix all date constructions in ChangeRequests.tsx**

  For every occurrence of `new Date(cr.original_date)` and `new Date(cr.proposed_date)`:
  - Wrap with `+ 'T00:00:00'` suffix
  - Also check `cr.reviewed_at` and `cr.created_at` — these are ISO datetime strings (include time), so they are fine as-is

- [ ] **Step 3: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 4: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/ChangeRequests.tsx
  git commit -m "fix: append T00:00:00 to ISO date strings in ChangeRequests to prevent timezone offset"
  ```

---

### Task 6: Journal Heading Size

Make the Journal page heading larger for visual hierarchy.

**Files:**
- Modify: `frontend/src/pages/Journal.tsx`

**Current state (line 12):**
```tsx
<h1 className="text-2xl font-bold text-gray-900">Mein Journal</h1>
```

- [ ] **Step 1: Change heading size**

  In `frontend/src/pages/Journal.tsx`, line 12:
  ```tsx
  // Before:
  <h1 className="text-2xl font-bold text-gray-900">Mein Journal</h1>
  // After:
  <h1 className="text-3xl font-bold text-gray-900">Mein Journal</h1>
  ```

- [ ] **Step 2: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/Journal.tsx
  git commit -m "feat: increase Journal heading from text-2xl to text-3xl"
  ```

---

### Task 7: Delete Welcome Box from Dashboard

The blue info box at the bottom of Dashboard ("Willkommen bei PraxisZeit") is redundant information that wastes screen real estate.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Current state (lines 557–564):**
```tsx
{/* Quick Info */}
<div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
  <h3 className="text-lg font-semibold text-blue-900 mb-2">Willkommen bei PraxisZeit</h3>
  <p className="text-blue-700">
    Nutzen Sie die Navigation links, um Ihre Zeiteinträge zu verwalten, Abwesenheiten einzutragen
    oder Ihre Übersicht anzusehen.
  </p>
</div>
```

- [ ] **Step 1: Delete the welcome box**

  Remove the entire `{/* Quick Info */}` block including the surrounding `<div>` from `Dashboard.tsx`.

- [ ] **Step 2: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 3: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/Dashboard.tsx
  git commit -m "feat: remove redundant welcome info box from Dashboard"
  ```

---

### Task 8: Smart Break Default (Auto 30 min when >6h)

When a user submits a new time entry where `end_time - start_time > 6h` AND `break_minutes === 0`, automatically set `break_minutes = 30` before submitting. This prevents the common case of forgetting to enter a break.

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx`

**Location:** The `handleSubmit` function (line 139).

- [ ] **Step 1: Add break auto-fill logic to handleSubmit**

  In `TimeTracking.tsx`, inside `handleSubmit`, BEFORE calling `validateTimeEntry()`, add:

  ```tsx
  // Auto-fill 30 min break if working > 6h with no break recorded
  let effectiveFormData = { ...formData };
  if (!editingId && effectiveFormData.break_minutes === 0) {
    const [sh, sm] = effectiveFormData.start_time.split(':').map(Number);
    const [eh, em] = effectiveFormData.end_time.split(':').map(Number);
    const grossMinutes = (eh * 60 + em) - (sh * 60 + sm);
    if (grossMinutes > 360) {
      effectiveFormData = { ...effectiveFormData, break_minutes: 30 };
      setFormData(effectiveFormData);
    }
  }
  ```

  Note: `validateTimeEntry()` reads from `formData` state, so we must call `setFormData` before it runs. But React state is async — instead, pass the computed break to validation directly, or use a ref.

  **Simpler approach:** Mutate `formData.break_minutes` in state first, then use `setTimeout(0)` to defer submit — but this is hacky.

  **Best approach:** Inline the break calculation directly in `handleSubmit` before the API call, after `validateTimeEntry` (which runs on current state), using a local variable:

  ```tsx
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateTimeEntry()) {
      return;
    }

    // Smart break default: auto-set 30 min break when working > 6h with no break
    let submitData = { ...formData };
    if (!editingId && submitData.break_minutes === 0) {
      const [sh, sm] = submitData.start_time.split(':').map(Number);
      const [eh, em] = submitData.end_time.split(':').map(Number);
      const grossMinutes = (eh * 60 + em) - (sh * 60 + sm);
      if (grossMinutes > 360) {
        submitData = { ...submitData, break_minutes: 30 };
      }
    }

    try {
      let response;
      if (editingId) {
        response = await apiClient.put(`/time-entries/${editingId}`, submitData);
        // ... rest unchanged
      } else {
        response = await apiClient.post('/time-entries', submitData);
        // ... rest unchanged
      }
      // ...
    }
  };
  ```

- [ ] **Step 2: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 3: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/TimeTracking.tsx
  git commit -m "feat: auto-set 30 min break when creating entry >6h with no break"
  ```

---

## Chunk 3: Simple-First — ArbZG Jargon, Dashboard Layout, Navigation Tabs

### Task 9: Remove ArbZG Legal Jargon from Employee UI

Employees shouldn't need to know German labor law paragraph numbers. Replace all legal references with plain German.

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx` (ArbZG toast warnings + sunday exception placeholder)
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx` (ArbZG badge tooltips + placeholder)
- Modify: `frontend/src/components/MonthlyJournal.tsx` (So/FT badge title attribute)

**Changes:**

**TimeTracking.tsx — toast warnings (lines 156–167):**
```tsx
// Before:
toast.warning('Tagesarbeitszeit überschreitet 8 Stunden (§3 ArbZG)');
toast.warning('Wochenarbeitszeit überschreitet 48 Stunden (§14 ArbZG)');
toast.warning('Achtung: Sonntagsarbeit – Ausnahmegrund nach §10 ArbZG dokumentieren');
toast.warning('Achtung: Feiertagsarbeit – Ausnahmegrund nach §10 ArbZG dokumentieren');

// After:
toast.warning('Tagesarbeitszeit über 8 Stunden');
toast.warning('Wochenarbeitszeit über 48 Stunden');
toast.warning('Sonntagsarbeit eingetragen – bitte Ausnahmegrund angeben');
toast.warning('Feiertagsarbeit eingetragen – bitte Ausnahmegrund angeben');
```

**TimeTracking.tsx — sunday_exception_reason input placeholder:**

Find the `sunday_exception_reason` input field. Change its placeholder from `"§10 Nr. 1 ArbZG"` (or whatever it currently says) to `"z. B. Notdienst, Patientenversorgung"`.

**MonthlyJournal.tsx — So/FT badge `title` attribute:**

Find badges with title like `"Sonn-/Feiertagsarbeit – §9/10 ArbZG"` and replace with `"Sonn- oder Feiertagsarbeit"`.

**AbsenceCalendarPage.tsx — any ArbZG references in UI text (placeholders, titles, labels).**

- [ ] **Step 1: Fix toast warnings in TimeTracking.tsx**

  Replace the 4 `toast.warning()` calls with plain-language versions (see above).

- [ ] **Step 2: Fix sunday_exception_reason placeholder in TimeTracking.tsx**

  Read `TimeTracking.tsx` fully (the form section) to find the `sunday_exception_reason` input.
  Change placeholder to `"z. B. Notdienst, Patientenversorgung"`.

- [ ] **Step 3: Fix So/FT badge title in MonthlyJournal.tsx**

  Read `MonthlyJournal.tsx`. Find badge/span with `title` containing "ArbZG".
  Change to `"Sonn- oder Feiertagsarbeit"`.

- [ ] **Step 4: Check AbsenceCalendarPage.tsx for ArbZG references**

  Read `AbsenceCalendarPage.tsx`. If any visible text or title attributes reference `§` or `ArbZG`, replace with plain German. (May not have any — verify.)

- [ ] **Step 5: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 6: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/TimeTracking.tsx frontend/src/components/MonthlyJournal.tsx frontend/src/pages/AbsenceCalendarPage.tsx
  git commit -m "feat: replace ArbZG legal jargon with plain language in employee UI"
  ```

---

### Task 10: Dashboard — Collapse Jahresübersicht and Team-Kalender

The Dashboard is too long on mobile. The upper portion (StampWidget + 4 stat cards + Monatsübersicht table) stays always visible. "Jahresübersicht" and "Geplante Abwesenheiten im Team" sections are hidden behind a "Details anzeigen" toggle.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Sections to collapse:**
1. Jahresübersicht block (lines 355–386, `{/* Yearly Absence Overview */}`)
2. Team Absences Calendar (lines 388–555, `{/* Team Absences Calendar */}`)

- [ ] **Step 1: Add state for the details toggle**

  In the `Dashboard()` function, add a state variable after the existing state declarations:
  ```tsx
  const [showDetails, setShowDetails] = useState(false);
  ```

- [ ] **Step 2: Wrap the two sections in a conditional + add toggle button**

  After the Monthly Overview Table section (after line 353's closing `</div>`), add the toggle button and wrap both collapsible sections:

  ```tsx
  {/* Details Toggle */}
  {trackHours && (
    <div className="mb-6 flex justify-center">
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
      >
        {showDetails ? (
          <>
            <ChevronUp size={16} />
            <span>Details ausblenden</span>
          </>
        ) : (
          <>
            <ChevronDown size={16} />
            <span>Details anzeigen (Jahresübersicht & Team-Kalender)</span>
          </>
        )}
      </button>
    </div>
  )}

  {/* Collapsible: Yearly Absence Overview + Team Calendar */}
  {showDetails && (
    <>
      {/* Yearly Absence Overview — existing JSX here */}
      {/* Team Absences Calendar — existing JSX here */}
    </>
  )}
  ```

- [ ] **Step 3: Import ChevronDown and ChevronUp from lucide-react**

  Add to the existing import line:
  ```tsx
  import { TrendingUp, TrendingDown, Calendar, Clock, Palmtree, ChevronDown, ChevronUp } from 'lucide-react';
  ```

- [ ] **Step 4: Verify build**

  ```bash
  npm run build 2>&1 | tail -5
  ```

- [ ] **Step 5: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/pages/Dashboard.tsx
  git commit -m "feat: collapse Jahresübersicht and Team-Kalender behind Details toggle on Dashboard"
  ```

---

### Task 11: Navigation — Merge Journal and Änderungsanträge as Tabs in Zeiterfassung

**Goal:** Remove "Journal" and "Änderungsanträge" from the sidebar nav. Add three tabs to the Zeiterfassung page: **Einträge** | **Journal** | **Anträge**.

**Approach:** Use URL search params for tab state (`?tab=journal`, `?tab=requests`, default = `eintraege`) so tabs are bookmarkable. Redirect old routes `/journal` → `/time-tracking?tab=journal` and `/change-requests` → `/time-tracking?tab=requests`.

**Files:**
- Modify: `frontend/src/components/Layout.tsx` (remove 2 nav items)
- Modify: `frontend/src/pages/TimeTracking.tsx` (add tabs, render Journal/ChangeRequests content)
- Modify: `frontend/src/App.tsx` (add redirect routes)

**Note:** `Journal.tsx` and `ChangeRequests.tsx` remain as standalone files — they just won't be in the sidebar anymore. They are composed inside TimeTracking via tabs.

- [ ] **Step 1: Remove Journal and Änderungsanträge from Layout.tsx nav**

  In `frontend/src/components/Layout.tsx`, find the `navItems` array (lines 66–74):
  ```tsx
  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/time-tracking', label: 'Zeiterfassung', icon: Clock },
    { path: '/change-requests', label: 'Änderungsanträge', icon: FileEdit },  // REMOVE
    { path: '/absences', label: 'Abwesenheiten', icon: Calendar },
    { path: '/journal', label: 'Journal', icon: BookOpen },                   // REMOVE
    { path: '/profile', label: 'Profil', icon: User },
    { path: '/help', label: 'Hilfe', icon: HelpCircle },
  ];
  ```

  Remove the two lines for `change-requests` and `journal`. Also remove unused imports `FileEdit` and `BookOpen` from the lucide import if they are no longer used elsewhere in Layout.tsx. (Check whether `FileEdit` appears elsewhere first — if not, remove from import.)

- [ ] **Step 2: Add redirect routes in App.tsx**

  In `frontend/src/App.tsx`, inside the protected employee routes block, add:
  ```tsx
  <Route path="journal" element={<Navigate to="/time-tracking?tab=journal" replace />} />
  <Route path="change-requests" element={<Navigate to="/time-tracking?tab=requests" replace />} />
  ```

  Add `Navigate` to the import if not already imported (it already is).

- [ ] **Step 3: Add tab UI and tab routing to TimeTracking.tsx**

  Add `import { useSearchParams } from 'react-router-dom';` at the top.
  Add `import Journal from './Journal';` and `import ChangeRequests from './ChangeRequests';`.

  Replace the existing `<h1>Zeiterfassung</h1>` header area and the return body structure with a tabbed layout:

  ```tsx
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') ?? 'eintraege';

  const setTab = (tab: string) => {
    setSearchParams(tab === 'eintraege' ? {} : { tab });
  };
  ```

  Add the tab bar just below the `<h1>`:
  ```tsx
  {/* Tab Bar */}
  <div className="flex border-b border-gray-200 mb-6 -mx-1">
    {[
      { id: 'eintraege', label: 'Einträge' },
      { id: 'journal', label: 'Journal' },
      { id: 'requests', label: 'Anträge' },
    ].map((tab) => (
      <button
        key={tab.id}
        onClick={() => setTab(tab.id)}
        className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
          activeTab === tab.id
            ? 'border-primary text-primary'
            : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
        }`}
      >
        {tab.label}
      </button>
    ))}
  </div>

  {/* Tab Content */}
  {activeTab === 'eintraege' && (
    <> {/* existing TimeTracking JSX content (MonthSelector, form, entries list) */} </>
  )}
  {activeTab === 'journal' && <Journal />}
  {activeTab === 'requests' && <ChangeRequests />}
  ```

  **Important:** The existing JSX body of `TimeTracking` (MonthSelector, form, entries list, totals row) must be wrapped in `{activeTab === 'eintraege' && (...)}`. The `ConfirmDialog` and `ChangeRequestForm` modal remain outside the tab conditional (they are modal overlays).

- [ ] **Step 4: Remove "Antrag" button from TimeTracking header when not on Einträge tab**

  The "Antrag" button (creates a ChangeRequest) is in the header area. Since Anträge now has its own tab, this button should only show when `activeTab === 'eintraege'`:
  ```tsx
  {activeTab === 'eintraege' && !isAdmin && (
    <Button ... onClick={openCreateChangeRequest}>Antrag</Button>
  )}
  ```

- [ ] **Step 5: Verify build**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend
  npm run build 2>&1 | tail -10
  ```
  Expected: No TypeScript errors.

- [ ] **Step 6: Commit**

  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git add frontend/src/components/Layout.tsx frontend/src/pages/TimeTracking.tsx frontend/src/App.tsx
  git commit -m "feat: merge Journal and Änderungsanträge as tabs in Zeiterfassung, remove from sidebar"
  ```

---

## Final Verification

- [ ] Run full build one last time:
  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend
  npm run build 2>&1 | tail -20
  ```

- [ ] Confirm all 11 tasks are committed:
  ```bash
  cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
  git log --oneline -12
  ```

- [ ] Signal branch is ready for review (do NOT merge — user wants to review first)
