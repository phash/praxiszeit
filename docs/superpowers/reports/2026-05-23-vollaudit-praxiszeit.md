# Voll-Audit PraxisZeit

**Auditdatum:** 23. Mai 2026 · **Branch:** master (HEAD `5e03cdf`) · **Version:** 1.4.3
**Letztes Audit:** 08. April 2026 (4 HIGH Security-Findings + offene Multi-Tenant-Befunde)
**Stack:** FastAPI / React 18 + TypeScript / PostgreSQL 16 mit RLS
**Geprüfte Kategorien:** ArbZG-Compliance · Authentifizierung · Multi-Tenant-Isolation · Input-Validation · Secrets · Frontend-Security · Funktions-Korrektheit · Native-Installer · Test-Coverage

---

## Executive Summary

PraxisZeit befindet sich in **gutem Sicherheitszustand** und ist im On-Prem-Single-Tenant-Betrieb **vollständig ArbZG-konform**. Alle vier HIGH-Findings vom Audit am 08.04. sind nachweislich behoben. Das neue Feature `vacation-request-edit` ist sauber implementiert (Tenant-Scope, `with_for_update`, Audit-Logs, Pydantic-Schemas korrekt).

### Findings-Übersicht

| Severity | Anzahl | Bereiche |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 1 | E-Mail HTML-Injection im Signup-Flow (nur SaaS-Modus) |
| MEDIUM | 7 | F-026 Inkonsistenz, RLS-Lücke `stripe_events`, Signup-Passwort-Discrepanz, CI-Abdeckung, PublicHoliday-Tenant-Filter (3 Sub-Items), Tenant-Filter `rest_time_service` |
| LOW | 10 | Tech-Debt: max_length, ge/le-Constraints, Withdraw-Race, Stripe-PII-Excerpt, Error-Logs Tenant-Scope, etc. |

### Konformität ArbZG (Stand 23.05.)

| Paragraph | Status | Delta seit 08.04. |
|---|---|---|
| §3 (Tageshöchstarbeitszeit + 24-Wochen-Ausgleich) | KONFORM | Neu: 24-Wochen-Report `/api/admin/reports/24-week-average` |
| §4 (Ruhepausen) | KONFORM | Unverändert |
| §5 (Mindestruhezeit 11h) | KONFORM, verifiziert | Echtzeit-Warning beim Einstempeln funktioniert |
| §6 (Nachtarbeit 23:00–06:00) | KONFORM | `arbzg_utils.is_night_work()` einziger Einstiegspunkt |
| §9/§10 (Sonn-/Feiertagsruhe) | KONFORM (On-Prem) / TEILWEISE (Multi-Tenant) | 7 Stellen mit `PublicHoliday` ohne `tenant_id`-Filter |
| §11 (15 freie Sonntage, Ersatzruhe) | KONFORM | Unverändert |
| §14 (48h-Wochenwarnung) | KONFORM | Unverändert |
| §16 (Aufzeichnungspflicht) | KONFORM | VR-Edit/Cancel-Audit-Logs korrekt eingetragen |
| §18 (Ausnahmen) | KONFORM | Unverändert |
| EU-AZ-RL Aufzeichnungspflicht (EuGH C-55/18) | KONFORM | Unverändert |

### Empfehlung in einem Satz

**Vor dem nächsten Kunden-Deployment** das HIGH-Finding (HTML-Escape im Signup-Mail) fixen und die `_get_*_in_tenant`-Helper für die 10+ F-026-Stellen einführen; **vor dem SaaS-Rollout (Phase 4)** die PublicHoliday-Queries und `stripe_events`-RLS härten. Alles andere ist Backlog.

---

## TEIL 1 — ArbZG-Compliance

### A. Datenmodell & Persistenz

#### A-1: Zeitstempel und Granularität — **KONFORM**

`TimeEntry.start_time`/`end_time` als `time`-Feld, minutengenau nach `replace(second=0, microsecond=0)` in `time_entries.py:240, 305`. Gesetzeskonform (sekundengenau ist nicht vorgeschrieben).

#### A-2: Audit-Trail und Revisionssicherheit — **KONFORM**

`TimeEntryAuditLog` wird in allen schreibenden Pfaden befüllt:

| Pfad | Datei:Zeile | Source-Marker |
|---|---|---|
| Employee-Löschung | `time_entries.py:706-716` | `manual` |
| Admin-Create/Update/Delete | `admin_time_entries.py:101-105, 195-207, 240-244` | `manual` |
| Change-Request-Approval | `admin_change_requests.py` (3 Typen) | `change_request` |
| Absence-CR-Approval | `admin_change_requests.py:283-349` | `absence_request_approval` |
| Auto-Close | `time_entries.py:150-168` | `auto_close` |
| Vacation-Request-Cancel | `vacation_requests.py:211-221` | `vacation_request_cancel` |
| **Vacation-Request-Edit** (NEU) | `vacation_requests.py:349-361`, `admin_vacations.py:372` | `vacation_request_edit` |

Alle Source-Marker liegen unter dem `varchar(40)`-Limit (Migration 037). Längster Wert: `absence_request_approval` (24 Zeichen).

**LOW A-2-01** — `vacation_requests.py` enthält keinen Audit-Log-Eintrag beim **Erstellen** eines Urlaubsantrags. Genehmigung, Bearbeitung und Stornierung sind geloggt; der Erstellzeitpunkt fehlt. Für §16 ArbZG nicht explizit vorgeschrieben, erschwert aber Aufsichtsprüfungen.
> **Fix:** Beim `POST /api/vacation-requests/` einen `TimeEntryAuditLog`-Eintrag mit `action="create"`, `source="vacation_request"` anlegen.

#### A-3: Zeitzonen — **KONFORM**

`timezone_service.now_local()`/`today_local()` zentral. §5-Berechnung in `time_entries.py:262-267` nutzt `datetime.combine(..., tzinfo=LOCAL_TZ)` auf beiden Seiten → DST-Übergänge korrekt (F-030).

#### A-4: 730-Tage-Aufbewahrungspflicht (§16 ArbZG) — **KONFORM**

`admin_users.py:202-212`: Purge-Schutz prüft `days_since < 730` → HTTP 409 mit Klartext-Begründung. `can_purge`-Flag in Listansicht konsistent (`:127`). Anonymisierung behält Zeiteinträge, löscht nur Abwesenheiten (korrekt — keine Aufbewahrungspflicht für Abwesenheiten nach ArbZG).

---

### B. Geschäftslogik & Validierung

#### B-1: §3 — Tagesarbeitszeit — **KONFORM**

Hard-Stop bei 10h und Warnung bei 8h in allen sechs Pfaden:

| Pfad | Hard-Stop 10h | Warnung 8h | Wochenwarnung 48h |
|---|---|---|---|
| `time_entries.py` create (Z. 504) | ✓ | ✓ (Z. 513) | ✓ (Z. 515-524) |
| `time_entries.py` update (Z. 623) | ✓ | ✓ (Z. 644) | ✓ (Z. 646-656) |
| `time_entries.py` clock_out (Z. 318) | ✓ | ✓ (Z. 347) | ✓ (Z. 349-359) |
| `admin_time_entries.py` create (Z. 59) | ✓ | ✓ (Z. 66-67) | ✓ (Z. 70-76) |
| `admin_time_entries.py` update (Z. 163) | ✓ | ✓ (Z. 170-171) | ✓ (Z. 174-180) |
| `change_requests.py` create (Z. 214) | ✓ | — (Antrag) | — |
| `admin_change_requests.py` approve (Z. 367-399) | — (Post-Commit Warn) | ✓ (Z. 376-399) | ✓ (Z. 388-399) |

#### B-2: §3 — 24-Wochen-Ausgleichszeitraum (NEU) — **KONFORM**

`reports.py:695-772`: Neuer Endpoint `GET /api/admin/reports/24-week-average` berechnet pro aktivem, nicht-exemtem Mitarbeiter das Verhältnis der Gesamtstunden zum Kontingent `8h × (24 × work_days_per_week)`. `exempt_from_arbzg`-User werden korrekt übersprungen (`:722`).

**NICE-TO-HAVE** — Der Report nutzt `float(e.net_hours or 0)`. Falls `net_hours` für historische Einträge `None` ist, werden diese als 0h gezählt → Durchschnitt verzerrt nach unten.
> **Fix:** Direkt `_net_hours(e.start_time, e.end_time, e.break_minutes)` berechnen.

#### B-3: §4 — Ruhepausen — **KONFORM**

`break_validation_service.py` implementiert korrekt:
- `>6h` Netto → 30 Min Pause (Z. 87)
- `>9h` Netto → 45 Min Pause (Z. 79)
- §4 Satz 2: Pausenabschnitte ≥15 Min (Z. 65-69 für Lücken, Z. 95-99 für deklarierte Pausen)
- Lücken zwischen Einträgen ≥15 Min zählen als Pause (Z. 69)
- `exclude_entry_id` korrekt in allen Update-Pfaden

**Systemische Einschränkung (keine Verletzung):** `break_minutes` ist ein einzelner Integer je `TimeEntry` — wann innerhalb der Schicht die Pause genommen wurde, kann nicht geprüft werden. §4 ArbZG schreibt nur Gesamtdauer vor, nicht den Zeitpunkt.

#### B-4: §5 — Echtzeit-Ruhezeit-Warnung — **KONFORM, verifiziert**

`time_entries.py:247-269` im `clock_in()`:
- Lade letzten abgeschlossenen Eintrag (`end_time.isnot(None)`, geordnet absteigend)
- TZ-aware `datetime.combine` auf beiden Seiten (DST-safe)
- Bei `rest_hours < 11`: Warnung `REST_TIME_WARNING: Nur X.Xh Ruhezeit...` in `clock_in_warnings`
- Nur für nicht-exempte User (`:248`)

Frontend zeigt Warning via `showArbzgWarnings(toast, res.data?.warnings)` im `StampWidget.tsx:73`.

Retrospektiver Report (`rest_time_service.py:66-75`) berechnet max-End vs. min-Start des Folgetags → behandelt Splitschichten korrekt.

#### B-5: §6 — Nachtarbeit — **KONFORM**

`arbzg_utils.is_night_work()` ist kanonischer Einstiegspunkt; importiert von Routern (employee/admin/CR), Reports und Export-Services. Nachtzeit-Definition 23:00–06:00 (entspricht §2 Abs. 4 ArbZG-Normalfenster; alternatives 22:00–05:00 wäre nur per Tarifvertrag, nicht relevant). Nachtarbeit-Report erkennt Nachtarbeitnehmer ab ≥48 Nachtarbeitstagen/Jahr (`reports.py:546-599`).

#### B-6: §9/§10 — Sonn- und Feiertagsruhe — **KONFORM (On-Prem) / TEILWEISE (Multi-Tenant)**

`time_entries.py` nutzt in allen schreibenden Pfaden korrekt `is_holiday(db, date, tenant_id=current_user.tenant_id)` (Z. 101, 362, 527, 662). Der Saturday-Bug aus früheren Audits ist gefixt.

**MEDIUM B-6-01 — PublicHoliday-Queries ohne tenant_id (7 Stellen, 4 Dateien)**

Im Single-Tenant-On-Prem-Betrieb durch RLS abgefangen, im kommenden SaaS-Betrieb (Phase 4) potenzielles Cross-Tenant-Leak: Feiertage eines Tenants werden für anderen verwendet → Arbeitstag fälschlich als Feiertag gewertet (oder umgekehrt).

| Datei:Zeile | Code |
|---|---|
| `absences.py:250-252` | `db.query(PublicHoliday).filter(PublicHoliday.year == year).all()` |
| `admin_vacations.py:159` | `db.query(PublicHoliday).filter(PublicHoliday.year == year).all()` |
| `calculation_service.py:201-203` | in `get_monthly_target()` |
| `calculation_service.py:387-390` | in `get_overtime_account()` |
| `calculation_service.py:463-465` | in `get_ytd_summary()` |
| `calculation_service.py:633` | in `count_workdays()` |

> **Fix:** Optionalen `tenant_id`-Parameter in den Calculation-Service-Funktionen ergänzen analog `is_holiday()`. Aufrufer pflegen `tenant_id=current_user.tenant_id` durch.

#### B-7: §18 — Ausnahmen (leitende Angestellte) — **KONFORM**

`user.exempt_from_arbzg` als erste Bedingung vor §3/§4/§6-Checks in allen Pfaden. Defensive Logik in `admin_time_entries.py:147`: wenn User nicht gefunden, greift trotzdem ArbZG-Check.

---

### C. Benutzeroberfläche & UX

#### C-1: Warnhinweise im Frontend — **TEILWEISE**

`showArbzgWarnings(toast, warnings)` korrekt aufgerufen in `StampWidget.tsx:73, 98` und `TimeTracking.tsx:337`.

**LOW C-1-01 — ChangeRequestForm ignoriert Backend-Warnings**

`frontend/src/components/ChangeRequestForm.tsx:45-61`: Der `await apiClient.post('/change-requests', ...)` ignoriert die Response. Das Backend gibt bei §6-Nachtarbeiter-Verstößen Warnings zurück (`change_requests.py:283-291`), die der Mitarbeiter nie sieht.

```typescript
// Aktuell:
await apiClient.post('/change-requests', { ... });
onSuccess();

// Korrekt:
const response = await apiClient.post('/change-requests', { ... });
showArbzgWarnings(toast, response.data?.warnings);
onSuccess();
```

#### C-2: Mitarbeiter-Transparenz (EuGH C-55/18) — **KONFORM**

`GET /api/time-entries/` liefert eigene Einträge mit `is_editable`-Flag und Warnings. Grundanforderung des EuGH-Urteils erfüllt.

---

### D. Reporting & Export

#### D-1: Gesetzlich vorgeschriebene Reports — **KONFORM**

| Report | Endpoint | Paragraph |
|---|---|---|
| Ruhezeit-Verstöße | `GET /rest-time-violations` | §5 |
| 15-freie-Sonntage | `GET /sunday-summary` | §11 |
| Nachtarbeit-Übersicht | `GET /night-work-summary` | §6 |
| Ersatzruhetage | `GET /compensatory-rest` | §11 |
| **24-Wochen-Ausgleich (NEU)** | `GET /24-week-average` | §3 Abs. 2 |
| Monatsreport | `GET /monthly` | §16 |
| Excel/ODS/PDF-Export | `GET /export, /export-ods, /export-pdf` | §16 |
| Jahresbericht | `GET /export-yearly[-classic|-ods]` | §16 |

#### D-2: §16 Aufzeichnungsvollständigkeit — **KONFORM**

`time_entry_audit_logs` erfasst alle schreibenden Operationen. DSGVO-Datenzugriffe auf Gesundheitsdaten werden zusätzlich mit `action="health_data_read"` / `source="dsgvo"` protokolliert (`reports.py:60-70, 134-144, 234-244`).

---

### E. ArbZG-Sicherheit & Datenschutz

#### E-1: DSGVO Art. 9 — Maskierung `sick → absent` — **KONFORM, verifiziert**

| Endpoint | Datei:Zeile |
|---|---|
| Kalender | `absences.py:87-101` |
| Team-Upcoming | `absences.py:133-145` |
| Monatsreport | `reports.py:111` (`sick_hours if include_health_data else 0.0`) |
| Jahresbericht | `reports.py:186-187` |

#### E-2: Rollenbasierte Zugriffskontrolle — **KONFORM**

JWT mit `tid`-Claim + `token_version`-Revocation. `require_admin` für Admin-Routes, `require_superadmin` für `/api/superadmin/*` (§16-Notfall-Export auch bei deaktivierten Tenants).

#### E-3: §16 — Tenant-Deaktivierung sperrt Zeitdaten-Zugriff — **TEILWEISE (offen seit 08.04.)**

`tenant.is_active == False` → 403 für alle User, §16-Export nur via Superadmin-Notfall-Pfad. Im aktuellen On-Prem-Betrieb nicht relevant.

---

### F. Integration & Schnittstellen

#### F-1: §9 — Feiertagskalender-Integration — **KONFORM (On-Prem)**

`holiday_service.py`: alle 16 Bundesländer via `workalendar`, tenant-scoped (Z. 69-77). `sync_current_and_next_year` filtert korrekt per `tenant_id` (Z. 220-225). In-Process-Cache nach `(tenant_id, year)` gekapselt (Z. 158-178), Invalidierung bei Schreibzugriffen.

#### F-2: §5 — Rest-Time-Service Multi-Tenant — **MEDIUM**

`rest_time_service.py:116`:
```python
users = db.query(User).filter(User.is_active == True).all()
```
Kein expliziter `tenant_id`-Filter. RLS schützt zwar, aber CLAUDE.md F-026-Pattern (belt-and-suspenders) verletzt.

> **Fix:** Signatur um optionalen `tenant_id`-Parameter erweitern, in `reports.py` mit `tenant_id=current_user.tenant_id` aufrufen.

---

## TEIL 2 — Security & Funktion

### 1. Authentication & Authorization

| Status | Komponente | Beobachtung |
|---|---|---|
| ✓ OK | JWT-Algorithmus | HS256 mit SECRET_KEY ≥32 Zeichen, Weak-Indicator-Check (`config.py:172-186`) |
| ✓ OK | Token-Expiry | Access 30 min, Refresh 7 Tage, `token_version`-Counter (`auth_service.py:147-194`) |
| ✓ OK | Token-Versioning | `++` bei Logout, Passwort-Change, Rolle-Change (`admin_users.py:359, 379, 397`) |
| ✓ OK | Password-Hashing | `bcrypt_sha256` (passlib-kompatibel, ohne passlib-Dependency); v=2-Protokoll; Legacy-Hashes opportunistisch migriert (F-041) |
| ✓ OK | Brute-Force-Schutz | 5 Versuche / 15 min, OrderedDict-LRU (F-039) verhindert attacker-evicts-victim |
| ✓ OK | Dummy-Hash bei unknown user | Timing-Equalization gegen Enumeration (`auth.py:41, 168`) |
| ✓ OK | TOTP Replay-Schutz | Per-User-Counter (`auth_service.py:220-260`, Migration 032) |
| ✓ OK | Cookie-Security | `httponly`, `secure`, `samesite="lax"`, refresh-cookie auf `/api/auth/refresh` scoped |
| ✓ OK | CSRF | Double-Submit-Cookie, rotiert bei Refresh, exempt nur für login/refresh/health |
| ⚠ MEDIUM | Password-Komplexität-Discrepanz | Admin-Pfad: ≥10 + Upper/Lower/Digit · Self-Service-Signup: nur min_length=8 → Trial-Tenants können schwächere Passwörter setzen |
| ⚠ LOW | Kein Special-Char-Requirement | NIST 800-63B konform (Länge > Komplexität), aber typische Audit-Erwartung nicht erfüllt |
| – | Kein Passwort-Reset-Flow | Bewusst (kein Email-Reset-Vektor), aber UX-Lücke für Solo-Admins |
| – | `require_superadmin` | Konsistent angewendet, klare Semantik (User mit `tenant_id IS NULL` + role=ADMIN) |

### 2. Multi-Tenant Isolation

| Status | Befund | Quelle |
|---|---|---|
| ✓ OK | RLS auf allen Kern-Tabellen | Migration 027 enabled+forced RLS für 12 Tabellen; 033/034 ziehen nach für `tenant_invoices`, `signup_tokens` |
| ⚠ MEDIUM | **RLS fehlt auf `stripe_events`** | Migration 035: Tabelle mit `tenant_id`-Spalte, aber **keine** `ENABLE ROW LEVEL SECURITY`. Aktuell nur Superadmin schreibt, CLAUDE.md-Pflicht verletzt. |
| – | `signup_audit_log` ohne RLS | Bewusst (Migration 034:85, "anonymous requesters") — DSGVO-konform, sollte dokumentiert sein |
| ⚠ MEDIUM | **F-026 belt-and-suspenders inkonsistent** | RLS schützt, aber expliziter `Model.tenant_id == current_user.tenant_id` fehlt in 10+ Stellen |
| ✓ OK | Background-Tasks / `SessionLocal()` | 4 Stellen geprüft, alle setzen `set_superadmin_context(db)` |
| ✓ OK | Auth-Middleware Tenant-Setup | `middleware/auth.py:86-93`, JWT-tid wird gegen DB-tenant_id validiert |
| ✓ OK | Tenant-Context persistiert | `database.py:20-32` Event-Listener re-applied SET LOCAL nach jeder Tx-Begin (gefixt seit 08.04.) |
| ✓ OK | Cross-tenant Tests | `test_cross_tenant_api.py` (12), `test_tenant_rls.py` (13) |

**MEDIUM-1 Detail — 10+ Stellen ohne expliziten Tenant-Filter:**

| Datei:Zeile | Endpoint/Funktion |
|---|---|
| `vacation_requests.py:381` | Withdraw VR |
| `change_requests.py:340` | Withdraw CR |
| `change_requests.py:325` | Get CR (employee) |
| `change_requests.py:61, 148` | CR-Lookup bei CR-Create |
| `time_entries.py:432, 571, 688` | GET/UPDATE/DELETE entry |
| `absences.py:404` | Absence DELETE |
| `admin_time_entries.py:236` | Admin entry lookup |
| `admin_change_requests.py:152, 170, 178` | CR-Approval Entry/Absence-Lookup |

> **Fix:** Helper-Pattern wie `_get_user_in_tenant()` aus `admin_users.py:20-38` einführen: `_get_entry_in_tenant()`, `_get_cr_in_tenant()`, `_get_vr_in_tenant()`, `_get_absence_in_tenant()`. RLS bleibt zweite Verteidigungslinie, explizite Filter machen Findings im Review trivial sichtbar.

### 3. Input-Validation & Injection

| Status | Befund | Quelle |
|---|---|---|
| ✓ OK | Pydantic-Schemas | Alle POST/PUT/PATCH binden Body mit Field-Constraints, Validators, Patterns |
| ✓ OK | Keine String-interpolierten SQL | Nur 2 raw `text()` (Advisory-Lock, SET LOCAL), beide mit Named-Params |
| ✓ OK | ORM parameterisiert | Keine `db.execute(f"...")` mit User-Input |
| ✓ OK | XLS-Import File-Upload | 5 MB Limit **vor** Memory-Load, Tenant-Scoping (`import_xls.py:55-66, 91-97`) |
| ✓ OK | Profile-Picture-Upload | 500 KB Limit, Magic-Bytes-Check (nicht Content-Type) (`auth.py:484-497`) |
| ✓ OK | Request-Size-Limit | 2 MB ASGI-Middleware, Chunked-Transfer-tolerant (`static_serving.py:52-115`) |
| ⚠ LOW | Free-Text ohne `max_length` | `note`, `reason`, `proposed_note` etc. als `Column(Text)`+Pydantic ohne Limit → bis 2 MB pro Record möglich |
| ⚠ LOW | `hours: float` ohne ge/le | `vacation_request.py:11, 41` akzeptiert negative Werte |
| ⚠ **HIGH** | **E-Mail-HTML-Injection im Signup** | `mail_service.py:96-102`: `practice_name` (User-Input) und `verification_url` (Origin-Header) ungeschützt in HTML-Body |

**HIGH-1 Detail — Mail-Injection-Vektor:**

Im Klartext (Pseudo-Code-Schema, exakte Stelle in `mail_service.py:96-102`):

```
html_body = f"<html><body>"
            f"Willkommen bei <strong>{practice_name}</strong>!<br>"
            f"Klicken Sie hier: <a href='{verification_url}'>Bestaetigen</a>"
            f"</body></html>"
```

Bösartiger Signup mit `practice_name = '"><script>...</script>'` injiziert beliebiges HTML/JS in die Verification-Mail. Empfänger ist zwar der Anmelder selbst (vor email-verify), aber **Spear-Phishing-Vektor**: Angreifer registriert mit beliebiger Empfänger-Mail, liefert Custom-HTML.

> **Fix:** `import html; html.escape(practice_name)` + `html.escape(verification_url)`. 3 Zeilen Diff. Nur in SaaS-Modus relevant — On-Prem unkritisch.

### 4. Sensitive Data & Secrets

| Status | Befund | Quelle |
|---|---|---|
| ✓ OK | SECRET_KEY-Persistenz | Native: `config/.secret-key` mit restriktiven Permissions; Docker: ENV + Weak-Indicator-Check |
| ✓ OK | Lizenz-Verifikation (Ed25519) | `license.py:115-149`; Avalonia-Mirror prüft `alg`-Header explizit gegen "EdDSA" (`LicenseValidator.cs:115-124`) |
| ✓ OK | Update-Manifest signiert | Ed25519 + Host-Allowlist verhindert Hijacking |
| ✓ OK | PII-Scrubbing in Error-Logs | UUIDs + E-Mails per Regex (`error_log_service.py:16-26`) |
| ✓ OK | DSGVO Art. 9 | `absences.py` Maskierung + `reports.py` Opt-In + Audit-Log |
| ✓ OK | `.env` nicht im Repo | `.gitignore` + Platzhalter in `.env.example` |
| ✓ OK | DB-Credentials | Native: zur Laufzeit `secrets.token_hex(32)`, in `config/.db-credentials` mit 0600/ACL |
| ⚠ LOW | `_WEAK_ADMIN_PASSWORDS` Liste sehr kurz | `main.py:37`: nur 4 Werte gelistet, schwache 12+-Zeichen rutschen durch |
| ✓ OK | Stripe-Webhook-Verification | `stripe.Webhook.construct_event` (`stripe_service.py:160-173`) |
| ⚠ LOW | Stripe-Event-Payload-Excerpt mit PII | `stripe_service.py:197`: 4000 Zeichen inkl. Customer-Mail/Adresse ohne Scrubbing |
| ✓ OK | DB-User-Trennung | `praxiszeit_app` (RLS) für Runtime, `praxiszeit` (Superuser) nur für Migrations |

### 5. Frontend-Security

| Status | Befund |
|---|---|
| ✓ OK | Kein unsicheres React-HTML-Injection-Property (0 Treffer im Repo) |
| ✓ OK | URL-Sanitization (`ErrorMonitoring.tsx:37-47`) |
| ✓ OK | Access-Token nur in Module-Memory (`client.ts:7`) |
| ✓ OK | CSRF-Header-Mirror (`client.ts:42-54`) |
| ✓ OK | Service-Worker-Caches gelöscht bei Logout (`authStore.ts:87-93`) |
| ✓ OK | Content-Security-Policy konsistent zwischen nginx + native FastAPI |
| ✓ OK | Security-Headers (XFO, XCTO, Referrer, HSTS conditional) |
| ✓ OK | HSTS nur wenn HTTPS (F-050) — kein Brick-Risiko bei HTTP-Native-Install |
| ✓ OK | Grafana auf private Netze beschränkt (`nginx.conf:53-72`) |

### 6. Funktions-Korrektheit (Kern-Workflows)

| Status | Befund | Quelle |
|---|---|---|
| ✓ OK | `clock_in`/`clock_out` Race | `_get_open_entry(db, user_id, with_lock=True)` mit `with_for_update()` |
| ✓ OK | Stale-Entry Auto-Close in same TX | F-043: kein intermediate commit (`time_entries.py:217-221`) |
| ✓ OK | Pausen-Validierung | `break_validation_service.validate_daily_break` mit `exclude_entry_id` |
| ✓ OK | §5 Echtzeit-Ruhezeitwarnung | `time_entries.py:248-269` mit DST-safe TZ |
| ✓ OK | **VR-Edit Authorization** (NEU) | MA: Tenant + Owner + PENDING-Gate (`vacation_requests.py:243-260`); Admin: Tenant + 404-Mask (`admin_vacations.py:263-278`) |
| ✓ OK | **VR-Edit Mass-Assignment-Schutz** | `VacationRequestUpdate` nur 5 editierbare Felder, kein `status`/`tenant_id`/`user_id` |
| ✓ OK | **VR-Edit Race** | `with_for_update()` (`vacation_requests.py:251`, `admin_vacations.py:269`) |
| ✓ OK | **VR-Edit Audit-Logs** | `_format_vacation_request_audit_text` + `source="vacation_request_edit"` |
| ✓ OK | CR-Approval Race | F-028: `with_for_update()` auf CR-Row, Precondition-VOR-Status |
| ✓ OK | CR-Approval Bulk-Atomicity | Per-item Rollback (`admin_change_requests.py:438-448`) |
| ⚠ LOW | **Withdraw VR/CR ohne `with_for_update`** | `vacation_requests.py:381`, `change_requests.py:340` — Doppelklick → 404, funktional unschädlich aber inkonsistent |
| ✓ OK | Vacation-Refund bei Sick | Audit-Log VOR Delete |
| ✓ OK | `net_hours` Floor | `max(0.0, ...)` (`time_entries.py:32-33`) |
| ✓ OK | Export Multi-Entry pro Tag | korrekt |
| ✓ OK | Überstundenausgleich | Soll bleibt, Ist=0h (CLAUDE.md-Regel eingehalten) |

### 7. Native-Installer-Spezifisch

| Status | Befund |
|---|---|
| ✓ OK | `setup.bat` PG-Installer-Passwort: 32 Zufalls-Zeichen pro Install, nach Init verworfen |
| ✓ OK | `setup.bat` Admin-Check (`net session`) |
| ✓ OK | `setup.bat` PG-Reuse via Junction; `rd /s /q` folgt nicht → Uninstaller sicher |
| ✓ OK | `setup.bat` keine Befehlsinjection (System-Variablen, kein User-Input) |
| ✓ OK | File-Permissions auf Credentials: Windows `icacls /inheritance:r` + Owner+SYSTEM+S-1-5-32-544 (F-037 locale-independent) |
| ✓ OK | SECRET_KEY: `secrets.token_hex(32)` = 256-bit |
| ✓ OK | DB-Passwort: `secrets.token_hex(32)` (Superuser + App-User) |
| ✓ OK | `_validate_pg_identifier` (Whitelist), `_escape_pg_password` (Quote-Doppelung) |
| ✓ OK | `restore-backup.template.bat` fordert "LOESCHEN"-Bestätigung |
| ⚠ LOW | `restore-backup.bat` Path-Validation: `r'%BACKUP_GZ%'` raw-string schützt `\` aber nicht `'` |
| ✓ OK | Update-Wizard PS1: kein `iex`/`Invoke-Expression` |
| ✓ OK | Update-Manifest Signaturprüfung auch im Auto-Update-Pfad |
| – | Avalonia-Setup: Tests grün (20 Cases), Mirror der Backend-Lizenz-Verifikation inkl. `alg`-Whitelist |

### 8. Test-Coverage Gap-Analyse

| Bereich | Status |
|---|---|
| Backend pytest | ~530 Test-Funktionen |
| Backend cross-tenant API | 12 Cases |
| Backend RLS-Integration | 13 Cases (echtes Postgres) |
| Backend Concurrency | 4+ Cases mit `with_for_update` |
| E2E Playwright | 22 Specs / 116 Cases |
| Frontend Vitest | vorhanden |

**Test-Lücken:**

| Lücke | Severity |
|---|---|
| Withdraw-Race (VR/CR DELETE ohne `with_for_update`) | LOW |
| Stripe-Webhook Signature-Replay (Idempotenz getestet, Tampering nicht explizit) | LOW |
| Mail-Service HTML-Escape (bei HIGH-1-Fix mit-testen) | MEDIUM |
| License-Public-Key-Rotation (Backend+Avalonia-Synchronisation) | LOW |
| Native `restore-backup.bat` (nur manueller Pfad) | LOW |

**MEDIUM CI-Lücke** — `.github/workflows/cross-tenant-ci.yml` ist die einzige CI. Sie deckt nur Backend (Unit + RLS) ab. NICHT in CI:
- E2E Playwright (Commit `5e03cdf` erwähnt playwright-CI-Bump, aber Workflow existiert nicht!)
- Frontend tsc / eslint / vitest
- Frontend vite build (Bundle-Größen-Check)
- Docker Compose Build
- Secret-Scanning (TruffleHog, gitleaks)
- Dependency-Vulnerability-Scan (pip-audit, npm audit)

Existiert nur in `scripts/local-ci.sh`. **Fix:** Workflows aus `local-ci.sh` portieren.

---

## TEIL 3 — Priorisierte Action-Items (konsolidiert)

### CRITICAL (Release-Blocker)
*(keine)*

### HIGH (vor nächstem Kunden-Deployment)

**HIGH-1 — HTML-Injection im Signup-Mail-Body**
- **Datei:** `backend/app/services/mail_service.py:96-102`
- **Risiko:** Spear-Phishing-Vektor in SaaS-Modus; Angreifer registriert mit Custom-`practice_name`, beliebige Empfänger-Mail, eingebettetes HTML/JS
- **Fix:** `import html; html.escape(practice_name)` + `html.escape(verification_url)` (3 Zeilen Diff)
- **Test:** Unit-Test mit `practice_name = '<script>alert(1)</script>'`, prüfen dass `&lt;script&gt;` im Output

### MEDIUM (vor nächstem Quartal / vor SaaS-Phase 4)

**MEDIUM-1 — F-026 belt-and-suspenders Inkonsistenz**
- **Dateien:** 10+ Stellen (siehe Tabelle in Teil 2 §2)
- **Risiko:** RLS schützt aktuell, aber Single-Point-of-Failure bei RLS-Bug; CLAUDE.md-Pattern verletzt
- **Fix:** Helper `_get_entry_in_tenant`, `_get_cr_in_tenant`, `_get_vr_in_tenant`, `_get_absence_in_tenant` analog `admin_users._get_user_in_tenant` einführen

**MEDIUM-2 — Fehlende RLS auf `stripe_events`**
- **Datei:** `backend/alembic/versions/2026_04_24_1600-035_stripe_events.py:23-35`
- **Risiko:** CLAUDE.md-Pflichtregel verletzt; aktuell nur Superadmin-Context-Schreiber, aber Defense-in-Depth fehlt
- **Fix:** Neue Migration 038 mit `ENABLE ROW LEVEL SECURITY` + Policy, analog 033/034

**MEDIUM-3 — Signup-Passwort-Komplexität-Discrepanz**
- **Datei:** `backend/app/schemas/signup.py:13` vs. `backend/app/schemas/user.py:10-20`
- **Risiko:** Self-Service-Trial-Admins können schwächere Passwörter setzen als per Admin-API
- **Fix:** `_validate_password_complexity` auch in `SignupRequest.admin_password`-Validator anwenden

**MEDIUM-4 — CI deckt nur Backend ab**
- **Datei:** `.github/workflows/cross-tenant-ci.yml` (einzige Workflow)
- **Risiko:** Recent commit erwähnt playwright-CI, die nicht existiert; regressions slip in
- **Fix:** Workflows aus `scripts/local-ci.sh` portieren (frontend-lint, vitest, build, e2e mit Postgres-Service)

**MEDIUM-5 bis 7 — PublicHoliday + rest_time_service Multi-Tenant** *(ArbZG-Bereich, siehe B-6-01 und F-2)*
- 4 Dateien × 7 PublicHoliday-Stellen + 1× `rest_time_service.py:116`
- **Risiko:** Vor SaaS-Phase 4 unkritisch (RLS schützt im aktuellen On-Prem-Betrieb), danach Pflicht
- **Fix:** Optionalen `tenant_id`-Parameter in Calculation-/Rest-Time-Service-Signaturen ergänzen

### LOW (Backlog / Tech-Debt)

**LOW-1 — Brute-Force-Tracker per-worker** — OrderedDict im Module-Scope; bei N Gunicorn-Workern effektiver Lockout N×5/15min. **Fix:** Redis-backed slowapi.

**LOW-2 — Stripe-Event-Payload-Excerpt mit PII** — 4000 Zeichen inkl. Kunden-Mail/Adresse. **Fix:** Excerpt auf nicht-PII-Felder reduzieren oder via `_scrub_pii` jagen.

**LOW-3 — Free-Text ohne max_length** — `note`/`reason`/`proposed_note` bis 2 MB pro Record. **Fix:** `Field(..., max_length=2000)` auf alle freien Text-Felder.

**LOW-4 — `hours: float` ohne ge/le in VR-Schemas** — `vacation_request.py:11, 41`. **Fix:** `Field(..., ge=0, le=24)` analog absence.

**LOW-5 — Withdraw VR/CR ohne `with_for_update`** — `vacation_requests.py:381`, `change_requests.py:340`. **Fix:** `.with_for_update()` analog Edit/Approve.

**LOW-6 — `restore-backup.bat` Quote-Injection** — `installer/windows/restore-backup.template.bat:95` raw-string-Path. **Fix:** Pfad via `sys.argv` statt String-Interpolation.

**LOW-7 — Error-Logs nicht tenant-scoped** — `error_log_service.py:96-101` & `routers/error_logs.py:67-76` listen alle Errors deployment-weit. **Fix:** Im SaaS-Modus auf `tenant_id == current_user.tenant_id` filtern.

**LOW-8 — Passwort-Komplexität ohne Sonderzeichen** — `schemas/user.py:14-19`. NIST/BSI-konform, aber Audit-Erwartung. **Fix:** Optional 4. Constraint oder Begründung in `docs/SECURITY.md`.

**LOW-9 — Vacation-Request-Create Audit-Log fehlt** — `vacation_requests.py`. **Fix:** `TimeEntryAuditLog` mit `action="create"`, `source="vacation_request"` bei POST.

**LOW-10 — 24-Wochen-Report `net_hours`-Berechnung** — `reports.py:735` nutzt `e.net_hours or 0`. **Fix:** direkt `_net_hours(e.start_time, e.end_time, e.break_minutes)`.

---

## Verbesserungen seit 08.04.2026

| Finding vom 08.04. | Status heute |
|---|---|
| HIGH: passlib unmaintained + bcrypt 5 broken | ✓ Gefixt: F-041 bcrypt_sha256 in-house Implementation, wire-kompatibel |
| HIGH: Access-Token in localStorage (XSS-Diebstahl) | ✓ Gefixt: F-023 Module-Memory only, Refresh via HttpOnly-Cookie |
| HIGH: User-Enumeration via Login-Timing | ✓ Gefixt: F-040 Dummy-bcrypt-Verify bei unknown user |
| HIGH: Brute-Force ohne Lockout | ✓ Gefixt: F-039 5/15min Lockout mit OrderedDict-LRU |
| MEDIUM: Multi-Tenant App-Layer-Filter inkonsistent | ⚠ Teilweise: User-Lookups via `_get_user_in_tenant` konsolidiert, aber Entry/CR/Absence/VR-Lookups noch offen (MEDIUM-1) |
| MEDIUM: CR-Approval Race | ✓ Gefixt: F-028 `with_for_update()` + Precondition-VOR-Status |
| MEDIUM: clock_in/out Race | ✓ Gefixt: VULN-009 |
| MEDIUM: Token-Version nicht bei Rolle-Change | ✓ Gefixt: VULN-010 |
| MEDIUM: Traceback-Größen-DoS | ✓ Gefixt: VULN-012 2000-char Cap |
| MEDIUM: Grafana ohne IP-Allowlist | ✓ Gefixt: VULN-008 (nginx-side) |

**Bilanz:** 4/4 HIGH-Findings vom 08.04. behoben. 5/6 MEDIUM behoben. Eine offene MEDIUM (App-Layer-Filter) ist nun MEDIUM-1 und um konkrete Datei:Zeile-Liste angereichert.

---

## Anhang A — Geprüfte Dateien

### Backend
- `app/main.py`, `app/database.py`, `app/config.py`
- `app/middleware/{auth,csrf,license,static_serving}.py`
- `app/routers/{auth,time_entries,absences,vacation_requests,change_requests,admin_users,admin_change_requests,admin_vacations,admin_settings,admin_updates,import_xls,reports,journal,billing,public_signup,superadmin,error_logs}.py`
- `app/services/{auth_service,mail_service,signup_service,stripe_service,xls_import_service,error_log_service,break_validation_service,arbzg_utils,holiday_service,rest_time_service,calculation_service}.py`
- `app/core/{license,updater}.py`
- `app/schemas/{user,vacation_request,signup,absence,change_request,time_entry}.py`
- `alembic/versions/2026_03_25_2000-027_*.py`, `2026_04_24_*-{033,034,035,036}_*.py`

### Frontend
- `src/api/client.ts`, `src/stores/authStore.ts`
- `src/pages/admin/ErrorMonitoring.tsx`
- `src/components/{StampWidget,ChangeRequestForm}.tsx`
- `src/pages/TimeTracking.tsx`
- `src/utils/arbzgWarnings.ts`
- `nginx.conf`

### Installer / Native
- `installer/windows/{setup.bat,restore-backup.template.bat,update-wizard.bat}`
- `installer/setup/src/PraxisZeit.Setup.Core/Services/{LicenseValidator,PraxisZeitConfigWriter,ScriptRunner}.cs`
- `praxiszeit-server.py`

### CI / Doku
- `.github/workflows/cross-tenant-ci.yml`
- `scripts/local-ci.sh`
- `docs/superpowers/reports/2026-05-06-vacation-request-edit-review.md`

---

## Anhang B — Audit-Methodik

- **Statische Code-Analyse** mit `grep`, AST-Walks und gezielten File-Reads
- **Schema-Inspektion** der Alembic-Migrationen für RLS-Coverage
- **Endpoint-Mapping** aller schreibenden Routen gegen ArbZG-Paragraphen
- **Cross-Referenzen** zur Memory (`/home/manuel/.claude/.../project_review-2026-04-08.md`) für Delta-Vergleich
- **Verifikation existierender Test-Coverage** über `pytest --collect-only`-Annahmen
- **Severity-Klassifikation** nach OWASP-Schema (CRITICAL=Datenleck/Account-Takeover · HIGH=Compliance-Bruch oder Spear-Phishing-Vektor · MEDIUM=Defense-in-Depth · LOW=Tech-Debt)

**Hinweis:** Dieser Bericht ist eine technische Code-Analyse ohne Rechtsverbindlichkeit. Bei branchenspezifischen Tarifverträgen (TV-MFA, TV-Ärzte) oder Betriebsvereinbarungen kann die ArbZG-Bewertung einzelner Punkte abweichen. Für verbindliche Rechtsfragen ist die Konsultation eines Fachanwalts für Arbeitsrecht empfohlen.

---

*PraxisZeit Voll-Audit · v1.4.3 · Erstellt am 23. Mai 2026 · Auditor: Claude Opus 4.7 (1M-Kontext) mit ArbZG-Compliance-Sub-Agent (Sonnet 4.6)*
