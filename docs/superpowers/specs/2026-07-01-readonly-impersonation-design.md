# Design: Read-only Impersonation „Login als…" (#370)

**Datum:** 2026-07-01
**Issue:** [#370](https://github.com/phash/praxiszeit/issues/370)
**Status:** freigegeben, Umsetzung offen

## Problem

Admins möchten das Frontend aus MA-Perspektive testen (individuelles Dashboard
bewerten, Featurewünsche, Debugging). Gewünscht: „Login als xy" aus der
Benutzerliste, Logout → „zurück zu Admin".

## Rechtlicher Rahmen (bestimmt das Design)

- **Einsicht** ist unkritisch: der Admin verarbeitet MA-Daten als Vertreter des
  Verantwortlichen ohnehin rechtmäßig (§ 26 BDSG / Art. 6 DSGVO). Die MA-Ansicht
  erweitert den Datenzugriff nicht.
- **Schreiben „als MA" ist die Gefahrenzone:** § 16 ArbZG (Beleg muss dem
  tatsächlichen Urheber zurechenbar sein) und Willenserklärungen des MA
  (Urlaubsantrag, Änderungsantrag, Pausen-/Krankmeldung) dürfen nicht im Namen
  des MA fabriziert werden (§ 164 BGB, Falschzurechnung).
- **Konsequenz:** Impersonation ist strikt **read-only**. Weil Schreiben hart
  blockiert ist, kann keine Aktion je fälschlich dem MA zugerechnet werden.
- **Rechenschaft (Art. 5 Abs. 2 DSGVO):** jede Session wird geloggt.
- **Ziel-Einschränkung (User-Entscheidung):** nur **Mitarbeiter** (role != ADMIN)
  im selben Tenant sind impersonierbar; keine Admin-über-Admin-Sicht, kein Superadmin.

## Token-Mechanik

Neuer Endpoint `POST /api/admin/users/{user_id}/impersonate` (`require_admin`).

**Ziel-Validierung:** existiert, `is_active`, gleicher Tenant, `role != ADMIN`,
nicht der Aufrufer selbst → sonst 404/400/403.

**Rückgabe:** ein **Impersonation-Access-Token** (Ablauf wie regulär, 30 min),
**KEIN Refresh-Token**. Claims:
- `sub` = MA-User-ID → RLS/Datenkontext = MA (genau das treibt die MA-Ansicht)
- `imp` = Admin-User-ID (echter Akteur)
- `imp_sid` = Impersonation-Session-ID (für Logging + End-Zuordnung)
- `role` = employee, `tid` = Tenant, `tv` = MA-token_version, `type` = "access"

Der Token wird in `auth_service.create_access_token(...)` um optionale
`imp`/`imp_sid`-Claims erweitert (rückwärtskompatibel, nur gesetzt wenn übergeben).

## Read-only-Durchsetzung

Neue `ImpersonationReadOnlyMiddleware` (spiegelt `LicenseReadOnlyMiddleware`,
`app/middleware/impersonation.py`):
- Dekodiert den Bearer-Token pro Request (lazy, wie `_check_saas_suspend`).
- Wenn `imp`-Claim vorhanden UND Methode ∈ {POST,PUT,PATCH,DELETE} UND Pfad nicht
  in der Whitelist → **403** mit klarer Meldung
  („Nur-Lese-Modus: In der Ansicht als Mitarbeiter sind keine Änderungen möglich.").
- **Whitelist (unter Impersonation erlaubt):** `POST /api/admin/impersonate/end`.
- Reihenfolge in `main.py`: neben `LicenseReadOnlyMiddleware` registrieren.

**Zusätzliche strukturelle Garantie:** die effektive Rolle ist `employee`, damit
schlägt `require_admin` auf allen Admin-Routen fehl → eine Impersonation-Session
kann keine Admin-Funktion erreichen (Defense in depth).

## get_current_user (middleware/auth.py)

- Nach dem Auflösen des Ziel-Users: wenn `imp`-Claim vorhanden →
  Impersonator laden (superadmin-Kontext), validieren (existiert, admin, gleicher
  Tenant, aktiv). Bei Ungültigkeit 401.
- `request.state.impersonator_id = imp`, `request.state.is_impersonating = True`
  (für Logging/Debug; die harte Read-only-Grenze zieht die Middleware).
- Gibt weiterhin den **Ziel-User** (MA) zurück.

## Logging: Tabelle `impersonation_sessions`

Neue Migration (nächste freie Revision), tenant-scoped, RLS-Policy + F-026-Filter.

Spalten:
- `id` UUID PK
- `tenant_id` UUID FK tenants NOT NULL
- `impersonator_id` UUID FK users(id) `ondelete=CASCADE` NOT NULL
- `target_id` UUID FK users(id) `ondelete=CASCADE` NOT NULL
- `started_at` timestamptz NOT NULL default now()
- `ended_at` timestamptz NULL

**Ablauf:**
- Beim Impersonate-Call: Row anlegen (started_at=now, ended_at=null), `id` in den
  Token (`imp_sid`).
- `POST /api/admin/impersonate/end` (nur `get_current_user`, prüft `imp`-Claim
  vorhanden): setzt `ended_at=now` für die `imp_sid`-Session. Idempotent.
- Sessions ohne explizites Ende bleiben `ended_at=null` (Token läuft nach 30 min
  ab) — akzeptabel.

**DSGVO/purge_user:** `ondelete=CASCADE` auf beiden User-FKs → `db.delete(user)`
räumt Sessions automatisch ab (kein ForeignKeyViolation auf Postgres). Test in
`test_dsgvo_purge`/`purge_user` ergänzen (SQLite-FK-off fängt es nicht).

## Frontend

### authStore.ts
- `impersonation` State: `{ active: bool, targetName: string, parentToken: string }`.
- `startImpersonation(userId, userName)`: `POST /admin/users/{id}/impersonate` →
  aktuellen Admin-Access-Token als `parentToken` parken, Impersonation-Token via
  `setAccessToken` aktiv setzen, `/me` + Stores neu laden, auf MA-Dashboard leiten.
- `stopImpersonation()`: `POST /admin/impersonate/end` (best-effort), `parentToken`
  wieder als Access-Token setzen, Impersonation-State leeren, State neu laden.
- `isImpersonating(): boolean`.

### client.ts (401-Interceptor)
- **Kritisch:** läuft der Impersonation-Token in ein 401, NICHT über den
  (Admin-)Refresh-Cookie refreshen (sonst bekäme die MA-Ansicht einen Admin-Token).
  Stattdessen bei `isImpersonating()` → `stopImpersonation()` (zurück zu Admin).
  Reiht sich in die bestehende Exclude-/Guard-Logik ein.

### Benutzerübersicht (pages/admin/Users.tsx)
- „Login als"-Button je **Mitarbeiter**-Zeile (nicht bei Admins). Ruft
  `startImpersonation`.

### Banner
- Persistenter Warnbanner (App-weit, z. B. in `Layout.tsx`): „Sie sehen PraxisZeit
  als **Name** (nur Lesen) — [Zurück zu Admin]".
- `isImpersonating()` blendet die prominenten Schreib-CTAs aus (v. a. Stempel-Button
  auf dem Dashboard) + zeigt Read-only-Hinweis. Die Middleware bleibt die harte
  Garantie; das Frontend-Gate ist UX.

## Tests

**Backend (pytest):**
- `impersonate`: nur Admin darf; Ziel muss MA sein (Admin-Ziel → 403, Self → 400,
  fremder Tenant → 404); Session-Row angelegt; Token trägt `imp`/`imp_sid`.
- Middleware: mit `imp`-Token wird POST/PUT/PATCH/DELETE 403; GET erlaubt;
  `/impersonate/end` erlaubt.
- `get_current_user`: Impersonator wird gesetzt; ungültiger Impersonator → 401.
- `end`: schließt Session (`ended_at` gesetzt), idempotent.
- `purge_user` mit vorhandenen Sessions (PG-Cascade, kein 500).

**Frontend (vitest):**
- Banner erscheint bei aktivem Impersonation-State; „Zurück zu Admin" restauriert
  Parent-Token.
- Read-only-Gate blendet Stempel-CTA aus.

## Nicht im Scope (YAGNI)

- Kein Schreibzugriff „als MA" (bewusst; siehe rechtlicher Rahmen). Falls je nötig:
  separater Marker `impersonated_by` im Audit (Akteur = Admin, nie MA) + Sperre der
  Selbst-Willenserklärungen — eigener Spec.
- Kein Impersonieren von Admins/Superadmin.
- Kein Feature-Flag (Standard-Admin-Funktion; read-only + geloggt).
