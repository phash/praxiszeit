# PraxisZeit mit Docker starten

Der schnellste Weg, PraxisZeit auf einem eigenen Server zu betreiben: Die
komplette Software **inklusive PostgreSQL** läuft in Containern — es werden keine
Daten in eine Cloud übertragen.

> **Wichtig — welches Paket?** Die **Native-Pakete**
> (`praxiszeit-…-linux-x64.tar.gz`, `…-windows-x64.zip` usw.) enthalten **kein**
> `docker-compose.yml` — sie sind für die Installation **ohne** Docker gedacht.
> Für Docker brauchen Sie das **Docker-Paket** `praxiszeit-<version>-docker.tar.gz`
> (enthält Compose + Build-Kontext) **oder** den Quellcode (`git clone`).

---

## Voraussetzungen

- **Docker Engine 24+** und **Docker Compose v2** (`docker compose version`)
- Ausgehender Internetzugang beim **ersten** Start (Base-Images + Build)
- ~2 GB RAM, ~5 GB freier Speicher

---

## 1. Docker-Paket entpacken

```bash
tar xzf praxiszeit-<version>-docker.tar.gz
cd praxiszeit-<version>
```

Das Paket enthält alles Nötige: `docker-compose.yml`, `docker-compose.ssl.yml`,
`.env.example`, `generate-secrets.sh`, `ssl/` (Zertifikats-Skript + nginx-Config)
und den Build-Kontext (`backend/`, `frontend/`, `prometheus/`, `grafana/`).

## 2. Secrets erzeugen

```bash
bash generate-secrets.sh
```

Schreibt eine `.env` mit zufälligem `SECRET_KEY`, Datenbank-Passwörtern und einem
komplexen `ADMIN_PASSWORD` (wird am Ende ausgegeben — **notieren!**).
Anschließend in `.env` noch Praxis-Name, `ADMIN_EMAIL` und `HOLIDAY_STATE`
(Bundesland) anpassen.

## 3. Starten

**Variante A — HTTP** (nur internes Netz / schneller Test):

```bash
docker compose up -d --build
```

→ erreichbar unter `http://<server-ip>`

**Variante B — HTTPS** (für den echten Einsatz empfohlen):

```bash
bash ssl/generate-cert.sh
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

→ erreichbar unter `https://<server-ip>` — beim ersten Aufruf das
selbstsignierte Zertifikat einmalig im Browser bestätigen.

Der erste Start dauert einige Minuten (Images werden gebaut, Datenbankschema
wird migriert).

## 4. Prüfen & anmelden

```bash
curl http://localhost/api/health        # {"status":"healthy","database":"connected"}
docker compose ps                        # alle Dienste "Up"/"healthy"
```

Im Browser öffnen und mit den Admin-Zugangsdaten aus Schritt 2 (`ADMIN_EMAIL` /
ausgegebenes `ADMIN_PASSWORD`) anmelden. Eine kurze **Willkommens-Tour** und der
**Schnellstart** (unten links) führen durch die Ersteinrichtung.

---

## Täglicher Betrieb

```bash
docker compose ps                 # Status
docker compose logs -f backend    # Backend-Logs
docker compose down               # Stoppen (Daten bleiben im Volume postgres_data)
docker compose up -d --build      # Wieder starten
```

PraxisZeit startet nach einem Server-Neustart automatisch
(`restart: unless-stopped`).

---

## Ohne Docker-Paket: aus dem Quellcode

Wer den Quellcode hat, kann denselben Weg gehen:

```bash
git clone https://github.com/phash/praxiszeit.git && cd praxiszeit
bash tools/docker/generate-secrets.sh
bash ssl/generate-cert.sh
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

---

## Backup, Updates & Details

Datenbank-Backup (§16 ArbZG: 2 Jahre aufbewahren), Update-Vorgehen,
`.env`-Variablen und Fehlerbehebung stehen ausführlich in
[INSTALL-DOCKER.md](INSTALL-DOCKER.md).

---

*Hinweis: Die App-Images werden lokal aus dem mitgelieferten Build-Kontext gebaut
(`build:` im Compose) — es wird keine externe Image-Registry benötigt.*
