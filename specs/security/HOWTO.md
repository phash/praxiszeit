# Security Audit – Durchführung

## Wann durchführen?

- Vor jedem Produktions-Release
- Nach größeren Feature-Implementierungen (Auth, Datei-Upload, neue API-Endpunkte)
- Nach Abhängigkeits-Updates (npm, pip)
- Nach Infrastruktur-Änderungen (Docker, nginx, CORS)
- Mindestens **alle 6 Monate**

---

## Wie wird der Audit erstellt?

### 1. Audit-Prompt an Claude

```
Führe einen vollständigen Security-Audit des PraxisZeit-Projekts durch.
Prüfe systematisch alle OWASP Top 10 Kategorien sowie:
- Authentifizierung & Token-Sicherheit (JWT, Refresh-Token, HttpOnly Cookies)
- Autorisierung & RBAC (Admin vs. Employee)
- Input-Validierung & Injection (SQL, XSS, Path Traversal)
- Passwort-Sicherheit (Hashing, Komplexität, Brute-Force-Schutz)
- Session-Management & CSRF
- Security Headers (CSP, HSTS, X-Frame-Options)
- Abhängigkeiten (bekannte CVEs in requirements.txt und package.json)
- Konfiguration (CORS, Secrets, Environment-Variablen)
- Fehlerbehandlung (keine sensitiven Daten in Error-Responses)
- API-Sicherheit (Rate Limiting, Authentifizierung aller Endpunkte)
- Infrastruktur (Docker, nginx, non-root Container)

Erstelle einen vollständigen HTML-Bericht mit:
- Executive Summary (Verdict, KPI-Grid mit Anzahl pro Schweregrad)
- Alle Findings mit ID (S-001...), Schweregrad, Beschreibung, Fundstelle, Risiko, Empfehlung
- OWASP-Mapping
- Positiv-Befunde
- Priorisierte Maßnahmen-Liste
```

### 2. Findings implementieren

Jeden Fund aus dem Bericht beheben. Bei jedem Finding die Fundstelle im Code aufsuchen und die Empfehlung umsetzen.

### 3. Aktualisierten Report erzeugen ← PFLICHT

Nach Implementierung **aller** Findings einen neuen Bericht erstellen:

```
Der Security-Audit vom [DATUM] wurde vollständig implementiert.
Aktualisiere den Bericht specs/security/security-audit-report-[DATUM].html:
- Alle behobenen Findings mit grünem "Behoben"-Badge markieren
- Executive Summary: Verdict auf "VOLLSTÄNDIG KONFORM" setzen
- KPI-Grid: offene Findings auf 0 setzen, "Behoben"-Zähler aktualisieren
- Maßnahmen-Liste: alle Prioritäten auf "Erledigt" setzen
```

### 4. Dateiname-Konvention

```
security-audit-report-YYYY-MM-DD.html   ← ein Bericht pro Audit-Zyklus
```

Der initiale (offene) Bericht und der aktualisierte (behobene) Bericht sind **eine Datei** — der Bericht wird nach Behebung aktualisiert, nicht neu angelegt.

---

## Enthaltene Berichte

| Datei | Beschreibung | Status |
|-------|-------------|--------|
| `security-audit-report-initial.html` | Erster Audit (2026-02-20) | 23 Findings identifiziert |
| `security-audit-report-2026-02-28.html` | Zweiter Audit (2026-02-28) | Alle Findings behoben ✓ |
