# Design: #204 Item 1 — users_overview Preload (Holidays + WHChanges)

**Datum:** 2026-07-13
**Issue:** [#204](https://github.com/phash/praxiszeit/issues/204) — Perf O(N)/Bulk-Queries in `users-overview`
**Typ:** Perf-Refactor am **auditierten Calc** — Ergebnisse MÜSSEN byte-identisch bleiben.

## Kontext / Stand

`GET /api/admin/users-overview` (`admin_users.users_overview`) ruft **pro User**
`get_vacation_account` + `get_soll_cutoff_date` + `get_ytd_summary` (+ bei
Konto-MA `get_overtime_history_detailed`, + bei Tenant-mit-Kind-krank
`child_sick_days_used`). Jede dieser Funktionen queriet ihre eigenen
`PublicHoliday`- und `WorkingHoursChange`-Zeilen → **O(N × ~9 Queries)**.

Bereits gefixt: #204 Item 2 (`_create_closure_absences` bulk preload) + Item 3
(`list_closures` gehoisted) + der child_sick-N+1 (Settings/Join) in #382. **Offen:
Item 1** — die per-User-Wiederhol-Queries in den Calc-Helfern.

**Scope-Entscheid (mit User):** GEZIELT — nur `PublicHoliday` (tenant+year) und
`WorkingHoursChange` (alle User) einmal vorladen und via **optionale** Parameter
durchreichen. `Absence`/`TimeEntry` bleiben per-User (inhärent). **Der auditierte
Calc bleibt semantisch eingefroren** — nur Query-Vermeidung, keine
Ergebnis-Änderung.

## Ausgangslage (verifizierte Call-Graph-Map)

Alle Zeilen `backend/app/services/calculation_service.py`.

- **`get_weekly_hours_for_date`** (L13) hat bereits `wh_changes: Optional[List] = None`
  (In-Memory-Scan bei Vorgabe, sonst DB-Query L43) — der **Präzedenzfall**.
- **`get_vacation_account`** (L1036): `PublicHoliday` ganzes Jahr (L1173, gefüttert
  in `vacation_deduction_dates_for_year` L1178); `WorkingHoursChange` **per-Urlaubs-
  Absence-N+1** (L1148 → `get_weekly_hours_for_date`) + per-Abzugstag (L1222, ≤2×).
  Nimmt heute KEIN `wh_changes`.
- **`get_ytd_summary`** (L862): `PublicHoliday` Range (L898, ⊆ Jahr); `WorkingHoursChange`
  einmal (L919) → bereits in `_day_soll_contribution` (L211, hat `wh_changes`)
  durchgereicht.
- **`get_soll_cutoff_date`** (L247): NUR `TimeEntry` (L257) — kein Holiday/WHChange,
  **kein Preload nötig**.
- **`child_sick_days_used`** (L1015) → `absence_days` (L983): `get_weekly_hours_for_date`
  **per-Absence-N+1** (L998), kein `wh_changes`.
- **milog `get_overtime_history_detailed`** (L681): `PublicHoliday` L773 (Range kann
  **multi-year** sein), `WorkingHoursChange` L779 → **außerhalb dieses Scopes** (nur
  Konto-MA + multi-year-Holiday-Range, das Jahres-Set greift nicht).

**Korrektheits-Note:** Holidays werden überall NUR als Membership-Set konsumiert
(`d in holiday_dates`, `d` im eigenen `[start,end]`). Ein (tenant, year)-Set ist
für `get_vacation_account` (ganzes Jahr = exakt) und `get_ytd_summary` (Range ⊆
Jahr = deckungsgleicher Superset) byte-identisch. Die `wh_changes`-Liste pro User
= genau das, was L43/L1148/L998 sonst querien würden.

## Lösung

### Router (`admin_users.users_overview`) — Preload vor der Schleife

```
_holidays = {h.date for h in db.query(PublicHoliday).filter(
    PublicHoliday.tenant_id == current_user.tenant_id,   # F-026
    PublicHoliday.year == year,
).all()}
_wh_rows = db.query(WorkingHoursChange).filter(
    WorkingHoursChange.tenant_id == current_user.tenant_id,  # F-026
).order_by(WorkingHoursChange.effective_from).all()
_wh_by_user: dict = {}
for c in _wh_rows:
    _wh_by_user.setdefault(c.user_id, []).append(c)
```

In der Schleife pro `u`: `_uwh = _wh_by_user.get(u.id, [])` und an die Calls
durchreichen (`holidays=_holidays, wh_changes=_uwh`).

### Calc-Signaturen (alle neuen Params **optional, Default `None`** → Bestandsaufrufer identisch)

- **`get_vacation_account(db, user, year, holidays=None, wh_changes=None)`**
  - Wenn `holidays is not None`: L1173-Query überspringen, `holidays` als
    `holiday_dates_year` nutzen (weiter in `vacation_deduction_dates_for_year`).
  - `wh_changes` in die `get_weekly_hours_for_date`-Calls L1148 + L1222 reichen.
- **`get_ytd_summary(db, user, year=None, cutoff_date=None, holidays=None, wh_changes=None)`**
  - `holidays` statt L898-Query (Range ⊆ Jahr, Superset ok).
  - `wh_changes` statt L919-Query (dieselbe Liste, weiter in `_day_soll_contribution`).
- **`absence_days(db, user, absences, wh_changes=None)`** + **`child_sick_days_used(db, user, year, wh_changes=None)`**
  - `wh_changes` in `get_weekly_hours_for_date` L998 reichen; `child_sick_days_used`
    gibt seinen Param an `absence_days` weiter.

**`_day_soll_contribution`, `get_weekly_hours_for_date`** — keine Signatur-Änderung
(haben `wh_changes` bereits).

### Backend-Verhalten

Keine Migration, keine Schema-/Response-Änderung. Reine Query-Reduktion; der
`response_model=List[AdminUserOverview]` bleibt identisch. F-026 (tenant-scope) bei
beiden Preload-Queries.

## Tests

1. **Byte-identisch (der Kern):** je ein Test, der `get_vacation_account` und
   `get_ytd_summary` für denselben User einmal MIT `holidays=`/`wh_changes=` und
   einmal OHNE aufruft und **exakt gleiche Dicts** asserted — mit nicht-trivialen
   Daten (Urlaub, Feiertag im Zeitraum, ein `WorkingHoursChange` mitten im Jahr,
   24./31.12.-Abzugstag). Analog für `absence_days`/`child_sick_days_used`.
2. **`users_overview`-Integration:** ein Test mit ≥2 Usern (einer mit
   WHChange/Urlaub) → Response gleich wie zuvor (bestehende Overview-Tests bleiben
   grün) + optional Query-Count-Assertion (Preload greift).
3. Bestehende Calc-Tests (Default-None-Pfad) bleiben unverändert grün.

## Bewusst NICHT dabei (YAGNI)

- **milog `get_overtime_history_detailed`** (multi-year Holiday-Range, nur
  Konto-MA) — separat, falls je nötig.
- Keine `Absence`/`TimeEntry`-Bulk-Vorladung (inhärent per-User; wäre die „Voll"-
  Variante mit tieferem Calc-Eingriff).
- Keine Pagination/Cache des Endpoints.

## Betroffene Dateien

- `backend/app/routers/admin_users.py` (Preload + Durchreichen).
- `backend/app/services/calculation_service.py` (`get_vacation_account`,
  `get_ytd_summary`, `absence_days`, `child_sick_days_used` — optionale Params).
- `backend/tests/` (neue Byte-identisch-Tests; z. B. `test_calc_preload.py`).

## Risiko

Gering-mittel: berührt den auditierten Calc, aber nur Query-Vermeidung hinter
Default-None-Params; Byte-identisch-Tests + volle Suite + adversariale Review
sichern ab. Kein Verhaltenswechsel für Bestandsaufrufer.
