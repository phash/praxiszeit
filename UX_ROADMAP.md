# UX/UI Optimierungs-Roadmap – PraxisZeit

**Erstellt:** 09.02.2026
**Basis:** Umfassende UX/UI-Analyse durch ux-ui-specialist Agent
**Ziel:** Mobile-First Transformation und professionelle User Experience

---

## 📊 Übersicht

| Phase | Fokus | Dauer | Aufwand | Impact |
|-------|-------|-------|---------|--------|
| **Phase 0** | Foundation & Shared Components | 3-5 Tage | Mittel | Hoch (ermöglicht alles andere) |
| **Phase 1** | Mobile Navigation & Critical Fixes | 2-3 Tage | Mittel | **Kritisch** |
| **Phase 2** | Responsive Tables & Cards | 4-6 Tage | Hoch | **Kritisch** |
| **Phase 3** | Accessibility & A11y Compliance | 2-3 Tage | Niedrig | Hoch |
| **Phase 4** | Calendar & Date Navigation | 3-4 Tage | Mittel | Hoch |
| **Phase 5** | Polish & Nice-to-haves | 3-5 Tage | Mittel | Mittel |

**Gesamt:** ca. 17-26 Arbeitstage (3-5 Wochen)

---

## Phase 0: Foundation & Shared Components 🏗️

**Warum zuerst?** Vermeidet Duplikation in späteren Phasen, reduziert Codebase um ~30%

### 0.1 Toast-Notification-System (PRIO 1)

**Aufwand:** 4-6h
**Dateien:**
- Neu: `frontend/src/components/Toast.tsx`
- Neu: `frontend/src/components/ToastProvider.tsx`
- Anpassen: `frontend/src/App.tsx` (Provider einbinden)

**Umsetzung:**
```tsx
// Toast.tsx mit Kontext API
// ToastProvider wrapper in App.tsx
// useToast() Hook für alle Komponenten
```

**Ersetzt:** 15+ `alert()` und `confirm()` Aufrufe in:
- `TimeTracking.tsx` (4 Stellen)
- `AbsenceCalendarPage.tsx` (3 Stellen)
- `admin/Users.tsx` (8 Stellen)

**Testing:** Browser-Tests für Auto-Dismiss, manuelle Schließung, Stacking

---

### 0.2 Shared Button Component

**Aufwand:** 2-3h
**Datei:** `frontend/src/components/Button.tsx`

```tsx
interface ButtonProps {
  variant: 'primary' | 'secondary' | 'danger' | 'ghost';
  size: 'sm' | 'md' | 'lg';
  icon?: LucideIcon;
  children: React.ReactNode;
  // ... weitere Props
}
```

**Varianten:**
- `primary`: Blau, für Hauptaktionen (Speichern, Erstellen)
- `secondary`: Grau, für sekundäre Aktionen (Abbrechen)
- `danger`: Rot, für destruktive Aktionen (Löschen)
- `ghost`: Transparent, für Icon-Buttons

**Reduziert Code in:** Alle 10 Komponenten mit Buttons

---

### 0.3 Shared Form Components

**Aufwand:** 4-5h
**Dateien:**
- `frontend/src/components/FormInput.tsx`
- `frontend/src/components/FormSelect.tsx`
- `frontend/src/components/FormTextarea.tsx`

**Features:**
- Konsistentes Styling
- Error-States mit Validierungsnachrichten
- Label + optional Required-Marker
- Accessibility-Attribute (aria-invalid, aria-describedby)

**Reduziert Code in:**
- `TimeTracking.tsx`
- `AbsenceCalendarPage.tsx`
- `admin/Users.tsx`
- `Profile.tsx`

---

### 0.4 Loading States (Spinner & Skeleton)

**Aufwand:** 2-3h
**Dateien:**
- `frontend/src/components/LoadingSpinner.tsx`
- `frontend/src/components/TableSkeleton.tsx`

**Ersetzt:** Alle "Lade Daten..."-Texte mit professionellen Animationen

---

### 0.5 Shared Constants

**Aufwand:** 1h
**Datei:** `frontend/src/constants/absenceTypes.ts`

```tsx
export const ABSENCE_TYPE_LABELS: Record<string, string> = { ... };
export const ABSENCE_TYPE_STYLES: Record<string, string> = { ... };
```

**Entfernt Duplikation aus:**
- `Dashboard.tsx`
- `AbsenceCalendarPage.tsx`
- `admin/AdminDashboard.tsx`

---

### 0.6 Badge Component

**Aufwand:** 1-2h
**Datei:** `frontend/src/components/Badge.tsx`

```tsx
<Badge variant="vacation">Urlaub</Badge>
<Badge variant="sick">Krank</Badge>
```

---

**✅ Phase 0 Checkpoint:**
- [ ] Toast-System funktioniert in allen Browsern
- [ ] Shared Components dokumentiert (Storybook optional)
- [ ] Alle alten `alert()`-Aufrufe durch `useToast()` ersetzt
- [ ] Code-Review: Konsistenz geprüft

---

## Phase 1: Mobile Navigation & Critical Fixes 📱

**Warum jetzt?** Blockiert aktuell jegliche Mobile-Nutzung

### 1.1 Responsive Layout mit Hamburger-Menü (K1 - KRITISCH)

**Aufwand:** 6-8h
**Datei:** `frontend/src/components/Layout.tsx`

**Implementierung:**
1. State für `sidebarOpen` (useState)
2. Mobile Header mit Hamburger-Button (nur `< lg`)
3. Sidebar als Overlay mit Transform-Animation
4. Backdrop (schwarzer Overlay) für Click-to-Close
5. Escape-Key-Handling

**Breakpoints:**
- `< 1024px` (lg): Hamburger-Menü
- `≥ 1024px` (lg): Sidebar permanent sichtbar

**Code-Struktur:**
```tsx
{/* Backdrop */}
{sidebarOpen && <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" />}

{/* Sidebar */}
<aside className={`
  fixed lg:relative
  transform transition-transform
  ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
`}>

{/* Mobile Header */}
<div className="lg:hidden sticky top-0">
  <button onClick={() => setSidebarOpen(true)}>
    <Menu size={24} />
  </button>
</div>
```

**Testing:**
- [ ] iPhone SE (375px): Sidebar klappt ein, Header sichtbar
- [ ] iPad (768px): Hamburger funktioniert
- [ ] Desktop (1440px): Sidebar immer sichtbar, kein Hamburger
- [ ] Escape-Key schließt Sidebar
- [ ] Click außerhalb schließt Sidebar

---

### 1.2 Icon-Buttons Accessibility (K3 - KRITISCH)

**Aufwand:** 2-3h
**Dateien:** Alle mit Icon-Buttons

**Änderungen:**
```tsx
// Vorher:
<button onClick={handleEdit}>
  <Edit2 size={16} />
</button>

// Nachher:
<button
  onClick={handleEdit}
  aria-label="Eintrag vom 15.01.2026 bearbeiten"
  className="p-2 rounded-lg hover:bg-gray-100"
>
  <Edit2 size={16} />
</button>
```

**Betroffene Dateien:**
- `TimeTracking.tsx`: Edit, Delete (2x)
- `admin/Users.tsx`: Edit, Delete, Key, UserX (4x)
- `admin/AdminDashboard.tsx`: Edit (1x)
- `AbsenceCalendarPage.tsx`: Kalender-Navigation (2x)

**Touch-Optimierung:** Alle Buttons mindestens `p-2` (44x44px Tap-Target)

---

### 1.3 Submit-Button Position Fix (H2)

**Aufwand:** 30min
**Datei:** `frontend/src/pages/AbsenceCalendarPage.tsx`

**Änderung:**
```tsx
<form className="space-y-4">
  {/* Alle Felder */}

  {/* Button IMMER unten, außerhalb des Grids */}
  <div className="flex justify-end pt-2">
    <button type="submit">Speichern</button>
  </div>
</form>
```

---

**✅ Phase 1 Checkpoint:**
- [ ] Mobile Navigation funktioniert auf iPhone/Android
- [ ] Alle Icon-Buttons haben aria-labels
- [ ] Lighthouse Accessibility Score > 90
- [ ] Submit-Button wandert nicht mehr

---

## Phase 2: Responsive Tables & Cards 📊

**Warum jetzt?** Daten aktuell unleserlich auf Mobile

### 2.1 TimeTracking.tsx – Responsive Table/Cards (K2)

**Aufwand:** 4-5h
**Datei:** `frontend/src/pages/TimeTracking.tsx`

**Strategie:**
- Desktop (`md:` und größer): Vollständige Tabelle
- Mobile (`< md`): Card-Layout mit wichtigsten Infos

**Implementierung:**
```tsx
{/* Desktop Table */}
<div className="hidden md:block overflow-x-auto">
  <table className="w-full">
    {/* 8 Spalten wie bisher */}
  </table>
</div>

{/* Mobile Cards */}
<div className="md:hidden space-y-3">
  {entries.map(entry => (
    <div className="bg-white border rounded-lg p-4">
      <div className="flex justify-between mb-2">
        <div>
          <p className="font-medium">{formatDate(entry.date)}</p>
          <p className="text-sm text-gray-500">{weekday}</p>
        </div>
        <div className="flex space-x-2">
          <button aria-label="Bearbeiten"><Edit2 size={18} /></button>
          <button aria-label="Löschen"><Trash2 size={18} /></button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Von</span>
          <p className="font-medium">{entry.start_time}</p>
        </div>
        <div>
          <span className="text-gray-500">Bis</span>
          <p className="font-medium">{entry.end_time}</p>
        </div>
        <div>
          <span className="text-gray-500">Netto</span>
          <p className="font-bold">{entry.net_hours.toFixed(2)} h</p>
        </div>
      </div>
    </div>
  ))}
</div>
```

**Testing:** iPhone, iPad, Desktop – alle Daten lesbar

---

### 2.2 admin/Users.tsx – Responsive Table (K2)

**Aufwand:** 4-5h
**Datei:** `frontend/src/pages/admin/Users.tsx`

**Mobile Cards zeigen:**
- Name + Email
- Aktiv/Inaktiv Badge
- Aktions-Buttons (Edit, Delete, Reset Password, Deactivate)

**Hidden in Mobile:**
- Mitarbeiter-ID
- Soll-Stunden
- Urlaubstage

→ Diese Infos in Detail-Modal verschieben (kommt in Phase 5)

---

### 2.3 admin/AdminDashboard.tsx – Responsive Tables (K2)

**Aufwand:** 5-6h
**Datei:** `frontend/src/pages/admin/AdminDashboard.tsx`

**Zwei Tabellen:**
1. **Mitarbeiter-Übersicht** (Zeile 216+)
2. **Abwesenheiten-Jahresübersicht** (Zeile 503+)

**Mobile Strategy:**
- Mitarbeiter-Tabelle: Cards mit Click-to-Detail (ChevronRight Icon)
- Jahresübersicht: Horizontal scrollbar beibehalten, aber kompakter

---

### 2.4 AbsenceCalendarPage.tsx – Table Cards

**Aufwand:** 2-3h
**Datei:** `frontend/src/pages/AbsenceCalendarPage.tsx`

Kleinere Tabelle (nur eigene Abwesenheiten), einfacher umzubauen.

---

**✅ Phase 2 Checkpoint:**
- [ ] Alle 4 Tabellen responsive getestet (375px, 768px, 1440px)
- [ ] Keine horizontalen Scrollbars mehr nötig auf Mobile
- [ ] Touch-Targets groß genug (min 44x44px)
- [ ] Loading-States mit Skeleton für Cards

---

## Phase 3: Accessibility & A11y Compliance ♿

**Warum jetzt?** Grundlegende Standards erfüllen

### 3.1 Modal Accessibility

**Aufwand:** 3-4h
**Dateien:**
- `admin/AdminDashboard.tsx` (Employee Detail Modal)
- `admin/Users.tsx` (Create/Edit User Modal)

**Implementierung:**
1. `role="dialog"` + `aria-modal="true"`
2. `aria-labelledby` für Modal-Titel
3. Focus-Trap (Tab zirkuliert im Modal)
4. Escape-Key schließt Modal
5. Focus auf ersten Input beim Öffnen
6. Focus zurück auf Trigger-Element beim Schließen

**Bibliothek-Option:** `@headlessui/react` (optional, oder manuell)

---

### 3.2 Form Validation & Error Messages

**Aufwand:** 2-3h

**Standards:**
- `aria-invalid="true"` bei Fehlern
- `aria-describedby` verknüpft mit Error-Message
- Error-Message mit `role="alert"` für Screen Reader

**Beispiel:**
```tsx
<input
  aria-invalid={errors.email ? "true" : "false"}
  aria-describedby={errors.email ? "email-error" : undefined}
/>
{errors.email && (
  <p id="email-error" role="alert" className="text-sm text-red-600">
    {errors.email}
  </p>
)}
```

---

### 3.3 Skip-to-Content Link

**Aufwand:** 30min
**Datei:** `frontend/src/components/Layout.tsx`

```tsx
<a
  href="#main-content"
  className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-primary text-white px-4 py-2 rounded-lg z-[100]"
>
  Zum Inhalt springen
</a>

{/* Main Content */}
<main id="main-content" className="flex-1">
  <Outlet />
</main>
```

---

### 3.4 Keyboard Navigation Testing

**Aufwand:** 2h (manuell)

**Checkliste:**
- [ ] Gesamte App mit Tab-Taste navigierbar
- [ ] Focus-Reihenfolge logisch
- [ ] Focus-Indicator sichtbar (nicht `outline: none` ohne Alternative)
- [ ] Modals mit Escape schließbar
- [ ] Dropdowns mit Pfeiltasten bedienbar

---

**✅ Phase 3 Checkpoint:**
- [ ] Lighthouse Accessibility Score ≥ 95
- [ ] WAVE-Tool zeigt keine Errors
- [ ] Screenreader-Test mit NVDA/JAWS (Windows) oder VoiceOver (Mac)

---

## Phase 4: Calendar & Date Navigation 📅

### 4.1 Custom MonthSelector Component (M2)

**Aufwand:** 3-4h
**Datei:** `frontend/src/components/MonthSelector.tsx`

**Features:**
- Pfeil-Buttons (← →) für prev/next Monat
- "Heute"-Button (nur sichtbar wenn nicht aktueller Monat)
- Monat/Jahr-Anzeige (klickbar für Dropdown? Optional)

**Ersetzt `<input type="month">` in:**
- `TimeTracking.tsx`
- `AbsenceCalendarPage.tsx`
- `admin/AdminDashboard.tsx`

---

### 4.2 Responsive Calendar Grid (H3)

**Aufwand:** 5-6h
**Dateien:**
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/AbsenceCalendarPage.tsx`

**Desktop (≥ 640px):**
```tsx
<div className="hidden sm:grid grid-cols-7 gap-2">
  {/* Kalender-Grid */}
</div>
```

**Mobile (< 640px):**
```tsx
<div className="sm:hidden space-y-2">
  {daysWithEntries.map(day => (
    <div className="border rounded-lg p-3">
      <p className="font-medium">{format(day, 'EEEE, dd.MM.')}</p>
      {entries.map(entry => (
        <div className={`text-sm px-2 py-1 rounded ${colors[entry.type]}`}>
          {entry.user_name} – {typeLabels[entry.type]}
        </div>
      ))}
    </div>
  ))}
</div>
```

---

### 4.3 Feiertage im Kalender anzeigen (N2)

**Aufwand:** 2-3h

**Backend:** Endpoint `/api/holidays?year=2026&month=1`
**Frontend:** Graue Badges im Kalender-Grid für Feiertage

---

**✅ Phase 4 Checkpoint:**
- [ ] MonthSelector funktioniert in allen 3 Seiten
- [ ] Kalender auf iPhone lesbar (Listenansicht)
- [ ] Kalender auf Desktop wie vorher (Grid)
- [ ] Feiertage sichtbar

---

## Phase 5: Polish & Nice-to-haves ✨

### 5.1 Sortierung & Filterung in Tabellen (N1)

**Aufwand:** 6-8h

**Features:**
- Klickbare Table-Header für Sortierung (↑↓)
- Filter-Input über Tabelle (Name, Email suchen)
- Optional: Dropdown-Filter für Status (Aktiv/Inaktiv)

**Library-Option:** `@tanstack/react-table` (empfohlen für komplexe Tables)

---

### 5.2 Passwort-Reset Modal statt Alert (M4)

**Aufwand:** 2-3h
**Datei:** `frontend/src/pages/admin/Users.tsx`

**Ersetzt:**
```tsx
alert(`Neues Passwort: ${response.data.temporary_password}`);
```

**Durch:**
```tsx
<Modal title="Temporäres Passwort erstellt">
  <div className="bg-gray-50 p-4 rounded-lg font-mono text-lg">
    {temporaryPassword}
  </div>
  <button onClick={() => navigator.clipboard.writeText(temporaryPassword)}>
    <Copy size={16} /> In Zwischenablage kopieren
  </button>
  <p className="text-sm text-red-600 mt-2">
    ⚠️ Dieses Passwort wird nur einmal angezeigt!
  </p>
</Modal>
```

---

### 5.3 Verbesserte Detail-Ansichten

**Aufwand:** 4-5h

**AdminDashboard – Employee Details:**
- Aktuell: Modal bei Klick auf Tabellenzeile
- Verbesserung: ChevronRight Icon am Zeilenende als visueller Hinweis (M3)
- Zusätzlich: Mehr Details im Modal (Mitarbeiter-ID, Urlaubstage, etc.)

---

### 5.4 Color Consistency Fix (N4)

**Aufwand:** 30min

**Problem:** `CLAUDE.md` sagt `#3b82f6` (blue-500), `tailwind.config.js` nutzt `#2563EB` (blue-600)

**Lösung:** Entscheiden und vereinheitlichen (Empfehlung: blue-600 beibehalten)

---

### 5.5 Inklusivere Sprache (M5)

**Aufwand:** 1h (Find & Replace)

**Ändern:**
- "Mitarbeiterin" → "Mitarbeitende" oder "Mitarbeiter:in"
- "Neue Mitarbeiterin" → "Neue:r Mitarbeiter:in"

**Betrifft:** `Users.tsx`, `AdminDashboard.tsx`

---

### 5.6 Reports-Button Consistency (N5)

**Aufwand:** 15min
**Datei:** `frontend/src/pages/admin/Reports.tsx`

**Ändern:**
```tsx
// Von:
className="bg-green-600 hover:bg-green-700"

// Zu:
className="bg-primary hover:bg-primary-dark"
```

Falls Farb-Differenzierung gewünscht: Sekundären Button-Stil nutzen statt grün.

---

**✅ Phase 5 Checkpoint:**
- [ ] Tabellen sortierbar
- [ ] Passwort-Reset UX verbessert
- [ ] Alle Farbinkonsistenzen behoben
- [ ] Sprache inklusiv

---

## 🚀 Deployment-Checkliste

Nach jeder Phase vor Deployment:

1. **Code Review:**
   - [ ] TypeScript-Fehler behoben (`npm run build`)
   - [ ] ESLint-Warnungen geprüft
   - [ ] Keine Console-Logs im Code

2. **Testing:**
   - [ ] Manuelle Tests auf Chrome, Firefox, Safari
   - [ ] Mobile Tests: iPhone (Safari), Android (Chrome)
   - [ ] Tablet Test: iPad
   - [ ] Lighthouse Score > 90 (Performance, Accessibility, Best Practices)

3. **Browser-Kompatibilität:**
   - [ ] Chrome 120+
   - [ ] Firefox 120+
   - [ ] Safari 17+
   - [ ] Edge 120+

4. **Responsive Breakpoints:**
   - [ ] 375px (iPhone SE)
   - [ ] 768px (iPad Portrait)
   - [ ] 1024px (iPad Landscape / Small Desktop)
   - [ ] 1440px (Desktop)

5. **Git:**
   - [ ] Feature-Branch mit aussagekräftigem Namen
   - [ ] Commit-Messages nach Convention
   - [ ] Pull Request mit Screenshots (vorher/nachher)

---

## 📈 Success Metrics

**Vor Optimierung:**
- Mobile Navigation: ❌ Nicht nutzbar
- Lighthouse Accessibility: ~75
- Mobile Tabellen: ❌ Unleserlich
- Alert-Popups: 15+
- Code-Duplikation: ~30%

**Nach Phase 1-2 (MVP):**
- Mobile Navigation: ✅ Funktional
- Lighthouse Accessibility: 90+
- Mobile Tabellen: ✅ Card-Layout
- Alert-Popups: 0 (Toast-System)

**Nach Phase 5 (Komplett):**
- Lighthouse Accessibility: 95+
- Code-Duplikation: < 10%
- User-Testing Score: > 4/5
- Mobile Conversion: Messbar (falls Analytics vorhanden)

---

## 🛠️ Technologie-Stack für neue Komponenten

- **Styling:** Tailwind CSS (bereits vorhanden)
- **Icons:** Lucide-react (bereits vorhanden)
- **Animationen:** Tailwind CSS `animate-*` + CSS Transitions
- **Date-Handling:** date-fns (bereits vorhanden)
- **State Management:** React useState/useContext (Toast), Zustand (Auth)
- **Optional:**
  - `@headlessui/react` für Modals/Dropdowns (empfohlen für A11y)
  - `@tanstack/react-table` für sortierbare Tables

---

## 📝 Notizen

### Quick Wins (falls Zeit knapp):
1. **Phase 0.1 + 1.2:** Toast-System + Icon aria-labels (6h, großer Impact)
2. **Phase 1.1:** Mobile Navigation (8h, kritisch)
3. **Phase 2.1:** Nur TimeTracking responsive (5h, meistgenutzte Seite)

### Langfristige Verbesserungen (Post-Launch):
- Offline-Modus mit Service Worker
- Push-Notifications für Genehmigungen
- Dark Mode
- Bulk-Actions in Admin-Tabellen
- Export-Funktionen (CSV, PDF)

---

**Autor:** Claude Sonnet 4.5 (ux-ui-specialist)
**Letzte Aktualisierung:** 09.02.2026
