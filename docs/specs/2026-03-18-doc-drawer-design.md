# Design: DocDrawer & DocModal – In-App Dokumentationsanzeige

**Datum:** 2026-03-18
**Status:** Approved
**Scope:** Frontend only

---

## Zusammenfassung

Handbuch- und Cheatsheet-Links in Sidebar (Layout.tsx) und Login-Seite öffnen die Dokumente künftig direkt in der App – als Side Drawer (Desktop) / Bottom Sheet (Mobile) bzw. als zentriertes Modal auf der Login-Seite. Kein Seitenwechsel, kein Download-Dialog.

---

## Kontext & Motivation

Die Markdown-Dateien (`HANDBUCH-MITARBEITER.md`, `HANDBUCH-ADMIN.md`, `CHEATSHEET-MITARBEITER.md`, `CHEATSHEET-ADMIN.md`) liegen bereits unter `frontend/public/help/`. Ihr Inhalt ist zusätzlich als React-Komponenten in `Help.tsx` hardcodiert (`CheatsheetMitarbeiter`, `CheatsheetAdmin`, `handbuchMitarbeiterSections`, `handbuchAdminSections`). Diese Komponenten werden direkt wiederverwendet – kein Markdown-Renderer nötig.

Bisheriges Verhalten: Links hatten `download`-Attribut → Browser-Download-Dialog. Neues Verhalten: Links öffnen Drawer/Modal.

---

## Architektur

### Neue Dateien

| Datei | Zweck |
|-------|-------|
| `frontend/src/components/DocDrawer.tsx` | Side Drawer (Desktop) / Bottom Sheet (Mobile) |
| `frontend/src/components/DocModal.tsx` | Zentriertes Modal für Login-Seite |
| `frontend/src/components/DocViewer.tsx` | Gemeinsamer Inhalt (Tabs + Komponenten), genutzt von beiden |

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `frontend/src/pages/Help.tsx` | Cheatsheet/Handbuch-Komponenten und Accordion nach `DocViewer.tsx` extrahieren; Help.tsx importiert und re-exportiert sie von dort. Die Download-Links in Help.tsx (innerhalb der Tab-Panes) bleiben unverändert — Help.tsx verwaltet seine eigenen Download-URLs wie bisher. |
| `frontend/src/components/Layout.tsx` | Download-Links ersetzen durch Buttons, die `DocDrawer` öffnen |
| `frontend/src/pages/Login.tsx` | Download-Links ersetzen durch Buttons, die `DocModal` öffnen |

---

## Komponenten-Design

### `DocViewer.tsx`

Enthält den gemeinsamen Inhalt — aktuell in Help.tsx hardcodiert:
- `CheatsheetMitarbeiter` (React-Komponente)
- `CheatsheetAdmin` (React-Komponente)
- `handbuchMitarbeiterSections` (AccordionItem[])
- `handbuchAdminSections` (AccordionItem[])
- `Accordion`-Komponente (mit `AccordionItem`-Interface)
- `DocViewerContent`-Komponente (Tab-Logik + Inhalt)

```
Props von DocViewerContent:
  isAdmin: boolean
  initialTab?: 'cheatsheet' | 'handbuch'   // Default: 'cheatsheet'
```

`DocViewerContent` verwaltet den aktiven Tab intern (`useState`). Es rendert:
1. Tab-Leiste: „Kurzanleitung" | „Handbuch"
2. Je nach aktivem Tab: Cheatsheet- oder Handbuch-Inhalt (rollenabhängig via `isAdmin`)

**Download-Button:** `DocViewerContent` rendert **keinen** Download-Button — dieser liegt im Header von `DocDrawer`/`DocModal` und wird dort direkt implementiert. Die Download-URL wird im Header-Code aus `isAdmin` + `activeTab` abgeleitet:

```ts
// Download-URL-Logik (im Header von DocDrawer und DocModal):
const downloadUrl = activeTab === 'cheatsheet'
  ? isAdmin ? '/help/CHEATSHEET-ADMIN.md' : '/help/CHEATSHEET-MITARBEITER.md'
  : isAdmin ? '/help/HANDBUCH-ADMIN.md'   : '/help/HANDBUCH-MITARBEITER.md';
```

Da `DocViewerContent` den aktiven Tab intern verwaltet, teilt es diesen nach oben via Callback-Prop mit:

```
Props von DocViewerContent (vollständig):
  isAdmin: boolean
  initialTab?: 'cheatsheet' | 'handbuch'
  onTabChange?: (tab: 'cheatsheet' | 'handbuch') => void
```

`DocDrawer` und `DocModal` halten den aktiven Tab im eigenen State (gespiegelt via `onTabChange`) um den Download-Link dynamisch zu aktualisieren.

### `DocDrawer.tsx`

```
Props:
  open: boolean
  onClose: () => void
  isAdmin: boolean
  initialTab?: 'cheatsheet' | 'handbuch'
```

**Desktop** (`md:` und größer):
- Positionierung: `fixed inset-y-0 right-0`, Breite `w-[70%] max-w-2xl`, `z-50`
- Hintergrund-Overlay: `fixed inset-0 bg-black/40 z-40`, klickbar zum Schließen
- Animation öffnen: `translate-x-full` → `translate-x-0`, `transition-transform duration-300`
- Animation schließen: `translate-x-0` → `translate-x-full` (Reverse); Komponente bleibt im DOM gemountet, `open`-Prop steuert die CSS-Klasse
- Header: Titel + Download-Button (`<a href={downloadUrl} download>`) + Schließen-Button (✕)
- Body: `<DocViewerContent>` mit `overflow-y-auto h-full`

**Mobile** (unter `md:`):
- Positionierung: `fixed inset-x-0 bottom-0`, Höhe `h-[80vh]`, `z-50`
- Abgerundete obere Ecken: `rounded-t-2xl`
- Drag-Handle: zentrierter grauer Balken oben (`w-10 h-1 bg-gray-300 rounded-full mx-auto mt-2 mb-3`)
- Animation öffnen: `translate-y-full` → `translate-y-0`
- Animation schließen: Reverse (`translate-y-0` → `translate-y-full`)
- Gleicher Header + Body wie Desktop

**Fokus-Management:**
- `role="dialog"`, `aria-modal="true"`, `aria-label="Dokumentation"`
- Escape-Taste schließt (`useEffect` mit `keydown`-Listener auf `document`, nur wenn `open`)
- Focus-Trap: hand-rolled mit `useEffect` — beim Öffnen alle fokussierbaren Elemente im Drawer sammeln via `querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')`, Tab/Shift+Tab innerhalb halten. Kein externes Package.
- Beim Öffnen: Fokus auf erstes fokussierbares Element im Drawer setzen
- Beim Schließen: Fokus auf das auslösende Element zurücksetzen (via `ref` auf den Button in Layout.tsx)

### `DocModal.tsx`

```
Props:
  open: boolean
  onClose: () => void
  initialTab?: 'cheatsheet' | 'handbuch'
```

- Rendert intern immer `isAdmin={false}` (Login-Seite hat keinen eingeloggten User; Mitarbeiter-Inhalte werden gezeigt — dieses Verhalten ist bewusst und permanent, da Admins sich zuerst einloggen müssen)
- Positionierung: `fixed inset-0 flex items-center justify-center z-50`
- Overlay: `fixed inset-0 bg-black/40 z-40`, klickbar zum Schließen
- Modal: `w-[90vw] max-w-2xl h-[80vh] rounded-xl shadow-2xl bg-white flex flex-col`
- Header: identisch zu DocDrawer (Titel, Download-Link, ✕)
- Body: `<DocViewerContent isAdmin={false}>` mit `overflow-y-auto flex-1`
- Animation: `opacity-0 scale-95` → `opacity-100 scale-100`, `transition duration-200`
- **Fokus-Management:** identisch zu DocDrawer (`role="dialog"`, `aria-modal="true"`, `aria-label="Dokumentation"`, Escape-Listener, Focus-Trap, Fokus-Rückgabe)

---

## Verhalten der Links

### Layout.tsx (Sidebar)

Aktuell:
```tsx
<a href="/help/CHEATSHEET-MITARBEITER.md" download>Cheat-Sheet</a>
<a href="/help/HANDBUCH-MITARBEITER.md" download>Mitarbeiter-Handbuch</a>
```

Neu:
```tsx
const [drawerOpen, setDrawerOpen] = useState(false);
const [drawerTab, setDrawerTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');

<button onClick={() => { setDrawerTab('cheatsheet'); setDrawerOpen(true); }}>Cheat-Sheet</button>
<button onClick={() => { setDrawerTab('handbuch'); setDrawerOpen(true); }}>
  {isAdmin ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch'}
</button>

<DocDrawer
  open={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  isAdmin={user?.role === 'admin'}
  initialTab={drawerTab}
/>
```

`DocDrawer` bleibt immer im DOM gemountet (kein `{open && <DocDrawer>}`), da die Schließ-Animation sonst nicht abspielbar ist. `isAdmin` kommt aus `useAuthStore`.

**Wichtig – Tab-Reset bei erneutem Öffnen:** Da `DocViewerContent` den aktiven Tab intern hält, muss sichergestellt werden, dass beim erneuten Öffnen der richtige Tab aktiv ist. Lösung: `<DocViewerContent key={drawerTab} ...>` — der `key`-Prop erzwingt ein Remount wenn sich `drawerTab` ändert, wodurch `initialTab` korrekt angewendet wird. Dasselbe gilt für `DocModal` mit `key={modalTab}`.

### Login.tsx

Neu:
```tsx
const [modalTab, setModalTab] = useState<'cheatsheet' | 'handbuch'>('cheatsheet');
const [modalOpen, setModalOpen] = useState(false);

<button onClick={() => { setModalTab('handbuch'); setModalOpen(true); }}>Mitarbeiter-Handbuch</button>
<button onClick={() => { setModalTab('cheatsheet'); setModalOpen(true); }}>Cheat-Sheet</button>

<DocModal open={modalOpen} onClose={() => setModalOpen(false)} initialTab={modalTab} />
```

---

## Extraktion aus Help.tsx — Genauer Umfang

Folgendes wird aus `Help.tsx` nach `DocViewer.tsx` verschoben:
- Interface `AccordionItem`
- Funktion `Accordion`
- Funktion `CheatsheetMitarbeiter`
- Funktion `CheatsheetAdmin`
- Konstante `handbuchMitarbeiterSections`
- Konstante `handbuchAdminSections`
- Funktion `DocViewerContent` (neu, enthält Tab-Logik)

In `Help.tsx` verbleiben:
- Import der o.g. Symbole aus `DocViewer.tsx`
- Der Seitenrahmen (`Help`-Komponente: Titel, Tab-Bar, Download-Links in den Tab-Panes)
- Die Download-Links in Help.tsx (`cheatsheetFile`, `handbuchFile`) bleiben unverändert — Help.tsx rendert sie weiterhin eigenständig ohne `DocViewerContent` zu nutzen. Help.tsx nutzt `CheatsheetMitarbeiter` etc. direkt.

**Wichtig:** `DocViewerContent` enthält **keine** Download-Links. Download-Links sind ausschließlich im Header von `DocDrawer`/`DocModal` und in der bestehenden `Help`-Seite.

---

## Styling

Folgt dem bestehenden Tailwind-Muster der App:
- Primärfarbe: `text-primary` / `border-primary` (bereits definiert)
- Overlay: `bg-black/40`
- Schatten: `shadow-2xl`
- Übergänge: `transition-transform duration-300` (Drawer), `transition duration-200` (Modal)
- Responsive-Breakpoint: `md:` (768px) für Drawer vs. Bottom Sheet

---

## Was sich NICHT ändert

- `/help`-Seite bleibt funktional unverändert nach dem Extrahieren
- Download der `.md`-Dateien bleibt möglich (Download-Button im Drawer/Modal-Header)
- Die Markdown-Dateien in `public/help/` bleiben bestehen
- Kein Markdown-Renderer wird eingeführt

---

## Testing

- Drawer öffnet via „Cheat-Sheet"-Link mit Kurzanleitung-Tab aktiv
- Drawer öffnet via „Handbuch"-Link mit Handbuch-Tab aktiv
- Drawer schließt via ✕-Button, Overlay-Klick und Escape
- Download-Link im Header zeigt die korrekte Datei für aktiven Tab und Rolle
- Admin sieht Admin-Inhalte, Mitarbeiter sieht Mitarbeiter-Inhalte
- Mobile: Bottom Sheet öffnet/schließt mit korrekter Animation
- Login: Modal öffnet mit korrektem initialTab, zeigt Mitarbeiter-Inhalte
- Help.tsx-Seite funktioniert unverändert nach dem Extrahieren
- Escape-Taste schließt Drawer und Modal
- Fokus kehrt nach Schließen zum auslösenden Button zurück
