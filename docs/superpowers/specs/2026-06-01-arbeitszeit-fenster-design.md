# Design-Spec: Arbeitszeit-Fenster (Frühstart-/Spät-Ende-Kappung) — #201

**Datum:** 2026-06-01
**Issue:** [#201](https://github.com/phash/praxiszeit/issues/201)
**Status:** Freigegeben (Brainstorming), bereit für Implementierungsplan

## 1. Problem / Motivation

Aktuell zählt jede gestempelte Minute als Arbeitszeit. Mitarbeitende können vor
dem offiziellen Arbeitsbeginn einstempeln (z. B. lange vor Praxisöffnung, „es
sind noch keine Patienten da") und sich so Arbeitszeit / freie Tage „erarbeiten".
Gewünscht ist eine **einstellbare Begrenzung**: Anwesenheit außerhalb eines
Soll-Fensters wird nicht angerechnet.

Im System existiert **kein** Konzept einer Soll-Uhrzeit — das User-Model kennt nur
Tagessoll-**Mengen** (`hours_monday..friday`), keine Start-/End-**Zeiten**. Dieses
Feature führt das Soll-Fenster ein.

## 2. Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|-------|--------------|
| Wo wird der Soll-Beginn definiert? | **Pro MA, pro Wochentag** (Mo–Fr), analog zu `hours_monday..friday`. |
| Umgang mit Zeit außerhalb? | **Kappen** (nicht anrechnen), durchsetzend. |
| Umfang | **Beide Enden:** Frühstart UND spätes Ausstempeln → Soll-**Beginn und -Ende** je Wochentag. |
| Kapp-Mechanismus | **Beim Schreiben kappen + Rohstempel bewahren** (Ansatz A). `net_hours`/Salden bleiben unverändert. |
| Umkleidezeiten | **Separat** (eigenes Folge-Issue). |
| Puffer | **Ein** konfigurierbarer Puffer für beide Enden (`work_window_grace_minutes`, Default 15). |

## 3. Ziele / Nicht-Ziele

**Ziele**
- Pro MA je Wochentag ein optionales Soll-Fenster `[Beginn, Ende]`.
- Effektiv angerechnete Eintragszeit wird auf `[Beginn − Puffer, Ende + Puffer]` gekappt.
- Der tatsächlich gestempelte/eingegebene Wert bleibt nachvollziehbar (§16 ArbZG).
- Opt-in: ohne gesetzte Soll-Zeiten ändert sich nichts (volle Abwärtskompatibilität).

**Nicht-Ziele**
- Umkleidezeiten (separates Issue).
- Soll-Uhrzeiten als neue Quelle des Tagessolls (die bestehenden `hours_*` bleiben die Soll-Menge; das Fenster kappt nur das **Ist**).
- Wochenend-Fenster (vorerst nur Mo–Fr, konsistent mit dem bestehenden Tagesplan).

## 4. Datenmodell

### 4.1 `users` (Migration: 10 neue Spalten)
Nullable `Time`, flach (konsistent zu `hours_monday..friday`):
- `scheduled_start_monday … scheduled_start_friday`
- `scheduled_end_monday … scheduled_end_friday`

`NULL` an einem Tag (Start **oder** Ende) ⇒ an dieser Seite keine Kappung. Beide
NULL ⇒ kein Fenster an dem Tag.

### 4.2 `time_entries` (Migration: 2 neue Spalten)
Nullable `Time`:
- `raw_start_time`, `raw_end_time`

Werden **nur** gesetzt, wenn die Kappung die jeweilige Seite verändert hat
(sonst `NULL` = nicht gekappt). Dienen Transparenz/§16-Nachweis.

### 4.3 `system_settings` (kein Schema-Change — Key/Value)
- `work_window_grace_minutes` (Default `"15"`), tenant-scoped. Aufnahme in
  `_ALLOWED_SETTINGS` (`admin_settings.py`) + Validierung als int ≥ 0.

## 5. Kapp-Logik

Neuer Service `backend/app/services/work_window_service.py` (Vorbild
`special_days_service.py`):

```
get_scheduled_window(user, d: date) -> tuple[time | None, time | None]
    # liest scheduled_start_<wd> / scheduled_end_<wd> für den Wochentag von d.
    # Wochenende → (None, None).

clamp(user, d, start: time, end: time | None, grace_minutes: int)
    -> tuple[eff_start, eff_end, raw_start | None, raw_end | None]
    # soll_start, soll_end = get_scheduled_window(user, d)
    # eff_start = max(start, soll_start - grace)  falls soll_start gesetzt, sonst start
    # eff_end   = min(end,   soll_end   + grace)  falls soll_end  gesetzt & end gesetzt, sonst end
    # raw_start = start  nur wenn eff_start != start, sonst None
    # raw_end   = end    nur wenn eff_end   != end,   sonst None
```

Regeln:
- **Opt-in:** ist die jeweilige Soll-Seite NULL, bleibt die Zeit unverändert.
- **Komplett außerhalb** (z. B. Eintrag endet vor `soll_start − grace`): die
  Kappung kann `eff_start >= eff_end` erzeugen; `TimeEntry.net_hours` floored
  bereits auf `max(0, …)` → 0 angerechnete Stunden, Rohstempel bewahrt. Kein
  Sonderfehler.
- **`track_hours = False`** (keine Stundenzählung): Kappung **übersprungen**
  (kein Ist/`net_hours` relevant).
- **`exempt_from_arbzg`** (§18): Kappung gilt trotzdem — sie ist eine
  Anwesenheits-Anrechnungs-Policy, **kein** ArbZG-Check (orthogonal zu §18).

## 6. Integration der Schreibpfade

Der Clamp-Helper MUSS an **allen** eintrags-erzeugenden/-ändernden Pfaden sitzen
(CLAUDE.md „mehrere Stellen"-Muster — sonst Lücken):

| Pfad | Datei | Besonderheit |
|------|-------|--------------|
| Live-Einstempeln | `time_entries.py` `clock_in` | nur **Start** kappen (Ende offen) |
| Live-Ausstempeln | `time_entries.py` `clock_out` | **Ende** kappen (Start kam aus clock_in) |
| Manueller Eintrag | `time_entries.py` `create_time_entry` / `update` | Start + Ende |
| Admin-Eintrag | `admin_time_entries.py` create/update | Start + Ende |
| XLS-Import | `xls_import_service.py` | Start + Ende |
| Antrags-Genehmigung | `admin_change_requests.py` (materialisiert Eintrag) | Start + Ende |

Der Puffer wird je Tenant einmal gelesen (`work_window_grace_minutes`).

## 7. Frontend

- **`UserForm.tsx`:** je Wochentag (Mo–Fr) zwei Time-Inputs „Soll-Beginn" /
  „Soll-Ende" (optional, leer = kein Fenster), platziert beim Tagesplan-Bereich
  (`use_daily_schedule`). Werte in Create/Update-Payload aufnehmen; Schemas
  (`UserBase`/`UserUpdate`/`UserListResponse`) + `create_user`/`update_user`
  ergänzen.
- **`Settings.tsx`:** Number-Input „Puffer (Min.)" → `work_window_grace_minutes`.
- **Eintrags-Anzeige** (`TimeTracking.tsx`, `MonthlyJournal.tsx`): bei gesetztem
  `raw_start_time`/`raw_end_time` ein Hinweis „gestempelt HH:MM · angerechnet
  ab/bis HH:MM".
- **`StampWidget.tsx`:** dezenter Hinweis beim Einstempeln vor dem Fenster
  („wird erst ab HH:MM angerechnet"). Optional, nicht blockierend.

## 8. Tests

- `test_work_window_service.py` (SQLite-Unit): clamp vor/innerhalb/nach Fenster;
  nur-Start, nur-Ende, kein Fenster; Puffer-Grenzen (genau auf der Grenze);
  Wochenende; `track_hours=False` übersprungen; komplett-außerhalb → 0h + raw
  bewahrt.
- Integration: `clock_in`/`clock_out` kappen korrekt + setzen `raw_*`;
  `create`/admin/import-Pfad. `net_hours` rechnet mit gekappter Zeit; Salden
  (`get_monthly_actual`/`get_overtime_account`) unverändert gegenüber manuell
  gekappten Zeiten.
- Schema-/API-Roundtrip der neuen User-Felder.

## 9. Migration & Doku

- Migration(en): `users` (10 Spalten) + `time_entries` (2 Spalten). Gegen
  Prod-DB-Kopie testen (Projektregel), keine Bestandsdaten ändern (alle NULL →
  kein Verhalten ändert sich).
- `CLAUDE.md` (Kritische Regeln) + `docs/BACKEND-ARCHITEKTUR.md` (Berechnungs-/
  Schreibpfad-Modell) + Handbücher (`HANDBUCH-ADMIN`, ggf. `-MITARBEITER`) +
  In-App-Hilfe (`DocViewer.tsx`, hardcoded — beides pflegen).

## 10. Rechtlicher Hinweis (in die Doku übernehmen)

Das Nicht-Anrechnen dokumentierter Anwesenheit ist eine **Arbeitgeber-Policy**.
Der tatsächlich gestempelte Wert bleibt über `raw_start_time`/`raw_end_time`
nachvollziehbar (§16 ArbZG). Das Feature ist opt-in und nur aktiv, wenn Soll-
Zeiten gesetzt sind. Die arbeitsrechtliche Bewertung (was als Arbeitszeit gilt)
verantwortet der Betrieb.

## 11. Offene / spätere Punkte

- Getrennte Puffer für früh/spät (aktuell ein gemeinsamer) — bei Bedarf später.
- Wochenend-Fenster (Sa/So) — aktuell out of scope.
- Umkleidezeiten — eigenes Issue (arbeitsrechtlich eigenes Thema).
