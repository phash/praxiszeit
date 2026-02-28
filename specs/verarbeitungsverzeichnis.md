# Verarbeitungsverzeichnis nach Art. 30 DSGVO

**Verantwortlicher:** [Name der Praxis / des Unternehmens]
**Stand:** 2026-02-28
**Erstellt mit:** PraxisZeit-Zeiterfassungssystem

---

## 1. Allgemeine Angaben zur Verarbeitungstätigkeit

| Feld | Inhalt |
|------|--------|
| **Bezeichnung** | Elektronische Zeiterfassung und Arbeitszeitverwaltung |
| **Zweck** | Erfassung und Auswertung von Arbeitszeiten, Abwesenheiten und Überstunden der Mitarbeitenden; Einhaltung des ArbZG (§16 Aufzeichnungspflicht) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c DSGVO (rechtliche Verpflichtung: §16 ArbZG), Art. 6 Abs. 1 lit. b DSGVO (Durchführung des Beschäftigungsverhältnisses), Art. 88 DSGVO i.V.m. §26 BDSG |
| **Besondere Kategorien (Art. 9)** | Ja: Gesundheitsdaten (Krankmeldungen/Abwesenheiten wegen Krankheit) |
| **Rechtsgrundlage Art. 9** | Art. 9 Abs. 2 lit. b DSGVO (Beschäftigungsverhältnis) i.V.m. §26 Abs. 3 BDSG |

---

## 2. Verantwortlicher

| Feld | Inhalt |
|------|--------|
| **Name / Firma** | [Name der Praxis / des Unternehmens] |
| **Adresse** | [Straße, PLZ, Ort] |
| **Telefon** | [Telefonnummer] |
| **E-Mail** | [E-Mail-Adresse] |
| **Datenschutzbeauftragter** | [Name, falls vorhanden – sonst „nicht gesetzlich erforderlich"] |

---

## 3. Kategorien betroffener Personen

| Kategorie | Beschreibung |
|-----------|-------------|
| **Mitarbeitende (Arbeitnehmer)** | Alle Beschäftigten der Praxis/des Unternehmens, die das System nutzen |
| **Admins** | Praxisinhaber/in oder beauftragte Person mit erhöhten Zugriffsrechten |

---

## 4. Kategorien personenbezogener Daten

### 4.1 Stammdaten (Nutzerkonto)

| Datenkategorie | Felder | Rechtsgrundlage |
|----------------|--------|-----------------|
| Identifikationsdaten | Benutzername, Vorname, Nachname | Art. 6 Abs. 1 lit. b DSGVO |
| Kontaktdaten | E-Mail-Adresse (optional) | Art. 6 Abs. 1 lit. b DSGVO |
| Zugangs­daten | Passwort-Hash (bcrypt), JWT-Token-Version, TOTP-Secret (verschlüsselt, optional) | Art. 6 Abs. 1 lit. b DSGVO |
| Vertrags­daten | Wochenstunden, Arbeitstage, Urlaubstage, Kalenderfarbe | Art. 6 Abs. 1 lit. b DSGVO |

### 4.2 Zeiterfassungsdaten

| Datenkategorie | Felder | Rechtsgrundlage |
|----------------|--------|-----------------|
| Arbeitszeitdaten | Datum, Startzeit, Endzeit, Pausenminuten, Notiztxt | Art. 6 Abs. 1 lit. c DSGVO (§16 ArbZG) |
| Sonn-/Feiertagsarbeit | Ausnahmegrund-Dokumentation (§10 ArbZG) | Art. 6 Abs. 1 lit. c DSGVO |

### 4.3 Abwesenheitsdaten

| Datenkategorie | Felder | Rechtsgrundlage | Besondere Kategorie |
|----------------|--------|-----------------|---------------------|
| Urlaub | Datum, Zeitraum | Art. 6 Abs. 1 lit. b DSGVO | Nein |
| Fortbildung | Datum, Zeitraum | Art. 6 Abs. 1 lit. b DSGVO | Nein |
| Sonstige Abwesenheit | Datum, Zeitraum | Art. 6 Abs. 1 lit. b DSGVO | Nein |
| **Krankmeldung** | Datum, Zeitraum | Art. 9 Abs. 2 lit. b DSGVO i.V.m. §26 Abs. 3 BDSG | **Ja (Art. 9)** |
| **Nachtarbeitnehmer-Status** | `is_night_worker`-Flag (Bool) gem. §6 ArbZG | Art. 6 Abs. 1 lit. c (ArbZG §6); ggf. Art. 9 Abs. 2 lit. b | **Ja – Gesundheitsbezug** (erhöhtes Berufsrisiko) |

> **Hinweis zu Krankheitsdaten:** Das System unterscheidet Abwesenheiten vom Typ „sick". Diese Gesundheitsdaten werden bei Excel- und ODS-Exporten standardmäßig **nicht** ausgegeben (Privacy by Default gem. Art. 25 DSGVO, maskiert als „Abwesenheit"). Die Anzeige erfordert aktive Freischaltung durch den Admin und wird im Audit-Log protokolliert (Aktion: `health_export`).
>
> **Hinweis zum Nachtarbeitnehmer-Status:** Das `is_night_worker`-Flag ist gesundheitsbezogen (§6 ArbZG: erhöhtes Gesundheitsrisiko) und wird analog zu Krankmeldungsdaten behandelt. JSON-Reportzugriffe werden protokolliert (Aktion: `health_data_read`).

### 4.4 Verlaufsdaten / Änderungshistorie

| Datenkategorie | Felder | Zweck |
|----------------|--------|-------|
| Arbeitszeitenhistorie | Wochenstunden, Gültigkeitsdatum | Korrekte historische Berechnung von Soll-Stunden |
| Änderungsanträge | Zeiteintrags-Korrekturen mit Begründung | Transparenz, Nachvollziehbarkeit |
| Audit-Log | Benutzer, Aktion, Zeitstempel, Details | Nachvollziehbarkeit von Admin-Aktionen, DSGVO-Compliance |

---

## 5. Aufbewahrungsfristen und Löschkonzept

| Datenkategorie | Aufbewahrungsfrist | Rechtsgrundlage | Löschmechanismus |
|----------------|-------------------|-----------------|------------------|
| Zeiterfassungsdaten | **2 Jahre** | §16 Abs. 2 ArbZG | Anonymisierung nach Deaktivierung; Purge nach Ablauf der Frist |
| Urlaubsdaten | 3 Jahre (steuerlich relevant) | §147 AO | Anonymisierung / Löschung nach Fristablauf |
| Krankmeldungen | 2 Jahre (ArbZG) | §16 ArbZG | Anonymisierung nach Deaktivierung |
| Audit-Log-Einträge | 2 Jahre | interne Policy | Manuelle Bereinigung nach Fristablauf |
| Stammdaten (aktiver MA) | Für Dauer des Beschäftigungsverhältnisses | §26 BDSG | Deaktivierung bei Austritt |
| Stammdaten (inaktiver MA) | Bis Ablauf aller Aufbewahrungsfristen | §16 ArbZG / §147 AO | Anonymisierung + Purge |
| Passwort-Hashes | Bis Kontoschließung / Anonymisierung | Art. 6 Abs. 1 lit. b DSGVO | Überschreiben bei Anonymisierung |

### Löschprozess (Implementierung in PraxisZeit)

1. **Deaktivierung:** Mitarbeiter wird auf `is_active = False` gesetzt (kein Login mehr möglich).
2. **Anonymisierung:** Nach Ausscheiden kann der Admin die Person anonymisieren:
   - Name → „Gelöschter Benutzer"
   - Benutzername → `deleted_<UUID-Präfix>`
   - E-Mail → leer
   - Abwesenheitsdaten werden gelöscht
   - Zeiterfassungsdaten bleiben (ArbZG-Pflicht), aber ohne Personenbezug
3. **Endgültige Löschung (Purge):** Erst nach Ablauf der 2-Jahres-Frist (§16 ArbZG) möglich:
   - Alle verbleibenden Daten werden gelöscht
   - Audit-Log-Eintrag bleibt als Nachweis erhalten

---

## 6. Empfänger der Daten

| Empfänger | Kategorie | Rechtsgrundlage | Dritt­land? |
|-----------|-----------|-----------------|------------|
| Praxisinhaberin / Geschäftsführung | Intern | Art. 6 Abs. 1 lit. b/c DSGVO | Nein |
| Lohnbuchhaltung | Intern / Extern (Steuerberater) | Art. 28 DSGVO (Auftragsverarbeitung) | Nein |
| Datev / Lohnprogramm | Extern (Software) | Art. 28 DSGVO | Nein |
| Finanzamt (im Rahmen Betriebsprüfung) | Behörde | Art. 6 Abs. 1 lit. c DSGVO | Nein |
| GitHub Inc. (Fehler-Monitoring, optional) | Extern (Auftragsverarbeiter) | Art. 28 DSGVO (AVV erforderlich) | Nein (EU-Standardvertragsklauseln) |

> **Auftragsverarbeitung:** Wird PraxisZeit auf einem externen Server (Hosting) betrieben, ist ein Auftragsverarbeitungsvertrag (AVV) nach Art. 28 DSGVO mit dem Hosting-Anbieter abzuschließen.
>
> **GitHub-Integration:** Bei aktivierter `GITHUB_TOKEN`-Konfiguration erstellt PraxisZeit automatisch GitHub Issues bei kritischen Fehlern. Es werden keine direkten personenbezogenen Daten (Name, E-Mail) im Issue-Titel übertragen. Technische Details im Issue-Body können indirekt Rückschlüsse erlauben. AVV mit GitHub Inc. abschließen oder Integration deaktivieren (kein `GITHUB_TOKEN` konfigurieren).

---

## 7. Technische und organisatorische Maßnahmen (TOM, Art. 32 DSGVO)

| Maßnahme | Umsetzung |
|----------|-----------|
| **Zugangskontrolle** | Benutzername + Passwort (bcrypt, min. 10 Zeichen + Komplexität), JWT-Tokens, optionale TOTP-2FA für alle Nutzer |
| **Zugriffskontrolle** | Rollenmodell (Admin / Mitarbeiter); Mitarbeitende sehen nur eigene Daten |
| **Token-Sicherheit** | Refresh-Token als HttpOnly-Cookie (XSS-Schutz); Access-Token kurzlebig (30 min) |
| **Weitergabekontrolle** | HTTPS (TLS) für alle Verbindungen (Pflicht in Produktion); kein API-Caching sensibler Daten |
| **Eingabekontrolle** | Audit-Log für Admin-Schreibaktionen und DSGVO-relevante Exporte/Lesezugriffe (Gesundheitsdaten) |
| **Verfügbarkeitskontrolle** | Docker-Health-Checks, PostgreSQL-Backups |
| **Trennungsgebot** | Rollenbasierte Datentrennung; Krankheitsdaten in Exporten standardmäßig ausgeblendet |
| **Privacy by Default** | Gesundheitsdaten (Krank + Nachtarbeit) in Exporten deaktiviert; opt-in mit Audit-Log |
| **Pseudonymisierung** | Anonymisierungsfunktion für ausgeschiedene Mitarbeitende (POST /anonymize, DELETE /purge) |
| **Betroffenenrechte (Art. 16)** | PUT /api/auth/profile: Stammdaten selbst korrigierbar |
| **Datenportabilität (Art. 20)** | GET /api/auth/me/export: vollständiger JSON-Self-Service-Export |

---

## 8. Rechte der betroffenen Personen

Mitarbeitende haben folgende Rechte gem. DSGVO:

| Recht | Grundlage | Umsetzung |
|-------|-----------|-----------|
| Auskunft | Art. 15 DSGVO | Einsicht über Profilseite; Self-Service-Export unter GET /api/auth/me/export |
| Berichtigung | Art. 16 DSGVO | PUT /api/auth/profile: Name und E-Mail direkt änderbar; Änderungsantrag für Zeiteinträge |
| Löschung | Art. 17 DSGVO | Anonymisierung + Purge-Prozess (s. Abschnitt 5); POST /anonymize, DELETE /purge |
| Einschränkung | Art. 18 DSGVO | Deaktivierung des Kontos auf Anfrage (is_active = False) |
| Datenübertragbarkeit | Art. 20 DSGVO | GET /api/auth/me/export: maschinenlesbarer JSON-Export aller eigenen Daten |
| Widerspruch | Art. 21 DSGVO | An Verantwortlichen zu richten |

---

## 9. Gemeinsame Verantwortlichkeit / Auftragsverarbeitung

- Wird PraxisZeit **lokal on-premises** betrieben: Kein AVV erforderlich.
- Wird PraxisZeit bei einem **externen Hosting-Anbieter** betrieben: AVV nach Art. 28 DSGVO erforderlich.
- Der **Steuerberater / die Lohnbuchhaltung** erhält ggf. Exports: Prüfen, ob AVV oder Berufsgeheimnis greift.

---

## 10. Änderungshistorie dieses Dokuments

| Datum | Version | Änderung | Bearbeiter |
|-------|---------|----------|------------|
| 2026-02-28 | 1.0 | Erstversion | [Name] |
| 2026-02-28 | 1.1 | TOTP-2FA-Felder, is_night_worker (Art. 9), GitHub als Empfänger, TOM aktualisiert, Betroffenenrechte vervollständigt | Claude Sonnet 4.6 |

---

*Dieses Dokument ist gemäß Art. 30 DSGVO vom Verantwortlichen zu führen und auf Anfrage der Aufsichtsbehörde vorzulegen.*
