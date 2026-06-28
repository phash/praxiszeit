# Spec: Betriebsferien über Urlaub → Überstundenabbau (#314)

**Status:** Done
**Erstellt:** 2026-06-28
**Zuletzt aktualisiert:** 2026-06-28
**Zugehörige Issues:** #314 (+ Folge-Fix Kundenreport „philvdb")
**Verwandt:** `2026-05-28-company-closures-editable-design.md` (#142, `closure_id`-FK),
`2026-05-28-paid-leave-special-days-design.md` (#145, `counts_as_vacation`),
`docs/specs/features/absences.md`, `docs/GLOSSAR.md`

---

## Überblick

Betriebsferien sind **angeordneter Pflichturlaub** (der Arbeitgeber legt den
Zeitraum fest) und werden für alle teilnehmenden Mitarbeitenden gebucht — **auch
über das verbleibende Urlaubsbudget hinaus** (bewusst kein Cap, anders als die
freiwilligen Direkt-/Antragspfade). Standardmäßig erzeugt das bei zu wenig
Resturlaub **Minus-Urlaub**.

Dieses Feature führt einen globalen Schalter ein, der den über das Budget
hinausgehenden Anteil **statt als Minus-Urlaub** als **Überstundenausgleich**
verbucht: erst wird der vorhandene Urlaub aufgebraucht, danach werden die
restlichen Betriebsferientage als `OVERTIME` gebucht (das Überstundenkonto sinkt
und **darf ins Minus** gehen). So zahlt der Mitarbeiter die angeordneten freien
Tage primär aus dem Urlaub und sekundär aus dem Überstundenkonto — nie aus einem
nicht existierenden („Minus"-)Urlaubsanspruch.

**Verifiziert gegen:** `backend/app/services/closure_split_service.py`,
`backend/app/routers/company_closures.py` (`_create_closure_absences`,
`create/update/delete_closure`), `backend/app/routers/admin_settings.py`,
`backend/app/routers/absences.py`, `backend/app/routers/admin_vacations.py`,
`backend/app/routers/vacation_requests.py`,
`backend/app/routers/admin_change_requests.py`.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich einstellen können, dass Betriebsferien, die das
Urlaubsbudget eines Mitarbeiters übersteigen, den Rest als Überstundenabbau
verrechnen statt Minus-Urlaub zu erzeugen.

- [x] **REQ-1**: Globaler (tenant-scoped) Bool-Schalter
  `closure_overtime_after_vacation`, **Default aus** → unverändertes Alt-Verhalten
  (alle Betriebsferientage = `VACATION`, ggf. Minus-Urlaub).
- [x] **REQ-2**: Bei aktivem Schalter **und** `counts_as_vacation=true` der
  Schließung: Betriebsferien-Arbeitstage werden **chronologisch** zuerst als
  `VACATION` gebucht (solange Resturlaubsbudget ≥ 1 ganzer Tag), danach als
  `OVERTIME` (Überstundenausgleich → Soll bleibt, Ist = 0, Überstundenkonto
  sinkt).
- [x] **REQ-3**: **Nie Minus-Urlaub** bei aktivem Schalter — sobald das Budget
  keinen vollen Tag mehr deckt, wird jeder weitere Tag `OVERTIME` (auch ein
  verbleibender halber Resttag wird `OVERTIME`, kein Minus-Urlaub).
- [x] **REQ-4**: Der Split folgt der **Kalenderreihenfolge** über **alle**
  Betriebsferien eines Jahres, nicht der Eingabe-/Anlegereihenfolge. Der Überhang
  landet auf den **kalendarisch spätesten** Betriebsferientagen.
- [x] **REQ-5**: Re-Split-Trigger an **allen** Schreibpfaden, die das Budget
  verschieben (siehe „Re-Split-Trigger").
- [x] **REQ-6**: Ein **nachträglich aktivierter** Schalter greift auf
  **bestehende** Betriebsferien per **Re-Save** (PUT) der Schließung.
- [x] **REQ-7**: `OVERTIME`-Tage zählen **nicht** gegen das Urlaubsbudget
  (`get_vacation_account` summiert nur `VACATION`).

### Nicht-funktionale Anforderungen

- [x] **Calc-Modell unverändert:** der Split setzt ausschließlich `Absence.type`
  (VACATION ↔ OVERTIME). Es werden keine neuen Berechnungspfade eingeführt; die
  bestehende Soll-/Ist-/Urlaubs-Logik trägt das Verhalten allein über den Typ.
- [x] **Idempotenz:** ein Re-Save ohne sonstige Änderung darf das Ergebnis nicht
  verändern (Budget-Snapshot wird ohne die eigenen Closure-Tage berechnet).
- [x] **Untracked-MA** (`track_hours=False`, kein Überstundenkonto) bleiben bei
  `VACATION` — ein `OVERTIME`-Tag würde aus der Verrechnung verschwinden.

### Out of Scope / Bekannte Limitierungen

- **`half_day`-Sondertage (24./31.12. = `half_day`):** werden bei der
  Betriebsferien-Buchung **als voller Tag** behandelt — Halbtags-Split innerhalb
  eines Closure-Tags ist nicht implementiert (Tech-Debt, dokumentiert in
  `docs/BACKEND-ARCHITEKTUR.md`).
- **Cap der Pflichturlaubs-Buchung:** wird **bewusst nicht** eingebaut —
  Betriebsferien dürfen über das Budget hinaus buchen (Schalter aus = Minus-
  Urlaub, Schalter an = Überstundenabbau). Die freiwilligen Pfade
  (`create_absence` / `review_vacation_request`) cappen dagegen hart (400).

---

## Design

### Einstellung

| Key | Typ | Default | Quelle |
|---|---|---|---|
| `closure_overtime_after_vacation` | Bool | `false` (aus) | `system_settings`, tenant-scoped |

**Synchron an zwei Stellen** (reines Backend-Verhalten, **kein** `system_info`):
- `admin_settings.py`: `_ALLOWED_SETTINGS` **+** `_BOOL_SETTINGS`.
- Frontend: Checkbox in `Settings.tsx` (mit Hinweistext zum Re-Save bestehender
  Betriebsferien).

### Verrechnungsregel (pro MA, pro Jahr)

1. **Budget** = Brutto-Jahres-Urlaubsbudget (`get_vacation_account(...)`,
   Pro-Rata + Carryover) — **unabhängig** von Buchungen.
2. **Nicht-Closure-Verbrauch** wird **vorab** vom Budget abgezogen:
   - privater Urlaub (`VACATION`-Absences mit `closure_id IS NULL`) des Jahres,
   - `free`+`counts_as_vacation`-Sondertage (24./31.12.) des Jahres
     (`special_days_service.vacation_deduction_dates_for_year`).
   - **`dt_day > 0`-Filter:** Tage mit Tagessoll 0 (z. B. der freie Wochentag
     eines `use_daily_schedule`-Teilzeitlers) verbrauchen **kein** Budget — exakt
     wie die `used_days`-Schleife in `get_vacation_account`. Außerdem werden Tage
     außerhalb des Beschäftigungsfensters (`first_work_day`/`last_work_day`)
     übersprungen.
   - **Auch später im Jahr** gebuchter Urlaub (z. B. Sommerurlaub) zählt mit →
     `closure_budget = budget − consumed`.
3. **Closure-Tage in Kalenderreihenfolge** (`sorted(absences, key=date)`):
   VACATION solange `closure_budget − used ≥ 1.0`, danach OVERTIME. Der Überhang
   landet damit auf der **kalendarisch letzten** Betriebsferien des Jahres.

### Zwei Implementierungsorte

Der Split lebt an zwei komplementären Stellen:

**(a) Buchungszeit — `_create_closure_absences` (`company_closures.py`):**
entscheidet beim **Anlegen** je Tag VACATION-vs-OVERTIME gegen einen
**Resturlaubs-Snapshot** (`get_vacation_account(...)["remaining_days"]`, lazy pro
Jahr am ersten buchbaren Tag), verbraucht ihn chronologisch (`sorted(workdays)`).
Übersprungene Tage (Fenster/Fremd-Absence/Tagessoll 0) verbrauchen **kein**
Budget — die Split-Entscheidung fällt erst unmittelbar vor `db.add`.

**(b) Jahres-Re-Split — `closure_split_service.resplit_year_closures`:** läuft
**nach** dem Anlegen/Ändern und re-klassifiziert **alle** budgetwirksamen
Betriebsferien-Absences des Jahres **in Kalenderreihenfolge** über alle
Schließungen hinweg — und korrigiert damit den Effekt, dass `(a)` je Schließung
in **Eingabereihenfolge** entscheidet (eine im Dezember zuerst angelegte
Schließung würde sonst das Budget vor der kalendarisch früheren Juni-Schließung
„aufbrauchen"). `(b)` mutiert **nur** `absence.type` — es wird kein Tag erzeugt
oder gelöscht, sodass alle Guards aus `(a)` (Beschäftigungsfenster #298,
Tagessoll-0-Skip, AC-11-Sondertage, #290-„work wins", Audit-Log, `half_day`,
`closure_id`, `hours`) erhalten bleiben.

> Der eigenständige Service-Modul-Schnitt (`closure_split_service.py`, in
> `company_closures.py` als `_resplit_year_closures` re-importiert) existiert,
> damit die Privaturlaubs-Schreibpfade den Re-Split **ohne** Router-Import (→
> Zirkelimport) aufrufen können.

### Re-Split-Trigger

Weil der Re-Split **allen Privaturlaub vorweg** vom Budget abzieht, MUSS jeder
Pfad, der Privaturlaub bucht/storniert oder eine Schließung verändert, den
Re-Split für die betroffenen Jahre auslösen (bei aktivem Schalter; vor dem
Budget-Snapshot ein `db.flush()`, damit gelöschte Absences nicht mehr zählen):

| Pfad | Datei | Auslöser |
|---|---|---|
| Betriebsferien anlegen | `company_closures.create_closure` | nach Buchung |
| Betriebsferien bearbeiten / Re-Save | `company_closures.update_closure` | jedes PUT (s. u.) |
| Betriebsferien löschen | `company_closures.delete_closure` | freigewordenes Budget → spätere Closure-OVERTIME-Tage flippen zurück auf VACATION |
| Urlaub direkt buchen | `absences.create_absence` (nur `type==VACATION`) | Budget sinkt |
| Urlaub direkt löschen | `absences.delete_absence` (war `VACATION`) | Budget steigt |
| Urlaubsantrag genehmigen | `admin_vacations.review_vacation_request` | Budget sinkt |
| Urlaubsantrag stornieren (Admin) | `admin_vacations.cancel_vacation_request_as_admin` | Budget steigt |
| Urlaubsantrag zurückziehen (MA) | `vacation_requests.withdraw_vacation_request` | Budget steigt |
| Abwesenheits-Änderungsantrag (CR) genehmigen | `admin_change_requests` | Budget verschiebt sich |

> Bei neuen Urlaubs-Schreibflächen den Trigger **mitziehen** (CLAUDE.md-Regel).

### Re-Save eines nachträglich aktivierten Schalters (Folge-Fix philvdb)

`update_closure` gated den Split **nicht** mehr auf eine strukturelle Änderung
(Datum/Flag): bei aktivem Schalter + `counts_as_vacation` löst **jedes** PUT
(auch reines „Speichern"/Umbenennen) ein **Delete + Re-Split** der in-range-
Absences aus. Der Budget-Snapshot wird **ohne** die eigenen Closure-Tage
berechnet (vorher gelöscht + `flush`) → ohne sonstige Änderung **idempotent**.

So greift ein **nachträglich** aktivierter globaler Schalter auf **bestehende**
Betriebsferien: das Umlegen des Schalters allein bucht persistierte Absences
**nicht** um — das **Re-Save** der Schließung tut es. (Re-Typing „in place" wäre
unsicher: ein blindes Zurückdrehen budget-erschöpfter OVERTIME-Tage auf VACATION
könnte Minus-Urlaub re-erzeugen.)

### Zusammenspiel mit Jahresabschluss

Löscht man eine Schließung in einem bereits **abgeschlossenen** Jahr, liefert
`delete_closure` eine **Warnung** (`stale_year_closing_warning`) als `200 +
{"warning": …}` — der eingefrorene Carryover wird **nie** automatisch neu
berechnet (Fix #5).

---

## Verhalten je Schalterstellung (Zusammenfassung)

| Schalter | Resturlaub deckt Closure? | Ergebnis |
|---|---|---|
| **aus** (Default) | egal | alles `VACATION` (ggf. Minus-Urlaub) — Alt-Verhalten |
| **an** | ja | alles `VACATION` (kein Überhang) |
| **an** | nein | Urlaub zuerst (chronologisch), Überhang `OVERTIME` auf den spätesten Tagen; **kein** Minus-Urlaub |
| **an**, Closure `counts_as_vacation=false` | egal | kein Split — `PAID_LEAVE` (bezahlte Freistellung, kein Urlaub/Überstunden) |
| **an**, MA `track_hours=False` | egal | kein Split — `VACATION` (kein Überstundenkonto) |

---

## Tests

- `backend/tests/test_closure_overtime_split.py`
  (`TestClosureOvertimeSplitUpdate`, `TestClosureSpecialDays`): Split bei Anlegen,
  Re-Save eines nachträglich aktivierten Schalters, Kalenderreihenfolge über
  mehrere Schließungen, `free`-Sondertage budget-neutral, untracked-MA bleibt
  VACATION, kein Minus-Urlaub bei Rest-Halbtag.
- Re-Split-Trigger der Privaturlaubs-Pfade (Buchung/Storno) verschieben das
  Budget korrekt (Closure-OVERTIME-Tag flippt ↔ VACATION).
