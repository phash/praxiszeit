# #312 — Eigene Abwesenheitsgründe (Custom Absence Reasons) — Design-Spec

**Status:** approved 2026-06-27 (Design); **Bau separat** (eigene Session).
**Branch (Spec):** `spec/issue-312-custom-absence-reasons`

Ursprung: Azubis haben Berufsschultage (keine Arbeit, aber auch kein Urlaub/krank).
Verallgemeinert (Manuel): Admins sollen in den **Einstellungen eigene
Abwesenheitsgründe** anlegen (Freitext + optional Farbe), umbenennen und
verwalten. Jeder Grund hat ein **Basis-Verhalten** (vom Admin gewählt), das das
ArbZG-/Berechnungsmodell bestimmt — **ohne** neue Calc-Pfade.

---

## Leitprinzip — Calc bleibt eingefroren

Das auditierte Berechnungsmodell läuft heute auf `Absence.type` (Enum). Ein
eigener Grund ist **ein Label + Farbe über einem bestehenden Basis-Verhalten**:

- `Absence.type` bleibt ein **bestehender** `AbsenceType` (treibt die Berechnung
  unverändert) — gesetzt aus dem Basis-Verhalten des Grundes.
- `Absence.reason_id` (neu, nullable FK) trägt **Label + Farbe** für die Anzeige.
- Alle Anzeige-Oberflächen bevorzugen `reason.name`/`reason.color`, wenn
  `reason_id` gesetzt ist; sonst das eingebaute Typ-Label.

So muss **kein** Calc-Filter (`get_monthly_target`, `get_overtime_account`,
`get_vacation_account`, Exporte, Journal) angefasst werden.

## Basis-Verhalten (vom Admin je Grund gewählt)

| Basis-Verhalten (UI) | mapped `AbsenceType` | Calc-Wirkung |
|---|---|---|
| **Zählt als gearbeitet** (z. B. Schule/Azubi) | `TRAINING` | Ist gutgeschrieben (§3-artig), Soll bleibt — MA verliert keine Stunden |
| **Bezahlt frei** | `PAID_LEAVE` | Soll → 0 an dem Tag, saldo-neutral, **kein** Urlaubsabzug |
| **Überstundenabbau** | `OVERTIME` | Soll bleibt, Ist=0 → Überstundenkonto sinkt |

> **Bewusst NICHT als Custom-Verhalten:** „Urlaub" (budgetgeführt) und „Krank"
> (Art.-9-Gesundheitsdatum) bleiben den eingebauten Typen vorbehalten.

**Wichtig (Aggregation):** Reports/Exports, die nach `type` summieren, zählen
einen „Schule"-Grund in die **Fortbildungs**-Summe (sein Basis-Typ). Für v1
akzeptiert (der Grund ist ein Sub-Label). Optionale Erweiterung: spätere
reason-granulare Summen.

---

## Datenmodell

**Neue Tabelle `absence_reasons`** (tenant-scoped, RLS-Policy + F-026, Migration `056`):
- `id` UUID PK
- `tenant_id` UUID FK → tenants, idx
- `name` varchar(80) — Freitext, eindeutig pro Tenant (aktiv)
- `color` varchar(7) nullable — `#RRGGBB`
- `base_behavior` varchar(20) — `worked | paid_free | overtime_comp`
- `is_active` bool default true — Soft-Deaktivierung (statt Hard-Delete, da
  Absences referenzieren)
- `sort_order` int default 0
- `created_at` timestamptz

**`absences.reason_id`** UUID FK → absence_reasons, **nullable**, `ondelete=SET NULL`
(Migration `056`). Modell-Cascade ohne `passive_deletes` (SQLite-Tests, vgl. #305).

**DSGVO/Erasure:** `absence_reasons` ist NICHT user-scoped → `purge_user`
unberührt. Das `reason_id` an `Absence` wird mit dem User mitgelöscht (Absences
des Users werden in `purge_user` ohnehin entfernt). `ondelete=SET NULL` deckt das
Löschen eines **Grundes** ab (Absences behalten den Basis-`type`, verlieren nur
das Label).

---

## API (`/api/admin/absence-reasons`, `require_admin`, F-026)

- `GET /` — Liste (inkl. inaktiver via `?include_inactive`).
- `POST /` — `{name, color?, base_behavior}` → 201. 409 bei Namensdublette (aktiv).
- `PUT /{id}` — Umbenennen / Farbe / `is_active`. **`base_behavior` nach dem
  ersten Buchen NICHT mehr änderbar** (sonst würden bestehende Absences inkonsistent
  zu ihrem `type` — alternativ: Änderung re-typed alle verknüpften Absences; v1:
  sperren, klare 400-Meldung).
- `DELETE /{id}` — nur wenn unbenutzt; sonst 409 mit Hinweis „deaktivieren".
- **Public/Employee-Read:** Die Buchungs-UIs brauchen die aktive Gründe-Liste →
  `GET /api/absence-reasons` (auth, alle Rollen, nur aktive) für den Auswahl-Dropdown.

## Absence-Buchung (3 Schreibpfade — wie #298 alle pflegen)

Die Absence-Erstellung gibt es an mehreren Stellen: `create_absence`
(Direkt-Buchung Admin), MA-**Änderungsantrag** (`entry_kind="absence"`,
CR-Genehmigung), und ggf. Import. Jeder Pfad:
1. akzeptiert optional `reason_id`,
2. validiert: Grund gehört zum Tenant + ist aktiv (F-026),
3. setzt `Absence.type` aus `reason.base_behavior` (Mapping oben),
4. speichert `reason_id`.
Ohne `reason_id` → heutiges Verhalten (eingebaute Typen).

## Anzeige

- **Label/Farbe:** Helper `absenceLabel(absence)` / `absenceColor(absence)` →
  `reason` bevorzugt, sonst Typ. Betrifft Kalender, Journal, Abwesenheitslisten,
  Tooltips. `type_colors_service` bleibt für eingebaute Typen.
- **DSGVO Art. 9 — Maskierung:** Kollegen-Feeds (`/absences/calendar`,
  `/absences/team/upcoming`) maskieren bereits `_MASKED_ABSENCE_TYPES`. Eigene
  Gründe können sensibel sein (z. B. „Reha") → **konservativ: jede Absence mit
  `reason_id` wird für Nicht-Admins als `"absent"` maskiert** (Label NICHT zeigen),
  unabhängig vom Basis-Typ. Admin sieht das echte Label. (Beide Feeds dieselbe
  Logik, wie die bestehende Konstante.)

## Frontend

- **Einstellungen → „Abwesenheitsgründe":** CRUD-Liste (Name inline editierbar,
  Farb-Picker, Basis-Verhalten-Select beim Anlegen, Aktiv-Toggle, Löschen).
  Muster wie die bestehende Custom-Feiertage-/Typ-Farben-Verwaltung in `Settings.tsx`.
- **Absence-Formular(e):** Typ-Auswahl erweitert um die aktiven eigenen Gründe
  (Gruppe „Eigene Gründe"); Auswahl sendet `reason_id`.
- API-Client `api/absenceReasons.ts`.

## Tests
- Backend: CRUD (+ 409 Dublette/benutzt, 400 base_behavior-Lock), F-026/Cross-Tenant,
  RLS; `create_absence` mit `reason_id` setzt korrekten `type` je Verhalten; CR-Pfad;
  Maskierung im Kollegen-Feed (Nicht-Admin sieht `"absent"`, Admin das Label);
  `get_monthly_target`/`get_vacation_account` reagieren korrekt je Basis-Verhalten
  (Schule = gearbeitet → kein Stundenverlust; paid_free → Soll 0; overtime_comp →
  Konto sinkt). Migration `056` auf echtem Postgres (RLS + ondelete).
- Frontend: Vitest Reason-CRUD + Label/Color-Helper; E2E Anlegen + Buchen.
- **arbzg-compliance-auditor** über die Verhaltens-Mappings + Maskierung.

## Doku
`docs/SCHICHTPLANUNG.md`-Pendant nicht nötig; pflegen: Admin-Handbuch
(Einstellungen-Kapitel), In-App-Hilfe (`DocViewer.tsx`), CLAUDE.md-Regel
(„reason_id = Label-Overlay, type treibt Calc; 3 Buchungspfade; Maskierung").

## Offene Punkte / YAGNI-Grenzen
- v1: `base_behavior` nach erstem Buchen gesperrt (kein Re-Typing-Migrationspfad).
- v1: reason-granulare Report-Summen NICHT enthalten (Aggregation in den Basis-Typ).
- v1: keine pro-Grund-Sensibilitäts-Flag — alle eigenen Gründe werden im
  Kollegen-Feed maskiert (sicher; ggf. später feiner).
