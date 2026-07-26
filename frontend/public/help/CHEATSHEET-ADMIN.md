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

> **Monatsjournal (#311):** Buch-Symbol in der Aktionsspalte öffnet das Journal; Überschrift jetzt **„Monatsjournal: Vorname Nachname"**.

### Stundenzählung an/aus (#191)

Checkbox **„Stundenzählung aktiv"** (Standard an). Aus = **Mitarbeiter ohne Stundenzählung** (NIE „leitende Angestellte" nennen!).
- Keine Soll-/Ist-/Überstundenberechnung → Spalte „Überstunden (JTD)" zeigt **„—"**.
- Felder Anfangssaldo / individuelle Tagesstunden entfallen.
- **Urlaub + Krank zählen trotzdem – tagebasiert** (1 Tag = 1 Tag; „Frei"-Sondertag = 1 Tag, „halber Feiertag" 24./31.12. = 0,5 Tag seit #394). Anspruch anteilig + Vorjahresübernahme bleiben.

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
**Benutzer öffnen** → Button **„Wochenstunden anpassen…"** (oder Uhr-Symbol in der Benutzerliste) → neue Wochenstunden + **„Gültig ab"**-Datum eintragen
→ Wochenstunden sind im Bearbeiten-Formular nur noch Anzeige, keine Direkteingabe mehr
→ Historische Salden bleiben korrekt! Verlauf zeigt „ab … bis …"; Berichte zeigen den zu Zeitraumsbeginn gültigen Wert + „ab TT.MM.JJJJ: X Std/Woche" (Dashboard, Excel, ODS, PDF)
→ **Rückwirkendes Datum:** Dialog zeigt vorab Zeitraum + altes/neues Tagessoll + betroffene Abwesenheiten – nach Bestätigung werden deren Stunden umgerechnet (Urlaubs**tage** bleiben unverändert, Tagesprinzip); abgeschlossenes Jahr wird nur gemeldet, nicht neu berechnet
→ Löschen einer Änderung rechnet zurück; **früheste** Änderung erst löschbar, wenn keine späteren mehr bestehen
→ Individueller Tagesplan: Button deaktiviert, Pflege über Tagesstunden

### Mitarbeiter deaktivieren (niemals löschen!)
**Benutzer öffnen** → Status „Inaktiv"
→ Daten 2 Jahre aufbewahren (§16 ArbZG)

### DSGVO: Anonymisierung & endgültige Löschung (Art. 17)
**Reihenfolge:** Deaktivieren → **14-Tage-Sperrfrist** → Anonymisieren → endgültig löschen
- **Anonymisieren** (nach 14-Tage-Sperrfrist): entfernt persönliche Daten (Name/E-Mail/Lichtbild/2FA), **Zeiteinträge bleiben** (§16 ArbZG), Abwesenheiten weg
- **Endgültig löschen (Purge):** vollständige Löschung – erst möglich, wenn die jüngste Aufzeichnung **≥ 730 Tage** alt ist (sonst blockiert)
- Anonymisierte Nutzer können erst **nach 730 Tagen** endgültig gelöscht werden; alles wird im Änderungsprotokoll vermerkt
- **Inaktive anzeigen** einblenden → System zeigt Sperrfrist + ob Anonymisierung/Löschung möglich

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

**Monat ↔ Woche (#329):** Umschalter „Monat / Woche" oben → Wochenansicht zeigt die KW (z. B. „22.–28.06.2026 (KW 26)"), Pfeile blättern wochenweise. Auswahl bleibt pro Browser/Gerät gespeichert.
**Soll-Basis (#313):** Dropdown „Soll: bis heute / Monatsende (volle Woche)". „bis heute" (Standard) zählt Soll nur bis zum letzten abgeschlossenen Arbeitstag → kein Monatsanfangs-Minus. Nur Live-Anzeigen; Datei-Exporte bleiben voller Monat.

---

## Berichte & Exporte

| Bericht | Inhalt | Formate |
|---------|--------|---------|
| **Monatsreport** | Tägliche Einträge aller MA | Excel (.xlsx) + ODS (.ods) + PDF (.pdf) |
| **Jahresreport Classic** | 12 Monate kompakt | Excel (.xlsx) + ODS (.ods) |
| **Jahresreport Detailliert** | 365 Tage, ~5s | Excel (.xlsx) + ODS (.ods) |

**Exportieren:** Berichte → Typ & Zeitraum wählen → Format klicken (**PDF nur beim Monatsreport**)
**Krankheitsdaten:** Checkbox „Krankheitsdaten einschließen" (Art. 9 DSGVO) → nimmt Krank-Daten auf, jeder solche Export wird protokolliert
**Aufbewahrungspflicht: 2 Jahre** (§16 ArbZG)

---

## Abwesenheitsanträge genehmigen

**Anträge** (Admin-Navigation, Seite: „Abwesenheitsanträge")

**Toggle oben:** Genehmigungspflicht ein-/ausschalten
- **Aus** (Standard): Mitarbeiter buchen Urlaub direkt
- **Ein**: Urlaub landet als „Offen" zur Genehmigung

**Genehmigen:** Grüner Button → Abwesenheiten werden automatisch eingetragen
**Ablehnen:** Roter Button → optionalen Ablehnungsgrund eingeben
**Stornieren:** Filter „Genehmigt" → Antrag → **„Urlaub stornieren"** (nur wenn Zeitraum noch nicht begonnen) → Abwesenheiten werden **automatisch entfernt**, Antrag wird „Zurückgezogen"

---

## Korrekturanträge prüfen

**Änderungsanträge** → offene Anträge → Antrag öffnen
- Alt vs. Neu vergleichen, Begründung lesen
- **Genehmigen** → Eintrag wird sofort geändert
- **Ablehnen** → optional Ablehnungsgrund eintragen

---

## Betriebsferien

**Abwesenheiten → Tab Betriebsferien → Neue Betriebsferien**
- Bezeichnung + Von–Bis + **Verrechnung** → Speichern
- → Alle MA **mit „Nimmt an Betriebsferien teil"** (Standard) erhalten automatisch Einträge an ihren **Arbeitstagen** – rollenunabhängig (auch Admins, die MA sind)
- **Nicht gebucht:** Wochenende, Feiertage, freie Wochentage (Teilzeit), „Frei"-Sondertage (24./31.12.), außerhalb des Beschäftigungszeitraums (Eintritt/Austritt), Tage mit vorhandener Abwesenheit
- **Verrechnung:** *Als Urlaub werten* (**Standard**, zieht 1 Urlaubstag je Tag, an einem Halbtags-Sondertag 24./31.12. nur 0,5, #394) **oder** *Bezahlte Freistellung* (kein Urlaubsabzug, saldoneutral)
- Nachträglich Berechtigte: Option setzen → Einträge werden **automatisch** für laufende und künftige Betriebsferien nachgetragen (Neu-Speichern nicht nötig)
- Löschen: Einträge werden bei allen MA automatisch entfernt

**Länger als der Jahresurlaub (#314)** – Schalter *Einstellungen → Betriebsferien & Urlaub → „Überzählige Betriebsferien als Überstundenabbau"* (global, Standard **aus**):
- **AUS:** alles Urlaub → Überschuss = **Minus-Urlaub** (Pflichturlaub)
- **AN:** erst Urlaub, dann **Überstundenabbau** (Konto sinkt, darf ins Minus) → **nie** Minus-Urlaub
- Zuteilung **chronologisch nach Datum** (frühere Schließung zuerst, Überstunden-Tage auf die **letzte** Schließung) – unabhängig von der Eingabereihenfolge; privater Urlaub wird **zuerst** verbraucht
- Wirkt beim **Anlegen/erneuten Speichern** → bestehende Betriebsferien einmal öffnen + neu speichern

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
| **Eigene Abwesenheitsgründe** | Bezeichnung + Farbe + Basis-Verhalten (#312) – s. u. |
| **Betriebsferien & Urlaub** | „Überzählige Betriebsferien als Überstundenabbau" (#314, Standard aus – s. Betriebsferien) |
| **Farben** | Farbe je An-/Abwesenheitstyp |

### Sondertage 24./31.12. (#188)

Heiligabend + Silvester sind **keine** gesetzlichen Feiertage → pro Tag getrennt einstellbar:

| Modus | Wirkung | Kalender |
|-------|---------|----------|
| **Arbeitstag** (Standard) | volles Tagessoll | normal |
| **Halbtag** | halbes Tagessoll | **amber/gelb** |
| **Frei** | Tagessoll 0 (wie Feiertag) | **grau** |

Bei „Frei" zusätzlich **Anrechnung:** Urlaub (vom Konto) oder Bezahlte Freistellung (kein Abzug). Wirkt auf Soll, Urlaubskonto und Kalender.

### Eigene Abwesenheitsgründe (#312)

Frei benannte Gründe (z. B. „Schule" für Azubis) mit Farbe + **Basis-Verhalten** (nach Anlegen **fix**):

| Basis-Verhalten | Wirkung |
|-----------------|---------|
| **zählt als gearbeitet** | Stunden als Arbeitszeit gutgeschrieben (wie Fortbildung) |
| **bezahlt frei** | Tagessoll 0, **kein** Urlaubsabzug |
| **unbezahlt frei** | Tagessoll 0, **kein** Urlaubsabzug, aber **unbezahlt** (Lohn gekürzt) – z. B. Kind krank (§45 SGB V) |
| **Überstundenabbau** | Überstundenkonto sinkt um Tagessoll |

Erscheinen beim Buchen unter „Eigene Gründe". Im Team-Kalender für Kolleg:innen als **„abwesend"** maskiert (Datenschutz); nur Admins sehen die Bezeichnung. Deaktivierbar.

**Kind krank (#376):** Ein „unbezahlt frei"-Grund mit gesetztem **Kind-krank-Limit** zählt gegen den §45-SGB-V-Jahresanspruch (Default 15 Tage, pro MA überschreibbar). Überschreitung → **weiche Warnung** beim Buchen (nie blockierend). Verbrauch je MA in der **Benutzerübersicht**.
**Minijob/MiLoG (#377):** Opt-in „Arbeitszeitkonto (§2 Abs.2 MiLoG)" je MA → weiche Warnungen bei >50 % Monats-Plus + 12-Monats-Ausgleichsfrist. Mindestlohn 13,90 €/h (2026), 14,60 €/h (2027).
**Feste Monatsarbeitszeit (#377 Baustein 2b):** zusätzliches Opt-in je MA (nur bei aktivem Arbeitszeitkonto **+** Stundenzählung, „Vereinbarte Monatsarbeitszeit" wird Pflicht) → Monats-Soll fix = vereinbarte Monatszeit (kalendertag-anteilig bei Ein-/Austritt) statt Tagessoll-Summe. Geplante Tagesstunden = reine Gutschrift-Basis: Feiertag/Urlaub/bez. Freistellung auf geplantem Tag → Ist-Gutschrift (Krank/Fortbildung laufen separat, keine Doppelgutschrift); unbezahlt (Sonstiges) → Soll-Minderung. Weiche Warnung bei Ist > vereinbart. **Grenze:** ganze Fehlmonate bei deutlich unter der Monatszeit liegenden Tagesstunden gleicht die Automatik nur teilweise aus (Rest = manuelle Korrektur); einzelne Fehltage sind korrekt.

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
- **Einweisungen:** Matrix MA × Arbeitsplätze; nicht eingewiesene Zuweisung → weiche Warnung (blockiert nicht). MA sehen ihre Einweisungen im Profil.
- **KW-/Jahresplanung (#305 M2):** pro Plan optionales Aktiv-Datums-Fenster („von/bis") + Jahres-Zeitstrahl. **Automatisch füllen** verteilt eingewiesene, verfügbare MA greedy auf die Slots (Zielwoche, ausgewogen nach Auslastung/Überstunden) → Entwurf, aktiviert den Plan **nicht**.
- **Woche/Tag-Umschalter** (#321); im Slot-Dialog **„Auf Wochentage kopieren"** → Schicht inkl. Zuweisungen auf weitere Tage (#322).
- **Auslastung (#330):** unter jedem Namen „zugewiesene Std / Wochenarbeitszeit" (z. B. „15,25 / 17 h") – grün ±30 Min, gelb ±1 Std, sonst rot.
- Reines Planungswerkzeug – **keine** Wirkung auf Zeiterfassung/ArbZG/Urlaub/Überstunden. Details: `docs/SCHICHTPLANUNG.md`.

---

*PraxisZeit · ArbZG-Volltext: [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
