# PraxisZeit – Security-Audit-Bericht

**Datum:** 2026-06-17
**Prüfer:** AppSec-Auditor (Claude Opus 4.8, AI-Assisted White-Box Review)
**Version (App):** 1.8.10 (`master` @ b354d93)
**Scope:** Full-Stack — FastAPI (Python 3.12) Backend, React/TS Frontend, PostgreSQL 16 (RLS), Docker-Compose **und** Native-Installer (systemd/launchd/Windows-Dienst)
**Prüfrahmen:** OWASP Top 10 2021, OWASP API Security Top 10 2023, CWE, DSGVO/BDSG
**Letzter Audit:** 2026-02-28 (`security-audit-report-2026-02-28.html`), Security-Review 2026-06 (`dc889dc`)

---

## 1. Executive Summary

**Gesamturteil: KONFORM / Niedriges Restrisiko.** Risiko-Score **2.5 / 10**.

PraxisZeit ist ein durchgängig sicherheitsbewusst entwickeltes System. Der Code trägt zu nahezu jeder sicherheitsrelevanten Stelle einen erläuternden Kommentar mit Verweis auf das auslösende Finding (F-xxx / VULN-xxx / H-x / M-SECx) — die historischen Audits wurden vollständig und nachvollziehbar umgesetzt. Alle 15 Findings des Audits 2026-02-28 sind behoben oder als dokumentiertes Restrisiko (CSP `unsafe-inline`, Glob-Pinning) akzeptiert.

Dieser Audit deckt **keine Critical- und keine High-Findings im Anwendungscode** auf. Es verbleiben **3 Medium**, **4 Low** und einige Info-Punkte, überwiegend Härtungs-/Defense-in-Depth-Empfehlungen und Supply-Chain-Hygiene. Jeder potenzielle High/Critical wurde am Quellcode bzw. an den real aufgelösten Dependency-Versionen verifiziert und entschärft.

| Severity | Anzahl |
|----------|--------|
| Critical | 0 |
| High     | 0 |
| Medium   | 3 |
| Low      | 4 |
| Info     | 5 |

**Kontext:** Die App verarbeitet sensible Arbeitszeit- und Gesundheitsdaten (DSGVO Art. 9 bei Krankheits-Abwesenheiten). Multi-Tenant-Isolation, Auth und Audit-Trail sind die kritischsten Schutzziele — alle drei sind robust implementiert.

---

## 2. Methodik

White-Box Code-Review mit Verifikation am laufenden Backend-Container für Dependency-Versionen. Geprüft:

- **AuthN/AuthZ:** `auth_service.py`, `routers/auth.py`, `middleware/auth.py`, `core/limiter.py`, Cookie-Handling
- **Multi-Tenant:** RLS-Policies (Migration 027/049), `database.py`, `middleware/auth.py`, F-026-Filter über alle Router/Services (Sub-Agent-Fan-out)
- **SSRF/Update:** `core/updater.py`, `routers/feedback.py`, Stripe-Webhook
- **SSL/TLS:** `praxiszeit-server.py::_ensure_self_signed_cert`, `install.sh`, `ssl/generate-cert.sh`
- **Secrets:** committed Tree (`git ls-files` Grep), `generate-secrets.sh`, SECRET_KEY/`.db-credentials`-Persistenz (Sub-Agent-Fan-out)
- **Injection/Export:** `export_service.py` (Formel- + PDF-Markup-Escaping), `import_xls.py`, raw-SQL-Grep
- **Infra:** `nginx.conf`, `ssl/nginx-ssl.conf`, `docker-compose.yml`, systemd-Unit
- **Dependencies:** `requirements.txt` + Container-`pip freeze`, `frontend/package-lock.json` (Sub-Agent-Fan-out)

---

## 3. Findings

### M-01 — `ALLOWED_HOSTS` Default `"*"` deaktiviert TrustedHostMiddleware (BadHost-Schutz opt-in)
- **Severity:** Medium · **CWE-16 / CWE-20** · **A05:2021 – Security Misconfiguration**
- **Fundstelle:** `backend/app/config.py:114`, `backend/app/main.py:438-452`
- **Beschreibung:** `TrustedHostMiddleware` ist korrekt als äußerste Middleware verdrahtet (Mitigation gegen Starlette `BadHost`/CVE-2026-48710 — *Starlette ist im Container bereits auf 1.3.1, also gepatcht*). Der Default `ALLOWED_HOSTS="*"` macht die Host-Validierung jedoch zu einem No-Op. Internet-exponierte Deployments, die die Variable nicht setzen, verlassen sich allein auf den Starlette-Patch und verlieren die Defense-in-Depth-Schicht. In Kombination mit dem dokumentierten `$http_host`-Proxy-Verhalten (307-Trailing-Slash baut absolute Location aus dem Host-Header) ist ein gespoofter Host-Header ein Open-Redirect-/Cache-Poisoning-Vektor.
- **Risiko-Realität:** On-Prem/LAN-by-IP (Default-Zielgruppe) ist kaum betroffen; der Punkt zählt für künftige internet-facing/SaaS-Installs.
- **Empfehlung:** In Deployment-Doku + Installer für internet-facing Installs `ALLOWED_HOSTS=<domain>` erzwingen/prompten. Optional: bei `DEPLOYMENT_MODE=saas` einen leeren/`*`-Wert beim Start ablehnen.

### M-02 — `python-multipart` Glob-Pin ohne Floor
- **Severity:** Medium · **CWE-1357** · **A06:2021 – Vulnerable Components**
- **Fundstelle:** `backend/requirements.txt` (`python-multipart==0.0.*`)
- **Beschreibung:** Der Glob `0.0.*` hat keinen unteren Bound. multipart-Parsing sitzt direkt im Login-/Upload-Pfad; ältere `0.0.x` hatten DoS-/ReDoS-Probleme (z. B. CVE-2024-53981, fix in 0.0.18). **Im laufenden Container ist 0.0.32 aufgelöst — aktuell sicher** — aber ein frischer `pip install` auf einem Build-Host ohne Lockfile könnte theoretisch eine ältere Build ziehen.
- **Empfehlung:** Floor setzen: `python-multipart>=0.0.18,<0.1`.

### M-03 — CSP `style-src 'unsafe-inline'`
- **Severity:** Medium · **CWE-79 (Residualrisiko)** · **A05:2021**
- **Fundstelle:** `backend/app/middleware/static_serving.py:32`, `frontend/nginx.conf:120`, `ssl/nginx-ssl.conf:136`
- **Beschreibung:** `script-src 'self'` ist streng (gut). `style-src` erlaubt weiterhin `'unsafe-inline'` für React-Inline-Styles und zwei Keyframe-Blöcke. Reines Style-Injection-Restrisiko (CSS-Exfiltration/UI-Redress), keine Skript-Ausführung. Bewusst dokumentiert (M-SEC3) und als Tech-Debt getrackt.
- **Empfehlung:** Mittelfristig Inline-Styles auf externe CSS/Nonces migrieren. Solange beide CSP-Quellen (Middleware + nginx) byte-identisch halten.

### L-01 — Vier ChangeRequest/Absence-Lookups ohne expliziten F-026-Filter
- **Severity:** Low · **CWE-639** · **A01:2021 – Broken Access Control**
- **Fundstelle:** `backend/app/routers/change_requests.py:352,367`, `backend/app/routers/admin_change_requests.py:282,288`
- **Beschreibung:** Diese vier `.filter()`-Lookups (ChangeRequest/Absence/User by-id) verlassen sich auf RLS (Session ist tenant-scoped) **plus** einen Ownership-Check (`cr.user_id != current_user.id` → 403) statt zusätzlich den F-026-Belt-and-Suspenders `Model.tenant_id ==`-Filter zu führen. **Heute kein Leak** (RLS + Ownership greifen), aber inkonsistent mit der projektweiten F-026-Regel.
- **Empfehlung:** `, Model.tenant_id == current_user.tenant_id` an die vier Filter ergänzen — reine Konsistenz/Defense-in-Depth.

### L-02 — Loose Dependency-Pinning ohne Backend-Lockfile
- **Severity:** Low · **CWE-1357** · **A06:2021** (historisch VULN-014)
- **Fundstelle:** `backend/requirements.txt` (`4.*`, `2.0.*`, `5.*`, `0.0.*`, `2.*` …); kein `requirements.lock`/`constraints.txt`
- **Beschreibung:** Nicht-reproduzierbare Builds; eine frische Installation kann je nach Zeitpunkt abweichende (potenziell zurückgezogene/kompromittierte) Transitiv-Versionen ziehen. Frontend hat ein `package-lock.json` (gut), Backend nicht.
- **Empfehlung:** Hash-gepinnte Lockfile (`pip-compile`/`uv lock --generate-hashes`) einführen. Höchster Hebel gegen Supply-Chain-Unsicherheit.

### L-03 — Grafana hinter breitem LAN-Allowlist
- **Severity:** Low · **CWE-284** · **A01:2021**
- **Fundstelle:** `frontend/nginx.conf:58-61`, `ssl/nginx-ssl.conf:77-80`
- **Beschreibung:** `/grafana/` ist auf `10/8, 192.168/16, 172.16/12, 127.0.0.1` freigegeben. Grafana selbst ist auth-gated (`GF_AUTH_ANONYMOUS_ENABLED=false`, Admin-PW erzwungen), daher Defense-in-Depth. Auf flachem LAN erreicht jeder Host die Login-Seite.
- **Empfehlung:** Für internet-facing Installs Allowlist verengen (konkrete Admin-IPs).

### L-04 — `workalendar` unmaintained (EOL)
- **Severity:** Low · **CWE-1104** · **A06:2021**
- **Fundstelle:** `backend/requirements.txt` (`workalendar==17.*`)
- **Beschreibung:** Letzte Release 2023, keine künftigen Security-Fixes. Kein bekannter offener CVE. Bereits im Code als Migrationskandidat (→ `python-holidays`) notiert.
- **Empfehlung:** Migration auf `python-holidays` in künftigem Release; bis dahin akzeptiertes Risiko.

### Info-Findings
- **I-01 (A07):** `/api/auth/totp/setup` gibt das TOTP-Secret im Klartext zurück (`auth.py:600`). Das ist **korrektes** Verhalten — der authentifizierte Nutzer braucht das eigene Secret für manuelle Authenticator-Eintragung. Endpoint ist rate-limited (`3/minute`). Historisches VULN-003 (Brute-Force) ist durch Rate-Limit + Counter-Replay-Schutz adressiert.
- **I-02 (A09):** `BETA_MODE=True` (`config.py:145`) deaktiviert die komplette Lizenz-/Read-Only-/MA-Limit-Logik. **Kein Sicherheitsrisiko** — es ist eine Geschäftslogik-/Lizenz-Durchsetzungsentscheidung, kein Schutzziel. `build-release.sh` warnt, solange True. Vor dem ersten kostenpflichtigen Release auf `False` setzen.
- **I-03 (A05):** `installer/linux/install-local.sh:58` hardcodet `ADMIN_PASSWORD=Admin2025!test` — Header weist es als Dev-/Test-Helper aus, kein Release-Artefakt. Empfehlung: "NICHT FÜR PRODUKTION"-Banner.
- **I-04 (A04):** In-Memory-Account-Lockout (`auth.py:36`) ist per-Worker, nicht über Gunicorn-Worker geteilt. Bei Multi-Worker-Deployment schwächt das den Lockout (slowapi-Rate-Limit greift weiter). Für SaaS-Skalierung Redis-backed slowapi erwägen.
- **I-05 (A08):** xlrd 1.2.0 ist bewusst gepinnt (.xls/BIFF-Support, kein XML → kein XXE im .xls-Pfad). Upload ist admin-only, tenant-scoped, 5-MB-limitiert. Akzeptabel; langfristig .xls-Import von xlrd lösen.

---

## 4. Verifizierte starke Controls (Positive Findings)

- **Multi-Tenant-Isolation (sehr robust):** `set_tenant_context`/`set_superadmin_context` nutzen transaktions-scoped `SET LOCAL`; ein `after_begin`-Listener re-appliziert den Kontext nach jedem Commit; `get_db()` cleart die Attribute im `finally` vor Pool-Rückgabe → **kein Kontext-Bleed über gepoolte Connections**. App-Rolle `praxiszeit_app` ist `NOSUPERUSER, NOBYPASSRLS`; alle Tenant-Tabellen `FORCE ROW LEVEL SECURITY`. Auth-Middleware setzt Kontext aus **DB-Wahrheit** (nicht JWT-Claim), validiert JWT-`tid` gegen DB. Migration 049 hat RLS auf `stripe_events`/`signup_audit_log` nachgezogen. (`database.py`, `middleware/auth.py:79-93`, `init-db-user.sql`)
- **Passwort-Hashing:** Eigenimplementiertes `bcrypt_sha256` (HMAC-SHA256(salt, pw) → bcrypt, cost 12) — wire-kompatibel mit passlib v2, defeated 72-Byte-Silent-Truncation, opportunistisches Re-Hash legacy-bcrypt beim Login. (`auth_service.py:38-120`)
- **TOTP-Replay-Schutz:** `verify_totp_with_counter` persistiert per-User-Counter, lehnt `counter <= last_counter` ab; konstante-Zeit-Vergleich. Setup/Verify/Disable alle rate-limited; Disable invalidiert Sessions (token_version++). (`auth_service.py:222`, `auth.py:581-666`)
- **Login-Härtung:** Account-Lockout (5/15min, LRU gegen Victim-Eviction), Timing-Equalization via Dummy-bcrypt für nicht-existente User, neutrale Security-Logs (kein Leak von Account-Existenz/Beschäftigungsstatus), token_version-Revocation. (`auth.py:36-267`)
- **SSRF/Update:** Ed25519-Manifest-Signaturprüfung (kanonisches JSON), HTTPS-Pflicht + Host-Allowlist (`_ALLOWED_UPDATE_HOSTS`), Anti-Rollback (`_is_newer_version` per semver), SHA256-Checksum-Verify, Host-Recheck in `download_update`. Feedback-Proxy nutzt dieselbe Allowlist + `follow_redirects=False`. (`updater.py`, `feedback.py`)
- **Lizenz-Trust:** Nur PUBLIC-Keys im Repo (Liste, nie hart rotiert), privater Key offline. Ungültige Lizenz → Read-Only (kein `sys.exit`-Totalausfall). (`license.py`)
- **SSL-Cert (4 Generatoren synchron):** RSA-2048, `CA:FALSE`(critical), `KeyUsage`(critical), `extendedKeyUsage=serverAuth`, Hostname+IP im SAN — browser-akzeptierbares End-Entity-Cert. (`praxiszeit-server.py:968-1019`)
- **Injection:** Keine string-gebaute SQL (SQLAlchemy 2.0 ORM durchgängig), kein `eval/exec/pickle/yaml.load/shell=True`. XLS-Export: Formel-Injection-Guard (`neutralize_spreadsheet_formula`) an **allen** User-Zellen; PDF: `escape_pdf_text` (xml-escape gegen reportlab-Markup-Injection/SSRF via `<img src>`).
- **Secrets:** Keine committeten Produktiv-Secrets/Private-Keys. CSPRNG durchgängig (`secrets.token_hex`, `openssl rand`); SECRET_KEY atomar via `O_CREAT|O_EXCL, 0o600`; `init-db-user.sh` lehnt schwache DB-Passwörter ab; docker-compose nutzt fail-hard `${VAR:?}`.
- **HTTP-Sicherheit:** CSRF Double-Submit-Cookie, CORS deaktiviert Credentials bei Wildcard-Origin, Security-Header (CSP/HSTS/X-Frame-Options/nosniff/Referrer) in Middleware **und** nginx, `server_tokens off`, Request-Size-Limit (ASGI-Ebene, chunked-safe), SPA-Fallback mit Path-Traversal-Guard, Prometheus nur lokal/nginx-404, traceback-PII-Scrubbing + Truncation.
- **Dependency-Status (Container `pip freeze`):** starlette **1.3.1** (BadHost gepatcht), python-multipart **0.0.32** (DoS gepatcht), reportlab **4.5.1**, PyJWT **2.13.0** (keine alg-confusion), bcrypt **5.0.0**, cryptography **49.0.0**, fastapi **0.136.3**. Frontend-Lockfile: esbuild 0.28.1, axios 1.18.0, vite 8.0.16 — alle über letzter bekannt-verwundbarer Version.

---

## 5. Status der historischen Findings (Audit 2026-02-28)

| ID | Titel | Status 2026-06-17 |
|----|-------|-------------------|
| VULN-001 | Dev-Credentials in `.env` | Behoben/akzeptiert — `.env` nicht committet, `.gitignore` korrekt |
| VULN-002 | Kein Rate-Limit auf TOTP-Endpoints | **Behoben** — `@limiter.limit("3/minute")` auf setup/verify/disable |
| VULN-003 | TOTP-Secret im Klartext | Behoben/akzeptiert (I-01) — eigenes Secret, rate-limited, Replay-Counter |
| VULN-004 | Refresh-Token in localStorage | **Behoben** — HttpOnly-Cookie, scoped auf `/api/auth/refresh` |
| VULN-005 | Fehlende Paginierung | Behoben — Admin-Overview-Endpoint (`#194`) bündelt; Reports tenant-scoped |
| VULN-006 | Inkonsistente PW-Längen-Prüfung FE | Behoben — Server validiert; bcrypt_sha256 |
| VULN-007 | Fehlende HSTS | **Behoben** — Middleware + nginx setzen HSTS (HTTPS-gated) |
| VULN-008 | Grafana ohne IP-Whitelist | Behoben/abgeschwächt (L-03) — LAN-Allowlist + Auth-Gate |
| VULN-009 | Race bei clock-in | **Behoben** — `with_for_update` in `_get_open_entry` |
| VULN-010 | Rollenwechsel ohne Token-Invalidierung | **Behoben** — token_version++ bei security-relevanten Änderungen |
| VULN-011 | Urlaubsüberschuss ohne Sperre | Behoben — tagebasierter Budget-Check (#156/#167) |
| VULN-012 | Traceback mit Pfaden in DB | **Behoben** — `_scrub_pii` + Truncation auf 2000 Zeichen |
| VULN-013 | Fehlende `server_tokens` | **Behoben** — `server_tokens off` in beiden nginx-Configs |
| VULN-014 | Glob-Pinning ohne SHA | **Offen (Low, L-02)** — kein Backend-Lockfile; bcrypt5/passlib-Migration erledigt |
| VULN-015 | Admin-Erstellung ohne PW-Komplexität | **Behoben** — Startup-Check + RuntimeError in production |

Zusätzlich behoben aus Security-Review 2026-06 (`dc889dc`): reportlab-Escaping, Art.9-Masking (`_MASKED_ABSENCE_TYPES` in beiden Feeds), Host-Allowlist (BadHost), XLS end>start-Guard, `formatHoursHM`-Overflow.

---

## 6. Priorisierte Maßnahmen

1. **(M-02, L-02)** `python-multipart>=0.0.18` Floor setzen; Backend-Lockfile mit Hashes einführen. *(geringer Aufwand, hoher Hebel)*
2. **(M-01)** Deployment-Doku/Installer: `ALLOWED_HOSTS` für internet-facing Installs erzwingen.
3. **(L-01)** Vier F-026-Filter in `change_requests.py`/`admin_change_requests.py` ergänzen (Konsistenz).
4. **(M-03)** CSP `style-src 'unsafe-inline'` mittelfristig per Nonces/externe CSS ablösen.
5. **(I-02)** Vor erstem kostenpflichtigem Release `BETA_MODE=False` setzen + Lizenz-Pfad reaktivieren testen.
6. **(L-03, L-04, I-03, I-04)** Defense-in-Depth: Grafana-Allowlist verengen, workalendar→python-holidays migrieren, install-local.sh-Banner, Redis-Lockout für Multi-Worker.

**Gesamturteil: Produktionsreif aus Security-Sicht.** Keine offenen High/Critical. Die verbleibenden Punkte sind Härtungs-/Hygiene-Maßnahmen ohne akut ausnutzbares Risiko in der Default-On-Prem-Konfiguration.

---
*Erstellt mit Claude Opus 4.8 (1M context). White-Box-Review verifiziert gegen Quellcode @ b354d93 und Container-`pip freeze`.*
