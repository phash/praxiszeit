# Glossar — PraxisZeit

Verbindliche Begriffsdefinitionen für die **Zeit- und Urlaubsrechnung**. Ziel: eine
**konsistente Verwendung von Stunden vs. Tagen** in Code, Tests, UI und Doku.

> **Goldene Regel:** **Arbeitszeit rechnet in Stunden, Urlaub rechnet in Tagen.**
> Die Brücke zwischen beiden ist das **Tagessoll** (Stunden pro Arbeitstag).
> Niemals Urlaub als Stundensumme ÷ Durchschnitts-Tagessoll führen (driftet bei
> ungleichmäßigem Tagesplan / Halbtagen) — siehe **Tagesprinzip**.

---

## 1. Einheiten & ihre Bezugsgrößen

| Größe | Einheit | Bedeutung | Maßgebliche Quelle |
|-------|---------|-----------|--------------------|
| **Wochenarbeitszeit** (`weekly_hours`) | Stunden/Woche | Vertraglich vereinbarte Stunden pro Woche (z. B. 40,0). Historisch korrekt über `WorkingHoursChange`. | `get_weekly_hours_for_date()` (NIE `user.weekly_hours` direkt lesen) |
| **work_days_per_week** | Tage/Woche | Anzahl Arbeitstage pro Woche (z. B. 5). | `User.work_days_per_week` |
| **Tagessoll** | Stunden/Tag | Soll-Stunden **eines konkreten Tages**. Standard: `weekly_hours ÷ work_days_per_week`. Bei `use_daily_schedule=True`: die pro-Wochentag hinterlegten Stunden (`hours_monday`…`hours_friday`). **Wochenende & nicht-geplante Wochentage = 0.** | `get_daily_target_for_date(user, date)` |
| **Arbeitstag** | — (Kalendertag) | Tag mit **Tagessoll > 0** für diesen MA (kein Wochenende, kein Feiertag, kein 0-Stunden-Wochentag). | abgeleitet aus Tagessoll |
| **Soll** | Stunden | Summe der Tagessolls über einen Zeitraum, **minus** soll-mindernder Abwesenheiten. | `get_range_target()` / `get_monthly_target()` |
| **Ist** | Stunden | Summe `net_hours` der Zeiteinträge **plus** angerechnete Abwesenheiten (TRAINING/SICK). | `get_range_actual()` / `get_monthly_actual()` |
| **net_hours** | Stunden | Brutto (Ende − Beginn) − Pause; `max(0, …)`. | `TimeEntry.net_hours` |
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
| Wochenstunden an Datum X? | `calculation_service.get_weekly_hours_for_date()` |
| Tagessoll an Datum X? | `calculation_service.get_daily_target_for_date()` |
| Soll/Ist über Zeitraum? | `get_range_target()` / `get_range_actual()` (Monat = Wrapper) |
| Überstundenkonto (kumuliert)? | `get_overtime_account()` |
| Urlaubskonto (Budget/Verbrauch/Rest, **Tage**)? | `get_vacation_account()` |
| Urlaubsverbrauch einer Abwesenheitsliste (**Tage**)? | `absence_days()` |
| Stichtag „bis heute"? | `get_soll_cutoff_date()` |

Anzeige in der UI: Stunden immer über `formatHoursHM()` (H:MM), Urlaub in **Tagen**.
