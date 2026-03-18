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
| `frontend/src/pages/Help.tsx` | Cheatsheet/Handbuch-Komponenten und Accordion nach `DocViewer.tsx` extrahieren; Help.tsx importiert sie von dort |
| `frontend/src/components/Layout.tsx` | Download-Links ersetzen durch Button, der `DocDrawer` öffnet |
| `frontend/src/pages/Login.tsx` | Download-Links ersetzen durch Button, der `DocModal` öffnet |

---

## Komponenten-Design

### `DocViewer.tsx`

Enthält den gemeinsamen Inhalt — aktuell in Help.tsx hardcodiert:
- `CheatsheetMitarbeiter` (React-Komponente)
- `CheatsheetAdmin` (React-Komponente)
- `handbuchMitarbeiterSections` (AccordionItem[])
- `handbuchAdminSections` (AccordionItem[])
- `Accordion`-Komponente
- Exportiert außerdem eine `DocViewerContent`-Komponente, die Tab-Logik kapselt

```
Props von DocViewerContent:
  isAdmin: boolean
  initialTab?: 'cheatsheet' | 'handbuch'
  downloadUrl: string   // für den Download-Button im Header
```

`DocViewerContent` rendert:
1. Tab-Leiste: „Kurzanleitung" | „Handbuch"
2. Je nach aktivem Tab: Cheatsheet- oder Handbuch-Inhalt (rollenabhängig)

### `DocDrawer.tsx`

```
Props:
  open: boolean
  onClose: () => void
  isAdmin: boolean
  initialTab?: 'cheatsheet' | 'handbuch'
```

**Desktop** (`md:` und größer):
- Positionierung: `fixed inset-y-0 right-0`, Breite `w-[70%] max-w-2xl`
- Hintergrund-Overlay: `fixed inset-0 bg-black/40`, klickbar zum Schließen
- Animation: `translate-x-full` → `translate-x-0` (CSS transition)
- Header: Titel + Download-Button (.md) + Schließen-Button (✕)
- Body: `<DocViewerContent>` mit `overflow-y-auto`

**Mobile** (unter `md:`):
- Positionierung: `fixed inset-x-0 bottom-0`, Höhe `h-[80vh]`
- Abgerundete obere Ecken: `rounded-t-2xl`
- Drag-Handle: zentrierter grauer Balken oben
- Animation: `translate-y-full` → `translate-y-0`
- Gleicher Header + Body wie Desktop

**Fokus-Management:**
- `aria-modal="true"`, `role="dialog"`, `aria-label`
- Escape-Taste schließt den Drawer
- Focus-Trap innerhalb des Drawers

### `DocModal.tsx`

```
Props:
  open: boolean
  onClose: () => void
  initialTab?: 'cheatsheet' | 'handbuch'
```

- Immer `isAdmin={false}` (Login-Seite hat keinen User-Kontext, zeigt Mitarbeiter-Inhalte)
- Positionierung: `fixed inset-0 flex items-center justify-center`
- Modal: `w-[90vw] max-w-2xl h-[80vh]`, `rounded-xl`, `shadow-2xl`
- Gleicher Header + `<DocViewerContent>`
- Escape-Taste schließt

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
<button onClick={() => openDrawer('cheatsheet')}>Cheat-Sheet</button>
<button onClick={() => openDrawer('handbuch')}>Mitarbeiter-Handbuch</button>
// admin: openDrawer('handbuch') öffnet mit Admin-Inhalten (isAdmin aus useAuthStore)
```

`DocDrawer` wird direkt in Layout.tsx gemountet (immer im DOM, open-State in Layout).

### Login.tsx

Aktuell:
```tsx
<a href="/help/HANDBUCH-MITARBEITER.md" download>Mitarbeiter-Handbuch</a>
<a href="/help/CHEATSHEET-MITARBEITER.md" download>Cheat-Sheet</a>
```

Neu:
```tsx
<button onClick={() => setModal('handbuch')}>Mitarbeiter-Handbuch</button>
<button onClick={() => setModal('cheatsheet')}>Cheat-Sheet</button>
```

`DocModal` wird am Ende von Login.tsx gerendert, open-State lokal in Login.

---

## Styling

Folgt dem bestehenden Tailwind-Muster der App:
- Primärfarbe: `text-primary` / `bg-primary` (bereits definiert)
- Overlay: `bg-black/40`
- Schatten: `shadow-2xl`
- Übergänge: `transition-transform duration-300`
- Responsive-Breakpoint: `md:` (768px) für Drawer vs. Bottom Sheet

---

## Was sich NICHT ändert

- `/help`-Seite bleibt unverändert (komplette Hilfe-Seite mit gleichem Inhalt)
- Download der `.md`-Dateien bleibt möglich (Download-Button im Drawer/Modal-Header)
- Die Markdown-Dateien in `public/help/` bleiben bestehen
- Kein Markdown-Renderer wird eingeführt

---

## Testing

- Drawer öffnet/schließt via Sidebar-Links (Cheatsheet-Tab und Handbuch-Tab)
- Drawer schließt via ✕-Button, Overlay-Klick und Escape
- Admin sieht Admin-Inhalte, Mitarbeiter sieht Mitarbeiter-Inhalte
- Mobile: Bottom Sheet öffnet/schließt korrekt
- Login: Modal öffnet mit korrektem initialTab
- Download-Button im Drawer lädt die `.md`-Datei herunter
- Help.tsx-Seite funktioniert unverändert nach dem Extrahieren der Komponenten
