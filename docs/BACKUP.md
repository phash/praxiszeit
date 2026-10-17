# Datensicherung (Backup & Restore)

PraxisZeit speichert alle Zeitdaten in PostgreSQL. **§16 ArbZG verlangt eine
Aufbewahrung von mindestens 2 Jahren** — sorgen Sie für Backups und prüfen Sie
gelegentlich die Wiederherstellung.

## Am einfachsten: über die Admin-Oberfläche (ab 1.9.0)

**Admin → Datensicherung** (Menüpunkt links). Funktioniert in **beiden**
Varianten (Native **und** Docker), ohne Kommandozeile:

- **Sofort sichern** — erzeugt umgehend ein vollständiges, komprimiertes Backup
  (`praxiszeit_<zeitstempel>.sql.gz`, Plain-SQL mit `--clean --if-exists`).
- **Geplante Sicherung** — täglich zur eingestellten Stunde aktivieren, mit
  Aufbewahrungsdauer (Tage) und optionalem Speicherort.
- **Liste** — vorhandene Backups herunterladen oder löschen.

> **Wo liegen die Backups?** Docker: im Volume `praxiszeit_backups`
> (`/app/backups` im Backend-Container). Native: im konfigurierten
> `data/backups/`. Für eine externe Kopie laden Sie die Datei über die Liste
> herunter oder sichern das Volume/Verzeichnis zusätzlich extern (s. u.).
>
> **Native-Hinweis:** Die *geplante* Sicherung läuft nativ weiterhin über den
> OS-Timer (systemd/launchd/Task, s. u.) — die In-App-Zeitplan-Einstellung steuert
> die **Docker**-Variante. Der **manuelle** Trigger + die Liste funktionieren auf
> beiden.

## Automatisches Backup — pro Variante

| Variante | Automatisch? | Wie / wann | Ablage |
|----------|--------------|------------|--------|
| **Native Linux** | ✅ ja | systemd-Timer `praxiszeit-backup.timer`, täglich **02:00** | `<install>/data/backups/` |
| **Native Windows** | ✅ ja | Scheduled Task `PraxisZeit-Backup`, täglich **03:00** (ruft `backup.bat`) | `C:\PraxisZeit\data\backups\` |
| **Native macOS** | ✅ ja | launchd `de.praxiszeit.backup.plist`, täglich **03:00** | `/usr/local/praxiszeit/data/backups/` |
| **Docker** | ✅ optional | In-App **Datensicherung** aktivieren (täglich), oder Host-Cron (s. u.) | Volume `praxiszeit_backups` bzw. wohin Sie den Dump schreiben |

> **Native:** Das Backup ruft intern `praxiszeit-server.py backup`. Der Dienst
> muss dafür **nicht** gestoppt werden (Online-Dump, Plain-SQL `pg_dump` + gzip).
> Standard-Aufbewahrung: **31 Tage** (`retention_days` in `praxiszeit.conf` → für
> §16 auf z. B. `730` (= 2 Jahre) erhöhen, oder zusätzlich Jahresarchive extern
> ablegen).
>
> **Docker:** Ab 1.9.0 kann der Admin in **Datensicherung** eine tägliche
> Sicherung aktivieren (läuft im Backend per Scheduler, Ablage im Volume
> `praxiszeit_backups`). Alternativ/zusätzlich ein Host-Cron (s. u.) oder das
> mitgelieferte Script `tools/docker/backup.sh` (im Docker-Bundle).

---

## Manuelles Backup

### Native (Linux / macOS / Windows)

Erzeugt sofort ein Backup im konfigurierten `data/backups/`-Verzeichnis (gleiche
Routine wie das automatische, inkl. Aufräumen alter Backups):

```bash
# Linux
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 \
    /opt/praxiszeit/praxiszeit-server.py backup

# macOS (Dienstkonto mit Unterstrich, anderer Installationsordner)
sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 \
    /usr/local/praxiszeit/praxiszeit-server.py backup
```

```bat
:: Windows (als Administrator)
cd C:\PraxisZeit
backup.bat
```

Backups anzeigen:
```bash
ls -la /opt/praxiszeit/data/backups/          # Windows: dir C:\PraxisZeit\data\backups
```

### Docker

Am einfachsten über die Admin-Oberfläche (**Datensicherung → Jetzt sichern**,
s. o.). Auf der Kommandozeile gibt es im Docker-Bundle das geprüfte Script
(empfohlen — gzip + Integritätsprüfung) — aus dem Verzeichnis neben der
`docker-compose.yml`/`​.env` ausführen:

```bash
bash backup.sh                       # -> ./backups/praxiszeit_<ts>.sql.gz
```

Oder direkt aus dem `db`-Container (Dienst läuft weiter) — **mit gzip**, damit der
Restore mit `gunzip -c | psql` zusammenpasst:

```bash
docker compose exec -T db pg_dump -U praxiszeit --clean --if-exists praxiszeit \
    | gzip > backup-$(date +%F).sql.gz
```

**Automatisieren per Host-Cron** (empfohlen, da Docker kein Auto-Backup hat) —
täglich 02:00 + 30-Tage-Rotation:

```cron
0 2 * * * cd /pfad/zu/praxiszeit && docker compose exec -T db pg_dump --clean --if-exists -U praxiszeit praxiszeit | gzip > ~/praxiszeit-backups/pz_$(date +\%F).sql.gz && find ~/praxiszeit-backups -name 'pz_*.sql.gz' -mtime +30 -delete
```

(Backup-Verzeichnis vorher anlegen: `mkdir -p ~/praxiszeit-backups`.)

---

## Restore (Wiederherstellung)

> Vorher prüfen, welche Version das Backup erzeugt hat — ein Restore in eine
> **ältere** Schemaversion wird nicht unterstützt (Migrationen sind vorwärts).

### Native

Die Backups sind **gzip-komprimierte Plain-SQL-Dumps** (`praxiszeit_<ts>.sql.gz`).
Unter Linux und macOS spielt sie ab 1.20.0 der Prozessmanager ein — Dienst
anhalten, Backup einspielen, Dienst wieder starten:

```bash
# Linux
sudo systemctl stop praxiszeit
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore /opt/praxiszeit/data/backups/<datei>.sql.gz
sudo systemctl start praxiszeit

# macOS (Dienstkonto mit Unterstrich, launchd statt systemd)
sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist
sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore /usr/local/praxiszeit/data/backups/<datei>.sql.gz
sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist
```

`restore` prüft das Backup auf Vollständigkeit, startet PostgreSQL nur für die
Dauer des Vorgangs, spielt das Backup in eine Zwischendatenbank ein und ersetzt
die bisherige Datenbank erst, wenn das gelungen ist. Scheitert etwas — abgebrochener
Dump, Fehler beim Einspielen, Backup einer **neueren** Version —, bleibt die
bisherige Datenbank unverändert, und der Dienst lässt sich wieder starten. Läuft
der Dienst noch, bricht das Kommando ab, ohne etwas anzufassen.

Erst der anschließende Dienststart hebt ein Backup einer älteren Version per
Migration auf den Stand der installierten Version (nativ laufen Migrationen nur
beim Start des Dienstes). Danach die Ausgabe der Migrationen in
`logs/praxiszeit.log` lesen (Zeilen mit `alembic:`, Hinweise zwischen
`*** HINWEIS` und `*** ENDE HINWEIS ***`).

> **Als Dienstkonto, nicht als root:** Bei angehaltenem Dienst muss `restore`
> PostgreSQL selbst starten, und `pg_ctl` verweigert das als root. Die
> Backup-Datei muss für das Dienstkonto lesbar sein — eine Datei von außerhalb
> zuerst nach `data/backups/` kopieren und dem Dienstkonto geben
> (`chown praxiszeit:praxiszeit …`, macOS `_praxiszeit:staff`).
>
> Bis 1.19 stand hier ein `gunzip -c … | psql` bei **laufendem** Dienst. Das
> ließ den Dienst gegen den Stand des Backups weiterarbeiten (nach dem Update auf
> 1.20.0: Anmeldung mit HTTP 500, bis zum nächsten Neustart), brach bei Backups
> von 1.18 und älter an Tabellen ab, die erst später hinzukamen, und meldete
> trotz Fehlern Erfolg.

```bat
:: Windows — als Administrator; erwartet die .sql.gz direkt:
cd C:\PraxisZeit
restore-backup.bat data\backups\<datei>.sql.gz
```

`restore-backup.bat` arbeitet wie `restore`: Es prüft das Backup **vor** jeder
Änderung auf Vollständigkeit, hält dann den Dienst an, spielt das Backup in eine
Zwischendatenbank ein (Abbruch beim ersten Fehler) und ersetzt die bisherige
Datenbank erst danach. Scheitert ein Schritt — auch bei einem Backup einer
**neueren** Version —, bleibt die bisherige Datenbank unverändert, der Dienst
bleibt aus, und das Script endet mit einer FEHLER-Meldung statt „Restore abgeschlossen!“. Liegt PraxisZeit nicht unter `C:\praxiszeit`,
vorher `set PRAXISZEIT_INSTALL_DIR=<ordner>` setzen.

### Docker

Mit dem mitgelieferten Script (empfohlen), aus dem Verzeichnis neben der
`docker-compose.yml` ausführen (im git-Checkout: `bash tools/docker/restore.sh …`):

```bash
bash restore.sh backups/praxiszeit_<ts>.sql.gz
```

Das Script prüft das Backup auf Vollständigkeit, hält das Backend an, legt die
Datenbank frisch an, spielt das Backup ein und startet das Backend wieder. Erst
dieser Start hebt ein Backup einer älteren Version per Migration auf den Stand der
installierten Version – Migrationen laufen nur beim Start des Backend-Containers,
und `docker compose up -d backend` startet ein schon laufendes Backend **nicht**
neu. Das Script meldet sich erst, wenn das Backend wieder gesund ist; danach die
Ausgabe der Migrationen lesen (`docker compose logs backend`).

Oder von Hand — nur für ein Backup **derselben** Version und mit angehaltenem
Backend. Die Dumps sind mit `--clean --if-exists` erzeugt: vorhandene Objekte, die
im Backup vorkommen, werden gedroppt und neu angelegt. Eine Tabelle, die erst eine
neuere Version angelegt hat, bleibt dagegen stehen und kann das Einspielen eines
älteren Backups abbrechen – dafür das Script nehmen. Das `.sql.gz` **direkt** durch
`psql` leiten (nicht vorher als Datei entpacken):

```bash
docker compose stop backend
gunzip -c backup.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit
docker compose start backend
```

---

## Compliance-Checkliste (§16 ArbZG)

- [ ] Automatisches Backup aktiv (Native: ja ab Installation; **Docker: in der Admin-Oberfläche *Datensicherung* aktivieren** oder Host-Cron)
- [ ] Aufbewahrung deckt **mind. 2 Jahre** ab (`retention_days` erhöhen oder Jahresarchive extern)
- [ ] Backup-Ziel liegt **nicht nur** auf demselben Server (externe Kopie)
- [ ] Restore regelmäßig testen
- [ ] Vor jedem **Update** zusätzlich ein Backup ziehen → [UPDATE.md](UPDATE.md)

---

*Details zur Installation: [INSTALL-NATIVE.md](INSTALL-NATIVE.md) · [INSTALL-DOCKER.md](INSTALL-DOCKER.md) · [DOCKER-START.md](DOCKER-START.md)*
