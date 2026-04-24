# Allgemeine Geschäftsbedingungen (AGB) — PraxisZeit SaaS

> ⚠️ **ENTWURF — Juristische Prüfung erforderlich.** Dieses Template ist
> ein Ausgangspunkt für die AGB der SaaS-Variante (praxiszeit.de). Es ist
> **nicht** als rechtsverbindlicher Vertrag gedacht; vor der Verwendung
> muss eine:r Rechtsanwält:in mit Schwerpunkt IT-/DSGVO-Recht Prüfung
> und Freigabe erteilen.

**Stand:** {{ENTWURF_DATUM}}
**Anbieter:** Manuel Rödig, MR Development — siehe Impressum

---

## §1 Geltungsbereich

Diese AGB regeln die Nutzung der Software "PraxisZeit" als
Software-as-a-Service (SaaS) durch Unternehmen im Sinne des §14 BGB
(insbesondere Arztpraxen, Zahnarztpraxen, Physiotherapie-Praxen) über
die Plattform praxiszeit.de.

## §2 Vertragsschluss

Der Nutzungsvertrag kommt durch Registrierung eines Accounts (Signup),
Bestätigung der E-Mail-Adresse (Double-Opt-In) und Annahme dieser AGB
zustande.

## §3 Leistungsumfang

Der Anbieter stellt die Software-Funktionen laut ausgewähltem Plan
(trial, starter, pro, enterprise) zur Verfügung. Die Verfügbarkeit
richtet sich nach dem jeweiligen [SLA](SLA.md).

## §4 Testphase (Trial)

Nach der Registrierung besteht ein kostenfreier 14-Tage-Test-Zeitraum.
Nach Ablauf wird der Account pausiert, sofern kein kostenpflichtiger
Plan gebucht wurde. Trial-Daten bleiben 30 Tage nach Pause-Beginn
exportierbar.

## §5 Preise & Zahlung

- **starter**: 19 € / Sitz / Monat (netto, zzgl. USt.)
- **pro**: 39 € / Sitz / Monat (netto, zzgl. USt.)
- **enterprise**: individuelle Konditionen
- Jahresabo: -15 %

Abrechnung erfolgt über Stripe; SEPA-Lastschrift und Karte werden
akzeptiert. Rechnungen sind binnen 14 Tagen zahlbar.

## §6 Verzug & Sperrung

Bei Zahlungsverzug (`past_due`) wird der Nutzer per E-Mail erinnert.
Nach 30 Tagen im Verzug wird der Account auf Read-Only gesetzt; die
Daten bleiben lesbar und exportierbar (insbesondere ArbZG-Daten).

## §7 Kündigung

- Monatsabo: zum Monatsende mit 7 Tagen Frist
- Jahresabo: zum Ende des Abrechnungsjahres
- Self-Service-Kündigung unter `/admin/billing` → "Account schließen"
- Nach Kündigung: 30 Tage Grace für Daten-Export, dann Anonymisierung
- Ausnahme: **ArbZG-pflichtige Arbeitszeitdaten werden 2 Jahre
  anonymisiert aufbewahrt** (§16 ArbZG)

## §8 Haftung

Der Anbieter haftet nur für Vorsatz und grobe Fahrlässigkeit.
Höchstbetrag pro Schadensfall: 12 Monatsentgelte. Ausnahme: Schäden
aus Verletzung der Leistungs- oder DSGVO-Pflichten — hier gilt
gesetzliche Haftung.

## §9 Datenschutz

Die Verarbeitung personenbezogener Daten erfolgt gemäß
Datenschutzerklärung (`docs/legal/DATENSCHUTZ-TEMPLATE.md`) und dem
individuellen Auftragsverarbeitungsvertrag (AVV gemäß §28 DSGVO).
Der Nutzer kann den AVV über `/api/tenant/avv` generieren.

## §10 Änderungen der AGB

Änderungen werden mit 6 Wochen Vorlauf per E-Mail angekündigt.
Widerspricht der Nutzer nicht, gelten sie als angenommen.

## §11 Gerichtsstand & anwendbares Recht

Es gilt deutsches Recht. Gerichtsstand ist der Sitz des Anbieters.

---

*Dieser Entwurf enthält keine abschließende Regelung zu SLA-
Verfügbarkeitsgarantien, Regelungen zu Subunternehmern/Cloud-Anbietern,
Regelungen zum ArbZG-konformen Umgang mit Arbeitszeitdaten aus
betrieblicher Sicht des Kunden, Regelungen zu Exportpflichten und
Aufbewahrungsfristen, Regelungen zur Streitbeilegung (VSBG). Diese
Abschnitte müssen durch die juristische Prüfung ergänzt werden.*
