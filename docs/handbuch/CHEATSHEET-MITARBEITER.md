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

## Häufige Probleme

| Problem | Lösung |
|---------|--------|
| Pause zu kurz beim Ausstempeln | Pause nachtragen **oder** kurz begründen (dokumentierte Ausnahme) |
| Zeiteintrag zu lang | Max. 10h netto (§3 ArbZG) |
| Eintrag lässt sich nicht bearbeiten | Zu alt → Änderungsantrag stellen |
| „angerechnet ab HH:MM" beim Eintrag | Soll-Zeit-Fenster: nur bis Puffer angerechnet (echte Zeit bleibt) |
| Stunden-/Überstundenkacheln fehlen | Kein Fehler – bei Ihnen ohne Stundenzählung |
| Passwort vergessen | Administrator kontaktieren |

---

## Ihr Admin-Kontakt

**Name:** ____________________________

**E-Mail / Telefon:** ____________________________

---

*PraxisZeit · Zeiterfassung nach ArbZG · [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
