# XLS-Import Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin-seitige Import-Funktion für historische Zeiterfassungsdaten aus TimeRec-XLS-Dateien mit 3-Schritte-Wizard (Hochladen → Vorschau → Ergebnis).

**Architecture:** Backend-Parsing via xlrd (Python), zwei Endpoints (preview/confirm), neuer Router + Service. Frontend-Wizard mit lokalem State, bestehende UI-Patterns (useToast, useConfirm, Tailwind).

**Tech Stack:** Python/FastAPI + xlrd==1.2.0, React/TypeScript + Tailwind CSS + Lucide icons

**Spec:** `docs/superpowers/specs/2026-03-10-xls-import-design.md`

---

## Chunk 1: Backend — Service, Router, Wiring

### Task 1: xlrd==1.2.0 in requirements.txt pinnen

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: xlrd zur requirements.txt hinzufügen**

  Füge diese Zeile ans Ende von `backend/requirements.txt` hinzu:
  ```
  xlrd==1.2.0
  ```

- [ ] **Step 2: Im Container installieren**

  ```bash
  docker-compose exec backend pip install xlrd==1.2.0
  ```

  Erwartete Ausgabe: `Successfully installed xlrd-1.2.0`

- [ ] **Step 3: Commit**

  ```bash
  git add backend/requirements.txt
  git commit -m "chore: pin xlrd==1.2.0 for .xls import support"
  ```

---

### Task 2: XLS-Import-Service implementieren

**Files:**
- Create: `backend/app/services/xls_import_service.py`

- [ ] **Step 1: Service-Datei erstellen**

  Erstelle `backend/app/services/xls_import_service.py`:

  ```python
  """
  Service für den Import historischer Zeiterfassungsdaten aus TimeRec-XLS-Dateien.
  Dateiformat: Sheet "Zeiterfassung", Spalten: Datum, Tag, Total, Ein, Aus, Tagesnotiz
  """
  import xlrd
  from datetime import datetime, timedelta, date, time
  from typing import Optional
  from sqlalchemy.orm import Session
  from pydantic import BaseModel

  from app.models import TimeEntry, User
  from app.services.arbzg_utils import is_night_work

  EXCEL_EPOCH = datetime(1899, 12, 30)
  MAX_DAILY_NET_HOURS = 10.0   # §3 ArbZG
  MIN_REST_HOURS = 11.0        # §5 ArbZG
  MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


  class ImportedEntry(BaseModel):
      date: date
      start_time: time
      end_time: time
      break_minutes: int
      note: Optional[str]
      has_conflict: bool
      arbzg_warnings: list[str]


  class ImportResult(BaseModel):
      imported: int
      skipped: int
      overwritten: int
      warnings: list[str]


  def _excel_serial_to_datetime(serial: float) -> datetime:
      """Konvertiert Excel-Serial-Datetime zu Python-datetime. Basis: 1899-12-30."""
      return EXCEL_EPOCH + timedelta(days=serial)


  def _calc_break_minutes(start: time, end: time) -> int:
      """ArbZG §4: Pausen automatisch nach Brutto-Arbeitszeit berechnen."""
      gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
      gross_hours = gross_seconds / 3600.0
      if gross_hours > 9:
          return 45
      elif gross_hours > 6:
          return 30
      return 0


  def _check_arbzg(
      entry_date: date,
      start: time,
      end: time,
      break_min: int,
      prev_end_dt: Optional[datetime],
  ) -> list[str]:
      """ArbZG-Warnungen ermitteln (§3 Tageslimit, §5 Ruhezeit, §6 Nachtarbeit)."""
      warnings = []
      gross_seconds = (end.hour * 3600 + end.minute * 60) - (start.hour * 3600 + start.minute * 60)
      net_hours = (gross_seconds / 3600.0) - (break_min / 60.0)

      if net_hours > MAX_DAILY_NET_HOURS:
          warnings.append(f"§3 ArbZG: Tägliche Netto-Arbeitszeit {net_hours:.1f}h überschreitet 10h-Limit")

      if is_night_work(start, end):
          warnings.append("§6 ArbZG: Nachtarbeit erkannt (>2h zwischen 23:00–06:00)")

      if prev_end_dt is not None:
          curr_start_dt = datetime.combine(entry_date, start)
          rest_hours = (curr_start_dt - prev_end_dt).total_seconds() / 3600.0
          if rest_hours < MIN_REST_HOURS:
              warnings.append(
                  f"§5 ArbZG: Ruhezeit {rest_hours:.1f}h unterschreitet 11h-Minimum "
                  f"(Vorletzter Eintrag endete {prev_end_dt.strftime('%d.%m %H:%M')})"
              )

      return warnings


  def parse_xls(file_bytes: bytes, user_id, db: Session) -> list[ImportedEntry]:
      """
      Parst eine TimeRec-XLS-Datei und gibt ImportedEntry-Liste zurück.
      Ermittelt Konflikte (user_id+date+start_time) und ArbZG-Warnungen.

      Raises ValueError bei ungültigem Format oder fehlenden Daten.
      """
      if len(file_bytes) > MAX_FILE_SIZE_BYTES:
          raise ValueError("Datei zu groß (max. 5 MB)")

      try:
          wb = xlrd.open_workbook(file_contents=file_bytes)
      except xlrd.XLRDError as e:
          raise ValueError(f"Datei konnte nicht geöffnet werden: {e}")

      if "Zeiterfassung" not in wb.sheet_names():
          raise ValueError(
              f"Sheet 'Zeiterfassung' nicht gefunden. "
              f"Vorhandene Sheets: {', '.join(wb.sheet_names())}"
          )

      ws = wb.sheet_by_name("Zeiterfassung")
      entries: list[ImportedEntry] = []
      prev_end_dt: Optional[datetime] = None
      first_import_date: Optional[date] = None

      for row_idx in range(ws.nrows):
          # Datenzeile erkennbar durch numerischen ctype (3) in Ein-Spalte (D)
          if ws.cell(row_idx, 3).ctype != 3:
              continue

          ein_serial = ws.cell_value(row_idx, 3)
          aus_serial = ws.cell_value(row_idx, 4)
          notiz_raw = ws.cell_value(row_idx, 5)

          ein_dt = _excel_serial_to_datetime(ein_serial)
          aus_dt = _excel_serial_to_datetime(aus_serial)
          note = str(notiz_raw).strip() if notiz_raw else None

          entry_date = ein_dt.date()
          # Sekunden auf 0 setzen (XLS hat keine Sekunden)
          start_t = ein_dt.time().replace(second=0, microsecond=0)
          end_t = aus_dt.time().replace(second=0, microsecond=0)
          break_min = _calc_break_minutes(start_t, end_t)

          # §5-Check: Für den ersten Eintrag im Import letzten DB-Eintrag vor Import-Zeitraum holen
          check_prev = prev_end_dt
          if first_import_date is None:
              first_import_date = entry_date
              last_db_entry = (
                  db.query(TimeEntry)
                  .filter(TimeEntry.user_id == user_id, TimeEntry.date < entry_date)
                  .order_by(TimeEntry.date.desc(), TimeEntry.start_time.desc())
                  .first()
              )
              if last_db_entry and last_db_entry.end_time:
                  check_prev = datetime.combine(last_db_entry.date, last_db_entry.end_time)

          arbzg_warnings = _check_arbzg(entry_date, start_t, end_t, break_min, check_prev)

          # Konflikt-Check nach UniqueConstraint (user_id + date + start_time)
          existing = (
              db.query(TimeEntry)
              .filter(
                  TimeEntry.user_id == user_id,
                  TimeEntry.date == entry_date,
                  TimeEntry.start_time == start_t,
              )
              .first()
          )

          entries.append(ImportedEntry(
              date=entry_date,
              start_time=start_t,
              end_time=end_t,
              break_minutes=break_min,
              note=note,
              has_conflict=existing is not None,
              arbzg_warnings=arbzg_warnings,
          ))

          prev_end_dt = datetime.combine(entry_date, end_t)

      if not entries:
          raise ValueError("Keine Datenzeilen im Sheet 'Zeiterfassung' gefunden")

      return entries


  def execute_import(
      user_id,
      entries: list[ImportedEntry],
      overwrite: bool,
      db: Session,
      changed_by_id,
      filename: str,
  ) -> ImportResult:
      """
      Führt den Import durch. Bei overwrite=True werden Konflikte überschrieben,
      sonst übersprungen. Schreibt Audit-Log-Einträge.
      """
      from app.models import TimeEntryAuditLog

      imported = 0
      skipped = 0
      overwritten = 0
      all_warnings: list[str] = []

      for entry in entries:
          for w in entry.arbzg_warnings:
              all_warnings.append(f"{entry.date.strftime('%d.%m.%Y')}: {w}")

          existing = (
              db.query(TimeEntry)
              .filter(
                  TimeEntry.user_id == user_id,
                  TimeEntry.date == entry.date,
                  TimeEntry.start_time == entry.start_time,
              )
              .first()
          )

          if existing:
              if not overwrite:
                  skipped += 1
                  continue

              # Audit-Log: alter Zustand
              log = TimeEntryAuditLog(
                  time_entry_id=existing.id,
                  user_id=user_id,
                  changed_by=changed_by_id,
                  action="update",
                  source="import",
                  old_date=existing.date,
                  old_start_time=existing.start_time,
                  old_end_time=existing.end_time,
                  old_break_minutes=existing.break_minutes,
                  old_note=existing.note,
                  new_date=entry.date,
                  new_start_time=entry.start_time,
                  new_end_time=entry.end_time,
                  new_break_minutes=entry.break_minutes,
                  new_note=entry.note,
              )
              existing.end_time = entry.end_time
              existing.break_minutes = entry.break_minutes
              existing.note = entry.note
              db.add(log)
              overwritten += 1
          else:
              new_entry = TimeEntry(
                  user_id=user_id,
                  date=entry.date,
                  start_time=entry.start_time,
                  end_time=entry.end_time,
                  break_minutes=entry.break_minutes,
                  note=entry.note,
              )
              db.add(new_entry)
              db.flush()  # ID für Audit-Log

              log = TimeEntryAuditLog(
                  time_entry_id=new_entry.id,
                  user_id=user_id,
                  changed_by=changed_by_id,
                  action="create",
                  source="import",
                  new_date=entry.date,
                  new_start_time=entry.start_time,
                  new_end_time=entry.end_time,
                  new_break_minutes=entry.break_minutes,
                  new_note=entry.note,
              )
              db.add(log)
              imported += 1

      # Zusammenfassungs-Eintrag im Audit-Log (action="import", time_entry_id=None)
      target_user = db.query(User).filter(User.id == user_id).first()
      username = f"{target_user.first_name} {target_user.last_name}" if target_user else str(user_id)
      summary = (
          f"XLS-Import: {imported} neu, {overwritten} überschrieben, {skipped} übersprungen "
          f"| Benutzer: {username} | Datei: {filename}"
      )
      summary_log = TimeEntryAuditLog(
          time_entry_id=None,
          user_id=user_id,
          changed_by=changed_by_id,
          action="import",
          source="import",
          new_note=summary,
      )
      db.add(summary_log)
      db.commit()

      return ImportResult(
          imported=imported,
          skipped=skipped,
          overwritten=overwritten,
          warnings=all_warnings,
      )
  ```

- [ ] **Step 2: Syntaxcheck**

  ```bash
  docker-compose exec backend python -c "from app.services.xls_import_service import parse_xls, execute_import; print('OK')"
  ```

  Erwartete Ausgabe: `OK`

---

### Task 3: Import-Router implementieren

**Files:**
- Create: `backend/app/routers/import_xls.py`

- [ ] **Step 1: Router-Datei erstellen**

  Erstelle `backend/app/routers/import_xls.py`:

  ```python
  """
  Admin-Endpoints für den XLS-Import von historischen Zeiterfassungsdaten.
  POST /api/admin/import/preview  — Datei parsen, Vorschau zurückgeben
  POST /api/admin/import/confirm  — Import ausführen
  """
  from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
  from pydantic import BaseModel
  from sqlalchemy.orm import Session
  from typing import Optional
  import uuid

  from app.database import get_db
  from app.middleware.auth import require_admin
  from app.models import User
  from app.services.xls_import_service import (
      ImportedEntry,
      ImportResult,
      parse_xls,
      execute_import,
  )

  router = APIRouter(
      prefix="/api/admin/import",
      tags=["admin-import"],
      dependencies=[Depends(require_admin)],
  )


  class PreviewResponse(BaseModel):
      entries: list[ImportedEntry]
      total: int
      conflicts: int
      arbzg_warnings: int


  class ConfirmRequest(BaseModel):
      user_id: uuid.UUID
      overwrite: bool
      entries: list[ImportedEntry]
      filename: Optional[str] = "import.xls"


  @router.post("/preview", response_model=PreviewResponse)
  def preview_import(
      file: UploadFile = File(...),
      user_id: uuid.UUID = Form(...),
      db: Session = Depends(get_db),
      current_admin: User = Depends(require_admin),
  ):
      """
      Parst die hochgeladene XLS-Datei und gibt eine Vorschau der zu importierenden
      Einträge zurück, inklusive Konflikt- und ArbZG-Warnung-Flags.
      Führt noch KEINEN Import durch.
      """
      # Benutzer verifizieren
      target_user = db.query(User).filter(User.id == user_id).first()
      if not target_user:
          raise HTTPException(status_code=400, detail="Benutzer nicht gefunden")

      content = file.file.read()

      try:
          entries = parse_xls(content, user_id, db)
      except ValueError as e:
          raise HTTPException(status_code=400, detail=str(e))

      return PreviewResponse(
          entries=entries,
          total=len(entries),
          conflicts=sum(1 for e in entries if e.has_conflict),
          arbzg_warnings=sum(len(e.arbzg_warnings) for e in entries),
      )


  @router.post("/confirm", response_model=ImportResult)
  def confirm_import(
      body: ConfirmRequest,
      db: Session = Depends(get_db),
      current_admin: User = Depends(require_admin),
  ):
      """
      Führt den Import aus. Bei overwrite=True werden Konflikte überschrieben,
      sonst übersprungen. Schreibt Audit-Log-Einträge.
      """
      target_user = db.query(User).filter(User.id == body.user_id).first()
      if not target_user:
          raise HTTPException(status_code=400, detail="Benutzer nicht gefunden")

      return execute_import(
          user_id=body.user_id,
          entries=body.entries,
          overwrite=body.overwrite,
          db=db,
          changed_by_id=current_admin.id,
          filename=body.filename or "import.xls",
      )
  ```

- [ ] **Step 2: Syntaxcheck**

  ```bash
  docker-compose exec backend python -c "from app.routers.import_xls import router; print('OK')"
  ```

  Erwartete Ausgabe: `OK`

---

### Task 4: Router in main.py registrieren

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Import hinzufügen**

  In `backend/app/main.py`, Zeile 19, die bestehende Import-Zeile erweitern:

  Vorher:
  ```python
  from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests, journal
  ```

  Nachher:
  ```python
  from app.routers import auth, admin, time_entries, absences, dashboard, holidays, reports, change_requests, company_closures, error_logs, vacation_requests, journal
  from app.routers import import_xls
  ```

- [ ] **Step 2: Router registrieren**

  In `backend/app/main.py`, nach `app.include_router(journal.router)` (Zeile 164):

  ```python
  app.include_router(import_xls.router)
  ```

- [ ] **Step 3: Backend neu starten und Endpoint prüfen**

  ```bash
  docker-compose restart backend
  ```

  Dann im Browser öffnen: http://localhost:8000/docs

  Prüfen: Abschnitt `admin-import` mit `POST /api/admin/import/preview` und `POST /api/admin/import/confirm` sichtbar.

- [ ] **Step 4: Commit**

  ```bash
  git add backend/app/services/xls_import_service.py \
          backend/app/routers/import_xls.py \
          backend/app/main.py \
          backend/requirements.txt
  git commit -m "feat(backend): XLS-Import Service und Router

  - xls_import_service: Parsing, ArbZG-Checks, Konflikt-Erkennung, execute_import
  - import_xls router: /api/admin/import/preview + /confirm
  - xlrd==1.2.0 in requirements.txt
  "
  ```

---

## Chunk 2: Backend-Tests

### Task 5: Service-Unit-Tests

**Files:**
- Create: `backend/tests/test_xls_import_service.py`

Hinweis: Diese Tests laufen mit SQLite (kein Docker nötig). `conftest.py` stellt `db` und `test_user` bereit.

- [ ] **Step 1: Testdatei erstellen**

  Erstelle `backend/tests/test_xls_import_service.py`:

  ```python
  """Tests für xls_import_service: Parsing, ArbZG-Checks, execute_import."""
  import io
  import pytest
  from datetime import date, time, datetime
  from unittest.mock import MagicMock

  import xlrd
  import xlwt  # xlwt für .xls-Erstellung in Tests (xlrd 1.2 liest, xlwt schreibt)

  from app.models import TimeEntry
  from app.services.xls_import_service import (
      _calc_break_minutes,
      _check_arbzg,
      _excel_serial_to_datetime,
      parse_xls,
      execute_import,
      ImportedEntry,
      MAX_FILE_SIZE_BYTES,
  )


  # ── Hilfsfunktionen ──────────────────────────────────────────────────────────

  def _make_xls_bytes(rows: list[list]) -> bytes:
      """Erstellt eine minimale XLS-Datei mit Sheet 'Zeiterfassung'."""
      wb = xlwt.Workbook()
      ws = wb.add_sheet("Zeiterfassung")
      date_style = xlwt.easyxf(num_format_str="DD.MM.YYYY HH:MM")
      for row_idx, row in enumerate(rows):
          for col_idx, val in enumerate(row):
              if isinstance(val, datetime):
                  ws.write(row_idx, col_idx, val, date_style)
              else:
                  ws.write(row_idx, col_idx, val)
      buf = io.BytesIO()
      wb.save(buf)
      return buf.getvalue()


  def _dt(year, month, day, hour, minute) -> datetime:
      return datetime(year, month, day, hour, minute)


  def _make_data_row(ein_dt: datetime, aus_dt: datetime, notiz: str = ""):
      """Eine gültige Datenzeile für das Sheet."""
      return ["12.01", "Mo", "05:30", ein_dt, aus_dt, notiz]


  # ── _calc_break_minutes ───────────────────────────────────────────────────────

  def test_break_under_6h_is_0():
      assert _calc_break_minutes(time(8, 0), time(13, 59)) == 0


  def test_break_exactly_6h_is_0():
      assert _calc_break_minutes(time(8, 0), time(14, 0)) == 0


  def test_break_over_6h_is_30():
      assert _calc_break_minutes(time(8, 0), time(14, 1)) == 30


  def test_break_exactly_9h_is_30():
      # Grenze: exakt 9h brutto → noch 30min (>9h = 45min)
      assert _calc_break_minutes(time(7, 0), time(16, 0)) == 30


  def test_break_over_9h_is_45():
      assert _calc_break_minutes(time(7, 0), time(16, 1)) == 45


  # ── _check_arbzg ─────────────────────────────────────────────────────────────

  def test_no_warnings_for_normal_entry():
      warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, None)
      assert warnings == []


  def test_warning_for_over_10h():
      # §3 prüft auf Netto-Stunden (brutto - pause).
      # 7:00–18:30 = 11.5h brutto, 45min Pause → 10.75h netto > 10h → §3-Warnung
      warnings = _check_arbzg(date(2026, 1, 12), time(7, 0), time(18, 30), 45, None)
      assert any("§3" in w for w in warnings)


  def test_warning_for_night_work():
      # 22:00–06:00 → Nachtarbeit
      warnings = _check_arbzg(date(2026, 1, 12), time(22, 0), time(6, 0), 0, None)
      assert any("§6" in w for w in warnings)


  def test_warning_for_insufficient_rest():
      prev_end = datetime(2026, 1, 11, 23, 0)  # Vortag 23:00
      # Heutiger Start 8:00 → Ruhezeit 9h < 11h → Warnung
      warnings = _check_arbzg(date(2026, 1, 12), time(8, 0), time(14, 0), 30, prev_end)
      assert any("§5" in w for w in warnings)


  def test_no_rest_warning_for_sufficient_rest():
      prev_end = datetime(2026, 1, 11, 18, 0)  # Vortag 18:00
      # Heutiger Start 7:15 → Ruhezeit 13.25h > 11h → keine Warnung
      warnings = _check_arbzg(date(2026, 1, 12), time(7, 15), time(12, 45), 30, prev_end)
      assert not any("§5" in w for w in warnings)


  # ── parse_xls ────────────────────────────────────────────────────────────────

  def test_parse_xls_extracts_data_rows(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          ["W03", "", "", "", "", ""],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
          _make_data_row(_dt(2026, 1, 14, 7, 15), _dt(2026, 1, 14, 14, 0)),
          ["Total:", "", "11:15", "", "", ""],
          ["", "", "", "", "", ""],
      ]
      xls_bytes = _make_xls_bytes(rows)
      entries = parse_xls(xls_bytes, test_user.id, db)
      assert len(entries) == 2
      assert entries[0].date == date(2026, 1, 12)
      assert entries[0].start_time == time(7, 15)
      assert entries[0].end_time == time(12, 45)


  def test_parse_xls_calculates_breaks(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 14, 0)),  # 6h45 > 6h → 30min
      ]
      entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
      assert entries[0].break_minutes == 30


  def test_parse_xls_detects_conflict(db, test_user):
      # Vorhandenen Eintrag in DB anlegen
      existing = TimeEntry(
          user_id=test_user.id,
          date=date(2026, 1, 12),
          start_time=time(7, 15),
          end_time=time(12, 45),
          break_minutes=30,
      )
      db.add(existing)
      db.commit()

      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
      ]
      entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
      assert entries[0].has_conflict is True


  def test_parse_xls_no_conflict_for_new_entry(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45)),
      ]
      entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
      assert entries[0].has_conflict is False


  def test_parse_xls_wrong_sheet_raises(db, test_user):
      wb = xlwt.Workbook()
      wb.add_sheet("FalschesSheet")
      buf = io.BytesIO()
      wb.save(buf)
      with pytest.raises(ValueError, match="Sheet 'Zeiterfassung' nicht gefunden"):
          parse_xls(buf.getvalue(), test_user.id, db)


  def test_parse_xls_empty_sheet_raises(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          ["Total:", "", "00:00", "", "", ""],
      ]
      with pytest.raises(ValueError, match="Keine Datenzeilen"):
          parse_xls(_make_xls_bytes(rows), test_user.id, db)


  def test_parse_xls_file_too_large_raises(db, test_user):
      with pytest.raises(ValueError, match="zu groß"):
          parse_xls(b"x" * (MAX_FILE_SIZE_BYTES + 1), test_user.id, db)


  def test_parse_xls_includes_note(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), "Arzttermin"),
      ]
      entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
      assert entries[0].note == "Arzttermin"


  def test_parse_xls_empty_note_is_none(db, test_user):
      rows = [
          ["Datum", "Tag", "Total", "Ein", "Aus", "Tagesnotiz"],
          _make_data_row(_dt(2026, 1, 12, 7, 15), _dt(2026, 1, 12, 12, 45), ""),
      ]
      entries = parse_xls(_make_xls_bytes(rows), test_user.id, db)
      assert entries[0].note is None


  # ── execute_import ────────────────────────────────────────────────────────────

  def _make_entries(n=1) -> list[ImportedEntry]:
      return [
          ImportedEntry(
              date=date(2026, 1, 12 + i),
              start_time=time(7, 15),
              end_time=time(12, 45),
              break_minutes=30,
              note=None,
              has_conflict=False,
              arbzg_warnings=[],
          )
          for i in range(n)
      ]


  def test_execute_import_creates_entries(db, test_user, test_admin):
      entries = _make_entries(2)
      result = execute_import(test_user.id, entries, overwrite=False, db=db,
                              changed_by_id=test_admin.id, filename="test.xls")
      assert result.imported == 2
      assert result.skipped == 0
      assert result.overwritten == 0
      db_entries = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id).all()
      assert len(db_entries) == 2


  def test_execute_import_skips_conflict_without_overwrite(db, test_user, test_admin):
      # Vorhandener Eintrag
      existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                           start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
      db.add(existing)
      db.commit()

      entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                               end_time=time(13, 0), break_minutes=30, note=None,
                               has_conflict=True, arbzg_warnings=[])]
      result = execute_import(test_user.id, entries, overwrite=False, db=db,
                              changed_by_id=test_admin.id, filename="test.xls")
      assert result.skipped == 1
      assert result.imported == 0
      # Bestehender Eintrag unverändert
      db.refresh(existing)
      assert existing.end_time == time(12, 45)


  def test_execute_import_overwrites_conflict(db, test_user, test_admin):
      existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                           start_time=time(7, 15), end_time=time(12, 45), break_minutes=30)
      db.add(existing)
      db.commit()

      entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                               end_time=time(13, 0), break_minutes=30, note="updated",
                               has_conflict=True, arbzg_warnings=[])]
      result = execute_import(test_user.id, entries, overwrite=True, db=db,
                              changed_by_id=test_admin.id, filename="test.xls")
      assert result.overwritten == 1
      db.refresh(existing)
      assert existing.end_time == time(13, 0)
      assert existing.note == "updated"


  def test_execute_import_writes_audit_log(db, test_user, test_admin):
      from app.models import TimeEntryAuditLog
      entries = _make_entries(1)
      execute_import(test_user.id, entries, overwrite=False, db=db,
                     changed_by_id=test_admin.id, filename="test.xls")
      logs = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).all()
      # 1 create-Log + 1 summary-Log
      assert len(logs) == 2
      actions = {l.action for l in logs}
      assert "create" in actions
      assert "import" in actions


  def test_execute_import_audit_log_for_overwrite(db, test_user, test_admin):
      """Jeder überschriebene Eintrag erhält einen eigenen Audit-Log-Eintrag mit alten Werten."""
      from app.models import TimeEntryAuditLog
      existing = TimeEntry(user_id=test_user.id, date=date(2026, 1, 12),
                           start_time=time(7, 15), end_time=time(12, 45), break_minutes=30,
                           note="alt")
      db.add(existing)
      db.commit()

      entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                               end_time=time(13, 0), break_minutes=30, note="neu",
                               has_conflict=True, arbzg_warnings=[])]
      execute_import(test_user.id, entries, overwrite=True, db=db,
                     changed_by_id=test_admin.id, filename="test.xls")

      update_logs = db.query(TimeEntryAuditLog).filter(
          TimeEntryAuditLog.user_id == test_user.id,
          TimeEntryAuditLog.action == "update",
      ).all()
      assert len(update_logs) == 1
      assert update_logs[0].old_end_time == time(12, 45)  # alter Wert gespeichert
      assert update_logs[0].old_note == "alt"
      assert update_logs[0].new_note == "neu"


  def test_execute_import_returns_arbzg_warnings(db, test_user, test_admin):
      entries = [ImportedEntry(date=date(2026, 1, 12), start_time=time(7, 15),
                               end_time=time(12, 45), break_minutes=30, note=None,
                               has_conflict=False, arbzg_warnings=["§3 ArbZG: Test-Warnung"])]
      result = execute_import(test_user.id, entries, overwrite=False, db=db,
                              changed_by_id=test_admin.id, filename="test.xls")
      assert len(result.warnings) == 1
      assert "§3" in result.warnings[0]
  ```

- [ ] **Step 2: xlwt für Tests installieren (nur Test-Dependency)**

  `xlwt` wird benötigt, um .xls-Testdateien zu erzeugen. Da `xlrd==1.2.0` .xls liest und xlwt .xls schreibt:

  ```bash
  docker-compose exec backend pip install xlwt
  ```

  Füge in `requirements.txt` hinzu:
  ```
  xlwt==1.3.0
  ```

- [ ] **Step 3: Tests ohne Syntax-Fehler laden**

  ```bash
  docker-compose exec backend pytest tests/test_xls_import_service.py --collect-only 2>&1 | tail -10
  ```

  Erwartete Ausgabe: Alle Tests aufgelistet (z.B. `20 tests collected`), kein `ERROR` beim Sammeln.

- [ ] **Step 4: Alle Tests ausführen — alle müssen passen**

  ```bash
  docker-compose exec backend pytest tests/test_xls_import_service.py -v
  ```

  Erwartete Ausgabe: Alle Tests `PASSED`. Kein `FAILED` oder `ERROR`.

- [ ] **Step 5: Gesamte Test-Suite prüfen (keine Regressionen)**

  ```bash
  docker-compose exec backend pytest tests/ -v --tb=short 2>&1 | tail -20
  ```

  Erwartete Ausgabe: Alle vorhandenen Tests weiterhin `PASSED`.

- [ ] **Step 6: Commit**

  ```bash
  git add backend/tests/test_xls_import_service.py backend/requirements.txt
  git commit -m "test(backend): Tests für xls_import_service

  - parse_xls: Datei-Parsing, Konflikt-Erkennung, ArbZG-Warnungen, Edge-Cases
  - execute_import: create/skip/overwrite, Audit-Log, Warnungen
  - xlwt als Test-Dependency für XLS-Erstellung
  "
  ```

---

## Chunk 3: Frontend

### Task 6: ImportXls.tsx Seite erstellen

**Files:**
- Create: `frontend/src/pages/admin/ImportXls.tsx`

- [ ] **Step 1: Typen und API-Hilfsfunktionen definieren (oben in der Datei)**

  Erstelle `frontend/src/pages/admin/ImportXls.tsx`:

  ```tsx
  import { useState, useRef } from 'react';
  import { Upload, CheckCircle, AlertTriangle, XCircle, RotateCcw } from 'lucide-react';
  import apiClient from '../../api/client';
  import { useToast } from '../../contexts/ToastContext';
  import { useConfirm } from '../../hooks/useConfirm';
  import ConfirmDialog from '../../components/ConfirmDialog';

  // ── Typen ────────────────────────────────────────────────────────────────────

  interface ImportedEntry {
    date: string;           // "2026-01-12"
    start_time: string;     // "07:15:00"
    end_time: string;       // "12:45:00"
    break_minutes: number;
    note: string | null;
    has_conflict: boolean;
    arbzg_warnings: string[];
  }

  interface PreviewResponse {
    entries: ImportedEntry[];
    total: number;
    conflicts: number;
    arbzg_warnings: number;
  }

  interface ImportResult {
    imported: number;
    skipped: number;
    overwritten: number;
    warnings: string[];
  }

  interface User {
    id: string;
    first_name: string;
    last_name: string;
    username: string;
  }

  type WizardStep = 'upload' | 'preview' | 'result';

  // ── Hilfsfunktionen ──────────────────────────────────────────────────────────

  function formatTime(t: string): string {
    return t.slice(0, 5); // "07:15:00" → "07:15"
  }

  function formatDate(d: string): string {
    const [y, m, day] = d.split('-');
    return `${day}.${m}.${y}`;
  }

  function calcNetHours(start: string, end: string, breakMin: number): string {
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    const gross = (eh * 60 + em) - (sh * 60 + sm);
    const net = gross - breakMin;
    const h = Math.floor(net / 60);
    const m = net % 60;
    return `${h}:${String(m).padStart(2, '0')}`;
  }

  // ── Komponente ───────────────────────────────────────────────────────────────

  export default function ImportXls() {
    const { toast } = useToast();
    const confirm = useConfirm();

    const [step, setStep] = useState<WizardStep>('upload');
    const [users, setUsers] = useState<User[]>([]);
    const [usersLoaded, setUsersLoaded] = useState(false);
    const [selectedUserId, setSelectedUserId] = useState('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [preview, setPreview] = useState<PreviewResponse | null>(null);
    const [overwrite, setOverwrite] = useState(false);
    const [result, setResult] = useState<ImportResult | null>(null);
    const [warningsExpanded, setWarningsExpanded] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Benutzer laden beim ersten Render
    const loadUsers = async () => {
      if (usersLoaded) return;
      try {
        const res = await apiClient.get('/admin/users');
        setUsers(res.data.filter((u: User & { is_active: boolean }) => u.is_active));
        setUsersLoaded(true);
      } catch {
        toast.error('Benutzer konnten nicht geladen werden');
      }
    };

    // ── Schritt 1: Datei hochladen und analysieren ──────────────────────────

    const handleAnalyze = async () => {
      if (!selectedUserId || !selectedFile) return;
      setIsLoading(true);
      try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('user_id', selectedUserId);
        const res = await apiClient.post('/admin/import/preview', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        setPreview(res.data);
        setStep('preview');
      } catch (err: any) {
        const msg = err.response?.data?.detail || 'Fehler beim Analysieren der Datei';
        toast.error(msg);
      } finally {
        setIsLoading(false);
      }
    };

    // ── Schritt 2: Import bestätigen ────────────────────────────────────────

    const handleConfirm = async () => {
      if (!preview || !selectedUserId) return;

      if (overwrite && preview.conflicts > 0) {
        const ok = await confirm(
          `${preview.conflicts} vorhandene Einträge werden überschrieben. Fortfahren?`,
          { confirmLabel: 'Überschreiben', variant: 'danger' }
        );
        if (!ok) return;
      }

      setIsLoading(true);
      try {
        const res = await apiClient.post('/admin/import/confirm', {
          user_id: selectedUserId,
          overwrite,
          entries: preview.entries,
          filename: selectedFile?.name,
        });
        setResult(res.data);
        setStep('result');
      } catch (err: any) {
        const msg = err.response?.data?.detail || 'Fehler beim Import';
        toast.error(msg);
      } finally {
        setIsLoading(false);
      }
    };

    // ── Zurücksetzen ────────────────────────────────────────────────────────

    const handleReset = () => {
      setStep('upload');
      setSelectedFile(null);
      setPreview(null);
      setResult(null);
      setOverwrite(false);
      setWarningsExpanded(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // ── Step-Indicator ──────────────────────────────────────────────────────

    const steps = [
      { key: 'upload', label: 'Hochladen' },
      { key: 'preview', label: 'Vorschau' },
      { key: 'result', label: 'Ergebnis' },
    ] as const;

    const StepIndicator = () => (
      <div className="flex items-center mb-8">
        {steps.map((s, idx) => {
          const isActive = step === s.key;
          const isDone =
            (s.key === 'upload' && (step === 'preview' || step === 'result')) ||
            (s.key === 'preview' && step === 'result');
          return (
            <div key={s.key} className="flex items-center">
              <div className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                    ${isActive ? 'bg-primary text-white' : isDone ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}`}
                >
                  {isDone ? '✓' : idx + 1}
                </div>
                <span className={`text-sm font-medium ${isActive ? 'text-primary' : 'text-gray-500'}`}>
                  {s.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div className="h-0.5 w-10 bg-gray-200 mx-3" />
              )}
            </div>
          );
        })}
      </div>
    );

    // ── Render: Schritt 1 ───────────────────────────────────────────────────

    const renderUpload = () => (
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-6">Datei hochladen</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Benutzer <span className="text-red-500">*</span>
            </label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              value={selectedUserId}
              onChange={(e) => setSelectedUserId(e.target.value)}
              onFocus={loadUsers}
            >
              <option value="">Benutzer auswählen…</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.first_name} {u.last_name} ({u.username})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              XLS-Datei <span className="text-red-500">*</span>
            </label>
            <div
              className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files[0];
                if (f && f.name.endsWith('.xls')) setSelectedFile(f);
                else toast.error('Nur .xls-Dateien werden unterstützt');
              }}
            >
              <Upload size={24} className="mx-auto text-gray-400 mb-2" />
              {selectedFile ? (
                <p className="text-sm text-primary font-medium">{selectedFile.name}</p>
              ) : (
                <>
                  <p className="text-sm text-gray-500">Datei hierher ziehen oder klicken</p>
                  <p className="text-xs text-gray-400 mt-1">.xls (TimeRec-Format, max. 5 MB)</p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setSelectedFile(f);
                }}
              />
            </div>
          </div>
        </div>

        <button
          onClick={handleAnalyze}
          disabled={!selectedUserId || !selectedFile || isLoading}
          className="mt-6 px-6 py-2.5 bg-primary text-white rounded-lg text-sm font-medium
            hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Analysiere…' : 'Datei analysieren →'}
        </button>
      </div>
    );

    // ── Render: Schritt 2 ───────────────────────────────────────────────────

    const renderPreview = () => {
      if (!preview) return null;
      return (
        <div>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Vorschau</h2>

          {/* Zusammenfassung */}
          <div className="flex flex-wrap gap-4 mb-4 text-sm">
            <span className="text-gray-600">
              <strong>{preview.total}</strong> Einträge gefunden
            </span>
            {preview.conflicts > 0 && (
              <span className="text-red-600 font-medium">
                <XCircle size={14} className="inline mr-1" />
                {preview.conflicts} Konflikte
              </span>
            )}
            {preview.arbzg_warnings > 0 && (
              <span className="text-amber-600 font-medium">
                <AlertTriangle size={14} className="inline mr-1" />
                {preview.arbzg_warnings} ArbZG-Warnungen
              </span>
            )}
          </div>

          {/* Tabelle */}
          <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {['Datum', 'Von', 'Bis', 'Pause', 'Netto', 'Notiz', 'Status'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.entries.map((e, idx) => {
                  const hasWarning = e.arbzg_warnings.length > 0;
                  const rowBg = e.has_conflict ? 'bg-red-50' : hasWarning ? 'bg-amber-50' : '';
                  return (
                    <tr key={idx} className={`border-b border-gray-100 ${rowBg}`}>
                      <td className="px-3 py-2">{formatDate(e.date)}</td>
                      <td className="px-3 py-2">{formatTime(e.start_time)}</td>
                      <td className="px-3 py-2">{formatTime(e.end_time)}</td>
                      <td className="px-3 py-2">{e.break_minutes} min</td>
                      <td className="px-3 py-2">{calcNetHours(e.start_time, e.end_time, e.break_minutes)}</td>
                      <td className="px-3 py-2 text-gray-500">{e.note || '–'}</td>
                      <td className="px-3 py-2">
                        {e.has_conflict ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">
                            <XCircle size={11} /> Konflikt
                          </span>
                        ) : hasWarning ? (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 cursor-help"
                            title={e.arbzg_warnings.join('\n')}
                          >
                            <AlertTriangle size={11} /> ArbZG
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">
                            <CheckCircle size={11} /> Neu
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Überschreiben-Checkbox */}
          {preview.conflicts > 0 && (
            <label className="flex items-center gap-2 text-sm mb-6 cursor-pointer">
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <span className="text-gray-700">
                Konflikte überschreiben ({preview.conflicts} Einträge)
              </span>
            </label>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep('upload')}
              className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              ← Zurück
            </button>
            <button
              onClick={handleConfirm}
              disabled={isLoading}
              className="px-6 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {isLoading ? 'Importiere…' : 'Import bestätigen →'}
            </button>
          </div>
        </div>
      );
    };

    // ── Render: Schritt 3 ───────────────────────────────────────────────────

    const renderResult = () => {
      if (!result) return null;
      return (
        <div>
          <div className="flex items-center gap-2 mb-6">
            <CheckCircle size={22} className="text-green-500" />
            <h2 className="text-lg font-semibold text-gray-800">Import abgeschlossen</h2>
          </div>

          <div className="grid grid-cols-3 gap-4 max-w-sm mb-6">
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-700">{result.imported}</div>
              <div className="text-xs text-green-600 mt-1">Importiert</div>
            </div>
            <div className="bg-red-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-red-700">{result.overwritten}</div>
              <div className="text-xs text-red-600 mt-1">Überschrieben</div>
            </div>
            <div className="bg-amber-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-amber-700">{result.warnings.length}</div>
              <div className="text-xs text-amber-600 mt-1">ArbZG-Warn.</div>
            </div>
          </div>

          {result.skipped > 0 && (
            <p className="text-sm text-gray-500 mb-4">
              {result.skipped} Einträge übersprungen (Konflikt, overwrite=false).
            </p>
          )}

          {result.warnings.length > 0 && (
            <div className="mb-6">
              <button
                onClick={() => setWarningsExpanded(!warningsExpanded)}
                className="flex items-center gap-2 text-sm text-amber-700 font-medium mb-2"
              >
                <AlertTriangle size={14} />
                {result.warnings.length} ArbZG-Warnung(en)
                <span className="text-gray-400">{warningsExpanded ? '▲' : '▼'}</span>
              </button>
              {warningsExpanded && (
                <ul className="text-xs text-gray-600 space-y-1 pl-4 border-l-2 border-amber-200">
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <p className="text-sm text-gray-500 mb-6">
            Import wurde im Änderungsprotokoll gespeichert.
          </p>

          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <RotateCcw size={14} />
            Weiteren Import starten
          </button>
        </div>
      );
    };

    // ── Haupt-Render ────────────────────────────────────────────────────────

    return (
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">XLS-Import</h1>
          <p className="text-sm text-gray-500 mt-1">
            Historische Zeiterfassungsdaten aus TimeRec-XLS-Dateien importieren
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <StepIndicator />
          {step === 'upload' && renderUpload()}
          {step === 'preview' && renderPreview()}
          {step === 'result' && renderResult()}
        </div>

        <ConfirmDialog />
      </div>
    );
  }
  ```

- [ ] **Step 2: TypeScript-Fehler prüfen**

  ```bash
  cd praxiszeit/frontend && npx tsc --noEmit 2>&1 | head -20
  ```

  Erwartete Ausgabe: Keine Fehler (leere Ausgabe oder nur bereits bekannte Warnungen).

---

### Task 7: Layout.tsx und App.tsx aktualisieren

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Nav-Eintrag in Layout.tsx hinzufügen**

  In `frontend/src/components/Layout.tsx`:

  **1a) `Upload` zum bestehenden Lucide-Import hinzufügen.**
  Ersetze die letzte Zeile im Icon-Import-Block. Aktuell endet der Block mit `ClipboardCheck,`. Ändere:

  ```tsx
    ClipboardCheck,
  } from 'lucide-react';
  ```

  zu:

  ```tsx
    ClipboardCheck,
    Upload,
  } from 'lucide-react';
  ```

  **1b) Import-Eintrag im `adminNavItems`-Array ergänzen.**
  Ersetze den bestehenden letzten Eintrag vor `settings`:

  ```tsx
      { path: '/admin/vacation-approvals', label: 'Urlaubsanträge', icon: ClipboardCheck },
      { path: '/admin/settings', label: 'Einstellungen', icon: Settings },
  ```

  durch:

  ```tsx
      { path: '/admin/vacation-approvals', label: 'Urlaubsanträge', icon: ClipboardCheck },
      { path: '/admin/import', label: 'Import', icon: Upload },
      { path: '/admin/settings', label: 'Einstellungen', icon: Settings },
  ```

- [ ] **Step 2: Route in App.tsx registrieren**

  In `frontend/src/App.tsx`:

  Import-Statement ergänzen (nach den anderen Admin-Importen):
  ```tsx
  import ImportXls from './pages/admin/ImportXls';
  ```

  Route im Admin-Bereich hinzufügen (nach `vacation-approvals`-Route, vor `settings`):
  ```tsx
  <Route path="import" element={<ImportXls />} />
  ```

- [ ] **Step 3: Frontend-Build prüfen**

  ```bash
  cd praxiszeit/frontend && npm run build 2>&1 | tail -10
  ```

  Erwartete Ausgabe: `built in Xs` ohne Fehler.

- [ ] **Step 4: TypeScript vollständig prüfen**

  ```bash
  cd praxiszeit/frontend && npx tsc --noEmit 2>&1 | head -20
  ```

  Erwartete Ausgabe: Keine Fehler (leere Ausgabe oder nur bestehende Warnungen).

- [ ] **Step 5: Manuell testen**

  1. `docker-compose up -d` — System starten
  2. http://localhost im Browser öffnen
  3. Als Admin einloggen (username: `admin`)
  4. In der Sidebar: Eintrag **Import** sichtbar → anklicken
  5. Seite `/admin/import` lädt ohne Fehler
  6. Benutzer auswählen + XLS-Datei `E:/claude/zeiterfassung/import/timerec_20260101_20260131_e11_p03.xls` hochladen
  7. „Datei analysieren" → Vorschau mit 10 Einträgen erscheint
  8. „Import bestätigen" → Ergebnis-Seite mit Kennzahlen

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/pages/admin/ImportXls.tsx \
          frontend/src/components/Layout.tsx \
          frontend/src/App.tsx
  git commit -m "feat(frontend): XLS-Import Admin-Seite

  - ImportXls.tsx: 3-Schritte-Wizard (Upload/Vorschau/Ergebnis)
  - Konflikt-Erkennung, ArbZG-Warnungen, Overwrite-Option
  - ConfirmDialog vor Überschreiben
  - Layout.tsx: Nav-Eintrag 'Import'
  - App.tsx: Route /admin/import
  "
  ```

---

## Abschlusskontrolle

- [ ] `docker-compose exec backend pytest tests/ -v --tb=short` — alle Tests grün
- [ ] Frontend-Build fehlerfrei: `cd frontend && npm run build`
- [ ] Manuelle End-to-End-Prüfung mit beiden Import-Dateien:
  - `timerec_20260101_20260131_e11_p03.xls` → 10 Einträge, Januar 2026
  - `timerec_20260201_20260228_e11_p03.xls` → prüfen wie viele Einträge
- [ ] Audit-Log nach Import prüfen: http://localhost/admin/audit-log (Route existiert in App.tsx: `<Route path="audit-log" element={<AuditLog />} />`)
- [ ] TypeScript-Check: `cd frontend && npx tsc --noEmit` — keine Fehler
