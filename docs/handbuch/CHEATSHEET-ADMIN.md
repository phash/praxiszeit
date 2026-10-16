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
**Benutzerverwaltung** → **„Neue:r Mitarbeiter:in"**
- Benutzername (Login-Name), Passwort (mind. 10 Zeichen)
- Vorname / Nachname, E-Mail (optional)
- Wochenstunden, Arbeitstage/Woche, Urlaubstage
- **Arbeitszeit** (nur bei Stundenzählung): **„Gleichmäßig"** (Wochenstunden + Arbeitstage), **„Nach Tagen"** (Stunden je Wochentag) oder **„Nach Arbeitsblöcken"** (Blöcke je Wochentag, Wochenstunden + Arbeitstage werden abgeleitet – s. u.)
- Rolle: Mitarbeiter:in oder Admin
- Optional: **Stundenzählung aktiv** (s. u.), **ArbZG-Prüfungen aussetzen (§18)** (separate Checkbox – s. u.), Nachtarbeitnehmer (§6), **Nimmt an Betriebsferien teil** (Standard an), Erster/Letzter Arbeitstag (Soll nur in diesem Zeitraum), Abteilung/Bereich, **Kalenderfarbe**, Anfangssaldo Überstunden

> **Urlaub (Tagesprinzip):** 1 freier Arbeitstag = 1 Urlaubstag (unabhängig von Tagesstunden/Wochentag). Halbtag = 0,5. Anspruch anteilig: `30 × Arbeitstage/5`. Verbrauch tagebasiert, Stunden nur intern.

> **Benutzerübersicht (#194)** zeigt je MA Urlaubskonto **und** aktuellen Überstundensaldo in der Spalte **„Überstunden (JTD)"**; „—" bei Mitarbeitern ohne Stundenzählung.

> **Monatsjournal (#311):** Buch-Symbol in der Aktionsspalte öffnet das Journal; Überschrift jetzt **„Monatsjournal: Vorname Nachname"**.

### Stundenzählung an/aus (#191)

Checkbox **„Stundenzählung aktiv"** (Standard an). Aus = **Mitarbeiter ohne Stundenzählung** (NIE „leitende Angestellte" nennen!).
- Keine Soll-/Ist-/Überstundenberechnung → Spalte „Überstunden (JTD)" zeigt **„—"**.
- Feld Anfangssaldo und Auswahl **„Arbeitszeit"** (Tagesplan/Blöcke) entfallen; Arbeitszeit-Blöcke kappen nicht.
- **Urlaub + Krank zählen trotzdem – tagebasiert** (1 Tag = 1 Tag; „Frei"-Sondertag = 1 Tag, „halber Feiertag" 24./31.12. = 0,5 Tag seit #394). Anspruch anteilig + Vorjahresübernahme bleiben.

> **Abgrenzung – zwei getrennte Checkboxen, nicht verwechseln:**
> - **„Stundenzählung aktiv"** = ob Soll-/Ist-/Überstunden geführt werden. Hat **nichts** mit §18 zu tun.
> - **„ArbZG-Prüfungen aussetzen (§18)"** = eigene Checkbox, setzt nur die ArbZG-Prüfungen aus (echte leitende Angestellte i. S. §18). Frei kombinierbar.

### Arbeitszeit-Blöcke (ab 1.20.0)

Je MA und Wochentag (Mo–Fr) bis zu **3 Blöcke** „von–bis" + **„Pause innerhalb der Blöcke"** (Raster 5 Min.); gepflegt nur mit Wirkungsdatum über **„Arbeitszeit anpassen…"** (s. u.), beim Anlegen Modus **„Nach Arbeitsblöcken"**.
- **Tagessoll = Σ Blöcke − Pause** (z. B. 08–12 + 15–18, Pause 30 → 6:30 h); Wochenstunden und Arbeitstage werden abgeleitet, ein Wochentag ohne Block ist kein Arbeitstag.
- **Kappung:** vor dem ersten, nach dem letzten und **zwischen** den Blöcken nicht angerechnet; **Puffer an jedem Blockrand** (Einstellungen → „Soll-Arbeitszeit-Fenster", Default **15**). Lücke ≤ 2 × Puffer wird voll angerechnet → geplante Pause als „Pause innerhalb der Blöcke" erfassen, nicht als kurze Lücke.
- Beispiel: Blöcke 08–12 + 15–18, Puffer 15, gestempelt 08:00–18:00 ohne Pause → **7:30 h** angerechnet (08:00–12:15 + 14:45–18:00), 2:30 h nicht; die Stempel bleiben gespeichert (§16).
- **Kein Block → keine Kappung:** blockfreie Wochentage, Wochenende, Feiertage, „freie" Sondertage („halber Feiertag" behält die Blöcke); MA ohne Stundenzählung; **anerkannte** Einträge. §18-MA werden trotzdem gekappt. Greift an allen Schreibwegen (Stempeln, manuell, Admin-Korrektur, Antrag, XLS-Import).
- **Auto-Close** (vergessenes Ausstempeln, 23:59) rechnet nur bis zum letzten Block + Puffer an („automatisch geschlossen"); tatsächliches Ende nachtragen (MA per Änderungsantrag) – auch ein echtes Ende 23:59 ist eintragbar (wird gekappt wie jedes Ende, bis 23:59 angerechnet erst nach „Anerkennen").
- **Pausen:** Lücke ab 15 Min. (nach Abzug des Puffers) zählt für §4 als Pause; Pause eingetragen **und** über die Lücke durchgestempelt → beides abgezogen (Hinweis „Pause in der Lücke wird zusätzlich abgezogen: …").
- **Sichtbar:** Zusatzzeile am Eintrag („… 2:30 h zwischen den Blöcken nicht angerechnet"), Journal-Summe „Anwesenheit nicht angerechnet", Export-Spalte „Nicht angerechnet (Min)" (letzte Spalte).
- **Anerkennen** (Admin-Dashboard-Detail, Monatsjournal): ganze gestempelte Zeit zählt, dauerhaft (keine Rücknahme), protokolliert („Anrechnung anerkannt"); offener Eintrag erst nach dem Ausstempeln, automatisch geschlossener erst mit tatsächlichem Ende. MA beantragen das per **„Anrechnung beantragen"**.
- **Altbestand:** frühere Soll-Fenster = „Arbeitszeit-Fenster (Altbestand, nur Kappung)" (kappen nur, ändern das Soll nicht) → im Dialog **„In Arbeitszeit-Blöcke umwandeln"** oder **„Fenster entfernen"**.
- ⚖️ Nichtanrechnung ersetzt keine Vergütungsentscheidung (§ 611a, § 612 BGB; MiLoG) – geduldete Arbeit anerkennen. Mitbestimmung § 87 Abs. 1 Nr. 2, 3, 6 BetrVG; Jugendliche §§ 11, 12 JArbSchG – PraxisZeit prüft das nicht.

### Arbeitszeit ändern (Wochenstunden, Tagesplan, Blöcke)
**Benutzer öffnen** → Button **„Arbeitszeit anpassen…"** (oder Uhr-Symbol in der Benutzerliste) → Dialog **„Arbeitszeit & Wochenstunden"** → **„Gültig ab"** → Modus **„Gleichmäßig"** / **„Nach Tagen"** / **„Nach Arbeitsblöcken"** (live je Tag „Gesamtzeit · Pause · Tagessoll" + Wochensumme; Blöcke nur bei Stundenzählung) → optional Notiz → Auswirkung prüfen → Speichern
→ Gilt für **alle** MA: Wochenstunden, Tagesstunden, Modus, Arbeitstage und Blöcke sind im Bearbeiten-Formular nur Anzeige (Bereich „Arbeitszeit heute"); beim **Anlegen** normale Felder bzw. Block-Editor
→ **Auswirkung** vor dem Speichern: Tagessoll je Wochentag alt → neu, Einträge je Monat alt → neu, übersprungene (mit Grund), Abwesenheiten, Δ Soll / Δ angerechnet / Überstundenkonto / Urlaubsverbrauch; Haken „Ich habe die Auswirkungen geprüft und möchte speichern" Pflicht, sobald Einträge, Abwesenheiten, Überstundenkonto oder Urlaubsverbrauch betroffen sind (rückwirkend immer)
→ **Rückwirkend:** Einträge an geänderten Wochentagen werden ab Rohstempel mit dem aktuellen Puffer **neu gekappt** (ohne Rohstempel „nicht erweiterbar"), danach Abwesenheits-Stunden aufs neue Tagessoll – auch bei Zukunftsdatum (Urlaubs**tage** bleiben); offene Einträge vergangener Tage werden vorher geschlossen; abgeschlossenes Jahr wird nur gemeldet
→ **Verkürzung** (Eintrag verliert Zeit **oder** Überstundenkonto sinkt – auch durch höheres Soll – **oder** Misch-Tag-Gutschrift sinkt stärker als das Tagessoll): Standard **„Ab heute (…) wirksam – vergangene Einträge bleiben unverändert"** (verliert kein Eintrag: „… – vergangene Tage bleiben unverändert"; verliert schon der heutige Tag: „Ab TT.MM.JJJJ wirksam – …" = ab morgen); **rückwirkend** nur mit Grund („Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)" / „Mit der beschäftigten Person vereinbart" / „Sonstiges"), Begründung (10–400 Zeichen) + Haken; Protokoll-Kürzel „[Erfassungsfehler korrigiert]" / „[Einvernehmlich vereinbart]" / „[Sonstiges]". Grund, Begründung und Notiz teilen sich das Notizfeld („Notiz und Begründung zusammen höchstens 500 Zeichen."). Falsche **Stempel** am Zeiteintrag korrigieren, nicht über die Arbeitszeit. In **abgeschlossene Jahre** gesperrt
→ ⚠️ Seit 1.20.0 braucht auch eine rückwirkende **Erhöhung** der Wochenstunden oder des Tagesplans Grund + Haken, wenn das Konto sinkt
→ **Löschen:** Papierkorb nur an der **jüngsten** Zeile des Verlaufs, rechnet zurück. Verkürzt es, Standard **„Ab … auf den vorherigen Stand zurücksetzen"** (Knopf „Zurücksetzen", neue Verlaufszeile) oder „Rückwirkend löschen mit Neuberechnung" (Grund + Begründung + Haken). Wurde inzwischen eine Änderung dazwischen angelegt, lehnt PraxisZeit die Rücksetzung ab: „Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden."
→ MA sehen 30 Tage den Dashboard-Kasten **„Hinweis zu Ihrer Arbeitszeit"** + Profil „Meine Arbeitszeit"; Protokoll: „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile je Änderung/Löschung
→ Berichte: Wert zu Zeitraumsbeginn + „ab TT.MM.JJJJ: …" (bei Blöcken „Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / …")
→ ⚠️ Arbeitstage-only-Änderung (gleiche Wochenstunden, andere Arbeitstage): Berichtstext nennt bei „Gleichmäßig" zwar die neue Arbeitstage-Zahl, die Wochenstundenzahl selbst bleibt aber gleich – das Tagessoll verschiebt sich trotzdem still; bei „Nach Tagen"/„Nach Arbeitsblöcken" ändert sich stattdessen der Urlaubsverbrauch – immer die Auswirkung prüfen, nicht nur die Wochenstundenzahl

### Mitarbeiter deaktivieren (niemals löschen!)
Benutzerliste → Aktionsspalte → **„Deaktivieren"** (Person mit X); das **letzte aktive Admin-Konto** ist nicht deaktivierbar
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
**Tagesspalten (Monatsreport und Jahresreport Detailliert, Excel/ODS):** hinten angehängt „Unterbrechung (Min)", „Zeiteinträge" und – auch im PDF – als letzte Spalte „Nicht angerechnet (Min)" (Lücke + vor/nach den Blöcken abgeschnittene Zeit); „Netto (Std)" ist die angerechnete Zeit; der Jahresreport Classic (eine Zeile je Monat) hat diese Spalten nicht

---

## Abwesenheitsanträge genehmigen

**Anträge** (Admin-Navigation, Seite: „Abwesenheitsanträge")

**Toggle oben:** Genehmigungspflicht ein-/ausschalten
- **Aus** (Standard): Mitarbeiter buchen Urlaub direkt
- **Ein**: Urlaub landet als „Offen" zur Genehmigung

**Arbeitstage** auf der Karte = was die Genehmigung kostet: nur Arbeitstage laut Tagesplan zum jeweiligen Datum (4-Tage-Woche, Mi frei: Mo–Fr = 4), ohne Wochenende/Feiertag/„frei"-Sondertag; Halbtag und „halber Feiertag" je 0,5
**Genehmigen:** Grüner Button → Abwesenheiten werden automatisch eingetragen
**Ablehnen:** Roter Button → optionalen Ablehnungsgrund eingeben
**Stornieren:** Filter „Genehmigt" → Antrag → **„Urlaub stornieren"** (nur wenn Zeitraum noch nicht begonnen) → Abwesenheiten werden **automatisch entfernt**, Antrag wird „Zurückgezogen"

---

## Korrekturanträge prüfen

**Änderungsanträge** → offene Anträge → Antrag öffnen
- Alt vs. Neu vergleichen, Begründung lesen
- **Genehmigen** → Eintrag wird sofort geändert
- **Ablehnen** → optional Ablehnungsgrund eintragen
- **„Anrechnung beantragt"** (MA): **„Genehmigen und anerkennen"** (beantragte Zeiten – vorbelegt die Stempel – zählen ungekappt, dauerhaft) oder **„Ohne Anerkennen genehmigen"** (nur die beantragten Zeiten, an den Blöcken gekappt); bei anderen Anträgen zu Einträgen mit nicht angerechneter Zeit neben „Genehmigen" zusätzlich **„Genehmigen und anerkennen"**; Sammel-Genehmigung mit Anrechnungsanträgen fragt nach (**„Alle genehmigen"**)

---

## Betriebsferien

**Abwesenheiten → Tab Betriebsferien → Neue Betriebsferien**
- Bezeichnung + Von–Bis + **Verrechnung** → Speichern
- → Alle MA **mit „Nimmt an Betriebsferien teil"** (Standard) erhalten automatisch Einträge an ihren **Arbeitstagen** – rollenunabhängig (auch Admins, die MA sind)
- **Nicht gebucht:** Wochenende, Feiertage, freie Wochentage (Teilzeit), Zeiträume mit 0 Wochenstunden (z. B. Elternzeit), „Frei"-Sondertage (24./31.12.), außerhalb des Beschäftigungszeitraums (Eintritt/Austritt), Tage mit vorhandener Abwesenheit
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
| **Pflicht-Pause-Ausnahme** | Ausnahme erlauben an/aus (Standard **an**, #499) + Genehmigungspflicht für §4-Ausnahmen (s. o.) |
| **Soll-Arbeitszeit-Fenster** | Puffer (Min.) an jedem Rand der Arbeitszeit-Blöcke, Default 15; wirkt auf neue Einträge, jeder Eintrag behält seinen Puffer (s. o.) |
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
| Tagesarbeitszeit 10h | > 10h Netto | **Live-Ausstempeln: nur Warnung (keine Sperre)**; manuelle Eingabe/Antrag: **harte Sperre** | §3 |
| Pausenpflicht | > 6h → 30 Min. / > 9h → 45 Min. über **alle Einträge des Tages**; Lücken < 15 Min. sind keine Pause | **Sperre** an allen Schreibwegen – auch beim Ausstempeln (#499); dokumentierte Ausnahme mit Begründung möglich, sofern erlaubt (s. u.) | §4 |
| Nachtarbeitnehmer | > 8h täglich | Warnung | §6 |
| Sonntagsarbeit | Eintrag an So/Feiertag | Warnung + Ausnahmegrund-Pflicht | §9/§10 |
| Wochenstunden | > 48h | Warnung | §3 |
| Ruhezeitwarnung | < 11h seit letztem Arbeitsende (beim Einstempeln) | Warnung | §5 |

> **§3-10h (R2):** Live-Ausstempeln über 10h wird **nicht gesperrt** (Zeit ist geleistet → §16-Doku-Pflicht), nur deutlich gewarnt. Manuelle Eingaben und Anträge bleiben über 10h **gesperrt**.

> **Arbeitszeit-Blöcke (ab 1.20.0):** Die Sperren nach §3/§4 rechnen mit der **angerechneten** Zeit. Damit eine Kappung keinen Verstoß verdeckt, kommen zusätzlich Hinweise **„laut Stempel"** (nie blockierend): über die Lücke zwischen den Blöcken durchgestempelt ohne erfasste Pause (§4), Anwesenheit > 10 h am Tag bzw. > 48 h in der Woche (§3).

---

## Pflicht-Pause-Ausnahme (§4)

Pause nicht eingehalten? Statt Blockade → Eintrag mit **Pflicht-Begründung** möglich (im Änderungsprotokoll dokumentiert, Quelle „break_waiver").
**Einstellungen → „Pflicht-Pause-Ausnahme" → „Ausnahme ‚Pflicht-Pause war nicht möglich' erlauben"** (#499):
- **An** (Standard): Begründung wird angeboten (Ausstempeln, Zeiterfassung, Anträge, Admin-Korrektur)
- **Aus**: kein Begründungsfeld mehr; der Server lehnt Ausnahmen ab (auch von Admins) – ein Tag über 6/9 h lässt sich nur mit eingetragener Pause speichern. Offene Ausnahme-Anträge gelten dann als Anträge ohne Ausnahme: Genehmigen klappt nur, wenn die Pause des Tages jetzt reicht (sonst ablehnen → mit Pause neu stellen). Bestehende Ausnahmen bleiben.

**„Genehmigung erforderlich"** (nur bei erlaubter Ausnahme; gilt für Ausnahmen, die MA in der Zeiterfassung beim Anlegen/Bearbeiten begründen):
- **Aus** (Standard): Eintrag sofort wirksam, Abweichung als Warnung
- **Ein**: Eintrag erst nach Admin-Genehmigung wirksam
- **Ausstempeln:** Begründung wirkt **immer sofort** (Eintrag muss geschlossen werden, §16) → im Änderungsprotokoll prüfen (Quelle „break_waiver"). Keine Ausnahme beim Ausstempeln gewünscht → Ausnahme ganz abschalten.
- **Nur Notiz geändert** (Datum, Zeiten, Pause gleich): keine neue Ausnahme – sofort gespeichert, dokumentierte Begründung bleibt (auch bei Genehmigungspflicht/abgeschalteter Ausnahme)
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

**Änderungsprotokoll:** Alle Aktionen lückenlos protokolliert → Betriebsprüfungsnachweis · Arbeitszeit-Änderungen: „Neukappung (Arbeitszeit-Änderung)" je Eintrag + Sammelzeile · Anerkennungen: „Anrechnung anerkannt"
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
- **Freigabe:** Plan-Einstellungen → „Für Mitarbeitende sichtbar" macht einen Plan unabhängig vom Datums-Fenster sichtbar – auch bevor er gilt **und nach dessen Ablauf** (Kopie erbt das nicht). **Falle:** befristeter Plan abgelaufen, Schalter vergessen zurückzusetzen → bleibt für MA sichtbar (als „Nicht mehr gültig" markiert). Freigegebene Pläne erkennbar am **Augen-Symbol** in der Planliste / Abzeichen „Sichtbar" im Plan-Kopf. **Hinweis** je Slot (optional, 500 Zeichen, sichtbar als »-Text). **PDF**-Knopf druckt Arbeitsplatz×Wochentag im Querformat – auch MA können ihren sichtbaren Plan drucken; gilt der gedruckte Plan gerade nicht, trägt der Ausdruck den Vermerk „Vorschau — gilt derzeit nicht" bzw. „Nicht mehr gültig". Einheitlicher Standort → Kopfzeile; unterschiedliche/teils fehlende Standorte → je Arbeitsplatzname, z. B. „Tresen (Hauptstelle)". **Praxisname** in der Kopfzeile = `[practice] name` in `config/praxiszeit.conf` (nativ) bzw. `PRACTICE_NAME` in `.env` (Docker); gilt nach Neustart des Dienstes (Docker: `docker compose up -d`), Vorgabe „Praxis".
- **Einweisungen:** Matrix MA × Arbeitsplätze; nicht eingewiesene Zuweisung → weiche Warnung (blockiert nicht). MA sehen ihre Einweisungen im Profil.
- **KW-/Jahresplanung (#305 M2):** pro Plan optionales Aktiv-Datums-Fenster („von/bis") + Jahres-Zeitstrahl. **Automatisch füllen** verteilt eingewiesene, verfügbare MA greedy auf die Slots (Zielwoche, ausgewogen nach Auslastung/Überstunden) → Entwurf, aktiviert den Plan **nicht**.
- **Woche/Tag-Umschalter** (#321); im Slot-Dialog **„Auf Wochentage kopieren"** → Schicht (Arbeitsplatz, Zeit, Mindestbesetzung, Zuweisungen **und Hinweis**) auf weitere Tage (#322).
- **Auslastung (#330):** unter jedem Namen „zugewiesene Std / Wochenarbeitszeit" (z. B. „15,25 / 17 h") – grün ±30 Min, gelb ±1 Std, sonst rot.
- Reines Planungswerkzeug – **keine** Wirkung auf Zeiterfassung/ArbZG/Urlaub/Überstunden. Details: `docs/SCHICHTPLANUNG.md`.

---

*PraxisZeit · ArbZG-Volltext: [gesetze-im-internet.de/arbzg](https://www.gesetze-im-internet.de/arbzg/BJNR117100994.html)*
