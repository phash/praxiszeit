# UX/UI Specialist Memory - PraxisZeit

## UX Audit Complete (2026-03-10)
Full audit of employee-facing frontend completed. Key findings below.

### Design System
- **Primary color**: `#2563EB` (blue-600), dark: `#1E40AF`, light: `#60A5FA`
- **Background**: `#F8FAFC` (slate-50)
- **Button.tsx** component exists but is NOT used anywhere -- all buttons are inline Tailwind
- **Badge.tsx**, **FormInput/Select/Textarea.tsx** exist as shared components
- **Card pattern**: `bg-white rounded-xl shadow-sm border border-gray-200 p-6`
- **Active nav**: `bg-primary text-white`, inactive: `text-gray-700 hover:bg-gray-100`

### Critical UX Issues (Priority Order)
1. **No bottom navigation** -- mobile (80% of users) relies on hamburger sidebar only
2. **Dashboard information overload** -- 6 API calls, 4 stat cards + table + year summary + 3-month calendar
3. **StampWidget not prominent enough** -- same visual weight as stat cards
4. **Touch targets too small** -- Journal icons at ~22px, action icons at ~34px (min should be 44px)
5. **Three different time-entry editing patterns** -- TimeTracking (direct), Journal (draft system), ChangeRequests (view only)
6. **Button.tsx exists but unused** -- inconsistent button styling throughout

### Consistency Issues
- Journal heading `text-2xl` vs all others `text-3xl`
- ChangeRequests.tsx shows raw ISO dates (line ~172)
- StampWidget uses `rounded-xl`, most buttons use `rounded-lg`
- Three different empty-state patterns (plain text, icon+card, icon+text)
- Filter buttons and tabs look identical but have different semantics

### Mobile-Specific Problems
- No swipe-to-close on sidebar
- Absence calendar grid hidden on mobile (`hidden sm:block`), no tap-to-add alternative
- Form inputs at ~36px height (below 44px iOS recommendation)
- Number inputs missing `inputMode="numeric"` attribute

### Files & Line Counts
- Dashboard.tsx: ~567 lines (bloated)
- TimeTracking.tsx: ~652 lines (complex form logic)
- AbsenceCalendarPage.tsx: ~910 lines (most complex page)
- MonthlyJournal.tsx: ~535 lines (inline editing + draft system)
- Profile.tsx: ~705 lines (6 feature sections on one page)
