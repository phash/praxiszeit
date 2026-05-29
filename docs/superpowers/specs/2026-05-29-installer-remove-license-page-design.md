# Design: Lizenz-Seite aus dem Windows-Installer entfernen (1.8.0)

**Datum:** 2026-05-29
**Branch:** `feature/installer-remove-license-page`
**Status:** Genehmigt (Brainstorming-Entscheidungen unten)

## Ziel

Das Lizenzmodell soll **vorerst (reversibel) wegfallen** und der Installer
nicht mehr nach einer Lizenz fragen. Auslieferung als Windows-Release 1.8.0.

## Ausgangslage (Ist-Stand im Repo)

- **Backend:** Die Lizenzprüfung ist über `BETA_MODE: bool = True`
  (`backend/app/config.py`) bereits **komplett deaktiviert** — kein
  Lizenzcheck, kein Read-Only, kein Mitarbeiter-Limit (`main.py` Schritt 7,
  `if settings.BETA_MODE: set_license_state(None, read_only=False)`).
- **Frontend:** zeigt ein „BETA"-Badge aus `/api/health.beta` (= `BETA_MODE`).
- **Build:** `tools/build-release.sh` **warnt** nur bei `BETA_MODE=True`
  (kein Abbruch) — Beta-Builds sind ausdrücklich erlaubt (#179).
- **Installer (Avalonia, `installer/setup/`):** Der Wizard enthält weiterhin
  eine **Lizenz-Seite** (`LicensePageViewModel`/`LicensePageView`), die eine
  Entscheidung „Lizenz-Token *oder* 30-Tage-Demo" **erzwingt**. Das ist der
  einzige Ort, der noch nach Lizenz fragt.

## Entscheidungen (Brainstorming 2026-05-29)

1. **Umfang:** *Reversibel.* Lizenz-Code bleibt im Repo, bleibt über
   `BETA_MODE=True` deaktiviert. Kein Backend-Change.
2. **Installer-Seite:** *Seite aus dem Wizard-Ablauf entfernen* (nicht nur
   überspringen). Page-/Validator-Klassen bleiben ungenutzt im Repo erhalten.
3. **BETA-Badge:** *bleibt sichtbar* (ehrliches Signal in der Beta).

## Änderungen (nur `installer/setup/src/PraxisZeit.Setup/` — UI-Projekt)

### `ViewModels/MainWindowViewModel.cs`
- Feld `_license` + Instanziierung (`new LicensePageViewModel()`) entfernen.
- In `RebuildPagesForMode`: `Pages.Add(_license)` entfernen.
  Neue Abläufe:
  - **Update:** Welcome → Location → Progress → Done
  - **Fresh/Repair:** Welcome → Location → Ports → Config → Progress → Done
- In `TransitionToProgressAndRunAsync`: die beiden `WriteLicenseFileAsync`-
  Blöcke (Update- und Fresh-Pfad) entfernen.
- In `BuildConfigValues`: `LicenseToken`/`DemoDays` nicht mehr setzen
  (Defaults bleiben `null` → die geschriebene `praxiszeit.conf` enthält weder
  `license.key`-Verweis noch `demo_expires_at`; mit `BETA_MODE=True` egal).
- Veraltete Doc-Kommentare (Lizenz) anpassen.

### `Views/MainWindow.axaml`
- `DataTemplate` für `LicensePageViewModel` entfernen.

### Bewusst unverändert (reversibel)
- `LicensePageViewModel.cs`, `LicensePageView.axaml(.cs)` — bleiben (ungenutzt).
- `Core/Services/LicenseValidator.cs` + `LicenseValidatorTests.cs`.
- `Core/Services/PraxisZeitConfigWriter.cs` Demo-/Lizenz-Pfad +
  `PraxisZeitConfigWriterTests.cs`.
- Backend komplett.

**Reaktivierung später:** Feld + `Pages.Add(_license)` + `DataTemplate` +
die zwei Conf-/File-Zeilen wieder einhängen, dann `BETA_MODE=False`.

## Verifikation

- `cd installer/setup && dotnet test` → alle Tests grün (Core-Lizenz-Tests
  bleiben grün, da Code erhalten).
- Code-Review des Diffs: Wizard ohne Lizenz-Seite, keine `_license`-Referenz
  mehr im UI-Projekt.

## Build & Auslieferung

- `bash tools/build-release.sh --windows-only --skip-download`
  (Cache in `build/cache/` vollständig: EDB-PG, vc_redist, nssm, get-pip,
  python-build-standalone).
- Artefakte: `dist/praxiszeit-1.8.0-windows-x64.zip` +
  `praxiszeit-1.8.0-setup-windows-x64.exe`.
- `BETA_MODE=True`-Build-Warnung ist erwartet (Beta).
- SHA256SUMS erzeugen; ZIP-Inhalt prüfen (`bin/python/Lib/site-packages`
  enthält cp313-Wheels, register-Call vorhanden).

## Nicht in Scope

Kein Backend-Change, kein Badge-Change, kein Linux/macOS-Build, kein
pzweb-Upload (nur auf gesonderte Ansage).
