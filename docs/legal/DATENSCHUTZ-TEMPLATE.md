# Datenschutzerklärung — praxiszeit.de

> ⚠️ **ENTWURF — Juristische Prüfung erforderlich.** Text aufgrund der
> Haftungsrisiken nach DSGVO vor der Veröffentlichung anwaltlich prüfen
> lassen.

**Stand:** {{ENTWURF_DATUM}}

## 1. Verantwortlicher

Manuel Rödig · MR Development · Lindenallee 1 · 61118 Bad Vilbel ·
{{KONTAKT_E-MAIL}}

## 2. Rechtsgrundlagen

- Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung) — Signup, Login, Nutzung
- Art. 6 Abs. 1 lit. c DSGVO (rechtliche Verpflichtung) — ArbZG §16
  (2 Jahre Aufbewahrung)
- Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse) — Server-Logs,
  Missbrauchsabwehr, Monitoring
- Art. 6 Abs. 1 lit. a DSGVO (Einwilligung) — Newsletter,
  Marketing-Cookies

## 3. Erhobene Daten

### Bei Signup
- Praxis-Name, E-Mail, Vor-/Nachname, Passwort-Hash, Land
- IP-Adresse + User-Agent (für DSGVO-Consent-Nachweis)

### Während Nutzung
- Arbeitszeiten, Pausen, Urlaubs-/Krankheitsmeldungen der Mitarbeiter
- Profilbilder (optional)
- Session-Cookies (Refresh-Token, CSRF-Token)

### Technisch
- Server-Log: IP, Request-Pfad, Status-Code (30 Tage)
- Prometheus-Metriken: tenant_id, Request-Rate, DAU
  (keine Personenbezug)

## 4. Empfänger

- **Hetzner Online GmbH** (Hosting, DE, AV-Vertrag)
- **Stripe Inc.** (Zahlung, EU-US Data Privacy Framework)
- **E-Mail-Dienstleister** (transaktional, noch zu bestimmen)
- Keine Weitergabe an Dritte zu Werbezwecken.

## 5. Datenübermittlung in Drittländer

- Stripe verarbeitet in den USA unter dem EU-US Data Privacy Framework.
- Zusätzlich Standardvertragsklauseln (SCCs).

## 6. Speicherdauer

| Datenkategorie | Dauer |
|---|---|
| Account + Login | bis Kündigung + 30 Tage Grace |
| Arbeitszeitdaten (ArbZG) | 2 Jahre nach Ende Arbeitsverhältnis / Kündigung |
| DSGVO-Consent-Nachweis | 3 Jahre (Verjährung) |
| Server-Logs | 30 Tage |
| Stripe-Rechnungen | 10 Jahre (§147 AO) |

## 7. Rechte der Betroffenen

- Auskunft (Art. 15)
- Berichtigung (Art. 16)
- Löschung (Art. 17) — via `/api/tenant/request-deletion` (30d Grace)
- Einschränkung (Art. 18)
- Datenportabilität (Art. 20) — via `/api/tenant/export`
- Widerspruch (Art. 21)
- Beschwerde bei der zuständigen Aufsichtsbehörde (z. B. HBDI)

## 8. Cookies

- `access_token` (HttpOnly, Memory) — Session, Pflicht
- `refresh_token` (HttpOnly, Secure) — Session-Refresh, Pflicht
- `csrf_token` (Secure, nicht HttpOnly) — CSRF-Schutz, Pflicht
- Keine Tracking-Cookies.

## 9. Automatisierte Entscheidungsfindung

Es finden **keine** automatisierten Entscheidungen im Sinne von
Art. 22 DSGVO statt.

## 10. Kontakt / Datenschutzbeauftragter

{{DPO_KONTAKT}} — noch zu benennen.

---

*Abschnitte zu Newsletter, Blog-Cookies, Social-Media-Buttons, Web-Analytics,
Cloudflare/CDN, Einwilligungs-Dialog und Formularen auf praxiszeit.de sind
in diesem Entwurf bewusst nicht enthalten — sie sind je nach endgültiger
Marketing-Site auszugestalten.*
