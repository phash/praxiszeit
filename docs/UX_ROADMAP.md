# UX/UI Optimierungs-Roadmap – PraxisZeit

**Erstellt:** 09.02.2026
**Zuletzt aktualisiert:** 28.02.2026
**Status:** ✅ **Alle Phasen abgeschlossen**

---

## 📊 Übersicht

| Phase | Fokus | Status | Commit |
|-------|-------|--------|--------|
| **Phase 0** | Foundation & Shared Components | ✅ Abgeschlossen | Feb 2026 |
| **Phase 1** | Mobile Navigation & Critical Fixes | ✅ Abgeschlossen | Feb 2026 |
| **Phase 2** | Responsive Tables & Cards | ✅ Abgeschlossen | Feb 2026 |
| **Phase 3** | Accessibility & A11y Compliance | ✅ Abgeschlossen | `26aaef2` |
| **Phase 4** | Calendar & Date Navigation | ✅ Abgeschlossen | Feb 2026 |
| **Phase 5** | Polish & Nice-to-haves | ✅ Abgeschlossen | `7750076` |

---

## ✅ Phase 0: Foundation & Shared Components

**Abgeschlossen:** Februar 2026

### Umgesetzte Komponenten

| Komponente | Datei | Beschreibung |
|-----------|-------|--------------|
| Toast-System | `contexts/ToastContext.tsx` | `useToast()` Hook – success/error/info/warning |
| ConfirmDialog | `components/ConfirmDialog.tsx` | Ersetzt native `confirm()` mit `useConfirm()` Hook |
| Button | `components/Button.tsx` | Varianten: primary, secondary, danger, ghost |
| Badge | `components/Badge.tsx` | Status-Badges mit Farbcodierung |
| FormInput | `components/FormInput.tsx` | Formular-Input mit Label + Validation |
| FormSelect | `components/FormSelect.tsx` | Formular-Select mit Label |
| FormTextarea | `components/FormTextarea.tsx` | Formular-Textarea mit Label |
| LoadingSpinner | `components/LoadingSpinner.tsx` | Animierter Spinner mit optionalem Text |
| TableSkeleton | `components/TableSkeleton.tsx` | Pulse-Skeleton für Tabellen |
| MonthSelector | `components/MonthSelector.tsx` | Monats-Navigation mit Prev/Next/Heute |

**Alle `alert()`-Aufrufe** (15+) durch Toast-Notifications und ConfirmDialog ersetzt.

---

## ✅ Phase 1: Mobile Navigation & Critical Fixes

**Abgeschlossen:** Februar 2026

### Umgesetzt

- **Hamburger-Menü** in `Layout.tsx`: Sidebar als Overlay auf Mobile (`< lg`)
- **Backdrop** mit Click-to-Close
- **Escape-Key** schließt Sidebar
- **Route-Change** schließt Sidebar automatisch
- **aria-label** auf allen Menü-Buttons
- **Skip-to-Content Link** (`#main-content`) für Keyboard-Navigation

---

## ✅ Phase 2: Responsive Tables & Cards

**Abgeschlossen:** Februar 2026

### Umgesetzte Card-Layouts (Mobile `< md`/`< lg`)

| Seite | Desktop | Mobile |
|-------|---------|--------|
| `TimeTracking.tsx` | Tabelle (8 Spalten) | Cards mit Edit/Delete |
| `admin/Users.tsx` | Tabelle (6 Spalten) | Cards mit Aktions-Buttons |
| `admin/AdminDashboard.tsx` | Tabelle (9 Spalten) | Cards mit Saldo-Übersicht |
| `AbsenceCalendarPage.tsx` | Tabelle | Cards |

Alle Card-Layouts mit **Touch-optimierten Tap-Targets** (min. 44×44px).

---

## ✅ Phase 3: Accessibility & A11y Compliance

**Abgeschlossen:** 28.02.2026 | Commit: `26aaef2`

### Umgesetzte Maßnahmen

| Maßnahme | Dateien | Details |
|---------|---------|---------|
| FocusTrap + alertdialog | `ConfirmDialog.tsx` | `role="alertdialog"`, `aria-modal`, `aria-labelledby/describedby`, `autoFocus` Cancel |
| aria-hidden Bugfix | `AdminDashboard.tsx`, `Users.tsx` | `aria-hidden="true"` von Modal-Backdrops entfernt (Dialog war Kind) |
| Keyboard-Navigation Rows | `AdminDashboard.tsx` | `role="button"`, `tabIndex`, `onKeyDown` (Enter/Space) auf clickbaren Zeilen |
| Inline-Form Labels | `AdminDashboard.tsx` | `aria-label` auf allen 5 unlabeled Inputs im Edit-Formular |
| Icon-Button aria-labels | `AdminDashboard.tsx` | Edit2/Trash2 von `title` auf `aria-label` mit Datum |
| Search/Year Labels | `AdminDashboard.tsx` | `sr-only <label>` + `htmlFor`/`id` |
| Form htmlFor/id | `Users.tsx` | Alle 9+ Felder in showForm programmatisch verknüpft + `autoFocus` |
| Password-Error | `Users.tsx` | `role="alert"` + `aria-describedby`/`aria-invalid` |
| Datum/Notiz Labels | `TimeTracking.tsx` | `htmlFor`/`id` ergänzt |

---

## ✅ Phase 4: Calendar & Date Navigation

**Abgeschlossen:** Februar 2026

### Umgesetzt

- **MonthSelector-Komponente** (`components/MonthSelector.tsx`):
  - Pfeil-Buttons ← → für Prev/Next Monat
  - „Heute"-Button (nur sichtbar wenn nicht aktueller Monat)
  - Eingesetzt in: `TimeTracking.tsx`, `AbsenceCalendarPage.tsx`, `AdminDashboard.tsx`, `AuditLog.tsx`

---

## ✅ Phase 5: Polish & Nice-to-haves

**Abgeschlossen:** 28.02.2026 | Commit: `7750076`

### Umgesetzte Maßnahmen

#### Sortierung & Filterung (bereits in Phase 0-2 eingebaut)

| Seite | Sortierung | Filter |
|-------|-----------|--------|
| `admin/AdminDashboard.tsx` | Alle Spalten (↑↓) | Name-Suche |
| `admin/Users.tsx` | Alle Spalten (↑↓) | Name/Username-Suche, Aktiv/Inaktiv-Filter |

#### Passwort-Modal (ersetzt Alert)

`admin/Users.tsx`: Admin setzt Passwort über Modal mit Validierung statt `alert()`.

#### Farbkonsistenz

Tailwind-Config verwendet durchgehend `#2563EB` (blue-600) als `bg-primary`. Alle Buttons konsistent.

#### Inklusivere Sprache

`Mitarbeiter:in` / `Mitarbeitende` in allen Seiten einheitlich verwendet.

#### LoadingSpinner überall

Alle verbleibenden "Lade..."-Texte durch animierten `<LoadingSpinner>` ersetzt:

| Datei | Ersetzte Texte |
|-------|----------------|
| `Dashboard.tsx` | „Lade Dashboard..." |
| `TimeTracking.tsx` | „Lade Einträge..." (Desktop-Tabelle) |
| `AdminDashboard.tsx` | 5× „Lade Daten..." (Monatsber. Desktop+Mobile, Jahresübersicht Desktop+Mobile, Modal) |
| `AuditLog.tsx` | „Lade Protokoll..." (Desktop + Mobile) |
| `admin/ChangeRequests.tsx` | „Lade Anträge..." |
| `ChangeRequests.tsx` | „Lade Anträge..." |

---

## 📈 Ergebnisse

| Metrik | Vorher | Nachher |
|--------|--------|---------|
| Mobile Navigation | ❌ Nicht nutzbar | ✅ Vollständig responsive |
| Alert-Popups | 15+ | 0 (Toast + ConfirmDialog) |
| Accessibility | Grundlegend | ARIA-konform, FocusTrap, Keyboard-Nav |
| Loading States | „Lade..."-Text | Animierter LoadingSpinner |
| Form-Labels | Teilweise verknüpft | Vollständig `htmlFor`/`id` |
| Mobile Tabellen | Unleserlich | Card-Layouts |

---

## 🛠️ Technologie-Stack

- **Styling:** Tailwind CSS 3 + Custom Theme (`bg-primary`, `bg-background`)
- **Icons:** Lucide-react
- **Modals/FocusTrap:** `focus-trap-react`
- **Date-Handling:** date-fns
- **State:** React useState/useContext (Toast), Zustand (Auth)

---

**Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6**
**Letzte Aktualisierung:** 28.02.2026
