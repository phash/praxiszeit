# Entfallene und geänderte Wortlaut-Prüfungen (Task 16)

Die Prüfungen in `scripts/check-doc-sync.sh` (`need`) lasen den alten, von Hand geschriebenen Handbuchtext. Mit dem Wechsel auf das erzeugte grafische Handbuch (`frontend/src/handbuch`, Markdown per `npm run handbuch:md`) wurde jede fehlschlagende Prüfung einzeln behandelt:

- **Umgestellt:** der neue Inhalt sagt den Sachverhalt mit anderen Worten – die Prüfung gilt jetzt dem neuen Wortlaut (verifiziert gegen die erzeugte Datei).
- **Entfallen:** der neue Inhalt nennt den Sachverhalt bewusst nicht mehr – Grund steht dabei. `forbid`-Prüfungen und `need_code`-Prüfungen (Wortlaute im Code) blieben unverändert.

Die Handbuch-Teile von `DocViewer.tsx` (`handbuchMitarbeiterSections`, `handbuchAdminSections`) sind entfernt; die zugehörigen Pflicht-/Verbotswörter in `DocViewer.test.tsx` sind auf den Handbuchinhalt umgezogen (siehe unten). Kurzanleitungen und Schnellstart bleiben unverändert.

Gruppe `versionen`: Fußzeilen-Prüfung entfallen (die erzeugten Handbücher tragen die Version nur im Kopf, `**Stand:** PraxisZeit x.y.z`; Kopf-Prüfung bleibt, Übereinstimmung mit `package.json` sichert `handbuch_md`).
Gruppe `mirror`: Handbuch-Download-Kopien sind keine Spiegel mehr, sondern erzeugt (`handbuch_md`); Kurzanleitungen und Schnellstart bleiben byte-identische Spiegel.

## Umgestellt auf neuen Wortlaut (72)

| Gruppe | Datei | alter Wortlaut | neuer Wortlaut |
|---|---|---|---|
| admin_aendern | HANDBUCH-ADMIN.md | **Arbeitszeit ändern:** | öffnet den Dialog „Arbeitszeit |
| admin_aendern | HANDBUCH-ADMIN.md | Gesamtzeit 9:00 h · Pause 1:00 h · Tagessoll 8:00 h | Tagessoll = Summe der Blöcke minus diese Pause |
| admin_aendern | HANDBUCH-ADMIN.md | ##### Rückwirkende Änderungen: Neuberechnung | Rückwirkend ab … mit Neuberechnung |
| admin_aendern | HANDBUCH-ADMIN.md | ##### Verlängerung und Verkürzung | **Verkürzung:** Verliert ein Eintrag angerechnete Zeit |
| admin_aendern | HANDBUCH-ADMIN.md | Ich habe die Gründe geprüft. | bestätigen Sie den Haken zum gewählten Grund |
| admin_aendern | HANDBUCH-ADMIN.md | Die Verkürzung reicht in das abgeschlossene Jahr 2025. Gespeichert wird mit Begründung; danach bitte den Jahresabschluss 2025 erneut ausführen. | Reicht die Änderung in ein abgeschlossenes Jahr, weist der Dialog darauf hin |
| admin_aendern | HANDBUCH-ADMIN.md | auf den vorherigen Stand zurücksetzen | auf den vorherigen Stand zurück |
| admin_aendern | HANDBUCH-ADMIN.md | Rückwirkend löschen mit Neuberechnung | rückwirkend nur mit Grund |
| admin_aendern | HANDBUCH-ADMIN.md | Auch eine rückwirkende **Erhöhung** | Auch eine Erhöhung kann eine Verkürzung sein |
| admin_aendern | HANDBUCH-ADMIN.md | Ihre Arbeitszeit wurde ab 01.09.2026 geändert | Hinweis zu Ihrer Arbeitszeit |
| admin_aendern | HANDBUCH-ADMIN.md | Krank 4,0 h — Arbeitszeit-Änderung ab 15.03.2026 | Quelle „Stundenänderung“ |
| admin_aendern | HANDBUCH-ADMIN.md | oder ändern sich Überstundenkonto bzw. Urlaubsverbrauch | sinkt das Überstundenkonto im Wirkungsbereich |
| admin_aendern | HANDBUCH-ADMIN.md | Unter **„Einzelheiten"** stehen | `Einzelheiten` listet jeden Eintrag |
| admin_aendern | HANDBUCH-ADMIN.md | Notiz und Begründung zusammen höchstens 500 Zeichen. | 10 bis 400 Zeichen |
| admin_aendern | HANDBUCH-ADMIN.md | verliert kein Eintrag angerechnete Zeit, sondern sinken nur das Überstundenkonto oder eine Abwesenheits-Gutschrift | Verliert ein Eintrag angerechnete Zeit, sinkt das Überstundenkonto im Wirkungsbereich |
| admin_aendern | HANDBUCH-ADMIN.md | sind Abwesenheiten betroffen, zusätzlich eine Sammelzeile **„Stundenänderung"** ohne Datum | je Änderung eine Sammelzeile |
| admin_bloecke | HANDBUCH-ADMIN.md | <a id="arbeitszeit-bloecke"></a> | <a id="bloecke-hinterlegen"></a> |
| admin_bloecke | HANDBUCH-ADMIN.md | ### Arbeitszeit-Blöcke (Soll-Arbeitszeit je Wochentag) | ### Wie hinterlege ich Arbeitszeit-Blöcke? |
| admin_bloecke | HANDBUCH-ADMIN.md | Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke | Tagessoll = Summe der Blöcke minus diese Pause |
| admin_bloecke | HANDBUCH-ADMIN.md | 08:00–12:15 und 14:45–18:00 = 7:30 h | 14:45–18:00 = **7:30 h** |
| admin_bloecke | HANDBUCH-ADMIN.md | Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert. | Wer von 08:00 bis 18:00 durchstempelt, bekommt 08:00–12:15 und 14:45–18:00 |
| admin_bloecke | HANDBUCH-ADMIN.md | gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet | gestempelt 08:00–16:00 · angerechnet 5:30 h · 2:30 h zwischen den Blöcken nicht angerechnet |
| admin_bloecke | HANDBUCH-ADMIN.md | Die gesamte gestempelte Zeit (08:00–18:00) wird angerechnet. | Dann wird die gesamte gestempelte Zeit angerechnet |
| admin_bloecke | HANDBUCH-ADMIN.md | Nichtanrechnung ersetzt keine Vergütungsentscheidung. | Nichtanrechnung ersetzt keine Vergütungsentscheidung |
| admin_bloecke | HANDBUCH-ADMIN.md | Im Modus **„Nach Tagen"** (ebenfalls Viertelstunden je Wochentag) | `Nach Tagen` (Stunden je Wochentag) |
| admin_bloecke | HANDBUCH-ADMIN.md | Bei einem Blockbeginn zur vollen Stunde und dem Standardpuffer von 15 Minuten landet | Standard 15, zulässig 0 bis 1439 |
| admin_rest | HANDBUCH-ADMIN.md | **Version 2.9 \| Stand: Oktober 2026 (für PraxisZeit 1.20.0)** | **Stand:** PraxisZeit |
| admin_rest | HANDBUCH-ADMIN.md | Rechenstand der Software (Version 1.20.0) | **Stand:** PraxisZeit |
| admin_rest | HANDBUCH-ADMIN.md | Netto-Spalte; unter der Uhrzeit steht bei gekappten Einträgen | Unter Netto steht bei gekappten Zeilen die nicht angerechnete Zeit |
| admin_rest | HANDBUCH-ADMIN.md | Unterbrechung (Min)** und **Zeiteinträge** | \| Unterbrechung (Min), Zeiteinträge \| |
| admin_rest | HANDBUCH-ADMIN.md | Nicht angerechnet (Min)** (13. Spalte, ab 1.20.0) | \| Nicht angerechnet (Min) \| |
| admin_rest | HANDBUCH-ADMIN.md | **Gestempelt (Von–Bis)** listet jeden Zeiteintrag | \| Gestempelt (Von–Bis), Anwesenheit laut Stempel (Std) |
| admin_rest | HANDBUCH-ADMIN.md | Urlaubs- und Krankheitszeiten verdünnen den Durchschnitt nicht | ohne Tage mit Urlaub, Krankheit, Fortbildung, Sonstiges oder Freistellung |
| admin_rest | HANDBUCH-ADMIN.md | 29.09.2026: übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026). | Wird übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026). |
| admin_rest | HANDBUCH-ADMIN.md | das Ergebnis unter den Hinweisen (*„29.09.2026: übersprungen | der Grund jeder übersprungenen Zeile |
| admin_rest | HANDBUCH-ADMIN.md | und darunter die **Hinweise** – Ruhezeit (§ 5) und Nachtarbeit (§ 6), die der Server bei der Bestätigung selbst prüft, | Ruhezeit (§ 5) und Nachtarbeit (§ 6), die der Server bei der Bestätigung prüft |
| admin_rest | HANDBUCH-ADMIN.md | \| **Anerkennungen** \| | \| Arbeitszeit-Änderungen und Anerkennungen \| |
| admin_rest | HANDBUCH-ADMIN.md | Eine Änderung des Puffers wirkt auf neue Einträge. Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird. | Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird |
| admin_rest | HANDBUCH-ADMIN.md | Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht. | gespeicherte Einträge ändern sich durch das Speichern allein nicht |
| admin_rest | HANDBUCH-ADMIN.md | **Nicht angerechnete Zeit prüfen** | Nicht angerechnete Zeit steht als Zusatzzeile unter der Uhrzeit |
| admin_rest | HANDBUCH-ADMIN.md | Ist = (Ende − Beginn) − Pause − nicht angerechnete Zeit zwischen den Arbeitszeit-Blöcken | Ist** ist die angerechnete Zeit – bei Arbeitszeit-Blöcken nach der Kappung |
| admin_rest | HANDBUCH-ADMIN.md | Zeiten weichen von den Stempeln ab (gestempelt 08:00–18:00) | Weichen die beantragten Zeiten von den Stempeln ab, steht das rot unter **Gewünscht** |
| admin_rest | HANDBUCH-ADMIN.md | nicht angerechnet aktuell 2:30 h | Unter **Aktuell** stehen die nicht angerechnete Lücke und die Stempel des Eintrags |
| admin_rest | HANDBUCH-ADMIN.md | ### §3 ArbZG – 24-Wochen-Durchschnitt | \| 24-Wochen-Durchschnitt §3 ArbZG \| |
| admin_rest | HANDBUCH-ADMIN.md | „laut Stempel Ø > 8 h" | angerechnet und laut Stempel je Werktag |
| admin_rest | HANDBUCH-ADMIN.md | ### §3/§4 ArbZG – Höchstarbeitszeit und Pausenausnahmen | \| Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG \| |
| admin_rest | HANDBUCH-ADMIN.md | sind Abwesenheiten betroffen, zusätzlich eine Sammelzeile ohne Datum (z. B. „Arbeitszeit-Änderung zum | je Änderung eine Sammelzeile |
| admin_rest | HANDBUCH-ADMIN.md | (beide Quelle „wh_change", Anzeige „Stundenänderung") | Quelle „Stundenänderung“ |
| admin_rest | HANDBUCH-ADMIN.md | \| **Ist** \| Angerechnete Arbeitszeit der Zeiteinträge (bei Arbeitszeit-Blöcken nach der Kappung, → 18.3) + gutgeschriebene Abwesenheiten (Krank/Fortbildung) \| | Ist** ist die angerechnete Zeit – bei Arbeitszeit-Blöcken nach der Kappung |
| arbzg_48h | HANDBUCH-ADMIN.md | \| **Wochenhöchstgrenze** \| > 48h/Woche \| Warnung \| § 3 ArbZG \| | \| § 3: mehr als 8 Stunden am Tag, mehr als 48 Stunden in der Woche \| Warnung \| |
| arbzg_48h | HANDBUCH-ADMIN.md | Wochenwarnung > 48h \| | \| § 3: mehr als 8 Stunden am Tag, mehr als 48 Stunden in der Woche \| Warnung \| |
| begriffe | HANDBUCH-MITARBEITER.md | 1 freier Arbeitstag = 1 Urlaubstag, ein halber Tag = 0,5 Urlaubstage – wie bei allen anderen. | Verbraucht wird nach Tagen |
| beschriftung | HANDBUCH-ADMIN.md | „Abwesenheitsanträge genehmigungspflichtig" | **Abwesenheitsanträge genehmigungspflichtig:** |
| mitarbeiter | HANDBUCH-MITARBEITER.md | **Version:** 2.9 · **Stand:** Oktober 2026 (PraxisZeit 1.20.0) | **Stand:** PraxisZeit |
| mitarbeiter | HANDBUCH-MITARBEITER.md | ### 3.3 Arbeitszeit-Blöcke und Anrechnung | Hat Ihre Praxis **Arbeitszeit-Blöcke** für Sie hinterlegt, wird nur die Zeit innerhalb der Blöcke angerechnet |
| mitarbeiter | HANDBUCH-MITARBEITER.md | gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet | gestempelt 08:00–16:00 · angerechnet 5:30 h · 2:30 h zwischen den Blöcken nicht angerechnet |
| mitarbeiter | HANDBUCH-MITARBEITER.md | nicht ausgestempelt – automatisch geschlossen | schließt einen offenen Eintrag eines früheren Tages automatisch |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Das Ende liegt in der Zukunft – die Änderung kann erst nach Arbeitsende beantragt werden. | Es darf nicht in der Zukunft liegen |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Ihre Arbeitszeit wurde ab 01.09.2026 geändert | Hinweis zu Ihrer Arbeitszeit |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Die gesamte gestempelte Zeit soll angerechnet werden. Bitte begründen Sie, warum Sie in dieser Zeit gearbeitet haben. | klicken Sie darunter auf `Anrechnung beantragen`, begründen Sie kurz |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Der Eintrag wurde automatisch geschlossen – bitte das tatsächliche Ende angeben. | tragen Sie dort Ihr tatsächliches Ende ein |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Das Datum bleibt beim Bearbeiten fest. Gehört die Zeit zu einem anderen Tag: Eintrag löschen und oben über „Antrag“ einen Änderungsantrag für diesen Tag stellen. | Beim Bearbeiten bleibt das Datum fest. |
| mitarbeiter | HANDBUCH-MITARBEITER.md | ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00 · Do 08:00–12:00 · 15,5 Std/Woche | listet jede Änderung mit dem Datum, ab dem sie gilt |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Ihr **Ist** ist Ihre angerechnete Arbeitszeit | **Netto** ist die angerechnete Arbeitszeit |
| mitarbeiter | HANDBUCH-MITARBEITER.md | \| **Netto** \| Angerechnete Arbeitszeit nach Abzug der Pause | **Netto** ist die angerechnete Arbeitszeit nach Abzug der Pause |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Einträge für vergangene Tage können nur per Änderungsantrag erstellt werden | Vergangene Tage nur per Antrag |
| mitarbeiter | HANDBUCH-MITARBEITER.md | ändern Sie selbst über **Bearbeiten** neben Ihrem Namen | `Bearbeiten`: Vorname, Nachname und E-Mail ändern |
| restore | HANDBUCH-ADMIN.md | `bash restore.sh <datei>` | bash restore.sh backups/ |
| restore | HANDBUCH-ADMIN.md | `praxiszeit-server.py restore <datei>` | praxiszeit-server.py restore /opt/praxiszeit/data/backups/ |
| restore | HANDBUCH-ADMIN.md | `restore-backup.bat <datei>` | restore-backup.bat data |
| restore | HANDBUCH-ADMIN.md | nur mit dem Zusatz `--force-unverified` | nur mit dem Zusatz --force-unverified |
| restore | HANDBUCH-ADMIN.md | Die Rechte eines **bestehenden** Ordners ändert PraxisZeit nicht | Die Rechte eines bestehenden Ordners ändert PraxisZeit nicht |

## Entfallen (73)

| Gruppe | Datei | alter Wortlaut | Grund |
|---|---|---|---|
| admin_aendern | HANDBUCH-ADMIN.md | [Erfassungsfehler korrigiert] | Notiz-Praefix der Grundtypen ist interne Protokollschrift (eingefroren in reclamp_audit.REASON_TYPES, Backend-Tests); das Handbuch nennt die Grund-Auswahl statt der Praefixe |
| admin_aendern | HANDBUCH-ADMIN.md | [Einvernehmlich vereinbart] | wie [Erfassungsfehler korrigiert] |
| admin_aendern | HANDBUCH-ADMIN.md | Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung | Rechtshinweis steht im neuen Inhalt nicht mehr (bewusste Kuerzung der Broschuere) - Rueckfrage an Manuel empfohlen (Mitbestimmung, § 87 Abs. 1 Nr. 2 BetrVG) |
| admin_aendern | HANDBUCH-ADMIN.md | mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten unwirksam. PraxisZeit prüft das nicht. | Rechtshinweis steht im neuen Inhalt nicht mehr (bewusste Kuerzung der Broschuere) - Rueckfrage an Manuel empfohlen (Mitbestimmung, § 87 Abs. 1 Nr. 2 BetrVG) |
| admin_aendern | HANDBUCH-ADMIN.md | Ab 01.03.2026 bis heute: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 = 15,0 h/Woche | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (Verlaufs-Beispielzeile) |
| admin_aendern | HANDBUCH-ADMIN.md | Automatisch erfasster Ausgangswert vor der ersten Stundenänderung | Ausgangswert-Zeile des Verlaufs: der neue Inhalt beschreibt den Verlauf allgemein (Karte „Meine Arbeitszeit“) |
| admin_aendern | HANDBUCH-ADMIN.md | Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| admin_aendern | HANDBUCH-ADMIN.md | weil inzwischen eine weitere Änderung dazwischen angelegt wurde | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| admin_aendern | HANDBUCH-ADMIN.md | Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: 25,0 h/Woche). | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext, reclamp_audit.notice_text); Handbuch beschreibt den Kasten allgemein |
| admin_aendern | HANDBUCH-ADMIN.md | (neu: 40,0 h/Woche auf 4 Arbeitstage) | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext) |
| admin_aendern | HANDBUCH-ADMIN.md | Eine Änderung, die erst nach heute beginnt, verkürzt beim Löschen nichts | Detailfall des Loeschens; der neue Inhalt nennt nur die Regel (rueckwirkend nur mit Grund) |
| admin_aendern | HANDBUCH-ADMIN.md | Ab dem frühesten Tag ohne Verlust (meist heute; morgen, wenn die Person heute schon gestempelt hat oder eingestempelt ist) bleibt die Änderung ohne Grund möglich. | Detail der Standard-Wirkung beim Loeschen (earliest_lossless_date); neuer Inhalt: „setzt ab heute zurueck“ |
| admin_bloecke | HANDBUCH-ADMIN.md | liegt vollständig zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet werden 0 Stunden. | Grenzfall „0 Stunden in der Luecke“ nennt der neue Inhalt nicht einzeln (Regel steht in so-rechnet) |
| admin_bloecke | HANDBUCH-ADMIN.md | gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (zweites Zusatzzeilen-Beispiel) |
| admin_bloecke | HANDBUCH-ADMIN.md | Arbeitszeit-Fenster (Altbestand, nur Kappung) | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| admin_bloecke | HANDBUCH-ADMIN.md | Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht. | Rechtshinweis steht im neuen Inhalt nicht mehr (bewusste Kuerzung der Broschuere) - Rueckfrage an Manuel empfohlen (Schichtzeit/Jugendliche) |
| admin_bloecke | HANDBUCH-ADMIN.md | Mitarbeitende lesen an den Lückenhinweisen zu geschlossenen Einträgen (nicht beim Einstempeln) zusätzlich | Detail der Lueckenhinweise; die zugehoerige forbid-Pruefung bleibt |
| admin_bloecke | HANDBUCH-ADMIN.md | Bis Version 1.19.2 wurde ein Feiertag auf einem Werktag wie ein normaler Arbeitstag gekappt. | Reparaturweg fuer Feiertagseintraege aus <= 1.19.2 steht nicht mehr im Handbuch (Altlast-Hinweis) |
| admin_bloecke | HANDBUCH-ADMIN.md | speichern ihn unverändert, wird er mit der tatsächlich gestempelten Zeit neu berechnet. | wie Feiertags-Reparaturweg (<= 1.19.2) |
| admin_bloecke | HANDBUCH-ADMIN.md | neu auch automatisch geschlossene Einträge | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| admin_bloecke | HANDBUCH-ADMIN.md | Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15) | Grenzfall P18 (eingetragenes Ende = angerechnetes Ende) nennt der neue Inhalt nicht mehr; Verhalten bleibt durch Backend-Tests gedeckt |
| admin_rest | HANDBUCH-ADMIN.md | Von 07:45, Bis 18:15, Netto 8,00, Nicht angerechnet 240 | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (Export-Beispielzeile) |
| admin_rest | HANDBUCH-ADMIN.md | inkl. Unterbrechung, Zeiteinträge und Nicht angerechnet | Spaltenliste steht jetzt in der Export-Tabelle (siehe ersetzte Pruefungen zu Unterbrechung/Nicht angerechnet) |
| admin_rest | HANDBUCH-ADMIN.md | Alle genehmigen | Sammelaktion wird im neuen Inhalt nicht mehr genannt |
| admin_rest | HANDBUCH-ADMIN.md | zeigt bei solchen Zeilen – wie bei Korrekturen durch die Verwaltung – „Manuell" | Detail der Quelle-Anzeige „Manuell“ bei Anerkennungen; der neue Inhalt nennt die Quellen „Anrechnung anerkannt“ etc. |
| admin_rest | HANDBUCH-ADMIN.md | steht am selben Tag eine Abwesenheit, zusätzlich je angeglichener Abwesenheit eine Zeile ohne Zeiten | Detail der Protokollzeilen je Abwesenheit; neuer Inhalt: Sammelzeile + Zeile je Eintrag |
| admin_rest | HANDBUCH-ADMIN.md | Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (PRESENCE_BREAK-Hinweis) |
| admin_rest | HANDBUCH-ADMIN.md | \| **Pause in der Lücke** \| | Tabellenzeile „Pause in der Luecke“ nennt der neue Inhalt nicht mehr einzeln |
| admin_rest | HANDBUCH-ADMIN.md | **Arbeitszeit-Blöcke – weitere Rechtsgrundlagen:** | Rechtshinweis steht im neuen Inhalt nicht mehr (bewusste Kuerzung der Broschuere) - Rueckfrage an Manuel empfohlen (Rechtsgrundlagen-Absatz zu Arbeitszeit-Blöcken) |
| admin_rest | HANDBUCH-ADMIN.md | Pause 30 Min. → 6,50 h | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor |
| admin_rest | HANDBUCH-ADMIN.md | Im **PDF** stehen die Einträge in „Von"/„Bis" untereinander | PDF-Detail der Exportspalten, im neuen Inhalt nicht mehr genannt |
| admin_rest | HANDBUCH-ADMIN.md | Eine Konfliktzeile kann beide Kennzeichen tragen | Detail der Konflikt-Kennzeichen, im neuen Inhalt nicht mehr genannt |
| admin_rest | HANDBUCH-ADMIN.md | „keine Werktage im Zeitraum" | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Statuswert der 24-Wochen-Auswertung) |
| admin_rest | HANDBUCH-ADMIN.md | die Grenze gilt für die tatsächliche Arbeitszeit | Satz zur Grenze „tatsaechliche Arbeitszeit“ im neuen Inhalt nicht mehr woertlich |
| admin_rest | HANDBUCH-ADMIN.md | Abwesenheit(en) im Zeitraum 2026-09-01–2026-10-09 auf neues Tagessoll nachgezogen | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Protokollnotiz der Rueckrechnung) |
| admin_rest | HANDBUCH-ADMIN.md | Es gelten die Grenzen für Erwachsene; die strengeren Regeln für Jugendliche (§§ 11, 12 JArbSchG) prüft PraxisZeit nicht | Rechtshinweis steht im neuen Inhalt nicht mehr (bewusste Kuerzung der Broschuere) - Rueckfrage an Manuel empfohlen (Jugendliche, §§ 11, 12 JArbSchG) |
| begriffe | HANDBUCH-ADMIN.md | **Hinweis zu Halbtagen:** Auch ohne Stundenzählung zählt ein halber freier Tag (Option „Halber Tag") **0,5 Urlaubstage** | Halbtags-Hinweis fuer Mitarbeitende ohne Stundenzaehlung steht nicht mehr im Admin-Kapitel; der Halbtag selbst ist im Mitarbeiter-Handbuch („Halber Tag“) erklaert |
| mitarbeiter | HANDBUCH-MITARBEITER.md | (#33-arbeitszeit-blöcke-und-anrechnung) | Anker der alten Nummerierung 3.3 entfaellt; interne Links prueft die Gruppe links |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet wird erst ab 14:45. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Pause in der Lücke wird zusätzlich abgezogen | Detail zur Pause in der Luecke, im neuen Inhalt nicht mehr genannt |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Das Ende liegt in der Zukunft – die Anrechnung kann erst nach Arbeitsende beantragt werden. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Pause zwischen den Arbeitsblöcken | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Du hast vor deinem Soll-Beginn eingestempelt — angerechnet ab 07:45. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Clock-in-Hinweis) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Einstempeln nicht möglich: Ein Zeiteintrag von heute beginnt bereits um 07:45, und der neue Eintrag würde ebenfalls um 07:45 beginnen. Bitte den vorhandenen Eintrag in der Zeiterfassung bearbeiten oder nach 07:45 erneut einstempeln. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (409-Meldung clock_in) |
| mitarbeiter | DocViewer.tsx | Einstempeln nicht möglich: Ein Zeiteintrag von heute beginnt bereits um 07:45 … | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (409-Meldung clock_in) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | gestempelt 19:00 · angerechnet bis 18:15 | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor |
| mitarbeiter | HANDBUCH-MITARBEITER.md | gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (zweites Zusatzzeilen-Beispiel) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | nach 0:30 h Pause | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Anwesenheit nicht angerechnet: 7:30 h | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich |
| mitarbeiter | HANDBUCH-MITARBEITER.md | eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15) · 2:30 h zwischen den Blöcken nicht angerechnet | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (Zusatzzeile eines automatisch geschlossenen Eintrags) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (PRESENCE_BREAK-Hinweis) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Auch ein tatsächliches Ende um **23:59** | Grenzfall „echtes Ende 23:59“ nennt der neue Inhalt nicht mehr; Verhalten durch Backend-Tests gedeckt |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15) | Grenzfall P18 (eingetragenes Ende = angerechnetes Ende) nennt der neue Inhalt nicht mehr; Verhalten bleibt durch Backend-Tests gedeckt |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Dieselbe Meldung erscheint, wenn Sie genau das angerechnete Ende eintragen | Grenzfall P18, siehe oben |
| mitarbeiter | HANDBUCH-MITARBEITER.md | lehnt PraxisZeit die Buchung ab und nennt den Tag, z. B. *„Am 05.10.2026 gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden."* | 409 der Abwesenheitsbuchung an anerkanntem Tag steht im neuen Inhalt nicht mehr (Meldung im Code, absences.CREDIT_OVERRIDE_ABSENCE_DETAIL) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: 25,0 h/Woche). | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext, reclamp_audit.notice_text); Handbuch beschreibt den Kasten allgemein |
| mitarbeiter | HANDBUCH-MITARBEITER.md | (neu: 40,0 h/Woche auf 4 Arbeitstage) | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | auf den vorherigen Stand zurückgesetzt (neu:  | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Dashboard-Hinweistext) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Überstundenkonto im Zeitraum +1:45 h. | Meldungs-/Maskentext steht im Code (Gruppe code prueft den Wortlaut), das Handbuch nennt ihn nicht mehr woertlich (Hinweistext der Rueckrechnung) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Wochenstunden: 15,5 | Rechenbeispiel/Beispielzeile des alten Handbuchs; der neue Inhalt rechnet ein anderes Beispiel (Rechenbeispiele.json, so-rechnet) vor (Profilkarte) |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Übernommenes Arbeitszeit-Fenster | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Diese Zeiten begrenzen nur die Anrechnung der erfassten Zeit; das Tagessoll wird nicht aus ihnen berechnet. | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| mitarbeiter | HANDBUCH-MITARBEITER.md | (neu: 40,0 h/Woche · Mo 07:30–16:30 / Fr 07:30–23:59 (nur Kappung)). | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| mitarbeiter | HANDBUCH-MITARBEITER.md | außer bei einem aus früheren Versionen übernommenen Arbeitszeit-Fenster | Altfenster (Migration 073, nur Kappung) beschreibt der neue Inhalt bewusst nicht mehr |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Bei älteren Einträgen ändern Sie das Datum direkt im Änderungsantrag | Detail (Datum aelterer Eintraege im Antrag) im neuen Inhalt nicht mehr genannt |
| admin_rest | DocViewer.tsx | Spalte „Quelle" dann „Manuell" | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe); Kontexthilfe helpContent.tsx bleibt geprueft |
| mitarbeiter | HANDBUCH-MITARBEITER.md | Fußzeile „Mitarbeiter-Handbuch v2.9 … 1.20.0“ | Fusszeile gibt es im erzeugten Handbuch nicht mehr; die Version steht im Kopf („**Stand:** PraxisZeit x.y.z“, Gruppe versionen + handbuch_md) |
| restore | DocViewer.tsx | <code>bash restore.sh &lt;datei&gt;</code> | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe) |
| restore | DocViewer.tsx | <code>praxiszeit-server.py restore &lt;datei&gt;</code> | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe) |
| restore | DocViewer.tsx | <code>restore-backup.bat &lt;datei&gt;</code> | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe) |
| restore | DocViewer.tsx | nur mit dem Zusatz <code>--force-unverified</code> | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe) |
| restore | DocViewer.tsx | Die Rechte eines <strong>bestehenden</strong> Ordners ändert PraxisZeit nicht | Der Handbuch-Teil von DocViewer.tsx entfaellt; der Sachverhalt wird weiter gegen die erzeugte HANDBUCH-ADMIN.md geprueft (ersetzte Pruefung in derselben Gruppe) |

## Inhaltliche Lücken zur Entscheidung (nicht nur Wortlaut)

Diese Aussagen standen im alten Handbuch und stehen im neuen Inhalt nicht mehr; sie sind keine Kürzung von Beispielen, sondern fachliche Hinweise:

- Mitbestimmung: Arbeitszeit-Blöcke, die den Umfang der Arbeitszeit ändern, sind eine Vertragsänderung bzw. nach § 87 Abs. 1 Nr. 2 BetrVG mitbestimmungspflichtig; PraxisZeit prüft das nicht.
- Jugendliche: strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG), PraxisZeit prüft nur die Erwachsenen-Grenzen.
- Altfenster (Migration 073, „nur Kappung“) und Reparaturweg für Feiertagseinträge aus Version <= 1.19.2.
- Grenzfälle der Auto-Close-Kennzeichnung (echtes Ende 23:59, Ende = angerechnetes Ende, P18).
- 409-Meldung der Abwesenheitsbuchung an einem anerkannten Tag.

## DocViewer.test.tsx

Die Handbuch-Fälle prüfen jetzt den Text der `HandbookPage` der Inhalte (`handbookText('praxisleitung' | 'mitarbeitende')`); die Verbotswörter (`FORBIDDEN_TERMS`, Quelle `frontend/src/handbuch/content/forbiddenTerms.ts`) gelten weiter für beide Handbücher und die Kurzanleitung (`expectNoStaleTerms`) und stehen zusätzlich in `content/content.test.ts`.

**Pflichtwörter umgestellt:** `Tagessoll = Summe der Blockdauern − Pause innerhalb der Blöcke` → `Tagessoll = Summe der Blöcke minus diese Pause`; `auf den vorherigen Stand zurücksetzen` → `auf den vorherigen Stand zurück`; `Eine Änderung des Puffers wirkt auf neue Einträge.` → `Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn`; `Nichtanrechnung ersetzt keine Vergütungsentscheidung.` → ohne Schlusspunkt; `Rückwirkend löschen mit Neuberechnung` → `Rückwirkend ab … mit Neuberechnung`; `Unterbrechung (Min) und Zeiteinträge` → `Unterbrechung (Min), Zeiteinträge`; Puffer-Satz gekürzt auf `Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer`; XLS-Import-Vorschau → `Unter Netto steht bei gekappten Zeilen die nicht angerechnete Zeit`; Mitarbeitende `Das Datum bleibt beim Bearbeiten fest.` → `Beim Bearbeiten bleibt das Datum fest.`, `erst nach Arbeitsende` → `Es darf nicht in der Zukunft liegen`, Profil-Satz → `Vorname, Nachname und E-Mail ändern`; Abschnittstitel `15. Admin-Passwort verloren` → `Admin-Passwort` + `reset-admin-password`; Vertragsverlauf `Vorschlag übernehmen (N)` → `Vorschlag übernehmen`. Neu aufgenommen: `Werktag ohne Block = 0 Stunden` (Praxisleitung), `Werktag ohne Block = freier Tag`, `Arbeitsende per Antrag nachtragen` (Mitarbeitende).

**Pflichtwörter entfallen (Inhalt nennt es nicht mehr):** Abschnittstitel `3. Arbeitszeit-Blöcke, Rückwirkung & Anerkennen` und `5. Arbeitszeit-Blöcke & Anrechnung` (Nummerierung entfällt); `[Erfassungsfehler korrigiert]`; `§ 87 Abs. 1 Nr. 2 BetrVG`, `PraxisZeit prüft das nicht.`, `Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln` (Rechtshinweise, siehe oben); `Details in Abschnitt 9`; `Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.`; `Notiz und Begründung zusammen höchstens 500 Zeichen.`; `Auch ein tatsächliches Ende um 23:59`; `vorher automatisch geschlossen`; `beendet die Blöcke ab dem Wirkungsdatum`; P18-Satz (Ende = angerechnetes Ende); die vier Sätze zu Bearbeiten-Formular/„geplant“ (Gesamtreview 1.20 Fund 6/25/14); `Pause zwischen den Arbeitsblöcken`; `Ihre Arbeitszeit wurde ab 01.09.2026 geändert`; `(neu: 40,0 h/Woche auf 4 Arbeitstage)`; der 23:59-Satz der Mitarbeitenden; `gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden.`; `Urlaubsanspruch {Jahr}`, `Urlaub verbraucht {Jahr}`; Profil-Verbot `Persönliche Daten wie Name und Wochenstunden können nur vom Administrator geändert werden` bleibt als Negativprüfung (steht im neuen Text nirgends).
