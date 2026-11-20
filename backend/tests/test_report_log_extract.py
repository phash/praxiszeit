"""Task 4 (#557): bounded, unsanitized log extract sources."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import settings
from app.models.error_log import ErrorLog
from app.services import report_log_extract as rle
from app.services.report_log_extract import (
    LOG_FILES,
    MAX_EXTRACT_LINES,
    MAX_LINE_CHARS,
    TAIL_BYTES,
    build_log_extract,
    error_log_lines,
    native_log_dir,
    tail_lines,
)

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _add(db, tenant, n, message="boom\nsecond line", **kw):
    row = ErrorLog(
        tenant_id=tenant, level="error", logger="app", message=message,
        fingerprint=f"fp{n}-{uuid.uuid4().hex}", count=kw.pop("count", 3),
        last_seen=datetime(2026, 11, 1, 12, 0, n % 60, tzinfo=timezone.utc),
        path="/api/x", method="GET", status_code=500, **kw,
    )
    db.add(row)
    db.commit()


def test_tail_reads_only_last_bytes_of_large_file(tmp_path, monkeypatch):
    p = tmp_path / "big.log"
    p.write_text("".join(f"line {i:07d}\n" for i in range(400_000)))
    assert p.stat().st_size > 5_000_000
    read_total = []
    real_open = open

    class Spy:
        def __init__(self, f):
            self._f = f

        def read(self, *a):
            data = self._f.read(*a)
            read_total.append(len(data))
            return data

        def __getattr__(self, n):
            return getattr(self._f, n)

        def __enter__(self):
            self._f.__enter__()
            return self

        def __exit__(self, *a):
            return self._f.__exit__(*a)

    monkeypatch.setattr(rle, "open", lambda *a, **k: Spy(real_open(*a, **k)), raising=False)
    lines = tail_lines(p)
    assert sum(read_total) <= TAIL_BYTES + 1
    assert len(lines) == 200
    assert lines[-1] == "line 0399999"
    assert lines[0] == "line 0399800"


def test_tail_handles_no_newlines_and_nul_bytes(tmp_path):
    p = tmp_path / "x.log"
    p.write_bytes((b"a" * 500 + b"\x00") * 2000)
    lines = tail_lines(p)
    assert len(lines) <= 1
    assert all(len(l) <= MAX_LINE_CHARS + 1 and "\x00" not in l for l in lines)


def test_tail_decodes_cp1252_bytes_without_error(tmp_path):
    p = tmp_path / "c.log"
    p.write_bytes("Grüße\r\nzweite\r\n".encode("cp1252"))
    lines = tail_lines(p)
    assert len(lines) == 2 and lines[1] == "zweite"
    assert "\r" not in lines[0]


def test_tail_cuts_long_lines(tmp_path):
    p = tmp_path / "l.log"
    p.write_text("x" * 5000 + "\n")
    (line,) = tail_lines(p)
    assert len(line) == MAX_LINE_CHARS + 1 and line.endswith("…")


def test_missing_file_returns_empty(tmp_path):
    assert tail_lines(tmp_path / "nope.log") == []


def test_error_log_lines_are_tenant_scoped_and_newest_first(db, default_tenant):
    _add(db, TENANT, 1, message="old")
    _add(db, TENANT, 30, message="new\ndetail")
    _add(db, OTHER, 59, message="foreign")
    lines = error_log_lines(db, TENANT)
    assert len(lines) == 2
    assert lines[0] == "2026-11-01T12:00:30Z error 500 GET /api/x 3x new"
    assert lines[1].endswith("old")
    assert not any("foreign" in l for l in lines)


def test_error_log_lines_naive_last_seen_and_missing_fields(db, default_tenant):
    db.add(ErrorLog(tenant_id=TENANT, level="warning", logger="a", message="m",
                    fingerprint="f", count=1, last_seen=datetime(2026, 1, 2, 3, 4, 5)))
    db.commit()
    assert error_log_lines(db, TENANT) == ["2026-01-02T03:04:05Z warning - - - 1x m"]


def test_native_log_dir_none_in_docker_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "REPORT_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SERVE_FRONTEND", False)
    assert native_log_dir() is None
    monkeypatch.setattr(settings, "SERVE_FRONTEND", True)
    assert native_log_dir() == tmp_path
    monkeypatch.setattr(settings, "REPORT_LOG_DIR", str(tmp_path / "missing"))
    assert native_log_dir() is None


def test_build_log_extract_caps_total_lines(db, default_tenant, tmp_path):
    for i in range(30):
        _add(db, TENANT, i)
    for name in LOG_FILES:
        (tmp_path / name).write_text("".join(f"{name} {i}\n" for i in range(1000)))
    out = build_log_extract(db, TENANT, tmp_path)
    assert len(out) == MAX_EXTRACT_LINES == 200
    assert out[0] == "[Fehler-Monitoring]"
    assert "[praxiszeit.log]" in out and "[service-stderr.log]" in out
    assert out[-1] == "service-stderr.log 999"


def test_build_log_extract_without_dir_or_files(db, default_tenant, tmp_path):
    _add(db, TENANT, 1)
    assert len(build_log_extract(db, TENANT, None)) == 2
    assert len(build_log_extract(db, TENANT, tmp_path)) == 2
