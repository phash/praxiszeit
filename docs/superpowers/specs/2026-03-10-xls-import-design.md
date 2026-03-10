# XLS-Import für historische Zeiterfassungsdaten

**Datum:** 2026-03-10
**Status:** Genehmigt
**Bereich:** Admin-Funktion

---

## Übersicht

Admins können historische Zeiterfassungsdaten aus XLS-Dateien (TimeRec-App-Format) über eine neue Admin-Seite importieren. Der Import läuft in einem 3-Schritte-Wizard mit Vorschau vor dem Speichern. Bestehende Einträge können auf Wunsch überschrieben werden.

---

## XLS-Dateiformat (fix, nicht anpassbar)

**Dateiname-Muster:** `timerec_YYYYMMDD_YYYYMMDD_eXX_pXX.xls`
**Sheet-Name:** `Zeiterfassung`

| Spalte | Inhalt | Typ |
|--------|--------|-----|
| A (Datum) | TT.MM (z.B. `12.01`) | Text |
| B (Tag) | Wochentagskürzel (Mo, Di, ...) | Text |
| C (Total) | Gesamtdauer HH:MM | Text |
| D (Ein) | Excel-Serial-DateTime (Eingang) | Numeric (ctype=3) |
| E (Aus) | Excel-Serial-DateTime (Ausgang) | Numeric (ctype=3) |
| F (Tagesnotiz) | Optionale Notiz | Text |

**Datenzeilen** werden erkannt durch: `ctype == 3` in Spalte D (Ein).

**Zu überspringende Zeilen:** Header (`Datum`), Wochenzeilen (`W03`, `W04`…), Summary-Zeilen (`Total:`, `Delta W:`, `Delta M:`, `Tage:`, `Durchschnitt:`), Leerzeilen.

**Datum-Auflösung:** Vollständiges Datum aus dem Excel-Serial-Wert extrahiert (Basis: 1899-12-30), kein Jahr-Parsing aus Dateinamen nötig.

---

## Entscheidungen

| Thema | Entscheidung |
|-------|--------------|
| Pausenberechnung | ArbZG §4: >9h → 45 min, >6h → 30 min, sonst 0 min |
| ArbZG-Validierung | Warnen (nicht blockieren) — Verstöße im Log markiert |
| Dateien pro Import | Eine Datei |
| Workflow | 3-Schritte-Wizard mit Vorschau |
| Logging | Bestehender Audit-Log-Mechanismus |
| Navigation | Eigener Menüpunkt „Import" in der Admin-Navigation |
| Architektur | Backend-Parsing (Python/xlrd) |

---

## Architektur

### Backend

**Neuer Router:** `backend/app/routers/import_xls.py`
**Neuer Service:** `backend/app/services/xls_import_service.py`
**Einbindung:** `main.py` unter `/api/admin/import`, Admin-only

#### Endpoint 1: Preview

```
POST /api/admin/import/preview
Content-Type: multipart/form-data
Body: file=<XLS-Datei>, user_id=<UUID>
Auth: Admin only

Response 200:
{
  "entries": [ImportedEntry, ...],
  "total": 10,
  "conflicts": 2,
  "arbzg_warnings": 3
}

Response 400: Ungültiges Format / Sheet nicht gefunden / keine Datenzeilen
```

#### Endpoint 2: Confirm

```
POST /api/admin/import/confirm
Body: { "user_id": UUID, "entries": [...], "overwrite": bool }
Auth: Admin only

Response 200:
{
  "imported": 8,
  "skipped": 2,
  "overwritten": 2,
  "warnings": ["§3: Tageslimit überschritten am 15.01.2026"]
}
```

#### ImportedEntry-Schema

```python
class ImportedEntry(BaseModel):
    date: date
    start_time: time
    end_time: time
    break_minutes: int        # ArbZG §4 auto-berechnet
    note: str | None
    has_conflict: bool        # user_id + date + start_time existiert bereits
    arbzg_warnings: list[str] # z.B. ["§3: >10h Arbeitszeit"]
```

#### Parsing-Logik (`xls_import_service.py`)

- Excel-Serial → datetime via `datetime(1899,12,30) + timedelta(days=serial)`
- Netto-Dauer = (end_time - start_time) in Stunden
- `break_minutes`: netto >9h → 45, netto >6h → 30, sonst 0 (direkt im Service berechnet, unabhängig vom `break_validation_service` der für User-Requests zuständig ist)
- **Konflikt-Definition:** Eintrag mit gleichem `user_id + date + start_time` — entspricht dem bestehenden `UniqueConstraint` der DB. Zeitüberschneidungen mit abweichender Startzeit sind kein Konflikt (konsistent mit bestehender Admin-Logik).
- **ArbZG §5 (Ruhezeit):** Für den ersten Eintrag im Import wird der letzte existierende DB-Eintrag des Benutzers vor dem Import-Zeitraum abgefragt.
- ArbZG-Prüfung: §3 (>10h Brutto), §5 (Ruhezeit <11h zum zeitlich vorherigen Eintrag), §6 (Nachtarbeit)
- **Datei-Größenlimit:** Max. 5 MB — bei Überschreitung 400-Fehler

#### Audit-Log-Einträge

Nach erfolgreichem Import:
- Sammeleintrag: `XLS-Import: 8 neu, 2 überschrieben, 0 übersprungen | Benutzer: Manuel Klotz | Datei: timerec_20260101_20260131_e11_p03.xls`
- Pro überschriebenem Eintrag: eigener Eintrag mit alten Werten (Datum, Von, Bis)

### Frontend

**Neue Seite:** `frontend/src/pages/admin/ImportXls.tsx`
**Route:** `/admin/import`
**State:** Lokaler React-State (Wizard-Schritt + Preview-Daten), kein globaler Store

#### Schritt 1 — Hochladen

- Dropdown: Benutzerauswahl (bestehende Admin-API)
- File-Input: Drag-&-Drop + Klick, nur `.xls`
- Button „Datei analysieren" → ruft `/api/admin/import/preview` auf

#### Schritt 2 — Vorschau

- Step-Indicator (1 → **2** → 3)
- Zusammenfassung: Anzahl Einträge, Konflikte (rot), ArbZG-Warnungen (gelb)
- Tabelle: Datum, Von, Bis, Pause, Netto, Notiz, Status-Badge (Neu / Konflikt / ArbZG)
- Checkbox „Konflikte überschreiben" (nur sichtbar wenn `conflicts > 0`)
- Bei Klick auf „Import bestätigen" mit aktivierter Overwrite-Checkbox: `ConfirmDialog` mit Anzahl der betroffenen Einträge
- Buttons: „← Zurück" | „Import bestätigen →"

#### Schritt 3 — Ergebnis

- Drei Kennzahlen-Kacheln: Importiert (grün) / Überschrieben (rot) / ArbZG-Warnungen (gelb)
- ArbZG-Warnungsliste (wenn vorhanden): aufklappbare Detail-Liste mit allen Warnmeldungen
- Hinweis: „Import wurde im Audit-Log protokolliert"
- Button „Weiteren Import starten" (Reset auf Schritt 1)

#### Admin-Navigation

Neuer Eintrag „Import" in der bestehenden Admin-Sidebar/Navigation (nach bestehenden Einträgen).

---

## Fehlerbehandlung

| Fall | Verhalten |
|------|-----------|
| Kein Sheet `Zeiterfassung` | 400 + Toast-Fehlermeldung im Frontend |
| Kein gültiges XLS | 400 + Toast |
| Keine Datenzeilen gefunden | 400 + Toast |
| `user_id` nicht gefunden | 400 + Toast |
| Datei > 5 MB | 400 + Toast |
| Netzwerkfehler beim Confirm | Toast, Schritt 2 bleibt aktiv |
| Alle Einträge vorhanden, overwrite=false | Schritt 3 mit 0 importiert + Hinweis |

---

## Abhängigkeiten

- **Backend:** `xlrd==1.2.0` (muss explizit gepinnt werden — xlrd ≥ 2.0 unterstützt `.xls` nicht mehr), bestehender Audit-Log-Service
- **Frontend:** Bestehende `useToast()`, `useConfirm()`, Admin-User-API — keine neuen npm-Pakete

---

## Sicherheitshinweise

- **Admin-only:** Beide Endpoints sind auf Admin-Rolle beschränkt. Admins können für jeden Benutzer importieren (inkl. andere Admins).
- **Confirm-Endpoint vertraut Client-Daten:** Der `/confirm`-Endpoint nimmt die vom Client gesendeten Einträge entgegen (keine erneute Server-seitige XLS-Verarbeitung). Da der Endpoint Admin-only ist, wird dieses Risiko als akzeptabel eingestuft.

---

## Nicht im Scope

- Mehrere Dateien gleichzeitig
- Rückgängig machen eines Imports
- Mapping von `e11`/`p03` Dateiname-Codes auf Benutzer (Admin wählt Benutzer manuell)
- XLSX-Format (nur `.xls`)
