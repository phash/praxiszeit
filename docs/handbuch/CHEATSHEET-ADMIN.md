# PraxisZeit – Kurzanleitung Administrator

---

## Login & Navigation
**URL:** `https://[Server-Adresse]/login` (beim ersten Aufruf Zertifikat-Warnung „Erweitert → Weiter zu …" bestätigen)

**Mitarbeiter-Bereich:** Dashboard · Zeiterfassung · Abwesenheiten · Profil

**Administration:** Admin-Dashboard · Benutzerverwaltung · Änderungsanträge · Berichte · Abwesenheiten · Änderungsprotokoll · Fehler-Monitoring · Anträge · Import · Einstellungen

> **Neu hier?** Der **Schnellstart** (Button unten links in der Seitenleiste) führt in wenigen Minuten durch die Ersteinrichtung der Praxis.

---

## Benutzerverwaltung

### Neuen Mitarbeiter anlegen
**Benutzerverwaltung** → **Neuer Mitarbeiter:in**
- Benutzername (Login-Name), Passwort (mind. 10 Zeichen)
- Vorname / Nachname, E-Mail (optional)
- Wochenstunden, Arbeitstage/Woche, Urlaubstage
- Rolle: Mitarbeiter:in oder Admin
- Optional: **Stundenzählung aktiv** (s. u.), **ArbZG-Prüfungen aussetzen (§18)** (separate Checkbox – s. u.), Nachtarbeitnehmer (§6), **Nimmt an Betriebsferien teil** (Standard an), **Soll-Arbeitszeiten je Wochentag** (s. u.), Erster/Letzter Arbeitstag (Soll nur in diesem Zeitraum), individuelle Tagesstunden, Abteilung/Bereich, **Kalenderfarbe**, Anfangssaldo Überstunden

> **Urlaub (Tagesprinzip):** 1 freier Arbeitstag = 1 Urlaubstag (unabhängig von Tagesstunden/Wochentag). Halbtag = 0,5. Anspruch anteilig: `30 × Arbeitstage/5`. Verbrauch tagebasiert, Stunden nur intern.

> **Benutzerübersicht (#194)** zeigt je MA Urlaubskonto **und** aktuellen Überstundensaldo in der Spalte **„Überstunden (JTD)"**; „—" bei Mitarbeitern ohne Stundenzählung.

### Stundenzählung an/aus (#191)

Checkbox **„Stundenzählung aktiv"** (Standard an). Aus = **Mitarbeiter ohne Stundenzählung** (NIE „leitende Angestellte" nennen!).
- Keine Soll-/Ist-/Überstundenberechnung → Spalte „Überstunden (JTD)" zeigt **„—"**.
- Felder Anfangssaldo / individuelle Tagesstunden entfallen.
- **Urlaub + Krank zählen trotzdem – tagebasiert** (1 Tag = 1 Tag, Sondertage = 1 Tag; Halbtag zählt hier als voller Tag). Anspruch anteilig + Vorjahresübernahme bleiben.

> **Abgrenzung – zwei getrennte Checkboxen, nicht verwechseln:**
> - **„Stundenzählung aktiv"** = ob Soll-/Ist-/Überstunden geführt werden. Hat **nichts** mit §18 zu tun.
> - **„ArbZG-Prüfungen aussetzen (§18)"** = eigene Checkbox, setzt nur die ArbZG-Prüfungen aus (echte leitende Angestellte i. S. §18). Frei kombinierbar.

### Soll-Arbeitszeit-Fenster (#201)

Pro MA je Wochentag (Mo–Fr) optionaler **Soll-Beginn / Soll-Ende** (Bereich „Soll-Arbeitszeiten je Wochentag").
- Anwesenheit außerhalb `[Soll−Puffer, Soll+Ende-Puffer]` wird **gekappt** (nicht angerechnet).
- **Rohstempel bleibt erhalten** (§16) – Salden/Überstunden rechnen mit der gekappten Zeit.
- **Puffer global:** Einstellungen → „Soll-Arbeitszeit-Fenster" → „Puffer (Min.)", Default **15**.
- **Opt-in:** ohne gesetzte Soll-Zeiten kein Verhaltenswechsel. Übersprungen bei Mitarbeitern ohne Stundenzählung; §18-MA werden **trotzdem** gekappt (reine Anwesenheits-Policy).
- Greift an allen Schreibpfaden (Stempeln, manuell, Admin-Korrektur, Import, CR-Genehmigung).

### Stundenänderung (Teilzeit etc.)
**Benutzer öffnen** → neue Wochenstunden + **Wirkungsdatum** eintragen
→ Historische Salden bleiben korrekt!

### Mitarbeiter deaktivieren (niemals löschen!)
**Benutzer öffnen** → Status „Inaktiv"
→ Daten 2 Jahre aufbewahren (§16 ArbZG)

---

## Admin-Dashboard

| Spalte | Bedeutung |
|--------|-----------|
| **Soll/Ist** | Stunden des gewählten Monats |
| **Saldo** | Differenz in H:MM |
| **Übersto. Kum.** | Kumulierter Jahressaldo |
| **Urlaub** | Verbleibende Tage (Ampel) |
| **Krank** | Kranktage im Monat |

Klick auf Pfeil → Detailansicht des Mitarbeiters

---

## Berichte & Exporte

| Bericht | Inhalt | Formate |
|---------|--------|---------|
| **Monatsreport** | Tägliche Einträge aller MA | Excel + CSV |
| **Jahresreport Classic** | 12 Monate kompakt | Excel + CSV |
| **Jahresreport Detailliert** | 365 Tage, ~5s | Excel + CSV |

**Exportieren:** Berichte → Typ & Zeitraum wählen → Excel oder CSV klicken
**Aufbewahrungspflicht: 2 Jahre** (§16 ArbZG)

---

## Abwesenheitsanträge genehmigen

**Anträge** (Admin-Navigation, Seite: „Abwesenheitsanträge")

**Toggle oben:** Genehmigungspflicht ein-/ausschalten
- **Aus** (Standard): Mitarbeiter buchen Urlaub direkt
- **Ein**: Urlaub landet als „Offen" zur Genehmigung

**Genehmigen:** Grüner Button → Abwesenheiten werden automatisch eingetragen
**Ablehnen:** Roter Button → optionalen Ablehnungsgrund eingeben

---

## Korrekturanträge prüfen

**Änderungsanträge** → offene Anträge → Antrag öffnen
- Alt vs. Neu vergleichen, Begründung lesen
- **Genehmigen** → Eintrag wird sofort geändert
- **Ablehnen** → optional Ablehnungsgrund eintragen

---

## Betriebsferien

**Abwesenheiten → Tab Betriebsferien → Neue Betriebsferien**
- Bezeichnung + Von–Bis → Speichern
- → Alle MA **mit „Nimmt an Betriebsferien teil"** (Standard) erhalten automatisch Abwesenheitseinträge (keine Urlaubstage!) – rollenunabhängig (auch Admins, die MA sind)
- Nachträglich Berechtigte: Option setzen → Einträge werden **automatisch** für laufende und künftige Betriebsferien nachgetragen (Neu-Speichern nicht nötig)
- Löschen: Einträge werden bei allen MA automatisch entfernt

---

## Einstellungen (Auswahl)

Jeder Bereich hat einen eigenen **Speichern**-Button.

| Bereich | Was |
|---------|-----|
| **Feiertage** | Bundesland wählen + eigene Feiertage (reduzieren Soll, grau im Kalender) |
| **Sondertage (24./31.12.)** | s. u. (#188) |
| **Urlaubsgenehmigung** | Genehmigungspflicht an/aus |
| **Pflicht-Pause-Ausnahme** | Genehmigungspflicht für §4-Ausnahmen (s. o.) |
| **Soll-Arbeitszeit-Fenster** | Puffer (Min.) für Soll-Zeiten, Default 15 (s. o.) |
| **Onboarding / Willkommens-Tour** | Erst-Login-Tour für neue Nutzer an/aus (Standard **an**) |
| **Farben** | Farbe je An-/Abwesenheitstyp |

### Sondertage 24./31.12. (#188)

Heiligabend + Silvester sind **keine** gesetzlichen Feiertage → pro Tag getrennt einstellbar:

| Modus | Wirkung | Kalender |
|-------|---------|----------|
| **Arbeitstag** (Standard) | volles Tagessoll | normal |
| **Halbtag** | halbes Tagessoll | **amber/gelb** |
| **Frei** | Tagessoll 0 (wie Feiertag) | **grau** |

Bei „Frei" zusätzlich **Anrechnung:** Urlaub (vom Konto) oder Bezahlte Freistellung (kein Abzug). Wirkt auf Soll, Urlaubskonto und Kalender.

---

## ArbZG-Pflichten – Automatik bei Zeiterfassung

| Prüfung | Grenze | Verhalten | § |
|---------|--------|-----------|---|
| Tagesarbeitszeit Warnung | > 8h Netto | Warnung | §3 |
| Tagesarbeitszeit 10h | > 10h Netto | **Live-Ausstempeln: nur Warnung (kein Block)**; manuelle Eingabe/Antrag: **harte Sperre** | §3 |
| Pausenpflicht | > 6h → 30 Min. / > 9h → 45 Min. | Warnung; dokumentierte Ausnahme mit Begründung möglich (s. u.) | §4 |
| Nachtarbeitnehmer | > 8h täglich | Warnung | §6 |
| Sonntagsarbeit | Eintrag an So/Feiertag | Warnung + Ausnahmegrund-Pflicht | §9/§10 |
| Wochenstunden | > 48h | Warnung | §14 |
| Ruhezeitwarnung | < 11h seit letztem Arbeitsende (beim Einstempeln) | Warnung | §5 |

> **§3-10h (R2):** Live-Ausstempeln über 10h wird **nicht geblockt** (Zeit ist geleistet → §16-Doku-Pflicht), nur deutlich gewarnt. Manuelle Eingaben und Anträge bleiben über 10h **gesperrt**.

---

## Pflicht-Pause-Ausnahme (§4)

Pause nicht eingehalten? Statt Blockade → Eintrag mit **Pflicht-Begründung** möglich (im Änderungsprotokoll dokumentiert, Quelle „break_waiver").
**Einstellungen → „Pflicht-Pause-Ausnahme" → „Genehmigung erforderlich":**
- **Aus** (Standard): Eintrag sofort wirksam, Abweichung als Warnung
- **Ein**: Eintrag erst nach Admin-Genehmigung wirksam
> **4-Augen:** Eigene Pflicht-Pause-Ausnahme **nie selbst genehmigen** – muss ein anderer Admin prüfen.

---

## Überstundenausgleich

**Abwesenheit → Typ „Überstundenausgleich"**
- Soll bleibt erhalten, Ist = 0h → Konto sinkt um Tagessoll
- Kein Budget-Check — Kontostand manuell prüfen!

---

## Abwesenheits-Änderungsanträge

- MA können Urlaub/Fortbildung per Änderungsantrag beantragen
- Krankmeldung per Antrag **gesperrt** (nur Admin)
- Genehmigung → Abwesenheit wird automatisch erstellt
- DSGVO: Kranktage im Kalender für Nicht-Admins als „abwesend" maskiert

---

## ArbZG-Compliance-Berichte (regelmäßig prüfen!)

**Berichte** → nach unten scrollen → ArbZG-Berichte

| Bericht | Inhalt | Handlungsbedarf bei |
|---------|--------|-------------------|
| **§5 Ruhezeitverstöße** | Fälle < 11h Ruhezeit | Sofort! Ursachen beseitigen |
| **§6 Nachtarbeit** | MA mit ≥ 48 Nachtarbeitstagen/Jahr | Arbeitsmed. Untersuchung anbieten |
| **§11 Sonntagsarbeit** | Sonntage pro MA (Ziel: max. 37/Jahr) | Dienstplanung anpassen |
| **§11 Ersatzruhetag** | Offene Ersatzruhetag-Pflichten | Ausgleich: Sonntag 2 Wo / Feiertag 8 Wo |

---

## Lizenz

- **Beta:** Die Lizenzprüfung ist derzeit **deaktiviert** – PraxisZeit läuft ohne `license.key` mit vollem Funktionsumfang. Es ist **kein** Lizenzierungs-Schritt nötig.
- Ein Lizenzmodell wird zu einem späteren Zeitpunkt eingeführt; Sie werden rechtzeitig informiert.

---

## Audit-Log & Monitoring

**Änderungsprotokoll:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis
**Fehler-Monitoring:** Technische Fehler → bei wiederkehrenden Fehlern IT kontaktieren oder GitHub Issue öffnen

---

## Wichtige Limits

| Regel | Wert | § |
|-------|------|---|
| Tagesarbeitszeit max. | **10 Stunden** | §3 |
| Ruhezeit min. | **11 Stunden** | §5 |
| Freie Sonntage min. | **15 pro Jahr** | §11 |
| Ersatzruhetag (Sonntag) | **2 Wochen** | §11 |
| Ersatzruhetag (Feiertag) | **8 Wochen** | §11 |
| Aufbewahrungspflicht | **2 Jahre** | §16 |

---

## Jahresabschluss

| Aktion | Button | Beschreibung |
|--------|--------|--------------|
| **Erstellen** | 🟠 Jahresabschluss | Berechnet Überstunden-Saldo + Resturlaub aller aktiven MA und übernimmt sie ins Folgejahr |
| **Löschen** | 🔴 Abschluss löschen | Entfernt alle Übernahmen fürs Folgejahr unwiderruflich (inkl. manueller Übernahmen!) |

**Wo:** Admin-Dashboard → Jahresübersicht → Jahr auswählen → Button klicken
**Achtung:** Löschen betrifft **alle** Mitarbeiter und kann nicht rückgängig gemacht werden. Bestätigungsdialog lesen!

---

## Notfall-Checkliste Monatsabschluss

- [ ] Alle Korrekturanträge geprüft und entschieden
- [ ] Monatsreport exportiert und gesichert
- [ ] §5 Ruhezeitbericht geprüft (Verstöße dokumentieren)
- [ ] §11 Ersatzruhetage nachgeführt
- [ ] Offene Urlaubstage geprüft (Ampel-System im Admin-Dashboard)

---

## Notfall-Kontakte

**IT-Support:** ____________________________

**Arbeitsrechtliche Fragen:** ____________________________

---

## Schichtplanung (optional)

- **Aus per Default.** Aktivieren: **Einstellungen → Schichtplanung → Speichern**.
- **Stammdaten:** Standorte (optional) + Arbeitsplätze (mit Farbe) anlegen.
- **Plan:** beliebig viele Wochenpläne; Slots per Drag & Drop / Klick, Mitarbeitende auf Slot ziehen, Mindestbesetzung optional.
- **Aktiv schalten** → für alle sichtbar (mehrere Pläne gleichzeitig aktiv möglich).
- Reines Planungswerkzeug – **keine** Wirkung auf Zeiterfassung/ArbZG/Urlaub/Überstunden. Details: `docs/SCHICHTPLANUNG.md`.

---

*PraxisZeit · ArbZG-Volltext: [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
