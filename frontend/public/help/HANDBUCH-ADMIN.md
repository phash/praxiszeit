<!-- Erzeugt aus frontend/src/handbuch — nicht von Hand bearbeiten -->

# Handbuch für die Praxisleitung

**Stand:** PraxisZeit 1.23.0

So richten Sie PraxisZeit ein, behalten Ihr Team im Blick, pflegen Verträge und Arbeitszeiten und entscheiden über Anträge. Jede Aufgabe beginnt mit einer Frage – suchen Sie sich die passende heraus.

<a id="erste-einrichtung"></a>
## Erste Einrichtung

*Einmal einrichten, dann läuft es: Einstellungen prüfen, das Team anlegen, die Arbeitszeiten hinterlegen. Als Praxisleitung sehen Sie alles, was Ihre Mitarbeitenden sehen – und zusätzlich den Bereich **Administration**.*

<a id="verwaltung-finden"></a>
### Wo finde ich die Verwaltung?

Melden Sie sich mit den Admin-Zugangsdaten an, die bei der Installation gesetzt wurden. Oben in der Seitenleiste steht Ihre eigene Zeiterfassung, darunter der Abschnitt **Administration**.

![Seitenleiste der Praxisleitung: unter „Administration“ Admin-Dashboard, Benutzerverwaltung und Arbeitszeiten im Team, unten der Knopf „Schnellstart“](/help/img/pl-navigation.webp)

1. `Admin-Dashboard`: Soll, Ist und Saldo des ganzen Teams für den Monat oder die Woche.
2. `Benutzerverwaltung`: Mitarbeitende anlegen, bearbeiten, deaktivieren, Arbeitszeit anpassen.
3. `Arbeitszeiten im Team`: wer laut Arbeitszeit-Blöcken wann arbeitet. Darunter folgen u. a. `Änderungsanträge`, `Berichte`, `Anträge` und `Einstellungen`.
4. `Schnellstart` öffnet die Kurzanleitung für die ersten Schritte. Daneben stehen `Cheat-Sheet` und `Admin-Handbuch`.

> **Gut zu wissen:** Eine rote Zahl neben `Änderungsanträge` oder `Anträge` zeigt, wie viele Anträge auf Ihre Entscheidung warten.

<a id="erste-schritte-checkliste"></a>
### Was richte ich zuerst ein?

Die Reihenfolge aus dem Schnellstart – einmal durchgehen, danach läuft die Zeiterfassung.

1. **Eigenes Passwort ändern:** `Profil` → `Passwort ändern`.
2. **Einstellungen:** Bundesland für die Feiertage, Genehmigungspflicht für Urlaub, Sondertage 24./31.12. und die Willkommens-Tour für neue Mitarbeitende.
3. **Team anlegen:** je Person ein Konto mit Wochenstunden, Arbeitstagen und Urlaubsanspruch, siehe [Neue Person anlegen](#mitarbeiter-anlegen).
4. **Arbeitszeit hinterlegen:** gleichmäßig, nach Tagen oder als Arbeitszeit-Blöcke, siehe [Arbeitszeit-Blöcke hinterlegen](#bloecke-hinterlegen).
5. **Erste Zeiterfassung prüfen:** Die Mitarbeitenden melden sich an und stempeln; im `Admin-Dashboard` sehen Sie Stunden, Salden und fehlende Buchungen.

<a id="bundesland-einstellen"></a>
### Wie stelle ich das Bundesland für die Feiertage ein?

Klicken Sie in der Navigation auf `Einstellungen`.

![Einstellungen, Abschnitt Feiertage: Auswahl des Bundeslands (Bayern) für die gesetzlichen Feiertage mit dem Knopf „Speichern“](/help/img/pl-bundesland.webp)

1. Scrollen Sie zum Abschnitt **Feiertage**.
2. Wählen Sie Ihr **Bundesland**. PraxisZeit trägt dessen gesetzliche Feiertage ein; an Feiertagen gibt es kein Soll.
3. Klicken Sie auf `Speichern`.

> **Achtung:** **Später das Bundesland wechseln?** Dann berechnet PraxisZeit die gesetzlichen Feiertage aller Jahre neu – auch zurückliegender; Soll und Salden dieser Jahre ändern sich entsprechend. Eigene Feiertage bleiben erhalten. Betrifft die Änderung ein bereits abgeschlossenes Jahr, weist PraxisZeit auf den veralteten Übertrag hin.

> **Gut zu wissen:** **Aufbewahrungspflicht (§ 16 ArbZG):** Arbeitszeitaufzeichnungen sind mindestens 2 Jahre aufzubewahren. Sorgen Sie von Anfang an für Datensicherungen.

<a id="dashboard-teamuebersicht"></a>
## Dashboard & Teamübersicht

*Das **Admin-Dashboard** zeigt Soll, Ist und Saldo aller Mitarbeitenden. **Arbeitszeiten im Team** zeigt, wer laut Vertrag wann da ist – so fallen Lücken in der Besetzung sofort auf.*

<a id="fehlende-buchungen-team"></a>
### Wer hat vergessen zu stempeln?

Auf Ihrem eigenen `Dashboard` steht oben ein gelber Kasten, sobald im Team etwas fehlt.

![Gelber Kasten „Fehlende Buchungen im Team“ auf dem Dashboard der Praxisleitung mit dem Eintrag „Thomas Bauer: 22.10.“](/help/img/pl-fehlende-buchungen.webp)

1. **Fehlende Buchungen im Team** erscheint nur, wenn bei mindestens einer Person etwas fehlt. Er nennt je Person die Tage: ein vergangener Arbeitstag des laufenden Monats ohne Zeiteintrag und ohne Abwesenheit, oder „(offen)“ für einen Eintrag eines früheren Tages ohne Ende. Feiertage und Tage ohne Tagessoll zählen nicht.

> **Gut zu wissen:** Die Mitarbeitenden sehen denselben Hinweis als roten Kasten „Buchung fehlt“ auf ihrem Dashboard und tragen den Tag per Antrag nach. Den Antrag entscheiden Sie unter `Änderungsanträge`, siehe [Korrekturantrag prüfen](#korrekturantrag-pruefen).

<a id="team-monatsuebersicht"></a>
### Wie steht mein Team in diesem Monat?

Klicken Sie in der Navigation auf `Admin-Dashboard`. Die Monatsübersicht zeigt alle aktiven Mitarbeitenden.

![Admin-Dashboard, Monatsübersicht Oktober: je Person Wochenstunden, Soll, Ist, Saldo, kumulierte Überstunden, Urlaub und Krank](/help/img/pl-admin-dashboard.webp)

1. Mit `Monat` und `Woche` schalten Sie zwischen Monats- und Wochenansicht um. Ihre Wahl merkt sich der Browser.
2. Mit den Pfeilen blättern Sie monats- bzw. wochenweise.
3. **Soll:** `bis heute` zählt das Soll nur bis zum letzten abgeschlossenen Arbeitstag, `Monatsende` den vollen Monat (in der Woche: `volle Woche`). Für abgeschlossene Monate sind beide gleich.
4. **Saldo** ist Ist minus Soll (Plus = Überstunden, Minus = Fehlstunden); **Überstd. kum.** ist der Stand des Überstundenkontos.
5. Der Pfeil am Zeilenende öffnet die Details der Person.

> **Gut zu wissen:** **Ist** ist die angerechnete Zeit – bei Arbeitszeit-Blöcken nach der Kappung – samt Gutschrift für Krankheit und Fortbildung. Die Einstellung „bis heute“ gilt nur für die Live-Übersichten. Datei-Exporte, Monatsjournal und Jahresabschluss rechnen immer den vollen Monat bzw. das volle Jahr. Mehr dazu: [So rechnet PraxisZeit: Monatssoll und Saldo „bis heute“](SO-RECHNET-PRAXISZEIT.md#monatssaldo).

<a id="mitarbeiter-details-ansehen"></a>
### Wie sehe ich die Einträge einer Person?

Klicken Sie im Admin-Dashboard am Ende der Zeile auf den Pfeil.

![Detailansicht von Maria Hoffmann im Admin-Dashboard mit Benutzerinformationen, Soll, Ist, Saldo und der Liste ihrer Zeiteinträge](/help/img/pl-mitarbeiter-details.webp)

1. Oben stehen Benutzerinformationen sowie Soll, Ist, Saldo und Überstunden kum. des gewählten Monats.
2. `Neuer Eintrag` legt für die Person einen Zeiteintrag oder eine Abwesenheit an.
3. In der Liste der Zeiteinträge bearbeiten (Stift) oder löschen (Papierkorb) Sie einzelne Einträge. Ist Zeit nicht angerechnet, steht hier auch `Anerkennen`.

<a id="arbeitszeiten-im-team"></a>
### Wer arbeitet laut Vertrag wann?

Klicken Sie in der Navigation auf `Arbeitszeiten im Team`. Je Person stehen die Arbeitszeit-Blöcke von Montag bis Freitag als Balken in ihrer Kalenderfarbe.

![Übersicht „Arbeitszeiten im Team“: je Person die Arbeitszeit-Blöcke von Montag bis Freitag als Balken, darüber die Besetzung je halbe Stunde](/help/img/pl-team-arbeitszeiten.webp)

1. **Stand am:** Gezeigt werden die Blöcke, die an diesem Tag gelten. Ein späterer Tag zeigt schon eingetragene künftige Arbeitszeiten.
2. `Alle` oder eine Abteilung filtert die Liste. Die Auswahl entsteht aus dem Feld „Abteilung/Bereich“ der Mitarbeitenden.
3. **Besetzung** zeigt je halbe Stunde, wie viele der gefilterten Personen eingeplant sind – der Tooltip nennt die Namen.
4. Je Person: Name, Wochenstunden und die Blöcke. Personen ohne Blöcke stehen mit „keine Arbeitszeit-Blöcke“ in der Liste.

> **Gut zu wissen:** Steht bei einer Person „ab … neu“, ist für sie eine spätere Änderung hinterlegt; die neuen Zeiten stehen im Tooltip. Wer am gewählten Tag außerhalb seines Beschäftigungszeitraums liegt, wird nicht aufgeführt.

<a id="team-arbeitszeiten-bearbeiten"></a>
### Kann ich Blöcke direkt in der Übersicht verschieben?

Ja, als Entwurf. Gespeichert wird immer über den Dialog „Arbeitszeit \& Wochenstunden“ – mit Vorschau und denselben Schutzregeln wie jede Arbeitszeit-Änderung.

![Arbeitszeiten im Team mit eingeschaltetem Schieber „Bearbeiten“: Hinweis zum Ziehen der Blöcke und bei jeder Person der Link „Ändern…“](/help/img/pl-team-bearbeiten.webp)

1. Schalten Sie rechts oben den Schieber `Bearbeiten` ein. Vorher lässt sich nichts verschieben.
2. Einen Block **ziehen** verschiebt ihn; am linken oder rechten Rand ziehen ändert Beginn bzw. Ende, im 15-Minuten-Raster. Geänderte Zeilen sind gelb hinterlegt; `Verwerfen` stellt den gespeicherten Stand wieder her.
3. `Ändern…` unter dem Namen öffnet den Dialog direkt – für Personen ohne Blöcke der einzige Weg. Nach dem Ziehen steht dort `Änderung speichern…`: Der Dialog öffnet mit den neuen Blöcken, „Gültig ab“ ist der Tag unter „Stand am“.

> **Gut zu wissen:** Per Tastatur: Block anwählen, Pfeiltasten verschieben um 15 Minuten, mit Umschalt ändert sich das Ende. Feinere Zeiten (5-Minuten-Raster), weitere Blöcke und die Pause innerhalb der Blöcke stellen Sie im Dialog ein. Solange Änderungen offen sind, ist „Stand am“ gesperrt.

<a id="mitarbeitende-vertrag"></a>
## Mitarbeitende anlegen, Vertragsdaten und Vertragsverlauf

*Jede Person bekommt ein eigenes Konto. Wochenstunden, Arbeitstage, Urlaubsanspruch und Stundenzählung bilden ihren **Vertrag** – und jede spätere Änderung gilt ab einem Datum, damit frühere Monate stimmen.*

<a id="benutzerliste"></a>
### Wo sehe ich alle Mitarbeitenden?

Klicken Sie in der Navigation auf `Benutzerverwaltung`.

![Benutzerverwaltung: Liste aller Mitarbeitenden mit Benutzername, Rolle, Wochenstunden, Arbeitstagen, Urlaubskonto und Überstunden seit Jahresbeginn](/help/img/pl-benutzerliste.webp)

1. Oben rechts: `Inaktive anzeigen` bzw. `Ausgeblendete anzeigen` blendet deaktivierte bzw. ausgeblendete Konten ein; `Neue:r Mitarbeiter:in` öffnet das Anlegeformular.
2. **Urlaubskonto:** Budget, genommen und übrig in Tagen, mit Ampelbalken.
3. **Überstunden (JTD):** der Überstundensaldo seit Jahresbeginn. Bei Mitarbeitenden ohne Stundenzählung steht hier „—“.

<a id="benutzer-aktionen"></a>
### Welche Aktionen gibt es je Person?

Die Symbole stehen rechts in der Spalte **Aktionen**; ist das Fenster schmal, scrollen Sie die Tabelle nach rechts.

![Aktionsspalte einer Person in der Benutzerverwaltung mit den Symbolen für Monatsjournal, Bearbeiten, Arbeitszeit und Deaktivieren](/help/img/pl-benutzer-aktionen.webp)

1. **Monatsjournal anzeigen** (Buch): jeder Tag des Monats mit Zeiteinträgen und Abwesenheiten. Hier tragen Sie auch an Wochenend- und Feiertagen ein.
2. **Bearbeiten** (Stift): Name, Rolle, E-Mail, Abteilung, Ein- und Austritt.
3. **Arbeitszeit \& Wochenstunden** (Uhr): Arbeitszeit und Vertragsdaten mit Wirkungsdatum ändern.
4. **Deaktivieren** (Person mit X): Die Person kann sich nicht mehr anmelden, ihre Daten bleiben erhalten. Über `Inaktive anzeigen` holen Sie sie mit „Reaktivieren“ zurück.

> **Gut zu wissen:** Weitere Symbole: **Passwort setzen**, **Vorjahresübernahme**, **Ausblenden** und **Als diese:n Mitarbeiter:in ansehen (nur Lesen)**. Diese Ansicht zeigt PraxisZeit aus Sicht der Person, ändern lässt sich dort nichts; ein Banner führt mit `Zurück zu Admin` zurück. Jede solche Sitzung wird protokolliert, Gesundheitsdaten erscheinen dort nur als „Abwesend“.

> **Achtung:** **Nicht löschen, deaktivieren:** Arbeitszeitaufzeichnungen sind mindestens 2 Jahre aufzubewahren (§ 16 ArbZG). Das letzte aktive Admin-Konto lässt sich weder deaktivieren noch herabstufen – ernennen Sie vorher eine weitere Person zum Admin. Wenn eine Person ihr Recht auf Löschung geltend macht, gehen Sie wie unten beschrieben vor.

<a id="mitarbeiter-loeschen"></a>
### Wie entferne ich eine Person endgültig (DSGVO Art. 17)?

Für das Recht auf Löschung gibt es zwei Stufen. Sie lösen den Konflikt zwischen Löschpflicht und der Aufbewahrungspflicht für Arbeitszeitaufzeichnungen (§ 16 ArbZG, mindestens 2 Jahre). Beide setzen voraus, dass das Konto zuerst deaktiviert wurde.

1. **Deaktivieren** Sie die Person in der Aktionsspalte. Damit beginnt eine **Sperrfrist von 14 Tagen**; in der Liste zeigt ein Schloss mit der Zahl der Resttage, wie lange die Anonymisierung noch gesperrt ist.
2. Blenden Sie über `Inaktive anzeigen` die deaktivierten Konten ein. Nach der Sperrfrist erscheint das Symbol **Anonymisieren**. Es entfernt Name, Benutzername, E-Mail und weitere persönliche Angaben und löscht die Abwesenheiten; die **Zeiteinträge bleiben** für die Aufbewahrungspflicht erhalten.
3. **Endgültig löschen** (Papierkorb-Symbol) gibt es erst für das anonymisierte Konto, und nur wenn die jüngste aufbewahrungspflichtige Aufzeichnung **mindestens 730 Tage** alt ist. Es entfernt die Person samt Zeiteinträgen, Abwesenheiten und Anträgen unwiderruflich; vorher blockiert PraxisZeit mit einem Hinweis auf die Frist.

> **Gut zu wissen:** Beide Vorgänge lassen sich nicht rückgängig machen und stehen im Änderungsprotokoll (Rechenschaftspflicht nach Art. 5 Abs. 2 DSGVO).

<a id="mitarbeiter-anlegen"></a>
### Wie lege ich eine neue Person an?

Klicken Sie in der Benutzerverwaltung auf `Neue:r Mitarbeiter:in`. Über der Liste erscheint das Formular.

![Formular „Neue:n Benutzer:in anlegen“ für Lena Wagner mit Benutzername, Passwort, 30 Wochenstunden, 4 Arbeitstagen und der Urlaubs-Empfehlung 24 Tage](/help/img/pl-neu-anlegen.webp)

1. **Benutzername:** eindeutiger Login-Name, z. B. „lena“. Dazu optional E-Mail, Vor- und Nachname.
2. **Passwort:** Startpasswort mit mindestens 10 Zeichen, einem Groß- und einem Kleinbuchstaben und einer Ziffer. Die Person ändert es danach selbst.
3. **Wochenstunden:** vertraglich vereinbart, in Viertelstunden-Schritten (z. B. 20,25).
4. **Arbeitstage pro Woche** (1–7).
5. **Urlaubstage:** Jahresanspruch in Tagen. Der Vorschlag rechnet 30 × Arbeitstage ÷ 5 – bei 4 Tagen also 24; `Übernehmen` trägt ihn ein, Sie können ihn überschreiben.

<a id="mitarbeiter-optionen"></a>
### Was bedeuten die weiteren Felder im Anlegeformular?

Scrollen Sie im Formular nach unten.

![Unterer Teil des Anlegeformulars: erster und letzter Arbeitstag, Abteilung/Bereich, die Wahl der Arbeitszeit (Gleichmäßig, Nach Tagen, Nach Arbeitsblöcken) und Speichern](/help/img/pl-neu-anlegen-optionen.webp)

1. **Stundenzählung aktiv** (weiter oben): Haken weg für Mitarbeitende ohne Stundenzählung – kein Soll und Ist, keine Überstunden; Urlaub und Krankheit werden trotzdem tagebasiert geführt.
2. **ArbZG-Prüfungen aussetzen (§18 ArbZG – leitende Angestellte):** nur für Personen, die tatsächlich unter § 18 ArbZG fallen. Darunter: **Nachtarbeitnehmer** (§ 6 ArbZG).
3. **Nimmt an Betriebsferien teil:** Die Person bekommt bei Betriebsferien automatisch die Abwesenheiten – unabhängig von der Rolle. Für reine Verwaltungskonten abwählbar.
4. **Erster / Letzter Arbeitstag:** Soll wird nur innerhalb dieses Zeitraums berechnet, der Urlaubsanspruch im Ein- und Austrittsjahr anteilig.
5. **Arbeitszeit:** `Gleichmäßig`, `Nach Tagen` (Stunden je Wochentag) oder `Nach Arbeitsblöcken` (Zeiten je Wochentag).
6. Klicken Sie auf `Speichern`.

> **Achtung:** **Eintritt im laufenden Jahr:** Tragen Sie den **Ersten Arbeitstag** ein. Ohne ihn zählt PraxisZeit das Soll auch für die Tage vor dem Eintritt – es entstehen Minusstunden, die es nicht gibt.

> **Gut zu wissen:** **Zwei getrennte Haken:** „Stundenzählung aktiv“ entscheidet nur, ob Soll und Ist geführt werden; mit § 18 ArbZG hat das nichts zu tun. Die § 18-Ausnahme ist eine eigene Einstellung – beide lassen sich frei kombinieren. Wer aus einem anderen System kommt, trägt den bisherigen Stand unter **Anfangssaldo Überstunden** und **Übertrag Urlaubstage** ein.

<a id="mitarbeiter-bearbeiten"></a>
### Warum kann ich die Wochenstunden im Bearbeiten-Formular nicht ändern?

Klicken Sie in der Aktionsspalte auf **Bearbeiten**. Alles, was das Soll oder den Urlaub bestimmt, gilt ab einem Datum und wird deshalb nicht hier geändert.

![Formular „Benutzer bearbeiten“ von Petra Schulz: Wochenstunden als Anzeige mit dem Knopf „Arbeitszeit anpassen…“ und darunter „Urlaub und Abrechnung“](/help/img/pl-bearbeiten.webp)

1. **Wochenstunden** und Arbeitstage stehen nur als Anzeige da – immer die heute gültigen Werte.
2. `Arbeitszeit anpassen…` öffnet den Dialog „Arbeitszeit \& Wochenstunden“; dort ändern Sie mit Wirkungsdatum.
3. **Urlaub und Abrechnung:** Urlaubsanspruch, Stundenzählung und Minijob-Einstellungen, ebenfalls nur Anzeige („Ändern über „Arbeitszeit anpassen…““).
4. **Resturlaub verfällt am:** eine eigene Verfallsfrist für diese Person. Es ist ein festes Datum für alle Jahre – nach Ablauf anpassen oder leeren; leer gilt der 31.03. des Folgejahres. Liegt das Datum in der Vergangenheit, warnt das Formular (Speichern bleibt möglich). Das Datum steht im Urlaubskonto der Person und in der Jahresend-Warnung der Verwaltung.

<a id="vertragsverlauf"></a>
### Wie ändere ich den Urlaubsanspruch oder die Arbeitszeit ab einem Datum?

Klicken Sie auf `Arbeitszeit anpassen…` oder in der Benutzerliste auf das Uhr-Symbol. Jede Änderung wird zu einer Zeile im **Verlauf** – dem Vertragsverlauf der Person.

![Dialog „Arbeitszeit & Wochenstunden“ von Petra Schulz: Gültig ab, Urlaubsanspruch 18 Tage und der Verlauf mit zwei Zeilen (16 und 18 Tage/Jahr)](/help/img/pl-vertragsverlauf.webp)

1. **Gültig ab:** ab wann die neue Regelung gilt.
2. Unter **Urlaub und Abrechnung** stehen „Urlaubsanspruch pro Jahr ab diesem Datum“, „Stundenzählung aktiv“ und die Minijob-Einstellungen. Ändern Sie die Arbeitstage, schlägt der Dialog einen neuen Anspruch vor (`Vorschlag übernehmen (N)`).
3. Prüfen Sie die Auswirkung über dem Knopf und klicken Sie auf `Speichern`. Solange die Eingabe dem Stand entspricht, der an diesem Datum ohnehin gilt, bleibt der Knopf gesperrt.
4. **Verlauf:** jede Regelung als „Ab … bis …“; die jüngste läuft „bis heute“.

> **Gut zu wissen:** **Anspruch wechselt im Jahr:** Dann rechnet PraxisZeit jeden Abschnitt anteilig nach Monaten. Beispiel: 16 Tage bis September, 18 Tage ab 1. Oktober ergeben 16 × 9/12 + 18 × 3/12 = **16,5 Tage** für das Jahr, ab dem Folgejahr 18. Mehr dazu: [So rechnet PraxisZeit: Urlaubskonto](SO-RECHNET-PRAXISZEIT.md#urlaubskonto).

> **Achtung:** **Minijob-Einstellungen** (MiLoG-Arbeitszeitkonto, vereinbarte Monatsarbeitszeit, festes Monats-Soll) lassen sich nur zum **Monatsersten** ändern. Sinkt der Urlaubsanspruch rückwirkend, ist das eine Verkürzung und braucht einen Grund, siehe [Rückwirkend ändern](#rueckwirkend-aendern).

<a id="arbeitszeit-bloecke-aenderungen"></a>
## Arbeitszeit-Blöcke & Änderungen

***Arbeitszeit-Blöcke** legen je Wochentag fest, wann eine Person laut Vertrag arbeitet – z. B. 08:00–12:00 und 15:00–16:00. Daraus folgen das Tagessoll und die Anrechnung: Zeit vor, nach und zwischen den Blöcken zählt nur bis zum Puffer.*

<a id="bloecke-hinterlegen"></a>
### Wie hinterlege ich Arbeitszeit-Blöcke?

Öffnen Sie den Dialog „Arbeitszeit \& Wochenstunden“ (Uhr-Symbol in der Benutzerliste oder `Arbeitszeit anpassen…`).

![Block-Editor im Dialog „Arbeitszeit & Wochenstunden“ für Sarah Klein: Gültig ab, Modus „Nach Arbeitsblöcken“ und Montag und Dienstag mit den Blöcken 08:00–12:00 und 15:00–16:00 samt Pause](/help/img/pl-bloecke.webp)

1. **Gültig ab:** ab wann die Blöcke gelten.
2. Wählen Sie `Nach Arbeitsblöcken`. Den Modus gibt es nur bei aktiver Stundenzählung.
3. Je Wochentag (Mo–Fr) tragen Sie „von–bis“ ein, im 5-Minuten-Raster. Blöcke dürfen sich nicht überschneiden und nicht direkt aneinanderstoßen – 08:00–12:00 und 12:00–16:00 erfassen Sie als einen Block.
4. `+ Block` fügt einen weiteren Block hinzu (höchstens drei je Tag), das **×** entfernt einen. Ein Tag ohne Block ist kein Arbeitstag.
5. **Pause innerhalb** der Blöcke in Minuten. Tagessoll = Summe der Blöcke minus diese Pause; der Dialog zeigt es je Tag live.
6. Unter dem Freitag steht die Woche mit Gesamtzeit, Wochensoll und Arbeitstagen. Prüfen Sie die Auswirkung und speichern Sie.

> **Gut zu wissen:** **Beispiel:** Blöcke 08:00–12:00 und 15:00–18:00, Pause 0, Puffer 15 Minuten. Wer von 08:00 bis 18:00 durchstempelt, bekommt 08:00–12:15 und 14:45–18:00 = **7:30 h** angerechnet; die 2:30 h dazwischen werden nicht angerechnet. Die gestempelten Zeiten bleiben unverändert gespeichert (§ 16 ArbZG). Eine geplante Pause erfassen Sie als „Pause innerhalb der Blöcke“, nicht als kurze Lücke – eine Lücke bis zum doppelten Puffer verschwindet ganz. Mehr dazu: [So rechnet PraxisZeit: Arbeitszeit-Blöcke und Kappung](SO-RECHNET-PRAXISZEIT.md#bloecke-kappung).

> **Achtung:** **Werktag ohne Block = 0 Stunden:** Hat eine Person Blöcke, aber an einem Werktag keinen, wird dort gestempelte Zeit gespeichert, aber nicht angerechnet – erst wenn Sie den Eintrag anerkennen oder den Antrag „Anrechnung beantragen“ mit `Genehmigen und anerkennen` annehmen. Ein aus früheren Versionen übernommenes Arbeitszeit-Fenster ist davon nicht betroffen: Ein Tag ohne Fenster wird dort weiter nicht gekappt. An Wochenenden, Feiertagen und als „frei“ eingestellten Sondertagen wird nichts gekappt. Mitarbeitende ohne Stundenzählung und anerkannte Einträge sind ausgenommen; bei § 18-befreiten Personen wird trotzdem gekappt.

> **Gut zu wissen:** **Anderer Modus beendet die Blöcke:** Speichern Sie mit `Gleichmäßig` oder `Nach Tagen`, enden die Arbeitszeit-Blöcke mit dieser Änderung; ab dem Gültig-ab-Datum wird nicht mehr gekappt. Bei **fester Monatsarbeitszeit** (Minijob) steht im Dialog „geplant“ statt „Tagessoll“ bzw. „Wochensoll“ – die Werte sind geplante Anwesenheit, kein Soll. Das Bearbeiten-Formular zeigt dagegen immer den heute gültigen Stand, auch nach dem Wirkungsdatum einer zukunftsdatierten Änderung.

> **Gut zu wissen:** **Arbeitszeit-Fenster (Altbestand, nur Kappung):** Das Update auf 1.20.0 hat jedes bis dahin hinterlegte Soll-Arbeitszeit-Fenster als einen Block je Tag übernommen. Es kappt weiter, ändert das Soll aber nicht. Im Dialog steht es als `Arbeitszeit-Fenster (Altbestand, nur Kappung)` mit `In Arbeitszeit-Blöcke umwandeln` (Zeiten vorbefüllt; Sie tragen die Pause ein und passen Zeiten außerhalb des 5-Minuten-Rasters an, z. B. 07:37 oder 23:59; nur bei aktiver Stundenzählung) und `Fenster entfernen` (ab dem Gültig-ab-Datum wird nicht mehr gekappt). Eine Änderung in den Modi Gleichmäßig oder Nach Tagen übernimmt ein Altfenster, solange Sie es nicht entfernen – für Altfenster gilt also nicht, dass der Moduswechsel die Blöcke beendet (siehe vorheriger Tipp). Bis Version 1.19.2 wurde außerdem ein Feiertag auf einem Werktag wie ein normaler Arbeitstag gekappt; solche Einträge bleiben, wie sie sind. Öffnen Sie einen im Admin-Dashboard oder Monatsjournal und speichern ihn unverändert, wird er mit der tatsächlich gestempelten Zeit neu berechnet.

> **Achtung:** **Arbeitsrecht und Mitbestimmung:** Ändert sich durch die Blöcke der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG). Die Lage der Arbeitszeit kann der Vertrag festlegen; sonst ändern Sie sie im Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und nur für die Zukunft. Vereinbarte Arbeitszeiten sind schriftlich nachzuweisen, eine Änderung spätestens am Tag des Wirksamwerdens (§§ 2, 3 NachwG). Mit Betriebsrat sind Lage, Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG) und die Kappung als technische Einrichtung (Nr. 6) mitbestimmungspflichtig; ohne Zustimmung des Betriebsrats ist die Maßnahme in der Regel unwirksam. PraxisZeit prüft das nicht und ersetzt keine Rechtsberatung – im Zweifel fragen Sie eine Fachanwältin oder einen Fachanwalt für Arbeitsrecht.

<a id="rueckwirkend-aendern"></a>
### Was passiert, wenn ich die Arbeitszeit rückwirkend ändere?

Liegt „Gültig ab“ in der Vergangenheit, rechnet PraxisZeit die erfassten Zeiteinträge an den geänderten Wochentagen neu – immer vom Stempel aus – und danach die gebuchten Abwesenheiten. Im Beispiel endet Sarahs Montagnachmittag rückwirkend um 15:30 statt 16:00.

![Kasten „Verkürzung“ bei einer rückwirkenden Arbeitszeit-Änderung: Wahl zwischen „Ab heute“ und „Rückwirkend mit Neuberechnung“, darunter Grund und Begründung](/help/img/pl-rueckwirkend.webp)

1. **Verkürzung:** Verliert ein Eintrag angerechnete Zeit, sinkt das Überstundenkonto im Wirkungsbereich oder sinkt die Gutschrift einer Abwesenheit an einem Tag mit Arbeit stärker als das Tagessoll, erscheint dieser Kasten mit den Gründen, z. B. „2 Einträge verlieren angerechnete Zeit (zusammen 0:30 h)“.
2. **Ab heute … wirksam** (Standard): Die Änderung gilt ab dem frühesten Tag, an dem nichts verloren geht – meist heute, morgen, wenn die Person heute schon gestempelt hat oder eingestempelt ist. Vergangene Einträge bleiben unverändert; ein Grund ist nicht nötig.
3. **Rückwirkend ab … mit Neuberechnung:** nur mit Grund, Begründung und Bestätigung.
4. **Grund:** „Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)“, „Mit der beschäftigten Person vereinbart“ oder „Sonstiges“.
5. **Begründung:** 10 bis 400 Zeichen. Danach bestätigen Sie den Haken zum gewählten Grund. Grund, Begründung und Notiz speichert PraxisZeit zusammen im Notizfeld der Änderung, höchstens 500 Zeichen; zu lang → „Notiz und Begründung zusammen höchstens 500 Zeichen.“, Speichern bleibt gesperrt – PraxisZeit kürzt nie.

<a id="auswirkung-pruefen"></a>
### Was zeigt mir die Auswirkung vor dem Speichern?

Ist „Gültig ab“ rückwirkend oder betrifft die Änderung schon Erfasstes, steht über `Speichern` ein Auswirkungs-Kasten. Er zeigt die gewählte Variante – hier die rückwirkende.

![Auswirkungs-Kasten einer rückwirkenden Änderung: Wirkungsbereich, Tagessoll vorher und nachher, zwei neu berechnete Einträge und die Tabelle für Soll, Überstunden und Urlaub](/help/img/pl-auswirkung.webp)

1. **Überschrift:** der Anlass und der Wirkungsbereich, z. B. „Rückwirkende Änderung: 14.10.2026 – …“. Darunter Puffer, geänderte Tage und das Tagessoll je Wochentag vorher → nachher.
2. **Zeiteinträge:** wie viele neu berechnet werden, je Monat mit der angerechneten Zeit vorher → nachher; übersprungene mit Grund. Danach die Zahl der Abwesenheiten, deren Stunden umgestellt werden. Offene Einträge vergangener Tage (vergessenes Ausstempeln) schließt PraxisZeit vorher automatisch und rechnet sie danach regulär neu; beim Überstundenkonto zählen sie in der Tabelle schon unter „bisher“.
3. **Tabelle** mit den Spalten bisher, neu und Δ: **Überstunden** und **Urlaub verbraucht** (bei geändertem Anspruch auch **Urlaubsanspruch**) mit allen drei Werten; für **Soll im Zeitraum** und **Angerechnet** steht nur die Differenz Δ.
4. `Einzelheiten` listet jeden Eintrag mit seinen Zeiten vorher → nachher.
5. Setzen Sie den Haken `Ich habe die Auswirkungen geprüft und möchte speichern` und klicken Sie auf `Speichern`. PraxisZeit meldet danach, wie viele Einträge neu berechnet wurden.

> **Achtung:** **Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit.** Eine rückwirkende Arbeitszeit-Änderung berichtigt nur eine falsch hinterlegte Arbeitszeit. Bei „Sonstiges“ warnt der Dialog zusätzlich: Eine einseitige rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO); geleistete Arbeit bleibt zu vergüten.

> **Gut zu wissen:** **Auch eine Erhöhung kann eine Verkürzung sein:** Steigt das Soll rückwirkend (längere Blöcke, mehr Wochenstunden), sinkt das Überstundenkonto – dann gelten dieselben Regeln. Reicht die Änderung in ein abgeschlossenes Jahr, weist der Dialog darauf hin. Führen Sie danach den Jahresabschluss für **jedes** genannte Jahr erneut aus, vom frühesten an. **Achtung:** Ein erneuter Jahresabschluss überschreibt die Überträge **aller** Mitarbeitenden für das Folgejahr – auch von Hand korrigierte Werte in der **Vorjahresübernahme**; tragen Sie solche Korrekturen danach erneut ein.

> **Gut zu wissen:** **Änderung löschen:** Das Papierkorb-Symbol steht nur an der jüngsten Zeile des Verlaufs. Das Löschen rechnet Einträge und Abwesenheiten zurück; verkürzt es, setzt PraxisZeit standardmäßig ab dem frühesten Tag ohne Verlust auf den vorherigen Stand zurück (`Zurücksetzen`) – meist heute, morgen, wenn die Person heute schon gestempelt hat oder eingestempelt ist, bei Minijob-Einstellungen der 1. des Folgemonats; rückwirkend nur mit Grund. Eine Änderung, die erst nach heute beginnt, verkürzt beim Löschen nichts; dort genügt „Löschen“. Hat sich der Verlauf seit dem Öffnen geändert – etwa weil in einem zweiten Fenster eine weitere Änderung dazwischen angelegt wurde –, lehnt PraxisZeit die Rücksetzung ab, statt den Vertrag dieser Änderung zu überschreiben: „Der vorherige Stand hat sich inzwischen geändert – bitte die Vorschau neu laden.“ Der Bereich lädt die Auswirkung dann neu.

> **Gut zu wissen:** **Wer davon erfährt:** Die Person sieht nach jeder Arbeitszeit-Änderung 30 Tage lang den Kasten „Hinweis zu Ihrer Arbeitszeit“ auf ihrem Dashboard – bei einer rückwirkenden Verkürzung mit dem Grundtyp, nie mit Ihrer Begründung. Das Änderungsprotokoll hält jede Neuberechnung fest: je Änderung und je Löschung eine Sammelzeile mit Wirkungsdatum, Zahl der neu berechneten Einträge, Puffer und Grund (auch ohne betroffene Einträge). Den Grund trägt sie als Kürzel „\[Erfassungsfehler korrigiert\]“, „\[Einvernehmlich vereinbart\]“ bzw. „\[Sonstiges\]“ vor Ihrer Begründung. Sind Abwesenheiten betroffen, kommen eine Sammelzeile „Stundenänderung“ ohne Datum und je nachgezogener Abwesenheit eine Zeile „Stundenänderung“ mit altem und neuem Stundenwert hinzu (z. B. „Krank 8,0 h“ → „Krank 4,0 h“).

<a id="nicht-angerechnet-anerkennen"></a>
### Wie rechne ich Zeit außerhalb der Blöcke doch an?

Nicht angerechnete Zeit steht als Zusatzzeile unter der Uhrzeit – im Monatsjournal (Buch-Symbol in der Benutzerliste) und in der Detailansicht des Admin-Dashboards.

![Zeile im Monatsjournal von Sarah Klein: gestempelt 08:00–16:00, angerechnet 5:30 h, 2:30 h zwischen den Blöcken nicht angerechnet, darunter der Knopf „Anerkennen“](/help/img/pl-anerkennen.webp)

1. Die Zusatzzeile nennt Stempel, angerechnete Zeit und den nicht angerechneten Teil, z. B. „gestempelt 08:00–16:00 · angerechnet 5:30 h · 2:30 h zwischen den Blöcken nicht angerechnet“.
2. Wurde in dieser Zeit tatsächlich gearbeitet, klicken Sie auf `Anerkennen` und bestätigen. Dann wird die gesamte gestempelte Zeit angerechnet – dauerhaft, auch bei späteren Neuberechnungen. Der Vorgang wird protokolliert.

> **Achtung:** **Anerkennen lässt sich nicht zurücknehmen.** Wurde nur ein Teil der Zeit gearbeitet, teilen oder korrigieren Sie den Eintrag besser. Ein offener Eintrag lässt sich erst nach dem Ausstempeln anerkennen, ein automatisch geschlossener erst, wenn das tatsächliche Ende eingetragen ist. Nichtanrechnung ersetzt keine Vergütungsentscheidung: angeordnete, gebilligte oder geduldete Arbeit ist zu vergüten.

> **Gut zu wissen:** **Automatisch geschlossene Einträge:** Das automatisch gesetzte 23:59 ist kein Stempel. Beim Bearbeiten zeigt das Formular das angerechnete Ende (z. B. 18:15); speichern Sie es unverändert, etwa nur mit ergänzter Pause, bleibt die Kennzeichnung „automatisch geschlossen“. Erst das tatsächliche Ende (Mitarbeitende per Änderungsantrag) hebt sie auf. Auch ein tatsächliches Ende um **23:59**, z. B. nach einem Notdienst, lässt sich eintragen: Es gilt dann als echter Stempel, wird wie jedes Ende gegen die Blöcke gekappt und nach dem Anerkennen bis 23:59 angerechnet. **Ausnahmen:** Hat das automatische Schließen nichts gekappt (Person ohne Arbeitszeit-Blöcke, Wochenende oder Feiertag, ohne Stundenzählung), steht als Ende schon 23:59; ein erneut gespeichertes 23:59 lässt sich dann nicht vom automatischen Wert unterscheiden, und die Kennzeichnung bleibt. An einem Werktag ohne Block (bei Personen mit Blöcken) zählt der automatisch geschlossene Eintrag 0 h. Ebenso bleibt die Kennzeichnung, wenn das eingetragene Ende genau dem angerechneten Ende entspricht (z. B. 18:15) – auch wenn die Person tatsächlich um diese Zeit aufgehört hat.

> **Gut zu wissen:** **Anerkannte Einträge sind für Mitarbeitende gesperrt:** Mitarbeitende können einen solchen Eintrag weder selbst ändern noch löschen – dafür brauchen sie einen Änderungs- oder Löschantrag. Eine Abwesenheit über einem anerkannten Eintrag lehnt PraxisZeit ab und nennt den Tag: „Am 05.10.2026 gibt es einen anerkannten Zeiteintrag – bitte an die Verwaltung wenden.“ Die Abwesenheit für diesen Tag tragen dann Sie ein; die übrigen Tage können die Mitarbeitenden getrennt buchen.

<a id="antraege-genehmigen"></a>
## Anträge genehmigen: Urlaub und Korrektur

*Urlaubsanträge landen unter **Anträge**, Korrekturen an Zeiteinträgen unter **Änderungsanträge**. Eine rote Zahl in der Navigation zeigt, was offen ist.*

<a id="urlaubsantrag-genehmigen"></a>
### Wie genehmige ich einen Urlaubsantrag?

Klicken Sie in der Navigation auf `Anträge`. Die Seite heißt „Abwesenheitsanträge“.

![Seite „Abwesenheitsanträge“: Schalter für die Genehmigungspflicht und der offene Urlaubsantrag von Thomas Bauer über 5 Arbeitstage](/help/img/pl-urlaubsantraege.webp)

1. **Abwesenheitsanträge genehmigungspflichtig:** Ist der Schalter an, landen Urlaubsanträge hier als „Offen“. Aus, buchen die Mitarbeitenden direkt. Krankmeldungen brauchen nie eine Freigabe.
2. Mit `Offen`, `Genehmigt`, `Abgelehnt` und `Alle` filtern Sie die Anträge.
3. **Arbeitstage** auf der Karte: was der Antrag nach der Genehmigung tatsächlich kostet – nur Tage, an denen die Person laut ihrem Arbeitsplan arbeitet; Wochenenden, Feiertage und freie Sondertage zählen nicht, ein halber Tag 0,5.
4. `Genehmigen` trägt die Abwesenheiten für diese Arbeitstage ein und zieht sie vom Urlaubskonto ab.
5. `Bearbeiten` ändert den Zeitraum vor der Entscheidung, z. B. wenn er über den letzten Arbeitstag hinausgeht.
6. `Ablehnen` öffnet ein Feld für den Ablehnungsgrund (optional); bestätigen Sie mit `Ablehnen`. Die Person sieht den Grund unter „Meine Anträge“.

> **Achtung:** **Vorhandene Zeiteinträge** an den genehmigten Tagen werden durch die Abwesenheit ersetzt (im Änderungsprotokoll dokumentiert). Zeigt die Karte **0** Arbeitstage, lehnt PraxisZeit die Genehmigung ab – lehnen Sie den Antrag dann ab oder passen Sie ihn an.

<a id="urlaub-stornieren-admin"></a>
### Wie nehme ich einen genehmigten Urlaub zurück?

Das geht, solange der Urlaub noch nicht begonnen hat.

1. Wählen Sie auf der Seite „Abwesenheitsanträge“ den Filter `Genehmigt`.
2. Klicken Sie am Antrag auf `Urlaub stornieren` und bestätigen Sie mit `Stornieren`.
3. Die zugehörigen Abwesenheitstage werden gelöscht; der Antrag steht danach als „Zurückgezogen“ da.

<a id="korrekturantrag-pruefen"></a>
### Wie prüfe ich einen Korrekturantrag?

Klicken Sie in der Navigation auf `Änderungsanträge`. Mitarbeitende beantragen hier Änderungen, Löschungen und Nachträge für vergangene Tage.

![Offener Änderungsantrag: aktuell 09:15–17:30, gewünscht 08:00–16:45, darunter die Begründung und die Knöpfe Genehmigen und Ablehnen](/help/img/pl-korrekturantrag.webp)

1. Mit `Offen`, `Genehmigt`, `Abgelehnt` und `Alle` filtern Sie; die Auswahl darunter zeigt nur eine Person.
2. **Aktuell:** der Eintrag, wie er heute gespeichert ist.
3. **Gewünscht:** die beantragten Werte.
4. Lesen Sie die **Begründung** – sie ist Pflicht.
5. `Genehmigen` übernimmt die Werte in den Zeiteintrag. `Ablehnen` fragt nach einem optionalen Ablehnungsgrund.

> **Gut zu wissen:** Die Genehmigung prüft dieselben Regeln wie ein direkter Eintrag: Arbeitszeit-Blöcke, Pausen nach § 4 ArbZG und den Beschäftigungszeitraum. Liegt der Tag eines neuen Eintrags – oder das neue Datum eines verschobenen – vor dem ersten oder nach dem inzwischen eingetragenen letzten Arbeitstag, lehnt PraxisZeit die Genehmigung ab – lehnen Sie den Antrag dann ab. Ein Abwesenheits-Antrag für einen vergangenen Tag ersetzt bei Genehmigung die Zeiteinträge dieses Tages.

<a id="anrechnung-beantragt"></a>
### Eine Person beantragt die Anrechnung – was tue ich?

Hat eine Person an einem Eintrag mit nicht angerechneter Zeit `Anrechnung beantragen` gewählt, trägt ihr Antrag ein eigenes Kennzeichen. Vorbelegt sind die gestempelten Zeiten.

![Antrag „Anrechnung beantragt“ von Sarah Klein: 2:30 h Lücke nicht angerechnet, gestempelt 08:00–16:00, Knöpfe „Genehmigen und anerkennen“ und „Ohne Anerkennen genehmigen“](/help/img/pl-anrechnung-beantragt.webp)

1. **Anrechnung beantragt:** das Kennzeichen des Antrags.
2. Unter **Aktuell** stehen die nicht angerechnete Lücke und die Stempel des Eintrags. Weichen die beantragten Zeiten von den Stempeln ab, steht das rot unter **Gewünscht**.
3. `Genehmigen und anerkennen` übernimmt den Antrag und rechnet die Zeiten ungekappt an – dauerhaft, wie `Anerkennen`.
4. `Ohne Anerkennen genehmigen` übernimmt nur die Zeiten; die Zeit vor, nach oder zwischen den Blöcken bleibt nicht angerechnet.

> **Gut zu wissen:** Auch bei einem gewöhnlichen Änderungsantrag zu einem Eintrag mit nicht angerechneter Zeit bietet die Prüfung neben `Genehmigen` zusätzlich `Genehmigen und anerkennen` an. Ihren eigenen Antrag genehmigt eine weitere Admin, sofern es eine gibt.

<a id="sammel-genehmigung"></a>
### Kann ich mehrere Anträge auf einmal genehmigen?

Ja – auf der Seite „Änderungsanträge“ im Filter `Offen`.

![Zwei offene Änderungsanträge ausgewählt („2 ausgewählt“); oben der Knopf „2 genehmigen, davon 1 mit Anerkennen“](/help/img/pl-sammel-genehmigung.webp)

1. Das Kästchen oben wählt alle offenen Anträge aus.
2. Einzelne Anträge markieren oder abwählen Sie über das Kästchen an der Karte.
3. Klicken Sie auf **… genehmigen** bzw. **… ablehnen**. Sind Anrechnungsanträge dabei, nennt der Knopf ihre Zahl („2 genehmigen, davon 1 mit Anerkennen“) und fragt vor dem Absenden nach; diese werden dann anerkannt.

> **Gut zu wissen:** Einen Anrechnungsantrag ohne Anerkennen zu genehmigen geht nur einzeln. Hinweise wie bei der Einzel-Genehmigung (Kappung, Wochen- oder Nachtarbeitszeit) erscheinen auch hier, jeweils mit dem Namen der Person. Prüfen Sie Anträge zeitnah, damit die Salden aktuell bleiben.

<a id="abwesenheiten-betriebsferien"></a>
## Abwesenheiten & Betriebsferien

*Unter **Abwesenheiten** im Bereich Administration tragen Sie Urlaub, Krankheit oder Fortbildung für eine Person ein. **Betriebsferien** schließen die ganze Praxis – PraxisZeit bucht die Tage für alle Teilnehmenden auf einmal.*

<a id="abwesenheit-fuer-person"></a>
### Wie trage ich eine Abwesenheit für eine Person ein?

Klicken Sie in der Navigation unter Administration auf `Abwesenheiten`. Die Seite heißt „Abwesenheiten verwalten“; der Tab `Mitarbeiter-Abwesenheiten` listet alle Personen mit ihren Abwesenheiten im gewählten Monat.

![Seite „Abwesenheiten verwalten“: Mitarbeiterin Sarah Klein gewählt, darunter das Formular „Abwesenheit eintragen“ mit Datum, Typ Urlaub, ausgegrautem Stundenfeld mit Hinweis zum Tagessoll und Speichern](/help/img/pl-abwesenheit-eintragen.webp)

1. Wählen Sie unter **Mitarbeiter** die Person – oder klicken Sie in der Liste bei ihr auf `+ Eintragen`. Oben rechts steht dann `Abwesenheit eintragen`.
2. Mehrere Tage? Setzen Sie den Haken bei `Zeitraum (mehrere Tage)`. Für einen einzelnen Tag gibt es `Halber Tag (zählt als 0,5 Tag)` – nicht bei Krank und Überstundenausgleich.
3. Wählen Sie das **Datum** – beim Zeitraum **Von** und **Bis**. Anders als die Mitarbeitenden tragen Sie auch vergangene Tage direkt ein.
4. **Typ:** Urlaub, Krank, Fortbildung (außer Haus), Überstundenausgleich, Bezahlte Freistellung (kein Urlaubsabzug), Sonstiges – oder unter „Eigene Gründe“ ein Grund Ihrer Praxis.
5. **Stunden:** Das Feld bleibt ausgegraut, solange es nichts einzutragen gibt – gebucht wird immer das Tagessoll des Tages laut Vertrag („Es wird das Tagessoll laut Vertrag gebucht“). Nur beim Überstundenausgleich (auch als eigener Grund „Überstundenabbau“) ist das Feld frei: Der eingetragene Wert geht vom Überstundenkonto ab – bei Personen mit Tagesplan bucht das System stattdessen das Tagessoll des Tages.
6. Klicken Sie auf `Speichern`.

> **Achtung:** **Nur an Arbeitstagen:** Wochenenden, Feiertage, als „frei“ eingestellte Sondertage und Tage ohne geplante Arbeitszeit (freie Wochentage, 0 Wochenstunden etwa in der Elternzeit) bleiben ausgenommen; bei Mitarbeitenden ohne Stundenzählung zählt jeder Werktag. Zeiteinträge der eingetragenen Tage werden ersetzt, Einträge an ausgenommenen Tagen bleiben stehen. Liegt im Zeitraum kein einziger Tag mit geplanter Arbeitszeit, lehnt PraxisZeit die Buchung ab. **Halbtage:** Auch ohne Stundenzählung zählt ein halber freier Tag (Option „Halber Tag“) **0,5 Urlaubstage**.

> **Gut zu wissen:** **Löschen:** Ohne gewählte Person klappt ein Klick auf den Namen die Abwesenheiten auf; der Papierkorb (`Löschen`) löscht eine Abwesenheit. Mitarbeitende beantragen die Löschung einer vergangenen Abwesenheit mit `Löschung beantragen` – der Antrag kommt als **Löschung** unter `Änderungsanträge` zu Ihnen. Betriebsferien-Tage ändert nur die Verwaltung.

<a id="betriebsferien-anlegen"></a>
### Wie lege ich Betriebsferien an?

Wechseln Sie auf derselben Seite zum Tab `Betriebsferien` und klicken Sie oben rechts auf `Betriebsferien erstellen`.

![Formular „Betriebsferien erstellen“ mit Bezeichnung „Umbau Empfang“, Von und Bis, der Verrechnung „Als Urlaub werten“ oder „Bezahlte Freistellung“ und dem Knopf zum Erstellen](/help/img/pl-betriebsferien.webp)

1. **Bezeichnung**, z. B. „Weihnachtsschließzeit 2026“.
2. **Von** und **Bis**: der Zeitraum der Schließung.
3. **Verrechnung:** `Als Urlaub werten` (Standard) zieht jeden gebuchten Schließtag vom Urlaubskonto ab – 1 Tag je Arbeitstag. `Bezahlte Freistellung` wirkt wie ein Feiertag: kein Urlaubsabzug, das Überstundenkonto bleibt unberührt.
4. Klicken Sie auf `Betriebsferien erstellen & Urlaub eintragen`. Jede teilnehmende Person bekommt für jeden ihrer Arbeitstage im Zeitraum eine Abwesenheit; vorhandene Zeiteinträge dieser Tage werden ersetzt (im Änderungsprotokoll dokumentiert).

> **Gut zu wissen:** **Wer bekommt die Tage?** Alle aktiven Mitarbeitenden mit dem Haken **Nimmt an Betriebsferien teil** (Standard) – unabhängig von der Rolle. Kein Eintrag entsteht an Wochenenden, Feiertagen, „frei“ eingestellten Sondertagen, Tagen ohne geplante Arbeitszeit, außerhalb des Beschäftigungszeitraums und an Tagen mit einer anderen Abwesenheit. Fällt diese später weg, bucht PraxisZeit den Schließtag nach – außer es steht inzwischen ein Zeiteintrag am Tag. Setzen Sie den Haken nachträglich, trägt PraxisZeit die laufenden und künftigen Betriebsferien automatisch nach.

<a id="betriebsferien-aendern"></a>
### Wie ändere oder lösche ich Betriebsferien?

Unter dem Tab `Betriebsferien` stehen alle Schließungen als Tabelle.

![Tabelle der Betriebsferien: „Teamklausur“ mit Zeitraum, Verrechnung Urlaub, Zahl der betroffenen Mitarbeitenden und in der Spalte Aktion den Symbolen Bearbeiten und Löschen](/help/img/pl-betriebsferien-liste.webp)

1. Je Schließung: Bezeichnung, Zeitraum, Verrechnung und unter **Betroffene MA**, für wie viele Personen Tage gebucht sind.
2. In der Spalte **Aktion**: **Bearbeiten** (Stift) – Ändern Sie den Zeitraum, bekommen neu hinzukommende Arbeitstage einen Eintrag und entfallene werden entfernt; eine umgestellte Verrechnung ändert den Typ der Einträge. Abweichende Einträge einzelner Personen bleiben unberührt. Speichern mit `Änderungen speichern`. Das erneute Speichern entfernt auch alte 0-Stunden-Einträge (Betriebsferien von vor 1.20.0) an Tagen ohne Soll; liegen sie in einem abgeschlossenen Jahr, prüfen Sie danach den Übertrag. **Löschen** (Papierkorb) – Die Abwesenheiten werden bei allen Personen entfernt.

> **Achtung:** **Abgeschlossenes Jahr:** Ändert das Anlegen, Speichern oder Löschen Buchungen in einem Jahr mit Jahresabschluss, meldet PraxisZeit z. B. „Jahresabschluss 2026 bereits erfolgt — Carryover 2027 ist nun veraltet, bitte Jahresabschluss erneut ausführen.“ Der Übertrag ändert sich nicht von selbst: Prüfen und korrigieren Sie ihn oder führen Sie den Jahresabschluss erneut aus (dabei werden von Hand korrigierte Überträge überschrieben). Reines Umbenennen löst den Hinweis nicht aus.

<a id="betriebsferien-ueberstundenabbau"></a>
### Die Betriebsferien sind länger als der Resturlaub – was passiert?

Das steuert ein Schalter unter `Einstellungen` → **Betriebsferien \& Urlaub**. Er gilt nur für Betriebsferien, die als Urlaub zählen.

![Einstellungen, Abschnitt „Betriebsferien & Urlaub“: Erklärtext, Hinweis zum erneuten Speichern und der Schalter „Überzählige Betriebsferien als Überstundenabbau“](/help/img/pl-betriebsferien-urlaub.webp)

1. **Überzählige Betriebsferien als Überstundenabbau** – aus (Standard): Alle Schließtage zählen als Urlaub, reicht der Resturlaub nicht, entstehen Minus-Urlaubstage. An: Erst wird der Urlaub aufgezehrt, die übrigen Tage bucht PraxisZeit als Überstundenausgleich – das Überstundenkonto darf dabei ins Minus gehen.
2. Klicken Sie auf `Speichern`.
3. Der Schalter wirkt beim Anlegen und erneuten Speichern. Bereits eingetragene Betriebsferien öffnen Sie einmal und speichern sie erneut – dann rechnet PraxisZeit sie nach derselben Regel neu.

> **Gut zu wissen:** **Pflichturlaub darf ins Minus:** Betriebsferien werden zwingend gebucht, auch über das Urlaubsbudget hinaus – anders als ein Urlaubsantrag oder eine direkte Buchung, die PraxisZeit bei fehlendem Resturlaub ablehnt. Mit eingeschaltetem Schalter verteilt PraxisZeit den Urlaub nach Datum (frühere Schließung zuerst); privater Urlaub im selben Jahr geht immer vor. Mehr dazu: [So rechnet PraxisZeit: Betriebsferien](SO-RECHNET-PRAXISZEIT.md#betriebsferien).

<a id="sondertage-verkuerzte-tage"></a>
## Sondertage & verkürzte Tage

*Heiligabend und Silvester sind keine gesetzlichen Feiertage. Ob dort voll, halb oder gar nicht gearbeitet wird, legen Sie selbst fest – ebenso einzelne **verkürzte Tage** wie Rosenmontag oder einen Betriebsausflug.*

<a id="sondertage-einstellen"></a>
### Wie stelle ich den 24. und 31.12. ein?

Klicken Sie auf `Einstellungen` und scrollen Sie zum Abschnitt **Sondertage (24./31.12.)**. Beide Tage stellen Sie getrennt ein.

![Einstellungen, Abschnitt „Sondertage (24./31.12.)“: 24.12. im Modus Halbtag, 31.12. im Modus Frei mit der Anrechnung Urlaub, darunter Speichern](/help/img/pl-sondertage.webp)

1. **Modus** je Tag: `Arbeitstag` (Standard), `Halbtag`, `Frei` oder `Verkürzt auf X Stunden`. Bei „Verkürzt“ erscheint daneben **Höchstens (Stunden)**: 0,25 bis 12 Stunden in Schritten von 0,25.
2. **Anrechnung** (nur bei „Frei“): `Urlaub` zieht den freien Tag vom Urlaubskonto ab, `Bezahlte Freistellung` nicht – wie ein Feiertag.
3. Klicken Sie auf `Speichern`. Der Knopf wird erst aktiv, wenn Sie etwas geändert haben.

| Modus | Tagessoll | Ein Urlaubstag an diesem Tag kostet |
| --- | --- | --- |
| Arbeitstag | volles Tagessoll | 1 Tag |
| Halbtag | halbes Tagessoll | 0,5 Tage |
| Frei | 0, wie ein Feiertag | mit Anrechnung „Urlaub“ zieht der Tag selbst 1 Urlaubstag ab; mit „Bezahlte Freistellung“ nichts |
| Verkürzt auf X Stunden | die kleinere Zahl aus Tagessoll und X | 0,5 Tage |

> **Gut zu wissen:** Die Einstellung gilt für **alle Jahre**, auch zurückliegende. Betroffene Betriebsferien bucht PraxisZeit beim Speichern selbst neu; ändert sich ein Jahr mit Jahresabschluss, erscheint dort nur der Hinweis auf den veralteten Übertrag. Wechselt ein Tag zwischen „Frei“ und Arbeitstag bzw. Halbtag, nennt PraxisZeit bestehende Zeiteinträge dieses Tages, deren Anrechnung sich ändern müsste – unverändert neu speichern berechnet sie neu. Mehr dazu: [So rechnet PraxisZeit: Sondertage und verkürzte Tage](SO-RECHNET-PRAXISZEIT.md#sondertage).

<a id="verkuerzte-tage"></a>
### Wie verkürze ich einen einzelnen Tag, z. B. Rosenmontag?

Unter `Einstellungen` → **Verkürzte Tage**, direkt unter den Sondertagen.

![Einstellungen, Abschnitt „Verkürzte Tage“: Eingabe Datum, Bezeichnung „Betriebsausflug“ und Höchstens 5 Stunden, darunter der eingetragene Brückentag mit höchstens 4 Stunden](/help/img/pl-verkuerzte-tage.webp)

1. Wählen Sie oben rechts das **Jahr**.
2. Tragen Sie in der Eingabezeile das **Datum** des Tages ein (für den 24. und 31.12. nimmt PraxisZeit keinen Eintrag an – dafür gibt es die Sondertage), eine **Bezeichnung** wie „Rosenmontag“ oder „Betriebsausflug“ und **Höchstens (Stunden)**: 0,25 bis 12, in Schritten von 0,25. Klicken Sie auf `Hinzufügen`. Je Datum gibt es genau einen Eintrag.
3. Eingetragene Tage stehen darunter. Ein Klick auf die Bezeichnung macht sie änderbar, ebenso die Stunden; danach erscheint `Speichern`. `Löschen` entfernt den Tag.

> **Gut zu wissen:** **So wirkt ein verkürzter Tag:** Das Soll ist die kleinere Zahl aus Tagessoll und Höchstwert – wer ohnehin weniger Soll hat, behält es. Ein Feiertag geht vor, am Wochenende wirkt der Tag nicht. Urlaub kostet 0,5 Tage; Krank und Fortbildung zählen anteilig (8 h Soll, höchstens 4 h → 4 h Soll und 4 h Gutschrift, Saldo 0). Angerechnet wird weiter die gestempelte Zeit, sie wird nicht auf den Höchstwert gekappt; die Arbeitszeit-Blöcke bleiben unverändert.

> **Gut zu wissen:** Mitarbeitende sehen den Tag im Kalender als „Brückentag: verkürzter Tag (max. 4 h)“ und auf der Stempelkarte als „verkürzter Tag (max. 4 h)“. Auch jede Änderung hier bucht betroffene Betriebsferien neu; in abgeschlossenen Jahren erscheint nur der Hinweis.

<a id="berichte-exporte"></a>
## Berichte & Exporte

*Für Lohnbuchhaltung, Steuerberatung und Betriebsprüfung exportieren Sie Monats- und Jahresberichte als Excel, ODS oder PDF. Die Dateien sind Ihr Nachweis nach § 16 ArbZG.*

<a id="monatsreport-exportieren"></a>
### Wie exportiere ich den Monatsreport?

Klicken Sie in der Navigation auf `Berichte`. Die Seite heißt „Berichte \& Export“; oben steht **Monatsreport exportieren**.

![Berichte & Export, Monatsreport: Monat auswählen, Knöpfe Excel, ODS und PDF, darunter „Krankheitsdaten einschließen“ und „Ausgeblendete Mitarbeitende einbeziehen“](/help/img/pl-monatsreport.webp)

1. Wählen Sie unter **Monat auswählen** den Monat.
2. Optional: `Krankheitsdaten einschließen (Art. 9 DSGVO)`. Ohne den Haken steht im Export „Abwesenheit“ statt „Krank“.
3. Optional: `Ausgeblendete Mitarbeitende einbeziehen` – etwa die Praxisinhaberin, wenn sie stempelt. Ausgeschiedene sind immer enthalten, wenn sie im Zeitraum Einträge oder Abwesenheiten haben.
4. Klicken Sie auf das Format – die Markierung sitzt am Knopf `PDF (.pdf)`, daneben stehen `Excel (.xlsx)` und `ODS (.ods)`. Die Datei wird heruntergeladen – je Person ein Blatt mit allen Tagen und einer Zusammenfassung.

> **Achtung:** **Krankheitsdaten (Art. 9 DSGVO)** sind besondere Kategorien personenbezogener Daten; jeder Export mit dem Haken wird im Änderungsprotokoll vermerkt. Ohne den Haken steht auch bei eigenen Abwesenheitsgründen „Abwesenheit“ (die Notiz entfällt), und das Kennzeichen „Nachtarbeitnehmer“ im Kopf jedes Blatts zeigt „–“. „Sonstiges“/„unbezahlt frei“ und „Bez. Freistellung“ stehen immer im Klartext.

| Spalte (Tageszeile) | Bedeutung |
| --- | --- |
| Von / Bis | Rahmen des Tages: erster Beginn, letztes Ende – bei Arbeitszeit-Blöcken die gekappten Zeiten |
| Pause (Min) | die erfasste Pause |
| Netto (Std) | die angerechnete Arbeitszeit der Zeiteinträge |
| Soll (Std) | das Tagessoll |
| Differenz | Netto plus Gutschrift für Krankheit und Fortbildung minus Soll – ein Krank- oder Fortbildungstag ist ±0; die Summe ist der „Saldo Monat“ |
| Abwesenheit, Bemerkung | Art der Abwesenheit und Notizen |
| Unterbrechung (Min), Zeiteinträge | nur Excel und ODS: Zeit zwischen den Einträgen eines Tages und die Einträge einzeln, z. B. „07:45–12:00, 14:15–17:00“ |
| Nicht angerechnet (Min) | gestempelte, aber nicht angerechnete Zeit vor, nach und zwischen den Arbeitszeit-Blöcken |
| Gestempelt (Von–Bis), Anwesenheit laut Stempel (Std), Pausenausnahme (§4 ArbZG) | die tatsächlichen Stempel, die Anwesenheit abzüglich Pausen (über 10 h hervorgehoben) und die Begründung einer Pausenausnahme; im PDF als Spalte „Gestempelt (Anwesenheit)“ und in der Bemerkung |

> **Gut zu wissen:** Neue Spalten hängt PraxisZeit immer hinten an – bestehende Auswertungen funktionieren weiter. Die **Zusammenfassung** je Person nennt Soll- und Ist-Stunden, Saldo Monat, Überstunden kumuliert, Urlaub und Nachtarbeitstage. Bei fester Monatsarbeitszeit (Minijob-Modus) ist nur die Zusammenfassung verbindlich, denn das Monats-Soll ist dort nicht die Summe der Tage.

<a id="jahresreport-exportieren"></a>
### Wie exportiere ich einen Jahresbericht?

Weiter unten auf derselben Seite: **Jahresreport exportieren**. Krankheitsdaten und ausgeblendete Mitarbeitende wählen Sie dort genauso.

![Berichte & Export, Jahresreport: Jahr auswählen und die beiden Formate „Classic“ und „Detailliert“ mit je einem Knopf für Excel und ODS](/help/img/pl-jahresreport.webp)

1. Tragen Sie unter **Jahr auswählen** das Jahr ein.
2. **Classic Format** (`Excel` oder `ODS`): je Person ein Blatt mit den 12 Monatswerten – Soll, Ist, Saldo, Urlaub und Krankheit in Stunden, Überstunden kumuliert und Resturlaub.
3. **Detailliertes Format** (`Excel` oder `ODS`): jeder Tag des Jahres je Person, mit denselben Tagesspalten wie der Monatsreport. Die Erstellung dauert einige Sekunden.

> **Achtung:** **Aufbewahrung (§ 16 ArbZG):** Exportieren Sie regelmäßig, mindestens jährlich, und bewahren Sie die Dateien **2 Jahre** sicher auf. Das PDF-Format gibt es nur für den Monatsreport.

<a id="arbzg-pruefung"></a>
## ArbZG-Prüfung & §4-Ausnahme

*PraxisZeit prüft beim Erfassen das Arbeitszeitgesetz und warnt oder sperrt. Unter **Berichte** werten Sie nachträglich aus – und unter **Einstellungen** legen Sie fest, ob es die Ausnahme „Pflicht-Pause war nicht möglich“ gibt.*

| Auswertung unter Berichte | Prüft |
| --- | --- |
| Ruhezeitprüfung | § 5: mindestens 11 Stunden Ruhezeit zwischen zwei Arbeitstagen (Mindestruhezeit einstellbar) |
| Sonntagsarbeit §11 ArbZG | gearbeitete und freie Sonntage – mindestens 15 Sonntage im Jahr müssen frei sein; bei Eintritt oder Austritt im Jahr zählen nur die Sonntage im Beschäftigungszeitraum, und die Mindestzahl gilt anteilig (aufgerundet, Hinweis „Teiljahr“) |
| Nachtarbeit §6 ArbZG | Nachtarbeitstage und Nachtarbeitnehmer, mit Monatsdurchschnitt je Werktag |
| Ersatzruhetage §11 ArbZG | Ersatzruhetag innerhalb von 2 Wochen nach Sonntags- und 8 Wochen nach Feiertagsarbeit |
| 24-Wochen-Durchschnitt §3 ArbZG | höchstens 8 Stunden je Werktag im Schnitt über 24 Wochen |
| Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG | Tage über 10 Stunden, Wochen über 48 Stunden, Pausenausnahmen und zu kurze Pausen |

> **Gut zu wissen:** **Wer erscheint?** Alle aktiven Mitarbeitenden und ausgeschiedene, die im Zeitraum Einträge oder Abwesenheiten haben. Ausgeblendete nur mit `Ausgeblendete Mitarbeitende einbeziehen` über den Auswertungen; § 18-befreite Mitarbeitende erscheinen nie.

> **Achtung:** **Jugendliche:** Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG: 30 Min Pause bei mehr als 4,5 h, 60 Min bei mehr als 6 h, höchstens 4,5 h ohne Pause, Schichtzeit inklusive Lücke höchstens 10 h; weitere Grenzen wie §§ 8, 15 JArbSchG kommen hinzu). PraxisZeit prüft nur die Grenzen für Erwachsene, nicht diese.

> **Gut zu wissen:** **Lücke zwischen Blöcken und Pause:** Bleiben von der Lücke nach Abzug des Puffers an beiden Rändern mindestens 15 Minuten, zählt sie für die Pausenpflicht (§ 4 ArbZG) als Pause – aber nur, wenn sie tatsächlich frei war. Wer ohne Pause durchstempelt, bekommt den Hinweis „Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst“. Wird zusätzlich eine Pause eingetragen, zieht PraxisZeit beides ab und meldet „Pause in der Lücke wird zusätzlich abgezogen: …“; lag die Pause in der Lücke, setzen Sie die Pause auf 0. Beide Hinweise blockieren nie.

<a id="arbzg-24-wochen"></a>
### Hält mein Team den 8-Stunden-Durchschnitt ein?

Auf der Seite „Berichte \& Export“ im Abschnitt **24-Wochen-Durchschnitt §3 ArbZG**.

![Auswertung „24-Wochen-Durchschnitt §3 ArbZG“ zum Stichtag: je Person Durchschnitt angerechnet und laut Stempel je Werktag, Summen, Wochen über 48 Stunden, Tage über 8 Stunden und Status](/help/img/pl-arbzg-24wochen.webp)

1. **Stichtag** (Standard heute): ausgewertet werden die 24 Wochen bis zu diesem Tag.
2. Klicken Sie auf `Prüfen`. Über der Tabelle stehen der Zeitraum und, falls jemand die Grenze überschreitet, die Zahl der nicht konformen Mitarbeitenden.
3. **Ø angerechnet / Werktag** und **Status** rechnen mit der angerechneten Zeit, geteilt durch die Werktage – Montag bis Samstag ohne Feiertage und ohne Tage mit Urlaub, Krankheit, Fortbildung, Sonstiges oder Freistellung. **Anwesenheit laut Stempel** ist die gestempelte Zeit abzüglich Pausen; liegt ihr Schnitt über 8 Stunden, ist sie rot hervorgehoben.

<a id="arbzg-hoechstarbeitszeit"></a>
### Wo sehe ich lange Tage und dokumentierte Pausenausnahmen?

Im Abschnitt **Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG**.

![Auswertung „Höchstarbeitszeit und Pausenausnahmen §3/§4 ArbZG“: Zähler je Befund und aufgeklappt eine dokumentierte Pausenausnahme von Thomas Bauer mit Zeit, Pause und Begründung](/help/img/pl-arbzg-hoechstarbeitszeit.webp)

1. Wählen Sie das **Jahr**, optional einen **Monat**, und klicken Sie auf `Prüfen`.
2. Die Zähler: Tage \> 10 h, Wochen \> 48 h, Pausenausnahmen und Pause zu kurz. Es erscheinen nur Personen mit mindestens einem Befund.
3. Ein Klick auf die Person klappt die Einzelheiten auf.
4. **Pausenausnahmen:** jeder Eintrag mit dokumentierter Ausnahme mit Zeit, erfasster Pause und Begründung. **Pause zu kurz** zeigt Tage, an denen die Pause nicht reicht und keine Ausnahme anerkannt ist – etwa weil die beantragte Ausnahme noch offen ist oder abgelehnt wurde.

<a id="pflicht-pause-ausnahme"></a>
### Wie lege ich fest, ob eine fehlende Pause begründet werden darf?

Klicken Sie auf `Einstellungen` und scrollen Sie zum Abschnitt **Pflicht-Pause-Ausnahme**.

![Einstellungen, Abschnitt „Pflicht-Pause-Ausnahme“: Schalter „Ausnahme Pflicht-Pause war nicht möglich erlauben“ und „Genehmigung erforderlich“ mit Erklärtext und Speichern](/help/img/pl-pflicht-pause.webp)

1. `Ausnahme „Pflicht-Pause war nicht möglich“ erlauben` (Standard: an): Mitarbeitende und Admins können eine fehlende Pause begründen. Aus: Die Auswahl verschwindet überall, PraxisZeit lehnt jede Ausnahme ab – auch für Admins; ein Tag über 6 bzw. 9 Stunden lässt sich nur mit eingetragener Pause speichern.
2. `Genehmigung erforderlich` (Standard: aus): Ist er an, wird eine Ausnahme aus der Zeiterfassung erst nach Ihrer Genehmigung gespeichert (4-Augen-Prinzip). Beim Ausstempeln wird der Eintrag sofort mit der echten Zeit geschlossen, die Ausnahme ist nur beantragt: Es entsteht ein Änderungsantrag mit unveränderten Zeiten und der Begründung.
3. Klicken Sie auf `Speichern`.

> **Achtung:** **§ 4 ArbZG:** mindestens 30 Minuten Pause bei mehr als 6 Stunden, 45 Minuten bei mehr als 9 Stunden. Maßstab ist der ganze Tag; eine Unterbrechung zählt erst ab 15 Minuten als Pause. Fehlt die Pause, sperrt PraxisZeit an jedem Erfassungsweg – auch beim Ausstempeln –, bis eine Pause eingetragen oder, falls erlaubt, eine Ausnahme mit mindestens 10 Zeichen begründet ist.

> **Gut zu wissen:** **Beantragte Ausnahme entscheiden:** Den Antrag finden Sie unter `Änderungsanträge`. Genehmigt, steht die Ausnahme am Eintrag; abgelehnt, bleibt der Eintrag ohne Ausnahme und erscheint unter „Pause zu kurz“. Ihre **eigene** Ausnahme genehmigt ein weiteres Admin-Konto. Gibt es nur eines, lässt sie sich nur ablehnen – brauchen Sie dann selbst Ausnahmen, schalten Sie „Genehmigung erforderlich“ aus.

| Automatische Prüfung | Verhalten |
| --- | --- |
| § 3: mehr als 10 Stunden am Tag | beim Ausstempeln Warnung (die Zeit ist geleistet), bei manueller Eingabe und im Antrag Sperre |
| § 3: mehr als 8 Stunden am Tag, mehr als 48 Stunden in der Woche | Warnung |
| § 4: Pause fehlt | Sperre, auch beim Ausstempeln; Ausnahme mit Begründung, sofern erlaubt |
| § 5: weniger als 11 Stunden Ruhezeit | Warnung beim Einstempeln |
| § 6: Nachtarbeitnehmer über 8 Stunden | Warnung |
| Arbeit an Sonn- und Feiertagen | Warnung; ohne Ausnahmegrund nach § 10 ArbZG fordert PraxisZeit ihn an (Feld auch beim Ausstempeln) |

<a id="gruende-kind-krank-minijob"></a>
## Eigene Abwesenheitsgründe, Kind krank, Minijob

*Nicht jede Abwesenheit passt zu Urlaub, Krank oder Fortbildung. Mit **eigenen Gründen** – etwa „Berufsschule“ oder „Kind krank“ – bilden Sie solche Fälle ab; das **Verhalten** des Grundes sagt PraxisZeit, wie die Tage zu rechnen sind. Für Minijobs auf Arbeitszeitkonto gibt es zusätzlich Hinweise nach dem Mindestlohngesetz.*

<a id="eigenen-grund-anlegen"></a>
### Wie lege ich einen eigenen Abwesenheitsgrund an?

Klicken Sie auf `Einstellungen`. Der Bereich **Eigene Abwesenheitsgründe** steht ganz oben.

![Einstellungen, Bereich „Eigene Abwesenheitsgründe“: Eingabezeile mit Bezeichnung, Verhalten, Farbe und Hinzufügen, darunter die Vorlagen und der vorhandene Grund „Fortbildung extern“ mit „Zählt als gearbeitet“](/help/img/pl-abwesenheitsgrund.webp)

1. Tragen Sie die **Bezeichnung** ein, zum Beispiel „Berufsschule“ (höchstens 80 Zeichen).
2. Wählen Sie das **Verhalten**. Es bestimmt die Berechnung und lässt sich nach dem Anlegen **nicht mehr ändern**. Die **Farbe** daneben dürfen Sie jederzeit ändern.
3. Klicken Sie auf `Hinzufügen`. Der Grund erscheint in der Liste und steht beim Eintragen einer Abwesenheit in der Typ-Auswahl unter „Eigene Gründe“.
4. Die **Vorlagen (1-Klick aktivieren)** legen gängige Gründe mit einem Klick an, siehe [Kind krank und Sonderurlaub](#kind-krank-vorlage).
5. In der Liste ändern Sie Farbe und Bezeichnung (Eingabe verlassen = speichern) und schalten mit dem Haken `aktiv` einen Grund ein oder aus. Der Papierkorb löscht ihn.

| Verhalten | Wirkung | Typisch für |
| --- | --- | --- |
| Zählt als gearbeitet | Die geplanten Stunden werden als Arbeitszeit gutgeschrieben (wie Fortbildung), es entstehen keine Stundenverluste | Berufsschule (Arbeitszeit nach § 15 JArbSchG) |
| Bezahlt frei | Das Tagessoll wird 0 (saldoneutral), kein Urlaubsabzug – der Arbeitgeber zahlt weiter | Todesfall, Hochzeit, Geburt |
| Unbezahlt frei | Das Tagessoll wird 0 (saldoneutral), kein Urlaubsabzug, aber unbezahlt (Lohn gekürzt) | Kind krank (§ 45 SGB V), unbezahlter Sonderurlaub |
| Überstundenabbau | Das Überstundenkonto sinkt um das Tagessoll | Freizeitausgleich mit eigener Bezeichnung |

> **Gut zu wissen:** **Deaktivieren statt löschen:** Deaktivierte Gründe stehen beim Buchen nicht mehr zur Auswahl, bleiben aber an bestehenden Abwesenheiten erhalten. Löschen geht nur, solange keine Abwesenheit den Grund nutzt – sonst fordert PraxisZeit Sie auf, ihn zu deaktivieren. Berechnet wird ausschließlich nach dem Verhalten; Farbe und Bezeichnung ändern nichts an den Zahlen.

> **Gut zu wissen:** **Datenschutz:** Ein eigener Grund kann sensibel sein (z. B. „Reha“). Im Team-Kalender sehen andere Mitarbeitende eine Abwesenheit mit eigenem Grund nur als „abwesend“; die Bezeichnung sehen Admins und die betroffene Person selbst.

<a id="kind-krank-vorlage"></a>
### Wie richte ich „Kind krank“ und andere Sonderurlaub-Gründe ein?

Unter der Eingabezeile stehen die **Vorlagen**: Kind krank, Todesfall naher Angehöriger, Eigene Hochzeit, Geburt eines Kindes, Umzug (betrieblich), Arztbesuch (unvermeidbar) und Pflege naher Angehöriger.

![Eigene Abwesenheitsgründe mit Verhalten „Unbezahlt frei“: darunter der Haken „Gegen das Kind-krank-Jahreslimit zählen (§45 SGB V)“ und in der Reihe der Vorlagen der Knopf „Kind krank“](/help/img/pl-kind-krank-grund.webp)

1. Klicken Sie auf die Vorlage `+ Kind krank`. PraxisZeit legt den Grund sofort an: Verhalten **Unbezahlt frei**, mit Zählung gegen das Jahreslimit. Eine aktivierte Vorlage verschwindet aus der Reihe.
2. Wollen Sie einen Grund selbst anlegen, der gegen das Limit zählt, wählen Sie als **Verhalten** `Unbezahlt frei`.
3. Dann erscheint der Haken `Gegen das Kind-krank-Jahreslimit zählen (§45 SGB V)`. Setzen Sie ihn, bevor Sie auf `Hinzufügen` klicken – nur Gründe mit diesem Haken zählen.

> **Gut zu wissen:** **Die Vorlagen sind Vorschläge.** Bezahlt oder unbezahlt hängt von Ihrem Betrieb ab – die rechtliche Einordnung (etwa ob § 616 BGB im Arbeitsvertrag ausgeschlossen ist) liegt bei Ihnen. Weil das Verhalten nach dem Anlegen feststeht, legen Sie einen Grund mit anderem Verhalten selbst an. PraxisZeit bildet nur die Zeiterfassung ab; die Meldung an Krankenkasse und Lohnbuchhaltung erfolgt außerhalb.

<a id="kind-krank-anspruch"></a>
### Wie viele Kind-krank-Tage stehen Mitarbeitenden zu?

PraxisZeit zählt die Tage eines Kind-krank-Grundes je Kalenderjahr. Den Standardanspruch stellen Sie unter `Einstellungen` im Bereich **Kind-krank-Standardanspruch** ein.

![Einstellungen: Bereich „Kind-krank-Standardanspruch“ mit dem Feld „Standard Kind-krank-Tage/Jahr“ (15) und Speichern, darunter „Gesetzlicher Mindestlohn“ mit 13,90 €/h seit 1.1.2026](/help/img/pl-kind-krank-limit.webp)

1. Tragen Sie unter `Standard Kind-krank-Tage/Jahr` die Zahl der Tage ein (Voreinstellung 15). Sie gilt für alle ohne eigenen Wert.
2. Klicken Sie auf `Speichern`.
3. Darunter zeigt der Bereich **Gesetzlicher Mindestlohn** den aktuellen Wert und die nächste Stufe an (13,90 € pro Stunde seit 1.1.2026, 14,60 € ab 1.1.2027). Das ist nur eine Anzeige.

> **Gut zu wissen:** **Eigener Wert je Person:** Im Formular zum Bearbeiten einer Person gibt es das Feld „Kind-krank-Tage/Jahr (§45 SGB V)“; leer gilt der Standard, siehe [Mitarbeiter bearbeiten](#mitarbeiter-bearbeiten).

> **Achtung:** **Nur ein Hinweis, keine Sperre:** Wird der Anspruch beim Buchen überschritten, weist PraxisZeit darauf hin – die Abwesenheit wird **trotzdem erfasst**, denn der Fehltag muss dokumentiert werden. Das gilt beim Eintragen, im Monatsjournal und bei der Genehmigung eines Änderungsantrags. Den Jahresverbrauch sehen Sie in der **Benutzerverwaltung** unter dem Namen („Kind krank“ mit genommenen Tagen und Anspruch, rot bei Überschreitung), sobald ein Tag verbraucht ist.

<a id="minijob-konto"></a>
### Wie führe ich eine Minijob-Beschäftigte auf Arbeitszeitkonto?

Für Minijobber:innen auf **Arbeitszeitkonto** (§ 2 Abs. 2 MiLoG, „sonstige flexible Arbeitszeitregelung“) stellen Sie die Felder beim Anlegen im Formular ein, bei bestehenden Mitarbeitenden über `Arbeitszeit anpassen…` im Abschnitt **Urlaub und Abrechnung**, siehe [Vertragsverlauf](#vertragsverlauf). Im Bild: Julia Meyer, 10 Stunden pro Woche.

![Dialog „Arbeitszeit & Wochenstunden“ von Julia Meyer, Abschnitt „Urlaub und Abrechnung“: Haken „Arbeitszeitkonto (§ 2 Abs. 2 MiLoG)“, Vereinbarte Monatsarbeitszeit 43 Stunden mit 50-%-Grenze und Haken „Feste Monatsarbeitszeit“](/help/img/pl-minijob-konto.webp)

1. **Gültig ab:** Minijob-Einstellungen gelten immer ab dem Monatsersten. Ein anderes Datum lehnt PraxisZeit mit „Änderungen an Minijob-Einstellungen gelten immer ab dem Monatsersten.“ ab.
2. Setzen Sie den Haken `Arbeitszeitkonto (§ 2 Abs. 2 MiLoG) – 50-%-Prüfung & 12-Monats-Ausgleichsfrist`. Er setzt aktive Stundenzählung voraus.
3. Tragen Sie die **Vereinbarte Monatsarbeitszeit (h)** ein, im Bild 43. Bleibt das Feld leer, rechnet PraxisZeit Wochenstunden × 13/3 (bei 10 Stunden etwa 43,3). Die Zeile darunter nennt den aktuellen Mindestlohn und die Obergrenze des Kontos: die Hälfte, hier etwa 21,5 Stunden im Monat.
4. Optional: `Feste Monatsarbeitszeit (Monats-Soll = vereinbarte Monatsarbeitszeit)`. Der Haken erscheint nur bei aktivem Arbeitszeitkonto und macht die vereinbarte Monatsarbeitszeit zur Pflichtangabe.

| Hinweis | Regel | Wo erscheint er? |
| --- | --- | --- |
| 50-%-Regel | Die auf das Konto eingestellten Plusstunden dürfen pro Monat 50 % der vereinbarten Arbeitszeit nicht übersteigen. Beispiel 10 h/Woche: Monatszeit etwa 43,33 h, Grenze 21,67 h | beim Buchen und Ausstempeln, im eigenen Überstundenkonto, in der Benutzerverwaltung (Kennzeichen „MiLoG“) |
| 12-Monats-Ausgleichsfrist | Zeitguthaben auf dem Konto muss binnen 12 Kalendermonaten ausgeglichen werden; bei Überfälligkeit erscheint ein Hinweis | wie oben |
| Monatszeit überschritten | Nur bei fester Monatsarbeitszeit: das Monats-Ist inklusive Gutschriften übersteigt die vereinbarte Monatsarbeitszeit | wie oben |

> **Achtung:** **Alle Hinweise sind weich, nichts wird blockiert.** Die 50-%-Grenze bindet nur die mindestlohnwirksamen Stunden; wird über dem Mindestlohn vergütet, sind mehr Stunden möglich. PraxisZeit speichert **keine Lohndaten** und prüft die Verdienstgrenze von 603 € nicht – das bleibt der Lohnbuchhaltung.

> **Gut zu wissen:** **Wozu die vereinbarte Monatsarbeitszeit dient:** Sie ist die Bezugsgröße der 50-%-Prüfung. Die 12-Monats-Frist rechnet dagegen bewusst gegen das tatsächliche Monats-Soll, damit Urlaub und Feiertage das Konto nicht belasten.

> **Gut zu wissen:** **Feste Monatsarbeitszeit:** Das Monats-Soll ist jeden Monat die vereinbarte Monatsarbeitszeit – egal, ob der Monat vier oder fünf Montage hat; bei Ein- oder Austritt im Monat anteilig nach Kalendertagen. Die Tagesstunden heißen dann „Geplante Anwesenheit“ und bestimmen nur noch, wie viele Stunden an Feiertagen, Urlaubs- und Freistellungstagen als Ist gutgeschrieben werden. Unbezahlt entschuldigte Tage (Typ „Sonstiges“, z. B. Kind krank) mindern stattdessen das Monats-Soll um die geplanten Stunden. Im Monatsjournal heißt die Spalte dann „Geplant“, einen Tages-Saldo gibt es nicht; **verbindlich ist die Monatsübersicht**. Mehr dazu: [So rechnet PraxisZeit: Minijob und Mindestlohn](SO-RECHNET-PRAXISZEIT.md#minijob).

> **Achtung:** **Bekannte Grenze:** Fällt ein **ganzer Monat** durch Urlaub oder Krankheit aus, schreibt PraxisZeit nur den geplanten Anteil gut. Der flexible Rest bleibt als Defizit auf dem Konto stehen; dann ist eine manuelle Korrektur nötig, etwa über das Überstundenkonto oder den Jahresübertrag. Bei einzelnen Fehltagen rechnet PraxisZeit korrekt von selbst.

<a id="einstellungen"></a>
## Einstellungen

*Unter **Einstellungen** legen Sie fest, wie PraxisZeit für die ganze Praxis arbeitet. **Jeder Bereich hat einen eigenen Speichern-Knopf** – eine Änderung gilt erst, wenn Sie ihn drücken. Die Tabelle zeigt, wo Sie die Bereiche in diesem Handbuch finden.*

| Bereich in den Einstellungen | Wofür | Mehr dazu |
| --- | --- | --- |
| Eigene Abwesenheitsgründe | zusätzliche Gründe mit eigenem Verhalten, Vorlagen | [Eigenen Grund anlegen](#eigenen-grund-anlegen) |
| Feiertage | Bundesland der gesetzlichen Feiertage | [Bundesland einstellen](#bundesland-einstellen) |
| Eigene Feiertage | regionale Feiertage wie Schützenfest | [Regionalen Feiertag anlegen](#eigene-feiertage) |
| Sondertage (24./31.12.) | Modus je Tag: Arbeitstag, Halbtag, Frei, Verkürzt | [Sondertage](#sondertage-einstellen) |
| Verkürzte Tage | einzelne Tage mit Höchststunden | [Verkürzte Tage](#verkuerzte-tage) |
| Urlaubsgenehmigung | Genehmigungspflicht für Urlaub | [Urlaubsgenehmigung](#urlaubsgenehmigung) |
| Pflicht-Pause-Ausnahme | Ausnahme bei fehlender Pause erlauben | [Pflicht-Pause-Ausnahme](#pflicht-pause-ausnahme) |
| Onboarding / Willkommens-Tour | Tour beim ersten Login | [Tour und Schichtplanung](#tour-schichtplanung) |
| Schichtplanung | Planungswerkzeug ein- oder ausschalten | [Tour und Schichtplanung](#tour-schichtplanung), [Wochentage](#schicht-wochentage) |
| Betriebsferien \& Urlaub | überzählige Betriebsferien als Überstundenabbau | [Betriebsferien länger als der Urlaub](#betriebsferien-ueberstundenabbau) |
| Überstunden-Projektion zum Jahresende | Anzeige des voraussichtlichen Saldos | [Saldo zum Jahresende](#jahresende-projektion) |
| Soll-Arbeitszeit-Fenster | Puffer an den Rändern der Arbeitszeit-Blöcke | [Puffer einstellen](#puffer-einstellen) |
| Kind-krank-Standardanspruch | Tage je Jahr | [Kind-krank-Anspruch](#kind-krank-anspruch) |
| Gesetzlicher Mindestlohn | reine Anzeige | [Kind-krank-Anspruch](#kind-krank-anspruch) |
| Farben | Farbe je Anwesenheits- und Abwesenheitstyp | [Farben ändern](#farben) |

<a id="eigene-feiertage"></a>
### Wie lege ich einen regionalen Feiertag an?

Im Bereich **Eigene Feiertage** unter `Einstellungen`. Gesetzliche Feiertage stehen dort nur zur Information und lassen sich nicht ändern.

![Einstellungen, Bereich „Eigene Feiertage“: Jahresauswahl, Eingabezeile mit Name „Schützenfest“, Datum 20.07.2026 und dem Knopf „Hinzufügen“](/help/img/pl-eigene-feiertage.webp)

1. Wählen Sie oben rechts das **Jahr**; darüber blättern Sie auch durch die Liste der Feiertage.
2. Tragen Sie den **Namen** ein, zum Beispiel „Schützenfest“.
3. Wählen Sie das **Datum**.
4. Klicken Sie auf `Hinzufügen`. In der Liste bearbeiten Sie einen eigenen Feiertag mit dem Stift und löschen ihn mit dem Papierkorb.

> **Gut zu wissen:** Eigene Feiertage senken das Soll wie gesetzliche Feiertage und bleiben erhalten, wenn Sie das Bundesland wechseln.

> **Achtung:** **Liegt der Tag in einem abgeschlossenen Jahr,** weist PraxisZeit auf den veralteten Übertrag hin, sobald Sie einen eigenen Feiertag anlegen, verschieben oder löschen; ein reines Umbenennen löst keinen Hinweis aus. Stehen am Tag schon Zeiteinträge von Mitarbeitenden mit Arbeitszeit-Blöcken, nennt PraxisZeit sie – sie behalten ihre Anrechnung, bis Sie sie unverändert neu speichern. Siehe [Übertrag korrigieren](#vorjahresuebernahme).

<a id="urlaubsgenehmigung"></a>
### Müssen Urlaubsanträge genehmigt werden?

Im Bereich **Urlaubsgenehmigung** unter `Einstellungen`.

![Einstellungen, Bereich „Urlaubsgenehmigung“: Schalter „Genehmigung erforderlich“ mit Erklärtext und dem Knopf „Speichern“](/help/img/pl-urlaubsgenehmigung.webp)

1. Schalten Sie `Genehmigung erforderlich` an oder aus. **Aus** (Standard): Mitarbeitende buchen Urlaub direkt. **An:** Urlaubsanträge landen als „Offen“ unter `Anträge` bei Ihnen.
2. Klicken Sie auf `Speichern`.

> **Gut zu wissen:** Denselben Schalter finden Sie oben auf der Seite „Abwesenheitsanträge“, siehe [Urlaubsantrag genehmigen](#urlaubsantrag-genehmigen).

<a id="tour-schichtplanung"></a>
### Wie schalte ich die Willkommens-Tour und die Schichtplanung ein oder aus?

Die beiden Bereiche **Onboarding / Willkommens-Tour** und **Schichtplanung** stehen untereinander. Jeder hat seinen eigenen Speichern-Knopf.

![Einstellungen: Bereiche „Onboarding / Willkommens-Tour“ mit dem Schalter „Willkommens-Tour anzeigen“ und „Schichtplanung“ mit dem Schalter „Schichtplanung aktivieren“, beide mit eigenem Speichern](/help/img/pl-onboarding-schichtplanung.webp)

1. `Willkommens-Tour anzeigen` (Standard: an): Neue Mitarbeitende und Admins sehen beim ersten Login eine kurze Tour mit den wichtigsten Bereichen. Bereits gesehene Touren erscheinen nicht erneut.
2. `Schichtplanung aktivieren` (Standard: aus): Erst dann gibt es Wochen-Schichtpläne, Arbeitsplätze und Standorte. Solange der Schalter aus ist, sehen weder Admins noch Mitarbeitende die Schichtplanung.

> **Gut zu wissen:** Die Schichtplanung ist ein reines Planungswerkzeug und verändert **keine** Zeiterfassungs-, Urlaubs- oder Überstundendaten. Ist sie eingeschaltet, wählen Sie darunter die **geplanten Wochentage** (Standard Montag bis Freitag, mindestens ein Tag bleibt aktiv) und klicken auf `Wochentage speichern`. Eine Anleitung für die Ersteinrichtung finden Sie jederzeit über den Knopf `Schnellstart` unten links in der Seitenleiste.

<a id="jahresende-projektion"></a>
### Wie blende ich den voraussichtlichen Saldo zum Jahresende aus?

Im Bereich **Überstunden-Projektion zum Jahresende** unter `Einstellungen`. Beide Anzeigen sind standardmäßig an.

![Einstellungen, Bereich „Überstunden-Projektion zum Jahresende“: zwei Schalter „Im Mitarbeiter-Dashboard anzeigen“ und „Im Admin-Dashboard anzeigen“ mit Erklärtexten und Speichern](/help/img/pl-projektion.webp)

1. `Im Mitarbeiter-Dashboard anzeigen`: Aus, sehen Mitarbeitende die Vorschau-Zeile in ihrem eigenen Überstundenkonto nicht mehr; die Berechnung entfällt dann ganz.
2. `Im Admin-Dashboard anzeigen`: Aus, entfällt die Spalte „Überstd. Jahresende“ im Monats- und Wochenbericht. Sie erscheint ohnehin nur im laufenden Monat und nur, wenn mindestens eine Person schon künftigen Ausgleich gebucht hat.
3. Klicken Sie auf `Speichern`.

> **Gut zu wissen:** **Was die Projektion zeigt:** den Saldo bis heute, abzüglich der Stunden aller bereits gebuchten künftigen **Überstundenausgleich**-Tage. Urlaub, Krankheit und Fortbildung sind saldoneutral und fließen nicht ein. Beide Schalter wirken nur auf die Anzeige – das Überstundenkonto selbst rechnet PraxisZeit unverändert weiter.

<a id="puffer-einstellen"></a>
### Wie stelle ich den Puffer für die Arbeitszeit-Blöcke ein?

Im Bereich **Soll-Arbeitszeit-Fenster** unter `Einstellungen`. Der Puffer entscheidet, wie viel gestempelte Zeit vor, nach und zwischen den Arbeitszeit-Blöcken noch angerechnet wird.

![Einstellungen, Bereich „Soll-Arbeitszeit-Fenster“: Erklärtext zum Puffer, das Feld „Puffer für Soll-Arbeitszeit-Fenster (Min.)“ mit 15 und der Knopf „Speichern“](/help/img/pl-puffer.webp)

1. Tragen Sie im Feld `Puffer für Soll-Arbeitszeit-Fenster (Min.)` die Minuten ein (Standard 15, zulässig 0 bis 1439). Der Puffer gilt an jedem Blockrand, auch zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet. Stempelzeit weiter außerhalb zählt nicht. Ab 1439 Minuten, einem ganzen Tag, kappt PraxisZeit nichts mehr.
2. Klicken Sie auf `Speichern`.

> **Achtung:** **Eine Änderung wirkt nur auf neue Einträge.** Jeder gekappte Eintrag merkt sich seinen Puffer und behält ihn, auch wenn er später bearbeitet wird; gespeicherte Einträge ändern sich durch das Speichern allein nicht. Einträge aus der Zeit vor Version 1.20.0 tragen keinen gespeicherten Puffer und werden bei einer Bearbeitung mit dem aktuellen gekappt. Nur eine Arbeitszeit-Änderung mit Neuberechnung kappt die betroffenen Einträge mit dem dann gültigen Puffer neu – die Vorschau nennt ihn; verliert ein Eintrag dabei angerechnete Zeit, gilt der Verkürzungsschutz, siehe [Rückwirkend ändern](#rueckwirkend-aendern).

<a id="farben"></a>
### Wie ändere ich die Farben der Abwesenheitstypen?

Im Bereich **Farben** unter `Einstellungen`: je Typ eine Farbe – Arbeit/Anwesenheit, Fortbildung, Urlaub, Krank, Überstundenausgleich, Sonstiges und Bezahlte Freistellung. Sie gelten im Kalender, in den Übersichten und bei der Zeiterfassung.

![Einstellungen, Bereich „Farben“: je Anwesenheits- und Abwesenheitstyp ein Farbfeld mit „Aa“-Vorschau, darunter der Knopf „Speichern“](/help/img/pl-farben.webp)

1. Klicken Sie neben dem Typ auf das Farbfeld und wählen Sie die Farbe. Die kleine „Aa“-Vorschau zeigt, ob die Schrift auf der gewählten Farbe lesbar bleibt.
2. Klicken Sie auf `Speichern`.

<a id="jahresabschluss"></a>
## Jahresabschluss

*Zum Jahreswechsel berechnet PraxisZeit für alle aktiven Mitarbeitenden den **Überstunden-Saldo zum 31.12.** und den **Resturlaub** und trägt beides als **Übernahme** ins Folgejahr ein. Diesen Schritt lösen Sie selbst aus – am besten, wenn alle Anträge für das Jahr entschieden sind. Wie der Übertrag entsteht: [So rechnet PraxisZeit: Jahresabschluss](SO-RECHNET-PRAXISZEIT.md#jahresabschluss).*

<a id="jahresuebersicht"></a>
### Wo finde ich den Jahresabschluss?

Auf dem `Admin-Dashboard` unterhalb der Monatsübersicht steht die **Jahresübersicht** mit Urlaubs- und Krankheitstagen aller Mitarbeitenden – und den Knöpfen für den Abschluss.

![Jahresübersicht auf dem Admin-Dashboard: Jahr 2026 mit den Knöpfen Jahresabschluss, Abschluss löschen und Berichte, darunter die gelbe Jahresend-Warnung und die Tabelle mit Urlaub, Resturlaub, Krank und Überstunden](/help/img/pl-jahresuebersicht.webp)

1. Wählen Sie im Feld `Jahr` das Jahr, das Sie abschließen oder prüfen wollen.
2. Der orangefarbene Knopf `Jahresabschluss` startet den Abschluss, siehe [Jahresabschluss erstellen](#jahresabschluss-erstellen).
3. Der rote Knopf `Abschluss löschen` nimmt ihn zurück, siehe [Jahresabschluss löschen](#jahresabschluss-loeschen).
4. Die Spalte **Resturlaub** zeigt die offenen Urlaubstage: grün über 5 Tage, gelb bis 5 Tage, rot bei 0 oder weniger.
5. Im letzten Quartal des laufenden Jahres erscheint die gelbe **Jahresend-Warnung: Offene Urlaubstage** mit allen, die noch mindestens einen ganzen Urlaubstag offen haben, und dem Verfallsdatum.

> **Gut zu wissen:** **Kleine Reste lösen keine Warnung aus:** Bruchteile unter einem Tag – typisch bei Teilzeit, etwa 0,3 oder 0,5 Tage – lassen sich nicht als ganzer Tag nehmen und werden im Folgejahr üblicherweise mit weiteren Bruchteilen zusammengelegt. In der Tabelle, im Urlaubskonto und beim Jahresabschluss zählen sie unverändert mit. Das Verfallsdatum ist in der Regel der 31.03. des Folgejahres, sonst die für die Person hinterlegte Frist; bei unterschiedlichen Fristen steht das Datum hinter jedem Namen. Dieselbe Schwelle und dasselbe Datum gelten für den Hinweis im Urlaubskonto auf dem Dashboard der Mitarbeitenden.

<a id="jahresabschluss-erstellen"></a>
### Wie erstelle ich den Jahresabschluss?

Wählen Sie in der Jahresübersicht das Jahr und klicken Sie auf `Jahresabschluss`. Es öffnet sich ein Bestätigungsdialog; erst Ihre Bestätigung löst den Abschluss aus.

![Bestätigungsdialog „Jahresabschluss 2026“: Überstunden-Saldo und Resturlaub aller aktiven Mitarbeiter werden als Übernahme in 2027 gespeichert, bestehende Übernahmen werden überschrieben; Knöpfe Abbrechen und Jahresabschluss erstellen](/help/img/pl-jahresabschluss-dialog.webp)

1. Lesen Sie den Text: Überstunden-Saldo und Resturlaub aller **aktiven** Mitarbeitenden werden berechnet und als Übernahme ins Folgejahr gespeichert. **Bestehende Übernahmen für das Folgejahr werden überschrieben.** Der Dialog nennt, wie viele davon von Hand eingetragen wurden. Beim **laufenden Jahr** warnt er zusätzlich, dass das Jahr noch nicht zu Ende ist: Das Soll der verbleibenden Monate würde ohne Ist eingefroren. Schließen Sie ein Jahr deshalb erst nach seinem Ende ab; ein künftiges Jahr lässt sich gar nicht abschließen.
2. Mit `Abbrechen` geschieht nichts.
3. Mit `Jahresabschluss erstellen` bestätigen Sie. Die Meldung nennt, wie viele Mitarbeitende nach dem Folgejahr übernommen wurden.

| PraxisZeit berechnet | Bedeutung im Folgejahr |
| --- | --- |
| Überstunden-Saldo zum 31.12. des Jahres (immer der volle Zeitraum, nicht „bis heute“) | Startwert des Überstundenkontos |
| Resturlaub in Tagen | wird dem Jahresurlaub des Folgejahres hinzugerechnet |

> **Gut zu wissen:** Der Abschluss schließt auch Mitarbeitende **ohne Stundenzählung** ein: Für sie ist der Überstundenwert 0, der Resturlaub wird tagebasiert übernommen – sonst ginge er beim Jahreswechsel verloren.

> **Achtung:** **PraxisZeit lehnt den Abschluss ab, solange offene Anträge das Jahr betreffen:** noch nicht entschiedene Änderungsanträge oder offene Urlaubsanträge. Die Meldung lautet zum Beispiel „Jahresabschluss 2026 abgelehnt: es gibt noch 2 offene Änderungsanträge für dieses Jahr. Bitte erst bearbeiten, dann erneut versuchen.“ Ein später genehmigter Antrag würde sonst den eingefrorenen Saldo verschieben. Entscheiden Sie die Anträge unter `Änderungsanträge` und `Anträge` und starten Sie den Abschluss dann erneut.

> **Achtung:** **Erneut ausführen überschreibt:** Ein zweiter Abschluss für dasselbe Jahr ersetzt die Übernahmen **aller** aktiven Mitarbeitenden für das Folgejahr – auch von Hand eingetragene. Die Zeile gilt danach wieder als Abschluss-Zeile.

<a id="jahresabschluss-loeschen"></a>
### Wie nehme ich einen Jahresabschluss zurück?

Das geht, wenn ein Abschluss versehentlich erstellt wurde. Die Löschung ist **unwiderruflich**.

1. Wählen Sie in der Jahresübersicht das Jahr, dessen Abschluss Sie löschen möchten.
2. Klicken Sie auf den roten Knopf `Abschluss löschen`.
3. Lesen Sie den Dialog „Jahresabschluss … löschen“ sorgfältig: Alle Übernahmen für das Folgejahr, die durch diesen Jahresabschluss erzeugt wurden, werden gelöscht – für alle Mitarbeitenden.
4. Bestätigen Sie mit `Jahresabschluss löschen`. Gibt es keinen Abschluss für das Jahr, meldet PraxisZeit „Kein Jahresabschluss für … gefunden“.

> **Gut zu wissen:** **Von Hand eingetragene Übernahmen bleiben stehen.** Das Löschen entfernt nur Übernahmen, die der Jahresabschluss erzeugt hat – Werte, die Sie in der Vorjahresübernahme eingetragen oder korrigiert haben, nicht.

<a id="vorjahresuebernahme"></a>
### Wie trage ich einen Übertrag von Hand ein oder korrigiere ihn?

Für einzelne Personen, etwa beim Start mit PraxisZeit oder nach einer Korrektur. Klicken Sie in der `Benutzerverwaltung` in der Zeile der Person auf den Knopf `Vorjahresübernahme`.

![Dialog „Vorjahresübernahme“ von Maria Hoffmann: Auswahl des Jahres, Überstunden aus dem Vorjahr in Stunden, Resturlaub aus dem Vorjahr in Tagen und der Knopf „Speichern“](/help/img/pl-uebernahme.webp)

1. Wählen Sie das **Jahr**. Die Werte gelten als Übernahme **in** das gewählte Jahr.
2. **Überstunden aus Vorjahr (Stunden):** positiv ist ein Guthaben, negativ sind Minusstunden.
3. **Resturlaub aus Vorjahr (Tage):** wird zum Jahresurlaub des gewählten Jahres addiert.
4. Klicken Sie auf `Speichern`. Unter „Gespeicherte Übernahmen“ stehen alle Jahre der Person; ein Klick auf eine Zeile lädt ihre Werte ins Formular.

> **Achtung:** **Rückwirkende Änderungen rechnet PraxisZeit nie von selbst nach.** Ändert sich etwas in einem bereits abgeschlossenen Jahr – Bundesland-Wechsel, Storno eines genehmigten Urlaubs, gelöschte Betriebsferien, geänderte Sondertage oder eigene Feiertage –, meldet PraxisZeit zum Beispiel „Jahresabschluss 2025 bereits erfolgt — Carryover 2026 ist nun veraltet, bitte Jahresabschluss erneut ausführen.“ Eine automatische Neuberechnung würde Ihre von Hand korrigierten Werte überschreiben. Prüfen Sie den Übertrag und führen Sie den Abschluss bei Bedarf erneut aus, danach tragen Sie Handkorrekturen noch einmal ein.

<a id="import"></a>
## Import

*Unter **Import** übernehmen Sie historische **Zeiteinträge** aus einer TimeRec-Datei, zum Beispiel Altdaten aus Ihrer bisherigen Zeiterfassung. Gedacht ist der Import für die einmalige Datenübernahme bei der Einführung. **Abwesenheiten** (Urlaub, Krank usw.) werden nicht importiert.*

| Anforderung | Wert |
| --- | --- |
| Format | echtes .xls (TimeRec-Export, BIFF) – keine .xlsx- und keine CSV-Dateien |
| Größe | höchstens 5 MB |
| Tabellenblatt | „Zeiterfassung“ mit den Spalten Datum, Tag, Total, Ein, Aus, Tagesnotiz |
| Vorlage | Es gibt keine Vorlagendatei zum Herunterladen. |

<a id="import-hochladen"></a>
### Wie lade ich eine TimeRec-Datei hoch?

Klicken Sie in der Navigation auf `Import`. Der Assistent hat drei Schritte: `Hochladen`, `Vorschau` und `Ergebnis`.

![Import, Schritt „Hochladen“: Auswahl der Person Petra Schulz, das gestrichelte Feld mit der gewählten TimeRec-Datei im Format xls und der Knopf „Datei analysieren“](/help/img/pl-import-hochladen.webp)

1. Wählen Sie unter **Benutzer** die Person, der die Einträge zugeordnet werden.
2. Ziehen Sie die .xls-Datei in das gestrichelte Feld oder klicken Sie hinein und wählen Sie die Datei aus. Der Dateiname erscheint im Feld.
3. Klicken Sie auf `Datei analysieren`. Dabei wird die Datei nur gelesen – gespeichert ist noch nichts.

<a id="import-vorschau"></a>
### Wie lese ich die Vorschau?

Die Vorschau zeigt alle gefundenen Einträge mit Datum, Von, Bis, Pause und Netto. Die Netto-Stunden rechnet der Server so, wie er sie anschließend speichert.

![Import, Schritt „Vorschau“: 20 Einträge gefunden, 6 werden importiert, 14 übersprungen, 1 Konflikt; in der Tabelle Zeilen mit Datum, Von, Bis, Pause, Netto und Status „Wird übersprungen“ samt Grund oder „Neu“](/help/img/pl-import-vorschau.webp)

1. Über der Tabelle stehen die Zahl der **Einträge**, wie viele davon importiert und wie viele **übersprungen** werden, die **Konflikte** (rot) und die **Hinweise** (gelb). **Konflikt** heißt: Ein Eintrag mit demselben Beginn am selben Tag ist schon vorhanden. Ob er ersetzt wird, entscheiden Sie im nächsten Schritt.
2. **Wird übersprungen:** Diese Zeile übernimmt der Import nicht. Der Grund steht direkt darunter (siehe Tabelle unten). **Hinweise** (gelb) stehen ebenso als Text in der Zeile: ArbZG-Warnungen (z. B. Ruhezeit, Höchstarbeitszeit) und bei hinterlegten Arbeitszeit-Blöcken die Kappung der importierten Zeit.
3. **Neu:** Die Zeile wird ohne Beanstandung importiert. Unter Netto steht bei gekappten Zeilen die nicht angerechnete Zeit, zum Beispiel „2:30 h nicht angerechnet“.

| Der Import überspringt … | Text in der Vorschau |
| --- | --- |
| einen ganzen Tag, an dem sich die Pause nach § 4 ArbZG nicht abziehen lässt | „Wird übersprungen — die Pause nach § 4 ArbZG lässt sich mit den Zeilen dieses Tages nicht abziehen (es fehlen 10 Min). Bitte den Tag von Hand erfassen.“ |
| einen Tag mit mehr als 10 Stunden angerechneter Arbeitszeit | „Wird übersprungen — die Tagesarbeitszeit beträgt 11:15 h und überschreitet die Höchstgrenze von 10 h nach § 3 ArbZG. Bitte den Tag von Hand erfassen.“ |
| eine Zeile, die sich mit einem vorhandenen Eintrag oder einer früheren Zeile des Tages überschneidet | „Wird übersprungen — die Zeile überschneidet sich mit dem Eintrag 08:00–12:00 (Zeiteinträge einer Person dürfen sich nicht überschneiden).“ |
| Zeilen vor dem ersten oder nach dem letzten Arbeitstag der Person | „Wird übersprungen — Datum liegt nach dem letzten Arbeitstag (25.09.2026).“ |
| Zeilen mit einem Datum nach heute | „Wird übersprungen — Datum liegt in der Zukunft.“ |

> **Gut zu wissen:** **Die Pause rechnet der Import je Tag:** Mehrere Zeilen desselben Tages (z. B. ein geteilter Dienst) und dort schon vorhandene Einträge zählen zusammen; ein Abstand von mindestens 15 Minuten zwischen zwei Einträgen deckt die Pausenpflicht ab. Abgezogen wird nur, was dann noch fehlt – an der längsten Zeile des Tages. Reicht das nicht, übernimmt der Import den Tag **nicht**, auch wenn die Ausnahme „Pflicht-Pause war nicht möglich“ erlaubt ist, denn der Import kennt keine Begründung. Erfassen Sie solche Tage von Hand.

> **Achtung:** **Altdaten:** Prüfen Sie vorher, dass als **Erster Arbeitstag** der tatsächliche Eintritt eingetragen ist und nicht der Starttag von PraxisZeit – Zeilen davor überspringt der Import. Eine Zeile ganz außerhalb der Arbeitszeit-Blöcke (z. B. 18:00–20:00 bei einem Block 08:00–12:00) übernimmt er dagegen wie jeden gestempelten Eintrag: angerechnet werden 0 Stunden, die Zeiten bleiben als Rohstempel gespeichert.

<a id="import-bestaetigen"></a>
### Wie bestätige ich den Import und was steht im Ergebnis?

Unter der Tabelle entscheiden Sie über Konflikte und starten den Import.

![Import, Ende der Vorschau: Haken „Konflikte überschreiben (1 Eintrag)“ und die Knöpfe „Zurück“ und „Import bestätigen“ unter der Tabelle der gefundenen Einträge](/help/img/pl-import-bestaetigen.webp)

1. `Konflikte überschreiben` (nur sichtbar, wenn es Konflikte gibt): Angekreuzt ersetzt der Import die vorhandenen Einträge, sonst bleiben sie stehen und zählen für die Pause des Tages mit. Die Vorschau rechnet jeden Konflikt als überschrieben.
2. `← Zurück` bringt Sie zur Auswahl von Person und Datei.
3. Klicken Sie auf `Import bestätigen`. Sollen vorhandene Einträge überschrieben werden, fragt PraxisZeit noch einmal nach („Einträge überschreiben?“).
4. Das **Ergebnis** nennt die Zahl der importierten, überschriebenen und übersprungenen Einträge. Die **Hinweise** klappen Sie auf: Ruhezeit (§ 5) und Nachtarbeit (§ 6), die der Server bei der Bestätigung prüft, eine angepasste Pause („Pause an den Tag angepasst (0 → 30 Min)“) und der Grund jeder übersprungenen Zeile. Der Import steht im **Änderungsprotokoll**. Mit `Weiteren Import starten` beginnen Sie von vorn.

> **Gut zu wissen:** **Bestätigung = Vorschau, neu gerechnet:** Höchstarbeitszeit, Pause und Überschneidungen rechnet die Bestätigung noch einmal und überspringt betroffene Tage oder Zeilen – die Hinweise der Vorschau übernimmt das Ergebnis nicht ungeprüft. Überschreibt der Import einen **anerkannten** Eintrag, steht in der Kurzinfo „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet.“

<a id="protokoll-fehler-monitoring"></a>
## Protokoll & Fehler-Monitoring

*Das **Änderungsprotokoll** hält fest, wer wann an Zeiteinträgen, Abwesenheiten und Verwaltungseinstellungen etwas geändert hat. Es dient als Nachweis nach § 16 Abs. 2 ArbZG. Im laufenden Betrieb wird das Protokoll nur ergänzt; jede Zeile trägt eine Prüfsumme. Entfernt werden Zeilen nur beim endgültigen Löschen einer Person (Art. 17 DSGVO, selbst protokolliert) und durch die Aufbewahrungsfrist: Protokollzeilen zu Anträgen werden nach 730 Tagen gelöscht und hinterlassen je betroffener Person einen Vermerk (Quelle „Aufbewahrungsfrist“) mit den entfernten Kettengliedern. Bei der Anonymisierung einer Person wird Klartext in Notizen ersetzt. Daneben zeigen **Konto-Vorgänge** die sicherheitsrelevanten Handlungen und das **Fehler-Monitoring** technische Störungen.*

<a id="protokoll-lesen"></a>
### Wie lese ich das Änderungsprotokoll?

Klicken Sie in der Navigation auf `Änderungsprotokoll`. Die Tabelle zeigt die Änderungen des gewählten Monats, die neuesten zuerst. Ihre Spalten: **Zeitpunkt**, **Mitarbeiter** (die Person, deren Eintrag sich geändert hat), **Geändert von** (die handelnde Person), **Aktion**, **Quelle** sowie **Alte Werte** und **Neue Werte**.

![Änderungsprotokoll: Monatswähler, Auswahl der Person und die Tabelle mit Zeitpunkt, Mitarbeiter, Geändert von, Aktion, Quelle sowie alten und neuen Werten](/help/img/pl-protokoll.webp)

1. **Monat wählen:** mit den Pfeilen neben dem Monatsnamen. `Zum aktuellen Monat springen` bringt Sie zurück.
2. **Person filtern:** Die Auswahl steht auf „Alle Mitarbeitende“; wählen Sie eine Person, sehen Sie nur ihre Zeilen.
3. **Quelle** zeigt, auf welchem Weg die Änderung entstand, zum Beispiel „Manuell“, „Ausstempeln“, „Antrag“, „Import“, „Jahresabschluss“, „Einstellungen“ oder „Stundenänderung“. Wurde die Person unter **Geändert von** später endgültig gelöscht (Art. 17 DSGVO), steht dort „Gelöschte Person“.
4. **Alte Werte** und **Neue Werte** zeigen Datum, Zeiten, Pause und Notiz vorher und nachher; bei einer Einstellung steht dort der Wert vor und nach der Änderung.

| Was PraxisZeit protokolliert | Beispiele |
| --- | --- |
| Zeiteinträge | Erstellen, Ändern, Löschen, Ausstempeln – auch Einträge, die Mitarbeitende selbst am selben Tag anlegen |
| Abwesenheiten | neue Abwesenheiten, Stornierungen |
| Anträge | Korrekturanträge stellen, genehmigen, ablehnen |
| Arbeitszeit-Änderungen und Anerkennungen | je Änderung eine Sammelzeile (Wirkungsdatum, neu berechnete Einträge, Grund), dazu eine Zeile je neu berechnetem Eintrag; Quelle „Stundenänderung“, „Neukappung (Arbeitszeit-Änderung)“ oder „Anrechnung anerkannt“ |
| Pflicht-Pause-Ausnahmen | die erfasste § 4-Ausnahme samt Begründung (Quelle „Pausen-Verzicht“) |
| Überträge und Jahresabschluss | manuell gesetzte Überträge und je Person der Übertrag beim Anlegen oder Löschen eines Jahresabschlusses |
| Einstellungen, Feiertage, verkürzte Tage | jede geänderte Einstellung mit altem und neuem Wert („Einstellung geändert“) |
| Benutzerangaben mit Wirkung auf Auswertungen | „Ausgenommen nach § 18 ArbZG“, „Nachtarbeitnehmer“, erster und letzter Arbeitstag („Benutzerangabe geändert“) |

> **Gut zu wissen:** **Tatsächliche Stempel:** Weichen die angerechnete und die gestempelte Zeit eines Eintrags voneinander ab, nennt die Zeile beide, zum Beispiel „07:45 - 16:15“ und darunter „gestempelt 06:00 - 18:00“. Das gilt auch beim Löschen.

> **Achtung:** **Das Protokoll ist kein unveränderbares Archiv.** Es macht nachträgliche Veränderungen **erkennbar**, verhindern kann sie nur der Schutz des Servers. Bewahren Sie deshalb auch die Datensicherungen auf, siehe [Datensicherung](#sicherung-einrichten).

<a id="protokoll-pruefen"></a>
### Wie prüfe ich, ob das Protokoll unverändert ist?

Unter der Tabelle steht die Karte **Prüfung des Änderungsprotokolls**. PraxisZeit prüft jede Nacht (03:15 Uhr) jede Zeile gegen ihre Prüfsumme, versiegelt neue Zeilen zu einer Kette und prüft, ob Glieder fehlen.

![Karte „Prüfung des Änderungsprotokolls“ mit dem Knopf „Jetzt prüfen“ und der Zeile zum Ergebnis der letzten Prüfung](/help/img/pl-protokoll-pruefung.webp)

1. Klicken Sie auf `Jetzt prüfen`, wenn Sie nicht bis zur nächsten Nacht warten möchten.
2. Die Zeile **Letzte Prüfung** nennt Zeitpunkt und Ergebnis. Solange noch keine Prüfung gelaufen ist, steht dort „Noch keine Prüfung gelaufen.“

| Ergebnis | Bedeutung und was Sie tun |
| --- | --- |
| **in Ordnung** | Keine Zeile verändert, keine entfernt. Ältere Zeilen ohne prüfbare Prüfsumme (Altbestand) werden nur gezählt. |
| **Abweichung gefunden** | Zeilen wurden außerhalb von PraxisZeit verändert oder entfernt, zum Beispiel direkt in der Datenbank. Der Vorgang steht zusätzlich unter „Konto-Vorgänge“ und im Fehler-Monitoring. Bewahren Sie die Datensicherungen auf und informieren Sie den Support. |
| **Kettenende fehlt** oder **ungültig** | Der versiegelte Abschluss der Kette ist weg oder verändert. PraxisZeit legt ihn **nicht** von selbst neu an. Bis zur Klärung sind das endgültige Löschen von Personen und das automatische Entfernen nach der Aufbewahrungsfrist gesperrt. Erst wenn die Ursache geklärt ist (zum Beispiel eine Datensicherung geprüft), setzen Sie ihn mit `Kettenende neu setzen…` und einem **Grund** (mindestens 10 Zeichen) neu. Das Neusetzen steht danach dauerhaft im Protokoll. |

> **Achtung:** **Der Schlüssel SECRET\_KEY gehört zur Prüfung:** Die Prüfsummen hängen am geheimen Schlüssel des Servers. Geht er verloren (zum Beispiel bei einer Neuinstallation ohne die Datei config/.secret-key), lassen sich die Prüfsummen nicht mehr prüfen. Bewahren Sie ihn getrennt von den Sicherungen auf.

<a id="konto-vorgaenge"></a>
### Wo sehe ich Konto-Vorgänge?

Die Liste **Konto-Vorgänge** steht ganz unten auf der Seite `Änderungsprotokoll`: Konten, Rollen, Passwörter, Zwei-Faktor und Datenbank-Sicherungen, also wer wann was getan hat. Sie zeigt die neuesten 200 Vorgänge und ist nicht gefiltert.

![Liste „Konto-Vorgänge“ unter dem Änderungsprotokoll mit den Spalten Zeitpunkt, Vorgang, Konto, Durch und Detail](/help/img/pl-konto-vorgaenge.webp)

1. Die Liste beginnt mit dem neuesten Vorgang. **Zeitpunkt** nennt Datum und Uhrzeit, **Konto** die betroffene Person, **Detail** ergänzt Einzelheiten, zum Beispiel die Rolle eines neuen Kontos.
2. **Vorgang** nennt, was geschah, zum Beispiel „Konto angelegt“, „Konto deaktiviert“, „Rolle geändert“, „Sicherung erstellt“, „Sicherung heruntergeladen“ oder „Sicherung gelöscht“.
3. **Durch** nennt die handelnde Stelle. Bei Notfall-Vorgängen auf dem Server steht dort „Kommandozeile (Benutzer@Rechner)“, siehe [Admin-Passwort verloren](#passwort-zuruecksetzen).

| In den Konto-Vorgängen stehen | Hinweis |
| --- | --- |
| Konten angelegt (mit Rolle), Benutzernamen geändert, Konten deaktiviert oder reaktiviert, Rolle gewechselt | Admin ↔ Mitarbeitende |
| fremdes Passwort durch die Verwaltung gesetzt | Das eigene Passwort ändern Sie unter **Profil → Passwort ändern**, nicht über die Benutzerverwaltung. |
| Zwei-Faktor im Profil ein- oder abgeschaltet, durch die Verwaltung zurückgesetzt, falsche Zwei-Faktor-Codes | Nach 10 falschen Codes in einer Stunde ist die Anmeldung des Kontos für eine Stunde gesperrt. |
| Abmeldung nach 5 falschen Passworteingaben in einer offenen Sitzung | zum Beispiel beim Passwort ändern oder beim Herunterladen einer Sicherung |
| Datenbank-Sicherungen erstellt, heruntergeladen, gelöscht, Einstellungen geändert | Die geplante tägliche Sicherung steht nicht darin. |
| Notfall-Vorgänge auf dem Server (Passwort-Reset, Zwei-Faktor abschalten, Reaktivieren) | Siehe das letzte Kapitel dieses Handbuchs. |

> **Gut zu wissen:** **Fehlgeschlagene Anmeldungen stehen hier nicht.** Sie stehen im Protokoll des Servers (AUTH login\_failed …), nicht im Änderungsprotokoll.

<a id="fehler-monitoring"></a>
### Wie lese ich das Fehler-Monitoring?

Klicken Sie in der Navigation auf `Fehler-Monitoring`. Die Seite zeigt technische Fehler, die im Betrieb aufgetreten sind.

![Fehler-Monitoring: oben der Knopf „Aktualisieren“, darunter die Reiter Alle, Offen, Ignoriert und Behoben und der grüne Hinweis „Keine Fehler gefunden“](/help/img/pl-fehler-monitoring.webp)

1. `Aktualisieren` lädt die Liste und die Zähler neu. Liegen Fehler vor, zeigen Zähler oben die Anzahl je Status (Offen, Ignoriert, Behoben).
2. Die Reiter `Alle`, `Offen`, `Ignoriert` und `Behoben` filtern die Liste. Am Reiter „Offen“ steht die Zahl der offenen Fehler, sobald es welche gibt.
3. Die Liste zeigt jeden Fehler als eigene Karte. Gibt es keinen, steht hier „Keine Fehler gefunden“, wie im Bild.

| Jeder Eintrag zeigt | Bedeutung |
| --- | --- |
| Stufe (zum Beispiel ERROR) | Schweregrad des Fehlers |
| ×Zahl | wie oft derselbe Fehler aufgetreten ist; einmalige Fehler sind meist unkritisch |
| Methode und Pfad | welcher Aufruf betroffen war |
| Meldung | die Fehlermeldung, oft mit verständlicher Beschreibung |
| Zuerst und Zuletzt | wann der Fehler zum ersten und zum letzten Mal auftrat |

| Symbol am Eintrag | Wirkung |
| --- | --- |
| Häkchen („Als behoben markieren“) | setzt den Fehler auf „Behoben“ |
| durchgestrichenes Auge („Ignorieren“) | blendet einen offenen Fehler aus der Liste „Offen“ aus |
| Warndreieck („Wieder öffnen“) | setzt einen behobenen oder ignorierten Fehler zurück auf „Offen“ |
| Papierkorb („Löschen“) | entfernt den Eintrag nach Rückfrage |
| Pfeil | klappt Stack Trace und GitHub-Issue auf |

> **Gut zu wissen:** **Was tun bei Fehlern?** Lesen Sie die Meldung, prüfen Sie die Häufigkeit und notieren Sie bei wiederkehrenden Fehlern Zeitstempel und Meldung. Wenden Sie sich an Ihren IT-Support oder melden Sie den Fehler als GitHub-Issue: Im aufgeklappten Eintrag öffnet `Issue auf GitHub erstellen` ein vorbereitetes Issue; die Adresse eines bestehenden Issues können Sie dort eintragen und speichern.

> **Achtung:** **Datenschutz (Art. 28 DSGVO):** Fehlermeldungen können personenbezogene Daten enthalten. Prüfen Sie vor der Übertragung zu GitHub, ob der Stack Trace sensible Angaben enthält; GitHub ist als Auftragsverarbeiter einzustufen. Die Seite weist im aufgeklappten Eintrag selbst darauf hin.

<a id="datensicherung"></a>
## Datensicherung

*PraxisZeit speichert alle Zeitdaten in einer Datenbank. **§ 16 ArbZG verlangt, Zeitaufzeichnungen mindestens 2 Jahre aufzubewahren.** Unter **Datensicherung** erstellen und verwalten Sie Sicherungen ohne Kommandozeile, in der Docker- **und** in der nativen Installation. Stellen Sie die Aufbewahrungsdauer entsprechend ein, halten Sie eine Kopie **außerhalb** des Servers vor und sichern Sie vor jedem Update zusätzlich.*

<a id="sicherung-einrichten"></a>
### Wie sichere ich jetzt und wie richte ich die tägliche Sicherung ein?

Klicken Sie in der Navigation auf `Datensicherung`. Eine Sicherung ist ein komprimierter Datenbank-Dump (praxiszeit\_\<Zeitstempel\>.sql.gz).

![Datensicherung: „Jetzt sichern“, die Einstellungen der geplanten Sicherung mit Uhrzeit, Aufbewahrung und Speicherort und darunter die Liste der vorhandenen Sicherungen](/help/img/pl-datensicherung.webp)

1. `Jetzt sichern` erstellt sofort eine vollständige Sicherung. Sie erscheint danach in der Liste.
2. Haken bei `Tägliche automatische Sicherung aktivieren`, wenn PraxisZeit täglich selbst sichern soll. Ein Hinweis unter dem Haken sagt, dass die folgenden Einstellungen für die Docker-Installation gelten und native Installationen über das Betriebssystem sichern.
3. **Uhrzeit (Stunde, 0–23), nur Docker:** lokale Zeit (Europe/Berlin); die Sicherung läuft um HH:30. Das gilt für die Docker-Installation; nativ sichert der Timer des Betriebssystems (Linux 02:00, Windows und macOS 03:00).
4. **Aufbewahrung (Tage), nur Docker:** ältere Sicherungen löscht PraxisZeit automatisch. Für § 16 ArbZG sind mindestens 2 Jahre (730 Tage) nötig; die Seite schlägt zunächst 30 Tage vor. Nativ gilt stattdessen retention\_days im Abschnitt \[backup\] der Datei config/praxiszeit.conf (Standard 31 Tage). Sonst zusätzlich Jahresarchive außerhalb des Servers ablegen.
5. **Speicherort (optional, nur Docker):** leer bedeutet Standardverzeichnis. Tragen Sie einen **absoluten Pfad** ein (relative Pfade lehnt PraxisZeit ab); er muss für den Dienst beschreibbar sein. Zum Zurücksetzen auf das Standardverzeichnis leeren Sie das Feld und speichern.
6. Klicken Sie auf `Einstellungen speichern`. Erst dann gelten Uhrzeit, Aufbewahrung und Speicherort, und zwar nur in der Docker-Installation; nativ steuert der Timer des Betriebssystems die geplante Sicherung.
7. Unter **Vorhandene Sicherungen** stehen Datei, Größe und Zeitpunkt. Ist die neueste Sicherung älter als 36 Stunden, erscheint oben ein Hinweis: Prüfen Sie dann den Zeitplan oder sichern Sie sofort. Dort laden Sie eine Sicherung herunter oder löschen sie, siehe die Tipps unten.

> **Gut zu wissen:** **Wo die Sicherungen liegen:** Docker im Volume praxiszeit\_backups, nativ im Verzeichnis data/backups/. **Native Installation:** Die \*geplante\* Sicherung läuft dort weiterhin über den Timer des Betriebssystems (Linux: täglich 02:00 über systemd, Windows: täglich 03:00 als geplante Aufgabe, macOS: täglich 03:00 über launchd). Die Einstellung auf dieser Seite steuert die Docker-Variante; „Jetzt sichern“ und die Liste funktionieren überall. Die Aufbewahrungsdauer der nativen Timer steht in config/praxiszeit.conf (retention\_days, Standard 31 Tage).

> **Gut zu wissen:** **Herunterladen und Löschen:** In der Liste lädt das Symbol „Herunterladen“ die Datei auf Ihren PC; vorher fragt PraxisZeit nach **Ihrem Passwort** (Dialog „Sicherung herunterladen“), weil die Datei die gesamte Datenbank mit allen Gesundheitsdaten enthält. Das Symbol „Löschen“ entfernt eine Sicherung nach Rückfrage endgültig. Erstellen, Herunterladen, Löschen und geänderte Einstellungen stehen unter „Konto-Vorgänge“, siehe [Konto-Vorgänge](#konto-vorgaenge).

> **Achtung:** **Sicherungen sind nicht verschlüsselt:** Sie enthalten die ganze Datenbank einschließlich Krankheitstagen. Legen Sie eine Kopie außer Haus nur verschlüsselt ab, zum Beispiel als 7-Zip-Archiv mit AES-256 oder auf einem BitLocker-USB-Stick, und löschen Sie heruntergeladene Dateien danach aus dem Download-Ordner. Spielen Sie nur eigene Sicherungen ein.

> **Achtung:** **Speicherort:** PraxisZeit lehnt Netzwerkpfade (\\\\Server\\Freigabe), Netzlaufwerke, für alle Konten lesbare Ordner, Systemordner und Laufwerkswurzeln ab, unter Windows auch alles unter C:\\Users, C:\\ProgramData und C:\\Program Files. Tragen Sie unter Windows am besten einen **neuen** Ordnernamen ein: PraxisZeit legt ihn an und gibt ihm die Rechte „nur SYSTEM und Administratoren“. Die Rechte eines bestehenden Ordners ändert PraxisZeit nicht; ist er für andere Konten zugänglich, erscheint ein Hinweis.

> **Achtung:** **Den Schlüssel SECRET\_KEY mitsichern:** Für einen neuen Rechner reicht die Datenbanksicherung nicht. Der Schlüssel (nativ config/.secret-key, Docker SECRET\_KEY in der .env) verschlüsselt die Zwei-Faktor-Geheimnisse und bildet die Prüfsummen des Änderungsprotokolls. Bewahren Sie ihn einmalig, verschlüsselt und **getrennt** von den Sicherungen auf, zum Beispiel im Passwort-Safe der Praxis. Ohne ihn müssen alle die Zwei-Faktor-Anmeldung neu einrichten.

**Wiederherstellen:** Die Oberfläche kann Sicherungen erstellen, laden und löschen, aber nicht einspielen. Das Einspielen geschieht auf dem Server mit einem Kommando. Eingespielt wird nur eine Sicherung mit passender **Signatur**: PraxisZeit signiert jede Sicherung mit dem SECRET\_KEY der Installation. Eine Sicherung einer älteren Version oder vom alten Rechner geht nur mit dem Zusatz --force-unverified, und nur, wenn sie sicher aus der eigenen Praxis stammt. Bei der nativen Installation bricht das Einspielen ab, wenn die Sicherung von einer **neueren** Version stammt oder das Einspielen scheitert; die bisherige Datenbank bleibt dann unverändert.

| Installation | Befehl zum Einspielen |
| --- | --- |
| Docker (neben der docker-compose.yml) | bash restore.sh backups/praxiszeit\_\<zeitstempel\>.sql.gz |
| Linux nativ, 1. Dienst anhalten | sudo systemctl stop praxiszeit |
| Linux nativ, 2. Sicherung einspielen | sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore /opt/praxiszeit/data/backups/\<datei\>.sql.gz |
| Linux nativ, 3. Dienst starten | sudo systemctl start praxiszeit |
| macOS nativ, 1. Dienst anhalten | sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist |
| macOS nativ, 2. Sicherung einspielen (Dienstkonto \_praxiszeit) | sudo -u \_praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore /usr/local/praxiszeit/data/backups/\<datei\>.sql.gz |
| macOS nativ, 3. Dienst starten | sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist |
| Windows nativ (Eingabeaufforderung als Administrator im Installationsordner) | restore-backup.bat data\\backups\\\<datei\>.sql.gz |

> **Gut zu wissen:** **Nach dem Einspielen** startet das Backend neu; erst dieser Start hebt eine Sicherung einer älteren Version per Migration auf den Stand der installierten Version. Nativ unter Linux und macOS muss der Dienst vor dem Einspielen **angehalten** sein, sonst bricht das Kommando ab, ohne etwas anzufassen. Führen Sie es als Dienstkonto aus, nicht als root. Alle Kommandozeilen-Varianten, auch das Sichern ohne Oberfläche, stehen in docs/BACKUP.md.

<a id="schichtplanung"></a>
## Schichtplanung

*Mit der **Schichtplanung** erstellen Sie wöchentliche Einsatzpläne: wer steht wann an welchem Arbeitsplatz. Sie ist ein **reines Planungswerkzeug** und verändert **nicht** Zeiterfassung, Soll und Ist, ArbZG-Prüfungen, Urlaub oder Überstunden. Das Modul ist nach der Installation **aus**; nur Admins können es einschalten, den Schalter beschreibt [Tour und Schichtplanung](#tour-schichtplanung). Erst danach erscheinen die Menüpunkte und die Dashboard-Karte „Deine Einteilung heute“.*

| Begriff | Bedeutung |
| --- | --- |
| Standort | optionale Gruppierung für Arbeitsplätze, zum Beispiel Hauptstelle oder Filiale |
| Arbeitsplatz | ein zu besetzender Platz (Anmeldung, Labor, Springer …) mit Farbe für die Wochenansicht |
| Schichtplan | ein benannter Wochenplan, zum Beispiel „Normalzustand“ oder „Azubis Schulferien“; beliebig viele |
| Zeitslot | ein Arbeitsplatz an einem Wochentag in einem Zeitfenster, mit optionaler Mindestbesetzung |
| Einweisung | für welche Arbeitsplätze eine Person eingewiesen ist |

<a id="schicht-wochentage"></a>
### Wie lege ich die geplanten Wochentage fest?

Bei eingeschalteter Schichtplanung steht unter dem Schalter in den `Einstellungen` der Bereich **Geplante Wochentage**. Standard ist Montag bis Freitag.

![Einstellungen, Bereich Schichtplanung: die Wochentage Montag bis Sonntag als Auswahlfelder mit dem Knopf „Wochentage speichern“](/help/img/pl-schicht-wochentage.webp)

1. Klicken Sie die Wochentage an, die der Schichtplaner anzeigen und planen soll. Samstag, Sonntag oder ein Schließtag lassen sich einzeln zu- und abschalten; **mindestens ein Tag** muss aktiv bleiben.
2. Klicken Sie auf `Wochentage speichern`.

> **Gut zu wissen:** Ein abgeschalteter Tag verschwindet aus der Wochenansicht, nimmt keine neuen Slots auf und wird beim automatischen Füllen übersprungen. Bereits angelegte Slots bleiben erhalten und kehren zurück, sobald Sie den Tag wieder aktivieren.

<a id="schicht-stammdaten"></a>
### Wie lege ich Standorte und Arbeitsplätze an?

Klicken Sie in der Navigation auf `Schichtplanung` und wählen Sie den Reiter `Stammdaten`. Links stehen die **Standorte**, rechts die **Arbeitsplätze**.

![Schichtplanung, Reiter Stammdaten: links die Standorte, rechts die Arbeitsplätze Anmeldung und Labor mit Namensfeld, Farbwähler und Knopf „Hinzufügen“](/help/img/pl-schicht-stammdaten.webp)

1. **Standorte** sind optional: Tragen Sie unter **Neuer Standort** einen Namen ein, zum Beispiel „Hauptstelle“, und bestätigen Sie mit dem Plus-Knopf. Arbeitsplätze können auch ohne Standort („global“) bestehen.
2. **Arbeitsplätze:** Tragen Sie unter **Name** zum Beispiel „Anmeldung“ oder „Labor“ ein; **Standort (optional)** ordnet ihn einem Standort zu.
3. Wählen Sie die **Farbe**, in der der Arbeitsplatz in der Wochenansicht erscheint.
4. Klicken Sie auf `Hinzufügen`. Der Arbeitsplatz erscheint in der Liste darunter.
5. In der Liste ändern Sie einen Eintrag mit dem Stift-Symbol („Bearbeiten“) oder entfernen ihn mit dem Papierkorb („Löschen“).

> **Gut zu wissen:** Löschen geht nur, solange nichts daran hängt: ein Standort nur, wenn kein Arbeitsplatz ihm zugeordnet ist, ein Arbeitsplatz nur, wenn er in keinem Slot verwendet wird.

<a id="schicht-einweisungen"></a>
### Wie halte ich fest, wer für welchen Arbeitsplatz eingewiesen ist?

Wählen Sie in der `Schichtplanung` den Reiter `Einweisungen`. Die Tabelle zeigt die Mitarbeitenden in den Zeilen und die Arbeitsplätze in den Spalten.

![Schichtplanung, Reiter Einweisungen: Tabelle mit den Mitarbeitenden in den Zeilen und den Arbeitsplätzen Anmeldung und Labor in den Spalten, Häkchen bei eingewiesenen Personen](/help/img/pl-schicht-einweisungen.webp)

1. Jede Spalte ist ein **Arbeitsplatz**, hier zum Beispiel „Labor“.
2. Ein **Häkchen** bedeutet: Die Person ist für diesen Arbeitsplatz eingewiesen. Die Änderung wird sofort gespeichert.
3. Ohne Häkchen ist die Person nicht eingewiesen. Ziehen Sie sie trotzdem auf einen Slot dieses Arbeitsplatzes, erscheint die **gelbe Warnung „nicht eingewiesen“**.

> **Gut zu wissen:** Die Warnung blockiert nicht. Sie entscheiden bewusst, zum Beispiel bei einer Einarbeitung unter Aufsicht. Mitarbeitende sehen ihre eigenen Einweisungen im Profil unter „Meine Einweisungen“.

<a id="schicht-plan-bearbeiten"></a>
### Wie lege ich einen Schichtplan an und bearbeite ihn?

Im Reiter `Schichtpläne` steht links die Liste der Pläne, rechts der Editor des gewählten Plans. Die ausklappbare **Jahresübersicht** darüber zeigt als Zeitstrahl, welcher Plan in welchem Zeitraum des Jahres läuft.

![Schichtplanung, Plan „Wochenplan Praxis“: Werkzeugleiste mit Deaktivieren, Slot, Automatisch füllen, Bearbeiten, PDF und Duplizieren, darunter das Wochenraster](/help/img/pl-schicht-editor.webp)

1. Tragen Sie unter **Neuer Plan** einen Namen ein, zum Beispiel „Normalzustand“, und legen Sie den Plan mit dem Plus-Knopf an. Ein Klick auf einen Plan in der Liste öffnet ihn; ein Punkt oder Haken zeigt, ob er aktiv ist.
2. `Aktiv schalten` macht den Plan für alle sichtbar; bei einem aktiven Plan, wie im Bild, heißt der Knopf `Deaktivieren`. **Mehrere Pläne können gleichzeitig aktiv** sein, zum Beispiel einer je Standort.
3. `Bearbeiten` öffnet die Plan-Einstellungen mit Name, Zeitraum und Freigabe, siehe [Plan freigeben](#schicht-plan-einstellungen).
4. `PDF` erzeugt einen Aushang im Querformat mit einer Tabelle Arbeitsplatz × Wochentag, zum Aushängen am Schwarzen Brett.
5. Der Umschalter `Woche` / `Tag` wechselt zwischen der Wochenansicht und einem einzelnen Wochentag in voller Breite; das ist beim Einrichten übersichtlich. Im Raster ziehen Sie einen Slot per Drag \& Drop auf einen anderen Tag oder eine andere Uhrzeit (15-Minuten-Raster); ein Klick auf eine freie Fläche legt einen Slot an, ein Klick auf einen Slot bearbeitet ihn.

> **Gut zu wissen:** Unter dem Raster (bei sehr breitem Fenster daneben) stehen die **Mitarbeitenden**. Ziehen Sie eine Person auf einen Slot, um sie zuzuweisen. Unter jedem Namen zeigt die **Auslastung** die zugewiesenen Schichtstunden zur Wochenarbeitszeit, zum Beispiel „15,25 / 17 h“: grün bei ±30 Minuten, gelb bei ±1 Stunde, sonst rot.

| Weitere Knöpfe der Werkzeugleiste | Wirkung |
| --- | --- |
| `Slot` | legt einen Zeitslot an, siehe [Zeitslot anlegen](#schicht-slot) |
| `Automatisch füllen` | besetzt die Slots selbst, siehe [Automatisch füllen](#schicht-fuellen) |
| `Duplizieren` | kopiert den Plan als Entwurf, siehe den Tipp darunter |
| Papierkorb („Plan löschen“) | löscht den Plan samt Slots und Zuweisungen nach Rückfrage |

> **Gut zu wissen:** **Duplizieren** kopiert einen Plan mit allen Slots und Zuweisungen. Die Kopie ist ein **inaktiver Entwurf** ohne Zeitraum und ohne Freigabe für Mitarbeitende; so leiten Sie Varianten wie „Sommer“ oder „Schulferien“ aus einem Bestandsplan ab. Arbeitsplätze und Einweisungen gehören keinem Plan und werden nicht mitkopiert.

<a id="schicht-slot"></a>
### Wie lege ich einen Zeitslot an?

Klicken Sie im Editor auf `Slot`. Der Dialog **Neuer Zeitslot** öffnet sich; ein vorhandener Slot heißt im Dialog **Zeitslot bearbeiten**.

![Dialog „Neuer Zeitslot“ mit Arbeitsplatz, Wochentag, Von und Bis, Mindestbesetzung, Hinweis und der Liste der zugewiesenen Mitarbeitenden](/help/img/pl-schicht-slot.webp)

1. Wählen Sie den **Arbeitsplatz**.
2. Wählen Sie den **Wochentag**.
3. Tragen Sie **Von** und **Bis** ein.
4. **Mindestbesetzung:** 0 bedeutet keine Mindestbesetzung; sonst markiert PraxisZeit den Slot bei Unterbesetzung. Das ist eine **weiche Warnung**, Speichern und Aktivieren bleiben möglich.
5. **Hinweis (optional):** bis zu 500 Zeichen, zum Beispiel „Einarbeitung Azubi“. Er erscheint mit vorangestelltem **»** im Wochenraster, im PDF-Aushang und auf der Dashboard-Karte „Deine Einteilung heute“.
6. Haken Sie unter **Zugewiesene Mitarbeiter** die Personen an. Wer nicht eingewiesen ist, trägt das Kennzeichen „nicht eingewiesen“. Zum Schluss speichern Sie den Slot mit `Speichern`.

> **Achtung:** **Der Hinweis ist für alle sichtbar:** Alle Mitarbeitenden, die den Plan sehen dürfen, lesen ihn, und der PDF-Aushang druckt ihn mit; ein Schwarzes Brett hängt oft an einem Ort, den auch Patientinnen und Patienten einsehen. Tragen Sie dort **keine Gesundheitsangaben** oder andere sensible Daten ein.

> **Gut zu wissen:** **Slot kopieren:** Beim Bearbeiten eines Slots legt „Auf Wochentage kopieren“ ihn auf weiteren Wochentagen zusätzlich an, mit Arbeitsplatz, Zeit, Mindestbesetzung, Zuweisungen **und Hinweis**. Bei einem personenbezogenen Hinweis wie „Vertretung für Frau Schmidt“ bedenken Sie, dass er mitkopiert wird.

<a id="schicht-fuellen"></a>
### Wie lasse ich einen Plan automatisch füllen?

Klicken Sie im Editor auf `Automatisch füllen`. Der Dialog besetzt die Slots mit eingewiesenen, verfügbaren Mitarbeitenden, ausgewogen nach Auslastung und Überstundenkonto.

![Dialog „Automatisch füllen“ mit der Zielwoche, der Wahl zwischen „Alle Zuweisungen neu verteilen“ und „Nur Lücken auffüllen“ und dem Knopf „Generieren“](/help/img/pl-schicht-fuellen.webp)

1. Wählen Sie die **Zielwoche**. Sie bestimmt, welche Abwesenheiten und Stunden berücksichtigt werden; der Dialog nennt darunter den Montag der Woche.
2. Wählen Sie den **Modus**: „Nur Lücken auffüllen (vorhandene behalten)“ (voreingestellt) oder „Alle Zuweisungen neu verteilen“. Das Neuverteilen löscht die bestehenden Zuweisungen des Plans und fragt vorher nach.
3. Klicken Sie auf `Generieren`. Das Ergebnis ist ein **Entwurf** zum Prüfen; der Plan wird dabei **nicht** aktiviert.

> **Gut zu wissen:** Der Generator liest Abwesenheiten, Wochenstunden und Überstundenkonto nur und verändert daran nichts. Er setzt niemanden ein, der an dem Tag abwesend oder außerhalb seines Beschäftigungsfensters ist, und keine Person auf zwei überlappende Slots. Slots, die sich nicht besetzen lassen, bleiben offen; eine Meldung und die Unterbesetzungs-Markierung sagen es Ihnen.

<a id="schicht-plan-einstellungen"></a>
### Wie gebe ich einen Plan für Mitarbeitende frei?

Klicken Sie im Editor auf `Bearbeiten`. Der Dialog **Plan-Einstellungen** öffnet sich.

![Dialog „Plan-Einstellungen“ mit Name, Beschreibung, dem Zeitraum für die automatische Aktivierung und dem Haken „Für Mitarbeitende sichtbar“](/help/img/pl-schicht-plan-einstellungen.webp)

1. Ändern Sie bei Bedarf den **Namen** und die Beschreibung.
2. **Automatisch aktiv im Zeitraum (optional):** Liegt das heutige Datum zwischen **von** und **bis**, gilt der Plan automatisch als aktiv, zusätzlich zum Knopf „Aktiv schalten“. Eine offene Grenze ist erlaubt.
3. Mit dem Haken **Für Mitarbeitende sichtbar** erscheint der Plan in der Mitarbeiteransicht, auch wenn er heute noch nicht gilt, zum Beispiel um einen ab September geltenden Plan früh bekannt zu machen.
4. Klicken Sie auf `Speichern`.

> **Achtung:** **Falle bei befristeten Plänen:** Die Freigabe gilt in beide Richtungen. Ein befristeter Plan, zum Beispiel ein Sommerplan Juli bis August, bleibt für Mitarbeitende sichtbar, solange der Haken gesetzt ist, auch Wochen nach Ablauf; dort steht er dann mit dem Vermerk „Nicht mehr gültig“. Nehmen Sie die Freigabe selbst zurück. Ein heute aktiver Plan ist ohnehin sichtbar. Eine **Kopie** übernimmt die Freigabe nicht. Welche Pläne freigegeben sind, sehen Sie am Augen-Symbol in der Planliste und am Abzeichen „Sichtbar“ im Kopf des geöffneten Plans.

> **Gut zu wissen:** **PDF-Aushang:** Gilt der gedruckte Plan gerade nicht (Vorschau oder abgelaufen), steht fett in der Kopfzeile „Vorschau — gilt derzeit nicht“ beziehungsweise „Nicht mehr gültig“, damit er am Schwarzen Brett nicht mit dem geltenden Plan verwechselt wird. Haben alle Arbeitsplätze denselben Standort, steht er einmal in der Kopfzeile, sonst hinter dem Namen jedes Arbeitsplatzes. Auch Mitarbeitende können den Plan, den sie sehen, mit dem Knopf „PDF“ drucken. Mitarbeitende sehen ihre heutige Einteilung auf dem Dashboard; ihre Seite beschreibt das Handbuch für Mitarbeitende.

<a id="admin-passwort-verloren"></a>
## Admin-Passwort verloren

*Kommt niemand mehr mit einem Administrator-Konto in die Anwendung, hilft ein Kommando **auf dem Server selbst**. Es setzt das Passwort direkt in der Datenbank neu und braucht dafür **keine Anmeldung**. Dieses Kapitel hat keine Bildschirmfotos, weil es keine Oberfläche dafür gibt: Sie arbeiten in einer Eingabeaufforderung oder einem Terminal auf dem Server.*

<a id="passwort-zuruecksetzen"></a>
### Wie setze ich das Admin-Passwort zurück?

Führen Sie den Befehl für Ihre Installation aus. Die lange Form ist nötig: praxiszeit-server.py liegt nicht im Suchpfad, und die Programmbibliotheken stecken nur im mitgelieferten Python unter bin/python.

1. Öffnen Sie auf dem Server ein Terminal (Windows: Eingabeaufforderung **als Administrator** im Installationsordner).
2. Führen Sie den Befehl aus der Tabelle aus.
3. Geben Sie das neue Passwort zweimal ein. Es wird nicht mit eingetippt, damit es nicht in der Befehls-Historie landet. PraxisZeit prüft dieselben Regeln wie die Anwendung: mindestens 10 Zeichen, Groß- und Kleinbuchstabe, Ziffer.
4. Melden Sie sich mit dem Benutzernamen und dem neuen Passwort an. Alle laufenden Sitzungen dieses Kontos sind danach ungültig; wer damit angemeldet war, muss sich neu anmelden.

| Installation | Befehl |
| --- | --- |
| Linux (Standardordner /opt/praxiszeit) | sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py reset-admin-password |
| macOS (Standardordner /usr/local/praxiszeit, Dienstkonto \_praxiszeit mit Unterstrich) | sudo -u \_praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py reset-admin-password |
| Windows (Installationsordner zum Beispiel C:\\PraxisZeit) | bin\\python\\python.exe praxiszeit-server.py reset-admin-password |
| Docker (neben der docker-compose.yml) | docker compose exec backend python -m app.cli.reset\_admin\_password |

| Option (hinten anhängen) | Wirkung |
| --- | --- |
| \--username \<name\> | setzt das Passwort eines anderen Kontos als admin |
| \--reactivate | ist das Konto **deaktiviert**, genügt ein neues Passwort nicht, die Anmeldung bleibt gesperrt (Meldung „Das Konto ist derzeit deaktiviert und bleibt es auch“); mit dieser Option setzt das Kommando das Passwort neu **und** aktiviert das Konto wieder |
| \--disable-2fa | ist auch das Handy mit der Zwei-Faktor-Anmeldung weg, verlangt der Login nach dem neuen Passwort weiter einen Code; diese Option schaltet die Zwei-Faktor-Anmeldung ab, danach richten Sie im Profil eine neue ein |

> **Gut zu wissen:** **Alles wird protokolliert:** Jeder solche Vorgang wird dauerhaft festgehalten, mit Zeitpunkt, betroffenem Konto und dem Betriebssystem-Konto, das ihn ausgelöst hat (Nachweispflicht nach Art. 5 Abs. 2 DSGVO). Sie finden ihn unter „Konto-Vorgänge“ mit der handelnden Stelle „Kommandozeile (Benutzer@Rechner)“, siehe [Konto-Vorgänge](#konto-vorgaenge). Ein Eingriff von Hand in die Datenbank ist weder nötig noch empfohlen; dabei entfiele die Protokollzeile.

> **Achtung:** **Der Eintrag \[admin\] password in config/praxiszeit.conf ist keine Antwort:** Er ist nur der Startwert der Erstinstallation und wird bei einer späteren Passwortänderung nicht nachgeführt. Nach einem Reset überschreibt ihn das Kommando mit einem Zufallswert. Löschen Sie den Eintrag nicht, die Anwendung setzt das Feld beim Start voraus.

<a id="zwei-faktor-zuruecksetzen"></a>
### Wie setze ich die Zwei-Faktor-Anmeldung einer Mitarbeiterin zurück?

Das geht ohne Kommandozeile: Hat eine Person ihr Handy verloren, setzen Sie die Zwei-Faktor-Anmeldung in der `Benutzerverwaltung` zurück.

1. Klicken Sie in der Zeile der Person auf das Schild-Symbol `Zwei-Faktor zurücksetzen`. Es erscheint nur bei Personen mit aktiver Zwei-Faktor-Anmeldung.
2. Bestätigen Sie mit **Ihrem** Passwort.
3. PraxisZeit schaltet die Zwei-Faktor-Anmeldung der Person ab und meldet sie ab. Sie meldet sich danach nur mit dem Passwort an und richtet Zwei-Faktor im Profil neu ein. Der Vorgang steht unter „Konto-Vorgänge“.

> **Gut zu wissen:** Die **eigene** Zwei-Faktor-Anmeldung setzen Sie so nicht zurück. Das geht im Profil, mit Passwort und Code; ein zweites Admin-Konto kann es für Sie übernehmen.

> **Achtung:** **Vorher prüfen: Ist das Passwort wirklich falsch?** Die Anmeldung geht nur mit dem **Benutzernamen**, nicht mit der E-Mail-Adresse; Passwortmanager tragen gern die E-Mail ein. Nach **5 Fehlversuchen in 15 Minuten von demselben Rechner** sperrt PraxisZeit den Benutzer an diesem Rechner vorübergehend („Konto vorübergehend gesperrt“), an anderen Rechnern geht die Anmeldung weiter; erst nach **50 Fehlversuchen insgesamt** ist der Benutzer überall gesperrt, dann hilft Warten oder ein Neustart des Dienstes. Nach **10 falschen Zwei-Faktor-Codes in einer Stunde** ist die Anmeldung des Kontos für eine Stunde gesperrt; dann ist das Passwort bekannt geworden, ändern Sie es. Welcher Fall vorliegt, steht im Protokoll des Servers: AUTH login\_failed user=\<name\> reason=bad\_password heißt Passwort falsch, reason=unknown\_user heißt Benutzername unbekannt **oder Konto deaktiviert**, dann hilft --reactivate.
