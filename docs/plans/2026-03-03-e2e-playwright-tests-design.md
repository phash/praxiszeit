# E2E Playwright Tests - Design Document

**Datum:** 2026-03-03
**Status:** Approved
**Scope:** Vollstaendige User-Story-Uebersicht + E2E-Tests fuer PraxisZeit

---

## 1. Ziel

Erstelle eine vollstaendige E2E-Testsuite mit Playwright, die alle Features der PraxisZeit-Anwendung in beiden Rollen (Employee + Admin) abdeckt. Die Tests laufen gegen die laufende Docker-Instanz (localhost).

## 2. Entscheidungen

| Aspekt | Entscheidung |
|--------|-------------|
| Test-Setup | Gegen laufendes Docker (localhost:80 Frontend, localhost:8000 Backend) |
| Test-Tiefe | Umfassend: Happy-Path + Fehlerfaelle + Rollenabgrenzung (~85 Tests) |
| Testdaten | Fixture-basiert (API-Setup/Teardown pro Test) |
| Verzeichnis | `praxiszeit/e2e/` |
| Architektur | Feature-basierte Test-Suites (kein Page-Object-Pattern) |

## 3. Projektstruktur

```
praxiszeit/e2e/
  playwright.config.ts
  package.json
  fixtures/
    auth.fixture.ts           # Login-Helper, adminPage/employeePage
    test-data.fixture.ts      # API-Factories: createTestUser, createTimeEntry, createAbsence
    base.fixture.ts           # Merged fixture als erweiterter test-Export
  helpers/
    api.helper.ts             # HTTP-Client fuer direkte API-Aufrufe
    date.helper.ts            # Datums-Utilities
  tests/
    auth/
      login.spec.ts
      logout.spec.ts
      password.spec.ts
    employee/
      dashboard.spec.ts
      time-tracking.spec.ts
      absences.spec.ts
      change-requests.spec.ts
      profile.spec.ts
    admin/
      user-management.spec.ts
      time-entries.spec.ts
      change-requests.spec.ts
      reports.spec.ts
      absences.spec.ts
      audit-log.spec.ts
      error-monitoring.spec.ts
      vacation-approvals.spec.ts
    shared/
      navigation.spec.ts
      help.spec.ts
```

## 4. Rollen

| Rolle | Beschreibung | Test-User |
|-------|-------------|-----------|
| **Employee** | Normaler Mitarbeiter, Zugriff nur auf eigene Daten | Per Fixture erstellt |
| **Admin** | Vollzugriff, Benutzerverwaltung, Reports, Audit | `admin` / `Admin2025!` |

## 5. Fixtures-Konzept

### auth.fixture.ts
- `adminPage`: Playwright Page eingeloggt als Admin (bestehender admin-User)
- `employeePage`: Playwright Page eingeloggt als Test-Employee (per API erstellt)
- Login via API (`POST /api/auth/login`), Token im localStorage setzen

### test-data.fixture.ts
- `createTestUser(data)` → erstellt User per Admin-API, gibt User + Cleanup-Funktion zurueck
- `createTimeEntry(userId, data)` → erstellt Zeiteintrag per API
- `createAbsence(userId, data)` → erstellt Abwesenheit per API
- `createChangeRequest(data)` → erstellt Korrekturantrag
- Automatisches Teardown: alle erstellten Ressourcen werden nach dem Test geloescht

### base.fixture.ts
- Exportiert erweitertes `test` und `expect` mit allen Fixtures kombiniert

## 6. User Stories & Testfaelle

### 6.1 AUTH (8 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 1 | MA loggt sich ein | Login → Dashboard sichtbar | P0 |
| 2 | Falsche Credentials | Falsches PW → Fehlermeldung | P0 |
| 3 | Leere Felder | Ohne Daten → Validierungsfehler | P1 |
| 4 | MA loggt sich aus | Logout → Redirect auf Login | P0 |
| 5 | Session nach Logout ungueltig | Geschuetzte Seite nicht erreichbar | P1 |
| 6 | Passwort aendern | Altes PW → Neues PW → Login mit neuem PW | P0 |
| 7 | Passwortkomplexitaet | Zu einfaches PW → Fehler | P1 |
| 8 | Falsches altes Passwort | Falsches aktuelles PW → Fehler | P1 |

### 6.2 EMPLOYEE: Dashboard (6 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 9 | Monatssaldo sehen | Soll/Ist/Saldo-Karte sichtbar | P0 |
| 10 | Ueberstundenkonto | Kumulative Ueberstunden angezeigt | P1 |
| 11 | Urlaubskonto | Budget/Verbraucht/Verbleibend | P0 |
| 12 | Ein-/Ausstempeln | StampWidget → Einstempeln → Ausstempeln → Eintrag | P0 |
| 13 | Monatsuebersicht | Tabelle mit Historie | P1 |
| 14 | Team-Abwesenheiten | Kalender mit Team-Abwesenheiten | P2 |

### 6.3 EMPLOYEE: Zeiterfassung (10 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 15 | Eintrag erstellen | Datum/Start/Ende/Pause → in Tabelle | P0 |
| 16 | Eintrag bearbeiten | Edit → aendern → neue Werte | P0 |
| 17 | Eintrag loeschen | Delete → Confirm → weg | P0 |
| 18 | Ende vor Start | Validierungsfehler | P1 |
| 19 | Monatsnavigation | Vor/Zurueck → anderer Monat | P1 |
| 20 | ArbZG §3 Warnung >8h | Warnung angezeigt | P0 |
| 21 | ArbZG §3 Block >10h | Fehler, nicht gespeichert | P0 |
| 22 | ArbZG §4 Pausenwarnung | >6h ohne 30min Pause → Warnung | P1 |
| 23 | Gesperrte Eintraege | Kein Edit/Delete moeglich | P0 |
| 24 | Aenderungsantrag stellen | Formular oeffnet sich, Antrag erstellt | P0 |

### 6.4 EMPLOYEE: Abwesenheiten (7 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 25 | Urlaubstag erstellen | Datum + "Urlaub" → angelegt | P0 |
| 26 | Mehrtaegige Abwesenheit | Zeitraum → nur Werktage | P0 |
| 27 | Abwesenheit loeschen | Loeschen → Confirm → entfernt | P0 |
| 28 | Kalender zeigt Abwesenheiten | Farbige Markierungen | P1 |
| 29 | Monats-/Jahresansicht | Toggle funktioniert | P1 |
| 30 | Krankheit waehrend Urlaub | Ueberlappung → Erstattungsoption | P2 |
| 31 | Verschiedene Typen | Urlaub/Krank/Fortbildung/Sonstiges | P1 |

### 6.5 EMPLOYEE: Korrekturantraege (5 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 32 | Aenderungsantrag erstellen | Antrag → Status "Offen" | P0 |
| 33 | Loeschantrag erstellen | Typ "Loeschen" sichtbar | P1 |
| 34 | Statusfilter | Tabs filtern korrekt | P1 |
| 35 | Antrag zurueckziehen | Zurueckziehen → Confirm | P0 |
| 36 | Ablehnungsgrund sichtbar | Nach Ablehnung → Grund angezeigt | P1 |

### 6.6 EMPLOYEE: Profil (5 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 37 | Profildaten sehen | Name, Username, Rolle etc. | P0 |
| 38 | Namen bearbeiten | Aendern → Speichern → aktualisiert | P1 |
| 39 | Kalenderfarbe aendern | Farbe waehlen → gespeichert | P2 |
| 40 | DSGVO-Datenexport | Download startet | P1 |
| 41 | Passwort aus Profil aendern | Neues PW → funktioniert | P1 |

### 6.7 ADMIN: Benutzerverwaltung (8 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 42 | Benutzerliste | Tabelle sichtbar | P0 |
| 43 | Benutzer erstellen | Formular → User in Liste | P0 |
| 44 | Benutzer bearbeiten | Wochenstunden aendern | P0 |
| 45 | Benutzer deaktivieren | Deaktivieren → "Inaktiv" | P0 |
| 46 | Benutzer reaktivieren | Reaktivieren → "Aktiv" | P1 |
| 47 | Passwort zuruecksetzen | Neues PW → Login moeglich | P0 |
| 48 | User ausblenden | Toggle Hidden | P2 |
| 49 | Suchfilter | Suche + Status-Filter | P1 |

### 6.8 ADMIN: Zeiteintraege (4 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 50 | Eintrag fuer MA erstellen | Eintrag → in MA-Zeiterfassung | P0 |
| 51 | Eintrag bearbeiten | Admin editiert → neue Werte | P1 |
| 52 | Eintrag loeschen | Admin loescht → entfernt | P1 |
| 53 | Audit-Log geschrieben | Aktion → Log-Eintrag | P0 |

### 6.9 ADMIN: Korrekturantraege (4 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 54 | Offene Antraege sehen | Liste mit Status-Filter | P0 |
| 55 | Antrag genehmigen | Genehmigen → Eintrag angepasst | P0 |
| 56 | Antrag ablehnen | Ablehnen + Grund → Status geaendert | P0 |
| 57 | Vergleichsansicht | Alt vs. Neu dargestellt | P1 |

### 6.10 ADMIN: Berichte (6 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 58 | Excel-Monatsexport | Download startet | P0 |
| 59 | ODS-Monatsexport | Download startet | P1 |
| 60 | PDF-Monatsexport | Download startet | P1 |
| 61 | Jahresexport | Classic + Detailliert Download | P1 |
| 62 | ArbZG Ruhezeitpruefung | Report → Ergebnistabelle | P0 |
| 63 | ArbZG Sonntagsarbeit | Report → Ergebnisse | P1 |

### 6.11 ADMIN: Abwesenheiten & Betriebsferien (5 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 64 | Abwesenheit fuer MA erstellen | User waehlen → anlegen | P0 |
| 65 | Abwesenheit loeschen | Loeschen → entfernt | P1 |
| 66 | Betriebsferien anlegen | Name + Zeitraum → auto-Abwesenheiten | P0 |
| 67 | Betriebsferien loeschen | Loeschen → auto-Abwesenheiten entfernt | P1 |
| 68 | Tab-Wechsel | MA-Abwesenheiten / Betriebsferien | P1 |

### 6.12 ADMIN: Audit-Log (3 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 69 | Aenderungen sichtbar | Eintraege mit Timestamp, Aktion | P0 |
| 70 | Monatsfilter | MonthSelector → gefiltert | P1 |
| 71 | Benutzerfilter | User-Dropdown → gefiltert | P1 |

### 6.13 ADMIN: Fehler-Monitoring (4 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 72 | Fehlerliste sehen | Fehler mit Severity etc. | P0 |
| 73 | Status aendern | Behoben/Ignoriert | P1 |
| 74 | Fehler loeschen | Loeschen → entfernt | P1 |
| 75 | Statusfilter | Tabs filtern korrekt | P1 |

### 6.14 ADMIN: Urlaubsantraege (5 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 76 | Toggle Genehmigungspflicht | Setting aendern | P0 |
| 77 | MA-Antrag wird Antrag | Bei Pflicht → Status "Offen" | P0 |
| 78 | Admin genehmigt | Genehmigen → Abwesenheiten erstellt | P0 |
| 79 | Admin lehnt ab | Ablehnen + Grund | P0 |
| 80 | MA zieht zurueck | Zurueckziehen → entfernt | P1 |

### 6.15 SHARED (5 Tests)

| # | User Story | Testfall | Prio |
|---|-----------|----------|------|
| 81 | Rollenbasierte Navigation | MA keine Admin-Links | P0 |
| 82 | Admin-Seiten geschuetzt | MA → /admin → Redirect | P0 |
| 83 | Mobile Hamburger-Menu | Kleiner Viewport → Menu | P1 |
| 84 | Hilfe-Seite | Tabs + Accordion | P2 |
| 85 | Datenschutzerklaerung | /privacy laedbar | P2 |

## 7. Zusammenfassung

| Kategorie | Spec-Datei | Anzahl Tests |
|-----------|-----------|-------------|
| Auth | 3 Dateien | 8 |
| Employee: Dashboard | 1 | 6 |
| Employee: Zeiterfassung | 1 | 10 |
| Employee: Abwesenheiten | 1 | 7 |
| Employee: Korrekturantraege | 1 | 5 |
| Employee: Profil | 1 | 5 |
| Admin: Benutzerverwaltung | 1 | 8 |
| Admin: Zeiteintraege | 1 | 4 |
| Admin: Korrekturantraege | 1 | 4 |
| Admin: Berichte | 1 | 6 |
| Admin: Abwesenheiten | 1 | 5 |
| Admin: Audit-Log | 1 | 3 |
| Admin: Fehler-Monitoring | 1 | 4 |
| Admin: Urlaubsantraege | 1 | 5 |
| Shared | 2 | 5 |
| **Gesamt** | **17 Dateien** | **85 Tests** |

**Prioritaetsverteilung:**
- P0 (Critical Path): 38 Tests
- P1 (Important): 35 Tests
- P2 (Nice-to-have): 12 Tests
