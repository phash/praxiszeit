# Unified Feedback (mrd-report-1) — PraxisZeit Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PraxisZeit reports bugs/feedback/server errors through protocol `mrd-report-1` into the central pzweb tracker, with sanitizing, an exact preview, "Als Datei speichern" and three in-app entry points plus the Windows setup assistant (issue #557).

**Architecture:** The FastAPI backend stays the proxy. `POST /api/feedback/preview` builds the complete payload server-side (context block, sanitized log extract, server fields) and returns it; the dialog shows it; `POST /api/feedback/send` receives exactly the previewed title/description back, re-sanitizes them (idempotent, so unchanged), adds the reporting key and forwards to `{REPORT_BASE}/v1/reports` (or legacy `/v1/bugs` while no key is configured). The sanitizer is a copy of the pzweb reference module plus PraxisZeit rules kept in a JSON file that the C# setup reads as well.

**Tech Stack:** Python 3.12 / FastAPI / httpx / SQLAlchemy (SQLite unit tests), React 18 + TypeScript + vitest/RTL + Playwright, .NET 10 / Avalonia 12 / xunit + FluentAssertions (`installer/setup`).

**Spec:** `/home/manuel/claude/pzweb/docs/superpowers/specs/2026-11-17-unified-feedback-design.md`, protocol contract `/home/manuel/claude/pzweb/docs/protocols/mrd-report-1/README.md` (pzweb branch `feat/unified-feedback`, commit `0dcfa32`, PR #127), master plan `/home/manuel/claude/pzweb/docs/superpowers/plans/2026-11-17-unified-feedback-master.md` (7-point client contract + review protocol). Issue: phash/praxiszeit#557.

## Global Constraints

**Fixed decisions (do not reopen):**
- Product slug `praxiszeit`, product kind `other` (screenshots allowed, no server patient gate) — the client still sanitizes every text it sends.
- Protocol id exactly `mrd-report-1`. Endpoint `POST {REPORT_BASE}/v1/reports`, multipart, all text values as form fields.
- `REPORT_BASE` default `https://report.mr-development.de` (setting `FEEDBACK_REPORT_BASE_URL`). Single fallback to `https://praxiszeit.mr-development.de`, **only** on a DNS or TLS error, **at most once**; never on an HTTP status, connection reset or timeout. Both hosts in a dedicated report allowlist `REPORT_ALLOWED_HOSTS = {"report.mr-development.de", "praxiszeit.mr-development.de"}`; the base-URL validator rejects anything else (bare `https://` origin, no path/query/fragment).
- Reporting key from setting `FEEDBACK_REPORT_KEY` (TOML `[feedback] report_key`, env `FEEDBACK_REPORT_KEY`), default empty. Empty → legacy transport `POST {FEEDBACK_SERVER_URL}/v1/bugs` (today's behaviour: `license_id` required, `"beta"` in BETA_MODE, 400 without license outside beta). The key is never written to any log, error message, preview or saved file; preview shows `mrk_praxiszeit_… (nicht angezeigt)`.
- `license_id` optional field = active license `customer_id`, `"beta"` in BETA_MODE without license, omitted otherwise (mrd-report-1 never fails for a missing license).
- `install_id`: UUIDv4 created once, stored in `system_settings` key `report_install_id` under the default tenant `00000000-0000-0000-0000-000000000001` (same pattern as the backup settings in `backup_service._set_setting`); survives updates on native and Docker because it lives in the database.
- Sanitizer: Python port = verbatim copy of the text part of pzweb `backend/app/core/report_sanitize.py` (commit `0dcfa32`); copy of `sanitize-vectors.json` (199 cases, 47 rules) at `backend/tests/data/mrd-report-1/sanitize-vectors.json`; all vectors must pass. PraxisZeit-specific rules (Task 2) on top.
- Log extracts never contain user free-text fields: sources are only `error_logs` (message/traceback, already value-free) and, on native installs, the tail of `logs/praxiszeit.log` and `logs/service-stderr.log`; every line passes the PraxisZeit sanitizer, which masks time-entry notes/reasons and person names in log formats.
- Preview = sent: the description and title sent are exactly the previewed strings (Task 7 justifies the re-send design). Sanitize **once over the fully composed description** and separately over the title, never part by part.
- Limits: title ≤ 200, description ≤ 20000 characters after sanitizing; user free text ≤ 4000; log extract ≤ 200 lines; outbound timeout ≤ 15 s total (including the fallback).
- Entry points: (1) FeedbackDialog from the help panel, all users, kinds „Fehler“ (`bug`) / „Feedback“ (`feedback`), optional contact e-mail, log-extract checkbox admin-only; (2) admin-only toast action „An Entwickler schicken“ on 5xx error toasts (kind `crash`); (3) „An Entwickler schicken“ per `error_logs` row on „Fehler-Monitoring“ (kind `crash`). On 201 show `ref` and the link `https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit` („Bekannte Probleme ansehen“). On every failure: „Senden fehlgeschlagen – als Datei speichern?“ with download of the previewed payload; input is never discarded; no automatic retry.
- Windows setup/update assistant: own C# sanitizer port + vector test (`dotnet test`, run **locally** on CachyTop — testbox has no dotnet). Key from optional build constant `MrdReportKey`; without key only „Als Datei speichern“ + mail hint to `LicensePageViewModel.LicenseContact`.
- Docs: section „Problem melden“ on all CLAUDE.md doc-sync surfaces in this repo; pzweb `anleitung` is out of scope (follow-up in the PR). Outbound allowlist line `report.mr-development.de:443` in the install docs.
- Tests run on testbox via `tb-run` (backend in Docker as in CLAUDE.md); dotnet tests locally. Releases out of scope. PR at the end, merge only with Manuel's approval; never push to master.

**Plan decisions (made while planning, see final report):**
- Kind `crash` for the two program-proposed entry points (toast, error-log row); `bug`/`feedback` from the dialog. Non-admins can only send `bug`/`feedback`.
- Separate report allowlist instead of widening `updater._ALLOWED_UPDATE_HOSTS` (that list guards update tarball downloads).
- PraxisZeit rules use the shared token `<user>` for person names and a new token `<text>` for free text.
- Python copy contains only the text sanitizer (up to the line `# --- attachments ---`); the attachment scanner is server-only.
- Screenshot attachment (PNG/JPEG ≤ 5 MB, sent as `screenshot.png`/`screenshot.jpg`) for all users in the dialog; the log extract stays inside the description (spec 5.5), never as attachment.
- Upstream failures and transport errors reach the frontend as HTTP 502 `{"detail": …, "upstream_status": <int|null>}` so they never collide with the proxy's own 422/429.
- Setup `install_id` in `%ProgramData%\PraxisZeit\report-install-id` (fallback LocalApplicationData, then in-memory), `component=setup`.
- New UI copy uses the Sie-form (handbook rule), replacing the dialog's current du-form.

**Commands used in the steps:**
- `S` (sync to testbox): `rsync -a --delete --exclude node_modules --exclude .venv --exclude dist --exclude bin --exclude obj /home/manuel/claude/pz-mrd-report/ testbox:work/pz-mrd-report/`
- `BT <files>` (backend tests): after `S`, run on testbox inside `tb-run 'pz-mrd-report:pytest (cachytop)'` the CLAUDE.md "Backend Unit" `docker run … praxiszeit-backend python -m pytest …` line with `tests/` replaced by `<files>` (keep `-e TZ=Europe/Berlin`, `--user`, the `rm -f backend/test.db…` prefix). Build the image first with `docker build -t praxiszeit-backend backend` when it is missing or `requirements.txt` changed.
- `FT <file>` (one vitest file, < 30 s, allowed locally): `cd frontend && npx vitest run <file> --pool=threads`. Full vitest suite only on testbox: `tb-run 'pz-mrd-report:vitest (cachytop)' -- bash -lc 'cd ~/work/pz-mrd-report/frontend && npx vitest run --pool=threads --maxWorkers=2'` (in `node:20` container if `node_modules` is missing, see CLAUDE.md).
- `DT <filter>` (dotnet, local): `dotnet test /home/manuel/claude/pz-mrd-report/installer/setup/tests/PraxisZeit.Setup.Core.Tests/PraxisZeit.Setup.Core.Tests.csproj --filter "FullyQualifiedName~<filter>"`.

## Review Focus

1. **Offline practice server (no DNS / no internet):** both hosts fail with a DNS error → exactly two attempts, total ≤ 15 s, the dialog shows „Senden fehlgeschlagen – als Datei speichern?“ with the preview intact, and the saved file contains the previewed description. Tests: Task 6 `test_dns_error_on_both_hosts_tries_each_once`, Task 8 `shows save-file path when send fails with 502`.
2. **Key not configured yet (all installs until Manuel creates `mrk_praxiszeit_…`):** transport `legacy`, payload goes to `/v1/bugs` with `license_id` (`"beta"` in BETA_MODE), preview says so, contact e-mail note is shown. Tests: Task 6 `test_empty_key_uses_legacy_bugs_endpoint`, Task 7 `test_preview_reports_legacy_transport_without_key`.
3. **Log extract with employee names / time-entry notes:** real lines (`AUTH login_failed user=anna.schmidt`, pydantic `input_value='Arzttermin …'`, JSON `"note": "…"`, access-log `?search=Schmidt`) never reach the preview unmasked. Tests: Task 2 vector cases, Task 7 `test_preview_log_extract_masks_names_and_notes` (fixture `praxiszeit.log` in a temp `REPORT_LOG_DIR`).
4. **Report while the license is expired (read-only mode):** `LicenseReadOnlyMiddleware` blocks POST — `/api/feedback/` must be exempt so a practice in trouble can still report. Test: Task 7 `test_feedback_routes_work_in_read_only_mode`.
5. **Huge or odd log file (hundreds of MB, no newlines, binary/NUL bytes, cp1252):** only the last 256 KiB are read, ≤ 200 lines, each line ≤ 2000 chars, description ≤ 20000 after sanitizing, response well under a second. Tests: Task 4 `test_tail_reads_only_last_bytes_of_large_file`, `test_tail_handles_no_newlines_and_nul_bytes`; Task 5 `test_description_never_exceeds_limit_with_full_extract`.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/core/report_sanitize.py` (new) | Verbatim copy of the pzweb text sanitizer (`sanitize_report_text`, `find_patient_data`, `Rule`, `RULES`) |
| `backend/app/core/report_rules/praxiszeit-sanitize.json` (new) | PraxisZeit rules + cases, same schema as `sanitize-vectors.json`; read by Python and C# |
| `backend/app/core/report_sanitize_pz.py` (new) | `PZ_RULES`, `sanitize_praxiszeit_text` |
| `backend/app/services/report_install_id.py` (new) | Persistent `install_id` |
| `backend/app/services/report_log_extract.py` (new) | Log sources, bounded tail |
| `backend/app/services/report_payload.py` (new) | Server fields, context block, error context, preview/send field dict |
| `backend/app/services/report_client.py` (new) | Transport (mrd-report-1 / legacy), fallback, result mapping |
| `backend/app/config.py` | New settings, validators, TOML keys, `REPORT_ALLOWED_HOSTS` |
| `backend/app/routers/feedback.py` | `/preview`, `/send` (replaces `/report`) |
| `backend/app/middleware/license.py` | Exempt `/api/feedback/` |
| `frontend/src/api/feedback.ts` (new) | Typed API calls |
| `frontend/src/utils/reportFile.ts` (new) | TXT rendering + download of a preview |
| `frontend/src/components/FeedbackDialog.tsx` | Form → preview → result |
| `frontend/src/stores/reportStore.ts` (new), `frontend/src/components/ReportDialogHost.tsx` (new) | Last 5xx + global dialog for toast action |
| `frontend/src/contexts/ToastContext.tsx`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`, `frontend/src/pages/admin/ErrorMonitoring.tsx` | Toast action, 5xx recording, host mount, per-row button |
| `installer/setup/src/PraxisZeit.Setup.Core/Services/Reporting/*.cs` (new) | C# sanitizer, builder, tail, install id, sender, key |
| `installer/setup/src/PraxisZeit.Setup/ViewModels/DonePageViewModel.cs`, `Views/DonePageView.axaml`, `MainWindowViewModel.cs` | Setup UI |

---

### Task 1: Shared sanitizer port and vector conformance

**Files:**
- Create: `backend/app/core/report_sanitize.py`
- Create: `backend/tests/data/mrd-report-1/sanitize-vectors.json` (byte copy of pzweb `docs/protocols/mrd-report-1/sanitize-vectors.json` @ `0dcfa32`)
- Test: `backend/tests/test_report_sanitize_vectors.py`

**Interfaces:**
- Produces: `sanitize_report_text(text: str) -> str`, `find_patient_data(text: str) -> list[str]`, `normalize_report_text(text: str) -> str`, dataclass `Rule(name, category, pattern, replacement, description, flags=(), condition=None, patient_value_group=None)` with `.apply(text: str, hits: set[str] | None = None) -> str`, `RULES: tuple[Rule, ...]`, `MAX_PASSES = 4`.

- [ ] **Step 1: Copy the vectors file**

`git -C /home/manuel/claude/pzweb show 0dcfa32:docs/protocols/mrd-report-1/sanitize-vectors.json > backend/tests/data/mrd-report-1/sanitize-vectors.json`.

- [ ] **Step 2: Write the failing tests** in `test_report_sanitize_vectors.py`:

```python
VECTORS = json.loads((Path(__file__).parent / "data/mrd-report-1/sanitize-vectors.json").read_text("utf-8"))

def test_vector_file_is_mrd_report_1():
    assert VECTORS["protocol"] == "mrd-report-1"
    assert len(VECTORS["cases"]) >= 199 and len(VECTORS["rules"]) >= 47

def test_rule_table_matches_vector_file():
    # name, category, flags, pattern, replacement, condition, patient_value_group — in order
    assert [_rule_dict(r) for r in RULES] == [_published(r) for r in VECTORS["rules"]]

@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["id"])
def test_case(case):
    assert sanitize_report_text(case["input"]) == case["expected"]
    assert sanitize_report_text(case["expected"]) == case["expected"]
    assert bool(find_patient_data(case["input"])) is case["patient_data"]
    assert find_patient_data(case["expected"]) == []
```

- [ ] **Step 3: Run to verify failure** — `BT tests/test_report_sanitize_vectors.py` → FAIL (`ModuleNotFoundError: app.core.report_sanitize`).

- [ ] **Step 4: Create `report_sanitize.py`** = `git -C /home/manuel/claude/pzweb show 0dcfa32:backend/app/core/report_sanitize.py`, lines from the top up to (excluding) `# --- attachments ---`. Drop imports that become unused (`base64`, `binascii`, `bz2`, `io`, `lzma`, `zipfile`, `zlib`). Prepend one header line: source repo, path, commit `0dcfa32`, "update together with tests/data/mrd-report-1/sanitize-vectors.json". No other edits.

- [ ] **Step 5: Run** — `BT tests/test_report_sanitize_vectors.py` → all PASS (≥ 199 parametrized cases).

- [ ] **Step 6: Commit** — `git add backend/app/core/report_sanitize.py backend/tests/data/mrd-report-1 backend/tests/test_report_sanitize_vectors.py && git commit -m "feat(report): port mrd-report-1 sanitizer with shared vectors (#557)"`

---

### Task 2: PraxisZeit sanitizer rules

**Files:**
- Create: `backend/app/core/report_rules/praxiszeit-sanitize.json`
- Create: `backend/app/core/report_sanitize_pz.py`
- Test: `backend/tests/test_report_sanitize_pz.py`

**Interfaces:**
- Consumes: `Rule`, `sanitize_report_text`, `find_patient_data` (Task 1).
- Produces: `PZ_RULES: tuple[Rule, ...]` (loaded from the JSON `rules[]` via `Path(__file__).parent / "report_rules/praxiszeit-sanitize.json"`), `sanitize_praxiszeit_text(text: str) -> str`, `PZ_RULES_PATH: Path`. JSON schema = `sanitize-vectors.json` (`protocol`, `version`, `rules[]` with `name, category, flags, pattern, replacement, description`, `cases[]` with `id, input, expected, patient_data`).

`sanitize_praxiszeit_text`: `t = sanitize_report_text(text)`; then up to 4 times: apply every `PZ_RULES` rule in order, then `sanitize_report_text`; stop when unchanged.

Rules (patterns exactly; `flags` `["i"]` except the last):

| name | category | pattern | replacement |
|---|---|---|---|
| `pz_user_token` | person | `\b(user\|username\|user_name\|login)([ \t]*=[ \t]*)[^ \t\n,;]+` | `{1}{2}<user>` |
| `pz_person_line` | person | `\b(full_name\|display_name\|employee_name\|employee\|name)([ \t]*[=:][ \t]*)([^ \t\n"'<][^\n]*)` | `{1}{2}<user>` |
| `pz_text_quoted` | text | `(["'](?:note\|notes\|comment\|description\|input\|input_value\|reason\|break_waiver_reason\|sunday_exception_reason\|rejection_reason\|proposed_note\|original_note\|name\|full_name\|display_name\|first_name\|last_name\|title)["'][ \t]*:[ \t]*)("(?:[^"\\\n]\|\\.)*"\|'(?:[^'\\\n]\|\\.)*')` | `{1}<text>` |
| `pz_text_assign` | text | `\b(input_value\|note\|notes\|comment\|break_waiver_reason\|sunday_exception_reason)([ \t]*=[ \t]*)("(?:[^"\\\n]\|\\.)*"\|'(?:[^'\\\n]\|\\.)*')` | `{1}{2}<text>` |
| `pz_query_value` | text | `([?&][A-Za-z0-9_.\[\]-]{1,64}=)[^ \t\n&#"]+` | `{1}<text>` |

(`\|` above is a table escape for `|`.) `reason=` (unquoted, AUTH enum) stays readable on purpose.

- [ ] **Step 1: Write the JSON `cases[]`** (real PraxisZeit log formats; expected values verified against the reference sanitizer):

| id | input | expected |
|---|---|---|
| `pz-auth-login-failed` | `2026-11-18 08:15:02 WARNING praxiszeit.security: AUTH login_failed user=anna.schmidt reason=bad_password ip=192.168.178.20` | `… AUTH login_failed user=<user> reason=bad_password ip=<ip>` |
| `pz-auth-redacted` | `… AUTH login_failed user=an…#3f9a2c1b0d4e reason=unknown_user ip=10.0.0.5` | `… user=<user> reason=unknown_user ip=<ip>` |
| `pz-access-query` | `2026-11-18 08:16:00 INFO:     192.168.178.20:51234 - "GET /api/admin/users?search=Schmidt&include_inactive=true HTTP/1.1" 200` | `2026-11-18 08:16:00 INFO:     <ip>:51234 - "GET /api/admin/users?search=<text>&include_inactive=<text> HTTP/1.1" 200` |
| `pz-pydantic-input-value` | `  String should have at most 500 characters [type=string_too_long, input_value='Arzttermin bei Dr. Weber wegen Rücken', input_type=str]` | `  String should have at most 500 characters [type=string_too_long, input_value=<text>, input_type=str]` |
| `pz-pydantic-dict` | `{'type': 'string_too_long', 'loc': ('body', 'note'), 'msg': 'String should have at most 500 characters', 'input': 'Kind krank, Schule angerufen'}` | `{… 'msg': 'String should have at most 500 characters', 'input': <text>}` |
| `pz-json-note` | `{"date": "2026-11-18", "start_time": "08:00", "note": "Arzttermin Dr. Weber", "break_waiver_reason": "Notfallpatient"}` | `{"date": "2026-11-18", "start_time": "08:00", "note": <text>, "break_waiver_reason": <text>}` |
| `pz-json-escaped-quote` | `{"note": "Sie sagte \"Kind krank\" am Telefon", "id": 4}` | `{"note": <text>, "id": 4}` |
| `pz-full-name-line` | `2026-11-18 08:20:00 ERROR app.routers.time_entries: update failed full_name=Sarah Klein username=s.klein` | `2026-11-18 08:20:00 ERROR app.routers.time_entries: update failed full_name=<user>` |
| `pz-context-untouched` | `Fehler: HTTP 500 POST /api/time-entries — IntegrityError (23505 unique_violation)` | same as input |

(`…` in the table stands for the unchanged prefix; write the full strings in the JSON.) All cases `patient_data: false`.

- [ ] **Step 2: Write the failing tests:**

```python
@pytest.mark.parametrize("case", PZ["cases"], ids=lambda c: c["id"])
def test_pz_case(case):
    out = sanitize_praxiszeit_text(case["input"])
    assert out == case["expected"]
    assert sanitize_praxiszeit_text(out) == out

@pytest.mark.parametrize("case", SHARED["cases"], ids=lambda c: c["id"])
def test_pz_rules_keep_shared_guarantees(case):
    out = sanitize_praxiszeit_text(case["input"])
    assert sanitize_praxiszeit_text(out) == out
    assert find_patient_data(out) == []

def test_pz_rules_file_ships_inside_app_package():
    assert PZ_RULES_PATH.is_relative_to(Path(app.__file__).parent) and len(PZ_RULES) == 5
```

- [ ] **Step 3: Run** — `BT tests/test_report_sanitize_pz.py` → FAIL (module missing).
- [ ] **Step 4: Implement** `report_sanitize_pz.py` and the JSON `rules[]` per the table above.
- [ ] **Step 5: Run** — `BT tests/test_report_sanitize_pz.py tests/test_report_sanitize_vectors.py` → PASS.
- [ ] **Step 6: Commit** — `feat(report): PraxisZeit sanitizer rules for names and time-entry notes (#557)`

---

### Task 3: Persistent install_id

**Files:**
- Create: `backend/app/services/report_install_id.py`
- Test: `backend/tests/test_report_install_id.py`

**Interfaces:**
- Produces: `INSTALL_ID_SETTING_KEY = "report_install_id"`, `get_or_create_install_id(session_factory: Callable[[], Session] = SessionLocal) -> str` (lower-case UUIDv4 string).

Implementation: own session from `session_factory`, `set_superadmin_context(db)`, query `SystemSetting` with explicit `tenant_id == DEFAULT_TENANT_ID` (superadmin context bypasses RLS — filter is mandatory). Missing or not a valid UUID → `str(uuid.uuid4())`, insert/overwrite, commit. `IntegrityError` on insert (parallel first report) → rollback and re-read. Never raises: on any DB error log a WARNING (no value) and return a fresh in-memory UUID for this request.

- [ ] **Step 1: Write the failing tests:** `test_creates_uuid4_once_and_reuses_it` (two calls → equal; `uuid.UUID(v).version == 4`; one row with `tenant_id == DEFAULT_TENANT_ID`), `test_invalid_stored_value_is_replaced`, `test_concurrent_insert_integrity_error_rereads_existing` (monkeypatch the first commit to raise `IntegrityError` after another session inserted `"11111111-…-4…"`; result equals that value), `test_db_failure_returns_uuid_and_does_not_raise`. Use the SQLite test session factory from `conftest.py`.
- [ ] **Step 2: Run** — `BT tests/test_report_install_id.py` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat(report): persistent install_id in system_settings (#557)`

---

### Task 4: Log extract sources

**Files:**
- Modify: `backend/app/config.py` (add `REPORT_LOG_DIR: str = "logs"`)
- Create: `backend/app/services/report_log_extract.py`
- Test: `backend/tests/test_report_log_extract.py`

**Interfaces:**
- Produces: `MAX_EXTRACT_LINES = 200`, `TAIL_BYTES = 256 * 1024`, `MAX_LINE_CHARS = 2000`, `LOG_FILES = ("praxiszeit.log", "service-stderr.log")`;
  `tail_lines(path: Path, max_lines: int = MAX_EXTRACT_LINES, max_bytes: int = TAIL_BYTES) -> list[str]`;
  `error_log_lines(db: Session, tenant_id: UUID, limit: int = 20) -> list[str]`;
  `native_log_dir() -> Path | None` (`Path(settings.REPORT_LOG_DIR)` if `settings.SERVE_FRONTEND` and it is a directory, else `None`);
  `build_log_extract(db: Session, tenant_id: UUID, log_dir: Path | None) -> list[str]` (unsanitized; sanitizing happens once in Task 5).

Rules: `tail_lines` seeks to `size - max_bytes`, drops the first (partial) line when it seeked, decodes UTF-8 with `errors="replace"`, removes NUL, splits on `\n`/`\r\n`, keeps the last `max_lines`, cuts each line to `MAX_LINE_CHARS` (suffix `…`); missing/unreadable file → `[]`. `error_log_lines`: newest `last_seen` first, F-026 tenant filter, format `"{last_seen:%Y-%m-%dT%H:%M:%SZ} {level} {status_code or '-'} {method or '-'} {path or '-'} {count}x {first line of message}"`; never reads `github_issue_url`, `user_id`, `resolved_by`. `build_log_extract` order: header `[Fehler-Monitoring]` + error lines, then per existing file `[<name>]` + tail; total ≤ `MAX_EXTRACT_LINES` (error lines first, the rest split evenly between files).

- [ ] **Step 1: Write the failing tests:** `test_tail_reads_only_last_bytes_of_large_file` (5 MB file of numbered lines; `open` spy records ≤ `TAIL_BYTES + 1` bytes read; result is the last 200 lines; first returned line is complete), `test_tail_handles_no_newlines_and_nul_bytes` (1 MB without `\n` plus `\x00` → ≤ 1 line, length ≤ 2001, no NUL), `test_tail_decodes_cp1252_bytes_without_error`, `test_missing_file_returns_empty`, `test_error_log_lines_are_tenant_scoped_and_newest_first` (row of another tenant absent), `test_native_log_dir_none_in_docker_mode`, `test_build_log_extract_caps_total_lines` (30 error rows + two 1000-line files → `len == 200`, headers present).
- [ ] **Step 2: Run** — `BT tests/test_report_log_extract.py` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat(report): bounded log extract from error_logs and native logs (#557)`

---

### Task 5: Payload builder (context block, error context, field dict)

**Files:**
- Create: `backend/app/services/report_payload.py`
- Test: `backend/tests/test_report_payload.py`

**Interfaces:**
- Consumes: `sanitize_praxiszeit_text` (Task 2), `get_or_create_install_id` (Task 3), `build_log_extract`, `native_log_dir` (Task 4), `error_log_service._scrub_path`, `APP_VERSION`, `license_module.get_current_license()`.
- Produces:
  - `PRODUCT = "praxiszeit"`, `PRODUCT_NAME = "PraxisZeit"`, `BOARD_URL = "https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit"`, `TITLE_MAX = 200`, `DESCRIPTION_MAX = 20000`, `USER_TEXT_MAX = 4000`.
  - `@dataclass(frozen=True) ServerFields(app_version: str, os: str, channel: str, system: str, install_type: str, install_id: str, license_id: str | None)`; `collect_server_fields() -> ServerFields` — `os = platform.system().lower()[:32]`, `system = f"{platform.system()} {platform.release()}/{platform.machine()}"`, `install_type = "native" if settings.SERVE_FRONTEND else "docker"`, `channel = "dev"` if `ENVIRONMENT == "development"` else `"beta"` if `BETA_MODE` else `"stable"`, `license_id` = customer_id / `"beta"` in BETA_MODE / `None`.
  - `@dataclass(frozen=True) ErrorContext(line: str, fingerprint: str | None, detail_lines: list[str])`; `resolve_error_context(db, tenant_id, *, error_log_id: UUID | None, server_error: ServerErrorHint | None, now: datetime) -> ErrorContext | None` — `error_log_id` not found in tenant → `LookupError`; `server_error` → newest `error_logs` row with same `method`, `status_code`, `path == _scrub_path(path)`, `last_seen ≥ now − 10 min`; no row → `ErrorContext(f"HTTP {status} {method} {_scrub_path(path)}", None, [])`. With a row: `line = f"{level} HTTP {status_code} {method} {path} — {first message line} ({count}x, zuletzt {last_seen:%Y-%m-%dT%H:%M:%SZ})"`, `fingerprint = row.fingerprint` (≤ 64), `detail_lines` = traceback lines (max 60).
  - `@dataclass(frozen=True) ServerErrorHint(status: int, method: str, path: str)`.
  - `compose_description(user_text: str, *, server: ServerFields, now_utc: datetime, error_line: str | None, log_lines: list[str] | None) -> str` — exactly spec 5.5:

    ```
    <user_text>

    ---- Kontext (automatisch) ----
    Produkt: PraxisZeit <app_version> (<channel>)
    System: <system>, Installationsart: <install_type>
    Zeit: <now_utc ISO-8601, seconds, "Z">
    Fehler: <error_line>                                  (line only if error_line)
    Protokoll (bereinigt, letzte <N> Zeilen):             (block only if log_lines is not None)
    <log lines>
    ```
  - `@dataclass(frozen=True) ReportPreview(title: str, description: str, log_line_count: int, truncated: bool)`; `build_preview(*, title: str, user_text: str, server: ServerFields, now_utc: datetime, error: ErrorContext | None, log_lines: list[str] | None) -> ReportPreview` — log lines passed = `error.detail_lines + log_lines`; compose, then `sanitize_praxiszeit_text` once over the whole description; while `len > DESCRIPTION_MAX` drop the oldest quarter of log lines (at least one) and recompose+sanitize, `truncated=True`; title = sanitized `title.strip()`, if > 200 → first 199 chars + `…` and sanitize again.
  - `build_fields(*, transport: Literal["mrd-report-1", "legacy"], kind: str, title: str, description: str, severity: str, contact_email: str | None, error_fingerprint: str | None, server: ServerFields) -> dict[str, str]` — mrd-report-1: `protocol, product, install_id, kind, title, description, app_version, os, channel, severity` + `license_id`/`contact_email`/`error_fingerprint` only when set; legacy: `license_id, title, description, app_version, os, severity`. No `credential` (added by the client in Task 6). Same function for preview and send → identical dicts.

- [ ] **Step 1: Write the failing tests:** `test_compose_matches_spec_layout` (exact string for fixed inputs, no `Fehler:` line without error, no `Protokoll` block when `log_lines is None`), `test_preview_sanitizes_whole_description_once` (user text with `anna@praxis.de` and a log line `user=anna` → `<email>`, `user=<user>`; `sanitize_praxiszeit_text(p.description) == p.description`), `test_description_never_exceeds_limit_with_full_extract` (200 lines × 2000 chars → `len ≤ 20000`, `truncated`, header shows the kept count), `test_title_over_limit_after_sanitize_is_cut_to_200`, `test_build_fields_mrd_report_1_has_no_credential_and_omits_empty_optionals`, `test_build_fields_legacy_shape`, `test_resolve_error_context_by_id_is_tenant_scoped` (other tenant → `LookupError`), `test_resolve_server_error_matches_recent_row_by_scrubbed_path` (path with UUID; row 11 min old is ignored), `test_collect_server_fields_beta_and_license` (monkeypatch license/BETA_MODE: customer_id / `"beta"` / `None`).
- [ ] **Step 2: Run** — `BT tests/test_report_payload.py` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `feat(report): payload builder with spec context block and limits (#557)`

---

### Task 6: Report client (transport, fallback, config)

**Files:**
- Modify: `backend/app/config.py` — `REPORT_ALLOWED_HOSTS: frozenset[str]` (module level), settings `FEEDBACK_REPORT_KEY: str = ""`, `FEEDBACK_REPORT_BASE_URL: str = "https://report.mr-development.de"`; validators; `_TOML_KEY_MAP` entries `("feedback", "report_key")` and `("feedback", "report_base_url")`
- Modify: `docker-compose.yml` (and every other compose file that passes `PRACTICE_ADDRESS:` to the backend — grep) — `FEEDBACK_REPORT_KEY: ${FEEDBACK_REPORT_KEY:-}`, `FEEDBACK_REPORT_BASE_URL: ${FEEDBACK_REPORT_BASE_URL:-https://report.mr-development.de}`; `.env.example` and `installer/praxiszeit.conf.example` get a commented `[feedback]` block
- Create: `backend/app/services/report_client.py`
- Test: `backend/tests/test_report_client.py`, extend `backend/tests/test_audit_1107_repo_config.py` only if it enumerates compose env vars

**Interfaces:**
- Produces: `REPORT_FALLBACK_BASE = "https://praxiszeit.mr-development.de"`, `REPORT_TIMEOUT_SECONDS = 15.0`;
  `current_transport() -> Literal["mrd-report-1", "legacy"]` (`"mrd-report-1"` iff `settings.FEEDBACK_REPORT_KEY`);
  `@dataclass(frozen=True) ReportResult(ok: bool, upstream_status: int | None, ref: str | None, report_id: str | None, detail: str | None)`;
  `is_dns_or_tls_error(exc: BaseException) -> bool` (walks `__cause__`/`__context__`: `socket.gaierror`, `ssl.SSLError`, `ssl.SSLCertVerificationError`);
  `send_report(fields: dict[str, str], attachment: tuple[str, bytes, str] | None = None) -> ReportResult` — never raises.

Behaviour: mrd-report-1 → `POST {FEEDBACK_REPORT_BASE_URL}/v1/reports` with `fields | {"credential": key}`; legacy → `POST {FEEDBACK_SERVER_URL}/v1/bugs` (host still checked against `updater._ALLOWED_UPDATE_HOSTS` as today). Each part `(None, value)`, attachment `("attachment", (name, bytes, mime))`. `follow_redirects=False`. One overall deadline of 15 s; the fallback (only mrd-report-1, only if `is_dns_or_tls_error`, only when the base host ≠ fallback host) gets the remaining budget. 201 → `ok=True`, `ref`/`id` from JSON object (non-object → `None`). Other status → `ok=False`, `detail` = JSON `detail` if it is a string (cut to 300 chars), else German default per status: 400 „Meldeprotokoll vom Server nicht unterstützt – bitte PraxisZeit aktualisieren.“, 403 „Meldung abgelehnt (Meldeschlüssel, Produkt oder Installation gesperrt).“, 413 „Anhang zu groß.“, 422 „Meldung vom Server abgelehnt.“, 429 „Zu viele Meldungen, bitte später erneut versuchen.“, other „Meldeserver-Fehler, bitte später erneut versuchen.“. Transport error → `upstream_status=None`, detail „Meldeserver nicht erreichbar.“. Log lines contain status and host only — never fields, key or body.

Config validators: base URL — bare `https` origin, host in `REPORT_ALLOWED_HOSTS`, else `ValueError` (consistent with `FEEDBACK_SERVER_URL`). Key — `strip()`; invalid (not `^mrk_[a-z0-9-]{2,32}_\S+$` or > 128) → `warnings.warn` without the value and treat as `""` (a typo must never stop the app from starting).

- [ ] **Step 1: Write the failing tests** (monkeypatch `report_client.httpx.post` with a recorder like `test_feedback._Recorder`):
  `test_201_returns_ref_and_id`, `test_sends_credential_protocol_and_all_fields_as_form_parts`,
  `test_dns_error_on_both_hosts_tries_each_once` (two `ConnectError` with `__cause__ = socket.gaierror` → exactly 2 calls, hosts `report…` then `praxiszeit…`, `ok False`, `upstream_status None`),
  `test_tls_error_falls_back_once_and_succeeds`, `test_timeout_and_http_status_never_fall_back` (`ReadTimeout`, 503 → 1 call each),
  `test_status_mapping_uses_detail_when_string` (422 with detail; 413 without body → default text),
  `test_empty_key_uses_legacy_bugs_endpoint` (URL ends `/v1/bugs`, no `credential`, no `protocol`),
  `test_key_never_logged` (caplog over a failing send contains no `mrk_`),
  `test_base_url_validator_rejects_foreign_host_and_path`, `test_invalid_key_is_ignored_with_warning`, `test_toml_feedback_section_maps_to_env`.
- [ ] **Step 2: Run** — `BT tests/test_report_client.py` → FAIL.
- [ ] **Step 3: Implement** config changes, compose/env/conf example lines, `report_client.py`.
- [ ] **Step 4: Run** — `BT tests/test_report_client.py tests/test_audit_1107_repo_config.py` → PASS.
- [ ] **Step 5: Commit** — `feat(report): mrd-report-1 client with DNS/TLS fallback and legacy path (#557)`

---

### Task 7: Feedback router — preview and send

**Files:**
- Modify: `backend/app/routers/feedback.py` (replace `POST /report` with `/preview` and `/send`; keep the module docstring's slowapi note)
- Modify: `backend/app/middleware/license.py` (`_EXEMPT_PATH_PREFIXES` += `"/api/feedback/"` with a one-line reason)
- Test: rewrite `backend/tests/test_feedback.py`

**Interfaces:**
- Consumes: Tasks 3–6.
- Produces (HTTP):
  - `POST /api/feedback/preview`, `@limiter.limit("30/hour")`, JSON `FeedbackPreviewIn{kind: Literal["bug","feedback","crash"]="bug", title: str(1..200), text: str(1..4000), severity: Literal["low","medium","high","critical"]="medium", contact_email: EmailStr | None (≤254), include_log: bool=False, error_log_id: UUID | None, server_error: ServerErrorIn | None}`; `ServerErrorIn{status: int(500..599), method: Literal["GET","POST","PUT","PATCH","DELETE"], path: str(1..500, must start with "/api/")}`.
    Response `FeedbackPreviewOut{transport: str, title: str, description: str, fields: dict[str, str], credential_note: str | None, log_line_count: int, truncated: bool, board_url: str, contact_email_dropped: bool}`. `credential_note = "mrk_praxiszeit_… (nicht angezeigt)"` for mrd-report-1, else `None`; `contact_email_dropped = transport == "legacy" and contact_email is not None`.
  - `POST /api/feedback/send`, `@limiter.limit("10/hour")`, multipart: `payload: str = Form(...)` (JSON of `FeedbackSendIn{kind, title ≤200, description ≤20000, severity, contact_email: EmailStr | None, error_fingerprint: str | None (≤64, [0-9a-f])}`), `attachment: UploadFile | None = File(None)`.
    200 `{"status": "received", "ref": str | None, "id": str | None, "board_url": BOARD_URL}`; upstream/transport failure → 502 `{"detail": str, "upstream_status": int | None}`; legacy without license outside BETA_MODE → 400 „Ohne hinterlegte Lizenz ist keine Bug-Meldung möglich.“ (unchanged text).

Rules: non-admin with `kind == "crash"`, `include_log`, `error_log_id` or `server_error` → 403 „Nur für Administratoren.“; `error_log_id` unknown in tenant → 404. Log lines = `build_log_extract(db, tenant_id, native_log_dir())` only when `include_log`. Send re-applies `sanitize_praxiszeit_text` to title and description (no-op for previewed text, defensive for tampered clients) and recomputes server fields with `collect_server_fields()` and `build_fields(...)` — no further text is added. Attachment: only `image/png` / `image/jpeg` with matching magic bytes, ≤ 5 MB (read 5 MB + 1), renamed to `screenshot.png` / `screenshot.jpg`; else 422 „Nur PNG- oder JPEG-Bilder bis 5 MB.“.

**Why re-send instead of a preview token:** stateless (works with several uvicorn workers and across a backend restart between preview and send), the dialog needs the full payload client-side anyway for „Als Datei speichern“, and the sanitizer is idempotent by protocol (`sanitize(sanitize(x)) == sanitize(x)`), so the server can re-check without changing what the user saw. A tampered client can only send text it could have typed itself.

- [ ] **Step 1: Write the failing tests** (keep `_create_test_app`/recorder helpers; patch `report_client.httpx.post`; admin and employee fixtures as in other router tests):
  `test_preview_returns_exact_fields_without_credential`, `test_send_forwards_exactly_previewed_title_and_description` (preview → send with returned strings → recorded form fields equal `preview.fields` plus `credential`),
  `test_preview_reports_legacy_transport_without_key` (`transport == "legacy"`, `contact_email_dropped` true when given),
  `test_preview_log_extract_masks_names_and_notes` (tmp `REPORT_LOG_DIR` with `praxiszeit.log` containing the Task 2 inputs, `SERVE_FRONTEND=True`; description contains none of `anna.schmidt`, `Arzttermin`, `Schmidt`, `Kind krank`),
  `test_employee_cannot_include_log_or_send_crash` (403), `test_error_log_id_of_other_tenant_is_404`,
  `test_send_maps_upstream_failure_to_502_with_status`, `test_send_offline_returns_502_without_upstream_status`,
  `test_send_rejects_non_image_attachment`, `test_send_renames_png_attachment`,
  `test_feedback_routes_work_in_read_only_mode` (license read-only → preview 200, send 200 with stubbed upstream),
  `test_legacy_no_license_non_beta_returns_400_without_upstream_call`, `test_old_report_route_is_gone` (404).
- [ ] **Step 2: Run** — `BT tests/test_feedback.py` → FAIL.
- [ ] **Step 3: Implement** router + middleware exemption.
- [ ] **Step 4: Run** — `BT tests/test_feedback.py tests/test_license_readonly_middleware.py tests/test_report_*.py` → PASS.
- [ ] **Step 5: Commit** — `feat(report): preview and send endpoints for mrd-report-1 (#557)`

---

### Task 8: FeedbackDialog — form, preview, result, save as file

**Files:**
- Create: `frontend/src/api/feedback.ts`, `frontend/src/utils/reportFile.ts`, `frontend/src/utils/reportFile.test.ts`
- Modify: `frontend/src/components/FeedbackDialog.tsx`, `frontend/src/components/FeedbackDialog.test.tsx`

**Interfaces:**
- Consumes: Task 7 HTTP contract.
- Produces:
  - `api/feedback.ts`: `type ReportKind = 'bug' | 'feedback' | 'crash'`; `interface ServerErrorHint { status: number; method: string; path: string }`; `interface FeedbackPreviewRequest { kind: ReportKind; title: string; text: string; severity?: Severity; contact_email?: string; include_log?: boolean; error_log_id?: string; server_error?: ServerErrorHint }`; `interface FeedbackPreview { transport: 'mrd-report-1' | 'legacy'; title: string; description: string; fields: Record<string, string>; credential_note: string | null; log_line_count: number; truncated: boolean; board_url: string; contact_email_dropped: boolean }`; `interface FeedbackSendResult { status: 'received'; ref: string | null; id: string | null; board_url: string }`; `previewReport(req: FeedbackPreviewRequest): Promise<FeedbackPreview>`; `sendReport(preview: FeedbackPreview, req: FeedbackPreviewRequest, screenshot?: File): Promise<FeedbackSendResult>` (multipart `payload` = JSON `{kind, title: preview.title, description: preview.description, severity, contact_email, error_fingerprint: preview.fields.error_fingerprint}`, axios `timeout: 30000`).
  - `utils/reportFile.ts`: `reportFileName(now: Date): string` → `praxiszeit-meldung-YYYYMMDD-HHMM.txt` (local time); `formatReportFile(preview: FeedbackPreview, now: Date, screenshotName?: string): string`; `saveReportFile(preview: FeedbackPreview, screenshotName?: string): void` (uses `downloadBlob(text, name, 'text/plain;charset=utf-8')`).
    File layout: line 1 `PraxisZeit – Problemmeldung (nicht gesendet)`, `Erstellt: <ISO>`, `Ziel: POST https://report.mr-development.de/v1/reports (mrd-report-1)` or `Ziel: POST https://praxiszeit.mr-development.de/v1/bugs (bisheriger Meldeweg)`, one `<key>: <value>` line per field except `title`/`description` (sorted), `Anhang: <name> (nicht in dieser Datei enthalten)` if any, blank line, `Titel: <title>`, blank line, description. Never contains a credential.
  - `FeedbackDialog` props: `{ onClose: () => void; origin?: 'help' | 'toast' | 'error-log'; errorLogId?: string; serverError?: ServerErrorHint; initialTitle?: string }`.

UI (copy verbatim): heading „Problem melden“; kind radios „Fehler“ / „Feedback“ (hidden for `origin` toast/error-log: kind `crash`); „Titel“ (≤ 200), „Beschreibung“ (≤ 4000), „Schweregrad“; „Rückmelde-E-Mail (optional)“; „Bildschirmfoto anhängen (optional)“ (PNG/JPEG ≤ 5 MB, client check, thumbnail in preview); admin-only checkbox „Protokollauszug anhängen (bereinigt)“ (default on for admins, absent for employees, preset on for toast/error-log); hint „Bitte keine Namen von Mitarbeitenden oder Notizen aus Zeiteinträgen eintragen.“; button „Vorschau“. Preview step: title, read-only `<pre>` of description, field list, `credential_note`, legacy note „Hinweis: Die Rückmelde-E-Mail wird über den bisherigen Meldeweg nicht übertragen.“ when `contact_email_dropped`, `truncated` note „Protokollauszug gekürzt.“; buttons „Zurück“, „Senden“, „Als Datei speichern“. Done: „Danke! Ihre Meldung ist eingegangen: <ref or id>.“ + link „Bekannte Probleme ansehen“ (`board_url`, `target="_blank" rel="noopener noreferrer"`). Failed: „Senden fehlgeschlagen – als Datei speichern?“ + `getErrorMessage(error)` + buttons „Als Datei speichern“, „Erneut senden“, „Zurück“. Admin = `useAuthStore` user role `admin`.

- [ ] **Step 1: Write the failing tests:** `reportFile.test.ts` — `formats header, fields, title and description`, `never contains credential or mrk_`, `file name pattern`. `FeedbackDialog.test.tsx` (mock `../api/feedback`, auth store role):
  `preview shows exactly the server description`, `send posts previewed title and description unchanged`,
  `shows ref and board link on success`, `shows save-file path when send fails with 502` (preview text still visible; „Als Datei speichern“ calls `saveReportFile` with the same preview),
  `employee sees no log checkbox`, `admin from error-log origin sends kind crash with error_log_id and include_log`,
  `legacy preview shows contact e-mail note`, `rejects screenshot over 5 MB before preview`.
- [ ] **Step 2: Run** — `FT src/utils/reportFile.test.ts` and `FT src/components/FeedbackDialog.test.tsx` → FAIL.
- [ ] **Step 3: Implement** api module, util, dialog (existing `DialogFocusTrap`, Tailwind classes as today).
- [ ] **Step 4: Run** — both files PASS; `FT src/components/HelpPanel.test.tsx src/components/HelpPanel.escape.test.tsx` still PASS; `cd frontend && npx tsc --noEmit` clean.
- [ ] **Step 5: Commit** — `feat(report): dialog with preview, ref and save-as-file (#557)`

---

### Task 9: Admin toast action and Fehler-Monitoring button

**Files:**
- Create: `frontend/src/stores/reportStore.ts`, `frontend/src/stores/reportStore.test.ts`, `frontend/src/components/ReportDialogHost.tsx`
- Modify: `frontend/src/api/client.ts` (response interceptor), `frontend/src/contexts/ToastContext.tsx` (+ test), `frontend/src/App.tsx` (mount host inside `BrowserRouter`), `frontend/src/pages/admin/ErrorMonitoring.tsx` (+ `ErrorMonitoring.actions.test.tsx`)

**Interfaces:**
- Consumes: `FeedbackDialog` props, `ServerErrorHint` (Task 8).
- Produces: `useReportStore` (zustand) with `lastServerError: (ServerErrorHint & { at: number }) | null`, `recordServerError(hint: ServerErrorHint, at?: number): void`, `takeRecentServerError(now?: number, windowMs?: number /* 5000 */): ServerErrorHint | null` (returns once, then clears), `request: { serverError: ServerErrorHint; initialTitle: string } | null`, `openReport(r): void`, `closeReport(): void`. Toast type gains `action?: { label: string; onClick: () => void }`.

Behaviour: interceptor records every response with `status >= 500` except URLs containing `/feedback/`, path = `(config.baseURL ?? '') + config.url` without query string. `ToastContext.error()` → if `takeRecentServerError()` and the current user's role is `admin` → toast with action „An Entwickler schicken“ (duration 15000) that calls `openReport({ serverError, initialTitle: `Serverfehler ${status} bei ${method} ${path}` })` and dismisses the toast. `ReportDialogHost` renders `FeedbackDialog origin="toast"` while `request` is set. ErrorMonitoring: per row button „An Entwickler schicken“ (next to the GitHub actions) opening `FeedbackDialog origin="error-log" errorLogId={err.id} initialTitle={`Fehler: ${err.message.slice(0, 80)}`}`.

- [ ] **Step 1: Write the failing tests:** `reportStore.test.ts` — `takeRecentServerError returns hint within window once`, `ignores hints older than window`. `ToastContext.test.tsx` — `admin error toast after 5xx shows action`, `employee error toast after 5xx shows no action`, `error toast without recent 5xx shows no action`, `action opens report request with path and status`. `client` test (existing interceptor test file or new `client.serverError.test.ts`) — `records 5xx with path without query`, `does not record feedback endpoints`. `ErrorMonitoring.actions.test.tsx` — `row button opens dialog with error_log_id`.
- [ ] **Step 2: Run** — `FT` each file → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — files PASS; `npx tsc --noEmit` clean.
- [ ] **Step 5: Commit** — `feat(report): send 5xx toasts and error_logs entries to developers (#557)`

---

### Task 10: E2E — preview and save as file

**Files:**
- Create: `e2e/tests/feedback-report.spec.ts`

**Interfaces:**
- Consumes: dialog copy from Task 8 (no sending — the E2E stack has no reporting key and no outbound access).

- [ ] **Step 1: Write the spec:** employee logs in → help panel „Fehler melden / Feedback“ → fill title, description containing `test.person@example.invalid` → „Vorschau“ → `main`-independent dialog locator shows `---- Kontext (automatisch) ----` and `<email>`, not the address → „Als Datei speichern“ → `page.waitForEvent('download')`, file name matches `/^praxiszeit-meldung-\d{8}-\d{4}\.txt$/`, content contains `<email>` and not `mrk_`. Second test (admin): checkbox „Protokollauszug anhängen (bereinigt)“ visible and checked; preview contains `Protokoll (bereinigt, letzte`.
- [ ] **Step 2: Run on testbox** (after `S`; the testbox `.env` of `~/work/pz-mrd-report` carries `LOGIN_RATE_LIMIT=10000/minute REFRESH_RATE_LIMIT=10000/minute` and `COOKIE_SECURE=false` per CLAUDE.md): `ssh testbox "tb-run 'pz-mrd-report:e2e (cachytop)' -- bash -lc 'cd ~/work/pz-mrd-report && docker compose up -d --build && cd e2e && TZ=Europe/Berlin npx playwright test tests/feedback-report.spec.ts'"` → 2 passed. Then `docker compose down` (no `-v`).
- [ ] **Step 3: Commit** — `test(e2e): report preview and save-as-file (#557)`

---

### Task 11: Documentation on all doc-sync surfaces

**Files:**
- Modify: `frontend/src/handbuch/content/mitarbeitende.ts` (task block `problem-melden`, no `shot`), `frontend/src/handbuch/content/praxisleitung.ts` (task block `pl-problem-melden` in the chapter `protokoll-fehler-monitoring`, no `shot`), regenerate `docs/handbuch/HANDBUCH-*.md` + `frontend/public/help/HANDBUCH-*.md` via `npm run handbuch:md` (node:20 container)
- Modify: `docs/handbuch/CHEATSHEET-ADMIN.md`, `docs/handbuch/CHEATSHEET-MITARBEITER.md` + byte-identical mirrors in `frontend/public/help/`
- Modify: `frontend/src/components/DocViewer.tsx` (cheat-sheet line), `frontend/src/constants/helpContent.tsx` (context help `/admin/errors`)
- Modify: `scripts/check-doc-sync.sh` (new group `report` with `need_code` for „An Entwickler schicken“, „Als Datei speichern“, „Protokollauszug anhängen (bereinigt)“, „Bekannte Probleme ansehen“; add to `all`)
- Modify: `docs/INSTALLATION.md`, `docs/INSTALL-NATIVE.md`, `docs/INSTALL-DOCKER.md` (outbound allowlist line `report.mr-development.de:443`, plus `praxiszeit.mr-development.de:443` as fallback/updates), `docs/NATIVE-BETRIEB.md` and `docs/INSTALL-DOCKER.md` (`[feedback] report_key` / `FEEDBACK_REPORT_KEY`, empty = bisheriger Meldeweg)
- Modify: `CLAUDE.md` (rule under "Kritische Regeln": report client — one sanitizer `sanitize_praxiszeit_text`, preview = sent, `/api/feedback/` license-exempt, key never logged, PZ rules JSON shared with C#), `CHANGELOG.md` (Unreleased)

Content (Sie-form, terms per `docs/GLOSSAR.md`): Mitarbeitende — where „Fehler melden / Feedback“ is, Fehler vs. Feedback, preview, „Als Datei speichern“ without internet, no names/notes in the text, reference number and „Bekannte Probleme ansehen“ (needs a pzweb account). Praxisleitung — additionally: „An Entwickler schicken“ on server-error messages and in Fehler-Monitoring, „Protokollauszug anhängen (bereinigt)“ and what is masked (Namen in Protokollzeilen, Notizen und Begründungen aus Zeiteinträgen, E-Mail- und IP-Adressen, Kennwörter), Windows setup „An Entwickler schicken“, firewall line.

- [ ] **Step 1: Add the `report` group to `check-doc-sync.sh`** — `need_code` for the four UI strings above, `need` for „Problem melden“ in `docs/handbuch/HANDBUCH-MITARBEITER.md`, `docs/handbuch/HANDBUCH-ADMIN.md`, both cheat sheets, and for `report.mr-development.de:443` in the three install docs — and run `bash scripts/check-doc-sync.sh report` → FAIL with `FEHLT` lines only for the docs (the `need_code` checks pass because Tasks 8–9 are in).
- [ ] **Step 2: Write the handbook blocks, cheat sheets, DocViewer/helpContent lines, install/ops docs, CLAUDE.md rule, CHANGELOG.**
- [ ] **Step 3: Regenerate** handbook markdown (`docker run --rm -v $PWD/frontend:/app -w /app node:20 sh -c "npm ci --silent && npm run handbuch:md"`, then `chown` per CLAUDE.md).
- [ ] **Step 4: Run** — `bash scripts/check-doc-sync.sh all` → exit 0; `FT src/components/DocViewer.test.tsx` and `FT src/handbuch/content/content.test.ts` → PASS.
- [ ] **Step 5: Commit** — `docs(report): Problem melden in handbooks, help and install docs (#557)`

---

### Task 12: Windows setup/update assistant — report on failure

**Files:**
- Create: `installer/setup/src/PraxisZeit.Setup.Core/Services/Reporting/ReportSanitizer.cs`, `SetupLogTail.cs`, `SetupReport.cs`, `ReportInstallId.cs`, `ReportSender.cs`, `ReportKey.cs`
- Modify: `installer/setup/src/PraxisZeit.Setup.Core/PraxisZeit.Setup.Core.csproj` (embed `..\..\..\..\backend\tests\data\mrd-report-1\sanitize-vectors.json` as `LogicalName` `mrd-sanitize-vectors.json` and `..\..\..\..\backend\app\core\report_rules\praxiszeit-sanitize.json` as `praxiszeit-sanitize.json`)
- Modify: `installer/setup/src/PraxisZeit.Setup/PraxisZeit.Setup.csproj` (`<AssemblyMetadata Include="MrdReportKey" Value="$(MrdReportKey)" />`), `ViewModels/DonePageViewModel.cs`, `Views/DonePageView.axaml`, `ViewModels/MainWindowViewModel.cs` (pass log path, target version, mode to `_done` on failure)
- Modify: `tools/build-release.sh` (`dotnet publish … -p:MrdReportKey="${MRD_REPORT_KEY:-}"`; info line whether a key is baked in, never print it)
- Test: `installer/setup/tests/PraxisZeit.Setup.Core.Tests/Services/Reporting/ReportSanitizerTests.cs`, `SetupReportTests.cs`, `ReportSenderTests.cs`, `SetupLogTailTests.cs`; test csproj links both JSON files as `None … CopyToOutputDirectory="PreserveNewest"` under `vectors/`

**Interfaces:**
- Produces:
  - `static class ReportSanitizer { string Sanitize(string text); IReadOnlyList<string> FindPatientData(string text); string SanitizePraxisZeit(string text); }` — rules loaded once from the embedded JSON; step 0 normalization, ≤ 4 passes, conditions (`ipv4_octets`, `contains_digit`, `upper_lower_digit`, `gdt_length`, `gdt_length_prefix`), `{n}` templates, PZ loop identical to Task 2. Regex: `RegexOptions.CultureInvariant` (+ `IgnoreCase`/`Multiline` per flag) with a 2 s match timeout; make `\b`, `\w`, `\W`, `\d`, `\D` ASCII-only by rewriting them at load (outside classes `\d`→`[0-9]`, `\w`→`[A-Za-z0-9_]`, `\b`→`(?:(?<=[A-Za-z0-9_])(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])(?=[A-Za-z0-9_]))`; inside classes `\d`→`0-9`, `\w`→`A-Za-z0-9_`) — engine note 5. `find_patient_data` per `engine_notes` (raw-text views incl. ESC variants, then hits during sanitize).
  - `static class SetupLogTail { IReadOnlyList<string> Read(string? path, int maxLines = 200, int maxBytes = 262144); }` (`FileShare.ReadWrite`, never throws).
  - `sealed record SetupReportInput(string AppVersion, string Os, string InstallMode, string Headline, string Summary, IReadOnlyList<string> LogLines, DateTime UtcNow, string InstallId)`; `sealed record SetupReport(string Title, string Description, IReadOnlyDictionary<string, string> Fields)`; `static SetupReport SetupReport.Build(SetupReportInput input)` — description layout = Task 5 (`Produkt: PraxisZeit <v> (stable)`, `System: <os>, Installationsart: native`, `Fehler: <Headline> – <Summary>`, `Protokoll (bereinigt, letzte N Zeilen):`), sanitized once with `SanitizePraxisZeit`, ≤ 20000 by dropping oldest lines; title `Setup fehlgeschlagen: <mode> <version>` ≤ 200; fields `protocol=mrd-report-1, product=praxiszeit, component=setup, kind=crash, severity=high, install_id, title, description, app_version, os` (no credential); `string ToFileText()` (same layout as Task 8 file).
  - `static class ReportInstallId { string GetOrCreate(string? baseDir = null); }` — `<CommonApplicationData>/PraxisZeit/report-install-id`, fallback `<LocalApplicationData>/PraxisZeit/…`, else fresh in-memory UUID; invalid content replaced.
  - `static class ReportKey { string? Value { get; } }` — `AssemblyMetadataAttribute` `MrdReportKey` of the entry assembly; empty/whitespace → `null`.
  - `sealed record ReportSendResult(bool Ok, int? Status, string? Ref, string? Detail)`; `sealed class ReportSender(HttpMessageHandler? handler = null) { Task<ReportSendResult> SendAsync(SetupReport report, string key, CancellationToken ct = default); }` — `MultipartFormDataContent` with `StringContent` parts + `credential`; base `https://report.mr-development.de`, fallback `https://praxiszeit.mr-development.de` once only for `HttpRequestException` whose inner chain has `SocketException` (`HostNotFound`/`NoData`/`TryAgain`) or `AuthenticationException`; overall 15 s; never throws; detail text as Task 6.
  - DonePage: `bool ShowReportActions` (= `!Success`), `bool CanSendReport` (= key present and not sent), `string ReportPreviewText` (title + description + field list, shown in an `Expander` „Vorschau der Meldung“ with a read-only `TextBox`), `string? ReportStatus`; commands `SendReportCommand` („An Entwickler schicken“, async, button disabled while sending) and `SaveReportCommand` („Als Datei speichern“, `StorageProvider.SaveFilePickerAsync`, default name `praxiszeit-setup-meldung-YYYYMMDD-HHMM.txt`). Without key: hint „Bitte speichern Sie die Meldung als Datei und senden Sie sie an projekt@phash.de.“ (built from `LicensePageViewModel.LicenseContact`). Success: „Meldung gesendet: <ref>.“ + link „Bekannte Probleme ansehen“. Failure: „Senden fehlgeschlagen – als Datei speichern?“ + detail.

- [ ] **Step 1: Write the failing tests:** `ReportSanitizerTests` — `[Theory] SharedVector_Passes(id)` over all `cases` (4 assertions as in Task 1), `[Theory] PraxisZeitCase_Passes(id)`, `RuleCount_MatchesFiles` (47 + 5). `SetupLogTailTests` — `ReadsOnlyLastBytesOfLargeFile` (5 MB), `MissingFile_ReturnsEmpty`, `LockedForWrite_StillReadable`. `SetupReportTests` — `Description_FollowsSpecLayoutAndIsSanitized` (log line `C:\Users\aschmidt\…` → `<user>`), `Description_NeverExceeds20000`, `Fields_HaveNoCredential`, `FileText_ContainsNoKey`. `ReportSenderTests` (stub `HttpMessageHandler`) — `Created_ReturnsRef`, `SendsCredentialAndProtocol`, `DnsFailure_FallsBackOnce` (2 requests, second host praxiszeit), `ServerError_NoFallback`, `Timeout_ReturnsFailureWithoutThrowing`, `Status429_UsesDetail`. `ReportInstallIdTests` — `CreatesOnceAndReuses`, `InvalidContentIsReplaced`.
- [ ] **Step 2: Run** — `DT Reporting` → FAIL (types missing).
- [ ] **Step 3: Implement** Core classes and csproj embedding; then the DonePage UI, MainWindow wiring, Setup csproj metadata, build-release flag.
- [ ] **Step 4: Run** — `DT Reporting` → PASS; `dotnet test` (whole Core.Tests project) → PASS; `dotnet build installer/setup/src/PraxisZeit.Setup/PraxisZeit.Setup.csproj -p:MrdReportKey=mrk_praxiszeit_test1234` and without the property → both succeed; `bash -n tools/build-release.sh`.
- [ ] **Step 5: Manual check (local, Linux):** `dotnet run --project installer/setup/src/PraxisZeit.Setup` against a deliberately invalid install dir to reach the error page; preview shows sanitized log; „Als Datei speichern“ writes the file; without key the mail hint is shown. (Windows emulator run is release work, out of scope.)
- [ ] **Step 6: Commit** — `feat(setup): report failed install/update with sanitized setup log (#557)`

---

### Task 13: Full verification, review rounds, PR

**Files:** none new (fixes go into the owning files with a regression test each).

- [ ] **Step 1: Full suites on testbox** (after `S`): `bash scripts/local-ci.sh` via `tb-run 'pz-mrd-report:local-ci (cachytop)'` (doc sync, backend SQLite + PG split, native PG lifecycle, vitest, tsc incl. `e2e/`, eslint, vite build, e2e). Expected: all green; pre-existing failures documented with proof they also fail on `origin/master`. Locally: `dotnet test` on `installer/setup`.
- [ ] **Step 2: Dependency audit** per CLAUDE.md (pip-audit, `npm audit` in `frontend/`, `e2e/`, `tools/`) — no new findings from this branch.
- [ ] **Step 3: Review workflow (master plan "Review protocol"):** finders in parallel over correctness, security/privacy (names/notes in extracts, key leaks, injection into multipart, SSRF via base URL), `mrd-report-1` conformance (README §2–§10, field limits, fallback rule, preview = sent), error/offline paths, test quality; each finding verified by 2 independent skeptics; repeat until two consecutive rounds find nothing new. Fix every confirmed finding ≤ medium, each with a regression test.
- [ ] **Step 4: Second opinion:** fresh reviewer with only `git diff origin/master...` and the spec + protocol README, no earlier findings; fix confirmed findings as in Step 3.
- [ ] **Step 5: Re-run Step 1** after fixes; clean up on testbox (`docker compose down` without `-v`, temp files, `df -h ~`, `tb-status`).
- [ ] **Step 6: Push branch and open PR** `feat/mrd-report-1` → `master` (body via `--body-file -`): summary, test results, open follow-ups — (a) Manuel creates the `mrk_praxiszeit_…` key in pzweb `/admin/meldeschluessel` and sets it as default/build variable `MRD_REPORT_KEY`, (b) DNS A-record `report.mr-development.de`, (c) pzweb deploy (PR #127) + live end-to-end report and feedback-watch poll, (d) pzweb `anleitung` section „Problem melden“, (e) issue #557 checklist. **Do not merge** without Manuel's approval.
