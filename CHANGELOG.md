# Changelog

## [Unreleased]

## [1.4.3] - 2026-05-03

### 🚀 Wizard — drei neue Pages: Installationsort, Ports, Lizenz
- **Install-Location-Page** zwischen Welcome und Konfiguration. User kann
  den Pfad explizit waehlen (Default `C:\PraxisZeit`), Update-Mode
  blockt das Feld auf den existierenden Pfad. Wenn der User Fresh-Install
  ausgewaehlt hat, der Pfad aber bereits eine Installation enthaelt,
  blendet sich eine rote Warnung ein mit zwei CTAs: "Auf Update
  umschalten" oder "Anderen Pfad waehlen". Continue ist gesperrt bis
  der Konflikt aufgeloest ist — verhindert versehentliches
  Daten-Clobbern.
- **Ports-Page** im Fresh/Repair-Flow. HTTPS-Port (Default 443) und
  HTTP-Redirect-Port (Default 80, abschaltbar). Live-Validation auf
  Range 1..65535 + Identitaets-Konflikt; zusaetzlich nicht-blockierende
  Warnung wenn ein Port laut `IPGlobalProperties.GetActiveTcpListeners`
  bereits belegt ist (z.B. anderer Webserver auf dem Setup-Server).
  Neuer Conf-Key `[server].http_redirect_port`, vom Backend in
  `config.py:_TOML_KEY_MAP` aufgenommen.
- **License-Page** im Fresh- *und* Update-Flow (im Update-Pfad fuer
  Lizenz-Erneuerung). User kann entweder einen Lizenz-Token einfuegen /
  per File-Picker eine `.key` waehlen ODER 30 Tage Demo starten.
  Live-Validierung gegen den gleichen Ed25519-Public-Key wie das Backend
  via BouncyCastle (.NET 10 hat keine native Ed25519-Unterstuetzung).
  Bei erfolgreicher Validierung zeigt der Wizard Kunde, Mitarbeiter-
  Limit und Ablaufdatum an. Bei Demo-Mode wird `demo_expires_at` in
  `praxiszeit.conf` geschrieben; Backend erkennt das in `main.py`
  Lifespan und schaltet ab dem Datum in Read-Only.

### 🐞 Wizard-UX-Fixes (aus Customer-Feedback)
- "Bitte warten..."-Button blieb stehen, obwohl die Installation
  fertig war: `NextButtonText` auf `ProgressPageViewModel` ist jetzt
  state-aware (`IsRunning ? "Bitte warten..." : "Weiter"`) und wird
  via `OnIsRunningChanged` neu emittiert.
- Button-Beschriftungen waren links-aligned trotz fixer MinWidth —
  `HorizontalContentAlignment="Center"` auf `.primary`, `.ghost`,
  `.success` ergaenzt.
- DonePageView ohne aeusseren ScrollViewer; bei DPI ≥ 125 % wurde
  der "Schliessen"-Button abgeschnitten. Wrap im ScrollViewer.
- Default-Window von 820x640 auf 900x720 (Min 780x620) — die jetzt
  vorhandenen 6 Pages und der Step-Indicator brauchten mehr Platz.

### Backend — Demo-Mode + Server-Port-Settings
- `LICENSE_DEMO_EXPIRES_AT` (TOML `[license].demo_expires_at`) und
  `SERVER_PORT` / `SERVER_HTTP_REDIRECT_PORT` (TOML `[server].port` /
  `http_redirect_port`) als neue Settings in `app/config.py`.
- `app/main.py` Lifespan: ohne `LICENSE_KEY_PATH` aber mit
  `LICENSE_DEMO_EXPIRES_AT` → Demo-Mode bis zum Datum, danach
  Read-Only (`set_license_state(None, read_only=True)`). Mit echter
  Lizenz unveraendert.

### Tests
- 31 neue Tests (Total 104 / 104 grün) in
  `installer/setup/tests/PraxisZeit.Setup.Core.Tests`:
  Port-Range/Konflikt-Validation, Conf-Roundtrip mit Custom-Ports,
  `demo_expires_at`-Serialisierung, License-Validator
  Negative-Paths (leerer Token, falsches Segment-Count, Non-EdDSA-
  Algorithm, Random-Signatur). License-Positive-Path-Tests laufen im
  Backend (`test_native_mode.py`) gegen denselben Public-Key.

## [1.4.2] - 2026-05-03

### 🐞 Bugfix — Tailwind v4 Spacing-Regression (alle `p-*`/`m-*`/`space-*`)
- **Symptom**: Karten ohne Innen-Padding, Sidebar-Items ohne `px-4 py-3`,
  `Budget`/`Genommen` ohne Spacing — die Oberflaeche sah komplett "kaputt"
  aus, obwohl Hintergruende, Schatten, Rahmen und runde Ecken alle korrekt
  rendeten. Nur die Spacing-Utilities waren stillgelegt.
- **Root Cause**: `frontend/src/index.css` hatte einen globalen
  `* { margin: 0; padding: 0; box-sizing: border-box; }`-Reset *ausserhalb*
  jedes `@layer`. Tailwind v4 wickelt jede Utility in `:where(...)` ein,
  damit User sie mit einfachen Selektoren ueberschreiben koennen — d.h.
  `:where(.p-6)` hat Specificity 0,0,0. Der unlayered `*`-Selektor hat
  ebenfalls 0,0,0, gewinnt aber trotzdem, weil **unlayered Regeln in der
  Cascade ueber layered Regeln stehen**. Ergebnis: jede `p-*`, `m-*`,
  `px-*`, `space-x-*`, `space-y-*` wurde stillschweigend von dem Reset
  ueberschrieben.
- **Fix**: Reset in `@layer base` packen. `@layer base` steht in der
  Tailwind-v4-Reihenfolge unter `@layer utilities`, also gewinnt
  `:where(.p-6)` wieder ueber das `*`. `box-sizing` ist im Reset entfallen,
  weil Tailwind-v4-Preflight das schon auf `*, ::before, ::after` setzt.
- Verifiziert end-to-end im Browser (Playwright gegen lokalen Docker-
  Stack): Card-Padding `0px → 24px`, Nav-Item-Padding `0px → 12px 16px`.
  Sidebar, Karten und Layout sind wieder so, wie sie vor 1.4.0 aussahen.

## [1.4.1] - 2026-05-03

### 🐞 Bugfix — CSS-Bruch nach Update bei stale Service-Worker
- **Symptom**: Nach Update auf 1.4.0 lieferte ein Native-Install dem Browser
  fuer alte hashed CSS-URLs (`/assets/index-OLDHASH.css`) die `index.html`
  zurueck — `200 OK` mit `Content-Type: text/html`. Browser verwirft das
  als Stylesheet, Seite landet komplett ungestyled, bis der User den
  Service Worker manuell unregistert. Erstmals durch Tailwind v3 → v4 in 1.4.0
  ausgeloest, weil sich saemtliche Asset-Hashes aenderten.
- **Root Cause**: `SPAFallbackMiddleware` in `backend/app/main.py` lieferte
  bei *jedem* GET-404 ausserhalb `/api/` die `index.html` aus — auch fuer
  Asset-Pfade. Stale-SW-Klienten bekamen so HTML als CSS und cachten den
  kaputten Zustand.
- **Fix**: Asset-foermige Requests (letztes Pfad-Segment hat eine Endung,
  kein `Accept: text/html`) bekommen jetzt einen echten 404. `/assets/*`
  short-circuit-t unabhaengig vom Accept-Header. SPA-Navigationen
  (`Accept: text/html`) erhalten weiterhin `index.html`. Damit erholt
  sich jeder Browser beim naechsten Refresh selber.
- **Bonus**: Die SPA-Fallback-Response umging bisher die `SecurityHeaders`-
  Middleware — `/login` & Co. lieferten *keine* CSP/HSTS/X-Frame-Options.
  Die Fallback-Response uebernimmt diese Header jetzt aus der inneren
  Middleware-Kette (Defence-in-Depth-Parity mit Docker-Mode + nginx).
- **Refactor**: `SPAFallbackMiddleware` aus dem `if SERVE_FRONTEND:`-Block
  in `backend/app/main.py` nach `app/middleware/static_serving.py`
  ausgelagert (importierbar, testbar). 10 Unit-Tests in
  `backend/tests/test_spa_fallback.py` decken Asset-404, Navigation-mit-
  index.html, Header-Propagation und SPA-Routes-mit-Punkt ab.

### 🚀 Feature — ConfigPage im Setup-Wizard (Erst-Admin-Setup)
- Neue Wizard-Page **"Konfiguration"** zwischen Welcome und Progress,
  nur im Fresh-Install / Repair-Modus aktiv. Fragt Praxis-Stammdaten
  (Name, Adresse, Bundesland-Dropdown mit allen 16 Bundeslaendern fuer
  Feiertags-Sync) und den Admin-Account (Username, Email, Vor-/Nachname,
  Passwort + Wiederholung) ab. Live-Validation matched 1:1 die
  Backend-Bootstrap-Regeln (`backend/app/main.py:_WEAK_ADMIN_PASSWORDS`,
  Min-Length 12) — der Wizard kann nichts durchwinken, was das Backend
  beim Start ablehnen wuerde.
- **PraxisZeitConfigWriter** (Core) generiert daraus eine vollstaendige
  TOML-`praxiszeit.conf` mit korrekt-escaped Strings (Backslash, Quotes,
  Steuerzeichen via `\uXXXX`). Schreibt UTF-8 **ohne BOM** (sonst bricht
  der Backend-TOML-Parser, F-053). Default-Sektionen ([server],
  [database], [security], [backup] etc.) bleiben bei sicheren Werten.
- **ScriptRunner** akzeptiert optional `PraxisZeitConfigValues`: nach
  dem File-Copy aber **vor** `setup.bat` wird die User-Config nach
  `<installDir>\config\praxiszeit.conf` geschrieben. setup.bat sieht
  das File schon und ueberspringt die `conf.example`-Vorlage —
  Backend-Bootstrap legt beim ersten Service-Start den User-gewaehlten
  Admin an, kein "BITTE_AENDERN"-Crash mehr.
- **Update-Pfad bleibt unangetastet**: ConfigPage wird nur fuer
  Fresh/Repair gebaut, im Update behaelt der Wizard die existierende
  praxiszeit.conf (User-Anpassungen wuerden sonst ueberschrieben).
- Step-Indicator im Footer wird **dynamisch** aus der Page-Anzahl
  generiert (3 Dots fuer Update, 4 Dots fuer Fresh). Welcome,
  ConfigPage und Done bekommen Animation/Brand-Colors fuer aktiven
  und abgeschlossenen Status.
- Done-Page zeigt jetzt eine konkrete Login-Anweisung ("Sie koennen
  sich jetzt mit dem Admin-Account `<username>` anmelden") statt der
  alten Formulierung "muss config\\praxiszeit.conf einmalig angepasst
  werden". Customer-Onboarding-Flow ist damit komplett unattended.
- 30 neue Unit-Tests fuer `PraxisZeitConfigWriter` (TOML-Escaping,
  Validation matched Backend-Regeln, UTF-8-ohne-BOM-Roundtrip).
  Gesamt-Testanzahl im Setup-Projekt: **73 / 73 grün**.

## [1.4.0] - 2026-04-25

### 🚀 Feature — Single-File `setup.exe` mit eingebettetem Payload
- **Eine Datei, ein Doppelklick**: `praxiszeit-1.4.0-setup-windows-x64.exe`
  (~445 MB) enthält jetzt das **komplette Payload** (Python-Embeddable,
  PostgreSQL-Installer, Backend, Frontend, nssm, alle .bat/.ps1-Scripts)
  als embedded resource. Beim Doppelklick (UAC → Admin) extrahiert die
  EXE den Payload nach `%TEMP%\praxiszeit-setup-<guid>` und ruft die
  bestehenden Install-Scripts auf — kein vorheriges ZIP-Entpacken,
  kein .NET-Runtime auf dem Zielserver. Cleanup nach Abschluss.
- **DB-Backup vor Update ist Pflicht** und wird in der Welcome-Page
  explizit beworben. Update-Pfad ruft `update-wizard.ps1 -Headless`
  auf, dessen Schritt 2 ein vollstaendiges `pg_dump` nach
  `data\backups\` schreibt — auch bei spaeterem Fehler bleiben alle
  Daten unversehrt.
- **Architektur-Entscheid**: Wir reimplementieren die 1436+ Zeilen
  bewaehrter `.bat`/`.ps1`-Logik (cp1252-Edge-Cases, Junctions,
  EDB-Aufraeumung, RLS-Kontext, robocopy-Excludes, F-037 ACL-Fix)
  bewusst NICHT in C#. Die EXE ist eine GUI-Huelle, die die getesteten
  Scripts unveraendert ausfuehrt → ZERO Regressionsrisiko fuer die
  Install-Logik beim Kunden.
- `update-wizard.ps1` neuer `-Headless`-Switch: ueberspringt die
  WinForms-GUI komplett und emittiert maschinenlesbare Marker
  (`[STEP] <id> <status>`, `[LOG] <text>`, `[PROGRESS] <0..100>`,
  `[DONE] <success|fail>`) auf stdout. Avalonia-Wizard parst die
  Marker und rendert daraus Step-Liste, Live-Log und Progress-Bar.
  Default-Verhalten (ohne `-Headless`) unveraendert — der bestehende
  WinForms-Wizard ist 1:1 funktional als Fallback verfuegbar.
- `setup.bat` und `install-service.bat` honorieren ab sofort
  `PRAXISZEIT_NONINTERACTIVE=1` und ueberspringen alle `pause`-Aufrufe
  → der Avalonia-Wizard kann beide unattended ausfuehren ohne
  Subprocess-Hang. Default-Verhalten (manuelles Aufrufen) unveraendert.

### 🛠️ Setup-Wizard — neue Pages, Orchestrator, Live-Progress
- **Progress-Page** (`ProgressPageView.axaml`): zwei-spaltiges Layout
  mit checklistartiger Step-Liste (Status-Punkte: Pending grau →
  Running blau → Ok gruen / Warn gelb / Fail rot) links und
  Konsolen-Log rechts (Consolas, 1000-Line-Cap), oben dezenter
  Progress-Bar in Brand-Primary. Refektiert pro Modus die genauen
  Schritte: Update zeigt 7 Schritte (ACL/Backup/Stop/Copy/Pip/Start/
  Task), Fresh-Install 4 (Copy/Setup/Service/Start).
- **MainWindowViewModel**: orchestriert Welcome → Progress → Done.
  Auf Welcome-"Weiter" extrahiert `EmbeddedPayloadExtractor` das
  ZIP, der `ScriptRunner` startet den passenden Subprocess, Marker
  fliessen via `IProgress<RunnerEvent>` als typed events
  (`RunnerStepEvent`/`RunnerLogEvent`/`RunnerProgressEvent`/
  `RunnerDoneEvent`) in die ViewModel-Layer. UI marshaling via
  `Progress<T>`-SyncContext-Capture, kein `Dispatcher.Post`-Boilerplate.
- **DonePage**: differenziert Erfolg (gruener Checkmark + URL-Karte +
  "Im Browser oeffnen"-Button) vs. Fehler (roter X-Kreis + Hinweis
  auf das automatische DB-Backup unter `data\backups`).
- **Welcome-Page**: zeigt im Update-Modus einen prominenten
  Backup-Callout ("Datenbank wird vor dem Update gesichert"), damit
  dem Anwender klar ist, dass `pg_dump` automatisch laeuft.
- **app.manifest**: `requireAdministrator` + `dpiAwareness=PerMonitorV2`
  → automatischer UAC-Prompt beim Doppelklick, scharfes Rendering
  auf High-DPI-Displays.
- **Step-Indicator** im Footer: 3 Dots (Welcome / Installation /
  Fertig) zeigen Fortschritt durch die Wizard-Stages, aktiver Step
  in Brand-Primary, abgeschlossene Steps in Accent-Green.

### 🎨 UI — Installer-Redesign
- Neue zentrale Markenpalette in `App.axaml` (Primary `#0E5BA8`,
  Accent `#13B981`) plus globale Button-Klassen (`primary`, `success`,
  `ghost`) und Card-/Pill-Styles.
- `MainWindow.axaml`: Gradient-Header mit stilisiertem Uhren-Logomark,
  Versions-Pill rechts, Step-Indikator-Punkte im Footer. Fenster auf
  820 × 640 vergrößert, hellgraue Surface-Background-Farbe.
- `WelcomePageView.axaml`: Card-Layout mit Icon-Tiles (Plattform,
  Pfad, aktuelle Version, neue Version), klare Typo-Hierarchie.
- `DonePageView.axaml`: gruener Erfolgs-Checkmark im Gradient-Kreis
  mit Soft-Shadow, "Im Browser oeffnen"-Action-Button, separater
  Fehler-Path mit rotem X-Kreis.

### 🔢 Version-Bump
- `backend/app/core/updater.py`, `frontend/package.json` (+ Lockfile)
  und `tools/build-release.sh` von **1.3.7 → 1.4.0**. Der
  Build-Konsistenz-Check (F-055-Followup) haelt die Stellen synchron.

### 📦 Build-Pipeline
- `tools/build-release.sh` Phase 5: erst Windows-Tree zusammenbauen,
  dann **Payload-ZIP als Build-Artefakt** unter
  `build/payload-X.Y.Z-windows-x64.zip`, dann `dotnet publish` mit
  `-p:PayloadZipPath=...` → EXE bekommt das ZIP als Manifest-Resource
  mit stabilem `LogicalName=praxiszeit_payload.zip`. Output-Naming:
  `praxiszeit-${VERSION}-setup-windows-x64.exe` damit der
  Phase-7-`sha256sum`-Glob die EXE mit aufnimmt. Fallbacks fuer
  fehlendes `.NET-SDK` und fehlendes `zip` (PowerShell
  `Compress-Archive`) sind erhalten.

## [1.3.7] - 2026-04-23

### ✨ Feature — Urlaub / Anträge stornieren (Issue #90)
- **`DELETE /api/vacation-requests/{id}`** erlaubt zusätzlich zur
  bisherigen PENDING-Zurücknahme jetzt auch das Stornieren eines
  bereits **genehmigten** Antrags, solange der Zeitraum noch
  **in der Zukunft** liegt (`vr.date > heute`). Beim Storno werden
  die zugehörigen `Absence`-Tage (matched auf `user_id`, Datumsbereich
  der VR, gleicher `absence_type`) gelöscht, ein Audit-Log-Eintrag pro
  Tag geschrieben (`source=vacation_request_cancel`), und die VR auf
  `withdrawn` geflipt. Angefangene/abgelaufene Urlaube sind bewusst
  nicht stornierbar (Arbeitstag ist bereits ausgefallen).
- **Neuer Admin-Endpoint `DELETE /api/admin/vacation-requests/{id}`**
  mit identischer Semantik für Admin-on-behalf-Storno; tenant-scoped
  und per `with_for_update()` gegen Race-Conditions beim gleichzeitigen
  Approve/Cancel-Click abgesichert.
- **Frontend**: "Stornieren"-Button jetzt auch bei genehmigten
  zukünftigen Urlauben sichtbar — im Mitarbeiter-Kalender
  (`AbsenceCalendarPage`) und auf der Admin-Seite
  (`VacationApprovals`). Bestätigungsdialog erklärt, dass die
  Abwesenheitstage mitgelöscht werden.
- **Tests:** Neues `tests/test_vacation_request_cancel.py` (11 Cases)
  deckt alle 4 VR-Status × {future, today, past} × {employee, admin,
  cross-user} Kombinationen ab.

### 🟡 Security — Dependency-Patches (Issue #85)
- **`python-dotenv` 1.0.* -> >=1.2.2** (GHSA-mf9w-mj56-hr94) —
  Symlink-following in `set_key()` erlaubte Arbitrary-File-Overwrite
  via Cross-Device-Rename-Fallback. Nur indirekt durch
  pydantic-settings `.env`-Loading genutzt; Pin hebt Floor auf das
  gepatchte Release.
- **`Tmds.DBus.Protocol` 0.90.3 -> 0.92.0** (GHSA-xrw6-gwf8-vvr9,
  HIGH) — malicious D-Bus peers konnten Signals spoofen und FDs
  erschoepfen. Transitive Dep von Avalonia 12.0.0 im neuen
  `installer/setup/` Projekt; expliziter `PackageReference`-Pin
  in `PraxisZeit.Setup.csproj` bis Avalonia selbst bumped. Macht
  den `dotnet build` NU1903-Warn-Free.

### 🧹 Cleanup
- Template-Stub `installer/setup/src/PraxisZeit.Setup.Core/Class1.cs`
  aus `dotnet new classlib`-Scaffolding entfernt (Issue #87).

### 📝 Docs
- `CLAUDE.md` "Native Installer" erweitert um Abschnitt zum
  Avalonia-Installer unter `installer/setup/` inkl. Build-Commands,
  .NET 10 Abhaengigkeit und Solution-Struktur; Hinweis auf
  `tools/generate-self-signed-cert.py` und auf die BOM-Falle in
  `praxiszeit.conf` (Issue #86).

## [1.3.6] - 2026-04-17

**Hotfix-Release direkt im Anschluss an 1.3.5.** Behebt zwei Fehler
die beim Live-Update eines Kundenservers sofort aufgefallen sind:
Footer-Versionsanzeige und kaputter `Step-PipInstall` im Update-
Wizard.

### 🔴 Frontend-Footer zeigte falsche Version
- **`frontend/package.json` von 1.3.0 auf 1.3.6** gebumpt. Das Feld
  wird in `vite.config.ts` als `__APP_VERSION__`-Define eingebettet
  und in `Layout.tsx:345` als `v{__APP_VERSION__}` im Footer
  gerendert. Seit Release 1.3.0 hat niemand es mehr hochgezogen —
  alle 1.3.1/1.3.2/1.3.3/1.3.4/1.3.5-Pakete haben Backend-Version
  korrekt aber Footer falsch ("v1.3.0") angezeigt. Backend
  (`/api/health`) war immer korrekt, nur die UI hat gelogen.
- **`tools/build-release.sh` Version-Drift-Check** — vor dem Frontend-
  Build wird jetzt `frontend/package.json` gegen `APP_VERSION`
  validiert und der Build bricht mit klarer Fehlermeldung ab wenn
  die zwei divergieren. Verhindert den Rueckfall.

### 🔴 Update-Wizard pip-Install crashte auf Kundenserver
- **F-056: `installer/windows/update-wizard.ps1 Step-PipInstall`** —
  fuehrt jetzt `get-pip.py --force-reinstall` **vor** dem
  `pip install -r requirements.txt` aus. Ursache war: `Step-CopyFiles`
  nutzt Robocopy mit Excludes fuer `data/`, `config/`, `logs/`, aber
  nicht fuer `bin/python/Lib/site-packages/`. Robocopy merged Files,
  loescht aber keine stale Dateien. Beim 1.3.3 -> 1.3.5 Update ist
  dadurch `pip._vendor.resolvelib/` in einem inkonsistenten Mix aus
  alten + neuen Files gelandet und `pip install` hat mit
  `ImportError: cannot import name 'RequirementInformation' from
  pip._vendor.resolvelib.structs` gecrasht. `get-pip.py
  --force-reinstall` baut pip + vendored deps sauber neu, macht den
  Schritt idempotent.

## [1.3.5] - 2026-04-17

**Audit-Response-Release.** Adressiert die Findings aus einem kritischen
Security-/ArbZG-/UX-/Test-Audit (PR #89). Kern: zwei neue Middleware-
Ebenen (License-Readonly, Request-Size-Limit), neuer Superadmin-Router
fuer §16-Notfall-Export, TOTP-Replay-Schutz per DB-Migration, neue
Admin-Change-Request-UI, sowie ein Frontend-Util das ArbZG-Warnungen
einheitlich anzeigt. Reiner Additiv-Release, keine Breaking Changes
ggue. 1.3.4.

### 🔴 Security — Dependency-CVEs gepatcht
- **`axios` 1.13.5 -> 1.15.0** (GHSA-3p68-rc4w-qgx5, GHSA-fvcv-3m26-pcqx)
  — NO_PROXY Hostname Normalization Bypass + Cloud Metadata
  Exfiltration via Header Injection Chain (beide SSRF-Eskalations-
  Vektoren, beide fixed in 1.15.0).
- **`follow-redirects` 1.15.11 -> 1.16.0** (GHSA-r4q5-vmmm-2653) —
  leaks Custom Authentication Headers to Cross-Domain Redirect
  Targets. Ueber `overrides` in `frontend/package.json` forciert, da
  transitive Dep via axios.
- **`pytest` 8.x -> >=9.0.3** (GHSA-6w46-j5rx-g56g) — vulnerable
  tmpdir handling.

### 🔴 Security
  `users`-Table ein `last_totp_counter` (bzw. Replay-Tracking) hinzu.
  Verhindert, dass ein bereits akzeptierter 6-stelliger TOTP-Code im
  selben 30-Sek-Fenster ein zweites Mal akzeptiert wird.
  Test: `tests/test_totp_replay.py`.
- **LicenseReadOnlyMiddleware** (`app/middleware/license.py`) — blockt
  alle schreibenden HTTP-Methoden (POST/PUT/PATCH/DELETE) bei
  abgelaufener Lizenz mit `403` und liefert nur noch Read-Only-API.
  Registriert global in `main.py`, deckt damit neue Writer-Endpoints
  automatisch ab (keine Per-Route-Dependency noetig).
- **Request-Size-Limit** — Middleware-Enforcement fuer Body-Groesse
  plus Regressions-Test `tests/test_request_size_limit.py`.
- **Cross-Tenant-API-Tests** (`tests/test_cross_tenant_api.py`,
  224 LOC) — systematische Negativ-Tests gegen alle Tenant-ueberquerende
  Angriffsvektoren (Read/Write/Delete auf fremde `tenant_id`).
- **Concurrency-Tests** (`tests/test_concurrency.py`, 170 LOC) —
  Postgres-only Race-Tests fuer `clock_out` / Absence-Unique-Constraint
  / Change-Request-Approval.

### 🟡 Superadmin / DSGVO-Art.20
- **Neuer Superadmin-Router** `/api/superadmin/*`
  (`app/routers/superadmin.py`, 205 LOC). Erfordert User **ohne**
  `tenant_id` (`require_superadmin`-Dependency). Zweck: §16-Notfall-
  Export deaktivierter Tenants. Setzt `set_superadmin_context(db)` um
  RLS zu umgehen und kann tenant-uebergreifend lesen/exportieren.

### 🟡 Change-Request-Workflow
- **Admin-Change-Requests-UI** (`pages/admin/ChangeRequests.tsx`,
  130 LOC) — endlich ein Admin-Frontend fuer die CR-Approval. Davor
  war das nur ueber die API ansteuerbar.
- **Precondition-Checks vor Status-Aenderung** in
  `admin_change_requests.py` (Race-Condition-Fix) +
  `change_request.py` Schema erweitert.

### 🟡 ArbZG-Warnings (Frontend)
- **Neues Util `utils/arbzgWarnings.ts`** + Tests
  (`arbzgWarnings.test.ts`). Alle ArbZG-Warnungen aus API-Responses
  werden ab jetzt zentral ueber `showArbzgWarnings(toast, warnings)`
  angezeigt. `StampWidget` und `TimeTracking` wurden umgestellt —
  statt duplizierten `if warnings.includes(...)`-Bloecken pro Seite.
- **ToastContext**: severity-basierte Default-Dauern (success 3s,
  error 8s, warning 6s, info 5s) damit Ruhezeitwarnungen lang genug
  stehen. Aufrufer muessen die Dauer **nicht** mehr pro Call setzen.

### 🟡 Exporte
- **ODS-Export** (`ods_export_service.py`) — Review-Fixes + neuer Test
  `tests/test_ods_export_service.py` (125 LOC).
- **reports.py** um ~80 LOC erweitert (Multi-Entry-Export + Report-
  Fixes, deckt die Mehrfachbuchung pro Tag korrekt ab).

### 🟡 Middleware / Infrastruktur
- **`middleware/static_serving.py`** — SPA-Fallback-Middleware (+75
  LOC): saubere Trennung zwischen API-Pfaden und SPA-Routes fuer den
  Native-Modus (`SERVE_FRONTEND=True`).
- **`middleware/auth.py`** — kleinere Haerteanpassungen (+15 LOC).
- **`auth_service.py`** +60 LOC, **`auth.py` Router** angepasst fuer
  TOTP-Replay + Login-Haertung.

### 🟡 Build / CI
- **`scripts/local-ci.sh`** gruendlich ueberarbeitet — split nach
  SQLite-Unit vs Postgres-Integration (RLS + Concurrency),
  vitest/tsc/eslint/vite build/e2e in einem Wrapper.
- **`frontend/vite.config.ts` + `tsconfig.json`** — Test-Pfade
  integriert, neue Frontend-Utils (`errorMessage.test.ts`,
  `formatters.test.ts`) laufen jetzt in der CI.
- **`deploy.sh`** um Smoke-Test-Steps erweitert (+14 LOC).

### 📝 Vorbereitung fuer 1.4.0
- **Avalonia-UI-Installer-Scaffolding** unter `installer/setup/`
  (C# / Avalonia, `1.4.0-alpha.1`). Noch **nicht** Teil des
  ausgelieferten Pakets — wird ab 1.4.0 als `praxiszeit-setup.exe`
  den NSSM/setup.bat-Stack bei Neuinstallationen ersetzen.

## [1.3.4] - 2026-04-11

**Massives Cleanup-Release nach einer Live-Debugging-Session auf einem
Kunden-Windows-Server.** Alle 1.3.x-ZIPs davor (1.3.0 bis 1.3.3) hatten
einen kritischen Auslieferungs-Bug: das **Frontend-Bundle** war ein
uralter vor-Sprint-1.3.0-Build (ohne CSRF-Interceptor), weil
`tools/build-release.sh` bei existierender `frontend/dist/` den
vite-Build uebersprang. Kombiniert mit dem neuen CSRF-Middleware-Check
im Backend hat das jede mutating Operation aus dem Browser zum 403
gemacht. Der gesamte Tag war im Wesentlichen eine Kaskade aus diesem
einen Auslieferungsfehler + Follow-up-Bugs.

### 🔴 Auslieferungs-Bug (hoch kritisch)
- **F-055: `tools/build-release.sh`** baut das Frontend jetzt **immer**
  neu (vite build, 5-10 Sek). Die alte "skip if dist/ exists"-
  Optimierung wird nur noch greifen wenn explizit `--skip-frontend`
  uebergeben wird, und selbst dann prueft sie dass dist/ wirklich da
  ist. Ohne diesen Fix haben alle 1.3.0-1.3.3-ZIPs stale Frontend
  mitausgeliefert. Der Symptom ist jede mutating Operation -> 403
  CSRF, obwohl Backend+Middleware korrekt waren.

### 🔴 Process Manager Fixes
- **F-053: `praxiszeit-server.py` ssl_cert Pfad-Resolution** —
  relative Pfade in `praxiszeit.conf` (z.B. `"config/ssl/cert.pem"`)
  werden jetzt relativ zu `BASE_DIR` (Install-Root) aufgeloest, nicht
  mehr relativ zu `CONFIG_DIR`. Der alte Code hat aus
  `config/ssl/cert.pem` -> `<install>/config/config/ssl/cert.pem`
  gemacht und die Datei nie gefunden. Resultat: `SSL cert/key not
  found` trotz vorhandener Dateien, Startup ohne TLS.
- **F-054: `praxiszeit-server.py` Health-Check Protocol** — die
  Health-Check-URL wird jetzt an `ssl_enabled` (tatsaechlicher State)
  gekoppelt, nicht an die Truthiness der Config-Strings `ssl_cert` /
  `ssl_key`. Wenn die Config auf Cert-Dateien zeigte die nicht
  existierten, pollte der alte Code `https://localhost:443/api/health`
  gegen einen Plain-HTTP-Server -> TLS-Handshake-Fehler -> 30 Sek
  Timeout -> `uvicorn failed to become healthy` -> NSSM-Restart-Loop.
- **`load_config()` BOM-Toleranz** — `praxiszeit.conf` die mit Notepad
  editiert wurde hat ein UTF-8 BOM am Anfang, `tomllib` knallt dann
  mit `TOMLDecodeError: Invalid statement (at line 1, column 1)` und
  der Service crasht sofort nach dem Start. `load_config` strippt den
  BOM jetzt automatisch mit einer WARN-Meldung und faengt ungueltiges
  UTF-8 / TOML-Syntax-Fehler mit lesbarer Fehlermeldung ab.

### 🔴 Update-Wizard Fixes
- **`update-wizard.ps1` Step-Backup** nutzte
  `$psi.ArgumentList.Add(...)` — das ist eine **.NET 5+ API**, die auf
  Windows-built-in PowerShell 5.1 (.NET Framework 4.x) nicht
  existiert. `$psi.ArgumentList` ist dort `$null`, `.Add()` crasht mit
  "Es ist nicht moeglich, eine Methode fuer einen Ausdruck
  aufzurufen, der den Wert NULL hat". Fix: `$psi.Arguments` als String
  (mit Quoting fuer Pfade mit Spaces).
- **Neue `Step-PipInstall`** — laeuft idempotent nach dem Robocopy
  Dateien-Update und vor dem Service-Start. Fuehrt
  `python -m pip install --quiet -r requirements.txt` aus. Ohne diesen
  Schritt hatten Updates zwischen Releases mit neuen Python-
  Dependencies keine Chance zu funktionieren, weil der Wizard die
  Files kopiert hat aber das site-packages nie aktualisiert wurde.
- **em-dashes entfernt** aus den Script-Strings (war die 1.3.3
  Hotfix-Ursache, dokumentiert hier fuer den Kontext).

### 🟡 Neues Tool
- **`tools/generate-self-signed-cert.py`** — offizielles CLI-Tool zum
  Generieren von self-signed SSL-Certs via `cryptography`. Parameter:
  `<ip> [<practice_name>] [<out_dir>]`. Setzt Subject CN=IP, SAN mit
  `localhost` + `127.0.0.1` + IP, 10 Jahre gueltig, RSA 2048 +
  SHA-256. Auf Unix zusaetzlich `chmod 0600` auf `key.pem`. Ersetzt
  die Linux-install.sh-openssl-Generation cross-platform und wird in
  der kommenden 1.4.0 `praxiszeit.exe` als optionaler Installer-Step
  eingebaut.
- `datetime.utcnow()` -> `datetime.now(timezone.utc)` im Tool (die
  inline-Variante aus der Live-Debugging-Session hatte
  DeprecationWarnings in Python 3.13).

### 🟡 Build
- `tools/build-release.sh` hat jetzt `--skip-frontend` als Flag (als
  Escape-Hatch, nicht als Default). Default-Version auf `1.3.4`.

### 📝 Bekannte Baustellen fuer 1.4.0
- **Service-Worker + self-signed Cert**: Chrome weigert sich, einen SW
  ueber HTTPS mit untrusted Cert zu registrieren. Fuer Offline-/PWA-
  Features muss das Cert als Trusted Root auf jedem Client installiert
  werden. Workaround fuer die Praxis: SW-Registrierung defensiv
  abschalten wenn das Cert nicht trusted ist.
- **`praxiszeit.exe` als Single-File-Installer** (Inno Setup) — war
  schon im Native-Installer-Design (Spec §6) vorgesehen, ersetzt dann
  `setup.bat` + `install-service.bat` + `update-wizard.*` durch einen
  echten Windows-Installer mit Wizard-Pages. Baustelle fuer 1.4.0.

---

## [1.3.3] - 2026-04-11

**Hotfix: update-wizard.ps1 Parse-Fehler auf deutschem Windows.**

### 🔴 Fix
- **`update-wizard.ps1`**: drei em-dashes (`U+2014`) in Warn-Meldungen
  entfernt (Zeile 373, 391, 396). PowerShell 5.1 auf de-DE Windows
  liest PS1-Dateien ohne BOM als Windows-1252; die UTF-8-kodierten
  em-dashes (`0xE2 0x80 0x94`) wurden als ungueltige String-Abschluesse
  interpretiert und rissen die gesamte Funktion `Step-ACLFix` /
  `Step-Backup` mit einer Kaskade von "missing catch / unterminated
  string / missing closing brace"-Fehlern auseinander. Der Wizard war
  in 1.3.2 deshalb ueberhaupt nicht lauffaehig. Jetzt durchgaengig
  7-bit ASCII in allen Meldungsstrings; `parse-file` vor jedem Build
  sicherstellen.

### Hinweis fuer Dev
Beim Ausliefern von PS1-Dateien via Repo: entweder strikt ASCII oder
UTF-8 **mit BOM** — sonst ueberrascht dich PS 5.1 mit
encoding-abhaengigen Parse-Fehlern auf Kunden-Servern.

---

## [1.3.2] - 2026-04-11

**Grafischer Update-Wizard fuer Windows.**

### 🟢 Neue Features
- **`installer/windows/update-wizard.bat` + `update-wizard.ps1`** —
  WinForms-GUI-Wizard, der eine bestehende Installation auf die
  gebuendelte Version aktualisiert. Erkennt Install-Verzeichnis
  automatisch (Fallback: Folder-Browser), zeigt alte/neue Version im
  Welcome-Screen, walkt durch sechs Schritte mit Live-Log und
  Progress-Bar:
  1. **ACL-Fix** auf `.db-credentials` (F-037, idempotent — greift auch
     bei bestehenden 1.3.0-Installs)
  2. **DB-Backup** via `praxiszeit-server.py backup` (Service laeuft
     noch → pg_dump funktioniert)
  3. **Service stoppen**
  4. **`robocopy`** mit Excludes fuer `data/`, `logs/`, `ssl/`,
     `praxiszeit.conf`, `.db-credentials`, `.secret-key`, `license.key`
     → User-Daten bleiben unangetastet
  5. **Service starten** (Alembic-Migrationen laufen beim Start)
  6. **Scheduled Task `PraxisZeit-Backup`** registrieren/aktualisieren
  Der Wizard refust, aus dem Installationsverzeichnis selbst gestartet
  zu werden (verhindert Self-Overwrite-Korruption). Launcher erzwingt
  Admin-Rechte via `net session`-Check und UAC-Prompt.

### 🟡 Build
- **`tools/build-release.sh`** kopiert `update-wizard.bat` und
  `update-wizard.ps1` ins Windows-Paket. Default-Version auf 1.3.2
  gebumpt. End-of-build-Summary unterscheidet jetzt Erstinstallation
  und Update-Flow.

---

## [1.3.1] - 2026-04-11

**Windows Native: Automatisches DB-Backup + ACL-Fix.**

### 🟢 Neue Features
- **`installer/windows/backup.bat`** — dünner Wrapper um
  `praxiszeit-server.py backup`, loggt nach `logs/backup.log`, erzwingt
  `PYTHONUTF8=1`. Manuell aufrufbar oder via Scheduled Task.
- **`install-service.bat`** legt jetzt neben dem NSSM-Service und der
  Firewall-Regel eine Scheduled Task `PraxisZeit-Backup` an (täglich
  03:00, läuft als `SYSTEM`, damit `.db-credentials` gelesen werden
  kann). Retention (31 Tage default, konfigurierbar via
  `[backup] retention_days`) war bereits in 1.3.0 in `create_backup()`.
- **`uninstall-service.bat` + `uninstall.bat`** entfernen die Scheduled
  Task sauber mit `schtasks /delete`.

### 🔴 Security / Fixes
- **F-037: `_restrict_file_permissions()`** gewährt jetzt zusätzlich
  `BUILTIN\Administrators:(R)` auf `.db-credentials` (via SID
  `*S-1-5-32-544`, locale-unabhängig). Vorher konnte ein manueller
  Admin-Aufruf von `praxiszeit-server.py backup` mit
  `PermissionError: [Errno 13] '.db-credentials'` abbrechen, wenn der
  Service die Datei zuvor als `SYSTEM`+`MACHINE$` geschrieben hatte.
  Die scheduled task lief vorher schon korrekt (als `SYSTEM`), der Fix
  betrifft ausschließlich den interaktiven CLI-Workflow.

### 🟡 Build
- **`tools/build-release.sh`** kopiert `backup.bat` ins Windows-Paket.
  Default-Version auf `1.3.1` gebumpt.

### 📝 Bekannte Lücken (nicht geschlossen)
- **`core/updater.py`** hat noch keinen `apply`-Flow — die Admin-API
  bietet nur `/status` + `/check`, kein `/download` + `/apply`. Das
  pre-update-Backup (Spec §5) ist deshalb leer-konstruiert und wird
  erst mit der Umsetzung der Apply-Route relevant.

---

## [1.3.0] - 2026-04-11

**Großer Security-, Stability-, Performance- und UX-Review — 41 gezielte Fixes.**
362/362 Backend-Tests grün (inkl. 13 RLS-Integrationstests gegen echte
Postgres-DB), Frontend TypeScript + Vite-Build clean, ESLint 9 + flat
config installiert (0 Errors, 86 Legacy-Warnings für späteren Cleanup).

### 🔴 Security (CRITICAL + HIGH)
- **Access-Token raus aus `localStorage`** — Token lebt nur noch im
  Modul-Memory, Session-Recovery über HttpOnly-Refresh-Cookie beim
  App-Start. XSS-Steals-Session-Vektor geschlossen.
- **CSRF Double-Submit-Cookie** — neue `CSRFMiddleware`, nicht-HttpOnly
  `csrf_token` Cookie beim Login/Refresh, `X-CSRF-Token`-Header-Check
  auf allen unsafe Methods.
- **Hardcoded `PraxisZeit2025!` aus Installern entfernt** — PowerShell /
  `/dev/urandom` generiert zur Installationszeit ein Einmal-Passwort.
  `uninstall.bat` + neuer `restore-backup.template.bat` lesen
  `.db-credentials` statt Fallback zu verwenden.
- **`.env` Schutz** — neuer `pre-commit-hook.sh` blockiert `.env`-Commits
  (auch mit `-f`), `init-db-user.sh` lehnt schwache `APP_DB_PASSWORD` ab,
  Dev-`.env` auf zufällige Werte rotiert.
- **Multi-Tenant tenant_id-Filter** — `is_holiday()` + alle Bulk-Deletes
  + Admin-User-Lookups kriegen explizite `tenant_id`-Filter zusätzlich
  zu RLS. Neuer Helper `_get_user_in_tenant()` in `admin_users.py`.
- **Auth-Enumeration-Fix** — Dummy-bcrypt-Verify bei nicht-existenten
  Usern gleicht Timing aus, `_failed_logins` als OrderedDict-LRU mit
  O(1)-Eviction, `move_to_end()` hält legitime Opfer-Lockouts "heiß"
  gegen Attacker-Evict-Flood.
- **`bcrypt_sha256` statt bcrypt** — eliminiert die stillschweigende
  72-Byte-Trunkierung. Opportunistischer Re-Hash beim nächsten Login
  migriert Legacy-Hashes ohne User-Reset.
- **Ed25519-signierte Update-Manifeste** — `updater.py` verifiziert
  Manifest-Signatur vor Download-URL-Vertrauen + Host-Allowlist + HTTPS
  erzwungen. Trust-Root aus `license.py` wiederverwendet.
- **HSTS nur noch auf HTTPS** — verhindert Safari-Brick in Native-HTTP-
  Install.
- **GitHub-Issue-URL-Sanitizer** — `sanitizeGithubUrl()` blockt
  `javascript:`-URLs auf Admin-ErrorMonitoring-Seite.
- **`update_profile` Audit-Log** bei E-Mail-Änderungen.

### 🟠 Stability (HIGH)
- **`with_for_update()` auf CR/VR/Absence/TimeEntry Approval-Paths** —
  schließt Double-Click-Races bei `review_change_request`,
  `review_vacation_request`, `create_absence` (Duplicate-Probe) und
  `admin_update_time_entry`.
- **`create_year_closing` pg_advisory_xact_lock(42, hash(tenant,year))**
  + Pending-CR-Refusal.
- **`_close_stale_entry`** committet nicht mehr mitten im Request,
  schreibt `TimeEntryAuditLog(action="update", source="auto_close")` so
  dass §3 ArbZG-Verstöße vom Vortag nachverfolgbar sind.
- **clock-in §5 DST-Fix** — `datetime.combine(..., tzinfo=LOCAL_TZ)`
  statt naive, korrekte Wall-Clock-Rechnung auch bei Umschalttagen.
- **`get_weekly_hours_for_date` Bypass entfernt** — die zwei lokalen
  Shadow-Helpers in `calculation_service.py` gelöscht, authoritative
  Lookup mit optionalem `wh_changes=` Prefetch. Einziger Ort der
  `user.weekly_hours` direkt liest.
- **`company_closures.py:145`** reicht jetzt `weekly_hours` explizit durch.
- **`AbsenceType.OTHER` Semantik** dokumentiert + Pinning-Test
  `test_absence_type_other_reduces_target_and_ignores_actual`.
- **`vacation_requests.create` Validierung** auf Parität mit
  `create_absence` (Range, first/last_work_day, Dedup, Budget).
- **`get_vacation_account` Div-by-Zero-Fix** — früher Return mit
  `track_hours=False` Sentinel für Users ohne Zeiterfassung.
- **`xls_import_service.execute_import` try/except + rollback +
  Failure-Audit-Log** statt halbimportierter DB.

### 🟡 Performance
- **Migration 031 — Composite-Indexe** `(tenant_id, user_id, date)` auf
  `time_entries` und `absences`, `(user_id, effective_from)` auf
  `working_hours_changes`.
- **`net_hours` `@expression`** — `func.sum(TimeEntry.net_hours)` läuft
  jetzt auf SQL-Ebene (dialekt-portabel mit `CASE` statt `GREATEST`).
- **`date_in_year` / `date_in_month` / `date_in_year_up_to_month`** in
  neuer `services/date_filters.py`. **70+ non-sargable
  `extract('year'|'month', date)`-Sites** umgeschrieben in `reports`,
  `calculation_service`, `journal_service`, `export_service`,
  `ods_export_service`, `time_entries`, `admin_time_entries`,
  `absences`, `vacation_requests`, `rest_time_service`.
- **Reports `/yearly-absences` Bulk-Fetch** aller 5 Absence-Typen in
  einem Query statt N+1 per User per Typ.
- **Per-(tenant_id, year) Holiday-Cache** in `holiday_service` — 
  `is_holiday()` ist O(1) nach erstem Zugriff, Invalidierung auf
  `sync_holidays` / `delete_all_holidays`.
- **`db.close()` vor `StreamingResponse`** in allen 6 Export-Endpoints
  (Excel/ODS/PDF × monthly/yearly/yearly-classic) — keine Pool-
  Connection wird mehr während Download gehalten.
- **Audit-Log Cursor-Pagination** — neuer `before`-Query-Parameter
  (ISO-8601) als bevorzugter Modus, Legacy-Offset bleibt backward-compat.
- **`get_deletion_candidates` Single GROUP BY MAX(date)** statt N+1
  per-User-Lookup.

### 🎨 Frontend UX
- **Dashboard + TimeTracking Async-Cleanup** — `cancelled`-Flag-Pattern
  in allen useEffects, keine setState-after-unmount-Warnings mehr.
- **`formatHoursHM` NaN-Guard** + `parseHours()`-Helper. 5 Form-Sites
  (`UserForm`, `WorkingHoursModal`, `AbsenceCalendarPage`,
  `AdminAbsences`, `Reports`) migriert.
- **Toast-IDs via `crypto.randomUUID()`** — keine React-Key-Kollisionen
  bei Burst-Errors mehr.
- **Router-aware ErrorBoundary** (`key={location.pathname}`) — ein
  broken Page lähmt nicht mehr die ganze SPA.
- **PWA `registerType: 'prompt'`** + Confirm-Dialog statt silent reload
  beim Deploy.
- **`Layout.isActive`** highlighted Sub-Routes korrekt
  (`/admin/users/:id/journal` → "Benutzerverwaltung"-Nav-Entry).

### 🏗️ Infrastructure
- **`deploy.sh`** refuses dirty working tree, pre-migration `pg_dump` via
  `scripts/backup-db.sh`, automatischer `git reset --hard` + Rebuild bei
  Healthcheck-Failure, `PREVIOUS_COMMIT` als Rollback-Target gespeichert.
- **Backend multi-stage Dockerfile** — `gcc` und `postgresql-client` aus
  Runtime raus (nur Build-Stage hat sie). Python gepinnt auf
  `3.12.7-slim-bookworm`. Image ~200MB kleiner.
- **Prometheus + Grafana Image-Tags gepinnt** — `v2.54.1` / `11.2.0`.
- **Grafana provisioned Dashboards locked** — `editable: false`,
  `disableDeletion: true`.
- **`praxiszeit-server.py`** konfigurierbares `bind_address` (für
  127.0.0.1-only Deployments) + loud WARNING bei `0.0.0.0` ohne TLS.
- **ESLint 9 Flat Config** installiert (`eslint.config.js`) — 0 Errors,
  86 Legacy-Warnings. `scripts/local-ci.sh` wrappt Backend-Tests,
  TypeScript, ESLint, Vite-Build (und optional E2E) in eine Pipeline.
- **pre-commit Hook** (`scripts/pre-commit-hook.sh` +
  `scripts/install-git-hooks.sh`) blockt `.env`-Commits und
  `PraxisZeit2025!`-Referenzen.

### Breaking Changes / Migration Notes
- **Alembic-Migration 031** läuft automatisch beim nächsten
  `alembic upgrade head`. Erzeugt drei `CREATE INDEX` — keine Daten-
  migration.
- **APP_DB_PASSWORD**: Dev-`.env` auf zufälligen Wert rotiert. Bei
  bestehenden Docker-Volumes muss das DB-User-Passwort einmalig per
  `ALTER ROLE praxiszeit_app PASSWORD '<new>'` synchronisiert werden —
  oder Volume neu anlegen (neues `init-db-user.sh` setzt es dann
  automatisch).
- **SECRET_KEY**: Dev-`.env` rotiert. Existing-Sessions werden beim
  Restart ungültig — User müssen sich einmal neu einloggen.
- **Legacy bcrypt-Hashes** werden beim nächsten erfolgreichen Login
  automatisch auf `bcrypt_sha256` migriert — kein Passwort-Reset nötig.
- **CSRF-Token**: Frontend-Interceptor setzt den neuen Header
  automatisch. Dritt-Client-Integrationen (pure Bearer-API-Clients)
  sind nicht betroffen, die CSRF-Middleware prüft nur bei vorhandenem
  `csrf_token`-Cookie.
- **GitHub-Actions deaktiviert** (Repository-Level) während dieser PR.
  Vor Production-Release wieder aktivieren:
  `gh api repos/phash/praxiszeit/actions/permissions -X PUT --input - <<< '{"enabled":true}'`

### Documentation
- Ausführliche Sprint-Dokumentation in Commit-Message
- PR-Body mit gruppierten Fixes nach Priorität
- neue Migration-Notes für 1.3.0

## [1.2.1] - 2026-04-07

### Bug Fixes (Native Windows Installation)
- **psql -v Interpolation:** Variable-Substitution funktioniert nicht mit `-c` auf PostgreSQL 18.3/Windows — direkte SQL-Strings statt `-v`/`:'var'`
- **Python 3.13 Glob-Expansion:** `*` in subprocess-Argumenten wird auf Windows als Glob expanded — explizite Werte statt Wildcards
- **SYSTEM-Permissions:** `.db-credentials` war fuer NSSM-Service (SYSTEM-Account) nicht lesbar — `SYSTEM:(R,W)` hinzugefuegt
- **cp1252 UnicodeEncodeError:** Emoji-Output crasht im NSSM-Service — `PYTHONUTF8=1` fuer uvicorn-Subprozesse
- **Config-to-Env Bridge:** `SECRET_KEY`, `ADMIN_EMAIL` etc. fehlten als Env-Vars fuer Backend — TOML-Config-Werte werden in `cmd_start()` gesetzt
- **FRONTEND_DIR:** Relativer Pfad im Native-Modus falsch aufgeloest — absoluter Pfad via `APP_DIR / "frontend"`
- **LICENSE_KEY_PATH:** Relativer Pfad nicht auffindbar vom Backend-CWD — wird zu absolutem Pfad aufgeloest
- **SPA-Fallback 405:** Catch-All `@app.get("/{full_path:path}")` verursachte 405 fuer POST/PUT/DELETE API-Requests — ersetzt durch `SPAFallbackMiddleware`
- **Session-Verlust:** `SECRET_KEY` wurde bei jedem Restart neu generiert (alle JWTs ungueltig) — Key wird in `config/.secret-key` persistiert
- **cookie_secure ohne SSL:** Secure-Cookie bei HTTP-Verbindung vom Browser abgelehnt — `cookie_secure=false` fuer Nicht-SSL-Setups

### Documentation
- Neue Doku: `docs/NATIVE-WINDOWS-PITFALLS.md` — 10 Fallstricke mit Loesungen und Deployment-Checkliste
- CLAUDE.md um Native-Windows-Regeln erweitert

## [1.2.0] - 2026-04-03

### Features
- **Überstundenausgleich korrigiert:** Soll bleibt bestehen, Ist = 0h — Überstundenkonto sinkt korrekt um Tagessoll
- **Absences mit Start-/Endzeit:** Abwesenheiten können optional Start-/Endzeit haben ("ganzer Tag" wenn leer)
- **Änderungsanträge für Abwesenheiten:** Mitarbeiter können Krank, Fortbildung, Urlaub etc. per CR beantragen (entry_kind="absence")
- **Journal Multi-Entry:** Tage mit mehreren Einträgen zeigen jeden Eintrag auf eigener Zeile mit Typ
- **Gemischte Tage:** Arbeitszeit + Absence am selben Tag korrekt dargestellt und berechnet
- **Admin CR-Filter:** User-Dropdown + Zeitraum-Filter (1M/3M/Jahr/Vorjahr/freier Zeitraum)
- **Echtzeit-Ruhezeitwarnung:** Warnung beim Einstempeln wenn <11h seit letztem Arbeitsende (§5 ArbZG)
- **Pausen-Mindestdauer:** Warnung bei Pausenabschnitten <15 Minuten (§4 Satz 2 ArbZG)
- **DSGVO sick_hours opt-in:** JSON-Reports maskieren Krankheitsdaten ohne explizites opt-in

### Bug Fixes
- CR-Approval Race Condition: Status wird erst nach Precondition-Checks gesetzt
- CR-Approval: Unique-Constraint-Check bei Datumsänderung
- CR-Approval: Nutzt jetzt CR-Tenant-ID statt Admin-Tenant-ID
- Absence-CRs: Duplikat-Prüfung für pending Anträge
- TimeEntry-CRs: Duplikat-Check für CREATE-Anträge repariert
- UPDATE-CRs: Zukunftsdaten blockiert, start >= end Validierung
- DELETE-CRs: Entry-Existenzprüfung vor Status-Änderung
- Journal: SICK-Tag nutzt daily_target statt absence_sum
- Journal: Absence-Ordering deterministisch (.order_by type)
- Mixed-Day: VACATION/OTHER/OVERTIME reduzieren Soll korrekt
- Mixed-Day: Absence-Erstellung löscht nicht mehr alle TimeEntries (keep_time_entries)
- Mixed-Day: Delete löscht nur gezielten Eintrag, nicht Absence
- Sick Absence: Nutzt historische weekly_hours statt aktuelle
- Cross-Year Vacation: Budget-Check pro Jahr statt nur Startjahr
- Overlapping Absences: Verschiedene Typen am selben Tag blockiert
- net_hours: Floor bei 0 (kann nicht negativ werden)
- Export: Mehrere TimeEntries pro Tag werden korrekt exportiert
- Export: Historische daily_target pro Tag statt statisch
- Export: "Überstundenausgleich" Label in Absence-Type-Maps
- Export: Night-Work-Days zählt unique Dates statt Entries
- Export: PDF zeigt non-sick Absence-Notes unabhängig von health_data Flag
- ODS: Überstundenausgleich-Spalte in Jahresübersicht ergänzt
- Reports: monthly weekly_hours nutzt historischen Wert
- Dashboard: Missing-Bookings-Query mit Datum-Untergrenze (Performance)
- Vacation-Approval: Historische weekly_hours + Cross-Year-Budget-Check
- User-Purge: VacationRequest FK-Bereinigung verhindert IntegrityError
- DSGVO: Kalender maskiert "sick" → "absent" für nicht-Admins
- Absence-Löschung: Audit-Log vor delete
- Alembic: version_num_width=128 verhindert Spalten-Overflow
- formatHoursSimple: Negative Werte korrekt dargestellt
- Admin 8h-Warnung: DAILY_HOURS_WARNING in Admin-Pfaden ergänzt
- Holiday-Service: is_holiday() mit optionalem Tenant-Filter
- Anonymisierung: Grace-Period Null-Check für Legacy-User

### Tests
- 343 Backend-Tests (vorher 275, +68 neue)
- Absence-Typ-Matrix: Parametrisierte Tests für alle 5 Typen
- Überstundenausgleich: 8 Tests (Soll/Ist, Tagesplan, Journal, kumulativ)
- Jahresabschluss: 8 Tests (Übertrag, Resturlaub, Mid-Year-Hire, Idempotenz)
- Mixed-Day: 4 Tests (Work+Training, Work+Sick, Work+Vacation, Work+Overtime)
- Absence-CRs: 8 Tests (Model, Zeiten, Approval, Journal-Integration)
- Berechnungs-Units: 13 Tests (Target, Actual, Balance, Vacation, Carryover)

### Security & Compliance
- 4 Runden Bughunting-Review (31 Bugs gefunden und gefixt)
- ArbZG-Audit: KONFORM (§2-§18 vollständig geprüft)
- DSGVO-Audit: KONFORM (Art. 5/6/9/15/17/20/25/32 geprüft)
- Security-Review: 0 kritische Schwachstellen

### Migration
- `030` — Absence start_time/end_time + Change Request absence fields (entry_kind, absence_id, proposed/original_absence_type/hours)

---

## [1.1.0] - 2026-03-26

- Multi-Tenant Phase 1-3 (RLS, Tenant-Modell, Auth-Middleware)
- VacationRequest absence_type Erweiterung

## [1.0.0] - 2026-02-14

- Initiales Release
