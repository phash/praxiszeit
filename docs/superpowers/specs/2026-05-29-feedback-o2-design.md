# Design: Nutzer-Feedback O2 — Typ-Farben, Anfangssaldo, Viertelstunden, Bezahlte Freistellung

**Datum:** 2026-05-29
**Issues:** #157, #158, #160, #161
**Branch:** `feat/feedback-o2-typcolors-saldo`

Umsetzung von vier Punkten aus dem Praxis-Feedback. Ein Branch, ein PR.

---

## #161 — Viertelstunden bei individuellen Tagesstunden

**Problem:** Frontend-Eingabefelder für Tagesstunden erlauben nur 0,5-Schritte (`step="0.5"`); Mini-/Midi-Jobs brauchen 0,25 (z. B. 3,75 h).

**Lösung:** `step="0.25"` auf den Tagesstunden-Feldern in `frontend/src/pages/admin/users/UserForm.tsx` und `WorkingHoursModal.tsx`. Backend akzeptiert bereits Viertelstunden (`hours_monday..friday` = `Numeric(4,2)`; Schema nur `ge=0, le=24`). **Kein Backend-/Migrationsbedarf.**

`weekly_hours` bleibt `Numeric(4,1)` (0,1-Schritte) — Viertelstunden gelten für die Tages-, nicht die Wochensumme.

## #160 — Bezahlte Freistellung (kein Urlaubsabzug) sichtbar machen

**Problem:** Wunsch nach Freistellung ohne Urlaubsabzug.

**Befund:** Fachlich bereits abgedeckt durch `AbsenceType.PAID_LEAVE` (#145): reduziert das Tagessoll (balance-neutral), berührt das Urlaubsbudget nicht (`get_vacation_account` summiert nur `VACATION`).

**Lösung:** Im manuellen Erfassungs-/Antragsdialog sicherstellen, dass `PAID_LEAVE` als Option „**Bezahlte Freistellung (kein Urlaubsabzug)**" auswählbar ist, inkl. Tooltip. Falls bereits vorhanden: nur Label/Tooltip präzisieren. **Kein Backend-Change.**

## #158 — Anfangssaldo Überstunden bei MA-Einrichtung

**Problem:** Kein auffindbares Feld für einen Überstunden-Startsaldo beim Einrichten eines MA.

**Befund:** Mechanik existiert — `get_overtime_account` (`calculation_service.py`) nutzt einen `YearCarryover.overtime_hours` als Startsaldo; setzbar via `PUT /api/admin/users/{id}/carryovers/{year}`. Nur nicht auffindbar.

**Lösung:** Feld **„Anfangssaldo Überstunden (h)"** im MA-Formular (Anlegen + Bearbeiten).
- Beim Speichern schreibt das Frontend einen `YearCarryover` für das **Startjahr** (Jahr des `first_work_day`, sonst aktuelles Jahr) via bestehendem Carryover-Endpoint.
- Anlegen: erst User anlegen (POST), dann mit zurückgegebener ID den Carryover setzen.
- Bearbeiten: Feld zeigt den aktuellen Startjahr-Carryover und aktualisiert ihn.
- **Kein Backend-Change** (Endpoint vorhanden), nur UI + ein Folge-API-Call.

## #157 — Admin-konfigurierbare Typ-Farben

**Problem:** Anwesenheit/Abwesenheit im Erfassungsdialog schwer unterscheidbar; Wunsch nach Admin-vergebbaren Farben pro Typ.

**Entscheidungen (mit Nutzer abgestimmt):**
- Farben für **Anwesenheit (Arbeit) + alle Abwesenheitstypen** (training, vacation, sick, overtime, other, paid_leave).
- Anwendung **überall inkl. Kalender**: Abwesenheiten werden nach Typ-Farbe statt Mitarbeiter-Farbe eingefärbt. `User.calendar_color` bleibt erhalten (Profil), im Kalender abgelöst.

### Backend
- Per-Tenant `SystemSetting`-Key **`type_colors`**, `value` = JSON-Map `{ "work": "#hex", "training": "#hex", "vacation": "#hex", "sick": "#hex", "overtime": "#hex", "other": "#hex", "paid_leave": "#hex" }`.
- Service-Modul `app/services/type_colors_service.py`:
  - `DEFAULT_TYPE_COLORS` (s. u.)
  - `get_type_colors(db, tenant_id) -> dict` — gespeicherte Werte über Defaults gemerged.
  - `set_type_colors(db, tenant_id, colors)` — validiert (nur bekannte Keys, Hex `^#[0-9A-Fa-f]{6}$`), upsert.
- `GET /api/type-colors` — **jeder authentifizierte Nutzer**, tenant-scoped (Employees brauchen die Farben fürs Rendern). In neuem leichten Router oder `me.py`.
- `GET/PUT /api/admin/settings/type-colors` (Admin) — in `admin_settings.py`, analog `/settings/special-days`. Validierung serverseitig.

**Default-Palette** (überschreibbar):
| Typ | Default |
|-----|---------|
| work (Arbeit) | `#16A34A` |
| training (Fortbildung) | `#15803D` |
| vacation (Urlaub) | `#2563EB` |
| sick (Krank) | `#DC2626` |
| overtime (Überstundenausgleich) | `#7C3AED` |
| other (Sonstiges) | `#6B7280` |
| paid_leave (Bez. Freistellung) | `#0D9488` |

### Frontend
- Store/Hook `useTypeColors` lädt `GET /api/type-colors` beim Login (analog systemStore); liefert die gemergte Map + Helper `colorForAbsenceType(type)` / `colorForWork()`.
- **Admin-Settings**: neuer Abschnitt „Farben" mit Color-Pickern (`<input type="color">`) pro Typ → `PUT /api/admin/settings/type-colors`.
- **Anwendung:**
  - Manueller Erfassungs-/Antragsdialog: Typ-Optionen mit Farb-Indikator (löst die Anwesenheit/Abwesenheit-Verwechslung aus #157-Ursprung).
  - Abwesenheits-/Team-Kalender + Übersichten (`Dashboard.tsx`, `AdminAbsences.tsx`): Einfärbung nach `colorForAbsenceType(absence.type)` statt `absence.user_color`.
  - Legende, die Typ↔Farbe erklärt.

---

## Tests
- **Backend (TDD, pytest/SQLite):** `type_colors_service` (Defaults-Merge, Validierung ungültiger Hex/Keys), `GET /api/type-colors` (Default ohne Konfiguration + nach Konfiguration), `PUT` Admin-only + Validierung, tenant-Isolation. Carryover-Wiring von #158 ist Endpoint-seitig schon getestet (bestehende `admin_carryovers`-Tests).
- **Frontend:** Vitest für `useTypeColors`-Helper/Merge. UI-Rendering manuell im laufenden Container verifizieren (Color-Picker, Kalender-Einfärbung, Erfassungsdialog).

## Nicht in diesem PR
- #156 (Urlaub tage- vs. stundenbasiert) — separat, rechtliche Prüfung nötig.
- #159, #162 — separat.
- `weekly_hours`-Viertelstunden (bräuchte Migration `Numeric(4,1)→(4,2)`).
