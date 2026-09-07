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

Der Lauf ist eine **Erstinstallation**. Der Update-Pfad (`update-wizard.bat`)
ist nicht Teil davon — dafür bei Bedarf über den Web-Viewer (siehe unten) von
Hand nachfahren.

---

## Voraussetzungen

| | |
|---|---|
| KVM | `/dev/kvm` muss vorhanden und nutzbar sein (`ls -l /dev/kvm`) |
| Docker | mit Compose-Plugin |
| Plattenplatz | ~60 GB frei (VM-Disk 48 GB dünn belegt + ~700 MB entpacktes Paket + Image) |
| VM-Ressourcen | 4 Kerne / 4 GB RAM (Vorgabe in `docker-compose.yml`) — der Host sollte deutlich mehr haben |
| Zeit | **30–50 Minuten** (Windows-Einrichtung, Installation, zwei Wartefenster von je bis zu 6 Minuten auf die Anwendung) |
| Paket | ein gebautes `dist/praxiszeit-<version>-windows-x64.zip` → [BUILD-RELEASE.md](BUILD-RELEASE.md) |

---

## Aufbau

Alles liegt in `tools/win-test/`:

```
tools/win-test/
├── docker-compose.yml      dockur/windows (Windows 11), KVM, Web-Viewer auf :8006
├── oem/install.bat         läuft nach der Windows-Einrichtung automatisch als Administrator
└── share/
    ├── acl-check.ps1        Rechteprüfung (SID-basiert, also sprachunabhängig)
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
```

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
docker compose down -v     # PFLICHT vor jedem erneuten Lauf
docker compose up -d
```

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
        'Setup abgeschlossen','deployment_mode','FEHLER','STATE','===== ']
for line in t.splitlines():
    l = line.strip()
    if l and any(k in l for k in keys):
        print(' ', l[:170])
PY
```

### Bestanden ist ein Lauf, wenn

| Zeile | erwartet |
|---|---|
| `PAKET_VERSION` | die Version, die getestet werden sollte |
| `Setup abgeschlossen!` | vorhanden, und **kein** `FEHLER:` davor |
| `HEALTH_HTTP` | `200` |
| `LOGIN_HTTP` | `200` — echte Anmeldung, nicht nur ein erreichbarer Port |
| `SYSTEM_INFO_RAW` | `"version":"<version>"` passend zu `PAKET_VERSION` |
| `ALEMBIC_VERSION` | der aktuelle Migrations-Kopf (z. B. `071_security_events`) |
| `psql (PostgreSQL)` | `18.4` — der gepinnte Stand, siehe `PG_WINDOWS_SHA256` |
| `STATE` | `4  RUNNING` |
| `HEALTH_HTTP_NACH_NEUSTART` / `LOGIN_HTTP_NACH_NEUSTART` | beide `200` |
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
5. `net start PraxisZeit`
6. bis zu 6 Minuten auf `GET /api/health` warten, dann `POST /api/auth/login`
7. `/api/system/info` abholen (Version, Modus, Beta-Kennzeichen)
8. `alembic_version` und `psql --version` direkt aus der mitgelieferten Datenbank
9. Rechte-Nachweis auf den Bestandsdateien
10. Rechte-Nachweis auf dem Neuanlage-Zweig von `setup.bat`
11. Rechte-Nachweis auf dem GUI-Installer-Pfad (nur mit `AclProbe.exe`)

Dazwischen die Gegenprobe: Rechte aufweichen → Dienst neu starten → prüfen, dass
er sich repariert **und** weiterhin hochkommt (eine zu strenge Rechtevergabe
würde das Dienstkonto aussperren — deshalb wird beides gemessen).

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
docker compose down -v
rm -rf share/tree
```

Die Ergebnisdateien vergangener Läufe (`share/install-result-*.txt`) ruhig
liegen lassen — sie kosten nichts und sind der Vergleichsmaßstab beim nächsten
Release.
