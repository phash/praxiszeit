# Design: "Kind krank" + Sonderurlaub-Gründe (#376)

**Issue:** [#376](https://github.com/phash/praxiszeit/issues/376) — „Kind krank" abbilden
**Datum:** 2026-07-07
**Status:** Implementiert (Branch `feat/376-kind-krank`) — Backend+Frontend+Doku, Tests grün, Migration 061 verifiziert
**Baut auf:** #312 (Eigene Abwesenheitsgründe / Custom Absence Reasons)

---

## 1. Problem & Kontext

Fehlt ein/e MitarbeiterIn wegen Betreuung eines erkrankten Kindes (§45 SGB V), so
zahlt **nicht** der Arbeitgeber den Lohn fort — die Krankenkasse zahlt
Kinderkrankengeld, der Arbeitgeber kürzt den Lohn (unbezahlte Freistellung).
Für die Zeiterfassung heißt das: der Tag ist **entschuldigt**, es entstehen **keine
Minusstunden**, es wird **kein Urlaub** verbraucht, aber der Tag zählt **nicht** als
gearbeitet (anders als Krankheit §3 EntgFG).

Der Issue-Ersteller wünscht außerdem einen ganzen Katalog weiterer Gründe
(Sonderurlaub: Todesfall, Hochzeit, Umzug, … — „D1–D8" in anderen Systemen), die
**über die Einstellungen aktivierbar** sein sollen. §45 SGB V begrenzt die
Kinderkrankentage pro Jahr — der Verbrauch soll gezählt und bei Überschreitung
**gewarnt** werden.

### Bestehende Infrastruktur (#312)

PraxisZeit hat bereits tenant-eigene Abwesenheitsgründe (`absence_reasons`):
Name + Farbe + `base_behavior`, in den Einstellungen anlegbar/aktivierbar. Ein
`Absence.reason_id` ist nur ein **Label-/Farb-Overlay**; der eingebaute
`Absence.type` (aus `base_behavior` abgeleitet) treibt **alle** Berechnung — das
auditierte Calc-Modell bleibt eingefroren.

`BEHAVIOR_TO_ABSENCE_TYPE` bildet heute **drei** Verhalten ab:

| `base_behavior` | → `AbsenceType` | Lohnwirkung |
|---|---|---|
| `worked` | `TRAINING` | zählt als gearbeitet (Ist += Soll) |
| `paid_free` | `PAID_LEAVE` | Soll→0, **bezahlt**, saldo-neutral, kein Urlaub |
| `overtime_comp` | `OVERTIME` | Überstundenabbau |

**Lücke:** Kein Verhalten bildet „entschuldigt **unbezahlt**" ab. `AbsenceType.OTHER`
existiert (Soll→0, Ist+=0, saldo-neutral, kein Urlaub, **unbezahlt**) und ist im
Calc vollständig behandelt — aber kein `base_behavior` mappt darauf. Genau diese
Mechanik braucht „Kind krank".

Reporting ist bereits gelöst: `export_service._absence_export_label` /
`ods_export_service` rendern den **Custom-Reason-Namen** (#312) → „Kind krank" taucht
in Exporten mit eigenem Label auf.

---

## 2. Ansatz (gewählt)

**#312 erweitern**, statt einen first-class `AbsenceType.CHILD_SICK` einzuführen:

- Skaliert auf beliebig viele Gründe (D1–D8) ohne Hardcoding.
- Kein Umbau des eingefrorenen Calc-Modells.
- Entspricht dem Wunsch „über Einstellungen aktivierbar".

Verworfen: eigener `AbsenceType` — mehr Arbeit, bricht das Calc-Modell auf,
skaliert nicht auf den Gründe-Katalog.

---

## 3. Detaildesign

### 3.1 Neues Verhalten `unpaid_free → OTHER`

`backend/app/models/absence.py`:

```python
class AbsenceReasonBehavior(str, enum.Enum):
    WORKED = "worked"
    PAID_FREE = "paid_free"
    OVERTIME_COMP = "overtime_comp"
    UNPAID_FREE = "unpaid_free"   # NEU: entschuldigt unbezahlt (Kind krank, unbez. Sonderurlaub)

BEHAVIOR_TO_ABSENCE_TYPE = {
    AbsenceReasonBehavior.WORKED: AbsenceType.TRAINING,
    AbsenceReasonBehavior.PAID_FREE: AbsenceType.PAID_LEAVE,
    AbsenceReasonBehavior.OVERTIME_COMP: AbsenceType.OVERTIME,
    AbsenceReasonBehavior.UNPAID_FREE: AbsenceType.OTHER,   # NEU
}
```

Mechanik (schon da via `OTHER`): Tagessoll → 0, Ist += 0, saldo-neutral, kein
Urlaubsabzug, unbezahlt. `create_absence` (absences.py:~317) setzt `type` aus dem
Verhalten → fließt automatisch, keine Calc-Änderung.

**Sync-Stellen** (Verhalten):
- `AbsenceReasonBehavior`-Enum + `BEHAVIOR_TO_ABSENCE_TYPE` (`models/absence.py`)
- Verhalten-Dropdown + Label-Map in `frontend/src/pages/Settings.tsx` (Abwesenheitsgründe)
- ggf. Validierungs-Whitelist im Pydantic-Schema (`AbsenceReasonCreate.base_behavior`)

### 3.2 Preset-Katalog (1-Klick aktivieren)

**Statische Frontend-Liste** kuratierter Vorlagen (kein DB-Seed, kein Tenant bekommt
ungefragt Gründe). Pro Preset: `name`, `color`, `base_behavior`,
`tracks_child_sick_limit`.

Startset (tunebar):

| Name | Verhalten | Kind-krank-Limit |
|---|---|---|
| Kind krank | `unpaid_free` | ja (Default 15/Jahr) |
| Todesfall naher Angehöriger | `paid_free` | – |
| Eigene Hochzeit | `paid_free` | – |
| Geburt eines Kindes | `paid_free` | – |
| Umzug (betrieblich) | `paid_free` | – |
| Arztbesuch (unvermeidbar) | `paid_free` | – |
| Pflege naher Angehöriger | `unpaid_free` | – |

„Aktivieren" ruft `POST /admin/absence-reasons` (bestehender Endpoint, um
`tracks_child_sick_limit` erweitert). Bereits per Name existierende Vorlagen werden
in der Liste als „aktiviert" markiert (Abgleich gegen `GET /admin/absence-reasons`).

Hinweistext: rechtliche Einordnung (bezahlt/unbezahlt) ist Sache des Betriebs —
Verhalten je Grund frei änderbar.

### 3.3 Kind-krank-Zähler + weiche Warnung

**Marker auf dem Grund:** `AbsenceReason.tracks_child_sick_limit` (bool, default
`false`). Vom Preset gesetzt; markiert *den* Kind-krank-Grund. Generisch gehalten,
in v1 nur von „Kind krank" genutzt.

**Per-MA-Anspruch:** `User.child_sick_days_per_year` (int, **nullable**). Leer →
Tenant-Default. Speichert **keine** Kinderzahl/Familiendaten (DSGVO-minimal) — HR
trägt den berechneten Jahresanspruch ein.

**Tenant-Default:** Setting-Key `child_sick_days_default` (int, Default **15**).
Umsetzung über bestehendes key/value `system_setting` → nur Aufnahme in
`admin_settings._ALLOWED_SETTINGS` + int-Validierung (≥0). **Keine** Schema-Änderung.

**Zählung (tagebasiert):** neuer Helper (z. B.
`calculation_service.child_sick_days_used(db, user, year)`) summiert Abwesenheits-
**Tage** im Kalenderjahr, deren `reason` `tracks_child_sick_limit=True` trägt —
exakt wie `absence_days` (half_day = 0,5, Beschäftigungsfenster berücksichtigt).
**Nicht** `Σh ÷ Tagessoll` (GLOSSAR-Tagesprinzip).

**Effektiver Cap:** `user.child_sick_days_per_year` ?? Tenant-`child_sick_days_default` ?? 15.

**Warnung (weich, non-blocking):** bei Buchung eines Kind-krank-Grunds wird die
resultierende Jahres-Summe berechnet; überschreitet sie den Cap, wird ein
`warnings`-Eintrag an die Response gehängt (gleiches Muster wie ArbZG-Warnungen,
`showArbzgWarnings`/`response.warnings`). Buchung geht **durch** (kein 400) — der
Fehltag muss erfassbar bleiben, auch wenn die Krankenkasse nicht mehr zahlt.

**Buchungspfade mit Warnung** (Parität wie sonstige `create_absence`-Guards):
- `absences.create_absence` (Direkt-Buchung)
- `admin_change_requests.review_change_request` (Absence-CR-Genehmigung, paralleler Buchungspfad)

Nicht betroffen: `company_closures` (bucht nur VACATION/OVERTIME),
`review_vacation_request` (nur VACATION).

### 3.4 UI

- **`Settings.tsx`** (Abwesenheitsgründe): `unpaid_free` im Verhalten-Dropdown +
  Label; neue „Vorlagen"-Sektion mit Aktivieren-Buttons; Feld
  `child_sick_days_default`.
- **`UserForm`**: Feld „Kind-krank-Tage/Jahr" (Zahl, leer = Tenant-Default als
  Platzhalter).
- **Abwesenheits-Buchung**: Reason-Picker existiert (#312); Kind krank erscheint nach
  Aktivierung; Warn-Toast bei Überschreitung über `showArbzgWarnings`-Pfad.
- **Admin-Übersicht** (nice-to-have): kompakte Anzeige „X/Y Kind-krank-Tage" im
  `GET /api/admin/users-overview` (#194) — Cap + Verbrauch je MA in einem Call.

### 3.5 Migration (eine)

Neue Alembic-Migration (Rev-ID ≤32 Zeichen):
- `absence_reasons.tracks_child_sick_limit` — `Boolean`, `nullable=False`,
  `server_default="false"`.
- `users.child_sick_days_per_year` — `Integer`, `nullable=True`.

Tenant-Default lebt in `system_setting` (key/value) → **kein** Schema.
Migration auf Host erstellen + committen vor Container-Rebuild. Up **und** Down.

### 3.6 DSGVO

Kind-krank ist kindsgesundheitsnah → sensibel. **Bereits abgedeckt** durch #312:
jede `reason_id` wird in **beiden** Kollegen-Feeds (`/absences/calendar`,
`/absences/team/upcoming`) für Nicht-Admins zu „absent" maskiert; Exporte maskieren
Custom-Reason-Label/Note außer bei explizitem `include_health_data`. **Keine neue
Maskier-Arbeit.** `child_sick_days_per_year` ist eine bloße Anspruchszahl (keine
Kinderdaten) — geringe Sensibilität, Zweck = §45-Anspruchsverwaltung.

---

## 4. Außerhalb Scope (v1)

- Payroll / Lohnbuchhaltung / Krankenkassen-Meldung (kein Payroll-Modul).
- Kinderzahl / Alleinerziehend-Status speichern (DSGVO-Minimierung; HR trägt den
  fertigen Anspruch ein).
- Journal (§16-Rechtsbeleg) bleibt bewusst basistyp-getrieben.
- Harte Blockade bei Limit-Überschreitung (bewusst weich).

---

## 5. Teststrategie

**Backend (pytest):**
- `unpaid_free → OTHER`: Buchung setzt `type=OTHER`; Soll wird um Tagessoll
  reduziert, Ist += 0, Saldo unverändert, **kein** Urlaubsabzug.
- Zähler `child_sick_days_used`: tagebasiert, half_day = 0,5, respektiert
  Beschäftigungsfenster; jahresweise korrekt.
- Weiche Warnung: feuert bei Überschreitung in `create_absence` **und**
  CR-Genehmigung; Buchung bleibt 2xx (kein 400).
- Cap-Fallback: MA-Feld → Tenant-Default → 15.
- Preset-Aktivierung: `POST /admin/absence-reasons` mit
  `tracks_child_sick_limit=True` legt Grund korrekt an.
- Multi-Tenant: neue Spalten tenant-scoped (F-026/RLS), Setting tenant-isoliert.

**Frontend (Vitest):** Verhalten-Dropdown enthält `unpaid_free`; Preset-Aktivieren
ruft korrekten POST; UserForm-Feld bindet `child_sick_days_per_year`.

**E2E (Playwright):** Kind-krank-Preset aktivieren → für MA buchen → über Cap →
Overage-Warnung sichtbar; Tag ist trotzdem erfasst.

---

## 6. Betroffene Dateien (Überblick)

**Backend:**
- `app/models/absence.py` — Enum + Map + `AbsenceReason.tracks_child_sick_limit`
- `app/models/user.py` — `child_sick_days_per_year`
- `app/schemas/…` — `AbsenceReason*`-Schema um Flag, `User*`-Schema um Feld
- `app/routers/absence_reasons.py` — Flag in create/update
- `app/routers/absences.py` — Warnung in `create_absence`
- `app/routers/admin_change_requests.py` — Warnung im CR-Buchungspfad
- `app/routers/admin_settings.py` — `child_sick_days_default` in `_ALLOWED_SETTINGS`
- `app/routers/admin_users.py` (`users-overview`) — Verbrauch/Cap (nice-to-have)
- `app/services/calculation_service.py` — `child_sick_days_used`-Helper
- `alembic/versions/…` — eine Migration

**Frontend:**
- `src/pages/Settings.tsx` — Dropdown + Preset-Sektion + Tenant-Default-Feld
- `src/components/…/UserForm` — Kind-krank-Tage-Feld
- Abwesenheits-Buchungskomponente — Warn-Toast (`showArbzgWarnings`)
- ggf. Admin-Übersicht — Verbrauchsanzeige

**Doku:**
- `docs/handbuch/*` + `frontend/src/components/DocViewer.tsx` (hardcoded In-App-Hilfe)
- CLAUDE.md — Regel-Ergänzung (neues Verhalten, Zähler-Buchungspfade)
