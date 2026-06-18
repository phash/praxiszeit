# Datensicherung (Backup & Restore)

PraxisZeit speichert alle Zeitdaten in PostgreSQL. **§16 ArbZG verlangt eine
Aufbewahrung von mindestens 2 Jahren** — sorgen Sie für Backups und prüfen Sie
gelegentlich die Wiederherstellung.

## Automatisches Backup — pro Variante

| Variante | Automatisch? | Wie / wann | Ablage |
|----------|--------------|------------|--------|
| **Native Linux** | ✅ ja | systemd-Timer `praxiszeit-backup.timer`, täglich **02:00** | `<install>/data/backups/` |
| **Native Windows** | ✅ ja | Scheduled Task `PraxisZeit-Backup`, täglich **03:00** (ruft `backup.bat`) | `C:\PraxisZeit\data\backups\` |
| **Native macOS** | ✅ ja | launchd `de.praxiszeit.backup.plist`, täglich **03:00** | `/usr/local/praxiszeit/data/backups/` |
| **Docker** | ❌ **nein** | nur manuell bzw. per Host-Cron (s. u.) | wohin Sie den Dump schreiben |

> **Native:** Das Backup ruft intern `praxiszeit-server.py backup`. Der Dienst
> muss dafür **nicht** gestoppt werden (Online-Dump). Standard-Aufbewahrung:
> **31 Tage** (`retention_days` in `praxiszeit.conf` → für §16 auf z. B. `760`
> erhöhen, oder zusätzlich Jahresarchive extern ablegen).
>
> **Docker hat KEIN eingebautes Auto-Backup** — richten Sie einen Host-Cron ein
> (siehe unten) oder ziehen Sie regelmäßig ein manuelles Backup.

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

Direkter DB-Dump aus dem `db`-Container (Dienst läuft weiter):

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
    > backup-$(date +%F).sql
```

**Automatisieren per Host-Cron** (empfohlen, da Docker kein Auto-Backup hat) —
täglich 02:00 + 30-Tage-Rotation:

```cron
0 2 * * * cd /pfad/zu/praxiszeit && docker compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > ~/praxiszeit-backups/pz_$(date +\%F).sql.gz && find ~/praxiszeit-backups -name 'pz_*.sql.gz' -mtime +30 -delete
```

(Backup-Verzeichnis vorher anlegen: `mkdir -p ~/praxiszeit-backups`.)

---

## Restore (Wiederherstellung)

> Vorher prüfen, welche Version das Backup erzeugt hat — ein Restore in eine
> **ältere** Schemaversion wird nicht unterstützt (Migrationen sind vorwärts).

### Native

```bash
# Linux/macOS — psql aus dem gebündelten PostgreSQL
/opt/praxiszeit/bin/postgresql/bin/psql -U praxiszeit -h /opt/praxiszeit/data/run \
    -d praxiszeit -f /opt/praxiszeit/data/backups/<datei>.sql
```
```bat
:: Windows
C:\PraxisZeit\bin\postgresql\bin\psql.exe -U praxiszeit -h localhost -d praxiszeit -f <datei>.sql
```

### Docker

```bash
# .sql.gz vorher entpacken: gunzip pz_<datum>.sql.gz
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql
```

---

## Compliance-Checkliste (§16 ArbZG)

- [ ] Automatisches Backup aktiv (Native: ja ab Installation; **Docker: Host-Cron einrichten**)
- [ ] Aufbewahrung deckt **mind. 2 Jahre** ab (`retention_days` erhöhen oder Jahresarchive extern)
- [ ] Backup-Ziel liegt **nicht nur** auf demselben Server (externe Kopie)
- [ ] Restore regelmäßig testen
- [ ] Vor jedem **Update** zusätzlich ein Backup ziehen → [UPDATE.md](UPDATE.md)

---

*Details zur Installation: [INSTALL-NATIVE.md](INSTALL-NATIVE.md) · [INSTALL-DOCKER.md](INSTALL-DOCKER.md) · [DOCKER-START.md](DOCKER-START.md)*
