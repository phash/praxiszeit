# In-App Bug-Reporting → pzweb (Design)

**Issue:** [praxiszeit#136](https://github.com/phash/praxiszeit/issues/136)
**Datum:** 2026-05-27
**Status:** Design approved

## Ziel

PraxisZeit-Nutzer melden aus der laufenden App heraus Fehler/Feedback (Titel +
Beschreibung + Schweregrad). Die Meldung geht über einen Backend-Proxy an den
zentralen pzweb-Bug-Tracker (`POST /v1/bugs`) und erscheint dort im Bug-Board.

## pzweb-Vertrag (Quelle der Wahrheit)

`POST https://praxiszeit.mr-development.de/v1/bugs` — offen, Auth über `license_id`.
`multipart/form-data`:

| Feld | Pflicht | Inhalt |
|---|---|---|
| `license_id` | ja | `customer_id` der Lizenz (`pz-<uuid>`, JWT-Claim `sub`) |
| `title` | ja | max. 200 Zeichen |
| `description` | ja | Freitext |
| `app_version` | optional | z. B. `1.5.6` |
| `os` | optional | `windows`/`linux`/`darwin` |
| `severity` | optional | `low`\|`medium`\|`high`\|`critical` (Default `medium`) |

Antworten: `201 {id,status:"received"}` · `403` (Lizenz unbekannt/inaktiv) ·
`422` (Validierung) · `429` (Rate-Limit 10/h pro IP).

## Architektur

Backend-Proxy (kein direkter Browser→pzweb-Call: CORS, und
`license_id`/Version/OS gehören nicht ins Frontend).

```
Frontend FeedbackDialog ──POST /api/feedback/report──► praxiszeit-Backend Proxy
   (title, description, severity)                          │ ergänzt license_id,
                                                           │ app_version, os
                                                           ▼
                                          POST https://praxiszeit.mr-development.de/v1/bugs
                                                     (multipart, httpx)
```

## Backend

**Datei:** `backend/app/routers/feedback.py`, registriert in `main.py`.

- `POST /api/feedback/report` — **authentifiziert** (`get_current_user`; CSRF/Auth
  laufen über den vorhandenen Axios-Client). Nur eingeloggte Nutzer melden.
- Request-Schema (Pydantic): `FeedbackReportIn`
  - `title: str` (1–200), `description: str` (≥1),
  - `severity: Literal["low","medium","high","critical"] = "medium"`.
- Ablauf:
  1. `lic = get_current_license()`. `None` → `400` „Ohne hinterlegte Lizenz ist
     keine Bug-Meldung möglich." (On-Prem ohne Lizenz hat keine `customer_id`.)
  2. Serverseitig ergänzen: `license_id = lic.customer_id`,
     `app_version = APP_VERSION` (`updater.py`), `os = platform.system().lower()`.
  3. Ziel `f"{settings.feedback_server_url}/v1/bugs"`; Host gegen
     `_ALLOWED_UPDATE_HOSTS` prüfen (Helper analog `_verify_download_host`).
  4. Outbound via **httpx** (bereits Dependency), `multipart/form-data`,
     Timeout ~15 s, `follow_redirects=False`.
- Response-Mapping (App bleibt stabil, nie crashen):
  - `201` → `200 {"status":"received","id":…}`
  - `403` → `409` „Lizenz inaktiv/abgelaufen — Bug-Meldung derzeit nicht möglich."
  - `429` → `429` „Zu viele Meldungen, bitte später erneut versuchen."
  - `422` → `400` „Ungültige Eingabe."
  - Netzwerk/Timeout/sonstige → `502` „Feedback-Server nicht erreichbar, bitte später erneut."
- **Read-Only-Middleware:** `/api/feedback/report` wird **nicht** ausgenommen.
  Bei abgelaufener Lizenz greift die generische `403`-Nur-Lese-Meldung (pzweb
  würde eine inaktive Lizenz ohnehin mit `403` ablehnen → kein nutzloser Call).
- **Config:** `feedback_server_url: str = "https://praxiszeit.mr-development.de"`
  in `config.py` (nicht hart kodieren).

## Frontend (React 18 + TS + Tailwind)

- `src/api/feedbackApi.ts`: `submitFeedback({title, description, severity})` →
  `apiClient.post('/feedback/report', …)`.
- `src/components/FeedbackDialog.tsx`: Titel (Pflicht, max 200, Counter),
  Beschreibung (Pflicht, Textarea), Schweregrad-Select (niedrig/mittel/hoch/
  kritisch → `low/medium/high/critical`, Default mittel). Read-only-Zeile
  „Version `__APP_VERSION__` · Betriebssystem wird automatisch mitgesendet".
  Keine automatische PII.
- Einstieg im **HelpPanel**: Button „Fehler melden / Feedback" öffnet den Dialog.
- Erfolg → Toast „Danke, deine Meldung wurde übermittelt" + Dialog schließen.
  Fehler → Toast je nach Status (`409`/`429`/`5xx`).

## Tests

- **Backend** (`backend/tests/test_feedback.py`, pytest): Outbound **gemockt**
  (httpx `MockTransport`). Verifiziert: korrektes Multipart (license_id aus
  Lizenz, app_version/os ergänzt, severity), Mapping `201/403/429`/Netzwerkfehler,
  „keine Lizenz" → `400`. Lauf: lokal mit SQLite-conftest + Env-Vars (ohne Docker)
  bzw. `docker compose exec backend pytest tests/ -v`.
- **Frontend** (Vitest): `FeedbackDialog` — Validierung (leer/zu lang), Submit,
  Erfolg/Fehler-States. Lauf: `cd frontend && npm test`.
- Optional E2E (Playwright) Happy-Path später.

## Scope / Non-Goals

- **Kein** Datei-Upload (Screenshots/Logs erst pzweb Plan 3) — nur Text.
- **Keine** automatische PII (keine User-Mail, kein Klartext-Name angehängt).

## Delivery & offene Gates

1. Feature + Unit-Tests implementieren, lokal grün, committen.
2. **Manuelle Verifikation gegen echtes pzweb** (gültige Lizenz, laufende
   Instanz, Bug erscheint als `source=app`) — **nicht** auf dem Windows-Builder
   möglich → bei Dev-Box/Betreiber.
3. **Erst nach (2):** Version-Bump 1.5.5→1.5.6 (`updater.py`,
   `frontend/package.json`, `tools/build-release.sh`) + `CHANGELOG.md` + neues
   GH-Issue für den Windows-Builder (Windows-Release bauen).

## Integrationspunkte

| Zweck | Datei |
|---|---|
| Lizenz/`customer_id` | `backend/app/core/license.py` → `get_current_license().customer_id` |
| App-Version | `backend/app/core/updater.py` → `APP_VERSION` |
| Host-Allowlist | `backend/app/core/updater.py` → `_ALLOWED_UPDATE_HOSTS` / `_verify_download_host` |
| OS | `platform.system().lower()` |
| Frontend-Client | `frontend/src/api/client.ts` (Axios, CSRF + withCredentials) |
| UI-Einstieg | `frontend/src/components/HelpPanel.tsx` |
| Read-Only-Middleware | `backend/app/middleware/license.py` |
