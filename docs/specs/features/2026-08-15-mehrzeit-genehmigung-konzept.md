# Mehrzeit: Begründung und Anerkennung — arbeitszeitrechtliches Konzept

**Stand:** 15.08.2026 · **Status:** Konzept, nicht implementiert · **Bezug:** erweitert #201 (Arbeitszeit-Fenster)

> **Keine Rechtsberatung.** Dieses Dokument ist eine technische Entscheidungsgrundlage. Es nennt Normen und
> Rechtsprechung, damit die Entwicklung an den richtigen Stellen konservativ baut — es ersetzt keine
> anwaltliche Prüfung. Die Punkte in [Abschnitt 10](#10-punkte-für-den-fachanwalt) gehören vor dem Rollout
> zu einer Fachanwältin oder einem Fachanwalt für Arbeitsrecht. Rechtsstand: 15.08.2026.

---

## 1. Die Vorgabe

> „Der Admin kann dieses Feature an/ausschalten und das Eingabefeld verpflichtend oder optional machen. In
> den Optionen kann der Admin auch eine Toleranzzeit eintragen, die jeder MA dann ohne Genehmigung länger
> arbeiten darf. Die Arbeitszeit eines Mitarbeiters ist nach Plan 6 h. Der MA bleibt aber 7 h da. Dann wird
> die Arbeitszeit auf die vereinbarte Arbeitszeit gekürzt, aber der MA kann einen Grund für die längere
> Arbeitszeit eintragen (oder der Admin kann es ohne Antrag genehmigen) — genehmigt der Admin den Grund,
> wird die tatsächliche Arbeitszeit des MA verwendet. Genehmigt der Admin nicht, wird nur die vereinbarte
> Arbeitszeit gezählt."

## 2. Das Ergebnis in fünf Sätzen

Die Grundidee ist zulässig, aber nur in einem schmalen Korridor. Zulässig ist, dass ein Zeit**konto** eine
Obergrenze hat und nicht anerkannte Mehrzeit dort nicht gutgeschrieben wird — das Bundesarbeitsgericht hat
eine solche Kappungsregelung ausdrücklich gebilligt und im selben Atemzug klargestellt: „Die Pflicht zur
Vergütung geleisteter Arbeit bleibt hiervon unberührt" (BAG 10.12.2013 – 1 ABR 40/12). Unzulässig ist
dagegen alles, was so wirkt, als hätte die Arbeit nicht stattgefunden: die **Aufzeichnung** muss immer die
tatsächliche Zeit zeigen, und beim **Mindestlohn** kann eine geleistete Stunde nicht „abgelehnt" werden
(§ 3 MiLoG). Entscheidend für die Praxis ist außerdem, dass die Ablehnung im Streitfall nichts wert ist,
wenn sie nur aus einem Klick besteht — genau daran ist ein Arbeitgeber am 12.02.2025 vor dem BAG
gescheitert (5 AZR 51/24).

**Der tragende Kunstgriff:** drei Größen statt einer Zahl — *tatsächliche Zeit* (Nachweis, immer
vollständig), *angerechnete Zeit* (Konto/Saldo, darf gekappt sein), *Mehrzeit* (die Differenz, mit eigenem
Status). Genau diese Trennung existiert im Datenmodell seit #201 bereits in Ansätzen (`raw_start_time` /
`raw_end_time`); das Feature ist ihre Fortsetzung, nicht ihr Bruch.

---

## 3. Was von der Vorgabe unverändert trägt

| Vorgabe | Bewertung |
|---|---|
| Feature an-/abschaltbar (Tenant-Setting, Default aus) | trägt |
| Toleranzzeit, die ohne Genehmigung „länger gearbeitet werden darf" | trägt — in der Lesart „genehmigungsfreie Schwelle": die Zeit wird **angerechnet**, nur ohne Antrag |
| Begründungsfeld verpflichtend oder optional | trägt, aber nur für den **Mitarbeiter**-Antrag (siehe 6.2) |
| Admin kann ohne Antrag anerkennen | trägt, ist rechtlich sogar der sauberste Pfad („nachträgliche Billigung") |
| Anerkannt → tatsächliche Zeit wird verwendet | trägt unverändert |
| Nicht anerkannt → nur die vereinbarte Zeit zählt | trägt **nur** im Kernfall: Mitarbeiter bleibt aus eigenem Antrieb ohne betrieblichen Anlass |

Zum letzten Punkt der Satz, auf den es ankommt: *„Der Arbeitgeber muss sich Leistung und Vergütung von
Überstunden nicht aufdrängen lassen"* (BAG 12.02.2025 – 5 AZR 51/24, Rn. 17). Bloße Anwesenheit begründet
keine Vermutung, dass die Mehrarbeit nötig war (BAG 10.04.2013 – 5 AZR 122/12). In diesem Kernfall ist die
Nichtanerkennung rechtlich tragfähig.

---

## 4. Was so nicht gebaut werden darf

### 4.1 „Nicht genehmigt = die Stunde hat es nie gegeben"

Mehrarbeit wird dem Arbeitgeber auf **vier gleichrangigen** Wegen zugerechnet: angeordnet, gebilligt,
geduldet — **oder zur Erledigung der geschuldeten Arbeit notwendig** (BAG 10.04.2013 – 5 AZR 122/12;
bestätigt BAG 04.05.2022 – 5 AZR 359/21). Die Genehmigung im Programm deckt nur den zweiten Weg ab.

> **Für den Praxisbetreiber:** Ihre Genehmigung ist einer von vier Wegen. War die Mehrzeit angeordnet, haben
> Sie sie monatelang hingenommen, oder war sie schlicht nötig, um die von Ihnen einbestellten Patienten zu
> versorgen — dann ist sie zu vergüten, unabhängig davon, was Sie im Programm anklicken. Der Klick
> entscheidet, ob die Zeit auf dem Zeitkonto landet. Er entscheidet nicht, ob sie stattgefunden hat.

**Folge fürs Produkt:** durchgängig „**anerkannt / nicht anerkannt**", nie „entstanden / verfallen".
Die tatsächliche Zeit bleibt in jeder Ansicht und in jedem Beleg sichtbar.

### 4.2 Kappung vor den ArbZG-Prüfungen — **Bestandsdefekt, blockierend**

`backend/app/routers/time_entries.py:640` kappt heute ausdrücklich *vor* den §-3-/§-4-Prüfungen („so that
compliance is assessed on the credited time, not on the raw input"). Nur § 5 rechnet korrekt gegen die
Rohstempel (`rest_time_service.py`).

Das Beispiel des Auftraggebers ist genau der kritische Fall: Plan 6 h, tatsächlich 7 h anwesend. Damit ist
die Sechs-Stunden-Schwelle des § 4 ArbZG überschritten und eine 30-Minuten-Pause zwingend. Kappt die
Software vorher weg, prüft sie die Pause gegen 6 h und meldet nichts — der Verstoß ist trotzdem passiert,
nur unsichtbar. Bußgeldrahmen § 22 ArbZG: bis 30.000 €.

**Regel:** §§ 3, 4, 5 ArbZG rechnen gegen die **tatsächliche** Zeit. Die Kappung wirkt ausschließlich auf
der Anrechnungsseite und darf keine Warnung unterdrücken. (Die *harte* Ablehnung eines Eintrags bleibt
pfadabhängig — `clock_out` verzichtet bewusst auf 422, sonst hängt der offene Eintrag.)

### 4.3 Nachweise ohne die tatsächliche Zeit — **Bestandsdefekt, blockierend**

`raw_start_time`/`raw_end_time` kommen in `export_service.py`, `ods_export_service.py`, `journal_service.py`
und `reports.py` **nicht vor** — nur in den DSGVO-Pfaden. Also gerade nicht in den Dokumenten, die
ausgedruckt und vorgelegt werden.

> **Für den Praxisbetreiber:** Sobald bei Ihnen auch nur eine Minijobberin arbeitet, müssen Sie deren
> tatsächliche tägliche Arbeitszeit aufzeichnen (§ 17 Abs. 1 MiLoG) — branchenunabhängig, kontrolliert vom
> Zoll, Bußgeldrahmen bis 50.000 € (§ 21 Abs. 1 Nr. 8 i. V. m. Abs. 3 MiLoG; der Tatbestand erfasst
> ausdrücklich „nicht richtig" und „nicht vollständig"). Ein Ausdruck mit nur der gekürzten Zeit ist keine
> richtige Aufzeichnung, auch wenn die echten Zeiten in der Datenbank stehen. Vorgelegt wird das Dokument,
> nicht die Datenbank.

**Folge:** Rohzeit-Spalten in allen Belegen (anhängen, nie einschieben — bestehende #415-Regel) plus ein
eigener Export „Arbeitszeitaufzeichnung (§ 17 MiLoG)": Datum, Beginn, Ende, Dauer, jeweils tatsächlich,
ohne Wertung, ohne Freitexte. Keinen „Kurzexport" ohne Rohzeit anbieten — genau der würde sonst vorgelegt.

### 4.4 Rohzeit nur bei Kappung speichern

`clamp()` setzt `raw_*` heute nur, wenn tatsächlich gekappt wurde. Ein Verfahren, das an der echten Zeit
hängt, braucht die echte Zeit aber immer — auch an Tagen ohne Kappung und solange eine Entscheidung
aussteht. **Semantikwechsel:** `raw_*` immer setzen (Migration mit Backfill).

⚠️ `raw_* IS NOT NULL` ist heute das Flag „wurde gekappt" (die `EARLY_START`-Warnung in `clock_in` hängt
daran, die DSGVO-Exporte dokumentieren es). Der Semantikwechsel braucht deshalb ein **eigenes**
Kappungs-Kennzeichen, sonst feuert die Warnung künftig bei jedem Einstempeln.

### 4.5 Toleranzzeit als „bis X Minuten täglich unbezahlt"

30 Minuten täglich sind rund 11 Stunden im Monat. Tauchen die dauerhaft weder auf dem Konto noch auf der
Abrechnung auf, ist das eine pauschale Überstundenabgeltung — und die ist nur wirksam, wenn sie mit klarer
Obergrenze im **Arbeitsvertrag** steht (§ 307 Abs. 1 S. 2 BGB; BAG 01.09.2010 – 5 AZR 517/09: „erforderliche
Überstunden … abgegolten" ist intransparent und unwirksam, ohne geltungserhaltende Reduktion). Ein
Zahlenfeld im Programm ist kein Vertrag. Beim Mindestlohn ist eine solche Pauschale ohnehin unwirksam
(§ 3 MiLoG).

**Folge:** Toleranz ausschließlich als genehmigungsfreie Schwelle — die Zeit wird **angerechnet**, nur ohne
Antrag. Harte Feldobergrenze, Monatsdeckel, kein Default „unbegrenzt".

### 4.6 Ablehnen per Klick ohne Begründung

Der präzise Treffer für dieses Feature. Dem BAG lag am 12.02.2025 eine Betriebsvereinbarung vor, die
technisch genau diesen Mechanismus abbildete: automatische Kürzung der erfassten Zeit, Anrechnung nur „nach
entsprechender Begründung des Beschäftigten und Bestätigung des Vorgesetzten". Tragender Satz (Rn. 15):

> „Der automatische Abzug von Pausenzeiten ersetzt nicht den Tatsachenvortrag zur Gewährung und
> Inanspruchnahme der Pausen."

Und weiter: ein Bestreiten mit Nichtwissen genügt nicht, weil der Arbeitgeber weiß, „welche Aufgaben sie der
Klägerin in Ausübung ihres Weisungsrechts (§ 106 GewO) zu welchen Zeiten … zugewiesen hat". Folge dort:
§ 138 Abs. 3 ZPO, die vorgetragenen Zeiten galten als zugestanden.

**Wichtige Einordnung, damit die Lehre nicht überzogen wird:** das BAG hat den Fall an das LAG
zurückverwiesen, nicht zulasten des Arbeitgebers durchentschieden; die Darlegungslast für die Veranlassung
bleibt beim Arbeitnehmer. Die Lehre lautet nicht „der Mechanismus ist verboten", sondern **„er trägt den
Prozess nicht"**.

**Folge:** Pflicht-Begründungsfeld bei **Ablehnung** — inhaltlich auf den vom Mitarbeiter genannten Grund
antwortend. „Nicht vorab genehmigt" ist prozessual wertlos. Die Begründungspflicht des Arbeitgebers ist
härter als die des Mitarbeiters und **nicht** abschaltbar.

### 4.7 Stille Ablehnung, Auto-Ablehnung, Verfall nach Frist

Duldung heißt: Kenntnis + keine Vorkehrungen, die Mehrarbeit künftig unterbinden. Eine Systemfrist kann
keinen materiellen Anspruch abschneiden; Ausschlussfristen sind nur vertraglich möglich, mindestens drei
Monate, höchstens Textform (§ 309 Nr. 13 lit. b BGB) und müssen den Mindestlohn ausnehmen, sonst insgesamt
unwirksam (BAG 18.09.2018 – 9 AZR 162/18).

**Folge:** Es gibt **keine** automatische Ablehnung — in keiner Konfiguration. Nach Fristablauf schließt
sich nur der Selbstservice des Mitarbeiters; der Vorgang bleibt offen und über den Änderungsantrag
korrigierbar. Eine automatische **Anerkennung** nach N Tagen ist dagegen zulässig und senkt das
Duldungsrisiko — als opt-in.

### 4.8 Stille Rücknahme einer Anerkennung

Ein vorbehaltlos ausgewiesenes Guthaben stellt den Saldo streitlos; der Arbeitgeber darf das Konto nicht
eigenmächtig korrigieren (BAG 23.09.2015 – 5 AZR 767/13; Wiedergutschrift gestrichener Stunden: BAG
21.03.2012 – 5 AZR 676/11). Rücknahme daher nur als neuer, auditierter Vorgang mit Pflichtbegründung.

### 4.9 Der stille Null-Stunden-Kollaps (Bestand)

Liegt ein Eintrag komplett außerhalb des Fensters, liefert `clamp()` heute 0 angerechnete Stunden — ohne
dass jemand davon erfährt. Notfall am Abend, Vertretung außerhalb der eigenen Sprechzeit, Fortbildung nach
Dienstschluss: das sind genau die Fälle, für die das Verfahren gebaut wird. Künftig muss dieser Pfad
zwingend einen **offenen Vorgang über die volle Dauer** erzeugen.

### 4.10 Produkttexte

Die Aufzeichnungspflicht hat „in der Regel arbeitsschutzrechtliche und nicht vergütungsrechtliche
Bedeutung" (BAG 12.02.2025 – 5 AZR 51/24, Rn. 25). Wer im Handbuch schreibt „genehmigte Stunden werden
ausgezahlt, abgelehnte verfallen", stellt selbst die Verbindung zwischen Zeiterfassung und Lohn her, die das
Gesetz nicht verlangt — und die im Streitfall gegen ihn wirkt. Vermarktung als **Steuerungswerkzeug**
(„Mehrarbeit sichtbar machen und steuern"), nicht als Sparinstrument. Kein „rechtssicher"-Claim, keine
Musterklauseln im Produkt (Rechtsdienstleistungsgesetz).

---

## 5. Die konstitutive Entscheidung: Dauer oder Uhrzeit?

Die Vorgabe sagt „auf die **vereinbarte Arbeitszeit** gekürzt" — das ist eine **Dauer**. #201 kappt aber
**Uhrzeiten** (`start < Soll-Beginn − Puffer`, `end > Soll-Ende + Puffer`). Das ist nicht dasselbe, und ohne
Entscheidung bleibt jede weitere Zeile unterbestimmt:

- Die `scheduled_*`-Felder sind **opt-in und nullable**. Eine Praxis, die nur Wochenstunden/Tagesplan
  pflegt — der Normalfall —, schaltet das Feature ein, und es passiert nie etwas.
- Fenster 08:00–15:00 = 7 h brutto; Tagessoll aus den Wochenstunden = 6 h netto; dazwischen liegt die Pause.
  Zwei Soll-Begriffe, zwei Wahrheiten.
- Das Tagessoll ist seit #431 **datumsaufgelöst und historisiert**, das Fenster nicht.

**Empfehlung: dauerbasiert.** Mehrzeit = tatsächlich geleistete Zeit − Tagessoll des Tages, aufgelöst über
den vorhandenen `Schedule`-Snapshot (`calculation_service.get_schedule_for_date`). Das entspricht dem
Wortlaut der Vorgabe, funktioniert für **jeden** Mitarbeitenden ohne zusätzliche Pflege, und es hängt an der
einzigen Soll-Größe, die im Produkt historisiert ist.

Das Fenster (#201) bleibt daneben bestehen — als **eigener**, optionaler Zweck („Anwesenheit außerhalb der
Sprechzeit"), der ebenfalls einen Vorgang erzeugt. Die Reihenfolge ist festzuschreiben: erst Fenster-Kappung
(falls Fenster gepflegt), dann Pausenabzug, dann Dauer-Vergleich gegen das Tagessoll, dann Toleranz.

⚠️ **Die Toleranzen addieren sich.** Zeit bis `Soll-Ende + work_window_grace_minutes` (Default 15) wird heute
gar nicht gekappt. Die genehmigungsfreie Schwelle ist faktisch `Grace + Toleranz`. Beide Zahlen bleiben
getrennt (zwei Zwecke), müssen in der Oberfläche aber gemeinsam ausgewiesen werden, sonst konfiguriert
niemand richtig.

---

## 6. Das Verfahren

### 6.1 Zustände

| Status | Bedeutung | Angerechnet |
|---|---|---|
| `auto_tolerance` | Mehrzeit ≤ Toleranz | volle Zeit, ohne Antrag |
| `open` | **Default** — Mehrzeit > Toleranz, noch keine Entscheidung | Tagessoll + Toleranz |
| `submitted` | Mitarbeiter hat einen Grund eingetragen | unverändert |
| `recognized` | anerkannt, ganz oder teilweise (`recognized_minutes`) | Tagessoll + anerkannte Minuten |
| `not_recognized` | begründet abgelehnt, dem Mitarbeiter zugegangen | Tagessoll + Toleranz |
| `ordered` | angeordneter Anteil | vorbelegt anerkannt, nicht ablehnbar |
| `void` | Trägereintrag korrigiert/gelöscht | — |

**Teilanerkennung ist Pflicht, nicht Kür.** Der Regelfall lautet: 30 Minuten angeordnet, 90 Minuten
geblieben. Eine Ja/Nein-Entscheidung zwingt zu „zu viel" oder „zu wenig" — beides erzeugt Streit.

### 6.2 Wer darf was

| Übergang | Wer | Bedingung |
|---|---|---|
| → `auto_tolerance` / `open` | System | Toleranz (Tag **und** Monatsdeckel) gerissen oder nicht |
| `open` → `submitted` | Mitarbeiter | strukturierter Grund + optionaler Freitext (Freitext Pflicht nur bei entsprechender Einstellung) |
| `open`/`submitted` → `recognized` | Admin | jederzeit, auch ohne Antrag; Begründung optional |
| `submitted` → `not_recognized` | Admin | **nur mit Pflichttext**, der auf den genannten Grund antwortet |
| `open` → `not_recognized` | Admin | zulässig, aber mit Warnung („der Mitarbeiter hatte keine Gelegenheit zur Begründung") |
| Entscheidung revidieren | Admin | nur als **neuer** Vorgang mit Pflichtbegründung; der alte bleibt in der Historie |

**Warum `open` der Default ist:** `not_recognized` als Default wäre eine automatische Ablehnung ohne
Tatsachengrundlage — genau das, was das BAG prozessual entwertet. `recognized` als Default höbe die
Steuerungsfunktion auf. `open` ist zusätzlich der einzige Zustand, der Sichtbarkeit erzwingt — und
Sichtbarkeit ist das, was der Betrieb braucht, um zu reagieren (Terminvergabe, Personaldecke).

### 6.3 Fristen und Zustellung

- `overtime_reason_deadline_days` (Default 7 — bewusst innerhalb der 7-Tage-Frist des § 17 MiLoG) schließt
  **nur** den Selbstservice. Der Vorgang bleibt offen.
- Eskalation statt Verfall: Badge im Admin-Dashboard, Zählung im Monatsabschluss.
- Optional (opt-in): automatische **Anerkennung** nach N Tagen ohne Entscheidung.
- Jede Entscheidung — auch die Anerkennung — geht dem Mitarbeiter nachweislich zu und wird protokolliert.
  Eine Entscheidung, die ihn nie erreicht, belegt im Streitfall das Gegenteil dessen, was sie soll.
- Nach der Ablehnung braucht der Mitarbeiter einen **dokumentierten Widerspruch**. Der nützt beiden Seiten:
  er beendet die Duldungslage und markiert den Zeitpunkt, ab dem gestritten wird.

### 6.4 Was der Mitarbeiter sieht

Tagesansicht und Journal zeigen **beide** Werte plus Differenz:
`08:00–15:00 erfasst · 6:00 h angerechnet · 1:00 h Mehrzeit — offen`.

Der Schwebezustand muss überall als „offen/vorbehaltlich" gekennzeichnet sein. Wird die Mehrzeit vorher
unmarkiert als Guthaben angezeigt, kann bereits diese Anzeige als vorbehaltlose Ausweisung — und damit als
Billigung — gewertet werden (BAG 23.09.2015 – 5 AZR 767/13). Ein UI-Detail mit materieller Wirkung.

---

## 7. Hart verdrahtete Sonderfälle

| Fall | Verdrahtung |
|---|---|
| **Minijob / § 17 MiLoG** | Kappung per Default **aus**. Rohzeit in jedem Beleg. Warnung, wenn ein Vorgang älter als 7 Kalendertage offen ist. Harte Warnung, wenn eine Nichtanerkennung den effektiven Stundenlohn (Entgelt ÷ tatsächliche Stunden) unter den Mindestlohn drückt — `app/core/minimum_wage.py` liegt vor. § 3 MiLoG ist unabdingbar: hier gibt es keine Konfiguration. |
| **Angeordnete Mehrarbeit** | Kennzeichen `ordered` mit Minutenbetrag, als anerkannt vorbelegt, nicht ablehnbar. Kein Voll-Lock des Vorgangs. |
| **Notfall / betriebliche Veranlassung** | Strukturierte Gründe (`notfall`, `patient_ueberzogen`, `personalausfall`, `dokumentation`, `angeordnet`, `umkleide_ruestzeit`, `sonstiges`). Bei `notfall`/`angeordnet` Vorbelegung „anerkannt". § 14 ArbZG lockert nur Arbeitsschutzgrenzen, nicht die Vergütung. |
| **ArbZG-Verstoß in der Rohzeit** | §§ 3, 4, 5 gegen die tatsächliche Zeit; Warnung dauerhaft und **nicht** unterdrückbar; das 10-h-Limit nicht durch Kappung erfüllbar. |
| **Personen mit gesetzlichen Höchstgrenzen** | Schwangere/Stillende (§ 4 MuSchG: keine Mehrarbeit über die vereinbarte Zeit hinaus), Jugendliche (§ 8 JArbSchG 8 h; § 11: **60 min** Pause über 6 h — doppelt so viel wie § 4 ArbZG; § 13: 12 h Freizeit), schwerbehinderte Menschen (§ 207 SGB IX: Freistellung von Mehrarbeit über 8 h auf Verlangen, ohne Zustimmung des Arbeitgebers). Dort ist Mehrzeit **nicht genehmigungsfähig, sondern verboten** — ein „Anerkennen"-Button dokumentiert den Verstoß, statt ihn zu heilen. **Umsetzung ohne Gesundheitsdaten:** neutrales Kennzeichen am Nutzer („Mehrarbeit ausgeschlossen" / „nur mit ausdrücklicher Zustimmung") ohne Angabe des Grundes, plus verschärfte Pausen-/Höchstzeitprüfung. Kein Feld „schwanger", kein Feld „schwerbehindert" — das wären Art.-9-Daten in einem System, das dafür nicht gebaut ist. |
| **`track_hours=False`** (leitende Angestellte) | Kein Vorgang, keine Kappung — **aber** Rohzeit dokumentieren und exportieren. Heute überspringt `clamp()` diese Nutzer komplett, es werden also gar keine `raw_*` gesetzt: eigener Arbeitsschritt, kein „bleibt wie im Bestand". |
| **Wochenende** | `clamp()` kennt nur Mo–Fr → am Samstag wird **nie** gekappt. Samstagssprechstunde ist in Praxen Standard und der Tag, an dem am ehesten überzogen wird. Entweder Wochenendfenster nachziehen oder die Grenze ausdrücklich dokumentieren. |
| **Feiertag** | Das Tagessoll ist 0 → „Kürzung auf die vereinbarte Zeit" ergäbe konsequent 0 h für einen ganzen gearbeiteten Feiertag. Regel: Feiertagsarbeit ist vollständig Mehrzeit (nie stille Nullstellung). Dazu § 11 Abs. 3 ArbZG (Ersatzruhetag). |
| **Halbe Tage** | Halbtags-Urlaub und Halbtags-Sondertage (24./31.12.) halbieren das Tagessoll — bei dauerbasierter Auslegung muss der Faktor in die Mehrzeit-Rechnung (`half_special_day_weight` existiert). |
| **Trägereintrag verschwindet** | Löscht eine nachträgliche Urlaubs-/Krankbuchung den `TimeEntry`, darf der schwebende Vorgang nicht still verschwinden: Zustellung + Historie wie bei jeder anderen Entscheidung. |
| **Austritt** | Vor `last_work_day` müssen offene Vorgänge entschieden sein. Ein Schwebezustand auf einem Konto, das die Person nicht mehr einsehen kann, ist der schlechteste denkbare Ort. |
| **Abgerechnete Zeiträume** | Änderungen an abgeschlossenen Monaten/Jahren nur mit Warnung, nie automatische Neuberechnung (analog `stale_year_closing_warning`). |

---

## 8. Einstellungen — und ihre Grenzen

**Einstellbar** (Tenant-Settings, jeweils die drei bekannten Sync-Flächen):

| Setting | Typ | Default |
|---|---|---|
| `overtime_approval_enabled` | bool | **false** |
| `overtime_reason_required` | bool | false (betrifft nur den Mitarbeiter-Antrag) |
| `overtime_tolerance_minutes_day` | int 0–60 | 0 |
| `overtime_tolerance_minutes_month` | int | 0 (aus) |
| `overtime_tolerance_prorata_parttime` | bool | false (§ 4 Abs. 1 TzBfG) |
| `overtime_reason_deadline_days` | int 1–31 | 7 |
| `overtime_auto_recognize_after_days` | int | 0 (aus) |
| pro Mitarbeiter abschaltbar | bool | für Minijob **aus** |

**Nicht verstellbar:**

1. Erfassung, Speicherung und Export der tatsächlichen Zeit — kein „Kurzexport" ohne Rohzeit.
2. Keine Auto-Ablehnung, kein Verfall, keine Löschung eines Vorgangs.
3. Ablehnungsbegründung immer Pflicht — unabhängig von `overtime_reason_required`.
4. ArbZG-Warnungen auf Rohzeitbasis nicht unterdrückbar; 10-h-Grenze nicht konfigurierbar.
5. Toleranz nie unbegrenzt; harte Feldobergrenze.
6. Keine rückwirkende Kappung entschiedener Vorgänge, keine stille Rücknahme.
7. Mindestlohn-Sonderregeln nicht editierbar.
8. Feature nie Default-an, auch nicht beim Update von Bestandsinstallationen.
9. Zustellung der Entscheidung nicht abschaltbar.

**Governance** (fehlt im Rollenmodell und muss mitgebaut werden): keine Selbstgenehmigung (ein Admin, der
zugleich Mitarbeiter ist, ist der Normalfall), Vertretungsregelung für die Einzelpraxis mit genau einem
Admin, und Kennzeichnung von Eingaben, die unter Impersonation (#370) entstanden sind — sonst ist eine
„Mitarbeiterbegründung" im Nachhinein nicht von einer Admin-Eingabe zu unterscheiden.

---

## 9. Was außerhalb der Software passieren muss

1. **Vertragliche Grundlage.** Ohne Betriebsrat bleibt der Arbeitsvertrag. Eine einseitige Weisung (§ 106
   GewO) trägt die Kappung nicht, soweit sie Zeitguthaben reduziert. Geregelt gehören: Genehmigungsvorbehalt,
   Toleranz **mit Zahl**, Verfahren, Fristen. Das Programm setzt die Regelung um, es ersetzt sie nicht.
2. **Nachweisgesetz.** § 2 Abs. 1 NachwG verlangt die Angaben zur vereinbarten Arbeitszeit und — sofern
   vereinbart — zur Möglichkeit der Anordnung von Überstunden samt Voraussetzungen. Toleranz und Verfahren
   *sind* diese Voraussetzungen. Verstoß ist Ordnungswidrigkeit.
3. **Beschäftigte informieren:** was die Kappung bedeutet, wie man begründet, bis wann, wer entscheidet. Ein
   Begründungsschritt, den niemand kennt, ist im Streitfall wertlos.
4. **Betriebsrat**, falls vorhanden: Einführung **und** Parametrierung sind nach § 87 Abs. 1 Nr. 2 und Nr. 6
   BetrVG mitbestimmungspflichtig.
5. **Tarifbindung prüfen** (MFA-Manteltarifvertrag, siehe 10.3).
6. **Organisatorisch handeln, nicht nur ablehnen.** Wer dieselbe Überschreitung Monat für Monat ablehnt und
   sonst nichts ändert, sammelt Belege gegen sich selbst.
7. **Datenschutz:** Verarbeitungsverzeichnis ergänzen, Rechtsgrundlage für die Begründungstexte klären,
   Löschfristen festlegen. Die mitgelieferte DSFA behauptet heute „keine automatisierten Entscheidungen mit
   Rechtswirkung" und stützt sich auf § 26 Abs. 1 BDSG — beides muss überarbeitet werden (BAG 08.05.2025 –
   8 AZR 209/21: „§ 26 Abs. 1 BDSG hat unangewendet zu bleiben").
8. **§ 203 StGB:** Der reale Freitext lautet „Notfall Frau M., Reanimation bis 18:40" — Patientendaten
   Dritter unter ärztlicher Schweigepflicht, in einem Feld, das sonst in Exporte wandert. Deshalb:
   strukturierte Gründe als Default, Warnhinweis am Feld, Freitext **nie** im § 17-MiLoG-Export.

---

## 10. Punkte für den Fachanwalt

1. **Wirksame Vertragsklausel** für Kappung, Toleranz und Genehmigungsvorbehalt. Eine BAG-Entscheidung, die
   genau einen Genehmigungsvorbehalt mit Verfallfolge prüft, wurde nicht gefunden; die Übertragung aus der
   Pauschalabgeltungs-Rechtsprechung ist eine begründete Analogie, keine gesicherte Rechtslage.
2. **Ab wann kippt eine Ablehnungsserie in Duldung?** Offen und in Spannung zu 5 AZR 51/24 Rn. 37 (allein die
   Erkennbarkeit im Zeiterfassungssystem begründet keine Billigung).
3. **MFA-Manteltarifvertrag** (Fassung ab 01.01.2025): Bindung ohne Verbandsmitgliedschaft, Zuschlagspflicht
   bei Teilzeit-Mehrarbeit, Länge des Ausgleichsfensters. **Höchste Priorität** — trifft den Beispielfall
   unmittelbar. Eine Allgemeinverbindlicherklärung ließ sich **nicht** belegen; die Bindung dürfte über
   Verbandsmitgliedschaft oder arbeitsvertragliche Bezugnahme laufen. Status: **nicht verifiziert**.
4. **§ 5 Abs. 2 ArbZG:** Ist eine Arztpraxis eine „andere Einrichtung zur Behandlung, Pflege und Betreuung
   von Personen"? Falls ja, gilt eine andere Ruhezeit-Systematik als die heute pauschal geprüften 11 h.
5. **§ 4 Abs. 1 TzBfG:** Darf die Toleranz in absoluten Minuten definiert werden, oder benachteiligt das
   Teilzeitkräfte proportional?
6. **Vollständige Nichtanrechnung** (Eintrag ganz außerhalb des Fensters): vertraglich überhaupt abbildbar?
7. **JArbSchG** bei minderjährigen Auszubildenden — in Praxen Regelfall; das Produkt kennt bis heute kein
   Geburtsdatum.
8. **Rücknahme einer Anerkennung nach erfolgter Lohnabrechnung:** Weg, Frist, Form.
9. **ArbZG-Novelle** (Referentenentwurf, am 18.06.2026 bekannt geworden — **Primärtext nicht eingesehen**,
   Angaben aus Sekundärquellen): berichtet werden ein Wechsel auf die Wochenhöchstarbeitszeit, elektronische
   Aufzeichnung am Tag der Arbeitsleistung und eine Ausnahme für Betriebe bis 10 Beschäftigte. Alle drei
   Punkte sind Architekturfragen, nicht Fußnoten: eine tagesbasierte Toleranz stünde auf der falschen Achse,
   und die taggleiche Aufzeichnung hebt Punkt 4.4 von „wäre gut" auf „ist Voraussetzung".
10. **RDG-Grenze:** Wie weit dürfen Handbuch, In-App-Hilfe und Website Aussagen zur Rechtslage treffen?

---

## 11. Umsetzungsreihenfolge

Die beiden Bestandsdefekte sind **Voraussetzung, nicht Nachlauf** — das Feature vergrößert sie sonst um
genau die Toleranzzeit.

1. **Rohzeit immer setzen** (Migration + Backfill + alle Schreibpfade), eigenes Kappungs-Kennzeichen,
   Invariantentests.
2. **§§ 3/4 gegen die Rohzeit** — zuerst als Warnung, angekündigt: bei Bestandskunden leuchten damit Tage
   auf, die seit Monaten grün waren. Ohne Erklärtext wird das als Regression gemeldet und die Warnung landet
   dauerhaft auf der Ignorierliste.
3. **Rohzeit in alle Nachweisflächen** + eigener § 17-MiLoG-Export; zuerst für Minijob-Nutzer.
4. **Pausen-Doppelabzug beheben:** `net_hours` zieht die Pause von der bereits gekappten Dauer ab. Pausen
   müssen auf das angerechnete Intervall abgebildet werden (Schnittmenge), sonst wird zweimal bestraft.
5. **Glossar und Begriffe** festschreiben, bevor die Felder in die fünf Doku-Sync-Flächen wandern.
6. **Vorgangsmodell + Zustandsmaschine**, inklusive Zustellung, Widerspruch und Audit-Anbindung. Neue
   Tabelle heißt: `tenant_id` + RLS + F-026, `purge_user`-Anschluss (Art. 17), Aufbewahrungs-Gate,
   Anonymisierungs-Scrub für die Freitexte, DSGVO-Exporte, Backup/Restore.
7. **Toleranz, Sonderfälle, Einstellungen, Governance.**
8. **Rollout:** Stichtag statt rückwirkender Vorgangserzeugung, plus einmaliger Report „Altkappungen".
   Der XLS-Import darf beim Nachimport historischer Daten keine Lawine offener Vorgänge mit abgelaufenen
   Fristen erzeugen.
9. **Handbuch, In-App-Hilfe, Aktivierungshinweis** — mit datiertem Rechtsstand-Feld.

### Offene technische Baustellen, die das Feature erbt

- **Mitternacht/Zeitumstellung:** `net_hours` rechnet `end − start` und floort auf 0 — ein Eintrag über
  Mitternacht ergibt 0 Stunden. Für Notdienst/Bereitschaft ist die Kette nicht tragfähig.
- **`scheduled_*` sind nicht historisiert.** Mit diesem Feature werden die Fenster entgeltrelevant, liegen
  aber weiterhin live und unprotokolliert auf der User-Zeile — während dieselbe Route die acht historisierten
  Felder mit 400 ablehnt (#431-Regel).
- **Mehrfacheinträge pro Tag** (Vormittags-/Nachmittagssprechstunde) sind Regelfall: es fehlt die Regel, wie
  3 × 8 Minuten gegen eine Tagestoleranz von 15 Minuten verrechnet werden.
- **Rundung** ist nirgends geregelt. Bei 15 Minuten Toleranz entscheidet die Rundungsregel jeden zweiten Fall.
- **Keine Benachrichtigungs-Infrastruktur:** die tragende „nachweisliche Zustellung" ist kein Feld
  `notified_at`, sondern ein eigenes Teilprojekt.
- **Gegenrichtung fehlt.** Wer zu früh kommt, verliert die Zeit; wer zu früh geht, behält das Minus. Diese
  Asymmetrie ist der Angriffspunkt jeder Kappungsklausel (§ 307 Abs. 1 BGB). Mindestens: „Minderzeit"
  symmetrisch ausweisen, und bei vorzeitigem Nachhausschicken das Kennzeichen „vom Arbeitgeber veranlasst"
  (§ 615 S. 1 BGB, Annahmeverzug).
- **Fehlkonfigurations-Guard:** Ist die Summe der Fenster kleiner als das Wochensoll, entsteht dauerhaft ein
  Minus, das niemand verursacht hat.

---

## 12. Verwendete Rechtsprechung

Alle Aktenzeichen wurden in einer zweiten Runde gegen die Primärquelle geprüft; keine Entscheidung ist
erfunden. Sicherheitsgrad in der letzten Spalte.

| Entscheidung | Kernaussage für dieses Konzept | Status |
|---|---|---|
| BAG 12.02.2025 – 5 AZR 51/24 | Automatische Systemkürzung ersetzt den Tatsachenvortrag nicht; Bestreiten mit Nichtwissen genügt dem Arbeitgeber nicht | Volltext geprüft |
| BAG 10.12.2013 – 1 ABR 40/12 | Kappungsregelung zulässig; „Die Pflicht zur Vergütung geleisteter Arbeit bleibt hiervon unberührt" | verifiziert |
| BAG 10.04.2013 – 5 AZR 122/12 | Vier Zurechnungswege: angeordnet, gebilligt, geduldet, notwendig | verifiziert |
| BAG 04.05.2022 – 5 AZR 359/21 | Darlegungslast im Überstundenprozess; die EuGH-Zeiterfassungspflicht ändert sie nicht | verifiziert |
| BAG 13.09.2022 – 1 ABR 22/21 | Pflicht zur Einführung eines Zeiterfassungssystems (§ 3 Abs. 2 Nr. 1 ArbSchG) | verifiziert |
| EuGH 14.05.2019 – C-55/18 (CCOO) | Objektives, verlässliches, zugängliches System zur Messung der täglichen Arbeitszeit | verifiziert |
| BAG 21.03.2012 – 5 AZR 676/11 | Kein Eingriff ins Arbeitszeitkonto ohne Befugnis; Anspruch auf Wiedergutschrift | verifiziert |
| BAG 23.09.2015 – 5 AZR 767/13 | Vorbehaltlos ausgewiesenes Guthaben stellt den Saldo streitlos | verifiziert |
| BAG 01.09.2010 – 5 AZR 517/09 | Pauschalabgeltungsklausel intransparent und unwirksam | verifiziert |
| BAG 18.09.2018 – 9 AZR 162/18 | Ausschlussfrist ohne Mindestlohn-Ausnahme insgesamt unwirksam | verifiziert |
| BAG 08.05.2025 – 8 AZR 209/21 | „§ 26 Abs. 1 BDSG hat unangewendet zu bleiben" | Volltext geprüft |
| MFA-Manteltarifvertrag | Zuschläge bei Teilzeit-Mehrarbeit, Bindungswirkung | **nicht verifiziert** |
| ArbZG-Novelle 2026 | Wochenhöchstarbeitszeit, taggleiche Aufzeichnung, Kleinbetriebsausnahme | **nicht verifiziert** (Referentenentwurf, Sekundärquellen) |
