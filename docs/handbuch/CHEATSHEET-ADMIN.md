# PraxisZeit – Kurzanleitung Administrator

---

## Login & Navigation
**URL:** `https://[Server-Adresse]/login` (beim ersten Aufruf Zertifikat-Warnung „Erweitert → Weiter zu …" bestätigen)

**Mitarbeiter-Bereich:** Dashboard · Zeiterfassung · Abwesenheiten · Profil

**Administration:** Admin-Dashboard · Benutzerverwaltung · Änderungsanträge · Berichte · Abwesenheiten · Änderungsprotokoll · Fehler-Monitoring · Anträge · Import · Einstellungen

---

## Benutzerverwaltung

### Neuen Mitarbeiter anlegen
**Benutzerverwaltung** → **Neuer Mitarbeiter:in**
- Benutzername (Login-Name), Passwort (mind. 10 Zeichen)
- Vorname / Nachname, E-Mail (optional)
- Wochenstunden, Arbeitstage/Woche, Urlaubstage
- Rolle: Mitarbeiter:in oder Admin
- Optional: Stundenzählung aus (leitende MA – Urlaub/Krank zählen trotzdem tagebasiert), ArbZG-Prüfungen aussetzen (§18), Nachtarbeitnehmer (§6), **Nimmt an Betriebsferien teil** (Standard an), Erster/Letzter Arbeitstag (Soll nur in diesem Zeitraum), Abteilung/Bereich, Anfangssaldo Überstunden

> **Urlaub (Tagesprinzip):** 1 freier Arbeitstag = 1 Urlaubstag (unabhängig von Tagesstunden/Wochentag). Anspruch anteilig: `30 × Arbeitstage/5`. Verbrauch tagebasiert, Stunden nur intern.

> **Benutzerübersicht** zeigt je MA Urlaubskonto **und** Überstundensaldo (JTD); „—" bei deaktivierter Stundenzählung.

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

## Abwesenheitsanträge genehmigen

**Anträge** (Admin-Navigation, Seite: „Abwesenheitsanträge")

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
- → Alle MA **mit „Nimmt an Betriebsferien teil"** (Standard) erhalten automatisch Abwesenheitseinträge (keine Urlaubstage!) – rollenunabhängig (auch Admins, die MA sind)
- Nachträglich Berechtigte: Option setzen, dann Betriebsferien **einmal erneut speichern** → Einträge werden nachgetragen
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
| Ruhezeitwarnung | < 11h seit letztem Arbeitsende (beim Einstempeln) | §5 |

---

## Überstundenausgleich

**Abwesenheit → Typ „Überstundenausgleich"**
- Soll bleibt erhalten, Ist = 0h → Konto sinkt um Tagessoll
- Kein Budget-Check — Kontostand manuell prüfen!

---

## Abwesenheits-Änderungsanträge

- MA können Urlaub/Fortbildung per Änderungsantrag beantragen
- Krankmeldung per Antrag **gesperrt** (nur Admin)
- Genehmigung → Abwesenheit wird automatisch erstellt
- DSGVO: Kranktage im Kalender für Nicht-Admins als „abwesend" maskiert

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

## Lizenz

- Liegt in `config/license.key` (aus dem Shop **praxiszeit.mr-development.de**).
- **Abgelaufen/ungültig → Read-Only-Modus:** Anmeldung und Daten-**Export** funktionieren weiter, aber **Stempeln** und **Anträge stellen/genehmigen** sind gesperrt. Der Dienst stürzt NICHT ab.
- **Lösung:** aktuelle Lizenz aus dem Shop holen, `config/license.key` ersetzen, Dienst neu starten (`net stop PraxisZeit` / `net start PraxisZeit`).

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

## Jahresabschluss

| Aktion | Button | Beschreibung |
|--------|--------|--------------|
| **Erstellen** | 🟠 Jahresabschluss | Berechnet Überstunden-Saldo + Resturlaub aller aktiven MA und übernimmt sie ins Folgejahr |
| **Löschen** | 🔴 Abschluss löschen | Entfernt alle Übernahmen fürs Folgejahr unwiderruflich (inkl. manueller Übernahmen!) |

**Wo:** Admin-Dashboard → Jahresübersicht → Jahr auswählen → Button klicken
**Achtung:** Löschen betrifft **alle** Mitarbeiter und kann nicht rückgängig gemacht werden. Bestätigungsdialog lesen!

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
