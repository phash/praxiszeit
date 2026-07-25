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
# Linux / macOS
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 \
    /opt/praxiszeit/praxiszeit-server.py backup          # macOS: /usr/local/praxiszeit/...
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

Die Backups sind **gzip-komprimierte Plain-SQL-Dumps** (`praxiszeit_<ts>.sql.gz`,
erzeugt mit `--clean --if-exists` → der Restore dropt + legt die Objekte neu an).
Erst entpacken, dann durch `psql` leiten — **nicht** `psql -f` auf die `.gz`:

```bash
# Linux/macOS — gebündeltes psql, Verbindung über den eigenen Unix-Socket.
# Das Superuser-Passwort steht in config/.db-credentials (SUPERUSER_PASSWORD=...).
PZ=/opt/praxiszeit          # macOS: /usr/local/praxiszeit
export PGPASSWORD="$(grep '^SUPERUSER_PASSWORD=' "$PZ/config/.db-credentials" | cut -d= -f2-)"
gunzip -c "$PZ/data/backups/<datei>.sql.gz" \
  | "$PZ/bin/postgresql/bin/psql" -w -h "$PZ/data/run" -U praxiszeit -d praxiszeit
unset PGPASSWORD
```
> Möglichst zu einem ruhigen Zeitpunkt einspielen (kein paralleles Stempeln).
> Der Dienst (und damit PostgreSQL) muss laufen, damit der Socket erreichbar ist.

```bat
:: Windows — der gebündelte restore-backup.bat stoppt den Dienst, legt die DB
:: frisch an, entpackt und spielt das Backup ein (erwartet die .sql.gz direkt):
cd C:\PraxisZeit
restore-backup.bat data\backups\<datei>.sql.gz
```

### Docker

Mit dem mitgelieferten Script (empfohlen — entpackt + spielt ein), aus dem
Verzeichnis neben der `docker-compose.yml` ausführen:

```bash
bash restore.sh backups/praxiszeit_<ts>.sql.gz
```

Oder von Hand — das `.sql.gz` **direkt** durch `psql` leiten (nicht vorher als
Datei entpacken). Da die Dumps mit `--clean --if-exists` erzeugt werden, ist der
Restore idempotent (vorhandene Objekte werden gedroppt und neu angelegt) — ein
manuelles Leeren der DB ist **nicht** nötig:

```bash
gunzip -c backup.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit
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
