# PraxisZeit aktualisieren (Docker & Native)

So bringen Sie eine **bestehende** Installation auf eine neue Version — ohne
Datenverlust. Datenbank-Migrationen laufen bei jedem Start automatisch.

> **Immer zuerst: Backup.** Vor jedem Update eine Datensicherung ziehen (siehe
> unten je Variante). PraxisZeit speichert ArbZG-pflichtige Daten — §16 verlangt
> 2 Jahre Aufbewahrung.

> **Nach jedem Update: Browser-Hard-Refresh** (`Strg`+`F5` bzw. `Cmd`+`Shift`+`R`)
> oder einmal im Inkognito-Fenster öffnen — sonst lädt der Browser das alte
> Frontend aus dem Cache (Service-Worker/PWA).

> ### ⚠️ Update auf 1.20.0 = Arbeitszeit-Fenster werden zu Arbeitszeit-Blöcken
>
> Die Migration `073_work_blocks` läuft beim ersten Start automatisch. Sie übernimmt
> jedes hinterlegte Soll-Arbeitszeit-Fenster als einen Block je Tag
> („Arbeitszeit-Fenster (Altbestand, nur Kappung)") und **entfernt die alten
> Fenster-Spalten**. Tagessoll, angerechnete Zeit und Überstundensaldo bestehender
> Einträge bleiben unverändert. Danach:
> - Seite neu laden (siehe oben) – ein noch geöffnetes altes Benutzerformular meldet
>   beim Speichern „Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende)
>   wurden durch Arbeitszeit-Blöcke ersetzt."
> - Ausgabe der Migration lesen (Docker: `docker compose logs backend`; nativ:
>   `logs/praxiszeit.log`, Zeilen mit `alembic:`). Der Abschnitt zwischen
>   `*** HINWEIS (Migration 073) ***` und `*** ENDE HINWEIS ***` nennt die Zahl
>   der übernommenen Konten und Verlaufszeilen; steht dort „Besonderheiten", die
>   genannten Personen im Dialog „Arbeitszeit anpassen…" prüfen.
> - **Zurück auf 1.19.x nur über das Backup** von vor dem Update. Ein Schema-Downgrade
>   stellt je Tag nur die Hülle der Blöcke (Beginn des ersten bis Ende des letzten
>   Blocks) als Fenster her – Zeit zwischen den Blöcken würde dann wieder angerechnet.

---

## Docker

Die Daten liegen im Docker-Volume `postgres_data` und bleiben über Updates
hinweg erhalten — der `docker compose down`/`up`-Zyklus löscht sie **nicht**
(nur `down -v` würde das Volume entfernen — niemals ungesichert tun).

> ### ⚠️ Update auf 1.10.0 = PostgreSQL-Major-Upgrade (16 → 18)
>
> Ab **1.10.0** bündelt PraxisZeit **PostgreSQL 18** (vorher 16). Ein PG-Major-
> Upgrade ist **nicht in-place**: `postgres:18` kann ein von `postgres:16`
> angelegtes `postgres_data`-Volume nicht starten (es bricht mit einer
> „incompatible"-Meldung ab). Kommst du von **1.9.x oder älter**, nutze den
> **geführten Helfer im Docker-Bundle** statt eines einfachen `up`:
>
> ```bash
> bash update-pg-major.sh   # alter Stack muss noch laufen
> ```
>
> Er sichert die laufende DB, entfernt **nur** das `*_postgres_data`-Volume (die
> #213-Backups im `praxiszeit_backups`-Volume bleiben), startet den frischen
> PG18-Stack und spielt den Dump wieder ein. Manuell:
> `bash backup.sh` → `docker compose down` → `docker volume rm <projekt>_postgres_data`
> → neuen Stack `up -d --build` → `bash restore.sh backups/praxiszeit_<ts>.sql.gz`.
> Verifiziert (PG16→18, Daten byte-genau identisch + Login). Spätere 1.10.x-Updates
> bleiben wieder normale In-Place-Updates.

### 1. Backup

```bash
# Default-User/-DB = praxiszeit (eigene Werte ggf. aus der .env ablesen).
# --clean --if-exists + gzip → exakt so zurückspielbar wie unter „Rollback".
docker compose exec -T db pg_dump -U praxiszeit --clean --if-exists praxiszeit | gzip > backup-$(date +%F).sql.gz
```

> Die `$POSTGRES_USER`/`$POSTGRES_DB` aus der `.env` sind **nur im Container** gesetzt,
> nicht in deiner Host-Shell — deshalb oben die festen Default-Namen `praxiszeit`.

### 2a. Mit Docker-Paket (Tarball/ZIP, ohne git)

Neues Paket `praxiszeit-<neu>-docker.(tar.gz|zip)` herunterladen und entpacken.
**Die bestehende `.env` übernehmen** (NICHT `generate-secrets.sh` erneut laufen
lassen — das überschriebe Secrets und das Admin-Passwort):

```bash
# im neuen, entpackten Paket-Ordner:
cp /pfad/zur/alten/installation/.env ./.env
# Falls SSL genutzt wird, auch das Zertifikat übernehmen:
cp /pfad/zur/alten/installation/ssl/cert.pem ssl/cert.pem 2>/dev/null || true
cp /pfad/zur/alten/installation/ssl/key.pem  ssl/key.pem  2>/dev/null || true

# Datenbank-Image auf den neuesten 18.x-Patchstand holen (Sicherheitsupdates —
# `up` allein nimmt sonst das bereits vorhandene, ältere Image):
docker compose pull db
# Basis-Images der selbst gebauten Dienste ebenfalls neu ziehen (Debian/Alpine-
# Sicherheitsupdates erscheinen unter demselben Tag — `--build` allein nimmt
# die lokal vorhandenen):
docker compose build --pull
# HTTP:
docker compose up -d
# ODER HTTPS:
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```

> Wichtig: Das **Postgres-Volume** muss dasselbe bleiben. Starten Sie das Update
> im **selben Verzeichnis** wie zuvor (gleicher Compose-Projektname = gleiches
> Volume), oder setzen Sie `COMPOSE_PROJECT_NAME` identisch. Im Zweifel: vor dem
> Wechsel das SQL-Backup ziehen und nach dem Start prüfen, ob die Daten da sind.

> **Eigene Anpassungen an `docker-compose.yml`** (z. B. ein anderer Port als 80
> oder ein freigegebener Prometheus-Port) stehen im neuen Paket wieder auf dem
> Auslieferungsstand und gehen beim Update verloren — die Anwendung lauscht dann
> still wieder auf Port 80. Vor dem `up` übernehmen, oder dauerhaft in eine
> eigene `docker-compose.override.yml` legen (Compose liest sie automatisch mit).
>
> **Den alten Paket-Ordner nicht mehr starten.** Er trägt denselben
> Projektnamen; ein `docker compose up` dort startet die alte Version gegen die
> bereits aktualisierte Datenbank. Nach erfolgreichem Update löschen oder
> umbenennen.

### 2b. Aus dem Quellcode (nur mit git-Zugriff)

> **Von 1.9.x oder älter? Erst das PostgreSQL-Major-Upgrade fahren** — sonst
> scheitert `up --build` am inkompatiblen PG16-Volume (siehe Box oben). Der Helfer
> funktioniert auch aus dem git-Checkout (er findet die `docker-compose.yml` im
> Repo-Root und nutzt `backup.sh`/`restore.sh` daneben):
> ```bash
> cd praxiszeit && git pull                 # holt PG18-Compose + den Helfer
> bash tools/docker/update-pg-major.sh      # Backup → frischer PG18 → Restore
> ```
> Bereits auf 1.10.x? Dann ist es ein normales In-Place-Update:

```bash
cd praxiszeit
git pull
docker compose down
docker compose pull db                 # PostgreSQL-18-Patchstand
docker compose build --pull            # frische Basis-Images (Sicherheitsupdates)
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d   # oder ohne -f … für HTTP
```

### 3. Prüfen

```bash
docker compose ps                      # alle Dienste "Up"/"healthy"
curl http://localhost/api/health       # {"status":"healthy","database":"connected"}
curl http://localhost/api/system/info   # enthält die neue Version
```

⚠️ Prüfen Sie den **Inhalt** der Antwort, nicht nur den Statuscode: unbekannte
Pfade beantwortet der Webserver mit der Oberfläche (HTTP 200 + HTML), damit die
App auch nach einem Neuladen funktioniert. Ein reiner Statuscode-Test meldet
deshalb auch dann Erfolg, wenn der Pfad gar nicht existiert.

Migrationen werden beim Backend-Start automatisch angewendet
(`docker compose logs backend` zeigt die alembic-Ausgabe). **Lesen Sie diese
Ausgabe:** Migrationen benennen dort Datensätze, die von Hand nachzuziehen sind
— zum Beispiel Mitarbeitende, deren hinterlegte Tagesstunden zusammen mehr als
60 Stunden pro Woche ergeben; deren Vertragswert lässt die Migration bewusst
unverändert.

---

## Native (ohne Docker)

Die native Installation aktualisiert man durch **erneutes Ausführen des
Installers in dasselbe Verzeichnis**. Daten (`data/db`), Konfiguration
(`config/`, inkl. `.env`/`.secret-key`/`.db-credentials`/`license.key`) und
das Backup-Verzeichnis bleiben dabei erhalten.

### Linux

```bash
# 1. Backup — frischer DB-Dump (Dienst läuft dabei), dann Konfiguration sichern
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 \
    /opt/praxiszeit/praxiszeit-server.py backup
ls /opt/praxiszeit/data/backups/                       # der neue Dump liegt hier
sudo systemctl stop praxiszeit
sudo cp -a /opt/praxiszeit/config /opt/praxiszeit/config.bak-$(date +%F)   # config/ ist nur fürs Dienstkonto lesbar

# 2. Neues Tarball flach in einen Ordner entpacken + Installer erneut ausführen
mkdir -p praxiszeit-<neu>
tar xzf praxiszeit-<neu>-linux-x64.tar.gz -C praxiszeit-<neu>
cd praxiszeit-<neu>
sudo ./install.sh                                       # erkennt die bestehende Installation,
                                                        # behält Daten/Config/Lizenz, spielt nur Code + Migrationen ein

# 3. Dienst läuft danach wieder; Status prüfen
sudo systemctl status praxiszeit
```

### macOS

Auf dem Mac weichen drei Dinge ab: der Installationsordner ist
`/usr/local/praxiszeit`, das Dienstkonto heißt **`_praxiszeit`** (mit
Unterstrich, wie bei macOS-Systemkonten üblich) und der Dienst läuft über
launchd statt systemd.

```bash
# 1. Backup — frischer DB-Dump (Dienst läuft dabei), dann Konfiguration sichern
sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 \
    /usr/local/praxiszeit/praxiszeit-server.py backup
ls /usr/local/praxiszeit/data/backups/
sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist
sudo cp -a /usr/local/praxiszeit/config /usr/local/praxiszeit/config.bak-$(date +%F)

# 2. Neues Paket flach in einen Ordner entpacken + Installer erneut ausführen
mkdir -p praxiszeit-<neu>
tar xzf praxiszeit-<neu>-macos-arm64.tar.gz -C praxiszeit-<neu>    # Intel-Mac: -macos-x64
cd praxiszeit-<neu>
sudo ./install.sh                                       # erkennt die bestehende Installation
                                                        # und lädt den Dienst am Ende wieder

# 3. Status prüfen
sudo launchctl list | grep de.praxiszeit
```

> Der Installer legt Verzeichnisse mit `mkdir -p` an (löscht nichts), übernimmt
> eine vorhandene `license.key` und lässt ein bereits initialisiertes
> PostgreSQL-Datenverzeichnis unangetastet. **`config/` niemals vorher löschen**
> — dort liegen `.secret-key` und `.db-credentials` (sonst Session-/DB-Verlust,
> siehe „Disaster Recovery" in [INSTALL-NATIVE.md](INSTALL-NATIVE.md)).

### Windows

```bat
:: Als Administrator. Backup vorher über die nächtliche Sicherung in data\backups\.
:: Neues praxiszeit-<neu>-windows-x64.zip entpacken, dann:
update-wizard.bat
```

Der Update-Wizard (`installer/windows/update-wizard.ps1`) stoppt den Dienst,
spielt Code + Python-Abhängigkeiten ein (pip-Bootstrap gegen stale Pakete),
installiert bei Bedarf die VC++-Runtime nach und startet den Dienst neu.
Konfiguration und Datenbank bleiben erhalten. Details + Stolperfallen:
[NATIVE-WINDOWS-PITFALLS.md](NATIVE-WINDOWS-PITFALLS.md).

### Update-Hinweis in der App

Als Admin sehen Sie im Dashboard ein **Update-Banner**, sobald eine neue Version
verfügbar ist (Abgleich gegen `updates.mr-development.de`, signiertes Manifest).
Das Banner informiert nur — eingespielt wird das Update über die oben
beschriebenen Schritte.

---

## Versionsstand prüfen

- **App-Footer** (unten links, nach Hard-Refresh): zeigt die aktive Version.
- `GET /api/system/info` liefert die Version auf **jeder** Installationsart.
- `GET /openapi.json` enthält sie ebenfalls — aber nur, solange `ENVIRONMENT` nicht auf `production` steht. Die Docker-Installation setzt das über `generate-secrets.sh` automatisch, dort liefert der Pfad keine Versionsangabe (über den Frontend-Port kommt die HTML-Startseite der Anwendung, direkt am Backend ein **404**).
- `GET /api/health` liefert die Version bewusst **nicht** (nur Status und Datenbank).

---

## Rollback

Es gibt keinen automatischen Rollback. Im Problemfall: die alte Paket-/Code-Version
erneut einspielen und das **vor** dem Update gezogene DB-Backup zurückspielen.
Docker (zum `--clean`-gzip-Backup aus Schritt 1) — Backend anhalten, Datenbank
frisch anlegen, Backup einspielen, Backend wieder starten:

```bash
docker compose stop backend
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d postgres \
    -c 'DROP DATABASE IF EXISTS praxiszeit WITH (FORCE)' -c 'CREATE DATABASE praxiszeit'
gunzip -c backup-JJJJ-MM-TT.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit
docker compose start backend           # Migrationen laufen nur beim Start des Containers
```

Frisch anlegen, weil `--clean` nur entfernt, was im Backup vorkommt: eine Tabelle,
die erst die neuere Version angelegt hat, bliebe stehen und könnte das Einspielen
abbrechen. Und `docker compose up -d backend` startet ein schon laufendes Backend
**nicht** neu – die Migrationen liefen dann nicht, das Backend arbeitete gegen das
Schema des Backups. Ab 1.20.0 erledigt `bash restore.sh backup-JJJJ-MM-TT.sql.gz`
(Docker-Paket; im git-Checkout `bash tools/docker/restore.sh …`) genau diese
Schritte und meldet sich erst, wenn das Backend wieder gesund ist.

Nativ (Linux/macOS) in dieser Reihenfolge: **zuerst** mit der noch installierten
neuen Version das Backup einspielen, **dann** den Anwendungsordner `app/` beiseitelegen
und **danach** die alte Version installieren – deren Start findet den Stand des
Backups vor.

```bash
sudo systemctl stop praxiszeit
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore /opt/praxiszeit/data/backups/<backup-vor-dem-update>.sql.gz
sudo mv /opt/praxiszeit/app /opt/praxiszeit/app.neu-$(date +%F)
# danach das alte Paket wie unter „Native → Linux“ installieren (legt app/ neu an und startet den Dienst)
```

```bash
# macOS: Ordner /usr/local/praxiszeit, Dienstkonto _praxiszeit, launchd
sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist
sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore /usr/local/praxiszeit/data/backups/<backup-vor-dem-update>.sql.gz
sudo mv /usr/local/praxiszeit/app /usr/local/praxiszeit/app.neu-$(date +%F)
# danach das alte Paket wie unter „Native → macOS“ installieren (lädt den Dienst am Ende)
```

**Warum `app/` beiseite:** Der Installer ersetzt `app/` nicht, er kopiert das neue
Paket nur darüber (er „löscht nichts“, siehe oben). Ohne diesen Schritt blieben die
Migrationsdateien der neueren Version in `app/backend/alembic/versions` liegen; schon
der erste Start der alten Version fände sie und höbe die Datenbank gleich wieder auf
den neuen Stand – mit Programmcode, der dieses Schema nicht kennt. Beim Rückweg von
1.20.0 auf 1.19.x wendet er `073` erneut an: die alten Fenster-Spalten sind wieder
weg, und **die alte Version startet nicht mehr** (sie fragt diese Spalten ab:
„column users.scheduled_start_monday does not exist“). `restore` erinnert daran, wenn
das Backup älter ist als die installierte Version. Den beiseitegelegten Ordner nach
erfolgreichem Rollback löschen.

Den Dienst zwischen `restore` und dem alten Paket **nicht** starten: die noch
installierte neue Version höbe das Backup beim Start wieder auf ihren Stand.
Andersherum (erst das alte Paket, dann das Backup) geht es nicht: mit frischem `app/`
startet die alte Version auf dem Datenbankstand der neueren gar nicht („Can't locate
revision“), und vor 1.20.0 kennt der Prozessmanager kein `restore`.

Windows (Administrator-Eingabeaufforderung) in dieser Reihenfolge: Dienst anhalten,
den Ordner `app` umbenennen, das alte Paket mit **dessen** `update-wizard.bat`
einspielen und **danach** mit `restore-backup.bat` das Backup einspielen. Der
Update-Wizard mischt ebenfalls nur darüber (robocopy ohne Löschen). Der Dienststart
am Ende des Wizards kann scheitern – die alte Version kennt den Datenbankstand der
neueren nicht; `restore-backup.bat` hält den Dienst an, spielt das Backup ein und
startet ihn wieder. Andersherum ginge es nicht: das Script startet den Dienst am Ende,
und die noch installierte neue Version höbe das Backup sofort wieder auf ihren Stand.

```bat
net stop PraxisZeit
cd C:\PraxisZeit
ren app app.neu
:: im entpackten alten Paket: update-wizard.bat (legt app neu an)
:: danach im Installationsordner:
restore-backup.bat data\backups\<backup-vor-dem-update>.sql.gz
```

Migrationen sind in der Regel vorwärtskompatibel; ein Downgrade des Schemas wird
**nicht** unterstützt — daher das Backup. Ab 1.20.0 gilt das besonders: Migration `073` entfernt die Spalten der alten Arbeitszeit-Fenster (siehe Kasten oben).
