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
- Im **Wochen-Editor** Slots anlegen/verschieben:
  - **Drag & Drop:** Slot-Block auf einen anderen Wochentag / eine andere Uhrzeit ziehen (15-Minuten-Raster). Mitarbeitende aus der Liste rechts auf einen Slot ziehen → zugewiesen.
  - **Klick-Pfad:** „+ Slot" bzw. Klick auf eine freie Rasterfläche öffnet einen Dialog (Arbeitsplatz, Wochentag, Von/Bis, Mindestbesetzung, Mitarbeitende). Klick auf einen vorhandenen Slot bearbeitet ihn.
- **Mindestbesetzung:** Pro Slot setzbar. Unterbesetzte Slots werden markiert (⚠), der Plan zeigt einen Hinweis. Es ist eine **weiche Warnung** – Speichern und Aktivieren bleiben möglich.

**Aktivschaltung:**
- „Aktiv schalten" macht den Plan für alle sichtbar (Read-only-Ansicht + Dashboard).
- **Mehrere Pläne können gleichzeitig aktiv** sein (z. B. je Standort). Das Dashboard zeigt jedem Mitarbeitenden die **Vereinigung** seiner Einteilungen über alle aktiven Pläne für den heutigen Wochentag.

## Bedienung (Mitarbeitende)

- **Schichtplan** (Menü): aktive Wochenpläne als Übersicht ansehen (nur lesen).
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
  `workstation_qualifications`), Migrationen `053_add_shift_planning` +
  `054_add_workstation_quals` (Tabellen + RLS). Einweisungen: `GET/PUT
  /qualifications`, `GET /me/qualifications`; pro Slot-Assignment ein
  `qualified`-Flag, pro Plan `unqualified_slot_ids` (weich).
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
