# Wochenstunden anpassen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wochenstunden werden im Bearbeiten-Formular nur noch angezeigt; Änderungen laufen über einen Dialog mit Wirkungsdatum, der rückwirkende Folgen vorher zeigt und die gespeicherten Abwesenheits-Stunden mitzieht.

**Architecture:** Ein neuer reiner Rechen-Helper in `calculation_service` ist die einzige Quelle für die Rückrechnung und wird von Anlegen, Löschen und der Vorschau genutzt. Die bestehenden Endpoints werden erweitert, nicht ersetzt. Im Frontend wird das vorhandene `WorkingHoursModal` ausgebaut und zusätzlich aus `UserForm` geöffnet.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (Backend), React + TypeScript (Frontend), pytest + Vitest.

## Global Constraints

- Master ist branch-protected — Arbeit auf `feat/wochenstunden-anpassen`, Merge per PR.
- Audit-Marker `source` ist `varchar(40)` — neue Marker müssen kürzer sein.
- F-026: jede Query auf tenant-scoped Tabellen trägt einen expliziten `tenant_id`-Filter.
- Die Berechnung bleibt eingefroren: kein zweiter Rechenpfad, alles über den einen Helper.
- Abwesenheits-**Tage** sind tagebasiert (§3 BUrlG) und dürfen sich durch diese Arbeit nicht ändern — nur die gespeicherten `hours`.
- Backend-Suite passt nicht in ein 600-Sekunden-Limit → in zwei Datei-Hälften fahren.
- Container-Sync vor jedem Testlauf: `docker compose cp backend/app backend:/app/` **aus dem Repo-Root**.

---

### Task 1: Rückrechnungs-Helper

**Files:**
- Modify: `backend/app/services/calculation_service.py`
- Test: `backend/tests/test_retarget_absence_hours.py` (neu)

**Interfaces:**
- Produces: `retarget_absence_hours(db, user, start: date, end: date, *, dry_run: bool = False) -> int`
  — setzt `Absence.hours` im Fenster auf das Tagessoll des jeweiligen Tages und liefert die Anzahl betroffener Zeilen. `dry_run=True` zählt nur.

- [ ] **Step 1: Tests schreiben** (`test_retarget_absence_hours.py`)

Fälle, je ein Test:
`test_vacation_hours_follow_the_new_daily_target`,
`test_vacation_days_stay_unchanged` (Tagesprinzip),
`test_sick_and_training_are_adjusted` (Ist-Gutschrift),
`test_overtime_is_never_touched`,
`test_half_day_gets_half_the_target`,
`test_half_special_day_uses_the_weight` (24.12.),
`test_absence_before_first_work_day_untouched`,
`test_absence_after_last_work_day_untouched`,
`test_weekend_and_holiday_are_skipped`,
`test_untracked_user_is_untouched` (`track_hours=False`),
`test_dry_run_changes_nothing_but_counts`,
`test_returns_zero_outside_the_window`.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

`docker compose exec -T -e TZ=Europe/Berlin backend pytest tests/test_retarget_absence_hours.py -q`
Erwartet: `AttributeError: module 'app.services.calculation_service' has no attribute 'retarget_absence_hours'`

- [ ] **Step 3: Helper implementieren**

```python
def retarget_absence_hours(
    db: Session, user: User, start: date, end: date, *, dry_run: bool = False
) -> int:
    """Setzt Absence.hours im Fenster auf das Tagessoll des jeweiligen Tages.

    Nach einer rückwirkenden Wochenstunden-Änderung rechnet das Soll automatisch
    neu (datumsbasiert), die beim Buchen festgeschriebenen `hours` aber nicht —
    ein Krankentag schriebe sonst weiter die alten Stunden gut. OVERTIME bleibt
    ausgenommen (trägt explizit beantragte Stunden), ebenso Mitarbeitende ohne
    Stundenzählung (dort zählt nur die Tageszählung).
    """
    if start > end or not user.track_hours:
        return 0
    holidays = {h.date for h in db.query(PublicHoliday).filter(
        PublicHoliday.tenant_id == user.tenant_id,
        PublicHoliday.date >= start, PublicHoliday.date <= end,
    ).all()}
    special_cfg = special_days_service.get_special_day_config(db, user.tenant_id, start.year)
    wh_changes = db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == user.tenant_id,
    ).order_by(WorkingHoursChange.effective_from).all()
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,
        Absence.date >= start, Absence.date <= end,
        Absence.type != AbsenceType.OVERTIME,
    ).all()

    changed = 0
    for a in absences:
        d = a.date
        if d.weekday() >= 5 or d in holidays:
            continue
        if not _within_employment_window(user, d):
            continue
        weekly = get_weekly_hours_for_date(db, user, d, wh_changes=wh_changes)
        target = get_daily_target_for_date(user, d, weekly)
        target *= special_days_service.special_day_target_factor(d, special_cfg)
        if target <= 0:
            continue
        new_hours = (target / 2) if a.half_day else target
        new_hours = Decimal(new_hours).quantize(Decimal('0.01'))
        if Decimal(str(a.hours)).quantize(Decimal('0.01')) == new_hours:
            continue
        changed += 1
        if not dry_run:
            a.hours = float(new_hours)
    if not dry_run and changed:
        db.flush()
    return changed
```

- [ ] **Step 4: Tests laufen lassen, grün**

- [ ] **Step 5: Commit** — `feat(wochenstunden): Rückrechnungs-Helper für Abwesenheits-Stunden`

---

### Task 2: Vorschau-Endpoint

**Files:**
- Modify: `backend/app/routers/admin_users.py`
- Modify: `backend/app/schemas/working_hours_change.py`
- Test: `backend/tests/test_wh_change_preview.py` (neu)

**Interfaces:**
- Consumes: `retarget_absence_hours(..., dry_run=True)` aus Task 1.
- Produces: `GET /api/admin/users/{user_id}/working-hours-changes/preview?effective_from=&weekly_hours=`
  → `WorkingHoursChangePreview{is_retroactive, period_start, period_end, current_daily_target, new_daily_target, affected_absences, closed_years, blocked_reason}`

- [ ] **Step 1: Tests** — `test_future_date_is_not_retroactive`, `test_today_is_not_retroactive`, `test_past_date_counts_affected_absences`, `test_daily_schedule_user_is_blocked`, `test_duplicate_date_is_blocked`, `test_closed_year_is_reported`, `test_preview_changes_nothing` (Zustand vorher/nachher identisch), `test_cross_tenant_404`.
- [ ] **Step 2: Fehlschlag bestätigen** (404 auf die Route)
- [ ] **Step 3: Schema + Endpoint implementieren** — `require_admin`, `_get_user_in_tenant`, `dry_run=True`, `stale_year_closing_warning` für `closed_years`.
- [ ] **Step 4: grün**
- [ ] **Step 5: Commit** — `feat(wochenstunden): Vorschau-Endpoint für rückwirkende Änderungen`

---

### Task 3: Anlegen zieht Abwesenheiten mit

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`create_working_hours_change`)
- Test: `backend/tests/test_wh_change_retroactive.py` (neu)

**Interfaces:**
- Consumes: `retarget_absence_hours` (Task 1).
- Produces: Antwort trägt zusätzlich `adjusted_absences: int` und optional `warning: str`.

- [ ] **Step 1: Tests** — `test_retroactive_change_adjusts_absences`, `test_future_change_adjusts_nothing`, `test_baseline_row_still_created_on_first_change` (1.16.0-Verhalten), `test_audit_row_written`, `test_closed_year_returns_warning`, `test_daily_schedule_still_400`, `test_duplicate_date_still_400`.
- [ ] **Step 2: Fehlschlag bestätigen**
- [ ] **Step 3: Implementieren** — nach `db.flush()` der neuen Zeile: bei `effective_from < today_local()` `retarget_absence_hours(db, user, effective_from, today_local())`; Audit-Zeile `action="update"`, `source="wh_change"` (8 Zeichen) mit Zeitraum + Anzahl; `stale_year_closing_warning` für die berührten Jahre.
- [ ] **Step 4: grün**
- [ ] **Step 5: Commit** — `feat(wochenstunden): rückwirkende Änderung zieht Abwesenheits-Stunden mit`

---

### Task 4: Löschen rechnet zurück

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`delete_working_hours_change`)
- Test: `backend/tests/test_wh_change_retroactive.py` (erweitern)

- [ ] **Step 1: Tests** — `test_delete_restores_absence_hours` (anlegen → Stunden geändert → löschen → wieder auf altem Wert), `test_delete_of_future_change_adjusts_nothing`.
- [ ] **Step 2: Fehlschlag bestätigen**
- [ ] **Step 3: Implementieren** — nach `db.delete(change)` + `db.flush()` dasselbe Fenster erneut über den Helper laufen lassen (jetzt mit dem verbliebenen gültigen Wert).
- [ ] **Step 4: grün**
- [ ] **Step 5: Commit** — `feat(wochenstunden): Löschen einer Änderung rechnet zurück`

---

### Task 5: update_user sperrt weekly_hours

**Files:**
- Modify: `backend/app/routers/admin_users.py` (`update_user`)
- Test: `backend/tests/test_wh_change_retroactive.py` (erweitern)

- [ ] **Step 1: Tests** — `test_put_user_with_weekly_hours_is_rejected` (400, Nutzer unverändert), `test_put_user_without_weekly_hours_succeeds`, `test_post_user_with_weekly_hours_still_works`.
- [ ] **Step 2: Fehlschlag bestätigen**
- [ ] **Step 3: Implementieren** — in `update_user` vor dem `setattr`-Loop:

```python
if 'weekly_hours' in update_data:
    raise HTTPException(
        status_code=400,
        detail=("Wochenstunden werden über „Wochenstunden anpassen“ mit Wirkungsdatum "
                "geändert, damit Historie und Soll vergangener Monate korrekt bleiben."),
    )
```

- [ ] **Step 4: grün** — zusätzlich die bestehenden Suiten `test_admin_users*`, `test_endpoints.py`, `test_cross_tenant_api.py` prüfen, die `weekly_hours` mitsenden könnten.
- [ ] **Step 5: Commit** — `feat(wochenstunden): PUT users lehnt weekly_hours ab`

---

### Task 6: UserForm read-only + Button

**Files:**
- Modify: `frontend/src/pages/admin/users/UserForm.tsx`
- Test: `frontend/src/pages/admin/users/UserForm.test.tsx` (neu)

- [ ] **Step 1: Tests** — `zeigt beim Bearbeiten ein read-only-Feld plus Button`, `zeigt beim Anlegen ein Eingabefeld`, `sendet weekly_hours beim Update nicht mit`, `sendet weekly_hours beim Anlegen mit`, `Button ist bei individuellem Tagesplan deaktiviert`.
- [ ] **Step 2: Fehlschlag bestätigen** — `npx vitest run src/pages/admin/users/UserForm.test.tsx --pool=threads`
- [ ] **Step 3: Implementieren** — `readOnly`-Anzeige + Button, der `onOpenHours(userId)` aufruft; im Update-Payload `weekly_hours` weglassen.
- [ ] **Step 4: grün**
- [ ] **Step 5: Commit** — `feat(wochenstunden): Formular zeigt Wochenstunden nur noch an`

---

### Task 7: Dialog ausbauen

**Files:**
- Modify: `frontend/src/pages/admin/users/WorkingHoursModal.tsx`
- Modify: `frontend/src/pages/admin/Users.tsx` (Modal auch aus dem Formular öffnen)
- Test: `frontend/src/pages/admin/users/WorkingHoursModal.test.tsx` (neu)

- [ ] **Step 1: Tests** — `Verlauf zeigt ab und bis`, `jüngster Eintrag zeigt bis heute`, `rückwirkendes Datum löst Vorschau aus`, `Warnhinweis nennt Zeitraum und Anzahl`, `Speichern erst nach Bestätigung`, `zukünftiges Datum zeigt keinen Hinweis`, `blocked_reason sperrt den Speichern-Button`.
- [ ] **Step 2: Fehlschlag bestätigen**
- [ ] **Step 3: Implementieren** — Vorschau-Abruf bei Datumsänderung (debounced), Warnblock, „bis"-Spalte aus dem jeweils nächsten Eintrag berechnet.
- [ ] **Step 4: grün**
- [ ] **Step 5: Commit** — `feat(wochenstunden): Dialog zeigt Gültigkeitszeitraum und rückwirkende Folgen`

---

### Task 8: Doku

**Files:**
- Modify: `docs/handbuch/HANDBUCH-ADMIN.md`, `docs/handbuch/CHEATSHEET-ADMIN.md`
- Modify: `frontend/public/help/HANDBUCH-ADMIN.md`, `frontend/public/help/CHEATSHEET-ADMIN.md`
- Modify: `frontend/src/components/DocViewer.tsx`
- Modify: `docs/BERECHNUNGEN.md`, `CLAUDE.md`

- [ ] **Step 1: Alle fünf Nutzer-Doku-Flächen auf den neuen Ablauf umstellen**
- [ ] **Step 2: `diff -q docs/handbuch/X frontend/public/help/X` für beide Dateien — müssen byte-identisch sein**
- [ ] **Step 3: `BERECHNUNGEN.md`** — Rückrechnung der Abwesenheits-Stunden dokumentieren, den bestehenden Warnhinweis zu `user.weekly_hours` auf den neuen Schreibweg umschreiben
- [ ] **Step 4: `CLAUDE.md`** — Regel: Wochenstunden ändern sich ausschließlich über den Historie-Endpoint
- [ ] **Step 5: Commit** — `docs(wochenstunden): Handbücher, In-App-Hilfe und Berechnungen nachziehen`

---

### Task 9: Gesamtverifikation

- [ ] **Step 1: Volle Backend-Suite in zwei Hälften** — erwartet: nur die 6 bekannten date-brittlen `shift_planning`-MyToday-Fehler
- [ ] **Step 2: Frontend** — `npx tsc --noEmit && npx vitest run --pool=threads && npm run build`
- [ ] **Step 3: Manueller Durchlauf gegen den lokalen Docker-Stack** — Nutzer bearbeiten, Dialog öffnen, rückwirkende Änderung mit Hinweis, danach Monatsbericht prüfen
- [ ] **Step 4: PR öffnen**
