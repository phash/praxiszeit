# DSGVO-Audit – Durchführung

## Wann durchführen?

- Bei Einführung neuer Datenkategorien (z.B. Biometrie, GPS, neue Pflichtfelder)
- Bei Änderung der Datenempfänger (neue Drittanbieter, Cloud-Umzug)
- Bei Änderung der Aufbewahrungsfristen oder Rechtsgrundlagen
- Nach größeren Feature-Implementierungen, die personenbezogene Daten betreffen
- Bei Änderungen in der DSGVO-Rechtslage (neue Aufsichtsbehörden-Leitlinien)
- Mindestens **alle 12 Monate**

---

## Wie wird der Audit erstellt?

### 1. Audit-Prompt an Claude

```
Führe einen vollständigen DSGVO-Compliance-Audit des PraxisZeit-Projekts durch.
Prüfe systematisch:
- Art. 5: Grundsätze (Zweckbindung, Datensparsamkeit, Speicherbegrenzung)
- Art. 6/9: Rechtsgrundlagen für alle Verarbeitungsvorgänge (inkl. Art. 9 Gesundheitsdaten)
- Art. 13: Informationspflicht (Datenschutzerklärung vollständig?)
- Art. 15–22: Betroffenenrechte (Auskunft, Berichtigung, Löschung, Portabilität)
- Art. 25: Privacy by Design / Privacy by Default
- Art. 28: Auftragsverarbeitung (alle Drittanbieter mit AVV?)
- Art. 30: Verarbeitungsverzeichnis aktuell?
- Art. 32: Technische und organisatorische Maßnahmen (TOMs)
- Art. 33/34: Datenpannen-Prozess dokumentiert?
- Art. 35: DSFA erforderlich und aktuell?
- §26 BDSG: Beschäftigtendatenschutz
- ArbZG §16: Aufzeichnungspflicht und Speicherfristen

Erstelle einen vollständigen HTML-Bericht mit:
- Executive Summary (Verdict, KPI-Grid)
- Datenkategorien-Tabelle mit Rechtsgrundlagen
- Alle Findings mit ID (F-001...), Schweregrad, Beschreibung, Fundstelle, Risiko, Empfehlung
- Betroffenenrechte-Implementierungsstand
- DSGVO-Compliance-Checkliste
- Priorisierte Maßnahmen-Liste
- Erforderliche Dokumentations-Übersicht
```

### 2. Findings implementieren

Jeden Fund aus dem Bericht beheben. Technische Maßnahmen im Code umsetzen, organisatorische Maßnahmen dokumentieren.

### 3. Begleitdokumente aktualisieren ← PFLICHT

Nach Implementierung **immer** alle vier Dokumente synchron halten:

```
Aktualisiere nach Umsetzung der DSGVO-Findings:
1. dsgvo-report.html     → Verdict auf "VOLLSTÄNDIG KONFORM", alle Findings mit "Behoben"-Badge
2. dsfa.md               → TOM-Tabelle und Risikobewertung auf aktuellen Stand bringen
3. verarbeitungsverzeichnis.md → Neue Datenkategorien, Empfänger, TOMs ergänzen
4. vier-augen-prinzip.md → Bei Änderungen am Admin-Zugriffsmodell aktualisieren
```

### 4. Dateiname-Konvention

```
dsgvo-report.html               ← wird nach jedem Zyklus aktualisiert (kein neues File)
dsfa.md                         ← lebendes Dokument, immer aktuell halten
verarbeitungsverzeichnis.md     ← lebendes Dokument, immer aktuell halten
```

---

## Enthaltene Dokumente

| Datei | Art | Beschreibung |
|-------|-----|-------------|
| `dsgvo-report.html` | Prüfbericht | DSGVO-Audit (alle 20 Findings behoben ✓) |
| `dsfa.md` | Lebendes Dokument | Datenschutz-Folgenabschätzung nach Art. 35 |
| `verarbeitungsverzeichnis.md` | Lebendes Dokument | Verarbeitungsverzeichnis nach Art. 30 |
| `vier-augen-prinzip.md` | Richtlinie | Organisatorische Richtlinie Admin-Zugriff |
