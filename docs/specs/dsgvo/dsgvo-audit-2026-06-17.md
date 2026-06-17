# DSGVO-Compliance-Audit – PraxisZeit

**System:** PraxisZeit – Elektronisches Zeiterfassungssystem für Arztpraxen (besondere Kategorien nach Art. 9 DSGVO)
**Stack:** React 18 + TypeScript / FastAPI (Python 3.12) + PostgreSQL 16, multi-tenant (RLS)
**Systemversion:** 1.8.10 (`backend/app/core/updater.py:39`)
**Prüfdatum:** 2026-06-17
**Prüfer:** Datenschutz-Audit (KI-gestützt, Claude Opus 4.8)
**Rechtsgrundlage:** DSGVO (EU) 2016/679; §16 ArbZG; §26 BDSG
**Branch/Stand:** `master` (bac703e)

---

## 1. Zusammenfassung (Executive Summary)

**Gesamturteil: KONFORM mit offenen Findings (überwiegend Niedrig/Info, ein Hoch).**

Die zentrale Art.-9-Schutzmaßnahme — die Maskierung sensibler Abwesenheitstypen in den
**Kollegen-Feeds** — ist korrekt und **in beiden Feeds identisch** umgesetzt. Die jüngste
Korrektur (`/team/upcoming` nutzt dieselbe `_MASKED_ABSENCE_TYPES`-Konstante wie `/calendar`)
ist im Code **bestätigt** vorhanden; ein Nur-SICK-Leak besteht **nicht** mehr.

Betroffenenrechte (Art. 15/16/17/20) sind vollständig und überdurchschnittlich sorgfältig
implementiert: vollständiger Self-Service-Export mit `art15_meta`-Pflichtangaben (a–h),
Anonymisierung + 14-Tage-Grace + 730-Tage-Purge-Frist, License-Read-Only-Allowlist für
DSGVO-Endpoints, IP-Scrubbing bei Tenant-Anonymisierung. Privacy by Default für
Gesundheitsdaten in Excel-/ODS-Exporten greift inklusive `health_export`-Audit.

Der einzige **Hoch**-Befund: das **TOTP-2FA-Secret wird im Klartext (Base32) in der DB
gespeichert** — bei einem DB-/Backup-Leak ist der zweite Faktor reproduzierbar. Daneben
mehrere **Mittel/Niedrig**-Punkte (Lese-Audit auf Fremd-SICK fehlt, nginx-Header-Vererbung
auf statischen Routes, Privacy-Seite mit hartkodierter On-Prem-Aussage im SaaS-Kontext,
Freitext-Felder ohne präzise Rechtsgrundlage).

### KPI

| Schweregrad | Anzahl (offen) |
|-------------|----------------|
| Kritisch    | 0 |
| Hoch        | 1 |
| Mittel      | 4 |
| Niedrig     | 4 |
| Info / Positiv | mehrere |

---

## 2. Art. 9 (besondere Kategorien) – Kernprüfung Kollegen-Feed-Maskierung

**Status: KONFORM (verifiziert am Code).**

| Feed | Maskierung greift? | Fundstelle |
|------|--------------------|------------|
| `/api/absences/calendar` | Ja, `_MASKED_ABSENCE_TYPES` | `backend/app/routers/absences.py:107-112` |
| `/api/absences/team/upcoming` | Ja, **dieselbe** `_MASKED_ABSENCE_TYPES` | `backend/app/routers/absences.py:168-173` |
| Konstante (Single Source) | `{SICK, OTHER, PAID_LEAVE}` | `backend/app/routers/absences.py:24` |

Beide Feeds maskieren bei `type ∈ {SICK, OTHER, PAID_LEAVE}` **und** Nicht-Admin **und**
Fremd-Eintrag auf den generischen Wert `"absent"`. Nicht-sensible Planungstypen (VACATION,
TRAINING, OVERTIME) bleiben wahrheitsgemäß sichtbar (Koordination). Der ausführliche
Code-Kommentar (`absences.py:17-23`, `:157-160`) dokumentiert die Begründung: ein
Nur-SICK-Masking wäre ein 1:1-Krankheits-Indikator. **Kein Leak.** Zusätzlich wird das
Abteilungsmerkmal (`department`) im Kalender nur an Admins ausgeliefert (`:116`,
Datenminimierung).

---

## 3. Befunde je Artikel

> Legende Severity: **Kritisch** / **Hoch** / **Mittel** / **Niedrig** / **Info**.
> Alle Hoch/Mittel-Befunde wurden direkt am Code verifiziert.

### Art. 5 / 25 – Grundsätze, Privacy by Design/Default

- **[Info – KONFORM]** Privacy by Default für Gesundheitsdaten in Exporten: `include_health_data: bool = False`
  Default; SICK → "Abwesenheit", `is_night_worker` maskiert.
  `backend/app/services/export_service.py:55,271-274,647-650`; Endpoint-Defaults `backend/app/routers/reports.py:42,230,282,322,362`.
- **[Info – KONFORM]** Speicherbegrenzung-Spannungsfeld §16 ArbZG vs. Art. 17 sauber aufgelöst über
  **Art. 17 Abs. 3 lit. b** (im `art15_meta`-Block dokumentiert): `backend/app/services/lifecycle_service.py:509-525`; DSFA `dsfa.md:85-86`.

### Art. 6 / 7 – Rechtsgrundlage & Einwilligung

- **[Info – KONFORM]** Signup-Consent-Audit (nur SaaS): IP/User-Agent/Zeitstempel + `accepted_terms`/`accepted_privacy`
  als Nachweis (Art. 7 Abs. 1), überlebt Tenant-Löschung bewusst (`tenant_id` nullable).
  `backend/app/models/signup_token.py:24-38`; Persistenz `backend/app/services/signup_service.py:159-167`; On-Prem→404 via `_saas_only()` `backend/app/routers/public_signup.py:29-32`.
- **[Info – KONFORM]** BETA_MODE deaktiviert nur die Lizenz-/Read-Only-Logik, **kein** DSGVO-Impact
  (RLS, Audit, Art.-9-Masking, Self-Export laufen unabhängig). `backend/app/config.py:145`; `backend/app/main.py:272-276`.
- **[Niedrig] F-A1 – Freitextfelder ohne präzise Rechtsgrundlage.** `User.department` (`backend/app/models/user.py:58`)
  ist über Art. 6 lit. f dokumentiert (im Beschäftigtenkontext rechtlich grenzwertig — sauberer §26 BDSG /
  Betriebsvereinbarung). `TimeEntry.note` (`backend/app/models/time_entry.py:26`) und `Absence.note`
  (`backend/app/models/absence.py:62`) sind Freitext und können ungewollt Art.-9-Inhalte aufnehmen
  („beim Arzt"). **`Absence.note` fehlt vollständig im Verarbeitungsverzeichnis.**
  *Empfehlung:* `Absence.note` ins VVT aufnehmen; Freitext bei Krank-Absencen einschränken/Hinweistext;
  `department`-Grundlage auf §26 BDSG umstellen.

### Art. 9 – besondere Kategorien (weitere)

- **[Mittel] F-A2 – Lese-Audit auf Fremd-SICK fehlt im Admin-Direktpfad.** Exporte/Reports auditieren
  Gesundheitsdaten-Lesezugriffe (`health_data_read`/`health_export`, `backend/app/routers/reports.py:65,140` + 7 Stellen).
  Aber die Admin-Lesepfade `GET /api/absences/?user_id=<MA>` (`backend/app/routers/absences.py:39-71`) und
  `get_absence_calendar` (`absences.py:74-127`, Admin sieht ab `:108-112` **unmaskiert**) liefern echte
  SICK-Einträge **ohne** jeden Audit-Eintrag. „Admin X hat Krankmeldungen von MA Z eingesehen" ist nicht
  rekonstruierbar (Art. 5 Abs. 2 / Art. 32 Abs. 1 lit. b Eingabe-/Zugriffskontrolle).
  *Empfehlung:* `health_data_read`-Audit ergänzen, wenn Fremd-SICK im Resultat enthalten ist.

### Art. 15 / 20 – Auskunft & Portabilität

- **[Info – KONFORM]** `GET /api/me/data-export`: vollständig (Stammdaten, Zeit, Abwesenheiten inkl. SICK,
  Vacation-/Change-Requests, Audit-Logs), `art15_meta`-Block mit allen Pflichtangaben Abs. 1 (a–h),
  rate-limited 5/Tag, schreibt `source=self_data_export`-Audit, Whitelist statt Blacklist (kein
  Secret-Leak von `password_hash`/`totp_secret`).
  Endpoint `backend/app/routers/me.py:41-91`; Builder `backend/app/services/lifecycle_service.py:375-483`; Meta `:486-554`.
- **[Niedrig] F-A3 – Legacy-Export redundant/unvollständig.** `GET /api/auth/me/export`
  (`backend/app/routers/auth.py:474-536`) ist gegenüber `/api/me/data-export` schlanker
  (ohne Requests/Audit-Logs), ohne eigenen Audit-Eintrag und ohne Rate-Limit.
  *Empfehlung:* als reinen Art.-20-Portabilitäts-Export dokumentieren oder deprecaten.

### Art. 16 – Berichtigung

- **[Info – KONFORM]** `PUT /api/auth/profile` (`backend/app/routers/auth.py:427-471`): Name/E-Mail
  selbst änderbar, E-Mail-Änderung audit-geloggt; von License-Read-Only ausgenommen (`backend/app/middleware/license.py:67`).

### Art. 17 – Löschung & Speicherbegrenzung

- **[Info – KONFORM]** Anonymisierung `POST /api/admin/users/{id}/anonymize` (`backend/app/routers/admin_users.py:202`):
  Name/Username/E-Mail/Profilbild/TOTP gescrubbt, Abwesenheiten gelöscht, Zeiteinträge bleiben (§16),
  Session-Invalidierung via `token_version++`, 14-Tage-Grace erzwungen (`:217-226`), Audit-Nachweis bleibt.
- **[Info – KONFORM]** Tenant-Lifecycle-Jobs (APScheduler 03:00, im pytest deaktiviert):
  Vacation-Audit-Purge 730 Tage, Tenant-Suspend (7-Tage-Grace), Tenant-Deletion → `anonymize_tenant`
  (30-Tage-Grace) mit **IP-Scrubbing** der Signup-Audit-Logs (`backend/app/services/lifecycle_service.py:234-237`);
  `backend/app/services/scheduler_service.py:135-216`; pytest-Guard `:139-167`.
- **[Mittel] F-A4 – Purge-Fristcheck ignoriert die längere AO-Frist für Urlaubsdaten.** Der 730-Tage-Check
  (`DELETE /api/admin/users/{id}/purge`, `backend/app/routers/admin_users.py:279-289`) stützt sich
  **ausschließlich** auf den letzten `TimeEntry`. Urlaubsdaten (laut VVT 3 Jahre, §147 AO) werden bei
  Purge mitgelöscht (`:322`) ohne eigene Fristprüfung → steuerrelevante Aufbewahrung kann unterlaufen werden.
  *Empfehlung:* Purge-Fristcheck zusätzlich gegen das jüngste relevante Urlaubsdatum (max. von TimeEntry/Absence-Vacation) führen.
- **[Niedrig] F-A5 – Purge ohne TimeEntry überspringt den 730-Tage-Check vollständig.**
  `backend/app/routers/admin_users.py:283` (if-Guard nur bei vorhandenem `last_entry`). Betrifft v.a. reine
  Nicht-Tracking-User (`track_hours=False`); formal vertretbar (keine §16-Daten), sollte aber bewusst sein.
- **[Niedrig] F-A6 – Grace-Period asymmetrisch.** `purge_user` prüft die 14-Tage-Grace nicht (nur `anonymize`);
  zudem Grace bei Legacy-`deactivated_at IS NULL` stillschweigend übersprungen.
  `backend/app/routers/admin_users.py:266-289`, `:227-232`.

### Art. 25 / 32 – Privacy by Design / Sicherheit

- **[Hoch] F-A7 – TOTP-2FA-Secret im Klartext at-rest.** `totp_secret = Column(String(64))`
  (`backend/app/models/user.py:59`), generiert als `pyotp.random_base32()`
  (`backend/app/services/auth_service.py:197`) und **unverschlüsselt** geschrieben
  (`backend/app/routers/auth.py:595`) / gelesen (`:237,626`). Keinerlei At-Rest-Krypto im Backend
  (`grep -E 'Fernet|encrypt|AES'` über `backend/app/` = 0 Treffer). Bei DB- oder Backup-Leak ist der
  zweite Faktor vollständig reproduzierbar → 2FA wertlos (Art. 32 Abs. 1 lit. a Verschlüsselung).
  Anmerkung: in Export/Anonymisierung wird das Feld korrekt unterdrückt/gescrubbt.
  *Empfehlung:* Secret mit App-Key (z.B. Fernet/`cryptography`) symmetrisch verschlüsseln, Schlüssel
  getrennt von der DB halten (analog `SECRET_KEY` in `config/.secret-key`). Bereits dokumentiert als TODO
  im Verarbeitungsverzeichnis (`verarbeitungsverzeichnis.md:50`).
- **[Mittel] F-A8 – Docker-nginx: Security-Header fehlen auf Sonder-Locations.** Die Server-weiten
  `add_header` (CSP/X-Frame/nosniff/Referrer/HSTS) in `frontend/nginx.conf:113-122` werden von
  nginx **nicht** in `location`-Blöcke vererbt, die einen eigenen `add_header` besitzen. Betroffen:
  `location = /index.html` (`:93-98`), `/assets/` (`:51-54`), `= /sw.js` (`:34-39`),
  `= /manifest.webmanifest` (`:42-48`), `= /help` (`:102-105`). **`index.html` ohne CSP/X-Frame**
  ist der relevanteste Treffer (Clickjacking-/CSP-Schutz genau dort wirkungslos). **Nur Docker**;
  Native-Modus ist immun (Middleware setzt Header explizit, `backend/app/middleware/static_serving.py:134-140`).
  Gilt analog für `ssl/nginx-ssl.conf`.
  *Empfehlung:* Security-Header in jeder dieser Locations wiederholen (oder via `include` snippet).
- **[Niedrig] F-A9 – RLS-Isolation rein app-layer-getragen (latent).** RLS ist solide gebaut
  (FORCE ROW LEVEL SECURITY + Non-Superuser-Rolle `praxiszeit_app` ohne BYPASSRLS,
  `backend/init-db-user.sql:11`, Policy in `027_add_multi_tenant.py:95-126`, Tests `test_tenant_rls.py`).
  Aber `app.is_superadmin` ist ein frei setzbarer Custom-GUC ohne DB-seitigen Guard
  (`backend/app/database.py:44`). Kein aktiv ausnutzbarer Bug (keine Roh-SQL-/SQLi-Fläche gefunden),
  app-seitig zusätzlich F-026-Filter; bekannter Tech-Debt (H3 aus Vorsessions).
- **[Niedrig] F-A10 – `POST /api/auth/change-password` nicht von License-Read-Only ausgenommen.**
  Im Read-Only/Suspend-Modus kann der Nutzer sein Passwort nicht selbst ändern (Konto-Sicherheit).
  `backend/app/middleware/license.py:62-68` (Allowlist) vs. `backend/app/routers/auth.py:357`.
  *Empfehlung:* zur DSGVO/Sicherheits-Allowlist hinzufügen.
- **[Info – KONFORM]** Passwort-Hashing `bcrypt_sha256` cost 12 (`backend/app/services/auth_service.py:31-59`);
  Refresh-Token als HttpOnly-Cookie; CSP `script-src 'self'` ohne `unsafe-eval`; varchar(40)-Audit-Limits
  ohne Überlauf (längster Marker 29 Zeichen); License-Read-Only-Allowlist für Art. 15/16/17/20 verifiziert.

### Art. 28 – Auftragsverarbeitung

- **[Niedrig] F-A11 – AVV-Generator juristisch unvollständig (Entwurf).** `backend/app/services/avv_generator.py:30`
  (Endpoint admin-only `backend/app/routers/tenant_billing.py:249-258`, reportlab, Injection-sicher).
  Art.-28-Abs.-3-Klauseln (b Vertraulichkeit, e/f Unterstützung, g Rückgabe/Löschung, h Audit) nur knapp/implizit;
  selbst als Entwurf gekennzeichnet. *Empfehlung:* juristische Vervollständigung vor produktivem Verkauf.

### Art. 13 – Informationspflicht (Frontend)

- **[Mittel] F-A12 – Datenschutzseite mit hartkodierter On-Prem-Aussage, im SaaS irreführend.**
  `frontend/src/pages/Privacy.tsx:160-162` behauptet „On-Premises … keine Übermittlung in Drittländer".
  Im SaaS-Modus (zentrales Hosting, Stripe-Billing) ist das **unzutreffend**; die `/privacy`-Route ist
  — anders als `/signup` — **nicht** deployment-mode-gated, und die SaaS-Signup-Checkbox verlinkt direkt
  darauf (`Signup.tsx:157,166`). Zusätzlich „Stand: Februar 2026" veraltet (`Privacy.tsx:22`).
  *Empfehlung:* Privacy-Inhalt deployment-mode-abhängig machen (SaaS: Auftragsverarbeiter/Stripe/Hosting,
  ggf. Drittland) und Stand aktualisieren. **Nur SaaS-relevant; im On-Prem-Betrieb korrekt.**

---

## 4. Verarbeitungsverzeichnis-Delta (Art. 30)

Gegenüber `verarbeitungsverzeichnis.md` (Stand 2026-06-06) ergeben sich aus diesem Audit folgende
**nachzutragende** Punkte (organisatorisch/redaktionell, kein Code-Block):

1. **`Absence.note` (Freitext an Abwesenheiten)** als eigene Datenkategorie ergänzen (Abschnitt 4.3).
   Risikohinweis: kann bei Krank-Absencen ungewollt Art.-9-Detail aufnehmen → Begrenzung/Hinweistext empfohlen (F-A1).
2. **`User.department`-Rechtsgrundlage** von Art. 6 lit. f auf §26 BDSG / Betriebsvereinbarung präzisieren (F-A1).
3. **Urlaubsdaten-Aufbewahrung (3 J / §147 AO)** vs. Purge-Mechanik: Purge berücksichtigt die AO-Frist
   derzeit nicht (F-A4) — Löschkonzept (Abschnitt 5) entsprechend klarstellen/korrigieren.
4. **TOM-Tabelle (Abschnitt 7) / DSFA-TOM (5):** „Pseudonymisierung/Verschlüsselung TOTP-Secret" von
   „TODO/ausstehend" auf den realen Stand (weiterhin offen, F-A7) konkretisieren; Ziel-Maßnahme nennen.
5. **Lese-Protokollierung Gesundheitsdaten:** TOM „Eingabekontrolle" um den offenen Punkt ergänzen, dass
   Admin-Direktlesepfade (`/absences` list/calendar) Fremd-SICK noch ohne `health_data_read`-Audit liefern (F-A2).

Die übrigen Tabellen (Stammdaten, Zeit, Krankheit/Art. 9, Nachtarbeiter, Signup-Consent, Aufbewahrungsfristen,
Empfänger, Betroffenenrechte) decken sich mit dem aktuellen Code und bleiben gültig.

---

## 5. Findings-Tabelle

| ID | Severity | Artikel | file:line | Kurzbeschreibung |
|----|----------|---------|-----------|------------------|
| F-A7 | **Hoch** | Art. 32 | `backend/app/models/user.py:59` (+ `routers/auth.py:595`) | TOTP-2FA-Secret im Klartext (Base32) at-rest, keine At-Rest-Krypto |
| F-A2 | Mittel | Art. 9 / 32 | `backend/app/routers/absences.py:39,74` | Admin-Lesepfade liefern Fremd-SICK ohne `health_data_read`-Audit |
| F-A4 | Mittel | Art. 17 / 5e | `backend/app/routers/admin_users.py:279-289` | Purge-Fristcheck nur auf TimeEntry; AO-Urlaubsfrist (3 J) ignoriert |
| F-A8 | Mittel | Art. 32 | `frontend/nginx.conf:51,93` (+ `ssl/nginx-ssl.conf`) | Docker-nginx: Security-Header fehlen auf index.html/assets/sw/help |
| F-A12 | Mittel | Art. 13 | `frontend/src/pages/Privacy.tsx:160-162,22` | On-Prem-Aussage im SaaS irreführend; /privacy nicht gated; Stand veraltet |
| F-A1 | Niedrig | Art. 6 / 30 | `models/user.py:58`, `models/absence.py:62`, `models/time_entry.py:26` | Freitextfelder ohne präzise Grundlage; `Absence.note` fehlt im VVT |
| F-A3 | Niedrig | Art. 20 | `backend/app/routers/auth.py:474-536` | Legacy-Export redundant/unvollständig, kein Audit/Rate-Limit |
| F-A6 | Niedrig | Art. 17 | `backend/app/routers/admin_users.py:266-289,227-232` | Grace-Period asymmetrisch (Purge ohne Grace; Legacy-NULL übersprungen) |
| F-A9 | Niedrig | Art. 32 | `backend/app/database.py:44` | RLS rein app-layer; `app.is_superadmin`-GUC ohne DB-Guard (latent) |
| F-A10 | Niedrig | Art. 12 / 32 | `backend/app/middleware/license.py:62`, `routers/auth.py:357` | `change-password` im Read-Only/Suspend blockiert |
| F-A5 | Niedrig | Art. 17 | `backend/app/routers/admin_users.py:283` | Purge ohne TimeEntry überspringt 730-Tage-Check ganz |
| F-A11 | Niedrig | Art. 28 | `backend/app/services/avv_generator.py:30` | AVV-Klauseln (b/e/f/g/h) juristisch unvollständig (Entwurf) |

**Positiv-Befunde (KONFORM):** Art.-9-Maskierung in beiden Kollegen-Feeds identisch; vollständiger
Art.-15-Self-Export mit (a–h)-Meta; Anonymisierung + Grace + Purge-Frist + IP-Scrubbing;
Privacy by Default + `health_export`-Audit in Excel/ODS; License-Read-Only-Allowlist für
Betroffenenrechte; Superadmin-§16-Export auf tenant-lose Superadmins beschränkt und protokolliert;
RLS mit FORCE + Non-Superuser-Rolle; bcrypt_sha256; varchar(40)-Audit ohne Überlauf;
Signup-Consent-Nachweis (Art. 7) mit On-Prem-404.

---

## 6. Gesamturteil

**KONFORM mit offenen Findings.** Keine kritischen, offenen Verstöße. Die für Arztpraxen
zentrale Art.-9-Schutzmaßnahme (Maskierung sensibler Abwesenheiten in beiden Kollegen-Feeds)
ist korrekt und der jüngste Fix bestätigt. Ein **Hoch**-Finding (TOTP-Secret-Klartext, F-A7)
sollte vor einem kostenpflichtigen Produktivbetrieb behoben werden; die vier **Mittel**-Findings
(Lese-Audit Art. 9, Purge-AO-Frist, nginx-Header, SaaS-Privacy-Seite) sind zeitnah anzugehen.
Die übrigen Punkte sind Niedrig/redaktionell. Organisatorische Maßnahmen (AVV mit
Hosting/Stripe/Steuerberater, Datenpannen-Reaktionsplan, Mitarbeiter-Information) liegen
weiterhin beim Verantwortlichen.

---

## 7. Priorisierte Maßnahmenliste

1. **(Hoch)** TOTP-Secret verschlüsseln (Fernet/`cryptography`, Key getrennt von DB) — F-A7.
2. **(Mittel)** `health_data_read`-Audit in `list_absences`/`get_absence_calendar` bei Fremd-SICK — F-A2.
3. **(Mittel)** Purge-Fristcheck um Urlaubs-/AO-Frist (3 J) erweitern — F-A4.
4. **(Mittel)** Docker-nginx Security-Header je Sonder-Location wiederholen (auch `ssl/nginx-ssl.conf`) — F-A8.
5. **(Mittel)** Privacy.tsx deployment-mode-abhängig (SaaS-Empfänger/Stripe) + Stand aktualisieren — F-A12.
6. **(Niedrig)** VVT-Delta (Abschnitt 4) einpflegen: `Absence.note`, `department`-Grundlage, Urlaubsfrist, TOTP-TOM, Lese-Audit-Hinweis.
7. **(Niedrig)** `change-password` zur License-Allowlist; Legacy-Export deprecaten; AVV-Klauseln vervollständigen.

---

*Erstellt durch KI-gestützten DSGVO-Audit (Claude Opus 4.8). Rechtsverbindliche Beurteilung durch
eine qualifizierte Datenschutzfachperson empfohlen. Lebende Begleitdokumente
(`verarbeitungsverzeichnis.md`, `dsfa.md`, `dsgvo-report.html`) sind nach Behebung der Findings
gemäß `HOWTO.md` Abschnitt 3 synchron nachzuziehen.*
