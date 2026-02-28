# F-011 – 4-Augen-Prinzip

**Status:** Organisatorische Richtlinie (kein Code-Change erforderlich)
**Kategorie:** Datenschutz / Interne Governance

---

## Risikobeschreibung

PraxisZeit verfügt über ein rollenbasiertes Berechtigungssystem mit zwei Rollen:

- **Employee** – kann eigene Zeiteinträge und Abwesenheiten verwalten
- **Admin** – hat Vollzugriff auf alle Mitarbeiterdaten, Berichte, Exporte und Systemeinstellungen

Ein einzelner Admin-Benutzer hat technisch die Möglichkeit, alle Daten einzusehen, zu ändern und zu exportieren – ohne dass eine zweite Person dies kontrolliert.

---

## Empfehlung: 2-Admin-Struktur

Für Praxen mit mehr als 3 Mitarbeitern wird empfohlen, mindestens zwei Admin-Konten zu führen:

1. **Primärer Admin** (z. B. Praxisinhaber:in)
2. **Sekundärer Admin** (z. B. Praxismanager:in oder Steuerberater:in)

Beide Admins sollten regelmäßig den **Audit-Log** (`/admin/audit-log`) prüfen, um ungewöhnliche Änderungen zu erkennen.

---

## Kompensationsmaßnahmen im System

PraxisZeit bietet folgende technische Maßnahmen als Ersatz für ein formales 4-Augen-Prinzip:

| Maßnahme | Beschreibung |
|----------|-------------|
| **Audit-Log** | Alle Änderungen an Zeiteinträgen werden mit User, Zeitstempel und alten/neuen Werten protokolliert |
| **Token-Versionierung** | Alle JWT-Tokens werden bei Passwortänderung sofort ungültig |
| **Rate Limiting** | Login-Versuche auf 5/Minute begrenzt |
| **Passwort-Komplexität** | Mindestens 10 Zeichen + Groß-/Kleinbuchstaben + Ziffer |
| **Optionale 2FA** | TOTP-basierte Zwei-Faktor-Authentifizierung für alle Benutzer verfügbar (F-019) |

---

## Empfohlene organisatorische Maßnahmen

1. **Passwörter nicht teilen** – Jeder Admin hat ein eigenes Passwort
2. **Regelmäßige Audit-Log-Prüfung** – Mindestens monatlich
3. **2FA aktivieren** – Für Admin-Konten wird die Aktivierung von TOTP-2FA dringend empfohlen
4. **Übergabe-Protokoll** – Bei Personalwechsel: sofortige Deaktivierung des alten Kontos und Passwortänderung
5. **Minimalprinzip** – Nur Personen, die Admin-Rechte benötigen, erhalten diese

---

## DSGVO-Relevanz

Gemäß **Art. 5 Abs. 1 lit. f DSGVO** (Integrität und Vertraulichkeit) sind technische und organisatorische Maßnahmen erforderlich, um unbefugten Zugang zu personenbezogenen Daten zu verhindern. Die oben beschriebenen Maßnahmen dienen als TOMs im Sinne des Art. 32 DSGVO.

Für die vollständige Verarbeitungsübersicht siehe: `specs/verarbeitungsverzeichnis.md`
