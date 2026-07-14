# Design: Minijob-Modus „feste Monatsarbeitszeit" (#377 Baustein 2b)

**Datum:** 2026-07-14
**Status:** Design freigegeben, bereit für Implementierungsplan
**Auslöser:** Kundenreport (Minijob/MiLoG, philvdb-Umfeld) — Feedback zu #377 Baustein 2a
**Bezug:** [[#377]] (MiLoG §2 Abs. 2 Arbeitszeitkonto), CLAUDE.md-Regel „Baustein 2b bewusst offen (= Calc-Umbau, hohes Risiko)"

---

## 1 · Problem

Ein Minijobber hat eine **fest vereinbarte Monatsarbeitszeit** (z. B. 40 h/Monat), die jeden Monat gleich sein soll. PraxisZeit kann heute (1.14.x) nur:

- **Wochenarbeitszeit** eingeben (`User.weekly_hours`, `NOT NULL`). Das Monats-**Soll** ist immer `Σ Tagessoll über die Arbeitstage des Monats` → **schwankt** je nach Wochentagsverteilung (mal 4, mal 5 Montage).
- `agreed_monthly_hours` (Baustein 2a) existiert, steuert aber **nur die MiLoG-50-%-Prüfung**, nicht das Soll.
- Feiertage setzen das Tagessoll auf 0 (bilanzneutral) — es werden **keine** Stunden gutgeschrieben.

Der Kunde will drei Dinge:

1. **Vereinbarte Monatsarbeitszeit direkt eintragen**, die **fix** jeden Monat als Soll gilt.
2. **Individuelle Tagesstunden frei definierbar**, entkoppelt von der Wochenzeit (der Minijobber ist nur für einen Teil regelmäßig da, arbeitet den Rest flexibel → geplante Tagesstunden können deutlich **unter** der Monatszeit liegen). Nur **Plausibilität** (Monatszeit nicht überschreiten), keine harte Sperre.
3. **Feiertag auf einen geplanten Tagesstunden-Tag** → die geplanten Stunden dem **Arbeitszeitkonto gutschreiben** (statt Soll auf 0).

Das ist **Baustein 2b**: das feste Monats-Soll treibt Balance/Überstundenkonto. Ein echter Eingriff ins eingefrorene §16-Calc → deshalb als **eigener opt-in-Modus** nur für MiLoG-Minijob-Konten, der das bestehende Per-Tag-Soll aller anderen MA unberührt (byte-identisch) lässt.

## 2 · Nicht-Ziele / Out of Scope

- Kein Umbau des Soll-Modells für Nicht-Modus-MA (byte-identisch bleiben).
- Kein Lohn-/603-€-Check (keine Lohndaten gespeichert — wie #377).
- Keine automatische Ableitung der Monatszeit aus Tagesstunden (die Tagesstunden sind bewusst < Monatszeit).
- Volle Fehlmonate (ganzer Monat Urlaub/Krank) mit flexiblem Rest-Anteil werden **nicht** vollautomatisch glattgezogen (siehe §5 „Bekannte Grenze").

## 3 · Datenmodell

- **Neues Flag** `User.use_fixed_monthly_target` (`Boolean`, `NOT NULL`, `default False`, `server_default 'false'`). Migration (nächste freie Revision nach 064). Tenant-neutral (User-Feld, RLS über users bereits vorhanden).
- **Soll-Quelle:** das bestehende `User.agreed_monthly_hours` (`Numeric(5,1)`, Baustein 2a). **Pflicht** (`> 0`), wenn `use_fixed_monthly_target = True` — Validierung im User-Schema/Router.
- **Planungsmuster:** die bestehenden `hours_monday…hours_friday` (`use_daily_schedule`). Im Modus = „geplante Anwesenheit", **nicht** Soll-Treiber. Dürfen frei/teilweise gesetzt sein (z. B. nur Mo + Mi).
- **`weekly_hours`** bleibt `NOT NULL` in der DB, wird im Modus **fürs Soll ignoriert**. Kein Schema-Zwang zur Nullable-Migration (Risiko/Aufwand vermeiden). Beim Anlegen im Modus wird ein plausibler Wert gesetzt/abgeleitet (z. B. `agreed_monthly × 3/13` gerundet), rein informativ.

**Vorbedingung:** `use_fixed_monthly_target` ist nur sinnvoll mit `track_hours = True` (ein Konto braucht Soll/Ist) und `milog_working_time_account = True` (Kontext). Das UserForm zeigt die Checkbox nur bei aktivem MiLoG-Konto; das Backend erzwingt `track_hours` (sonst 400).

## 4 · Kern-Calc

### 4.1 Zentrale Helper (Single Source of Truth)

Zwei neue Helper in `calculation_service.py`:

```
fixed_monthly_target(user, year, month) -> Decimal
    # agreed_monthly_hours, ANTEILIG bei Eintritt/Austritt im Monat.
    # Pro-rata-Faktor = (Kalendertage des Beschäftigungsfensters im Monat)
    #                   / (Kalendertage des Monats)
    # Volle Monate im Fenster → voller agreed. Monate ganz außerhalb → 0.
    # (Bewusst Kalendertag-Bruchteil wie die bestehende get_vacation_account-
    #  Pro-rata — einfach, vorhersehbar, unabhängig vom Wochentagsmuster.)

fixed_month_credit(user, year, month, up_to_date=None) -> Decimal
    # BEZAHLTE, entschuldigte Nicht-Arbeitstage schreiben dem Ist die GEPLANTEN
    # Tagesstunden gut. Für jeden Tag im Monat (im Beschäftigungsfenster,
    # ≤ up_to_date), der (a) ein Feiertag ODER (b) eine ganztägige
    #   VACATION- oder PAID_LEAVE-Absence trägt,
    # addiere die GEPLANTE Tagesstundenzahl dieses Wochentags
    # (get_daily_target_for_date im use_daily_schedule-Sinn; 0 an ungeplanten
    #  Tagen), × Sondertags-/Halbtags-Faktor (#394-Analogie).
    # ⚠️ SICK und TRAINING sind hier NICHT enthalten — die werden bereits über
    #    den bestehenden credited_absences-Pfad (get_range_actual, EntgFG/
    #    Fortbildung) dem Ist gutgeschrieben; sie hier erneut zu addieren wäre
    #    eine DOPPELGUTSCHRIFT.
    # KEINE Doppelzählung mit real erfassten TimeEntry-Stunden am selben Tag
    #   (an einem Feiertag/Absence-Tag existiert regulär kein TimeEntry;
    #    falls doch, gewinnt die reale Erfassung — Tag wird NICHT gutgeschrieben).

fixed_month_unpaid_reduction(user, year, month, up_to_date=None) -> Decimal
    # UNBEZAHLTE, entschuldigte Nicht-Arbeitstage MINDERN das feste Monats-Soll
    # (statt Ist gutzuschreiben — es besteht keine Vergütungspflicht). Für jeden
    # Tag mit einer ganztägigen OTHER- oder UNPAID_FREE-Absence (#376) auf einem
    # geplanten Tag: geplante Tagesstunden × Faktor, halbtags × 0,5.
```

Alle drei sind reine Lese-Helper (kein DB-Write).

**Warum paid vs. unpaid getrennt:** ein bezahlter Fehltag (Feiertag/Urlaub/bez. Freistellung/Krank) erfüllt die vergütete Monatspflicht → Ist+. Ein *unbezahlter* Fehltag (OTHER = unbezahlt entschuldigt, UNPAID_FREE = „Kind krank" unbezahlt) verringert die vergütete Pflicht → Soll−. Beides hält das Konto bei einem fixen Monats-Soll fair; nur Ist+ für alles würde unbezahlte Tage fälschlich vergüten, nur Soll− für alles würde bezahlte Feiertage nicht als geleistet zeigen.

### 4.2 Einhängepunkte (die drei parallelen Schleifen)

Der Modus wird an **allen** Stellen abgezweigt, die Soll/Ist akkumulieren — genau EIN Branch je Stelle:

| Funktion | Soll-Seite | Ist-Seite |
|----------|-----------|-----------|
| `get_range_target` / `get_monthly_target` | `if user.use_fixed_monthly_target: Σ (fixed_monthly_target(...) − fixed_month_unpaid_reduction(...))` über die Monate im Range, statt Per-Tag-Summe | — |
| `get_range_actual` / `get_monthly_actual` | — | `+ fixed_month_credit(...)` zusätzlich zur bestehenden TRAINING/SICK-Gutschrift |
| `get_overtime_account` (Inline-Monatsloop) | im Monatsloop: `monthly_target = fixed_monthly_target(...) − fixed_month_unpaid_reduction(...)` statt der Inline-Per-Tag-Summe | `+ fixed_month_credit(...)` zum `actual_by_month` |
| `get_ytd_summary` (Monats-/Tagesloop) | dito | dito |

**⚠️ Parallelpfad-Disziplin (Lektion aus #394/1.14.3):** Diese vier Funktionen bauen die Soll/Ist-Akkumulation **je eigenständig** nach. Der Modus MUSS in allen greifen, sonst divergiert genau eine Anzeige. Deshalb: die Verzweigung läuft ausschließlich über die zwei zentralen Helper — kein Inline-Nachbau der Fix-Logik. Ein gemeinsamer Konsistenz-Test (get_overtime_account ↔ Σ(get_monthly_target) ↔ get_ytd_summary) sichert das ab.

### 4.3 Abwesenheiten im Modus

Der Per-Tag-`absence_half_map`-Soll-Abzug (VACATION/OTHER/PAID_LEAVE → Soll des Tages 0) wird für Modus-MA **übersprungen** — das Monats-Soll ist fix. Stattdessen:

- **Bezahlt entschuldigt** (Feiertag / VACATION / PAID_LEAVE): `fixed_month_credit` schreibt geplante Stunden dem Ist gut (§5).
- **Bezahlt, schon gutgeschrieben** (SICK / TRAINING): unverändert über `credited_absences` — NICHT in `fixed_month_credit` (Doppelgutschrift-Guard).
- **Unbezahlt entschuldigt** (OTHER / UNPAID_FREE): `fixed_month_unpaid_reduction` mindert das feste Monats-Soll.

Für alle Nicht-Modus-MA bleibt der `absence_half_map`-Abzug unverändert (byte-identisch).

## 5 · Ist-Gutschrift (symmetrisch)

Feiertag **und** Krank **und** Urlaub (und Fortbildung) auf einem **geplanten** Tagesstunden-Tag schreiben die geplanten Tagesstunden dieses Wochentags dem Ist gut (Konto steigt, als wäre gearbeitet worden). Krank/Fortbildung tun das heute schon über die `credited_absences`; im Modus kommen **Feiertag** (Kundenwunsch) und **Urlaub** über `fixed_month_credit` dazu.

- Gutschrift-Basis = **geplante Tagesstunden** des Wochentags (`hours_<wd>`), 0 an ungeplanten Tagen, Halbtag × 0,5.
- Urlaub bleibt zusätzlich **tagebasiert** im Urlaubskonto (`get_vacation_account`, Tage-Ledger) — die Stunden-Gutschrift ist ein separates Ledger (Konto-Stunden). Keine Doppelbegünstigung: Tage ≠ Stunden.

**⚠️ Bekannte Grenze (dokumentiert, kein Blocker):** Liegt die Summe der geplanten Tagesstunden **unter** der Monatszeit (der flexible Rest), deckt die Gutschrift bei einem *ganzen* Fehlmonat nur den geplanten Anteil — der flexible Rest bliebe als Konto-Defizit. Für Einzel-Fehltage (Regelfall) korrekt. Volle Fehlmonate = Arbeitgeber-Handanpassung (manuelle Überstunden-/Carryover-Korrektur). Wird im Handbuch vermerkt.

## 6 · Plausibilität + #377-Harmonisierung

- **Weiche Warnung** (neuer transienter Warncode `MILOG_MONTHLY_EXCEEDED`, nur im Response, nicht persistiert): wenn Monats-**Ist** (inkl. Gutschriften) > vereinbarte Monatszeit → Warnung über die bestehende `AbsenceResponse.warnings`/`OvertimeAccount.warnings`-Schiene + `showArbzgWarnings`-Frontend. **NIE blockierend.** Frontend-Warncode-Liste + `collectAbsenceWarnings` mitpflegen (wie #376/#377). Push-Flächen: `clock_out` / `create_time_entry` / `update_time_entry`; Pull-Flächen: `dashboard.get_overtime_account` (self) + `admin_users.users_overview` (`is_current_year`-gated) — dieselben Flächen wie die #377-Warnungen.
- **#377-Harmonisierung (Nebeneffekt, kein Code-Umbau):** im Modus ist `target == agreed` (flach, pro-rata). Das #377-`settlement_aging` (actual − target) und die 50-%-Prüfung rechnen dann automatisch gegen dieselbe Basis; der in CLAUDE.md verankerte Konflikt „agreed vs. getrimmtes target → Phantom-Defizit" entfällt für Modus-MA (Soll ist ja nicht mehr durch Feiertage/Urlaub getrimmt, sondern fix + Gutschrift auf der Ist-Seite). **`settlement_aging` bleibt target-basiert** (liest `get_overtime_history_detailed`, dessen target im Modus = fixed) — kein Sonderpfad nötig. Für Nicht-Modus-MA gilt die #377-Regel unverändert.

## 7 · UI

- **UserForm** (`frontend/src/pages/admin/users/UserForm.tsx`): neue Checkbox „Feste Monatsarbeitszeit" — sichtbar nur bei aktivem `milog_working_time_account`. An:
  - blendet das Wochenzeit-Feld aus (bzw. read-only informativ),
  - macht `agreed_monthly_hours` zur Pflicht (`> 0`),
  - beschriftet die Tagesstunden-Matrix als „geplante Anwesenheit (für Feiertags-/Fehltags-Gutschrift)".
- **`UserListResponse`** trägt `use_fixed_monthly_target` mit (sonst Edit-Reset — vgl. der #376/#377-Latenz-Bug).
- **Dashboard / Benutzerübersicht:** zeigen für Modus-MA das feste Monats-Soll (statt der schwankenden Per-Tag-Summe). `systemStore`/Badges wie bei #377.
- **In-App-Hilfe/Handbuch** (`DocViewer.tsx` + `docs/handbuch/*`): den Modus + die Fehlmonat-Grenze dokumentieren (beides pflegen — CLAUDE.md-Regel).

## 8 · Randfälle

- **Modus AUS → byte-identisch** zum heutigen Verhalten (Kontroll-Tests).
- **Eintritt/Austritt im Monat:** Soll = `agreed × Kalendertag-Bruchteil` (§4.1). Ist-Gutschrift nur für in-window-Tage.
- **`agreed_monthly_hours` NULL bei aktivem Flag:** 400 beim Speichern (Pflicht-Validierung); defensiv im Calc: Flag ohne agreed → wie Modus AUS behandeln (kein Crash).
- **Halbtags-Sondertag (24./31.12., #394):** die Gutschrift nutzt `get_daily_target_for_date` × Sondertags-/Halbtags-Faktor konsistent (der `half_special_day_weight`-Gedanke greift analog; Feiertags-Gutschrift an einem Halbtags-Sondertag = 0,5 × geplante Stunden). In den Tests mit abdecken.
- **`use_daily_schedule = False` im Modus:** dann gibt es kein Planungsmuster → Gutschrift-Basis 0 (Feiertag/Urlaub schreiben nichts gut, Soll bleibt fix). UI weist darauf hin, dass für die Gutschrift Tagesstunden gesetzt sein müssen.

## 9 · Tests

- **Byte-Identität:** Nicht-Modus-MA — `get_monthly_target`/`get_overtime_account`/`get_ytd_summary`/`get_range_actual` vor/nach unverändert (dedizierte Vergleichstests).
- **Festes Soll:** ein Modus-MA hat in Monaten mit 4 vs. 5 Montagen dasselbe Monats-Soll (= agreed).
- **Gutschrift (bezahlt):** Feiertag / VACATION / PAID_LEAVE auf geplantem Tag → Ist + geplante Stunden; auf ungeplantem Tag → 0. Halbtag → 0,5. Halbtags-Sondertag → 0,5 × geplant.
- **Keine Doppelgutschrift:** SICK / TRAINING auf geplantem Tag → genau EINE Gutschrift (über `credited_absences`), NICHT zusätzlich über `fixed_month_credit`.
- **Unbezahlt mindert Soll:** OTHER / UNPAID_FREE auf geplantem Tag → festes Monats-Soll − geplante Stunden (kein Ist+).
- **Warnung:** Monats-Ist > agreed → `MILOG_MONTHLY_EXCEEDED` (weich); knapp darunter → keine.
- **Pro-rata:** Eintritt zum 15. → halbes (kalendertag-anteiliges) Soll im Startmonat; Ist-Gutschrift nur ab Eintritt.
- **Konsistenz:** `get_overtime_account(bis M)` == Σ(`get_monthly_target` − `get_monthly_actual` + credits) über die Monate == `get_ytd_summary`-Balance (der Parallelpfad-Test).
- **#377-Kohärenz:** `settlement_aging` + 50-%-Prüfung im Modus liefern konsistente Werte gegen das feste target (keine Phantom-Defizite durch Feiertage/Urlaub).

## 10 · Risiko & Rollout

- **Frozen-Calc-Risiko:** mittel-hoch (drei parallele Akkumulations-Schleifen). Mitigation: zwei zentrale Helper + Parallelpfad-Konsistenz-Test + Byte-Identitäts-Tests für Nicht-Modus.
- **Opt-in, additiv:** eine Migration (Flag), keine Datenmigration bestehender MA (alle starten mit Flag = false → unverändert).
- **Multi-Agent-Review vor Release** (wie 1.14.3): gezielt „welche ANDEREN Pfade lesen Soll/Ist?" prüfen.
- Auslieferung als **eigenes MINOR** (neues Feature), nicht als Patch.
