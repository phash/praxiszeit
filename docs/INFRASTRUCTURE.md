# Infrastruktur – PraxisZeit

## Docker-Services

| Service | Image | Port (intern) | Port (extern) | Zweck |
|---------|-------|---------------|----------------|-------|
| **db** | postgres:16-alpine | 5432 | — | PostgreSQL mit RLS |
| **backend** | praxiszeit-backend | 8000 | — | FastAPI (Python 3.12) |
| **frontend** | praxiszeit-frontend | 80/443 | 80, 443 (SSL) | nginx Reverse Proxy + SPA |
| **prometheus** | prom/prometheus | 9090 | 127.0.0.1:9090 | Metriken |
| **grafana** | grafana/grafana | 3000 | — (via /grafana/) | Monitoring-Dashboard |

### Docker Compose Files

| Datei | Zweck |
|-------|-------|
| `docker-compose.yml` | Basis (alle Services, HTTP only) |
| `docker-compose.ssl.yml` | SSL-Overlay: Port 443, Zertifikate, nginx-ssl.conf |

**Prod:** Immer beide Dateien zusammen verwenden:
```bash
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```

### Volumes

- `postgres_data` — Datenbank (Aufbewahrungspflicht: 2 Jahre, §16 ArbZG)
- `prometheus_data` — Metriken
- `grafana_data` — Dashboards

## nginx-Konfiguration

| Datei | Kontext |
|-------|---------|
| `frontend/nginx.conf` | HTTP (Entwicklung) |
| `ssl/nginx-ssl.conf` | HTTPS (Produktion) |

Routing:
- `/api/*` → Backend (proxy_pass)
- `/grafana/*` → Grafana (nur private IPs: 10.x, 172.16.x, 192.168.x)
- `/assets/*` → Statische Dateien (immutable cache)
- `/*` → SPA Fallback (index.html)

**Gotcha:** Neue SPA-Routes die mit einem statischen Verzeichnis kollidieren brauchen explizite `location =` **vor** dem Fallback-Block.

## Caddy

> **TODO:** Caddy-Integration dokumentieren. Falls Caddy als externer Reverse Proxy vor dem Docker-Stack eingesetzt wird, hier Konfiguration beschreiben (TLS-Termination, Proxy-Header, etc.)

## Mailserver

> **TODO:** Mailserver-Integration dokumentieren. Aktuell hat PraxisZeit keine SMTP/Mail-Anbindung. Falls E-Mail-Benachrichtigungen geplant sind (Urlaubsantrags-Bestätigungen, Passwort-Reset etc.), hier SMTP-Konfiguration und Umgebungsvariablen beschreiben.

## Netzwerk

```
Browser (LAN)
  │
  └─► https://192.168.178.44 ──► nginx (443) ──┬─► /api/*     → backend:8000
                                                 ├─► /grafana/* → grafana:3000
                                                 └─► /*         → SPA (index.html)
```

## Datenbank

- **App-User:** `praxiszeit_app` (RLS enforced)
- **Migrations-User:** `praxiszeit` (Superuser)
- **RLS:** Alle Tenant-Tabellen haben `tenant_isolation` Policy
- **Default Tenant:** `00000000-0000-0000-0000-000000000001`

## Monitoring

- **Prometheus:** http://localhost:9090 (nur lokal)
- **Grafana:** https://192.168.178.44/grafana/ (nur private IPs)
- **Backend-Metriken:** `/metrics` Endpoint (intern, von nginx nach außen geblockt)

## Umgebungsvariablen

Siehe `.env.example` für vollständige Liste. Wichtigste:

| Variable | Zweck |
|----------|-------|
| `ENVIRONMENT` | `development` / `production` |
| `SECRET_KEY` | JWT-Signing (64-char hex) |
| `DATABASE_URL` | PostgreSQL Connection String |
| `APP_DB_USER` / `APP_DB_PASSWORD` | RLS-enforced App-User |
| `COOKIE_SECURE` | `true` für HTTPS-Prod |
| `CORS_ORIGINS` | Erlaubte Origins |
