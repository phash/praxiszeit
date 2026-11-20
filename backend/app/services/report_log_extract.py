"""Bounded, UNSANITIZED log extract sources for problem reports (#557).

Sanitizing happens once over the fully composed description (Task 5).
Never reads user free text: only error_logs (value-free) and native log tails.
The native tails (service-stderr.log) can carry exception messages and uploaded
file names; the PraxisZeit sanitizer rules mask those (Review F5).
"""
from __future__ import annotations

import os
import re
from datetime import timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models.error_log import ErrorLog
from app.services.error_log_service import _scope_to_tenant

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


def error_log_lines(db: Session, tenant_id: UUID | None, limit: int = 20) -> list[str]:
    # Same scope as the Fehler-Monitoring list: tenant id = own + NULL-tenant
    # infrastructure rows (F-026 in addition to RLS), None (on-prem) = no filter.
    rows = (
        _scope_to_tenant(db.query(ErrorLog), tenant_id)
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


def build_log_extract(db: Session, tenant_id: UUID | None, log_dir: Path | None) -> list[str]:
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


_FILE_HEADER = re.compile(r"^\[[^\]\n]+\.log\]$")


def _is_header(line: str) -> bool:
    return line == ERROR_HEADER or bool(_FILE_HEADER.match(line))


def trim_extract(lines: list[str], keep: int) -> list[str]:
    """Cut an extract from ``build_log_extract`` to at most ``keep`` lines (Review F18).

    The extract is not chronological: ``[Fehler-Monitoring]`` rows are newest
    first, the log tails oldest first. Cutting from the front dropped the newest
    error rows and the section headers. Instead: drop the oldest line of the
    largest log section (header-less leading lines count as a log section), and
    only when no log lines are left the oldest (last) error row; a section whose
    body becomes empty loses its header too."""
    if keep <= 0:
        return []
    sections: list[list] = []  # [header or None, body]
    for line in lines:
        if _is_header(line):
            sections.append([line, []])
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append([None, [line]])
    total = len(lines)
    while total > keep:
        logs = [s for s in sections if s[0] != ERROR_HEADER and s[1]]
        if logs:
            target = max(logs, key=lambda s: len(s[1]))
            target[1].pop(0)
        else:
            errs = [s for s in sections if s[0] == ERROR_HEADER and s[1]]
            if not errs:
                break
            errs[-1][1].pop()
        total -= 1
        for s in [s for s in sections if not s[1]]:
            sections.remove(s)
            if s[0] is not None:
                total -= 1
    out: list[str] = []
    for header, body in sections:
        if header is not None:
            out.append(header)
        out.extend(body)
    return out[-keep:] if len(out) > keep else out
