# Spec Driven Development (SDD) – PraxisZeit

Dieses Verzeichnis enthält alle Feature-Spezifikationen für PraxisZeit.
Die Spezifikationen folgen dem **Spec-Driven Development**-Ansatz nach [Martin Fowler](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html).

---

## Was ist Spec Driven Development?

> "Specifications — not code — are the primary artifact."

SDD bedeutet, dass strukturierte Spezifikationen geschrieben werden, *bevor* Code entsteht.
Specs beschreiben das *Was* und *Warum* – nicht das *Wie* (Implementierungsdetails).

### Reifegrade

| Stufe | Name | Beschreibung |
|-------|------|-------------|
| 1 | **Spec-first** | Specs zuerst schreiben, dann AI-gestützte Entwicklung |
| 2 | **Spec-anchored** | Specs nach der Entwicklung aktuell halten |
| 3 | **Spec-as-source** | Specs sind die einzige menschlich bearbeitete Datei; Code ist generiert |

PraxisZeit nutzt aktuell **Stufe 2 (Spec-anchored)**: Specs existieren parallel zum Code und werden bei Änderungen aktualisiert.

---

## Dateistruktur

```
specs/
├── README.md               # Diese Datei – Anleitung
├── TEMPLATE.md             # Vorlage für neue Specs
├── features/               # Feature-Spezifikationen
│   ├── auth.md             # Authentifizierung & Benutzerverwaltung
│   ├── time-tracking.md    # Zeiterfassung
│   ├── absences.md         # Abwesenheitsverwaltung
│   ├── reports.md          # Berichte & Export
│   ├── dashboard.md        # Dashboard (MA + Admin)
│   ├── holidays.md         # Feiertage & Betriebsferien
│   └── notifications.md    # Benachrichtigungen & Warnungen
├── dsgvo/                  # Datenschutz-Dokumentation
│   ├── dsgvo-report.html   # DSGVO-Prüfbericht (alle Findings behoben)
│   ├── dsfa.md             # Datenschutz-Folgenabschätzung (Art. 35)
│   ├── verarbeitungsverzeichnis.md  # Verarbeitungsverzeichnis (Art. 30)
│   └── vier-augen-prinzip.md        # 4-Augen-Prinzip Richtlinie
└── arbzg/                  # Arbeitszeitgesetz-Compliance
    ├── arbzg-compliance.html  # ArbZG-Prüfbericht
    └── arbzg-compliance.md   # ArbZG-Implementierungsdokumentation
```

---

## Workflow: Neues Feature mit SDD

### 1. Spec erstellen
```bash
cp specs/TEMPLATE.md specs/features/mein-feature.md
```

Felder ausfüllen:
- **Requirements**: Was soll das Feature leisten? (Nutzer-Perspektive)
- **Design**: Technische Umsetzung – welche Dateien, Endpunkte, Datenbank-Änderungen?
- **Tasks**: Konkrete, abhakbare Aufgaben (Migration → Backend → Frontend → Tests)

### 2. Spec mit AI umsetzen
Die fertige Spec als Prompt an Claude übergeben:
```
Implementiere das Feature gemäß specs/features/mein-feature.md
Halte dich an die technischen Entscheidungen im Design-Abschnitt.
Beginne mit den Tasks in der angegebenen Reihenfolge.
```

### 3. Spec nach Implementierung aktualisieren
Falls sich während der Umsetzung Abweichungen ergeben:
- Spec anpassen (nicht den Code)
- Neue Erkenntnisse dokumentieren
- Status-Marker in Tasks aktualisieren (`[ ]` → `[x]`)

---

## Spec-Qualitätskriterien

Eine gute Spec ist:

- **Behavior-orientiert**: Beschreibt Verhalten aus Nutzersicht, nicht Implementierung
- **Vollständig**: Alle Akzeptanzkriterien sind messbar
- **Unabhängig**: Kann ohne Kenntnis des Codes verstanden werden
- **Aktuell**: Spiegelt den tatsächlichen Stand der Implementierung wider

---

## Konventionen für PraxisZeit

### Statusmarker
```markdown
- [ ] Ausstehend
- [x] Erledigt
- [~] Teilweise erledigt / In Arbeit
- [!] Blockiert / Problem
```

### Endpunkt-Notation
```
GET /api/resource          → Lesen
POST /api/resource         → Erstellen
PUT /api/resource/{id}     → Vollständig ersetzen
PATCH /api/resource/{id}   → Teilweise aktualisieren
DELETE /api/resource/{id}  → Löschen
```

### Migrations-Konvention
Migrations-Dateien: `backend/alembic/versions/YYYY_MM_DD_HHMM-NNN_beschreibung.py`

---

## Bestehende Features

Alle bestehenden Features sind rückwirkend als Specs dokumentiert:

| Feature | Spec-Datei | Status |
|---------|-----------|--------|
| Authentifizierung | `features/auth.md` | Spec-anchored |
| Zeiterfassung | `features/time-tracking.md` | Spec-anchored |
| Abwesenheiten | `features/absences.md` | Spec-anchored |
| Berichte & Export | `features/reports.md` | Spec-anchored |
| Dashboard | `features/dashboard.md` | Spec-anchored |
| Feiertage | `features/holidays.md` | Spec-anchored |
| Warnungen | `features/notifications.md` | Spec-anchored |
