# PraxisZeit – Kurzanleitung Administrator

---

## 🔐 Login & Navigation
**URL:** `http://[Server-Adresse]/login`
Admin-Navigation: Dashboard · Benutzer · Kalender · Berichte · Korrekturanträge · Audit-Log · Fehler · Betriebsferien

---

## 👤 Benutzerverwaltung

### Neuen Mitarbeiter anlegen
**Benutzerverwaltung** → **Neuer Benutzer**
- Benutzername (Login), Vor-/Nachname, Passwort
- Wochenstunden, Arbeitstage/Woche, Urlaubstage
- Rolle: Mitarbeiter oder Admin
- Optional: Kalenderfarbe, ArbZG-Ausnahme (§18)

### Stundenänderung (Teilzeit etc.)
**Benutzer bearbeiten** → neue Wochenstunden + **Wirkungsdatum** eintragen
→ Historische Salden bleiben korrekt!

### Mitarbeiter deaktivieren (nie löschen!)
**Benutzer bearbeiten** → Status „Inaktiv"
→ Daten 2 Jahre aufbewahren (§16 ArbZG)

---

## 📊 Berichte & Exporte

| Bericht | Inhalt | Verwendung |
|---------|--------|------------|
| **Monatsreport** | Tägliche Einträge aller MA | Gehaltsabrechnung |
| **Jahresreport Classic** | 12 Monate kompakt | Jahresüberblick |
| **Jahresreport Detailliert** | 365 Tage, ~5s | Steuerberater, Prüfung |

**Exportieren:** Berichte → Typ & Zeitraum wählen → Exportieren → Excel-Download
**Aufbewahrungspflicht: 2 Jahre** (§16 ArbZG)

---

## ✅ Korrekturanträge prüfen

**Korrekturanträge** → offene Anträge → **Prüfen**
- Alt vs. Neu vergleichen, Begründung lesen
- **Genehmigen** → Eintrag wird sofort geändert
- **Ablehnen** → optional Ablehnungsgrund eintragen

---

## 📅 Betriebsferien

**Betriebsferien** → **Neue Betriebsferien**
- Bezeichnung + Von–Bis → Speichern
- → Alle MA erhalten automatisch Abwesenheitseinträge (keine Urlaubstage!)
- Löschen: Einträge werden bei allen MA automatisch entfernt

---

## ⚖️ ArbZG-Pflichten – Tägliche Automatik

| Prüfung | Grenze | § |
|---------|--------|---|
| Tagesarbeitszeit | Warnung >8h, Sperrung >10h | §3 |
| Pausenpflicht | >6h → 30 min / >9h → 45 min | §4 |
| Sonntagsarbeit | Warnung + Ausnahmegrund-Pflicht | §9/§10 |
| Wochenstunden | Warnung >48h | §14 |
| Nachtarbeit | 8h-Grenze für Nachtarbeitnehmer | §6 |

---

## 📋 ArbZG-Compliance-Berichte (regelmäßig prüfen!)

| Bericht | Inhalt | Handlungsbedarf bei |
|---------|--------|-------------------|
| **§5 Ruhezeitverstöße** | Fälle < 11h Ruhezeit | Sofort! Ursachen beseitigen |
| **§6 Nachtarbeit** | MA mit ≥ 48 Nachtarbeitstagen/Jahr | Arbeitsmed. Untersuchung anbieten |
| **§11 Sonntagsarbeit** | Sonntage pro MA, Ziel: max. 37/Jahr | Dienstplanung anpassen |
| **§11 Ersatzruhetag** | Offene Ersatzruhetag-Pflichten | Ausgleich innerhalb 2 Wochen |

**Pfad:** Berichte → nach unten scrollen → ArbZG-Berichte

---

## 🔍 Audit-Log & Monitoring

**Audit-Log:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis
**Fehler-Monitoring:** Technische Fehler → bei wiederkehrenden Fehlern IT kontaktieren

---

## 🚨 Notfall-Checkliste Monatsabschluss

- [ ] Alle Korrekturanträge geprüft und entschieden
- [ ] Monatsreport exportiert und gesichert
- [ ] §5 Ruhezeitbericht geprüft (Verstöße dokumentieren)
- [ ] §11 Ersatzruhetage nachgeführt
- [ ] Offene Urlaubstage geprüft (Ampel-System im Dashboard)

---

## ⚠️ Wichtige Limits

| Regel | Wert | § |
|-------|------|---|
| Tagesarbeitszeit max. | **10 Stunden** | §3 |
| Ruhezeit min. | **11 Stunden** | §5 |
| Freie Sonntage min. | **15 pro Jahr** | §11 |
| Ersatzruhetag (Sonntag) | **2 Wochen** | §11 |
| Ersatzruhetag (Feiertag) | **8 Wochen** | §11 |
| Aufbewahrungspflicht | **2 Jahre** | §16 |

---

## 📞 Notfall-Kontakte

**IT-Support:** ____________________________

**Arbeitsrechtliche Fragen:** ____________________________

---

*PraxisZeit · ArbZG-Volltext: [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
