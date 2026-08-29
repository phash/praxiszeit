# PraxisZeit – Windows-Installation und Erstinbetriebnahme

**Aktuelle Version:** 1.9.0 · **Stand:** Juni 2026
**Zielgruppe:** Praxis-Inhaber:in oder IT-Betreuer:in, der/die PraxisZeit erstmalig auf einem Windows-Rechner einrichtet
**Ergebnis:** Ein einsatzbereiter Praxis-Server, eingerichtete Mitarbeiter:innen-Konten und der erste erfolgreiche Stempelvorgang am Morgen.

> **Maßgebliche, gepflegte Anleitungen:** [INSTALL-NATIVE.md](INSTALL-NATIVE.md),
> [UPDATE.md](UPDATE.md), [BACKUP.md](BACKUP.md) und
> [NATIVE-WINDOWS-PITFALLS.md](NATIVE-WINDOWS-PITFALLS.md). Auslieferung erfolgt
> über den Shop (praxiszeit.mr-development.de); in der Beta ist keine Lizenz nötig.
> Einzelne versionsspezifische Beispiele unten stammen noch aus der 1.4.x-Ära.

Diese Anleitung deckt **nur Windows** ab und führt Schritt für Schritt vom heruntergeladenen ZIP-Paket bis zum ersten Arbeitstag eines Mitarbeiters. Für Linux- oder Docker-Installationen siehe [`setup-anleitung.md`](setup-anleitung.md).

---

## Inhaltsverzeichnis

1. [Voraussetzungen prüfen](#1-voraussetzungen-prüfen)
2. [Paket herunterladen und verifizieren](#2-paket-herunterladen-und-verifizieren)
3. [Entpacken und SmartScreen entsperren](#3-entpacken-und-smartscreen-entsperren)
4. [`setup.bat` als Administrator ausführen](#4-setupbat-als-administrator-ausführen)
5. [`praxiszeit.conf` anpassen](#5-praxiszeitconf-anpassen)
6. [Windows-Dienst installieren und starten](#6-windows-dienst-installieren-und-starten)
7. [Im Browser öffnen und Admin-Login](#7-im-browser-öffnen-und-admin-login)
8. [Praxis-Stammdaten ergänzen](#8-praxis-stammdaten-ergänzen)
9. [Erste Mitarbeiter:innen anlegen](#9-erste-mitarbeiterinnen-anlegen)
10. [Mitarbeiter:innen-Zugangsdaten übergeben](#10-mitarbeiterinnen-zugangsdaten-übergeben)
11. [Erster Arbeitstag — Mitarbeiter:in stempelt ein](#11-erster-arbeitstag--mitarbeiterin-stempelt-ein)
12. [Backup und Wartung im Überblick](#12-backup-und-wartung-im-überblick)
13. [Windows-Stolperfallen (Quick-Reference)](#13-windows-stolperfallen-quick-reference)
14. [Weiterführende Dokumente](#14-weiterführende-dokumente)

---

## 1. Voraussetzungen prüfen

### Hardware (Praxis-Server)

| Komponente | Minimum | Empfohlen |
|---|---|---|
| CPU | 2 Kerne | 4 Kerne |
| RAM | 2 GB | 4 GB (ab 10 MA) |
| Festplatte | 5 GB frei | 20 GB frei (Datenbank wächst ≈ 50 MB / MA / Jahr) |
| Netzwerk | LAN | LAN mit statischer IP |

### Betriebssystem

- **Windows 11** oder **Windows Server 2022** (empfohlen)
- **Windows 10 22H2** oder **Windows Server 2019** (unterstützt)
- **Administrator-Konto** für die Installation (Dienst-Registrierung, Firewall-Regel, Scheduled Task)

### Bestehendes PostgreSQL? (optional, aber wichtig zu wissen)

`setup.bat` erkennt eine bereits installierte PostgreSQL-Instanz in Registry und `%ProgramFiles%\PostgreSQL\{14..18}\`.

- **Major-Version ≥ 16** → wird per Junction (`mklink /J`) in das PraxisZeit-Bundle verlinkt, kein Neu-Setup nötig
- **Major-Version < 16** → der mitgelieferte EDB-Installer installiert PostgreSQL 18 parallel ins Bundle-Verzeichnis

> Wer kein PostgreSQL hat, muss nichts vorbereiten — der Installer bringt alles mit.

### Netzwerk-Ports

| Port | Wofür | Aktion |
|---|---|---|
| 443 | HTTPS-Browserzugriff (empfohlen) | Firewall wird von `install-service.bat` automatisch geöffnet |
| 80 | HTTP, falls bewusst ohne SSL | Manuell freigeben (siehe Schritt 13) |
| 5432 | PostgreSQL (intern) | **Niemals** nach außen öffnen |

---

## 2. Paket herunterladen und verifizieren

### 2.1 Download

Im Browser öffnen:
<https://github.com/phash/praxiszeit/releases/latest>

Folgende Dateien herunterladen:

- `praxiszeit-<VERSION>-windows-x64.zip` (z. B. `praxiszeit-1.3.6-windows-x64.zip`)
- `praxiszeit-<VERSION>-SHA256SUMS.txt` (Prüfsummen-Datei)

> **Hinweis zur Versionslage:** Releases (inkl. Windows-ZIP) werden inzwischen
> zentral über den Shop **praxiszeit.mr-development.de** ausgeliefert (nicht mehr
> nur als GitHub-Release). Aktuelle Version: **1.9.0**. Ein Eigen-Build aus dem
> `master`-Branch ist weiterhin via `tools/build-release.sh` möglich.

### 2.2 Integrität prüfen (PowerShell)

PowerShell öffnen, in das Download-Verzeichnis wechseln und vergleichen:

```powershell
cd $env:USERPROFILE\Downloads
Get-FileHash praxiszeit-1.3.6-windows-x64.zip -Algorithm SHA256
notepad praxiszeit-1.3.6-SHA256SUMS.txt
```

Die Hash-Werte müssen **zeichengenau** übereinstimmen. Stimmen sie nicht überein → Download wiederholen, **nicht** installieren.

---

## 3. Entpacken und SmartScreen entsperren

### 3.1 SmartScreen-Blockade entfernen

Windows markiert Dateien aus dem Internet mit dem „Mark of the Web". Wird die ZIP so entpackt, lehnt Windows die Skripte später teilweise ab.

1. **Rechtsklick** auf die ZIP → **Eigenschaften**
2. Im Reiter **Allgemein** unten den Haken **„Zulassen"** setzen
3. **OK**

### 3.2 Entpacken

Per Rechtsklick → **„Alle extrahieren …"** nach:

```
C:\PraxisZeit\
```

> **Wichtig:** **Nicht** nach `C:\Program Files\` entpacken. Der UAC-VirtualStore blockiert dort Schreibzugriffe auf die Daten- und Konfigurationsordner, was zu schwer auffindbaren Fehlern führt.

Nach dem Entpacken muss `C:\PraxisZeit\setup.bat` existieren.

---

## 4. `setup.bat` als Administrator ausführen

1. Im Startmenü „cmd" tippen → **Rechtsklick** auf **Eingabeaufforderung** → **„Als Administrator ausführen"**
2. In das Installationsverzeichnis wechseln und Setup starten:

```cmd
cd C:\PraxisZeit
setup.bat
```

### Was läuft jetzt automatisch?

1. **PostgreSQL-Erkennung** — bestehende Installation wird per Junction wiederverwendet (Major ≥ 16) oder PostgreSQL 18.4 still neu installiert (mit zufälligem 32-Zeichen-Passwort, das danach sofort durch ein in `config\.db-credentials` abgelegtes ersetzt wird).
2. **Verzeichnisse** `data\db\`, `data\backups\`, `config\ssl\`, `logs\` werden angelegt.
3. **Python-Bootstrap** — `pip` wird neu installiert, anschließend werden alle Abhängigkeiten aus `requirements.txt` ins gebundelte `bin\python\` installiert.
4. **Konfigurations-Vorlage** — falls noch nicht vorhanden, wird `config\praxiszeit.conf.example` nach `config\praxiszeit.conf` kopiert.

Dauer: 3 – 10 Minuten je nachdem, ob PostgreSQL neu installiert werden muss.

> **Bei Abbruch mit „Bitte als Administrator ausführen!":** Die Eingabeaufforderung läuft nicht erhöht. Schritt 1 wiederholen — der Titel des Fensters muss mit „Administrator: Eingabeaufforderung" beginnen.

---

## 5. `praxiszeit.conf` anpassen

> **Editor-Wahl:** Empfohlen sind **VS Code** oder **Notepad++** mit Encoding „UTF-8 ohne BOM". Notepad fügt eine UTF-8-BOM ein; der Dienst startet damit zwar (das Backend entfernt das BOM beim Lesen), schreibt aber bei jedem Start eine Warnung ins Log. Sauberer ist BOM-freies UTF-8.

VS Code installieren (einmalig): <https://code.visualstudio.com/download>

Datei öffnen:

```cmd
code C:\PraxisZeit\config\praxiszeit.conf
```

Mindestens diese Werte anpassen (die mitgelieferte Vorlage enthält Platzhalter wie `Praxis Dr. Muster`, `BITTE_AENDERN_min12zeichen` und `retention_days = 31`, die zwingend überschrieben werden müssen):

```toml
[practice]
name = "Praxis Dr. Müller"
address = "Musterstraße 1, 80000 München"
holiday_state = "Bayern"            # Bundesland für Feiertage

[admin]
username = "admin"
email = "admin@praxis.local"
password = "EinSicheresStartPasswort!2026"   # siehe Passwortregeln unten
first_name = "Dr. Maria"
last_name = "Müller"

[server]
port = 443                          # 443 mit SSL, 80 ohne SSL

[security]
cookie_secure = false               # bleibt false bis SSL aktiv ist (Schritt 6)

[backup]
enabled = true
schedule = "03:00"
retention_days = 730                # 2 Jahre — Pflicht nach § 16 ArbZG (Default 31 ist zu kurz!)
```

Speichern (Strg + S). Beim ersten Speichern bietet VS Code unten rechts die Kodierung an — auf **UTF-8** (ohne BOM) achten.

### Passwortregeln für `[admin].password`

Das Backend prüft:

- mindestens **10 Zeichen**
- mindestens **1 Großbuchstabe**
- mindestens **1 Kleinbuchstabe**
- mindestens **1 Ziffer**
- **nicht** in der Liste typischer Default-/Beispielpasswörter (z. B. `change`, `secret`, `password`, `12345`, `BITTE_AENDERN…`)
- praktisch **min. 12 Zeichen** — kürzere Passwörter lösen einen Sicherheitshinweis im Log aus

Das `[admin].password` wird beim Start gelesen, um das Admin-Konto anzulegen, **falls es fehlt**; existiert es bereits, bleibt es unberührt. Spätere Passwortänderungen erfolgen über das Frontend (Profil → Passwort ändern) — der Wert in der Datei wird dabei **nicht** nachgeführt und ist danach falsch.

Den Klartextwert sollte man deshalb entwerten. ⚠️ **Nicht durch einen festen Platzhalter** wie `set-via-ui`: fehlt das Admin-Konto irgendwann (Benutzername umgestellt, Konto nach Art. 17 endgültig gelöscht), legt der nächste Start es mit genau diesem Wert neu an — und ein in der Projektdokumentation veröffentlichter Wert ist dann das Passwort. Die Schwachpasswort-Prüfung greift dabei nicht: sie bricht den Start nur bei `ENVIRONMENT=production` ab, und der native Standard ist `development`.

Stattdessen einen **zufälligen** Ersatzwert eintragen — oder einfacher das mitgelieferte Kommando nutzen, das den Eintrag selbst mit einem Zufallswert überschreibt (siehe Admin-Handbuch, „Admin-Passwort verloren"):

```
bin\python\python.exe praxiszeit-server.py reset-admin-password
```

### Optional, aber empfohlen: Produktiv-Modus erzwingen

Das Backend startet im Native-Modus per Default mit `ENVIRONMENT=development`. Das bedeutet: schwache Admin-Passwörter erzeugen nur eine Log-Warnung statt einen Service-Abbruch, und die API-Doku unter `/docs` (Swagger) ist im LAN erreichbar.

Für den Praxisbetrieb empfohlen: nach `install-service.bat` (Schritt 6) als Administrator setzen:

```cmd
cd C:\PraxisZeit
nssm.exe set PraxisZeit AppEnvironmentExtra ENVIRONMENT=production
net stop PraxisZeit
net start PraxisZeit
```

Damit wird ein schwaches Admin-Passwort zum harten Startfehler (der Dienst bleibt aus, bis die Konfiguration korrigiert wird), Swagger wird deaktiviert. Variable ausschließlich für den `PraxisZeit`-Dienst — keine System-Env, also kein Konflikt mit anderer Software.

---

## 6. Windows-Dienst installieren und starten

### 6.1 Dienst registrieren

In derselben Administrator-Eingabeaufforderung:

```cmd
cd C:\PraxisZeit
install-service.bat
```

`install-service.bat` erledigt:

- Registrierung des Windows-Dienstes **PraxisZeit** (NSSM) mit Autostart
- Log-Rotation in `C:\PraxisZeit\logs\service-stdout.log` / `service-stderr.log` (10 MB)
- Firewall-Regel für **Port 443** (TCP, eingehend)
- Scheduled Task **PraxisZeit-Backup** täglich um **03:00** (läuft als SYSTEM)

### 6.2 Optional: SSL-Zertifikat erzeugen

Selbstsigniertes Zertifikat für lokalen HTTPS-Zugriff:

```cmd
:: WICHTIG: RSA-2048 + serverAuth. Browser lehnen ed25519-TLS-Server-Zertifikate
:: und CA-Certs (ohne extendedKeyUsage=serverAuth) ohne "Erweitert"-Option ab.
cd C:\PraxisZeit
bin\postgresql\bin\openssl.exe req -x509 -nodes -newkey rsa:2048 ^
  -keyout config\ssl\key.pem ^
  -out    config\ssl\cert.pem ^
  -days 3650 ^
  -subj "/O=PraxisZeit/CN=praxiszeit" ^
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" ^
  -addext "basicConstraints=critical,CA:FALSE" ^
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" ^
  -addext "extendedKeyUsage=serverAuth"
```

Dann in `config\praxiszeit.conf` aktivieren:

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"
ssl_key  = "config/ssl/key.pem"

[security]
cookie_secure = true                # ab jetzt true, weil HTTPS aktiv
```

> Ohne SSL bleibt `port = 80` und `cookie_secure = false` — sonst lehnt der Browser das Refresh-Cookie ab und der Login schlägt fehl.

### 6.3 Dienst starten

```cmd
net start PraxisZeit
```

Status prüfen:

```cmd
sc query PraxisZeit
type C:\PraxisZeit\logs\service-stdout.log
```

Health-Check (`curl` ist seit Windows 10 1803 und Windows Server 2019 vorinstalliert):

```cmd
curl http://localhost/api/health
:: {"status":"healthy","database":"connected"}
```

Alternativ in PowerShell:

```powershell
Invoke-RestMethod http://localhost/api/health
```

> **Erststart kann 1–3 Minuten dauern**, weil beim aller­ersten Lauf der PostgreSQL-Cluster initialisiert wird (`initdb`), Datenbank-Migrationen laufen und der Default-Tenant + Admin-User angelegt werden. Folge­starts sind unter 30 Sekunden. Fortschritt verfolgen: `type C:\PraxisZeit\logs\praxiszeit.log` (oder `Get-Content -Wait` in PowerShell).

---

## 7. Im Browser öffnen und Admin-Login

URL je nach SSL-Konfiguration:

- Mit SSL: `https://localhost/` (Sicherheitswarnung bei selbstsigniertem Zertifikat einmalig akzeptieren)
- Ohne SSL: `http://localhost/`

Login:

- **Benutzername:** `admin` (oder der Wert aus `[admin].username`)
- **Passwort:** der Wert aus `[admin].password`

**Sofort nach dem ersten Login Pflicht:** rechts oben das Profil-Menü öffnen → **Profil → Passwort ändern** → neues Passwort setzen.

---

## 8. Praxis-Stammdaten ergänzen

Im Menü **Einstellungen → Praxis** vervollständigen:

- Vollständiger Praxis-Name (taucht in Excel-Exporten auf)
- Adresse, ggf. weitere Standorte
- **Bundesland** (steuert die gesetzlichen Feiertage)
- Optional: Betriebsferien einplanen (**Einstellungen → Betriebsferien**)
- Optional: Lizenzschlüssel laden (**Einstellungen → Lizenz**)

---

## 9. Erste Mitarbeiter:innen anlegen

Navigation: **Mitarbeiter → „Neuer Mitarbeiter:in"**

### Pflichtfelder (vom Backend erzwungen)

| Feld | Beispiel | Wertebereich / Regel |
|---|---|---|
| **Benutzername** | `m.hoffmann` | 1–100 Zeichen, eindeutig im Mandanten |
| **Vorname** | `Maria` | 1–100 Zeichen |
| **Nachname** | `Hoffmann` | 1–100 Zeichen |
| **Passwort** | `Start-Pwd-2026!` | Min. 10 Zeichen, mind. 1 Groß-, 1 Klein-, 1 Ziffer (nicht aus Default-Liste) |
| **Rolle** | Mitarbeiter:in | Admin oder Mitarbeiter:in |
| **Wochenstunden** | `40` | 0–60 Stunden |
| **Urlaubstage** | `30` | 0–50 Tage pro Jahr |
| **Arbeitstage pro Woche** | `5` | 1–7 (Default 5) |

### Optionale, aber praktisch wichtige Felder

- **E-Mail** — für Kontakt und Passwort-Reset (kann leer bleiben)
- **Erster Arbeitstag** — wichtig für die korrekte Soll-Stunden-Berechnung im Eintrittsmonat. Vor diesem Datum kann sich die Person **nicht einstempeln** („Datum liegt vor dem ersten Arbeitstag").
- **Letzter Arbeitstag** — analog für Austritt
- **Individuelle Tagesstunden** (Mo–Fr) — wenn z. B. Freitags nur halbtags gearbeitet wird
- **Stundenzählung aktiv** — deaktivieren für leitende Angestellte ohne Stundenpflicht; **ohne diese Option sehen Mitarbeiter:innen keine Stempeluhr** (siehe Abschnitt 11)
- **ArbZG-Prüfungen aussetzen** (§ 18 ArbZG) — leitende Angestellte: keine Ruhezeit-/Pausen-Warnungen
- **Nachtarbeitnehmer** (§ 6 ArbZG) — 8h-Tageslimit statt 10h
- **Kalenderfarbe** — für die Darstellung im Abwesenheitskalender

> **§ 18 ArbZG** (Leitende Angestellte ausnehmen) nur setzen, wenn die Person wirklich darunter fällt — andernfalls werden gesetzliche Höchstgrenzen ignoriert.

Speichern. Die Person erscheint sofort in der Mitarbeiterliste.

> **Wichtig:** Mitarbeiter:innen werden **niemals gelöscht**, nur **deaktiviert** — § 16 ArbZG verlangt die Aufbewahrung der Zeitaufzeichnungen für mindestens 2 Jahre.

---

## 10. Mitarbeiter:innen-Zugangsdaten übergeben

Übergeben Sie pro Mitarbeiter:in folgende drei Informationen — am besten **schriftlich auf einem Übergabezettel**:

1. **URL** des Praxis-Servers
   - Im Praxis-LAN: `https://<Server-IP>/` (IP per `ipconfig` ermitteln, z. B. `https://192.168.1.20/`)
   - Per DNS-Eintrag: `https://praxiszeit.meinepraxis.de/`
2. **Benutzername** (z. B. `m.hoffmann`)
3. **Start-Passwort** mit Hinweis: „Bitte bei der ersten Anmeldung sofort unter **Profil → Passwort ändern** ein eigenes Passwort setzen."

Optional: Den **Mitarbeiter-Cheat-Sheet** drucken und beilegen: [`docs/handbuch/CHEATSHEET-MITARBEITER.md`](handbuch/CHEATSHEET-MITARBEITER.md).

---

## 11. Erster Arbeitstag — Mitarbeiter:in stempelt ein

Diese Schritte führt die Mitarbeiter:in am ersten Arbeitstag selbst aus (idealerweise mit Begleitung des Admins).

### 11.1 Anmelden

1. Im Browser die übergebene URL öffnen
2. Benutzername und Start-Passwort eingeben
3. **Anmelden** klicken

### 11.2 Eigenes Passwort setzen (einmalig)

Direkt nach dem ersten Login:

1. Oben rechts auf das Profil-Symbol klicken → **Profil**
2. Abschnitt **Passwort ändern**
3. Aktuelles (Start-)Passwort eingeben, neues Passwort zweimal eintragen
4. **Speichern**

### 11.3 Auf dem Dashboard einstempeln

Nach dem Login landet die Mitarbeiter:in automatisch auf dem **Dashboard**. Ganz oben befindet sich die **Stempeluhr (Stamp-Widget)**:

1. Großen Button **„Einstempeln"** klicken
2. Toast-Meldung **„Erfolgreich eingestempelt"** erscheint kurz
3. Die Anzeige wechselt auf einen **laufenden Timer** im Format `0h 00min`, der jede Minute weiterzählt
4. Die Kachel **Tagessaldo** wird grün

> Das Backend prüft beim Einstempeln automatisch die **§ 5 ArbZG-Ruhezeit** (mindestens 11 Stunden seit dem letzten Ausstempeln). Liegt die letzte Ausstempelung zu kurz zurück, erscheint eine **Warnung** als Toast — der Eintrag wird trotzdem erstellt, der Hinweis aber dokumentiert. Bei Mitarbeiter:innen mit gesetztem Flag „ArbZG-Prüfungen aussetzen" (§ 18 ArbZG) entfällt diese Warnung.

> **Wenn statt der Stempeluhr nichts erscheint:** Im Mitarbeiter:innen-Profil ist die Option **„Stundenzählung aktiv"** deaktiviert — dann blendet das Widget sich komplett aus. Admin: Profil prüfen und Option anhaken.

> **Sonderfall vergessenes Ausstempeln vom Vortag:** Das Backend erkennt einen offenen Eintrag vom Vortag und schließt ihn beim erneuten Einstempeln **automatisch** ab — die Mitarbeiter:in sollte den Vortag aber noch manuell unter „Zeiterfassung → Bearbeiten" korrigieren (oder per Änderungsantrag).

### 11.4 Pausen erfassen

Pausen werden **nicht** durch Aus- und Wieder-Einstempeln abgebildet. Stattdessen:

- Zum Feierabend einmal **Ausstempeln** klicken (siehe nächster Schritt)
- Pause als Minutenwert beim Ausstempeln eintragen

### 11.5 Zum Feierabend ausstempeln

1. Auf dem Dashboard **„Ausstempeln"** klicken
2. Ein Eingabefeld **Pause (Minuten)** erscheint — Wert eintragen (z. B. `30`)
3. Erneut **„Ausstempeln"** klicken zur Bestätigung
4. Toast **„Erfolgreich ausgestempelt"** — der Eintrag steht jetzt unter **Zeiterfassung → Einträge** mit Von, Bis, Pause, Netto-Stunden

> **Pflicht-Pausen (§ 4 ArbZG):**
> bei > 6 h Arbeitszeit → mindestens 30 Min., bei > 9 h → mindestens 45 Min.
> Bei zu kurzer Pause erscheint eine Warnung; bei mehr als 10 h Nettoarbeit wird der Eintrag blockiert.

### 11.6 Mobil

Die Stempeluhr steht auf dem Smartphone genauso bereit:

- URL im Mobile-Browser öffnen, einloggen
- Der „Stempeln"-Button erscheint unten als feste Aktions-Schaltfläche
- Optional: Die URL als App-Symbol zum Home-Bildschirm hinzufügen

### 11.7 Vergessen einzustempeln?

Wenn das Stempeln einmal vergessen wird, kann die Zeit nachgetragen werden:

1. Menü **Zeiterfassung → + Neuer Eintrag**
2. Datum, Von, Bis und Pause eintragen
3. **Speichern**

Ist der Tag bereits gesperrt (typisch nach Monatsabschluss): Button **Änderungsantrag** in der Tageszeile → korrekte Werte + **Begründung** eingeben → Admin genehmigt.

---

## 12. Backup und Wartung im Überblick

### Automatisches Backup

- Läuft täglich um **03:00** als Scheduled Task `PraxisZeit-Backup` (eingerichtet durch `install-service.bat`)
- Ablage: `C:\PraxisZeit\data\backups\praxiszeit_YYYYMMDD_HHMMSS.sql.gz`
- Format: PostgreSQL **Custom Format** (`pg_dump -Fc`), gzip-komprimiert — Wiederherstellung erfolgt mit `pg_restore` (siehe unten)
- Aufbewahrung: gesetzt durch `praxiszeit.conf` → `[backup].retention_days`. **Default in der Vorlage ist 31** — für die ArbZG-Pflicht von 2 Jahren manuell auf **730** erhöhen (siehe Schritt 5).

### Backup-Status prüfen

```cmd
schtasks /query /tn "PraxisZeit-Backup" /v /fo LIST
dir C:\PraxisZeit\data\backups\
```

### Manuelles Backup

```cmd
cd C:\PraxisZeit
bin\python\python.exe praxiszeit-server.py backup
```

### Wiederherstellung aus Backup

Backups liegen als `.sql.gz` im PostgreSQL-**Custom-Format** vor. Dadurch ist `pg_restore` Pflicht — `psql` funktioniert mit diesem Format **nicht**.

Schritt für Schritt (Administrator-Eingabeaufforderung):

```cmd
:: 1. PraxisZeit stoppen, PostgreSQL läuft weiter
net stop PraxisZeit

:: 2. Datenbankpasswort aus der Credentials-Datei in die Umgebung holen
for /f "tokens=1,* delims==" %A in (C:\PraxisZeit\config\.db-credentials) do @if "%A"=="SUPERUSER_PASSWORD" set "PGPASSWORD=%B"

:: 3. Backup zuerst entpacken (PowerShell hat kein eingebautes gunzip,
::    daher Tools wie 7-Zip oder das Bundle-Binary "gzip.exe" nutzen)
"C:\Program Files\7-Zip\7z.exe" e C:\PraxisZeit\data\backups\praxiszeit_20260523_030001.sql.gz -oC:\Temp\

:: 4. Wiederherstellen (entpackte Datei: praxiszeit_20260523_030001.sql)
"C:\PraxisZeit\bin\postgresql\bin\pg_restore.exe" -U praxiszeit -d praxiszeit --clean --if-exists C:\Temp\praxiszeit_20260523_030001.sql

:: 5. Dienst wieder starten
net start PraxisZeit
```

> **Vor jeder Restore-Aktion:** aktuellen Stand sichern (`praxiszeit-server.py backup`) und schriftlich dokumentieren, **wer wann warum** zurückgespielt hat. Restores sind nach § 16 ArbZG protokollpflichtig.

### Externe Ablage (§ 16 ArbZG-Empfehlung)

Backup-Verzeichnis zusätzlich auf NAS / USB-Festplatte / verschlüsselten Cloud-Bucket spiegeln (z. B. via geplanter `robocopy`-Aufgabe). Eine Inhouse-Kopie allein reicht im Ernstfall **nicht**.

### Updates einspielen

**Empfohlen — Update-Wizard im Browser:** Als Admin einloggen → **Einstellungen → Updates** → „Nach Updates suchen" → „Update installieren". Der Dienst startet automatisch neu; danach im Browser einen **Hard-Refresh** (`Strg + F5`) ausführen.

**Manuelles Update mit neuem ZIP:**

```cmd
:: 1. Sicherung der aktiven Daten ist Pflicht
cd C:\PraxisZeit
bin\python\python.exe praxiszeit-server.py backup

:: 2. Dienst stoppen
net stop PraxisZeit

:: 3. Neues ZIP in ein TEMP-Verzeichnis entpacken (nicht direkt nach C:\PraxisZeit\)
powershell -Command "Expand-Archive C:\Users\<USER>\Downloads\praxiszeit-1.4.x-windows-x64.zip C:\Temp\pz-update -Force"

:: 4. Selektiv kopieren — nur app\, bin\, *.py, *.bat, requirements; config\ und data\ NIE überschreiben
robocopy C:\Temp\pz-update\app  C:\PraxisZeit\app  /MIR
robocopy C:\Temp\pz-update\bin  C:\PraxisZeit\bin  /MIR /XD bin\postgresql bin\python\Lib\site-packages
robocopy C:\Temp\pz-update      C:\PraxisZeit       *.py *.bat /XF setup.bat
copy /Y C:\Temp\pz-update\app\backend\requirements.txt C:\PraxisZeit\app\backend\requirements.txt

:: 5. Python-Abhängigkeiten neu installieren (pip wird hierfür frisch gebootet — siehe F-056)
bin\python\python.exe bin\python\get-pip.py --force-reinstall
bin\python\python.exe -m pip install --quiet -r app\backend\requirements.txt

:: 6. Dienst wieder starten — Migrationen laufen automatisch beim ersten Start
net start PraxisZeit
```

Anschließend im Browser einen **Hard-Refresh** (`Strg + F5`) erzwingen, sonst lädt das alte Frontend-Bundle aus dem Service-Worker-Cache.

> **Wann das manuelle Update?** Wenn der eingebaute Wizard fehlschlägt (z. B. ohne Internet-Anbindung), beim Sprung über mehrere Versionen, oder wenn man bewusst auf eine bestimmte Version festlegen will.

---

## 13. Windows-Stolperfallen (Quick-Reference)

| Problem | Ursache | Lösung |
|---|---|---|
| `setup.bat` bricht mit „Bitte als Administrator ausführen" ab | Eingabeaufforderung nicht erhöht gestartet | Per Rechtsklick → „Als Administrator ausführen" |
| Log enthält Warnung „praxiszeit.conf enthielt UTF-8 BOM" | Notepad hat eine UTF-8-BOM geschrieben | Funktional unkritisch (Backend strippt das BOM beim Lesen), aber bitte Datei mit VS Code / Notepad++ neu als „UTF-8 ohne BOM" speichern, damit die Warnung verschwindet |
| Dienst startet nicht, Log zeigt `TOMLDecodeError` mit Zeile/Spalte | Echter TOML-Syntaxfehler (fehlende Anführungszeichen, Komma, falsche Section-Klammer) | Fehler-Position aus dem Log lesen und die `praxiszeit.conf` korrigieren |
| Login schlägt fehl, kein Cookie wird gesetzt | HTTP genutzt, aber `cookie_secure = true` | `cookie_secure = false` solange kein SSL aktiv ist |
| Stempeluhr lädt nicht, Netzwerk-Tab zeigt 405 | Alter Service-Worker im Browser-Cache | `Strg + F5` oder DevTools → Application → Service Workers → Unregister |
| Setup will PostgreSQL neu installieren, obwohl schon vorhanden | Vorhandene Version ist < 16 | Lokales PostgreSQL auf Major-Version ≥ 16 aktualisieren oder bewusst die Bundle-Variante akzeptieren |
| Firewall blockt LAN-Zugriff trotz `install-service.bat` | Port nachträglich geändert | `netsh advfirewall firewall add rule name="PraxisZeit" dir=in action=allow protocol=TCP localport=80` |
| `data\db\` ist leer, PostgreSQL startet nicht | Junction auf zu altes PG oder Berechtigungsproblem auf `data\db\` | `setup.bat` neu laufen lassen; Junction ggf. mit `rd C:\PraxisZeit\bin\postgresql` entfernen |
| Excel-Export hat falsche Praxis-Adresse im Kopf | `[practice].address` leer | In `praxiszeit.conf` ergänzen, Dienst neu starten |
| Mitarbeiter:in sieht „Keine gültigen Arbeitstage" beim Eintrag | Datum liegt auf einem nicht-Arbeitstag | Mitarbeiter-Profil prüfen: Arbeitstage pro Woche bzw. individuelle Tagesstunden |
| Update-Wizard ändert Code, alter UI-Stand bleibt sichtbar | Browser-Cache hält altes Bundle | `Strg + F5` oder Inkognito-Fenster |

### Logs für den Support sammeln

```cmd
cd C:\PraxisZeit\logs
powershell Compress-Archive *.log ..\praxiszeit-support.zip
```

Zusätzlich nützlich:

```cmd
sc query PraxisZeit > C:\PraxisZeit\logs\service-status.txt
schtasks /query /tn "PraxisZeit-Backup" /v /fo LIST > C:\PraxisZeit\logs\task-status.txt
```

---

## 14. Weiterführende Dokumente

| Thema | Pfad |
|---|---|
| Vollständige Setup-Anleitung (alle Plattformen) | [`docs/setup-anleitung.md`](setup-anleitung.md) |
| Native-Installer Detail-Doku | [`docs/INSTALL-NATIVE.md`](INSTALL-NATIVE.md) |
| Native-Windows-Fallstricke (für Entwickler) | [`docs/NATIVE-WINDOWS-PITFALLS.md`](NATIVE-WINDOWS-PITFALLS.md) |
| Admin-Handbuch | [`docs/handbuch/HANDBUCH-ADMIN.md`](handbuch/HANDBUCH-ADMIN.md) |
| Admin-Cheat-Sheet | [`docs/handbuch/CHEATSHEET-ADMIN.md`](handbuch/CHEATSHEET-ADMIN.md) |
| Mitarbeiter-Handbuch | [`docs/handbuch/HANDBUCH-MITARBEITER.md`](handbuch/HANDBUCH-MITARBEITER.md) |
| Mitarbeiter-Cheat-Sheet | [`docs/handbuch/CHEATSHEET-MITARBEITER.md`](handbuch/CHEATSHEET-MITARBEITER.md) |
| Security & DSGVO | [`docs/SECURITY.md`](SECURITY.md) |

### Support

- Repository: <https://github.com/phash/praxiszeit>
- Bug-Reports: <https://github.com/phash/praxiszeit/issues>
- Releases: <https://github.com/phash/praxiszeit/releases>

---

*PraxisZeit · Windows-Setup · Version 1.9.0 · © 2026*
