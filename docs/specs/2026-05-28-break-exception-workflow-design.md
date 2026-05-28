# Spec: „Pflicht-Pause nicht möglich" + konfigurierbarer Genehmigungsworkflow

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #144

---

## Überblick

Nicht von §18 ArbZG befreite Mitarbeiter sollen ausnahmsweise einen Eintrag ohne die gesetzlich geforderte Pause erfassen können, wenn die Pause nachweislich nicht möglich war — mit Pflicht-Begründung. Ob das sofort gilt (mit Dokumentation) oder eine Admin-Genehmigung erfordert, ist **pro Praxis konfigurierbar**. Grundlage: `feedback/feedback_01.txt`, Punkt 3.

---

## Requirements

### Funktionale Anforderungen

Als **Mitarbeiter** möchte ich **bei nicht möglicher Pflicht-Pause einen begründeten Ausnahme-Eintrag erfassen**, damit **die tatsächlich geleistete Zeit korrekt und nachvollziehbar dokumentiert ist**.

Als **Admin** möchte ich **steuern, ob solche Ausnahmen genehmigungspflichtig sind**, damit ich **die Kontrolle über ArbZG-Abweichungen behalte (4-Augen-Prinzip)**.

- [ ] **REQ-1**: Würde die Pausenprüfung fehlschlagen (>6h/<30min bzw. >9h/<45min), bietet die Zeiterfassung die Option „Pflicht-Pause war nicht möglich" an.
- [ ] **REQ-2**: Diese Option schaltet ein **Pflicht-Freitextfeld** (Begründung) frei; ohne Begründung kein Verzicht.
- [ ] **REQ-3**: Praxis-Einstellung `break_exception_requires_approval` (bool):
  - **true** → Eintrag wird genehmigungspflichtiger Antrag (Status `pending`), erst nach Admin-Freigabe wirksam; Ablehnung mit Grund.
  - **false** → Eintrag sofort gespeichert, Begründung persistiert, als ArbZG-Warnung + im Admin-Reporting/Audit-Log sichtbar.
- [ ] **REQ-4**: Begründung, Genehmiger und Zeitpunkt sind im Änderungsprotokoll nachvollziehbar.

### Nicht-funktionale Anforderungen

- [ ] Sicherheit/Compliance: Backend erzwingt Begründung (nicht nur Frontend); Audit-Trail vollständig.
- [ ] Audit-Source-Marker < 40 Zeichen (`time_entry_audit_logs.source` ist `varchar(40)`, Migration 037).
- [ ] Gilt nur für nicht-exempte MA (exempt → keine Prüfung, #141).

### Out of Scope

- Verhalten exempter MA (#141).
- Automatische arbeitsrechtliche Bewertung der Begründung.

---

## Design

### Grundlagen (verifiziert)

- Pausenprüfung: `backend/app/services/break_validation_service.py` (Backend, >540min⇒45, >360min⇒30); client-seitig in `TimeTracking.tsx:267-303`.
- Antrags-Infrastruktur wiederverwendbar: `ChangeRequest` (`models/change_request.py`) — `status` (pending/approved/rejected), `reason`, `reviewed_by`, `reviewed_at`, `rejection_reason`; Review-Endpunkte in `change_requests.py` / `admin_change_requests.py`.
- Einstellungen: `system_setting` + `admin_settings.py` (Pattern für neue Settings vorhanden, vgl. `holiday_state`).

### Architektur-Entscheidung (Antrag vs. Eintrag-Flag)

Empfehlung: **Hybrid über vorhandene Bausteine**, statt eines komplett neuen Antragstyps:

- **Eintrag-Flag (immer):** neues Feld `break_waiver_reason` (Text, nullable) auf `time_entries` — hält die Begründung am Eintrag. Audit-Source-Marker `break_waiver` (12 Zeichen).
- **Genehmigung (wenn `requires_approval=true`):** der zu erfassende Eintrag wird **nicht** direkt geschrieben, sondern als `ChangeRequest` (`request_type=CREATE`, `entry_kind="time_entry"`) mit `reason` = Begründung angelegt. Bei Genehmigung wird der Eintrag mit gesetztem `break_waiver_reason` materialisiert. Damit greift der bestehende CR-Approval-Flow (inkl. Precondition-Checks vor Status-Änderung, CLAUDE.md-Regel).

> Damit wird kein paralleler Workflow gebaut; die `requires_approval=true`-Variante nutzt exakt das CR-Approval-Muster.

### Datenbank

```sql
ALTER TABLE time_entries ADD COLUMN break_waiver_reason TEXT NULL;
-- system_setting: key='break_exception_requires_approval', value bool (Default false)
```

**Migration:** `backend/alembic/versions/YYYY_MM_DD_HHMM-NNN_add_break_waiver_reason.py` (Revision-ID ≤ 32 Zeichen).

### Backend (FastAPI)

- `break_validation_service` / Time-Entry-Endpunkte: wenn Prüfung fehlschlägt **und** ein gültiger `break_waiver_reason` mitgeliefert wird → je nach Setting entweder Eintrag mit Begründung zulassen (`requires_approval=false`) oder als CR anlegen (`true`).
- ArbZG-Warnung über `warnings`-Response (Frontend nutzt `showArbzgWarnings`).
- Neue Settings-Keys in `admin_settings.py` lesen/schreiben (Validierung bool).

### Frontend (React/TypeScript)

- `TimeTracking.tsx`: bei Pausen-Validierungsfehler statt hartem Block die Option „Pflicht-Pause war nicht möglich" + Begründungsfeld einblenden.
- Bei `requires_approval=true`: Hinweis „Eintrag wird zur Genehmigung eingereicht".
- Admin-Settings-Seite: Toggle `break_exception_requires_approval`.
- Genehmigung sichtbar im bestehenden Änderungsanträge-Bereich (ggf. Badge-Integration mit #140).

---

## Tasks

### Backend
- [ ] **T-1**: Migration `add_break_waiver_reason` + Setting-Key Default.
- [ ] **T-2**: `time_entries`-Model/Schema um `break_waiver_reason`.
- [ ] **T-3**: Setting-Read/Write in `admin_settings.py`.
- [ ] **T-4**: Validierungs-/Einreichungslogik (Flag-Pfad + CR-Pfad) in Time-Entry-Endpunkten + `break_validation_service`.
- [ ] **T-5**: Audit-Source-Marker `break_waiver`.

### Frontend
- [ ] **T-6**: „Pause nicht möglich"-Option + Pflicht-Begründungsfeld in `TimeTracking.tsx`.
- [ ] **T-7**: Settings-Toggle.

### Tests & Qualität
- [ ] **T-8**: Backend-Test: `requires_approval=false` → Eintrag mit Begründung gespeichert + Warnung; ohne Begründung → Fehler.
- [ ] **T-9**: Backend-Test: `requires_approval=true` → CR `pending`, Genehmigung materialisiert Eintrag.
- [ ] **T-10**: E2E für beide Konfigurationen.
- [ ] **T-11**: Builds/Tests grün.

### Abschluss
- [ ] **T-12**: Spec aktualisieren, Commit & Push.

---

## Offene Fragen

1. Soll die Begründung auch im MA-/Admin-Export erscheinen? → Vorschlag: ja, als Notizspalte.
2. Reicht ein globaler Toggle, oder pro Mitarbeitergruppe? → Start: global pro Praxis (YAGNI).

---

## Notizen

- **Rechtsnatur des Waivers (A-M1):** Die §4-ArbZG-Pausenpflicht ist vom Arbeitnehmer **nicht** abdingbar. Der Break-Waiver ist daher **keine rechtliche Erlaubnis**, sondern die auditierte Dokumentation eines §4-Verstoßes (Beweis-/Nachvollziehbarkeitszweck) — die Pflicht bleibt bestehen. UI-Text in `TimeTracking.tsx` stellt dies klar.
- Abgrenzung zu #141: Dieses Feature betrifft **nicht-exempte** MA; exempte MA durchlaufen die Prüfung gar nicht.
- CR-Approval-Precondition-Checks vor Status-Änderung beachten (Race-Condition-Fix, CLAUDE.md).
