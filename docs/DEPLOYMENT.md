# Deployment – PraxisZeit

## Deployment-Modi (`DEPLOYMENT_MODE`)

PraxisZeit liefert **eine Codebasis in zwei Varianten**, gesteuert über die Env-Variable `DEPLOYMENT_MODE`:

| Modus | Default | Verwendung | Merkmale |
|-------|---------|-----------|---------|
| `onprem` | ✅ | Docker-Server, Native-Installer (Kundenserver) | Single-Tenant, License-Middleware aktiv, Public-Signup deaktiviert, Default-Tenant + Default-Admin werden beim Start angelegt |
| `saas` | — | Hosted-Cloud (praxiszeit.de) | Multi-Tenant, Self-Service-Signup, Stripe-Billing, KEINE automatische Tenant-/Admin-Erzeugung, License-Middleware pausiert (Suspend erfolgt per Tenant-Status) |

**Default = `onprem`**: Bestandsinstallationen werden beim Upgrade nicht gebrochen — sie benötigen keine Env-Änderung.

**Runtime-Check**:
- Public `GET /api/system/info` liefert `{deployment_mode, version}` (ohne Auth)
- Backend-Helper: `from app.core.deployment import is_saas, is_onprem`
- Frontend: `useSystemInfo()` / SPA versteckt SaaS-UI (Billing, Signup, Trial-Banner) im `onprem`-Modus

**SaaS-spezifische Env-Variablen** (nur wenn `DEPLOYMENT_MODE=saas`): siehe Phase 3–4 Dokumentation (Signup, Stripe).

## Prod-Server

- **Host:** 192.168.178.44
- **Pfad:** `/opt/praxiszeit/praxiszeit`
- **Zugang:** SSH als `manuel` (Key-Auth eingerichtet)
- **URL:** https://192.168.178.44 (selbstsigniertes Zertifikat)

## Deployment ausführen

```bash
ssh manuel@192.168.178.44 "cd /opt/praxiszeit/praxiszeit && sudo ./deploy.sh"
```

`deploy.sh` macht: `git pull` → `build frontend backend` → `up -d` (mit SSL-Overlay) → Health-Check.

### Manuell (falls deploy.sh nicht nutzbar)

```bash
cd /opt/praxiszeit/praxiszeit
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.ssl.yml build frontend backend
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```

**Wichtig:** Immer `-f docker-compose.ssl.yml` angeben! Ohne SSL-Overlay lauscht nginx nur auf Port 80 und HTTPS (443) ist nicht erreichbar → "Network Error" im Frontend.

## Nach dem Deploy prüfen

```bash
# Container-Status
docker compose ps

# Backend-Logs (Fehler?)
docker compose logs --tail=30 backend

# Frontend erreichbar?
curl -k https://localhost/api/health
```

## Nur Frontend oder Backend rebuilden

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.ssl.yml"

# Nur Frontend (nach UI/nginx-Änderungen)
$COMPOSE build frontend && $COMPOSE up -d frontend

# Nur Backend (nach Python-Änderungen)
$COMPOSE build backend && $COMPOSE up -d backend
```

## Migrationen

Alembic-Migrationen laufen automatisch beim Backend-Start (`alembic upgrade head` im Entrypoint).

**Neue Migration erstellen** (auf dem Dev-Rechner, nicht im Container):
```bash
cd backend
alembic revision --autogenerate -m "beschreibung"
```
Migration committen **vor** Container-Rebuild.

## Rollback

```bash
# Auf vorherigen Commit zurück
git log --oneline -5
git checkout <commit-hash>
docker compose -f docker-compose.yml -f docker-compose.ssl.yml build frontend backend
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```
