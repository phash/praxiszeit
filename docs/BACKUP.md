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

> **Speicherort (Audit 2026-11-07):** Netzwerkpfade (`\\Server\Freigabe`),
> Netzlaufwerke, für alle Konten lesbare Ordner (z. B. `C:\Users\Public`),
> Systemordner und das Stammverzeichnis eines Laufwerks lehnt die Oberfläche ab;
> unter Windows außerdem alles unter `C:\Users` (Benutzerprofile),
> `C:\ProgramData` und `C:\Program Files`. Unter Windows gilt: einen **neuen**
> Ordner (noch nicht vorhanden, der übergeordnete schon) legt PraxisZeit selbst
> an und gibt ihm die Rechte „nur SYSTEM und Administratoren“. Einen
> **bestehenden** Ordner ändert PraxisZeit nicht — er wird nur übernommen, wenn
> er schon so eingeschränkt ist (Eigentümer SYSTEM oder Administratoren, keine
> geerbten Rechte); sonst erscheint ein Hinweis, einen neuen Ordnernamen
> einzutragen. Lassen sich die Rechte nicht einrichten, wird der Ordner nicht
> übernommen. Eine Kopie außer Haus gehört nicht auf eine
> Netzwerkfreigabe des Dienstes, sondern verschlüsselt auf ein externes Medium
> (siehe [Sicherheit der Sicherungen](#sicherheit-der-sicherungen)).

## Sicherheit der Sicherungen

Eine Sicherung ist die **vollständige Datenbank im Klartext** (gzip ist keine
Verschlüsselung): alle Mitarbeitenden, Arbeitszeiten, Krankheits- und andere
Abwesenheitstage (Gesundheitsdaten nach Art. 9 DSGVO), Passwort-Hashes und die
verschlüsselten 2FA-Geheimnisse. PraxisZeit verschlüsselt die Dumps selbst
**nicht** — das ist ein bewusst dokumentiertes Restrisiko des Vor-Ort-Betriebs.
Deshalb:

- **Auf dem Server** liegen die Dumps nur für den Dienst lesbar (Linux/macOS
  `0600`, Windows nur SYSTEM und Administratoren, die Docker-Skripte
  `backup.sh`/`backup-db.sh` ebenfalls `0600`).
- **Kopie außer Haus nur verschlüsselt**, z. B.
  - Windows: 7-Zip-Archiv mit *AES-256* und *Dateinamen verschlüsseln*, oder ein
    mit BitLocker To Go verschlüsselter USB-Datenträger;
  - Linux/macOS: `gpg --symmetric --cipher-algo AES256 praxiszeit_<ts>.sql.gz`
    oder `age -p -o praxiszeit_<ts>.sql.gz.age praxiszeit_<ts>.sql.gz`;
  - ein verschlüsseltes Laufwerk (LUKS, FileVault, BitLocker).
  Das Passwort getrennt vom Datenträger aufbewahren (Passwort-Safe, Tresor).
- **Heruntergeladene Sicherungen** (Liste → Herunterladen) landen im
  Download-Ordner des Admin-PCs. Dort nach dem Verschlüsseln/Wegspeichern
  löschen — der PC ist meist nicht verschlüsselt und wird von mehreren
  Personen benutzt.
- **Nur eigene Sicherungen einspielen.** Eine Datei aus fremder Quelle
  („Ihre Sicherung vom alten PC“, Mail eines „Technikers“) kann Befehle
  enthalten, die beim Einspielen mit vollen Datenbankrechten laufen. Deshalb
  sind die Sicherungen **signiert** (siehe unten), und die Wiederherstellung
  lehnt zusätzlich psql-Befehle und SQL ab, die `pg_dump` für PraxisZeit nie
  schreibt.

### Signatur der Sicherungen

Jede Sicherung, die PraxisZeit schreibt (Admin-Oberfläche, nächtliche
Sicherung, `praxiszeit-server.py backup`, Docker `backup.sh`/`backup-db.sh`),
endet mit einer Kommentarzeile `-- praxiszeit-backup-hmac-v1 <Prüfwert>`: ein
HMAC-SHA256 über den ganzen Dump, gebildet mit einem aus dem `SECRET_KEY` der
Installation abgeleiteten Schlüssel. Für `psql` ist die Zeile ein Kommentar, die
Datei bleibt ein normaler Dump.

`restore`, `restore-backup.bat` und `restore.sh` spielen nur eine Sicherung mit
**passender** Signatur ein. Ohne Signatur (Sicherung einer älteren Version, die
Sicherung von `uninstall.bat`, ein von Hand erstellter Dump) oder mit einer
Signatur eines anderen `SECRET_KEY` (anderer Rechner) brechen sie ab, **bevor**
etwas verändert wird. Stammt die Datei sicher aus der eigenen Installation,
den Aufruf mit `--force-unverified` wiederholen. Nativ (`restore`,
`restore-backup.bat`) läuft die Prüfung auf fremde Befehle trotzdem: abgelehnt
werden psql-Befehle, Rollen und Rollen-Mitgliedschaften, Daten-Anweisungen
außerhalb von `COPY` (pg_dump schreibt Daten nur als `COPY`) und jeder Zugriff
auf Systemkataloge wie `pg_authid` außerhalb der Funktionsrümpfe sowie jeder
schreibende Zugriff darauf in einem Funktionsrumpf, dazu `U&"…"`-Bezeichner,
`CREATE RULE`, Funktionen in anderen Sprachen als `sql`/`plpgsql` und
Funktionsrümpfe mit dynamischem oder verschachteltem Code (`EXECUTE`, `DO`,
`CREATE FUNCTION/TRIGGER/RULE`), mit E-Zeichenketten samt Backslash oder mit
anderen `pg_*`-Namen als denen der eigenen Protokollfunktionen.

Diese Liste ist nur die zweite Linie. **Nativ (`restore` unter Linux/macOS,
`restore-backup.bat` unter Windows) lädt eine unverifizierte Sicherung als
eigene, kurzlebige Datenbankrolle
`praxiszeit_restore_load` ohne Superuser-Rechte** (kein `CREATEROLE`,
`CREATEDB`, `BYPASSRLS`, keine Mitgliedschaft, Zufallspasswort, darf nur im
Schema `public` der Zwischendatenbank Objekte anlegen; die Datenbank selbst
gehört dem Superuser und entsteht aus `template0`, Erweiterungen kann die
Rolle nicht anlegen). Was die Liste übersieht — Systemkataloge
schreiben, `COPY … PROGRAM`, Server-Dateien lesen, C-Funktionen anlegen,
Rollen ändern, Funktionen, die beim Laden in einem Index oder `CHECK` laufen —
lehnt dann der Server selbst ab. Die `OWNER TO`-Zeilen des Dumps entfallen
dabei; danach überträgt PraxisZeit alle Objekte an den Datenbank-Superuser und
entfernt die Rolle. Das Ergebnis ist dasselbe wie beim Laden als Superuser
(die Standardrechte setzt `init-db-user.sql` danach wie immer). **Vor der
Übertragung müssen Funktionen und Trigger genau denen entsprechen, die die
Migrationen dieser Installation bis zum Datenbankstand der Sicherung anlegen**
(gleicher Inhalt, gleiche Sprache, `SECURITY DEFINER` und Einstellungen;
Trigger mit gleichem Zeitpunkt, gleichen Ereignissen und Spalten, `WHEN` und
`FOR EACH ROW`; keine Sichten, Regeln oder Ereignis-Trigger; als Erweiterung
nur `plpgsql` in Standardform), **und jede Tabelle mit Zeilenschutz muss ihn
mit `FORCE` und genau den Policies der Migrationen haben** — sonst liefe eine
Funktion, die die Liste übersieht, danach mit den Rechten des Superusers, oder
die Mandantentrennung wäre still geschwächt. Weicht etwas ab, bricht
der Vorgang mit der Liste der Abweichungen ab; die bisherige Datenbank bleibt
unverändert. **`restore.sh` (Docker)
prüft die Anweisungen nicht** — dort sperrt nur der eigene `\restrict`-Schlüssel
die psql-Befehle; eine erzwungene Sicherung läuft sonst ungeprüft als
Datenbank-Superuser. Mit `--force-unverified` unter Docker also nur Dateien
einspielen, die nachweislich von der eigenen Installation stammen:

```bash
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore <datei>.sql.gz --force-unverified
bash restore.sh backups/<datei>.sql.gz --force-unverified          # Docker
```

```bat
restore-backup.bat data\backups\<datei>.sql.gz --force-unverified
```

Für den Umzug auf einen neuen Rechner deshalb am besten zuerst den alten
`SECRET_KEY` zurücklegen (nächster Abschnitt) — dann passt die Signatur.

### Den Schlüssel `SECRET_KEY` mitsichern (einmalig, getrennt)

Die Datenbanksicherung allein reicht für einen **neuen Rechner** nicht: mit dem
Schlüssel `SECRET_KEY` sind die 2FA-Geheimnisse verschlüsselt und die
Prüfsummen des Änderungsprotokolls (§ 16 ArbZG, „Integrität prüfen“) gebildet.
Ohne den alten Schlüssel muss jede Person 2FA neu einrichten, und die
Integritätsprüfung meldet alle Protokollzeilen als verändert.

| Variante | Wo liegt der Schlüssel? |
|----------|--------------------------|
| Native (Linux/macOS/Windows) | `config/.secret-key` (bzw. `[security] secret_key` in `config/praxiszeit.conf`, falls dort gesetzt) |
| Docker | `SECRET_KEY` in der `.env` |

Den Schlüssel **einmal** (und nach jeder Änderung) zusammen mit
`config/praxiszeit.conf` bzw. `.env` **verschlüsselt und getrennt** von den
Dumps aufbewahren — etwa im Passwort-Safe der Praxis. Er gehört bewusst **nicht**
in jede Sicherungsdatei: wer Dump und Schlüssel zusammen hat, könnte sich mit
dem Schlüssel zusätzlich gültige Anmelde-Token ausstellen. Bei einer
Wiederherstellung auf einem neuen Rechner die alte `config/.secret-key` (bzw.
den alten `SECRET_KEY` in der `.env`) **vor dem ersten Start** zurücklegen —
dann prüft die Wiederherstellung auch die Signatur der alten Sicherungen.

## Automatisches Backup — pro Variante

| Variante | Automatisch? | Wie / wann | Ablage |
|----------|--------------|------------|--------|
| **Native Linux** | ✅ ja | systemd-Timer `praxiszeit-backup.timer`, täglich **02:00** | `<install>/data/backups/` |
| **Native Windows** | ✅ ja | Scheduled Task `PraxisZeit-Backup`, täglich **03:00** (ruft `backup.bat`) | `C:\PraxisZeit\data\backups\` |
| **Native macOS** | ✅ ja | launchd `de.praxiszeit.backup.plist`, täglich **03:00** | `/usr/local/praxiszeit/data/backups/` |
| **Docker** | ✅ optional | In-App **Datensicherung** aktivieren (täglich), oder Host-Cron mit `backup.sh` (s. u.) | Volume `praxiszeit_backups` bzw. `./backups/` neben der `docker-compose.yml` |

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

Backups anzeigen (`data/` ist nur fürs Dienstkonto lesbar — Linux mit `sudo`,
Windows in einer Eingabeaufforderung **als Administrator**):
```bash
sudo ls -la /opt/praxiszeit/data/backups/     # Windows (als Administrator): dir C:\PraxisZeit\data\backups
```

### Docker

Am einfachsten über die Admin-Oberfläche (**Datensicherung → Jetzt sichern**,
s. o.). Auf der Kommandozeile gibt es im Docker-Bundle das geprüfte Script
(empfohlen — gzip + Integritätsprüfung) — aus dem Verzeichnis neben der
`docker-compose.yml`/`​.env` ausführen:

```bash
bash backup.sh                       # -> ./backups/praxiszeit_<ts>.sql.gz (signiert)
```

Ab 1.23.0 [signiert](#signatur-der-sicherungen) `backup.sh` die Sicherung; dafür
muss neben dem `db`- auch der `backend`-Dienst laufen. Ist das Backend nicht
erreichbar, entsteht die Sicherung trotzdem, aber ohne Signatur (Warnung in der
Ausgabe), und `restore.sh` verlangt für sie `--force-unverified`.

Ein von Hand gezogener Dump aus dem `db`-Container geht ebenfalls, ist aber
**unsigniert** — `restore.sh` spielt ihn nur mit `--force-unverified` ein, und
dann laufen seine Anweisungen ungeprüft als Datenbank-Superuser:

```bash
docker compose exec -T db pg_dump -U praxiszeit --clean --if-exists praxiszeit \
    | gzip > backup-$(date +%F).sql.gz
```

**Automatisieren per Host-Cron** (Alternative zur In-App-Datensicherung) —
täglich 02:00 + 30-Tage-Rotation. `backup.sh` wechselt selbst in seinen Ordner und
schreibt nach `backups/` daneben (git-Checkout: `tools/docker/backup.sh`, Ablage
`backups/` im Repo-Root):

```cron
0 2 * * * bash /pfad/zu/praxiszeit/backup.sh && find /pfad/zu/praxiszeit/backups -name 'praxiszeit_*.sql.gz' -mtime +30 -delete
```

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
> (`chown praxiszeit:praxiszeit …`, macOS `_praxiszeit:_praxiszeit`).
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
bleibt aus, und das Script endet mit einer FEHLER-Meldung statt „Restore abgeschlossen!“. Es arbeitet im
Ordner, in dem es liegt (ein anderer Ordner über
`set PRAXISZEIT_INSTALL_DIR=<ordner>`), auch mit Leerzeichen im Pfad. Die
entpackte Datei liegt während des Vorgangs in `data\` (nur SYSTEM und
Administratoren) und wird auch nach einem abgebrochenen Lauf beim nächsten
Aufruf entfernt.

> **Deinstallation (Windows):** `uninstall.bat` legt eine geprüfte Sicherung auf
> den Desktop (Abbruch, wenn `pg_dump` scheitert oder die Schlusszeile fehlt —
> dann wird nichts gelöscht) und verschiebt die automatischen Sicherungen aus
> `data\backups` nach `Desktop\PraxisZeit-Sicherungen-<Datum>`, bevor der
> Installationsordner entfernt wird. Die Desktop-Sicherung ist ein
> **unkomprimierter, unsignierter** Dump: zum Einspielen mit gzip packen und
> `restore-backup.bat <datei>.sql.gz --force-unverified` verwenden; die
> automatischen Sicherungen sind signiert (passend zum alten `SECRET_KEY`).
> Packen geht ohne Zusatzprogramm mit dem mitgelieferten Python — im
> Installationsordner (erzeugt `<datei>.sql.gz` neben der Datei):
>
> ```bat
> bin\python\python.exe -c "import gzip,shutil,sys; shutil.copyfileobj(open(sys.argv[1],'rb'), gzip.open(sys.argv[1]+'.gz','wb'))" <datei>.sql
> ```

### Docker

Mit dem mitgelieferten Script (empfohlen), aus dem Verzeichnis neben der
`docker-compose.yml` ausführen (im git-Checkout: `bash tools/docker/restore.sh …`):

```bash
bash restore.sh backups/praxiszeit_<ts>.sql.gz
```

Das Script prüft das Backup auf Vollständigkeit und auf die
[Signatur](#signatur-der-sicherungen) (im Backend-Container mit dessen
`SECRET_KEY`; ohne passende Signatur nur mit `--force-unverified`), hält das Backend an, legt die
Datenbank frisch an, spielt das Backup ein und startet das Backend wieder. Erst
dieser Start hebt ein Backup einer älteren Version per Migration auf den Stand der
installierten Version – Migrationen laufen nur beim Start des Backend-Containers,
und `docker compose up -d backend` startet ein schon laufendes Backend **nicht**
neu. Das Script meldet sich erst, wenn das Backend wieder gesund ist; danach die
Ausgabe der Migrationen lesen (`docker compose logs backend`).

Eine Sicherung ohne Signatur (von 1.22.0 oder älter, von Hand gezogen) spielt das
Script nur mit `--force-unverified` ein — und dann ungeprüft als Datenbank-Superuser
(siehe [Signatur](#signatur-der-sicherungen)), also nur mit Dateien der eigenen
Installation:

```bash
bash restore.sh backups/praxiszeit_<ts>.sql.gz --force-unverified
```

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
- [ ] Backup-Ziel liegt **nicht nur** auf demselben Server (externe Kopie, **verschlüsselt**)
- [ ] `SECRET_KEY` (`config/.secret-key` bzw. `.env`) einmal getrennt und verschlüsselt aufbewahrt
- [ ] Restore regelmäßig testen
- [ ] Vor jedem **Update** zusätzlich ein Backup ziehen → [UPDATE.md](UPDATE.md)

---

*Details zur Installation: [INSTALL-NATIVE.md](INSTALL-NATIVE.md) · [INSTALL-DOCKER.md](INSTALL-DOCKER.md) · [DOCKER-START.md](DOCKER-START.md)*
