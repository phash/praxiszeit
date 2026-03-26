# Mobile Refresh – "Soft & Clean" Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the PraxisZeit mobile UI with a "Soft & Clean" aesthetic – new colors, typography, bottom-nav FAB, hero stamp widget, refreshed dashboard and journal cards.

**Architecture:** Design tokens (colors, shadows, radii, font) applied globally via Tailwind config + CSS custom properties. New `uiStore` manages stamp bottom-sheet state. StampWidget promoted from inline Dashboard child to global bottom-sheet in Layout.tsx. Bottom nav restructured with centered FAB.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3.4, Zustand, Lucide icons, DM Sans (self-hosted woff2)

**Spec:** `docs/superpowers/specs/2026-03-17-mobile-refresh-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/public/fonts/DMSans-Regular.woff2` | Create | DM Sans 400 |
| `frontend/public/fonts/DMSans-Medium.woff2` | Create | DM Sans 500 |
| `frontend/public/fonts/DMSans-SemiBold.woff2` | Create | DM Sans 600 |
| `frontend/public/fonts/DMSans-Bold.woff2` | Create | DM Sans 700 |
| `frontend/tailwind.config.js` | Modify | Colors, shadows, radii, font-family |
| `frontend/src/index.css` | Modify | @font-face, keyframes, reduced-motion |
| `frontend/index.html` | Modify | theme-color, viewport-fit |
| `frontend/vite.config.ts` | Modify | theme_color in PWA manifest, font caching |
| `frontend/src/stores/uiStore.ts` | Create | isStampSheetOpen state |
| `frontend/src/components/Layout.tsx` | Modify | Bottom-nav FAB, stamp sheet, safe area |
| `frontend/src/components/StampWidget.tsx` | Modify | Bottom-sheet hero with timer, swipe-dismiss |
| `frontend/src/pages/Dashboard.tsx` | Modify | Greeting, status-card, stat-pills, recent entries |
| `frontend/src/pages/TimeTracking.tsx` | Modify | Week-dots, day-cards with time bar |
| `frontend/src/components/Button.tsx` | Modify | Radii, tap animation |
| `frontend/src/components/Badge.tsx` | Modify | Updated colors |
| `frontend/src/components/MonthSelector.tsx` | Modify | Typography, ghost style |
| `frontend/src/components/LoadingSpinner.tsx` | Modify | Primary color (auto via token) |

---

## Task 1: Create Feature Branch

**Files:** None (git only)

- [ ] **Step 1: Create and switch to feature branch**

```bash
cd E:/claude/zeiterfassung/praxiszeit
git checkout -b feat/mobile-refresh
```

- [ ] **Step 2: Verify clean state**

```bash
git status
```

Expected: `On branch feat/mobile-refresh`, nothing to commit.

---

## Task 2: Design Tokens – Tailwind Config + CSS

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Modify: `frontend/index.html`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Download DM Sans woff2 files**

Download DM Sans font files from Google Fonts API and place in `frontend/public/fonts/`. Need 4 weights: Regular (400), Medium (500), SemiBold (600), Bold (700).

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
mkdir -p public/fonts
# Download from Google Fonts CSS API, extract woff2 URLs, download each
curl -s "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" -H "User-Agent: Mozilla/5.0" | grep -oP 'https://[^)]+\.woff2' | head -4
# Then curl each URL to public/fonts/DMSans-{Regular,Medium,SemiBold,Bold}.woff2
```

If download fails, use an alternative source or the npm package `@fontsource/dm-sans`.

- [ ] **Step 2: Update tailwind.config.js with new design tokens**

Replace full content of `frontend/tailwind.config.js`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#4A90B8',
          dark: '#3A7196',
          light: '#E8F4F8',
        },
        background: '#FAFBFC',
        surface: '#FFFFFF',
        muted: '#F0F4F7',
        border: 'rgba(26, 43, 61, 0.06)',
        success: '#5CB88A',
        danger: '#E07070',
        text: {
          primary: '#1A2B3D',
          secondary: '#6B7F8E',
        },
      },
      boxShadow: {
        soft: '0 2px 8px rgba(26, 43, 61, 0.06)',
        card: '0 4px 16px rgba(26, 43, 61, 0.08)',
        elevated: '0 8px 32px rgba(26, 43, 61, 0.12)',
      },
      borderRadius: {
        '2xl': '16px',
        'xl': '12px',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 3: Update index.css with @font-face, keyframes, reduced-motion**

Replace full content of `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* DM Sans - self-hosted for PWA offline support */
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('/fonts/DMSans-Regular.woff2') format('woff2');
}
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url('/fonts/DMSans-Medium.woff2') format('woff2');
}
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url('/fonts/DMSans-SemiBold.woff2') format('woff2');
}
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('/fonts/DMSans-Bold.woff2') format('woff2');
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'DM Sans', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #FAFBFC;
  color: #1A2B3D;
}

#root {
  min-height: 100vh;
}

/* Animations */
@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

@keyframes fabPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(92, 184, 138, 0.4); }
  50% { box-shadow: 0 0 0 10px rgba(92, 184, 138, 0); }
}

@keyframes stampSuccess {
  0% { opacity: 0; transform: scale(0.5); }
  50% { opacity: 1; transform: scale(1.1); }
  100% { opacity: 0; transform: scale(1); }
}

@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}

/* Skeleton shimmer utility */
.skeleton {
  background: linear-gradient(90deg, #F0F4F7 25%, #E8EDF1 50%, #F0F4F7 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}

/* Page enter animation */
.page-enter {
  animation: fadeSlideIn 200ms ease-out;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Update index.html – theme-color + viewport-fit**

In `frontend/index.html`, change line 7 and 8:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
<meta name="theme-color" content="#4A90B8" />
```

- [ ] **Step 5: Update vite.config.ts – PWA theme_color + font caching**

In `frontend/vite.config.ts`, change `theme_color` on line ~18 from `'#2563EB'` to `'#4A90B8'`. Also add `woff2` to the workbox `globPatterns` (already present, verify).

- [ ] **Step 6: Verify build compiles**

```bash
cd E:/claude/zeiterfassung/praxiszeit
docker-compose exec frontend npm run build
```

If no frontend container, run directly:
```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit && npx vite build
```

Expected: Build succeeds with no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/public/fonts/ frontend/tailwind.config.js frontend/src/index.css frontend/index.html frontend/vite.config.ts
git commit -m "feat(mobile): add design tokens – Soft Clinical palette, DM Sans, shadows, animations"
```

---

## Task 3: UI Store for Stamp Sheet State

**Files:**
- Create: `frontend/src/stores/uiStore.ts`

- [ ] **Step 1: Create uiStore.ts**

Create `frontend/src/stores/uiStore.ts`:

```typescript
import { create } from 'zustand';

interface UIState {
  isStampSheetOpen: boolean;
  openStampSheet: () => void;
  closeStampSheet: () => void;
}

export const useUIStore = create<UIState>()((set) => ({
  isStampSheetOpen: false,
  openStampSheet: () => set({ isStampSheetOpen: true }),
  closeStampSheet: () => set({ isStampSheetOpen: false }),
}));
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/uiStore.ts
git commit -m "feat(mobile): add uiStore for stamp bottom-sheet state"
```

---

## Task 4: Button + Badge + MonthSelector + LoadingSpinner Token Updates

**Files:**
- Modify: `frontend/src/components/Button.tsx`
- Modify: `frontend/src/components/Badge.tsx`
- Modify: `frontend/src/components/MonthSelector.tsx`
- Modify: `frontend/src/components/LoadingSpinner.tsx`

- [ ] **Step 1: Update Button.tsx – rounded-2xl + tap animation**

In `frontend/src/components/Button.tsx`, change `baseStyles` (line 29):

From:
```typescript
const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';
```

To:
```typescript
const baseStyles = 'inline-flex items-center justify-center font-medium rounded-2xl transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed';
```

Update `variantStyles` (lines 31-36) to use new token colors:

```typescript
const variantStyles = {
  primary: 'bg-primary text-white hover:bg-primary-dark focus:ring-primary shadow-soft',
  secondary: 'bg-muted text-text-primary hover:bg-gray-200 focus:ring-gray-400',
  danger: 'bg-danger text-white hover:bg-red-700 focus:ring-red-500',
  ghost: 'bg-transparent text-text-primary hover:bg-muted focus:ring-gray-400',
};
```

- [ ] **Step 2: Update Badge.tsx – updated semantic colors**

In `frontend/src/components/Badge.tsx`, update `variantStyles` (lines 14-20):

```typescript
const variantStyles: Record<BadgeVariant, string> = {
  ...ABSENCE_TYPE_BADGE_COLORS,
  success: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
  warning: 'bg-yellow-100 text-yellow-800',
  info: 'bg-primary-light text-primary-dark',
  default: 'bg-muted text-text-secondary',
};
```

- [ ] **Step 3: Update MonthSelector.tsx – ghost style, font**

In `frontend/src/components/MonthSelector.tsx`:

Change button classes (lines 33-34) from `rounded-lg hover:bg-gray-100` to `rounded-xl hover:bg-muted`.

Change month display (line 41) from `bg-gray-50 rounded-lg` to `bg-muted rounded-xl`.

Change month text (line 43) from `text-gray-900` to `text-text-primary font-semibold`.

Change calendar icon (line 42) from `text-gray-500` to `text-text-secondary`.

Change "Heute" button (line 59) from `text-primary hover:bg-blue-50 rounded-lg` to `text-primary hover:bg-primary-light rounded-xl`.

- [ ] **Step 4: Update LoadingSpinner.tsx**

In `frontend/src/components/LoadingSpinner.tsx`, change `text-gray-600` (line 36) to `text-text-secondary`. The `text-primary` on the spinner SVG (line 17) will automatically pick up the new primary color via the Tailwind config change.

- [ ] **Step 5: Verify build**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Button.tsx frontend/src/components/Badge.tsx frontend/src/components/MonthSelector.tsx frontend/src/components/LoadingSpinner.tsx
git commit -m "feat(mobile): update shared components with Soft Clinical tokens"
```

---

## Task 5: Bottom Navigation with FAB + Clock Status + Stamp Sheet

**Files:**
- Modify: `frontend/src/components/Layout.tsx`

This is the most complex task. The bottom nav gets redesigned with a centered FAB (including clock-status awareness), and the stamp bottom-sheet gets integrated. Merges former Task 10 (FAB clock status) into this task so QA can test the complete feature.

- [ ] **Step 1: Add imports to Layout.tsx**

At the top of `frontend/src/components/Layout.tsx`, add these imports (note: use **existing** icon names from the file – `LayoutDashboard`, `Clock`, `Calendar`, `User` – plus new ones for the FAB):

```typescript
import { useUIStore } from '../stores/uiStore';
import { Play, Timer, Square, X } from 'lucide-react';
import StampWidget from './StampWidget';
import apiClient from '../api/client';
```

Inside the component function, add:

```typescript
const { isStampSheetOpen, openStampSheet, closeStampSheet } = useUIStore();
const [isClockedIn, setIsClockedIn] = useState(false);
const [sheetClosing, setSheetClosing] = useState(false);

// Clock status for FAB appearance
useEffect(() => {
  if (!user?.track_hours) return;
  const checkStatus = async () => {
    try {
      const res = await apiClient.get('/time-entries/clock-status');
      setIsClockedIn(res.data.is_clocked_in);
    } catch { /* ignore */ }
  };
  checkStatus();
  const interval = setInterval(checkStatus, 60000);
  return () => clearInterval(interval);
}, [user]);

// Stamp success handler – refreshes FAB status and closes sheet
const handleStampSuccess = () => {
  apiClient.get('/time-entries/clock-status').then(res => {
    setIsClockedIn(res.data.is_clocked_in);
  }).catch(() => {});
  // Animate sheet closed
  setSheetClosing(true);
  setTimeout(() => {
    closeStampSheet();
    setSheetClosing(false);
  }, 250);
};
```

- [ ] **Step 2: Replace mobile bottom navigation**

Replace the existing mobile bottom nav section (the `lg:hidden fixed bottom-0` nav block) with the new FAB-centered navigation. Use the **existing** icon names from Layout.tsx (`LayoutDashboard`, `Clock`, `Calendar`, `User`):

```tsx
{/* Mobile Bottom Navigation */}
<nav className="lg:hidden fixed bottom-0 left-0 right-0 z-30" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
  <div className="relative">
    {/* FAB - Centered Stamp Button */}
    {user?.track_hours && (
      <button
        onClick={openStampSheet}
        className={`absolute left-1/2 -translate-x-1/2 -top-3 z-[31] w-14 h-14 rounded-full shadow-elevated flex items-center justify-center transition-all duration-300 active:scale-90 ${
          isClockedIn
            ? 'bg-gradient-to-br from-success to-[#4AA87A]'
            : 'bg-gradient-to-br from-primary to-primary-dark'
        }`}
        style={isClockedIn ? { animation: 'fabPulse 3s ease-in-out infinite' } : undefined}
        aria-label={isClockedIn ? 'Eingestempelt – Stempeluhr öffnen' : 'Stempeluhr öffnen'}
      >
        {isClockedIn ? <Timer size={24} className="text-white" /> : <Play size={24} className="text-white ml-0.5" />}
      </button>
    )}

    {/* Nav Bar */}
    <div className="bg-white/85 supports-[backdrop-filter]:backdrop-blur-xl supports-not-[backdrop-filter]:bg-white/[0.97] border-t border-border rounded-t-3xl">
      <div className="flex items-center h-16">
        <Link to="/" className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${location.pathname === '/' ? 'text-primary' : 'text-text-secondary'}`}>
          <LayoutDashboard size={22} strokeWidth={1.75} />
          <span className="text-[10px] font-medium">Home</span>
          {location.pathname === '/' && <div className="w-1 h-1 rounded-full bg-primary" />}
        </Link>
        <Link to="/time-tracking" className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${location.pathname.startsWith('/time-tracking') ? 'text-primary' : 'text-text-secondary'}`}>
          <Clock size={22} strokeWidth={1.75} />
          <span className="text-[10px] font-medium">Journal</span>
          {location.pathname.startsWith('/time-tracking') && <div className="w-1 h-1 rounded-full bg-primary" />}
        </Link>
        {/* FAB spacer */}
        <div className="w-[72px] shrink-0" />
        <Link to="/absences" className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${location.pathname.startsWith('/absences') ? 'text-primary' : 'text-text-secondary'}`}>
          <Calendar size={22} strokeWidth={1.75} />
          <span className="text-[10px] font-medium">Abwes.</span>
          {location.pathname.startsWith('/absences') && <div className="w-1 h-1 rounded-full bg-primary" />}
        </Link>
        <Link to="/profile" className={`flex-1 flex flex-col items-center justify-center gap-1 py-2 min-w-[44px] min-h-[44px] transition-colors ${location.pathname.startsWith('/profile') ? 'text-primary' : 'text-text-secondary'}`}>
          <User size={22} strokeWidth={1.75} />
          <span className="text-[10px] font-medium">Profil</span>
          {location.pathname.startsWith('/profile') && <div className="w-1 h-1 rounded-full bg-primary" />}
        </Link>
      </div>
    </div>
  </div>
</nav>
```

Key fixes vs. original plan:
- Uses existing icon names (`LayoutDashboard`, `Clock`, `Calendar`, `User`)
- Route paths use `/` for dashboard (matching existing router config)
- `z-[31]` with bracket syntax (valid Tailwind arbitrary value)
- `min-w-[44px] min-h-[44px]` for WCAG touch target compliance
- `supports-[backdrop-filter]` for glassmorphism with CSS fallback
- No `.filter(Boolean)` – explicit spacer div instead

- [ ] **Step 3: Add Stamp Bottom-Sheet to Layout**

After the bottom nav, before the closing `</>` of the Layout component, add the stamp bottom-sheet with **close button** and **close animation**:

```tsx
{/* Stamp Bottom Sheet */}
{isStampSheetOpen && (
  <>
    {/* Backdrop */}
    <div
      className="fixed inset-0 bg-black/40 z-40 lg:hidden transition-opacity duration-200"
      style={{ opacity: sheetClosing ? 0 : 1 }}
      onClick={handleStampSuccess}
    />
    {/* Sheet */}
    <div
      className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-surface rounded-t-3xl shadow-elevated transition-transform duration-250 ease-out"
      style={{
        animation: sheetClosing ? undefined : 'slideUp 300ms ease-out',
        transform: sheetClosing ? 'translateY(100%)' : 'translateY(0)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      {/* Header: Handle bar + Close button */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="w-8" /> {/* spacer for centering */}
        <div className="w-10 h-1 bg-gray-300 rounded-full" />
        <button
          onClick={handleStampSuccess}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-muted transition"
          aria-label="Schließen"
        >
          <X size={18} className="text-text-secondary" />
        </button>
      </div>
      <div className="px-6 pb-6">
        <StampWidget variant="sheet" onSuccess={handleStampSuccess} />
      </div>
    </div>
  </>
)}
```

Key fixes: X close button top-right, close animation via `sheetClosing` state, backdrop click also closes.

- [ ] **Step 4: Update mobile header with new tokens**

Update the mobile header bar to use new design tokens:
- Change any `bg-white` to `bg-surface`
- Change text colors to `text-text-primary`
- Change hover states to `hover:bg-muted`

- [ ] **Step 5: Update main content padding**

The main content area needs updated padding to account for the taller bottom nav with FAB:

```tsx
<main id="main-content" className="flex-1 overflow-auto pt-16 pb-20 lg:pt-0 lg:pb-0 bg-background">
```

Changed `pb-16` to `pb-20` to give more space for the protruding FAB.

- [ ] **Step 6: Update sidebar tokens**

Update sidebar colors throughout Layout.tsx:
- Logo area: Use `text-primary` for the brand name
- Active nav item: Use `bg-primary-light text-primary-dark` instead of `bg-blue-50 text-primary`
- Inactive nav items: Use `text-text-secondary hover:bg-muted`
- User section: Use `bg-muted` for the user info area

- [ ] **Step 7: Verify build**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat(mobile): redesign bottom nav with FAB, clock-status pulse, stamp bottom-sheet"
```

---

## Task 6: StampWidget Hero Bottom-Sheet

**Files:**
- Modify: `frontend/src/components/StampWidget.tsx`

The StampWidget needs to support two modes: `inline` (for desktop dashboard) and `sheet` (for the mobile bottom-sheet). The sheet mode has the large timer, info-pills layout.

- [ ] **Step 1: Add variant prop and timer format**

Update the component interface and add HH:MM:SS formatting:

```typescript
interface StampWidgetProps {
  variant?: 'inline' | 'sheet';
  onSuccess?: () => void;
}
```

Add a `formatTimer` helper:

```typescript
function formatTimer(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  const s = 0; // seconds not tracked, show :00
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
```

- [ ] **Step 2: Update timer interval to 1s for sheet mode**

Change the `useEffect` timer (around lines 44-51) to update every second when in sheet mode:

```typescript
useEffect(() => {
  if (!status?.is_clocked_in) return;
  const interval = setInterval(() => {
    setElapsed(prev => prev + (variant === 'sheet' ? 1/60 : 1));
  }, variant === 'sheet' ? 1000 : 60000);
  return () => clearInterval(interval);
}, [status?.is_clocked_in, variant]);
```

- [ ] **Step 3: Add sheet variant render**

When `variant === 'sheet'`, render the hero layout:

```tsx
if (variant === 'sheet') {
  return (
    <div className="text-center">
      {/* Large Timer */}
      <div className="text-[40px] font-bold tabular-nums text-text-primary leading-none mb-1">
        {status?.is_clocked_in ? formatTimer(elapsed) : '00:00:00'}
      </div>
      <p className="text-sm text-text-secondary mb-6">Arbeitszeit heute</p>

      {/* Info Pills */}
      <div className="flex justify-center gap-3 mb-6">
        <div className="bg-muted rounded-full px-4 py-2 text-center">
          <div className="text-sm font-semibold tabular-nums">
            {status?.current_entry ? format(new Date(status.current_entry.start_time), 'HH:mm') : '—'}
          </div>
          <div className="text-xs text-text-secondary">Start</div>
        </div>
        <div className="bg-muted rounded-full px-4 py-2 text-center">
          <div className="text-sm font-semibold tabular-nums">
            {breakMinutes > 0 ? `${breakMinutes} min` : '—'}
          </div>
          <div className="text-xs text-text-secondary">Pause</div>
        </div>
      </div>

      {/* Break Input (only when clocked in and ready to clock out) */}
      {showBreakInput && (
        <div className="mb-4">
          <label className="block text-sm text-text-secondary mb-1">Pause (Minuten)</label>
          <input
            type="number"
            min={0}
            max={480}
            value={breakMinutes}
            onChange={(e) => setBreakMinutes(Number(e.target.value))}
            className="w-full border border-gray-200 rounded-xl px-4 py-3 text-center text-lg focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
      )}

      {/* Action Button */}
      {status?.is_clocked_in ? (
        <button
          onClick={handleClockOut}
          disabled={acting}
          className="w-full h-14 rounded-2xl bg-danger text-white font-semibold text-lg flex items-center justify-center gap-2 active:scale-[0.97] transition-all disabled:opacity-50"
        >
          <Square size={20} />
          {showBreakInput ? 'Jetzt ausstempeln' : 'Ausstempeln'}
        </button>
      ) : (
        <button
          onClick={handleClockIn}
          disabled={acting}
          className="w-full h-14 rounded-2xl bg-gradient-to-r from-primary to-primary-dark text-white font-semibold text-lg flex items-center justify-center gap-2 active:scale-[0.97] transition-all disabled:opacity-50"
        >
          <Play size={20} />
          Einstempeln
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Update inline variant styling**

Update the existing (inline) render to use new design tokens:
- Replace hardcoded green/gray colors with `bg-success/10`, `border-success` etc.
- Use `rounded-2xl` instead of `rounded-xl`
- Use `shadow-card` for the card

- [ ] **Step 5: Add success animation + call onSuccess**

Add a `showSuccess` state:

```typescript
const [showSuccess, setShowSuccess] = useState(false);
```

In `handleClockIn` and `handleClockOut`, after successful API call, show the checkmark briefly before closing:

```typescript
// After successful API call in both handlers:
await fetchStatus();
if (variant === 'sheet') {
  setShowSuccess(true);
  setTimeout(() => {
    setShowSuccess(false);
    onSuccess?.();
  }, 600);
} else {
  // inline variant: no animation needed
}
```

Add the success overlay at the top of the sheet variant render (inside the `if (variant === 'sheet')` block):

```tsx
{showSuccess && (
  <div className="absolute inset-0 flex items-center justify-center z-10">
    <Check size={48} className="text-success" style={{ animation: 'stampSuccess 400ms ease-out' }} />
  </div>
)}
```

Import `Check` from lucide-react at the top of the file.

- [ ] **Step 6: Verify build**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/StampWidget.tsx
git commit -m "feat(mobile): StampWidget hero bottom-sheet with large timer and info pills"
```

---

## Task 7: Dashboard Redesign

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add imports**

Add to Dashboard.tsx:

```typescript
import { useUIStore } from '../stores/uiStore';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
```

Inside component:

```typescript
const { openStampSheet } = useUIStore();
const { user } = useAuthStore();
```

- [ ] **Step 2: Add clock status + recent entries state + fetch**

Add state for clock status, recent entries, and derived values:

```typescript
const [clockStatus, setClockStatus] = useState<{ is_clocked_in: boolean; current_entry?: { start_time: string } } | null>(null);
const [recentEntries, setRecentEntries] = useState<Array<{
  id: string;
  date: string;
  start_time: string;
  end_time: string | null;
  net_hours: number;
}>>([]);

// Inside the existing fetchData useEffect, add these two API calls:
const currentMonth = format(new Date(), 'yyyy-MM');
const [entriesRes, clockRes] = await Promise.all([
  apiClient.get(`/time-entries?month=${currentMonth}`),
  user?.track_hours ? apiClient.get('/time-entries/clock-status') : Promise.resolve({ data: null }),
]);
setRecentEntries(entriesRes.data.slice(-5).reverse());
if (clockRes.data) setClockStatus(clockRes.data);
```

Derive `actualHours` and `targetHours` from existing dashboard data:

```typescript
const actualHours = dashboardData?.actual_hours ?? 0;
const targetHours = dashboardData?.target_hours ?? 8;
```

- [ ] **Step 3: Redesign mobile layout – Greeting**

Replace the title section (around lines 172-177) with:

```tsx
{/* Greeting */}
<div className="mb-6">
  <h1 className="text-2xl font-semibold text-text-primary">
    Hallo, {user?.first_name || 'Willkommen'}
  </h1>
  <p className="text-sm text-text-secondary">
    {format(new Date(), 'EEEE, d. MMMM yyyy', { locale: de })}
  </p>
</div>
```

- [ ] **Step 4: Add Status Card Hero (mobile only)**

Below the greeting, add:

```tsx
{/* Status Card - Mobile Hero */}
<div
  className="md:hidden bg-surface rounded-2xl shadow-card p-5 mb-6 cursor-pointer active:shadow-soft transition-shadow"
  onClick={openStampSheet}
>
  <div className="flex items-center gap-2 mb-3">
    <div className={`w-2 h-2 rounded-full ${clockStatus?.is_clocked_in ? 'bg-success' : 'bg-gray-300'}`} />
    <span className="text-sm font-medium text-text-primary">
      {clockStatus?.is_clocked_in
        ? `Eingestempelt seit ${format(new Date(clockStatus.current_entry!.start_time), 'HH:mm')}`
        : 'Nicht eingestempelt'}
    </span>
  </div>
  {/* Progress bar */}
  <div className="h-1.5 bg-muted rounded-full overflow-hidden mb-2">
    <div
      className="h-full bg-gradient-to-r from-primary to-primary-dark rounded-full transition-all duration-1000"
      style={{ width: `${Math.min((actualHours / targetHours) * 100, 100)}%` }}
    />
  </div>
  <p className="text-xs text-text-secondary">
    {actualHours.toFixed(1)} von {targetHours.toFixed(1)} Std
  </p>
</div>
```

Note: `clockStatus`, `actualHours`, `targetHours` need to be derived from existing dashboard data (DashboardData.actual_hours, target_hours). The clock status may need fetching from `/time-entries/clock-status`.

- [ ] **Step 5: Redesign stat cards as pills (mobile)**

Replace the stats grid (around lines 180-319) for mobile with compact pills:

```tsx
{/* Stat Pills - Mobile */}
<div className="grid grid-cols-3 gap-3 mb-6 md:hidden">
  <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
    <div className={`text-xl font-bold tabular-nums ${overtime >= 0 ? 'text-success' : 'text-danger'}`}>
      {overtime >= 0 ? '+' : ''}{overtime.toFixed(1)}
    </div>
    <div className="text-xs text-text-secondary mt-1">Überstd.</div>
  </div>
  <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
    <div className="text-xl font-bold tabular-nums text-text-primary">
      {vacationRemaining}
    </div>
    <div className="text-xs text-text-secondary mt-1">Urlaub</div>
  </div>
  <div className="bg-surface rounded-2xl shadow-soft p-4 text-center">
    <div className="text-xl font-bold tabular-nums text-text-primary">
      {sickDays}
    </div>
    <div className="text-xs text-text-secondary mt-1">Krank</div>
  </div>
</div>
```

Keep the existing desktop grid for `hidden md:grid`.

- [ ] **Step 6: Add recent entries section (mobile)**

Below the stat pills, add:

```tsx
{/* Recent Entries - Mobile */}
{recentEntries.length > 0 && (
  <div className="md:hidden bg-surface rounded-2xl shadow-soft mb-6">
    <div className="px-4 py-3 border-b border-muted">
      <h3 className="text-sm font-semibold text-text-primary">Letzte Einträge</h3>
    </div>
    <div className="divide-y divide-muted">
      {recentEntries.map(entry => (
        <div key={entry.id} className="px-4 py-3 flex items-center justify-between">
          <span className="text-sm text-text-secondary">
            {format(new Date(entry.date + 'T00:00:00'), 'EE d.MM', { locale: de })}
          </span>
          <span className="text-sm text-text-secondary tabular-nums">
            {entry.start_time?.slice(0, 5)}–{entry.end_time?.slice(0, 5) || '…'}
          </span>
          <span className="text-sm font-medium tabular-nums text-text-primary">
            {entry.net_hours.toFixed(1)}h
          </span>
        </div>
      ))}
    </div>
    <Link to="/time-tracking" className="block px-4 py-3 text-sm text-primary font-medium text-center border-t border-muted">
      Alle anzeigen →
    </Link>
  </div>
)}
```

- [ ] **Step 7: Keep StampWidget inline for desktop only**

The existing `<StampWidget />` in Dashboard should now only show on desktop:

```tsx
<div className="hidden md:block">
  <StampWidget />
</div>
```

- [ ] **Step 8: Update desktop cards with new tokens**

Update the existing stat cards' colors to use new tokens:
- `bg-white` → `bg-surface`
- `rounded-xl` → `rounded-2xl`
- `shadow` → `shadow-card`
- `text-gray-600` → `text-text-secondary`
- `text-gray-900` → `text-text-primary`
- Green/red semantic colors → `text-success`/`text-danger`

- [ ] **Step 9: Add mobile skeleton loading states**

Replace the existing loading spinner for mobile with skeleton placeholders:

```tsx
{loading && (
  <div className="md:hidden space-y-4">
    {/* Greeting skeleton */}
    <div className="skeleton h-7 w-3/5 mb-1" />
    <div className="skeleton h-4 w-2/5 mb-6" />
    {/* Status card skeleton */}
    <div className="skeleton h-24 rounded-2xl mb-6" />
    {/* Stat pills skeleton */}
    <div className="grid grid-cols-3 gap-3 mb-6">
      <div className="skeleton h-20 rounded-2xl" />
      <div className="skeleton h-20 rounded-2xl" />
      <div className="skeleton h-20 rounded-2xl" />
    </div>
    {/* Recent entries skeleton */}
    <div className="skeleton h-12 rounded-2xl mb-2" />
    <div className="skeleton h-12 rounded-2xl mb-2" />
    <div className="skeleton h-12 rounded-2xl" />
  </div>
)}
```

Keep the existing `<LoadingSpinner>` for desktop (inside a `hidden md:flex` wrapper).

- [ ] **Step 10: Add page-enter animation**

Wrap the main content in:

```tsx
<div className="page-enter p-4 md:p-6 lg:p-8">
```

- [ ] **Step 10: Verify build**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(mobile): dashboard redesign – greeting, status hero, stat pills, recent entries"
```

---

## Task 8: Journal / TimeTracking Card Redesign

**Files:**
- Modify: `frontend/src/pages/TimeTracking.tsx`

- [ ] **Step 1: Add week-dots component (inline)**

Add a WeekDots helper component inside `TimeTracking.tsx` (or as a separate small component):

```tsx
function WeekDots({
  entries,
  currentDate,
  onDotClick,
  onWeekChange,
}: {
  entries: TimeEntry[];
  currentDate: Date;
  onDotClick: (date: string) => void;
  onWeekChange: (direction: -1 | 1) => void;
}) {
  // Calculate Monday of the week containing currentDate
  const day = currentDate.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(currentDate);
  monday.setDate(monday.getDate() + mondayOffset);

  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(d.getDate() + i);
    return format(d, 'yyyy-MM-dd');
  });
  const today = format(new Date(), 'yyyy-MM-dd');
  const entryDates = new Set(entries.map(e => e.date));

  return (
    <div className="flex items-center gap-1 px-1 py-3 md:hidden">
      <button onClick={() => onWeekChange(-1)} className="p-1 rounded-lg hover:bg-muted transition" aria-label="Vorherige Woche">
        <ChevronLeft size={16} className="text-text-secondary" />
      </button>
      <div className="flex-1 flex items-center justify-between">
        {days.map(dateStr => {
          const dayOfWeek = format(new Date(dateStr + 'T00:00:00'), 'EEEEEE', { locale: de });
          const hasEntry = entryDates.has(dateStr);
          const isToday = dateStr === today;
          return (
            <button
              key={dateStr}
              onClick={() => onDotClick(dateStr)}
              className="flex flex-col items-center gap-1"
            >
              <span className="text-[10px] text-text-secondary uppercase">{dayOfWeek}</span>
              <span className="text-xs tabular-nums text-text-secondary">
                {new Date(dateStr + 'T00:00:00').getDate()}
              </span>
              <div className={`w-2 h-2 rounded-full transition-colors ${
                hasEntry ? 'bg-primary' : 'bg-muted'
              } ${isToday ? 'ring-2 ring-primary ring-offset-1' : ''}`} />
            </button>
          );
        })}
      </div>
      <button onClick={() => onWeekChange(1)} className="p-1 rounded-lg hover:bg-muted transition" aria-label="Nächste Woche">
        <ChevronRight size={16} className="text-text-secondary" />
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Add time bar component (inline)**

Add a TimeBar helper for the visual time representation:

```tsx
function TimeBar({ startTime, endTime, breakMinutes }: { startTime: string; endTime: string | null; breakMinutes: number }) {
  if (!endTime) return null;
  const dayStart = 6 * 60; // 06:00
  const dayEnd = 20 * 60;  // 20:00
  const range = dayEnd - dayStart;

  const [sh, sm] = startTime.split(':').map(Number);
  const [eh, em] = endTime.split(':').map(Number);
  const startMin = sh * 60 + sm;
  const endMin = eh * 60 + em;

  const left = Math.max(0, ((startMin - dayStart) / range) * 100);
  const width = Math.max(0, ((endMin - startMin) / range) * 100);

  return (
    <div className="relative h-2 bg-muted rounded-full my-3">
      <div
        className="absolute h-full bg-gradient-to-r from-primary to-primary-dark rounded-full"
        style={{ left: `${left}%`, width: `${width}%` }}
      />
      <div className="flex justify-between mt-2">
        <span className="text-[10px] text-text-secondary tabular-nums">{startTime.slice(0, 5)}</span>
        <span className="text-[10px] text-text-secondary tabular-nums">{endTime.slice(0, 5)}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Redesign mobile entry cards**

Replace the existing mobile card view (the `md:hidden` section) with new day-cards:

```tsx
{/* Mobile Day Cards */}
<div className="md:hidden space-y-3">
  <WeekDots entries={entries} currentDate={new Date()} onDotClick={(date) => {
    document.getElementById(`entry-${date}`)?.scrollIntoView({ behavior: 'smooth' });
  }} />
  {entries.map((entry, i) => (
    <div
      key={entry.id}
      id={`entry-${entry.date}`}
      className="bg-surface rounded-2xl shadow-soft p-4"
      style={{ animation: `fadeSlideIn 200ms ease-out ${i * 50}ms both` }}
    >
      <div className="font-semibold text-text-primary">
        {format(new Date(entry.date + 'T00:00:00'), 'EEEE, d. MMMM', { locale: de })}
      </div>
      <TimeBar startTime={entry.start_time} endTime={entry.end_time} breakMinutes={entry.break_minutes} />
      <div className="grid grid-cols-2 gap-2 text-sm mb-3">
        <div>
          <span className="text-text-secondary">Arbeitszeit</span>
          <span className="float-right font-medium tabular-nums">{entry.net_hours.toFixed(1)}h</span>
        </div>
        <div>
          <span className="text-text-secondary">Pause</span>
          <span className="float-right font-medium tabular-nums">{entry.break_minutes} min</span>
        </div>
      </div>
      {entry.is_editable && (
        <div className="flex gap-2">
          <button
            onClick={() => handleEdit(entry)}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-text-secondary hover:bg-muted transition"
          >
            <Edit2 size={14} /> Bearbeiten
          </button>
          <button
            onClick={() => handleDelete(entry.id)}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl text-sm text-danger hover:bg-red-50 transition"
          >
            <Trash2 size={14} /> Löschen
          </button>
        </div>
      )}
    </div>
  ))}
</div>
```

- [ ] **Step 4: Update tab navigation styling**

Update the tab navigation at the top of TimeTracking to use new tokens:
- Active tab: `bg-primary text-white rounded-xl`
- Inactive tab: `text-text-secondary hover:bg-muted rounded-xl`

- [ ] **Step 5: Update desktop table with new tokens**

Update the desktop table (`hidden md:block` section):
- `bg-white` → `bg-surface`
- `rounded-lg` → `rounded-2xl`
- `shadow` → `shadow-card`
- Header text: `text-text-secondary`
- Body text: `text-text-primary`

- [ ] **Step 6: Add page-enter animation wrapper**

Wrap the page content in `<div className="page-enter">`.

- [ ] **Step 7: Verify build**

```bash
cd E:/claude/zeiterfassung/praxiszeit/frontend
npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/TimeTracking.tsx
git commit -m "feat(mobile): journal day-cards with time bars, week-dots navigation"
```

---

## Task 9: Visual QA + Polish

**Files:** Various (all modified files)

- [ ] **Step 1: Start the app and check on mobile**

```bash
cd E:/claude/zeiterfassung/praxiszeit
docker-compose up -d
```

Open http://localhost on a mobile device or Chrome DevTools mobile emulator (iPhone 14 Pro, 393x852).

- [ ] **Step 2: Check each screen**

Verify on mobile (Chrome DevTools → responsive mode):

1. **Bottom Nav:** FAB centered, tabs evenly spaced, glassmorphism blur visible, active dot indicator
2. **FAB tap:** Opens stamp bottom-sheet, handle bar visible, timer displays
3. **Dashboard:** Greeting with name + date, Status Card with progress bar, 3 stat pills, recent entries list
4. **Journal:** Week dots show current week, day-cards with time bars, staggered animation
5. **All pages:** DM Sans font loaded, new color scheme consistent, shadows visible

- [ ] **Step 3: Check desktop is not broken**

Open http://localhost on desktop (1440px width):
- Sidebar still works, all nav items accessible
- Dashboard stat cards render in 4-column grid
- TimeTracking table visible
- Admin pages accessible via sidebar

- [ ] **Step 4: Check safe area on iPhone (if available)**

In Chrome DevTools, test with iPhone viewport. Verify bottom nav doesn't overlap with home indicator area.

- [ ] **Step 5: Check reduced motion**

In Chrome DevTools → Rendering → Emulate CSS media feature `prefers-reduced-motion: reduce`. Verify all animations are suppressed.

- [ ] **Step 6: Fix any issues found**

Address visual glitches, misaligned elements, color inconsistencies, or TypeScript errors.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat(mobile): visual QA polish and fixes"
```

---

## Summary

| Task | Description | Estimated Complexity |
|------|-------------|---------------------|
| 1 | Feature branch | Trivial |
| 2 | Design tokens (Tailwind, CSS, fonts) | Medium |
| 3 | UI Store | Trivial |
| 4 | Shared component updates | Low |
| 5 | Bottom Nav + FAB + Clock Status + Stamp Sheet | High |
| 6 | StampWidget Bottom-Sheet | High |
| 7 | Dashboard redesign | High |
| 8 | Journal card redesign | Medium |
| 9 | Visual QA + Polish | Medium |

**Total commits:** 9 (one per task)
