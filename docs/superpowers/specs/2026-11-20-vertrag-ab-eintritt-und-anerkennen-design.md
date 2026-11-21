# Vertrag ab Eintritt korrigieren · Anerkennen einfacher · Leiste „wen bearbeite ich“ · Hilfe-Icons

Stand: 2026-11-20 · Ziel: nächstes MINOR-Release (keine Migration) · Basis: `origin/master` 1.24.3

Entscheidungen von Manuel sind mit **(Manuel)** markiert. Entscheidungen des Designs, die er prüfen soll, mit **(Entwurf)**.

---

## 1. Anlass

**Kundenfall vom 20.11.2026.** Die Praxisleitung hat eine Mitarbeiterin mit erstem Arbeitstag 01.10.2026 angelegt. Vereinbart sind 2 Tage pro Woche (Mo + Di in Blöcken).

- Heute zeigt das Benutzerformular „Arbeitszeit heute: Mo … · Di …“. Das stimmt.
- Das Monatsjournal Oktober zeigt dagegen an **allen fünf Werktagen** ein Soll von 8 h. Die Mitarbeiterin hat deshalb Minusstunden.
- Zusätzlich hat sie an einzelnen Mittwochen und Donnerstagen als Aushilfe gearbeitet.

**Ursache (Bedienung, kein Rechenfehler):** Der Vertrag mit 2 Tagen wurde über „Arbeitszeit anpassen…“ mit dem vorgeschlagenen Wirkungsdatum **heute** gespeichert, nicht ab 01.10. Für Oktober gilt deshalb weiter der Stand vom Anlegen (Vorgabe 40 h / 5 Tage).

**Warum die Korrektur „nicht ging“ (vermutet):** Eine Änderung ab 01.10. mit den Blöcken Mo + Di macht Mittwoch und Donnerstag zu Werktagen ohne Block. Einträge an solchen Tagen zählen **0 h**, bis jemand sie anerkennt. Die Vorschau meldet das als rückwirkende Verkürzung. Speichern verlangt dann Grundtyp, Begründung und Bestätigungen. Danach müsste jeder Aushilfe-Eintrag einzeln im Journal anerkannt werden.

Abgegrenzt und als eigenes Issue erfasst: persönliche verkürzte Tage und Sonderurlaub je Person (#570) **(Manuel: „als Issue für danach“)**.

## 2. Ziele

1. **Hinweis im Dialog „Arbeitszeit anpassen“**, wenn das Wirkungsdatum nach dem ersten Arbeitstag liegt und seit dem Eintritt nie ein Vertrag gesetzt wurde. Ein Klick übernimmt den ersten Arbeitstag als Wirkungsdatum.
2. **Anerkennen im selben Schritt (Teil A, Manuel: „A dann B“):** Die Vorschau listet die Einträge, die durch die Änderung Zeit verlieren. Gewählte Einträge werden beim Speichern anerkannt. Anerkannte Einträge verlieren nichts. Sind alle Verluste anerkannt, gibt es keine Verkürzung und kein Schutzpaket. Bleiben Randschnitte an schon bestehenden Blöcken, gilt für sie das Schutzpaket wie heute.
3. **Sammel-Anerkennen im Monatsjournal (Teil B):** Häkchen je Zeile und ein Knopf „Ausgewählte anerkennen (n)“. Ein Aufruf, eine Transaktion.
4. **Leiste oben immer sichtbar (Manuel):** Beim Bearbeiten einer Person steht ihr Name in einer festen Leiste, die beim Scrollen stehen bleibt.
5. **Handbuch:** Eine neue Aufgabe beschreibt den Fall von Anfang bis Ende. Die Aufgabe zum Anerkennen nennt das Sammel-Anerkennen.
6. **„?“-Icons (Manuel):** An Feldern und Abschnitten, zu denen es einen Handbuch-Eintrag gibt, steht ein kleines „?“. Ein Klick zeigt einen Kurzhinweis und den Link „Mehr im Handbuch“.

## 3. Nicht-Ziele

- Keine Änderung der Rechenregeln. Werktag ohne Block bleibt 0 h, bis jemand anerkennt.
- Anerkennen bleibt **unumkehrbar** (Handbuch `nicht-angerechnet-anerkennen`). Es gibt keine Rücknahme, auch nicht beim Löschen der Arbeitszeit-Änderung.
- Kein automatisches Anerkennen ohne sichtbare Auswahl der Admin.
- Keine persönlichen Sondertage (#570).
- Keine neue Migration.

## 4. Anti-Ziele (Fehlschlag, auch wenn es technisch läuft)

- **Vorschau und Speichern rechnen verschieden.** Die Vorschau muss das Anerkennen genauso einrechnen wie das Speichern (ein Rechenpfad `run_change`, Spec 9.3).
- **Anerkennen umgeht die Sperrordnung.** Die Ankersperre der Person kommt zuerst, dann die Zeilensperren der Einträge in fester Reihenfolge (P5).
- **Eine teilweise angewandte Sammelaktion.** Scheitert ein Eintrag (Kollision, offen, automatisch geschlossen), wird nichts geschrieben.
- **Eine stille Verkürzung.** Wählt die Admin Einträge ab, gilt für den Rest das Schutzpaket wie heute.
- **Ein „?“-Icon, das ins Leere zeigt.** Jeder Anker wird im Test geprüft.

---

## 5. Teil 1 — Hinweis „ab erstem Arbeitstag“

**Wo:** `frontend/src/pages/admin/users/WorkingHoursModal.tsx`, unter dem Datumsfeld.

**Daten:** Neues Prop `firstWorkDay?: string | null`. Es wird in `Users.tsx` aus `editUser.first_work_day` durchgereicht, ebenso von der Teamübersicht (`TeamSchedule.tsx`), falls sie den Dialog öffnet. Den Verlauf lädt der Dialog schon selbst (`GET …/working-hours-changes`).

**Bedingung (Entwurf).** Der Hinweis deckt zwei Zustände ab: den Fehler **vor** dem Speichern und den schon gespeicherten Fehler. Der zweite ist der Kundenfall.

Hintergrund: Das erste Speichern mit falschem Datum schreibt automatisch eine Basiszeile (`_frozen_row`, Notiz `BASELINE_ROW_NOTE`) am ersten Arbeitstag. Der Verlauf hat dann zwei Zeilen: 01.10. (Basis, Vertrag vom Anlegen) und 20.11. (Mo + Di).

Der Hinweis erscheint, wenn alle folgenden Punkte gelten:
- `firstWorkDay` ist gesetzt.
- Der heute gültige Vertrag weicht vom Vertrag am ersten Arbeitstag ab. Grundlage ist `scheduleAt` aus dem geladenen Verlauf, Vergleich über `comparableSnapshot`.
- Zwischen dem ersten Arbeitstag und heute liegt **keine** echte Änderung außer der jüngsten. Eine automatisch geschriebene Basiszeile zählt nicht als echte Änderung.

Für die Erkennung der Basiszeile braucht das Frontend ein Kennzeichen. Die Verlaufsantwort (`WorkingHoursChangeResponse`) bekommt `is_baseline: bool`. Der Server setzt es, wenn die Notiz `BASELINE_ROW_NOTE` ist. Das Frontend vergleicht keine Texte.

**Text (Entwurf):**
> Vom 01.10.2026 (erster Arbeitstag) bis zum 19.11.2026 gilt noch der Vertrag vom Anlegen (5 Tage, 40 h). Soll die heutige Arbeitszeit schon ab dem ersten Arbeitstag gelten?
> [Ab 01.10.2026 übernehmen]

Der Knopf setzt das Wirkungsdatum auf den ersten Arbeitstag und füllt das Formular mit dem heute gültigen Vertrag. Danach läuft die Vorschau neu.

Liegt dort die früheste Zeile, ersetzt das Speichern sie wie heute (`_correction_target` erlaubt das für die früheste Zeile). Die spätere Zeile mit gleichem Vertrag bleibt stehen. Sie ändert keine Rechnung, und der Verlauf bleibt nachvollziehbar **(Entwurf)**.

Vor dem ersten Speichern gilt dieselbe Regel sinngemäß. Der Hinweis erscheint dann, wenn das gewählte Wirkungsdatum nach dem ersten Arbeitstag liegt und es noch keine echte Änderung gibt.

**Server:** nur das Feld `is_baseline` in der Verlaufsantwort. Sonst keine Änderung.

## 6. Teil 2A — Anerkennen im Dialog „Arbeitszeit anpassen“

### 6.1 Backend

**Eingabe:** Der Body von Anlegen und Vorschau (`_parse_change_body`, `WorkingHoursChangeCreate`) bekommt das optionale Feld `recognize_entry_ids: list[UUID]` (Vorgabe leer). Es ist Teil des Vorschau-Schlüssels.

**Rechenpfad:** `wh_change_service.run_change(..., recognize_entry_ids=...)`. Das Anerkennen läuft **nach der Neukappung und vor `retarget_absence_hours`**. So sieht die F1-Rückrechnung die angerechnete Zeit nach dem Anerkennen, und die Klassifikation vergleicht den Endzustand.

1. Die Ankersperre hält der Router schon (`_lock_and_reload`). Die Vorschau nimmt bewusst keine Ankersperre (Spec 9.3) und rollt am Ende zurück. Für Einträge gilt das genauso: In der Vorschau keine Zeilensperre, beim Speichern `load_entry_locked` je ID, aufsteigend nach `id` sortiert.
2. Jede ID muss zur Person und zum Mandanten gehören (F-026). Fremde oder unbekannte IDs ergeben 404 `ENTRY_NOT_FOUND`, geprüft **vor** jeder Zeilensperre.
3. Nur Einträge im Wirkungsbereich der Änderung, die geschlossen und nicht `auto_closed` sind. Sonst 400 mit Datum und Grund. Der Text kommt aus `credit_override_service`, er wird nicht neu formuliert.
4. Je Eintrag `credit_override_service.apply_credit_override(db, entry, changed_by_id=admin.id, on_request=False)`. Bereits anerkannte Einträge sind idempotent (`False`). Kollisionen ergeben 409 wie heute.
5. Danach Abwesenheits-Rückrechnung und Klassifikation wie heute. Ein anerkannter Eintrag hat `new_net ≥ old_net` und ist damit kein Verlust.

**Doppelte F1-Rechnung vermeiden:** `apply_credit_override` ruft `reapply_f1_for_day`. Gleich danach folgt `retarget_absence_hours` über das ganze Fenster. Der Builder prüft, ob die doppelte Rechnung am Misch-Tag dasselbe Ergebnis und dieselben Protokollzeilen liefert. Ist das nicht der Fall, bekommt `apply_credit_override` einen Schalter `reapply_f1=False` für diesen Pfad.

**Vorschau-Antwort:** `time_entry_changes` bekommt je Eintrag drei neue Felder:
- `recognizable: bool`: geschlossen, nicht `auto_closed`, nicht schon anerkannt.
- `recognized: bool`: in diesem Lauf anerkannt.
- `blockless_workday: bool`: Werktag ohne Block, der Eintrag fällt auf 0 h. Die Quelle ist `work_window_service.credit_blocks(...) == []`, nicht `new_net == 0`.

Damit die Liste die Kandidaten kennt, auch wenn sie schon gewählt sind, rechnet die Vorschau die Kandidaten **ohne** Anerkennen (so wie heute). Das Ergebnis mit Anerkennen liefert sie getrennt in `impact` (Saldo, `is_shortening`, Gründe) **(Entwurf)**. Alternative für den Builder: zwei Läufe in einer zurückgerollten Transaktion. Entscheidend ist, dass die Liste stabil bleibt, während Häkchen gesetzt werden.

**Protokoll (Entwurf, Variante b):** Ein anerkannter Eintrag erscheint **nicht** als Verlust der Neukappung.
- Er bekommt keine `wh_reclamp`-Zeile. Er bekommt nur die bestehende `credit_override`-Zeile mit dem Wert vor der Änderung als altem Wert und der ganzen gestempelten Zeit als neuem Wert.
- Die Sammelzeile `wh_reclamp` (Format eingefroren, `summary_note`) zählt und summiert **nach** dem Anerkennen. Anerkannte Einträge zählen nicht in „neu berechnet“ und nicht ins Δ.
- `adjusted_time_entries` zählt sie ebenfalls nicht.
- `run_change` bildet die Liste `changed` deshalb nach dem Anerkennen neu bzw. filtert anerkannte IDs heraus.

Grund: Der 30-Tage-Hinweis auf dem Dashboard der Mitarbeitenden liest die Sammelzeile (`parse_summary_note`). Er darf keinen Verlust melden, der nie gewirkt hat. Das Protokoll bleibt vollständig: Wert vorher, Wert nachher, wer, wann, Quelle `credit_override`.
- Die Notiz der Arbeitszeit-Änderung (`compose_change_note`) bekommt **keinen** Zusatz, damit die 500-Zeichen-Grenze nicht gefährdet ist. Die Zuordnung ergibt sich aus Zeit und Admin im Protokoll **(Entwurf)**.

**Löschen einer Änderung:** Anerkannte Einträge bleiben anerkannt (Nicht-Ziel „keine Rücknahme“). Die Löschvorschau nennt sie als „bleibt anerkannt“. Das zeigt sie heute schon über `skipped_time_entries` mit Grund `credit_override`.

### 6.2 Frontend

`WhImpactBox.tsx` / `WorkingHoursModal.tsx`:
- Neuer Abschnitt **„Einträge, die Zeit verlieren“** über der heutigen Einzelheiten-Liste. Je Zeile ein Häkchen, Datum, Wochentag, „gestempelt 07:50–12:05 · bisher 4:15 h → neu 0:00 h“ und ein Kennzeichen „Tag ohne Block“.
- **Vorauswahl (Entwurf):** Vorausgewählt sind Einträge an Werktagen, die nach der Änderung keinen Block haben (`blockless_workday`, Aushilfe-Fall). Ebenso Einträge, deren Tag **vor** der Änderung gar nicht gekappt wurde: Die Kappung ist dort neu, kein gewollter Randschnitt. Dafür liefert die Vorschau zusätzlich `newly_clamped: bool`, wenn `credit_blocks` vorher `None` war. Einträge, die nur am Rand eines schon bestehenden Blocks stärker gekappt werden, sind nicht vorausgewählt. Bleiben solche Verluste, erscheint das Schutzpaket für den Rest. Das ist gewollt: Es ist eine echte Verkürzung.
- Darüber steht der Link „Alle auswählen / keine“.
- Nicht anerkennbare Einträge (offen, automatisch geschlossen) haben ein deaktiviertes Häkchen und den Hinweis aus `utils/creditOverride.ts`.
- Hinweis unter der Liste: „Anerkannte Einträge zählen mit der ganzen gestempelten Zeit, auch bei späteren Änderungen. Anerkennen lässt sich nicht zurücknehmen.“
- Jede Änderung eines Häkchens löst die Vorschau neu aus, wie heute jede Feldänderung (`scheduleBody` → Vorschau-Schlüssel).
- Sind alle Verluste anerkannt, verschwindet die Verkürzungswahl (`ShorteningChoice`). Bleiben Verluste übrig, erscheint sie wie heute, nur für den Rest.
- Speichern-Knopf: „Speichern und 3 Einträge anerkennen“, wenn mindestens ein Eintrag gewählt ist.

## 7. Teil 2B — Sammel-Anerkennen im Monatsjournal

**Backend:** neuer Endpunkt `POST /api/admin/users/{user_id}/time-entries/credit-override` mit dem Body `{"entry_ids": [UUID, …]}` (1–200 IDs).
- `require_admin`, F-026, Person über `_get_user_in_tenant`.
- Alle IDs gehören der Person. Sonst 404 vor jeder Sperre, mit derselben Regel wie beim Einzelaufruf.
- `lock_user_row` zuerst, dann die Einträge mit `load_entry_locked` aufsteigend nach `id`.
- Je Eintrag `apply_credit_override`. Ein Fehler rollt alles zurück. Die Antwort nennt den Eintrag mit Datum, z. B. „07.10.2026: …“.
- Antwort: `{"recognized": n, "already": m, "warnings": [...]}` mit `override_warnings` je Eintrag, dedupliziert.
- Der Einzel-Endpunkt bleibt unverändert. Beide teilen sich einen Helfer, damit die Prüfreihenfolge nicht auseinanderläuft.

**Frontend (`MonthlyJournal.tsx`, nur `isAdminView`):**
- Neue Spalte mit Häkchen, nur an Einträgen, an denen `CreditOverrideButton` erscheint. Dieselbe Bedingung steht in `utils/creditOverride.ts` als Funktion `isRecognizable(entry)`, die der Knopf ebenfalls nutzt.
- Kopfzeile: „Alle nicht angerechneten auswählen“.
- Leiste mit „Ausgewählte anerkennen (n)“. Sie erscheint bei mindestens einer Auswahl.
- Bestätigungsdialog nennt Zahl, Summe der zusätzlich angerechneten Zeit und den Satz „lässt sich nicht zurücknehmen“.
- Danach lädt das Journal neu, und Warnungen erscheinen über `showArbzgWarnings`.
- Die Detailtabelle im Admin-Dashboard (`EmployeeTimeEntryTable.tsx`) bekommt **kein** Sammel-Anerkennen **(Entwurf)**. Das Journal ist der Ort für Monatsarbeit.

## 8. Teil 3 — Leiste „wen bearbeite ich“

**Benutzerformular (`UserForm.tsx`, inline in `Users.tsx`):**
- Der Kopf der Karte wird zu einer festen Leiste (`sticky top-0 z-20`, weißer Hintergrund, untere Linie).
- Inhalt: „Bearbeiten: Vorname Nachname (benutzername)“ bzw. „Neue:n Benutzer:in anlegen“, rechts die Knöpfe **Speichern** und **Abbrechen**. Die Knöpfe sind dieselben Aktionen wie unten (`form="user-form"`, `type="submit"`).
- Auf dem Handy bleibt der Name in einer Zeile mit Abschneiden (`truncate`). Die Knöpfe werden zu Symbolen mit `aria-label`.
- Der untere Speichern-Knopf bleibt.

**Monatsjournal der Admin (`pages/admin/UserJournal.tsx`):** Der Titel „Monatsjournal: Name“ und die Monatsnavigation werden eine feste Leiste. So bleiben Name und Monat beim Scrollen durch lange Monate sichtbar.

**Dialog „Arbeitszeit anpassen“:** ist schon fest (`WorkingHoursModal.tsx` `sticky top-0`) und zeigt den Namen. Keine Änderung.

**Achtung Layout:** Der Builder prüft, ob ein Elternelement `overflow` setzt. Dann greift `sticky` nicht. Er prüft auch den Abstand zur oberen Leiste auf dem Handy (`Layout.tsx`).

## 9. Teil 4 — Handbuch

Quelle ist `frontend/src/handbuch/content/praxisleitung.ts`. `docs/handbuch/HANDBUCH-ADMIN.md` und `frontend/public/help/HANDBUCH-ADMIN.md` werden daraus erzeugt (`check-doc-sync.sh handbuch_md`).

- **Neue Aufgabe** `vertrag-ab-eintritt` im Kapitel um `vertragsverlauf` / `rueckwirkend-aendern`: „Die Arbeitszeit gilt erst ab heute – wie korrigiere ich sie ab dem ersten Arbeitstag?“ Schritte:
  1. Symptom: Im Journal stimmt das Soll vor dem Änderungsdatum nicht.
  2. Dialog öffnen. Der Hinweis erscheint auch, wenn die Änderung schon gespeichert ist. „Ab … übernehmen“ klicken.
  3. Vorschau lesen, Aushilfe-Einträge anerkennen.
  4. Speichern.
  5. Ergebnis im Journal prüfen.
  Dazu ein Rechenbeispiel ohne Kundennamen: 2 Tage à 8 h, zwei Aushilfe-Tage à 4 h.
- **Aufgabe `nicht-angerechnet-anerkennen`** ergänzen: Sammel-Anerkennen im Journal und Anerkennen im Dialog.
- **Aufgabe `auswirkung-pruefen`** ergänzen: der neue Abschnitt „Einträge, die Zeit verlieren“.
- Screenshot-Platzhalter (`shot`) nur, wenn die Screenshot-Pipeline (`shotOrder`) das trägt. Sonst bleibt es bei Text **(Entwurf)**.
- **Doku-Sync, 5 Flächen:**
  - `praxisleitung.ts`, daraus erzeugt `HANDBUCH-ADMIN.md` und der Spiegel.
  - `docs/BERECHNUNGEN.md`, nur falls nötig. Die Rechenregel ändert sich nicht.
  - `CHEATSHEET-ADMIN.md` mit einer Zeile.
  - pzweb `anleitung` als eigener PR im pzweb-Repo.
  - `SchnellstartAdmin`, falls dort Anerkennen vorkommt.
  - Dazu `check-doc-sync.sh` um eine Gruppe für die neuen Wortlaute ergänzen.

## 10. Teil 5 — „?“-Icons mit Kurzhinweis

**Komponente:** `frontend/src/components/HandbookHint.tsx`
- Props: `hintId`.
- Knopf mit `HelpCircle` (lucide, 16 px, grau, `aria-label="Hilfe: <Titel>"`).
- Klick öffnet ein kleines Popover: Titel, 1–3 Sätze, Link „Mehr im Handbuch →“ auf `/help/<book>#<anchor>`.
- Schließt mit Esc, mit Klick daneben und beim Fokusverlust. Per Tastatur erreichbar.
- Auf dem Handy erscheint es als Bottom-Sheet, wenn das Popover nicht passt.

**Register:** `frontend/src/constants/handbookHints.ts` mit `Record<HintId, {book, anchor, title, text}>`. Texte stehen nur hier, nie inline an der Einsatzstelle.

**Tests:**
- Jeder Anker existiert. Dafür wird der Prüfer aus `helpContent.test.ts` wiederverwendet.
- Jeder Registereintrag wird mindestens einmal verwendet. Das prüft eine Quelltextsuche nach `hintId="…"`.
- Keine verbotenen Begriffe (`handbuch/content/forbiddenTerms.ts`).
- Darstellung, Esc und Link per RTL.

**Einsatzstellen (Entwurf, Startliste ~30).** Der Builder gleicht die Liste mit den Kapitel- und Aufgaben-IDs in `praxisleitung.ts` und `mitarbeitende.ts` ab. Er setzt ein Icon nur dort, wo ein Abschnitt genau zu der Stelle passt.

- **Admin – Benutzerformular:**
  - Stundenzählung
  - ArbZG-Ausnahme §18
  - Nachtarbeit
  - Betriebsferien-Teilnahme
  - Erster/letzter Arbeitstag
  - Anfangssaldo
  - Urlaubsanspruch
  - Kind-krank-Tage
  - Minijob-Felder
  - „Nach Arbeitsblöcken“
- **Admin – Dialog „Arbeitszeit anpassen“:**
  - Wirkungsdatum (`rueckwirkend-aendern`)
  - Blöcke (`bloecke-hinterlegen`)
  - Vorschau (`auswirkung-pruefen`)
  - Verkürzungswahl
  - Verlauf (`vertragsverlauf`)
  - Neuer Abschnitt Anerkennen
- **Admin – Monatsjournal:**
  - Spalte Anerkennen (`nicht-angerechnet-anerkennen`)
  - Soll/Ist/Saldo (`so-rechnet`-Kapitel)
- **Admin – Einstellungen:**
  - Sondertage 24./31.12.
  - Verkürzte Tage
  - Bundesland
  - Puffer
  - Pausen-Ausnahme
  - Urlaubsantrag-Genehmigung
  - Schichtplanung
  - Betriebsferien
- **Admin – Berichte und Jahresabschluss:** Soll-Basis „bis heute / Monatsende“, Jahresabschluss
- **Admin – Abwesenheiten:** eigene Gründe, Vorlagen Kind krank
- **Mitarbeitende:**
  - Stempelkarte
  - Monatssaldo
  - Überstundenkonto
  - Urlaubskonto
  - „nicht angerechnet“-Zeile
  - Änderungsantrag

**Abgrenzung:** Das bestehende „?“ je Seite (`HelpPanel`) bleibt. Die Icons sind feiner und ersetzen es nicht.

## 11. Ansätze (betrachtet)

**Anerkennen einfacher:**
- **A – im Dialog „Arbeitszeit anpassen“.** Löst den Korrekturfall in einem Schritt und vermeidet das Schutzpaket. Kostet Eingriff in `run_change` und Vorschau.
- **B – Sammel-Anerkennen im Journal.** Deckt den Alltag ab (Aushilfe ohne Vertragsänderung). Kleiner, eigener Endpunkt.
- **Entscheidung (Manuel): A, dann B.** Beides wird gebaut, in dieser Reihenfolge.

**Soll für einen vergangenen Zeitraum ändern (vor dem Befund):**
- A – persönliche Sondertage
- B – Abwesenheit „bezahlt frei“ mit Sammelbuchung
- C – Arbeitszeit-Änderung mit Enddatum

Der Befund zeigte einen Bedienfehler (falsches Wirkungsdatum). Deshalb sind hier die Verbesserungen gewählt. Persönliche Sondertage folgen als #570 **(Manuel)**.

## 12. Tests (Mindestumfang)

**Backend:**
- `run_change` mit `recognize_entry_ids`, Kundenfall nachgestellt:
  - Person mit erstem Arbeitstag 01.10., Basis 5 × 8 h.
  - Änderung ab 01.10. auf Mo + Di.
  - Aushilfe-Einträge Mi/Do.
  - Ohne Auswahl: Verkürzung `entries`.
  - Mit Auswahl: keine Verkürzung, Einträge `credit_override=True`, Saldo Oktober = Ist − 2-Tage-Soll.
  - Vorschau und Speichern liefern dieselben Zahlen.
- Fremde ID → 404 ohne Sperre (Muster `test_write_path_locks.py`). `auto_closed` → 400. Kollision → 409, nichts geschrieben.
- Sammel-Endpunkt: alles oder nichts, Sperrreihenfolge, idempotent, F-026.
- Misch-Tag (Abwesenheit + Eintrag): F1-Ergebnis und Protokollzeilen wie beim Einzel-Anerkennen.
- PG-Test (`_pg`), weil Sperren und rohe Pfade betroffen sind: Sammel-Anerkennen unter echten Zeilensperren.

**Frontend (vitest):**
- Hinweis-Bedingung (Teil 1) mit allen drei Bedingungen.
- Vorauswahl.
- Neue Vorschau bei Häkchen.
- `ShorteningChoice` verschwindet bei vollständiger Anerkennung.
- Journal-Auswahl und Bestätigung.
- `HandbookHint`.
- Feste Leiste rendert den Namen.

**E2E:** eine Spec für den Kundenfall (anlegen → Änderung mit falschem Datum **speichern** → Dialog neu öffnen → Hinweis → übernehmen → anerkennen → Journal-Soll und Saldo) und eine für das Sammel-Anerkennen im Journal.

## 13. Dem Builder überlassen

- Exakte Platzierung der Icons innerhalb der Startliste und die Kurztexte. Sie sind fachlich aus dem jeweiligen Handbuchabschnitt abgeleitet und von Manuel gegenzulesen.
- Ob die Vorschau zwei Läufe braucht oder die Kandidaten aus einem Lauf ableitet (6.1).
- Ob `apply_credit_override` den Schalter `reapply_f1` braucht (6.1).
- Reihenfolge der PRs. Vorschlag:
  - PR 1: Teil 1 + 2A + 3
  - PR 2: Teil 2B
  - PR 3: Teil 5
  - Handbuch je PR mitziehen.
