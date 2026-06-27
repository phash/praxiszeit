# #313 — Monatssaldo bis zum letzten abgeschlossenen Arbeitstag

**Status:** approved 2026-06-27 · **Branch:** `feat/issue-313-saldo-prev-workday`

Der Monatssaldo startet am Monatsersten heute mit dem vollen Monats-Soll als
Minus und arbeitet sich bis Monatsende auf 0/Plus. Stattdessen soll das **Soll
nur bis zum letzten abgeschlossenen Arbeitstag** gezählt werden — kein
Monatsanfangs-Minus mehr.

## Kernidee — ein einziger Stichtag (cutoff)

`get_soll_cutoff_date(db, user, today=None) -> date`:
- `today` = der heutige Arbeitstag, **wenn** heute ein **ausgestempelter**
  Zeiteintrag existiert (`TimeEntry.date == today AND end_time IS NOT NULL`),
  sonst **gestern** (`today - 1 Tag`).

Da vergangene Monate ausschließlich Tage **vor** dem Stichtag enthalten, trimmt
ein simples `if d > cutoff: skip` **nur** den laufenden (und zukünftige) Monat —
abgeschlossene Monate bleiben voll. Ein einziger Stichtag, durch alle Summen
gefädelt, ist daher korrekt für Monatssumme **und** kumuliertes Konto.

## Signatur-Erweiterungen (alle additiv, Default = heutiges Verhalten)

- `get_monthly_target(db, user, year, month, up_to_date=None)` — `if up_to_date and d > up_to_date: continue`.
- `get_monthly_actual(db, user, year, month, up_to_date=None)` — Einträge/credited nur `date <= up_to_date`.
- `get_monthly_balance(db, user, year, month, up_to_date=None)` — reicht durch.
- `get_overtime_account(db, user, up_to_year, up_to_month, cutoff_date=None)` — Soll-Loop `if cutoff_date and d > cutoff_date: continue`; Ist-Aggregation `if cutoff_date and e.date > cutoff_date: continue` (entries + credited).
- `get_ytd_summary(db, user, year, cutoff_date=None)` — laufender Monat getrimmt.
- `get_overtime_history(...)` — der **letzte** (laufende) Monatsbalken nutzt denselben Stichtag, damit Chart und Saldo-Karte konsistent sind.

**`Default None ⇒ unverändert`** → bestehende Tests (u. a. `test_overtime_history_matches_account`) bleiben grün; Aufrufer opten ein.

## Aufrufer

- **Dashboard (MA)** `dashboard.py`: Monats-Soll/Ist-Karte, Überstundenkonto, YTD → Stichtag.
- **Admin** `admin_users.py` users-overview (Soll/Ist/YTD je MA) + Admin-Dashboard-Team → Stichtag.
- **Reports/Export** `reports.py`: **umschaltbar** per Query-Param `soll_basis=bis_heute|monatsende` (Default `bis_heute`); `monatsende` ⇒ `cutoff=None` (voller Monat). Für abgeschlossene Monate sind beide identisch.

## Tests (TDD)
- `get_soll_cutoff_date`: heute ausgestempelt ⇒ heute; nicht ⇒ gestern; Monatsanfang ohne Eintrag ⇒ vor Monatsbeginn.
- `get_monthly_target/actual` mit `up_to_date`: trimmt laufenden Monat, voller vergangener Monat, 0 für Zukunft.
- `get_overtime_account` mit `cutoff_date`: kein Monatsanfangs-Minus; vergangene Monate unverändert; `None` = altes Verhalten (Regression).
- Report-Toggle `bis_heute` vs `monatsende`.
- Danach **arbzg-compliance-auditor** über die gesamte Änderung (Soll/Überstunden = §16-relevant), inkl. Konsistenz Chart ↔ Saldo.

## Nicht-Ziele
Keine Änderung an gespeicherten Werten (Jahresabschluss/Carryover bleiben Monatsende-basiert). Reine Berechnungs-/Anzeige-Schicht.
