# Incident-Response-Plan — PraxisZeit SaaS

Dieser Plan deckt sowohl technische Incidents (Ausfall, Performance, Bug mit
Datenverlust-Risiko) als auch **Datenschutzvorfälle** nach DSGVO Art. 33/34 ab.
**Meldefrist Art. 33:** 72 Stunden an die zuständige Aufsichtsbehörde.

## 0. Severity-Matrix

| Severity | Definition | Erstantwort |
|---|---|---|
| **P0** | Datenleck, Cross-Tenant-Sichtbarkeit, Auth-Bypass, kompromittierte Credentials | 15 min |
| **P1** | Totalausfall / nicht erreichbar / kein Login möglich | 30 min |
| **P2** | Core-Funktion kaputt (Stempeln, Export, Abrechnung), aber App erreichbar | 2 h |
| **P3** | Kosmetische Bugs, Einzelfall-Probleme | 1 Arbeitstag |

**P0 ist potenziell DSGVO-meldepflichtig — immer wie ein Data-Breach behandeln.**

## 1. Erkennung

- Slack-Alerts (`SLACK_WEBHOOK_URL`) für: past_due, signup, delete-request
- Grafana: 5xx-Rate > 1 %, API-Latency > 2s P95
- Kundenmeldung (E-Mail / Support)
- Externe (z.B. Security-Researcher, Responsible Disclosure)

## 2. Sofortmaßnahmen (erste 30 min)

1. **Bestätigen**: Ist der Vorfall reproduzierbar?
2. **Scope eingrenzen**: Welche Tenants sind betroffen? (Prometheus:
   `praxiszeit_tenant_api_requests_total` + Error-Logs)
3. **Eindämmen**:
   - Bei Cross-Tenant-Leak: betroffene Route temporär abdrehen
     (Feature-Flag / Deployment revert)
   - Bei Credential-Leak: `SECRET_KEY` rotieren → alle JWT-Sessions
     invalidiert (Nutzer müssen neu einloggen)
   - Bei Stripe-Webhook-Manipulation: `STRIPE_WEBHOOK_SECRET` rotieren
4. **Dokumentieren**: Incident-Ticket auf GitHub (label: `incident`)
   mit Timeline erstellen.

## 3. Untersuchung (erste 24 h)

- Root-Cause-Analyse: Git-History + Log-Korrelation
- Datenumfang: welche personenbezogenen Daten wurden potenziell
  exponiert? (Spalten, Zeitfenster, Anzahl Betroffener)
- Beweis-Sicherung: Error-Logs + DB-Snapshot einfrieren (keine
  Rotation bis Incident geschlossen)

## 4. DSGVO-Meldung (Art. 33)

**Binnen 72 Stunden** nach Bekanntwerden:

- An zuständige Aufsichtsbehörde (in DE meistens HBDI bzw. LDA je nach Bundesland):
  https://www.bfdi.bund.de/DE/Fachthemen/Datenpannen-melden/
- Mindestinhalt:
  - Art des Vorfalls, Kategorien und ungefähre Anzahl Betroffener
  - Name + Kontakt DPO
  - Wahrscheinliche Folgen
  - Getroffene / geplante Maßnahmen

**Bei hohem Risiko für Betroffene (Art. 34):** zusätzlich direkte
Benachrichtigung der betroffenen Personen.

## 5. Kommunikation mit Kunden

- E-Mail an alle betroffenen `billing_email`-Adressen
- Status-Page-Update
- Transparenter Timeline-Post nach Abschluss

## 6. Post-Mortem (binnen 7 Tagen)

- Blameless Post-Mortem mit Timeline, Wurzelursache, Fix, Präventions­maßnahmen
- Ablage in `docs/incidents/{date}-{slug}.md`
- Actions ins Backlog als GitHub Issues

## 7. Häufige Incident-Typen + Playbooks

### a) Cross-Tenant-Leak
1. Route in nginx lokal `return 503`
2. Fix deployen (siehe Phase 0 F-026 Pattern)
3. `set_superadmin_context` Logs prüfen
4. Alle Audit-Logs mit verdächtiger `tenant_id` rauskopieren

### b) Stripe-Webhook-Zustellungslücke
1. `/api/superadmin/tenants-overview` auf inkonsistente Status prüfen
2. Stripe-Dashboard → Events → fehlgeschlagene Events replayen
3. Ggf. manuelle State-Reconciliation

### c) DB-Totalausfall
1. Status-Page auf "Degraded" / "Outage"
2. `/api/health` zeigt `database: disconnected`
3. Restore ggf. aus letztem `pg_dump` → `docs/ops/RUNBOOK-tenant-restore.md`
4. Nach Restore: `alembic current` prüfen, fehlende Migrations nachziehen

### d) Credential-Leak
1. `SECRET_KEY` rotieren (alle Sessions invalidiert)
2. `ADMIN_PASSWORD` rotieren
3. `STRIPE_SECRET_KEY` und `STRIPE_WEBHOOK_SECRET` rotieren
4. `APP_DB_PASSWORD` rotieren (Compose-Restart erforderlich)
5. `.env` aus Git-History entfernen falls aus Versehen committed

## 8. Kontaktliste

- On-Call: Manuel Rödig ({{KONTAKT_E-MAIL}}, {{KONTAKT_TELEFON}})
- DPO: {{DPO_KONTAKT}}
- Hosting-Support: Hetzner Kundencenter
- Stripe-Support: support@stripe.com
- Aufsichtsbehörde: HBDI (Hessen) — https://datenschutz.hessen.de

---

*Dieser Plan wird jährlich (oder nach jedem P0-Incident) überprüft.*
