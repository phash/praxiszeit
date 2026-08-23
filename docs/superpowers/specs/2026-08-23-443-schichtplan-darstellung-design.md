# Design: Schichtplan-Darstellung, Freigabe und Druck (#443)

**Datum:** 2026-08-23
**Issue:** [#443](https://github.com/phash/praxiszeit/issues/443) — „Schichtplan-Darstellung, ggf. druckbare Version"
**Mit erledigt:** [#450](https://github.com/phash/praxiszeit/issues/450) (dieselbe Datei, dieselbe Runde)
**Feature-Bereich:** Schichtplanung (#305), Feature-Flag `shift_planning_enabled`, Default aus
**Release-Ziel:** MINOR (neue Migration, neues Feld, neuer Endpunkt)

---

## 1 Ausgangslage

Die Schichtplanung ist seit #305 ein bewusst von der ArbZG-/Soll-Ist-Berechnung
entkoppeltes Planungsartefakt. Drei Beobachtungen aus dem Betrieb:

1. **Ein künftiger Plan lässt sich nicht ankündigen.** `list_plans` und
   `get_plan` zeigen Nicht-Admins ausschließlich Pläne, die *heute* aktiv sind
   (`is_active` oder Datumsfenster deckt heute ab); ein Entwurf antwortet für
   sie mit 404. Der reale Anlass: im September beginnt eine Auszubildende, der
   neue Plan soll den Mitarbeitenden jetzt bekannt gemacht werden.
2. **Es gibt keinen Ausdruck.** Die Chefin fordert einen Aushang; angeboten
   wird bisher nur die Bildschirmansicht.
3. **Das Wochenraster kürzt Namen ab.** Parallele Slots werden horizontal in
   Spuren gepackt; jede Spur wird schmal, `truncate` schneidet Arbeitsplatz-
   und Personennamen ab — während vertikal Platz frei bleibt.

Ergänzend aus dem Issue-Kommentar (philvdb): ein **Kommentarfeld** je
Arbeitsplatzeinteilung, um Erläuterungen wie „Einarbeitung Azubi" zu hinterlegen.

## 2 Zielbild

- Ein Admin kann einen Plan gezielt **für Mitarbeitende freigeben**, unabhängig
  davon, ob er heute schon gilt.
- Ein Plan lässt sich als **PDF im Querformat** ausgeben (Aushang).
- Das Wochenraster **bricht um** statt abzuschneiden.
- Je Slot ist ein **Hinweistext** hinterlegbar, der am Bildschirm und im PDF
  erscheint.

**Nicht im Umfang:** Print-CSS als zweite Druckfläche, Kommentare je einzelner
Person, ein Veröffentlichungsdatum („sichtbar ab"), Änderungen am
Berechnungsmodell.

## 3 Entscheidungen und ihre Begründung

| Frage | Entscheidung | Grund |
|---|---|---|
| Wie wird ein künftiger Plan sichtbar? | Explizites Feld `visible_to_employees` (Default `false`) | Ein Ableiten aus dem Datumsfenster würde jeden Planungsentwurf, der ein Fenster trägt, ungewollt veröffentlichen. Der Default hält das Bestandsverhalten byte-identisch. |
| Wie entsteht der Ausdruck? | Server-PDF über reportlab | Deterministisch und auf jedem Rechner gleich; reportlab und `landscape(A4)` sind über `generate_monthly_report_pdf` bereits im Haus. Print-CSS wäre browserabhängig (Hintergrundfarben standardmäßig aus) und im absolut positionierten Zeitraster beim Seitenumbruch unzuverlässig. |
| Woran hängt der Kommentar? | `ShiftSlot.note` | Deckt die genannten Fälle ab. Ein Feld je Zuweisung würde den Vertrag von `PUT /slots/{id}/assignments` von einer ID-Liste auf Objekte umstellen — ein Bruch ohne belegten Bedarf. |
| Wie wird das Raster lesbar? | Umbruch, Blockhöhe wächst bei Bedarf | Genau der Vorschlag des Issues. Ein gröberes Zeitraster allein löst den Fall „30-Minuten-Slot, drei Personen" nicht; eine zusätzliche Listenansicht wäre eine dritte Darstellungsfläche mit dauerhafter Pflege. |
| Darf ein Mitarbeitender das PDF ziehen? | Ja, hinter demselben Sichtbarkeits-Gate | Er druckt damit nur, was er ohnehin am Bildschirm liest. Die Einweisungs-Flags bleiben admin-only und stehen nicht im PDF. |

## 4 Datenmodell

Migration `070_shift_plan_visibility_note` (Head ist derzeit `069_weekly_hours_precision`):

| Tabelle | Spalte | Typ | Bemerkung |
|---|---|---|---|
| `shift_plans` | `visible_to_employees` | `BOOLEAN NOT NULL DEFAULT false` | `server_default="false"` |
| `shift_slots` | `note` | `TEXT NULL` | Hinweistext je Einteilung |

Beide Tabellen sind bereits tenant-scoped mit RLS-Policy (Migration 053) —
reine Spalten-Ergänzungen, keine Policy-Änderung. Downgrade lässt beide Spalten
fallen.

## 5 Backend

### 5.1 Sichtbarkeit — ein Helfer statt zweier Kopien

`list_plans` (`shift_planning.py`, Filterzeile im Schleifenkopf) und `get_plan`
(404-Gate) prüfen die Regel heute **je eigenständig** über
`is_plan_active_on(...)`. Zwei Kopien derselben fachlichen Regel sind im Projekt
mehrfach auseinandergelaufen (CR-Genehmigung CREATE/UPDATE, Feiertags-Guard).
Deshalb eine gemeinsame Quelle in `app/services/shift_planning_service.py`:

```python
def is_plan_visible_to(plan: ShiftPlan, d: date, is_admin: bool) -> bool:
    """Darf dieser Nutzer den Plan sehen?

    Admins sehen alles. Für alle anderen gilt: der Plan ist heute aktiv ODER
    er wurde ausdrücklich für Mitarbeitende freigegeben (#443).
    """
    return is_admin or is_plan_active_on(plan, d) or bool(plan.visible_to_employees)
```

Beide Aufrufstellen rufen ausschließlich diesen Helfer. Da `visible_to_employees`
per Default `false` ist, bleibt das Verhalten bestehender Installationen
unverändert.

### 5.2 Schemata und Serialisierung

- `PlanIn.visible_to_employees: bool = False` → wirkt in `create_plan` und
  `update_plan`.
- `_plan_summary` und `_build_plan_detail` geben das Feld aus (die Admin-UI
  braucht den Schaltzustand).
- `SlotIn.note: Optional[str] = Field(None, max_length=500)`; `_slot_dict` gibt
  `note` zurück.
- **`duplicate_plan` kopiert die Freigabe NICHT** (eine Kopie ist ein Entwurf),
  **kopiert den Slot-Hinweis aber schon**.

### 5.3 PDF-Export

Neues Modul `app/services/shift_plan_export_service.py`. Bewusst **nicht** in
`export_service.py`: das ist die §16-/Berechnungs-gekoppelte Exportfläche, die
Schichtplanung ist davon laut #305 entkoppelt. Ein eigenes Modul hält die
Trennung sichtbar.

```
GET /api/shift-planning/plans/{plan_id}/export.pdf
```

- Die Renderfunktion nimmt **das Dict von `_build_plan_detail`** entgegen und
  stellt keine eigenen Abfragen. Damit erbt das PDF den `#371`-Wochentagsfilter
  und die Unterbesetzungs-Markierung automatisch; ein zweiter Abfragepfad wäre
  die nächste Divergenz (vgl. die Export-Parallelpfade im Berechnungsmodell).
- Layout: Querformat A4. Kopf mit Plan-Name, Beschreibung, Gültigkeitsfenster
  und „Stand: TT.MM.JJJJ". Tabelle Arbeitsplatz (Zeilen, sortiert nach Standort,
  `sort_order`, Name) × Wochentag (Spalten, nur freigeschaltete Wochentage).
  Zelle je Slot: Zeitfenster, Namen, darunter `↳ Hinweis`. Mehrere Slots
  desselben Arbeitsplatzes am selben Tag stapeln in einer Zelle.
  `Table(repeatRows=1)` für den Seitenumbruch.
- **Jeder Nutzertext läuft durch `escape_pdf_text`** (Name, Hinweis,
  Beschreibung) — reportlab parst eine intra-Paragraph-Markup-Sprache.
- Zugriff: `is_plan_visible_to(...)`, **nicht** `require_admin`. Die
  Einweisungs-Flags (`qualified` / `unqualified`) stehen nicht im PDF.
- Die Router-Dependency `require_shift_planning_enabled` greift automatisch →
  404 bei ausgeschaltetem Feature.
- Dateiname `Schichtplan_<Plan>_<Datum>.pdf`, Sonderzeichen bereinigt,
  `Content-Disposition: attachment`.

### 5.4 Mit erledigt: #450

Dieselbe Datei, deshalb in derselben Runde:

1. `set_user_qualifications` ersetzt `db.commit()` durch
   `_commit_or_conflict(db, "Die Einweisungen wurden zwischenzeitlich geändert, bitte erneut versuchen")`
   → 409 statt 500 beim Bedienkonflikt.
2. `LocationIn`, `WorkstationIn`, `PlanIn`, `PlanDuplicateIn`:
   `name: str = Field(..., min_length=1, max_length=255)` → 422 statt
   `StringDataRightTruncation`/500 auf PostgreSQL.

### 5.5 DSGVO

`shift_slots.note` ist eine neue Freitextfläche. #440 führt „Namen in der
Schichtplanung" bereits als offenen Restposten. Das Feld wird deshalb sofort in
`lifecycle_service.anonymize_tenant` mitgeschrubbt, statt die Liste zu
verlängern.

## 6 Frontend

### 6.1 Raster: Umbruch statt Abschneiden

Zwei getrennte Mechanismen, die nicht verwechselt werden dürfen:

**Die Höhe wächst im Browser, nicht in der Rechnung.** Der Block gibt seine
Zeitdauer künftig als `minHeight` vor statt als festes `height`; `truncate`
entfällt, Namen und Hinweis brechen um (`break-words`). Damit wächst ein Block
genau so weit, wie sein Inhalt es verlangt — unabhängig davon, wie schmal seine
Spur gerade ist. Das allein löst das Problem des Issues.

**Die Markierung kommt aus einer Schätzung.** Damit erkennbar bleibt, wo die
Blockhöhe nicht mehr die Uhrzeit meint, bekommt `weekGridUtils.ts` eine reine
Funktion `estimateContentHeight(slot)`: Kopfzeile + Zeitzeile + **eine** Zeile je
zugewiesener Person + Hinweiszeile(n) + Innenabstand, 14 px je Zeile.
`computeWeekLayout` liefert je Box zusätzlich `contentHeight` und
`grown = contentHeight > timeHeight`. Ist `grown` gesetzt, rendert der Block eine
gestrichelte Unterkante und `title="Anzeige reicht über das Zeitfenster hinaus"`.

Bewusst geschätzt statt im DOM gemessen: die Funktion bleibt rein und
unit-testbar, und das Ergebnis ist über alle Browser gleich. Die Schätzung ist
damit in erster Linie eine **Untergrenze** — bricht ein langer Name in einer
sehr schmalen Spur auf zwei Zeilen um, wächst der Block korrekt, kann aber ohne
Markierung bleiben. Das ist hingenommen: die Markierung ist ein Hinweis, keine
Zusicherung.

**Spezifikations-Drift (nachgetragen, Prüfrunde 2):** hier stand ursprünglich,
der umgekehrte Fehler (Markierung ohne echtes Wachstum) könne "nicht
auftreten" — das war zu stark und wurde im Code inzwischen ehrlich
zurückgenommen (Kommentar an `estimateContentHeight` in `weekGridUtils.ts`).
Er ist durch die feste Konstante `NAME_CHARS_PER_LINE` zwar *deutlich
seltener*, aber nicht grundsätzlich ausgeschlossen: in einer sehr breiten Spur
(z. B. der vollen Spalte der Tagesansicht) passen real mehr Zeichen in eine
Zeile, als die Konstante annimmt — bei sehr vielen, kombiniert langen Namen
kann die Schätzung dort eine zusätzliche Zeile ansetzen, die real nicht
gebraucht wird. Der konkret gemeldete Fehlerfall (kurze, wenige Namen in einer
schmalen/normalen Spur) ist damit behoben; eine Garantie für jede denkbare
Namenskombination und Spurbreite gäbe nur eine echte DOM-Messung, die hier
bewusst vermieden wird (siehe Kommentar an `NAME_CHARS_PER_LINE`).

Wächst ein Block in den folgenden hinein, malt der folgende darüber — die
DOM-Reihenfolge folgt der Startzeit — und bleibt lesbar.

### 6.2 Dialoge und Bedienelemente

| Fläche | Änderung |
|---|---|
| `SlotDialog.tsx` | Feld „Hinweis (optional)", `maxLength=500` |
| `PlanSettingsDialog.tsx` | Checkbox „Für Mitarbeitende sichtbar" samt Erklärtext |
| `WeekGrid.tsx` / `SlotBody` | Umbruch, `↳ Hinweis`-Zeile |
| `pages/admin/ShiftPlanning.tsx` | Button „PDF" in der Plan-Werkzeugleiste, über `utils/downloadBlob.ts` |
| `api/shiftPlanning.ts` | `visible_to_employees` an Summary und Detail, `note` an `ShiftSlot`, `exportPlanPdf(id)` |

### 6.3 Mitarbeiter-Ansicht

`pages/ShiftPlanning.tsx` filtert heute **clientseitig**
`summaries.filter(p => p.active_today)`. Bleibt dieser Filter stehen, wirft er
den freigegebenen Zukunftsplan wieder weg — das Feature wäre serverseitig
fertig und am Bildschirm unsichtbar. Der Filter entfällt; das Backend liefert
Mitarbeitenden ohnehin nur noch Sichtbares.

Statt alle Details parallel zu laden: eine Auswahl (`<select>`), sobald mehr als
ein Plan sichtbar ist; das Detail wird nur für den gewählten Plan geholt.
Vorbelegt ist der erste heute aktive Plan, sonst der erste der Liste. Je Eintrag
ein Vermerk „Aktuell" beziehungsweise „Ab 01.09.2026". Der PDF-Knopf steht auch
hier zur Verfügung.

## 7 Tests

**Backend**

- `tests/test_shift_planning_visibility.py`
  - Mitarbeitender sieht einen freigegebenen Zukunftsplan in `list_plans` **und**
    über `get_plan`.
  - Ein nicht freigegebener Entwurf bleibt für ihn 404.
  - Ohne gesetztes Flag ist das Verhalten unverändert (Bestandsfall).
  - `duplicate_plan` kopiert die Freigabe nicht, den Hinweis schon.
- `tests/test_shift_plan_pdf.py`
  - 200 und `%PDF`-Signatur am Dateianfang.
  - 404 bei ausgeschaltetem Feature-Flag.
  - 404 für einen Mitarbeitenden bei nicht sichtbarem Plan.
  - Ein Hinweis mit `<script>` und `&` kommt escaped durch (kein reportlab-Fehler).
- #450: 422 bei einem 300 Zeichen langen Namen; 409 statt 500 beim
  Qualifikations-Konflikt.

**Frontend (vitest)**

- `weekGridUtils.test.ts`: `estimateContentHeight`, `grown`-Flag, und dass ein
  ausreichend langer Slot **nicht** als gewachsen gilt (Kontrollfall).
- `SlotDialog.test.tsx`: Hinweisfeld wird geladen und gespeichert.
- `PlanSettingsDialog.test.tsx` (neu): Checkbox spiegelt den Zustand und wird
  mitgesendet.

**E2E** (`e2e/tests/admin/`, dort liegen bereits drei Shift-Specs)

- Admin gibt einen Zukunftsplan frei → der Mitarbeitende findet ihn in der
  Auswahl.

## 8 Doku-Sync

Nutzer-sichtbare Änderung, also alle Flächen (siehe CLAUDE.md):

1. `docs/SCHICHTPLANUNG.md`
2. `frontend/src/components/DocViewer.tsx` — Admin- **und** Mitarbeiter-Akkordeon
3. `docs/handbuch/*.md` und der Laufzeit-Spiegel `frontend/public/help/*.md`
   (byte-identisch, `diff -q` prüfen)
4. CLAUDE.md — Eintrag zur Sichtbarkeitsregel und zum PDF-Pfad
5. pzweb-Marketing — separater Schritt außerhalb dieses Repos

## 9 Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Der clientseitige `active_today`-Filter bleibt versehentlich stehen und macht das Feature unsichtbar | Ausdrücklicher E2E-Test über die Mitarbeiter-Ansicht, nicht nur ein Backend-Test |
| Ein gewachsener Block überdeckt den folgenden | Der folgende Block wird später gemalt und bleibt oben; gewachsene Blöcke sind durch die gestrichelte Kante gekennzeichnet |
| Das PDF entwickelt einen eigenen Abfragepfad und läuft dem Bildschirm davon | Die Renderfunktion nimmt ausschließlich das Dict von `_build_plan_detail` entgegen und hat keinen `db`-Zugriff |
| Freigabe verrät einen halbfertigen Entwurf | Default `false`; das Duplizieren überträgt die Freigabe nicht |
