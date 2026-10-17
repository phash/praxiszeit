# Glossar — PraxisZeit

Verbindliche Begriffsdefinitionen für die **Zeit- und Urlaubsrechnung**. Ziel: eine
**konsistente Verwendung von Stunden vs. Tagen** in Code, Tests, UI und Doku.

> **Goldene Regel:** **Arbeitszeit rechnet in Stunden, Urlaub rechnet in Tagen.**
> Die Brücke zwischen beiden ist das **Tagessoll** (Stunden pro Arbeitstag).
> Niemals Urlaub als Stundensumme ÷ Durchschnitts-Tagessoll führen (driftet bei
> ungleichmäßigem Tagesplan / Halbtagen) — siehe **Tagesprinzip**.
>
> Seit #431 sind nicht nur die Wochenstunden, sondern der **gesamte Vertragszustand**
> (Wochenstunden, Modus gleichmäßig/Tagesplan, Tageswerte, Arbeitstage/Woche) pro
> Wirkungsdatum historisiert — dieselbe Regel „nie das Live-Feld lesen, immer die
> datumsaufgelöste Funktion" gilt jetzt für alle vier Größen gemeinsam.
>
> Seit 1.20.0 gehören auch die **Arbeitszeit-Blöcke** zu diesem Snapshot (§7).

---

## 1. Einheiten & ihre Bezugsgrößen

| Größe | Einheit | Bedeutung | Maßgebliche Quelle |
|-------|---------|-----------|--------------------|
| **Wochenarbeitszeit** (`weekly_hours`) | Stunden/Woche | Vertraglich vereinbarte Stunden pro Woche (z. B. 40,0). Historisch korrekt über `WorkingHoursChange`. Bei Tagesplan die **Summe** der Tageswerte — serverseitig erzwungen in der `WorkingHoursChange`-Zeile (`check_mode`) und seit #431 auch beim Anlegen (`UserCreate`-Validator). Ein Tagesplan-Mitarbeiter **ohne** eine einzige `WorkingHoursChange`-Zeile fällt dagegen im Fallback-Zweig von `get_schedule_for_date` auf den direkten `user.weekly_hours`-Wert zurück — der kann bei einem vor dieser Regel angelegten Konto weiterhin von der Tagessumme abweichen. | `get_weekly_hours_for_date()` (NIE `user.weekly_hours` direkt lesen) |
| **work_days_per_week** | Tage/Woche | Anzahl Arbeitstage pro Woche (z. B. 5). Seit #431 ebenfalls historisiert. Bei Tagesplan berechnet es ausschließlich der **Dialog** (Frontend) als Zahl der Wochentage mit Stunden > 0 und schickt es mit — Schema und Router übernehmen unverändert, was der Client sendet, ohne eigene Ableitung oder Prüfung. Im Modus „Nach Arbeitsblöcken" (§7) leitet dagegen der Server es ab (`derive_targets`: Zahl der Tage mit Blöcken; ein mitgeschickter Wert wird überschrieben). | `get_schedule_for_date().work_days_per_week` (NIE `User.work_days_per_week` direkt für ein Datum lesen) |
| **Tagessoll** | Stunden/Tag | Soll-Stunden **eines konkreten Tages**. Standard: `weekly_hours ÷ work_days_per_week`. Bei `use_daily_schedule=True`: die pro-Wochentag hinterlegten Stunden (`hours_monday`…`hours_friday`), historisch aus demselben Snapshot. **Wochenende & nicht-geplante Wochentage = 0.** | `get_daily_target_for_date(user, date, schedule)` mit `schedule = get_schedule_for_date(db, user, date)` |
| **Arbeitstag** | — (Kalendertag) | Tag mit **Tagessoll > 0** für diesen MA (kein Wochenende, kein Feiertag, kein 0-Stunden-Wochentag). | abgeleitet aus Tagessoll |
| **Soll** | Stunden | Summe der Tagessolls über einen Zeitraum, **minus** soll-mindernder Abwesenheiten. | `get_range_target()` / `get_monthly_target()` |
| **Ist** | Stunden | Summe `net_hours` der Zeiteinträge **plus** angerechnete Abwesenheiten (TRAINING/SICK). | `get_range_actual()` / `get_monthly_actual()` |
| **net_hours** | Stunden | (Ende − Beginn) − Pause − `uncredited_minutes` (nicht angerechnete Lückenzeit, §7); `max(0, …)`. | `TimeEntry.net_hours` |
| **Saldo** | Stunden | `Ist − Soll` über einen Zeitraum. | `(actual - target)` |
| **Überstundenkonto** | Stunden | **Kumulativer** laufender Saldo (über Monate/Jahr). Darf negativ sein. | `get_overtime_account()` |
| **Urlaubsanspruch / Budget** | **Tage** | Jahresanspruch in Tagen (z. B. 30), anteilig bei Ein-/Austritt + Carryover. | `get_vacation_account()["budget_days"]` |
| **Urlaubsverbrauch (used)** | **Tage** | Σ Urlaubstage (voller Tag = 1,0; Halbtag = 0,5). **Tagebasiert, nicht stundenbasiert.** | `get_vacation_account()["used_days"]` |
| **Resturlaub (remaining)** | **Tage** | `budget_days − used_days`. | `get_vacation_account()["remaining_days"]` |

> **Achtung — `Absence.hours`:** Jede Abwesenheit speichert in `hours` das **Tagessoll
> des Tages** (für die Soll/Ist-Rechnung). Das ist eine **Stunden**-Größe und **nicht**
> das Maß für den Urlaubsverbrauch. Urlaub wird **tagebasiert** gezählt (s. Tagesprinzip),
> nicht durch Summieren von `hours`.

---

## 2. Tagesprinzip (§3 BUrlG)

- **1 freier Arbeitstag = 1 Urlaubstag**, unabhängig vom Tagessoll des Tages.
  **Halbtag = 0,5** Urlaubstage (`Absence.half_day=True`).
- Urlaub an einem **Nicht-Arbeitstag** des MA (Tagessoll = 0, z. B. Donnerstag bei
  einer Mo/Mi/Fr-Kraft) verbraucht **0 Urlaubstage** — das Überspringen ist gewollt,
  **kein** Buchungsverlust. Ein solcher Tag sollte gar nicht erst als „Urlaub"
  erscheinen (irreführend), weil dort nicht gearbeitet wird.
- **Anspruch anteilig:** `30 × Arbeitstage ÷ 5` (überschreibbar beim Anlegen),
  pro-rata bei unterjährigem Ein-/Austritt (`first_work_day`/`last_work_day`).
- Die intern gespeicherten `hours` einer Urlaubs-Abwesenheit dienen **nur** der
  Soll-/Ist-Rechnung, nicht dem Urlaubskonto.

---

## 3. Abwesenheitstypen — Wirkung auf Soll/Ist/Urlaub

| Typ | Soll | Ist | Urlaubskonto (Tage) | Überstundenkonto (Std) |
|-----|------|-----|---------------------|------------------------|
| `VACATION` (Urlaub) | reduziert (Tag zählt nicht als Soll) | — | **−1 Tag** (Halbtag −0,5) | — |
| `SICK` (Krank, §3 EntgFG) | bleibt | **+Tagessoll** (als gearbeitet angerechnet) | — | — |
| `TRAINING` (Fortbildung) | bleibt | **+Tagessoll** (als gearbeitet) | — | — |
| `OVERTIME` (Überstundenausgleich) | **bleibt**, Ist = 0 | 0 | — | **−Tagessoll** (Konto sinkt, darf ins Minus) |
| `PAID_LEAVE` (bezahlte Freistellung, #145) | reduziert | — | — (**kein** Abzug) | — |
| `OTHER` (unbezahlt) | reduziert | 0 | — | — |

> **Überstundenausgleich ≠ Urlaub:** Ein OVERTIME-Tag reduziert das **Überstundenkonto
> um das Tagessoll (Stunden)**, das **Soll bleibt** (NICHT Soll reduzieren). Ein
> VACATION-Tag reduziert das **Urlaubskonto um 1 Tag** und **reduziert das Soll**.

Eigene Abwesenheitsgründe (#312) sind nur ein Etikett über einem dieser eingebauten
Typen (`base_behavior` → `worked`/`paid_free`/`overtime_comp`); die **Berechnung
folgt immer `Absence.type`**.

---

## 4. Schlüssel-Beziehung Stunden ↔ Tage (häufige Fehlerquelle)

```
Tagessoll [Std/Tag]  =  weekly_hours [Std/Woche] ÷ work_days_per_week [Tage/Woche]
                        (oder per-Wochentag bei use_daily_schedule)

Soll [Std]           =  Σ Tagessoll über Arbeitstage des Zeitraums (− soll-mindernde Abw.)
Urlaubsverbrauch [Tage] = Σ (1,0 | 0,5) je VACATION-Arbeitstag        ← NICHT Σ hours ÷ ⌀Tagessoll
OVERTIME-Tag           ⇒ Überstundenkonto −Tagessoll [Std]            ← Stunden, kein Tag
VACATION-Tag           ⇒ Urlaubskonto −1 [Tag] + Soll −Tagessoll [Std]
```

**Konsequenzen, auf die zu achten ist:**
- **Budget-Vergleiche in Tagen führen.** Ein „Rest-Budget ≥ 1 Tag"-Check vergleicht
  **Tage** mit **Tagen** (`remaining_days >= 1.0`), nie Stunden mit Tagen.
- **Zeitbezug von `remaining_days`:** `get_vacation_account(year)` zählt **alle**
  VACATION-Tage des Jahres (auch **zukünftig** gebuchte). Wer den Resturlaub
  **zu einem Stichtag** braucht (z. B. „welcher Urlaub ist bis zu den Betriebsferien
  schon verbraucht?"), darf nicht den Jahres-Rest nehmen — sonst reserviert er
  künftigen Urlaub und verschiebt Tage fälschlich in den Überstundenausgleich
  (Ursache des #314-Folgefehlers).
- **0-Tagessoll-Tage** dürfen weder Urlaub (0 Tage) noch Überstundenausgleich
  (0 Std) erzeugen — an einem Nicht-Arbeitstag gibt es nichts auszugleichen.

---

## 5. Stichtag „bis heute" (#313)

`get_soll_cutoff_date(db, user)` = **heute**, wenn heute ein ausgestempelter
TimeEntry existiert, sonst **gestern**. Live-Anzeigen kappen Soll/Ist an diesem
Stichtag (kein Monats-/Wochen­anfangs-Minus); **Datei-Exporte / §16-Belege rechnen
immer den vollen Zeitraum** (kein Stichtag).

---

## 6. Maßgebliche Funktionen (Single Source of Truth)

| Frage | Funktion |
|-------|----------|
| Vollständiger Vertrags-Snapshot an Datum X (Modus, Tageswerte, Wochenstunden, Arbeitstage)? | `calculation_service.get_schedule_for_date()` |
| Wochenstunden an Datum X? | `calculation_service.get_weekly_hours_for_date()` |
| Tagessoll an Datum X? | `calculation_service.get_daily_target_for_date()` (braucht den Snapshot aus `get_schedule_for_date()` als Pflichtparameter) |
| Soll/Ist über Zeitraum? | `get_range_target()` / `get_range_actual()` (Monat = Wrapper) |
| Überstundenkonto (kumuliert)? | `get_overtime_account()` |
| Urlaubskonto (Budget/Verbrauch/Rest, **Tage**)? | `get_vacation_account()` |
| Urlaubsverbrauch einer Abwesenheitsliste (**Tage**)? | `absence_days()` |
| Stichtag „bis heute"? | `get_soll_cutoff_date()` |
| Arbeitszeit-Blöcke an Datum X? | `work_window_service.get_scheduled_blocks()` (über `get_schedule_for_date()`, nie `users.work_blocks` direkt) |
| Wird an Datum X gekappt? | `work_window_service.clamp_applies()` |
| Nicht angerechnete Minuten eines Eintrags? | `work_window_service.not_credited_minutes()` |

Anzeige in der UI: Stunden immer über `formatHoursHM()` (H:MM), Urlaub in **Tagen**.

---

## 7. Arbeitszeit-Blöcke und Anrechnung (ab 1.20.0)

| Begriff | Bedeutung | Maßgebliche Quelle |
|---------|-----------|--------------------|
| **Arbeitszeit-Block** | Vertraglich hinterlegter Zeitraum „von–bis" an einem Wochentag (Mo–Fr, höchstens 3 je Tag, Raster 5 Min). Teil des Vertrags-Snapshots `working_hours_changes.blocks`; `users.work_blocks` nur Rückfall vor der ersten Verlaufszeile. **Nicht** verwechseln mit einem **Zeiteintrag** (gestempelte Zeit; die Exportspalte „Zeiteinträge" listet diese). | `get_schedule_for_date().blocks` → `get_scheduled_blocks()` |
| **Pause innerhalb der Blöcke** | Geplante Pause (`pause_minutes`); Tagessoll = Σ Blöcke − Pause. NULL = Altfenster aus Migration 073 (nur Kappung, kein Soll). | `work_blocks_service.derive_targets()` |
| **Hülle** | Erster Block − Puffer bis letzter Block + Puffer; Beginn/Ende außerhalb werden verschoben, der Rohstempel bleibt. | `clamp()` |
| **Lücke** | Zeit zwischen zwei Blöcken, an beiden Rändern um den Puffer geschrumpft; eine Lücke ≤ 2 × Puffer verschwindet. Gestempelte Zeit darin ist `uncredited_minutes`. Nicht verwechseln mit der „Unterbrechung" der Datei-Exporte (Zeit ohne Eintrag zwischen zwei Einträgen). | `credit_gaps()` |
| **Puffer** | Toleranz an jedem Blockrand (Mandanten-Setting `work_window_grace_minutes`, Default 15); je Eintrag gespeichert (`clamp_grace_minutes`). | `get_grace_minutes()`, `grace_for_entry()` |
| **angerechnet** | Zeit, die ins Ist eingeht = `net_hours` (nach Pause und Lücke). | `TimeEntry.net_hours` |
| **nicht angerechnet** | Lücke **plus** an der Hülle abgeschnittene Zeit; ohne die synthetische 23:59 des Auto-Close. | `not_credited_minutes()` |
| **Anwesenheit laut Stempel** | `(raw_end or end) − (raw_start or start) − Pause`, beim Auto-Close bis zum wirksamen Ende; Basis der weichen Hinweise `PRESENCE_*` und der Spalte „Anwesenheit laut Stempel" der 24-Wochen-Auswertung. | `presence_minutes()` |
| **Anerkennen** | Verwaltung rechnet einen Eintrag ungekappt an (`credit_override`), dauerhaft, protokolliert (`source = "credit_override"`). | `POST /admin/time-entries/{id}/credit-override` |
| **Neukappung** | Neuberechnung erfasster Einträge nach einer rückwirkenden Arbeitszeit-Änderung – ab Rohstempel, nur geänderte Wochentage, aktueller Puffer; protokolliert als `wh_reclamp`. | `reclamp_time_entries()` |
| **Verkürzung** | Arbeitszeit-Änderung, bei der ein Eintrag angerechnete Zeit verliert, das Überstundenkonto sinkt oder eine Misch-Tag-Gutschrift stärker als das Tagessoll sinkt; rückwirkend nur mit Grund (Schutzpaket). | Vorschau `is_shortening` |

> **Stunden, nicht Tage:** Blöcke, Lücke und „nicht angerechnet" sind Stunden- bzw.
> Minutengrößen. Am Urlaub ändert sich dadurch nichts – er bleibt tagebasiert (§2); ein Wochentag
> ohne Block hat Tagessoll 0 und kostet keinen Urlaubstag.
