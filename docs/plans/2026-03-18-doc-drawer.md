# DocDrawer & DocModal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace download links for Handbuch/Cheatsheet with an in-app Side Drawer (desktop) / Bottom Sheet (mobile) and a Login-page Modal that render the existing React content directly.

**Architecture:** Extract shared content components from `Help.tsx` into `DocViewer.tsx`, build `DocDrawer` and `DocModal` around them, then wire up `Layout.tsx` and `Login.tsx`. No new dependencies, no Markdown renderer — existing JSX components are reused directly.

**Tech Stack:** React 18, TypeScript, Tailwind CSS v3, Vite (frontend only). No unit test framework — verification is via `docker-compose build frontend` + manual browser check. E2E suite is in `e2e/` (Playwright) but not extended in this plan.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `frontend/src/components/DocViewer.tsx` | All shared doc content: `AccordionItem`, `Accordion`, `CheatsheetMitarbeiter`, `CheatsheetAdmin`, `handbuchMitarbeiterSections`, `handbuchAdminSections`, `DocViewerContent` |
| **Create** | `frontend/src/components/DocDrawer.tsx` | Side drawer (desktop) + bottom sheet (mobile); wraps `DocViewerContent` |
| **Create** | `frontend/src/components/DocModal.tsx` | Centered modal for Login page; wraps `DocViewerContent` with `isAdmin={false}` |
| **Modify** | `frontend/src/pages/Help.tsx` | Import symbols from `DocViewer.tsx` instead of defining them locally |
| **Modify** | `frontend/src/components/Layout.tsx` | Replace `<a download>` links with buttons that open `DocDrawer` |
| **Modify** | `frontend/src/pages/Login.tsx` | Replace `<a download>` links with buttons that open `DocModal` |
| **Modify** | `.gitignore` | Add `.superpowers/` entry |

---

## Task 1: Add `.superpowers/` to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add entry**

Open `.gitignore` and append after the `.worktrees/` line:

```
.superpowers/
```

- [ ] **Step 2: Commit**

```bash
cd E:/claude/zeiterfassung/praxiszeit
git add .gitignore
git commit -m "chore: gitignore .superpowers/ brainstorm sessions"
```

---

## Task 2: Create `DocViewer.tsx` — extract shared content from Help.tsx

**Files:**
- Create: `frontend/src/components/DocViewer.tsx`

This task moves seven symbols out of `Help.tsx` into a shared file and adds the new `DocViewerContent` component.

- [ ] **Step 1: Create `DocViewer.tsx`**

Create `frontend/src/components/DocViewer.tsx` with the following content (copy the relevant blocks from `Help.tsx` verbatim, then add `DocViewerContent` at the bottom):

```tsx
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

export interface AccordionItem {
  title: string;
  content: React.ReactNode;
}

// ── Accordion ────────────────────────────────────────────────────────────────

export function Accordion({ items }: { items: AccordionItem[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="divide-y divide-gray-200 border border-gray-200 rounded-lg overflow-hidden">
      {items.map((item, i) => (
        <div key={i}>
          <button
            onClick={() => setOpen(open === i ? null : i)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
          >
            <span className="font-medium text-gray-800 text-sm">{item.title}</span>
            {open === i
              ? <ChevronDown size={16} className="text-gray-500 flex-shrink-0" />
              : <ChevronRight size={16} className="text-gray-500 flex-shrink-0" />}
          </button>
          {open === i && (
            <div className="px-4 py-3 text-sm text-gray-600 bg-gray-50 border-t border-gray-200">
              {item.content}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Cheatsheet content ───────────────────────────────────────────────────────

export function CheatsheetMitarbeiter() {
  // ← PASTE the full CheatsheetMitarbeiter function body from Help.tsx (lines 7-123)
}

export function CheatsheetAdmin() {
  // ← PASTE the full CheatsheetAdmin function body from Help.tsx (lines 126-216)
}

// ── Handbuch sections ────────────────────────────────────────────────────────

export const handbuchMitarbeiterSections: AccordionItem[] = [
  // ← PASTE from Help.tsx (lines 252-309)
];

export const handbuchAdminSections: AccordionItem[] = [
  // ← PASTE from Help.tsx (lines 311-375)
];

// ── DocViewerContent ─────────────────────────────────────────────────────────

type DocTab = 'cheatsheet' | 'handbuch';

interface DocViewerContentProps {
  isAdmin: boolean;
  initialTab?: DocTab;
  onTabChange?: (tab: DocTab) => void;
}

export function DocViewerContent({ isAdmin, initialTab = 'cheatsheet', onTabChange }: DocViewerContentProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);

  function handleTab(tab: DocTab) {
    setActiveTab(tab);
    onTabChange?.(tab);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="border-b border-gray-200 px-4 flex gap-6 flex-shrink-0">
        {(['cheatsheet', 'handbuch'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => handleTab(tab)}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'cheatsheet' ? 'Kurzanleitung' : 'Handbuch'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'cheatsheet'
          ? (isAdmin ? <CheatsheetAdmin /> : <CheatsheetMitarbeiter />)
          : <Accordion items={isAdmin ? handbuchAdminSections : handbuchMitarbeiterSections} />
        }
      </div>
    </div>
  );
}
```

**Important:** Replace the placeholder comments with the actual content copied verbatim from `Help.tsx`. The approximate line ranges in the current `Help.tsx` are: `CheatsheetMitarbeiter` ~lines 7–123, `CheatsheetAdmin` ~lines 126–216, `handbuchMitarbeiterSections` ~lines 252–309, `handbuchAdminSections` ~lines 311–375. Verify actual ranges with `Read frontend/src/pages/Help.tsx` before copying, as line numbers can drift.

- [ ] **Step 2: Update `Help.tsx` to import from `DocViewer.tsx`**

At the top of `Help.tsx`, replace the local definitions of `AccordionItem`, `Accordion`, `CheatsheetMitarbeiter`, `CheatsheetAdmin`, `handbuchMitarbeiterSections`, `handbuchAdminSections` with imports:

```tsx
import {
  AccordionItem,
  Accordion,
  CheatsheetMitarbeiter,
  CheatsheetAdmin,
  handbuchMitarbeiterSections,
  handbuchAdminSections,
} from '../components/DocViewer';
```

Remove the local definitions of all six symbols from `Help.tsx` (the `// ── Cheatsheet content ──` and `// ── Handbuch accordion ──` sections). The rest of `Help.tsx` (the main `Help` page component) stays unchanged.

- [ ] **Step 3: Verify the build**

```bash
cd E:/claude/zeiterfassung/praxiszeit
docker-compose build frontend 2>&1 | tail -20
```

Expected: Build succeeds, no TypeScript errors.

- [ ] **Step 4: Smoke-test Help page**

```bash
docker-compose up -d frontend
```

Open http://localhost in the browser, navigate to `/help`. Both tabs (Kurzanleitung, Handbuch) must display content correctly. The download buttons must still work.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocViewer.tsx frontend/src/pages/Help.tsx
git commit -m "refactor: extract doc content from Help.tsx into DocViewer.tsx"
```

---

## Task 3: Create `DocDrawer.tsx`

**Files:**
- Create: `frontend/src/components/DocDrawer.tsx`

- [ ] **Step 1: Create `DocDrawer.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { DocViewerContent } from './DocViewer';

type DocTab = 'cheatsheet' | 'handbuch';

interface DocDrawerProps {
  open: boolean;
  onClose: () => void;
  isAdmin: boolean;
  initialTab?: DocTab;
}

function getDownloadUrl(isAdmin: boolean, tab: DocTab): string {
  if (tab === 'cheatsheet') {
    return isAdmin ? '/help/CHEATSHEET-ADMIN.md' : '/help/CHEATSHEET-MITARBEITER.md';
  }
  return isAdmin ? '/help/HANDBUCH-ADMIN.md' : '/help/HANDBUCH-MITARBEITER.md';
}

export function DocDrawer({ open, onClose, isAdmin, initialTab = 'cheatsheet' }: DocDrawerProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Sync activeTab when initialTab changes (triggered by parent before open)
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Focus management: save trigger element, trap focus inside drawer, restore on close
  const triggerElementRef = useRef<Element | null>(null);

  useEffect(() => {
    if (open) {
      // Save the element that triggered the drawer so we can return focus on close
      triggerElementRef.current = document.activeElement;
    } else {
      // Return focus to the triggering element when drawer closes
      if (triggerElementRef.current && triggerElementRef.current instanceof HTMLElement) {
        triggerElementRef.current.focus();
        triggerElementRef.current = null;
      }
    }
  }, [open]);

  useEffect(() => {
    if (!open || !drawerRef.current) return;
    const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first?.focus();

    function handleTab(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', handleTab);
    return () => document.removeEventListener('keydown', handleTab);
  }, [open]);

  const downloadUrl = getDownloadUrl(isAdmin, activeTab);
  const title = isAdmin ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch';

  return (
    <>
      {/* Overlay */}
      <div
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity duration-300 ${
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer — desktop: right side; mobile: bottom sheet */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Dokumentation"
        className={`
          fixed z-50 bg-white flex flex-col shadow-2xl transition-transform duration-300
          md:inset-y-0 md:right-0 md:w-[70%] md:max-w-2xl
          inset-x-0 bottom-0 h-[80vh] rounded-t-2xl
          md:rounded-none md:h-auto
          ${open
            ? 'md:translate-x-0 translate-y-0'
            : 'md:translate-x-full translate-y-full'
          }
        `}
      >
        {/* Mobile drag handle */}
        <div className="md:hidden w-10 h-1 bg-gray-300 rounded-full mx-auto mt-3 mb-1 flex-shrink-0" />

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <span className="font-semibold text-gray-800 text-sm">📖 {title}</span>
          <div className="flex items-center gap-2">
            <a
              href={downloadUrl}
              download
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <Download size={13} />
              <span>.md</span>
            </a>
            <button
              ref={closeButtonRef}
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              aria-label="Schließen"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <DocViewerContent
            key={initialTab}
            isAdmin={isAdmin}
            initialTab={initialTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify the build**

```bash
docker-compose build frontend 2>&1 | tail -20
```

Expected: No TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DocDrawer.tsx
git commit -m "feat: add DocDrawer component (side drawer + mobile bottom sheet)"
```

---

## Task 4: Create `DocModal.tsx`

**Files:**
- Create: `frontend/src/components/DocModal.tsx`

- [ ] **Step 1: Create `DocModal.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { DocViewerContent } from './DocViewer';

type DocTab = 'cheatsheet' | 'handbuch';

interface DocModalProps {
  open: boolean;
  onClose: () => void;
  initialTab?: DocTab;
}

function getDownloadUrl(tab: DocTab): string {
  return tab === 'cheatsheet'
    ? '/help/CHEATSHEET-MITARBEITER.md'
    : '/help/HANDBUCH-MITARBEITER.md';
}

export function DocModal({ open, onClose, initialTab = 'cheatsheet' }: DocModalProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);
  const modalRef = useRef<HTMLDivElement>(null);

  // Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Focus trap
  useEffect(() => {
    if (!open || !modalRef.current) return;
    const focusable = modalRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first?.focus();

    function handleTab(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', handleTab);
    return () => document.removeEventListener('keydown', handleTab);
  }, [open]);

  if (!open) return null;

  const downloadUrl = getDownloadUrl(activeTab);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Dokumentation"
        className="relative z-10 bg-white rounded-xl shadow-2xl w-full max-w-2xl h-[80vh] flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <span className="font-semibold text-gray-800 text-sm">📖 Mitarbeiter-Handbuch</span>
          <div className="flex items-center gap-2">
            <a
              href={downloadUrl}
              download
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <Download size={13} />
              <span>.md</span>
            </a>
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              aria-label="Schließen"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <DocViewerContent
            key={initialTab}
            isAdmin={false}
            initialTab={initialTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the build**

```bash
docker-compose build frontend 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DocModal.tsx
git commit -m "feat: add DocModal component for Login page"
```

---

## Task 5: Wire up `Layout.tsx`

**Files:**
- Modify: `frontend/src/components/Layout.tsx`

Current code to replace (around line 263–291):
```tsx
{/* Handbuch-Downloads */}
<div className="mb-2 flex flex-col gap-1">
  <a href={...} download ...>Cheat-Sheet</a>
  <a href={...} download ...>...</a>
</div>
```

- [ ] **Step 1: Add import**

At the top of `Layout.tsx`, add:
```tsx
import { DocDrawer } from './DocDrawer';
```

Note: `BookOpen`, `FileText`, and `useState` are already imported in `Layout.tsx` — no changes needed there.

- [ ] **Step 2: Add drawer state**

Inside the `Layout` function, before the `return`, add:
```tsx
const [drawerOpen, setDrawerOpen] = useState(false);
const [drawerTab, setDrawerTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');
```

Make sure `useState` is imported from `'react'` (it should already be).

- [ ] **Step 3: Replace the download links**

Find the `{/* Handbuch-Downloads */}` block and replace with:
```tsx
{/* Handbuch-Downloads */}
<div className="mb-2 flex flex-col gap-1">
  <button
    onClick={() => { setDrawerTab('cheatsheet'); setDrawerOpen(true); }}
    className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors w-full text-left"
  >
    <BookOpen size={13} />
    <span>Cheat-Sheet</span>
  </button>
  <button
    onClick={() => { setDrawerTab('handbuch'); setDrawerOpen(true); }}
    className="flex items-center space-x-2 px-4 py-1.5 text-xs text-gray-500 hover:text-primary hover:bg-gray-50 rounded-lg transition-colors w-full text-left"
  >
    <FileText size={13} />
    <span>{user?.role === 'admin' ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch'}</span>
  </button>
</div>
```

- [ ] **Step 4: Mount DocDrawer**

Just before the closing `</div>` of the Layout's outermost element (or at the very end of the `return` statement, after all other JSX), add:
```tsx
<DocDrawer
  open={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  isAdmin={user?.role === 'admin'}
  initialTab={drawerTab}
/>
```

`DocDrawer` must always be in the DOM (not conditional) so its close animation can play.

- [ ] **Step 5: Verify the build**

```bash
docker-compose build frontend 2>&1 | tail -20
```

- [ ] **Step 6: Test in browser**

Open http://localhost, log in as `admin` / `Admin2025!`:
- Click "Cheat-Sheet" → Drawer opens with Kurzanleitung tab active, shows Admin content
- Click "Admin-Handbuch" → Drawer opens with Handbuch tab active
- Click ✕ → Drawer closes with slide-out animation
- Click backdrop → Drawer closes
- Press Escape → Drawer closes
- Download link downloads the correct `.md` file for the active tab

Log in as `manuel@klotz-roedig.de`:
- "Mitarbeiter-Handbuch" appears (not "Admin-Handbuch")
- Content is Mitarbeiter-variant

Resize to mobile (< 768px): Drawer becomes bottom sheet.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat: open DocDrawer from sidebar links instead of downloading"
```

---

## Task 6: Wire up `Login.tsx`

**Files:**
- Modify: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Add import**

At the top of `Login.tsx`, add:
```tsx
import { DocModal } from '../components/DocModal';
```

- [ ] **Step 2: Add modal state**

Inside the `Login` function, before the `return`, add:
```tsx
const [modalOpen, setModalOpen] = useState(false);
const [modalTab, setModalTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');
```

Make sure `useState` is imported from `'react'`.

- [ ] **Step 3: Replace the download links**

Find this block (around line 151–168):
```tsx
<a href="/help/HANDBUCH-MITARBEITER.md" download ...>Mitarbeiter-Handbuch</a>
<span className="text-gray-300">·</span>
<a href="/help/CHEATSHEET-MITARBEITER.md" download ...>Cheat-Sheet</a>
```

Replace with:
```tsx
<button
  onClick={() => { setModalTab('handbuch'); setModalOpen(true); }}
  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-primary transition-colors"
>
  <FileText size={13} />
  Mitarbeiter-Handbuch
</button>
<span className="text-gray-300">·</span>
<button
  onClick={() => { setModalTab('cheatsheet'); setModalOpen(true); }}
  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-primary transition-colors"
>
  <FileText size={13} />
  Cheat-Sheet
</button>
```

- [ ] **Step 4: Mount DocModal**

At the end of the `Login` component's `return`, just before the final closing tag, add:
```tsx
<DocModal
  open={modalOpen}
  onClose={() => setModalOpen(false)}
  initialTab={modalTab}
/>
```

- [ ] **Step 5: Remove unused `FileText` import if needed**

`FileText` is still used (now in the buttons), so no import change needed.

- [ ] **Step 6: Verify the build**

```bash
docker-compose build frontend 2>&1 | tail -20
```

- [ ] **Step 7: Test in browser**

Open http://localhost (logout first or open in incognito):
- Click "Mitarbeiter-Handbuch" → Modal opens with Handbuch tab
- Click "Cheat-Sheet" → Modal opens with Kurzanleitung tab
- Click ✕ → closes
- Click backdrop → closes
- Press Escape → closes
- Download link works

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat: open DocModal from Login page doc links"
```

---

## Task 7: Final build + push + PR

- [ ] **Step 1: Full rebuild and smoke test**

```bash
cd E:/claude/zeiterfassung/praxiszeit
docker-compose build frontend && docker-compose up -d frontend
```

Run through all test scenarios:
- Sidebar: Cheat-Sheet + Handbuch links (admin and employee)
- Login: both modal links
- `/help` page still works (both tabs, download buttons)
- Mobile (DevTools, 375px): bottom sheet behaviour

- [ ] **Step 2: Push and open PR**

```bash
git push
gh pr create --title "feat: in-app DocDrawer & DocModal for Handbuch/Cheatsheet" \
  --body "Replaces download links with an in-app Side Drawer (desktop) / Bottom Sheet (mobile) and Login Modal. No new dependencies — reuses existing Help.tsx content components."
```
