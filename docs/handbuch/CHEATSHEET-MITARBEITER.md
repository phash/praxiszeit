# PraxisZeit – Kurzanleitung Mitarbeiter

---

## Anmelden
**URL:** `https://[Server-Adresse]/login`
Beim ersten Aufruf evtl. Zertifikat-Warnung → „Erweitert" → „Weiter zu …".
Benutzernamen + Passwort eingeben → **Anmelden**

---

## Navigation
**Desktop (linke Leiste):** Dashboard · Zeiterfassung · Abwesenheiten · Profil

**Mobil (unten):** Home · Journal · Abwes. · Profil
**Mobil-Menü:** ☰ (oben rechts) öffnet vollständige Navigation

---

## Zeiterfassung (tägliche Aufgabe)

### Schnell ein-/ausstempeln
**Dashboard → Einstempeln** startet die Zeit live; später **Ausstempeln** beendet
sie und speichert den Eintrag automatisch. Alternativ Zeiten manuell erfassen:

### Pause beim Ausstempeln
Beim **Ausstempeln** Feld **Pause (Min.)** ausfüllen → **Jetzt ausstempeln**.
- Bei **mehr als 6 h** verlangt das Gesetz eine Pause (§4 ArbZG).
- Reicht die Pause nicht → gelber Hinweis. Zwei Wege:
  1. **Pause nachtragen** (Minuten korrigieren), oder
  2. **kurz begründen**, warum keine Pause möglich war (z. B. „Notfall, keine Vertretung") → **dokumentierte Ausnahme**
- Erst danach ist das Ausstempeln fertig (flüchtiger Hinweis reicht nicht mehr).

### Neuen Zeiteintrag erstellen
**Zeiterfassung** → Tab **Einträge** → **+ Neuer Eintrag**
- Datum, Startzeit (Von), Endzeit (Bis)
- Pause in Minuten *(Pflicht!)*
- Optional: Notiz
- **Speichern**

Mobil: **+**-Button oben rechts auf der Zeiterfassungsseite

### Eintrag bearbeiten / löschen
Aktionsspalte in der Einträge-Tabelle:
- **Bearbeiten** – bei entsperrten Einträgen
- **Löschen** – bei nicht gesperrten Einträgen

### Pflicht-Pausen (§4 ArbZG)
| Arbeitszeit | Mindestpause |
|-------------|-------------|
| > 6 Stunden | **30 Minuten** |
| > 9 Stunden | **45 Minuten** |

### Tagesgrenze (§3 ArbZG)
- Warnung ab **8 Stunden** Nettoarbeitszeit
- Ab **10 Stunden** netto: manuelle Eingabe gesperrt; Live-Ausstempeln nur Warnung (Zeit ist bereits geleistet)

### Soll-Arbeitszeit-Fenster
*Nur aktiv, wenn die Praxis für Sie Soll-Zeiten hinterlegt hat – sonst zählt alles wie gewohnt.*
- Zu früh ein- / zu spät ausgestempelt → angerechnet wird nur bis zum **Puffer** (Std. 15 Min.).
- Hinweis z. B. *„gestempelt 07:30 · angerechnet ab 07:45"*.
- Ihre **echte Stempelzeit bleibt gespeichert** (§16 ArbZG); fürs Stundenkonto zählt nur die angerechnete Zeit.

---

## Korrekturantrag stellen

Wenn ein Eintrag gesperrt / zu alt ist:

**Zeiterfassung → Tab Einträge** → Zeile des Eintrags → **Änderungsantrag**-Button
1. Korrekte Zeiten eintragen
2. Begründung schreiben
3. **Antrag stellen**

Für Löschung: **Löschantrag**-Button → Begründung → Bestätigen

**Pflicht-Pause nicht möglich?** Erfüllen die korrigierten Zeiten die Pausenregel nicht, wird der Antrag nicht abgelehnt: Zusatzfeld **„Begründung"** ausfüllen (z. B. „Notfall, keine Vertretung") → **Mit dokumentierter Ausnahme senden**. Die Abweichung geht zur Genehmigung an den Admin.

---

## Anträge einsehen

**Zeiterfassung → Tab Anträge**

| Status | Bedeutung |
|--------|-----------|
| Offen | Wartet auf Admin-Entscheidung |
| Genehmigt | Angenommen, Eintrag korrigiert |
| Abgelehnt | Abgelehnt – Begründung sichtbar |

Filter: Alle / Offen / Genehmigt / Abgelehnt
Zurückziehen: Button **Zurückziehen** bei offenen Anträgen

---

## Abwesenheiten

**Abwesenheiten → + Abwesenheit eintragen**

| Schritt | Aktion |
|---------|--------|
| Typ wählen | Urlaub / Krank / Fortbildung / Sonstiges |
| Einzeltag | Nur Startdatum |
| Zeitraum | Checkbox „Zeitraum" + Enddatum |
| Speichern | Wochenenden/Feiertage werden übersprungen |

> **Eigene Gründe:** Richtet Ihre Praxis weitere Gründe ein (z. B. „Schule"), erscheinen sie bei „Typ wählen" unter **„Eigene Gründe"**.

**Löschen:** Kalender-Eintrag anklicken → Löschen-Symbol

### Sondertage 24./31.12.
Hat Ihre Praxis Heiligabend / Silvester als frei oder halben Tag eingestellt, sind diese im Kalender markiert (z. B. „Heiligabend (frei)" / „Silvester (½ Tag)") – wie ein Feiertag.

### Bei aktiver Urlaubsgenehmigungspflicht
- Urlaub-Speichern → **Antrag** (kein direkter Eintrag)
- Tab **„Meine Anträge"** zeigt Status
- Offene Anträge können zurückgezogen werden

### Urlaubsberechnung
- **1 freier Arbeitstag = 1 Urlaubstag** (egal wie viele Stunden der Tag hat)
- Freie Woche = Anzahl Ihrer Arbeitstage; Konto zeigt Resttage

---

## Dashboard verstehen

| Karte | Bedeutung |
|-------|----------|
| **Tagessaldo** | Heute: Ist-Zeit vs. Tagessoll (grün = eingestempelt) |
| **Monatssaldo** | Über-/Unterstunden diesen Monat (H:MM) |
| **Überstunden** | Kumulierter Jahressaldo |
| **Urlaub** | Verbleibende Urlaubstage |

**Grüner Saldo (+)** = Überstunden · **Roter Saldo (–)** = Fehlstunden

*Monatssaldo und Überstunden zählen nur bis zum letzten abgeschlossenen Arbeitstag (kein Monatsanfangs-Minus am 1.).*

---

## Ohne Stundenzählung

Für manche Mitarbeitende führt die Praxis **keine Stundenzählung**:
- Kein Soll/Ist, keine Überstunden, kein Stempel-Button → Kacheln Tagessaldo / Monatssaldo / Überstunden fehlen.
- **Urlaub & Krank werden trotzdem geführt** – tagebasiert (1 freier Arbeitstag = 1 Tag). Urlaubskonto bleibt sichtbar.
- Das ist eine bewusste Einstellung Ihrer Praxis, **kein Fehler**.

---

## Passwort ändern

**Profil → Passwort ändern → Ändern**
- Altes Passwort eingeben
- Neues Passwort: **min. 10 Zeichen** + Groß- + Kleinbuchstabe + Ziffer
- Bestätigen → **Speichern**

---

## Zwei-Faktor-Authentifizierung (2FA)

Zusätzlicher Schutz per Einmal-Code aus einer Authenticator-App (z. B. Google Authenticator, Authy).

**Aktivieren:** Profil → Karte „Zwei-Faktor-Authentifizierung" → **2FA aktivieren** → aktuelles **Passwort** bestätigen → QR-Code scannen (oder Schlüssel manuell eintragen) → 6-stelligen Code eingeben → **Bestätigen**
**Login:** Benutzername + Passwort → danach **6-stelligen Code** aus der App
**Deaktivieren:** **2FA deaktivieren** → aktuelles **Passwort** bestätigen
> App/Handy verloren? → Administrator kontaktieren

---

## Häufige Probleme

| Problem | Lösung |
|---------|--------|
| Pause zu kurz beim Ausstempeln | Pause nachtragen **oder** kurz begründen (dokumentierte Ausnahme) |
| Zeiteintrag zu lang | Max. 10h netto (§3 ArbZG) |
| Eintrag lässt sich nicht bearbeiten | Zu alt → Änderungsantrag stellen |
| „angerechnet ab HH:MM" beim Eintrag | Soll-Zeit-Fenster: nur bis Puffer angerechnet (echte Zeit bleibt) |
| Stunden-/Überstundenkacheln fehlen | Kein Fehler – bei Ihnen ohne Stundenzählung |
| Gelber Hinweis unter „Überstundenkonto" | Minijob-Arbeitszeitkonto (§ 2 Abs. 2 MiLoG): Konto zu weit im Plus oder Ausgleichsfrist läuft bald ab – kein Fehler, im Zweifel mit Admin klären |
| Passwort vergessen | Administrator kontaktieren |

---

## Ihr Admin-Kontakt

**Name:** ____________________________

**E-Mail / Telefon:** ____________________________

---

## Schichtplan (falls aktiv)

- Menü **Schichtplan**: sichtbare Wochenpläne ansehen (wer wann wo) – heute geltende **und** vom Admin freigegebene, aktuell nicht geltende Pläne; alle heute geltenden Pläne stehen untereinander, freigegebene übrige Pläne zusätzlich in einer Vorschau-Auswahl mit Vorschau-Hinweis.
- Hinweis an einer Einteilung erkennbar am **»**; Knopf **„PDF"** druckt den angezeigten Plan. Bei mehreren Standorten steht der Standort in der Kopfzeile (einheitlich) oder hinter dem Arbeitsplatznamen (gemischt).
- **Dashboard → „Deine Einteilung heute"**: Ihre heutigen Einsätze mit Zeit.
- Nur Planung – ändert **nicht** Ihre Arbeitszeiten/Urlaub/Überstunden. Einteilung macht der Admin.

---

*PraxisZeit · Zeiterfassung nach ArbZG · [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
