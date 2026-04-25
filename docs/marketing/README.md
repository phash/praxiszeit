# PraxisZeit — Marketing-Material

## flyer.html

Zwei-seitiger A4-Info-Flyer. Selbsttragend (HTML + Inline-CSS + Inline-SVG, keine externen
Abhängigkeiten außer den zwei Screenshots aus `../handbuch/screenshots/`).

### Im Browser ansehen
```bash
xdg-open docs/marketing/flyer.html      # Linux
open docs/marketing/flyer.html          # macOS
start docs/marketing/flyer.html         # Windows
```

### Als PDF exportieren

**Headless-Chromium** (gibt 1:1 das gleiche Ergebnis wie Drucken im Browser):
```bash
chromium --headless --disable-gpu \
    --print-to-pdf=docs/marketing/flyer.pdf \
    --no-pdf-header-footer \
    "file://$(pwd)/docs/marketing/flyer.html"
```

**Manuell im Browser**: `Strg+P` → Druckziel "Als PDF speichern" → Ränder = "Keine" → Skalierung 100%.

### Stock-Photos statt SVG

Die Hero-Illustration ist eine reine SVG-Stilisierung (lizenzfrei, druckfest). Wer echte
Foto-Assets von glücklichen MFA einsetzen möchte, ersetzt den `<svg>`-Block in `.hero-svg`
durch ein `<img src="hero.jpg">`. Empfohlene lizenzfreie Quellen:

- [Unsplash](https://unsplash.com) — Suche: "medical assistant", "nurse smiling", "dental practice"
- [Pexels](https://www.pexels.com) — Suche: "medical office", "healthcare team"

Die Quote-Box auf Seite 1 ist als Platzhalter formuliert; gegen ein echtes Kunden-Zitat
austauschen, sobald eines vorliegt.

### Anpassen

Branding-Variablen liegen oben im `:root`-Block:
```css
--primary: #4A90B8;       /* Hauptfarbe */
--primary-dark: #2D6F94;
--primary-soft: #E8F1F7;  /* Hintergründe */
--accent: #FFB84D;        /* Hervorhebungen */
```

Workflow-Schritte sind reine HTML-Listen — Texte direkt anpassbar.
