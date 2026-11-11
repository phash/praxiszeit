# Design: Grafische Handbücher mit echten Screenshots (App + Webseite)

Stand: 2026-11-10 · Basis: master 1.23.0 (`4cefd90f`) · Repos: `phash/praxiszeit` (App), `phash/pzweb` (Webseite)

## 1. Absicht

Die heutigen Handbücher sind lange Textwände: Markdown in `docs/handbuch/`, JSX-Zusammenfassungen in `DocViewer.tsx` und eine dritte Abschrift in pzweb unter `/anleitung/handbuch-*`. Keine dieser Fassungen ist mit den anderen verbunden, und keine hat Bilder, die auf dem Bildschirm zeigen, wo etwas ist.

Ziel sind **grafisch aufbereitete Handbuchseiten** mit **echten Screenshots aus der laufenden App**. Nummerierte Markierungen (①②③) liegen direkt auf dem Bild, die Schritte stehen daneben, und Comics lockern auf. Es gibt die Seiten an zwei Orten:

- **Webseite (pzweb):** In der Kopfleiste steht „Handbuch“ mit einem Dropdown.
- **App:** Die neuen Seiten ersetzen das bisherige Handbuch in der Hilfe.

Zielgruppen:

- **MFA / Mitarbeitende und Praxisleitung im Alltag:** „Wie geht X?“, schnell finden, im Bild sehen, nachmachen.
- **Interessenten vor dem Kauf:** Sie bekommen kein Handbuch, sondern die bestehende **Broschüre**, ergänzt um echte Screenshots. Sie bleibt kurz und zeigt grafisch, was die App kann.

Der gebilligte visuelle Entwurf (Nutzerfreigabe 2026-11-10: „sehr gut, setz das so um“):

- Kopfleiste mit dem Dropdown „Handbuch“
- links ein Kapitelverzeichnis, das beim Scrollen stehen bleibt
- je Aufgabe eine Karte: echter Screenshot mit orangefarbenen Markierungen (Rahmen um das Element, nummerierter Kreis an der Ecke), daneben nummerierte Schritte; fährt man mit der Maus über einen Schritt, wird die passende Markierung hervorgehoben
- Tipp-Kasten „Gut zu wissen“ mit Querverweis auf „So rechnet PraxisZeit“
- Comic-Einschub (Figur mit Sprechblase) als Auflockerung

Referenzdatei: `.superpowers/brainstorm/*/content/handbuch-entwurf-v2.html` (lokal, nicht eingecheckt).

## 2. Ziele

1. **Drei Handbücher** als grafische Seiten:
   - **Mitarbeitende**
   - **Praxisleitung** (Verwaltung/Admin)
   - **So rechnet PraxisZeit**: Soll, Ist, Saldo, Urlaubstage, Pausen, Arbeitszeit-Blöcke und Kappung, Betriebsferien, Minijob. Erklärt mit Diagrammen und Beispielrechnungen statt Fließtext, ergänzt um Screenshots von Journal und Dashboard.
2. **Echte Screenshots**, automatisch erzeugt: ein Playwright-Skript fährt eine saubere Wegwerf-Installation mit Demodaten ab. Bei jedem Release lassen sich alle Bilder mit einem Befehl neu aufnehmen.
3. **Markierungen positionieren sich selbst.** Der Inhalt beschreibt eine Markierung über einen Playwright-Locator (z. B. Rolle `button`, Name „Neuer Eintrag“), nicht über Pixel. Das Aufnahmeskript misst die Position und schreibt sie in eine Manifest-Datei. Ändert sich das Layout, wandert die Markierung bei der nächsten Aufnahme mit.
4. **Eine Inhaltsquelle für App und Webseite.** Text, Schritte, Markierungen und Bildverweise liegen genau einmal als typisierte Daten vor. Dieselbe React-Komponente stellt sie in App und pzweb dar.
5. **pzweb-Kopfleiste:** Menüpunkt „Handbuch“ mit Dropdown:
   - Für Mitarbeitende
   - Für die Praxisleitung
   - So rechnet PraxisZeit
   - Installation & Update (die bestehenden `/anleitung`-Seiten)

   Er funktioniert auch auf dem Handy.
6. **Broschüre `/broschuere`:** Die Comics bleiben. Je Szene kommt ein echter Screenshot dazu (Stempeln, Übersicht, Urlaub, Nachweise und neu Teamübersicht), mit höchstens drei Markierungen und ohne Schrittfolge.
7. **Comics in den Handbüchern:** etwa ein Einschub pro Kapitel, gezeichnet mit dem bestehenden `ComicKit`.

## 3. Nicht-Ziele

- **Kein neuer Text-Inhalt erfunden.** Fachlich gilt, was die heutigen Handbücher und `BERECHNUNGEN.md` sagen und was die App tut. Der Inhalt wird umgeschrieben (kürzer, aufgabenorientiert), nicht neu erdacht.
- **Cheat-Sheets und Schnellstart bleiben** in diesem Projekt unverändert (`CheatsheetMitarbeiter`, `CheatsheetAdmin`, `SchnellstartAdmin`, `CHEATSHEET-*.md`, `SCHNELLSTART.md`). *Meine Entscheidung.*
- **Installationsanleitungen** (`/anleitung/windows|linux|macos|update`) bleiben, wie sie sind. Sie werden nur über das neue Dropdown verlinkt.
- **Keine Schichtplanungs-Screenshots als Pflicht.** Der Schalter steht im Standard auf aus. Für das Kapitel Schichtplanung schaltet das Aufnahmeskript ihn in der Wegwerf-Instanz ein. Die Seite trägt den Hinweis „nur wenn eingeschaltet“.
- **Kein SaaS-Bezug** (Abrechnung, Signup, Trial).
- **Kein Ratgeber-, Landingpage- oder Rundgang-Umbau.** `/rundgang` kann seine Bilder aus derselben Pipeline beziehen; das ist optional (siehe 9).

## 4. Anti-Ziele

Das Projekt ist gescheitert, wenn eines davon eintritt, auch wenn es technisch läuft:

- **Nachgebaute oder gemalte UI** statt echter Screenshots.
- **Markierungen zeigen daneben.** Ein Kreis liegt nicht auf dem gemeinten Element, oder die Nummer im Bild passt nicht zum Schritt.
- **Eine vierte, frei laufende Textkopie.** App und Webseite zeigen verschiedene Stände.
- **Screenshots mit Testmüll:** `e2e_test_*`, `probe489`, englische Platzhalter, echte Namen oder E-Mails.
- **Bilder aus einer anderen Version als der beschriebenen**, z. B. Schaltflächen, die es nicht mehr gibt.
- **Handbuchseiten sind auf dem Handy unbenutzbar**, z. B. weil man den Screenshot horizontal scrollen muss.
- **Die Hilfe in der App bricht weg,** solange das neue Handbuch unvollständig ist. Abgelöst wird erst, wenn alle Kapitel stehen.

## 5. Randbedingungen

- **Gleicher Stack in beiden Repos:** React 18.3, Tailwind 4.3 (`@theme` mit identischen `--color-primary*`-Tokens), Vite 8, react-router 7. Eine gemeinsame Komponente ist also technisch einfach.
- **pzweb-CSP `style-src 'self'`** (`pzweb/frontend/nginx.conf:17`): `style={}` ist verboten. Die Markierungen werden deshalb als **SVG mit `viewBox` in Bildpixeln** gebaut, also `<image>` plus `<rect>` und `<circle>` mit Attributen. Die App erlaubt `'unsafe-inline'`; die gemeinsame Komponente hält trotzdem die strengere Regel ein.
- **pzweb rendert jede Route beim Build vorab** (`scripts/prerender.mjs`, `entry-server.tsx`). Die Komponente muss ohne Effekte vollständig rendern. Hover-Hervorhebung ist eine Verbesserung per Event-Handler, kein Pflichtteil.
- **pzweb `seo/routes.test.ts`:** Jede neue Route braucht einen Eintrag in `seo/routes.ts`. Titel ≤ 95 Zeichen und Beschreibung 50–200 Zeichen, beide eindeutig.
- **pzweb `Rundgang.test.tsx`-Muster:** Die Bildmaße stehen im Code und werden gegen den WebP-Header geprüft. Für die Handbuchbilder liefert das Manifest die Maße; ein Test prüft Manifest gegen Datei.
- **App-Hilfe heute:** `DocDrawer` (Schublade, max-w-2xl), `DocModal` (Login-Seite, nur Mitarbeitende), `Help.tsx` (`/help`, eigene Tab-Logik), Kontexthilfe `helpContent.tsx` je Route.
- **Doku-Sync-Regel (CLAUDE.md):** heute 5 Sync-Flächen, geprüft durch `scripts/check-doc-sync.sh` und `DocViewer.test.tsx`. Die neue Struktur muss diese Prüfungen ersetzen oder weiterführen, nicht stillschweigend aushebeln.
- **Demodaten:** fiktiv und deutsch, keine echten Personen, keine `@example.de`/`@praxis.de`-Mischung. Ein einheitlicher Praxisname, z. B. „Praxis am Lindenplatz“ wie im Rundgang.
- **Speicher knapp** (CLAUDE.md): Aufnahme, vitest, pytest und `docker build` nie gleichzeitig laufen lassen.
- **master ist branch-geschützt.** Arbeit auf `feat/handbuch-grafisch` (praxiszeit) und einem Feature-Branch in pzweb, je ein PR. Merge macht Manuel.

## 6. Architektur (entschieden)

### 6.1 Inhaltsquelle und gemeinsames Paket — *meine Entscheidung*

Neues Verzeichnis **`handbuch/`** im praxiszeit-Repo (Wurzel). Es ist die einzige Quelle:

```
handbuch/
  content/
    mitarbeitende.ts        # Kapitel → Aufgaben → Schritte (typisiert)
    praxisleitung.ts
    so-rechnet.ts
    broschuere.ts           # Screenshot-Ergänzungen der Broschüre
    types.ts                # Handbook, Chapter, Task, Step, Shot, Marker, Tip, Comic, Diagram
  shots/
    capture.spec.ts         # Playwright: Aufnahme + Marker-Vermessung
    manifest.json           # generiert: {shotId: {file, width, height, markers: {id: {x,y,w,h}}}}
  img/                      # generiert: <shotId>.webp (1440er-Breite, deviceScaleFactor 2)
  components/               # HandbookPage, ShotFigure (SVG-Overlay), StepList, Tip, ComicSlot, Toc, Diagram-Bausteine
  comics/                   # aus pzweb übernommenes ComicKit + Handbuch-Szenen
  render/
    to-markdown.ts          # erzeugt docs/handbuch/HANDBUCH-*.md + frontend/public/help/HANDBUCH-*.md
  sync-to-pzweb.sh          # kopiert content/components/comics/img/manifest nach pzweb
```

- **Inhalt als TypeScript-Daten, nicht MDX.** Typen erzwingen, dass jede Markierung im Bild einen Schritt hat und umgekehrt. Es braucht keinen zusätzlichen MDX-Compiler in zwei Builds.
- **Fließtext darf Inline-Auszeichnung haben** (UI-Begriff, fett, Link) über kleine Hilfsfunktionen. Freies JSX gibt es nicht, damit `to-markdown.ts` alles verlustfrei nach Markdown übersetzen kann.
- **Die App** bindet `handbuch/` per Vite-Alias ein (`@handbuch`). Die Bilder kopiert ein Build-Schritt nach `frontend/public/help/img/`.
- **pzweb erhält eine eingecheckte Kopie** unter `frontend/src/handbuch/` und `public/handbuch/img/`, erzeugt per `sync-to-pzweb.sh`. Der Kopf jeder Datei sagt „generiert, nicht bearbeiten“.
  - Gegen Auseinanderlaufen prüft `check-doc-sync.sh` eine neue Gruppe `handbuch_pzweb`: Byte-Gleichheit, sofern `../pzweb` existiert, sonst Hinweis statt Fehler.
  - pzweb prüft selbst die Bildmaße gegen das Manifest.

### 6.2 Darstellung

- **`HandbookPage`** rendert Kapitelverzeichnis, Aufgaben-Karten, Tipps, Comic-Einschübe und Diagramme. Es gibt zwei Layout-Varianten:
  - `wide`: Webseite und App-Vollseite. Screenshot und Schritte stehen nebeneinander, das Verzeichnis links.
  - `narrow`: Handy und schmale Fenster. Die Schritte stehen unter dem Bild, das Verzeichnis wird zu einem Auswahlfeld oben.
- **`ShotFigure`:**
  - `<svg viewBox="crop">` mit `<image href>` in voller Bildgröße. Der Ausschnitt (`crop`) kann je Aufgabe einen Bildteil zeigen, z. B. nur den Inhaltsbereich ohne Seitenleiste; so bleiben Details lesbar.
  - Markierungen werden als `<rect>` (Rahmen) und `<circle>` mit Zahl gezeichnet.
  - Klick öffnet das Bild in voller Größe (wie Rundgang).
  - Der Alt-Text kommt aus den Daten und ist Pflicht, mindestens 40 Zeichen (Muster `Rundgang.test.tsx`).
- **Zuordnung Schritt ↔ Markierung:** Beide teilen dieselbe Nummer. Beim Überfahren eines Schritts wird die Markierung hervorgehoben, die übrigen werden gedimmt.
- **Deep-Links:** Jede Aufgabe hat eine stabile ID als Anker (`#zeiterfassung-nachtragen`). Die Kontexthilfe der App (`helpContent.tsx`) bekommt je Route einen Link „Im Handbuch ansehen →“ auf das passende Kapitel. *Meine Entscheidung.*

### 6.3 App-Integration — *meine Entscheidung*

- **`/help` wird die Vollseite des Handbuchs:** `/help/mitarbeitende`, `/help/praxisleitung`, `/help/so-rechnet`, jeweils mit Anker.
  - Admins sehen alle drei, Mitarbeitende „Mitarbeitende“ und „So rechnet“.
  - Die doppelte Tab-Logik in `Help.tsx` entfällt.
- **Die Seitenleisten-Schaltfläche „Admin-/Mitarbeiter-Handbuch“** öffnet die Vollseite statt der Schublade. „Cheat-Sheet“ und „Schnellstart“ bleiben in der Schublade.
- **`DocModal` auf der Login-Seite** zeigt das Mitarbeitenden-Handbuch in der `narrow`-Variante.
- **`handbuchMitarbeiterSections` und `handbuchAdminSections` in `DocViewer.tsx` werden gelöscht,** wenn das neue Handbuch vollständig ist (Anti-Ziel „Hilfe bricht weg“). Die zugehörigen Wortlaut-Tests in `DocViewer.test.tsx` ziehen auf die Inhaltsdaten um.

### 6.4 Markdown-Fassungen — *meine Entscheidung*

- `docs/handbuch/HANDBUCH-ADMIN.md` und `HANDBUCH-MITARBEITER.md` bleiben bestehen, werden aber **aus den Daten erzeugt** (`render/to-markdown.ts`). Sie bekommen nummerierte Schrittlisten und Bildverweise auf `docs/handbuch/img/`.
- **Der Download-Spiegel** `frontend/public/help/HANDBUCH-*.md` wird ebenfalls erzeugt. Seine Bildlinks zeigen auf `/help/img/…`, damit sie heruntergeladen funktionieren. Damit ist der heutige Fehler „Bilder im Download lösen nicht auf“ behoben.
- **`docs/BERECHNUNGEN.md` bleibt die technische Referenz** für Entwickler und wird nicht erzeugt. „So rechnet PraxisZeit“ ist die nutzerseitige, grafische Fassung. Sie verweist auf Abschnitte von `BERECHNUNGEN.md`; `check-doc-sync.sh` prüft diese Anker.
- **Bestehende `check-doc-sync.sh`-Gruppen,** die Handbuch-Wortlaute prüfen (`mitarbeiter`, `admin_*`, `begriffe`, `versionen`, `mirror`), laufen gegen die erzeugten Markdown-Dateien weiter. Wo ein Wortlaut wegfällt, weil der Inhalt kürzer wird, wird die Prüfung angepasst, nicht gelöscht. Das steht im PR-Text.
- `docs/handbuch/screenshots/*.png` (alte PNGs) und die alten Skripte in `tools/handbook/*.js` werden entfernt. `e2e/capture-handbook-screenshots.ts` wird durch `handbuch/shots/capture.spec.ts` ersetzt. `HANDBUCH-ERSTELLEN.md` beschreibt den neuen Ablauf.

### 6.5 Screenshot-Pipeline

- **Wegwerf-Instanz:** eigenes Compose-Projekt `pzhandbuch` mit eigenen Ports, frischer DB und gebaut aus dem aktuellen Branch. Die Dev-DB wird nie benutzt (Testmüll).
  - Skript `handbuch/shots/run.sh`: hochfahren, `alembic upgrade`, Demodaten, Aufnahme, herunterfahren.
- **Demodaten:** `backend/create_handbuch_testdata.py` wird überarbeitet.
  - Alle Daten liegen **relativ zu einem festen Stichtag**, Standard „heute“. Für reproduzierbare Bilder fixiert das Aufnahmeskript Browser-Uhr und Stichtag.
  - Praxis „Praxis am Lindenplatz“, Admin „Dr. Andrea Werner“ (fiktiv), fünf bis sechs Mitarbeitende mit fiktiven Namen und Adressen `@praxis-lindenplatz.example`.
  - Abgedeckt werden alle Funktionen aus 1.23.0, die ein Kapitel zeigt:
    - Arbeitszeit-Blöcke, verkürzte Tage, Vertragsverlauf
    - offene Urlaubs- und Änderungsanträge, Betriebsferien, Sondertage, Minijob
    - Teamübersicht, ein ArbZG-Befund, Jahresabschluss-Kandidat
  - Erneutes Ausführen ergibt denselben Stand; die DB ist ohnehin frisch.
- **Aufnahme (`capture.spec.ts`):**
  - Je `Shot` aus den Inhaltsdaten: Rolle, Route, Vorbereitungsschritte (Dialog öffnen, Monat blättern), Fenstergröße (`desktop` 1440×900, `mobile` 390×844), deviceScaleFactor 2.
  - Für jede Markierung wird `locator.boundingBox()` gemessen und ins Manifest geschrieben.
  - Ausgabe als WebP in Qualität ~85 (über `sharp` oder `cwebp`; Entscheidung im Plan).
  - Kann ein Locator nicht aufgelöst werden, **schlägt die Aufnahme fehl.** Ein Bild mit fehlender Markierung wird nie still erzeugt.
  - Fokus-Ring und Toasts werden vor der Aufnahme entfernt; das Willkommens-Fenster (#132) wird geschlossen.
- **Prüfung nach der Aufnahme:**
  - Ein Kontakt-Bogen (HTML mit allen Bildern und Markierungen) wird zur Sichtkontrolle erzeugt.
  - Jedes Bild wird einmal von einem Menschen oder Agenten angesehen, bevor es eingecheckt wird (Anti-Ziel „Markierung daneben“).

### 6.6 „So rechnet PraxisZeit“

- **Aufbau je Thema:**
  1. eine Kernaussage in einem Satz
  2. ein Diagramm als SVG-Komponente
  3. ein Rechenbeispiel als Tabelle
  4. optional ein Screenshot (Journal, Dashboard-Saldo, Urlaubskonto)
- **Diagramm-Bausteine:**
  - Zeitstrahl Tag mit Blöcken, Puffer, Kappung und „nicht angerechnet“
  - Waage Soll/Ist
  - Monatsbalken Saldo
  - Urlaubskonto als Topf (Anspruch, Übertrag, Verbrauch, Rest)
  - Betriebsferien-Aufteilung Urlaub/Überstunden
- **Themen** (aus `BERECHNUNGEN.md` 1–12, für Nutzer zusammengefasst):
  - Grundbegriffe
  - Tagessoll
  - Ist und Pausen
  - Arbeitszeit-Blöcke und Kappung
  - Monatssoll und Saldo „bis heute“
  - Abwesenheiten (Matrix als Bildtabelle)
  - Urlaubskonto
  - Betriebsferien
  - Sondertage und verkürzte Tage
  - Minijob/MiLoG
  - Jahresabschluss
- **Fachliche Prüfung:** Jede Aussage wird gegen `BERECHNUNGEN.md` und den `calculation_service` gegengelesen. Die Rechenbeispiele werden durch einen Test gegen echte Berechnungen gesichert, wo es geht, z. B. Tagessoll-Beispiele über Backend-Testfälle.

### 6.7 pzweb

- **Kopfleiste:**
  - Desktop: Menüpunkt „Handbuch“ als Dropdown, umgesetzt als Disclosure-Button mit `aria-expanded`. Er schließt bei Escape und Klick außerhalb und ist ohne JavaScript per `<details>` bedienbar.
  - Handy: Das Dropdown wird Teil eines neuen Menüs unter `md` (heute werden dort Links nur versteckt).
  - Header-Tests bekommen Fälle für die Marketing-Links.
- **Routen:**
  - `/handbuch` (Übersicht mit drei Kacheln plus Installation)
  - `/handbuch/mitarbeitende`
  - `/handbuch/praxisleitung`
  - `/handbuch/so-rechnet-praxiszeit`
  - Jede bekommt einen Eintrag in `seo/routes.ts`.
- **Alte Routen** `/anleitung/handbuch-mitarbeiter`, `/anleitung/handbuch-admin` und `/anleitung/berechnungen` leiten per **301 in nginx** auf die neuen um, damit Suchmaschinen und Links aus `llms.ts` und Footer weiter funktionieren. Die alten TSX-Seiten und ihre Tests werden gelöscht; Footer `DOKU_LINKS`, `AnleitungHub` und `llms.ts` werden umgestellt.
- **Broschüre:** `BrochureSection` bekommt optional einen `shot` (aus `handbuch/content/broschuere.ts`) neben der Comic-Szene. Die Druckfassung behält ihr A4-Layout; die hinterlegte PDF wird neu erzeugt (Skript statt Handarbeit, z. B. Playwright `page.pdf()`).

## 7. Inhaltsgliederung (Ausgangspunkt, Builder darf verfeinern)

**Mitarbeitende:**
1. Anmelden & erster Start (inkl. 2FA)
2. Dashboard: Saldo, Urlaub, heute
3. Zeiterfassung: stempeln, Pause, Einträge ansehen und nachtragen, Journal
4. Urlaub & Abwesenheit: Kalender, Antrag, Halbtag
5. Anträge: Korrektur, Löschung, Status, zurückziehen
6. Auf dem Handy: Stempel-Knopf, untere Leiste
7. Profil, Passwort, 2FA
8. Schichtplan (wenn eingeschaltet)
9. Häufige Fragen

**Praxisleitung:**
1. Erste Einrichtung (Schnellstart-Inhalt verlinkt)
2. Dashboard & Teamübersicht
3. Mitarbeitende anlegen, Vertragsdaten und Vertragsverlauf
4. Arbeitszeit-Blöcke & Änderungen (inkl. rückwirkend, Anerkennen)
5. Anträge genehmigen (Urlaub, Korrektur)
6. Abwesenheiten & Betriebsferien
7. Sondertage & verkürzte Tage
8. Berichte & Exporte
9. ArbZG-Prüfung & §4-Ausnahme
10. Eigene Abwesenheitsgründe, Kind krank, Minijob
11. Einstellungen
12. Jahresabschluss
13. Import
14. Protokoll & Fehler-Monitoring
15. Datensicherung
16. Schichtplanung
17. Admin-Passwort verloren

**So rechnet PraxisZeit:** siehe 6.6.

## 8. Qualität und Prüfung

- **Tests:**
  - **Typ-Prüfung der Daten:** Jede Markierungs-ID im Schritt existiert im Manifest, jeder Shot hat ein Bild, Alt-Texte sind vorhanden.
  - **vitest für die Komponenten:** SSR-Render ohne Effekte, SVG ohne `style`-Attribute (CSP-Wächter), Anker-IDs eindeutig.
  - **pzweb-Tests:** Routen/SEO, Header-Dropdown, Bildmaße gegen das Manifest.
  - **App-Tests:** `/help`-Routen, Rollen-Sichtbarkeit, Kontexthilfe-Links lösen auf existierende Anker auf.
- **Doku-Sync:** `check-doc-sync.sh all` bleibt grün. Neue Gruppen `handbuch_md` (erzeugte Markdown-Dateien sind aktuell; der Generator lässt sie unverändert) und `handbuch_pzweb`.
- **Fachliche Gegenlesung** der drei Handbücher gegen App-Verhalten und `BERECHNUNGEN.md`, z. B. durch Review-Agenten (Arbeitsrecht/ArbZG für die Pausen-, Ruhezeit- und §16-Teile).
- **Sichtprüfung** jedes Screenshots (siehe 6.5).
- **Läuft auf Handy-Breite** (390 px) ohne horizontales Scrollen, in App und pzweb.

## 9. Dem Builder überlassen

- Genaue Komponenten-API, Dateinamen innerhalb von `handbuch/`, WebP-Werkzeug.
- Wie die App den `@handbuch`-Alias und die Bildkopie in Vite und Docker-Build einbindet (`frontend/.dockerignore` und Build-Kontext prüfen: `handbuch/` liegt außerhalb von `frontend/`).
- Aufteilung in Pakete und PRs (Empfehlung: Pipeline + Komponente → Mitarbeitende → Praxisleitung → So rechnet → App-Ablösung → pzweb).
- Ob `/rundgang` seine Bilder aus der Pipeline bezieht (Nice-to-have).
- Feinschnitt der Kapitel.

## 10. Entscheidungen aus dem Builder-Check

1. **Versionsstand auf pzweb:** Die Webseite zeigt immer das **zuletzt veröffentlichte Release**. Das ist die bestehende Praxis: pzweb-Doku-PRs werden zusammen mit dem Release gemergt.
   - Daraus folgt: Der pzweb-PR dieses Projekts wird erst mit dem Release gemergt, das das neue Handbuch ausliefert.
   - `/buildrelease` bekommt die Schritte „Screenshots neu aufnehmen“ und „`sync-to-pzweb.sh`“.
   - `handbuch_pzweb` vergleicht gegen den Stand des Release-Branches, nicht gegen einen Feature-Branch.
   - Die Regel kommt als neue Sync-Fläche in CLAUDE.md.
2. **ComicKit gehört nach `handbuch/comics/`** — *meine Entscheidung*.
   - Die Broschüren-Szenen ziehen mit um.
   - pzweb löscht sein eigenes `ComicKit.tsx` und die `Scene*.tsx`. Die Broschüre importiert die erzeugte Kopie. Es gibt keine zweite, frei laufende Fassung.
3. **Kein stückweiser Austausch auf master** — *meine Entscheidung*.
   - Die Arbeit läuft auf `feat/handbuch-grafisch`, Teil-PRs gehen gegen diesen Branch.
   - master bekommt das Handbuch in einem Zug, wenn alle drei Teile und die App-Ablösung fertig sind.
   - Es braucht keinen Feature-Schalter. Alte und neue Prüfungen laufen nicht parallel über Releases hinweg.
4. **Sichtbarkeit in `/help` richtet sich nach der Rolle** (Admin/Mitarbeitende).
   - Teil A (Einzelrechte, Tillwich) stellt das später auf Rechte um. Das Handbuch der Praxisleitung wird dann je Kapitel nach Recht gefiltert.
   - Dafür trägt jedes Kapitel schon jetzt ein optionales Feld `requires` (heute ungenutzt).

## 11. Offene Frage an Manuel

- Reihenfolge zu Tillwich Teil B/A: **Handbuch zuerst, Stand 1.23.0** (Freigabe 2026-11-10 „perfekt. Mach das“). Tillwich-PRs pflegen danach Inhalt und Screenshots als weitere Sync-Fläche mit; die CLAUDE.md-Regel kommt mit diesem Projekt.
