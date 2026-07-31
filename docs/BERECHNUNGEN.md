# Stunden- und Urlaubsberechnung – PraxisZeit

> **Stand: Juli 2026 · App-Version 1.17.0**
> Diese Doku beschreibt **exakt**, wie PraxisZeit Soll-, Ist-, Überstunden- und
> Urlaubswerte berechnet. Alle Formeln sind aus
> [`backend/app/services/calculation_service.py`](../backend/app/services/calculation_service.py)
> hergeleitet. Bei Code-Änderungen an der Berechnung **diese Datei mitpflegen**.
>
> Verwandt: [ARC42.md](ARC42.md) · [BACKEND-ARCHITEKTUR.md](BACKEND-ARCHITEKTUR.md) → Berechnungsmodell · [GLOSSAR.md](GLOSSAR.md) → verbindliche Begriffe.

---

## 0. Inhalt

1. [Grundbegriffe](#1-grundbegriffe)
2. [Pro-Mitarbeiter-Konfiguration](#2-pro-mitarbeiter-konfiguration)
3. [Tagessoll](#3-tagessoll-daily-target)
4. [Ist-Stunden (net_hours)](#4-ist-stunden-net_hours)
5. [Monats-Soll](#5-monats-soll)
6. [Abwesenheits-Typen-Matrix](#6-abwesenheits-typen-matrix)
7. [Saldo & Überstundenkonto](#7-saldo--überstundenkonto)
8. [Urlaubskonto](#8-urlaubskonto)
9. [Betriebsferien (Company Closures)](#9-betriebsferien-company-closures)
10. [Minijob / MiLoG-Arbeitszeitkonto](#10-minijob--milog-arbeitszeitkonto)
11. [Jahresabschluss / Carryover](#11-jahresabschluss--carryover)
12. [Sonderfälle](#12-sonderfälle)
13. [Worked Examples – Vollzeit](#13-worked-examples--vollzeit)
14. [Worked Examples – Teilzeit](#14-worked-examples--teilzeit)
15. [Worked Example – Minijob (MiLoG-Fixmodus)](#15-worked-example--minijob-milog-fixmodus)

---

## 1. Grundbegriffe

| Begriff | Bedeutung |
|---------|-----------|
| **Soll** | Stunden, die der MA an einem Tag/Monat arbeiten *müsste* (vertraglich) |
| **Ist** | Tatsächlich erfasste Arbeitszeit (`net_hours`) + gutgeschriebene Abwesenheiten |
| **Saldo / Überstunden** | `Ist − Soll` (positiv = Mehrarbeit, negativ = Minusstunden) |
| **Tagessoll** | Soll-Stunden für einen einzelnen Arbeitstag |
| **Tagesprinzip** | Urlaub wird in **Tagen** gezählt (§3 BUrlG): 1 freier Arbeitstag = 1 Urlaubstag |
| **Carryover** | Jahresübertrag von Überstunden und Resturlaub ins Folgejahr |
| **Saldo-Stichtag „bis heute"** | Für **Live-Anzeigen**: letzter Tag mit abgeschlossenem (ausgestempeltem) Arbeitstag (§7.4, #313). Datei-Exporte/Journal/Jahresabschluss rechnen ohne Stichtag den vollen Zeitraum (§16-Rechtsbeleg). |

**Goldene Regel (CLAUDE.md):** Das Wochensoll wird **nie** direkt aus `user.weekly_hours`
gelesen, sondern immer über `get_weekly_hours_for_date(db, user, datum)` — nur so werden
rückwirkende Stundenänderungen (`working_hours_changes`) tagesgenau berücksichtigt.

---

## 2. Pro-Mitarbeiter-Konfiguration

Diese Felder am `User` steuern die gesamte Berechnung:

| Feld | Bedeutung | Beispiel VZ | Beispiel TZ |
|------|-----------|-------------|-------------|
| `weekly_hours` | Wochensoll in Stunden (historisiert, s. u.) | `40` | `20` |
| `work_days_per_week` | Arbeitstage/Woche (Divisor fürs Tagessoll bei gleichmäßiger Verteilung; historisiert, s. u.) | `5` | `3` |
| `use_daily_schedule` | individueller Tagesplan statt gleichmäßiger Verteilung (historisiert, s. u.) | `false` | `true` |
| `hours_monday … hours_friday` | Stunden je Wochentag (nur bei `use_daily_schedule`; historisiert, s. u.) | – | `8/8/8/0/0` |
| `vacation_days` | Jahres-Urlaubsanspruch in **Tagen** | `30` | `18` |
| `track_hours` | Soll/Ist-Zählung aktiv? (`false` = leitende Angestellte) | `true` | `true` |
| `first_work_day` / `last_work_day` | Eintritt/Austritt (Soll/Urlaub anteilig) | optional | optional |
| `scheduled_start_<wd>` / `scheduled_end_<wd>` | Arbeitszeit-Fenster je Wochentag (#201) | optional | optional |
| `receives_company_closures` | Nimmt an Betriebsferien teil? (§9, Default `true`, unabhängig von der Rolle) | `true` | `true` |
| `milog_working_time_account` | Minijob-Arbeitszeitkonto § 2 Abs. 2 MiLoG aktiv (§10, Default `false`) | `false` | `false` |
| `agreed_monthly_hours` | Vereinbarte Monatszeit für die Minijob-Prüfung (§10.4, optional) | – | – |
| `use_fixed_monthly_target` | Festes Monats-Soll statt Tages-Summe (Minijob-Baustein 2b, §10.5, Default `false`) | `false` | `false` |
| `child_sick_days_per_year` | Persönlicher Kind-krank-Jahresanspruch (§45 SGB V, überschreibt den Tenant-Default) | – | – |

> **Historie (#415/#431):** Ändert sich der Vertragszustand mitten im Jahr — Wochenstunden,
> Arbeitstage/Woche, der Wechsel zwischen gleichmäßiger Verteilung und individuellem
> Tagesplan, oder die Tagesstunden selbst —, wird ein `WorkingHoursChange` mit
> `effective_from` angelegt. Seit #431 trägt diese eine Zeile den **vollständigen
> Vertrags-Snapshot** (alle vier Felder gemeinsam), nicht mehr nur `weekly_hours`.
> `get_schedule_for_date(db, user, datum)` liefert für jeden Tag den damals gültigen
> Snapshot — `get_weekly_hours_for_date` ist seither ein dünner Wrapper darüber. Alte
> Monate bleiben korrekt, neue rechnen mit dem neuen Vertragszustand — gleichermaßen für
> gleichmäßige Verteilung **und** individuellen Tagesplan.

---

## 3. Tagessoll (daily target)

### 3.1 Gleichmäßige Verteilung (`use_daily_schedule = false`)

```
Tagessoll = weekly_hours / work_days_per_week
```

| weekly_hours | work_days_per_week | Tagessoll |
|---|---|---|
| 40 | 5 | **8,00 h** |
| 20 | 5 | **4,00 h** |
| 20 | 2 | **10,00 h** |
| 24 | 3 | **8,00 h** |

> ⚠️ Der Divisor ist `work_days_per_week`, **nicht** fix 5. Ein 3-Tage-MA mit 24 h hat
> 8 h/Tag, nicht 4,8 h.

### 3.2 Individueller Tagesplan (`use_daily_schedule = true`)

`get_daily_target_for_date(user, datum, schedule)` liest aus dem übergebenen
**Vertrags-Snapshot** (`schedule`, aufgelöst über `get_schedule_for_date(db, user, datum)`,
#431) die für diesen **Wochentag** konfigurierten Stunden (`hours_monday … hours_friday`).
Der Snapshot ist ein Pflichtparameter — er liefert für vergangene Daten den damals
gültigen Tagesplan, nicht den heute hinterlegten. Beispiel `8/8/8/0/0`:

| Wochentag | Mo | Di | Mi | Do | Fr | Sa/So |
|---|---|---|---|---|---|---|
| Tagessoll | 8 | 8 | 8 | 0 | 0 | 0 |

> Wie die gleichmäßige Verteilung (§3.1) lässt sich auch dieser Tagesplan über
> „Wochenstunden anpassen…" mit Wirkungsdatum historisch ändern — inkl. Rückrechnung
> bereits gebuchter Abwesenheiten. Siehe TZ-F in §14.

### 3.3 Allgemeine Regeln

- **Wochenende** (Sa/So): Tagessoll immer `0`.
- **`track_hours = false`**: Tagessoll immer `0` (keine Stundenzählung).
- **Sondertage 24./31.12.** (`half_day` / `free`): Tagessoll wird mit Faktor `0,5` bzw. `0` multipliziert (siehe §12.2).

---

## 4. Ist-Stunden (`net_hours`)

Pro Zeiteintrag (`TimeEntry`):

```
net_hours = max( 0 , (end_time − start_time) − break_minutes )
```

- Auf **2 Nachkommastellen** gerundet.
- **Floor bei 0**: kann nie negativ werden (offene Einträge ohne `end_time` → 0).
- **Pause** wird in Minuten geführt und abgezogen.

### 4.1 Arbeitszeit-Fenster (#201)

Ist ein Soll-Fenster gesetzt (`scheduled_start_<wd>` / `scheduled_end_<wd>`), kappt
`work_window_service.clamp()` die Stempelzeit auf `[Soll-Beginn − Puffer, Soll-Ende + Puffer]`
(`work_window_grace_minutes`, Default 15). Die **Rohstempel** bleiben in `raw_start_time` /
`raw_end_time` erhalten (§16 ArbZG); `net_hours` und alle Salden rechnen mit der **gekappten** Zeit.

**Beispiel:** Soll-Fenster Mo 08:00–16:00, Puffer 15 min, MA stempelt 07:30–17:10:

| | Roh | gekappt (effektiv) |
|---|---|---|
| Start | 07:30 | 07:45 |
| Ende | 17:10 | 16:15 |
| Pause | 30 min | 30 min |
| **net_hours** | (informativ) | (16:15 − 07:45) − 0:30 = **8,00 h** |

### 4.2 Gutgeschriebene Abwesenheiten

Zusätzlich zu den Zeiteinträgen zählen **Fortbildung (TRAINING)** und **Krankheit (SICK)**
als geleistete Ist-Stunden (§3 EntgFG): ihre gebuchten `hours` werden zum Ist addiert.

```
Monats-Ist = Σ net_hours(Zeiteinträge im Beschäftigungsfenster)
           + Σ hours(TRAINING + SICK im Beschäftigungsfenster)
```

> Im Minijob-Fixmodus (§10.5) kommt eine dritte, ebenfalls gutgeschriebene Quelle
> hinzu (Feiertag/VACATION/PAID_LEAVE auf einem geplanten Tag) — Details dort.

---

## 5. Monats-Soll

`get_monthly_target(db, user, jahr, monat)` iteriert **jeden Kalendertag** des Monats:

```
für jeden Tag d im Monat:
    überspringe, wenn Wochenende (Sa/So)
    überspringe, wenn d außerhalb [first_work_day, last_work_day]   (#193)
    überspringe, wenn d Feiertag (tenant-scoped)
    überspringe, wenn d ein Abwesenheitstag ist, der das Soll reduziert
    schedule = get_schedule_for_date(db, user, d)                   (#431)
    tagessoll = get_daily_target_for_date(user, d, schedule)
    tagessoll × Sondertag-Faktor (24./31.12.)                       (#146)
    Monats-Soll += tagessoll
```

**Welche Abwesenheiten reduzieren das Soll?** Alle **außer** `TRAINING`, `SICK`, `OVERTIME`
(siehe Matrix §6). D. h. **VACATION, OTHER, PAID_LEAVE** reduzieren das Soll (der MA muss an
diesen Tagen nicht arbeiten); TRAINING/SICK reduzieren es nicht (sie zählen stattdessen als Ist).

> **Optionaler Stichtag:** `get_monthly_target`/`get_monthly_actual` akzeptieren einen
> optionalen `up_to_date`-Parameter, der Soll und Ist zusätzlich an einem Datum kappt. Live-
> Anzeigen füttern hier den **Saldo-Stichtag** aus `get_soll_cutoff_date()` (§7.4); ohne
> diesen Parameter (Default `None`) gilt die volle Monatslogik oben unverändert — so rechnen
> Datei-Exporte/Journal/Jahresabschluss (§9–§15 Worked Examples).
>
> **Minijob-Fixmodus (`use_fixed_monthly_target`, §10.5):** verzweigt früh auf ein **festes**
> Monats-Soll (`agreed_monthly_hours`, pro-rata) statt der Per-Tag-Summe oben — Details §10.5.

---

## 6. Abwesenheits-Typen-Matrix

Wie jeder Abwesenheitstyp Soll, Ist und Urlaubskonto beeinflusst:

| Typ | reduziert Soll? | zählt als Ist? | bucht `hours` | belastet Urlaubsbudget? | Effekt aufs Konto |
|-----|:---:|:---:|---|:---:|---|
| **VACATION** (Urlaub) | ✅ ja | ❌ nein | Tagessoll des Tages | ✅ ja | saldo-neutral; zieht Urlaubstag |
| **SICK** (Krank) | ❌ nein | ✅ ja | Tagessoll des Tages | ❌ nein | saldo-neutral (Soll bleibt, Ist gutgeschrieben) |
| **TRAINING** (Fortbildung) | ❌ nein | ✅ ja | Tagessoll des Tages | ❌ nein | saldo-neutral (zählt als gearbeitet) |
| **PAID_LEAVE** (bezahlte Freistellung) | ✅ ja | ❌ nein | Tagessoll des Tages | ❌ **nein** | saldo-neutral wie OTHER, aber **kein** Urlaubsverbrauch |
| **OTHER** (sonstige, inkl. unbezahlt entschuldigt) | ✅ ja | ❌ nein | Tagessoll des Tages | ❌ nein | saldo-neutral, aber **unbezahlt** (Lohn gekürzt) |
| **OVERTIME** (Überstundenausgleich) | ❌ **nein** | ❌ nein (Ist = 0) | **explizite** Stunden | ❌ nein | **Soll bleibt, Ist = 0 h → Überstundenkonto sinkt** um die geplanten Stunden |

> **OVERTIME-Sonderregel (CLAUDE.md):** Beim Überstundenausgleich bleibt das **Soll bestehen**
> und das **Ist ist 0 h** für den Tag — dadurch reduziert sich das Überstundenkonto. Soll wird
> **nicht** reduziert.
>
> **Buchung der `hours`:** Bei Voll-Tag-Typen wird `hours` = **Tagessoll des konkreten Tages**
> gebucht (nicht der 8-h-Client-Default). Nur OVERTIME behält die explizit eingegebenen Stunden.
> Halbtag (`half_day`): `hours` = 0,5 × Tagessoll.

### 6.1 Eigene Abwesenheitsgründe (`AbsenceReason`, #312) — Calc bleibt eingefroren

Admins können frei benannte Abwesenheitsgründe anlegen (Name, Farbe, `is_active`). Ein
solcher Grund ist **nur ein Label-/Farb-Overlay**: gespeichert wird er über `Absence.reason_id`,
aber **die Berechnung folgt ausschließlich `Absence.type`** — der eingebaute, oben tabellierte
Typ. Beim Anlegen mappt `base_behavior` den Grund fest auf einen dieser Typen
(`BEHAVIOR_TO_ABSENCE_TYPE`, `models/absence.py`; nach dem Anlegen unveränderlich):

| `base_behavior` | mappt auf `AbsenceType` | Bedeutung |
|---|---|---|
| `worked` | `TRAINING` | zählt als gearbeitet |
| `paid_free` | `PAID_LEAVE` | bezahlt frei, kein Urlaubsabzug |
| `overtime_comp` | `OVERTIME` | Überstundenabbau |
| `unpaid_free` | `OTHER` | **unbezahlt** entschuldigt (#376, z. B. „Kind krank") |

**`unpaid_free` (z. B. „Kind krank"):** entschuldigt **unbezahlt** — Soll↓ (wie jedes
`OTHER`), kein Ist, kein Urlaubsverbrauch, saldo-neutral, aber der Lohn wird gekürzt. Im
Calc-Modell ist `unpaid_free` **identisch** zu `paid_free`/`PAID_LEAVE` (beide reduzieren
Soll und lassen Ist/Saldo unberührt) — der einzige Unterschied ist das Reporting-Label
(unbezahlt vs. bezahlt). Es gibt **keinen** Soll- oder Ist-Delta zwischen `PAID_LEAVE` und
einem `unpaid_free`-`OTHER`-Tag.

Für „Kind krank" gilt zusätzlich ein weiches **§45-SGB-V-Limit**: `child_sick_cap()` liefert
den Jahresanspruch in Tagen (`User.child_sick_days_per_year`, sonst Tenant-Setting
`child_sick_days_default`, Default 15); `child_sick_days_used()` zählt **tagebasiert** (wie
§8.2) die Absenzen eines als `tracks_child_sick_limit` markierten Grundes. Wird das
Limit überschritten, erscheint die weiche Warnung `CHILD_SICK_LIMIT` — sie blockiert die
Buchung **nie**.

**DSGVO Art. 9:** Jede Abwesenheit mit `reason_id` wird in den Kollegen-Feeds
(`/absences/calendar`, `/absences/team/upcoming`) für **Nicht-Admins** als `"absent"`
maskiert — ein selbst benannter Grund kann sensibel sein (z. B. „Reha").

---

## 7. Saldo & Überstundenkonto

### 7.1 Monatssaldo

```
Monatssaldo = Monats-Ist − Monats-Soll
```

### 7.2 Kumuliertes Überstundenkonto

`get_overtime_account(db, user, jahr, monat, cutoff_date=None)` summiert die Monatssalden
**kumulativ**:

- **Mit Carryover:** Startwert = `YearCarryover.overtime_hours` (neuester ≤ Jahr), Iteration ab
  Januar dieses Jahres → kein Doppelzählen.
- **Ohne Carryover:** Start ab dem ersten Zeiteintrag, Startwert 0.

```
Konto = Startwert + Σ (Monats-Ist − Monats-Soll)   über alle Monate bis (jahr, monat)
```

Der optionale `cutoff_date`-Parameter ist der **Saldo-Stichtag** (§7.4, #313) — Live-Anzeigen
übergeben ihn, damit der laufende Monat nicht mit einem vollen Monats-Soll gegen ein
unvollständiges Ist rechnet. `get_overtime_history_detailed`/`get_overtime_history` liefern
dieselbe Kette **je Monat** (Soll/Ist/Konto in einem Pass) und sind bitgleich zu
`get_monthly_target`/`get_monthly_actual`/`get_overtime_account` bei gleichem Stichtag.

### 7.3 Year-to-Date (JTD)

`get_ytd_summary` summiert Tagessoll und Ist vom **1. Januar** bis **heute** — bzw. bis zum
**Saldo-Stichtag** (§7.4), wenn ein `cutoff_date` übergeben wird (alle Live-Aufrufer tun das)
— und addiert den Carryover des Jahres:

```
JTD-Überstunden = JTD-Ist − JTD-Soll + carryover_hours(Jahr)
```

### 7.4 Saldo-Stichtag „bis heute" (#313)

Ohne Stichtag zeigte das laufende Monats-/JTD-Saldo am 1. eines Monats sofort ein volles
Monats-Soll gegen (noch) 0 Ist — ein irreführendes „Monatsanfangs-Minus". `get_soll_cutoff_date`
löst das:

```
get_soll_cutoff_date(db, user) =
    heute,    wenn heute bereits ein AUSGESTEMPELTER TimeEntry existiert
    gestern,  sonst
```

**Live-Anzeigen, die den Stichtag nutzen** (kappen Soll UND die per-Tag-Zählung von Ist
gleichermaßen an diesem Datum):

- MA-Dashboard (`/api/dashboard/*`)
- Admin-Team-Tabelle `GET /admin/reports/monthly` + `GET /admin/reports/weekly` — Umschalter
  `?soll_basis=bis_heute|monatsende` (Default `bis_heute`), UI-Dropdown „Soll: bis heute /
  Monatsende"
- Admin-Benutzerübersicht `GET /admin/users-overview`
- Überstundenkonto + -Verlauf (`get_overtime_account`, `get_overtime_history[_detailed]`) und
  dessen Chart
- Year-to-Date (`get_ytd_summary`)

Vergangene, bereits abgeschlossene Monate liegen komplett **vor** dem Stichtag — ein einziger
Stichtag trimmt daher effektiv nur den **laufenden** Monat; ältere Monate sehen mit oder ohne
Stichtag identisch aus.

> **Bewusste Ausnahme — §16-Rechtsbelege rechnen IMMER den vollen Zeitraum:** Alle
> Datei-Exporte (`export_service`, `ods_export_service`), das Monatsjournal
> (`journal_service`) und der Jahresabschluss/Carryover (`create_year_closing`, §11) rufen
> `get_monthly_target`/`get_monthly_actual`/`get_overtime_account` **ohne** `cutoff_date` —
> diese Dokumente bleiben unverändert nach der vollen Monatslogik, damit ein §16-Beleg nicht
> von einer Live-Anzeige abweicht.

### 7.5 Voraussichtlicher Saldo zum Jahresende (#402)

```
Prognose = Saldo bis heute − future_freizeitausgleich_impact(db, user)
```

`calculation_service.future_freizeitausgleich_impact` summiert das **Tages-Soll aller
bereits gebuchten künftigen `OVERTIME`-Abwesenheiten** ab dem Tag NACH dem Saldo-Stichtag
(§7.4) bis zum 31.12. des laufenden Jahres — genau der Betrag, um den ein Ausgleichstag das
Konto später senkt (bei `OVERTIME` bleibt das Soll stehen, das Ist ist 0 → Konto −=
Tages-Soll). Angezeigt im MA-Dashboard und in der Admin-Benutzerübersicht.

* Bewusst **Soll-basiert** über dieselbe Quelle `_day_soll_contribution` wie
  `get_overtime_account`, **nicht** über das `hours`-Feld — so ist die Projektion im
  Dezember bitgleich zum dann tatsächlich gebuchten Saldo.
* `> cutoff_date` verhindert die Doppelzählung mit dem aktuellen (bis-heute-)Saldo.
* Wochenenden, Feiertage (im Fix-Modus) und Tage außerhalb des Beschäftigungsfensters
  zählen nicht; ohne `track_hours` ist die Prognose 0.
* Im **festen Monats-Soll-Modus** (#377 Baustein 2b, §10) zählt statt des abgeleiteten
  Tages-Solls die geplante Tagesarbeitszeit (`_fixed_planned_hours`): dort mindert ein
  `OVERTIME`-Tag das flache Monats-Soll nicht und bringt kein Ist — der Saldo sinkt um die
  geplanten Stunden des Tages.

---

## 8. Urlaubskonto

`get_vacation_account(db, user, jahr)` liefert Budget, Verbrauch und Rest — **in Tagen
(maßgeblich)** und in Stunden (informativ).

### 8.1 Budget

```
budget_days  = vacation_days  (anteilig bei Eintritt/Austritt)  + carryover_days
budget_hours = budget_days × Tagessoll
```

- **Tagessoll fürs Budget** = `get_daily_target(user)` = `weekly_hours / work_days_per_week`
  (Durchschnitt, **nicht** datumsabhängig).
- **Anspruch (vacation_days):** wird pro MA konfiguriert. Empfehlung/Standard nach Tagesprinzip:

  ```
  vacation_days = 30 × work_days_per_week / 5      (Vollzeit 5 Tage → 30; 3 Tage → 18; 4 Tage → 24)
  ```

- **Pro-rata bei Eintritt/Austritt im Jahr** (`first_work_day` / `last_work_day`):

  ```
  budget_days = vacation_days × beschäftigte_Monate / 12
  ```
  Der angebrochene Eintritts-/Austrittsmonat wird taggenau anteilig gerechnet
  (z. B. Eintritt 15.04. → Restmonate = (12−4) + 16/30 = 8,53 → 30 × 8,53/12 ≈ **21,3 Tage**).

### 8.2 Verbrauch (Tagesprinzip)

Nur **VACATION** belastet das Budget (PAID_LEAVE bewusst nicht). Pro Urlaubs-Abwesenheit:

```
used_days  += hours / Tagessoll_DIESES_Tages     (Volltag → 1,0 ; Halbtag → 0,5)
used_hours += hours                                (nur informativ)
```

> Dadurch kostet ein Urlaubstag immer **genau einen Tag seines eigenen Tagessolls** — ein
> 10-h-Montag kostet nicht mehr als ein 4-h-Mittwoch. Beide = 1,0 Urlaubstag.

**Halbtags-Sondertag (24./31.12. als `half_day`, #394):** Fällt ein Urlaubstag auf einen
solchen Tag, kostet er nur **0,5** statt 1,0 Urlaubstag — die tagesbasierte Zählung wendet
dafür den Faktor aus `calculation_service.half_special_day_weight(d, special_cfg)` an. Das
ist **die eine** Quelle für diesen Faktor, geteilt von `get_vacation_account`, `absence_days`
(§12.2), der Betriebsferien-Buchung und dem #314-Re-Split (§9.4) sowie allen
Urlaubsbudget-Pre-Checks — so kann die Halbtags-Regel nie zwischen den Buchungspfaden
divergieren.

**Zusätzlich:** Ein Sondertag (24./31.12.), der als `free` **und** `counts_as_vacation`
konfiguriert ist, verbraucht ebenfalls **1 Urlaubstag** je MA (sofern im Beschäftigungsfenster
und nicht schon als echter Urlaub gebucht) — er ist als kompletter freier Tag konfiguriert,
nicht als Halbtag, und kostet daher den vollen Tag.

### 8.3 Rest

```
remaining_days  = budget_days  − used_days      (maßgeblich, Tagesprinzip)
remaining_hours = budget_hours − used_hours     (informativ)
```

### 8.4 Budget-Check beim Antrag

Beim Anlegen eines Urlaubs/Antrags wird **tagebasiert** geprüft:

```
benötigte_Tage = Σ über buchbare Arbeitstage d von
                   [ (0,5 wenn Halbtag-Antrag, sonst 1,0) × half_special_day_weight(d) ]
```
„Buchbare Arbeitstage" = Werktage im Zeitraum mit Tagessoll > 0 (Feiertage/Wochenenden/
Null-Soll-Tage zählen nicht). Ein 3-Tage-Teilzeit-MA, der „eine ganze Woche" Urlaub nimmt,
verbraucht so nur **3** Urlaubstage. Der Faktor `half_special_day_weight(d)` ist **derselbe
zentrale Helper** wie in §8.2/§12.2: ein Antragstag, der auf einen als „Halbtag" konfigurierten
24./31.12. fällt, trägt nur **0,5** statt 1,0 zum Bedarf bei (Vollzeit-Woche mit 24.12.-Halbtag →
`1,0 + 1,0 + 0,5 = 2,5`). Alle vier Buchungspfade (`absences`, `vacation_requests` ×2,
`admin_change_requests`) wenden ihn an. Dieser Check ist **hart** (400 bei Überziehung) — anders
als die Betriebsferien-Buchung (§9.5), die bewusst nicht cappt.

---

## 9. Betriebsferien (Company Closures)

Ein Admin legt eine Betriebsferien-Periode (Von–Bis + Name + Verrechnung,
`POST /api/company-closures`) an. PraxisZeit bucht daraufhin **automatisch** für jeden
teilnehmenden MA eine Abwesenheit an jedem seiner Arbeitstage im Zeitraum. Teilnahme steuert
`User.receives_company_closures` (Bool, Default `true`, **unabhängig von der Rolle**, §2 —
ein Admin, der zugleich Stunden trackt, nimmt so teil; reine Verwaltungs-Accounts lassen sich
per Flag abwählen).

### 9.1 Wer/was wird gebucht

**Nicht** gebucht wird an:

- Wochenenden
- gesetzlichen Feiertagen
- individuell freien Wochentagen (Teilzeit-Tagesplan, Tagessoll an diesem Wochentag = 0 —
  zum Datum der Schließung historisch aufgelöst, #431)
- als `free` konfigurierten Sondertagen (24./31.12. — ein soll-freier Tag darf keinen
  Urlaubstag kosten)
- Tagen außerhalb `[first_work_day, last_work_day]` (#298 — künftige oder bereits
  ausgetretene MA werden übersprungen, kein „genommener Urlaub" vor dem Eintritt)
- Tagen, an denen der MA bereits **irgendeine** Abwesenheit hat (eine Fremd-Absence wird
  nie überschrieben)

Jede generierte Abwesenheit ist ein **Einzeltag** (`end_date = None`, #394) mit
`note = "Betriebsferien: <Name>"` und einer `closure_id`-Verknüpfung (nicht die ganze
Closure-Spanne — sonst würde die Abwesenheitsliste je Zeile „24.12–31.12." zeigen).

### 9.2 Verrechnung je Schließung (`counts_as_vacation`)

| Option | `Absence.type` | Urlaubsabzug? | Saldo-Effekt |
|---|:---:|:---:|---|
| **Als Urlaub werten** (Standard) | `VACATION` | ✅ 1 Urlaubstag je Arbeitstag | saldo-neutral (Soll↓, Urlaubskonto↓) |
| **Bezahlte Freistellung** | `PAID_LEAVE` | ❌ kein Abzug | saldo-neutral (wie ein Feiertag) |

### 9.3 Halbtags-Sondertag in Betriebsferien (#394)

Fällt ein Closure-Arbeitstag auf einen als `half_day` konfigurierten Sondertag (24./31.12.,
„halber Feiertag"), kostet er nur **0,5 Urlaubstage** statt 1:

```
gebuchte hours          = 0,5 × Tagessoll des Tages
half_day (Feld)          = False    (die generierte Absence selbst ist KEIN Halbtag)
Urlaubs-/Konto-Kosten     = 0,5 × Tagessoll  über half_special_day_weight(), NICHT über half_day
```

> ⚠️ Der naheliegende Weg (`half_day=True` an der generierten Absence setzen) wäre ein
> **Doppel-Halbieren** (Sondertag-Faktor 0,5 × Halbtags-Faktor 0,5 = 0,25) und würde ein
> Phantom-Defizit erzeugen. Richtig: `half_day=False` (das Tagessoll ist durch den
> Sondertag-Faktor bereits auf die Hälfte reduziert — kein Rest-Defizit), die 0,5-Kosten für
> die Urlaubs-/Konto-Zählung kommen zentral über den einen Helper
> `calculation_service.half_special_day_weight(d, cfg)` (§8.2).

### 9.4 Betriebsferien über Jahresurlaub hinaus → Überstundenausgleich (#314)

Ohne Einstellung bucht eine Betriebsferien-Schließung **immer** `VACATION` — reicht das
Jahresbudget nicht, entsteht **Minus-Urlaub** (bewusst zulässig, §9.5).

Globales Tenant-Setting **`closure_overtime_after_vacation`** (Bool, Default **aus**,
Admin-Einstellungen) ändert dieses Verhalten für Schließungen mit `counts_as_vacation = true`:

```
Closure-Arbeitstage CHRONOLOGISCH (nach Datum) sortiert, pro MA:
für jeden Tag:
    Tageskosten = 1,0  (oder 0,5 bei Halbtags-Sondertag, §9.3)
    wenn verbleibendes Jahres-Urlaubsbudget ≥ Tageskosten:
        type = VACATION;  Budget -= Tageskosten
    sonst:
        type = OVERTIME   (Überstundenausgleich: Soll bleibt, Ist = 0 → Konto sinkt, darf ins Minus)
```

Nur für **Stunden-getrackte** MA (`track_hours = True`) — untracked MA (kein
Überstundenkonto) bleiben immer `VACATION`.

**Re-Save wirkt rückwirkend & idempotent:** Ein **nachträglich** aktivierter Schalter bucht
bereits gespeicherte Betriebsferien nicht automatisch um — dafür muss die Schließung erneut
gespeichert werden (`PUT /api/company-closures/{id}`, auch ein reines Umbenennen genügt).
Das löst `resplit_year_closures()` (`services/closure_split_service.py`) aus: **alle**
Closure-Tage des betroffenen Jahres werden **kalenderchronologisch über alle Schließungen
dieses Jahres hinweg** neu klassifiziert (nicht nur die gerade gespeicherte einzelne
Schließung) — der Budget-Snapshot zieht zuerst den privaten Urlaubsverbrauch + freie
Sondertage des Jahres vom Jahresbudget ab, danach werden die Closure-Tage der Reihe nach
verbraucht; der Überschuss landet auf der **letzten** Schließung des Jahres. Derselbe
Re-Split läuft außerdem bei jedem Anlegen/Ändern/Stornieren von Privaturlaub und beim
Löschen einer Schließung (das Budget wird dadurch wieder frei).

### 9.5 Bewusst KEIN Budget-Cap

Anders als der Direkt- oder Antragspfad für privaten Urlaub (Anlegen einer Abwesenheit,
Genehmigen eines Urlaubsantrags — beide lehnen eine das Budget überziehende Buchung **hart**
mit `400` ab, §8.4), prüft die Betriebsferien-Buchung das Resturlaubsbudget **nicht als
Blocker**: Der Arbeitgeber kann Pflichturlaub anordnen, auch wenn er das Budget übersteigt
(Schalter aus → Minus-Urlaub; Schalter an → Überstundenausgleich, §9.4). Ein MA kann
umgekehrt nicht freiwillig überziehen.

---

## 10. Minijob / MiLoG-Arbeitszeitkonto

Opt-in-Feature für geringfügig Beschäftigte mit Arbeitszeitkonto nach § 2 Abs. 2 MiLoG
(#377). Reine **LESE-Schicht** über `calculation_service` (`services/milog_service.py`) —
das auditierte Soll/Ist-Modell wird dafür nicht verändert. Alle Warnungen sind **weich**
(informativ) und blockieren nie das Stempeln oder Buchen.

### 10.1 Gesetzlicher Mindestlohn (Konstante)

`app/core/minimum_wage.py` hält eine datumsabhängige Stufentabelle (chronologisch erweitert,
Werte nie geraten):

| Gültig ab | €/h |
|---|---|
| 01.01.2025 | 12,82 |
| **01.01.2026** | **13,90** |
| 01.01.2027 | 14,60 |

Angezeigt über `/api/system/info`, rein informativ — PraxisZeit speichert **keine
Lohndaten** und prüft keinen 603-€-Grenzwert.

### 10.2 Baustein 1 — 50-%-Warnung (`MILOG_ACCOUNT_50`)

Opt-in je MA: `User.milog_working_time_account = true`. Vergleichsgröße ist die
**vereinbarte Monatszeit** — flach, **nicht** das schwankende Tages-Soll:

```
agreed_monthly = User.agreed_monthly_hours              (Baustein 2a, §10.4, falls gesetzt)
                 sonst  get_weekly_hours_for_date(...) × 13/3   (52 Wochen / 12 Monate)

Konto-Plusstunden = max(0, Monats-Ist − agreed_monthly)
Warnung MILOG_ACCOUNT_50, wenn Konto-Plusstunden > agreed_monthly / 2
```

**Beispiel:** 10 h/Woche vereinbart → `agreed_monthly` = 10 × 13/3 ≈ **43,33 h**, Grenze
(Cap) = **21,67 h**. Erfasstes Monats-Ist = 66 h → Konto-Plusstunden = 66 − 43,33 = 22,67 h
> 21,67 h → `MILOG_ACCOUNT_50`.

> Beide Seiten des 50-%-Vergleichs nutzen bewusst dieselbe **flache** Basis — würde eine
> Seite das (feiertags-/urlaubs-/teilmonats-getrimmte) Tages-Soll nutzen und die andere die
> flache `agreed_monthly`, kippt der Vergleich bei kurzen/langen Monaten fälschlich.

### 10.3 Baustein 1/3 — 12-Monats-Ausgleichsfrist (`MILOG_SETTLEMENT_DUE`)

§ 2 Abs. 2 S. 2 MiLoG verlangt einen Ausgleich von Zeitguthaben binnen 12 Kalendermonaten.
`milog_service.settlement_aging()` führt dafür ein **FIFO** über die **Soll-basierten**
Monats-Deltas (`Ist − Soll`, aus `get_overtime_history_detailed`, mit dem #313-Saldo-Stichtag
gefüttert):

```
für jeden Monat (chronologisch):
    Delta = Monats-Ist − Monats-Soll
    Delta > 0 → neue „Einlage" (Alterung ab diesem Monat)
    Delta < 0 → verbraucht die ÄLTESTEN offenen Einlagen zuerst (FIFO)

älteste offene Einlage > 12 Monate alt   → MILOG_SETTLEMENT_DUE (überfällig)
älteste offene Einlage 11–12 Monate alt  → „bald fällig"
```

Der letzte `YearCarryover` wird als ältester offener Posten geseedet, damit Alt-Guthaben aus
Vorjahren nicht unsichtbar bleibt.

> ⚠️ **Bewusst Soll-basiert, NICHT gegen die flache `agreed_monthly` gerechnet:** Das
> tatsächliche Monats-Soll (`target`) ist bereits um Feiertage, soll-mindernde
> Abwesenheiten (Urlaub, bezahlte Freistellung), Beschäftigungs-Teilmonate und den
> Saldo-Stichtag bereinigt — Urlaub ist **kein** Freizeitausgleich und darf das Arbeitszeit­
> konto nicht belasten. Die flache `agreed_monthly` ist ausschließlich die vertragliche
> Bezugsgröße für die **50-%-Prüfung** (§10.2), nicht für dieses Aging.

Beide Warnungen tragen den Hinweis „sofern die Stunden zur Mindestlohnhöhe vergütet werden"
— ohne gespeicherte Lohndaten kann PraxisZeit den tatsächlichen Mindestlohnbezug nicht prüfen.

### 10.4 Baustein 2a — Vereinbarte Monatszeit direkt hinterlegen

`User.agreed_monthly_hours` (optional): überschreibt die aus `weekly_hours` abgeleitete
flache 13/3-Monatszeit für die 50-%-Prüfung (§10.2) exakt. Ohne gesetzten Wert bleibt die
Ableitung aus den Wochenstunden aktiv.

### 10.5 Baustein 2b — Festes Monats-Soll (`use_fixed_monthly_target`)

Opt-in je MA (`User.use_fixed_monthly_target = true`), setzt zwingend `agreed_monthly_hours
> 0` **und** `track_hours = true` **und** `milog_working_time_account = true` voraus
(Schema-Guard bei Anlage **und** Änderung — ein isoliertes Deaktivieren des Konto-Flags bei
aktivem Fixmodus wird mit `400` blockiert). **Für alle anderen MA ändert sich nichts**
(byte-identisches Verhalten — der Modus ist rein opt-in).

**Monats-Soll wird FEST statt aus Tagen summiert:**

```
Monats-Soll = agreed_monthly_hours
              (bei Ein-/Austritt im Monat kalendertag-anteilig, pro-rata)
```

Die geplanten Tagesstunden (`hours_monday …`) treiben das Soll in diesem Modus **nicht
mehr** — sie sind nur noch das Anwesenheitsmuster und die Basis für die Gutschriften unten.

**Gutschrift bezahlter Fehltage (Monats-Ist):** Ein Feiertag, ein VACATION- oder ein
PAID_LEAVE-Tag auf einem **geplanten** Tag (`hours_<wd> > 0`) schreibt die geplanten
Tagesstunden dem Ist gut (das Konto bleibt neutral):

```
Monats-Ist += Σ geplante Tagesstunden an (Feiertag ∪ VACATION ∪ PAID_LEAVE)-Tagen
              mit hours_<wd> > 0, ohne konkurrierenden TimeEntry
```

> SICK/TRAINING sind **nicht** in dieser Gutschrift enthalten — sie schreiben ihre `hours`
> bereits über den normalen §3-EntgFG-Pfad (§4.2) dem Ist gut; ein zweites Mal addieren
> wäre eine Doppelgutschrift.

**Minderung unbezahlter Fehltage (Soll):** Ein unbezahlter Fehltag (`OTHER`, z. B. „Kind
krank" §6.1) auf einem geplanten Tag **mindert das feste Soll** statt das Ist gutzuschreiben
(unbezahlt entschuldigt — nichts zum Gutschreiben):

```
Monats-Soll -= Σ geplante Tagesstunden an OTHER-Tagen mit hours_<wd> > 0
```

**Weiche Warnung `MILOG_MONTHLY_EXCEEDED`**, wenn das Monats-Ist die vereinbarte Monatszeit
übersteigt (reine Fix-Soll-Plausibilität, unabhängig von §10.2/§10.3).

**Bekannte Grenze:** Fällt ein **ganzer Monat** aus (z. B. Urlaub/Krankheit über den ganzen
Monat) und liegen die geplanten Tagesstunden deutlich unter der vereinbarten Monatszeit
(flexibler Rest), deckt die Gutschrift nur den geplanten Anteil ab — der verbleibende
flexible Rest bleibt ein Konto-Defizit, das der Arbeitgeber manuell korrigieren muss.
Einzelne Fehltage (der Regelfall) sind vollautomatisch korrekt.

> **§16-Datei-Exporte im Fixmodus:** Die Monats-/Jahres-Detailsheets
> (`export_service`/`ods_export_service`) tragen für Fixmodus-MA einen eigenen Branch, der
> die Summenzeilen „Soll/Ist/Saldo" aus `get_monthly_target`/`get_monthly_actual` zieht
> (statt das per-Tag-Soll selbst zu rekonstruieren) — sonst widerspräche sich das
> §16-Dokument selbst.

Ein vollständiges Zahlenbeispiel: §15.

---

## 11. Jahresabschluss / Carryover

`create_year_closing(db, jahr, users)` erzeugt für jedes Mitglied einen `YearCarryover` fürs
Folgejahr (`jahr + 1`):

```
carryover.overtime_hours = get_overtime_account(user, jahr, 12)      # Saldo am 31.12., OHNE Stichtag
carryover.vacation_days  = get_vacation_account(user, jahr).remaining_days   # Resturlaub
```

Diese Werte gehen als Startwerte ins Folgejahr ein (Überstundenkonto-Start bzw. zusätzliche
Budget-Tage). ⚠️ Offen (#191): Carryover für `track_hours = false` (leitende Angestellte).

> **Rückwirkende Änderungen an einem bereits abgeschlossenen Jahr** (z. B. Storno eines
> genehmigten Urlaubs, Löschen einer Betriebsferien-Schließung) machen dessen Carryover
> stale — PraxisZeit rechnet ihn **nicht automatisch neu** (das würde manuelle
> Carryover-Anpassungen überschreiben), sondern liefert eine Warnung
> (`stale_year_closing_warning`), die einen erneuten Jahresabschluss empfiehlt.

---

## 12. Sonderfälle

### 12.1 Leitende Angestellte (`track_hours = false`)

- **Kein Soll/Ist**: Tagessoll = 0, keine Überstundenrechnung.
- **Urlaub trotzdem tagebasiert**: jeder VACATION-Tag = **1 Tag** (Halbtage `half_day=True`
  zählen 0,5, ein Halbtags-Sondertag zusätzlich × 0,5, siehe §8.2/§9.3), jeder
  `free`+`counts_as_vacation`-Sondertag = 1 Tag. Alle Stundenwerte bleiben 0; Budget folgt
  normaler Pro-rata- + Carryover-Logik.
- Response trägt `track_hours: false` (UI blendet Stundenspalten aus).

### 12.2 Sondertage 24.12. / 31.12. (#146)

Tenant-Setting je Tag: `working_day` (Faktor 1), `half_day` (Faktor **0,5**) oder `free`
(Faktor **0**). Bei `free` zusätzlich `counts_as_vacation` (zieht 1 Urlaubstag, §8.2). Der
Faktor wird **nach** Wochenende/Feiertag/Abwesenheit angewandt, damit kein Tag doppelt behandelt wird.

**Halbtags-Sondertag (`half_day`, #394):** kostet in **jeder** tagebasierten Urlaubs-/
Absenz-Zählung nur **0,5** statt 1,0 — egal ob privat gebuchter Urlaub (§8.2), eine
Betriebsferien-Buchung (§9.3) oder ein exportierter Bericht (`absence_days()`). Alle diese
Stellen fragen denselben zentralen Helper `calculation_service.half_special_day_weight(d,
cfg)` ab, damit der Faktor nie zwischen den Pfaden divergiert.

### 12.3 Eintritt/Austritt (#193/#195)

Tage **vor** `first_work_day` oder **nach** `last_work_day` tragen weder Soll noch Ist
(`_within_employment_window`). Das gilt symmetrisch an allen Per-Tag-Schleifen (Monats-Soll,
Überstundenkonto, JTD und Ist-Seite) **und** an der Betriebsferien-Buchung (#298, §9.1) →
keine Phantom-Überstunden durch Einträge außerhalb des Fensters und keine Closure-Absence
vor dem Eintritt.

> ⚠️ **Ist `first_work_day` NICHT gesetzt** und existiert kein Carryover, beginnt
> `get_overtime_account` am 1. des Monats des **ersten Zeiteintrags** und `get_ytd_summary` am
> 1. Januar — das Soll der davorliegenden Tage wird mitgezählt → **Phantom-Minusstunden** bei
> unterjährigem Eintritt. Praxis-Empfehlung: bei jedem nicht-Januar-Eintritt `first_work_day`
> setzen (siehe [HANDBUCH-ADMIN.md](handbuch/HANDBUCH-ADMIN.md) §4 Benutzerverwaltung).

---

## 13. Worked Examples – Vollzeit

> **Annahmen für alle Monatsbeispiele:** Beispielmonat mit **22 Werktagen (Mo–Fr)**, davon
> **1 gesetzlicher Feiertag**. Werte gerundet auf 2 Nachkommastellen. Wie in §7.4 beschrieben,
> gilt hier — wie in Datei-Exporten/Journal — der **volle Monat** (kein Saldo-Stichtag).

### VZ-Profil

| Feld | Wert |
|---|---|
| `weekly_hours` | 40 |
| `work_days_per_week` | 5 |
| `use_daily_schedule` | false |
| **Tagessoll** | 40 / 5 = **8,00 h** |
| `vacation_days` | 30 |

### Beispiel 13.1 – Monatssaldo mit Feiertag und 4 Urlaubstagen

```
Werktage im Monat              = 22
−  Feiertage                   = 1
−  Urlaubstage (VACATION)      = 4        (reduzieren Soll)
= Soll-relevante Arbeitstage   = 17

Monats-Soll  = 17 × 8,00 h     = 136,00 h
```

Der MA arbeitet an den 17 Tagen, an 3 Tagen jeweils 0,5 h länger:

```
Monats-Ist   = 14 × 8,00 + 3 × 8,50 = 112,00 + 25,50 = 137,50 h
Monatssaldo  = 137,50 − 136,00      = +1,50 h  (Mehrarbeit)
```

### Beispiel 13.2 – Krankheit statt Arbeit

Statt eines Arbeitstags ist der MA 1 Tag krank (SICK):

```
SICK reduziert das Soll NICHT  → Soll bleibt 136,00 h (bei 4 Urlaub + 1 Krank: 22−1FT−4U = 17 Soll-Tage,
   der Kranktag ist einer dieser 17 → Soll zählt ihn voll)
SICK zählt als Ist             → 8,00 h gutgeschrieben (Tagessoll)
Saldo-Effekt des Kranktags     = 0 h  (8 h Soll, 8 h gutgeschrieben)
```

### Beispiel 13.3 – Überstundenausgleich (OVERTIME)

MA nimmt 1 Tag Überstundenausgleich, gebucht mit 8,00 h:

```
Soll des Tages bleibt          = 8,00 h
Ist des Tages                  = 0,00 h   (OVERTIME zählt nicht als Ist)
→ Überstundenkonto sinkt       um 8,00 h
```

### Beispiel 13.4 – Urlaubskonto Vollzeit

```
Tagessoll (Budget)  = 40 / 5            = 8,00 h
budget_days         = 30
budget_hours        = 30 × 8,00 h       = 240,00 h

Verbrauch: 4 volle Urlaubstage à 8,00 h
used_days   = 4 × (8,00 / 8,00)         = 4,0 Tage
used_hours  = 4 × 8,00                  = 32,00 h

remaining_days  = 30 − 4                = 26,0 Tage
remaining_hours = 240 − 32              = 208,00 h
```

---

## 14. Worked Examples – Teilzeit

### TZ-A: Gleichmäßig 20 h / 5 Tage

| Feld | Wert |
|---|---|
| `weekly_hours` | 20 |
| `work_days_per_week` | 5 |
| **Tagessoll** | 20 / 5 = **4,00 h** |
| `vacation_days` (Empfehlung 30×5/5) | 30 |

```
Monat (17 Soll-Tage wie 13.1):
Monats-Soll  = 17 × 4,00 h = 68,00 h

Urlaub: 4 volle Tage à 4,00 h
used_days   = 4 × (4 / 4) = 4,0 Tage
budget_days = 30 ,  budget_hours = 30 × 4 = 120 h
remaining   = 26,0 Tage / 104,00 h
```

> Lehre: Auch ein 5-Tage-Teilzeitler hat **30 Urlaubstage** Anspruch — Teilzeit über die
> Stundenzahl/Tag, nicht über weniger Tage.

### TZ-B: 24 h / 3 Tage (Mo–Mi, gleichmäßig)

| Feld | Wert |
|---|---|
| `weekly_hours` | 24 |
| `work_days_per_week` | 3 |
| **Tagessoll** | 24 / 3 = **8,00 h** |
| `vacation_days` (30×3/5) | 18 |

```
Tagessoll (Budget) = 24 / 3 = 8,00 h
budget_days        = 18
budget_hours       = 18 × 8 = 144,00 h

„Ganze Woche" Urlaub: der MA arbeitet nur Mo/Di/Mi → nur 3 buchbare Arbeitstage
benötigte_Tage     = 3 × 1,0 = 3,0 Tage     (Do/Fr haben Tagessoll 0 → zählen nicht!)
used_days          = 3 × (8 / 8) = 3,0 Tage
remaining          = 18 − 3 = 15,0 Tage
```

> Lehre: Der Budget-Check ist **tagebasiert über buchbare Arbeitstage**. Eine Urlaubswoche
> kostet einen 3-Tage-MA nur 3 Tage, nicht 5.

### TZ-C: Ungleichmäßiger Tagesplan (`use_daily_schedule = true`)

Tagesplan **Mo 10 h · Di 10 h · Mi 4 h · Do 0 · Fr 0** = 24 h auf 3 Tage,
`work_days_per_week = 3`, `vacation_days = 18`.

| Wochentag | Mo | Di | Mi | Do | Fr |
|---|---|---|---|---|---|
| Tagessoll | 10 | 10 | 4 | 0 | 0 |

**Tagesprinzip beim Urlaub** — jeder Urlaubstag kostet **1 Tag**, egal wie viele Stunden:

```
Urlaub Montag:    hours = 10,00 ;  used_days += 10 / 10 = 1,0 Tag
Urlaub Mittwoch:  hours =  4,00 ;  used_days +=  4 / 4  = 1,0 Tag
→ 2 Urlaubstage genommen = 2,0 Tage Verbrauch (NICHT 14h / Ø-Tagessoll!)

Budget (informativ in Stunden):
Tagessoll-Ø (Budget) = 24 / 3 = 8,00 h →  budget_hours = 18 × 8 = 144 h
used_hours (informativ) = 10 + 4 = 14,00 h
```

> Lehre: **Tage sind maßgeblich, Stunden nur informativ.** Bei ungleichmäßigem Tagesplan kann
> `used_hours` von `Tage × Ø-Tagessoll` abweichen — das ist gewollt (Tagesprinzip §3 BUrlG).

> Seit #431 lässt sich auch dieser Tagesplan datiert ändern (Wirkungsdatum, mit
> Rückrechnung gebuchter Abwesenheiten je Wochentag) — siehe TZ-F.

### TZ-D: Unterjähriger Eintritt (Pro-rata-Budget)

TZ-B-Profil (`vacation_days = 18`), Eintritt **15.04.**:

```
Tage im April            = 30
Resttage ab 15.04. (inkl)= 30 − 15 + 1 = 16
Restmonate               = (12 − 4) + 16/30 = 8 + 0,533 = 8,533
budget_days              = 18 × 8,533 / 12 ≈ 12,8 Tage   (gerundet auf 0,1)
```

### TZ-E: Rückwirkende Stundenänderung (Historie)

MA war bis 28.02. Vollzeit (40 h/5 = 8 h/Tag), ab 01.03. Teilzeit (20 h/5 = 4 h/Tag).
Ein `WorkingHoursChange(effective_from = 01.03., weekly_hours = 20)` wird angelegt.

```
Februar-Soll  → 8 h/Tag   (alter Wert, unverändert)
März-Soll     → 4 h/Tag   (neuer Wert)
```

`get_weekly_hours_for_date` liefert pro Tag automatisch den damals gültigen Wert — kein
manuelles Nachrechnen alter Monate nötig.

**Darstellung im Bericht (#415).** Wechselt die Stundenzahl *innerhalb* eines
Berichtszeitraums, gibt es keine einzelne richtige Wochenstundenzahl mehr. Berichte weisen
deshalb den **zu Zeitraumsbeginn** gültigen Wert aus und nennen die Änderung daneben:

```
Wochenstunden: 40,0      ab 01.03.2026: 20,0 Std/Woche
```

Die Segmente liefert `calculation_service.weekly_hours_segments(db, user, von, bis)` —
dieselbe Quelle für Bildschirm (Admin-Dashboard) und Datei-Export (Excel, ODS, PDF; in der
Jahresübersicht als angehängte Spalte „Stundenänderungen"). Eine Änderung *vor* dem
Zeitraum steckt bereits im Startwert, eine Änderung auf denselben Wert wird nicht
ausgewiesen.

> ⚠️ **Fallstrick — die Wochenstundenzahl bleibt bei einer reinen Arbeitstage-Änderung
> gleich, das Tagessoll nicht.** Seit #431 lässt sich im Dialog bei gleichmäßiger
> Verteilung auch **„Arbeitstage pro Woche"** mit Wirkungsdatum ändern, unabhängig von den
> Wochenstunden. Bleiben die Wochenstunden dabei gleich (z. B. 40 h auf 5 Tage → 40 h auf
> 4 Tage), hängt der Bericht seit dem Abschluss-Review #431 (Welle 2) den Zusatz **„auf 4
> Arbeitstage"** an — z. B. „ab 16.03.2026: 40,0 Std/Woche auf 4 Arbeitstage" (Singular
> „auf 1 Arbeitstag"; PDF-Kurzform „auf 4 Tage", `_work_days_suffix`). Die Änderung ist
> damit nicht mehr unsichtbar — der Fallstrick liegt jetzt darin, dass die genannte
> **Wochenstundenzahl selbst unverändert bleibt** (weiterhin „40,0"): Wer nur auf diese
> Zahl schaut und den angehängten Halbsatz überliest, übersieht, dass sich das
> **Tagessoll** dabei trotzdem still verschiebt (8 h/Tag → 10 h/Tag), weil
> `Tagessoll = weekly_hours ÷ work_days_per_week` (§3.1). Verlassen Sie sich beim Prüfen
> einer Änderung deshalb **nicht** auf die Wochenstundenzahl allein, sondern lesen Sie den
> vollständigen Änderungstext bzw. die Tagessoll-Vorschau im Dialog (§ „Wochenstunden
> anpassen…", zeigt Mo–Fr alt→neu).

**Rückrechnung bereits gebuchter Abwesenheiten.** `calculation_service.retarget_absence_hours(db, user, start, end)`
zieht die **gespeicherten `hours`** bereits gebuchter `Absence`-Zeilen im Wirkungsbereich
der Änderung auf das neue Tagessoll des jeweiligen Tages nach — sonst widerspräche das
alte `hours` (z. B. ein Krankentag mit 8 h) dem neuen Tagessoll (4 h) im selben
§16-Beleg. Beispiel: Ein Krankentag am 10.03. trug bislang `hours = 8` (altes Tagessoll).
Nach der Änderung auf 20 h/Woche (4 h/Tag) wird er auf `hours = 4` umgestellt.

⚠️ **Ausgelöst wird das nicht vom Datum, sondern von den Buchungen** (Release-Review
1.17.0; bis dahin klemmte jeder Aufrufer das Fenster selbst auf `[effective_from, heute]`
und feuerte nur bei rückwirkendem Datum). `create_absence` hat keinerlei Zukunftssperre:
genehmigte Urlaubsanträge, Betriebsferien und geplante Fortbildungen werden routinemäßig
im Voraus gebucht — mit `hours` = Tagessoll ZUM Buchungszeitpunkt. Das Soll dieser Tage
folgt einer späteren Wochenstunden-Änderung datumsbasiert automatisch, die gespeicherten
Stunden nicht. Bei `SICK`/`TRAINING` ist das ein direkter Saldo-Fehler (dort sind die
`hours` die Ist-Gutschrift), bei `VACATION`/`PAID_LEAVE`/`OTHER` ein in sich
widersprüchlicher §16-Beleg. Und der REGELFALL des Dialogs ist ein Wirkungsdatum in der
ZUKUNFT („ab dem 1.9. arbeitet sie 20 Stunden") — dort griffe ein „nur rückwirkend"-
Trigger nie.

**Der Wirkungsbereich** kommt aus `calculation_service.retarget_window(db, user, effective_from)`
— DIE eine Stelle dafür, die Anlegen, Löschen und Vorschau gemeinsam nutzen:

* **Start** = `effective_from`.
* **Ende** = Tag VOR der nächsten Änderung mit größerem `effective_from` (was danach
  liegt, gehört bereits einem anderen Vertragswert und darf nicht mit umgeschrieben
  werden).
* Gibt es keine spätere Änderung, ist der Bereich offen und wird praktisch auf die
  **späteste bereits gebuchte Abwesenheit** begrenzt, mindestens aber auf heute bzw. auf
  das Wirkungsdatum selbst (damit das Fenster auch ohne Abwesenheiten einen sinnvollen
  Anzeigewert hat).
* `RetargetWindow.has_absences` (= es existiert eine Abwesenheit ≠ `OVERTIME` im Bereich)
  ist der Auslöser. `OVERTIME` bleibt schon bei der Suche außen vor, damit der Trigger
  nicht für Zeilen feuert, die ohnehin nie angefasst würden.

Bewusst ausgenommen:

* `OVERTIME` — Freizeitausgleich trägt explizit beantragte Stunden, kein abgeleitetes
  Tagessoll.
* `track_hours = False` — dort zählt ausschließlich die Tageszählung.
* Wochenenden, Feiertage und Tage ohne Soll (freier Wochentag im Tagesplan) — sie werden
  übersprungen, nicht auf 0 gesetzt.
* Tage außerhalb des Beschäftigungsfensters (#193).
* Alt-Zeilen ohne Halbtags-Information (`half_day IS NULL`, gebucht vor #205) — für sie
  zählen `get_vacation_account`/`absence_days` die Tage stundenbasiert (`hours ÷ Tagessoll`),
  ein Umschreiben der Stunden würde also den Tage-Verbrauch verschieben und die einzige
  verbliebene Spur des Halbtags löschen.

`half_day` halbiert die Umrechnung, der #146/#394-Sondertagsfaktor (24./31.12.) wird über
`special_days_service.special_day_target_factor` angewandt — dieselbe, **stundenbasierte**
Quelle wie `_day_soll_contribution` (nicht der tagebasierte
`half_special_day_weight`-Helper, der die Urlaubs*tage* gewichtet).
**Die Abwesenheits-TAGE ändern sich dadurch nie** —
Urlaub (und jede tagebasierte Zählung) hängt an `absence_days`/`get_vacation_account`,
nicht an `hours` (§3 BUrlG, Tagesprinzip, s. o.).

Berührt das Fenster ein bereits abgeschlossenes Jahr (`YearCarryover` existiert für das
Folgejahr), wird **nicht** automatisch neu gerechnet — nur eine Warnung zurückgegeben
(`stale_year_closing_warning`, Fix #5). Löschen einer `WorkingHoursChange` rechnet
dasselbe Fenster mit dem dann gültigen Wert zurück (derselbe Helper, jetzt gegen den
vorherigen Wert) und **meldet denselben Jahresabschluss-Hinweis** — mit Warnung `200` +
`{"warning": …}`, ohne Warnung `204` (Muster von `delete_closure` /
`cancel_vacation_request_as_admin`). Mitarbeitende mit individuellem Tagesplan sind seit
#431 **nicht mehr** vom Zurückrechnen ausgenommen: ihr Tagessoll kommt jetzt ebenfalls aus
der Historien-Zeile (`get_schedule_for_date`), eine `WorkingHoursChange` setzt und
verschiebt es also genauso wie bei gleichmäßiger Verteilung. Ändert eine Änderung nur
einen einzelnen Wochentag (z. B. nur den Mittwochswert), überspringt die
Gleichheitsprüfung in `retarget_absence_hours` die übrigen Wochentage von selbst — es
braucht dafür keinen eigenen Wochentagsfilter, nur Mittwochs-Abwesenheiten im Fenster
werden umgerechnet. Die **früheste** Änderung eines Mitarbeiters lässt sich nicht löschen,
solange spätere existieren — sie ist die einzige Stelle, an der der davor gültige Wert
noch steht; ohne sie hätte `retarget_absence_hours` beim Löschen einer späteren Änderung
keinen validen Rückfallwert mehr zum Zurückrechnen.

⚠️ `user.weekly_hours` ist zugleich der aktuelle Vertragswert **und** der Rückfallwert für
alle Tage *vor* der ersten erfassten Änderung — das Feld ist beim Bearbeiten aber nicht
mehr direkt änderbar: `PUT /admin/users/{id}` lehnt `weekly_hours` im Payload mit 400 ab.
Der einzige Schreibweg ist `POST .../working-hours-changes` mit `effective_from` (s. o.);
`POST /admin/users` (Anlegen) darf `weekly_hours` weiterhin setzen — dort gibt es noch
keine Historie, der Startwert muss direkt gesetzt werden können.

Seit #431 gilt dieselbe Sperre für **alle acht** historisierten Felder, ohne Ausnahme:
`weekly_hours`, `use_daily_schedule`, `work_days_per_week` und `hours_monday … hours_friday`.
`PUT /admin/users/{id}` lehnt den Request mit 400 ab, sobald **eines** dieser Felder im
Payload steckt. Bis 1.17.0 lehnte der Stundenverlauf-Endpoint eine Zeile für Mitarbeitende
mit individuellem Tagesplan ab (`use_daily_schedule = true`) — für sie gab es also gar
keine Historie, und die PUT-Sperre machte deshalb eine Ausnahme: `weekly_hours` blieb bei
ihnen direkt editierbar, weil es keinen anderen Schreibweg gab. Seit #431 nimmt der
Stundenverlauf-Endpoint auch ihre Änderungen an (vollständiger Vertrags-Snapshot statt
Einzelfeld), also entfällt die Ausnahme ersatzlos — Tagesplan-Mitarbeitende ändern ihren
Modus, ihre Tageswerte, ihre Arbeitstage und ihre Wochenstunden jetzt genauso über
„Wochenstunden anpassen…" mit Wirkungsdatum wie alle anderen.

Die automatische **Basis-Zeile** vor der allerersten Änderung (sie friert den bis dahin
gültigen Wert ein) datiert auf das Früheste aus `first_work_day`, der ältesten vorhandenen
Buchung (`TimeEntry`/`Absence`) und dem Vortag der Änderung. `first_work_day` allein
genügt nicht — es ist nullable, und ohne die anderen Kandidaten deckte die Basis-Zeile nur
einen einzigen Tag ab.

### TZ-F: Rückwirkende Tagesplan-Änderung (#431)

MA mit individuellem Tagesplan **Mo 8 h · Di 8 h · Mi 8 h · Do 0 · Fr 0** (24 h auf
3 Arbeitstage) hat am Mittwoch, den 04.03.2026, einen ganzen Krankheitstag gebucht
(`hours = 8,00`, Tagessoll an dem Tag zum Buchungszeitpunkt).

Am 15.03.2026 ändert die Praxis **nur den Mittwochswert** auf 4 h (Mo/Di bleiben 8 h,
Do/Fr bleiben 0):

```
Alter Tagesplan (bis 14.03.2026): Mo 8 / Di 8 / Mi 8 / Do 0 / Fr 0 = 24,0 h/Woche
Neuer Tagesplan (ab 15.03.2026):  Mo 8 / Di 8 / Mi 4 / Do 0 / Fr 0 = 20,0 h/Woche
```

Weil der Krankentag am 04.03.2026 **vor** dem Wirkungsdatum liegt, bleibt sein Tagessoll
bei 8 h — die Änderung wirkt hier nicht (das Fenster beginnt am 15.03.2026). Ein zweiter
Krankheitstag am **18.03.2026** (ebenfalls Mittwoch, im Wirkungsbereich) trug bislang
ebenfalls `hours = 8,00`. Nach der Änderung wird **nur er** auf `hours = 4,00`
umgerechnet — ein Montags- oder Dienstags-Krankheitstag im selben Fenster bliebe
unangetastet, weil sich deren Tagessoll (8 h) nicht geändert hat. `retarget_absence_hours`
prüft pro gebuchtem Tag, ob sich **sein** historisch aufgelöstes Tagessoll geändert hat —
ein eigener Wochentagsfilter ist dafür nicht nötig, die bestehende Gleichheitsprüfung
überspringt unveränderte Tage von selbst.

> ⚠️ **Fallstrick — eine Arbeitstage-Verschiebung ändert den Urlaubsverbrauch, nicht immer
> das Tagessoll.** Verschiebt eine Änderung Stunden von einem Wochentag auf einen anderen,
> ohne die Wochensumme zu ändern (z. B. Mo 8 / Di 8 / Mi 8 / Do 0 / Fr 0 → Mo 8 / Di 8 /
> Mi 0 / Do 8 / Fr 0, weiterhin 24 h auf 3 Arbeitstage), bleibt das Tagessoll von Montag
> und Dienstag unverändert. War am (jetzt wegfallenden) Mittwoch bereits ein ganzer
> Urlaubstag gebucht, zählt dieser Tag rückwirkend **nicht mehr als Urlaubsverbrauch** —
> sein Tagessoll ist ab dem Wirkungsdatum 0, und `absence_days`/`get_vacation_account`
> zählen nur Tage mit Tagessoll > 0 (§14 TZ-B/TZ-C). Der bereits gespeicherte
> `Absence.hours`-Wert bleibt dabei unverändert stehen (`retarget_absence_hours`
> überspringt Tage mit neuem Tagessoll 0, statt sie auf 0 zu setzen) — nur der
> **Urlaubsverbrauch** ändert sich, nicht die Stundenzahl. Genau das zeigt die
> „Urlaub {Jahr}: bisher/neu"-Zeile der Vorschau vor dem Speichern.

---

## 15. Worked Example – Minijob (MiLoG-Fixmodus)

MJ-Profil: `track_hours = true`, `use_daily_schedule = true` mit `hours_monday = 5` (alle
übrigen Wochentage `0`, der MA arbeitet nur montags), `milog_working_time_account = true`,
`agreed_monthly_hours = 40`, `use_fixed_monthly_target = true`. Das Monats-Soll ist damit
**immer 40,00 h**, unabhängig davon, wie viele Montage der Kalendermonat hat oder wie die
geplante Stunde tatsächlich genutzt wird.

### 15.1 Feiertag auf einem geplanten Tag → Gutschrift, Soll bleibt

Ein gesetzlicher Feiertag fällt in diesem Monat auf einen geplanten Montag (`hours_monday =
5`). Der MA hat an den übrigen Montagen 33,00 h real erfasst:

```
Monats-Soll (fest)        = 40,00 h                          (agreed_monthly_hours, unverändert)

Feiertag auf geplantem Montag (5,00 h)
  → Ist-Gutschrift        = +5,00 h                          (fixed_month_credit)

Monats-Ist  = Σ Zeiteinträge (33,00 h) + Feiertags-Gutschrift (5,00 h) = 38,00 h
Monatssaldo = 38,00 − 40,00 h                                 = −2,00 h
```

Das feste Soll (40,00 h) ändert sich durch den Feiertag **nicht** — nur das Ist bekommt die
geplanten Stunden gutgeschrieben, statt an diesem Tag 0 h zu zählen.

### 15.2 Unbezahlter Fehltag → Soll-Minderung

An einem anderen geplanten Montag (`hours_monday = 5`) bucht der MA einen unbezahlten
Fehltag (`OTHER`, z. B. „Kind krank", §6.1). An den restlichen geplanten Montagen erfasst er
35,00 h:

```
Monats-Soll (fest)        = 40,00 h
OTHER an geplantem Montag (5,00 h) mindert das Soll:
  Monats-Soll             = 40,00 − 5,00 h                    = 35,00 h    (fixed_month_unpaid_reduction)

Monats-Ist  = Σ Zeiteinträge (35,00 h)                        = 35,00 h    (kein Gutschriftstag, da unbezahlt)
Monatssaldo = 35,00 − 35,00 h                                 = 0,00 h     (saldo-neutral)
```

Der unbezahlte Fehltag verschwindet damit korrekt sowohl aus dem Soll als auch aus dem Ist —
das Konto bleibt neutral, aber der Lohn wird für diesen Tag gekürzt (Reporting, keine
Lohndaten in PraxisZeit).

---

## Quellen im Code

| Funktion | Datei |
|---|---|
| `get_schedule_for_date` (Vertrags-Snapshot, #431), `get_weekly_hours_for_date`, `get_daily_target(_for_date)` | `services/calculation_service.py` |
| `retarget_window`, `retarget_absence_hours` (Rückrechnung gebuchter Abwesenheiten, #415/#431) | `services/calculation_service.py` |
| `get_range_target`/`_actual`, `get_monthly_target` / `_actual` / `_balance` | `services/calculation_service.py` |
| `get_soll_cutoff_date` (#313 Saldo-Stichtag) | `services/calculation_service.py` |
| `get_overtime_account`, `get_overtime_history[_detailed]`, `get_ytd_summary` | `services/calculation_service.py` |
| `get_vacation_account`, `absence_days`, `half_special_day_weight` (#394) | `services/calculation_service.py` |
| `child_sick_cap`, `child_sick_days_used` (#376) | `services/calculation_service.py` |
| `fixed_monthly_target`, `fixed_month_credit`, `fixed_month_unpaid_reduction` (#377 Baustein 2b) | `services/calculation_service.py` |
| `create_year_closing`, `stale_year_closing_warning` | `services/calculation_service.py` |
| `TimeEntry.net_hours` | `models/time_entry.py` |
| Sondertag-Faktoren (`special_day_target_factor`, `vacation_deduction_dates_for_year`) | `services/special_days_service.py` |
| Arbeitszeit-Fenster | `services/work_window_service.py` |
| `hours`-Buchung (Tagessoll/Halbtag/OVERTIME) | `routers/absences.py`, `routers/admin_vacations.py` |
| Betriebsferien-CRUD + Buchung (`_create_closure_absences`) | `routers/company_closures.py` |
| Betriebsferien-Split VACATION↔OVERTIME (#314) | `services/closure_split_service.py` |
| Eigene Abwesenheitsgründe, `BEHAVIOR_TO_ABSENCE_TYPE` (#312/#376) | `models/absence.py` |
| Mindestlohn-Konstante (#377) | `core/minimum_wage.py` |
| Minijob-Warnungen `MILOG_ACCOUNT_50` / `MILOG_SETTLEMENT_DUE` / `MILOG_MONTHLY_EXCEEDED` | `services/milog_service.py` |
| `soll_basis`-Umschalter (Admin-Reports) | `routers/reports.py` |
