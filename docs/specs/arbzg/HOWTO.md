# ArbZG-Compliance-Audit – Durchführung

## Wann durchführen?

- Bei Änderungen an der Zeiterfassungslogik (create/update/clock-out)
- Bei neuen Arbeitszeitmodellen (z.B. Schichtarbeit, Gleitzeit)
- Bei Änderungen am ArbZG durch den Gesetzgeber
- Nach der Implementierung neuer ArbZG-relevanter Features
- Mindestens **einmal jährlich**

---

## Wie wird der Audit erstellt?

### 1. Audit-Prompt an Claude

```
Führe einen vollständigen ArbZG-Compliance-Audit des PraxisZeit-Projekts durch.
Prüfe für jeden relevanten Paragraphen, ob die Implementierung korrekt und vollständig ist:

- §3 ArbZG: Tägliche Höchstarbeitszeit (8h Warnung, 10h Hard-Limit)
- §4 ArbZG: Ruhepausen (>6h → 30 min, >9h → 45 min)
- §5 ArbZG: Ruhezeit (11h Mindestruhezeit zwischen Arbeitstagen)
- §6 ArbZG: Nachtarbeit (23–6 Uhr, is_night_worker, 8h-Limit für Nachtarbeitnehmer)
- §9 ArbZG: Sonn- und Feiertagsruhe
- §10 ArbZG: Ausnahmen Sonn-/Feiertagsarbeit (Dokumentationspflicht)
- §11 ArbZG: Ersatzruhetage (15 freie Sonntage/Jahr, Kompensation)
- §14 ArbZG: Mehrarbeit (48h-Wochenwarnung)
- §16 ArbZG: Aufzeichnungspflicht und Aufbewahrung (2 Jahre)
- §18 ArbZG: Leitende Angestellte (exempt_from_arbzg-Flag)

Prüfe alle Eingabepfade:
- Mitarbeiter: create, update, clock-out
- Admin: admin-create, admin-update
- Änderungsanträge: change-request-apply

Erstelle einen vollständigen HTML-Bericht mit:
- Executive Summary (Compliance-Status pro Paragraph)
- Alle Findings mit Fundstelle im Code
- Positiv-Befunde (korrekt implementierte Checks)
- Empfohlene Maßnahmen
```

### 2. Findings implementieren

Jeden Fund im Code beheben. Sicherstellen, dass **alle Eingabepfade** (nicht nur einer) den Check enthalten.

### 3. Aktualisierten Report erzeugen ← PFLICHT

Nach Implementierung **aller** Findings den Bericht aktualisieren:

```
Der ArbZG-Audit wurde vollständig implementiert.
Aktualisiere specs/arbzg/arbzg-compliance.html:
- Alle behobenen Findings mit grünem "Behoben"-Badge markieren
- Compliance-Status pro Paragraph auf ✓ setzen
- Executive Summary aktualisieren
```

Außerdem `arbzg-compliance.md` aktualisieren:
- Neue Checks in der Implementierungstabelle ergänzen
- Fundstellen (Datei + Funktion) auf aktuellen Stand bringen

### 4. Dateiname-Konvention

```
arbzg-compliance.html   ← wird nach jedem Zyklus aktualisiert
arbzg-compliance.md     ← lebendes Dokument, immer aktuell halten
```

---

## Enthaltene Dokumente

| Datei | Art | Beschreibung |
|-------|-----|-------------|
| `arbzg-compliance.html` | Prüfbericht | ArbZG-Audit mit Compliance-Status pro § |
| `arbzg-compliance.md` | Lebendes Dokument | Implementierungsdetails aller ArbZG-Checks |
