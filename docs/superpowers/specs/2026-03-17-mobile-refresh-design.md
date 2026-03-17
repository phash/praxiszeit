# Mobile Refresh – "Soft & Clean" Redesign

**Datum:** 2026-03-17
**Scope:** Umfassendes Mobile-Facelift für PraxisZeit
**Priorität:** Stempeln > Dashboard > Journal
**Ästhetik:** Soft & Clean – moderne Health-App, beruhigend-professionell

---

## 1. Design Tokens

### Farbpalette "Soft Clinical"

Globale Änderung – betrifft Desktop und Mobile gleichermaßen. Die Tailwind-Token-Werte in `tailwind.config.js` werden ersetzt. `theme-color` in `index.html` wird auf `#4A90B8` aktualisiert.

| Token | Wert | Tailwind-Mapping | Verwendung |
|-------|------|------------------|------------|
| `primary` | `#4A90B8` | `colors.primary.DEFAULT` | Buttons, Links, Akzente |
| `primary-dark` | `#3A7196` | `colors.primary.dark` | Hover, Gradients |
| `primary-light` | `#E8F4F8` | `colors.primary.light` | Hintergrund-Akzente |
| `background` | `#FAFBFC` | `colors.background` | Seiten-Hintergrund |
| `surface` | `#FFFFFF` | `colors.surface` | Cards |
| `text-primary` | `#1A2B3D` | `colors.text.primary` | Überschriften, Fließtext |
| `text-secondary` | `#6B7F8E` | `colors.text.secondary` | Labels, Untertitel |
| `border` | `rgba(26,43,61,0.06)` | `colors.border` | Trennlinien |
| `success` | `#5CB88A` | `colors.success` | Eingestempelt, positive Werte |
| `danger` | `#E07070` | `colors.danger` | Ausstempeln, Fehler, negative Werte |
| `stamp-active-from` | `#5CB88A` | – | Gradient-Start FAB eingestempelt |
| `stamp-active-to` | `#4AA87A` | – | Gradient-Ende FAB eingestempelt |
| `muted` | `#F0F4F7` | `colors.muted` | Hintergründe, inaktive Elemente |

### Typografie

- **Font:** `DM Sans`, **self-hosted** (woff2-Dateien in `public/fonts/`)
- Gewichte: 400, 500, 600, 700
- `@font-face` in `index.css` mit `font-display: swap` (vermeidet FOIT)
- **Kein Google Fonts CDN** – PWA muss offline funktionieren
- Tailwind `fontFamily.sans` wird auf `'DM Sans', system-ui, sans-serif` gesetzt
- Numerische Darstellung: Tailwind-Klasse `tabular-nums` auf allen Zahlenwerten

### Schatten

| Token | Tailwind-Key | Wert |
|-------|-------------|------|
| `shadow-soft` | `boxShadow.soft` | `0 2px 8px rgba(26,43,61,0.06)` |
| `shadow-card` | `boxShadow.card` | `0 4px 16px rgba(26,43,61,0.08)` |
| `shadow-elevated` | `boxShadow.elevated` | `0 8px 32px rgba(26,43,61,0.12)` |

### Radii

| Element | Wert | Tailwind-Klasse |
|---------|------|-----------------|
| Cards, Buttons | `16px` | `rounded-2xl` |
| Inputs | `12px` | `rounded-xl` |
| Pills, Badges | `999px` | `rounded-full` |
| Bottom-Nav (oben) | `24px` | `rounded-t-3xl` |

---

## 2. Bottom Navigation + Floating Action Button

### Mobile Header

Der bestehende mobile Header (h-16, "PraxisZeit" Logo + Hamburger-Menü) **bleibt erhalten**. Er bietet weiterhin Zugang zur Slide-over Sidebar mit allen Navigationseinträgen inkl. Admin-Seiten. Der Header erhält die neuen Design Tokens (Farben, Font), aber keine strukturellen Änderungen.

### Struktur: 4 Tabs + zentrierter FAB

```
[ 🏠 Home ]  [ 📋 Journal ]  [ ⏱ FAB ]  [ 📅 Abw. ]  [ 👤 Profil ]
```

**Tab-Layout:** Jeder der 4 Tabs bekommt `calc((100% - 72px) / 4)` Breite. Der zentrale FAB-Slot ist 72px breit (56px Button + 8px Margin pro Seite). Minimale Touch-Target-Größe pro Tab: 44x44px.

### FAB (Stempel-Button)

- **Position:** Zentriert, ragt 12px über die Nav-Leiste hinaus
- **Größe:** 56px Durchmesser, `border-radius: 50%`
- **Eingestempelt:** Grün-Gradient (`#5CB88A → #4AA87A`), pulsierender Glow (3s Zyklus), Timer-Icon (Lucide `Timer`)
- **Ausgestempelt:** Primary-Gradient (`#4A90B8 → #3A7196`), Play-Icon (Lucide `Play`)
- **Schatten:** `shadow-elevated` + Ring-Effekt
- **Tap:** Öffnet StampWidget als Bottom-Sheet

### Nav-Leiste

- **Hintergrund:** `rgba(255,255,255,0.85)` + `backdrop-filter: blur(16px)`
- **Fallback:** `@supports not (backdrop-filter: blur(16px)) { background: rgba(255,255,255,0.97); }`
- **Obere Ecken:** `rounded-t-3xl`
- **Obere Border:** `1px solid rgba(26,43,61,0.06)`
- **Aktiver Tab:** Primary-Farbe + 4px Dot-Indikator (Kreis unter Icon)
- **Inaktive Tabs:** `#6B7F8E`
- **Icons:** Lucide, 22px, `stroke-width: 1.75`
- **Safe Area:** `padding-bottom: env(safe-area-inset-bottom)` für iPhone-Homebar
- **Z-Index:** `z-30` (wie aktuell), FAB `z-31`
- `index.html`: `<meta name="viewport">` ergänzt um `viewport-fit=cover`

### Änderung vs. aktuell

- "Zeiterfassung"-Tab → "Journal" (zeigt die bestehende Journal/Einträge-Seite)
- "Admin"-Tab entfällt aus Bottom-Nav (erreichbar via Hamburger → Sidebar)
- Admin nutzt primär Desktop; auf Mobile bleibt der Zugang via Sidebar gewährleistet

---

## 3. StampWidget Hero (Bottom-Sheet)

### Architektur

Der StampWidget wird von einer Inline-Komponente auf dem Dashboard zu einem **globalen Bottom-Sheet in `Layout.tsx`** umgebaut:

- Neuer Zustand in Zustand-Store (`uiStore.ts`): `isStampSheetOpen: boolean` + `openStampSheet()` / `closeStampSheet()`
- Das Bottom-Sheet wird in `Layout.tsx` gerendert (Portal-Level, über allem)
- **Trigger:** FAB-Tap (in Bottom-Nav) und Status-Card-Tap (auf Dashboard) rufen beide `openStampSheet()` auf
- Auf dem Dashboard wird die Status-Card (Sektion 4.2) den aktuellen Stempel-Status anzeigen, aber der eigentliche StampWidget lebt nur noch im Bottom-Sheet
- Z-Index: Backdrop `z-40`, Sheet `z-50` (wie bestehende Sidebar)

### Auslöser

Tap auf FAB oder Dashboard Status-Card → `uiStore.openStampSheet()`

### Layout

1. **Handle-Bar** oben (40x4px, `#D0D5DA`, `rounded-full`) – Swipe-to-Dismiss-Griff
2. **Timer-Display:** `DM Sans 700, 40px`, `tabular-nums`, Format `HH:MM:SS`, Update-Intervall 1s via `setInterval`
3. **Untertitel:** "Arbeitszeit heute", `text-secondary`, `14px`
4. **Info-Pills** (2 nebeneinander):
   - Startzeit (z.B. "08:02") + Label "Start"
   - Bisherige Pause (z.B. "0:30") + Label "Pause"
   - Style: `bg-muted`, `rounded-full`, `px-4 py-2`
5. **Pause-Input:** Nur sichtbar wenn eingestempelt, `rounded-xl`
6. **Action-Button:** Full-width, `h-14`, `rounded-2xl`
   - Einstempeln: Primary-Gradient + Play-Icon
   - Ausstempeln: Danger-Farbe + Stop-Icon (Lucide `Square`)
7. **Close-Button:** X-Icon oben rechts als zusätzliche Schließmöglichkeit

### Zustände

- **Eingestempelt:** Timer zählt (1s-Intervall), Info-Pills gefüllt, Pause-Input sichtbar, Button = Ausstempeln (rot)
- **Ausgestempelt:** Timer zeigt `00:00:00` in `text-secondary` (ausgegraut), Pills zeigen "—", Button = Einstempeln (primary)

### Swipe-to-Dismiss

- Swipe-down auf Handle-Bar oder Sheet-Content schließt das Sheet
- **Schwellwert:** 100px Drag-Distanz oder 500px/s Velocity
- Während Drag: Sheet folgt Finger via `transform: translateY()`
- Bei Release unter Schwellwert: Spring-Back zur offenen Position (200ms `ease-out`)

### Animation

- Öffnen: `translateY(100%) → 0`, 300ms `ease-out`
- Schließen: `translateY(0) → 100%`, 250ms `ease-in`
- Backdrop: `opacity: 0 → 0.4`, synchron
- Button-Tap: `scale(0.97) → scale(1)`, 150ms
- Stempel-Erfolg: Kurzer Checkmark-Flash (Lucide `Check` faded ein/aus, 400ms), dann Sheet schließt nach 600ms

---

## 4. Dashboard

### Layout-Reihenfolge (Mobile, top → bottom)

1. **Greeting:** "Hallo, [Vorname]" (`font-semibold text-2xl`) + Wochentag/Datum darunter in `text-secondary`

2. **Status-Card (Hero):**
   - Volle Breite, `shadow-card`, `rounded-2xl`, `p-5`
   - Farbiger Dot (8px, `rounded-full`) + "Eingestempelt seit 08:02" / "Nicht eingestempelt"
   - Fortschrittsbalken: `h-1.5`, `rounded-full`, Hintergrund `bg-muted`, Füllung Primary-Gradient, Animation `transition-all duration-1000`
   - "6:34 von 8:00 Std" darunter
   - Tap → `uiStore.openStampSheet()`
   - **Cursor:** `cursor-pointer`, leichter Hover-Schatten

3. **Stat-Pills (Grid statt Scroll):**
   - `grid grid-cols-3 gap-3`
   - Je Pill: `shadow-soft`, `rounded-2xl`, `p-4`, `bg-surface`
   - Großer Wert (`font-bold text-xl tabular-nums`) + Label darunter (`text-xs text-secondary`)
   - Inhalte: Überstunden-Saldo (grün wenn positiv, danger wenn negativ), Resturlaub, Krankentage
   - Daten aus bestehenden Dashboard-API-Endpunkten (`/api/dashboard/stats`)

4. **Letzte Einträge:**
   - `rounded-2xl`, `shadow-soft`, `bg-surface`, `divide-y divide-muted`
   - Max 5 Einträge, Daten von `GET /api/time-entries?month=CURRENT_MONTH` (sortiert nach Datum desc, erste 5)
   - Jede Zeile: Datum links, Zeitspanne Mitte, Dauer rechts (`tabular-nums`)
   - "Alle anzeigen →" Link → navigiert zu `/time-tracking`

5. **Team heute:** Entfällt aus diesem Spec (erfordert neue Backend-Endpoints + DSGVO-Prüfung → separates Ticket)

### Loading & Error States

- **Loading:** Skeleton-Platzhalter pro Sektion:
  - Greeting: Textzeile 60% Breite, Shimmer
  - Status-Card: Full-width Skeleton, `h-24`, `rounded-2xl`
  - Stat-Pills: 3x Skeleton-Pill, `h-20`
  - Letzte Einträge: 3x Zeilen-Skeleton
- **Error:** Toast-Notification + "Erneut laden" Button
- **Leer (keine Einträge):** "Noch keine Einträge diesen Monat" mit `EmptyState`-Komponente

### Was auf Mobile entfällt

- Monats-Tabelle (Desktop-only, `hidden md:block` bleibt)
- Großer Team-Kalender (Desktop-only)

---

## 5. Journal / Zeiteinträge

### Scope-Klarstellung

Diese Sektion betrifft den **"Einträge"-Tab** der bestehenden `TimeTracking.tsx`-Seite (die mobile Card-Ansicht). Die drei Tabs (Einträge, Journal, Anträge) bleiben als Struktur erhalten. Das Redesign betrifft nur die mobile Darstellung der Einträge-Liste und das visuelle Styling der Tab-Navigation.

### Kopfbereich

- **Tab-Navigation:** Bestehendes 3-Tab-Layout (Einträge / Journal / Anträge), aber mit neuen Tokens: `rounded-xl` Tabs, Primary-Farbe für aktiven Tab, `text-secondary` für inaktive
- MonthSelector mit `font-semibold`, Ghost-Buttons (`rounded-xl`)
- **Wochen-Dots:** Horizontaler Streifen der aktuellen Woche, unterhalb des MonthSelector
  - `●` = Eintrag vorhanden (Primary), `○` = kein Eintrag (muted)
  - Heute: Ring-Highlight (`ring-2 ring-primary`)
  - Tap auf Dot → scrollt zur Tages-Card (via `scrollIntoView({ behavior: 'smooth' })`)
  - Kein Swipe-Geste (zu konfliktanfällig mit vertikalem Scroll) – stattdessen Wochen-Navigation via Pfeil-Buttons links/rechts

### Tages-Cards

- **Container:** `rounded-2xl`, `shadow-soft`, `bg-surface`, `p-4`, `mb-3`
- **Header:** Voller Wochentag + Datum (`font-semibold text-base`)
- **Zeitbalken (visuelles Highlight):**
  - `h-2`, `rounded-full`
  - Hintergrund `bg-muted`, Füllung Primary-Gradient
  - Lücke = Pause (Hintergrund sichtbar)
  - Start-/Endzeit als kleine Labels (`text-xs text-secondary`) über dem Balken
  - Darstellung: Balken repräsentiert 06:00–20:00; Position berechnet als Prozent: `left: (startMinutes - 360) / 840 * 100%`
- **Metriken:** 2 Spalten – Label links (`text-secondary text-sm`), Wert rechts (`font-medium tabular-nums`)
  - Arbeitszeit, Pause, Typ
- **Actions:** 2 Ghost-Buttons (Bearbeiten, Löschen), `rounded-xl`, `text-sm`
- **Abwesenheiten:** Farbiger Badge (`rounded-full`) statt Zeitbalken
- **Tage ohne Eintrag:** Nicht angezeigt

### Bestehende Funktionalität (unverändert)

- Bottom-Sheet-Formular für Einträge erstellen/bearbeiten (erhält neue Tokens/Radii)
- Journal-Tab (MonthlyJournal.tsx) – erhält neue Tokens
- Anträge-Tab – erhält neue Tokens

---

## 6. Micro-Animationen

### Keyframe-Definitionen (in `index.css`)

```css
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
```

### Globale Transitions

| Element | Animation | Dauer |
|---------|-----------|-------|
| Seitenwechsel | `fadeSlideIn` | 200ms `ease-out` |
| Cards laden | `fadeSlideIn` + staggered `animation-delay: calc(var(--i) * 50ms)` | 200ms `ease-out` |
| Skeleton Loading | `shimmer` auf `background: linear-gradient(90deg, #F0F4F7 25%, #E8EDF1 50%, #F0F4F7 75%)` mit `background-size: 200% 100%` | 1.5s infinite |

### Interaktions-Feedback

| Element | Animation | Dauer |
|---------|-----------|-------|
| Button-Tap | `active:scale-[0.97]` | 150ms |
| Card-Tap | `shadow-soft → shadow-card` | 100ms |
| FAB-Tap | `active:scale-90` mit Bounce | 300ms `cubic-bezier(0.34,1.56,0.64,1)` |
| Nav-Tab Dot | `scale(0) → scale(1)` | 200ms |
| FAB Puls (eingestempelt) | `fabPulse` | 3s infinite |
| Stempel-Erfolg | `stampSuccess` auf Checkmark-Icon | 400ms |

### Performance-Regeln

- Nur `transform` und `opacity` animieren (GPU-beschleunigt)
- `will-change: transform` **nur** auf permanent animierte Elemente (FAB Puls) – nicht auf Cards oder Transitions
- `@media (prefers-reduced-motion: reduce)` → `animation: none !important; transition-duration: 0.01ms !important;`
- CSS-only bevorzugt – kein Motion-Library-Dependency

---

## 7. Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `tailwind.config.js` | Neue Farben, Schatten, Radii, Font-Family |
| `index.css` | `@font-face` DM Sans (self-hosted), Keyframes, `prefers-reduced-motion` |
| `index.html` | `theme-color` → `#4A90B8`, `viewport-fit=cover` |
| `public/fonts/` | **Neu:** DM Sans woff2-Dateien (400, 500, 600, 700) |
| `stores/uiStore.ts` | **Neu:** `isStampSheetOpen` State + open/close Actions |
| `Layout.tsx` | Bottom-Nav Redesign mit FAB, StampWidget Bottom-Sheet einbinden, Safe-Area |
| `Dashboard.tsx` | Neues Layout: Greeting + Hero-Card + Stat-Pills + Letzte Einträge |
| `TimeTracking.tsx` | Einträge-Cards mit Zeitbalken, Wochen-Dots, Tab-Styling |
| `StampWidget.tsx` | Hero Bottom-Sheet mit Timer (1s), Info-Pills, Swipe-to-Dismiss |
| `Button.tsx` | Neue Radii (`rounded-2xl`), active:scale Tap-Animation |
| `MonthSelector.tsx` | Neue Typografie, Ghost-Style |
| `Badge.tsx` | Aktualisierte Farben |
| `LoadingSpinner.tsx` | Primary-Farbe |

---

## 8. Nicht im Scope

- Desktop-Layout-Struktur (profitiert automatisch von geänderten Design Tokens)
- Backend-Änderungen (keine neuen Endpoints)
- Neue Funktionalität (rein visuell)
- Login-Page (separates Ticket)
- Dark Mode (separates Ticket)
- "Team heute" Live-Status (erfordert neuen Backend-Endpoint + DSGVO-Prüfung → separates Ticket)
