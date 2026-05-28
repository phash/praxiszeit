# Spec: Betriebsferien bearbeitbar (Edit/PUT) + closure_id-FK

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #142

---

## Überblick

Betriebsferien lassen sich heute nur anlegen und löschen — bei einem Tippfehler muss der Admin alles löschen und neu erfassen. Dieses Feature ergänzt einen Bearbeiten-Endpunkt + UI und ersetzt die fragile Note-String-Verknüpfung der erzeugten Absences durch einen sauberen `closure_id`-Fremdschlüssel. Grundlage: `feedback/feedback_01.txt`, Punkt 4.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich **bestehende Betriebsferien (Name + Zeitraum) bearbeiten**, damit ich **Tippfehler korrigieren kann, ohne löschen und neu anlegen zu müssen**.

- [ ] **REQ-1**: Name und Start-/Enddatum bestehender Betriebsferien sind via UI änderbar.
- [ ] **REQ-2**: Bei Datumsänderung werden die erzeugten Abwesenheiten konsistent angepasst: neu hinzukommende Arbeitstage erhalten Absences, entfallene werden entfernt.
- [ ] **REQ-3**: Die Zuordnung Closure → Absences erfolgt über `closure_id` (FK), nicht über Note-String-Matching.

### Nicht-funktionale Anforderungen

- [ ] Sicherheit: nur Admins; alle Queries mit explizitem `tenant_id`-Filter (F-026).
- [ ] Datenintegrität: bestehende, abweichende MA-Einträge im Zeitraum werden nicht überschrieben (Skip-Logik wie beim Anlegen, `company_closures.py:118-123`).
- [ ] Migration abwärtskompatibel (Backfill der Altdaten).

### Out of Scope

- Wahl Urlaub vs. bezahlte Freistellung → #145 (baut hierauf auf).
- Rückwirkende Anpassung bereits genehmigter, abweichender Anträge im Zeitraum.

---

## Design

### Datenbank

```sql
ALTER TABLE absences ADD COLUMN closure_id UUID NULL
    REFERENCES company_closures(id) ON DELETE SET NULL;
CREATE INDEX ix_absences_closure_id ON absences(closure_id);
```

**Backfill** in der Migration: bestehende `VACATION`-Absences mit `note LIKE 'Betriebsferien: %'` dem passenden Closure (Name + Datum im Zeitraum, gleicher `tenant_id`) zuordnen.

**Migration:** `backend/alembic/versions/YYYY_MM_DD_HHMM-NNN_add_closure_id_to_absences.py` (Revision-ID ≤ 32 Zeichen).

### Backend (FastAPI)

**Betroffene Datei:** `backend/app/routers/company_closures.py`

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `PUT` | `/api/company-closures/{id}` | Admin | Name + Zeitraum ändern, Absences re-synchronisieren |

**Re-Sync-Logik bei `PUT`** (Refaktorierung von `create_closure`):
1. Soll-Arbeitstage des neuen Zeitraums berechnen (`_get_workdays`).
2. Bestehende Closure-Absences (`Absence.closure_id == closure.id`) laden.
3. Diff bilden: Tage entfernen, die nicht mehr im Zeitraum liegen; fehlende Arbeitstage anlegen (mit Skip-Logik bei Fremd-Absences); Name in `note` aktualisieren.
4. Bei Namensänderung: `note` der verbundenen Absences mitziehen (über FK, kein String-Match).

**Refactor `create_closure` / `delete_closure`:** Absences mit `closure_id=closure.id` erzeugen bzw. über `Absence.closure_id == closure_id` löschen statt Note-Pattern (`company_closures.py:190-203`).

**Cleanup (gleiche Datei, F-026):**
- `_get_holidays_for_range` (Z. 50): `PublicHoliday`-Query um `tenant_id == current_user.tenant_id` ergänzen (CLAUDE.md: PublicHoliday immer tenant-scoped).
- `list_closures` (Z. 61): `CompanyClosure`-Query um `tenant_id`-Filter ergänzen.

**Schema:** `CompanyClosureUpdate` (name, start_date, end_date) analog `CompanyClosureCreate`.

### Frontend (React/TypeScript)

**Betroffene Datei:** `frontend/src/pages/admin/AdminAbsences.tsx`

- Edit-Button je Betriebsferien-Eintrag → öffnet das bestehende `closureForm`, vorbefüllt.
- Submit ruft `PUT /api/company-closures/{id}`.
- Bestätigungshinweis bei Datumsänderung („betroffene Abwesenheiten werden angepasst").

---

## Tasks

### Backend
- [ ] **T-1**: Migration `add_closure_id_to_absences` (Spalte + Index + Backfill).
- [ ] **T-2**: `Absence`-Model um `closure_id` ergänzen.
- [ ] **T-3**: `create_closure` + `delete_closure` auf `closure_id`-FK umstellen.
- [ ] **T-4**: `PUT /api/company-closures/{id}` + `CompanyClosureUpdate`-Schema + Re-Sync-Logik.
- [ ] **T-5**: F-026-Cleanup in `_get_holidays_for_range` (Z. 50) und `list_closures` (Z. 61).

### Frontend
- [ ] **T-6**: Edit-Button + vorbefülltes Formular in `AdminAbsences.tsx`.

### Tests & Qualität
- [ ] **T-7**: Backend-Test: PUT verlängert/verkürzt Zeitraum → Absences korrekt angepasst; Fremd-Absences unberührt.
- [ ] **T-8**: Backend-Test: Löschen über `closure_id` entfernt genau die zugehörigen Absences (auch nach Namensänderung).
- [ ] **T-9**: E2E: Betriebsferien anlegen → bearbeiten → Liste/Absences stimmen.
- [ ] **T-10**: `npm run build` + Backend-Tests grün.

### Abschluss
- [ ] **T-11**: Spec aktualisieren, Commit & Push.

---

## Offene Fragen

1. Soll bei Verkürzung des Zeitraums geprüft werden, ob MA in den entfallenen Tagen inzwischen manuell gebucht haben (Konfliktwarnung)? → Vorschlag: nur Closure-eigene Absences entfernen, Fremdeinträge unberührt lassen (kein harter Konflikt).

---

## Notizen

- Die Note-String-Limitation ist im Code bereits dokumentiert (`company_closures.py:190-193`) — dieses Issue setzt die dort empfohlene FK-Lösung um.
- `affected_employees` in `CompanyClosureResponse` ist heute eine naive „alle aktiven MA"-Zählung (Z. 65-66); optional über `closure_id` exakt zählbar.
