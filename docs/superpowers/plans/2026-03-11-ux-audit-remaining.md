# UX Audit – Verbleibende 12 Befunde Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all 12 remaining UX audit findings to complete the full UX overhaul of PraxisZeit.

**Architecture:** Pure frontend changes in React/TypeScript/Tailwind. Backend unchanged. All changes in `frontend/src/`. No new routes needed.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3, date-fns, lucide-react, React Router v6, Zustand (auth store)

**Build & Deploy:**
```bash
# From worktree root:
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
docker-compose build frontend --no-cache
docker tag ux-improvements-frontend:latest praxiszeit-frontend:latest
cd E:/claude/zeiterfassung/praxiszeit
docker-compose up -d --no-deps frontend
# Verify at http://localhost
```

---

## File Map

| File | Task(s) | Change |
|------|---------|--------|
| `frontend/src/pages/TimeTracking.tsx` | #12, #5, #2 | Placeholder verify, smart defaults, mobile sheet |
| `frontend/src/pages/AbsenceCalendarPage.tsx` | #6, #4 | Year nav arrows, mobile tap-to-add, form simplification |
| `frontend/src/pages/Dashboard.tsx` | #7 | EmptyState adoption |
| `frontend/src/pages/ChangeRequests.tsx` | #7 | EmptyState adoption |
| `frontend/src/pages/Help.tsx` | #11 | Content update (nav, password 8 chars, tabs) |
| `frontend/src/pages/Profile.tsx` | #9 | Restructure: häufig visible, selten in accordion |
| `frontend/src/components/Layout.tsx` | #11, #1 | Remove FAB + Hilfe nav, add ? sidebar footer, bottom-nav |
| `frontend/src/components/MonthlyJournal.tsx` | #3, #7 | Remove draft system, direct save + EmptyState |
| `frontend/src/components/EmptyState.tsx` | #7 | CREATE: shared empty state component |
| `frontend/src/constants/helpContent.tsx` | #11 | Update /change-requests → tab, password 8 chars, nav list |
| `frontend/src/components/SubmitChangesModal.tsx` | #3 | DELETE after removal from MonthlyJournal |

---

## Chunk 1: Small Fixes — Placeholder, Defaults, Year Nav, EmptyState, Visual Distinction

### Task 1: Verify #12 — ArbZG Placeholder (verify-only, likely already done)

**Files:**
- Read: `frontend/src/pages/TimeTracking.tsx` (line ~460)

- [ ] **Step 1: Check placeholder in TimeTracking.tsx**

Open `frontend/src/pages/TimeTracking.tsx` and find the `sunday_exception_reason` input (around line 458-462). The placeholder should read:
```
"z. B. Notdienst, Patientenversorgung"
```
If it still contains `§10 Nr. 1 ArbZG`, remove it.

- [ ] **Step 2: Check AbsenceCalendarPage.tsx for any § placeholders**

Search for `§` in `frontend/src/pages/AbsenceCalendarPage.tsx`. No ArbZG § symbols should appear in any `placeholder` attribute in user-facing inputs.

- [ ] **Step 3: Commit only if changes were needed**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/TimeTracking.tsx frontend/src/pages/AbsenceCalendarPage.tsx
git commit -m "fix: remove ArbZG paragraph from user-facing input placeholder"
```
If already correct (very likely), skip the commit.

---

### Task 2: #5 — Sollstunden as Smart Form Defaults in TimeTracking

When a user selects a date in the TimeTracking form, auto-compute the `end_time` from `start_time` + the user's daily target hours for that weekday.

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx`

**Context:** The `user` from `useAuthStore()` has `use_daily_schedule: boolean`, `hours_monday..hours_friday: number | null`, `weekly_hours: number`, `work_days_per_week: number`.

- [ ] **Step 1: Add helper functions after the imports at the top of TimeTracking.tsx**

Add these two helper functions after the `TimeEntry` interface definition (around line 32):

```tsx
/** Returns the user's daily target hours for a given date string "YYYY-MM-DD". */
function getDailyTargetHours(user: ReturnType<typeof useAuthStore>['user'], dateStr: string): number {
  if (!user) return 8;
  if (user.use_daily_schedule) {
    const weekday = new Date(dateStr + 'T00:00:00').getDay(); // 0=Sun
    const map: Record<number, number | null | undefined> = {
      1: user.hours_monday,
      2: user.hours_tuesday,
      3: user.hours_wednesday,
      4: user.hours_thursday,
      5: user.hours_friday,
    };
    return map[weekday] ?? 0;
  }
  // No daily schedule: distribute weekly_hours over work_days
  const weekday = new Date(dateStr + 'T00:00:00').getDay();
  if (weekday === 0 || weekday === 6) return 0; // weekend
  return user.work_days_per_week > 0 ? user.weekly_hours / user.work_days_per_week : 8;
}

/** Adds `hours` to a "HH:mm" start time and returns the result as "HH:mm". */
function addHoursToTime(startTime: string, hours: number): string {
  const [h, m] = startTime.split(':').map(Number);
  const totalMins = h * 60 + m + Math.round(hours * 60);
  const endH = Math.floor(totalMins / 60) % 24;
  const endM = totalMins % 60;
  return `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;
}
```

- [ ] **Step 2: Update the date onChange handler to recalculate end_time**

Find the date input onChange in TimeTracking.tsx (around line 362-366):
```tsx
onChange={(e) => {
  setFormData({ ...formData, date: e.target.value });
  setErrors({});
}}
```
Replace with:
```tsx
onChange={(e) => {
  const newDate = e.target.value;
  const targetHours = getDailyTargetHours(user, newDate);
  const newEndTime = targetHours > 0
    ? addHoursToTime(formData.start_time, targetHours)
    : formData.end_time;
  setFormData({ ...formData, date: newDate, end_time: newEndTime });
  setErrors({});
}}
```

- [ ] **Step 3: Set smart defaults in the resetForm function**

Find the `resetForm` function (around line 242-254). Replace the hard-coded defaults:
```tsx
const resetForm = () => {
  setShowForm(false);
  setEditingId(null);
  const today = format(new Date(), 'yyyy-MM-dd');
  const targetHours = getDailyTargetHours(user, today);
  const defaultEnd = targetHours > 0 ? addHoursToTime('08:00', targetHours) : '17:00';
  setFormData({
    date: today,
    start_time: '08:00',
    end_time: defaultEnd,
    break_minutes: 0,
    note: '',
    sunday_exception_reason: '',
  });
  setErrors({});
};
```

- [ ] **Step 4: Build and verify**

Open the browser at http://localhost/time-tracking, click "Neuer Eintrag", change the date. Verify the end time adjusts automatically.

- [ ] **Step 5: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/TimeTracking.tsx
git commit -m "feat: auto-compute end_time from daily target hours when selecting date"
```

---

### Task 3: #6 — Year Navigation: Replace Input with Arrows in AbsenceCalendarPage

**Files:**
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`

**Context:** Currently in the Jahresansicht, year navigation is a `<input type="number">` (line ~564-571). Replace with prev/next arrow buttons.

- [ ] **Step 1: Add ChevronLeft and ChevronRight to the lucide-react import**

Find the lucide-react import line in AbsenceCalendarPage.tsx:
```tsx
import { Plus, X, Trash2, Clock, CheckCircle, XCircle } from 'lucide-react';
```
Add `ChevronLeft, ChevronRight`:
```tsx
import { Plus, X, Trash2, Clock, CheckCircle, XCircle, ChevronLeft, ChevronRight } from 'lucide-react';
```

- [ ] **Step 2: Replace the year input with arrow buttons**

Find this block (around line 562-572):
```tsx
        <input
          type="number"
          value={currentYear}
          onChange={(e) => setCurrentYear(parseInt(e.target.value))}
          min="2020"
          max={new Date().getFullYear() + 1}
          className="px-4 py-2 border border-gray-300 rounded-lg"
        />
```
Replace with:
```tsx
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setCurrentYear(y => y - 1)}
            className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition"
            aria-label="Vorheriges Jahr"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="font-medium text-gray-800 w-16 text-center">{currentYear}</span>
          <button
            onClick={() => setCurrentYear(y => y + 1)}
            disabled={currentYear >= new Date().getFullYear() + 1}
            className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition disabled:opacity-40"
            aria-label="Nächstes Jahr"
          >
            <ChevronRight size={18} />
          </button>
        </div>
```

- [ ] **Step 3: Verify in browser**

Go to Abwesenheiten → Jahresansicht. The year arrows should navigate year by year.

- [ ] **Step 4: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/AbsenceCalendarPage.tsx
git commit -m "feat: replace year number input with prev/next arrow buttons in absence year view"
```

---

### Task 4: #7 — EmptyState Component + Adopt Everywhere

**Files:**
- Create: `frontend/src/components/EmptyState.tsx`
- Modify: `frontend/src/pages/TimeTracking.tsx`
- Modify: `frontend/src/pages/ChangeRequests.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`
- Modify: `frontend/src/components/MonthlyJournal.tsx`

- [ ] **Step 1: Create EmptyState component**

Create `frontend/src/components/EmptyState.tsx`:

```tsx
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  className?: string;
}

export default function EmptyState({ icon: Icon, title, description, className = '' }: EmptyStateProps) {
  return (
    <div className={`py-12 flex flex-col items-center justify-center text-center ${className}`}>
      {Icon && <Icon size={36} className="text-gray-300 mb-3" />}
      <p className="text-gray-500 font-medium">{title}</p>
      {description && <p className="text-sm text-gray-400 mt-1">{description}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Replace Pattern A in TimeTracking.tsx (desktop table empty row)**

Find (around line 500-506):
```tsx
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-4 text-center text-gray-500">
                    Keine Einträge für diesen Monat
                  </td>
                </tr>
```
Replace with:
```tsx
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <EmptyState title="Keine Einträge für diesen Monat" />
                  </td>
                </tr>
```
Add `import EmptyState from '../components/EmptyState';` to the imports.

- [ ] **Step 3: Replace mobile empty state in TimeTracking.tsx**

Find the mobile cards empty state (a div with "Keine Einträge...") and replace with:
```tsx
<EmptyState title="Keine Einträge für diesen Monat" />
```

- [ ] **Step 4: Replace empty state in ChangeRequests.tsx**

Open `frontend/src/pages/ChangeRequests.tsx`. Find the empty state pattern (icon + centered text in a white card). Replace with:
```tsx
import EmptyState from '../components/EmptyState';
import { FileEdit } from 'lucide-react';
// ...
<div className="bg-white rounded-xl shadow-sm border border-gray-200">
  <EmptyState icon={FileEdit} title="Keine Änderungsanträge" description="Neue Anträge stellst du über den 'Antrag'-Button in der Zeiterfassung." />
</div>
```

- [ ] **Step 5: Replace empty state in Dashboard.tsx (team calendar)**

Find the team calendar "no absences" empty state and replace with:
```tsx
import EmptyState from '../components/EmptyState';
// ...
<EmptyState title="Keine Abwesenheiten in diesem Zeitraum" />
```

- [ ] **Step 6: Replace empty state in AbsenceCalendarPage.tsx (mobile list)**

Find (around line 698-702):
```tsx
            {days.filter(...).length === 0 && (
              <div className="p-6 text-center text-gray-500">
                Keine Abwesenheiten oder Feiertage in diesem Monat
              </div>
            )}
```
Replace with:
```tsx
            {days.filter(...).length === 0 && (
              <EmptyState title="Keine Abwesenheiten oder Feiertage in diesem Monat" />
            )}
```
Also add EmptyState to the requests tab empty state (if any).

- [ ] **Step 7: Replace empty state in MonthlyJournal.tsx if any**

Check if MonthlyJournal has any inline empty states and replace with `<EmptyState />`.

- [ ] **Step 8: Build and verify**

Check all 4 pages for correct EmptyState rendering.

- [ ] **Step 9: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/components/EmptyState.tsx frontend/src/pages/TimeTracking.tsx frontend/src/pages/ChangeRequests.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/AbsenceCalendarPage.tsx frontend/src/components/MonthlyJournal.tsx
git commit -m "feat: add EmptyState component and adopt across all pages"
```

---

### Task 5: #8 — Visual Distinction: Tabs vs. Filters vs. View-Toggle

**Files:**
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`

**Context:** The AbsenceCalendarPage has two semantically different UI patterns that look identical:
- **Tabs** (Kalender / Meine Anträge): navigation between content areas → use border-b-2 underline pattern
- **View-Mode-Toggle** (Monatsansicht / Jahresansicht): switch between display modes → use icon + text with ring border

The TimeTracking tabs already use border-b-2 ✓. Dashboard details toggle uses ChevronDown/Up ✓.

- [ ] **Step 1: Update the Kalender/Anträge tabs to use border-b-2 underline pattern**

Find the tabs div in AbsenceCalendarPage.tsx (around line 292-320):
```tsx
      <div className="flex space-x-2 mb-6">
        <button
          onClick={() => setActiveTab('calendar')}
          className={`px-4 py-2 rounded-lg font-medium transition ${
            activeTab === 'calendar'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          Kalender
        </button>
        {vacationApprovalRequired && (
          <button
            onClick={() => { setActiveTab('requests'); fetchMyVacationRequests(); }}
            className={`px-4 py-2 rounded-lg font-medium transition flex items-center space-x-2 ${
              activeTab === 'requests'
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            ...
```
Replace with border-b-2 underline tabs (matching TimeTracking):
```tsx
      <div className="flex border-b border-gray-200 mb-6">
        <button
          onClick={() => setActiveTab('calendar')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'calendar'
              ? 'border-primary text-primary'
              : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
          }`}
        >
          Kalender
        </button>
        {vacationApprovalRequired && (
          <button
            onClick={() => { setActiveTab('requests'); fetchMyVacationRequests(); }}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center space-x-2 ${
              activeTab === 'requests'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
            }`}
          >
            <span>Meine Anträge</span>
            {myVacationRequests.filter((r) => r.status === 'pending').length > 0 && (
              <span className="bg-amber-500 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
                {myVacationRequests.filter((r) => r.status === 'pending').length}
              </span>
            )}
          </button>
        )}
      </div>
```

- [ ] **Step 2: Update the view-mode toggle to use icon-style segmented control**

Find the view mode buttons (around line 536-557):
```tsx
        <div className="flex items-center space-x-2">
          <button onClick={() => setViewMode('month')} className={`px-4 py-2 rounded-lg font-medium transition ${viewMode === 'month' ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
            Monatsansicht
          </button>
          <button onClick={() => setViewMode('year')} className={`px-4 py-2 rounded-lg font-medium transition ${viewMode === 'year' ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
            Jahresansicht
          </button>
        </div>
```
Replace with a segmented control style (inline border group):
```tsx
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
          <button
            onClick={() => setViewMode('month')}
            className={`px-3 py-1.5 font-medium transition-colors ${
              viewMode === 'month' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            Monat
          </button>
          <button
            onClick={() => setViewMode('year')}
            className={`px-3 py-1.5 font-medium transition-colors border-l border-gray-200 ${
              viewMode === 'year' ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            Jahr
          </button>
        </div>
```

- [ ] **Step 3: Verify in browser**

Open Abwesenheiten. The Kalender/Anträge tabs should use underline style. The Monat/Jahr toggle should use the compact segmented border style.

- [ ] **Step 4: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/AbsenceCalendarPage.tsx
git commit -m "ux: visually distinguish tabs (underline) from view-mode toggle (segmented) in AbsenceCalendarPage"
```

---

## Chunk 2: Medium Complexity — Help Consolidation, Profile Simplification

### Task 6: #11 — Help Consolidation + Content Update

Remove the floating help FAB and the standalone "Hilfe" nav item. Move help access to a single `?` icon in the sidebar footer that opens HelpPanel. Update help content to reflect current navigation.

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/constants/helpContent.tsx`
- Modify: `frontend/src/pages/Help.tsx`

- [ ] **Step 1: Remove FAB and Hilfe nav item from Layout.tsx**

In Layout.tsx, find the `navItems` array and remove the Hilfe entry:
```tsx
// REMOVE this line:
{ path: '/help', label: 'Hilfe', icon: HelpCircle },
```

Find the Help FAB block (around line 265-274) and remove it entirely:
```tsx
// REMOVE:
{location.pathname !== '/help' && (
  <button
    onClick={() => setHelpOpen(true)}
    className="fixed bottom-6 right-6 ..."
  >
    <HelpCircle size={22} />
  </button>
)}
```

- [ ] **Step 2: Add ? icon button in sidebar footer**

In Layout.tsx, find the logout button block in the sidebar footer (around line 248-254):
```tsx
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center space-x-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <LogOut size={16} />
            <span>Abmelden</span>
          </button>
          <p className="text-center text-xs text-gray-300 mt-2">v{__APP_VERSION__}</p>
```
Replace with:
```tsx
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setHelpOpen(true)}
              className="flex items-center space-x-2 px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 rounded-lg transition-colors"
              aria-label="Hilfe öffnen"
            >
              <HelpCircle size={16} />
              <span>Hilfe</span>
            </button>
            <button
              onClick={handleLogout}
              className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <LogOut size={16} />
              <span>Abmelden</span>
            </button>
          </div>
          <p className="text-center text-xs text-gray-300 mt-1">v{__APP_VERSION__}</p>
```

- [ ] **Step 3: Update helpContent.tsx — fix outdated entries**

In `frontend/src/constants/helpContent.tsx`:

**Update the `/change-requests` entry** (this route now redirects to `/time-tracking?tab=requests`). Change the `Antrag stellen` step to:
```tsx
<li>Zu <span className="font-medium">Zeiterfassung → Tab „Anträge"</span> navigieren</li>
<li>Auf <span className="font-medium">„Neuer Antrag"</span> klicken</li>
```

**Update the `/profile` password requirements:**
```tsx
// Change:
Anforderungen: mind. 10 Zeichen ...
// To:
Anforderungen: mind. 8 Zeichen, Groß- + Kleinbuchstabe, mindestens eine Ziffer.
```

**Update the `getFallbackHelp` navigation list:**
```tsx
export const getFallbackHelp = (): HelpEntry => ({
  title: 'Navigation & Hilfe',
  content: (
    <div className="space-y-4">
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Hauptnavigation</h3>
        <ul className="space-y-1 text-sm text-gray-600">
          <li>🏠 <span className="font-medium">Dashboard</span> – Ihre tägliche Übersicht</li>
          <li>⏱️ <span className="font-medium">Zeiterfassung</span> – Einträge · Journal · Anträge</li>
          <li>📅 <span className="font-medium">Abwesenheiten</span> – Urlaub, Krank, etc.</li>
          <li>👤 <span className="font-medium">Profil</span> – Passwort & Einstellungen</li>
        </ul>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Korrekturanträge</h3>
        <p className="text-sm text-gray-600">Zeiterfassung → Tab „Anträge" → Neuer Antrag.</p>
      </section>
      <section>
        <h3 className="font-semibold text-gray-800 mb-2">Journal</h3>
        <p className="text-sm text-gray-600">Zeiterfassung → Tab „Journal" – Monatsübersicht mit allen Tagen.</p>
      </section>
    </div>
  ),
});
```

Also add a `/time-tracking` context entry for the tab navigation:
Update the existing `/time-tracking` entry to mention tabs:
```tsx
// At the top of the content, add a new section:
<section>
  <h3 className="font-semibold text-gray-800 mb-2">Tabs</h3>
  <ul className="space-y-1 text-sm text-gray-600">
    <li><span className="font-medium">Einträge</span> – Monatliche Zeittabelle, neue Einträge</li>
    <li><span className="font-medium">Journal</span> – Tagesübersicht des Monats</li>
    <li><span className="font-medium">Anträge</span> – Korrekturanträge stellen &amp; verfolgen</li>
  </ul>
</section>
```

- [ ] **Step 4: Update Help.tsx content for password (8 chars) and navigation**

In `frontend/src/pages/Help.tsx`:

**CheatsheetMitarbeiter:** Change the Passwort section:
```tsx
// Change:
<p className="text-sm text-gray-500 mt-1">Mind. 10 Zeichen, Groß- + Kleinbuchstabe, mind. eine Ziffer.</p>
// To:
<p className="text-sm text-gray-500 mt-1">Mind. 8 Zeichen, Groß- + Kleinbuchstabe, mind. eine Ziffer.</p>
```

**CheatsheetMitarbeiter Korrekturantrag section:** Update the nav path:
```tsx
// Change:
<li>Korrekturanträge → Neuer Antrag</li>
// To:
<li>Zeiterfassung → Tab „Anträge" → Neuer Antrag</li>
```

**CheatsheetAdmin Login & Navigation section:**
```tsx
// Change:
<p className="text-sm text-gray-600">Admin-Navigation: Dashboard · Benutzer · Kalender · Berichte · Korrekturanträge · Audit-Log · Fehler-Monitoring</p>
// To:
<p className="text-sm text-gray-600">Mitarbeiter-Navigation: Dashboard · Zeiterfassung (Einträge, Journal, Anträge) · Abwesenheiten · Profil.<br/>Admin-Navigation zusätzlich: Admin-Dashboard · Benutzerverwaltung · Berichte · Abwesenheiten · Audit-Log · Einstellungen</p>
```

**handbuchMitarbeiterSections section 4 "Korrekturanträge":**
```tsx
// Change:
navigieren Sie zu <strong>Korrekturanträge → Neuer Antrag</strong>
// To:
navigieren Sie zu <strong>Zeiterfassung → Tab „Anträge" → Neuer Antrag</strong>
```

**handbuchMitarbeiterSections section 6 "Profil & Passwort":**
```tsx
// Change:
mind. 10 Zeichen
// To:
mind. 8 Zeichen
```

- [ ] **Step 5: Build and verify**

1. Sidebar should show no standalone "Hilfe" nav item
2. Sidebar footer should show "Hilfe" button next to "Abmelden"
3. Clicking ? in sidebar opens HelpPanel correctly
4. FAB is gone
5. HelpPanel footer still links to /help page (keep working)
6. /help page content is updated

- [ ] **Step 6: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/components/Layout.tsx frontend/src/constants/helpContent.tsx frontend/src/pages/Help.tsx
git commit -m "ux: consolidate help to single sidebar ? button, update content for current navigation and 8-char password"
```

---

### Task 7: #9 — Profile Page Simplification

Restructure Profile.tsx so frequent actions (User Info edit, Passwort ändern) are always visible and rare actions (2FA, Kalenderfarbe, DSGVO-Export, Anzeige-Info) are in a collapsible "Weitere Einstellungen" section.

**Files:**
- Modify: `frontend/src/pages/Profile.tsx`

- [ ] **Step 1: Read the full Profile.tsx**

Read `frontend/src/pages/Profile.tsx` completely to understand all 6 sections and their current layout (the file is ~400+ lines — read all of it).

- [ ] **Step 2: Add `showExtendedSettings` state**

After the existing state declarations, add:
```tsx
const [showExtendedSettings, setShowExtendedSettings] = useState(false);
```

Add `ChevronDown, ChevronUp` to lucide-react imports.

- [ ] **Step 3: In the JSX, wrap rarely-used sections**

Identify the following sections in the JSX:
- 2FA/TOTP block
- Kalenderfarbe block
- DSGVO Datenexport block
- Anzeige-Informationen block (username, role, weekly hours display)

Wrap them all in:
```tsx
{/* Weitere Einstellungen */}
<div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
  <button
    onClick={() => setShowExtendedSettings(s => !s)}
    className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors"
    aria-expanded={showExtendedSettings}
  >
    <span className="font-medium text-gray-800">Weitere Einstellungen</span>
    {showExtendedSettings
      ? <ChevronUp size={18} className="text-gray-500" />
      : <ChevronDown size={18} className="text-gray-500" />
    }
  </button>
  {showExtendedSettings && (
    <div className="border-t border-gray-200 divide-y divide-gray-100">
      {/* 2FA block */}
      {/* Kalenderfarbe block */}
      {/* DSGVO block */}
      {/* Anzeige-Info block */}
    </div>
  )}
</div>
```

Keep the following always visible (above the accordion):
- User Info card (photo + name + edit form)
- Passwort ändern card

- [ ] **Step 4: Build and verify**

Profile page should show: User Info card + Passwort section. Clicking "Weitere Einstellungen" expands 2FA, Kalenderfarbe, DSGVO, Info.

- [ ] **Step 5: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/Profile.tsx
git commit -m "ux: collapse rarely-used profile sections into 'Weitere Einstellungen' accordion"
```

---

## Chunk 3: Large Structural Changes — Bottom Nav, Mobile Form Sheet, Journal Direct Save, Absence Tap-to-Add

### Task 8: #1 — Mobile Bottom Navigation

Add a 4-5 icon bottom navigation bar on mobile (`lg:hidden`). Primary navigation items (Dashboard, Zeiterfassung, Abwesenheiten, Profil) are accessible without opening the sidebar.

**Files:**
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Add bottom nav to Layout.tsx**

In Layout.tsx, after the closing `</main>` tag and before the `<HelpPanel>` component, add the mobile bottom nav:

```tsx
      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white border-t border-gray-200 z-30 flex items-stretch">
        {[
          { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
          { path: '/time-tracking', icon: Clock, label: 'Zeiten' },
          { path: '/absences', icon: Calendar, label: 'Abwesen.' },
          { path: '/profile', icon: User, label: 'Profil' },
          ...(user?.role === 'admin' ? [{ path: '/admin', icon: Settings, label: 'Admin' }] : []),
        ].map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex-1 flex flex-col items-center justify-center space-y-0.5 transition-colors ${
                active ? 'text-primary' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon size={22} strokeWidth={active ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </Link>
          );
        })}
      </nav>
```

- [ ] **Step 2: Add bottom padding to main content on mobile**

Find the `<main>` element in Layout.tsx:
```tsx
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden lg:pt-0 pt-16" tabIndex={-1}>
```
Add `pb-16 lg:pb-0` to prevent content being hidden behind bottom nav:
```tsx
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden lg:pt-0 pt-16 pb-16 lg:pb-0" tabIndex={-1}>
```

- [ ] **Step 3: Verify the bottom nav is correct on mobile viewport**

Use browser DevTools (iPhone SE, 375px). Bottom nav should show 4 icons (5 if admin). Active item highlighted in primary blue. Content is not hidden under the nav.

- [ ] **Step 4: Verify desktop is unaffected**

On desktop (`≥ lg`), the bottom nav should be invisible. Sidebar and main layout unchanged.

- [ ] **Step 5: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/components/Layout.tsx
git commit -m "feat: add mobile bottom navigation with 4-5 primary nav icons"
```

---

### Task 9: #2 — TimeTracking Form as Mobile Bottom Sheet

On mobile, replace the inline collapsing form with a bottom-sheet overlay that slides up from the bottom. Desktop form remains unchanged.

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx`

- [ ] **Step 1: Understand current form structure**

The form is at lines ~340-467 in TimeTracking.tsx, inside `{showForm && (<div ...>)}`. It uses a 5-column grid (`grid-cols-1 md:grid-cols-2 lg:grid-cols-5`).

- [ ] **Step 2: Add CSS animation keyframe for slide-up**

In TimeTracking.tsx, add a style block or inline animation. The simplest approach: use a fixed overlay on mobile and normal inline on desktop. We split the form render into two: one for desktop (`hidden md:block`), one for mobile (bottom sheet, `md:hidden`).

However, the simplest non-duplicating approach: wrap the existing form div differently based on breakpoint using a class switch.

Replace the outer form container div:
```tsx
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
```
With a responsive container that becomes a bottom sheet on mobile:
```tsx
      {showForm && (
        <>
          {/* Mobile backdrop */}
          <div
            className="md:hidden fixed inset-0 bg-black/40 z-40"
            onClick={resetForm}
          />
          <div
            className={`
              bg-white border-gray-200
              md:rounded-xl md:shadow-sm md:border md:p-6 md:mb-6 md:relative md:z-auto
              fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl shadow-2xl border-t
              md:static
            `}
            style={{ animation: 'slideUpSheet 0.25s ease-out' }}
          >
            {/* Mobile handle bar */}
            <div className="md:hidden flex justify-center pt-3 pb-1">
              <div className="w-10 h-1 bg-gray-300 rounded-full" />
            </div>
```

- [ ] **Step 3: Add animation keyframe via inline style**

In TimeTracking.tsx's return, add a style tag before the main div (or use a class). Since the project has no global CSS besides Tailwind, add:
```tsx
      <style>{`
        @keyframes slideUpSheet {
          from { transform: translateY(100%); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
```

- [ ] **Step 4: Add close button for mobile sheet header**

At the top of the form div (after the handle bar), add a header row for mobile:
```tsx
            <div className="md:hidden flex items-center justify-between px-4 pb-3 border-b border-gray-100">
              <h3 className="text-base font-semibold text-gray-900">
                {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
              </h3>
              <button onClick={resetForm} className="p-2 text-gray-500 hover:text-gray-700">
                <X size={20} />
              </button>
            </div>
            {/* Desktop title */}
            <h3 className="hidden md:block text-lg font-semibold mb-4">
              {editingId ? 'Eintrag bearbeiten' : 'Neuer Zeiteintrag'}
            </h3>
```

- [ ] **Step 5: Make the form fields more spacious on mobile**

The form grid `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4` already stacks on mobile. Add `p-4` to the form content area on mobile:
```tsx
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 p-4 md:p-0 pb-6 md:pb-0 overflow-y-auto max-h-[70vh] md:max-h-none md:overflow-visible">
```

This limits the mobile sheet height to 70% of viewport and enables scroll within the form.

- [ ] **Step 6: Make Save button sticky at bottom on mobile**

Wrap the existing Save button column. The button is at line ~434:
```tsx
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
              <Button type="submit" variant="primary" size="md" icon={Save} fullWidth>
                Speichern
              </Button>
            </div>
```
The sticky save on mobile needs to be outside the scrollable area. Move the save button to a footer div outside the form grid on mobile:

Split the button out of the grid and make a sticky footer version for mobile only. The simplest: keep it in the grid (desktop), and add a separate sticky footer for mobile:

After the closing `</form>`, add:
```tsx
            {/* Sticky save button for mobile */}
            <div className="md:hidden px-4 py-3 border-t border-gray-100 bg-white">
              <Button
                type="button"
                variant="primary"
                size="md"
                fullWidth
                onClick={(e) => {
                  const form = e.currentTarget.closest('div')?.querySelector('form');
                  form?.requestSubmit();
                }}
              >
                Speichern
              </Button>
            </div>
```

And hide the original save button on mobile:
```tsx
            <div className="hidden md:block">
              <label className="block text-sm font-medium text-gray-700 mb-1">&nbsp;</label>
              <Button type="submit" variant="primary" size="md" icon={Save} fullWidth>
                Speichern
              </Button>
            </div>
```

- [ ] **Step 7: Close the extra div opened in Step 2**

Ensure the JSX structure is balanced: the mobile backdrop `<>` fragment needs to close after the form container `</div>` and before `</>`.

- [ ] **Step 8: Build and test**

On mobile (375px): "Neuer Eintrag" button opens a bottom sheet from the bottom. Handle bar visible. Form scrollable within 70vh. Save button sticky at bottom. Tapping backdrop closes it.
On desktop: normal inline form, no change.

- [ ] **Step 9: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/TimeTracking.tsx
git commit -m "ux: TimeTracking form becomes mobile bottom-sheet with sticky save button"
```

---

### Task 10: #3 — Journal: Remove Draft System, Direct Change Request per Entry

Replace the batch draft system in MonthlyJournal.tsx (employee path) with immediate single-entry change request submission. When an employee saves in the Journal, it immediately POSTs to `/change-requests/` without batching.

**Files:**
- Modify: `frontend/src/components/MonthlyJournal.tsx`
- Delete: `frontend/src/components/SubmitChangesModal.tsx` (after removal)

- [ ] **Step 1: Read the full MonthlyJournal.tsx**

Read the complete file to understand all usages of `draftChanges`, `showSubmitModal`, `handleEmployeeSave`, `handleEmployeeDelete`. Note that `isAdminView` controls two different paths — only the employee path needs changing.

- [ ] **Step 2: Add a reason state for the inline submit**

Replace the `draftChanges` and `showSubmitModal` states with a simpler reason input state:

Remove:
```tsx
const [draftChanges, setDraftChanges] = useState<DraftChange[]>([]);
const [showSubmitModal, setShowSubmitModal] = useState(false);
```

Add:
```tsx
const [submittingDate, setSubmittingDate] = useState<string | null>(null);
const [submitReason, setSubmitReason] = useState('');
const [submitting, setSaving2] = useState(false);
```

- [ ] **Step 3: Replace handleEmployeeSave with direct API call + reason prompt**

The new employee save flow:
1. After clicking the check icon, show an inline reason input
2. When reason is confirmed, immediately POST to `/change-requests/`

Replace `handleEmployeeSave`:
```tsx
function startEmployeeSubmit(day: JournalDay) {
  // Same validation as before
  const start = editState.startTime;
  const end = editState.endTime;
  if (!start || !end) {
    toast.error('Von und Bis sind Pflichtfelder');
    return;
  }
  setSubmittingDate(day.date);
  setSubmitReason('');
}

async function confirmEmployeeSubmit(day: JournalDay) {
  if (!submitReason.trim()) {
    toast.error('Bitte eine Begründung angeben');
    return;
  }
  setSaving2(true);
  try {
    const existing = day.time_entries[0];
    const payload: Record<string, unknown> = {
      request_type: existing ? 'update' : 'create',
      reason: submitReason.trim(),
      proposed_date: day.date,
      proposed_start_time: editState.startTime,
      proposed_end_time: editState.endTime,
      proposed_break_minutes: Math.min(parseInt(editState.breakMinutes, 10) || 0, 480),
    };
    if (existing) payload.time_entry_id = existing.id;
    await apiClient.post('/change-requests/', payload);
    toast.success('Änderungsantrag eingereicht');
    setSubmittingDate(null);
    cancelEdit();
    setReloadKey(k => k + 1);
  } catch (err) {
    toast.error(getErrorMessage(err, 'Fehler beim Einreichen'));
  } finally {
    setSaving2(false);
  }
}
```

- [ ] **Step 4: Replace handleEmployeeDelete with direct single change request**

```tsx
function handleEmployeeDelete(day: JournalDay) {
  const entry = day.time_entries[0];
  if (!entry) return;
  confirm({
    title: 'Eintrag löschen (Antrag)',
    message: 'Ein Lösch-Antrag wird direkt eingereicht. Bitte Begründung eingeben.',
    confirmLabel: 'Antrag stellen',
    variant: 'danger',
    onConfirm: async () => {
      // Show reason prompt inline or use a default
      const reason = 'Eintrag fehlerhaft erfasst';
      try {
        await apiClient.post('/change-requests/', {
          request_type: 'delete',
          time_entry_id: entry.id,
          reason,
        });
        toast.success('Lösch-Antrag eingereicht');
        cancelEdit();
        setReloadKey(k => k + 1);
      } catch (err) {
        toast.error(getErrorMessage(err, 'Fehler'));
      }
    },
  });
}
```

- [ ] **Step 5: Update the JSX to show inline reason input**

In the JSX, find where employee save/discard buttons are rendered. Replace the check (✓) button's onClick to call `startEmployeeSubmit(day)` instead of `handleEmployeeSave(day)`.

After the edit row inputs, add a conditional reason input when `submittingDate === day.date`:
```tsx
{submittingDate === day.date && !isAdminView && (
  <div className="col-span-full mt-2 flex gap-2 items-center">
    <input
      type="text"
      value={submitReason}
      onChange={(e) => setSubmitReason(e.target.value)}
      placeholder="Begründung eingeben (Pflicht)"
      className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
      autoFocus
    />
    <button
      onClick={() => confirmEmployeeSubmit(day)}
      disabled={!submitReason.trim() || submitting}
      className="px-3 py-1 text-sm bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50"
    >
      {submitting ? '…' : 'Absenden'}
    </button>
    <button
      onClick={() => setSubmittingDate(null)}
      className="px-3 py-1 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
    >
      Abbrechen
    </button>
  </div>
)}
```

- [ ] **Step 6: Remove SubmitChangesModal import and usage**

Remove from MonthlyJournal.tsx:
```tsx
import SubmitChangesModal from './SubmitChangesModal';
// and all JSX usage of <SubmitChangesModal ... />
```

Also remove the `DraftChange` export from MonthlyJournal.tsx and the corresponding import from SubmitChangesModal.tsx.

- [ ] **Step 7: Delete SubmitChangesModal.tsx**

```bash
rm E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend/src/components/SubmitChangesModal.tsx
```

Check for any remaining imports of SubmitChangesModal:
```bash
grep -r "SubmitChangesModal" E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements/frontend/src/
```
Should return nothing.

- [ ] **Step 8: Build and test**

In the Journal tab (Zeiterfassung → Journal), click edit on a past entry. Enter times, click the check (✓). A reason input should appear. Enter reason, click Absenden. Toast "Änderungsantrag eingereicht" appears. No SubmitChangesModal dialog.

- [ ] **Step 9: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/components/MonthlyJournal.tsx
git rm frontend/src/components/SubmitChangesModal.tsx
git commit -m "ux: replace Journal batch draft system with immediate single-entry change request"
```

---

### Task 11: #4 — Absence Form: Tap-to-Add on Mobile + Simplified Hours Text

**Files:**
- Modify: `frontend/src/pages/AbsenceCalendarPage.tsx`

- [ ] **Step 1: Enable tap-to-add in the mobile list view**

In the mobile list view (around line 640-692), find the `<div key={dateStr} className="border-b border-gray-200 p-4">` row. Add a tap-to-add button at the top of each non-weekend, non-holiday day row (or a "+" button):

In each mobile day row, add a tap area after the day header:
```tsx
                return (
                  <div key={dateStr} className="border-b border-gray-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="font-semibold text-gray-900">
                          {format(day, 'EEEE, dd. MMMM', { locale: de })}
                        </p>
                        {isWeekend && (
                          <span className="text-xs text-gray-500">Wochenende</span>
                        )}
                      </div>
                      {/* Tap-to-add button on mobile (only for non-weekends) */}
                      {!isWeekend && !dayHoliday && (
                        <button
                          onClick={() => {
                            setFormData(prev => ({ ...prev, date: dateStr, hours: getHoursForDate(currentUser, dateStr) || prev.hours }));
                            setShowForm(true);
                            setIsDateRange(false);
                          }}
                          className="p-2 text-gray-400 hover:text-primary hover:bg-gray-50 rounded-lg transition"
                          aria-label={`Abwesenheit für ${format(day, 'dd. MMMM')} eintragen`}
                        >
                          <Plus size={18} />
                        </button>
                      )}
                    </div>
```

**Note:** The mobile list currently only shows days with entries. To enable tap-to-add for all days, we need to also show days WITHOUT entries on mobile. Add a toggle or show all days in mobile list:

Option A (minimal change): Keep showing only days with entries, but the existing form button is enough.
Option B (better): Show all weekdays in the mobile list with a "+" button.

Use Option B — modify the filter:
```tsx
          {/* Mobile List View — show all non-weekend days */}
          <div className="sm:hidden">
            {days
              .filter((day) => day.getDay() !== 0 && day.getDay() !== 6) // show all weekdays
              .map((day) => {
```
Then render the "+" button for days without entries, and the existing entries for days with them. Show a greyed placeholder text for empty days: "Keine Abwesenheit" in small gray text.

- [ ] **Step 2: Simplify the hours field explanation text**

Find the 4 conditional `<p>` texts under the hours input (around line 474-493):
```tsx
                {formData.type === 'vacation' && (
                  <p className="text-xs text-blue-600 mt-1">
                    Urlaub wird in Tagen berechnet (Regelarbeitszeit pro Tag)
                  </p>
                )}
                {formData.type === 'overtime' && (
                  <p className="text-xs text-blue-600 mt-1">
                    Vorausgefüllt mit Regelstunden des Tages
                  </p>
                )}
                {formData.type !== 'vacation' && formData.type !== 'overtime' && currentUser?.use_daily_schedule && !isDateRange && (
                  <p className="text-xs text-blue-600 mt-1">
                    Automatisch aus Tagesplan
                  </p>
                )}
                {formData.type !== 'vacation' && formData.type !== 'overtime' && currentUser?.use_daily_schedule && isDateRange && (
                  <p className="text-xs text-blue-600 mt-1">
                    Bei Tagesplan werden Stunden pro Tag automatisch berechnet
                  </p>
                )}
```

Replace with a single conditional:
```tsx
                <p className="text-xs text-gray-500 mt-1">
                  {formData.type === 'vacation'
                    ? 'Stunden = Regelarbeitszeit pro Tag (für Urlaubsberechnung)'
                    : formData.type === 'overtime'
                    ? 'Vorausgefüllt mit Ihren Sollstunden des Tages'
                    : currentUser?.use_daily_schedule
                    ? 'Stunden werden aus Ihrem Tagesplan übernommen'
                    : 'Stunden, die als Abwesenheit angerechnet werden'}
                </p>
```

- [ ] **Step 3: Build and test on mobile viewport**

Mobile (375px): Abwesenheiten → Kalender-Tab. Mobile list should show all weekdays. Tapping "+" for a day prefills the date and opens the form. Hours text is a single clear sentence.

- [ ] **Step 4: Commit**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
git add frontend/src/pages/AbsenceCalendarPage.tsx
git commit -m "ux: tap-to-add for all weekdays in mobile absence list + simplify hours help text"
```

---

## Final: Build, Deploy, Verify All 11 Tasks

- [ ] **Final build from worktree**
```bash
cd E:/claude/zeiterfassung/praxiszeit/.worktrees/ux-improvements
docker-compose build frontend --no-cache
docker tag ux-improvements-frontend:latest praxiszeit-frontend:latest
cd E:/claude/zeiterfassung/praxiszeit
docker-compose up -d --no-deps frontend
```

- [ ] **Verify checklist at http://localhost**

| # | Check | Pass? |
|---|-------|-------|
| #12 | No § in TimeTracking sunday_exception_reason placeholder | |
| #5 | Selecting a date in TimeTracking auto-fills end_time from daily schedule | |
| #6 | Year view in Abwesenheiten uses prev/next arrows, no number input | |
| #7 | EmptyState component shown on empty months in Zeiterfassung, Anträge, Dashboard | |
| #8 | Abwesenheiten tabs use underline, view-toggle uses segmented border | |
| #11 | No FAB, no "Hilfe" nav item, ? button in sidebar footer opens HelpPanel | |
| #9 | Profile: häufige Sektionen sichtbar, rare in "Weitere Einstellungen" Accordion | |
| #1 | Bottom nav with 4 icons visible on mobile (≤1023px) | |
| #2 | TimeTracking "Neuer Eintrag" opens bottom sheet on mobile | |
| #3 | Journal edit shows inline reason input, submits as change request immediately | |
| #4 | All weekdays in mobile absence list have + button for tap-to-add | |
