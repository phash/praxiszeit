# PraxisZeit – Schnellstart für Admins

**In 10 Minuten von der Installation zur laufenden Zeiterfassung.** Diese Kurzanleitung führt durch die ersten Schritte als Administrator. Details stehen im [Admin-Handbuch](HANDBUCH-ADMIN.md).

---

## 0. Anmelden

Öffnen Sie PraxisZeit im Browser (`https://<server-adresse>`) und melden Sie sich mit den **Admin-Zugangsdaten** an, die bei der Installation gesetzt wurden.

> Beim ersten Aufruf erscheint evtl. eine Zertifikatswarnung (selbstsigniertes Zertifikat) → **„Erweitert" → „Weiter zu …"**. Einmalig pro Gerät.

**Passwort sofort ändern:** Profil (unten links) → *Passwort ändern*.

---

## 1. Praxis konfigurieren (Einstellungen)

**Einstellungen** (Zahnrad in der Navigation) – einmalig festlegen:

| Einstellung | Was tun |
|-------------|---------|
| **Bundesland** | Für die automatischen Feiertage (z. B. Bayern) |
| **Urlaubsgenehmigung** | An, wenn Urlaub erst vom Admin freigegeben werden soll; aus = Mitarbeiter buchen direkt |
| **Sondertage 24./31.12.** | Heiligabend / Silvester als *frei* oder *halber Tag* markieren |
| **Onboarding-Tour** | Willkommens-Tour für neue Nutzer (Standard: **an**) |

---

## 2. Mitarbeiter anlegen

**Benutzerverwaltung → „Neue:r Mitarbeiter:in"** – pro Person:

1. **Benutzername** + **Passwort** (Startpasswort, Mitarbeiter ändert es selbst)
2. **Vor- / Nachname**, optional E-Mail
3. **Wochenstunden** (z. B. 40 für Vollzeit, 20 für Teilzeit)
4. **Arbeitstage** bzw. – bei ungleichmäßiger Verteilung – **Tagesplan** (Stunden je Wochentag)
5. **Urlaubsanspruch** (Tage/Jahr)
6. **Speichern**

**Sonderfälle:**
- **Leitende Angestellte ohne Stundenzählung:** Häkchen *„Keine Stundenzählung"* (`track_hours=False`) – Urlaub/Krank werden trotzdem tagebasiert geführt.
- **Ein-/Austritt:** *Erster/Letzter Arbeitstag* setzen – außerhalb zählt kein Soll.
- **Soll-Arbeitszeit-Fenster (optional):** Soll-Beginn/-Ende je Wochentag, wenn früh-/spät-Stempel auf das Soll begrenzt werden sollen.
- **Spätere Änderungen:** Wochenstunden, Tagesplan, Modus (gleichmäßig/Tagesplan) und Arbeitstage lassen sich nach dem Anlegen nur noch über den Button „Wochenstunden anpassen…" mit Wirkungsdatum ändern – direkt im Formular sind diese Felder dann nur noch Anzeige (siehe [Admin-Handbuch](HANDBUCH-ADMIN.md#mitarbeiter-bearbeiten)).

---

## 3. Erste Zeiterfassung prüfen

- Mitarbeiter melden sich an und **stempeln** (Dashboard → *Einstempeln* / *Ausstempeln* mit Pauseneingabe) **oder** tragen Zeiten manuell ein (*Zeiterfassung → + Neuer Eintrag*).
- Das **Admin-Dashboard** zeigt Team-Stunden, Salden und fehlende Buchungen.

---

## 4. Laufender Betrieb

| Aufgabe | Wo |
|---------|-----|
| **Korrekturanträge** prüfen/freigeben | Admin → Änderungsanträge |
| **Urlaubsanträge** genehmigen | Admin → Urlaubsanträge (bei aktiver Genehmigungspflicht) |
| **Berichte & Excel-Export** | Admin → Berichte (Monat/Jahr, ArbZG-Reports) |
| **Betriebsferien** | Einstellungen → Betriebsferien (gilt für teilnehmende MA) |

---

## 5. Pflichten nicht vergessen (§16 ArbZG)

- **Zeitaufzeichnungen 2 Jahre aufbewahren** – sorgen Sie für **Backups** (Docker: DB-Dump; nativ: tägliches Backup läuft automatisch).
- Über **10 h** Nettoarbeitszeit ist gesperrt, ab **8 h** kommt eine Warnung; Pflichtpausen ab 6 h / 9 h.

---

## Hilfe

- **Cheat-Sheet** + **Admin-Handbuch**: unten links in der Seitenleiste (Button „Schnellstart" / „Cheat-Sheet" / „Admin-Handbuch") oder über **Hilfe**.
- Vollständige Doku: [HANDBUCH-ADMIN.md](HANDBUCH-ADMIN.md) · [CHEATSHEET-ADMIN.md](CHEATSHEET-ADMIN.md)

---

*PraxisZeit · Zeiterfassung nach ArbZG · [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
