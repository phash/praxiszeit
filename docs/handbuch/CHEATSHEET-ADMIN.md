# PraxisZeit – Kurzanleitung Administrator

---

## Login & Navigation
**URL:** `http://[Server-Adresse]/login`

**Mitarbeiter-Bereich:** Dashboard · Zeiterfassung · Abwesenheiten · Profil

**Administration:** Admin-Dashboard · Benutzerverwaltung · Änderungsanträge · Berichte · Abwesenheiten · Änderungsprotokoll · Fehler-Monitoring · Urlaubsanträge · Import · Einstellungen

---

## Benutzerverwaltung

### Neuen Mitarbeiter anlegen
**Benutzerverwaltung** → **Neuer Mitarbeiter:in**
- Benutzername (Login-Name), Passwort (mind. 10 Zeichen)
- Vorname / Nachname, E-Mail (optional)
- Wochenstunden, Arbeitstage/Woche, Urlaubstage
- Rolle: Mitarbeiter:in oder Admin
- Optional: ArbZG-Prüfungen aussetzen (§18), Nachtarbeitnehmer (§6)

### Stundenänderung (Teilzeit etc.)
**Benutzer öffnen** → neue Wochenstunden + **Wirkungsdatum** eintragen
→ Historische Salden bleiben korrekt!

### Mitarbeiter deaktivieren (niemals löschen!)
**Benutzer öffnen** → Status „Inaktiv"
→ Daten 2 Jahre aufbewahren (§16 ArbZG)

---

## Admin-Dashboard

| Spalte | Bedeutung |
|--------|-----------|
| **Soll/Ist** | Stunden des gewählten Monats |
| **Saldo** | Differenz in H:MM |
| **Übersto. Kum.** | Kumulierter Jahressaldo |
| **Urlaub** | Verbleibende Tage (Ampel) |
| **Krank** | Kranktage im Monat |

Klick auf Pfeil → Detailansicht des Mitarbeiters

---

## Berichte & Exporte

| Bericht | Inhalt | Formate |
|---------|--------|---------|
| **Monatsreport** | Tägliche Einträge aller MA | Excel + CSV |
| **Jahresreport Classic** | 12 Monate kompakt | Excel + CSV |
| **Jahresreport Detailliert** | 365 Tage, ~5s | Excel + CSV |

**Exportieren:** Berichte → Typ & Zeitraum wählen → Excel oder CSV klicken
**Aufbewahrungspflicht: 2 Jahre** (§16 ArbZG)

---

## Urlaubsanträge genehmigen

**Urlaubsanträge** (Admin-Navigation)

**Toggle oben:** Genehmigungspflicht ein-/ausschalten
- **Aus** (Standard): Mitarbeiter buchen Urlaub direkt
- **Ein**: Urlaub landet als „Offen" zur Genehmigung

**Genehmigen:** Grüner Button → Abwesenheiten werden automatisch eingetragen
**Ablehnen:** Roter Button → optionalen Ablehnungsgrund eingeben

---

## Korrekturanträge prüfen

**Änderungsanträge** → offene Anträge → Antrag öffnen
- Alt vs. Neu vergleichen, Begründung lesen
- **Genehmigen** → Eintrag wird sofort geändert
- **Ablehnen** → optional Ablehnungsgrund eintragen

---

## Betriebsferien

**Abwesenheiten → Tab Betriebsferien → Neue Betriebsferien**
- Bezeichnung + Von–Bis → Speichern
- → Alle MA erhalten automatisch Abwesenheitseinträge (keine Urlaubstage!)
- Löschen: Einträge werden bei allen MA automatisch entfernt

---

## ArbZG-Pflichten – Automatik bei Zeiterfassung

| Prüfung | Grenze | § |
|---------|--------|---|
| Tagesarbeitszeit Warnung | > 8h Netto | §3 |
| Tagesarbeitszeit Sperrung | > 10h Netto | §3 |
| Pausenpflicht | > 6h → 30 Min. / > 9h → 45 Min. | §4 |
| Nachtarbeitnehmer | > 8h täglich | §6 |
| Sonntagsarbeit | Warnung + Ausnahmegrund-Pflicht | §9/§10 |
| Wochenstunden | Warnung > 48h | §14 |

---

## ArbZG-Compliance-Berichte (regelmäßig prüfen!)

**Berichte** → nach unten scrollen → ArbZG-Berichte

| Bericht | Inhalt | Handlungsbedarf bei |
|---------|--------|-------------------|
| **§5 Ruhezeitverstöße** | Fälle < 11h Ruhezeit | Sofort! Ursachen beseitigen |
| **§6 Nachtarbeit** | MA mit ≥ 48 Nachtarbeitstagen/Jahr | Arbeitsmed. Untersuchung anbieten |
| **§11 Sonntagsarbeit** | Sonntage pro MA (Ziel: max. 37/Jahr) | Dienstplanung anpassen |
| **§11 Ersatzruhetag** | Offene Ersatzruhetag-Pflichten | Ausgleich: Sonntag 2 Wo / Feiertag 8 Wo |

---

## Audit-Log & Monitoring

**Änderungsprotokoll:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis
**Fehler-Monitoring:** Technische Fehler → bei wiederkehrenden Fehlern IT kontaktieren oder GitHub Issue öffnen

---

## Wichtige Limits

| Regel | Wert | § |
|-------|------|---|
| Tagesarbeitszeit max. | **10 Stunden** | §3 |
| Ruhezeit min. | **11 Stunden** | §5 |
| Freie Sonntage min. | **15 pro Jahr** | §11 |
| Ersatzruhetag (Sonntag) | **2 Wochen** | §11 |
| Ersatzruhetag (Feiertag) | **8 Wochen** | §11 |
| Aufbewahrungspflicht | **2 Jahre** | §16 |

---

## Notfall-Checkliste Monatsabschluss

- [ ] Alle Korrekturanträge geprüft und entschieden
- [ ] Monatsreport exportiert und gesichert
- [ ] §5 Ruhezeitbericht geprüft (Verstöße dokumentieren)
- [ ] §11 Ersatzruhetage nachgeführt
- [ ] Offene Urlaubstage geprüft (Ampel-System im Admin-Dashboard)

---

## Notfall-Kontakte

**IT-Support:** ____________________________

**Arbeitsrechtliche Fragen:** ____________________________

---

*PraxisZeit · ArbZG-Volltext: [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
