# PraxisZeit — Installation mit Docker

Empfohlene Methode für Server mit Docker. Es gibt zwei Wege, an die nötigen
Dateien (inkl. `docker-compose.yml`) zu kommen:

| Weg | Für wen | Quelle |
|-----|---------|--------|
| **A) Docker-Bundle** | Kunden ohne Git | `praxiszeit-X.Y.Z-docker.tar.gz` (GitHub-Release-Asset) |
| **B) Aus dem Quellcode** | Entwickler / Updates per `git pull` | `git clone https://github.com/phash/praxiszeit` |

> Die Native-Pakete (`praxiszeit-X.Y.Z-linux-x64.tar.gz` etc.) enthalten **kein**
> `docker-compose.yml` — sie sind für die Installation ohne Docker gedacht
> (siehe [INSTALL-NATIVE.md](INSTALL-NATIVE.md)). Für Docker eines der beiden
> oben genannten Bundles verwenden.

---

## Voraussetzungen

- Docker Engine 24+ und Docker Compose v2 (`docker compose version`)
- Ausgehender Internetzugang beim ersten `up` (Base-Images, pip/npm-Build)

---

## Weg A — Docker-Bundle

```bash
# 1. Bundle entpacken (enthält einen Top-Level-Ordner praxiszeit-<version>/)
tar xzf praxiszeit-<version>-docker.tar.gz
cd praxiszeit-<version>      # z. B. praxiszeit-1.10.3

# 2. Secrets erzeugen (.env mit Zufallswerten + komplexem Admin-Passwort)
bash generate-secrets.sh
#    -> gibt das initiale Admin-Passwort aus. Notieren!

# 3a. Schneller HTTP-Test (nur lokal/intern, KEINE externe Exposition):
#     in .env ENVIRONMENT=development und COOKIE_SECURE=false setzen, dann:
docker compose up -d --build
#     -> http://<server-ip>

# 3b. Produktiv mit HTTPS (empfohlen):
bash ssl/generate-cert.sh          # selbstsigniertes Zertifikat (oder eigenes ablegen)
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
#     -> https://<server-ip>
```

---

## Weg B — Aus dem Quellcode

```bash
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit

bash tools/docker/generate-secrets.sh   # schreibt ./.env

# HTTPS (empfohlen)
bash ssl/generate-cert.sh
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

Updates: `git pull && docker compose up -d --build` (bei aktivem SSL-Overlay
beide `-f`-Dateien angeben).

---

## HTTP vs. HTTPS

- **HTTP** (`docker compose up -d`): Frontend auf Port **80**. Nur für interne
  Tests. Bei `ENVIRONMENT=production` muss `COOKIE_SECURE=false` gesetzt werden,
  sonst sendet der Browser das Refresh-Cookie über HTTP nicht und der Login
  schlägt nach 30 Minuten fehl.
- **HTTPS** (`-f docker-compose.ssl.yml`): Frontend zusätzlich auf Port **443**,
  `COOKIE_SECURE` bleibt auf `true` (Default). Empfohlen für jeden echten
  Einsatz. Bei eigener Domain `SERVER_DOMAIN` in `.env` setzen und
  `CORS_ORIGINS` anpassen.

---

## .env — wichtige Werte

`generate-secrets.sh` setzt zufällig: `SECRET_KEY`, `POSTGRES_PASSWORD`,
`APP_DB_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, ein komplexes `ADMIN_PASSWORD` und
`ENVIRONMENT=production`. Manuell anpassen:

| Variable | Bedeutung |
|----------|-----------|
| `CORS_ORIGINS` | Erlaubte Origins (eigene Domain statt `localhost`) |
| `ADMIN_USERNAME` / `ADMIN_EMAIL` | Initialer Admin |
| `PRACTICE_NAME` / `PRACTICE_ADDRESS` | Erscheint u.a. in Excel-Exporten (DSGVO) |
| `HOLIDAY_STATE` | Bundesland für Feiertage (z.B. `Bayern`) |

Das initiale Admin-Passwort **nach dem ersten Login** in der Benutzerverwaltung
ändern.

---

## Dienste & Ports

| Dienst | Port | Zweck |
|--------|------|-------|
| frontend (nginx) | 80 (+443 mit SSL) | Web-UI + Reverse-Proxy auf das Backend |
| backend (FastAPI) | intern 8000 | API |
| db (PostgreSQL 18) | intern 5432 | Datenbank (Volume `postgres_data`) |
| prometheus | `127.0.0.1:9090` | Metriken (nur lokal) |
| grafana | unter `/grafana/` | Dashboards (Passwort = `GRAFANA_ADMIN_PASSWORD`) |

Monitoring (Prometheus/Grafana) läuft mit — wer es nicht braucht, kann
`docker compose stop prometheus grafana` ausführen.

---

## Verwaltung

```bash
docker compose ps                 # Status
docker compose logs -f backend    # Backend-Logs
docker compose down               # Stoppen (Daten bleiben im Volume)
docker compose pull && docker compose up -d --build   # Update (Weg A: neues Bundle entpacken)
```

---

## Backup (gesetzliche Aufbewahrung, §16 ArbZG)

Die Zeitdaten liegen im Docker-Volume `postgres_data`. **Vor jedem `docker
compose down -v` und vor Updates** sichern.

**Am einfachsten:** in der App unter **Admin → Datensicherung** — manuell auslösen
oder einen täglichen Zeitplan + Aufbewahrung konfigurieren. Die Sicherungen landen
im Volume `praxiszeit_backups` und lassen sich dort herunterladen.

**Kommandozeile** (gzip, damit der Restore mit `gunzip -c | psql` zusammenpasst):

```bash
docker compose exec -T db pg_dump -U praxiszeit --clean --if-exists praxiszeit \
    | gzip > backup-$(date +%F).sql.gz
```

Im Docker-Bundle gibt es dafür auch die geprüften Scripts `bash backup.sh` /
`bash restore.sh` (neben der `docker-compose.yml`). Restore + Details:
[BACKUP.md](BACKUP.md).

§16 ArbZG verlangt eine Aufbewahrung von mindestens 2 Jahren. Die Volumes
`postgres_data` + `praxiszeit_backups` daher **niemals ungesichert löschen**.

---

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| Login bricht nach 30 Min ab (HTTP) | `COOKIE_SECURE=false` setzen **oder** auf HTTPS umstellen |
| `APP_DB_PASSWORD is missing` | `generate-secrets.sh` ausführen / `.env` prüfen |
| Backend startet nicht (production) | Schwaches/Platzhalter-`ADMIN_PASSWORD` → von `generate-secrets.sh` setzen lassen |
| 502 auf `/grafana/` | Grafana-Container läuft nicht (`docker compose up -d grafana`) |
| Port 80/443 belegt | Anderen Host-Port mappen oder Konflikt auflösen |
