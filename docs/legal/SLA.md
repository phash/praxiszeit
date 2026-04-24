# Service Level Agreement (SLA) — PraxisZeit SaaS

> ⚠️ ENTWURF — Vor verbindlicher Verwendung mit Anwält:in und nach
> ersten realen Verfügbarkeits-Messungen überarbeiten.

## Verfügbarkeits-Ziele

| Plan | Monatliche Verfügbarkeit | Ausnahmen |
|---|---|---|
| starter | 99,0 % (best effort) | Wartungsfenster, höhere Gewalt |
| pro | 99,5 % | wie starter + Incident-Krediten |
| enterprise | 99,9 % (individuell vereinbar) | nur dokumentierte Wartungen |

## Messung

- Gemessen wird die Erreichbarkeit von `https://praxiszeit.de/api/health`
  aus zwei unabhängigen Monitoring-Standorten.
- Basis ist die Summe aller Kalendertage des Abrechnungsmonats à 24h.
- Ausgenommen sind angekündigte Wartungen (max. 2× pro Monat, max. 60 min).

## Reaktionszeiten (nur `pro` + `enterprise`)

| Severity | Erste Antwort | Eskalation |
|---|---|---|
| P1 — Totalausfall | 30 min (24/7) | 2 h On-Call |
| P2 — eingeschränkter Betrieb | 4 h (Mo–Fr 08–18) | 1 Arbeitstag |
| P3 — Unbequem, aber nicht blockierend | 1 Arbeitstag | 5 Arbeitstage |

## Incident-Gutschriften

Unterschreitet die gemessene Verfügbarkeit das vereinbarte Ziel:

- pro: 10 % Monatskredit pro 1 Prozentpunkt Abweichung (max. 50 %)
- enterprise: individuell

Nicht erstattet werden Folgeschäden über den Monatskredit hinaus.

## Was **nicht** zum SLA zählt

- Stripe-Ausfälle (Drittanbieter) — separat gemessen, aber Stripe-
  Verfügbarkeit zählt nicht zum praxiszeit.de-SLA
- Mandantenseitige Probleme (falsche Zeitzone, fehlerhafte Import-Files)
- Höhere Gewalt (Unwetter, rechtliche Eingriffe, Pandemien)

## Statusseite

Aktuelle Verfügbarkeit unter `https://status.praxiszeit.de` (sobald
Status-Page live — siehe Go-Live-Checkliste).
