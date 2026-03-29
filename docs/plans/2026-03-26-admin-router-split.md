# Admin Router Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the 1244-line `admin.py` god-file into focused sub-routers while preserving all existing behavior and tests.

**Architecture:** Extract sections into separate router modules, each with their own APIRouter. The main `admin.py` becomes a thin coordinator that includes sub-routers. Shared helpers (`_create_audit_log`, `_enrich_cr_response`, `_enrich_audit_response`, `_get_field`) move to a shared `admin_helpers.py` module.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy

---

## File Structure

| Action | File | Lines | Responsibility |
|--------|------|-------|---------------|
| Create | `backend/app/routers/admin_helpers.py` | ~75 | Shared: `_create_audit_log`, `_enrich_cr_response`, `_enrich_audit_response`, `_get_field`, `SettingUpdate` model |
| Create | `backend/app/routers/admin_users.py` | ~320 | User CRUD, DSGVO (anonymize/purge), working hours changes (lines 104-516) |
| Create | `backend/app/routers/admin_change_requests.py` | ~200 | Change request listing, review, pending count (lines 518-717) |
| Create | `backend/app/routers/admin_time_entries.py` | ~185 | Admin time entry CRUD + audit log (lines 719-933) |
| Create | `backend/app/routers/admin_settings.py` | ~80 | System settings + holiday sync (lines 936-1009) |
| Create | `backend/app/routers/admin_vacations.py` | ~150 | Vacation request management (lines 1011-1157) |
| Create | `backend/app/routers/admin_carryovers.py` | ~90 | Year carryovers + year closing (lines 1160-1244) |
| Modify | `backend/app/routers/admin.py` | ~15 | Thin coordinator: imports and includes sub-routers |

## Key Rules

1. **All sub-routers use the same prefix `/api/admin`** — no URL changes
2. **All sub-routers have `dependencies=[Depends(require_admin)]`** — admin-only
3. **No behavior changes** — pure structural refactor
4. **All 147 existing tests must pass unchanged**
5. **Shared helpers in `admin_helpers.py`** — imported by sub-routers that need them
