# SaaS Phase 3/4: Public Signup, Billing/Stripe & Tenant-Lifecycle

**Status:** Done (implementiert)
**Datum:** 2026-06-28
**Scope:** Phase 3 (Self-Service-Signup + E-Mail-Verifikation), Phase 4 (Billing/Stripe),
mit Phase 6 (Tenant-Lifecycle: Suspend / Löschung / Anonymisierung)
**Meta-Issue:** [#100](https://github.com/phash/praxiszeit/issues/100) (8-Phasen-SaaS-Umbau)
**Zugehörige Issues:** #94 (Signup), #95 (Billing), #97 (Lifecycle), #129 (Webhook-PII)
**Vorgänger:** `2026-03-25-multi-tenant-phase-1-3-design.md` (DB + Middleware + RLS;
schob Signup/Billing „auf später" — diese Spec dokumentiert die Umsetzung)

---

## Überblick

Die Multi-Tenant-Phasen 1–3 (Tenants-Tabelle, JWT-`tid`, RLS) schufen das
Fundament; Signup, Billing und Lifecycle blieben im Ursprungsdesign offen. Diese
Spec dokumentiert das **tatsächlich implementierte** Verhalten:

- **Self-Service-Signup** mit doppelter Opt-in-E-Mail-Verifikation (enumeration-safe).
- **14-tägige Trial**, danach **Stripe-Abo** (Checkout + Customer-Portal + Webhooks).
- **Tenant-Lifecycle**: geplante Suspendierung, Löschanfrage mit Karenz und
  DSGVO-konforme Anonymisierung über tägliche Scheduler-Jobs.

Das gesamte SaaS-Verhalten ist hinter `DEPLOYMENT_MODE` gegated: **On-Prem**
(Default) verhält sich unverändert single-tenant; **SaaS** schaltet Signup +
Trial-/Cancel-Scheduler frei.

**Verifiziert gegen:** `backend/app/core/deployment.py`,
`backend/app/routers/public_signup.py`, `backend/app/services/signup_service.py`,
`backend/app/routers/billing.py`, `backend/app/routers/tenant_billing.py`,
`backend/app/services/stripe_service.py`, `backend/app/services/lifecycle_service.py`,
`backend/app/services/scheduler_service.py`, `backend/app/models/tenant.py`.

---

## 0. Deployment-Mode-Gating

`backend/app/core/deployment.py`:

```python
def is_saas()   -> bool:  return settings.DEPLOYMENT_MODE == "saas"
def is_onprem() -> bool:  return settings.DEPLOYMENT_MODE == "onprem"
```

`DEPLOYMENT_MODE` (Default `"onprem"`) in `config.py`.

| Bereich | onprem | saas |
|---|---|---|
| `/api/public/signup`, `/api/verify-email`, `/api/public/resend-verification` | **404** (`_saas_only`) | aktiv |
| Startup-Bootstrap (Default-Tenant + Admin + Holidays) | läuft | **läuft nicht** (Tenants via Signup) |
| Scheduler-Jobs `suspend_expired_trials` + `suspend_canceled_after_grace` | **nicht registriert** | registriert |
| Billing-/Lifecycle-Endpoints | technisch aktiv (Billing → 503 ohne Stripe-Key) | aktiv |

> Default-Tenant-UUID `00000000-0000-0000-0000-000000000001` (onprem,
> `plan="enterprise"`, `subscription_status="active"`).

---

## 1. Phase 3 — Public Signup + E-Mail-Verifikation

### Endpunkte (`public_signup.py`, alle mit `Depends(_saas_only)`)

| Methode | Pfad | Rate-Limit | Auth | Beschreibung |
|---|---|---|---|---|
| `POST` | `/api/public/signup` | `5/hour` | — | Praxis + Admin anlegen, Verifikations-Mail senden |
| `GET` | `/api/verify-email?token=…` | `10/minute` | — | E-Mail bestätigen, Admin aktivieren |
| `POST` | `/api/public/resend-verification` | `3/hour` | — | Verifikations-Mail erneut anfordern |

### Signup-Ablauf (`signup_service.create_signup`)

`SignupRequest`: `practice_name`, `admin_email`, `admin_first_name`,
`admin_last_name`, `admin_password` (8–128, volle Stärkeprüfung erst beim Login),
`accept_terms` (=True Pflicht), `accept_privacy` (=True Pflicht), `country`
(ISO-3166-1 alpha-2).

Bei freier E-Mail wird angelegt:
- **Tenant**: `is_active=True`, `plan="trial"`, `subscription_status="active"`,
  `trial_ends_at = now + 14 Tage` (`TRIAL_LENGTH_DAYS = 14`), Slug deterministisch
  aus dem Praxisnamen (Kollisions-Suffix).
- **Admin-User**: `role=ADMIN`, **`is_active=False`** (erst nach Verifikation aktiv).
- **SignupToken**: gespeichert wird **nur** `token_hash = SHA256(secrets.token_urlsafe(32))`
  (Rohtoken nie persistiert), `expires_at = now + 24 h` (`VERIFY_TOKEN_TTL_HOURS = 24`),
  `consumed_at = NULL`.
- **SignupAuditLog** (`event="signup_requested"`): `ip_address`, `user_agent`,
  `accepted_terms`, `accepted_privacy` (DSGVO-Art.-7-Einwilligungsnachweis).
- Verifikations-Mail mit Roh-Token in der URL.

### Enumeration-Sicherheit (M-API5)

Gehört die E-Mail bereits einem **aktiven Admin** (`_email_already_admin`), ist die
Antwort **ununterscheidbar** von einer frischen Registrierung: gleicher Status
**201**, gleiches `SignupResponse`-Schema, `tenant_id` = **zufällige** UUID (nicht
der echte Tenant), kein angelegter Datensatz. Der echte Inhaber bekommt eine
Out-of-Band-„Konto existiert bereits"-Mail; der Vorgang wird als
`signup_rejected_email_exists` protokolliert. `resend-verification` antwortet
**immer 202**, unabhängig davon, ob die E-Mail existiert.

### Verifikation (`GET /api/verify-email`)

Token wird gehasht und nachgeschlagen. **410 Gone** bei: nicht gefunden / bereits
konsumiert (`consumed_at != NULL`) / abgelaufen / User existiert nicht. Bei
Erfolg: `user.is_active = True`, `token.consumed_at = now`, Audit
`event="email_verified"`, Rückgabe des echten `tenant_id`.

### Sicherheit der Verifikations-URL (S-M01)

Die Verifikations-URL wird aus `settings.SAAS_APP_URL` (betreiberkontrolliert)
gebaut — **nie** aus dem `Host`/`Origin`-Header des Requests (kein
Domain-Injection ins Bestätigungs-Mail).

---

## 2. Phase 4 — Billing / Stripe

Stripe ist **optional**: ohne `STRIPE_SECRET_KEY` liefern die Billing-Endpoints
**503** („Zahlungsabwicklung nicht konfiguriert"). Konfig-Env-Vars:
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_{STARTER,PRO}_{MONTHLY,YEARLY}`,
`STRIPE_CANCEL_GRACE_DAYS` (Default 30).

### Endpunkte

| Methode | Pfad | Auth | Beschreibung |
|---|---|---|---|
| `POST` | `/api/billing/checkout` | Admin | Stripe-Checkout-Session-URL (`plan`, `yearly`, `success/cancel_url`); Session-`metadata={tenant_id, plan}` |
| `POST` | `/api/billing/portal` | Admin | Stripe-Customer-Portal-URL |
| `POST` | `/api/webhooks/stripe` | Stripe-signiert | Webhook-Verarbeitung (s. u.) |
| `GET` | `/api/tenant/billing` | Admin | voller Billing-Stand (read-only) |
| `PATCH` | `/api/tenant/billing` | Admin | nur Adress-Submenge ändern (s. u.) |
| `GET` | `/api/tenant/usage` | Admin | belegte vs. erlaubte Seats + Plan-Features |
| `GET` | `/api/tenant/invoices` | Admin | gecachte Stripe-Rechnungen |

### Billing-Felder am Tenant

`plan` (`trial`|`starter`|`pro`|`enterprise`), `subscription_status`
(`active`|`past_due`|`canceled`|`suspended`), `trial_ends_at`, `seat_limit`
(NULL = unbegrenzt), `stripe_customer_id`, `stripe_subscription_id`,
`billing_email`, `company_name`, `vat_id`, `country`, `billing_address` (JSONB,
`JSON().with_variant(JSONB,"postgresql")` für SQLite-Tests).

**`PATCH /api/tenant/billing` erlaubt nur**: `billing_email`, `company_name`,
`vat_id`, `country`, `billing_address`. **Nicht** änderbar (webhook-/superadmin-
owned): `plan`, `subscription_status`, `stripe_customer_id`, `stripe_subscription_id`,
`seat_limit`.

### Webhook (`POST /api/webhooks/stripe`)

1. **Signatur**: `stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)`;
   400 bei ungültiger Signatur/Payload.
2. **Idempotenz**: `StripeEvent`-Zeile mit unique `event_id` wird **vor** jeder
   Mutation eingefügt; Doppel-Zustellung trifft den Unique-Constraint → Kurzschluss.
3. **PII-Schutz (#129)**: nur ein **Whitelist-Auszug** des Payloads wird gespeichert
   (keine `customer_email`/Name/Adresse).

| Event | Tenant-Wirkung |
|---|---|
| `checkout.session.completed` | `stripe_subscription_id` setzen → `active`, Plan aus `metadata` |
| `customer.subscription.updated` | Plan aus Price-ID (`_plan_from_price_id`), Status `active`/`past_due`/`canceled` |
| `customer.subscription.deleted` | → `canceled` (startet Karenz) |
| `invoice.payment_succeeded` | `TenantInvoice` (paid); `past_due` → `active` |
| `invoice.payment_failed` | `TenantInvoice` (open); → `past_due` |

Tenant-Zuordnung: zuerst `metadata.tenant_id`, sonst über
`customer` ↔ `stripe_customer_id`. Auch ohne Treffer **200** (Event bleibt
persistiert).

### Seat-Limit

`tenant.seat_limit` (NULL = unbegrenzt, sonst per Plan-Default in
`plan_enforcement.py`); `active_seat_count` zählt `is_active=True`-User; neue
User-Anlage prüft das Limit (analog zur On-Prem-`check_employee_limit`).

---

## 3. Phase 6 — Tenant-Lifecycle (`lifecycle_service.py` + `tenant_billing.py`)

### Selbstbedienungs-Endpunkte (Admin)

| Methode | Pfad | Wirkung |
|---|---|---|
| `POST` | `/api/tenant/suspend` | Suspend in **7 Tagen** planen (`SUSPEND_GRACE_DAYS=7`), `scheduled_suspend_at/_by` |
| `POST` | `/api/tenant/cancel-suspend` | geplanten Suspend abbrechen |
| `POST` | `/api/tenant/request-deletion` | Löschung anfordern (`deletion_requested_at/_by`), Anonymisierung in **30 Tagen** (`DELETE_GRACE_DAYS=30`), Slack-Alert |
| `POST` | `/api/tenant/cancel-deletion` | Löschanfrage abbrechen |
| `POST` | `/api/tenant/transfer-ownership` | Billing-Eigentum auf anderen Tenant-Admin (`billing_email`) übertragen |
| `GET` | `/api/tenant/export` | DSGVO-Selbstexport (JSON: Tenant/User/Zeiten/Abwesenheiten/CRs/Audit) |
| `GET` | `/api/tenant/avv` | personalisierter AVV-PDF-Entwurf |

### Status-Wirkung

`suspended` schaltet den Tenant **read-only** (`LicenseReadOnlyMiddleware`).
`past_due`/`canceled` behalten Vollzugriff (Karenz). Suspend ist innerhalb der
7-Tage-Karenz per `cancel-suspend` reversibel.

### Anonymisierung (`anonymize_tenant`, DSGVO-konform)

- **User**: `username → deleted_<hex>`, `email → NULL`, Name → „Anonymisiert
  Benutzer", `password_hash → "!disabled:…"` (Login unmöglich), `is_active=False`.
- **Tenant**: `name → "[gelöscht]"`, Adress-/Billing-Felder → NULL, `is_active=False`,
  `subscription_status="canceled"`, `anonymized_at=now`; **Stripe-IDs bleiben**
  (Buchhaltungs-Audit).
- **SignupAuditLog**: `email → "[anon]"`, `ip_address`/`user_agent` → NULL,
  Einwilligungs-Flags bleiben.
- **Nicht gelöscht** (ArbZG §16 / Buchhaltung): `TimeEntry`, `Absence`,
  `ChangeRequest`, `TimeEntryAuditLog`, `TenantInvoice`.

---

## 4. Scheduler-Jobs (`scheduler_service.py`)

APScheduler (`BackgroundScheduler`, `timezone="Europe/Berlin"`), gestartet in
`main.py`; **deaktiviert im pytest-Modus** (`PYTEST_CURRENT_TEST`). Tägliche Jobs
laufen **03:00** (Backup-Poll stündlich :30). Jeder Job öffnet eigene
`SessionLocal()` mit `set_superadmin_context()` (Cross-Tenant).

| Job | Lauf | Gating | Wirkung |
|---|---|---|---|
| `vacation_audit_purge` | 03:00 | immer | Urlaubs-/Abwesenheits-Audit > **730 Tage** löschen (DSGVO Art. 5) |
| `apply_scheduled_suspends` | 03:00 | immer | `scheduled_suspend_at <= now` → `suspended` |
| `apply_scheduled_deletions` | 03:00 | immer | `deletion_requested_at <= now − 30 T` & `anonymized_at IS NULL` → `anonymize_tenant` |
| `cleanup_old_errors` | 03:00 | immer | erledigte `error_log` > 90 Tage |
| `scheduled_backup` | stündlich :30 | Docker | Backup zur Admin-Sollstunde + Pruning |
| `suspend_expired_trials` | 03:00 | **saas** | `plan="trial"` & `trial_ends_at < now` & kein Abo & `active` → `suspended` |
| `suspend_canceled_after_grace` | 03:00 | **saas** | `canceled` länger als `STRIPE_CANCEL_GRACE_DAYS` → `suspended` |

Die beiden SaaS-Jobs sind in `if is_saas():` gekapselt — ein On-Prem-Tenant kann
so nie vom Scheduler suspendiert werden.

---

## 5. Datenmodell (neu/erweitert)

- **`tenants`**: Billing-Felder (Abschnitt 2) + Lifecycle-Felder
  (`scheduled_suspend_at/_by`, `deletion_requested_at/_by`, `anonymized_at`).
- **`signup_tokens`**: `tenant_id`, `user_id`, `token_hash` (unique, SHA-256),
  `expires_at`, `consumed_at`.
- **`signup_audit_log`**: `tenant_id` (nullable für Einwilligungs-Aufbewahrung
  nach Löschung), `email`, `event`, `ip_address`, `user_agent`, `accepted_terms`,
  `accepted_privacy`.
- **`stripe_events`**: `event_id` (unique), `event_type`, `tenant_id`,
  `payload_excerpt` (PII-safe).
- **`tenant_invoices`**: `stripe_invoice_id` (unique), `amount_cents`, `currency`,
  `status`, `paid_at`, `period_start/end`, `hosted_invoice_url`.

---

## 6. Offene Punkte / YAGNI-Grenzen

- Plan/Price-Mapping ist **statisch** über Env-Vars (`_PLAN_PRICE_MAP`); keine
  dynamische Produktverwaltung (keine `stripe_products`-Tabelle).
- `seat_limit`-Defaults pro Plan leben in `plan_enforcement.py` (nicht in dieser
  Spec ausgearbeitet).
- Restliche Meta-Issue-#100-Phasen (z. B. Self-Service-Onboarding-Politur,
  SSO) sind hier nicht abgedeckt.
