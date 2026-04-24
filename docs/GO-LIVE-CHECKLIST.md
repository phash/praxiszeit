# PraxisZeit SaaS — Go-Live Checkliste

Stand: 2026-04-24 · Teil der Phase-8-Roadmap ([#99](https://github.com/phash/praxiszeit/issues/99))

Diese Liste deckt **alles ab, was zwischen dem Ende der technischen SaaS-Phasen 1–7 und dem ersten zahlenden Kunden liegt**. Items mit "EXTERN" brauchen eine:n Anwält:in, Pen-Test-Anbieter, Notar oder Marketing-Dienstleister; alle anderen können intern erledigt werden.

> ⚠️ Die PraxisZeit-Plattform ist **erst dann SaaS-reif**, wenn alle mit ✅ markierten Punkte grün sind.

## 1. Rechtssicher

- [ ] **AGB** auf Basis von [`docs/legal/AGB-TEMPLATE.md`](legal/AGB-TEMPLATE.md) **EXTERN** durch Anwält:in prüfen & finalisieren
- [ ] **Datenschutzerklärung** auf Basis von [`docs/legal/DATENSCHUTZ-TEMPLATE.md`](legal/DATENSCHUTZ-TEMPLATE.md) **EXTERN** prüfen
- [ ] **Impressum** auf Basis von [`docs/legal/IMPRESSUM-TEMPLATE.md`](legal/IMPRESSUM-TEMPLATE.md) veröffentlichen (TMG §5)
- [ ] **AVV (§28 DSGVO)**: automatisch generiertes PDF via `/api/tenant/avv` **EXTERN** juristisch prüfen (Template in `app/services/avv_generator.py`)
- [ ] **SLA** definiert ([`docs/legal/SLA.md`](legal/SLA.md)); für `pro` + `enterprise` verbindlich, `starter` best-effort
- [ ] **Widerrufsbelehrung**: bei B2B i.d.R. nicht erforderlich, **EXTERN** prüfen
- [ ] **DPO** benannt (intern oder extern, Pflicht ab 20+ Personen in Kundenseitiger DV)

## 2. Sicher

- [ ] **Externer Pen-Test** **EXTERN** beauftragt (Fokus: Cross-Tenant-Leaks, Auth-Bypass, JWT-Manipulation, Stripe-Webhook-Manipulation, File-Upload)
- [ ] **Pen-Test-Findings**: P1/P2 = 0 vor Go-Live
- [ ] **Secret-Scanning** aktiv: pre-commit + `.github/workflows/secret-scan.yml`
- [ ] **Cross-Tenant-Tests im CI blocken**: siehe [`/.github/workflows/cross-tenant-ci.yml`](../.github/workflows/cross-tenant-ci.yml)
- [ ] **TLS**: Produktions-Cert (Let's Encrypt), HTTPS-Redirect, HSTS preload erwogen
- [ ] **Secrets**: `.env` nirgends committed (Git-History gecheckt, BFG ggf. angewendet)
- [ ] **Bcrypt-Cost** ≥ 12 (heute: siehe `auth_service.hash_password`)

## 3. Operativ

- [ ] **Status-Page** online (statuspage.io ODER Eigenbau via `/api/status` + statisches HTML)
- [ ] **On-Call-Rotation** eingerichtet (mind. 1 Person, 24/7 für P1)
- [ ] **Incident-Response-Plan** durchgespielt: [`docs/ops/INCIDENT-RESPONSE-PLAN.md`](ops/INCIDENT-RESPONSE-PLAN.md) — insbesondere 72h-Meldefrist DSGVO Art. 33
- [ ] **Backups**: Daily `pg_dump`, 30d Retention, Off-Site-Kopie, Restore einmal getestet → [`docs/ops/RUNBOOK-tenant-restore.md`](ops/RUNBOOK-tenant-restore.md)
- [ ] **Monitoring**: Grafana-Dashboard (`monitoring/grafana/dashboards/tenants-overview.json`) importiert, Alerts für: API-5xx-Rate > 1%, DB-Verbindungen ausgeschöpft, Disk > 80%
- [ ] **Slack/E-Mail-Alerts** wirken (SLACK_WEBHOOK_URL gesetzt)
- [ ] **Staging-Umgebung** mit Stripe-Test-Mode läuft

## 4. Kommerziell

- [ ] **Marketing-Site** live mit Pricing-Tabelle
- [ ] **Free-Trial-CTA** im Hero, funktioniert end-to-end (Signup → Verify → Login)
- [ ] **Welcome-Mail-Sequenz**: Tag 1, 3, 7, 13 (Erinnerungen, How-Tos, Trial-Ende-Warnung)
- [ ] **Knowledge-Base**: mind. Artikel *"Wie richte ich meine Praxis ein?"* + *"Was passiert bei Zahlungsausfall?"*
- [ ] **Demo-Video** (~5 min, eingebettet auf Landing-Page)
- [ ] **Stripe-Produkte** angelegt: `starter` (19€/Sitz/Mo + 15% annual), `pro` (39€/Sitz/Mo + 15% annual), `enterprise` (per Contract)
- [ ] **Test-Trial von extern** erfolgreich durchlaufen (anderes IP, fremder Browser)

## 5. Dev-Hygiene

- [ ] CI blockt Merge bei rotem Cross-Tenant-Test
- [ ] Dependabot aktiv (Python + npm)
- [ ] Release-Prozess dokumentiert (siehe CLAUDE.md)
- [ ] Runbook für Tenant-Restore getestet
- [ ] Alle Phase 1–7 Issues [#92–#98] geschlossen

## Verantwortlichkeiten

| Bereich | Zuständig |
|---|---|
| Legal/AGB/DS | Anwalt (extern) + Manuel |
| Pen-Test | Externer Anbieter |
| Marketing-Site | Manuel |
| Monitoring/On-Call | Manuel |
| Stripe-Setup | Manuel |
| DPO | Manuel (interner DPO bis zur Personenzahl-Schwelle) |

## Nach Go-Live — erste 30 Tage

- Tägliche Überprüfung der Slack-Alerts
- Wöchentlicher Blick auf Grafana (MRR, Churn, Trial-Conversion)
- Nach 30 Tagen: Churn-Analyse + erste Kunden-Feedbacks sammeln
- Erste Kündigung durchspielen (Delete-Flow + Anonymisierungs-Cron validieren)
