# Schichtplanung (Issue #305)

Die **Schichtplanung** ist ein optionales Modul, mit dem Admins wöchentliche
Einsatzpläne erstellen: *wer steht wann an welchem Arbeitsplatz*. Sie ist ein
**reines Planungswerkzeug** und **vollständig entkoppelt** von der Zeiterfassung
– sie verändert **keine** Soll-/Ist-Stunden, löst **keine** ArbZG-Prüfungen aus
und berührt **weder Urlaub noch Überstundenkonten**.

> **Standardmäßig deaktiviert.** Das Modul ist nach der Installation **aus** und
> kann **nur von einem Administrator** unter **Einstellungen → Schichtplanung**
> aktiviert werden. Solange es aus ist, sehen weder Admins noch Mitarbeitende
> irgendetwas davon (die API-Endpoints antworten mit 404).

---

## Aktivieren / Deaktivieren

1. Als Administrator anmelden.
2. **Einstellungen → Schichtplanung** öffnen.
3. Schalter **„Schichtplanung aktivieren"** umlegen → **Speichern**.

Danach erscheinen die Menüpunkte **Schichtplanung** (Admin, bearbeiten) und
**Schichtplan** (alle, nur ansehen) sowie auf dem Dashboard die Karte
**„Deine Einteilung heute"**. Deaktivieren blendet alles wieder aus; die
angelegten Daten bleiben erhalten und erscheinen beim erneuten Aktivieren wieder.

Technisch steuert das tenant-weite Setting `shift_planning_enabled` (Default
`false`) das Modul.

### Geplante Wochentage (#371)

Unter **Einstellungen → Schichtplanung** (nur sichtbar, wenn die Schichtplanung
aktiv ist) legen Sie über die Wochentag-Auswahl fest, **welche Wochentage im
Schichtplaner angezeigt und geplant werden**. Standard ist **Montag–Freitag**;
Samstag/Sonntag (oder z. B. ein Schließtag Donnerstag) lassen sich einzeln zu-
oder abschalten. Mindestens ein Tag muss aktiv bleiben.

Ein deaktivierter Wochentag verschwindet aus der **Wochenansicht**, kann **keine
neuen Slots** aufnehmen (400) und wird von der **Auto-Generierung** übersprungen;
Plan-Validierung, „Unterbesetzt"-Badge und die MA-Karte „Deine Einteilung heute"
ignorieren ihn ebenfalls. Bereits auf einem Tag angelegte Slots bleiben in der
Datenbank erhalten und erscheinen wieder, sobald der Tag reaktiviert wird (kein
Datenverlust). Technisch: tenant-weites Setting `shift_planning_weekdays`
(CSV `0`=Mo … `6`=So, Default `0,1,2,3,4`).

---

## Konzepte

| Begriff | Bedeutung |
|---------|-----------|
| **Standort** | Optionale Gruppierung für Arbeitsplätze (z. B. Hauptstelle, Filiale). Arbeitsplätze können auch ohne Standort („global") existieren. |
| **Arbeitsplatz** | Ein zu besetzender Platz (Tresen, Backoffice, Labor, Springer …) mit Farbe für die Wochenansicht. |
| **Schichtplan** | Ein benannter **Wochenplan** (z. B. „Normalzustand", „Azubis Schulferien", „Gabi nicht da") mit optionaler Beschreibung. Beliebig viele möglich. |
| **Zeitslot** | Ein Arbeitsplatz, an einem Wochentag, in einem Zeitfenster (z. B. Tresen, Mo, 08:00–12:00), mit optionaler **Mindestbesetzung**. |
| **Zuweisung** | Ein oder mehrere Mitarbeitende, die einem Slot zugeordnet sind. |
| **Einweisung** | Für welche Arbeitsplätze ein:e Mitarbeiter:in qualifiziert/eingewiesen ist (z. B. Azubi: Empfang ja, Labor nein). |

---

## Bedienung (Admin)

**Stammdaten** (Reiter *Stammdaten*):
- **Standorte** anlegen/umbenennen/löschen (löschen nur, wenn kein Arbeitsplatz daran hängt).
- **Arbeitsplätze** anlegen mit optionalem Standort und Farbe (löschen nur, wenn in keinem Slot verwendet).

**Einweisungen** (Reiter *Einweisungen*):
- Matrix **Mitarbeiter × Arbeitsplätze** mit Häkchen: festlegen, für welche Arbeitsplätze jemand eingewiesen ist. Speichern erfolgt pro Zeile sofort.
- Zieht man im Editor eine:n nicht eingewiesene:n Mitarbeiter:in auf einen Slot, erscheint die **weiche Warnung „nicht eingewiesen"** (gelb); der Slot wird im Wochenraster dezent (gestrichelt) markiert. Es wird **nicht** blockiert — der Admin entscheidet bewusst (z. B. Einarbeitung unter Aufsicht).
- Mitarbeitende sehen ihre eigenen Einweisungen unter **Profil → „Meine Einweisungen"**.

**Schichtpläne** (Reiter *Schichtpläne*):
- Plan anlegen, auswählen, umbenennen, löschen (löscht zugehörige Slots + Zuweisungen).
- **Duplizieren:** Über **Duplizieren** im Plankopf wird ein Plan inklusive aller Slots und Zuweisungen kopiert. Die Kopie ist ein **inaktiver Entwurf ohne Aktiv-Datumsfenster und ohne Freigabe für Mitarbeitende** — ideal, um Varianten („Sommer", „Schulferien") aus einem Bestandsplan abzuleiten, statt alles neu anzulegen. Arbeitsplätze/Einweisungen sind nicht plan-gebunden und werden nicht mitkopiert.
- Im **Wochen-Editor** Slots anlegen/verschieben:
  - **Drag & Drop:** Slot-Block auf einen anderen Wochentag / eine andere Uhrzeit ziehen (15-Minuten-Raster). Mitarbeitende aus der Liste rechts auf einen Slot ziehen → zugewiesen.
  - **Klick-Pfad:** „+ Slot" bzw. Klick auf eine freie Rasterfläche öffnet einen Dialog (Arbeitsplatz, Wochentag, Von/Bis, Mindestbesetzung, Hinweis, Mitarbeitende). Klick auf einen vorhandenen Slot bearbeitet ihn.
- **Mindestbesetzung:** Pro Slot setzbar. Unterbesetzte Slots werden markiert (⚠), der Plan zeigt einen Hinweis. Es ist eine **weiche Warnung** – Speichern und Aktivieren bleiben möglich.
- **Hinweis je Einteilung (#443):** Im Slot-Dialog gibt es das Feld **„Hinweis (optional)"** (höchstens 500 Zeichen), z. B. „Einarbeitung Azubi" oder „Vertretung für Frau Schmidt". Der Text erscheint mit vorangestelltem **»** im Wochenraster unter der Zuweisung und im PDF-Ausdruck. Rein informativ — er fließt in keine Berechnung, Validierung oder Warnung ein und übersteht auch das „Auf Wochentage kopieren" (#322). **Achtung:** sichtbar für alle Mitarbeitenden mit Plansicht und Teil des PDF-Aushangs — keine Gesundheitsangaben oder anderen sensiblen Daten hineinschreiben.

**Aktivschaltung:**
- „Aktiv schalten" macht den Plan für alle sichtbar (Read-only-Ansicht + Dashboard).
- **Mehrere Pläne können gleichzeitig aktiv** sein (z. B. je Standort). Das Dashboard zeigt jedem Mitarbeitenden die **Vereinigung** seiner Einteilungen über alle aktiven Pläne für den heutigen Wochentag.
- **Freigabe für Mitarbeitende (#443):** Über den Knopf „Bearbeiten" (Stift-Symbol) in der Werkzeugleiste des Plan-Editors öffnen Sie die Plan-Einstellungen; dort gibt es zusätzlich den Schalter **„Für Mitarbeitende sichtbar"**. Er blendet den Plan in der Mitarbeiteransicht ein, **auch wenn er heute noch gar nicht gilt** — gedacht, um z. B. einen ab September geltenden Plan schon jetzt bekannt zu machen. Ein heute aktiver bzw. im Datums-Fenster liegender Plan ist ohnehin sichtbar; der Schalter betrifft nur den Fall davor. Er wirkt nicht rückwirkend auf bereits laufende Pläne, die niemand extra freigegeben hat.
- **PDF-Ausdruck (#443):** Der Knopf **„PDF"** in der Werkzeugleiste erzeugt einen Aushang im **Querformat** (A4) mit einer Tabelle **Arbeitsplatz × Wochentag** — zum Aushängen am Schwarzen Brett. Mitarbeitende haben denselben Knopf in ihrer Ansicht und können damit **nur den Plan drucken, den sie ohnehin sehen dürfen**. Der Hinweistext je Einteilung wird mitgedruckt — ein Schwarzes Brett ist oft auch für Patientinnen und Patienten einsehbar. Ein noch nicht geltender (freigegebener) oder bereits abgelaufener Plan trägt in der Kopfzeile des Ausdrucks denselben Vorschau-/Ablauf-Vermerk wie am Bildschirm (fett: „Vorschau — gilt derzeit nicht" bzw. „Nicht mehr gültig") — er ist also auch am Schwarzen Brett nicht mit dem aktuell geltenden Plan zu verwechseln (Prüfrunde 2, I-1).

**KW-/Ganzjahres-Planung (Datums-Fenster):**
- Über **Bearbeiten** kann pro Plan ein optionales **Aktiv-Datums-Fenster** („aktiv von/bis") gesetzt werden. Der Plan gilt dann **automatisch** als aktiv, wenn das heutige Datum im Fenster liegt — zusätzlich zum manuellen „Aktiv schalten". Eine offene Grenze ist erlaubt (nur „von" oder nur „bis").
- Die ausklappbare **Jahresübersicht** zeigt als Zeitstrahl, welcher Plan in welchem Zeitraum des Jahres läuft (mit „heute"-Markierung).

**Auto-Generierung (automatisch füllen):**
- **Automatisch füllen** öffnet einen Dialog: Zielwoche (für Abwesenheiten/Stunden) + Modus (**alle neu verteilen** oder **nur Lücken auffüllen**).
- Der Generator besetzt die Slots greedy mit **eingewiesenen, an dem Tag nicht abwesenden** Mitarbeitenden (innerhalb ihres Beschäftigungsfensters, keine Doppelbelegung überlappender Slots), ausgewogen nach **Auslastung** und **Überstundenkonto**. Ergebnis ist ein **Entwurf** zum Review; der Plan wird **nicht** automatisch aktiv. Nicht besetzbare Slots bleiben offen (Rückmeldung im Toast + Unterbesetzungs-Markierung).
- Liest Abwesenheiten/Stunden/Überstunden **nur lesend** — verändert nichts am Berechnungs-/ArbZG-Modell.

**Tagesansicht (#321):** Im Plan-Editor schaltet **Woche / Tag** die Ansicht um; im Tag-Modus wählt ein Dropdown den Wochentag und zeigt nur dessen Slots in voller Breite — übersichtlich beim Einrichten.

**Schicht kopieren (#322):** Beim **Bearbeiten** eines Slots gibt es **„Auf Wochentage kopieren"**: Wochentage anwählen → der Slot (Arbeitsplatz, Zeit, Mindestbesetzung **und** Zuweisungen) wird auf den gewählten Tagen zusätzlich angelegt — spart das wiederholte Eintippen wiederkehrender Schichten.

**Auslastungsanzeige (#330):** In der Mitarbeiterliste des Editors steht unter jedem Namen die **Auslastung** — zugewiesene Schichtstunden (dieses Plans) zur Wochenarbeitszeit, z. B. **„15,25 / 17 h"**. Die Farbe signalisiert die Passung zur Vertragszeit: **grün** bei ±30 Minuten, **gelb** bei ±1 Stunde, sonst **rot** (ohne hinterlegte Wochenarbeitszeit bleibt die Anzeige neutral). Das erleichtert eine ausgewogene Einteilung.

## Bedienung (Mitarbeitende)

- **Schichtplan** (Menü): **sichtbare** Wochenpläne als Übersicht ansehen (nur
  lesen) — das sind die heute aktiven Pläne **und** die ausdrücklich für
  Mitarbeitende freigegebenen (#443, siehe „Freigabe für Mitarbeitende" oben).
  Sonstige Entwürfe sind reine Admin-Planungsartefakte und werden für
  Nicht-Admins **serverseitig** ausgeblendet — nicht nur im Frontend (s.
  „Sichtbarkeit").
- **Mehrere sichtbare Pläne (#443):** Steht mehr als ein Plan zur Auswahl, erscheint oben eine **Plan-Auswahl** (Dropdown mit Namen + „Aktuell"/„Ab TT.MM.JJJJ"/„Vorschau"). Ein noch nicht geltender Plan trägt zusätzlich den Hinweis „Dieser Plan gilt noch nicht — er ist zur Ansicht freigegeben." — er ist also klar als Vorschau erkennbar und wird nicht mit dem aktuellen Plan verwechselt. Das gilt seit Prüfrunde 2 (I-1) auch für den **Ausdruck** (siehe nächster Punkt) — vorher endete die Kennzeichnung am Bildschirmrand.
- **PDF-Ausdruck (#443):** Der Knopf **„PDF"** druckt den gerade angezeigten Plan als Aushang (Querformat, Arbeitsplatz × Wochentag) — denselben, den Sie auch am Bildschirm sehen. Gilt der Plan heute noch nicht oder nicht mehr, steht das fett in der Kopfzeile des Ausdrucks („Vorschau — gilt derzeit nicht" bzw. „Nicht mehr gültig") — das Papier am Schwarzen Brett verrät also denselben Status wie der Bildschirm.
- **Dashboard → „Deine Einteilung heute":** Arbeitsplatz, Zeit und Plan der heutigen Einsätze.

---

## Abgrenzung / Datenschutz / Recht

- **Keine Kopplung an die Zeiterfassung:** Schichten sind Planung, keine erfassten
  Arbeitszeiten. Es findet **keine** ArbZG-Validierung auf Slots statt und es
  werden **keine** Soll-/Ist-/Urlaubs-/Überstundenwerte verändert.
- **Mandantentrennung:** Alle Daten sind tenant-scoped (RLS + explizite
  `tenant_id`-Filter, F-026).

---

## Architektur (Kurzüberblick)

- **Backend:** `app/routers/shift_planning.py` (Router, hinter der Flag-Dependency
  `require_shift_planning_enabled` → 404 wenn aus), `app/services/shift_planning_service.py`
  (Validierung + „my-today"), Modelle in `app/models/shift_planning.py`
  (`locations`, `workstations`, `shift_plans` inkl. `visible_to_employees`,
  `shift_slots` inkl. `note`, `shift_assignments`, `workstation_qualifications`),
  Migrationen `053`–`055` (Tabellen + RLS + `shift_plans.active_from_date/active_until_date`)
  und `070` (`visible_to_employees` + `shift_slots.note`, #443). Einweisungen: `GET/PUT
  /qualifications`, `GET /me/qualifications`; pro Slot-Assignment ein
  `qualified`-Flag, pro Plan `unqualified_slot_ids` (weich, admin-only).
- **KW-Planung:** `shift_planning_service.is_plan_active_on/plan_active_filter`
  (is_active ODER Datums-Fenster deckt heute ab, Europe/Berlin via `today_local()`);
  `active_today` in der Plan-Liste/-Detail.
- **Sichtbarkeit (serverseitiges Gating, Fix #7, erweitert #443):** Die Read-Endpoints
  filtern für Nicht-Admins **im Backend** — nicht nur das Frontend. Die Regel „darf
  dieser Nutzer den Plan sehen?" lebt **ausschließlich** in
  `shift_planning_service.is_plan_visible_to(plan, d, is_admin)`: Admins sehen jeden
  Plan ihres Mandanten, alle anderen sehen ihn, wenn er an `d` aktiv ist
  (`is_plan_active_on`) **oder** `visible_to_employees` gesetzt ist. `list_plans` und
  `get_plan` hatten bis #443 je eine eigene Inline-Kopie der alten (nur „aktiv heute")
  Regel — genau das Muster, das im Projekt schon mehrfach auseinandergelaufen ist —
  und rufen seither diesen einen Helfer:
  - `GET /plans` (`list_plans`): Nicht-Admins überspringen unsichtbare Pläne; Admins
    sehen alle (inkl. Entwürfe).
  - `GET /plans/{id}` (`get_plan`) und `GET /plans/{id}/export.pdf`: ein für den
    aufrufenden Nutzer unsichtbarer Plan liefert **404** („existiert nicht"), nie 403 —
    das verrät einem Nicht-Admin nicht, dass der Plan überhaupt existiert.
  - `get_my_today` vereinigt die eigenen Zuweisungen weiterhin über **alle** aktiven
    Pläne (`plan_active_filter(today)`) — die Dashboard-Karte zeigt nur, was heute
    tatsächlich gilt, eine Freigabe allein reicht dafür nicht.
  - ⚠️ **Die Mitarbeiter-Frontendseite (`pages/ShiftPlanning.tsx`) darf nicht
    clientseitig auf `active_today` filtern** — vor #443 tat sie genau das und hätte
    einen freigegebenen Zukunftsplan wieder unsichtbar gemacht, obwohl das Backend ihn
    längst liefert. Test: `e2e/tests/admin/shift-planning-visibility.spec.ts`.
- **PDF-Aushang (#443):** `GET /plans/{id}/export.pdf`, Renderer in
  `app/services/shift_plan_export_service.py` — bewusst **nicht** in
  `export_service.py` (dort liegt die §16-/Calc-Exportfläche, dieser Export berührt
  keine Berechnung). Der Renderer ist eine **reine** Funktion über dem bereits
  gebauten Dict von `_build_plan_detail` (kein eigener `db`-Zugriff), damit der
  Ausdruck kein zweiter Abfragepfad wird und automatisch den #371-Wochentagsfilter
  erbt. Die Unterbesetzung (`understaffed`/`min_staff`) steckt aus demselben Grund
  bereits im Dict; `_cell_paragraph` druckt sie als „Unterbesetzt (x/y)" in die
  Zelle (M-3, Fix-Runde 2) — vorher stand hier fälschlich, das geschähe schon
  "automatisch", ohne dass der Renderer die Felder je gelesen hätte. Zugriff über
  `is_plan_visible_to`, nicht
  `require_admin` — Mitarbeitende drucken nur, was sie ohnehin sehen; Einweisungs-Flags
  stehen nie im PDF. Der Praxisname im Kopf kommt aus `Tenant.name` (`practice_name`
  ist **kein** Settings-Key im Projekt). Alle Nutzertexte (Plan-/Arbeitsplatzname,
  Hinweis) laufen durch `escape_pdf_text`. Der Hinweis-Marker vor `shift_slots.note`
  ist **`»`** (U+00BB), nicht der ursprünglich vorgesehene Pfeil `↳` (U+21B3) — der
  fehlt in reportlabs Standardschrift Helvetica/WinAnsiEncoding und erschien im
  Ausdruck als schwarzes Kästchen. `»` liegt in Helvetica und wird identisch im
  Wochenraster (`WeekGrid.tsx`) verwendet, damit Bildschirm und Ausdruck dasselbe
  Zeichen zeigen. `shift_slots.note` wird bei `lifecycle_service.anonymize_tenant`
  geleert (reines Anzeigefeld, kein Berechnungsbezug, aber potenziell personenbezogener
  Freitext). **`Table(..., splitInRow=1)` (C-1, Prüfrunde 2):** reportlab kann eine
  Tabellenzeile sonst nicht über einen Seitenumbruch teilen — eine hohe Zeile (z. B.
  drei Einteilungen mit je 500-Zeichen-Hinweis am selben Arbeitsplatz/Tag, oder
  ~100 Personen in einer Einteilung) warf sonst dauerhaft eine `LayoutError` (HTTP
  500, der Plan ließ sich nie wieder drucken). **`_status_note()` (I-1, Prüfrunde
  2):** liest `detail["active_today"]` und schreibt bei `False` fett in die
  Kopfzeile — „Vorschau — gilt derzeit nicht" normalerweise, „Nicht mehr gültig"
  wenn `active_until_date` in der Vergangenheit liegt. Bewusst **nicht** an
  `_validity_text`/ein gesetztes Datumsfenster gekoppelt (Freigabe-Schalter und
  Datumsfelder sind unabhängige Einstellungen, siehe `is_plan_visible_to`).
- **Auto-Generierung:** `app/services/shift_planning_generator.py` (Greedy,
  read-only ggü. Calc-Modell), Endpoint `POST /plans/{id}/generate`
  (`target_monday` + `mode=replace|fill_gaps`).
- **Feature-Flag `shift_planning_enabled`** an **drei** Stellen synchron:
  `admin_settings.py` (`_ALLOWED_SETTINGS` + `_BOOL_SETTINGS`), `main.py::system_info()`
  (öffentlich, Default `false`, nie 500), `frontend/src/stores/systemStore.ts`
  (`isShiftPlanningEnabled()`, Default `false`).
- **Frontend:** `pages/admin/ShiftPlanning.tsx` (Editor inkl. Drag & Drop via
  `@dnd-kit/core`), `pages/ShiftPlanning.tsx` (Read-only, Plan-Auswahl + PDF-Knopf,
  #443), `components/ShiftTodayCard.tsx` (Dashboard-Widget), `api/shiftPlanning.ts`,
  `components/shiftplanning/*` (u. a. `PlanSettingsDialog.tsx` mit dem
  Freigabe-Schalter, `SlotDialog.tsx` mit dem Hinweisfeld). ⚠️ **`PUT /slots/{id}`
  ist ein Vollersatz** (kein Patch) — ein Aufrufer, der seine Nutzlast Feld für Feld
  aufzählt statt den bestehenden Slot als Basis zu nehmen, setzt jedes vergessene
  Feld (z. B. `note`) stillschweigend auf `null` zurück. Genau das passierte dem
  Drag-Handler beim Verschieben eines Slots (Fix in derselben #443-Reihe); neuer Code
  gegen diesen Endpunkt übernimmt unveränderte Felder aus dem geladenen Slot.

---

## Website-Text (pzweb) — separater Schritt

Die Produktwebseite (Repo [`pzweb`](https://github.com/phash/pzweb),
`praxiszeit.mr-development.de`) liegt **außerhalb dieses Repos** und hat einen
eigenen Release-/PR-Zyklus. Vorlage zum Übernehmen (z. B. in der Funktionsliste):

> **Schichtplanung (optional).** Erstellen Sie wöchentliche Einsatzpläne: Arbeitsplätze
> (Tresen, Labor, Springer …) je Zeitfenster über die Woche verteilen, Mitarbeitende
> per Drag & Drop zuweisen, Mindestbesetzung prüfen. Mehrere benannte Pläne
> („Normalzustand", „Schulferien") aktiv schalten; jede:r sieht die eigene Einteilung
> im Dashboard. Standardmäßig deaktiviert, jederzeit vom Administrator aktivierbar –
> ein reines Planungswerkzeug, das die Zeiterfassung nicht verändert.

---

*Eingeführt mit Issue #305.*
