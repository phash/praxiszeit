"""Bounded, UNSANITIZED log extract sources for problem reports (#557).

Sanitizing happens once over the fully composed description (Task 5).
Never reads user free text: only error_logs (value-free) and native log tails.
"""
from __future__ import annotations

import os
from datetime import timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models.error_log import ErrorLog

MAX_EXTRACT_LINES = 200
TAIL_BYTES = 256 * 1024
MAX_LINE_CHARS = 2000
LOG_FILES = ("praxiszeit.log", "service-stderr.log")
ERROR_HEADER = "[Fehler-Monitoring]"


def _cut(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + "…"


def tail_lines(path: Path, max_lines: int = MAX_EXTRACT_LINES, max_bytes: int = TAIL_BYTES) -> list[str]:
    try:
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            seeked = size > max_bytes
            if seeked:
                f.seek(size - max_bytes)
            data = f.read(max_bytes)
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace").replace("\x00", "")
    lines = text.replace("\r\n", "\n").split("\n")
    if seeked:
        lines = lines[1:]  # first line is partial
    if lines and lines[-1] == "":
        lines.pop()
    if max_lines <= 0:
        return []
    return [_cut(l) for l in lines[-max_lines:]]


def error_log_lines(db: Session, tenant_id: UUID, limit: int = 20) -> list[str]:
    rows = (
        db.query(ErrorLog)
        .filter(ErrorLog.tenant_id == tenant_id)  # F-026 (additional to RLS)
        .order_by(ErrorLog.last_seen.desc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        ts = r.last_seen
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc)
        first = (r.message or "").splitlines()[0] if (r.message or "").strip() else ""
        out.append(_cut(
            f"{ts:%Y-%m-%dT%H:%M:%SZ} {r.level} {r.status_code or '-'} "
            f"{r.method or '-'} {r.path or '-'} {r.count}x {first}"
        ))
    return out


def native_log_dir() -> Path | None:
    if not settings.SERVE_FRONTEND:
        return None
    p = Path(settings.REPORT_LOG_DIR)
    return p if p.is_dir() else None


def build_log_extract(db: Session, tenant_id: UUID, log_dir: Path | None) -> list[str]:
    out = [ERROR_HEADER] + error_log_lines(db, tenant_id)
    if log_dir is None:
        return out[:MAX_EXTRACT_LINES]
    out = out[:MAX_EXTRACT_LINES]
    remaining = MAX_EXTRACT_LINES - len(out)
    present = [(n, Path(log_dir) / n) for n in LOG_FILES if (Path(log_dir) / n).is_file()]
    if not present or remaining < 2:
        return out
    tails = {n: tail_lines(p, max_lines=remaining) for n, p in present}
    # share includes the "[name]" header; shortest files first so surplus flows on
    budgets: dict[str, int] = {}
    left = remaining
    order = sorted(present, key=lambda np_: len(tails[np_[0]]))
    for i, (n, _) in enumerate(order):
        share = left // (len(order) - i)
        take = min(share, len(tails[n]) + 1)
        budgets[n] = take
        left -= take
    for n, _ in present:
        b = budgets[n]
        if b < 2:
            continue
        out.append(f"[{n}]")
        out.extend(tails[n][-(b - 1):])
    return out
