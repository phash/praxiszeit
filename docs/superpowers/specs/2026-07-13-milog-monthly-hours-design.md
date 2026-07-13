# Design: #377 Baustein 2a — vereinbarte Monatsarbeitszeit (MiLoG-Konto)

**Datum:** 2026-07-13
**Issue:** [#377](https://github.com/phash/praxiszeit/issues/377) — „Minijob mit Monatsstunden" (Baustein 2)
**Typ:** Feature (Backend-Modell + MiLoG-Lese-Schicht + Frontend). **Calc bleibt eingefroren.**

## Kontext

#377 Baustein 1+3 ist in **v1.14.0** ausgeliefert: § 2 Abs. 2 MiLoG 50-%-Prüfung,
12-Monats-Aging, datumsabhängiger Mindestlohn. **Offen: Baustein 2** — die direkte
Eingabe einer vereinbarten **Monats**-Arbeitszeit statt der aus `weekly_hours`
abgeleiteten (`weekly × 13/3`).

Kundenfall: Minijobberin mit **fester Monatsvereinbarung 33 h/Monat** auf einem
Arbeitszeitkonto („sonstige flexible Arbeitszeitregelung", § 2 Abs. 2 MiLoG). Die
aktuell flach aus den Wochenstunden abgeleitete Monatszeit trifft das nicht exakt.

**Scope-Entscheidung (mit User):** die eingegebene Monatszeit fixt **beide**
MiLoG-Prüfungen konsistent — die 50-%-Prüfung **und** das 12-Monats-Aging (nicht
nur die 50-%-Prüfung). **2b** (Monats-Soll treibt Balance/Überstundenkonto) bleibt
außen vor.

## Ausgangslage (Code)

- `milog_service.agreed_monthly_hours(db, user, ref_date)` = `weekly × 13/3`
  (FLACH). Der Kommentar sagt bereits: „Baustein 2 ersetzt das später durch eine
  direkt vereinbarte Monatszahl." → **der eine vorbereitete Hook**.
- `milog_service.milog_50_check` nutzt `agreed_monthly_hours` (→ profitiert
  automatisch).
- `milog_service.settlement_aging` FIFO-t die Monats-Deltas `actual − target`, wo
  `target` der **werktagsbasierte Soll** aus `get_overtime_history_detailed` ist.
  Das ist NICHT die vereinbarte Monatszeit → für ein Arbeitszeitkonto inkonsistent
  zur 50-%-Prüfung.
- `weekly_hours` treibt den regulären Soll an ~25 Stellen in
  `calculation_service` (auditiert, **wird NICHT angefasst**).
- CLAUDE.md-Regel: neue User-Felder MÜSSEN in `UserListResponse` + `UserResponse`
  stehen, sonst Edit-Reset (#376/#377 waren latente Bugs).

## Lösung

### 1. Modell + Migration

- `User.agreed_monthly_hours: float | None` (nullable, Default `NULL`).
  `NULL` = Verhalten wie bisher (aus `weekly_hours` abgeleitet).
- Additive Alembic-Migration (nächste Revision nach `062_milog_flag`), nur
  `add_column`. `users` ist bereits tenant-scoped (RLS + F-026) → keine
  Policy-Änderung. up→down→up auf Wegwerf-PG 18 verifizieren.

### 2. `milog_service` (reine Lese-Schicht — Calc eingefroren)

- **`agreed_monthly_hours(db, user, ref_date)`**: wenn
  `user.agreed_monthly_hours is not None` → `Decimal(str(user.agreed_monthly_hours))`,
  sonst `weekly × 13/3` (unverändert). Damit nutzt `milog_50_check` automatisch
  die echte Monatszahl.
- **`settlement_aging`**: die Monats-Delta-Basis wechselt von `actual − target`
  (Soll) auf **`actual − agreed_monthly_hours(db, user, date(y, m, 1))`**. `detailed`
  liefert weiter `.actual` je Monat; der `.target` wird für die Delta-Bildung nicht
  mehr genutzt. Seed (letzter `YearCarryover`), Defizit-Overhang, FIFO,
  `overdue`/`incomplete` bleiben unverändert. Wirkt für **alle** Konto-MA (§ 2
  Abs. 2: „eingestellte Stunden" = Ist über der **vereinbarten** Zeit) — im
  Default (`agreed = weekly × 13/3`) ≈ gleich, exakt bei abweichender Monatszahl.

### 3. Frontend (`UserForm.tsx`)

- Feld **„Vereinbarte Monatsarbeitszeit (h)"** — nur sichtbar, wenn
  `milog_working_time_account` an ist (direkt im/neben dem Arbeitszeitkonto-Block).
  `type=number`, `step=0.5`, `min=0`; leer = `null` (= aus Wochenstunden). Info:
  „Überschreibt die aus den Wochenstunden abgeleitete Monatszeit für die
  MiLoG-Prüfungen (50 % + 12-Monats-Ausgleich). Leer = automatisch aus den
  Wochenstunden."
- Prefill aus `editUser.agreed_monthly_hours`; im Payload mitsenden (echtes
  User-Feld, anders als der Carryover — kein separater Endpoint).

### 4. Schemas

- `agreed_monthly_hours: float | None` in `UserCreate`, `UserUpdate`,
  **`UserResponse`** UND **`UserListResponse`** (Edit-Reset-Falle). `float`, nicht
  `Decimal` (Response-Schema-Regel). Validierung: `>= 0` (kein Cap; realistisch
  klein, aber keine künstliche Grenze). `/system/info` unberührt (Leak-Guard-Test
  `test_deployment_mode.py` bleibt grün — kein neues Leak).

### 5. Tests

- `test_milog.py`:
  - `agreed_monthly_hours`: gesetzt → exakt diese Zahl; `None` → `weekly × 13/3`.
  - `milog_50_check` mit expliziter Monatszahl (z. B. 33 → Cap 16,5).
  - `settlement_aging` mit expliziter Monatszahl (Delta gegen 33, nicht gegen Soll).
  - **Bestehende `settlement_aging`-Tests umstellen:** die Delta-Basis ist jetzt
    `agreed`, nicht `target`. Testnutzer bekommen ein explizites
    `agreed_monthly_hours` (oder passende `weekly_hours`), sodass `agreed` eine
    runde Zahl ist und die erwarteten FIFO-Ergebnisse erhalten bleiben. Die `_MO`-
    Fixtures behalten `.actual`; `.target` wird für die MiLoG-Deltas irrelevant.
- `test_user_schema` / `admin_users`: `agreed_monthly_hours` round-trip (Create →
  List → Edit, kein Reset).
- Migration up→down→up auf Wegwerf-PG 18.
- Vitest (`UserForm.test.tsx`): Feld sichtbar bei aktivem Flag, prefillt, wird im
  User-Payload gesendet.

## Bewusst NICHT dabei (YAGNI)

- **2b:** kein Monats-Soll, das Balance/Überstundenkonto/Journal/Export treibt —
  der auditierte per-Tag-Soll bleibt unangetastet.
- Keine Lohndaten, kein 603-€-Grenzcheck (DSGVO-Zweckbindung; Warnung bleibt
  „sofern zur Mindestlohnhöhe vergütet").
- **Keine** Umrechnung `weekly_hours ↔ agreed_monthly_hours` — beide bleiben
  unabhängig; `weekly_hours` treibt weiter das reguläre Soll, `agreed_monthly_hours`
  nur die MiLoG-Prüfungen.

## Risiko

MiLoG-Lese-Schicht only, Calc eingefroren, opt-in (nur Konto-MA). Einzige
Verhaltensänderung für Bestands-Konto-MA: `settlement_aging` jetzt agreed- statt
Soll-basiert — im Default ≈ gleich, korrekter bei abweichender Monatszahl; MiLoG
ist Beta. Adversariale Multi-Agent-Review wie bei #382/#375/#383.

## Betroffene Dateien

- `backend/app/models/user.py` (+ Feld), neue `alembic/versions/…_agreed_monthly_hours.py`.
- `backend/app/services/milog_service.py` (`agreed_monthly_hours`, `settlement_aging`).
- `backend/app/schemas/user.py` (Create/Update/Response/ListResponse).
- `backend/app/routers/admin_users.py` (falls Feld dort explizit gemappt wird).
- `frontend/src/pages/admin/users/UserForm.tsx` (+ Feld), `frontend/src/types/user.ts`.
- `backend/tests/test_milog.py` (+ neue, bestehende Aging-Tests umgestellt),
  `frontend/src/pages/admin/users/UserForm.test.tsx`.
- Doku: `docs/handbuch/HANDBUCH-ADMIN.md` (MiLoG-Abschnitt) + `DocViewer.tsx` synchron.
