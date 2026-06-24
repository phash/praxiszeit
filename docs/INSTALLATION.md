# PraxisZeit - Installationsanleitung (Linux Mint 22 / Ubuntu)

## Voraussetzungen

- Linux Mint 22 (oder Ubuntu 24.04)
- Internetzugang (fuer Docker-Images und git pull)
- sudo-Rechte
- Mindestens 2 GB RAM, 5 GB Festplatte frei

---

## Schritt 1: Docker Engine installieren

```bash
# Alte Docker-Versionen entfernen (falls vorhanden)
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Abhaengigkeiten installieren
sudo apt update
sudo apt install -y ca-certificates curl gnupg

# Docker GPG-Key hinzufuegen
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker-Repository hinzufuegen (Mint 22 basiert auf Ubuntu 24.04 "noble")
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker installieren
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Eigenen Benutzer zur docker-Gruppe hinzufuegen (damit kein sudo noetig ist)
sudo usermod -aG docker $USER

# WICHTIG: Ab- und wieder anmelden, damit die Gruppenänderung wirkt
# Oder: newgrp docker

# Pruefen ob Docker funktioniert
docker --version
docker compose version
```

---

## Schritt 2: Repository klonen

```bash
cd ~
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit
```

---

## Schritt 3: Konfiguration (.env-Datei)

PraxisZeit liest alle Geheimnisse und Einstellungen aus einer `.env`-Datei.
**Niemals echte Passwörter/Keys fest in eine Anleitung schreiben** — das
mitgelieferte Skript erzeugt starke Zufallswerte:

```bash
cd ~/praxiszeit
bash tools/docker/generate-secrets.sh
```

Das Skript schreibt `.env` mit zufälligem `SECRET_KEY`, `POSTGRES_PASSWORD`,
`APP_DB_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` und einem komplexen `ADMIN_PASSWORD`
(wird am Ende ausgegeben — **notieren!**) und setzt `ENVIRONMENT=production`.

Anschließend nur noch die praxis-spezifischen Werte anpassen:

```bash
nano .env
```

| Variable | Bedeutung |
|----------|-----------|
| `ADMIN_USERNAME` / `ADMIN_EMAIL` | Initialer Admin-Login |
| `ADMIN_FIRST_NAME` / `ADMIN_LAST_NAME` | Name des Admins |
| `PRACTICE_NAME` / `PRACTICE_ADDRESS` | Erscheint in Excel-Exporten (DSGVO) |
| `HOLIDAY_STATE` | Bundesland für Feiertage (z. B. `Bayern`) |
| `CORS_ORIGINS` / `ALLOWED_HOSTS` | Eigene Domain statt `localhost` (bei Internet-Zugriff) |

> **Wichtig (seit RLS-Umbau):** Die `.env` braucht zusätzlich
> `APP_DB_USER`/`APP_DB_PASSWORD`, `ENVIRONMENT` und `CORS_ORIGINS`. Eine alte,
> von Hand geschriebene `.env` ohne diese Werte lässt `docker compose up` mit
> `required variable APP_DB_PASSWORD is missing` abbrechen — daher
> `generate-secrets.sh` nutzen (oder `cp .env.example .env` als Vorlage).

---

## Schritt 4: PraxisZeit starten

```bash
cd ~/praxiszeit
docker compose up -d
```

Beim ersten Start dauert es einige Minuten (Docker baut die Images).

Fortschritt beobachten:
```bash
docker compose logs -f
```
(`Strg+C` zum Beenden der Logs)

Pruefen ob alles laeuft:
```bash
docker compose ps
```

Alle Dienste sollten "Up" zeigen (`db`, `backend`, `frontend` und das Monitoring
`prometheus`/`grafana`). Health-Check:
```bash
curl http://localhost/api/health
# Erwartet: {"status":"healthy","database":"connected"}
```

---

## Schritt 5: Zugriff im Netzwerk

### Auf dem Server selbst
```
http://localhost
```

### Von anderen Computern
```
http://<SERVER-IP>
```

Server-IP herausfinden:
```bash
hostname -I
```

### Erster Login
- **Email/Benutzer:** der in `.env` gesetzte `ADMIN_EMAIL` / `ADMIN_USERNAME`
- **Passwort:** das von `generate-secrets.sh` ausgegebene `ADMIN_PASSWORD`
- **Wichtig:** Passwort nach dem ersten Login unter "Profil" aendern!

### Firewall (falls ufw aktiv)
```bash
sudo ufw allow 80/tcp
```

---

## Taeglicher Betrieb

PraxisZeit startet automatisch neu nach einem Server-Neustart (`restart: unless-stopped`).

```bash
# Status pruefen
docker compose ps

# Stoppen
docker compose down

# Starten
docker compose up -d

# Logs ansehen
docker compose logs -f

# Nur Backend-Logs
docker compose logs -f backend
```

---

## HTTPS aktivieren (optional)

HTTPS verschluesselt die Verbindung zwischen Browser und Server.

### Schritt 1: Zertifikat generieren

```bash
cd ~/praxiszeit
chmod +x ssl/generate-cert.sh
./ssl/generate-cert.sh
```

Das Skript erkennt automatisch die Server-IP und erstellt ein Zertifikat (10 Jahre gueltig).

### Schritt 2: Mit HTTPS starten

```bash
docker compose down
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```

### Schritt 3: Firewall anpassen

```bash
sudo ufw allow 443/tcp
```

### Schritt 4: Im Browser oeffnen

```
https://<SERVER-IP>
```

Beim **ersten Zugriff** zeigt der Browser eine Warnung ("Nicht sicher" / "NET::ERR_CERT_AUTHORITY_INVALID"). Das ist normal bei selbstsignierten Zertifikaten:
- **Chrome:** "Erweitert" → "Weiter zu ... (unsicher)"
- **Firefox:** "Erweitert" → "Risiko akzeptieren und fortfahren"
- **Edge:** "Erweitert" → "Weiter zu ... (unsicher)"

Diese Warnung erscheint nur einmalig pro Browser/Geraet. Danach ist die Verbindung verschluesselt.

### Zurueck zu HTTP (falls noetig)

```bash
docker compose down
docker compose up -d
```

---

## Updates einspielen

> **⚠️ Von 1.9.x oder älter auf 1.10.x?** Das ist ein PostgreSQL-Major-Upgrade
> (16 → 18, **nicht in-place**) — ein einfaches `up --build` scheitert am
> inkompatiblen PG16-Volume. Vorher den geführten Helfer fahren (läuft auch aus
> dem git-Checkout): `bash tools/docker/update-pg-major.sh`. Vollständige
> Anleitung inkl. Backup/Restore: **[UPDATE.md](UPDATE.md)**.

```bash
cd ~/praxiszeit
docker compose down
git pull
# Ohne SSL:
docker compose up -d --build
# Mit SSL:
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

Datenbank-Migrationen werden automatisch beim Start ausgefuehrt.
Details & alle Pfade (Docker, Native, Windows): **[UPDATE.md](UPDATE.md)**.

---

## Datensicherung (Backup)

### Manuelles Backup
```bash
cd ~/praxiszeit
# --clean --if-exists + gzip → sauber zurückspielbar (s. „Backup wiederherstellen").
docker compose exec -T db pg_dump -U praxiszeit --clean --if-exists praxiszeit | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Automatisches taegliches Backup (Cron)
```bash
# Crontab oeffnen
crontab -e

# Diese Zeile hinzufuegen (Backup taeglich um 2:00 Uhr):
0 2 * * * cd ~/praxiszeit && docker compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > ~/backups/praxiszeit_$(date +\%Y\%m\%d).sql.gz && find ~/backups -name "praxiszeit_*.sql.gz" -mtime +30 -delete
```

Backup-Ordner vorher anlegen:
```bash
mkdir -p ~/backups
```

### Backup wiederherstellen
```bash
cd ~/praxiszeit
gunzip -c backup_20260214.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U praxiszeit -d praxiszeit
docker compose up -d backend   # Migrationen heben das Schema auf head
```

---

## Troubleshooting

### "Seite nicht erreichbar" von anderen PCs
- Server-IP korrekt? → `hostname -I`
- Firewall? → `sudo ufw status` (Port 80 muss offen sein)
- Docker laeuft? → `docker compose ps`

### Container starten nicht
- Docker-Dienst laeuft? → `sudo systemctl status docker`
- Logs pruefen: `docker compose logs`

### "Permission denied" bei docker-Befehlen
```bash
sudo usermod -aG docker $USER
# Dann ab- und wieder anmelden
```

---

## Gesetzliche Aufbewahrungspflichten (§16 ArbZG)

Nach **§16 Abs. 2 ArbZG** sind Arbeitgeber verpflichtet, die Arbeitszeiten von Arbeitnehmenden, die
über 8 Stunden werktäglich hinausgehen, aufzuzeichnen und diese Aufzeichnungen **mindestens 2 Jahre
aufzubewahren**. Verstöße sind bußgeldbewehrt (bis zu 30.000 €).

### Was PraxisZeit speichert
Alle Zeiteinträge werden in der PostgreSQL-Datenbank persistent gespeichert (Docker-Volume `postgres_data`).
Solange das Volume nicht manuell gelöscht wird, bleiben alle Daten erhalten.

### Empfohlene Backup-Strategie (2-Jahres-Retention)

**Tägliches automatisches Backup** (bereits in "Datensicherung" beschrieben) **plus** Jahresarchivierung:

```bash
# Jahresarchiv erstellen (jeweils zum Jahresende)
YEAR=$(date +%Y)
docker compose exec -T db pg_dump -U praxiszeit praxiszeit \
  | gzip > ~/praxiszeit-backup/praxiszeit_archiv_${YEAR}.sql.gz

# Backup-Verzeichnis prüfen (mind. 2 Jahrgänge vorhanden?)
ls -lh ~/praxiszeit-backup/praxiszeit_archiv_*.sql.gz
```

### Checkliste Compliance §16 ArbZG
- [ ] Automatisches tägliches Backup eingerichtet (Cron-Job, siehe "Datensicherung")
- [ ] Jahresarchive werden für **mind. 2 Jahre** aufbewahrt
- [ ] Backup-Speicherort ist gesichert (nicht nur auf dem selben Server)
- [ ] Regelmäßige Wiederherstellungs-Tests durchführen
- [ ] Exportierte Excel-Berichte ebenfalls 2 Jahre archivieren

> **Hinweis:** Diese Anforderungen gelten unabhängig von PraxisZeit.
> Der Arbeitgeber ist selbst für die gesetzeskonforme Aufbewahrung verantwortlich.
