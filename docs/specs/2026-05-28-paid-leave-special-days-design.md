# Spec: Bezahlte Freistellung + konfigurierbare Sondertage (24./31.12.)

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #145, #146

---

## Überblick

Zwei eng gekoppelte Feedback-Punkte teilen denselben Mechanismus und werden gemeinsam spezifiziert:

- **#145**: Bei Betriebsferien wählbar, ob die Tage als **Urlaub** (Urlaubsabzug) oder als **bezahlte Freistellung** (kein Abzug, wie Feiertag) gelten.
- **#146**: Für 24.12. und 31.12. konfigurierbar, ob sie **voller Arbeitstag**, **halber Arbeitstag** oder **frei** sind — und bei „frei" dieselbe Urlaub-vs-Freistellung-Wahl.

Gemeinsames Fundament: ein neuer Abwesenheitstyp `PAID_LEAVE` („Bezahlte Freistellung"). Grundlage: `feedback/feedback_01.txt`, Punkte 6 und 7.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich **bei Betriebsferien und an 24./31.12. wählen, ob freie Tage Urlaub kosten oder bezahlte Freistellung sind**, damit **das Urlaubskonto der MA korrekt geführt wird**.

- [ ] **REQ-1**: Neuer Abwesenheitstyp `PAID_LEAVE`: reduziert die Soll-Zeit auf 0, **kein** Urlaubsabzug, **keine** Auswirkung aufs Überstundenkonto (wie ein Feiertag), als bezahlt geführt.
- [ ] **REQ-2** (#145): Betriebsferien haben ein Flag `counts_as_vacation` (Default `true` = bisheriges Verhalten). Bei `false` werden `PAID_LEAVE`- statt `VACATION`-Absences erzeugt.
- [ ] **REQ-3** (#146): Für 24.12. und 31.12. (separat einstellbar) Modus `working_day | half_day | free`.
  - `half_day`: Soll = halbe Tagessollzeit.
  - `free`: Urlaub **oder** bezahlte Freistellung (nutzt `PAID_LEAVE`).
- [ ] **REQ-4**: Urlaubskonto-Berichte weisen `PAID_LEAVE` getrennt von Urlaub aus.
- [ ] **REQ-5**: Default-Verhalten 24./31.12. = `working_day` (abwärtskompatibel).

### Nicht-funktionale Anforderungen

- [ ] Sicherheit: Admin-only; tenant-scoped (F-026).
- [ ] Korrektheit: Urlaubsbudget bei `counts_as_vacation=false` unverändert; Soll der freien Tage = 0 (bzw. halbe bei `half_day`).
- [ ] Konsistenz: Absence-Typ-Matrix in `docs/BACKEND-ARCHITEKTUR.md` + `models/absence.py`-Docstring aktualisieren.

### Out of Scope

- Andere Feiertage halbtags (separat ggf. später).
- Rückwirkende Umbuchung bereits verbuchter Vorjahres-Betriebsferien.

---

## Design

### Grundlagen (verifiziert)

- `company_closures.py:152` erzeugt heute hart `AbsenceType.VACATION`.
- `models/absence.py:9-33` — `AbsenceType`: VACATION/SICK/TRAINING/OVERTIME/OTHER. Semantik laut Docstring:
  - **VACATION**: Soll↓, Ist=0, **Urlaubsbudget↓**.
  - **OTHER**: Soll↓, Ist=0, balance-neutral, **explizit UNBEZAHLT**.
  - → Es fehlt eine **bezahlte** Freistellung ohne Urlaubsabzug.
- 24./31.12. heute normale Arbeitstage (kein Sonderfall); Soll-Berechnung überspringt Feiertage + Absences in `calculation_service.get_monthly_target`.

### PAID_LEAVE — Rechen-Semantik

Identische Soll/Ist/Balance-Mechanik wie `OTHER` (Soll reduziert, Ist 0, balance-neutral, kein Urlaubsabzug), aber als **eigene, bezahlte Reporting-Kategorie**. In `calculation_service.get_monthly_target`/`get_monthly_actual` analog OTHER behandeln; in Urlaubskonto-Auswertungen NICHT als Urlaub zählen.

### Datenbank

```sql
-- neuer Enum-Wert
ALTER TYPE absencetype ADD VALUE 'paid_leave';   -- bzw. via Alembic-konformes Vorgehen

-- #145: Closure-Flag
ALTER TABLE company_closures ADD COLUMN counts_as_vacation BOOLEAN NOT NULL DEFAULT true;

-- #146: Sondertags-Einstellungen über system_setting (keine neue Tabelle):
--   special_day_dec24_mode  ∈ {working_day, half_day, free}
--   special_day_dec24_vacation  (bool, nur bei free)
--   special_day_dec31_mode, special_day_dec31_vacation
```

> Hinweis Enum: das Hinzufügen eines Enum-Werts in Postgres + SQLite-Testsuite sorgfältig migrieren (ggf. `ALTER TYPE ... ADD VALUE` außerhalb Transaktionsblock; SQLite nutzt String-Enum). Migrationen ≤ 32 Zeichen Revision-ID, auf Host erstellen + committen vor Container-Rebuild.

**Migrationen:**
- `..._add_paid_leave_absence_type.py`
- `..._add_counts_as_vacation_to_closures.py`

### Backend (FastAPI)

**#145 — Betriebsferien:**
- `CompanyClosureCreate`/`CompanyClosureUpdate` (siehe #142) um `counts_as_vacation: bool = True` erweitern.
- `create_closure`/`PUT` (`company_closures.py`): Absence-`type` = `VACATION` wenn `counts_as_vacation` sonst `PAID_LEAVE`.

**#146 — Sondertage:**
- Settings in `admin_settings.py` (lesen/schreiben, Validierung der Modi).
- Anwendung der Sondertags-Regeln in der Sollzeit-Berechnung (`calculation_service`): für 24./31.12. je nach Modus Soll = voll / halb / 0; bei `free` zusätzlich Absence-Erzeugung (`VACATION` oder `PAID_LEAVE`) bzw. Behandlung wie Feiertag.
- **Modellierungs-Entscheidung (im Build final zu fixieren):** Sondertage als jährlich generierte, vorkonfigurierte Einträge — bevorzugt über den vorhandenen Betriebsferien-/Closure-Mechanismus (ein „free"-Sondertag = 1-Tages-Closure mit gesetztem `counts_as_vacation`) ODER über eine Sollzeit-Sonderregel. Empfehlung: **Closure-Wiederverwendung** für `free` (nutzt #142/#145 direkt), `half_day` als reine Soll-Reduktion ohne Absence.

### Frontend (React/TypeScript)

- `AdminAbsences.tsx` (#145): Beim Anlegen/Bearbeiten von Betriebsferien Auswahl „als Urlaub werten" vs. „bezahlte Freistellung".
- Settings-Seite (#146): je 24.12./31.12. Dropdown (Arbeitstag / Halbtag / Frei) + bei „Frei" Urlaub/Freistellung-Auswahl.
- Kalender/Reports: `PAID_LEAVE` eigenes Label/Farbe; Urlaubskonto zeigt Freistellung getrennt.

---

## Tasks

### Backend — Fundament
- [ ] **T-1**: Migration + Enum `PAID_LEAVE`; `AbsenceType`-Docstring + `docs/BACKEND-ARCHITEKTUR.md` aktualisieren.
- [ ] **T-2**: `calculation_service`: `PAID_LEAVE` in Soll/Ist/Balance + Urlaubskonto korrekt behandeln.

### Backend — #145
- [ ] **T-3**: Migration `counts_as_vacation` auf `company_closures`.
- [ ] **T-4**: Create/Update-Logik wählt Absence-Typ nach Flag.

### Backend — #146
- [ ] **T-5**: Sondertags-Settings (dec24/dec31: mode + vacation) in `admin_settings.py`.
- [ ] **T-6**: Sollzeit-/Absence-Anwendung der Sondertags-Regeln (inkl. half_day = halbe Sollzeit).

### Frontend
- [ ] **T-7**: Urlaub/Freistellung-Auswahl bei Betriebsferien (`AdminAbsences.tsx`).
- [ ] **T-8**: 24./31.12.-Konfiguration in Settings.
- [ ] **T-9**: `PAID_LEAVE`-Darstellung in Kalender/Reports/Urlaubskonto.

### Tests & Qualität
- [ ] **T-10**: Backend: `counts_as_vacation=false` → Urlaubsbudget unverändert, Soll der Tage = 0.
- [ ] **T-11**: Backend: dec24 `half_day` → Soll = halbe Tagessollzeit; `free`+Urlaub vs. `free`+Freistellung korrekt.
- [ ] **T-12**: E2E: Betriebsferien als Freistellung anlegen; 24.12. auf Halbtag stellen → Sollzeit stimmt.
- [ ] **T-13**: Builds/Tests grün (inkl. SQLite-Enum-Kompatibilität).

### Abschluss
- [ ] **T-14**: Spec aktualisieren, Commit & Push.

---

## Offene Fragen

1. Endgültige Modellierung der Sondertage (Closure-Wiederverwendung vs. eigene Sonderregel) — im Implementierungs-Setup festzurren; Empfehlung: Closure-Wiederverwendung für `free`.
2. Sollen vergangene/laufende Betriebsferien beim Umstellen des Flags rückwirkend umgebucht werden? → Vorschlag: nur zukünftige; bestehende bleiben, manuell über Edit (#142) änderbar.
3. Enum-Erweiterung vs. separates Feld: `PAID_LEAVE` als Enum-Wert (empfohlen, konsistent zur Typ-Matrix) vs. zusätzliches `is_paid`-Flag — Enum bevorzugt.

---

## Notizen

- Abhängigkeit: #145 baut auf #142 (closure_id-FK + Re-Sync). #146 baut auf #145 (PAID_LEAVE).
- Reihenfolge: #142 → #145 → #146.
- CLAUDE.md-Regeln: `get_weekly_hours_for_date()` pro Tag; Überstundenausgleich-Sonderfall nicht verwechseln (OVERTIME bleibt eigenständig).
