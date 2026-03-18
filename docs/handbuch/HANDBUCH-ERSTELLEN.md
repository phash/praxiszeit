# Leitfaden: Handbücher und Cheat-Sheets erstellen

**Zweck:** Dieses Dokument beschreibt den Prozess und die Standards für die Erstellung und Aktualisierung der PraxisZeit-Nutzerdokumentation.

---

## Übersicht der Dokumentationsdateien

| Datei | Zielgruppe | Format | Zweck |
|-------|-----------|--------|-------|
| `HANDBUCH-MITARBEITER.md` | Mitarbeiter | Markdown | Vollständiges Referenzdokument |
| `CHEATSHEET-MITARBEITER.md` | Mitarbeiter | Markdown | Kompakte Kurzreferenz (1–2 Seiten) |
| `HANDBUCH-ADMIN.md` | Administratoren | Markdown | Vollständiges Referenzdokument |
| `CHEATSHEET-ADMIN.md` | Administratoren | Markdown | Kompakte Kurzreferenz (1–2 Seiten) |

**Pfade:**
- Quelldateien: `docs/handbuch/*.md`
- Screenshots: `docs/handbuch/screenshots/`
- Downloadbar in der App: `frontend/public/help/*.md`
- PDF-Dateien (optional): `frontend/public/docs/*.pdf`

**Wichtig:** Nach jeder Änderung an den Quelldateien müssen die Dateien nach `frontend/public/help/` synchronisiert werden (siehe [Schritt 5: Synchronisieren](#5-dateien-synchronisieren)).

---

## Wann muss die Dokumentation aktualisiert werden?

Aktualisierung notwendig bei:

- **UI-Änderungen:** Neue Seiten, geänderte Button-Bezeichnungen, neue Features, verschobene Navigationspunkte
- **Feature-Entfernung:** Veraltete Abschnitte löschen
- **Neue ArbZG-Prüfungen:** Gesetzliche Änderungen, neue Compliance-Reports
- **Formularänderungen:** Neue oder entfernte Pflichtfelder
- **Versionswechsel:** Bei jeder Minor- oder Major-Version

---

## Prozess zur Aktualisierung

### 1. Neuen Branch erstellen

```bash
git checkout -b docs/handbuch-update-YYYY-MM-DD
```

### 2. Screenshots aktualisieren

Screenshots werden mit **Playwright** automatisiert aufgenommen. Die App muss lokal laufen:

```bash
docker-compose up -d
```

#### Mitarbeiter-Screenshots (als Employee einloggen oder als Admin mit Employee-Sicht)

| Datei | URL | Beschreibung |
|-------|-----|-------------|
| `01-ma-login.png` | `/login` | Login-Seite |
| `02-ma-dashboard.png` | `/` | Dashboard (Mitarbeiter) |
| `03-ma-zeiterfassung.png` | `/time-tracking` | Zeiterfassung – Einträge-Tab |
| `04-ma-zeiteintrag-formular.png` | `/time-tracking` | Formular nach Klick auf „+ Neuer Eintrag" |
| `05-ma-abwesenheiten.png` | `/absences` | Abwesenheiten – Listenansicht |
| `06-ma-abwesenheiten-kalender.png` | `/absences` | Abwesenheiten – Kalenderansicht |
| `07-ma-abwesenheit-formular.png` | `/absences` | Formular „+ Abwesenheit eintragen" |
| `08-ma-korrekturantraege.png` | `/time-tracking` (Tab: Anträge) | Änderungsanträge-Tab leer |
| `09-ma-korrekturantrag-modal.png` | `/time-tracking` | Modal nach Klick auf „Änderungsantrag" bei gesperrtem Eintrag |
| `10-ma-profil.png` | `/profile` | Profilseite |
| `11-ma-mobile-dashboard.png` | `/` | Mobil (390px) – Dashboard |
| `12-ma-mobile-zeiterfassung.png` | `/time-tracking` | Mobil (390px) – Zeiterfassung |
| `13-ma-mobile-menu.png` | beliebig | Mobil (390px) – Hamburger-Menü offen |

#### Admin-Screenshots (als Admin einloggen)

| Datei | URL | Beschreibung |
|-------|-----|-------------|
| `14-admin-dashboard.png` | `/admin` | Admin-Dashboard mit Teamübersicht |
| `15-admin-benutzer.png` | `/admin/users` | Benutzerliste |
| `16-admin-benutzer-formular.png` | `/admin/users` | Formular „Neuer Mitarbeiter:in" |
| `17-admin-benutzer-bearbeiten.png` | `/admin/users` | Bearbeiten-Formular eines Benutzers |
| `18-admin-abwesenheitskalender.png` | `/admin/absences` | Abwesenheitskalender Admin |
| `19-admin-berichte.png` | `/admin/reports` | Berichte & Export |
| `20-admin-korrekturantraege.png` | `/admin/change-requests` | Korrekturanträge-Liste |
| `21-admin-korrekturantrag-details.png` | `/admin/change-requests` | Detailansicht eines Antrags |
| `22-admin-auditlog.png` | `/admin/audit-log` | Audit-Log |
| `23-admin-fehlermonitoring.png` | `/admin/errors` | Fehler-Monitoring |
| `24-admin-betriebsferien.png` | `/admin/absences` (Tab: Betriebsferien) | Betriebsferien-Tab |
| `25-admin-arbzg-berichte.png` | `/admin/reports` (nach unten scrollen) | ArbZG-Compliance-Reports |

#### Screenshots mit Playwright MCP aufnehmen (empfohlen)

Wenn Playwright-MCP verfügbar ist:

```
1. mcp__plugin_playwright_playwright__browser_navigate → URL aufrufen
2. mcp__plugin_playwright_playwright__browser_take_screenshot → {
     filename: "E:\\...\\screenshots\\XX-name.png",
     fullPage: true,
     type: "png"
   }
3. Für mobile (390px): mcp__plugin_playwright_playwright__browser_resize zuerst
```

#### Screenshots manuell aufnehmen

Alternativ mit dem Playwright-CLI:

```bash
cd e2e
npx playwright screenshot --viewport-size 1280,800 http://localhost/admin docs/handbuch/screenshots/14-admin-dashboard.png
```

### 3. Markdown-Dateien bearbeiten

**Schreibstil:**
- Klare, präzise Sprache (kein Fachjargon ohne Erklärung)
- Imperativ für Handlungsanweisungen: „Klicken Sie auf ...", „Geben Sie ... ein"
- Nummerierte Listen für Schritt-für-Schritt-Anleitungen
- Tabellen für strukturierte Informationen (Felder, Status, Optionen)
- Gesetzeslinks immer als Markdown-Links: `[§ 3 ArbZG](https://www.gesetze-im-internet.de/arbzg/__3.html)`

**Screenshot-Referenz:**
```markdown
![Beschreibung](screenshots/XX-name.png)
```

**Handbuch-Struktur:**
1. Versionskopf (Version, Stand, System, Zugangsdaten)
2. Inhaltsverzeichnis mit Ankerlinks
3. Abschnitte mit H2-Überschriften (##)
4. Unterabschnitte mit H3 (###)
5. Footer (Version, Stand)

**Cheat-Sheet-Struktur:**
1. H1-Titel
2. Abschnitte mit H2-Überschriften (##)
3. Kompakt: Max. 2–3 Zeilen pro Punkt, Tabellen bevorzugen
4. Kontaktblock am Ende (für Ausdruck)
5. Footer mit Gesetzeslink

### 4. Versionsnummer und Datum aktualisieren

Im Handbuch:
```markdown
**Version:** 2.1 · **Stand:** April 2026
```

Im Footer:
```markdown
*PraxisZeit – Handbuch v2.1 | April 2026*
```

### 5. Dateien synchronisieren

Nach jeder Änderung an den Quelldateien:

```bash
cp docs/handbuch/HANDBUCH-MITARBEITER.md frontend/public/help/HANDBUCH-MITARBEITER.md
cp docs/handbuch/CHEATSHEET-MITARBEITER.md frontend/public/help/CHEATSHEET-MITARBEITER.md
cp docs/handbuch/HANDBUCH-ADMIN.md frontend/public/help/HANDBUCH-ADMIN.md
cp docs/handbuch/CHEATSHEET-ADMIN.md frontend/public/help/CHEATSHEET-ADMIN.md
```

### 6. Help.tsx inline-Content aktualisieren

Die Hilfe-Seite (`frontend/src/pages/Help.tsx`) enthält zwei Arten von Inhalten:

1. **CheatsheetMitarbeiter / CheatsheetAdmin** – Inline React-Komponenten (werden direkt in der App angezeigt)
2. **handbuchMitarbeiterSections / handbuchAdminSections** – Accordion-Abschnitte für das Handbuch

Diese müssen **manuell** aktualisiert werden, wenn sich der Inhalt der Markdown-Dateien ändert:
- Neue Abschnitte als `AccordionItem` hinzufügen
- Geänderte Abläufe in den Cheatsheet-Sektionen anpassen
- Neue Navigationspunkte in der Login/Navigation-Sektion aktualisieren

### 7. PDF-Dateien generieren (optional)

Die PDFs in `frontend/public/docs/` können aus den Markdown-Dateien generiert werden.

**Mit pandoc (empfohlen):**
```bash
pandoc docs/handbuch/HANDBUCH-MITARBEITER.md \
  -o frontend/public/docs/Mitarbeiter-Handbuch.pdf \
  --pdf-engine=wkhtmltopdf \
  --css=docs/handbuch/handbuch.css \
  --metadata title="PraxisZeit – Mitarbeiter-Handbuch"
```

**Hinweis:** Wenn keine automatische PDF-Generierung eingerichtet ist, müssen die PDFs manuell erstellt werden (z. B. via Browser → Drucken → Als PDF speichern).

### 8. Committen und pushen

```bash
git add docs/handbuch/ frontend/public/help/ frontend/src/pages/Help.tsx
git commit -m "docs: Handbücher und Cheatsheets aktualisieren (vX.Y, März 2026)"
git push origin docs/handbuch-update-YYYY-MM-DD
```

Dann Pull Request erstellen für Review.

---

## Inhaltliche Standards

### Was gehört ins Handbuch?

- Vollständige Schritt-für-Schritt-Anleitungen für alle Funktionen
- Erklärungen aller Felder und Optionen
- Rechtliche Hintergründe (ArbZG-Paragraphen) mit Links
- FAQ-Abschnitt
- Screenshots für alle wichtigen Seiten und Formulare

### Was gehört ins Cheat-Sheet?

- Nur die häufigsten / wichtigsten Aktionen
- Keine Erklärungen, nur Kurzanweisungen
- Tabellen für schnellen Überblick (Felder, Status, Limits)
- Gesetzliche Limits in Tabellenform
- Kontaktblock zum Ausfüllen (für Ausdruck)
- Maximal 2 DIN-A4-Seiten

### Was gehört in Help.tsx?

- Kurzversion des Cheat-Sheets (inline, ohne Download nötig)
- Accordion-Abschnitte für die wichtigsten Handbuch-Kapitel
- Download-Links für die vollständigen Markdown-Dateien

---

## Qualitätssicherung

Vor dem Commit prüfen:

- [ ] Alle Screenshot-Referenzen existieren als Dateien in `screenshots/`
- [ ] Alle URLs und Navigationspfade stimmen mit der aktuellen App überein
- [ ] Button-Bezeichnungen stimmen mit den aktuellen Labels überein
- [ ] Version und Datum in Kopf und Footer aktualisiert
- [ ] Dateien nach `frontend/public/help/` synchronisiert
- [ ] Help.tsx auf Konsistenz mit Markdown geprüft
- [ ] Gesetzeslinks funktionieren
- [ ] Markdown rendert fehlerfrei (z. B. mit VS Code Preview)

---

*Zuletzt aktualisiert: März 2026*
