# Windows-Test im Emulator

Ein echtes Windows 11 in einem Container (KVM), das ein gebautes Release-Paket
**unbeaufsichtigt installiert**, den Dienst startet, sich anmeldet und das
Ergebnis auf den Host zurückschreibt. Damit ist der Windows-Zweig vor einem
Release prüfbar, ohne dass ein Windows-Rechner bereitstehen muss.

**Warum das nötig ist:** Der Windows-Pfad hat Eigenschaften, die auf Linux
grundsätzlich nicht auffallen — `cmd.exe` findet in `.bat`-Dateien mit
LF-Zeilenenden keine Sprungmarken (realer Fehler #286: „PostgreSQL-Installation
fehlgeschlagen", obwohl PostgreSQL lief), der Dienst läuft über NSSM, PostgreSQL
kommt aus dem EDB-Installer statt aus den theseus-Tarbällen, und die
Rechte-Härtung auf `praxiszeit.conf` und `ssl/key.pem` existiert nur dort.
Unit-Tests und `validate-release.sh` sehen davon nichts.

Es gibt vier Läufe, gewählt über `share/mode.txt`:

- `fresh` (Vorgabe, Datei fehlt oder leer): **Erstinstallation** des Pakets aus `share/tree`.
- `update`: zuerst das **Vorgängerpaket** aus `share/tree-old` installieren, dann
  mit `update-wizard.ps1 -Headless` aus dem neuen Paket aktualisieren — derselbe
  Weg, den der GUI-Installer im Update-Modus nimmt.
- `foreignpg`: wie `fresh`, aber ein **fremdes PostgreSQL belegt Port 5432**
  (Wegwerf-Cluster `C:\foreignpg` aus den gebündelten Binaries, nach `setup.bat`
  angelegt — vorher gibt es die Binaries noch nicht). Der Dienst muss mit dem
  Standard-Port mit Exit 78 stehen bleiben und die Meldung „… ist von einem
  anderen PostgreSQL belegt …" nach `logs\service-stderr.log` schreiben; danach
  trägt der Lauf `[database] port = 5433` ein, startet neu und spielt eine
  Sicherung mit `restore-backup.bat` zurück. Der Fremdserver muss dabei
  unangetastet weiterlaufen.
- `portchange`: wie `fresh`, danach `[database] port = 5433` bei **laufendem**
  Dienst eintragen und sofort `restore-backup.bat` — der Restore muss den
  Portwechsel selbst nachziehen (`sync-db-port` hält „PraxisZeit-PostgreSQL“ an,
  das Script startet ihn wieder) und den Dienst auf 5433 hochbringen.

Alle Läufe enden mit einem **echten Neustart der VM**; danach prüft eine
geplante Aufgabe Dienst, Anmeldung und Rechte noch einmal.

---

## Voraussetzungen

| | |
|---|---|
| KVM | `/dev/kvm` muss vorhanden und nutzbar sein (`ls -l /dev/kvm`) |
| Docker | mit Compose-Plugin |
| Plattenplatz | ~60 GB frei (VM-Disk 48 GB dünn belegt + ~700 MB entpacktes Paket + Image) |
| VM-Ressourcen | 4 Kerne / 4 GB RAM (Vorgabe in `docker-compose.yml`) — der Host sollte deutlich mehr haben |
| Zeit | **40–70 Minuten** (Windows-Einrichtung, Installation, VM-Neustart; Wartefenster auf die Anwendung von je bis zu 6 Minuten nach dem Erststart und nach dem Dienst-Neustart, im `update`-Lauf zusätzlich nach dem Update, dazu bis zu 10 Minuten nach dem Neustart der VM) |
| Paket | ein gebautes `dist/praxiszeit-<version>-windows-x64.zip` → [BUILD-RELEASE.md](BUILD-RELEASE.md) |

---

## Aufbau

Alles liegt in `tools/win-test/`:

```
tools/win-test/
├── docker-compose.yml      dockur/windows (Windows 11), KVM, Web-Viewer auf :8006
├── oem/install.bat         läuft nach der Windows-Einrichtung automatisch als Administrator
└── share/
    ├── acl-check.ps1        Rechteprüfung einzelner Dateien (SID-basiert, also sprachunabhängig)
    ├── install-acl-check.ps1  Rechte des ganzen Installationsordners (Programmteile / private Ordner)
    ├── run-probe.ps1        legt ein Standardkonto an und startet damit nonadmin-probe.ps1
    ├── nonadmin-probe.ps1   versucht als Standardkonto zu schreiben und zu lesen
    ├── hardening-probe.ps1  Negativfälle von secure-install.ps1 in Wegwerf-Ordnern (C:\hp)
    ├── post-reboot.bat      Nachprüfung nach dem Neustart (geplante Aufgabe)
    ├── mode.txt            ← fresh | update | foreignpg | portchange (nicht im Repo)
    ├── tree-old/           ← Vorgängerpaket für den Update-Lauf (nicht im Repo)
    ├── admin-password.txt  ← Admin-Kennwort der Test-VM (nicht im Repo)
    ├── tree/               ← hier wird das Release-Paket entpackt (nicht im Repo)
    ├── aclprobe/           ← optionale .NET-Sonde (nicht im Repo)
    └── install-result.txt  ← Ergebnis des Laufs (nicht im Repo)
```

Die Zuordnung in der VM:

- `./oem` → `/oem` — dockur führt `install.bat` **einmalig** nach der
  Windows-Einrichtung mit Administratorrechten aus. Das ist der einzige
  Automatik-Haken; alles Weitere macht das Skript selbst.
- `./share` → `/data`, in der VM erreichbar als `\\host.lan\Data`. Über diesen
  Weg geht das Paket hinein und das Ergebnis heraus.
- Ein benanntes Volume hält die VM-Platte.

---

## Lauf vorbereiten

```bash
cd tools/win-test

# Ergebnis des letzten Laufs aufheben (nützlich für den Vergleich, s. u.)
mv share/install-result.txt share/install-result-<vorige-version>.txt 2>/dev/null

# Release-Paket bereitstellen
rm -rf share/tree && mkdir -p share/tree
unzip -q ../../dist/praxiszeit-<version>-windows-x64.zip -d share/tree

# Admin-Passwort der Test-VM (einmalig; die Datei ist gitignoriert)
head -c 12 /dev/urandom | base64 | tr -d '/+=' > share/admin-password.txt

# Lauf wählen
echo fresh > share/mode.txt
# … oder Update-Lauf: Vorgängerpaket (z. B. das veröffentlichte Release) daneben
#   rm -rf share/tree-old && mkdir -p share/tree-old
#   unzip -q praxiszeit-<vorgänger>-windows-x64.zip -d share/tree-old
#   echo update > share/mode.txt
# … oder Fremd-PostgreSQL-Lauf (Paket aus share/tree, kein Vorgänger nötig)
#   echo foreignpg > share/mode.txt
# … oder Portwechsel im Restore-Pfad
#   echo portchange > share/mode.txt
```

⚠️ `build-release.sh` überschreibt `dist/praxiszeit-<version>-windows-x64.zip`,
solange die Version nicht gehoben ist. Wer das veröffentlichte Paket als
Vorgänger braucht, entpackt es **vor** dem Bauen nach `share/tree-old`.

Das Kennwort steht bewusst **nicht** im Skript: ein fest eingetragenes Passwort
im Repo ist ein Fund für jeden Secret-Scanner, auch wenn es nur in einer
Wegwerf-VM gilt. Es muss den Komplexitätsregeln der Anwendung genügen
(mindestens 12 Zeichen); der Lauf meldet es nie im Ergebnis, prüft damit aber
zweimal die echte Anmeldung.

Die Version muss **nirgends** eingetragen werden: `install.bat` liest sie aus
dem kopierten Paket (`PAKET_VERSION`) und prüft zusätzlich, was die laufende
Anwendung meldet (`SYSTEM_INFO_RAW`). Eine im Skript gepflegte Zahl wäre beim
nächsten Release veraltet und würde ein falsches Ergebnis behaupten.

**Optional — GUI-Installer-Pfad (Schritt 11):** `share/aclprobe/AclProbe.exe`
ist eine kleine Konsolenanwendung, die genau die Produktionsmethoden
`PraxisZeitConfigWriter.WriteAsync` und `CertificateGenerator.Generate` aus
`installer/setup/src/PraxisZeit.Setup.Core/Services/` aufruft und die erzeugten
Dateien unter `C:\AclProbe` ablegt — damit wird derselbe Rechte-Nachweis auch
für den .NET-Installer geführt. Fehlt die Datei, überspringt der Lauf den
Schritt und schreibt das ins Ergebnis.

---

## Lauf starten

```bash
docker compose -p pz-wintest down -v     # PFLICHT vor jedem erneuten Lauf
docker compose -p pz-wintest up -d
```

`-p pz-wintest`: andere Projekte auf derselben Maschine haben ebenfalls ein
Verzeichnis `win-test` — ohne eigenen Projektnamen teilen sie sich Container und
Volume.

⚠️ **Das `-v` ist nicht optional.** `install.bat` läuft nur auf einer frisch
eingerichteten Windows-Installation. Bleibt das alte Volume liegen, startet die
VM einfach in ihren letzten Zustand — der Test läuft dann **gar nicht**, und das
sieht von außen aus wie „dauert noch".

**Zuschauen:** <http://localhost:8006> (Web-Viewer). Nützlich, wenn nach
40 Minuten nichts im Ergebnis steht — meist hängt dann die Windows-Einrichtung
und nicht die Anwendung.

**Warten:**

```bash
until [ -f share/install-result.txt ] && grep -qaF -e '===== DONE =====' share/install-result.txt; do sleep 60; done
```

⚠️ **Beide Schalter sind nötig, sonst wartet die Schleife ins Leere, obwohl die
Zeile längst in der Datei steht:**

- `-e` — ein Muster, das mit `=` beginnt, frisst grep sonst als Option.
- `-a` — die Ergebnisdatei enthält Nullbytes (einzelne Windows-Werkzeuge geben
  UTF-16 aus), gilt damit als Binärdatei und wird ohne `-a` von der Suche
  übersprungen. `file` sagt dazu schlicht `data`.

---

## Ergebnis lesen

`share/install-result.txt` wird von `cmd.exe` geschrieben; einzelne Werkzeuge
(NSSM, `sc`, `psql`) geben UTF-16 aus, deren Nullbytes mitten in der Datei
landen. Deshalb nicht blind `cat`, sondern gezielt lesen:

```bash
python3 - <<'PY'
t = open('share/install-result.txt', encoding='utf-8', errors='replace').read()
keys = ['PAKET_VERSION','HEALTH_HTTP','LOGIN_HTTP','ALEMBIC','psql (','VERDICT',
        'Setup abgeschlossen','deployment_mode','FEHLER','STATE','===== ',
        'PROBE','BACKUP_EXIT','LAST_BOOT','REBOOT','UPDATE_EXIT','NEUER_CODE',
        'INSTALLDIR','DB_PORT','OWN_DETECTED','FOREIGN','RESTORE','PGCONF',
        'STDERR_LEAK','NEUER_PORT_CODE','NSSM_APPEXIT','PORTWECHSEL']
for line in t.splitlines():
    l = line.strip()
    if l and any(k in l for k in keys):
        print(' ', l[:170])
PY
```

### Härtungs-Sonde (`hardening-probe.ps1`)

Läuft in jedem Modus nach der Standardkonto-Sonde, zwischen `===HARDENING_BEGIN===`
und `===HARDENING_END===`, und fasst `C:\PraxisZeit` nicht an: jeder Fall baut einen
eigenen Ordner unter `C:\hp` und ruft `secure-install.ps1` aus der Installation auf.
Je Fall stehen `HP_<FALL>_EXIT` und `HP_<FALL>_VERDICT` (OK/FEHLER, bei FEHLER die
ersten Ausgabezeilen mit `|` davor) im Ergebnis, am Ende `HP_FAILS=<anzahl>`.
Abgedeckt: fremdes `data\db` bzw. fremde Datei in `config` ohne Dienst (Exit 2,
nichts verschoben), Benutzerrechte an `data\db` und geschützte `postgresql.conf`
(Zurücksetzen mit HINWEIS) samt Gegenprobe, Junctions in Tiefe ≥ 2 unter `data`,
`app`, `bin`, `logs`, `mklink /D`, harte Links, Namen mit Punkt/Leerzeichen am Ende,
ein nicht lesbarer Ordner, vorab angelegtes `bin\postgresql` (Junction, Ordner,
tote Junction) und tote Junction als `data\db`, `setup.bat` mit Junction (bricht bei
„Setup gesperrt“ ab), ein sauberes Paket (Exit 0) und eine fremde Datei unter `app`.
Bei Verknüpfungen und harten Links prüft der Fall zusätzlich, dass sich Eigentümer
und Rechte des Ziels außerhalb (`C:\hp-victim`) nicht geändert haben.
Bestanden: `HP_FAILS=0`.

### Bestanden ist ein Lauf, wenn

| Zeile | erwartet |
|---|---|
| `PAKET_VERSION` | die Version, die getestet werden sollte |
| `Setup abgeschlossen!` | vorhanden, und **kein** `FEHLER:` davor |
| `HEALTH_HTTP` | `200` |
| `LOGIN_HTTP` | `200` — echte Anmeldung, nicht nur ein erreichbarer Port |
| `SYSTEM_INFO_RAW` | `"version":"<version>"` passend zu `PAKET_VERSION` |
| `ALEMBIC_VERSION` | der aktuelle Migrations-Kopf (z. B. `073_work_blocks`) |
| `DB_PORT` | `5432` (`fresh`/`update`; im `update` vor dem Update mit „Rückfall", der Vorgänger kennt `print-db-port` nicht) bzw. `5433` (`foreignpg`) |
| `OWN_DETECTED` (auch `_NACH_UPDATE`, `_NACH_RESTORE`, `_NACH_REBOOT`) | `1` — `praxiszeit-server.py status` erkennt den eigenen Cluster als eigenen (`pg_ctl status -D data\db` + Port aus `postmaster.pid`, aus der erhöhten Harness-Shell unter den gehärteten Ordnerrechten) |
| `PGCONF_UNVERAENDERT` | nur `update`: `ja` — ohne `[database] port` fasst der neue Code `data\db\postgresql.conf` nicht an (MD5 vorher/nachher in `PGCONF_MD5*`) |
| `NEUER_PORT_CODE` | nur `update`: `ja` (bei gleicher Versionsnummer der einzige Beleg, dass das neue Paket installiert ist) |
| `FOREIGN_DETECTED` / `FOREIGN_SERVICE_STAYS_STOPPED` | nur `foreignpg`: `1` / `1` — Meldung im `service-stderr.log`, NSSM startet nicht neu |
| `CLUSTER_MARKER_NACH_NEGATIVPROBE` / `CREDENTIALS_NACH_NEGATIVPROBE` | nur `foreignpg`: was der abgebrochene Erststart hinterlässt. Ein Marker ohne Zugangsdaten kann der nächste Start nicht übernehmen (`.db-credentials is missing …`) — erwartet ist `0` / `0` (der Abbruch kommt vor jeder Cluster-Anlage, es bleibt nichts zurück) |
| `===LOGS_<Anlass>_BEGIN===` | letzte 40 Zeilen von `logs\service-stderr.log` und `logs\praxiszeit.log` — nach der Negativprobe und immer, wenn `HEALTH_HTTP` nicht `200` ist |
| `RESTORE_EXIT` | nur `foreignpg`: `0`, danach `HEALTH_HTTP_NACH_RESTORE` / `LOGIN_HTTP_NACH_RESTORE` = `200` |
| `RESTORE_NACH_PORTWECHSEL_EXIT` | nur `portchange`: `0`, danach `HEALTH_HTTP_NACH_PORTWECHSEL` / `LOGIN_HTTP_NACH_PORTWECHSEL` = `200`, `DB_PORT_NACH_PORTWECHSEL=5433`, `OWN_DETECTED_NACH_PORTWECHSEL=1` |
| `NSSM_APPEXIT_78_NACH_UPDATE` | nur `update`: `Exit` — der Update-Wizard hat `AppExit 78 Exit` gesetzt (`_VOR_UPDATE` zeigt den Stand der Vorgängerversion) |
| `FOREIGN_PG_STILL_ON_5432` | nur `foreignpg`: `0` (`pg_isready`-Exitcode: der Fremdserver läuft nach Install, Sicherung und Restore weiter) |
| `STDERR_LEAK_MIT_2NUL` / `STDERR_LEAK_OHNE_2NUL`, `STDERR_PROBE_*_ARGS` | **Messwert, keine Erwartung.** Prüft, ob `2^>nul` in der gequoteten `for /f`-Zeile (Form aus `setup.bat`/`uninstall.bat`) stderr unterdrückt. Befund Windows 11 (2026-11-06): `1` / `1` — cmd.exe reicht `2>nul` als **Argument** an das Programm weiter, statt umzuleiten (`setup.bat` meldet im selben Lauf `praxiszeit-server.py: error: unrecognized arguments: 2>nul`). `print-db-port` scheiterte in dieser Form; `setup.bat`/`uninstall.bat` nutzen seitdem `2>nul` ohne Caret innerhalb des äußeren Anführungszeichenpaars. Dafür erwartet: `STDERR_LEAK_NEUE_FORM=0`, `STDERR_PROBE_NEUE_FORM_ARGS=[]` und `DB_PORT_UNINSTALL_FORM` = konfigurierter Port (exakte Portzeile aus `uninstall.bat`) |
| `psql (PostgreSQL)` | `18.6` — der gepinnte Stand, siehe `PG_WINDOWS_SHA256` |
| `STATE` | `4  RUNNING` |
| `HEALTH_HTTP_NACH_NEUSTART` / `LOGIN_HTTP_NACH_NEUSTART` | beide `200` (Dienst-Neustart) |
| `UPDATE_EXIT` / `NEUER_CODE` | nur `update`: `0` / `ja` |
| `HEALTH_HTTP_NACH_UPDATE` / `LOGIN_HTTP_NACH_UPDATE` | nur `update`: beide `200` |
| `BACKUP_EXIT` | `0` — sonst prüft die Probe keine echte Sicherung |
| `LAST_BOOT` | Zeitpunkt **nach** `REBOOT=JETZT` — belegt den echten Neustart |
| `HEALTH_HTTP_NACH_REBOOT` / `LOGIN_HTTP_NACH_REBOOT` | beide `200` |
| `ALEMBIC_VERSION_NACH_REBOOT` | wie `ALEMBIC_VERSION` |
| jede Zeile `PROBE …` | `PROBE OK …` — kein `PROBE FAIL` |
| `===== DONE =====` | vorhanden (sonst ist der Lauf abgebrochen, nicht bestanden) |

### Die Rechte-Blöcke

Das Ergebnis enthält fünf `===ACL_*===`-Abschnitte. **Ein `FAIL` ist nicht
automatisch ein Fehler** — einer der Blöcke stellt den Schaden absichtlich her:

| Block | erwartet | Bedeutung |
|---|---|---|
| `ACL_BESTAND` | OK | Rechte nach der normalen Installation |
| `ACL_NEUANLAGE` | OK | der echte Neuanlage-Zweig von `setup.bat` |
| `ACL_AUFGEWEICHT` | **FAIL (gewollt)** | Rechte werden künstlich aufgeweicht wie bei einer Altinstallation |
| `ACL_REPARIERT` | OK | der Dienst hat sich beim Neustart selbst repariert — **das** ist der Nachweis |
| `ACL_DOTNET` | OK, außer `cert.pem` | Pfad des GUI-Installers |

Dazu die Blöcke des **ganzen Installationsordners** (`install-acl-check.ps1`):
Programmteile (Ordner, `bin`, `python.exe`, `postgres.exe`, `main.py`,
`praxiszeit-server.py`) dürfen für Benutzer höchstens lesbar sein, private
Ordner (`data`, `data\backups`, die neueste Sicherung, `logs`, `config`) gar
nicht.

| Block | erwartet |
|---|---|
| `INSTALLDIR_ACL_ALT` | nur `update`: **FAIL (gewollt)** — der Stand vor der Härtung |
| `INSTALLDIR_ACL` | OK |
| `INSTALLDIR_ACL_AUFGEWEICHT` | **FAIL (gewollt)** — Vererbung von `C:\` wieder an |
| `INSTALLDIR_ACL_REPARIERT` | OK — der Dienststart hat den Ordner selbst wieder gehärtet |
| `INSTALLDIR_ACL_REBOOT` | OK |

`PROBE_BEGIN` und `PROBE_REBOOT_BEGIN` sind die Gegenprobe mit einem echten
Standardkonto (`pzprobe`, Kennwort zufällig, nur im Prozess): Schreiben in den
Programmordner, in `bin`, nach `bin\python\Lib` und auf `.py`-Dateien muss
scheitern, ebenso das Lesen von `data\backups`, einer Sicherung, der
`praxiszeit.conf`, von `logs` und `data\db`. Die Lesekontrolle auf `main.py`
muss dagegen **gelingen** — sonst beweist ein „verweigert" nur, dass das Konto
gar nichts darf.

**`cert.pem` meldet dauerhaft `FAIL`** — das ist das *öffentliche* Zertifikat,
lesbar zu sein ist dort kein Mangel; der private `key.pem` daneben ist gesperrt.
Der Befund steht wortgleich in den Läufen von 1.18.2, 1.19.0 und 1.19.1. Deshalb
lohnt es, die alten Ergebnisdateien zu behalten: der schnellste Weg, ein `FAIL`
als bekannt statt als Regression einzuordnen, ist der Vergleich mit dem
Vorgänger.

---

## Was der Lauf im Einzelnen tut

1. Paket von `\\host.lan\Data\tree` nach `C:\PraxisZeit` kopieren, Version lesen
2. `config\praxiszeit.conf` aus der Vorlage schreiben — das Admin-Passwort kommt aus `share/admin-password.txt` (fehlt die Datei, bricht der Lauf mit `FEHLER:` ab, statt still mit einem leeren Kennwort weiterzumachen)
3. `setup.bat` (PostgreSQL 18 + Python-Abhängigkeiten), unbeaufsichtigt über `PRAXISZEIT_NONINTERACTIVE=1`
4. `install-service.bat` (NSSM-Dienst, Firewall-Regel, Backup-Aufgabe)
5. `net start PraxisZeit` — im `foreignpg`-Lauf davor der Fremdserver auf 5432,
   danach die Negativprobe (Exit 78), `[database] port = 5433` und ein zweiter Start
6. bis zu 6 Minuten auf `GET /api/health` warten, dann `POST /api/auth/login`
7. `/api/system/info` abholen (Version, Modus, Beta-Kennzeichen)
8. `alembic_version` und `psql --version` direkt aus der mitgelieferten Datenbank
   (Port über `praxiszeit-server.py print-db-port`), `status` → `OWN_DETECTED`

   Zwischen Schritt 8 und 9: im `update`-Lauf zuerst die Messung des Altstands
   (`INSTALLDIR_ACL_ALT`) und das Update (`UPDATE_EXIT`, `NEUER_CODE`, Anmeldung
   danach); in allen Läufen dann Sicherung anlegen (`BACKUP_EXIT`) — im
   `foreignpg`-Lauf gleich danach `restore-backup.bat` mit dieser Sicherung
   (`RESTORE_EXIT`, `FOREIGN_PG_STILL_ON_5432`) —, Rechte des ganzen Ordners messen (`INSTALLDIR_ACL`) und die Probe als Standardkonto
   (`PROBE_BEGIN`).

9. Rechte-Nachweis auf den Bestandsdateien
10. Rechte-Nachweis auf dem Neuanlage-Zweig von `setup.bat`

    Zwischen Schritt 10 und 11 die Gegenprobe: Rechte aufweichen → Dienst neu
    starten → prüfen, dass er sich repariert **und** weiterhin hochkommt (eine zu
    strenge Rechtevergabe würde das Dienstkonto aussperren — deshalb wird beides
    gemessen).

11. Rechte-Nachweis auf dem GUI-Installer-Pfad (nur mit `AclProbe.exe`)

Am Ende: geplante Aufgabe anlegen und die VM neu starten (`REBOOT=JETZT`);
`post-reboot.bat` prüft danach Dienst, Anmeldung, Migrationsstand, Ordnerrechte
und Probe noch einmal und schreibt erst dann `===== DONE =====`.

---

## Fallstricke

- **`.bat` müssen CRLF sein.** `.gitattributes` erzwingt das (`*.bat text eol=crlf`),
  und `build-release.sh` prüft es im Paket. Mit LF findet `cmd.exe` keine
  Sprungmarken, mehrzeilige `()`-Blöcke brechen — und zwar lautlos, mit einer
  irreführenden Fehlermeldung am Ende (#286).
- **`docker compose down -v` vergessen** → der Test läuft nicht, sieht aber aus
  wie „läuft noch".
- **Nicht auf Prozessnamen warten.** Eine Warteschleife mit
  `pgrep -f <skriptname>` trifft ihre eigene Kommandozeile und endet nie. Auf den
  `===== DONE =====`-Marker in der Ergebnisdatei warten — und dabei `grep -qaF -e`
  nehmen (siehe oben: ohne `-a` findet die Suche in der als binär geltenden Datei
  nichts, ohne `-e` ist das Muster eine Option).
- **Eine Warteschleife im Vordergrund läuft in die Zeitgrenze.** Der Lauf dauert
  länger als jedes vernünftige Kommando-Zeitlimit; entweder im Hintergrund warten
  oder schlicht zwischendurch nachsehen.
- **Der Test räumt die VM nicht auf.** Nach dem Lauf `docker compose down -v`,
  sonst bleiben ~50 GB im Volume liegen.
- **Das Ergebnis ersetzt keinen Blick.** Ist etwas unklar, den Web-Viewer öffnen,
  solange die VM noch läuft — danach ist der Zustand weg.

## Aufräumen

```bash
docker compose -p pz-wintest down -v
rm -rf share/tree
```

Die Ergebnisdateien vergangener Läufe (`share/install-result-*.txt`) ruhig
liegen lassen — sie kosten nichts und sind der Vergleichsmaßstab beim nächsten
Release.
