# Spec: Überstundenausgleich-Korrektur + Journal-Verbesserungen

**Status:** Done
**Erstellt:** 2026-04-01
**Session:** Opus 4.6 — 10 Commits, 335 Tests (275 → 335)

---

## Problem

Überstundenausgleich wurde falsch verrechnet: Das Monats-Soll wurde um die Abwesenheitsstunden reduziert, was dazu führte, dass ein Ausgleichstag effektiv nur ~1h statt der geplanten ~8h vom Überstundenkonto abzog.

**Beispiel (vorher falsch):** 10 Tage, 8h Soll, 9h/Tag, 1 Tag Ausgleich:
- Soll: 72h (80h - 8h Reduktion), Ist: 81h → Bilanz: **+9h** (falsch)

**Beispiel (jetzt korrekt):**
- Soll: 80h (unverändert), Ist: 81h → Bilanz: **+1h** (korrekt: 9h aufgebaut - 8h abgebaut)

## Lösung

### Kernfix: Überstundenausgleich-Verrechnung

`OVERTIME` Absences werden jetzt wie `SICK`/`TRAINING` aus der Soll-Reduktion ausgeschlossen, aber NICHT als Ist-Stunden gutgeschrieben:

| Absence-Typ | Reduziert Soll | Zählt als Ist |
|---|---|---|
| VACATION | Ja | Nein |
| SICK | Nein | Ja (§3 EntgFG) |
| TRAINING | Nein | Ja |
| **OVERTIME** | **Nein** | **Nein** |
| OTHER | Ja | Nein |

**Geänderte Dateien:**
- `backend/app/services/calculation_service.py` — 3 Stellen (get_monthly_target, get_overtime_account, get_ytd_summary)
- `backend/app/services/journal_service.py` — OVERTIME: Ist=0, Soll=Tagesplan

### Journal: Multi-Entry + Mixed-Day-Anzeige

- Tage mit mehreren TimeEntries zeigen jeden Eintrag auf eigener Zeile (statt "(2x)" Badge)
- Gemischte Tage (TimeEntry + Absence) zeigen pro Zeile den korrekten Typ (z.B. "Arbeitszeit" + "Fortbildung")
- Pro Eintrag ein eigener Edit-Button (Stift-Icon)

**Geänderte Dateien:**
- `frontend/src/components/MonthlyJournal.tsx`
- `backend/app/services/journal_service.py` — neuer `day_type = "mixed"`

### Admin ChangeRequests: Filter + Sicherheit

**UI-Verbesserungen:**
- User-Dropdown-Filter
- Zeitraum-Filter (1M / 3M / Jahr / Vorjahr / freier Zeitraum)
- Kein Zeitfilter bei "Offen" (pending zeigt immer alle)
- Deutsches Datumsformat (dd.MM.yyyy)

**Bug-Fixes:**
- Race Condition: CR-Status wird erst NACH Precondition-Checks gesetzt
- Unique-Constraint-Check bei UPDATE-CRs mit Datumsänderung
- DELETE-CRs: Entry-Existenzprüfung vor Approval
- UPDATE-CRs: Zukunftsdaten blockiert
- Start >= End Validierung

**Geänderte Dateien:**
- `backend/app/routers/admin_change_requests.py`
- `backend/app/routers/change_requests.py`
- `frontend/src/pages/admin/ChangeRequests.tsx`

### Sonstige Fixes

- `backend/alembic/env.py` — `version_num_width=128` (verhindert varchar(32) Overflow)

## Tests (60 neue)

| Kategorie | Tests | Geprüft |
|---|---|---|
| Überstundenausgleich | 8 | Soll/Ist, Tagesplan, Journal, kumulativ |
| Absence-Typ-Matrix | 5 | Parametrisiert für alle 5 Typen |
| Journal Mixed-Days | 4 | Work+Training, Work+Sick, Work+Vacation, Work+Overtime |
| Jahresabschluss | 8 | Übertrag, Resturlaub, Negativsaldo, Mid-Year-Hire, Idempotenz |
| Urlaubskonto | 5 | Basis, Nutzung, Übertrag, Pro-Rata |
| Multi-Entry | 2 | 2 und 3 Einträge pro Tag |
| Monatsübergreifend | 2 | Kumulierung, 3-Monats-Akkumulation |
| Tagesplan-Edge-Cases | 2 | 0h-Tag, Ausgleich auf 0h-Tag |
| Carryover | 3 | Startbilanz, Multi-Year, kumuliert |
| Berechnungs-Units | 8 | Actual, Break, Target, Sick, Other |
| Berechnungen-Existing | 13 | Weekly Hours, Daily Target, Working Days |

## Security Review

Separates Security Review ergab: **0 kritische Schwachstellen.** JWT, RLS, Input-Validierung, Rate-Limiting, CORS alle sauber.

## Commits

1. `9736c14` — fix: Überstundenausgleich reduziert nicht mehr das Soll
2. `bb7bc27` — feat: Journal Multi-Entry + Admin CR Filter
3. `0532545` — fix: Race Condition CR-Approval + 35 Edge-Case-Tests
4. `f9d5b64` — fix: Code-Review-Findings
5. `a5e3567` — fix: Alembic version_num_width
6. `dc20104` — fix: Per-Entry Edit-Button
7. `2c4cfd7` — feat: Gemischte Tage im Journal
8. `6c7a7dd` — fix: Mixed-Day Soll-Berechnung + Delete
9. `361ad65` — fix: Edit-Button für Absences auf Mixed-Days
10. `5a70544` — fix: Typ pro Zeile bei Multi-Entry
11. `7750c4c` — test: 21 weitere Tests
