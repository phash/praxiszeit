# Arbeitszeit als Blöcke je Tag — Design

**Datum:** 2026-10-08
**Status:** Entwurf (Entscheidungen vom Betreiber freigegeben am 2026-10-07/08)
**Ziel-Version:** 1.20.0 (MINOR)
**Branch:** `feat/arbeitszeit-bloecke`
**Löst ab:** #201 (ein Soll-Fenster je Wochentag, Spalten `users.scheduled_*`)

Verbindliche Grundlage ist das Entscheidungsprotokoll des Betreibers. Wo die
Touchpoint-Karte (D1–D35) oder die Rechtsbewertung etwas anderes empfehlen, gilt das
Protokoll. Ergänzungen dieser Spec, die das Protokoll nicht ausdrücklich regelt, stehen
gesammelt unter „Präzisierungen" (Abschnitt 2.10) und sind als solche gekennzeichnet.
Review-Funde, die eine Protokoll-Entscheidung ändern würden, sind **nicht** eingearbeitet,
sondern stehen als Frage an den Betreiber mit Empfehlung in Abschnitt 19.1.

---

## 1. Anlass & Ziel

### Anlass

Eine Kundenpraxis meldet: Als Verwaltung kann sie die Soll-Arbeitszeiten ihrer
Mitarbeitenden („wer arbeitet wann") nicht rückwirkend ändern. Das braucht sie
gelegentlich, und jede Änderung muss protokolliert sein. Außerdem hat ein Arbeitstag
in der Praxis mehrere Blöcke mit einer Pause dazwischen, z. B. Montag 08:00–12:00 und
15:00–18:00, und die Gesamtzeit soll sichtbar sein.

Heute gibt es dafür nur das #201-Fenster: **ein** Paar `scheduled_start_<tag>` /
`scheduled_end_<tag>` je Wochentag direkt auf der User-Zeile
(`backend/app/models/user.py:44-55`). Es ist

- **nicht historisiert**: `_HISTORISED_FIELDS` (`admin_users.py:1170-1173`) enthält kein
  `scheduled_*`, ein `PUT /admin/users/{id}` ändert das Fenster live und damit still die
  Kappung jedes künftigen Schreibvorgangs, auch für vergangene Tage;
- **einteilig**: eine Mittagslücke lässt sich nicht abbilden, wer 08:00–18:00
  durchstempelt, bekommt 10 h angerechnet;
- **ohne Soll-Wirkung**: das Fenster kappt nur das Ist, das Tagessoll kommt getrennt aus
  Wochenstunden bzw. Tagesplan — zwei Pflegestellen für dieselbe Aussage.

### Ziel

Die Soll-Arbeitszeit wird je Wochentag als bis zu drei Zeitblöcke mit einer Pause
innerhalb der Blöcke gepflegt, datiert im Vertrags-Snapshot `working_hours_changes`
(#431). Daraus folgen Tagessoll **und** Kappung. Zeit zwischen den Blöcken wird nicht
angerechnet, bleibt aber als Rohstempel erhalten und ist überall sichtbar. Rückwirkende
Änderungen rechnen bereits erfasste Einträge neu, mit Vorschau, Protokoll je Eintrag und
einem Schutzpaket gegen rückwirkende Verkürzung.

### Erfolgskriterien (prüfbar)

1. Im Dialog „Arbeitszeit & Wochenstunden" lassen sich je Wochentag Mo–Fr bis zu drei
   Blöcke „von–bis" im 5-Minuten-Raster und eine „Pause innerhalb der Blöcke" erfassen;
   der Dialog zeigt je Tag live „Gesamtzeit · Pause · Tagessoll" und die Wochensumme.
2. Mit Blöcken Mo 08:00–12:00 + 15:00–18:00, Pause 0, Puffer 15 Min ergibt ein
   durchgestempelter Eintrag 08:00–18:00: `start_time` 08:00, `end_time` 18:00,
   `raw_*` leer, `uncredited_minutes` 150, `net_hours` 7,50.
3. Das Tagessoll eines Block-Tages ist (Σ Blockdauer − Pause) in Stunden, beim Speichern
   in `hours_<tag>` materialisiert; `calculation_service` bleibt für alle Soll-Schleifen
   unverändert, und alle bestehenden Soll-/Saldo-Suiten bleiben grün — bis auf die in 17.6
   genannten mechanischen Anpassungen (`ScheduleSegment`-/`Schedule`-Helfer) und die bewusst
   geänderten F1-Fälle in `test_retarget_absence_hours.py` (E51, 9.6).
4. Nach Migration 073 sind `net_hours`, Tagessoll und Überstundensaldo aller
   Bestandsdaten byte-identisch (Nachweis per Postgres-Lauf auf einer Prod-Kopie).
5. Eine Änderung mit Wirkungsdatum in der Vergangenheit kappt die betroffenen Einträge
   neu; die Vorschau nennt vorher die Anzahl, die Monatssummen alt → neu, die
   Überstunden-Differenz und jeden übersprungenen Eintrag mit Grund.
6. Jeder neu gekappte Eintrag erzeugt genau eine Protokollzeile `source="wh_reclamp"`,
   jedes Anlegen und jedes Löschen einer Arbeitszeit-Änderung genau eine Sammelzeile mit
   handelnder Admin — auch ohne betroffene Einträge (10.2);
   `GET /api/admin/audit/verify-integrity` bleibt grün.
7. Verliert durch die Änderung mindestens ein erfasster Eintrag angerechnete Zeit, ist
   „rückwirkend" nur mit Grundtyp, Begründung und Bestätigung speicherbar; in ein
   abgeschlossenes Jahr hinein gar nicht (HTTP 400).
8. Nicht angerechnete Zeit — Lücke **und** von der Hülle gekappte Anwesenheit (P19) —
   steht an jedem Eintrag (Admin-Dashboard, Monatsjournal, Zeiterfassung), als
   Monatssumme im Journal und als angehängte Spalte „Nicht angerechnet (Min)" in XLSX, ODS
   und PDF; ein Admin kann sie je Eintrag anerkennen, Mitarbeitende können die Anrechnung
   beantragen (P21).
9. Mitarbeitende sehen ihre heute gültigen Blöcke und den Verlauf im Profil und nach
   jeder sie betreffenden Arbeitszeit-Änderung (auch „ab heute" und zukunftsdatiert)
   30 Tage lang einen Hinweis im Dashboard (P20).
10. Die harten §3/§4-Prüfungen rechnen weiter auf der angerechneten Zeit; zusätzlich gibt
    es weiche Warnungen auf der tatsächlichen Anwesenheit (Rohstempel) für Tag (§3, §4)
    und Woche (48 h, P22).
11. Kein Code liest mehr `scheduled_*` (Guard-Test), kein Code außer dem Resolver liest
    `users.work_blocks` für eine Berechnung (Guard-Test).
12. Alle fünf Doku-Sync-Flächen und `CLAUDE.md` sind nachgezogen.

---

## 2. Entscheidungen

Jede Zeile des Protokolls ist hier aufgenommen. Spalte „Begründung" fasst den Grund
knapp zusammen.

### 2.1 Grundentscheidungen

| Nr | Entscheidung | Begründung |
|---|---|---|
| E1 | **Rückwirkung:** bereits erfasste Einträge im Zeitraum werden **neu berechnet**, mit Vorschau alt → neu — Muster der Wochenstunden-Änderung (#415/#431). | Ohne Neuberechnung stünde neues Soll neben alt gekapptem Ist im selben §16-Beleg (Phantomsaldo). |
| E2 | **Gesamtzeit bestimmt das Tagessoll** (individueller Tagesplan); angezeigt als Gesamtzeit / Pause / Tagessoll. | Eine Pflegestelle statt zwei (Fenster + Tagesstunden). |
| E3 | **Lücke zwischen Blöcken wird nicht angerechnet**, behandelt wie Zeit außerhalb des Fensters heute (#201); Rohstempel bleibt, Hinweis wird gezeigt. | Konsequente Fortsetzung von #201; Nachweis der Anwesenheit (§16 ArbZG) bleibt unberührt. |
| E4 | **Datenmodell Ansatz A:** Blöcke sind Teil des datierten Vertrags-Snapshots `working_hours_changes` als JSON-Spalte — keine Kindtabelle, keine eigene Historie. | „Die nächste Zeile ist immer die Fenstergrenze" (#431) gilt automatisch; keine zweite Historie, keine neue RLS-Tabelle. |
| E5 | **Puffer an jedem Blockrand**, auch an den inneren, symmetrisch: 8–18 durchgestempelt bei 8–12 + 15–18 und 15 Min Puffer → angerechnet 08:00–12:15 + 14:45–18:00 = 7:30 h. Eine Lücke ≤ 2 × Puffer verschwindet. | Eine einheitliche Regel; kein Minutenabzug beim Ausstempeln um 12:05. |
| E6 | **Schutzpaket für rückwirkende Verkürzung** (Abschnitt 9.5). | Lage der Arbeitszeit ist einseitig nur für die Zukunft änderbar (§ 106 GewO); Rechtsbewertung „rot" ohne Schutzpaket. |
| E7 | **Oberfläche, „Anerkennen", Mitarbeiter-Hinweis** wie beschrieben (Abschnitte 12–14). | Nichtanrechnung darf nicht still sein (Rechtsbewertung „rot" ohne Sichtbarkeit und Freigabeweg). |

### 2.2 Datenmodell

| Nr | Entscheidung | Begründung |
|---|---|---|
| E8 | `working_hours_changes.blocks`: `JSON().with_variant(JSONB(), "postgresql")`, nullable, kanonisch eine Liste aus genau 5 Einträgen (Mo–Fr), je `{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int \| null}`. **NULL in einer Verlaufszeile heißt „keine Blöcke", NIE Rückfall** auf `users.work_blocks`. | Das Muster `work_days_per_week` (NULL = Rückfall) würde jede Sync der User-Zeile rückwirkend in alle Altzeilen durchschlagen lassen (#431-Fehlerklasse). JSONB-Variante, sonst bricht die SQLite-Suite. |
| E9 | `users.work_blocks`: gleiche Form, Rückfall **nur** für Tage vor der ersten Verlaufszeile (wie `weekly_hours` seit #415). Änderbar nur über den Verlauf, nie live per `PUT`. | Ein Live-Feld ohne Historie wäre exakt die #431-Lücke. |
| E10 | `pause_minutes` = Pause innerhalb der Blöcke. **NULL = „Soll nicht aus Blöcken abgeleitet"** (Altzeilen aus Migration 073): die Blöcke kappen nur, das Soll bleibt wie gespeichert. | Altfenster passen oft nicht zum Tagessoll (halboffen, kürzer als Soll, 13,33 h je Tag); eine abgeleitete Pause wäre negativ oder erfunden. |
| E11 | `time_entries.uncredited_minutes`: `INT NOT NULL DEFAULT 0`. In der Lücke liegende, nicht angerechnete Zeit des Eintrags. **Nie Eingabefeld** (kein Schema nimmt es an), immer serverseitig abgeleitet. | Sonst setzt der Client seine Anrechnung selbst. |
| E12 | `time_entries.credit_override`: `BOOL NOT NULL DEFAULT false`. Gesetzt per Admin-Aktion „Anerkennen": für diesen Eintrag keine Kappung (Fenster ignoriert), dauerhaft, auch bei späterer Neukappung. Protokolliert. | Freigabeweg für geduldete Arbeit (§ 612 BGB); muss Neuberechnungen überleben. |
| E13 | `net_hours` = Ende − Beginn − Pause − `uncredited_minutes`, als Hybrid-Property in Python **und** als SQL-Ausdruck. | Ohne das wirkt das Feature in keinem Saldo und keinem Export. |
| E14 | Raster 5 Minuten für Blockgrenzen und Pause. Höchstens 3 Blöcke je Tag. Validierung: sortiert, überlappungsfrei, Beginn < Ende, 0 ≤ Pause < Σ Blockdauer. Nur Mo–Fr. | Tagessoll und Fenster kennen heute nur Mo–Fr; 5 Min hält die Rundungsabweichung ≤ 0,005 h/Tag. |

### 2.3 Tagessoll

| Nr | Entscheidung | Begründung |
|---|---|---|
| E15 | **Neue Blöcke** (über den Dialog geschrieben): `hours_<tag>` = (Σ Blöcke − Pause) als `Decimal`, `quantize(0.01, ROUND_HALF_EVEN)`; `weekly_hours` = Σ `hours_<tag>`; `work_days_per_week` = Anzahl Tage mit Blöcken; `use_daily_schedule` = `True`. **Beim Schreiben materialisiert** → `calculation_service` und alle Gates bleiben byte-identisch. | Option B (Soll aus Blöcken rechnen) hätte vier Gates plus `is_vacation_billable_day` umgebaut. |
| E16 | Ein Wochentag ohne Blöcke in einem Block-Snapshot = 0 h (kein Arbeitstag), keine Kappung. | Folgt aus E15. |
| E17 | Personen ohne Blöcke behalten ihre bisherigen Modi (gleichmäßig / Tagesplan) unverändert. | Opt-in, keine Verhaltensänderung ohne Absicht. |
| E18 | Altfenster aus 073 (`pause_minutes` NULL) kappen in beiden Modi wie heute und haben keine Wirkung aufs Soll. | Byte-Identität der Migration. |

### 2.4 Migration 073

| Nr | Entscheidung | Begründung |
|---|---|---|
| E19 | Neue Spalten wie E8–E12. Backfill in Python (`Decimal`), als Superuser (FORCE RLS). | SQL-`ROUND` rundet anders als Python-HALF_EVEN; unter FORCE RLS träfe der Backfill sonst still 0 Zeilen. |
| E20 | Jede Person mit Fenster: `users.work_blocks` = heutiges Fenster als ein Block je Tag (`pause_minutes` NULL), **und jede bestehende Verlaufszeile dieser Person** bekommt denselben Wert. | Die Fenster wirkten live → Verhalten byte-identisch, gleiches Prinzip wie 067. |
| E21 | Bestandsfallen: halboffenes Fenster → Platzhalter 00:00 bzw. 23:59 (identisches Kappungsverhalten) plus Diagnosezeile; Beginn ≥ Ende → nicht übernommen, Diagnosezeile; Sekunden → abgeschnitten, Diagnosezeile. | Keine Abbrüche (Update eines Kundensystems darf nicht hängen), aber nichts verschweigen. |
| E22 | Keine Neukappung in der Migration, `uncredited_minutes` bleibt 0, `net_hours` byte-identisch, Soll byte-identisch. | §16-Belege der Vergangenheit bleiben unangetastet (Rechtsbewertung Pflicht 1). |
| E23 | Die `scheduled_*`-Spalten werden in 073 gelöscht (kein Expand/Contract), dazu ein Guard-Test (grep), dass kein Code mehr `scheduled_*` liest. | `getattr(user, "scheduled_…", None)` würde nach dem Drop die Kappung still abschalten; einen App-Rollback ohne DB-Downgrade gibt es nicht. |
| E24 | Downgrade ist verlustbehaftet: Rekonstruktion **aus dem ersten Block**, mit Diagnose der Personen mit mehreren Blöcken und der Einträge mit `uncredited_minutes` > 0. | Vom Betreiber so entschieden; Folgen siehe Abschnitt 19.1 Nr. 3. |
| E25 | Vorbedingung: Diagnose-SQL (Abschnitt 5.1) auf einer Kopie der Produktions-DB, **bevor** implementiert wird. | Welche Fallen real vorkommen, ist unbekannt; keine der Analyse-Lanes hatte DB-Zugriff. |

### 2.5 API

| Nr | Entscheidung | Begründung |
|---|---|---|
| E26 | `PUT`/`POST /admin/users` mit alten Feldnamen `scheduled_*` → **400 „Bitte Seite neu laden"**, nicht still verworfen. | Ein gecachtes altes Frontend schickt die Felder bei jedem Speichern; still verwerfen hieße „gespeichert" melden, ohne zu speichern. |
| E27 | `work_blocks` kommt in `_HISTORISED_FIELDS` → `PUT` lehnt es ab (400, wie die #431-Felder). | Genau ein Schreibweg. |
| E28 | `POST /admin/users` nimmt `work_blocks` als Startvertrag an (Soll abgeleitet). | Beim Anlegen gibt es noch keine Historie. |
| E29 | Leseschemas (`UserResponse`/`UserListResponse` — auch die Login- und Impersonation-Antwort!) typisieren `work_blocks` locker, **ohne** strengen Validator. Strenge Prüfung nur in Anlege-/Schreibschemas. | Ein strenger Leseschema-Validator macht den Login einer Person mit Altfenster (07:37, 23:59) zu HTTP 500. |
| E30 | Vorschau: `POST /admin/users/{id}/working-hours-changes/preview` mit Body (dieselbe Body-Verarbeitung wie beim Speichern), rein lesend mit Rollback. | axios serialisiert verschachtelte Objekte als `blocks[0][start]`, FastAPI parst das nicht. |

### 2.6 Kappung

| Nr | Entscheidung | Begründung |
|---|---|---|
| E31 | `clamp(db, user, d, start, end, grace)` liefert ein `NamedTuple` `(eff_start, eff_end, raw_start, raw_end, uncredited_minutes)`. Altes Entpacken in 4 Variablen scheitert laut (gewollt). | Jede übersehene Aufrufstelle fällt im Test sofort auf. |
| E32 | Äußere Hülle wie heute: Beginn vor erstem Block − Puffer → verschoben, Ende nach letztem Block + Puffer → verschoben, `raw_*` bleiben. Kollaps außerhalb der Hülle wie heute (0 h, `uncredited` 0). | Bestandsverhalten #201/#462. |
| E33 | **Beginn in der Lücke wird NICHT verschoben.** Die Lücke läuft über `uncredited`. | Verschieben erzeugt UNIQUE-Verletzungen auf `uq_tenant_user_date_start` (clock_in hat keine Duplikatprüfung), und Einträge mit Beginn = Ende ließen sich nicht mehr speichern. |
| E34 | `uncredited` = Überlappung von [eff_start, eff_end] mit den Lücken (um 2 × Puffer geschrumpft). Eintrag ganz in der Lücke → 0 h angerechnet, Kollaps-Hinweis, Stempel bleiben. | Folgt aus E3/E5. |
| E35 | `end=None` / keine Blöcke / `track_hours=False` / `credit_override` / Sonntag, Feiertag, freier Sondertag (#484) → `uncredited` 0, kein Fenster. | §§ 9/10 ArbZG: Arbeit dort ist Ausnahme, keine verschobene Regelarbeitszeit (#484). |
| E36 | **Alle 12 clamp-Aufrufstellen** (`time_entries` 300/403/655/990, `admin_time_entries` 88/293, `admin_change_requests` 387/488/535/1019, `xls_import_service` 220/416) **plus Auto-Close** (`_close_stale_entry`, 23:59): läuft über `clamp` (Ende = letzter Block + Puffer, `raw_end` = 23:59). | Schließt das Altschlupfloch, dass der Abend voll angerechnet wurde. |
| E37 | Warncode `WORK_WINDOW_CLAMPED` bleibt; der Text aus `clamp_warning_text` wird um Lücke und nicht angerechnete Zeit erweitert. Einstempeln in der Lücke nutzt denselben Text. | Eine Textquelle (#462), keine Mapping-Änderung im Frontend. |
| E38 | XLS: Helfer `has_blocks(...)` statt `get_scheduled_window(...) != (None, None)`. Auto-Pause = nur, was nach Lückensegmenten ≥ 15 Min fehlt. `/confirm` rechnet serverseitig neu. | `[] != (None, None)` ist immer wahr → `raw_*` würden an Tagen ohne Blöcke gelöscht. |

### 2.7 Mitbehobene Bestandsfehler

| Nr | Entscheidung | Begründung |
|---|---|---|
| E39 | MA-`PUT`: `date` kommt ins Neukappungs-Gate. | Ein reiner Datumswechsel auf einen anderen Wochentag kappt heute nicht neu. |
| E40 | MA-Antrag (`change_requests.py`) validiert mit `clamp` + `uncredited`, speichert weiter roh. | Heute prüft der Antrag roh, die Genehmigung gekappt → gültige Teilschicht-Anträge („08–18, Pause 0") sind nicht stellbar. |
| E41 | CR-Nachprüfung nach dem Commit: `exclude_entry_id=cr.time_entry_id`. | Der Eintrag zählt heute doppelt (§6/48-h-Warnungen zu hoch). |
| E42 | Auto-Close über `clamp` (siehe E36). | — |

### 2.8 ArbZG

| Nr | Entscheidung | Begründung |
|---|---|---|
| E43 | **Harte Prüfungen unverändert auf angerechneter Zeit** (§3 10-h-Grenze, §4 Pausen); ein Lückensegment ≥ 15 Min zählt für §4 als Pausenabschnitt. | Eine geplante Lücke ist eine im Voraus feststehende Ruhepause (#201-Prinzip). |
| E44 | **Zusätzlich weiche Warnungen auf tatsächlicher Anwesenheit (Rohstempel)**, nicht blockierend, über `showArbzgWarnings`: Anwesenheit > 10 h am Tag (§3); durchgestempelt über eine Lücke, > 6 h Anwesenheit ohne erfasste Pause (§4). | Neukappung darf Verstöße nicht verschwinden lassen (Rechtsbewertung Pflicht 4). |
| E45 | Doppelabzug vermeiden: XLS-Auto-Pause und §4-Bedarf aus der angerechneten Zeit; bei Pause > 0 **und** `uncredited` > 0 weiche Warnung „Pause in der Lücke wird zusätzlich abgezogen". StampWidget verlangt keine Pause, wenn die Lücke §4 abdeckt. | Additive Formel (E13) bleibt, der Doppelabzug wird sichtbar statt still. |
| E46 | §5 unverändert (Rohstempel). §6-Nachterkennung auf Rohstempel → eigenes Ticket. | §6 ist unabhängig von Blöcken (16 Stellen). |

### 2.9 Rückwirkung, Oberfläche, Transparenz, Export, Doku

| Nr | Entscheidung | Begründung |
|---|---|---|
| E47 | Neukappung nur für Einträge in [Wirkungsdatum, nächste Änderung) und nur an Wochentagen, deren Blöcke sich zwischen altem und neuem Snapshot unterscheiden. Reine Pausenänderung → keine Neukappung. Es gilt der **aktuelle** Mandanten-Puffer; die Vorschau nennt ihn. | Der historische Puffer ist nicht gespeichert; unbeteiligte Tage bleiben unberührt. |
| E48 | Quelle der Neukappung ist der Rohstempel; fehlt er, ist die gespeicherte Zeit der Stempel (nie gekappt). | Kein kumulatives Doppelkappen (1.18.2-Fehlerklasse). |
| E49 | Übersprungen und einzeln in Vorschau und Antwort gemeldet: offene Einträge; Sonntag/Feiertag/freier Sondertag; `track_hours=False`; außerhalb des Beschäftigungsfensters; `credit_override`; UNIQUE-Kollisionen. | Kein stilles Auslassen. |
| E50 | Einträge, deren Rohstempel vor 1.19.1 verloren ging, sind nicht erkennbar; sie werden in der Vorschau als „nicht erweiterbar" markiert, wenn die gespeicherte Zeit exakt auf der alten Fensterkante liegt. | Ehrliche Grenze statt falscher Verlängerung. |
| E51 | Reihenfolge: erst Zeiteinträge neu kappen, dann `retarget_absence_hours`. `retarget_absence_hours` bekommt die F1-Klemmung (`kept_net_by_date`) und schließt damit die Bestandslücke. | Sonst Phantomsalden an Misch-Tagen (Krank/Fortbildung + Arbeit). |
| E52 | Eine Transaktion unter der Ankersperre (`lock_user_row`). Keine stille Obergrenze; die Vorschau nennt die Anzahl. | Atomar; CLAUDE.md „no silent caps". |
| E53 | **Verlängerung** (niemand verliert angerechnete Zeit): Vorschau (Einträge alt → neu je Monat, Δ Überstundenkonto, übersprungene), Speichern nach Bestätigung; abgeschlossenes Jahr (YearCarryover für Y+1) → nur Warnung. | Begünstigt die Beschäftigten bei der **angerechneten Zeit** (Rechtsbewertung „gelb"). Achtung: Im Block-Modell bestimmen die Blöcke auch das Soll (E2/E15); längere Blöcke oder eine kleinere Pause erhöhen rückwirkend das Soll und können den Saldo senken, ohne dass ein Eintrag verliert. Ob das unter das Schutzpaket fällt, ist offene Frage 19.1 Nr. 1 (R1); die Vorschau weist Soll- und Ist-Differenz getrennt aus (9.4). |
| E54 | **Verkürzung** (mindestens ein Eintrag verliert angerechnete Zeit): Standard „Ab heute wirksam" (Wirkungsdatum = heute, keine rückwirkende Zeile, keine Neukappung der Vergangenheit → auch keine Hintertür über späteres Bearbeiten). Option „Rückwirkend ab ‹Datum› mit Neuberechnung" verlangt Grundtyp (Erfassungsfehler korrigiert / einvernehmlich vereinbart / sonstiges) plus Freitext, einen Bestätigungshaken zum Vergütungsrisiko und zeigt eine Zusatzwarnung bei MiLoG-Konto/Minijob. Rückwirkende Verkürzung in ein abgeschlossenes Jahr ist **gesperrt**. Der Grund steht in `working_hours_changes.note` (mit Typ) und in der Sammelzeile. | Schutzpaket der Rechtsbewertung. |
| E55 | Löschen einer Verlaufszeile rechnet symmetrisch zurück (eigene Vorschau/Bestätigung, gleiche Regeln inkl. Verkürzungsschutz). Die früheste Änderung bleibt gesperrt, solange spätere existieren (bestehende Regel). | Symmetrie wie #415. |
| E56 | Zukunftsdatierte Änderungen: kein Scheduler. Ein Guard-Test sichert, dass nichts `users.work_blocks` live liest. | Wie D29; der Resolver ist datumsaufgelöst. |
| E57 | Protokoll: je neu gekapptem Eintrag eine `TimeEntryAuditLog`-Zeile, `source="wh_reclamp"` (≤ 40 Zeichen), Label „Neukappung (Arbeitszeit-Änderung)"; alte/neue effektive Beginn/Ende, Notiz mit `uncredited`, Auslöser und Grund. Eine Sammelzeile je Änderung (handelnde Admin, Wirkungsdatum, Grund, Anzahlen). `row_hash` über die Objektschicht (#121), kein Bulk-UPDATE. Die Vorschau protokolliert nie (Rollback). | Revisionssicherheit (Art. 5 Abs. 2 DSGVO, §16 ArbZG). |
| E58 | Knopf „Arbeitszeit anpassen…", Dialogtitel „Arbeitszeit & Wochenstunden". | Die E2E-Regex `/Wochenstunden/i` passt weiter. |
| E59 | Je Wochentag bis zu 3 Zeilen „von–bis" plus „Pause innerhalb der Blöcke"; live „Gesamtzeit 9:00 h · Pause 1:00 h · Tagessoll 8:00 h" plus Wochensumme. | E2. |
| E60 | Wirkungsdatum; Vorschau darunter; bei Verkürzung die Wahl „ab heute" vs. „rückwirkend" mit Grund/Haken. | E54. |
| E61 | Fester Hinweis zu Mitbestimmung (§ 87 Abs. 1 Nr. 2 BetrVG) und Direktionsrecht (§ 106 GewO; Änderung der Lage einseitig nur für die Zukunft). | Rechtsbewertung Pflicht 11. |
| E62 | UserForm: der alte Fenster-Abschnitt entfällt; stattdessen Zusammenfassung der heute gültigen Blöcke (serverseitig datumsaufgelöst) plus Link zum Dialog. Beim Anlegen ein Block-Editor für den Startvertrag. | E9/E28. |
| E63 | `track_hours=false`: Block-Editor ausgeblendet, gespeicherte Werte bleiben. | Ohne Stundenzählung wirkt weder Soll noch Kappung. |
| E64 | `RawStampNote` erweitert: „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet" (Admin-Dashboard, Monatsjournal, Zeiterfassung). | E7. |
| E65 | Journal-Monatssumme: Zeile „Anwesenheit nicht angerechnet". | E7. |
| E66 | **Anerkennen:** Admin-Aktion je Eintrag → `credit_override=true`, `uncredited=0`, protokolliert. Überlebt spätere Neukappungen. | E12. |
| E67 | Profil der Mitarbeitenden: heute gültige Blöcke (serverseitig datumsaufgelöst) und Verlauf mit Wirkungsdaten. | Art. 5 Abs. 1 lit. a, Art. 12 ff. DSGVO. |
| E68 | Nach einer sie betreffenden rückwirkenden Neuberechnung 30 Tage lang ein Dashboard-Hinweis „Ihre Arbeitszeit wurde ab ‹Datum› angepasst, ‹n› Einträge neu berechnet", abgeleitet aus der `wh_reclamp`-Sammelzeile (keine neue Bestätigungstabelle). | Transparenz ohne neues Datenmodell. |
| E69 | Dashboard-Status in der Lücke nicht rot. | Eine geplante Pause ist kein Fehlverhalten. |
| E70 | XLSX/ODS/PDF: Spalte „Nicht angerechnet (Min)" **angehängt** (nie eingeschoben — Kundenauswertungen). | #415-Regel. |
| E71 | Berichtstext (`format_weekly_hours_history` + Frontend-Zwilling `formatWeeklyHoursChanges`, wortgleich): Blöcke nur, wenn sie sich geändert haben, „ab 01.09.: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min)", Kurzform für PDF. | Eingefrorener Wortlaut bleibt sonst byte-identisch. |
| E72 | Art.-15/20-Export (`lifecycle_service._user_dict`, `auth /me/export`): Blöcke und Verlauf als HH:MM-Strings. | `time` ist nicht JSON-serialisierbar (#383/#408-Klasse). |
| E73 | Anonymisierung (beide Pfade): Freitext `working_hours_changes.note` (Grund) leeren; Blöcke sind reine Zeitwerte und bleiben. Protokollzeilen wie bisher: Scrub über Inhalt + `row_hash`-Neuberechnung. | #440-Muster. |
| E74 | Neue Felder in bestehenden Tabellen → RLS/F-026 folgen aus den Tabellen; jede neue Abfrage in `calculation_service`/`work_window_service` trägt den `tenant_id`-Filter trotzdem. | F-026 belt-and-suspenders. |
| E75 | Doku über alle 5 Sync-Flächen (docs/handbuch + BERECHNUNGEN, DocViewer, `public/help`-Spiegel byte-identisch, pzweb-Anleitung, In-App-Schnellstart wo relevant). | CLAUDE.md-Pflicht. |
| E76 | Handbuch ausdrücklich: Nichtanrechnung ist keine Vergütungsentscheidung (§ 611a, § 612 BGB, MiLoG — geduldete Arbeit ist geschuldet). Hinweis Mitbestimmung. | Rechtsbewertung Pflicht 8/11. |
| E77 | `CLAUDE.md`: neue Regeln zu Blöcken / `uncredited` / Neukappung. | Abschnitt 16. |
| E78 | Außerhalb des Umfangs (Folgetickets): Blöcke am Samstag; §6-Nachterkennung auf Rohstempel; #314-Re-Split bei Arbeitszeit-Änderung; Rohstempel in Exportdateien; JArbSchG-Schichtzeit für Auszubildende; Warnschwelle für wiederholt nicht angerechnete Zeit. | Abschnitt 18. |

### 2.10 Präzisierungen dieser Spec

Diese Punkte regelt das Protokoll nicht ausdrücklich; sie folgen aus ihm. **Ausnahme:**
P1 weicht vom Wortlaut des Protokolls ab („effective_from = today") und gilt nur bis zur
Bestätigung durch den Betreiber; P13, P23 und P24 legen Protokollformulierungen aus. Alle
vier stehen in Abschnitt 19.1 zur Bestätigung.

| Nr | Präzisierung | Grund |
|---|---|---|
| P1 | **Abweichung vom Protokoll bis zur Bestätigung (19.1 Nr. 2).** „Verkürzung" ist rein über die Wirkung auf **erfasste** Einträge definiert. Erfasst ist auch ein geschlossener Eintrag von heute. Ein **offener Eintrag von heute** (nur dieser; offene Einträge vergangener Tage gibt es nach P23 im Fenster nicht mehr) an einem geänderten Wochentag zählt nur dann als verlierend, wenn der neue Snapshot für **irgendein** mögliches Ende ≥ jetzt weniger anrechnet als der alte. Exakte Prüfung: Die Differenz `angerechnet_neu(Ende) − angerechnet_alt(Ende)` ist in `Ende` stückweise linear mit Knickstellen an den Hüllen- und Lückenkanten beider Snapshots; geprüft wird an `max(jetzt, Beginn)`, an jeder Knickstelle danach und an 23:59. Ist sie überall ≥ 0 (z. B. reine Verlängerung), wird der offene Eintrag nur als `open` übersprungen (E49) und beeinflusst `is_shortening` nicht. Die Standardoption heißt „Ab heute wirksam", wenn ab heute kein Eintrag verliert, sonst „Ab ‹frühestes verlustfreies Datum› wirksam" (im Regelfall morgen). | Sonst würde „ab heute" bereits geleistete Arbeit von heute Vormittag rückwirkend kürzen, beim Ausstempeln über die normale Kappung sogar ohne Vorschau. Die Knickstellen-Prüfung verhindert, dass eine reine Verlängerung, gespeichert während jemand eingestempelt ist, als Verkürzung gilt. |
| P2 | Altfenster (`pause_minutes` NULL) werden in neue Verlaufszeilen der Modi „Gleichmäßig"/„Nach Tagen" übernommen, bis sie ausdrücklich entfernt (`remove_legacy_window`) oder durch Blöcke ersetzt werden. Quelle ist der **vor der Änderung für `effective_from` gültige Snapshot** (Vorgängerzeile bzw. Rückfall `users.work_blocks`, wie 9.1) — nicht die User-Zeile und nicht der heutige Stand (P24). | Sonst schaltete jede Wochenstunden-Änderung die bewusst gesetzte Kappung still ab. |
| P3 | `credit_override` bleibt bei Admin-Direktbearbeitung, bei Genehmigung eines Änderungsantrags (UPDATE) und beim XLS-Überschreib-Import **erhalten** — die Verwaltung bestätigt dort die neuen Zeiten ausdrücklich. Antragsprüfung und XLS-Vorschau zeigen dazu den Hinweis „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet." Ein MA-`PUT` auf einen anerkannten Eintrag → **409** „Anerkannter Eintrag – Änderung bitte per Änderungsantrag." Kein Pfad setzt das Flag still zurück. | Ein stilles Zurücksetzen wäre eine Rücknahme anerkannter Zeit ohne Vorschau, Grund und Protokoll — genau die Verkürzung, die P11 ausschließt (R2). |
| P4 | „Anerkennen" blockiert nie an §3/§4; Verstöße kommen als weiche Warnung. | Anerkennen ändert den Nachweis nicht, nur die Anrechnung; eine Sperre würde geleistete Arbeit verstecken. |
| P5 | **Jeder** Schreibpfad für Zeiteinträge (7.1 Nr. 1–13 und die Anerkennung 13.3) nimmt als **erste** Anweisung, vor `get_grace_minutes`, Snapshot-Auflösung und `clamp`, die Ankersperre `lock_user_row(db, tenant_id, owner_id)`. `clock_in` (`time_entries.py:267`) und `review_change_request` (`admin_change_requests.py:235`, damit auch Bulk) tun das schon; neu sind `clock_out`, `create_time_entry`, `update_time_entry`, `admin_create/update_time_entry`, `_execute_import_inner` (einmal je Import, Zielperson) und der Stale-Zweig von `GET /clock-status` (sperren, offenen Eintrag danach neu lesen). `create_change_request` (7.1 Nr. 14) schreibt keinen Eintrag und braucht keine Sperre. Reihenfolge: Ankersperre **vor** jeder Zeilensperre auf `time_entries`. | Unter READ COMMITTED liest ein nicht sperrender Schreiber während einer laufenden Änderung noch den alten Snapshot, kappt danach und wird von der bereits gelaufenen Neukappungs-Abfrage nicht erfasst — Eintrag unter alten Blöcken, ohne Protokoll. Die feste Reihenfolge verhindert Deadlocks (40P01 → 500). |
| P6 | `Schedule` bekommt die neuen Felder **ohne** Vorgabewert; `clamp` nimmt `credit_override` als **pflichtiges** Schlüsselwort-Argument. | Übersehene Aufrufstellen scheitern laut (Projektregel seit #431). |
| P7 | Die Sammelzeile trägt Wirkungsdatum, Löschkennzeichen, Anzahl, Δ angerechnete Minuten, Verkürzungskennzeichen und Grundtyp in einem festen Notiz-Präfix; Schreiben und Lesen leben in einem Modul mit Round-Trip-Test (10.2). | Keine neue gehashte Spalte (sonst meldet `verify-integrity` alle Altzeilen). |
| P8 | `DELETE …/working-hours-changes/{id}` nimmt einen optionalen JSON-Body (Verkürzungsschutz) und hat eine eigene Vorschau `POST …/{id}/delete-preview`. | E55 verlangt Vorschau und Schutzpaket auch beim Löschen. |
| P9 | Plan-Hinweise im Dialog (nicht blockierend, `block_break_notices`), abgeleitet aus dem **ganzen** Tagesplan statt aus Einzelblöcken: (a) §4 — geplante Arbeitszeit = Σ Blöcke − Pause, Bedarf 30 bzw. 45 Min; geplante Pausen = `pause_minutes` + Σ **rohe** Lücken ≥ 15 Min; Hinweis, wenn sie nicht reichen oder (bei Pause 0) eine Strecke ohne Lücke ≥ 15 Min länger als 6 h ist; (b) eine Lücke ≤ 2 × aktueller Puffer verschwindet in der Anrechnung → Hinweis „Mo: Die Lücke 12:00–12:30 ist nicht länger als der doppelte Puffer (15 Min) und wird vollständig angerechnet. Eine geplante Pause bitte als „Pause innerhalb der Blöcke" erfassen."; (c) §3 — Tagessoll > 10 h: deutlicher Hinweis („geplanter Verstoß gegen § 3 ArbZG; eine Erfassung nach diesem Plan lehnt die Zeiterfassung mit 400 ab"), Tagessoll > 8 h: Hinweis auf den 24-Wochen-Durchschnitt, Wochensoll > 48 h: Hinweis; entfällt bei `exempt_from_arbzg`. Kein 422 (die Protokoll-Validierung bleibt abschließend). | §4 hängt an der täglichen Arbeitszeit, nicht am Einzelblock; eine verschwindende 30-Min-Lücke würde sonst still voll angerechnet und mit harter §4-Sperre enden (R11, Fund F13). |
| P10 | Drei Nebenbefunde im ohnehin umgebauten Code werden mitbehoben (Abschnitt 7.3). | Die Funktionen werden ohnehin neu geschrieben. |
| P11 | Eine Rücknahme von „Anerkennen" gibt es in diesem Umfang nicht (Folgeticket). | Rücknahme = Verkürzung angerechneter Zeit, bräuchte eigenes Schutzkonzept. |
| P12 | Das Profil der Mitarbeitenden zeigt den Freitext `note` nicht; er steht im Art.-15-Export. Der Dashboard-Hinweis (P20) nennt höchstens den festen Grundtyp. | Der Verwaltungsfreitext ist kein Anzeigeelement; das Auskunftsrecht bleibt vollständig. |
| P13 | **Löschen mit Verkürzung (zur Bestätigung, 19.1 Nr. 4):** wie beim Anlegen ist die Standardoption verlustfrei — „Ab ‹earliest_lossless_date› auf den vorherigen Stand zurücksetzen" legt **statt des Löschens** eine neue Verlaufszeile mit dem Snapshot des Vorgängers an (keine Neukappung der Vergangenheit). Angeboten nur, wenn `earliest_lossless_date` nach dem `effective_from` der zu löschenden Zeile und vor der nächsten Änderung liegt (P25), sonst nur „Löschen mit Neuberechnung" mit Grund/Haken. | Das Protokoll verlangt beim Löschen „dieselben Regeln inkl. Verkürzungsschutz"; dessen Standard ist „ab heute". |
| P14 | Zusatzbedingungen der weichen Anwesenheits-Warnungen: `PRESENCE_DAILY_HOURS` nur, wenn die harte §3-Prüfung auf angerechneter Zeit nicht gegriffen hat; `PRESENCE_BREAK` nur, wenn die §4-Prüfung auf angerechneter Zeit kein `BREAK_WARNING`/400 ausgelöst hat (Doppelmeldung vermeiden). **Keine** Bedingung „nur dank Lückensegmenten bestanden" (8.3). | Die frühere Zusatzbedingung unterdrückte die Warnung bei K9 und immer dann, wenn die angerechnete Zeit ≤ 6 h ist (K19) — genau die Fälle, die Pflicht 4 meint. |
| P15 | `retroactive_reason_text` mindestens 10, höchstens 400 Zeichen. | Ein Ein-Wort-Grund ist kein Grund; Gesamtlänge der `note` ≤ 500 (9.5). |
| P16 | Aneinanderstoßende Blöcke (Ende_i = Beginn_i+1) sind unzulässig (3.4). | Sie wären ein Block mit einer Lücke von 0 Min; zwei Darstellungen derselben Arbeitszeit. |
| P17 | Für `end=None` gilt E35 („kein Fenster") nur für die **Lücke**: die Hülle verschiebt den Beginn weiter wie seit #201 (`raw_start`, `EARLY_START`), `uncredited` = 0. Fall K20. | Wörtlich gelesen schaltete E35 die #201-Kappung beim Einstempeln ab; E32 („Äußere Hülle wie heute") verlangt sie. |
| P18 | Neue Spalte `time_entries.auto_closed` (BOOL, Default false): vom Auto-Close gesetzt, von jedem anderen Schreibpfad, der `end_time` setzt, zurückgesetzt. `raw_end_time = 23:59` bleibt (Protokoll), wird aber nie als echter Stempel gelesen: Anerkennen → 400, `RawStampNote` „nicht ausgestempelt – automatisch geschlossen, angerechnet bis 18:15", Anwesenheit (8.3) bis zum wirksamen Ende, Hüllenminuten am Ende zählen nicht als „nicht angerechnet" (P19). Erkennung über die Spalte, nicht über die editierbare Notiz. | 23:59 ist ein synthetischer Wert in einer Spalte, die sonst §16-Nachweis ist; ohne Kennzeichen öffnete Anerkennen das Schlupfloch wieder (16 h angerechnet), das E36/E42 schließen. |
| P19 | „angerechnet" = `net_hours` (nach Pause und `uncredited`). „Nicht angerechnet" eines Eintrags = `uncredited_minutes` + Hüllenminuten (`eff_start − raw_start`, `raw_end − eff_end`; 0 ohne `raw_*`; Endseite bei `auto_closed` ausgenommen). Eine Quelle: `work_window_service.not_credited_minutes(entry)` + Frontend-Zwilling `utils/workBlocks.ts::notCreditedMinutes` (wortgleiche Testfälle). Genutzt von `RawStampNote`, Journal-Summe und Export-Spalte. | Sonst bliebe gekappte Anwesenheit außerhalb der Hülle im §16-Beleg unerklärt (K7: 1:30 h, K15: 5:44 h) — Pflicht 8 nur halb erfüllt (R6, F11). |
| P20 | Sammelzeile bei **jedem** Anlegen und Löschen einer Arbeitszeit-Änderung (auch 0 betroffene Einträge, auch reine Wochenstunden-Änderung); der Dashboard-Hinweis wird aus diesen Sammelzeilen der letzten 30 Tage abgeleitet und erscheint für jede Änderung (auch „ab heute"/zukunftsdatiert, Löschung), mit Neukappungs-Zusatz nur bei n > 0. | Das Protokoll verlangt „a summary row per change"; eine Weisung muss Mitarbeitende erreichen (§ 106 GewO, Art. 5 Abs. 1 lit. a, Art. 13 DSGVO) (F2, R8). |
| P21 | **Anrechnung beantragen:** Mitarbeitende können an einem eigenen geschlossenen Eintrag mit nicht angerechneter Zeit einen Änderungsantrag mit Kennzeichen `request_credit_override` stellen (Begründung Pflicht wie jeder Antrag). Die Antragsprüfung bietet „Genehmigen = Anerkennen" (Pfad 13.3) und zeigt für jeden UPDATE-Antrag auf einen Eintrag mit nicht angerechneter Zeit zusätzlich die Option „genehmigen und anerkennen". | Art. 22 Abs. 3 DSGVO: Eingreifen einer Person, eigener Standpunkt, Anfechtung; ein gleichlautender Antrag würde sonst bei Genehmigung wieder gekappt (R9). |
| P22 | Weicher Code `PRESENCE_WEEKLY_HOURS` (Anwesenheit laut Stempel > 48 h je Kalenderwoche, nur wenn `WEEKLY_HOURS_WARNING` auf angerechneter Zeit nicht schon kam); die 24-Wochen-Auswertung bekommt einen zweiten Wert „Anwesenheit laut Stempel"; die Vorschau der Neukappung nennt geänderte ArbZG-Befunde. | Neukappung darf Verstöße nicht aus Warnungen **und** Berichten verschwinden lassen (Pflicht 4, R5). |
| P23 | **(zur Bestätigung, 19.1 Nr. 5)** Offene Einträge mit Datum < heute im Fenster werden vor der Neukappung per `_close_stale_entry` geschlossen (wie `clock_in` es tut, handelnde Admin als `changed_by`) und danach regulär neu gekappt und protokolliert. „Übersprungen: offen" betrifft damit nur den Eintrag von heute. | Sonst schlösse sie später der Auto-Close unter dem neuen Snapshot — Verlust ohne `wh_reclamp`-Zeile und ohne Klassifikation (F08). |
| P24 | **(zur Bestätigung, 19.1 Nr. 6)** Neue Blöcke (`pause_minutes` int) bleiben in einer neuen Verlaufszeile nur, solange der Modus „Nach Arbeitsblöcken" bleibt (mit abgeleiteten `hours_*`). Ein Wechsel nach „Gleichmäßig"/„Nach Tagen" setzt `blocks = NULL` — auch bei `track_hours=false`; der Dialog nennt das vor dem Speichern. „Gespeicherte Werte bleiben" (E63) heißt: unverändert, solange der Modus nicht gewechselt wird. | Sonst entstünde eine Zeile mit neuen Blöcken neben `use_daily_schedule=False` und fremdem Soll — die Doppelpflege, die E2 abschafft; nach Wiedereinschalten von `track_hours` kappten Blöcke gegen ein Soll aus anderer Quelle (F15). |
| P25 | `earliest_lossless_date` ist durch die **nächste** Änderung begrenzt: liegt es am oder nach deren `effective_from`, ist es `null`, Option 1 wird nicht angeboten, Text „Die Änderung liegt vollständig vor der Änderung ab ‹Datum›; nur rückwirkend mit Begründung oder abbrechen." | Sonst landete die neue Zeile hinter der nächsten und überschriebe ab heute deren Vertrag (F07). |
| P26 | Schutzpaket je Grundtyp: Hilfetext unter „Erfassungsfehler korrigiert" („Falsche Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit."); Bestätigungstext je Typ (12.1); bei „Sonstiges" rote Zusatzwarnung zum Direktionsrecht und eigener Pflicht-Haken `other_reason_risk_confirmed`; jeder Bestätigungstext endet mit dem MiLoG-Verzichtssatz. MiLoG-Warnung zusätzlich bei gesetztem `agreed_monthly_hours`, allgemeiner Minijob-/Mindestlohnsatz bei **jeder** rückwirkenden Verkürzung. | Ein einziger Haken „Fehlerkorrektur oder einvernehmlich" widerspräche bei „Sonstiges" der eigenen Auswahl; Minijobber ohne Opt-in-Flag blieben ohne Warnung (R10, R12). |
| P27 | F1-Angleichungen in `retarget_absence_hours` (9.6) zählen **nicht** als Verkürzung: sie korrigieren eine Doppelanrechnung (Arbeit + volles Tagessoll als Gutschrift am selben Tag). Sie stehen als eigene Vorschauzeile „n Abwesenheiten an Misch-Tagen angeglichen" und lösen bei abgeschlossenem Jahr einen Hinweis aus. Ob sie künftig mitzählen sollen, ist Teil von Frage 19.1 Nr. 1. | Ausdrückliche Entscheidung statt stiller Lücke (F19). |
| P28 | Neue Spalte `change_requests.original_uncredited_minutes` (INT NULL) ergänzt den `original_*`-Snapshot des Antrags. | Der Antrag friert den Vorher-Zustand ein; ohne die Spalte zeigte die Prüfung „vorher angerechnet" falsch, sobald der Eintrag sich ändert (F10). |

---

## 3. Datenmodell

### 3.1 JSON-Form

Kanonisch für `working_hours_changes.blocks` **und** `users.work_blocks`:

```json
[
  {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
  {"blocks": [{"start": "08:00", "end": "13:00"}],                                      "pause_minutes": 0},
  {"blocks": [],                                                                        "pause_minutes": 0},
  {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 30},
  {"blocks": [],                                                                        "pause_minutes": 0}
]
```

- Index 0 = Montag … 4 = Freitag. Immer genau 5 Einträge.
- Zeiten als String `"HH:MM"`, nie als `time`-Objekt, nie mit Sekunden.
- Eine Liste, kein Dict: Int-Schlüssel eines Dicts würden nach einem JSONB-Umlauf zu
  Strings.
- Kein Freitext im JSON (kein `label`) — Anonymisierung muss das JSON nicht anfassen.
- Änderung nur per Neuzuweisung des ganzen Werts (`row.blocks = neue_liste`); eine
  In-place-Mutation erkennt SQLAlchemy nicht und speichert sie nicht.

Altzeile aus Migration 073 (Fenster Mo–Do 07:30–16:30, Fr halboffen ab 07:30):

```json
[
  {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": null},
  {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": null},
  {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": null},
  {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": null},
  {"blocks": [{"start": "07:30", "end": "23:59"}], "pause_minutes": null}
]
```

### 3.2 Spalten

| Tabelle | Spalte | Typ | NULL | Default | Bedeutung |
|---|---|---|---|---|---|
| `working_hours_changes` | `blocks` | `JSON` / `JSONB` | ja | — | Blöcke ab `effective_from`. **NULL = keine Blöcke**, kein Rückfall. |
| `users` | `work_blocks` | `JSON` / `JSONB` | ja | — | Rückfall nur vor der ersten Verlaufszeile; Spiegel der jüngsten Zeile ≤ heute (Sync). |
| `time_entries` | `uncredited_minutes` | `INTEGER` | nein | `0` (server_default `'0'`) | In der Lücke liegende, nicht angerechnete Minuten. Nur serverseitig. |
| `time_entries` | `credit_override` | `BOOLEAN` | nein | `false` (server_default `'false'`) | Eintrag wird nie gekappt („Anerkennen"). |
| `time_entries` | `auto_closed` | `BOOLEAN` | nein | `false` (server_default `'false'`) | Vom Auto-Close geschlossen; `raw_end_time` 23:59 ist dann kein echter Stempel (P18). Jeder andere Pfad, der `end_time` schreibt, setzt es auf `false`. |
| `change_requests` | `request_credit_override` | `BOOLEAN` | nein | `false` (server_default `'false'`) | Antrag „Anrechnung beantragen" (P21). |
| `change_requests` | `original_uncredited_minutes` | `INTEGER` | ja | — | Vorher-Snapshot der nicht angerechneten Lückenminuten (P28). |
| `users` | `scheduled_start_<tag>`, `scheduled_end_<tag>` (10 Spalten) | — | — | — | **entfallen** in 073. |

Modelle: `app/models/working_hours_change.py:28-41`, `app/models/user.py:44-55`,
`app/models/time_entry.py:19-25`. Alle bestehenden Konstruktoren laufen ohne die neuen
Felder (Defaults): `time_entries.py` 304/814, `admin_time_entries.py` 176,
`admin_change_requests.py` 497, `xls_import_service.py` 481,
`create_handbuch_testdata.py` 181, `setup_extended_testdata.py` 391,
`create_test_data.py` 244, `tests/conftest.py:253-266`.

### 3.3 Semantik von NULL

| Wert | Bedeutung | Wirkung Kappung | Wirkung Soll |
|---|---|---|---|
| `blocks` = NULL (Verlaufszeile) | keine Blöcke ab diesem Datum | keine | aus `weekly_hours`/`hours_*` wie bisher |
| `work_blocks` = NULL (User) | keine Blöcke vor der ersten Verlaufszeile | keine | wie bisher |
| Tag mit `"blocks": []` | kein Block an diesem Wochentag | keine | neue Zeile: 0 h; Altzeile: wie gespeichert |
| `pause_minutes` = int | Blöcke sind Soll-Quelle (neue Zeile) | ja | `hours_<tag>` = Σ − Pause (materialisiert) |
| `pause_minutes` = NULL | Altfenster aus 073 | ja | unverändert wie gespeichert |

Eine Zeile ist entweder ganz „neu" (alle fünf `pause_minutes` int) oder ganz „alt" (alle
fünf NULL). Gemischte Zeilen entstehen nicht; der Resolver behandelt eine Zeile mit
mindestens einem NULL als Altzeile.

**Kanonische Normalisierung:** Eine Liste, in der alle fünf Tage `"blocks": []` haben, ist
gleichbedeutend mit NULL. Geschrieben wird sie nie (Migration 5.2 Schritte 5/6 schreiben
NULL, das Schreibschema verlangt mindestens einen Tag mit Blöcken); gelesen wird sie im
Resolver (`get_schedule_for_date` → `blocks=None`) und in allen Vergleichen
(`_comparable_snapshot`, `blocks_changed`, `weekly_hours_segments`) zu NULL normalisiert,
damit NULL und „5× leer" nie als Änderung gelten (sonst Scheinsegment im #415-Text und
gebrochene Byte-Identität, E22).

### 3.4 Validierung (nur Schreibschemas)

Gemeinsame Funktion `app/schemas/validators.py::validate_week_blocks(value)`, aufgerufen
von `UserCreate` und `WorkingHoursChangeCreate`, **nicht** von `UserBase`,
`UserResponse`, `UserListResponse`, `WorkingHoursChangeBase`/`…Response`.

| Regel | Meldung (422, deutsch, über `_schedule_input_error` mit Feld-Label) |
|---|---|
| genau 5 Einträge | „Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet." |
| höchstens 3 Blöcke je Tag | „Mo: höchstens drei Blöcke je Tag." |
| Format `HH:MM`, 00–23 / 00–59 | „Mo, Block 1: Uhrzeit im Format HH:MM angeben." |
| 5-Minuten-Raster | „Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)." |
| Beginn < Ende | „Mo, Block 2: Beginn muss vor dem Ende liegen." |
| sortiert, überlappungsfrei, nicht aneinanderstoßend (Ende_i < Beginn_i+1, P16) | „Mo: Block 2 muss nach dem Ende von Block 1 beginnen; aneinandergrenzende Blöcke bitte als einen Block erfassen." |
| `pause_minutes` int, Raster 5, 0 ≤ Pause < Σ Blockdauer | „Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke." |
| Tag ohne Blöcke → `pause_minutes` = 0 | „Mi: Pause nur an Tagen mit Blöcken." |
| `pause_minutes` NULL im Schreibschema | „Mo: Pause angeben (0, wenn keine)." |
| mindestens ein Tag mit Blöcken | „Mindestens ein Wochentag braucht einen Block." |
| Σ Tagessoll ≤ 60 h | „Die Wochensumme darf 60 Stunden nicht überschreiten." (bestehende Grenze) |

ArbZG-Plausibilität des Plans (§3 > 10 h, §4 über den ganzen Tag, Lücke ≤ 2 × Puffer) ist
**keine** Validierungsregel, sondern ein Hinweis in `block_break_notices` (P9, 11.3).

`_schedule_input_error` (`admin_users.py:1683-1733`) bekommt Labels für verschachtelte
`loc`-Pfade (`("blocks", 0, "blocks", 1, "start")` → „Mo, Block 2, Beginn"); eine
unerwartete `loc`-Form fällt auf den generischen Text zurück statt `IndexError`/500.

Leseschemas: `work_blocks: Optional[Any] = None`, `blocks: Optional[Any] = None` — keine
Prüfung. Altwerte wie `"07:37"`, `"23:59"` oder `"00:00"` werden gelesen und angezeigt.

### 3.5 Raster und Grenzen

- Blockgrenzen und Pause: 5 Minuten (neue Zeilen). Altzeilen tragen beliebige Minuten.
- Größte Endzeit einer neuen Zeile: 23:55. Platzhalter 23:59 gibt es nur in Altzeilen.
- Keine Blöcke über Mitternacht (Ende > Beginn am selben Tag).

### 3.6 Resolver

`calculation_service.Schedule` (`:13-25`) bekommt zwei Felder **ohne** Vorgabewert (P6):

```python
class Schedule(NamedTuple):
    weekly_hours: Decimal
    use_daily_schedule: bool
    day_hours: tuple
    work_days_per_week: int
    blocks: Optional[tuple]        # 5 × tuple[(start_min, end_min), …] oder None
    block_pauses: Optional[tuple]  # 5 × Optional[int]; None-Einträge = Altzeile
```

Konstruktor-Stellen: `calculation_service.py:72` (Verlaufszeile), `:91` (Rückfall
`users.work_blocks`), `admin_users.py:1819` (Vorschau). `get_schedule_for_date` ist die
einzige Lesestelle für Blöcke: aus der Verlaufszeile (NULL → `None`, **kein** Rückfall),
ohne Zeile aus `users.work_blocks`; eine Liste mit fünf leeren Tagen wird zu `None`
normalisiert (3.3). Parse-Cache am ORM-Objekt (Attribut
`_parsed_blocks`, geprüft gegen die Identität des JSON-Werts), damit der Preload-Pfad
(#449) nicht je Tag neu parst.

---

## 4. Soll-Ableitung

### 4.1 Formel (neue Blöcke)

```python
from decimal import Decimal, ROUND_HALF_EVEN

def derive_targets(week_blocks) -> dict:
    hours = []
    for day in week_blocks:                       # Mo … Fr
        total = sum(_min(b["end"]) - _min(b["start"]) for b in day["blocks"])
        net = total - day["pause_minutes"] if day["blocks"] else 0
        hours.append((Decimal(net) / Decimal(60)).quantize(Decimal("0.01"), ROUND_HALF_EVEN))
    return {
        "hours_monday": hours[0], "hours_tuesday": hours[1], "hours_wednesday": hours[2],
        "hours_thursday": hours[3], "hours_friday": hours[4],
        "weekly_hours": sum(hours, Decimal("0")),
        "work_days_per_week": sum(1 for d in week_blocks if d["blocks"]),
        "use_daily_schedule": True,
    }
```

DIE eine Stelle: `app/services/work_blocks_service.py::derive_targets`, genutzt von
`WorkingHoursChangeCreate` (Ableitung), `UserCreate` (Startvertrag) und der Vorschau.
Frontend-Zwilling `utils/workBlocks.ts::deriveTargets` (nur Anzeige, wortgleiche
Testfälle).

Beispiele:

| Blöcke | Pause | Σ | Tagessoll |
|---|---|---|---|
| 08:00–12:00 + 15:00–18:00 | 30 | 7:00 h | 6,50 h |
| 08:00–12:05 | 0 | 4:05 h | 4,08 h (4,0833…) |
| 07:30–12:00 + 13:00–16:25 | 0 | 7:55 h | 7,92 h (7,9166…) |
| — | 0 | 0 | 0,00 h |

Rundung: höchstens 0,005 h (18 s) je Tag Abweichung zwischen Blocksumme und
gespeichertem Tagessoll. Zusätzlich rundet `net_hours` **je Eintrag** auf 2 Stellen
(`round(…, 2)`). Ein exakt nach Blöcken gestempelter Tag ergibt deshalb Saldo 0 bis auf
höchstens 0,005 h × (Anzahl Einträge + 1), bei drei Einträgen also ≤ 0,02 h. Beispiel:
drei Blöcke zu 55 Min, je ein Eintrag → je 0,92 h, zusammen 2,76 h gegen ein Tagessoll von
2,75 h (Test in `test_derive_targets.py`).

### 4.2 Materialisierung

Die abgeleiteten Werte werden beim Speichern der Verlaufszeile in deren Spalten
geschrieben und über `_sync_user_from_change` (`admin_users.py:228`) bei
`effective_from ≤ heute` auf die User-Zeile gespiegelt (`work_blocks` per
`copy.deepcopy`). Ein vom Client mitgeschickter `weekly_hours`/`hours_*`-Wert neben
`blocks` wird mit 422 abgelehnt („Tagesstunden werden aus den Arbeitszeit-Blöcken
abgeleitet."). `get_daily_target_for_date`, `is_vacation_billable_day` und alle
Konsumenten (Karte Anhang B, Gruppe 4) bleiben unverändert.

**Anlegen (`POST /admin/users`) leitet ab und überschreibt, statt mit 422 abzulehnen** —
bewusst anders als der Verlaufs-Endpunkt: `UserBase.weekly_hours` ist ein Pflichtfeld,
das Anlegeformular muss es mitschicken (Präzedenz „Fund E"). Die Ableitung aus
`work_blocks` ist ein `model_validator(mode="after")` in `UserCreate`, im Klassenkörper
**vor** `check_daily_schedule_matches_weekly_hours` definiert (Pydantic führt die
`after`-Validatoren einer Klasse in Definitionsreihenfolge aus; die beiden geerbten
`UserBase`-Validatoren `schemas/user.py:70/74` prüfen keine Stundenwerte). Sie setzt
`use_daily_schedule`, `hours_*`, `weekly_hours` und `work_days_per_week`. Test: abweichende
Clientwerte werden überschrieben, kein 422.

### 4.3 Moduswechsel

| Von → nach | Wirkung ab Wirkungsdatum |
|---|---|
| ohne Blöcke → Blöcke | `use_daily_schedule=True`, `hours_*` abgeleitet, Kappung aktiv |
| Blöcke → „Gleichmäßig" / „Nach Tagen" | `blocks` = NULL, Kappung endet, Soll aus der neuen Eingabe; der Dialog nennt das vor dem Speichern (P24) |
| Blöcke → Blöcke (geändert) | neue Ableitung; Neukappung nur an geänderten Wochentagen |
| Nur Pause geändert | neues Tagessoll (Abwesenheiten werden wie #415 nachgezogen), **keine** Neukappung |
| Altfenster → Blöcke | `pause_minutes` Pflicht; Soll neu abgeleitet (Vorschau zeigt Δ Tagessoll und Δ Saldo) |
| Altfenster, Änderung in „Gleichmäßig"/„Nach Tagen" | Altfenster aus dem **Vorgänger-Snapshot** für `effective_from` wird übernommen (P2), außer `remove_legacy_window=true`. Test: Zeile wird zwischen eine Zeile mit Fenster und eine ohne Fenster eingefügt → übernimmt das Fenster, die Folgezeile bleibt ohne |
| `track_hours=false` | Block-Modus nicht angeboten. Altfenster: nach P2 übernommen. Neue Blöcke: bleiben nur, solange nichts geändert wird; eine Änderung in „Gleichmäßig"/„Nach Tagen" setzt `blocks` = NULL (P24), der Dialog nennt das vor dem Speichern |

### 4.4 Altzeilen

- Altzeilen (`pause_minutes` NULL) entstehen nur durch Migration 073 und durch die
  Übernahme nach P2. Der Dialog schreibt nie selbst neue Altfenster.
- Ihr Soll stammt aus `weekly_hours`/`hours_*` der Zeile, nie aus den Blöcken.
- Im Dialog erscheinen sie als „Arbeitszeit-Fenster (Altbestand, nur Kappung)" mit den
  Aktionen „In Arbeitszeit-Blöcke umwandeln" (öffnet den Block-Modus vorbefüllt, Pause
  leer und Pflicht) und „Fenster entfernen".
- Leseflächen akzeptieren nicht gerasterte Zeiten und die Platzhalter 00:00/23:59.

---

## 5. Migration 073

Datei `backend/alembic/versions/2026_10_08_1200-073_work_blocks.py`,
`revision = "073_work_blocks"` (15 Zeichen ≤ 32), `down_revision = "072_cr_sunday_reason"`.

### 5.1 Vorbedingung: Diagnose auf der Prod-Kopie

Vor der Implementierung zieht der Betreiber eine Kopie der Produktions-DB in eine
Wegwerf-PG18-Instanz und führt als Superuser `praxiszeit` (umgeht FORCE RLS) folgendes
Skript aus (`psql -U praxiszeit -d praxiszeit -f diagnose-073.sql`). Das Ergebnis wird
in Abschnitt 19 nachgetragen.

```sql
-- diagnose-073.sql — rein lesend

-- Q1: Befund je Fenster und Wochentag
SELECT u.tenant_id, u.username, d.nr, d.tag, d.beginn, d.ende,
       CASE
         WHEN d.beginn IS NULL OR d.ende IS NULL           THEN 'halboffen'
         WHEN d.beginn >= d.ende                           THEN 'Beginn>=Ende'
         WHEN EXTRACT(SECOND FROM d.beginn) <> 0
           OR EXTRACT(SECOND FROM d.ende) <> 0             THEN 'Sekunden'
         ELSE 'ok'
       END AS befund
FROM users u
CROSS JOIN LATERAL (VALUES
  (1, 'Mo', u.scheduled_start_monday,    u.scheduled_end_monday),
  (2, 'Di', u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
  (3, 'Mi', u.scheduled_start_wednesday, u.scheduled_end_wednesday),
  (4, 'Do', u.scheduled_start_thursday,  u.scheduled_end_thursday),
  (5, 'Fr', u.scheduled_start_friday,    u.scheduled_end_friday)
) AS d(nr, tag, beginn, ende)
WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
ORDER BY u.tenant_id, u.username, d.nr;

-- Q2: Zusammenfassung je Befund
WITH f AS (
  SELECT CASE
           WHEN d.beginn IS NULL OR d.ende IS NULL THEN 'halboffen'
           WHEN d.beginn >= d.ende THEN 'Beginn>=Ende'
           WHEN EXTRACT(SECOND FROM d.beginn) <> 0 OR EXTRACT(SECOND FROM d.ende) <> 0 THEN 'Sekunden'
           ELSE 'ok'
         END AS befund
  FROM users u
  CROSS JOIN LATERAL (VALUES
    (u.scheduled_start_monday,    u.scheduled_end_monday),
    (u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
    (u.scheduled_start_wednesday, u.scheduled_end_wednesday),
    (u.scheduled_start_thursday,  u.scheduled_end_thursday),
    (u.scheduled_start_friday,    u.scheduled_end_friday)
  ) AS d(beginn, ende)
  WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
)
SELECT befund, COUNT(*) AS fenster FROM f GROUP BY befund ORDER BY befund;

-- Q3: Umfang des Backfills — Konten mit Fenster, Verlaufszeilen, Stundenzählung
SELECT u.tenant_id, u.username, u.track_hours, u.use_daily_schedule,
       (SELECT COUNT(*) FROM working_hours_changes w WHERE w.user_id = u.id) AS verlaufszeilen
FROM users u
WHERE COALESCE(u.scheduled_start_monday, u.scheduled_end_monday,
               u.scheduled_start_tuesday, u.scheduled_end_tuesday,
               u.scheduled_start_wednesday, u.scheduled_end_wednesday,
               u.scheduled_start_thursday, u.scheduled_end_thursday,
               u.scheduled_start_friday, u.scheduled_end_friday) IS NOT NULL
ORDER BY u.tenant_id, u.username;

-- Q4: Fenster kürzer als das (heutige) Tagessoll — informativ, mit E10/E18 unkritisch
SELECT u.username, d.tag,
       ROUND(EXTRACT(EPOCH FROM (d.ende - d.beginn)) / 3600, 2) AS fenster_h,
       ROUND(CASE WHEN u.use_daily_schedule THEN COALESCE(d.std, 0)
                  ELSE u.weekly_hours / NULLIF(u.work_days_per_week, 0) END, 2) AS tagessoll_h
FROM users u
CROSS JOIN LATERAL (VALUES
  ('Mo', u.scheduled_start_monday,    u.scheduled_end_monday,    u.hours_monday),
  ('Di', u.scheduled_start_tuesday,   u.scheduled_end_tuesday,   u.hours_tuesday),
  ('Mi', u.scheduled_start_wednesday, u.scheduled_end_wednesday, u.hours_wednesday),
  ('Do', u.scheduled_start_thursday,  u.scheduled_end_thursday,  u.hours_thursday),
  ('Fr', u.scheduled_start_friday,    u.scheduled_end_friday,    u.hours_friday)
) AS d(tag, beginn, ende, std)
WHERE d.beginn IS NOT NULL AND d.ende IS NOT NULL AND d.beginn < d.ende
  AND EXTRACT(EPOCH FROM (d.ende - d.beginn)) / 3600
      < CASE WHEN u.use_daily_schedule THEN COALESCE(d.std, 0)
             ELSE u.weekly_hours / NULLIF(u.work_days_per_week, 0) END
ORDER BY u.username, d.tag;

-- Q5: Einträge exakt auf der alten Fensterkante ohne Rohstempel
--     (später „nicht erweiterbar", E50)
WITH g AS (
  SELECT t.id AS tenant_id,
         COALESCE((SELECT NULLIF(s.value, '')::int FROM system_settings s
                   WHERE s.tenant_id = t.id AND s.key = 'work_window_grace_minutes'), 15) AS grace
  FROM tenants t
), w AS (
  SELECT u.id AS user_id, u.username, u.tenant_id, d.isodow, d.beginn, d.ende
  FROM users u
  CROSS JOIN LATERAL (VALUES
    (1, u.scheduled_start_monday,    u.scheduled_end_monday),
    (2, u.scheduled_start_tuesday,   u.scheduled_end_tuesday),
    (3, u.scheduled_start_wednesday, u.scheduled_end_wednesday),
    (4, u.scheduled_start_thursday,  u.scheduled_end_thursday),
    (5, u.scheduled_start_friday,    u.scheduled_end_friday)
  ) AS d(isodow, beginn, ende)
  WHERE d.beginn IS NOT NULL OR d.ende IS NOT NULL
)
SELECT w.username,
       COUNT(*) FILTER (WHERE e.raw_start_time IS NULL
                          AND e.start_time = w.beginn - make_interval(mins => g.grace)) AS beginn_auf_kante,
       COUNT(*) FILTER (WHERE e.raw_end_time IS NULL
                          AND e.end_time = w.ende + make_interval(mins => g.grace))     AS ende_auf_kante,
       COUNT(*) FILTER (WHERE e.raw_start_time IS NOT NULL OR e.raw_end_time IS NOT NULL) AS mit_rohstempel
FROM w
JOIN g ON g.tenant_id = w.tenant_id
JOIN time_entries e ON e.user_id = w.user_id AND EXTRACT(ISODOW FROM e.date) = w.isodow
GROUP BY w.username
ORDER BY w.username;

-- Q6: Puffer je Mandant
SELECT t.id, t.name,
       COALESCE((SELECT s.value FROM system_settings s
                 WHERE s.tenant_id = t.id AND s.key = 'work_window_grace_minutes'), '15 (Default)') AS puffer
FROM tenants t ORDER BY t.name;
```

### 5.2 Upgrade-Schritte

1. Spalten anlegen: `users.work_blocks`, `working_hours_changes.blocks`
   (`sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`, nullable);
   `time_entries.uncredited_minutes` (`Integer`, NOT NULL, `server_default="0"`);
   `time_entries.credit_override` und `time_entries.auto_closed` (`Boolean`, NOT NULL,
   `server_default="false"`); `change_requests.request_credit_override` (`Boolean`, NOT
   NULL, `server_default="false"`); `change_requests.original_uncredited_minutes`
   (`Integer`, nullable).
2. Auf der Migrationsverbindung `SET LOCAL app.is_superadmin = 'true'` (Absicherung,
   falls die Migrationsrolle Eigentümerin, aber nicht Superuser ist: FORCE RLS).
3. `SELECT id, tenant_id, username, scheduled_*` aller Konten mit mindestens einem
   gesetzten Fensterwert lesen.
4. Je Konto in Python die kanonische Liste bauen (Regeln 5.3), Diagnosezeilen sammeln.
5. `UPDATE users SET work_blocks = CAST(:j AS JSONB) WHERE id = :id` (auf SQLite ohne
   `CAST`), `:j` = `json.dumps(liste)`; ergibt die Liste fünf leere Tage (z. B. nur
   invertierte Fenster), wird für dieses Konto **nichts** geschrieben —
   `users.work_blocks` bleibt NULL.
6. `UPDATE working_hours_changes SET blocks = CAST(:j AS JSONB) WHERE user_id = :id` —
   **jede** Verlaufszeile des Kontos; bei fünf leeren Tagen ebenfalls nichts (alle
   Verlaufszeilen bleiben NULL, 3.3).
7. Zählprobe: Anzahl aktualisierter Konten = Anzahl der Konten aus Schritt 3 mit
   **mindestens einem nicht leeren Tag**, sonst Diagnosezeile „Abweichung … (RLS?)". Kein
   Abbruch.
8. `UPDATE time_entries SET auto_closed = true` für Einträge mit einer Protokollzeile
   `source='auto_close'` **und** `end_time = '23:59'` (vor 073 kappte der Auto-Close nie,
   ein später korrigiertes Ende fällt damit heraus). Reines Kennzeichen; `net_hours`
   unverändert.
9. Diagnoseblock ausgeben (5.4).
10. Die zehn `scheduled_*`-Spalten löschen.

Kein Schritt kappt Einträge neu, setzt `uncredited_minutes` oder berührt `hours_*`,
`weekly_hours`, `use_daily_schedule`, `work_days_per_week`.

Wiederholbarkeit: Nach dem Restore eines alten Dumps läuft 073 erneut; der Backfill ist
deterministisch und hängt nur von den `scheduled_*`-Werten des Dumps ab.

### 5.3 Backfill-Regeln je Bestandsfalle

| Fall (je Wochentag) | Ergebnis im Tag | Diagnose |
|---|---|---|
| beide NULL | `{"blocks": [], "pause_minutes": null}` | — |
| Beginn und Ende gesetzt, Beginn < Ende | `{"blocks": [{"start": B, "end": E}], "pause_minutes": null}` | — |
| nur Beginn gesetzt | Ende = `"23:59"` | „halboffen: Mo ab 07:30 → Ende 23:59 (Kappung unverändert)" |
| nur Ende gesetzt | Beginn = `"00:00"` | „halboffen: Mo bis 16:30 → Beginn 00:00 (Kappung unverändert)" |
| Sekunden ≠ 0 | auf Minute abgeschnitten (`replace(second=0)`), danach weiter wie oben | „Sekunden abgeschnitten: Mo 07:30:45 → 07:30" |
| Beginn ≥ Ende (nach Abschneiden) | `{"blocks": [], "pause_minutes": null}` | „nicht übernommen: Mo 17:00–08:00 (Beginn nicht vor Ende); Einträge an diesem Wochentag werden künftig nicht mehr gekappt" |
| Fenster kürzer als Tagessoll, Tagessoll 0, Tagessoll außerhalb Raster | wie „gesetzt" | keine — mit `pause_minutes` NULL ohne Soll-Wirkung (E10/E18) |

Die Platzhalter verhalten sich identisch: `_shift(23:59, +g)` wird heute schon auf 23:59
begrenzt, `_shift(00:00, −g)` auf 00:00.

### 5.4 Diagnose-Ausgabe

```
*** HINWEIS (Migration 073) ***
Arbeitszeit-Fenster wurden in Arbeitszeit-Blöcke übernommen: 7 Konten, 23 Verlaufszeilen.
Besonderheiten (bitte im Dialog „Arbeitszeit anpassen…" prüfen):
  - mfa.mueller (Mandant 0000…0001): halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)
  - azubi.schmidt (Mandant 0000…0001): nicht übernommen: Mi 17:00–08:00 (Beginn nicht vor Ende) …
  - …
*** ENDE HINWEIS ***
```

Ohne Besonderheiten nur die Zählzeile. Die Ausgabe nutzt `print` wie 067 (landet im
Update-Log nativ und im Container-Log bei Docker).

### 5.5 Downgrade

1. Die zehn `scheduled_*`-Spalten (`Time`, nullable) anlegen.
2. Je Konto mit `work_blocks`: je Tag **erster Block** → `scheduled_start_<tag>` /
   `scheduled_end_<tag>`. Platzhalter `"00:00"` als Beginn und `"23:59"` als Ende werden
   zu NULL zurück (Round-Trip der halboffenen Fenster).
3. Diagnose:
   - Konten mit mehr als einem Block an einem Tag (Name, Tag, verworfene Blöcke) —
     nach dem Downgrade kappt das 072-Fenster am Ende des ersten Blocks;
   - Einträge mit `uncredited_minutes > 0` je Konto (Anzahl, Summe in h) — deren
     angerechnete Zeit steigt um diese Summe;
   - Einträge mit `credit_override = true` je Konto (Anzahl);
   - offene Anträge mit `request_credit_override = true` (Anzahl) — sie werden nach dem
     Downgrade wie gewöhnliche UPDATE-Anträge genehmigt, also wieder gekappt.
4. Spalten `uncredited_minutes`, `credit_override`, `auto_closed` (`time_entries`),
   `request_credit_override`, `original_uncredited_minutes` (`change_requests`),
   `work_blocks`, `blocks` löschen.

Verluste: die Verlaufshistorie der Blöcke (Fenster waren nie historisiert), alle
Blöcke ab dem zweiten, die Nichtanrechnung der Lücken, alle Anerkennungen, das
Auto-Close-Kennzeichen und die Anrechnungs-Anträge.

---

## 6. Kappung

### 6.1 Algorithmus

`app/services/work_window_service.py` (`:51-71`, `:74-78`, `:180-216` werden ersetzt):

```python
class ClampResult(NamedTuple):
    eff_start: Optional[time]
    eff_end: Optional[time]
    raw_start: Optional[time]
    raw_end: Optional[time]
    uncredited_minutes: int


def get_scheduled_blocks(db, user, d, *, wh_changes=None,
                         soll_free_dates=None) -> list[tuple[int, int]]:
    """Blöcke des Datums in Minuten seit Mitternacht, sortiert.
    [] am Wochenende, ohne Blöcke im datumsaufgelösten Snapshot, an Feiertagen
    und an freien Sondertagen (#484, _is_soll_free_weekday bleibt).
    wh_changes / soll_free_dates: optional vorgeladen (Muster #449); ohne sie
    fragt die Funktion je Aufruf den Resolver bzw. die Feiertage ab."""
    if d.weekday() > 4:
        return []
    sched = calculation_service.get_schedule_for_date(db, user, d, wh_changes)
    if sched.blocks is None or not sched.blocks[d.weekday()]:
        return []
    if (d in soll_free_dates) if soll_free_dates is not None \
            else _is_soll_free_weekday(db, user, d):
        return []
    return list(sched.blocks[d.weekday()])


def has_blocks(db, user, d, **preload) -> bool:
    return bool(get_scheduled_blocks(db, user, d, **preload))


def clamp_applies(db, user, d, *, credit_override: bool, **preload) -> bool:
    """Kappt clamp an diesem Tag überhaupt? (XLS-Gate statt has_blocks allein, E38)."""
    return (getattr(user, "track_hours", True) and not credit_override
            and has_blocks(db, user, d, **preload))


def credit_gaps(blocks, grace) -> list[tuple[int, int]]:
    """Innere Lücken, um den Puffer an BEIDEN Rändern geschrumpft (E5).
    Eine Lücke ≤ 2 × Puffer verschwindet."""
    gaps = []
    for (_, end_a), (start_b, _) in zip(blocks, blocks[1:]):
        gs, ge = end_a + grace, start_b - grace
        if ge > gs:
            gaps.append((gs, ge))
    return gaps


def _overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def clamp(db, user, d, start, end, grace, *, credit_override: bool,
          wh_changes=None, soll_free_dates=None) -> ClampResult:
    if credit_override or not getattr(user, "track_hours", True):
        return ClampResult(start, end, None, None, 0)
    blocks = get_scheduled_blocks(db, user, d, wh_changes=wh_changes,
                                  soll_free_dates=soll_free_dates)
    if not blocks:
        return ClampResult(start, end, None, None, 0)

    floor = _shift_min(blocks[0][0], -grace)      # begrenzt auf [00:00, 23:59]
    ceil = _shift_min(blocks[-1][1], +grace)
    eff_start, eff_end, raw_start, raw_end = start, end, None, None
    if start is not None and _min(start) < floor:
        eff_start, raw_start = _t(floor), start
    if end is not None and _min(end) > ceil:
        eff_end, raw_end = _t(ceil), end

    # Kollaps außerhalb der Hülle — unverändert seit #201
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return ClampResult(start, start, start, end, 0)
    if eff_end is None:                            # offener Eintrag (P17: Hülle gilt)
        return ClampResult(eff_start, None, raw_start, None, 0)
    if eff_start is None:                          # Teil-Update ohne Beginn
        return ClampResult(None, eff_end, None, raw_end, 0)

    s, e = _min(eff_start), _min(eff_end)
    uncredited = sum(_overlap(s, e, gs, ge) for gs, ge in credit_gaps(blocks, grace))
    return ClampResult(eff_start, eff_end, raw_start, raw_end, uncredited)
```

- `_min(t)` = `t.hour * 60 + t.minute` (Sekunden werden ignoriert wie in `_net_hours`).
- Der Beginn wird **nur** an der Hülle verschoben, nie in einer Lücke (E33).
- `credit_override` ist pflichtiges Schlüsselwort-Argument (P6); jede Aufrufstelle
  entscheidet ausdrücklich.
- `gap_segments(db, user, d, start, end, grace, *, credit_override) -> list[int]`
  liefert dieselben Überlappungen als Liste je Lücke (für §4, XLS-Auto-Pause und
  StampWidget); `sum(gap_segments(...)) == clamp(...).uncredited_minutes` ist Test-Invariante.
- `start=None` bei gesetztem Ende (Teil-Updates der CR-Pfade `_in_start`/`_in_end`,
  Admin-Teil-Update) liefert ein Ergebnis ohne Lückenberechnung statt `AttributeError`
  (Test in `test_clamp_blocks.py`).
- Weitere Helfer im selben Modul (je eine Quelle, Frontend-Zwilling in
  `utils/workBlocks.ts` mit wortgleichen Testfällen):
  - `not_credited_minutes(entry) -> int` (P19): `uncredited_minutes` + Hüllenminuten
    (`eff_start − raw_start`, `raw_end − eff_end`; 0 ohne `raw_*`; Endseite bei
    `auto_closed` ausgenommen). K7 → 240, K8 → 120, K15 → 150, K20 → 195.
  - `presence_minutes(entry) -> int` (8.3): `(raw_end or end) − (raw_start or start)
    − break_minutes`; bei `auto_closed` bis zum wirksamen Ende `end_time`; offene
    Einträge zählen nicht.

`net_hours` (`models/time_entry.py:36-57` und `:59-80`):

```python
net = duration_hours - self.break_minutes / 60.0 - (self.uncredited_minutes or 0) / 60.0
return Decimal(str(max(round(net, 2), 0)))
```

SQL-Ausdruck zusätzlich `- func.coalesce(cls.uncredited_minutes, 0) / 60.0`. Das
`or 0` deckt transiente Einträge vor dem `flush` ab. Der SQL-Ausdruck rundet wie bisher
**nicht** je Zeile (eine Rundung dort veränderte bestehende SQL-Summen und bräche die
Byte-Identität, E22); die Parität Python ↔ SQL gilt deshalb mit Toleranz
n × 0,005 h (17.3).

### 6.2 Warntext

`clamp_warning_text` / `clamp_warning` (`:90-146`, `:169-177`) bekommen die Signatur
`clamp_warning(db, user, d, result: ClampResult, grace, *, for_employee: bool) ->
Optional[str]` und lösen die Lücken selbst auf. Code-Präfix bleibt `WORK_WINDOW_CLAMPED`.
`for_employee=True` (Mitarbeiterpfade `clock_in`, `clock_out`, `create_time_entry`,
`update_time_entry`) hängt an die **Lückentexte geschlossener Einträge** (nicht an den
byte-identischen Hülle-Text, nicht an „Einstempeln in der Lücke") den Satz „Haben Sie in dieser Zeit gearbeitet, beantragen Sie die Anrechnung
(Zeiterfassung → Eintrag → „Anrechnung beantragen")." an (P21); Admin-Pfade übergeben
`False`.

| Fall | Text (ohne Code-Präfix) |
|---|---|
| nur Hülle gekappt | unverändert (byte-identisch, in der Doku zitiert): „Die eingetragene Zeit wurde auf das hinterlegte Arbeitszeit-Fenster gekappt (Beginn 07:37 → 07:45; Puffer 15 Minuten). Angerechnet wird die gekappte Zeit; die ursprüngliche Eingabe bleibt als Rohstempel gespeichert." |
| Kollaps außerhalb der Hülle | unverändert |
| nur Lücke | „Zwischen den Arbeitsblöcken (12:15–14:45, Puffer 15 Minuten eingerechnet) werden 2:30 h nicht angerechnet. Die gestempelte Zeit bleibt unverändert gespeichert." |
| Hülle und Lücke | Hülle-Satz wie oben, ergänzt um „ Zusätzlich werden zwischen den Arbeitsblöcken (12:15–14:45) 2:30 h nicht angerechnet." |
| ganz in der Lücke (angerechnet 0, `uncredited` > 0) | „Die eingetragene Zeit (12:30–14:30) liegt vollständig zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet werden 0 Stunden. Die gestempelte Zeit bleibt gespeichert." |
| Einstempeln in der Lücke (offen) | „Eingestempelt zwischen zwei Arbeitsblöcken (Lücke 12:15–14:45, Puffer 15 Minuten) — angerechnet wird erst ab 14:45." |

Stunden im Text im Format H:MM (`_hm(minuten)`), Lücken als „HH:MM–HH:MM".

### 6.3 Sonderfälle mit erwarteten Werten

Blöcke Mo 08:00–12:00 + 15:00–18:00, Pause im Snapshot 0, Puffer g = 15 Min →
Hülle 07:45–18:15, Lücke nach Schrumpfung 12:15–14:45. Pause des Eintrags 0, sofern
nicht anders angegeben. Die Spalte „Meldung" listet **alle** erwarteten Codes vollständig
(Fixture für Backend- und Frontend-Tests, 17.3); `WORK_WINDOW_CLAMPED` steht mit dem Fall
aus 6.2 in Klammern. „nicht angerechnet" = `not_credited_minutes` (P19).

| Nr | Fall | Eingabe | `start`/`end` gespeichert | `raw_*` | `uncredited` | `net_hours` | nicht angerechnet | Meldung |
|---|---|---|---|---|---|---|---|---|
| K1 | durchgestempelt | 08:00–18:00 | 08:00–18:00 | – / – | 150 | 7,50 | 150 | `WORK_WINDOW_CLAMPED` (Lücke 2:30 h); `PRESENCE_BREAK` |
| K2 | Einstempeln 13:00 | 13:00–(offen) | 13:00–– | – | 0 | 0,00 | 0 | `WORK_WINDOW_CLAMPED` (Einstempeln in der Lücke) |
| K2b | … später Ausstempeln 18:00 | 13:00–18:00 | 13:00–18:00 | – / – | 105 | 3,25 | 105 | `WORK_WINDOW_CLAMPED` (Lücke 1:45 h) |
| K3 | ganz in der Lücke | 12:30–14:30 | 12:30–14:30 | – / – | 120 | 0,00 | 120 | `WORK_WINDOW_CLAMPED` („vollständig zwischen zwei Arbeitsblöcken") |
| K4 | Ausstempeln 12:05 | 08:00–12:05 | 08:00–12:05 | – / – | 0 | 4,08 | 0 | keine |
| K5 | Ausstempeln 12:30 | 08:00–12:30 | 08:00–12:30 | – / – | 15 | 4,25 | 15 | `WORK_WINDOW_CLAMPED` (Lücke 0:15 h) |
| K6 | Lücke ≤ 2g (Blöcke 08:00–12:00 + 12:30–16:00) | 08:00–16:00 | 08:00–16:00 | – / – | 0 | 8,00 | 0 | §4 hart wie heute (30 Min fehlen: `BREAK_WARNING` bzw. 400/202); Plan-Hinweis P9 (b) im Dialog |
| K7 | Hülle und Lücke | 07:00–19:00 | 07:45–18:15 | 07:00 / 19:00 | 150 | 8,00 | 240 | `WORK_WINDOW_CLAMPED` (Hülle + Lücke); `PRESENCE_DAILY_HOURS` (12 h); `PRESENCE_BREAK` |
| K8 | Kollaps vor der Hülle | 05:00–07:00 | 05:00–05:00 | 05:00 / 07:00 | 0 | 0,00 | 120 | `WORK_WINDOW_CLAMPED` (Kollaps, unverändert) |
| K9 | Pause und Lücke | 08:00–18:00, Pause 30 | 08:00–18:00 | – / – | 150 | 7,00 | 150 | `WORK_WINDOW_CLAMPED` (Lücke 2:30 h); `BREAK_IN_GAP`; `PRESENCE_BREAK` (9:30 h Anwesenheit, 30 Min erfasst < 45) |
| K10 | `credit_override` | 08:00–18:00, Pause 45 | 08:00–18:00 | – / – | 0 | 9,25 | 0 | `DAILY_HOURS_WARNING` (wie ohne Blöcke) |
| K11 | Feiertag auf Montag (Ostermontag) | 08:00–18:00, Pause 45 | 08:00–18:00 | – / – | 0 | 9,25 | 0 | `HOLIDAY_WORK`, `DAILY_HOURS_WARNING` (wie heute) |
| K12 | Sonntag | 08:00–18:00, Pause 45 | 08:00–18:00 | – / – | 0 | 9,25 | 0 | `SUNDAY_WORK`, `DAILY_HOURS_WARNING` (wie heute) |
| K13 | `track_hours=false` | 08:00–18:00, Pause 45 | 08:00–18:00 | – / – | 0 | 9,25 | 0 | `DAILY_HOURS_WARNING` (wie ohne Blöcke) |
| K14 | offen (`end=None`) | 08:00–(offen) | 08:00–– | – | 0 | 0,00 | 0 | keine |
| K15 | Auto-Close nach Mitternacht | 08:00–(offen) | 08:00–18:15 | – / 23:59 | 150 | 7,75 | 150 | keine Warnung; Audit `auto_close`; `auto_closed = true` (P18) |
| K16 | Einstempeln 14:30, Aus 18:00 | 14:30–18:00 | 14:30–18:00 | – / – | 15 | 3,25 | 15 | Einstempeln: `WORK_WINDOW_CLAMPED` (in der Lücke); Ausstempeln: `WORK_WINDOW_CLAMPED` (Lücke 0:15 h) |
| K17 | Drei Blöcke 07:00–10:00 + 11:00–13:00 + 16:00–19:00 (Lücken 10:15–10:45, 13:15–15:45) | 07:00–19:00 | 07:00–19:00 | – / – | 30 + 150 = 180 | 9,00 | 180 | `WORK_WINDOW_CLAMPED` (Lücke 3:00 h); `DAILY_HOURS_WARNING` (9,00 > 8); `PRESENCE_DAILY_HOURS` (12 h); `PRESENCE_BREAK` |
| K18 | Halbtags-Sondertag 24.12. (Mo) | 08:00–18:00 | 08:00–18:00 | – / – | 150 | 7,50 | 150 | wie K1 — Blöcke gelten (Sondertag hat Soll) |
| K19 | kurze Blöcke 08:00–10:00 + 15:00–18:00 (Lücke 10:15–14:45) | 08:00–18:00 | 08:00–18:00 | – / – | 270 | 5,50 | 270 | `WORK_WINDOW_CLAMPED` (Lücke 4:30 h); `PRESENCE_BREAK` (10 h Anwesenheit ohne Pause; angerechnet 5:30 h, die harte §4-Prüfung verlangt keine Pause) |
| K20 | Einstempeln vor der Hülle (P17) | 07:00–(offen), später Aus 18:00 | 07:45–18:00 | 07:00 / – | 0, nach dem Ausstempeln 150 | 7,75 | 195 | Einstempeln: wie heute (#201, Beginn 07:45, `EARLY_START`); Ausstempeln: `WORK_WINDOW_CLAMPED` (Lücke 2:30 h); `PRESENCE_DAILY_HOURS` (11 h); `PRESENCE_BREAK` |
| K21 | Pause genügt trotz Lücke | 08:00–18:00, Pause 45 | 08:00–18:00 | – / – | 150 | 6,75 | 150 | `WORK_WINDOW_CLAMPED` (Lücke 2:30 h); `BREAK_IN_GAP`; **kein** `PRESENCE_BREAK` (9:15 h Anwesenheit, 45 Min erfasst) |

---

## 7. Schreibpfade

### 7.1 Aufrufstellen

Für alle schreibenden Zeilen (1–6, 8, 9, 12, 13 und die Anerkennung) gilt P5: erste
Anweisung ist `lock_user_row(db, tenant_id, owner_id)`, vor `get_grace_minutes`,
Snapshot-Auflösung und `clamp`; erst danach werden Eintragszeilen mit `with_for_update`
geladen. Jeder Pfad außer dem Auto-Close, der `end_time` schreibt, setzt `auto_closed =
false` (P18).

| Nr | Stelle | Funktion | Änderung |
|---|---|---|---|
| 1 | `routers/time_entries.py:300` | `clock_in` | Sperre besteht (`:267`). `ClampResult` entpacken, `credit_override=False`; Insert (`:304-313`) mit `uncredited_minutes=0`; Einstempeln in der Lücke → `WORK_WINDOW_CLAMPED` (Text „Einstempeln in der Lücke"); vor der Hülle wie heute (P17, K20): `EARLY_START` (`:319-326`) unverändert nur bei `raw_start` (vor dem ersten Block). |
| 2 | `routers/time_entries.py:403` | `clock_out` | Neu `lock_user_row` vor dem Lesen des offenen Eintrags (P5); `credit_override=open_entry.credit_override`; `end_time`, `raw_end_time`, `uncredited_minutes` schreiben (`:429-432`); §3 daily (`:408-417`), §4 (`:461-489`), weekly (`:505-514`) und Nacht (`:518-526`) mit `uncredited`/Lückensegmenten; Warnung (`:457-459`) über `clamp_warning(…, for_employee=True)`; Anwesenheits-Warnungen (Abschnitt 8). |
| 3 | `routers/time_entries.py:655` | `create_time_entry` | Neu `lock_user_row` (P5). `uncredited` in Insert (`:814-826`), §3 (`:685-698`), §4/202 (`:705-760`), Waiver (`:772-782`), weekly (`:785-794`); Warnung (`:768-770`, `for_employee=True`). Der 202-Antrag speichert weiter die **rohen** Zeiten. |
| 4 | `routers/time_entries.py:990` | `update_time_entry` (MA) | Neu `lock_user_row` (P5). Anerkannter Eintrag (`credit_override`) → **409** „Anerkannter Eintrag – Änderung bitte per Änderungsantrag." (P3), vor jeder Änderung. Neukappungs-Gate (`:998-1004`) um `"date"` erweitern (E39); `uncredited` neu, sobald `start_time`, `end_time` oder `date` geschrieben wird. **Warn-Gate** (`:1121-1129`, heute nur bei `start_time`/`end_time` im Payload und nicht `_resubmitted_unchanged`) ebenfalls um `date` erweitern, analog `_times_written` im Admin-Pfad — sonst kappt ein reiner Datumswechsel still (#462-Klasse). `uncredited_minutes`/`credit_override`/`auto_closed` nie über die generische `setattr`-Schleife (`:911-913`). |
| 5 | `routers/admin_time_entries.py:88` | `admin_create_time_entry` | Neu `lock_user_row` (P5). `uncredited` setzen und an §4 (`:122-136`), §3 (`:139-150`), weekly (`:156-164`), Nacht (`:167-174`) durchreichen; Insert (`:176-190`). |
| 6 | `routers/admin_time_entries.py:293` | `admin_update_time_entry` | Neu `lock_user_row` (P5; `user_id` des Eintrags vorab ohne Sperre lesen, dann sperren, dann Eintrag laden). `uncredited` aus dem endgültig gespeicherten Paar, wenn `start`, `end` oder `_times_affected`; `credit_override=entry.credit_override` (bleibt gesetzt, P3); §4/§3/weekly (`:339-385`). |
| 7 | `routers/admin_change_requests.py:387` | `review_change_request`, Vorprüfung | Sperre besteht (`:235`, auch Bulk). `uncredited` an §3 (`:391-404`) und §4 (`:406-419`); sonst scheitert die Genehmigung regulärer Teilschicht-Anträge (auch in `bulk_review_change_requests`). Schreibt selbst keinen Eintrag. |
| 8 | `routers/admin_change_requests.py:488` | CREATE-Zweig | `uncredited` in den `TimeEntry` (`:497-511`); Warnung über `clamp_warning(…, for_employee=False)`, fließt über `:969-974` und Bulk (`:1084-1092`). |
| 9 | `routers/admin_change_requests.py:535` | UPDATE-Zweig | `uncredited` beim Übernehmen (`:559-575`); `credit_override` **bleibt** (P3), die Antragsprüfung zeigt dazu den Hinweis; `request_credit_override` bzw. „genehmigen und anerkennen" → nach dem Übernehmen Pfad 13.3 Schritte 3–6 (P21). |
| 10 | `routers/admin_change_requests.py:1019` | Nachprüfung nach dem Commit | `uncredited` an `_calculate_daily/weekly_net_hours` (`:1022`, `:1044`); `exclude_entry_id=cr.time_entry_id` (E41). Schreibt selbst keinen Eintrag. |
| 11 | `services/xls_import_service.py:220` | `parse_xls` (Vorschau) | `ImportedEntry.uncredited_minutes` (nur Anzeige); Auto-Pause-Rest (7.4); Vorschau-Warntext über `clamp_warning_text`. Kappungsnotiz-Gate (`:268`, heute nur `raw_start_t is not None or raw_end_t is not None`) → `r.raw_start or r.raw_end or r.uncredited_minutes > 0`, sonst bekommen reine Lückenfälle (K1) keinen Hinweis. Inline-ArbZG `_check_arbzg` (`:59-158`) bekommt `uncredited` und die Lückensegmente (8.2); bei anerkanntem Zieleintrag Hinweis „Eintrag ist anerkannt – die neuen Zeiten werden ungekappt angerechnet" (P3). |
| 12 | `services/xls_import_service.py:416` | `_execute_import_inner` | Neu `lock_user_row` der Zielperson einmal am Anfang (P5). `_hat_fenster` (`:412-414`) → `clamp_applies(db, user, d, credit_override=…)` (E38; prüft zusätzlich `track_hours` und `credit_override`, sonst löschte `track_hours=false` + Blöcke ein mitgeliefertes `raw_*`); `uncredited` und Auto-Pause serverseitig neu; beide Zweige: Überschreiben (`:455-478`, `credit_override` **bleibt**, P3) und Neuanlage (`:481-506`). |
| 13 | `routers/time_entries.py:165` | `_close_stale_entry` (Aufrufer `:223`, `:281`, `:386`) | Über `clamp(entry.start_time, 23:59, credit_override=entry.credit_override)`: `end_time` = Hülle, `raw_end_time` = 23:59 (wenn gekappt), `uncredited`, `auto_closed = true` (P18); Audit `source="auto_close"` unverändert. Ohne Blöcke bleibt 23:59 ungekappt (wie heute), `auto_closed = true`. Aufrufer `:223` (`GET /clock-status`, Stale-Zweig) nimmt vorher die Ankersperre und liest den offenen Eintrag danach neu (P5); `:281` (`clock_in`) und `:386` (`clock_out`) liegen hinter ihrer Sperre. |
| 14 | **neu** `routers/change_requests.py:194-232, 270-283, 289-331` | `create_change_request` (MA-Antrag) | §3/§4/§6/48 h mit `clamp` + `uncredited` prüfen (E40), weiterhin roh speichern; `original_uncredited_minutes` (P28) im Snapshot setzen; neues Feld `request_credit_override` (P21, nur UPDATE auf einen eigenen geschlossenen Eintrag mit `not_credited_minutes > 0`, nicht anerkannt, nicht `auto_closed` ohne korrigiertes Ende). |
| 15 | **neu** `services/work_window_service.py::reclamp_time_entries` | Rückwirkung | Abschnitt 9. |
| 16 | **neu** `routers/admin_time_entries.py` `POST /time-entries/{id}/credit-override` | Anerkennen | Abschnitt 13. |

Gemeinsame Netto-Helfer (`time_entries.py:46-57, 60-85, 88-119`):
`_net_hours(st, et, brk, uncredited)` und
`_calculate_daily/weekly_net_hours(…, uncredited_minutes: int, …)` — `uncredited_minutes`
ist **Pflichtparameter**; bestehende Einträge des Tages/der Woche tragen ihr gespeichertes
`e.uncredited_minutes` bei. Betroffen sind alle 17 Aufrufstellen (`time_entries` 408,
505, 685, 785, 1014, 1149, 1161; `admin_time_entries` 139, 156, 359, 376;
`admin_change_requests` 391, 1022, 1044; `change_requests` 218, 297, 321). Ohne das ergäbe
„gestempelt 08:00–18:30, gekappt auf 18:15" 10,25 h und HTTP 422, obwohl angerechnet nur
7,75 h sind.

Schemas (`schemas/time_entry.py:23-75`, `ClockOutRequest`, `ChangeRequestCreate`,
`ImportedEntry`-Eingabe): `uncredited_minutes`, `credit_override` und `auto_closed` sind
**nie** Eingabefelder (einzige neue Eingabe ist `ChangeRequestCreate.request_credit_override`,
P21). `TimeEntryResponse`/`ClockStatusResponse` (`:84-109`, `:124-127`) tragen
`uncredited_minutes: int = 0`, `credit_override: bool = False`, `auto_closed: bool = False`
und `not_credited_minutes: int = 0` (P19) nur lesend.

### 7.2 Mitbehobene Bestandsfehler (Protokoll)

| Fehler | Fundstelle | Behebung |
|---|---|---|
| Reiner Datumswechsel (MA) kappt nicht neu | `time_entries.py:998-1004` | `"date"` ins Gate (E39) |
| MA-Antrag prüft roh, Genehmigung gekappt | `change_requests.py:194-331` | Antrag validiert mit `clamp` + `uncredited` (E40) |
| CR-Nachprüfung zählt den Eintrag doppelt | `admin_change_requests.py:1022/1044` | `exclude_entry_id=cr.time_entry_id` (E41) |
| Auto-Close rechnet den Abend voll an | `time_entries.py:165-205` | über `clamp` (E36/E42); Hinweis in den Release-Notes |

### 7.3 Nebenbefunde im umgebauten Code (P10)

| Fehler | Fundstelle | Behebung |
|---|---|---|
| `validate_daily_break` ohne `tenant_id`-Filter | `services/break_validation_service.py:13-58` | Filter ergänzen (Signatur ändert sich ohnehin) |
| XLS-§5 prüft gegen die gekappte Endzeit statt Rohstempel | `xls_import_service.py:236-245, 303` | `raw_end or end` wie `rest_time_service` |
| XLS-Abfragen ohne F-026-Filter | `xls_import_service.py:182, 238, 281` | `TimeEntry.tenant_id == …` ergänzen |

### 7.4 XLS-Auto-Pause

`_calc_break_minutes(start, end)` (`:46-55`) wird zu
`_calc_break_minutes(eff_start, eff_end, segments)`:

```python
credited_gross = (_min(eff_end) - _min(eff_start)) - sum(segments)
required = 45 if credited_gross > 9 * 60 else 30 if credited_gross > 6 * 60 else 0
covered = sum(s for s in segments if s >= 15)
rest = max(0, required - covered)
return 15 if 0 < rest < 15 else rest       # §4 Satz 2: Abschnitte ≥ 15 Min
```

Beispiel K1 als Import (08:00–18:00): angerechnete Bruttozeit 7:30 h → Bedarf 30, gedeckt
150 → Auto-Pause 0 (heute 45 → Doppelabzug von 45 Min). `/confirm` übernimmt vom Client
weder `raw_*` noch `uncredited` noch Pause, sondern rechnet neu (Manipulationsschutz wie
`raw_*`). `ImportXls.tsx` zeigt das Netto aus der Server-Vorschau (`PreviewResponse`,
`routers/import_xls.py:29`, um `net_hours` und `uncredited_minutes` erweitert) statt
clientseitig zu rechnen.

---

## 8. ArbZG-Prüfungen

### 8.1 Übersicht

| Prüfung | Basis | Art | Änderung |
|---|---|---|---|
| §3 10 h (`DAILY_HOURS_HARD`) | angerechnete Zeit (`net_hours` mit `uncredited`) | hart (400); beim Ausstempeln Warnung (wie heute) | nur `uncredited` einrechnen |
| §3 8 h (`DAILY_HOURS_WARNING`) | angerechnet | weich | dito |
| §3 48 h/Woche (`WEEKLY_HOURS_WARNING`) | angerechnet | weich | dito |
| §4 Pausen (`BREAK_WARNING`, 202-Waiver) | angerechnet; Lückensegmente ≥ 15 Min zählen als Pausenabschnitt | hart wie heute | `validate_daily_break` kennt Lückensegmente |
| §6 Abs. 2 Nachtarbeitnehmer 8 h | angerechnet; Erkennung auf gespeicherten Zeiten | weich | nur `uncredited` |
| §5 Ruhezeit (`REST_TIME_WARNING`) | Rohstempel (`raw_* or start/end`) | weich | **keine**; Neukappung setzt `raw_*` nie aus gekappten Werten |
| 24-Wochen-Durchschnitt (`reports.py:957-1080`) | `net_hours` **und** zusätzlich Anwesenheit laut Stempel | Bericht | bestehender Wert folgt dem Hybrid (Neukappung ändert ihn rückwirkend); **neu** ein zweiter, eigens gekennzeichneter Wert „Anwesenheit laut Stempel" (Σ `presence_minutes`) je Woche und im Durchschnitt, angehängt an die Antwort (`presence_hours`, `presence_average`) und als eigene Spalte in `admin/Reports.tsx` — den ändert keine Neukappung (P22). Exportdateien unverändert (Rohstempel in Dateien: Folgeticket) |
| **neu** `PRESENCE_DAILY_HOURS` | Rohstempel | weich | 8.3 |
| **neu** `PRESENCE_BREAK` | Rohstempel | weich | 8.3 |
| **neu** `PRESENCE_WEEKLY_HOURS` | Rohstempel | weich | 8.3 (P22) |
| **neu** `BREAK_IN_GAP` | Eintrag | weich | 8.4 |
| XLS-Vorschau `_check_arbzg` (`xls_import_service.py:59-158`) | heute Brutto aus `start`/`end` (`:83`, `:92`) | Zeilenwarnung | auf angerechnete Zeit und Lückensegmente umstellen (8.2) |

### 8.2 §4 mit Lücken

`validate_daily_break(db, user, entry_date, start, end, break_minutes, *,
uncredited_segments: list[int], exclude_entry_id=None, tenant_id)`:

- Bruttozeit je Eintrag = (Ende − Beginn) − Σ Lückensegmente (nicht angerechnete Zeit
  ist keine Arbeitszeit).
- Wirksame Pause = erfasste Pausen ≥ 15 + Abstände zwischen Einträgen ≥ 15 +
  Lückensegmente ≥ 15.
- Segmente bestehender Einträge des Tages rechnet die Funktion über
  `work_window_service.gap_segments(...)` aus deren **gespeicherten** wirksamen Zeiten
  (`start_time`/`end_time`) und den Blöcken des Datums nach; ein einzelner gespeicherter
  Integer verlöre die Segmentierung. **Weicht Σ Segmente vom gespeicherten
  `uncredited_minutes` ab** (Puffer seit der Kappung geändert, Eintrag von der Neukappung
  übersprungen), zählt der **gespeicherte** Wert als Abzug von der Bruttozeit und **nicht**
  als Pausenabschnitt (strenge Richtung); §3 und §4 rechnen so auf derselben Grundlage. Für
  `credit_override`-Einträge: keine Segmente.
- Alle 9 Aufrufstellen (`time_entries` 462, 707, 773, 1036, 1132; `admin_time_entries`
  123, 344; `admin_change_requests` 410; `change_requests` 201) reichen die Segmente des
  neuen Eintrags durch.
- **XLS-Vorschau:** `_check_arbzg` (`xls_import_service.py:59-158`) prüft §3/§4/§6 heute
  inline auf der Bruttozeit aus `start`/`end` (`:83`, `:92`) und kennt in
  `same_day_blocks` kein `uncredited`. Sie bekommt `uncredited` und die Lückensegmente des
  Eintrags (`same_day_blocks` je Eintrag mit `uncredited_minutes` und Segmenten) und rechnet
  mit denselben Regeln wie `validate_daily_break`/`_net_hours` (bevorzugt durch Aufruf der
  gemeinsamen Helfer statt eines vierten Nachbaus). Test in `test_xls_blocks.py`: K1 als
  Import ergibt keine §3/§4-Warnung (angerechnet 7:30 h, Lücke deckt §4).

Ein Lückensegment < 15 Min (Lücke knapp über 2g) ist nicht angerechnet, zählt aber nicht
als Pausenabschnitt.

### 8.3 Weiche Anwesenheits-Warnungen

Anwesenheit eines Eintrags = `work_window_service.presence_minutes(entry)` (6.1):
(`raw_end` oder `end`) − (`raw_start` oder `start`) − erfasste Pause; bei `auto_closed`
endet sie am wirksamen Ende `end_time`, nie bei 23:59 (P18). Anwesenheit des Tages bzw. der
Kalenderwoche = Σ über die geschlossenen Einträge. Lücken werden **nicht** abgezogen (keine
nachgewiesene Pause), die Hülle nicht angewandt.

| Code | Bedingung | Text |
|---|---|---|
| `PRESENCE_DAILY_HOURS` | Anwesenheit des Tages > 10 h **und** die harte §3-Prüfung auf angerechneter Zeit hat nicht gegriffen | „§3 ArbZG: Laut Stempel {x} h anwesend (abzüglich erfasster Pausen) – mehr als 10 Stunden. Angerechnet werden {y} h; die Höchstgrenze gilt für die tatsächliche Arbeitszeit." |
| `PRESENCE_BREAK` | Anwesenheit des Tages > 6 h **und** (erfasste Pausen ≥ 15 Min + Abstände zwischen Einträgen ≥ 15 Min) < 30 Min (bei > 9 h: < 45 Min) **und** die §4-Prüfung auf angerechneter Zeit hat kein `BREAK_WARNING`/400 ausgelöst (nur gegen Doppelmeldung). Keine Bedingung „nur dank Lückensegmenten bestanden" (P14). Praktisch erreichbar nur, wenn gekappt wurde (Lücke oder Hülle), denn ohne Kappung ist Anwesenheit = angerechnete Zeit und die harte Prüfung greift | mit Lücke (mindestens ein Eintrag des Tages mit `uncredited_minutes` > 0): „§4 ArbZG: Durchgehend über die Lücke zwischen den Arbeitsblöcken gestempelt – eine Ruhepause ist nicht erfasst ({x} h Anwesenheit). Die Lücke gilt nur dann als Pause, wenn sie tatsächlich frei war." · nur Hülle: „§4 ArbZG: Laut Stempel {x} h anwesend ohne ausreichende erfasste Ruhepause; angerechnet werden nur {y} h. Die Pausenpflicht gilt für die tatsächliche Arbeitszeit." |
| `PRESENCE_WEEKLY_HOURS` (P22) | Anwesenheit der Kalenderwoche (Mo–So) > 48 h **und** `WEEKLY_HOURS_WARNING` auf angerechneter Zeit kam nicht | „§3 ArbZG: Laut Stempel {x} h in dieser Woche anwesend (abzüglich erfasster Pausen) – mehr als 48 Stunden. Angerechnet werden {y} h; die Grenze gilt für die tatsächliche Arbeitszeit." |

Fälle: K1, K7, K9, K17, K19, K20 → `PRESENCE_BREAK`; K21 (Pause 45) → keine; K6 → keine
(harte Prüfung griff). Beispiel Woche: Mo–Fr 08:00–18:00 durchgestempelt bei Blöcken
08:00–12:00 + 15:00–18:00 → angerechnet 37:30 h, anwesend 50 h → `PRESENCE_WEEKLY_HOURS`.

Ausgegeben an: `clock_out`, `create_time_entry`, `update_time_entry`,
`admin_create_time_entry`, `admin_update_time_entry`, Anerkennen (13.3), CR-Genehmigung
(Nachprüfung, auch Bulk), XLS-Vorschau (Zeilenwarnung als Klartext ohne Code). Übersprungen
bei `exempt_from_arbzg` (§18) wie alle übrigen ArbZG-Warnungen. Frontend:
`utils/arbzgWarnings.ts` bekommt je Code einen `case` (Text vom Server, Rückfalltext
im Client).

Es gelten die Schwellen für Erwachsene. Für Jugendliche (§§ 11, 12 JArbSchG: 30 Min ab
4,5 h, 60 Min ab 6 h, Schichtzeit inkl. Lücke ≤ 10 h) prüft PraxisZeit nichts; das steht
als feste Infozeile im Dialog und im Handbuch (12.1, 16.1) und bleibt Folgeticket (18).

### 8.4 Pausen-Doppelabzug

| Regel | Umsetzung |
|---|---|
| §4-Bedarf und XLS-Auto-Pause aus angerechneter Zeit | 7.4 und 8.2 |
| Pause > 0 **und** `uncredited` > 0 am selben Eintrag | weiche Warnung `BREAK_IN_GAP`: „Pause in der Lücke wird zusätzlich abgezogen: {p} Min Pause und {u} nicht angerechnet zwischen den Arbeitsblöcken. Lag die Pause in der Lücke, bitte die Pause auf 0 setzen." |
| StampWidget verlangt keine Pause, wenn die Lücke §4 abdeckt | `GET /time-entries/clock-status` liefert in **jedem** Antwortzweig (11.1) `blocks_today` (Liste `{start, end}`) und `grace_minutes`; `utils/workBlocks.ts::gapSegments(blocks, grace, start, end)` (Zwilling von `gap_segments`) speist `computeBreakError` (`utils/breakValidation.ts:23-92`, `StampWidget.tsx:104-117`, auch `TimeTracking.tsx:311-322`). |
| Keine Formel `max(Pause, Lücke)` | widerspräche „Pause innerhalb der Blöcke" |

### 8.5 Abgrenzung §5 / §6

- §5 bleibt auf Rohstempeln (`rest_time_service.py:66-81`, `time_entries.py:340-357`).
  Die Neukappung liest `raw_*` nur, sie setzt sie nie aus gekappten Werten.
- §6-Nachterkennung (`is_night_work`, 16 Stellen) bleibt auf den gespeicherten Zeiten;
  die Umstellung auf Rohstempel ist ein eigenes Ticket. Blöcke enden spätestens 23:55,
  die Hülle verschiebt höchstens um den Puffer — die Nachterkennung ändert sich durch
  dieses Feature nur, wenn ein Eintrag über die Hülle hinaus in die Nachtzeit reicht
  (wie heute bei #201).

---

## 9. Rückwirkung & Neukappung

### 9.1 Umfang

- Fenster: `calculation_service.retarget_window` (`:293`) wird um
  `last_time_entry: Optional[date]` und `has_time_entries` erweitert (Abfrage
  `max(TimeEntry.date)` im Bereich, F-026). Das offene Ende ist
  `max(effective_from, heute, last_absence, last_time_entry)`, sonst der Tag vor der
  nächsten Änderung.
- Geänderte Wochentage: je Wochentag Vergleich der kanonischen Blocklisten (ohne Pause)
  zwischen dem Snapshot, der vor der Änderung für das Datum galt, und dem neuen.
  Beim Löschen: gelöschte Zeile → Vorgänger (bzw. Rückfall `users.work_blocks`).
- Nur Einträge im Fenster an geänderten Wochentagen. Reine Pausenänderung → leere Menge.
- Puffer: aktueller Mandantenwert (`get_grace_minutes`), in Vorschau und Sammelzeile
  genannt.
- Offene Einträge mit Datum < heute im Fenster werden vorher geschlossen (P23, 9.3
  Schritt 2), sind also reguläre Kandidaten; „offen" betrifft nur den Eintrag von heute.

### 9.2 Funktion

```python
class ReclampChange(NamedTuple):
    entry_id: Any
    date: date
    old_start: time; old_end: time; old_uncredited: int; old_net: Decimal
    new_start: time; new_end: time; new_uncredited: int; new_net: Decimal
    not_extendable: Optional[str]          # None | "start" | "end" | "both"

class ReclampSkip(NamedTuple):
    entry_id: Any
    date: date
    reason: str   # open | soll_free_day | track_hours_off | outside_employment
                  # | credit_override | unique_collision

class ReclampResult(NamedTuple):
    changed: list[ReclampChange]
    skipped: list[ReclampSkip]
    flagged: list[ReclampChange]           # nicht erweiterbar, auch wenn unverändert

def reclamp_time_entries(db, user, start: date, end: date, weekdays: set[int],
                         prev_blocks_by_weekday, grace) -> ReclampResult
```

Ort: `work_window_service.py`, direkt neben `clamp`. Ablauf je Eintrag
(Abfrage mit `TimeEntry.tenant_id == user.tenant_id`, nach Datum/Beginn sortiert,
Feiertage/Sondertage als Menge `soll_free_dates` und Verlaufszeilen `wh_changes` für das
Fenster einmal vorgeladen und an `clamp`/`get_scheduled_blocks` über deren optionale
Vorlade-Parameter durchgereicht, 6.1):

1. `track_hours=False` → alle Einträge als `track_hours_off` überspringen.
2. `end_time is None` → `open`.
3. außerhalb `_within_employment_window` → `outside_employment`.
4. `credit_override` → `credit_override`.
5. Wochentag mit Blöcken im neuen Snapshot, aber Datum Feiertag/freier Sondertag
   (oder Sonntag) → `soll_free_day`.
6. Quelle = (`raw_start_time or start_time`, `raw_end_time or end_time`) (E48).
7. `r = clamp(db, user, d, quelle…, grace, credit_override=False, wh_changes=…,
   soll_free_dates=…)`.
8. Kollisionsprüfung in Python: neues (`date`, `r.eff_start`) gegen alle übrigen
   Einträge des Tages (mit deren bereits berechneten neuen Beginnzeiten); Treffer →
   `unique_collision`, Eintrag unverändert. (SQLite meldet die Verletzung je nach
   flush-Reihenfolge anders als Postgres; die Prüfung macht beide gleich.)
9. Alle fünf Werte unverändert → kein Eintrag in `changed`.
10. Sonst ORM-Attribute setzen (`start_time`, `end_time`, `raw_start_time`,
    `raw_end_time`, `uncredited_minutes`) — kein `query.update`.
11. „Nicht erweiterbar" (E50): Seite ohne Rohstempel und gespeicherte Zeit = alte
    Hüllenkante (`alter erster Beginn − g` bzw. `altes letztes Ende + g`) **und** die
    neue Hülle ist auf dieser Seite weiter → in `flagged`.

Kein `commit`, kein Protokoll (beides im Router). Idempotent: ein zweiter Lauf mit
denselben Blöcken liefert `changed == []`.

### 9.3 Reihenfolge, Transaktion, Sperre

In `create_working_hours_change` (`admin_users.py:1433`), eine Transaktion:

1. `lock_user_row(db, tenant_id, user.id)` (Ankersperre, E52).
2. Offene Einträge mit Datum < heute im künftigen Fenster per `_close_stale_entry`
   schließen (P23; unter dem **alten** Snapshot, Audit `auto_close` mit der handelnden
   Admin als `changed_by`), `flush`.
3. Bestehende Logik: Basis-Zeile (`:1514-1567`, jetzt mit `_current.blocks` und
   `_current.block_pauses`), neue Zeile, `flush`.
4. `reclamp_time_entries(...)` für `retarget_window` ∩ geänderte Wochentage, `flush`.
5. Klassifikation (9.4/9.5) und Schutzpaket-Prüfung; Verstoß → `HTTPException`,
   der Request-Rollback verwirft Schritt 2–4.
6. `retarget_absence_hours(...)` (`:373`) wie bisher bei `has_absences`, jetzt mit
   F1-Klemmung (9.6).
7. Protokoll (Abschnitt 10): Einzelzeilen je `changed`, **immer** genau eine Sammelzeile
   (P20, auch ohne Neukappungs-Umfang), Abwesenheitszeilen wie bisher.
8. `stale_year_closing_warning` (`:2509`) für die Jahre des Fensters.
9. Sync (`_sync_user_from_change`), `commit`.

Alle übrigen Schreibpfade für Zeiteinträge nehmen dieselbe Ankersperre als erste
Anweisung (P5); damit wartet jeder parallele Schreiber, bis die Änderung committet ist,
und löst danach den neuen Snapshot auf. Die Vorschau nimmt keine Ankersperre; sie führt
dieselben Schritte 2–6 im `flush`/Rollback-Lauf aus (die Zeilensperren auf geschlossenen
Alteinträgen halten nur für die Dauer der Vorschau-Anfrage) und fasst den offenen Eintrag
von heute nicht an, damit `clock_out` nicht auf ihn wartet. Keine Obergrenze für die
Anzahl; die Vorschau nennt sie.

### 9.4 Verlängerung

Kein Eintrag verliert angerechnete Zeit (`new_net ≥ old_net` für alle `changed`,
keine verlierende offene Zeile nach P1).

- Vorschau: Einträge alt → neu je Monat, Δ Überstundenkonto **getrennt nach Soll und
  angerechneter Zeit** (`target_delta_hours`, `credited_delta_hours`, 11.3), Übersprungene,
  „nicht erweiterbar", geänderte ArbZG-Befunde (P22).
- Eine Verlängerung kann den Saldo senken, wenn sie zugleich das Soll erhöht (längere
  Blöcke, kleinere Pause). Das Protokoll stuft sie trotzdem als Verlängerung ein; ob dafür
  das Schutzpaket gelten soll, ist offene Frage 19.1 Nr. 1. Bis dahin macht die Vorschau den
  Effekt sichtbar („Soll im Zeitraum +4:00 h · angerechnet +0:15 h · Überstunden −3:45 h").
- Speichern nach Bestätigung (Haken „Ich habe die Auswirkungen geprüft", Pflicht sobald
  `affected_time_entries > 0`, unabhängig davon, ob das Datum in der Vergangenheit liegt).
- Abgeschlossenes Jahr im Fenster → nur Warnung (`closed_year_warning`).

### 9.5 Verkürzung und Schutzpaket

Verkürzung = mindestens ein `changed` mit `new_net < old_net`, **oder** der offene
Eintrag von heute an einem geänderten Wochentag verliert nach der Knickstellen-Prüfung aus
P1 für irgendein mögliches Ende angerechnete Zeit. Ein offener Eintrag, der nach P1 nichts
verliert, ist nur `open` übersprungen. Gemischte Änderungen (manche Tage gewinnen, andere
verlieren) sind Verkürzungen. Abwesenheits-Angleichungen nach F1 (9.6) zählen nicht (P27).

`earliest_lossless_date` = `max(heute, letztes Datum eines verlierenden Eintrags + 1 Tag)`
— im Regelfall heute, mit einem heute bereits erfassten oder offenen verlierenden Eintrag
morgen. **Begrenzung (P25):** Liegt der Wert am oder nach dem `effective_from` der nächsten
Änderung, ist er `null`; Option 1 entfällt mit dem Text „Die Änderung liegt vollständig vor
der Änderung ab ‹Datum›; nur rückwirkend mit Begründung oder abbrechen." Eine weitere
Server-Prüfung braucht es nicht — jedes gesendete `effective_from` wird für sich bewertet.

| Variante | Voraussetzung | Wirkung |
|---|---|---|
| **„Ab ‹earliest_lossless_date› wirksam"** (Standard, Beschriftung „Ab heute wirksam", wenn das Datum heute ist) | keine | Der Client sendet `effective_from = earliest_lossless_date`; im Fenster verliert dann niemand → keine rückwirkende Zeile, keine Neukappung der Vergangenheit. Spätere Bearbeitungen alter Einträge lösen den alten Snapshot auf → keine Hintertür. |
| **„Rückwirkend ab ‹Datum› mit Neuberechnung"** | `retroactive_reason_type` ∈ {`erfassungsfehler`, `einvernehmlich`, `sonstiges`}; `retroactive_reason_text` (10–400 Zeichen, P15); `wage_risk_confirmed = true`; bei `sonstiges` zusätzlich `other_reason_risk_confirmed = true` (P26) | Neukappung wie berechnet; Grund in `note` und Sammelzeile. |
| Rückwirkend in ein abgeschlossenes Jahr | verlierender Eintrag in einem Jahr Y mit `YearCarryover` für Y+1 | **400**, nicht speicherbar; genannt wird das **größte** solche Y, Vorschlag 01.01.{Y+1} (11.4) |

Zusatzwarnungen (nicht blockierend) im Dialog und in der Vorschau-Antwort
(`milog_warning`):

- wenn `milog_working_time_account = true` **oder** `agreed_monthly_hours` gesetzt ist
  (ein eigenes Minijob-Kennzeichen gibt es im Modell nicht; `use_fixed_monthly_target`
  setzt das Konto-Flag voraus, ist also mit abgedeckt — Minijobber ohne beide Angaben
  erkennt die Anwendung nicht): „Diese Person führt ein Arbeitszeitkonto nach § 2 Abs. 2
  MiLoG bzw. hat eine vereinbarte Monatsarbeitszeit. Eine rückwirkende Kürzung angerechneter
  Zeit verändert den Kontostand und kann Mindestlohnansprüche sowie die
  12-Monats-Ausgleichsfrist berühren."
- **bei jeder** rückwirkenden Verkürzung, unabhängig von Kennzeichen: „Bei Minijob oder
  Vergütung in Mindestlohnhöhe kann die Kürzung Mindestlohnansprüche (§§ 1, 3 MiLoG) und
  die Aufzeichnung nach § 17 MiLoG berühren."

Bestätigungstexte je Grundtyp (P26, Wortlaut in 12.1); bei `sonstiges` zusätzlich die rote
Warnung zum Direktionsrecht mit eigenem Haken. Fehlt `other_reason_risk_confirmed` bei
`sonstiges` → 400 (11.4).

Speicherung des Grundes in `working_hours_changes.note` (String(500)):
`"[Erfassungsfehler korrigiert] <Begründung>"` bzw. `"[Einvernehmlich vereinbart] …"` /
`"[Sonstiges] …"`; eine zusätzliche Notiz wird mit `" · "` angehängt. Gesamtlänge > 500 →
422 „Notiz und Begründung zusammen höchstens 500 Zeichen." (keine stille Kürzung). Die
Präfixe stehen als Konstante in `reclamp_audit.py`; ein Test sichert, dass
`_audit_note_is_health_sensitive` für Sammelzeile und Eintragsnotiz mit **allen drei**
Präfixen ohne Freitext `False` liefert (das Präfix „[Sonstiges]" enthält das Label des
maskierten Typs OTHER und entgeht dem Token „Sonstiges " nur durch die schließende Klammer;
jede Formatänderung fiele damit sofort auf).

### 9.6 F1-Klemmung in `retarget_absence_hours`

Nach der Berechnung von `new_hours` (Tagessoll, `half_day`, Sondertagsfaktor) und vor dem
Gleichheitsvergleich:

```python
kept_net = kept_net_by_date.get(a.date, 0.0)     # Σ net_hours geschlossener Einträge des Tages
if kept_net > 0:
    # Vergleich in GUTSCHRIFTS-Einheiten: die Gutschrift ist new_hours × w
    # (credit_day_weight: Halbtags-Sondertag 0,5, frei 0, sonst 1,0); das wirksame
    # Tagessoll trägt denselben Faktor.
    w = float(credit_day_weight(a.date, holiday_dates, special_cfg))
    if w > 0:
        full_target = float(get_daily_target_for_date(user, a.date, schedule))
        cap_credit = max(0.0, full_target * w - kept_net)
        new_hours = round(max(0.0, min(new_hours, cap_credit / w)), 2)
```

Test: 24.12. (Halbtags-Sondertag) + Krank + 3 h Arbeit bei Tagessoll 8 h → Soll 4 h,
Gutschrift höchstens 1 h, Saldo des Tages 0.

`kept_net_by_date` wird einmal je Aufruf für das Fenster geladen
(`TimeEntry.user_id`, `TimeEntry.tenant_id`, `end_time IS NOT NULL`) — **nach** dem
`flush` der Neukappung, also mit den neuen Netto-Werten. Gleiche Regel wie
`absences.create_absence` (`absences.py:622-640, 667-679`). Folge: Misch-Tage
(Krank/Fortbildung + Arbeit) bekommen nach jeder Wochenstunden- oder Blockänderung den
nicht gearbeiteten Rest statt des vollen Tagessolls; Zeilen, die vor 1.18.0 ohne F1
gebucht wurden, werden dabei mit angeglichen. Das gilt auch an unveränderten Wochentagen
und bei reinen Wochenstunden-Änderungen ohne Blöcke.

Einordnung (P27): Diese Angleichungen korrigieren eine Doppelanrechnung und zählen
**nicht** als Verkürzung. Sie stehen in der Vorschau als eigene Zeile
(`absence_f1_adjustments`: „2 Abwesenheiten an Misch-Tagen angeglichen (Arbeit und
Gutschrift am selben Tag)") und im Protokoll wie jede Abwesenheits-Rückrechnung
(`source="wh_change"`); liegt eine davon in einem abgeschlossenen Jahr, kommt ein eigener
Hinweis (`closed_year_warning`, keine Sperre). Ob sie künftig unter das Schutzpaket fallen
sollen, ist Teil von Frage 19.1 Nr. 1.

### 9.7 Löschen einer Verlaufszeile

- `POST /admin/users/{id}/working-hours-changes/{change_id}/delete-preview` — gleiche
  Antwortform wie die Vorschau (Abschnitt 11), simuliert das Löschen in `flush`/Rollback.
- `DELETE …/{change_id}` mit optionalem JSON-Body
  (`retroactive_reason_type`, `retroactive_reason_text`, `wage_risk_confirmed`,
  `other_reason_risk_confirmed`).
- Gleiche Regeln: `lock_user_row`, Schließen alter offener Einträge (P23), Neukappung gegen
  den Vorgänger-Snapshot, `retarget_absence_hours` mit F1, Protokoll inkl. Sammelzeile
  („… gelöscht", 10.2), Jahreswarnung.
- Verkürzt das Löschen, gilt das Schutzpaket wie beim Anlegen (P13, zur Bestätigung in
  19.1 Nr. 4): **Standard** ist „Ab ‹earliest_lossless_date› auf den vorherigen Stand
  zurücksetzen" — der Dialog legt dann statt des Löschens über den normalen
  Anlege-Endpunkt eine neue Verlaufszeile mit dem Snapshot des Vorgängers an (keine
  Neukappung der Vergangenheit). Angeboten nur, wenn `earliest_lossless_date` nach dem
  `effective_from` der zu löschenden Zeile und vor der nächsten Änderung liegt (P25).
  Die zweite Option „Löschen mit Neuberechnung" verlangt Grund/Haken wie 9.5. In ein
  abgeschlossenes Jahr hinein → 400.
- Die früheste Zeile bleibt gesperrt, solange spätere existieren (bestehende Regel,
  `admin_users.py:2056-2075`).
- Antwort: 200 mit `{adjusted_absences, adjusted_time_entries, skipped_time_entries,
  warning}`, sobald etwas angepasst oder gewarnt wurde; sonst 204 (wie heute).

### 9.8 Zukunftsdatierung

Kein Scheduler. `users.work_blocks` bleibt bis zur nächsten Sync auf dem alten Stand;
niemand liest es live, der Resolver ist datumsaufgelöst. Guard-Test
`tests/test_no_live_work_blocks_read.py`: das Token `.work_blocks` kommt in `app/` nur an
den tatsächlich vorhandenen Lesestellen vor — `calculation_service.get_schedule_for_date`
(Rückfall vor der ersten Verlaufszeile), `admin_users` (`_sync_user_from_change`,
`create_user`), `schemas/user.py` (Feldnamen), `lifecycle_service._user_dict` und
`routers/auth.py` (`/me/export`). Nicht auf der Liste: die Migration (liegt in `alembic/`,
nicht in `app/`) und die Anonymisierung (fasst Blöcke nach E73 nicht an).
`work_blocks_today` entsteht über den Resolver, nicht über `.work_blocks`.

---

## 10. Protokoll

### 10.1 Zeile je neu gekapptem Eintrag

| Feld | Wert |
|---|---|
| `time_entry_id` | Eintrag |
| `user_id` | betroffene Person |
| `changed_by` | handelnde Admin |
| `action` | `"update"` |
| `source` | `"wh_reclamp"` (10 Zeichen, < 40) |
| `old_date` / `new_date` | Datum des Eintrags (gleich — keine Verschiebung) |
| `old_start_time` / `old_end_time` | effektive Zeiten vorher |
| `new_start_time` / `new_end_time` | effektive Zeiten nachher |
| `old_break_minutes` / `new_break_minutes` | Pause (unverändert) |
| `old_note` | `credit_summary_text(vorher)`, z. B. `"angerechnet 7:30 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"` |
| `new_note` | `credit_summary_text(nachher)` + `" — Arbeitszeit-Änderung ab 01.09.2026"` + bei Verkürzung `" · Grund: [Erfassungsfehler korrigiert] <Begründung>"`; beim Löschen Auslöser „Löschung der Arbeitszeit-Änderung ab 01.09.2026" |

Begriffe (P19): „angerechnet" = `net_hours` (nach Pause und Lücke), „nicht angerechnet" =
`not_credited_minutes` (Lücke + Hülle), „davon … zwischen den Blöcken" = `uncredited_minutes`
(entfällt, wenn gleich der Gesamtzahl oder 0); bei Pause > 0 folgt „, Pause 0:30 h".
Eine Quelle `work_window_service.credit_summary_text(entry)` für alle Protokollnotizen
(10.1, 13.3); `RawStampNote` (13.1) nutzt dieselben Zahlen über den Frontend-Zwilling.

Feste Notizteile enthalten keine Typlabels („Krank ", „Sonstiges ",
„Bez. Freistellung "), damit `_audit_note_is_health_sensitive`
(`admin_time_entries.py:59-64`) nicht anschlägt; ein Freitext-Grund kann sie enthalten,
dann maskiert die Fläche die Zeile (sichere Richtung). Das Grundtyp-Präfix „[Sonstiges]"
ist nur wegen der schließenden Klammer unauffällig — Test aus 9.5.

### 10.2 Sammelzeile

Genau **eine** Sammelzeile bei **jedem** Anlegen und **jedem** Löschen einer
Arbeitszeit-Änderung (P20) — auch zukunftsdatiert, auch ohne Einträge und Abwesenheiten,
auch bei einer reinen Wochenstunden-Änderung. `WorkingHoursChange` hat keine
`created_by`-Spalte; die Sammelzeile ist der Nachweis der handelnden Admin.

| Feld | Wert |
|---|---|
| `time_entry_id` | NULL |
| `old_date` / `new_date` | NULL (unterscheidet sie von Einzelzeilen, deren Eintrag später gelöscht wurde — `time_entry_id` ist `ON DELETE SET NULL`, `time_entry_audit_log.py:18`) |
| `user_id` / `changed_by` | betroffene Person / handelnde Admin |
| `action` / `source` | `"update"` / `"wh_reclamp"` |
| `new_note` | festes Präfix (P7), danach Klartext |

```
Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, 1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] Stempeluhr lief falsch · Vertrag: Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00
Arbeitszeit-Änderung ab 01.11.2026: 0 Einträge neu berechnet, Δ +0 Min · Puffer 15 Min · Vertrag: 20,0 h/Woche (gleichmäßig, 5 Tage) → 25,0 h/Woche (gleichmäßig, 5 Tage)
Arbeitszeit-Änderung ab 01.09.2026 gelöscht: 1 Eintrag neu berechnet, Δ +15 Min · Puffer 15 Min · Vertrag: … → …
```

- „Δ" = Σ (`new_net − old_net`) der neu berechneten Einträge in ganzen Minuten, ASCII-
  Vorzeichen `+`/`-`.
- „Vertrag:" = Kurzform alt → neu (PDF-Kurzform aus 15.2 bzw. #415-Text ohne Blöcke).
- Singular/Plural korrekt: „1 Eintrag", sonst „n Einträge".

Modul `app/services/reclamp_audit.py`: `summary_note(...)` und
`parse_summary_note(note) -> Optional[SummaryNote]` mit
`SummaryNote(effective_from, deleted, count, delta_minutes, shortening, reason_label)`.
Regex des Präfixes:
`^Arbeitszeit-Änderung ab (\d{2}\.\d{2}\.\d{4})( gelöscht)?: (\d+) Eintr(?:ag|äge) neu berechnet, Δ ([+-]\d+) Min`;
`shortening` = Teilstring „ · Verkürzung · "; `reason_label` = Inhalt von „Grund: [ … ]",
nur wenn er einer der drei festen Grundtyp-Labels ist (sonst `None`; der Freitext danach
wird nie gelesen, P12). Round-Trip-Test in `test_reclamp_audit.py` für n = 0, 1, 2 und 14,
mit und ohne Verkürzung, mit Löschkennzeichen.

### 10.3 Integrität

- Jede Zeile per `db.add` → der `before_insert`-Hook setzt `row_hash` (#121).
- **Keine** neue gehashte Spalte, `_HASHED_FIELDS` und `_HKDF_INFO` bleiben
  (`core/audit_integrity.py:43-53`); sonst meldete `verify-integrity` alle Altzeilen.
- Kein Bulk-UPDATE auf Protokollzeilen.
- Die Abwesenheits-Rückrechnung protokolliert weiter über `_log_wh_change_retarget`
  (`source="wh_change"`), Präfix „Arbeitszeit-Änderung" statt „Wochenstunden-Änderung".
- Die Vorschau (beide) protokolliert nie: alle Zeilen entstehen erst im Speichern-Pfad
  nach der Klassifikation, die Vorschau rollt zurück.
- Frontend `AuditLog.tsx:80-89`: Labels `wh_reclamp: 'Neukappung (Arbeitszeit-Änderung)'`,
  `credit_override: 'Anrechnung anerkannt'`; Zeilen mit identischem Von–Bis zeigen die
  Notiz (`AuditValues.tsx`).
- Auto-Close (`source="auto_close"`) unverändert; die vor der Neukappung geschlossenen
  Alteinträge (P23) tragen die handelnde Admin als `changed_by`.

---

## 11. API

### 11.1 Endpunkte

| Methode + Pfad | Rolle | Änderung |
|---|---|---|
| `POST /api/admin/users` | Admin | nimmt `work_blocks` (streng); leitet `hours_*`, `weekly_hours`, `work_days_per_week`, `use_daily_schedule` ab und überschreibt mitgeschickte Werte; Altfelder → 400 |
| `PUT /api/admin/users/{id}` | Admin | `work_blocks` in `_HISTORISED_FIELDS` → 400; Altfelder → 400 |
| `GET /api/admin/users`, `GET /api/admin/users/{id}`, Login- und Impersonation-Antwort (`auth.py:302`, `impersonation.py:92`, `admin_users.py:438`) | — | `work_blocks` (locker) und neu `work_blocks_today` (datumsaufgelöst für heute, locker; Liste mit einem Preload der Verlaufszeilen, #449-Muster) |
| `GET /api/admin/users/{id}/working-hours-changes` | Admin | Antwort trägt `blocks` (locker) |
| `POST /api/admin/users/{id}/working-hours-changes` | Admin | Body `WorkingHoursChangeCreate` (11.2); Antwort zusätzlich `adjusted_time_entries`, `skipped_time_entries` |
| `POST /api/admin/users/{id}/working-hours-changes/preview` | Admin | **neu** (ersetzt `GET …/preview`); Body wie Speichern, aber **untypisiert** entgegengenommen (`body: dict = Body(...)`) und intern per `WorkingHoursChangeCreate.model_validate` in `try/except ValidationError` geprüft → Fehler als `blocked_reason` über `_schedule_input_error` (wie heute `admin_users.py:1740-1743`), nie hartes 422 beim Tippen; Antwort 11.3 |
| `POST /api/admin/users/{id}/working-hours-changes/{change_id}/delete-preview` | Admin | **neu**; Body ebenso untypisiert; Antwort 11.3 |
| `DELETE /api/admin/users/{id}/working-hours-changes/{change_id}` | Admin | optionaler Body (Schutzpaket); 200 mit Zusammenfassung oder 204 |
| `POST /api/admin/time-entries/{entry_id}/credit-override` | Admin | **neu**, Abschnitt 13 |
| `GET /api/time-entries/clock-status` | angemeldet | `blocks_today` und `grace_minutes` in **allen drei** Rückgabezweigen — nicht eingestempelt (`time_entries.py:~218`), Stale-Auto-Close (`~225`, mit Ankersperre, P5) und eingestempelt; `uncredited_minutes` am laufenden Eintrag (0). E69 braucht die Blöcke gerade im nicht eingestempelten Zustand (14) |
| `GET /api/auth/me/work-schedule` | angemeldet, nur eigene Daten | **neu**, Abschnitt 14 |
| `GET /api/dashboard/` | angemeldet | zusätzlich `schedule_change_notices` (Liste, jüngste zuerst, Abschnitt 14) |
| `GET /api/journal/…` | wie heute | je Eintrag `uncredited_minutes`, `not_credited_minutes`, `credit_override`, `auto_closed`; Monatssumme `not_credited_minutes_total` (P19) |
| `POST /api/change-requests` | angemeldet | `ChangeRequestCreate.request_credit_override` (P21, 7.1 Nr. 14) |
| `POST /api/admin/change-requests/{id}/review` | Admin | `ChangeRequestReview.grant_credit_override: Optional[bool]` (Default = `request_credit_override` des Antrags); Bulk übernimmt den Antragswert (P21) |
| `GET /api/admin/reports/24-week-average` (`routers/reports.py:957-1080`) | Admin | zusätzlich `presence_hours` je Woche und `presence_average` (P22, 8.1) |

Das alte `GET …/preview` entfällt (ein gecachtes altes Frontend bekommt 405; der Dialog
zeigt dann den allgemeinen Fehlertext, das Neuladen behebt es).

### 11.2 Schreibschema `WorkingHoursChangeCreate`

```python
class TimeBlockIn(BaseModel):
    start: str          # "HH:MM", Raster 5
    end: str

class DayBlocksIn(BaseModel):
    blocks: List[TimeBlockIn] = Field(default_factory=list, max_length=3)
    pause_minutes: int = Field(ge=0)

class WorkingHoursChangeCreate(WorkingHoursChangeBase):
    blocks: Optional[List[DayBlocksIn]] = None          # gesetzt → Block-Modus
    remove_legacy_window: bool = False                   # P2
    retroactive_reason_type: Optional[Literal["erfassungsfehler", "einvernehmlich", "sonstiges"]] = None
    retroactive_reason_text: Optional[str] = Field(None, min_length=10, max_length=400)  # P15
    wage_risk_confirmed: bool = False
    other_reason_risk_confirmed: bool = False            # P26, Pflicht bei "sonstiges"
```

- `blocks` gesetzt → `validate_week_blocks` + `derive_targets`; `weekly_hours`/`hours_*`
  im selben Body → 422. `use_daily_schedule` wird `True`.
- `blocks` nicht gesetzt → Modus wie bisher (`check_mode`); Altfenster-/`track_hours`-
  Übernahme nach 4.3, `remove_legacy_window=true` entfernt ein Altfenster.
- Leseschema `WorkingHoursChangeBase`/`…Response`: `blocks: Optional[Any] = None`, kein
  Validator (ein Validator auf `Base` liefe beim Lesen und machte Altzeilen zu 500).

### 11.3 Vorschau-Antwort (`WorkingHoursChangePreview`, erweitert)

Bestehende Felder bleiben (`is_retroactive`, `period_start`, `period_end`,
`current_daily_target`, `new_daily_target`, `day_targets_current`, `day_targets_new`,
`overtime_before`, `overtime_after`, `vacation_days_before`, `vacation_days_after`,
`affected_absences`, `blocked_reason`, `closed_years`, `closed_year_warning`). Neu:

| Feld | Typ | Bedeutung |
|---|---|---|
| `grace_minutes` | int | angewandter Puffer |
| `blocks_current` / `blocks_new` | Liste[5] (locker) | Blöcke vorher/nachher |
| `changed_weekdays` | List[int] | 0 = Mo … 4 = Fr |
| `affected_time_entries` | int | Anzahl `changed` |
| `time_entry_months` | List[{`month`: "2026-09", `entries`: int, `net_before`: float, `net_after`: float}] | Summen je Monat |
| `time_entry_changes` | List[{`entry_id`, `date`, `old_start`, `old_end`, `old_uncredited`, `old_net`, `new_start`, `new_end`, `new_uncredited`, `new_net`, `not_extendable`}] | vollständig, ohne Obergrenze |
| `skipped_time_entries` | List[{`entry_id`, `date`, `reason`}] | E49 |
| `not_extendable_count` | int | E50 |
| `is_shortening` | bool | 9.5 |
| `earliest_lossless_date` | Optional[date] | P1; `null`, wenn es die nächste Änderung erreicht (P25) |
| `earliest_lossless_note` | Optional[str] | Text aus P25, wenn `earliest_lossless_date` null ist |
| `lost_credited_hours` | float | Σ Verlust der verlierenden Einträge (Anzeige im Verkürzungs-Kasten) |
| `target_delta_hours` / `credited_delta_hours` | float | Δ Soll und Δ angerechnete Zeit im Wirkungsbereich (9.4, Frage 19.1 Nr. 1) |
| `absence_f1_adjustments` | int | F1-Angleichungen (P27, 9.6) |
| `stale_entries_closed` | int | vor der Neukappung geschlossene Alteinträge (P23) |
| `arbzg_findings` | {`days_over_10_credited_before`, `days_over_10_credited_after`, `days_over_10_presence`, `weeks_over_48_credited_before`, `weeks_over_48_credited_after`, `weeks_over_48_presence`} | geänderte ArbZG-Befunde im Wirkungsbereich (P22); Anzeige z. B. „Wochen > 48 h: angerechnet bisher 3, neu 0 · laut Stempel 3" |
| `milog_warning` | List[str] | 9.5 (bis zu zwei Sätze) |
| `block_break_notices` | List[str] | P9, z. B. „Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." / „Mo: Die Lücke 12:00–12:30 ist nicht länger als der doppelte Puffer …" / „Mo: Tagessoll 10:30 h – geplanter Verstoß gegen § 3 ArbZG …" |

`overtime_after` stammt aus demselben `flush`/Rollback-Lauf, in dem die Neukappung
**ausgeführt** (nicht nur gezählt) wurde — also vor dem Rollback berechnet. Der
Kurzschluss „Snapshot unverändert" (`admin_users.py:1891-1897`) vergleicht über
`_comparable_snapshot` (`:155`) jetzt einschließlich kanonischer Blöcke und Pausen; eine
reine Blockänderung ist damit eine Änderung (Basis-Zeile, Segment, Neukappung).

### 11.4 Fehlercodes und Meldungen

| Status | Wann | `detail` |
|---|---|---|
| 400 | `POST`/`PUT /admin/users` enthält einen Schlüssel mit Präfix `scheduled_` (erkannt per `model_validator(mode="before")`, siehe unten) | „Bitte Seite neu laden: Die Arbeitszeit-Fenster (Soll-Beginn/Soll-Ende) wurden durch Arbeitszeit-Blöcke ersetzt." |
| 400 | `PUT /admin/users/{id}` mit `work_blocks` oder einem anderen historisierten Feld | „Wochenstunden, Tagesstunden, Arbeitstage und Arbeitszeit-Blöcke werden über „Arbeitszeit anpassen…" mit Wirkungsdatum geändert, damit Historie und Soll vergangener Monate korrekt bleiben." |
| 422 | Blockvalidierung | Tabelle 3.4 |
| 422 | `blocks` zusammen mit `weekly_hours`/`hours_*` | „Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet." |
| 400 | Verkürzung rückwirkend ohne Grund/Haken | „Rückwirkende Verkürzung: Bitte Grund, Begründung und die Bestätigung zum Vergütungsrisiko angeben – oder die Änderung ab dem {earliest_lossless_date} wirksam werden lassen." |
| 400 | `retroactive_reason_type = "sonstiges"` ohne `other_reason_risk_confirmed` | „Bei „Sonstiges" bitte bestätigen, dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist." |
| 400 | Verkürzung in abgeschlossenes Jahr | „Rückwirkende Verkürzung in das abgeschlossene Jahr {Y} ist gesperrt. Bitte die Änderung frühestens ab 01.01.{Y+1} wirksam werden lassen." — Y = das **größte** abgeschlossene Jahr mit verlierendem Eintrag (sonst scheiterte auch das vorgeschlagene Datum) |
| 400 | bestehende Regeln (Datum doppelt, früheste Zeile löschen) | unverändert |
| 404 | Person/Zeile/Eintrag nicht im Mandanten | unverändert |
| 400 | Anerkennen eines offenen Eintrags | „Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden." |
| 400 | Anerkennen eines automatisch geschlossenen Eintrags (`auto_closed`, P18) | „Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen." |
| 409 | Anerkennen: anderer Eintrag beginnt bereits zur Rohzeit | „Ein anderer Eintrag an diesem Tag beginnt bereits um {HH:MM}." |
| 409 | MA-`PUT` auf einen anerkannten Eintrag (P3) | „Anerkannter Eintrag – Änderung bitte per Änderungsantrag." |
| 400 | `request_credit_override` an einem Eintrag ohne nicht angerechnete Zeit, offen, anerkannt oder fremd | „Für diesen Eintrag kann keine Anrechnung beantragt werden." |

Altfelder werden **ohne** ihre wörtlichen Namen erkannt (sonst bräche der Guard-Test 17.6):
`UserCreate` und `UserUpdate` bekommen einen `model_validator(mode="before")`, der prüft
`any(k.startswith("scheduled_") for k in data)`, die Schlüssel aus `data` entfernt und das
deklarierte Feld `legacy_window_fields_sent: bool = Field(False, exclude=True)` setzt; der
Router wirft daraufhin den 400. Ohne diesen Validator verwürfe Pydantic die Felder still.

### 11.5 Lese- vs. Schreibschemas

| Schema | `work_blocks`/`blocks` | Validator |
|---|---|---|
| `UserBase` (`schemas/user.py:58-72`) | nicht enthalten | — (Fensterteil von `validate_employment_and_window_order`, `validators.py:48-58`, und `SCHEDULED_WINDOW_PAIRS` `:14-21` entfallen) |
| `UserCreate` | `Optional[List[DayBlocksIn]]` | streng; plus `before`-Validator für Altfelder (11.4) |
| `UserUpdate` | `Optional[Any]` (nur deklariert, damit die Sperre greift) | keiner; plus `before`-Validator für Altfelder (11.4) |
| `UserResponse`, `UserListResponse` | `Optional[Any]`, plus `work_blocks_today: Optional[Any]` | keiner |
| `WorkingHoursChangeBase`/`Response` | `Optional[Any]` | keiner |
| `WorkingHoursChangeCreate` | `Optional[List[DayBlocksIn]]` | streng |

---

## 12. Oberfläche Admin

### 12.1 Dialog „Arbeitszeit & Wochenstunden"

`pages/admin/users/WorkingHoursModal.tsx`, geöffnet über „Arbeitszeit anpassen…" im
UserForm und das Uhr-Symbol der Benutzerliste (`Users.tsx`, aria-Label/Titel
„Arbeitszeit & Wochenstunden für …").

Beispiel (heute = Do 08.10.2026): Mo-Nachmittagsblock 15:00–18:00 wird rückwirkend ab
01.09.2026 auf 15:00–17:00 gekürzt; nur Mo ändert sich, Pausen bleiben 0. Montage im
Wirkungsbereich: 07.09. (Urlaub), 14.09., 21.09., 28.09. (Nachmittag anerkannt), 05.10.;
gestempelt jeweils 08:00–12:00 und 15:00–18:00. Der Admin hat Option 2 gewählt, deshalb
zeigt die Auswirkungs-Box die rückwirkende Vorschau (Regel unten).

```
Arbeitszeit & Wochenstunden – Anna Beispiel                                   [×]
─────────────────────────────────────────────────────────────────────────────────
Heute gültig (seit 01.03.2026)
  Mo 08:00–12:00 + 15:00–18:00 · Di 08:00–12:00 · Mi – · Do 08:00–12:00 · Fr –
  Wochensoll 15,0 h · 3 Arbeitstage

Neue Änderung
  Gültig ab [01.09.2026]
  ( ) Gleichmäßig   ( ) Nach Tagen   (•) Nach Arbeitsblöcken

  Mo  [08:00]–[12:00]  [15:00]–[17:00]  [+ Block]        Pause innerhalb [  0] Min
      Gesamtzeit 6:00 h · Pause 0:00 h · Tagessoll 6:00 h
  Di  [08:00]–[12:00]                   [+ Block]        Pause innerhalb [  0] Min
      Gesamtzeit 4:00 h · Pause 0:00 h · Tagessoll 4:00 h
  Mi  kein Arbeitstag                   [+ Block]
  Do  [08:00]–[12:00]                   [+ Block]        Pause innerhalb [  0] Min
      Gesamtzeit 4:00 h · Pause 0:00 h · Tagessoll 4:00 h
  Fr  kein Arbeitstag                   [+ Block]
  ─────────────────────────────────────────────────────────────────────────────
  Woche: Gesamtzeit 14:00 h · Pause 0:00 h · Wochensoll 14:00 h · 3 Arbeitstage

  ⓘ Ändert sich der Umfang (Tagessoll/Wochenstunden), ist das eine Vertragsänderung …
    Lage nur für die Zukunft (§ 106 GewO) … schriftlich mitteilen (§ 3 NachwG) …
    Betriebsrat (§ 87 Abs. 1 Nr. 2, 3, 6 BetrVG) … PraxisZeit prüft das nicht.
  ⓘ Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln (§§ 11, 12 JArbSchG);
    PraxisZeit prüft diese nicht.

  Notiz [ ............................................. ]

  Auswirkung (Puffer 15 Min)                                    [Einzelheiten ▾]
    Wirkungsbereich 01.09.2026 – 08.10.2026 · geänderte Tage: Mo
    Zeiteinträge: 3 neu berechnet · 1 übersprungen (1 anerkannt)
      Sep 2026   2 Einträge    6:00 h → 4:30 h
      Okt 2026   1 Eintrag     3:00 h → 2:15 h
    Abwesenheiten: 1 Stundenwert angepasst (Urlaub 07.09.: 7:00 → 6:00 h)
                       bisher      neu         Δ
    Soll im Zeitraum                            −4:00 h
    Angerechnet                                 −2:15 h
    Überstunden        +12:30 h    +14:15 h     +1:45 h

  ⚠ Verkürzung: 3 Einträge verlieren angerechnete Zeit (zusammen 2:15 h)
    ( ) Ab heute (08.10.2026) wirksam – vergangene Einträge bleiben unverändert
    (•) Rückwirkend ab 01.09.2026 mit Neuberechnung
          Grund        [Erfassungsfehler korrigiert ▾]
                       Falsche Stempelzeiten bitte am Zeiteintrag korrigieren,
                       nicht über die Arbeitszeit.
          Begründung   [ .......................................... ]
          ☐ Ich habe geprüft, dass die hinterlegte Arbeitszeit falsch war
            (Fehlerkorrektur). Tatsächlich geleistete Arbeit, die angeordnet,
            gebilligt oder geduldet wurde, ist unabhängig von der Anrechnung zu
            vergüten (§ 611a, § 612 BGB). Auf den Mindestlohn für geleistete
            Stunden kann nicht verzichtet werden (§ 3 MiLoG).
          ⚠ Bei Minijob oder Vergütung in Mindestlohnhöhe kann die Kürzung
            Mindestlohnansprüche (§§ 1, 3 MiLoG) und die Aufzeichnung nach
            § 17 MiLoG berühren.
          ⚠ MiLoG-Arbeitszeitkonto: …               (nur wenn zutreffend)

  ☐ Ich habe die Auswirkungen geprüft und möchte speichern
                                                     [Abbrechen] [Speichern]
Verlauf
  ab 01.03.2026 bis heute: Mo 08:00–12:00 + 15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 = 15,0 h/Woche   [Löschen]
  ab 01.01.2026 bis 28.02.2026: 20,0 Std/Woche (gleichmäßig, 5 Tage)
```

Nachrechnung: je verlierendem Montag kappt der Nachmittag 15:00–18:00 auf 15:00–17:15
(Hülle 17:00 + 15 Min) → −0:45 h, drei Montage → −2:15 h; das Soll sinkt an vier Montagen
um je 1:00 h (am Urlaubstag 07.09. heben sich Soll und Urlaub auf) → −4:00 h; Überstunden
+1:45 h. Die Verkürzung zeigt sich also an den Einträgen, nicht am Saldo (Frage 19.1 Nr. 1).
`[Löschen]` steht nur an der jüngsten Zeile (die früheste bleibt gesperrt, solange spätere
existieren). Bei Option 1 zeigt die Box die Vorschau für 08.10.2026: keine Zeiteinträge
betroffen, Soll ab heute −1:00 h je Montag.

Zweiter Zustand — **Verlängerung** (Mo 15:00–18:00 → 15:00–19:00; am 21.09. bis 18:30
gestempelt, am 14.09. Ende 18:15 ohne Rohstempel aus der Zeit vor 1.19.1):

```
  Auswirkung (Puffer 15 Min)
    Wirkungsbereich 01.09.2026 – 08.10.2026 · geänderte Tage: Mo
    Zeiteinträge: 1 neu berechnet · 1 übersprungen (1 anerkannt)
      Sep 2026   1 Eintrag     3:15 h → 3:30 h
    1 Eintrag ohne Rohstempel – nicht erweiterbar (14.09., Ende 18:15)
    Abwesenheiten: 1 Stundenwert angepasst (Urlaub 07.09.: 7:00 → 8:00 h)
                       bisher      neu         Δ
    Soll im Zeitraum                            +4:00 h
    Angerechnet                                 +0:15 h
    Überstunden        +12:30 h    +8:45 h      −3:45 h
```

Kein Verkürzungs-Kasten (niemand verliert angerechnete Zeit, E53); der Saldo sinkt trotzdem
durch das höhere Soll — sichtbar gemacht, Einordnung offene Frage 19.1 Nr. 1.

Verhalten:

- **Block-Editor** (`components/WorkBlocksEditor.tsx`, gemeinsam für Dialog und
  Anlegen): je Tag bis zu 3 Zeilen „von–bis" (`<input type="time" step="300">`),
  „+ Block" bis 3, Entfernen je Zeile; „Pause innerhalb der Blöcke" in Minuten (Raster 5).
  Live je Tag „Gesamtzeit H:MM h · Pause H:MM h · Tagessoll H:MM h", darunter die
  Wochensumme. Rechnung über `utils/workBlocks.ts` (`sumBlocks`, `deriveTargets`,
  `validateWeekBlocks`, `formatBlocks`, `gapSegments`, `notCreditedMinutes`) — wortgleiche
  Testfälle zum Backend.
- **Validierung im Client** mit denselben Texten wie 3.4; Speichern gesperrt bei Fehlern.
- **Vorschau** per `POST …/preview` mit JSON-Body, 400-ms-Debounce wie heute; der
  Effekt-Schlüssel ist `JSON.stringify(body)` (stabil, sonst Anfragesturm,
  `WorkingHoursModal.test.tsx:862`). Unfertige Eingaben kommen als `blocked_reason` zurück,
  nie als 422 (11.1).
- `comparableSnapshot` (`:191-198`) nimmt Blöcke und Pausen auf; „Speichern" gesperrt,
  solange sich gegenüber dem heute gültigen Zustand nichts geändert hat.
- **Bestätigungspflicht**, sobald `affected_time_entries > 0` oder `affected_absences > 0`
  — auch bei Wirkungsdatum heute (dort ist `isRetroactive` false, Einträge von heute
  werden trotzdem neu gekappt).
- **Verkürzungs-Wahl, Zustand (F24):** Der Dialog hält das vom Admin eingegebene Datum
  (`requestedDate`) und dessen Vorschau getrennt vom gesendeten `effective_from`. Ob der
  Kasten erscheint und welche Optionen er anbietet, leitet sich **immer** aus der Vorschau
  für `requestedDate` ab (`is_shortening`, `earliest_lossless_date`); die Auswirkungs-Box
  zeigt die Vorschau der **gewählten** Option (bei Option 1 eine zweite Anfrage für
  `earliest_lossless_date`). So bleibt nach der Wahl von Option 1 der Rückweg zu Option 2
  offen. Standard ist Option 1; ist `earliest_lossless_date` null (P25), gibt es nur Option
  2 mit `earliest_lossless_note`. Option 2 blendet Grund (mit Hilfetext), Begründung und den
  Bestätigungshaken ein; bei „Sonstiges" zusätzlich die rote Warnung und den zweiten Haken.
  Ohne alle Pflichtangaben bleibt „Speichern" gesperrt. `closed_years` mit verlierenden
  Einträgen → Option 2 deaktiviert mit dem Text der 400-Meldung.
- **Bestätigungstexte je Grundtyp (P26):**
  - Erfassungsfehler korrigiert (Hilfetext „Falsche Stempelzeiten bitte am Zeiteintrag
    korrigieren, nicht über die Arbeitszeit."): „Ich habe geprüft, dass die hinterlegte
    Arbeitszeit falsch war (Fehlerkorrektur)."
  - Einvernehmlich vereinbart: „Ich habe geprüft, dass die rückwirkende Änderung mit der
    beschäftigten Person vereinbart ist."
  - Sonstiges: „Ich habe die Gründe geprüft." plus rote Warnung „Eine einseitige
    rückwirkende Kürzung deckt das Direktionsrecht nicht (§ 106 GewO wirkt nur für die
    Zukunft); geleistete Arbeit bleibt zu vergüten." und zweiter Haken „Mir ist bewusst,
    dass eine einseitige rückwirkende Kürzung vom Direktionsrecht nicht gedeckt ist."
  - Jeder Text endet mit: „Tatsächlich geleistete Arbeit, die angeordnet, gebilligt oder
    geduldet wurde, ist unabhängig von der Anrechnung zu vergüten (§ 611a, § 612 BGB). Auf
    den Mindestlohn für geleistete Stunden kann nicht verzichtet werden (§ 3 MiLoG)."
  - Die Beschriftungen der Grundtypen folgen dem Protokoll; eine Umbenennung von
    „Erfassungsfehler korrigiert" ist offene Frage 19.1 Nr. 7.
- **Hinweis Arbeitsrecht/Mitbestimmung** fest unter dem Editor (Kurzfassung; volle
  Fassung im Handbuch, 16.1):
  „Ändert sich der Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine
  Vertragsänderung und braucht das Einverständnis der beschäftigten Person. Die Lage kann,
  soweit der Vertrag sie nicht festlegt, im Rahmen des Direktionsrechts (§ 106 GewO) nach
  billigem Ermessen und mit angemessener Ankündigung nur für die Zukunft geändert werden.
  Vereinbarte Arbeitszeiten und Pausen sind spätestens am Tag des Wirksamwerdens schriftlich
  mitzuteilen (§ 3 NachwG). Mit Betriebsrat ist die Änderung mitbestimmungspflichtig
  (§ 87 Abs. 1 Nr. 2, 3 und 6 BetrVG). PraxisZeit prüft das nicht."
- **JArbSchG-Infozeile** fest darunter: „Für Jugendliche gelten strengere Pausen- und
  Schichtzeitregeln (§§ 11, 12 JArbSchG); PraxisZeit prüft diese nicht." (Folgeticket 18.)
- **Plan-Hinweise** aus `block_break_notices` als Infozeilen (P9): §4 über den ganzen Tag,
  Lücke ≤ 2 × Puffer, §3 > 10 h / > 8 h / Woche > 48 h. Nicht blockierend.
- **Altfenster:** Kasten „Arbeitszeit-Fenster (Altbestand, nur Kappung)" mit den Aktionen
  aus 4.4.
- **Moduswechsel weg von Blöcken** (auch bei `track_hours=false`): Hinweis vor dem
  Speichern „Die Arbeitszeit-Blöcke enden mit dieser Änderung; ab ‹Datum› wird nicht mehr
  gekappt." (P24).
- **`track_hours=false`:** Modus „Nach Arbeitsblöcken" nicht angeboten, gespeicherte
  Blöcke als Text „Arbeitszeit-Blöcke gespeichert, ohne Wirkung (keine Stundenzählung)".
- **Toast nach dem Speichern:** „Gespeichert. 3 Zeiteinträge neu berechnet, 1 übersprungen,
  1 Abwesenheit angepasst." plus `warning` über `showResponseWarning`.
- **Löschen** (nur an der jüngsten Zeile) öffnet eine Bestätigung mit der `delete-preview`
  (gleiche Auswirkungs-Box); verkürzt das Löschen, dieselbe Zwei-Optionen-Wahl wie oben
  mit „Ab ‹Datum› auf den vorherigen Stand zurücksetzen" als Standard (P13, 9.7).

### 12.2 UserForm

`pages/admin/users/UserForm.tsx`:

- Der Abschnitt mit den Feldern „Soll-Beginn Mo" … (`:942-977`) entfällt — **und** die
  `scheduled_*`-Schlüssel verschwinden vollständig aus `formData` (`:90-99`), aus der
  Edit-Vorbelegung (`:142-151`) und aus dem Payload (`:221-237`). Sonst endet mit E26 jedes
  Anlegen und Bearbeiten im **neuen** Frontend mit 400 „Bitte Seite neu laden".
  `UserForm.test.tsx` prüft, dass weder der POST- noch der PUT-Payload einen Schlüssel mit
  Präfix `scheduled_` enthält.
- Beim **Bearbeiten**: Zusammenfassung „Arbeitszeit heute: Mo 08:00–12:00 + 15:00–18:00 ·
  Di 08:00–12:00 …" aus `work_blocks_today` (Anzeige-Prop `displayBlocks` aus `Users.tsx`
  nach dem Muster `displayDayHours`, `editingUser` wird nicht ersetzt) und der Knopf
  „Arbeitszeit anpassen…". Ohne Blöcke: „Keine Arbeitszeit-Blöcke hinterlegt".
- Die Edit-`PUT`-Destrukturierung (ca. `:269-273`) nimmt `work_blocks` und
  `work_blocks_today` in die Ausschlussliste — sonst endet jedes Speichern mit 400.
- Beim **Anlegen**: Moduswahl „Gleichmäßig / Nach Tagen / Nach Arbeitsblöcken"; der
  dritte Modus zeigt `WorkBlocksEditor`, die Felder Wochenstunden/Tagesstunden/Arbeitstage
  werden dann schreibgeschützt aus den Blöcken abgeleitet angezeigt, der Payload trägt
  `work_blocks`.
- `track_hours=false`: Editor ausgeblendet, gespeicherte Werte bleiben.
- Texte „Änderung über „Wochenstunden anpassen…"" (`:540-541`, `:879`) →
  „Arbeitszeit anpassen…".

### 12.3 Weitere Admin-Flächen

- `pages/admin/Settings.tsx:1320-1353`: Puffer-Text „gilt an jedem Blockrand, auch zwischen
  zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet". Zusätzlich:
  „Eine Änderung des Puffers wirkt auf jede künftige Kappung — auch wenn ein älterer Eintrag
  später bearbeitet oder bei einer Arbeitszeit-Änderung neu berechnet wird. Ein kleinerer
  Puffer kann dabei die angerechnete Zeit alter Einträge senken; bereits gespeicherte
  Einträge ändern sich durch das Speichern dieser Einstellung allein nicht." (Ob der
  angewandte Puffer je Eintrag gespeichert werden soll, ist offene Frage 19.1 Nr. 8.)
- `pages/admin/AdminDashboard.tsx:1473-1515`: Detailtabelle bekommt eine Netto-Spalte und
  die `RawStampNote`; dort sitzt auch „Anerkennen".

---

## 13. Nicht angerechnete Zeit sichtbar + Anerkennen

### 13.1 Anzeige je Eintrag

`components/RawStampNote.tsx` bekommt die Props `uncreditedMinutes`,
`notCreditedMinutes` (P19), `rawSpan` (`"08:00–18:00"`, aus `raw_* or start/end`),
`effSpan` (gespeicherte `start`/`end`), `creditedHours` (= `net_hours`), `breakMinutes`
und `autoClosed`. „angerechnet" ist immer `net_hours` (nach Pause und Lücke, P19).

| Lage | Anzeige |
|---|---|
| nichts gekappt (`not_credited_minutes` = 0) | keine Zeile (Guard `raw === eff`) |
| nur Hülle gekappt (`uncredited_minutes` = 0) | unverändert je Seite: „gestempelt 07:30 · angerechnet ab 07:45" (Wortlaut in Handbuch/Cheat-Sheet zitiert) |
| nur Lücke (`uncredited_minutes` = `not_credited_minutes` > 0) | **eine** Zeile statt der Seitenzeilen, Wortlaut des Protokolls (E64): „gestempelt 08:00–18:00 · angerechnet 7:30 h · 2:30 h zwischen den Blöcken nicht angerechnet" |
| Hülle **und** Lücke | „gestempelt 07:00–19:00 · angerechnet 8:00 h (07:45–18:15) · 4:00 h nicht angerechnet, davon 2:30 h zwischen den Blöcken" (K7; K20: „gestempelt 07:00–18:00 · angerechnet 7:45 h (07:45–18:00) · 3:15 h nicht angerechnet, davon 2:30 h zwischen den Blöcken") |
| Pause > 0 (zusätzlich zu einer der Zeilen oben) | „angerechnet 7:00 h" bekommt den Zusatz „nach 0:30 h Pause" (K9) |
| `auto_closed` (P18) | „eingestempelt 08:00, nicht ausgestempelt – automatisch geschlossen · angerechnet 7:45 h (08:00–18:15)" + bei Lücke „· 2:30 h zwischen den Blöcken nicht angerechnet" (K15); ohne Blöcke „… automatisch geschlossen um 23:59" |
| `credit_override` | Kennzeichen „anerkannt" (grau), keine Kappungszeile |
| Mitarbeiter-Ansicht, `not_credited_minutes` > 0, nicht anerkannt | zusätzlich Aktion „Anrechnung beantragen" (P21, 14) |

Genutzt in `MonthlyJournal.tsx` (`:800-801`), `TimeTracking.tsx` (`:884/890`; die
Inline-Kopie der Mobilkarte `:992-1000` wird durch die Komponente ersetzt) und
`AdminDashboard.tsx` (`:1490/1494`). Testfälle K1, K7, K9, K15, K20 in
`RawStampNote.test.tsx`.

### 13.2 Monatsjournal

`services/journal_service.py` liefert je Eintrag `uncredited_minutes`,
`not_credited_minutes`, `credit_override` und `auto_closed` (wie `raw_*` seit #485) und im
Monats-Summary `not_credited_minutes_total` = Σ `not_credited_minutes` (P19, Lücke **und**
Hülle). `MonthlyJournal.tsx` zeigt in der Zusammenfassung die Zeile „Anwesenheit nicht
angerechnet: 7:30 h" (nur wenn > 0) — das Etikett deckt damit genau das ab, was es sagt.

### 13.3 Anerkennen

`POST /api/admin/time-entries/{entry_id}/credit-override` (`require_admin`, F-026):

1. `user_id` des Eintrags ohne Sperre lesen (404, wenn nicht im Mandanten), dann
   **zuerst** `lock_user_row` der Person, **danach** den Eintrag mit `with_for_update`
   laden (Muster `clock_in`). Dieselbe Reihenfolge wie `create_working_hours_change`
   (Anker vor Zeile) — umgekehrt verklemmten sich Anerkennen und eine parallele
   Neukappung desselben Eintrags (PostgreSQL 40P01 → 500).
2. Offen → 400. `auto_closed` → 400 „Automatisch geschlossener Eintrag: Bitte zuerst das
   tatsächliche Ende eintragen." (P18). Bereits `credit_override` → 200 ohne Änderung
   (idempotent, kein Protokoll).
3. Neue Zeiten: `start = raw_start_time or start_time`, `end = raw_end_time or end_time`;
   UNIQUE-Prüfung gegen andere Einträge des Tages → 409.
4. Setzen: `start_time`, `end_time`, `raw_start_time = None`, `raw_end_time = None`,
   `uncredited_minutes = 0`, `credit_override = True`.
5. Protokoll: `source="credit_override"` (15 Zeichen), `action="update"`, alte/neue
   effektive Zeiten, `old_note` = `credit_summary_text(vorher)` (z. B. „angerechnet 7:30 h,
   nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken"), `new_note` „angerechnet
   10:00 h — von der Verwaltung anerkannt" bzw. „… — auf Antrag der beschäftigten Person
   von der Verwaltung anerkannt" (P21).
6. §3/§4/48 h und Anwesenheits-Prüfungen nur als **weiche** Warnungen in
   `TimeEntryResponse.warnings` (P4).
7. Antwort 200 `TimeEntryResponse`.

Derselbe Ablauf ab Schritt 2 läuft bei der Genehmigung eines Antrags mit
`request_credit_override` bzw. „genehmigen und anerkennen" (7.1 Nr. 9) — im Pfad von
`review_change_request`, der die Ankersperre schon hält.

UI: Knopf „Anerkennen" an Einträgen mit `not_credited_minutes > 0` (Admin-Dashboard-
Detailtabelle, Monatsjournal in der Admin-Ansicht); bei `auto_closed` deaktiviert mit dem
Text aus Schritt 2. Bestätigung:
„Die gesamte gestempelte Zeit (08:00–18:00) wird angerechnet. Sie bleibt angerechnet —
auch bei späteren Neuberechnungen und wenn die Verwaltung die Zeiten ändert; Mitarbeitende
können den Eintrag danach nur noch per Änderungsantrag ändern. Wurde nur ein Teil der Zeit
gearbeitet, den Eintrag besser aufteilen oder korrigieren. Der Vorgang wird protokolliert."

Dauerhaftigkeit: `reclamp_time_entries` überspringt den Eintrag (`credit_override`), jede
Aufrufstelle von `clamp` reicht das Flag durch. Kein Pfad setzt es zurück (P3); eine
eigene Rücknahme gibt es nicht (P11).

---

## 14. Mitarbeitende / Transparenz

- **Profil** (`pages/Profile.tsx`, Karte „Meine Arbeitszeit"): heute gültige Blöcke je
  Wochentag mit Tagessoll und der Verlauf („ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00
  (Pause 30 Min) …") aus `GET /api/auth/me/work-schedule`:

  ```json
  {
    "today": {"date": "2026-10-08", "blocks": [ …5 Tage… ], "day_targets": [6.5, 5.0, 0, 4.0, 0],
              "weekly_hours": 15.5},
    "history": [{"effective_from": "2026-09-01", "effective_until": null,
                 "blocks": [ … ], "day_targets": [ … ], "weekly_hours": 15.5}]
  }
  ```

  Datumsaufgelöst über `get_schedule_for_date`, nie aus `users.work_blocks` direkt.
  Kein Freitext `note` (P12). Nur eigene Daten (`current_user`), F-026.
- **Dashboard-Hinweise** (`pages/Dashboard.tsx`, P20):
  `MonthlyDashboard.schedule_change_notices` = alle Sammelzeilen (10.2) mit
  `user_id = current_user.id`, `source = 'wh_reclamp'`, `time_entry_id IS NULL`,
  `old_date IS NULL AND new_date IS NULL`, `created_at ≥ jetzt − 30 Tage`, jüngste zuerst,
  **nur** solche, die `parse_summary_note` erfolgreich liest (eine Einzelzeile, deren
  Eintrag später gelöscht wurde, verdrängt so keinen echten Hinweis). Text je Zeile:
  - Anlegen, `effective_from` ≤ heute: „Ihre Arbeitszeit wurde ab 01.09.2026 geändert
    (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00)."
  - Anlegen, zukunftsdatiert: „Ihre Arbeitszeit ändert sich ab 01.11.2026 (neu: …)."
  - Löschen: „Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen."
  - Zusatz bei n > 0: „ 3 Einträge neu berechnet, angerechnete Zeit −2:15 h."
  - Zusatz bei Verkürzung: „ Rückwirkende Verkürzung – Grund: Erfassungsfehler
    korrigiert." (nur der feste Grundtyp, nie der Freitext, P12)
  „neu: …" ist der Kurztext des **heute** für `effective_from` aufgelösten Snapshots
  (`get_schedule_for_date`); ohne Blöcke der #415-Text („25,0 h/Woche"). Link auf das
  Profil. Keine Bestätigungstabelle; jeder Hinweis verschwindet nach 30 Tagen. Unter
  Impersonation sichtbar wie alles andere. Test: Eintrag nach der Neukappung löschen →
  Hinweis bleibt.
- **Status in der Lücke** (`Dashboard.tsx:362-383`): `shouldBeClockedIn` (heute
  `isWorkday && !isClockedIn`) wird gerade im **nicht** eingestempelten Zustand rot —
  deshalb kommen `blocks_today`/`grace_minutes` aus jedem Zweig von `clock-status` (11.1).
  Liegt die aktuelle Uhrzeit in einer **ungeschrumpften** Lücke (Ende Block i bis Beginn
  Block i+1 — laut Plan beginnt die Pause um 12:00, nicht um 12:15), ist `shouldBeClockedIn`
  false und die Karte zeigt neutral „Pause zwischen den Arbeitsblöcken" statt rot. Die
  geschrumpfte Lücke gilt nur für Anrechnung und Warntext. Vitest: nicht eingestempelt,
  12:05 bzw. 13:00, Blöcke 08–12 + 15–18 → neutral.
- **Zeiterfassung** (`TimeTracking.tsx`): `RawStampNote` mit Lückenzeile; Von/Bis neuer
  Einträge werden aus den heutigen Blöcken vorbelegt (erster Beginn, letztes Ende).
- **Anrechnung beantragen** (P21): an eigenen geschlossenen Einträgen mit
  `not_credited_minutes > 0`, nicht anerkannt, Aktion „Anrechnung beantragen" in
  Zeiterfassung und Monatsjournal → Änderungsantrag (UPDATE, Zeiten = Rohstempel,
  `request_credit_override=true`, Begründung Pflicht). Bei `auto_closed` muss die Person
  das tatsächliche Ende im selben Antrag angeben. Bei anerkannten Einträgen ist das direkte
  Bearbeiten gesperrt (409, P3); die Oberfläche bietet stattdessen „Änderung beantragen".
- **Warnungen** beim Stempeln/Erfassen über `showArbzgWarnings` (Abschnitt 6.2/8); die
  Lückentexte enthalten den Hinweis auf „Anrechnung beantragen" (6.2).
- **Datenschutzseite** (`pages/Privacy.tsx:84`): Kategorie „Soll-Arbeitszeiten
  (Arbeitszeit-Blöcke, Pause) und nicht angerechnete Zeit" **plus** eine kurze
  Beschreibung der Logik (Art. 13 Abs. 2 lit. f DSGVO, soweit Art. 22 einschlägig): „Ihre
  Arbeitszeit wird in Blöcken hinterlegt. Gestempelte Zeit vor dem ersten Block, nach dem
  letzten Block und zwischen den Blöcken wird – abzüglich eines Puffers – automatisch nicht
  angerechnet; die Stempelzeiten bleiben gespeichert. Die Verwaltung kann nicht angerechnete
  Zeit anerkennen; Sie können die Anrechnung per Änderungsantrag beantragen."

---

## 15. Export, Berichte, DSGVO

### 15.1 Datei-Exporte (§16)

Spalte **„Nicht angerechnet (Min)"** am **Ende** angehängt (#415-Regel), Wert je Tageszeile
= Σ `not_credited_minutes` (P19: Lücke **und** von der Hülle gekappte Anwesenheit, ohne die
synthetische Auto-Close-Endseite) der Einträge des Tages (ganze Minuten), Summenzeile = Σ
Monat. Der Spaltenname bleibt; die Datei zeigt gekappte Von/Bis-Zeiten, die Spalte macht
die gesamte nicht angerechnete Anwesenheit sichtbar (K7: 240, nicht 150):

| Fläche | Stelle |
|---|---|
| XLSX-Monatsblatt | `services/export_service.py:498, 594-619`; falscher Kommentar „Netto = Stempelzeit" (`:736-740`) wird korrigiert („Netto = angerechnete Zeit; nicht angerechnete Lückenzeit steht in der letzten Spalte") |
| XLSX-Jahres-Mitarbeiterblatt | `export_service.py:1085, 1186-1211` |
| PDF-Monat | `export_service.py:1762` (Spaltenbreiten auf 267 mm neu verteilen), `:1845`, `:1881-1901`; Kopf zweizeilig „Nicht angerechnet / (Min)"; `escape_pdf_text`, nur Helvetica-taugliche Zeichen |
| ODS Monat/Jahr | `services/ods_export_service.py:222-226, 287-299, 595-599, 659-670` |

`absence_day_target(..., worked_hours=net)` (`export_service` 666/1938, ODS-Gegenstücke)
folgt dem Hybrid und bleibt unverändert. Rohstempel in Dateien: Folgeticket.

### 15.2 Berichtstext der Vertragsänderungen (#415)

`calculation_service.ScheduleSegment`/`weekly_hours_segments` (`:139-238`) führen Blöcke
und Pausen mit; neue Funktion `blocks_changed(prev, seg)` neben `work_days_changed`
(`:241`) ist die einzige Quelle für Text und API-Feld. `format_weekly_hours_history`
(`export_service.py:217-357`) und der Frontend-Zwilling
`utils/formatters.ts::formatWeeklyHoursChanges` (wortgleich):

- Segment ohne `blocks_changed` → bisheriger Wortlaut **byte-identisch**.
- Segment mit `blocks_changed` und neuen Blöcken:
  `ab 01.09.2026: Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00 = 11,5 h/Woche`
  (nur Tage mit Blöcken; „(Pause … Min)" nur bei Pause > 0).
- Segment mit Altfenster: `… / Fr 07:30–23:59 (nur Kappung)`.
- Segment, das Blöcke entfernt: bisheriger Wortlaut plus „ · ohne Arbeitszeit-Blöcke".
- PDF-Kurzform (Schriftgröße 8): `Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00`.

Flächen: XLSX-Monatsblatt, Jahresübersicht, Jahres-Mitarbeiterblatt (`:474-480`,
`:910-917`, `:1074-1080`), PDF-Meta (`:1792-1800`), ODS (`:196-201`, `:489-503`,
`:583-589`), `/admin/reports/monthly|weekly` (`schemas/reports.py:79-134`,
`routers/reports.py:147-173, 294-318`) → Admin-Dashboard. Überlauf: nur Zelle F1 hat
`_attach_overflow_comment` (`:272-298`); lange Blocktexte laufen dort in den Kommentar.

### 15.3 Art. 15 / Art. 20 DSGVO

| Fläche | Neu |
|---|---|
| `lifecycle_service._user_dict` (`:509-589`) | `work_blocks` (Strings wie gespeichert), Verlaufszeilen mit `blocks` und `note` |
| `lifecycle_service._time_entry_dict` (`:592-610`) | `uncredited_minutes` (int), `credit_override` (bool), `auto_closed` (bool) |
| Änderungsanträge im Art.-15/20-Export (sofern dort geführt) | `request_credit_override` (bool), `original_uncredited_minutes` (int oder null) |
| `routers/auth.py /me/export` (`:538-637`) | dieselben Felder |
| `routers/superadmin.py` §16-Notfallexport (`:55-130`) | `uncredited_minutes` je Eintrag; Mandantenfilter (`:229`) bleibt Pflicht |
| Art.-15-Kategorien (`lifecycle_service.py:820-837`) | „Soll-Arbeitszeiten (Arbeitszeit-Blöcke, Pause, Verlauf)", „nicht angerechnete Zeit und Anerkennungen" |

Nur `str`/`int`/`bool` in den rohen JSON-Pfaden — ein `time`- oder `Decimal`-Objekt macht den
Export für jede Person zu HTTP 500 (#383/#408). Test mit `json.dumps` auf dem Ergebnis.

### 15.4 Anonymisierung und Aufbewahrung

- `lifecycle_service.anonymize_tenant` (`:214-456`): `working_hours_changes.note` aller
  Zeilen des Mandanten → NULL.
- `admin_users.anonymize_user` (`:726-872`): `note` der Verlaufszeilen der Person → NULL.
- Blöcke bleiben (reine Zeitwerte, kein Freitext).
- `wh_reclamp`-/`credit_override`-Protokollzeilen fallen unter den bestehenden
  Notiz-Scrub: eigene Zeilen → Notizen NULL, fremde Zeilen → Fundstelle ersetzen, jeweils
  über die Objektschicht mit `compute_row_hash()`-Neuberechnung (#121).
- `purge_user` (`:876-1000`): keine Änderung, kein neuer FK auf `users`.
- Aufbewahrung: keine neue Löschfrist. Zeiteinträge, Verlauf und Protokoll leben wie
  bisher bis zum Art.-17-Löschen bzw. zur Mandantenlöschung. Pflicht mindestens 2 Jahre
  (§ 16 Abs. 2 ArbZG, § 17 Abs. 1 MiLoG) — ein Löschlauf darunter wäre unzulässig; darüber
  hinaus berechtigtes Interesse bis zum Ende der Verjährung von Vergütungsansprüchen
  (§§ 195, 199 BGB: 3 Jahre ab Jahresende); Lohnunterlagen ggf. länger (§ 28f SGB IV,
  § 147 AO).
- RLS/F-026: keine neue Tabelle; jede neue Abfrage trägt `tenant_id`.
- Backup/Restore (`backup_service.py:265-331`, `tools/docker/restore.sh`,
  `praxiszeit-server.py:1049-1075`): keine Änderung; 073 läuft nach Restore eines alten
  Dumps erneut (5.2).

---

## 16. Doku-Flächen + CLAUDE.md

### 16.1 Nutzer-Doku (5 Sync-Flächen)

| Fläche | Dateien |
|---|---|
| (1) Quelle | `docs/handbuch/HANDBUCH-ADMIN.md` (`:26, 188, 217-262, 635-640, 911-913`), `HANDBUCH-MITARBEITER.md` (`:16, 187-194, 405, 570-571`), `CHEATSHEET-ADMIN.md` (`:43-56, 156`), `CHEATSHEET-MITARBEITER.md` (`:58-62, 129, 176`), `SCHNELLSTART.md` (`:44-45`); `docs/BERECHNUNGEN.md` (`:64, 125-162, 239-241`); `docs/GLOSSAR.md` (`:27-28`, Begriffe „Arbeitszeit-Block", „Lücke", „nicht angerechnet", „Anerkennen", „Neukappung") |
| (2) In-App | `frontend/src/components/DocViewer.tsx` (`:195-198, 316-323, 356, 416-420, 525, 607-612`), `constants/helpContent.tsx:198-216` |
| (3) Spiegel | `frontend/public/help/*.md` byte-identisch (`diff -q`) |
| (4) pzweb (eigener PR, Tests in `node:20` glibc) | `HandbuchAdmin.tsx` (`:176, 233-352, 506-509`), `HandbuchMitarbeiter.tsx` (`:198-215`), `AnleitungBerechnungen.tsx` (`:170-200, 259-268`), `HandbuchAdmin.test.tsx:46` |
| (5) Schnellstart | `SchnellstartAdmin` (Knopfname „Arbeitszeit anpassen…") |

Pflichtinhalte:

- Blöcke, Pause innerhalb der Blöcke, Tagessoll-Ableitung, Puffer an jedem Blockrand
  (Beispiel K1 mit 7:30 h).
- Wortlaute aus 6.2 und 13.1 wörtlich zitiert.
- Rückwirkung: Vorschau (Soll- und Ist-Differenz getrennt), Verlängerung/Verkürzung,
  Schutzpaket je Grundtyp, Sperre abgeschlossener Jahre, Löschen mit „auf vorherigen Stand
  zurücksetzen", Dashboard-Hinweis an die Mitarbeitenden bei jeder Änderung.
- **Kasten Vergütung:** „Nichtanrechnung ersetzt keine Vergütungsentscheidung. Tatsächlich
  geleistete Arbeit, die angeordnet, gebilligt oder geduldet wurde oder zur Erledigung der
  Arbeit notwendig war, ist zu vergüten (§ 611a Abs. 2, § 612 Abs. 1 BGB; MiLoG). Wurde
  vor, nach oder zwischen den Blöcken gearbeitet, nutzen Sie „Anerkennen"; wurde nur ein
  Teil gearbeitet, den Eintrag aufteilen oder korrigieren statt die ganze Zeit
  anzuerkennen."
- **Kasten Arbeitsrecht/Mitbestimmung (volle Fassung):** „Ändert sich durch die Blöcke der
  Umfang der Arbeitszeit (Tagessoll/Wochenstunden), ist das eine Vertragsänderung und
  braucht das Einverständnis der beschäftigten Person (sonst Änderungskündigung, § 2 KSchG;
  bei Teilzeit §§ 8, 9 TzBfG). Die Lage kann, soweit der Vertrag sie nicht festlegt, im
  Rahmen des Direktionsrechts (§ 106 GewO) nach billigem Ermessen und mit angemessener
  Ankündigung nur für die Zukunft geändert werden (Arbeit auf Abruf: mindestens 4 Tage
  vorher, § 12 Abs. 3 TzBfG). Vereinbarte Arbeitszeiten und Ruhepausen sind wesentliche
  Vertragsbedingungen (§ 2 Abs. 1 Satz 2 Nr. 7 NachwG); eine Änderung ist spätestens am Tag
  des Wirksamwerdens schriftlich mitzuteilen (§ 3 NachwG). Mit Betriebsrat sind Lage,
  Verteilung und Pausen (§ 87 Abs. 1 Nr. 2 BetrVG), vorübergehende Änderungen der
  betriebsüblichen Arbeitszeit (Nr. 3) und die Kappung als technische Einrichtung (Nr. 6)
  mitbestimmungspflichtig; ohne Zustimmung ist die Maßnahme gegenüber den Beschäftigten
  unwirksam. PraxisZeit prüft das nicht." Der Dialog zeigt die Kurzfassung aus 12.1.
- **JArbSchG-Hinweis:** „Für Jugendliche gelten strengere Pausen- und Schichtzeitregeln
  (§§ 11, 12 JArbSchG: 30 Min Pause ab 4,5 h, 60 Min ab 6 h, höchstens 4,5 h ohne Pause,
  Schichtzeit inklusive Lücke höchstens 10 h); PraxisZeit prüft diese nicht."
- **Mitarbeiter-Handbuch:** nicht angerechnete Zeit erkennen (Wortlaute 13.1), „Anrechnung
  beantragen" (P21), Dashboard-Hinweis bei Änderungen, anerkannte Einträge nur per Antrag
  änderbar.
- Bekannte Grenze: Arbeit in der Lücke bleibt in der angerechneten Zeit unsichtbar, bis sie
  anerkannt wird; §6-Nachterkennung auf Rohstempeln folgt separat.
- Release-Notes: Auto-Close kappt jetzt (Abend wird nicht mehr voll angerechnet).
- Weitere Texte: `Profile.tsx:369-373`, `Privacy.tsx:84`, `admin/Reports.tsx:362`.
- Screenshots: `e2e/capture-handbook-screenshots.ts:168/181`,
  `tools/handbook/handbuch-screenshots.js:178/196`, `docs/handbuch/screenshots/16-*.png`,
  `17-*.png`; Demo-Person mit Blöcken in `create_handbuch_testdata.py`
  (`set_superadmin_context`, `TENANT_ID`).
- Technik-Doku: `docs/BACKEND-ARCHITEKTUR.md` (`:118-127, 150, 155`),
  `docs/specs/dsgvo` (Verarbeitungsverzeichnis: Kategorien aus 15.3; Rechtsgrundlage wie
  Anhang A.2: Art. 6 Abs. 1 lit. b und lit. c DSGVO, § 26 BDSG nach EuGH C-34/21 nur
  ergänzend).

### 16.2 CLAUDE.md (neue/geänderte Regeln)

1. **Arbeitszeit-Blöcke (ersetzt die #201-Regel):** `working_hours_changes.blocks` /
   `users.work_blocks`, Liste[5] Mo–Fr, `"HH:MM"`, max. 3 Blöcke, Raster 5. NULL in einer
   Verlaufszeile = keine Blöcke, **nie** Rückfall. `pause_minutes` NULL = Altfenster aus
   073 (nur Kappung, keine Soll-Wirkung). Neue Blöcke materialisieren `hours_*`,
   `weekly_hours`, `work_days_per_week`, `use_daily_schedule=True` beim Schreiben —
   `calculation_service` liest nie Blöcke fürs Soll. Einzige Leseschnittstelle:
   `get_schedule_for_date` → `work_window_service.get_scheduled_blocks`.
2. **`clamp` liefert `ClampResult` (5 Felder), `credit_override` ist Pflicht-Schlüsselwort.**
   Beginn in der Lücke wird nie verschoben (UNIQUE `uq_tenant_user_date_start`); die
   Lücke läuft über `uncredited_minutes`. Puffer an jedem Blockrand, Lücke schrumpft um 2g.
   Jede neue Schreibfläche für Zeiteinträge: `clamp` + `uncredited` + Warnung, und die
   Netto-Helfer `_calculate_daily/weekly_net_hours` mit `uncredited_minutes`.
3. **`net_hours` = Ende − Beginn − Pause − `uncredited_minutes`** (Python **und** SQL,
   Paritätstest auf PG mit Toleranz n × 0,005 h — Python rundet je Zeile, SQL nicht, und
   das bleibt so wegen der Byte-Identität bestehender Summen). Keine Inline-Netto-Rechnung
   ohne `uncredited`.
4. **Neukappung** (`reclamp_time_entries`): Quelle Rohstempel, nur geänderte Wochentage,
   aktueller Puffer, erst Zeiteinträge, dann `retarget_absence_hours` (mit F1), eine
   Transaktion unter `lock_user_row`, Protokoll `wh_reclamp` je Eintrag + Sammelzeile im
   Router, Vorschau rollt zurück und protokolliert nie. Rückwirkende **Verkürzung** nur
   mit Grund/Haken, in abgeschlossene Jahre gesperrt.
5. **`credit_override`** überlebt jede Neuberechnung und jede Zeitänderung durch die
   Verwaltung (Direktbearbeitung, Antragsgenehmigung, XLS-Überschreiben); kein Pfad setzt
   es still zurück. MA-`PUT` auf einen anerkannten Eintrag → 409 (nur per Antrag).
6. **#431-Satz erweitern:** „Bei jedem neuen Soll-Treiber … gehört das Feld in den Snapshot"
   gilt auch für Kappungsregeln (Blöcke, Pause).
7. **`time_entry_audit_logs.source`-Liste** um `wh_reclamp`, `credit_override` ergänzen;
   Sammelzeile bei **jedem** Anlegen/Löschen einer Arbeitszeit-Änderung (erkennbar an
   `time_entry_id IS NULL AND old_date IS NULL AND new_date IS NULL`, Parser in
   `reclamp_audit.py`).
8. **Ankersperre zuerst:** Jeder Schreibpfad für Zeiteinträge nimmt `lock_user_row` als
   erste Anweisung, vor Snapshot-Auflösung und `clamp`, und **immer vor** einer Zeilensperre
   auf `time_entries` — sonst kappt ein paralleler Schreiber unter dem alten Snapshot
   (READ COMMITTED) bzw. verklemmen sich Anerkennen und Neukappung (40P01 → 500).
9. **`auto_closed`:** `raw_end_time = 23:59` eines automatisch geschlossenen Eintrags ist
   kein Stempel — nie anerkennen, nie als Anwesenheit oder „nicht angerechnet" zählen.
10. **„Nicht angerechnet" = Lücke + Hülle** (`not_credited_minutes`, eine Quelle +
    Frontend-Zwilling); „angerechnet" = `net_hours`. Neue Anzeige-/Exportflächen nutzen den
    Helfer, nie `uncredited_minutes` allein.

---

## 17. Tests

TDD; Backend-Suite mit beiden `--ignore=` plus Postgres-Lauf
(`test_tenant_rls.py`, `test_concurrency.py`), Frontend `npx vitest run --pool=threads`,
alles zusammen über `bash scripts/local-ci.sh`.

### 17.1 Migration (`tests/test_073_work_blocks_migration.py`)

- Backfill: zweiseitiges Fenster; halboffen (nur Beginn → 23:59, nur Ende → 00:00);
  Beginn ≥ Ende → leerer Tag; Sekunden abgeschnitten; Konto ohne Fenster → NULL;
  alle Verlaufszeilen des Kontos tragen denselben Wert; Diagnose-Marker in der Ausgabe
  (`capsys`).
- Konto mit **nur** invertierten Fenstern (alle fünf Tage leer): `users.work_blocks` und
  alle Verlaufszeilen bleiben NULL, keine Zählprobe-Abweichung, **keine**
  Segmentänderung in `weekly_hours_segments`/#415-Text (3.3, 5.2).
- `auto_closed`-Backfill: Eintrag mit `auto_close`-Protokollzeile und Ende 23:59 → true;
  mit später korrigiertem Ende → false; `net_hours` unverändert.
- Byte-Identität: für eine Stichprobe von Daten vor/nach der Migration gleiches
  `get_daily_target_for_date`, gleiches `net_hours` je Eintrag, gleiches
  `get_overtime_account`.
- Kappungsparität: `clamp` nach 073 liefert für Einträge an Altfenster-Tagen dieselben
  `eff_*`/`raw_*` wie der 072-Code (Falltabelle aus `test_work_window_service.py:25-45`
  übernommen, inkl. halboffen).
- Downgrade: erster Block → `scheduled_*`; Platzhalter → NULL; Diagnose nennt
  Mehrblock-Personen, `uncredited > 0`, `credit_override`, offene Anrechnungs-Anträge;
  alle neuen Spalten (auch `auto_closed`, `request_credit_override`,
  `original_uncredited_minutes`) entfernt.
- **Postgres-Round-Trip** auf Wegwerf-PG18 mit der Prod-Kopie: `alembic upgrade 073` →
  `downgrade 072` → `upgrade 073`; Tabellenvergleich order-unabhängig
  (`count(*) + md5(string_agg(t::text ORDER BY t::text))`) für `time_entries`,
  `working_hours_changes`, `users` (ohne die neuen Spalten) — identisch bis auf die
  diagnostizierten Fälle; Backfill als `praxiszeit` unter FORCE RLS trifft alle Zeilen.

### 17.2 Schema und API

- `test_work_blocks_validation.py`: jede Regel aus 3.4 (Grenzwerte: 3 vs. 4 Blöcke,
  Raster 08:05 vs. 08:07, Pause = Σ, aneinanderstoßende Blöcke, leere Woche, 60 h).
- `test_users_api_work_blocks.py`: `PUT` mit `work_blocks` → 400; `PUT`/`POST` mit
  `scheduled_start_monday` → 400 „Bitte Seite neu laden" (erkannt per Präfix, 11.4);
  `POST` mit `work_blocks` leitet `hours_*`/`weekly_hours`/`work_days_per_week` ab und
  überschreibt mitgeschickte Werte, kein 422 (4.2);
  **Login** und `GET /admin/users` einer Person mit Altblöcken `"07:37"`/`"23:59"` → 200;
  `work_blocks_today` datumsaufgelöst (zukunftsdatierte Zeile wirkt nicht heute).
- `test_wh_change_blocks.py`: reine Blockänderung erzeugt Basis-Zeile und Segment;
  `_comparable_snapshot` erkennt Blöcke; NULL und „5× leer" gelten als gleich;
  Pausenänderung → neues Soll, keine Neukappung; Altfenster-Übernahme in „Gleichmäßig"
  aus dem **Vorgänger**-Snapshot (Zeile zwischen eine mit und eine ohne Fenster eingefügt);
  `remove_legacy_window`; Wechsel von neuen Blöcken nach „Gleichmäßig" setzt `blocks` NULL,
  auch bei `track_hours=false` (P24); `blocks` + `weekly_hours` → 422; Vorschau ist `POST`
  mit JSON-Body; **unfertiger** Body (Pause ≥ Σ, Block unvollständig, Raster) → 200 mit
  `blocked_reason`, kein 422 (11.1).
- `test_work_blocks_plan_notices.py`: `block_break_notices` (P9) — 07:00–12:00 +
  12:10–17:10 bei Pause 0 → §4-Hinweis (10 Min Lücke ist keine Pause); drei Blöcke mit
  2 × 20 Min Lücke bei 10:20 h → §4-Hinweis (40 < 45); Lücke 12:00–12:30 bei Puffer 15 →
  Hinweis „verschwindet"; Tagessoll > 10 h → §3-Hinweis, > 8 h → 24-Wochen-Hinweis,
  Woche > 48 h → Hinweis; `exempt_from_arbzg` → keine §3/§4-Hinweise; nie 422.
- `test_derive_targets.py`: Tabelle 4.1 inkl. 4,0833 → 4,08 und 7,9166 → 7,92; Kopplung an
  `get_daily_target_for_date`; drei Blöcke zu 55 Min → Saldo-Abweichung 0,01 h ≤ Grenze aus
  4.1.

### 17.3 Kappung und Schreibpfade

- `test_clamp_blocks.py`: Falltabelle K1–K21 inkl. Spalte „nicht angerechnet" und
  vollständiger Codeliste (Fall-IDs identisch im Frontend-Test); Invariante
  `sum(gap_segments) == uncredited`; Ergebnis hat 5 Felder (4er-Entpacken → `ValueError`);
  fehlendes `credit_override` → `TypeError`; `start=None` mit gesetztem Ende → kein
  Fehler (6.1); Vorlade-Parameter `wh_changes`/`soll_free_dates` liefern dasselbe Ergebnis
  wie ohne; `not_credited_minutes`/`presence_minutes` für K7, K8, K15, K20.
- `test_write_paths_uncredited.py`: parametrisiert über die **schreibenden** Stellen aus
  7.1 (1–6, 8, 9, 12, 13) — jede setzt `uncredited` und (außer 13) `auto_closed = false`;
  eigener Test für 7 und 10 (Genehmigung eines Teilschicht-Antrags „08–18, Pause 0" ohne
  422 und ohne Doppelzählung); eigener Test für 11 (`ImportedEntry.uncredited_minutes`
  gesetzt, Kappungsnotiz auch bei reinem Lückenfall K1 ohne `raw_*`); Formular-Re-Save
  (`unclamp_input`) behält `raw_*` und `uncredited`; Datumswechsel auf anderen Wochentag
  (MA- und Admin-Pfad) kappt neu **und** liefert die Warnung (Warn-Gate mit `date`, 7.1
  Nr. 4).
- `test_auto_close_blocks.py`: K15 inkl. `auto_closed = true`; ohne Blöcke bleibt 23:59
  (`auto_closed = true`); eine spätere Admin-Korrektur des Endes setzt `auto_closed =
  false`; Anwesenheit des Tages endet am wirksamen Ende (kein falsches
  `PRESENCE_DAILY_HOURS` bei einem weiteren Eintrag desselben Tages).
- `test_legacy_fixes_blocks.py`: E39 (Datumswechsel), E40 (Antrag „08–18, Pause 0" wird
  angenommen, gespeichert roh), E41 (keine Doppelzählung in der 48-h-Warnung).
- `test_xls_blocks.py`: `clamp_applies`; Tag ohne Blöcke behält mitgelieferte `raw_*`;
  `track_hours=false` + Blöcke behält mitgeliefertes `raw_*` (F27); Auto-Pause-Rest inkl.
  Aufrunden auf 15; `/confirm` ignoriert Client-`uncredited`; F-026-Filter; §5 auf
  Rohstempel; K1 als Import ohne §3/§4-Warnung aus `_check_arbzg` (8.2); Überschreiben
  eines anerkannten Eintrags behält `credit_override` und zeigt den Hinweis.
- `test_net_hours_parity_pg.py` (PG-only): `func.sum(TimeEntry.net_hours)` gegen
  Σ Python-`net_hours` für eine Menge mit `uncredited`, Pause, offenen Einträgen und
  5-Min-Werten wie K4 — gleich bis auf eine Toleranz von n × 0,005 h (6.1).
- `test_credit_override.py`: Anerkennen setzt Felder + Protokoll; idempotent; offen → 400;
  `auto_closed` → 400; Kollision → 409 (PG); §3-Überschreitung nur Warnung; überlebt
  Neukappung; **MA-`PUT` → 409**, Admin-Bearbeitung, Antragsgenehmigung (UPDATE) und
  XLS-Überschreiben **behalten** das Flag (P3); Antrag mit `request_credit_override` →
  Genehmigung setzt das Flag, Protokollnotiz „auf Antrag"; Antrag auf einen Eintrag ohne
  nicht angerechnete Zeit → 400; Bulk-Genehmigung übernimmt den Antragswert.
- `test_write_path_locks.py`: jeder Pfad aus P5 ruft `lock_user_row` vor `clamp` (Spy auf
  der Reihenfolge); Anerkennen sperrt Anker vor Eintrag.

### 17.4 ArbZG

- `test_arbzg_blocks.py`: §4 bestanden durch Lückensegment ≥ 15; Segment < 15 zählt nicht;
  §3 hart auf angerechneter Zeit (K7 → kein 400); `PRESENCE_DAILY_HOURS` (K7, K20);
  `PRESENCE_BREAK` (K1, K9 trotz bestandener harter §4-Prüfung, K19 bei angerechnet
  ≤ 6 h, Hüllen-Fall ohne Lücke mit eigenem Text); **kein** `PRESENCE_BREAK` bei K21
  (Pause 45) und K6 (harte Prüfung griff); `PRESENCE_WEEKLY_HOURS` (Mo–Fr 08–18 bei Blöcken
  08–12 + 15–18 → 50 h anwesend); `BREAK_IN_GAP` (K9); §18-Ausnahme unterdrückt alle;
  §5 nutzt Rohstempel nach Neukappung; `validate_daily_break` mit `tenant_id`; gespeichertes
  `uncredited` ≠ Σ Segmente (Puffer geändert) → gespeicherter Wert zählt, nicht als
  Pausenabschnitt (8.2).
- `test_24_week_presence.py`: 24-Wochen-Auswertung liefert `presence_hours`/
  `presence_average`; eine rückwirkende Verkürzung senkt den angerechneten Wert, nicht den
  Anwesenheitswert.

### 17.5 Rückwirkung und Protokoll

- `test_reclamp.py`:
  - Verlängerung: Werte, `affected_time_entries`, Monatssummen, Δ Saldo,
    `target_delta_hours`/`credited_delta_hours` (Beispiel „Verlängerung" aus 12.1);
  - Verkürzung ohne Grund → 400; mit Grund/Haken → ok, Grund in `note` und Sammelzeile;
    `sonstiges` ohne `other_reason_risk_confirmed` → 400; `retroactive_reason_text` mit
    9 Zeichen → 422;
  - `earliest_lossless_date` = heute bzw. morgen (geschlossener Eintrag heute; offener
    Eintrag heute, der nach P1 verliert);
  - **Verlängerung mit offenem Eintrag heute** → `is_shortening = false`, Eintrag nur
    `open` übersprungen (P1, Knickstellen-Prüfung); offener Eintrag, dessen Hülle sich
    verkürzt → `is_shortening = true`;
  - `earliest_lossless_date` erreicht die nächste Änderung → `null` +
    `earliest_lossless_note` (P25);
  - abgeschlossenes Jahr: Verkürzung 400, Verlängerung nur Warnung; **zwei**
    abgeschlossene Jahre mit Verlust → Meldung nennt das größere Y, Vorschlag 01.01.{Y+1};
  - offener Eintrag von gestern im Fenster → vorher geschlossen (Audit `auto_close` mit
    Admin), danach neu gekappt und protokolliert (P23);
  - MiLoG-Warnung bei `agreed_monthly_hours` ohne Konto-Flag; allgemeiner Satz bei jeder
    rückwirkenden Verkürzung;
  - **Idempotenz:** zweimal dieselbe Änderung anwenden → zweiter Lauf `changed == []`,
    keine neuen Protokollzeilen;
  - **Reversibilität:** anlegen + löschen → alle Einträge wieder byte-gleich (inkl. `raw_*`,
    `uncredited`);
  - nur geänderte Wochentage; Pausenänderung → 0;
  - Überspringen je Grund (offen, Feiertag, `track_hours=false`, außerhalb Fenster,
    `credit_override`, Kollision — Kollision auf PG);
  - „nicht erweiterbar" an der alten Kante ohne Rohstempel;
  - Vorschau: DB nach dem Aufruf unverändert, **keine** Protokollzeile;
  - F1-Misch-Tag: Krank + 4 h Arbeit, Tagessoll 8 → Abwesenheit 4 h nach Neukappung;
    zählt nicht als Verkürzung, `absence_f1_adjustments = 1` (P27);
  - F1 am Halbtags-Sondertag: 24.12. + Krank + 3 h Arbeit, Tagessoll 8 → Saldo des Tages 0
    (9.6);
  - `arbzg_findings`: rückwirkende Verkürzung senkt `weeks_over_48_credited_after`,
    `weeks_over_48_presence` bleibt;
  - Reihenfolge: Ist und Soll im selben Monat konsistent (`get_overtime_history` bitgleich
    zu `get_overtime_account` unter Stichtag).
- `test_reclamp_audit.py`: Anzahl Zeilen = `changed` + 1 Sammelzeile; **zukunftsdatierte
  Änderung ohne Einträge und Abwesenheiten erzeugt genau eine Sammelzeile mit
  `changed_by`**, ebenso das Löschen einer solchen Zeile und eine reine
  Wochenstunden-Änderung (P20); Notizformate; `parse_summary_note(summary_note(...))`
  Round-Trip für n = 0, 1, 2, 14, mit/ohne Verkürzung, mit Löschkennzeichen;
  `_audit_note_is_health_sensitive` ist für alle drei Grundtyp-Präfixe ohne Freitext
  `False`; `verify-integrity` grün nach Neukappung und nach Anonymisierung; `source` ≤ 40
  auf PG.
- `test_reclamp_concurrency.py` (PG-only, in `test_concurrency.py`-Stil), parametrisiert
  über `clock_out`, `create_time_entry`, `admin_update_time_entry`, CR-Genehmigung und den
  Auto-Close in `GET /clock-status`: der Schreiber wartet während einer laufenden Änderung
  auf die Ankersperre und kappt danach mit den neuen Blöcken; Anerkennen parallel zu einer
  Neukappung desselben Eintrags endet ohne Deadlock.
- `test_wh_change_delete_reclamp.py`: symmetrisches Löschen, `delete-preview`, Schutzpaket
  beim Löschen inkl. Variante „auf vorherigen Stand zurücksetzen" (P13: neue Zeile, keine
  Neukappung der Vergangenheit), früheste Zeile weiter gesperrt, Antwort 200/204.

### 17.6 Export, DSGVO, Guards

- `test_export_uncredited_column.py`: Spalte ist die **letzte** in XLSX-Monat,
  XLSX-Jahres-Mitarbeiterblatt, ODS (beide), PDF; Wert = Σ `not_credited_minutes` (K7 →
  240, K15 → 150); Summen; bestehende Spaltenpositionen unverändert.
- `test_format_blocks_history.py`: Texte aus 15.2; ohne `blocks_changed` byte-identisch zu
  1.19.3 (eingefrorene Fixtures aus `test_415_*`).
- `test_dsgvo_work_blocks.py`: `_user_dict`, `/me/export`, Superadmin-Export →
  `json.dumps` ohne Fehler, Felder vorhanden (inkl. `auto_closed`,
  `request_credit_override`, `original_uncredited_minutes`); Anonymisierung leert `note`
  (beide Pfade).
- `test_no_scheduled_columns.py`: in `app/` kommt **kein** Token `scheduled_start_` oder
  `scheduled_end_` vor (die Altfeld-Erkennung nutzt nur das Präfix `scheduled_`, 11.4;
  die Migration liegt in `alembic/`, nicht in `app/`). In `tests/` sind nur **Lesezugriffe**
  verboten (Muster `\.scheduled_(start|end)_` und `getattr\([^)]*["']scheduled_`), damit
  Tests die Altfelder als JSON-Schlüssel senden dürfen; ausgenommen sind
  `tests/test_073_*.py` (Backfill/Downgrade lesen die Spalten per SQL) und der Guard
  selbst.
- `test_no_live_work_blocks_read.py`: 9.8 (Liste der realen Lesestellen).
- `test_dashboard_schedule_notice.py`: Hinweis 30 Tage, nur eigene Zeilen; Hinweis auch bei
  n = 0 (Änderung „ab heute", zukunftsdatiert, Löschung) mit den Texten aus 14;
  Neukappungs-Zusatz nur bei n > 0; Verkürzung nennt nur den Grundtyp; eine Einzelzeile,
  deren Eintrag gelöscht wurde (`time_entry_id` NULL), verdrängt den Hinweis nicht.
- Anzupassende Suiten (Anhang B, Gruppe 7): u. a. `test_work_window_service.py`,
  `test_work_window_integration.py`, `test_xls_import_service.py`, `test_endpoints.py`,
  `test_release_1_19_1_review.py`, `test_fix2_update_keeps_raw.py`,
  `test_retarget_absence_hours.py`, `test_wh_change_preview.py`, `test_415_*`,
  `test_449_schedule_preload.py`, `test_audit_integrity.py`, `test_break_validation.py`.
  Fälle, die einen realen Vorfall kodieren, werden umgeschrieben, nicht gelöscht.

### 17.7 Frontend (Vitest)

`workBlocks.test.ts` (K1–K21, `deriveTargets`, `notCreditedMinutes`, Validierungstexte),
`WorkingHoursModal.test.tsx` (Editor, Live-Summen, POST-Body statt Query, stabiler
Effekt-Schlüssel, `blocked_reason` statt 422, Bestätigung bei `affected_time_entries > 0`
und Datum heute, Verkürzungs-Wahl: Option 1 wählen, dann zurück zu Option 2 —
`requestedDate` bleibt erhalten (F24), `earliest_lossless_date = null` → nur Option 2,
gesperrtes Speichern ohne Grund/Haken, „Sonstiges" mit zweitem Haken, Bestätigungstexte je
Grundtyp, Plan-Hinweise inkl. K6-Lücke, JArbSchG-Infozeile, Hinweis beim Moduswechsel weg
von Blöcken, Altfenster-Aktionen, `track_hours=false`, `[Löschen]` nur an der jüngsten
Zeile), `UserForm.test.tsx` (kein Fenster-Abschnitt, POST- und PUT-Payload ohne Schlüssel
mit Präfix `scheduled_`, `PUT` ohne `work_blocks`, Anlegen mit Blöcken), `Users.test.tsx`
(`displayBlocks`), `RawStampNote.test.tsx` (K1, K7, K9, K15, K20; Guard `raw === eff`;
„anerkannt"; „Anrechnung beantragen" nur in der Mitarbeiter-Ansicht),
`MonthlyJournal.test.tsx` (Summenzeile aus `not_credited_minutes_total`, Anerkennen,
deaktiviert bei `auto_closed`), `TimeTracking.test.tsx` (Mobilkarte nutzt Komponente;
Bearbeiten eines anerkannten Eintrags bietet „Änderung beantragen"),
`arbzgWarnings.test.ts` (vier neue Codes inkl. `PRESENCE_WEEKLY_HOURS`),
`formatters.test.ts` (Blocktexte wortgleich zum Backend), `StampWidget`/`breakValidation`
(keine Pausenabfrage, wenn die Lücke §4 deckt), `Dashboard` (nicht eingestempelt um 12:05
bzw. 13:00 bei Blöcken 08–12 + 15–18 → neutral; Hinweisliste mit allen Varianten),
`ImportXls` (Netto vom Server), `AuditValues.test.tsx`/`AuditLog` (Labels), `Reports`
(Spalte „Anwesenheit laut Stempel"), `Settings` (Puffer-Hinweis).

### 17.8 E2E (Playwright)

- Neu `e2e/tests/admin/work-blocks.spec.ts`, je Test **eigene** Mitarbeitende
  (`workers: 2`, sonst kappt eine Neuberechnung fremde Einträge):
  1. Anlegen mit Blöcken → Tagessoll in der Benutzerliste;
  2. Einträge per API, Admin verlängert rückwirkend → Vorschau zeigt Anzahl → Speichern →
     Journal zeigt neue Werte und Lückenzeile;
  3. Verkürzung: Standard „ab heute", dann rückwirkend mit Grund/Haken;
  4. Anerkennen im Admin-Dashboard;
  5. Mitarbeiter-Sicht: Profilkarte, Dashboard-Hinweis (auch nach einer Änderung „ab
     heute");
  6. Mitarbeiter beantragt Anrechnung, Admin genehmigt → Eintrag anerkannt.
- Anpassen: `prod-release-features.spec.ts:39-67` (Labels „Soll-Beginn Mo",
  API-Prüfung `scheduled_start_monday`), `user-management.spec.ts:51-226` (Knopf, Dialog,
  Verlaufs-Regex), `visual-prod-release.spec.ts:19-25`,
  `fixtures/test-data.fixture.ts:172-184, 243-256`.
- Vor dem Lauf erhöhte Auth-Rate-Limits (CLAUDE.md).
- Nach dem Merge: echter Login + Stempeln auf einem realen Host (Docker-Bundle und nativ),
  weil 073 Spalten löscht.

---

## 18. Außerhalb des Umfangs (Folgetickets)

| Thema | Grund |
|---|---|
| Blöcke am Samstag | Soll und Fenster kennen heute nur Mo–Fr (`hours_<tag>`, `get_daily_target_for_date`). |
| §6-Nachterkennung auf Rohstempeln | 16 Stellen, unabhängig von Blöcken. |
| #314-Re-Split der Betriebsferien bei Arbeitszeit-Änderung | Bestandslücke; Blöcke können Tage auf 0 h setzen. Falls nachgezogen, wie #448 nur bei eingeschaltetem Setting. |
| Rohstempel in Exportdateien | Eigene Spaltenfrage für §16-Dateien. |
| JArbSchG: Pausen und Schichtzeit für Jugendliche/Auszubildende (§ 4 Abs. 2, §§ 11, 12 JArbSchG) | 8–18 = 10 h Schichtzeit inkl. Lücke; strengere Pausen; braucht Kennzeichen „jugendlich". Bis dahin feste Infozeile im Dialog und im Handbuch (12.1, 16.1). |
| Warnschwelle für wiederholt nicht angerechnete Zeit | Rechtsbewertung Pflicht 8, separat. |
| Rücknahme einer Anerkennung | P11. |
| Live-Timer mit angerechneter Zeit im Dashboard | D34, später. |
| MA-`PUT` in die Vergangenheit (Datums-Validator in `TimeEntryUpdate`) | D16-Nebenbefund, eigenes Ticket. |
| Bearbeiten-Formular für Kollaps-Einträge | `admin_time_entries.py:262-274`; Bestandsproblem, unabhängig. |

---

## 19. Risiken & offene Punkte

1. **Ergebnis der Prod-Diagnose fehlt (Vorbedingung E25).** Bis Q1–Q6 auf der Prod-Kopie
   gelaufen sind, ist unbekannt, wie viele Fenster halboffen, invertiert, mit Sekunden oder
   auf der Kante ohne Rohstempel sind. Besonders „Beginn ≥ Ende": dort kollabiert heute jeder
   Eintrag des Wochentags auf 0 h; nach 073 wird an diesem Tag gar nicht mehr gekappt
   (künftige Einträge voll angerechnet, bestehende unverändert). Ergebnis hier nachtragen,
   bevor Task 1 beginnt.
2. **Aktueller statt historischer Puffer.** Wurde der Mandanten-Puffer seit der Erfassung
   geändert, kappt die Neukappung die betroffenen Wochentage mit dem neuen Wert; ebenso jede
   Einzelbearbeitung eines alten Eintrags. Die Vorschau nennt den Puffer, `Settings.tsx`
   weist darauf hin (12.3), §4 rechnet bei Abweichung mit dem gespeicherten `uncredited`
   (8.2). Speicherung je Eintrag: Frage 19.1 Nr. 8.
3. **Historische Compliance-Ergebnisse verschieben sich.** Der angerechnete Wert der
   24-Wochen-Auswertung (`reports.py:957-1080`) und die 48-h-Auswertung folgen `net_hours`;
   eine Neukappung ändert sie rückwirkend. Gegenmittel (P22): zweiter Wert „Anwesenheit
   laut Stempel", `PRESENCE_WEEKLY_HOURS`, `arbzg_findings` in der Vorschau. Exportdateien
   tragen keine Rohstempel (Folgeticket).
4. **Rückwirkende Soll-Erhöhung fällt nicht unter das Schutzpaket** — siehe Frage 19.1
   Nr. 1. Bis zur Entscheidung macht die Vorschau Soll- und Ist-Differenz getrennt sichtbar.
5. **Nicht erweiterbare Alteinträge.** Rohstempel, die vor 1.19.1 verloren gingen, sind
   unwiederbringlich; eine Verlängerung erreicht diese Einträge nicht. Ausgewiesen, nicht
   behebbar.
6. **Natives Update.** 073 löscht Spalten; scheitert die Migration, startet der Dienst nicht.
   Deshalb kein Abbruch in der Migration (nur Diagnose) und Test des Updates auf einer
   Prod-Kopie sowie nativ und per Docker auf einem realen Host.
7. **Mitbestimmung, Vertragsänderung, NachwG werden nicht geprüft.** Die Anwendung kann
   nicht erkennen, ob ein Betriebsrat zugestimmt hat, ob die Person einer Umfangsänderung
   zugestimmt hat oder ob die Änderung schriftlich mitgeteilt wurde; sie weist nur darauf
   hin (12.1, 16.1).
8. **Lange Transaktion bei großen Fenstern.** Keine Obergrenze (E52); eine Änderung über
   mehrere Jahre hält die Ankersperre der einen Person, bis gespeichert ist. Andere Personen
   sind nicht betroffen; Schreibvorgänge der Person warten (P5).
9. **Minijob ohne Kennzeichen.** Die MiLoG-Warnung erkennt Minijobber nur über
   `milog_working_time_account` oder `agreed_monthly_hours`; der allgemeine Mindestlohnsatz
   bei jeder rückwirkenden Verkürzung fängt den Rest auf (9.5).

### 19.1 Offene Fragen an den Betreiber

Die folgenden Punkte würden eine Protokoll-Entscheidung ändern oder legen sie aus. Sie
sind **nicht** (bzw. nur vorläufig, wie gekennzeichnet) eingearbeitet und brauchen eine
Antwort vor dem Plan für PR3 (Abschnitt 20).

1. **Verkürzung auch über Soll und Abwesenheits-Gutschrift definieren? (Review-Fund R1,
   betrifft E53/E54/E55; auch F19)**
   Das Protokoll definiert Verkürzung als „mindestens ein Eintrag verliert angerechnete
   Zeit". Im Block-Modell bestimmen die Blöcke aber auch das Soll: längere Blöcke oder eine
   kleinere Pause erhöhen rückwirkend das Soll vergangener Tage und senken das
   Überstundenkonto, ohne dass ein Eintrag verliert. Beispiel: Mo–Fr 08–12 rückwirkend ab
   01.01. → 08–12 + 13–15, Einträge 08:00–12:00 unverändert, Soll +2 h/Tag, Konto rund
   −380 h — heute eine „Verlängerung" mit nur dem Haken „Auswirkungen geprüft". Dasselbe
   gilt für Altfenster → Blöcke mit gleichen Zeiten, reine Pausenänderungen und die
   F1-Angleichung (9.6). Den **Umfang** der Arbeitszeit rückwirkend zu ändern, deckt nicht
   einmal § 106 GewO.
   **Empfehlung:** Ja. Verkürzung zusätzlich, wenn Δ Überstundenkonto im Wirkungsbereich
   < 0 (`overtime_after − overtime_before` einschließlich nachgezogener Abwesenheiten) oder
   irgendeine Abwesenheits-Gutschrift sinkt (F1). Dann dasselbe Paket wie E54 (Standard „ab
   ‹earliest_lossless_date›", rückwirkend nur mit Grundtyp, Freitext, Haken,
   MiLoG-Warnung, 400 bei Verlust in einem abgeschlossenen Jahr), auch beim Löschen.
   „Verlängerung" nur, wenn weder Netto noch Saldo sinken. Test: reine Soll-Erhöhung
   rückwirkend → 400 ohne Grund. Die Vorschau liefert die nötigen Werte schon
   (`target_delta_hours`, `credited_delta_hours`, `absence_f1_adjustments`).
2. **P1 bestätigen: Standard „ab morgen", wenn heute schon ein Eintrag verliert.**
   Das Protokoll sagt „effective_from = today". P1 verschiebt den Standard auf das
   früheste verlustfreie Datum (im Regelfall morgen), wenn heute bereits ein geschlossener
   Eintrag verliert oder der offene Eintrag nach der Knickstellen-Prüfung verlieren kann.
   **Empfehlung:** bestätigen — sonst kürzt „ab heute" die Arbeit von heute Vormittag
   rückwirkend, beim Ausstempeln über die normale Kappung sogar ohne Vorschau. Eine reine
   Verlängerung bleibt dank der Knickstellen-Prüfung „ab heute".
3. **Downgrade „aus dem ersten Block" (E24) — Bestätigung.** Für Mehrblock-Personen kappt
   das 072-Fenster nach einem Rückfall am Ende des **ersten** Blocks; ein
   Nachmittagseintrag kollabiert dann auf 0 h. Die Hülle (erster Beginn bis letztes Ende)
   wäre milder (Lücke würde angerechnet). Die Spec folgt dem Protokoll; die Diagnose nennt
   die betroffenen Personen. (Bestand vor diesem Review, nur hierher verschoben.)
4. **P13 bestätigen: Löschen mit Verkürzung bekommt die „ab heute"-Variante.**
   Das Protokoll verlangt beim Löschen „dieselben Regeln inkl. Verkürzungsschutz"; dessen
   Standard ist „ab heute". P13 setzt das als „Ab ‹Datum› auf den vorherigen Stand
   zurücksetzen" um (neue Verlaufszeile mit dem Vorgänger-Snapshot statt Löschen).
   **Empfehlung:** bestätigen. Alternative wäre „kein ‚ab heute' beim Löschen, nur mit
   Grund" (Stand vor dem Review) — weicht dann vom Protokollwortlaut ab.
5. **P23 bestätigen: offene Einträge vergangener Tage vor der Neukappung schließen.**
   Das Protokoll listet „offene Einträge" als übersprungen. Ein offener Eintrag von gestern
   würde sonst später vom Auto-Close unter dem **neuen** Snapshot geschlossen — Verlust ohne
   `wh_reclamp`-Zeile und ohne Klassifikation. **Empfehlung:** bestätigen; „übersprungen:
   offen" gilt dann nur für den Eintrag von heute.
6. **P24 bestätigen: Moduswechsel beendet neue Blöcke, auch bei `track_hours=false`.**
   Das Protokoll sagt „track_hours=false: Block-Editor ausgeblendet, gespeicherte Werte
   bleiben". P24 liest das als „bleiben, solange der Modus nicht gewechselt wird"; ein
   Wechsel nach „Gleichmäßig"/„Nach Tagen" setzt `blocks` = NULL (sonst Doppelpflege und
   ein Soll aus anderer Quelle nach Wiedereinschalten). **Empfehlung:** bestätigen.
7. **Beschriftung der Grundtypen ändern? (Review-Fund R10, betrifft E54)**
   „Erfassungsfehler korrigiert" ist mehrdeutig: falsche Stempel gehören am Zeiteintrag
   korrigiert (sonst bleibt der falsche Rohstempel als §16-Nachweis stehen); eine
   rückwirkende Blockänderung rechtfertigt nur eine **falsch hinterlegte Arbeitszeit**.
   Das Protokoll nennt die Typen „Erfassungsfehler korrigiert / einvernehmlich vereinbart /
   sonstiges". **Empfehlung:** Beschriftungen „Arbeitszeit war falsch hinterlegt
   (Fehlerkorrektur)", „Mit der beschäftigten Person vereinbart", „Sonstiges"; Schlüssel
   und Note-Präfixe bleiben. Eingearbeitet ist bis zur Antwort nur der Hilfetext („Falsche
   Stempelzeiten bitte am Zeiteintrag korrigieren, nicht über die Arbeitszeit."), die
   Bestätigungstexte je Typ und die Zusatzwarnung bei „Sonstiges" (P26).
8. **Angewandten Puffer je Eintrag speichern? (Review-Fund R16, betrifft E47)**
   Der Mandanten-Puffer ist nicht historisiert. Sinkt er (z. B. 15 → 0), verliert ein alter
   Eintrag bei **jeder** Einzelbearbeitung (Admin-Edit, Antragsgenehmigung, XLS-Überschreiben,
   Datumswechsel) bis zu 30 Min je Lücke plus 15 Min je Hüllenrand — nebenbei, ohne
   Verkürzungsschutz. Das Protokoll legt für die Neukappung den **aktuellen** Puffer fest.
   **Empfehlung:** neue Spalte `time_entries.clamp_grace_minutes` (bei jeder Kappung
   gesetzt) und Einzel-Neukappungen alter Einträge mit diesem Wert; die Massen-Neukappung
   bleibt beim aktuellen Puffer (Protokoll). Bis zur Antwort nur der Hinweis in
   `Settings.tsx` (12.3).

---

## 20. Umsetzungsphasen

Der Umfang (Migration mit Spalten-Drop, 13 Schreibpfade, 17 Netto- und 9 §4-Aufrufer, neue
ArbZG-Warnungen, Neukappung mit Schutzpaket, neue Endpunkte, drei Exportformate, Dialog,
UserForm, Journal, Dashboard, Profil, fünf Doku-Flächen und pzweb) ist für einen Plan oder
PR zu groß. Jede Phase bekommt einen eigenen Plan und PR; keine Phase wird allein
released.

| Phase | Inhalt | Verhalten nach dem Merge |
|---|---|---|
| **PR1 „Fundament, verhaltensneutral"** | Diagnose (E25) vorher; Migration 073 inkl. aller neuen Spalten und `auto_closed`-Backfill; Modelle; Resolver mit Normalisierung (3.3); `ClampResult`/`uncredited`/`clamp_applies`/`not_credited_minutes`/`presence_minutes`; `net_hours` Python + SQL; Netto-Helfer und `validate_daily_break` mit Pflichtparameter; alle 13 Schreibpfade inkl. Ankersperren (P5); E39–E42 und 7.3; UserForm ohne Fenster-Abschnitt und ohne `scheduled_*` im Payload, 400 für Altfelder; Guard-Tests; E2E-Fixtures | Altfenster wirken als Einzelblock unverändert (`uncredited` immer 0, weil Einzelblöcke keine Lücke haben); Auto-Close kappt jetzt (E42). Altfenster sind bis PR3 nicht editierbar. |
| **PR2 „Sichtbarkeit"** | `RawStampNote`, Journal-Summe, Export-Spalte, Anerkennen inkl. „Anrechnung beantragen", `PRESENCE_*`/`BREAK_IN_GAP`, 24-Wochen-Anwesenheit, StampWidget/Dashboard-Status, Profil-Endpunkt, Audit-Labels, Privacy-Text | wirkungslos, solange `uncredited` = 0; Hüllenminuten werden schon sichtbar |
| **PR3 „Aktivierung"** | Schreibschemas mit Blöcken, `derive_targets`, Dialog/Editor, Vorschau per `POST` (untypisiert), Neukappung, Schutzpaket, Löschen, Sammelzeile bei jeder Änderung, Dashboard-Hinweise, F1-Klemmung, Plan-Hinweise. **Voraussetzung:** Antworten auf 19.1 | Blöcke und Lückenkappung aktiv |
| **PR4 „Doku"** | fünf Doku-Flächen, `CLAUDE.md`, Screenshots, Release-Notes; pzweb als eigener PR | — |

Release-Regeln: 1.20.0 erst nach PR1–PR4. PR3 nie ohne PR2 auf `master` (Lückenkappung
ohne Sichtbarkeit und Anerkennen wäre nach A.1 „rot"). Zwischen PR1 und PR3 kein Release,
weil Altfenster dort nicht editierbar sind.

---

## Anhang A: Rechtsbewertung

Technische Prüfung mit rechtlichem Kontext, keine Rechtsberatung. Für Vergütung und
Rückwirkung sollte eine Fachanwältin für Arbeitsrecht mitlesen.

### A.1 Ampel je Teilfunktion

| Teilfunktion | vor den Entscheidungen | nach den Entscheidungen | Bedingung |
|---|---|---|---|
| Blöcke im datierten Snapshot, protokolliert | grün | grün | Migration/Backfill sauber (Abschnitt 5) |
| Tagessoll = Σ Blöcke | grün/gelb | grün | „Pause innerhalb der Blöcke" klärt netto/brutto |
| Rückwirkende Verlängerung mit Neukappung | gelb | gelb | Vorschau (Soll und Ist getrennt), Protokoll, MA-Hinweis. Nicht grün: im Block-Modell kann eine „Verlängerung" über das höhere Soll den Saldo senken (Umfangsänderung, die § 106 GewO nicht deckt) — offene Frage 19.1 Nr. 1 |
| Rückwirkende **Verkürzung** mit Neukappung | **rot** (automatisch) | gelb | nur mit Schutzpaket (9.5); abgeschlossene Jahre gesperrt |
| Vorschau / Protokoll / Jahresabschluss-Warnung | grün | grün | Muster `_log_wh_change_retarget` |
| Nichtanrechnung der Lücke | **rot** (still, ohne Freigabe) | gelb | Sichtbarkeit von Lücke **und** Hülle (P19; 13.1/13.2/15.1) + Anerkennen (13.3) + „Anrechnung beantragen" (P21) |

### A.2 Normen und Umsetzung

| Norm | Anforderung | Umsetzung |
|---|---|---|
| § 16 Abs. 2 ArbZG, EuGH C-55/18, BAG 1 ABR 22/21 | systematische Erfassung der gesamten tatsächlichen Arbeitszeit; Rohstempel ist der Nachweis | Rohstempel unangetastet (`raw_*` bzw. Stempel selbst), Anrechnung als abgeleitete Zahl `uncredited_minutes`, Protokoll je Eintrag mit `row_hash` |
| § 2 Abs. 1, § 3 ArbZG | Höchstarbeitszeit gegen tatsächliche Arbeitszeit (Tag und 48-h-Woche bzw. 24-Wochen-Durchschnitt); Neukappung darf Verstöße weder aus Warnungen noch aus Berichten verschwinden lassen | harte Prüfung auf angerechneter Zeit (E43) + `PRESENCE_DAILY_HOURS` und `PRESENCE_WEEKLY_HOURS` auf Rohstempel (E44, P22), 24-Wochen-Auswertung mit Anwesenheitswert, `arbzg_findings` in der Vorschau, Plan-Hinweis bei Tagessoll > 10 h (P9) |
| § 4 ArbZG | Ruhepause im Voraus feststehend, > 15 Min teilbar; durchgestempelte Lücke ist keine genommene Pause; kein Doppelabzug | Lückensegment ≥ 15 Min als Pausenabschnitt (8.2), `PRESENCE_BREAK` auf reiner Anwesenheit (P14), `BREAK_IN_GAP`, Auto-Pause-Rest (7.4), Plan-Hinweise über den ganzen Tag (P9) |
| § 5 ArbZG | Ruhezeit ab tatsächlichem Ende | unverändert auf Rohstempel |
| §§ 9/10 ArbZG | Blöcke gelten nicht an Sonn-/Feiertagen | `get_scheduled_blocks` → `[]` (E35, #484) |
| § 611a Abs. 2, § 612 Abs. 1 BGB; §§ 1, 3, 17 MiLoG; § 2 Abs. 2 MiLoG (Arbeitszeitkonto); § 4 Abs. 4 TVG | angeordnete, gebilligte, geduldete oder zur Erledigung notwendige Arbeit ist zu vergüten (BAG 5 AZR 359/21); Kappung beseitigt den Anspruch nicht; auf Mindestlohn (und tarifliche Ansprüche) kann nicht wirksam verzichtet werden | Handbuch-Kasten (E76), Anerkennen (E66), „Anrechnung beantragen" (P21), MiLoG-Warnungen (9.5, P26), Bestätigungstexte je Grundtyp mit MiLoG-Verzichtssatz |
| § 106 GewO | Lage der Arbeitszeit einseitig nur für die Zukunft, nach billigem Ermessen und mit angemessener Ankündigung; Vertrag kann sie festlegen; der **Umfang** ist nicht vom Direktionsrecht gedeckt | Standard „ab heute", rückwirkend nur mit Grund (E54); Zusatzwarnung bei „Sonstiges" (P26); Umfangsänderung: Hinweis 12.1/16.1, Schutzpaket-Frage 19.1 Nr. 1 |
| § 2 KSchG; §§ 8, 9, 12 Abs. 3 TzBfG | Umfangsänderung nur einvernehmlich oder per Änderungskündigung; Teilzeitregeln; Abrufarbeit mit 4 Tagen Ankündigung | Hinweis im Handbuch (16.1), Kurzfassung im Dialog (12.1) |
| § 2 Abs. 1 Satz 2 Nr. 7, § 3 NachwG | vereinbarte Arbeitszeit und Ruhepausen sind wesentliche Vertragsbedingungen; Änderung spätestens am Tag des Wirksamwerdens schriftlich mitteilen | Hinweis im Dialog und Handbuch (12.1, 16.1); PraxisZeit prüft das nicht (19 Nr. 7) |
| § 87 Abs. 1 Nr. 2, Nr. 3 und Nr. 6 BetrVG | Mitbestimmung bei Lage/Verteilung/Pausen, vorübergehender Änderung der betriebsüblichen Arbeitszeit und technischer Einrichtung (Kappung); ohne Zustimmung gegenüber den Beschäftigten unwirksam | fester Hinweis im Dialog (Kurzfassung) und Handbuch (volle Fassung), Wortlaut 12.1/16.1 |
| Art. 6 Abs. 1 lit. b und lit. c DSGVO | Rechtsgrundlage | lit. b: Durchführung des Arbeitsverhältnisses (Anrechnung); lit. c: Aufzeichnungspflicht (§ 16 Abs. 2 ArbZG, § 3 Abs. 2 Nr. 1 ArbSchG i. V. m. BAG 1 ABR 22/21, § 17 MiLoG); § 26 BDSG nach EuGH C-34/21 nur ergänzend. So auch im Verarbeitungsverzeichnis (16.1) |
| Art. 5 Abs. 1 lit. a, Art. 12 ff. DSGVO | Transparenz | Profilkarte, Verlauf, Dashboard-Hinweis bei **jeder** Änderung (P20, Abschnitt 14) |
| Art. 22, Art. 13 Abs. 2 lit. f DSGVO | Risiko gering bis mittel: die tägliche Kappung beim Ausstempeln läuft automatisch und wirkt auf das Überstundenkonto; Schutzmaßnahmen (Eingreifen einer Person, eigener Standpunkt, Anfechtung) und Erklärung der Logik | menschliche Prüfung bei Änderungen (Vorschau, Bestätigung), Sichtbarkeit (P19), Anerkennen (13.3), „Anrechnung beantragen" mit Begründung (P21), Logikbeschreibung auf der Datenschutzseite (14) |
| Art. 5 Abs. 2 DSGVO | Rechenschaft | Protokoll je Eintrag + Sammelzeile |
| Art. 5 Abs. 1 lit. e DSGVO; § 16 Abs. 2 ArbZG; § 17 Abs. 1 MiLoG; §§ 195, 199 BGB; § 28f SGB IV; § 147 AO | Speicherbegrenzung vs. Pflicht mindestens 2 Jahre, berechtigtes Interesse bis Verjährungsende (3 Jahre ab Jahresende), Lohnunterlagen ggf. länger | keine neue Löschfrist (15.4) |
| Art. 15/20 DSGVO | Auskunft/Übertragbarkeit inkl. Blöcke und Verlauf | 15.3, HH:MM-Strings |
| Art. 17 DSGVO | Anonymisierung der Freitexte | 15.4 (#440-Muster, `row_hash`-Neuberechnung) |
| § 4 Abs. 2, §§ 11, 12 JArbSchG | strengere Pausen (30 Min ab 4,5 h, 60 Min ab 6 h, max. 4,5 h ohne Pause), Schichtzeit inkl. Lücke ≤ 10 h | feste Infozeile im Dialog und im Handbuch (12.1, 16.1); Prüfung als Folgeticket (Abschnitt 18) |

### A.3 Pflichtenliste des Prüfers — Stand nach den Entscheidungen

| Nr | Pflicht | Erfüllt durch |
|---|---|---|
| 1 | Migration ohne automatische Neukappung; angerechnete Werte eingefroren | E22 |
| 2 | Kappung als eigene Größe | E11 |
| 3 | Blöcke als Soll-Quelle ohne Doppelpflege | E15, E10 |
| 4 | §3/§4 zusätzlich auf Anwesenheit, kein Doppelabzug, Lücke nie automatisch genommene Pause beim Durchstempeln; Verstöße verschwinden weder aus Warnungen noch aus Berichten | E43–E45, P14, P22 |
| 5 | Pufferregel an inneren Rändern | E5 |
| 6 | Verlängerung: Vorschau, Protokoll, MA-Hinweis, Jahreswarnung, symmetrisches Löschen | E53, E55, E57, E68 |
| 7 | Verkürzung: Schutzpaket, abgeschlossenes Jahr gesperrt | E54 |
| 8 | Nicht angerechnete Anwesenheit sichtbar (Lücke und Hülle), Freigabeweg, Antragsweg der Beschäftigten | E64–E66, E70, P18, P19, P21; Warnschwelle → Ticket |
| 9 | Ausnahmen (Sonn-/Feiertag, offen, `track_hours=false`, Beschäftigungsfenster) | E35, E49 |
| 10 | Transparenz für Mitarbeitende | E67–E69, P20 |
| 11 | Hinweis Mitbestimmung/Vergütung/Vertragsänderung/NachwG | E61, E76; Wortlaute 12.1, 16.1 |
| 12 | DSGVO-Kette | E72–E74 |
| 13 | Nebenläufigkeit / atomar | E52, P5 (Ankersperre in **allen** Schreibpfaden, Anker vor Zeile) |
| 14 | JArbSchG | Infozeile (12.1, 16.1); Prüfung als Folgeticket |
| 15 | Tests inkl. Grenzfälle, Idempotenz, PG-Round-Trip für Migration und Export | Abschnitt 17 |

---

## Anhang B: Touchpoint-Karte kompakt

Pfade relativ zu `backend/` bzw. `frontend/src/`.

**1 Datenmodell + Migration** — `alembic/versions/2026_10_08_1200-073_work_blocks.py` (neu;
Muster 067 `:96-120`); `app/models/user.py:44-55`; `app/models/working_hours_change.py:28-41`;
`app/models/time_entry.py:19-25, 36-57, 59-80`; `app/services/calculation_service.py:13-25, 28-102`;
`app/schemas/user.py` (UserBase 58-72, UserCreate 89-142, UserUpdate 145-207,
UserResponse 210-229, UserListResponse 232-284; Login `auth.py:302`, Impersonation
`impersonation.py:92`, `admin_users.py:438`); `app/schemas/validators.py:14-21, 48-58`;
`app/schemas/working_hours_change.py:8-25, 28-56, 59-75, 78-150`; `app/main.py:209-220`;
`services/signup_service.py:133-142`; `tests/conftest.py:128-270`;
`app/models/change_request.py:65-69` (P21/P28: `request_credit_override`,
`original_uncredited_minutes`); `app/models/time_entry.py` (`auto_closed`, P18).

**2 Kappung / Schreibpfade** — `services/work_window_service.py:15-21, 51-71, 74-78, 90-146,
149-166, 169-177, 180-216`; `routers/time_entries.py:46-57, 60-85, 88-119, 165-205, 211-238,
243-365, 370-560, 628-861, 867-1205`; `routers/admin_time_entries.py:68-205, 207-450`;
`routers/admin_change_requests.py:296-330, 346-425, 480-575, 969-974, 1005-1056, 1084-1092`;
`routers/change_requests.py:194-232, 270-283, 289-331` (plus `request_credit_override`, P21);
`routers/admin_change_requests.py:193-260` (Review-Body `grant_credit_override`, Ankersperre `:235`);
`routers/admin_helpers.py:79-107` (`lock_user_row` in allen Schreibpfaden, P5);
`services/xls_import_service.py:22-31, 46-55, 59-158, 182, 216-224, 236-251, 265-290, 303,
412-428, 455-506`; `routers/import_xls.py:29, 36-40, 100-120`; `schemas/time_entry.py:23-75,
84-109, 124-127`; `routers/absences.py:622-640, 667-679`.

**3 Netto / ArbZG / Anzeige** — `services/break_validation_service.py:13-111` (9 Aufrufer);
`_calculate_*`-Aufrufer (17, Liste 7.1); `is_night_work` (16 Stellen, unverändert);
`services/rest_time_service.py:66-81`; `routers/reports.py:957-1080`;
`calculation_service.py` Ist-Summen 775, 1014, 1338, 1471, 1567, 1785, 2082 (folgen dem
Hybrid, nicht umbauen); `services/journal_service.py:205, 308-318`;
`schemas/journal.py:6-17`.

**4 Verlauf / Rückwirkung / Protokoll** — `routers/admin_users.py:66-152`
(`_log_wh_change_retarget`), `155-177` (`_comparable_snapshot`), `180-261`
(`_normalise_schedule_input`, `_sync_user_from_change`), `1074-1114` (`create_user`),
`1170-1183` (Sperrliste), `1244-1253`, `1433-1665` (Anlegen), `1683-1733`
(`_schedule_input_error`), `1736-2016` (Vorschau), `2019-2165` (Löschen);
`calculation_service.py:139-238` (Segmente), `241-269` (`work_days_changed`), `272-349`
(`retarget_window`), `352-518` (`retarget_absence_hours`), `560-644` (unverändert),
`2475-2520` (Jahreswarnung); `routers/admin_helpers.py:79-107` (`lock_user_row`),
`141-175`; `core/audit_integrity.py:43-53`; `models/time_entry_audit_log.py:28-39`;
`routers/admin_time_entries.py:44-64` (Art.-9-Notizmaskierung).

**5 Frontend** — `types/user.ts:30-39`; `utils/workBlocks.ts` (neu);
`components/WorkBlocksEditor.tsx` (neu); `pages/admin/users/UserForm.tsx:14-50, 90-99,
142-151, 221-237, 255-276, 320-349, 444-491, 537-543, 857-977`; `pages/admin/Users.tsx:155-184,
391-398, 524, 671-676, 789-792, 853-858, 943-962`;
`pages/admin/users/WorkingHoursModal.tsx:16-69, 89-164, 173-181, 191-198, 310-345, 369-411,
464-538, 544-636, 677-688, 727-837, 846-962, 994-1004, 1049-1058`;
`components/RawStampNote.tsx:16-31`; `pages/TimeTracking.tsx:25-108, 311-322, 465-482, 680,
882-899, 947-1010`; `components/MonthlyJournal.tsx:21-30, 656-663, 795-856`;
`pages/admin/AdminDashboard.tsx:49-61, 786-796, 870-875, 1290-1295, 1473-1515, 1593-1625`;
`utils/formatters.ts:56-77, 119-140, 166-191`; `pages/Dashboard.tsx:125, 195-197, 362-377,
464-474`; `components/StampWidget.tsx:104-117`; `utils/breakValidation.ts:23-92`;
`utils/arbzgWarnings.ts:124-138, 196`; `pages/admin/ImportXls.tsx:11-19, 51-60, 328/345`;
`pages/admin/AuditLog.tsx:13-35, 80-89`; `components/AuditValues.tsx`;
`pages/admin/Settings.tsx:1320-1353`; `pages/Profile.tsx:369-373`; `pages/Privacy.tsx:84`
(plus Logikbeschreibung, P21); `pages/admin/Reports.tsx` (Spalte „Anwesenheit laut Stempel",
P22); Antragsprüfung im Admin-Frontend („genehmigen und anerkennen", P21);
`constants/helpContent.tsx:198-216`; `pages/admin/Reports.tsx:362`;
`pages/AbsenceCalendarPage.tsx:77-97` (unverändert bei Ansatz A).

**6 Lebenszyklus / Export / Anonymisierung** — `services/export_service.py:217-357, 474-480,
498, 594-619, 666, 736-740, 910-917, 1074-1085, 1186-1211, 1762, 1792-1800, 1845, 1881-1901,
1938`; `services/ods_export_service.py:196-201, 222-226, 287-299, 489-503, 583-599, 659-670`;
`schemas/reports.py:79-134`; `routers/reports.py:147-173, 294-318`;
`routers/auth.py:538-637`; `services/lifecycle_service.py:214-456, 509-610, 820-837`;
`routers/superadmin.py:55-130, 229`; `routers/admin_users.py:635-872, 876-1000`;
`services/backup_service.py:265-331`; Seed-Skripte `create_handbuch_testdata.py:13-16,
118-136, 181-189, 366`, `create_test_data.py:244, 275-281`, `setup_extended_testdata.py:391`
(`fix_utc_times.py` nach 073 nicht erneut ausführen).

**7 Tests / Doku** — Backend mit `scheduled_*` (7 Dateien, 67 Fundstellen):
`test_endpoints.py`, `test_work_window_integration.py`, `test_xls_import_service.py`,
`test_work_window_service.py`, `test_admin_entry_date_change_keeps_raw.py`,
`test_486_bulk_warnings.py`, `test_break_waiver.py`; 4er-Tupel/`unclamp`:
`test_release_1_19_1_review.py`, `test_fix2_update_keeps_raw.py`; weitere Suiten 17.6;
Frontend-Tests 17.7; E2E 17.8; Screenshots und Doku-Flächen 16.1.
