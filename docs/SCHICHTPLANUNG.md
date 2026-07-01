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
- **Duplizieren:** Über **Duplizieren** im Plankopf wird ein Plan inklusive aller Slots und Zuweisungen kopiert. Die Kopie ist ein **inaktiver Entwurf ohne Aktiv-Datumsfenster** — ideal, um Varianten („Sommer", „Schulferien") aus einem Bestandsplan abzuleiten, statt alles neu anzulegen. Arbeitsplätze/Einweisungen sind nicht plan-gebunden und werden nicht mitkopiert.
- Im **Wochen-Editor** Slots anlegen/verschieben:
  - **Drag & Drop:** Slot-Block auf einen anderen Wochentag / eine andere Uhrzeit ziehen (15-Minuten-Raster). Mitarbeitende aus der Liste rechts auf einen Slot ziehen → zugewiesen.
  - **Klick-Pfad:** „+ Slot" bzw. Klick auf eine freie Rasterfläche öffnet einen Dialog (Arbeitsplatz, Wochentag, Von/Bis, Mindestbesetzung, Mitarbeitende). Klick auf einen vorhandenen Slot bearbeitet ihn.
- **Mindestbesetzung:** Pro Slot setzbar. Unterbesetzte Slots werden markiert (⚠), der Plan zeigt einen Hinweis. Es ist eine **weiche Warnung** – Speichern und Aktivieren bleiben möglich.

**Aktivschaltung:**
- „Aktiv schalten" macht den Plan für alle sichtbar (Read-only-Ansicht + Dashboard).
- **Mehrere Pläne können gleichzeitig aktiv** sein (z. B. je Standort). Das Dashboard zeigt jedem Mitarbeitenden die **Vereinigung** seiner Einteilungen über alle aktiven Pläne für den heutigen Wochentag.

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

- **Schichtplan** (Menü): **heute aktive** Wochenpläne als Übersicht ansehen (nur
  lesen). Inaktive Entwürfe sind reine Admin-Planungsartefakte und werden für
  Nicht-Admins **serverseitig** ausgeblendet — nicht nur im Frontend (s.
  „Sichtbarkeit").
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
  (`locations`, `workstations`, `shift_plans`, `shift_slots`, `shift_assignments`,
  `workstation_qualifications`), Migrationen `053`–`055` (Tabellen + RLS +
  `shift_plans.active_from_date/active_until_date`). Einweisungen: `GET/PUT
  /qualifications`, `GET /me/qualifications`; pro Slot-Assignment ein
  `qualified`-Flag, pro Plan `unqualified_slot_ids` (weich, admin-only).
- **KW-Planung:** `shift_planning_service.is_plan_active_on/plan_active_filter`
  (is_active ODER Datums-Fenster deckt heute ab, Europe/Berlin via `today_local()`);
  `active_today` in der Plan-Liste/-Detail.
- **Sichtbarkeit (serverseitiges Gating, Fix #7):** Die Read-Endpoints filtern für
  Nicht-Admins **im Backend** auf heute aktive Pläne — nicht nur das Frontend:
  - `GET /plans` (`list_plans`): Nicht-Admins überspringen Pläne, die heute nicht
    aktiv sind (`if not is_admin and not active_today: continue`); Admins sehen
    alle (inkl. Entwürfe).
  - `GET /plans/{id}` (`get_plan`): ein heute **nicht** aktiver Plan liefert für
    Nicht-Admins **404** („existiert nicht"), Admins bekommen das volle Detail
    (`_build_plan_detail(..., is_admin)`).
  - `get_my_today` vereinigt die eigenen Zuweisungen über **alle** aktiven Pläne
    (`plan_active_filter(today)`).
- **Auto-Generierung:** `app/services/shift_planning_generator.py` (Greedy,
  read-only ggü. Calc-Modell), Endpoint `POST /plans/{id}/generate`
  (`target_monday` + `mode=replace|fill_gaps`).
- **Feature-Flag `shift_planning_enabled`** an **drei** Stellen synchron:
  `admin_settings.py` (`_ALLOWED_SETTINGS` + `_BOOL_SETTINGS`), `main.py::system_info()`
  (öffentlich, Default `false`, nie 500), `frontend/src/stores/systemStore.ts`
  (`isShiftPlanningEnabled()`, Default `false`).
- **Frontend:** `pages/admin/ShiftPlanning.tsx` (Editor inkl. Drag & Drop via
  `@dnd-kit/core`), `pages/ShiftPlanning.tsx` (Read-only), `components/ShiftTodayCard.tsx`
  (Dashboard-Widget), `api/shiftPlanning.ts`, `components/shiftplanning/*`.

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
