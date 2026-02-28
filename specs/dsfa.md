# Datenschutz-Folgenabschätzung (DSFA) nach Art. 35 DSGVO

**System:** PraxisZeit – Elektronisches Zeiterfassungssystem
**Verantwortlicher:** [Name der Praxis / des Unternehmens]
**Stand:** 2026-02-28
**Status:** Entwurf – durch Verantwortlichen zu prüfen und zu unterzeichnen

---

## 1. Beschreibung der Verarbeitungsvorgänge

### 1.1 Art der Verarbeitung

PraxisZeit erfasst systematisch das Arbeitsverhalten von Mitarbeitenden:

| Vorgang | Beschreibung |
|---------|-------------|
| Zeitstempelung | Tägliche Start-/Endzeiten, Pausenzeiten |
| Abwesenheitserfassung | Urlaub, Krankheit (Art. 9), Fortbildung |
| Überstunden-Tracking | Kumulierte Soll/Ist-Differenzen |
| ArbZG-Compliance-Prüfung | Automatisierte Reports zu Ruhezeitverstößen, Nachtarbeit, Sonntagsarbeit |
| Admin-Auswertung | Zugriff auf alle Mitarbeiterdaten durch Admins |
| Excel-Exporte | Weitergabe an Lohnbuchhaltung |

### 1.2 Zweck der Verarbeitung

- Erfüllung gesetzlicher Pflichten (§16 ArbZG: Aufzeichnungspflicht)
- Verwaltung des Arbeitsverhältnisses (Urlaub, Überstunden, Abrechnung)
- ArbZG-Compliance-Nachweis (§§ 3, 4, 5, 6, 9, 11 ArbZG)

### 1.3 Betroffene Personen

Alle Mitarbeitenden der Praxis/des Unternehmens (typisch: 2–50 Personen).

### 1.4 Datenkategorien

- **Reguläre Daten:** Name, Kontaktdaten, Arbeitszeiten, Vertragsdaten
- **Besondere Kategorien (Art. 9):** Krankmeldungen, Nachtarbeitnehmer-Status

---

## 2. Schwellenwert-Test: Ist eine DSFA erforderlich?

### 2.1 Kriterien nach Art. 29-Gruppe (Leitlinien WP 248)

| Kriterium | Trifft zu? | Begründung |
|-----------|-----------|------------|
| Bewertung oder Scoring | ✓ Ja | Überstunden-Score, ArbZG-Compliance-Score |
| Automatisierte Entscheidung | Nein | Keine automatisierten Entscheidungen mit Rechtswirkung |
| Systematische Überwachung | ✓ Ja | Lückenlose tägliche Zeiterfassung aller MA |
| Sensible Daten (Art. 9) | ✓ Ja | Krankheitsdaten, Nachtarbeitnehmer-Status |
| Große Datenmenge | Nein | Kleine Praxis (<50 MA) |
| Datenabgleich/-zusammenführung | Nein | Kein Abgleich mit externen Quellen |
| Innovative Technologie | Nein | Standard-Webanwendung |
| Datenübermittlung in Drittländer | Nein | Alle Daten bleiben in EU/lokal |
| Verhinderung Ausübung v. Rechten | Nein | Betroffenenrechte implementiert |

**Ergebnis:** 3 von 9 Kriterien erfüllt. Ab 2 Kriterien empfehlen Aufsichtsbehörden eine DSFA.
**Fazit: Eine DSFA ist durchzuführen.**

### 2.2 Rechtliche Einordnung

Art. 35 Abs. 3 lit. b DSGVO: Systeme zur „systematischen umfangreichen Überwachung öffentlich zugänglicher Bereiche" und Art. 35 Abs. 3 lit. a (Verarbeitung besonderer Datenkategorien in großem Maßstab) könnten anwendbar sein. Auch für kleinere Organisationen ist die DSFA aus Vorsorgegründen empfohlen (vgl. BfDI-Positionspapiere zur Arbeitnehmerüberwachung).

---

## 3. Notwendigkeit und Verhältnismäßigkeit

### 3.1 Rechtmäßigkeit

| Zweck | Rechtsgrundlage | Verhältnismäßig? |
|-------|-----------------|-----------------|
| Zeiterfassung (Pflicht) | Art. 6 Abs. 1 lit. c + §16 ArbZG | ✓ Ja – gesetzliche Pflicht |
| Urlaubs-/Überstundenverwaltung | Art. 6 Abs. 1 lit. b + §26 BDSG | ✓ Ja – Beschäftigungsverhältnis |
| Krankheitsdaten | Art. 9 Abs. 2 lit. b + §26 Abs. 3 BDSG | ✓ Ja – gesetzlich erforderlich |
| ArbZG-Compliance-Reports | Art. 6 Abs. 1 lit. c + ArbZG | ✓ Ja – gesetzliche Pflicht |
| Admin-Vollzugriff | Art. 6 Abs. 1 lit. b | ⚠ Teilweise – Zugriffsprotokoll empfohlen |

### 3.2 Erforderlichkeit und Datensparsamkeit

- Zeiterfassung auf das gesetzlich geforderte Minimum beschränkt (kein GPS, keine Biometrie)
- Krankheitsdaten nur als Typ-Flag, keine Diagnosen gespeichert
- Excel-Exporte: Krankheitsdaten standardmäßig ausgeblendet (Privacy by Default)
- Inaktive Mitarbeitende: Anonymisierungs- und Löschprozess implementiert
- Aufbewahrung: 2 Jahre entsprechend §16 ArbZG

---

## 4. Risikobewertung

### 4.1 Identifizierte Risiken

| Risiko | Wahrscheinlichkeit | Schwere | Gesamtrisiko | Maßnahme |
|--------|-------------------|---------|-------------|---------|
| Unbefugter Zugriff auf Mitarbeiterdaten | Mittel | Hoch | **Hoch** | Rollenmodell, starke Passwörter, JWT-Revocation |
| Datenverlust / DB-Ausfall | Niedrig | Hoch | **Mittel** | Regelmäßige DB-Backups |
| Übergang Gesundheitsdaten in Exporte | Niedrig | Hoch | **Mittel** | Privacy by Default – Checkbox mit Audit-Log |
| Identitätsdiebstahl (Token-Klau via XSS) | Niedrig | Mittel | **Mittel** | CSP-Header, HttpOnly-Cookie empfohlen |
| Überwachungsgefühl / Verhaltensanpassung MA | Mittel | Mittel | **Mittel** | Transparenz durch Datenschutzhinweis, DSFA |
| Fehler in ArbZG-Berechnungen | Niedrig | Niedrig | **Niedrig** | Tests vorhanden |
| Weitergabe an Dritte (Lohnbuchhaltung) | Niedrig | Mittel | **Niedrig** | AVV mit Steuerberater abschließen |

### 4.2 Verbleibende Risiken

Die verbleibenden Risiken nach Implementierung der Maßnahmen werden als **akzeptabel** eingestuft, da:
- Eine gesetzliche Pflicht zur Verarbeitung besteht (§16 ArbZG)
- Die Datenmenge gering ist (kleine Praxis, wenige Mitarbeitende)
- Umfangreiche technische Schutzmaßnahmen implementiert sind

---

## 5. Technische und organisatorische Maßnahmen (Gesamtübersicht)

| Maßnahme | Implementiert | Anmerkung |
|----------|-------------|-----------|
| Passwort-Hashing (bcrypt) | ✓ | Min. 10 Zeichen + Komplexität |
| JWT-Token-Revocation | ✓ | token_version-Mechanismus |
| Rate Limiting (Auth) | ✓ | 5/min Login, 3/min PW-Change |
| Rollenbasierte Zugriffskontrolle | ✓ | Admin / Employee getrennt |
| Audit-Log (Schreiboperationen) | ✓ | time_entry_audit_logs |
| Audit-Log (Exporte mit Gesundheitsdaten) | ✓ | health_export-Aktion |
| Privacy by Default (Krankheitsdaten) | ✓ | Standardmäßig ausgeblendet |
| Anonymisierungsfunktion | ✓ | DSGVO Art. 17 |
| Löschfristenkonzept | ✓ | 2 Jahre (§16 ArbZG) |
| Datenportabilität (Art. 20) | ✓ | GET /api/auth/me/export |
| Berichtigungsrecht (Art. 16) | ✓ | PUT /api/auth/profile |
| Datenschutzerklärung (Art. 13) | ✓ | /privacy-Seite |
| HTTPS | ⚠ | docker-compose.ssl.yml vorhanden; Pflicht in Produktion |
| DB-Verbindungsverschlüsselung | ⚠ | ?sslmode=require bei externem DB-Server |
| 2FA für Admins | ✗ | Im Backlog – empfohlen |
| Lese-Zugriffsprotokoll | ⚠ | Teilweise (Exporte); vollständig empfohlen |

---

## 6. Konsultation der betroffenen Personen

Für kleine Praxen ≤10 Mitarbeitende: Keine formale Konsultation zwingend erforderlich.
**Empfehlung:** Mitarbeitende über Zeiterfassungssystem informieren (Datenschutzhinweis, Betriebsversammlung oder Aushang).

---

## 7. Vorabkonsultation (Art. 36 DSGVO)

Eine Vorabkonsultation der zuständigen Datenschutzaufsichtsbehörde ist erforderlich, wenn die Risiken **nach Ergreifung aller Maßnahmen** noch als hoch eingestuft werden.

**Bewertung:** Nach Umsetzung aller Maßnahmen verbleibt ein **mittleres Restrisiko** – eine Vorabkonsultation ist **nicht zwingend erforderlich**, aber bei Unsicherheiten empfehlenswert.

---

## 8. Überprüfung und Aktualisierung

Diese DSFA ist zu überprüfen bei:
- Einführung neuer Features (z.B. GPS-Tracking, Biometrie)
- Erweiterung der Datenkategorien
- Änderung der Aufbewahrungsfristen
- Änderung des Hostings (z.B. Cloud-Umzug)
- Änderungen in der Rechtslage

**Nächste reguläre Überprüfung:** [Datum + 2 Jahre]

---

## 9. Verantwortliche Unterzeichnung

| Funktion | Name | Datum | Unterschrift |
|----------|------|-------|-------------|
| Verantwortlicher | | | |
| Datenschutzbeauftragter (falls vorhanden) | | | |

---

*Erstellt auf Basis der DSGVO-Prüfung des PraxisZeit-Systems (2026-02-28).
Rechtsbindende Beurteilung durch qualifizierte Datenschutzfachperson empfohlen.*
