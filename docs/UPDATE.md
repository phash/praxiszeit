# PraxisZeit aktualisieren (Docker & Native)

So bringen Sie eine **bestehende** Installation auf eine neue Version — ohne
Datenverlust. Datenbank-Migrationen laufen bei jedem Start automatisch.

> **Immer zuerst: Backup.** Vor jedem Update eine Datensicherung ziehen (siehe
> unten je Variante). PraxisZeit speichert ArbZG-pflichtige Daten — §16 verlangt
> 2 Jahre Aufbewahrung.

> **Nach jedem Update: Browser-Hard-Refresh** (`Strg`+`F5` bzw. `Cmd`+`Shift`+`R`)
> oder einmal im Inkognito-Fenster öffnen — sonst lädt der Browser das alte
> Frontend aus dem Cache (Service-Worker/PWA).

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

# HTTP:
docker compose up -d --build
# ODER HTTPS:
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

> Wichtig: Das **Postgres-Volume** muss dasselbe bleiben. Starten Sie das Update
> im **selben Verzeichnis** wie zuvor (gleicher Compose-Projektname = gleiches
> Volume), oder setzen Sie `COMPOSE_PROJECT_NAME` identisch. Im Zweifel: vor dem
> Wechsel das SQL-Backup ziehen und nach dem Start prüfen, ob die Daten da sind.

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
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build   # oder ohne -f … für HTTP
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

### Linux / macOS

```bash
# 1. Backup (Dienst läuft) — DB + Konfiguration sichern
sudo systemctl stop praxiszeit                         # Linux (macOS: launchctl unload, s. INSTALL-NATIVE.md)
cp -a /opt/praxiszeit/config /opt/praxiszeit/config.bak-$(date +%F)
ls /opt/praxiszeit/data/backups/                       # nächtliche Backups liegen hier

# 2. Neues Tarball flach in einen Ordner entpacken + Installer erneut ausführen
mkdir -p praxiszeit-<neu>
tar xzf praxiszeit-<neu>-linux-x64.tar.gz -C praxiszeit-<neu>      # macOS: -macos-x64 / -macos-arm64
cd praxiszeit-<neu>
sudo ./install.sh                                       # erkennt die bestehende Installation,
                                                        # behält Daten/Config/Lizenz, spielt nur Code + Migrationen ein

# 3. Dienst läuft danach wieder; Status prüfen
sudo systemctl status praxiszeit
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
- `GET /openapi.json` enthält sie ebenfalls — aber nur, solange `ENVIRONMENT` nicht auf `production` steht. Die Docker-Installation setzt das über `generate-secrets.sh` automatisch, dort antwortet der Pfad mit **404**.
- `GET /api/health` liefert die Version bewusst **nicht** (nur Status und Datenbank).

---

## Rollback

Es gibt keinen automatischen Rollback. Im Problemfall: die alte Paket-/Code-Version
erneut einspielen und das **vor** dem Update gezogene DB-Backup zurückspielen.
Docker (zum `--clean`-gzip-Backup aus Schritt 1):

```bash
gunzip -c backup-JJJJ-MM-TT.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit
docker compose up -d backend
```

Nativ: `pg_dump`/`psql` aus `bin/postgresql/bin` (siehe INSTALL-Dokumente).
Migrationen sind in der Regel vorwärtskompatibel; ein Downgrade des Schemas wird
**nicht** unterstützt — daher das Backup.
