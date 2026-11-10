# Grafische Handbücher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drei grafische Handbücher (Mitarbeitende, Praxisleitung, So rechnet PraxisZeit) mit echten, automatisch aufgenommenen und markierten Screenshots, in der App (`/help`) und auf pzweb (Kopfleiste „Handbuch“), dazu Broschüre mit Screenshots.

**Architecture:** Typisierte Inhaltsdaten und React-Komponenten liegen genau einmal in `frontend/src/handbuch/`. Ein Playwright-Lauf gegen eine Wegwerf-Instanz (`pzhandbuch`) nimmt alle Screenshots auf, misst die Markierungen per Locator und schreibt WebP-Dateien plus `manifest.json`. Die App bindet das Verzeichnis direkt ein. pzweb bekommt per `sync-to-pzweb.sh` eine eingecheckte Kopie. Die Markdown-Handbücher werden aus den Daten erzeugt.

**Tech Stack:** React 18.3, Tailwind 4.3, Vite 8, vitest 4 + RTL, Playwright 1.64 (`e2e/`), `sharp` für WebP, Python-Seed im Backend-Container, PostgreSQL 18.

**Spec:** `docs/superpowers/specs/2026-11-10-handbuch-grafisch-design.md`

## Global Constraints

- **Kein `style`-Attribut** in Handbuch-Komponenten. pzweb-CSP ist `style-src 'self'`. Positionen nur über SVG-Attribute oder Tailwind-Klassen.
- **SSR-fest:** Alles rendert mit `renderToString` ohne Effekte. Kein Zugriff auf `window` oder `document` auf Modulebene oder im Render. Hover-Hervorhebung nur per Event-Handler.
- **Screenshots nur aus der Wegwerf-Instanz** (Compose-Projekt `pzhandbuch`), nie aus der Dev-DB.
  - Desktop 1440×900 und mobil 390×844, `deviceScaleFactor: 2`, WebP-Qualität 85.
- **Demodaten fiktiv:**
  - Praxis „Praxis am Lindenplatz“
  - Admin „Dr. Andrea Werner“, Benutzer `admin`
  - Mail-Domain `praxis-lindenplatz.example`
  - Kein `@praxis.de`, kein `example.de`, keine `e2e_`/`probe`-Konten.
- **Alt-Text Pflicht,** mindestens 40 Zeichen, deutsch.
- **Markierung ↔ Schritt:** Jede Markierungsnummer im Bild hat genau einen Schritt mit derselben Nummer und umgekehrt.
- **Locator-Regel:** Ein Locator muss beim Aufnehmen genau **ein sichtbares** Element treffen, sonst bricht die Aufnahme ab.
- **Texte deutsch**, Sie-Form, Begriffe laut `docs/GLOSSAR.md`:
  - „Arbeitszeit-Block“ = Vertrag, „Zeiteintrag“ = Stempel
  - „Mitarbeitende ohne Stundenzählung“
  - UI-Beschriftungen wortgleich zur App
- **Inhalt erfindet nichts.** Jede fachliche Aussage stammt aus `docs/handbuch/*.md` (Stand master), `docs/BERECHNUNGEN.md` oder dem App-Verhalten.
- **Arbeit auf `feat/handbuch-grafisch`** (Worktree `/home/manuel/claude/praxiszeit-handbuch`) und auf pzweb-Branch `feat/handbuch-grafisch`. Kein Merge nach master oder main, kein Push ohne Manuel.
- **Speicher:** vitest, pytest, Playwright und `docker build` nie gleichzeitig. vitest mit `--pool=threads --maxWorkers=2`.
- **Kapitel tragen optional `requires?: string`**, heute ungenutzt (Vorbereitung Tillwich Teil A).

**Abweichung vom Spec-Layout (Builder-Entscheidung laut Spec §9):** Das Spec nennt `handbuch/` in der Repo-Wurzel. Der Docker-Build-Kontext des Frontends ist aber `./frontend` (`docker-compose.yml:89`, `COPY . .`), Code außerhalb davon käme nicht ins Image. Deshalb gilt:
- Quelle unter `frontend/src/handbuch/`
- Aufnahme unter `e2e/handbuch/`
- Bilder unter `frontend/public/help/img/`

## Review Focus

1. **Locator trifft mehrere oder unsichtbare Elemente** (z. B. „Antrag“ steht in Kopf und Tab). Erwartet: Die Aufnahme bricht mit Shot- und Marker-ID ab und malt nicht still auf das erste Element. → Task 6, Test `resolveSingleVisible`.
2. **Handy-Breite 390 px:** Ein Screenshot-Ausschnitt mit winzigen Details oder eine Tabelle sprengt die Breite. Erwartet: kein horizontales Scrollen, das Bild skaliert, Klick öffnet die Vollgröße. → Task 2 (`narrow`-Layout-Test) und Task 21 (Playwright-Breitenprüfung).
3. **Veraltetes Manifest:** Die Inhaltsdaten nennen eine Markierung oder einen Shot, den das Manifest nicht kennt, z. B. nach einer Inhaltsänderung ohne Neuaufnahme. Erwartet: vitest schlägt fehl, bevor das Handbuch ausgeliefert wird. → Task 1, `validateHandbook`.
4. **Stichtag fällt auf Wochenende, Feiertag oder Monatsanfang:** Dashboard und Monat sind dann leer oder zeigen einen seltsamen Saldo. Erwartet: Seed und Aufnahme nutzen denselben festen Stichtag, einen Mittwoch Mitte des Monats, mit Daten davor. → Task 4.
5. **Anker-Kollision und tote Deep-Links:** Zwei Aufgaben mit gleicher ID, oder die Kontexthilfe verlinkt einen umbenannten Anker. Erwartet: Test schlägt fehl. → Task 1 (Eindeutigkeit) und Task 15 (Links).

---

## Phase 1 — Grundlage

### Task 1: Datentypen, Inline-Markup, Validierung

**Files:**
- Create: `frontend/src/handbuch/types.ts`, `frontend/src/handbuch/inline.tsx`, `frontend/src/handbuch/validate.ts`, `frontend/src/handbuch/manifest.json` (Start: `{}`)
- Test: `frontend/src/handbuch/validate.test.ts`, `frontend/src/handbuch/inline.test.tsx`

**Interfaces:**
- Produces (`types.ts`):
  ```ts
  export type HandbookId = 'mitarbeitende' | 'praxisleitung' | 'so-rechnet';
  export type Persona = 'admin' | 'maria' | 'sarah' | 'thomas' | 'petra' | 'julia' | 'anon';  // Login-Konten aus Task 4, anon = nicht angemeldet
  export type Inline = string;                                                  // Mini-Markup, siehe inline.tsx
  export type LocatorSpec =
    | { role: string; name: string; exact?: boolean; within?: 'main' | 'dialog' | 'nav' }
    | { label: string; within?: 'main' | 'dialog' }
    | { text: string; within?: 'main' | 'dialog' }
    | { css: string };
  export type PrepareStep =
    | { goto: string } | { click: LocatorSpec } | { fill: LocatorSpec; value: string }
    | { monthBack: number } | { waitFor: LocatorSpec } | { scrollTo: LocatorSpec };
  export interface MarkerDef { n: number; id: string; locator: LocatorSpec }
  export interface ShotDef {
    id: string; persona: Persona; viewport: 'desktop' | 'mobile'; route: string;
    prepare?: PrepareStep[]; crop?: 'full' | 'main' | 'dialog' | { around: string[]; pad: number };
    markers: MarkerDef[]; alt: string; settings?: Record<string, boolean | string | number>;
  }
  export interface Step { n?: number; text: Inline }
  export type Block =
    | { kind: 'task'; id: string; title: string; intro?: Inline; shot?: string; steps: Step[] }
    | { kind: 'tip'; tone: 'info' | 'warn'; text: Inline }
    | { kind: 'comic'; scene: string; text: Inline }
    | { kind: 'diagram'; diagram: string; caption: Inline }
    | { kind: 'table'; head: string[]; rows: Inline[][] }
    | { kind: 'prose'; text: Inline };
  export interface Chapter { id: string; title: string; requires?: string; blocks: Block[] }
  export interface Handbook { id: HandbookId; title: string; lead: Inline; chapters: Chapter[]; shots: ShotDef[] }
  export interface ManifestShot { file: string; width: number; height: number; pxWidth: number; pxHeight: number;
    crop: { x: number; y: number; w: number; h: number }; markers: Record<string, { x: number; y: number; w: number; h: number }> }
  export type Manifest = Record<string, ManifestShot>;   // Koordinaten in CSS-px des Fensters
  ```
- Produces (`inline.tsx`): `renderInline(text: Inline, opts: InlineOpts): ReactNode` und `inlineToMarkdown(text: Inline, opts: InlineOpts): string` mit `type InlineOpts = { linkBase: string; slugs?: Partial<Record<HandbookId, string>> }` (Slug-Standard = HandbookId; pzweb setzt `so-rechnet → so-rechnet-praxiszeit`).
  - Markup:
    - `**fett**`
    - `[[UI-Begriff]]` (graue Pille, Klasse `hb-ui`)
    - `[Text](#anker)` innerhalb des Handbuchs
    - `[Text](handbuch:so-rechnet#anker)` für ein anderes Handbuch
    - `[Text](/route)` absolut
  - Sonst nur Text. Kein HTML.
- Produces (`validate.ts`): `validateHandbook(h: Handbook, m: Manifest): string[]` (leere Liste = gültig).

- [ ] **Step 1: Failing tests**

  `validate.test.ts`, kleine Fixture-Handbücher:
  - `rejects step number without marker` → Fehler enthält `"task zeiterfassung-nachtragen: Schritt 3 ohne Markierung"`.
  - `rejects marker without step`
  - `rejects shot missing in manifest`
  - `rejects marker missing in manifest` (Review Focus 3)
  - `rejects duplicate task/chapter ids across handbook` (Review Focus 5)
  - `rejects alt shorter than 40 chars`
  - `rejects unknown handbuch: link target`
  - `accepts valid fixture` → `[]`

  `inline.test.tsx`:
  - `**a**` ergibt `<strong>`.
  - `[[Neuer Eintrag]]` ergibt `span.hb-ui`.
  - `[x](handbuch:so-rechnet#ist)` mit `linkBase: '/help'` ergibt `href="/help/so-rechnet#ist"`.
  - `<b>` bleibt Text.
  - `inlineToMarkdown` liefert `**a**`, `` `Neuer Eintrag` ``, `[x](HANDBUCH-…)` (Mapping in Task 7).

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/handbuch --pool=threads`. Expected: FAIL (Module fehlen).
- [ ] **Step 3: Implement** types, `renderInline`/`inlineToMarkdown` (ein Tokenizer, zwei Ausgaben) und `validateHandbook`.
- [ ] **Step 4: Run** wie Step 2. Expected: PASS. Dazu `npx tsc --noEmit`. Expected: keine Fehler.
- [ ] **Step 5: Commit** `feat(handbuch): content types, inline markup and validation`

### Task 2: Darstellungs-Komponenten

**Files:**
- Create: `frontend/src/handbuch/components/ShotFigure.tsx`, `StepList.tsx`, `TaskCard.tsx`, `TipBox.tsx`, `Toc.tsx`, `HandbookPage.tsx`, `index.ts`
- Test: `frontend/src/handbuch/components/HandbookPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 types, `renderInline`.
- Produces:
  - `HandbookPage(props: { handbook: Handbook; manifest: Manifest; imgBase: string; linkBase: string; variant: 'wide' | 'narrow'; comics?: Record<string, ComponentType> }): JSX.Element`
  - `ShotFigure(props: { shotId: string; def: ShotDef; m: ManifestShot; imgBase: string; active?: number | null })`
- Optik laut gebilligtem Entwurf (`.superpowers/brainstorm/*/content/handbuch-entwurf-v2.html`, im Haupt-Checkout):
  - Markierungsfarbe Orange `#f59e0b`, Rahmen 3 px, Kreis mit weißem Rand und Ziffer
  - Karte `rounded-2xl border`
  - Schritte mit orangener Nummernplakette
  - Tipp-Kasten blau mit linkem Rand
  - Kapitelverzeichnis links, bleibt beim Scrollen stehen (`sticky` per Klasse)
- `ShotFigure`:
  - `<svg viewBox="{crop.x} {crop.y} {crop.w} {crop.h}">`, darin `<image href="{imgBase}/{file}" width={width} height={height}>`.
  - Je Markierung `<rect>` und `<circle r=17>` mit `<text>`.
  - Hervorhebung über Klassen (`hb-act` / `hb-dim`).
  - Umschlossen von `<a href={vollbild} target="_blank" rel="noopener">`.
  - `role="img"` plus `aria-label={alt}`.
- `variant='narrow'`: Schritte unter dem Bild, Verzeichnis als `<select>`-freie Linkliste oben, eingeklappt in `<details>`.

- [ ] **Step 1: Failing tests**
  - `renders via renderToString without effects` (react-dom/server).
  - `no element has a style attribute` (Query `[style]` liefert 0; CSP-Wächter).
  - `marker numbers in svg match step numbers`
  - `hovering step 2 adds hb-act to marker 2 and hb-dim to others`
  - `narrow variant puts steps after figure in DOM order`
  - `each task has id anchor equal to task id`
  - `image href uses imgBase`
- [ ] **Step 2: Run** `npx vitest run src/handbuch/components --pool=threads`. Expected: FAIL.
- [ ] **Step 3: Implement** die Komponenten.
- [ ] **Step 4: Run.** Expected: PASS. Dazu `npx tsc --noEmit`.
- [ ] **Step 5: Commit** `feat(handbuch): page, figure and step components`

### Task 3: ComicKit übernehmen

**Files:**
- Create: `frontend/src/handbuch/comics/ComicKit.tsx` (Kopie von `pzweb/frontend/src/pages/marketing/broschuere/ComicKit.tsx`)
- Create: `frontend/src/handbuch/comics/Scene{Hero,Stempeln,Uebersicht,Urlaub,Nachweise}.tsx` (Kopien, Importpfad angepasst)
- Create: `frontend/src/handbuch/comics/ComicSlot.tsx`, `frontend/src/handbuch/comics/scenes.ts`
- Test: `frontend/src/handbuch/comics/comics.test.tsx`

**Interfaces:**
- Produces:
  - `COMIC_SCENES: Record<string, ComponentType>` mit den Schlüsseln `hero`, `stempeln`, `uebersicht`, `urlaub`, `nachweise` plus neuen Handbuch-Szenen aus Phase 2.
  - `ComicSlot({ scene, text, linkBase })`: Figur links, Text rechts, Verlaufshintergrund wie im Entwurf.

- [ ] **Step 1: Failing test:** Für jeden Schlüssel in `COMIC_SCENES` gilt: rendert per `renderToString`, enthält `<svg`, kein `style=`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Copy und anpassen.** Kein inhaltlicher Umbau.
  - `useId` bleibt (SSR-fest).
  - Lint/tsc-Regeln der App einhalten: `noUnusedLocals`. Ungenutzte Exporte sind ok, ungenutzte Locals nicht.
- [ ] **Step 4: Run.** Expected: PASS. Dazu `npx tsc --noEmit`.
- [ ] **Step 5: Commit** `feat(handbuch): move ComicKit and brochure scenes into the app`

### Task 4: Demodaten relativ zum Stichtag

**Files:**
- Modify: `backend/create_handbuch_testdata.py` (Umbau)
- Modify: `backend/tests/test_handbuch_seed_pg.py`

**Interfaces:**
- Produces:
  - CLI `python create_handbuch_testdata.py --stichtag YYYY-MM-DD`. Standard: der Mittwoch der Kalenderwoche, die 14 Tage vor heute liegt; falls Feiertag, der nächste Werktag.
  - Gibt den Stichtag als letzte Zeile `STICHTAG=YYYY-MM-DD` aus.
- **Personas** (Passwort aller MA `Handbuch2026!`, Admin `Handbuch2026!`):

  | Benutzer | Name | Vertrag |
  |---|---|---|
  | `admin` | Dr. Andrea Werner | Admin |
  | `maria` | Maria Hoffmann | 40 h, 5 Tage, 30 Urlaubstage |
  | `sarah` | Sarah Klein | 25 h mit Arbeitszeit-Blöcken Mo–Do 08–12 + 15–16, Fr 08–13 |
  | `thomas` | Thomas Bauer | 38,5 h |
  | `petra` | Petra Schulz | 20 h, 4 Tage |
  | `julia` | Julia Meyer | Minijob 10 h, MiLoG-Konto an |

  Mails `vorname.nachname@praxis-lindenplatz.example`. `PRACTICE_NAME=Praxis am Lindenplatz` kommt per Env (Task 5).
- **Daten:** Zeiteinträge für alle Werktage ab 1. des Vormonats bis Stichtag, ohne Feiertage und Abwesenheiten.
  - Maria: am Stichtag ein offener Eintrag ab 07:45 (für „läuft“-Anzeige).
- **Zusätzlich anlegen** (alle Daten relativ zum Stichtag):
  - Urlaub Maria (vergangen, 3 Tage)
  - offener Urlaubsantrag Thomas (Zukunft, 5 Tage)
  - Krank Sarah (2 Tage)
  - offener Korrekturantrag Maria
  - abgelehnter Korrekturantrag Thomas
  - Betriebsferien (Zukunft, 3 Tage, alle)
  - Sondertage 24./31.12. auf `half_day`
  - ein verkürzter Tag (Feature 1.22)
  - Vertragsverlauf-Zeile Petra (Urlaubsanspruch ab Monatsanfang geändert)
  - eigener Abwesenheitsgrund „Fortbildung extern“
  - ein §4-Pausenbefund (Thomas, 6:30 h ohne Pause mit Ausnahme-Grund)
  - Arbeitszeit-Änderung Sarah ab Vormonat
- **Bestehende Konten** mit gleichem Namen werden gelöscht und neu angelegt (frische DB, Task 5), statt übersprungen zu werden.

- [ ] **Step 1: Failing PG test** in `test_handbuch_seed_pg.py`:
  - `test_seed_relative_to_stichtag`: `--stichtag 2026-03-11` erzeugt einen Zeiteintrag am 2026-03-10 für maria, einen offenen am 11.03., einen Urlaubsantrag `pending` nach dem Stichtag, keinen Eintrag am Wochenende oder Feiertag, eine Betriebsferie nach dem Stichtag.
  - `test_seed_contains_no_legacy_domains`: keine Mail auf `@praxis.de`.
  - `test_default_stichtag_is_wednesday`: `default_stichtag(date(2026,11,10)) == date(2026,10,28)`.
  - Der bestehende RLS-Test (zwei Change Requests) bleibt.
- [ ] **Step 2: Run** gegen Wegwerf-PG laut `scripts/local-ci.sh` Schritt 2 (dort steht die Env für `APP_DB_URL`/`ADMIN_DB_URL`), z. B. `bash scripts/local-ci.sh` nur bis Schritt 2 oder der dort dokumentierte Einzelaufruf. Expected: FAIL.
- [ ] **Step 3: Implement.** Schreibwege wie heute über die ORM-Session unter `set_superadmin_context`. Den Rohzugriff an SQLAlchemy vorbei gibt es nicht (Lehre B9 im Dateikopf). Neue Objekte (verkürzte Tage, Vertragsverlauf, Gründe) über ihre Modelle; Feldnamen aus `backend/app/models/`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(handbuch): demo data relative to a reference date`

### Task 5: Wegwerf-Instanz

**Files:**
- Create: `e2e/handbuch/compose.override.yml`, `e2e/handbuch/env.template`, `e2e/handbuch/run.sh`

**Interfaces:**
- Produces: `bash e2e/handbuch/run.sh up|seed|down|all`. Nach `up` und `seed` gibt es `http://localhost:8099`; die Datei `e2e/handbuch/.state` enthält `BASE_URL=…` und `STICHTAG=…`.
- **Projektname `pzhandbuch`,** nie `praxiszeit` (Dev-Volumes! CLAUDE.md-Gotcha).
- **Nur `db`, `backend` und `frontend` starten.** Im Override:
  - `frontend.ports: !override ["127.0.0.1:8099:80"]`
  - `frontend.depends_on: !override {backend: {condition: service_healthy}}`
  - prometheus und grafana nicht starten.
- **`env.template`:**
  - `ENVIRONMENT=development`, `COOKIE_SECURE=false`
  - `LOGIN_RATE_LIMIT=10000/minute`, `REFRESH_RATE_LIMIT=10000/minute`
  - `PRACTICE_NAME=Praxis am Lindenplatz`
  - `ADMIN_FIRST_NAME=Andrea`, `ADMIN_LAST_NAME=Werner`
  - `HOLIDAY_STATE=Bayern`
  - `GRAFANA_ADMIN_PASSWORD` mit einem Dummy-Wert (Compose-Pflicht)
  - Secrets per `python3 -c secrets.token_hex` beim ersten `up` erzeugen und in `e2e/handbuch/.env` schreiben (gitignored).
- **`seed`:** `docker cp` des Seeds in den Backend-Container, dann `docker compose -p pzhandbuch exec -T backend python create_handbuch_testdata.py </dev/null`. Den Stichtag aus der Ausgabe nach `.state` übernehmen.
- **`down`:** `docker compose -p pzhandbuch down -v`.

- [ ] **Step 1:** `.gitignore` um `e2e/handbuch/.env` und `e2e/handbuch/.state` ergänzen.
- [ ] **Step 2: Run** `bash e2e/handbuch/run.sh up && bash e2e/handbuch/run.sh seed`. Expected: `curl -s localhost:8099/api/system/info` zeigt die Version aus `frontend/package.json`; `curl -s -XPOST localhost:8099/api/auth/login -H 'content-type: application/json' -d '{"username":"maria","password":"Handbuch2026!"}'` liefert `access_token`.
- [ ] **Step 3: Run** `docker compose -p praxiszeit ps`. Expected: Der Dev-Stack ist unverändert, kein neuer Container dort.
- [ ] **Step 4: Run** `bash e2e/handbuch/run.sh down`. Expected: Volumes `pzhandbuch_*` sind weg.
- [ ] **Step 5: Commit** `feat(handbuch): throwaway instance for screenshot capture`

### Task 6: Aufnahme und Vermessung

**Files:**
- Create: `frontend/src/handbuch/geometry.ts` (rein, in vitest testbar)
- Create: `e2e/handbuch/capture.ts`, `e2e/handbuch/contact-sheet.ts`
- Create: `frontend/src/handbuch/content/index.ts` (zunächst nur `_probe.ts`; Task 8 erweitert), `frontend/src/handbuch/content/_probe.ts`
- Modify: `e2e/package.json` (devDependencies `sharp`, `tsx`; Script `"handbuch:capture": "tsx handbuch/capture.ts"`)
- Test: `frontend/src/handbuch/geometry.test.ts`

**Interfaces:**
- Consumes: `Handbook.shots` aller Handbücher (Import aus `frontend/src/handbuch/content/index.ts`, Task 8), `.state`.
- Produces:
  - `geometry.ts`:
    - `computeCrop(kind: ShotDef['crop'], viewport: {w,h}, boxes: { main?: Box; dialog?: Box; markers: Record<string, Box> }): Box`. Beschnitt aufs Fenster; `'main'` = Box von `<main>`; `{around, pad}` = Vereinigung der Marker-Boxen plus `pad`, mindestens 480 breit.
    - `assertSingleVisible(count: number, visible: number, ctx: string): void` (wirft `Error("<ctx>: <count> Treffer, <visible> sichtbar — Locator muss genau ein sichtbares Element treffen")`).
  - CLI `npx tsx handbuch/capture.ts [--only <shotId,…>]`:
    - schreibt `frontend/public/help/img/<shotId>.webp`
    - aktualisiert `frontend/src/handbuch/manifest.json`, nur die aufgenommenen Shots; Schlüssel sortiert
    - erzeugt `e2e/handbuch/contact-sheet.html`, gitignored
- **Ablauf je Shot:**
  1. Kontext mit Viewport und `deviceScaleFactor` 2, `locale de-DE`, `timezoneId Europe/Berlin`.
  2. `page.clock.setFixedTime(<STICHTAG>T10:30:00)`.
  3. Login als Persona und Willkommens-Fenster schließen (wie bisher in `e2e/capture-handbook-screenshots.ts:24-45`).
  4. `settings` per Admin-API setzen (`PUT /api/admin/settings/...`, Feldnamen aus `admin_settings._ALLOWED_SETTINGS`) und danach zurücksetzen.
  5. `prepare` ausführen; `monthBack` klickt n-mal „Vorheriger Monat“.
  6. Fokus entfernen, Toasts ausblenden (warten, bis `[role=status]` leer ist).
  7. Je Marker: Locator bauen (`within` grenzt auf `main`, `[role=dialog]` oder `nav` ein), `assertSingleVisible`, `boundingBox`.
  8. Ganzes Fenster als PNG aufnehmen, Crop nicht ins Bild schneiden (Crop wirkt nur über die `viewBox`), mit `sharp` nach WebP konvertieren und `pxWidth`/`pxHeight` lesen.
- **Lange Formulare:** Für `crop: 'dialog'` mit Inhalt über dem Fenster wird das Fenster vorher bis zur Unterkante gestreckt (Muster `shotUntil`, `e2e/capture-handbook-screenshots.ts:60`).

- [ ] **Step 1: Failing tests** in `geometry.test.ts`:
  - `main crop equals main box clamped to viewport`
  - `around crop unions marker boxes plus pad`
  - `around crop is at least 480 wide`
  - `assertSingleVisible throws on 2 matches` (Review Focus 1)
  - `assertSingleVisible throws on 1 match hidden`
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/handbuch/geometry.test.ts --pool=threads`. Expected: FAIL.
- [ ] **Step 3: Implement** `geometry.ts` und `capture.ts`. Einen Probe-Shot `probe-zeiterfassung` (Maria, `/time-tracking`, 2 Marker „Neuer Eintrag“ und „Vorheriger Monat“) in `content/_probe.ts` anlegen; er wird in Task 8 gelöscht.
- [ ] **Step 4: Run** `bash e2e/handbuch/run.sh up && bash e2e/handbuch/run.sh seed && cd e2e && npx tsx handbuch/capture.ts --only probe-zeiterfassung`. Expected: Die WebP-Datei existiert, das Manifest hat zwei Marker-Boxen, und im `contact-sheet.html`-Rendering sitzen beide Markierungen auf ihren Knöpfen. Bild ansehen (Read-Tool aufs PNG der Kontaktseite).
- [ ] **Step 5: Commit** `feat(handbuch): capture with measured markers`

### Task 7: Markdown-Erzeugung und Doku-Sync

**Files:**
- Create: `frontend/src/handbuch/render/toMarkdown.ts`, `frontend/scripts/generate-handbuch-md.ts`
- Modify: `frontend/package.json` (Script `"handbuch:md": "tsx scripts/generate-handbuch-md.ts"`)
- Modify: `scripts/check-doc-sync.sh` (neue Gruppe `handbuch_md`)
- Test: `frontend/src/handbuch/render/toMarkdown.test.ts`

**Interfaces:**
- Produces: `toMarkdown(h: Handbook, m: Manifest, target: 'docs' | 'download'): string`.
  - Bildpfade: `docs` → `img/<file>` (Ausgabe `docs/handbuch/HANDBUCH-*.md`, Bilder werden nach `docs/handbuch/img/` kopiert); `download` → `/help/img/<file>`.
  - Dateinamen: `HANDBUCH-MITARBEITER.md`, `HANDBUCH-ADMIN.md`, `SO-RECHNET-PRAXISZEIT.md`.
  - `handbuch:`-Links werden auf diese Dateien gemappt.
  - Kopf: `<!-- Erzeugt aus frontend/src/handbuch — nicht von Hand bearbeiten -->`, dazu die Versionszeile im heutigen Format (`check-doc-sync.sh` Gruppe `versionen`, :1171; Format von dort übernehmen).
- **Gruppe `handbuch_md`:** führt `npm run -s handbuch:md -- --check` aus. Weicht eine Datei ab, ist der Exit nicht 0 mit Diff-Hinweis. Eintrag in `run_group all`.

- [ ] **Step 1: Failing tests:**
  - `task renders as heading, numbered steps and image with alt`
  - `download target uses /help/img paths`
  - `cross-handbook link maps to md file`
  - `header contains generated marker and version line`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Der Generator schreibt die drei Docs-Dateien, die Download-Dateien (`frontend/public/help/HANDBUCH-*.md`, `SO-RECHNET-PRAXISZEIT.md`) und kopiert die Bilder nach `docs/handbuch/img/`. Mit `--check` vergleicht er nur.
- [ ] **Step 4: Run** Tests (PASS) und `bash scripts/check-doc-sync.sh handbuch_md` (PASS, solange noch keine Inhalte da sind: der Generator überspringt Handbücher ohne Kapitel).
- [ ] **Step 5: Commit** `feat(handbuch): generate markdown handbooks from content`

## Phase 2 — Inhalte

**Gemeinsames Vorgehen für Task 8–13 (je Task):**
1. Quelle lesen: der genannte Abschnitt aus `docs/handbuch/*.md` und die betroffenen Seiten in `frontend/src/pages`.
2. Inhalt als Daten schreiben: kürzer, eine Aufgabe = Frage → Screenshot → 3–6 Schritte, plus Tipps.
3. Shots definieren.
4. `capture.ts --only …` ausführen.
5. Jedes Bild der Kontaktseite ansehen und Markierungen prüfen (Anti-Ziel „Markierung daneben“).
6. `validateHandbook` grün.
7. `npm run handbuch:md`.
8. Commit `docs(handbuch): <Kapitel>`.

**Test je Task:** `frontend/src/handbuch/content/content.test.ts` (in Task 8 anlegen):
- `validateHandbook(<h>, manifest)` liefert `[]` für jedes Handbuch.
- `every chapter of <h> has at least one task with a shot` (gilt nicht für So rechnet: dort Diagramm oder Shot).
- Wortlaut-Wächter: Begriffe aus `DocViewer.test.tsx` `VERALTET` (`frontend/src/components/DocViewer.test.tsx:34`) kommen in keinem Inhalt vor. Der Test importiert die Liste nach `frontend/src/handbuch/content/forbiddenTerms.ts`, die von dort ab die Quelle ist.

**Comics:** etwa ein `comic`-Block pro Kapitel. Neue Szenen in `comics/` mit `ComicKit`-Bausteinen (`Person`, `Bubble`, `Screen`, `UiCard`), Schlüssel in `scenes.ts`.

### Task 8: Handbuch Mitarbeitende

**Files:**
- Create: `frontend/src/handbuch/content/mitarbeitende.ts`, `frontend/src/handbuch/content/content.test.ts`
- Modify: `frontend/src/handbuch/content/index.ts`, `frontend/src/handbuch/content/forbiddenTerms.ts`
- Delete: `content/_probe.ts`

**Interfaces:**
- Produces: `export const HANDBOOKS: Record<HandbookId, Handbook>`, `export const ALL_SHOTS: ShotDef[]` in `content/index.ts`.

**Kapitel:** Spec §7 Mitarbeitende 1–9. Quelle `docs/handbuch/HANDBUCH-MITARBEITER.md` 1–9 plus Schichtplan.
- Mobil-Kapitel mit `viewport: 'mobile'`.
- Schichtplan mit `settings: { shift_planning_enabled: true }` und `requires`-freiem Hinweis-Tipp „nur wenn eingeschaltet“.

- [ ] Steps: Gemeinsames Vorgehen 1–8. Abschluss: `npx vitest run src/handbuch --pool=threads` PASS.

### Task 9: Handbuch Praxisleitung, Kapitel 1–9

**Files:** Create `frontend/src/handbuch/content/praxisleitung.ts`.
- Kapitel: Spec §7 Praxisleitung 1–9.
- Quelle: `HANDBUCH-ADMIN.md` (Dashboard, Benutzerverwaltung inkl. Vertragsverlauf, Arbeitszeit-Blöcke inkl. rückwirkend und Anerkennen, Anträge, Abwesenheiten/Betriebsferien, Sondertage/verkürzte Tage, Berichte, ArbZG).
- Persona `admin`.

- [ ] Steps: Gemeinsames Vorgehen 1–8.

### Task 10: Handbuch Praxisleitung, Kapitel 10–17

**Files:** Modify `frontend/src/handbuch/content/praxisleitung.ts`.
- Kapitel: Spec §7 Praxisleitung 10–17.
- Kapitel 15 Datensicherung und 17 Admin-Passwort: Wo es keine Oberfläche gibt (CLI `praxiszeit-server.py reset-admin-password`), wird statt eines Screenshots ein `table`- oder `prose`-Block mit dem Befehl gesetzt. Das ist die Ausnahme von der Regel „mindestens ein Shot“; im Test als erlaubte Ausnahme-ID führen.

- [ ] Steps: Gemeinsames Vorgehen 1–8.

### Task 11: Diagramm-Bausteine für „So rechnet“

**Files:**
- Create: `frontend/src/handbuch/diagrams/{DayTimeline,SollIstScale,MonthBalanceBars,VacationPot,ClosureSplit}.tsx`, `frontend/src/handbuch/diagrams/index.ts`
- Test: `frontend/src/handbuch/diagrams/diagrams.test.tsx`

**Interfaces:**
- Produces: `DIAGRAMS: Record<string, ComponentType>` mit den Schlüsseln `tag-zeitstrahl`, `soll-ist`, `saldo-monat`, `urlaubskonto`, `betriebsferien-split`. Die Werte sind fest im Diagramm, als Beispiel aus `BERECHNUNGEN.md` 13/14.
- **`DayTimeline`:** Blöcke 08–12 und 15–16, Puffer 15 min, ein Stempel 07:30–12:10 → 07:45 angerechnet, Lücke „nicht angerechnet“.
  - Begriffe wie `work_window_service`: Hülle, Puffer, Lücke.
  - Die Zahlen müssen dem Kappungsverhalten laut `BERECHNUNGEN.md` (Abschnitt Arbeitszeit-Blöcke) entsprechen. Gegenprüfung über einen Backend-Unit-Test, siehe Task 12.

- [ ] **Step 1: Failing tests:** Jedes Diagramm rendert per SSR, ohne `style`, mit `role="img"` und `aria-label` ≥ 40 Zeichen. `HandbookPage` rendert `kind: 'diagram'` über `DIAGRAMS`.
- [ ] **Step 2–4:** Implementieren, bis PASS.
- [ ] **Step 5: Commit** `feat(handbuch): calculation diagrams`

### Task 12: „So rechnet PraxisZeit“

**Files:**
- Create: `frontend/src/handbuch/content/so-rechnet.ts`
- Create: `backend/tests/test_handbuch_rechenbeispiele.py`

**Kapitel:** Spec §6.6 (11 Themen). Je Thema:
1. Kernsatz (`prose`)
2. Diagramm
3. Beispieltabelle (`table`)
4. optional ein Shot: Journal (Persona maria), Dashboard-Saldo, Urlaubskonto, Admin-Bericht

- **Anker** an `docs/BERECHNUNGEN.md`-Abschnitte, als Link `[Technische Details](/…)`. Auf pzweb zeigt er auf GitHub `blob/master/docs/BERECHNUNGEN.md#…`; der Link-Builder nimmt `linkBase`. In der App auf denselben GitHub-Link.
- **`test_handbuch_rechenbeispiele.py` (SQLite-Suite):** Jede Zahl aus den Beispieltabellen und aus `DayTimeline` wird über `calculation_service` bzw. `work_window_service.clamp` nachgerechnet:
  - Tagessoll Teilzeit 25 h / 5 Tage = 5,0 h
  - Kappung 07:30 → 07:45 bei Block 08:00 und Puffer 15 min
  - Halbtags-Sondertag kostet 0,5 Urlaubstag
  - Betriebsferien-Split mit Resturlaub 1 Tag: erster Tag Urlaub, Rest Überstunden
  - Die Werte stehen im Test und in `so-rechnet.ts` als gemeinsame Konstanten-Kommentare mit Abschnitts-ID. Ein Abgleich-Test in vitest liest die Zahlen aus `so-rechnet.ts` und vergleicht sie mit `frontend/src/handbuch/content/rechenbeispiele.json`; diese JSON-Datei liest auch der Python-Test.

- [ ] **Step 1: Failing tests:** `test_handbuch_rechenbeispiele.py` (liest `frontend/src/handbuch/content/rechenbeispiele.json`, rechnet nach) und ein vitest-Fall `so-rechnet tables match rechenbeispiele.json`.
- [ ] **Step 2:** Run backend (CLAUDE.md-Wegwerf-Container-Befehl, Datei einzeln) und vitest. Expected: FAIL.
- [ ] **Step 3:** Inhalt plus JSON schreiben, Shots aufnehmen, Bilder prüfen.
- [ ] **Step 4:** Run. Expected: PASS. Fachliche Gegenlesung: ein Review-Agent mit `docs/BERECHNUNGEN.md` und `so-rechnet.ts`; Funde beheben.
- [ ] **Step 5: Commit** `docs(handbuch): how PraxisZeit calculates`

### Task 13: Broschüren-Screenshots

**Files:** Create `frontend/src/handbuch/content/broschuere.ts`.

**Interfaces:**
- Produces: `export const BROSCHUERE_SHOTS: { section: 'stempeln' | 'uebersicht' | 'urlaub' | 'nachweise' | 'team'; shot: ShotDef; caption: Inline }[]`.
- Pro Shot höchstens 3 Marker, keine Schritte; die Zahlen im Bild genügen.
- `content/index.ts` nimmt die Shots in `ALL_SHOTS` auf.
- **Validierung:** `validateBroschuere(list, manifest)` in `validate.ts`: Shot und Marker im Manifest, ≤ 3 Marker, Alt ≥ 40.

- [ ] **Step 1: Failing test:** `validateBroschuere` lehnt 4 Marker ab und akzeptiert die echte Liste.
- [ ] **Step 2–4:** Implementieren, aufnehmen, Bilder prüfen, PASS.
- [ ] **Step 5: Commit** `docs(handbuch): brochure screenshots`

## Phase 3 — App-Ablösung

### Task 14: `/help` als Vollseite

**Files:**
- Modify: `frontend/src/pages/Help.tsx` (Umbau), `frontend/src/App.tsx:32,143` (Route `help/:book?`), `frontend/src/components/Layout.tsx:368-375` (Handbuch-Schaltfläche navigiert zu `/help/<book>`), `frontend/src/components/DocModal.tsx`
- Test: `frontend/src/pages/Help.test.tsx`

**Interfaces:**
- Consumes: `HandbookPage`, `HANDBOOKS`, `manifest.json`, `COMIC_SCENES`, `DIAGRAMS`.
- **`/help`:** Admin → `/help/praxisleitung`, sonst `/help/mitarbeitende`.
  - Erlaubte Bücher: Admin alle drei, Mitarbeitende `mitarbeitende` und `so-rechnet`.
  - Ein nicht erlaubtes Buch → Umleitung auf das Standardbuch.
  - Kopf mit drei Reitern (nur erlaubte).
- `imgBase='/help/img'`, `linkBase='/help'`, `variant` nach Breite: `wide` ab `lg` über eine CSS-Klassenweiche. Beide Varianten werden gerendert und per `hidden lg:block` / `lg:hidden` umgeschaltet. Kein `matchMedia` (SSR-Gleichheit mit pzweb).
- **`DocModal`** (Login-Seite): Reiter „Handbuch“ rendert `HandbookPage` Mitarbeitende `narrow`. Der Cheat-Sheet-Reiter bleibt.
- **`DocDrawer`:** Der Handbuch-Reiter entfällt, Schnellstart und Cheat-Sheet bleiben. `getDownloadUrl` (`DocDrawer.tsx:13-21`) wird entsprechend angepasst.

- [ ] **Step 1: Failing tests:**
  - `employee visiting /help/praxisleitung is redirected to /help/mitarbeitende`
  - `admin sees three tabs`
  - `employee sees two tabs`
  - `renders chapter anchors from content`
  - `sidebar handbook button links to /help/mitarbeitende for employees`
- [ ] **Step 2–4:** Implementieren, bis PASS. `npx tsc --noEmit`, `npm run build`.
- [ ] **Step 5: Commit** `feat(help): full-page graphic handbook in the app`

### Task 15: Kontexthilfe verlinkt Kapitel

**Files:**
- Modify: `frontend/src/constants/helpContent.tsx` (je Eintrag Feld `handbook?: { book: HandbookId; anchor: string }`), `frontend/src/components/HelpPanel.tsx` (Link „Im Handbuch ansehen →“)
- Test: `frontend/src/constants/helpContent.test.ts`

- [ ] **Step 1: Failing test:** `every helpContent handbook link resolves to an existing chapter or task id` (Review Focus 5) und `HelpPanel shows link for /time-tracking`.
- [ ] **Step 2–4:** Links für alle 12 Einträge setzen. PASS.
- [ ] **Step 5: Commit** `feat(help): context help links into the handbook`

### Task 16: Altes Handbuch entfernen, Prüfungen umziehen

**Files:**
- Modify: `frontend/src/components/DocViewer.tsx` (lösche `handbuchMitarbeiterSections` :297–440 und `handbuchAdminSections` :441–663 sowie den Handbuch-Reiter)
- Modify: `frontend/src/components/DocViewer.test.tsx` (Handbuch-Fälle :63–166 ziehen auf `content`-Daten um: dieselben Pflicht- und Verbotswörter, jetzt per `textOf` auf `HandbookPage`)
- Modify: `scripts/check-doc-sync.sh` (Gruppen `mitarbeiter`, `admin_*`, `begriffe`, `mirror`, `versionen`, `links` auf die erzeugten Dateien und neuen Namen; Gruppe `mirror` vergleicht die Download-Dateien jetzt gegen den Generator statt gegen `docs/`)
- Modify: `docs/handbuch/HANDBUCH-ERSTELLEN.md` (neuer Ablauf: `run.sh all`, `capture`, Kontaktseite, `handbuch:md`)
- Delete: `docs/handbuch/screenshots/`, `tools/handbook/*.js`, `e2e/capture-handbook-screenshots.ts`, `e2e/capture-new-features.ts`
- Modify: `CLAUDE.md` (Doku-Sync-Abschnitt: neue Quelle `frontend/src/handbuch/`, sechste Sync-Fläche pzweb-Kopie, Regel „neue oder geänderte UI → Shots neu aufnehmen“ für Tillwich-PRs)

**Wortlaut-Regel:** Eine `need`-Prüfung darf nur entfallen, wenn der Inhalt den Sachverhalt bewusst nicht mehr nennt. Jede entfernte Prüfung kommt mit Grund in die PR-Beschreibung (Liste in `docs/superpowers/plans/2026-11-10-handbuch-grafisch-entfallene-pruefungen.md`).

- [ ] **Step 1:** Prüfungen umziehen. `bash scripts/check-doc-sync.sh all` muss vorher (alter Stand) und nachher grün sein.
- [ ] **Step 2: Run** `cd frontend && npx vitest run --pool=threads --maxWorkers=2`. Expected: alles grün. Dann `npx tsc --noEmit`, `npm run lint`, `npm run build`.
- [ ] **Step 3: Run** `grep -rn "handbuchMitarbeiterSections\|handbuchAdminSections\|docs/handbuch/screenshots" frontend/src docs scripts`. Expected: keine Treffer.
- [ ] **Step 4: Commit** `refactor(help): replace text handbook with graphic handbook`

## Phase 4 — pzweb

pzweb-Arbeit im Branch `feat/handbuch-grafisch` von `origin/main` in einem Worktree `/home/manuel/claude/pzweb-handbuch`. Tests: `cd frontend && npx vitest run`, Build `npm run build`; die Tests laufen in Docker `node:20` laut CLAUDE.md-Doku-Sync-Hinweis, falls Host-Node bricht.

### Task 17: Sync-Skript und Gleichheitsprüfung

**Files:**
- Create (praxiszeit): `scripts/sync-handbuch-to-pzweb.sh`
- Modify: `scripts/check-doc-sync.sh` (Gruppe `handbuch_pzweb`)

**Interfaces:**
- Produces: `bash scripts/sync-handbuch-to-pzweb.sh [<pzweb-pfad>=../pzweb]`
  - kopiert `frontend/src/handbuch/**` (ohne `*.test.*`) nach `<pzweb>/frontend/src/handbuch/`
  - kopiert `frontend/public/help/img/*.webp` nach `<pzweb>/frontend/public/handbuch/img/`
  - stellt jeder `.ts`/`.tsx`-Datei die Kopfzeile `// GENERIERT aus phash/praxiszeit frontend/src/handbuch — nicht bearbeiten (scripts/sync-handbuch-to-pzweb.sh)` voran
  - löscht dort Dateien, die es in der Quelle nicht mehr gibt (`rsync --delete`)
- **`handbuch_pzweb`:** Fehlt `../pzweb` (bzw. `$PZWEB_DIR`), meldet die Gruppe „übersprungen“ mit Exit 0. Sonst führt sie das Sync-Skript in ein Temp-Verzeichnis aus und vergleicht per `diff -r`. Bei Abweichung ist der Exit nicht 0.

- [ ] **Step 1:** Skript schreiben und gegen `/home/manuel/claude/pzweb-handbuch` ausführen. Expected: Dateien vorhanden, Kopfzeilen gesetzt.
- [ ] **Step 2: Run** `PZWEB_DIR=../pzweb-handbuch bash scripts/check-doc-sync.sh handbuch_pzweb`. Expected: PASS. Dann eine Datei in pzweb ändern. Expected: FAIL. Änderung zurücknehmen.
- [ ] **Step 3: Commit** (praxiszeit) `feat(handbuch): sync to pzweb with equality check`; (pzweb) `chore(handbuch): generated handbook copy`

### Task 18: Kopfleiste mit Dropdown und Handy-Menü

**Files:**
- Create: `pzweb/frontend/src/components/layout/HandbuchMenu.tsx`, `MobileMenu.tsx`
- Modify: `pzweb/frontend/src/components/layout/Header.tsx:52-84`
- Test: `pzweb/frontend/src/components/layout/Header.test.tsx`

**Interfaces:**
- **Desktop:** Disclosure-Button „Handbuch“ (`aria-expanded`, `aria-controls`) mit vier Links:

  | Label | Unterzeile | Ziel |
  |---|---|---|
  | „Für Mitarbeitende“ | „Stempeln, Urlaub, Anträge“ | `/handbuch/mitarbeitende` |
  | „Für die Praxisleitung“ | „Team, Genehmigungen, Berichte“ | `/handbuch/praxisleitung` |
  | „So rechnet PraxisZeit“ | „Soll, Ist, Saldo, Urlaub erklärt“ | `/handbuch/so-rechnet-praxiszeit` |
  | „Installation & Update“ | „Windows, Linux, macOS“ | `/anleitung` |

  Schließt bei Escape, bei Klick außerhalb und bei Routenwechsel. Ohne JS (Prerender) ist das Menü als `<details>`-Fallback bedienbar: Das Element ist ein `<details>`, das per JS gesteuert wird.
- Der bisherige Link „Anleitung“ entfällt in der Kopfleiste (steckt im Dropdown).
- **Unter `md`:** Hamburger öffnet `MobileMenu` mit allen Marketing-Links inklusive Handbuch-Gruppe.

- [ ] **Step 1: Failing tests:**
  - `marketing header shows Handbuch button`
  - `click opens menu with four links and correct hrefs`
  - `escape closes and returns focus`
  - `mobile menu contains handbook links`
  - `renderToString of header contains details fallback`
- [ ] **Step 2–4:** Implementieren, bis PASS.
- [ ] **Step 5: Commit** `feat(nav): handbook dropdown and mobile menu`

### Task 19: Routen, SEO, Umleitungen, Altseiten weg

**Files:**
- Create: `pzweb/frontend/src/pages/marketing/handbuch/{HandbuchHub,HandbuchSeite}.tsx`, Tests daneben
- Modify: `pzweb/frontend/src/AppRoutes.tsx` (vier Routen, alte drei raus), `pzweb/frontend/src/seo/routes.ts` (vier Einträge mit `techArticle`/`breadcrumb`; alte raus), `pzweb/frontend/src/seo/llms.ts:22`, `pzweb/frontend/src/components/layout/Footer.tsx:9-15` (`DOKU_LINKS`), `pzweb/frontend/src/pages/marketing/anleitung/AnleitungHub.tsx:244-256`
- Modify: `pzweb/frontend/nginx.conf`: `location = /anleitung/handbuch-mitarbeiter { return 301 /handbuch/mitarbeitende; }`, analog `handbuch-admin` → `/handbuch/praxisleitung` und `berechnungen` → `/handbuch/so-rechnet-praxiszeit`. Die Blöcke stehen VOR `location /`. CSP-Header-Regel beachten: `add_header` je location, siehe `nginx.conf:15-16`.
- Delete: `pzweb/frontend/src/pages/marketing/anleitung/{HandbuchMitarbeiter,HandbuchAdmin,AnleitungBerechnungen}.tsx` und deren Tests.

**Interfaces:**
- `HandbuchSeite({ book: HandbookId })` rendert `HandbookPage` mit:
  - `imgBase='/handbuch/img'`
  - `linkBase='/handbuch'` (`handbuch:so-rechnet` → `/handbuch/so-rechnet-praxiszeit`; Mapping-Funktion im generierten Code über `linkBase` plus `BOOK_SLUGS`, siehe Task 1 `renderInline`. Task 1 `InlineOpts.slugs`)
  - beide Varianten, per Klasse umgeschaltet

  `HandbuchHub`: drei Kacheln plus Kachel Installation.

- [ ] **Step 1: Failing tests:**
  - `seo routes contain /handbuch/*` (der bestehende `routes.test.ts` erzwingt das automatisch)
  - `HandbuchSeite renders all chapter titles of mitarbeitende`
  - `all handbook images exist in public/handbuch/img and match manifest pxWidth/pxHeight` (WebP-Header-Parser aus `Rundgang.test.tsx:10-27` wiederverwenden, nach `src/test/webp.ts` auslagern)
  - `footer links point to /handbuch/*`
- [ ] **Step 2–4:** Implementieren, bis PASS. `npm run build` (inkl. Prerender) muss grün sein, `dist/handbuch/mitarbeitende/index.html` enthält die Kapiteltitel.
- [ ] **Step 5: Run** nginx-Umleitung gegen den gebauten Container (`docker build` pzweb-Frontend, `curl -sI localhost:<port>/anleitung/handbuch-admin` → `301` mit `Location: /handbuch/praxisleitung`).
- [ ] **Step 6: Commit** `feat(handbuch): graphic handbooks replace text guides`

### Task 20: Broschüre mit Screenshots

**Files:**
- Modify: `pzweb/frontend/src/pages/marketing/broschuere/Broschuere.tsx:21-196` (Szenen-Import auf `src/handbuch/comics`, `BrochureSection` mit optionalem `shot` aus `BROSCHUERE_SHOTS`, neue Sektion „team“ mit Shot plus Comic `uebersicht` oder neuer Szene)
- Delete: `pzweb/frontend/src/pages/marketing/broschuere/{ComicKit,Scene*}.tsx`
- Create: `pzweb/scripts/broschuere-pdf.mjs` (Playwright `page.pdf({ format: 'A4', printBackground: true })` gegen `vite preview`, schreibt `frontend/public/broschuere/praxiszeit-broschuere.pdf`)
- Test: `pzweb/frontend/src/pages/marketing/broschuere/Broschuere.test.tsx`

- [ ] **Step 1: Failing tests:**
  - `each brochure section with a shot renders an svg figure with markers ≤ 3`
  - `comics still render in all sections`
  - `no import from ./ComicKit remains`
- [ ] **Step 2–4:** Implementieren, bis PASS. PDF erzeugen, Seite 1–3 ansehen (Read-Tool auf PDF).
- [ ] **Step 5: Commit** `feat(broschuere): real screenshots next to the comics`

## Phase 5 — Abschluss

### Task 21: Gesamtprüfung

- [ ] **Step 1: Run** `bash scripts/local-ci.sh` (praxiszeit). Expected: alle Schritte grün. Dann pzweb `npx vitest run` und `npm run build`.
- [ ] **Step 2: Breitenprüfung (Review Focus 2):** Playwright-Skript `e2e/handbuch/width-check.ts`. Es öffnet je Handbuch die App-Route (`:8099/help/...`) und die pzweb-Preview-Route bei 390 px Breite und prüft `document.documentElement.scrollWidth <= 390`. Expected: PASS für alle sechs.
- [ ] **Step 3: Sichtprüfung:** Kontaktseite komplett durchsehen. Jede Markierung sitzt, kein Testmüll, Version im Bild (Seitenleiste `v…`) = `frontend/package.json`.
- [ ] **Step 4: Whole-branch-Review** (beide Repos) mit `superpowers:requesting-code-review`. Funde ≤ medium beheben.
- [ ] **Step 5: `/buildrelease`-Skill ergänzen** (`~/.claude/skills/buildrelease/SKILL.md`): nach dem Versions-Bump `bash e2e/handbuch/run.sh all && npm run handbuch:md && bash scripts/sync-handbuch-to-pzweb.sh`, pzweb-PR mit dem Release mergen.
- [ ] **Step 6:** `bash e2e/handbuch/run.sh down`. Beide Branches pushen und PRs öffnen (praxiszeit gegen `master`, pzweb gegen `main`), erst nach Manuels Freigabe. PR-Texte mit der Liste entfallener Prüfungen (Task 16).
