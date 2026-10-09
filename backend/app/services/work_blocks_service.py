"""Arbeitszeit-Blöcke (Spec 2026-10-08, Abschnitt 3): kanonische JSON-Form.

Kanonisch für ``working_hours_changes.blocks`` und ``users.work_blocks``: eine
Liste aus genau fünf Einträgen (Index 0 = Montag … 4 = Freitag), je
``{"blocks": [{"start": "HH:MM", "end": "HH:MM"}, …], "pause_minutes": int | None}``.

Reine Funktionen ohne Datenbank. Gelesen werden auch Altzeilen aus Migration 073
(``07:37``, Platzhalter ``00:00``/``23:59``, ``pause_minutes`` None) — die
STRENGE Prüfung (5-Minuten-Raster, höchstens drei Blöcke, Pause < Σ) gehört in
die Schreibschemas (PR3), nie hierher: ein Lesepfad, der Altwerte ablehnt,
machte den Login einer Person mit Altfenster zu HTTP 500 (E29).
"""
from typing import Any, NamedTuple, Optional

WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr")
_LAST_MINUTE = 23 * 60 + 59


class ParsedWeek(NamedTuple):
    blocks: tuple   # 5 × tuple[(start_min, end_min), …], je Tag sortiert
    pauses: tuple   # 5 × Optional[int]; None = Altzeile (Soll nicht aus Blöcken)


def hhmm_to_minutes(value: str) -> int:
    """``"HH:MM"`` → Minuten seit Mitternacht (00:00–23:59)."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"Uhrzeit {value!r} nicht im Format HH:MM")
    hh, mm = value[:2], value[3:]
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"Uhrzeit {value!r} nicht im Format HH:MM")
    hours, minutes = int(hh), int(mm)
    if hours > 23 or minutes > 59:
        raise ValueError(f"Uhrzeit {value!r} außerhalb 00:00–23:59")
    return hours * 60 + minutes


def minutes_to_hhmm(minutes: int) -> str:
    if not 0 <= minutes <= _LAST_MINUTE:
        raise ValueError(f"Minutenwert {minutes} außerhalb des Tages")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_week_blocks(raw: Any) -> Optional[ParsedWeek]:
    """Kanonische JSON-Woche → :class:`ParsedWeek`.

    ``None`` und eine Woche mit fünf leeren Tagen ergeben ``None`` (Spec 3.3:
    beides heißt „keine Blöcke" — sonst entstünden Scheinänderungen)."""
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError("Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet.")
    all_blocks, pauses = [], []
    for idx, day in enumerate(raw):
        label = WEEKDAY_LABELS[idx]
        if not isinstance(day, dict) or not isinstance(day.get("blocks", []), list):
            raise ValueError(f"{label}: Tag nicht in der Form {{blocks, pause_minutes}}.")
        day_blocks = []
        for block in day.get("blocks") or []:
            try:
                start = hhmm_to_minutes(block["start"])
                end = hhmm_to_minutes(block["end"])
            except (KeyError, TypeError) as exc:
                raise ValueError(f"{label}: Block ohne start/end.") from exc
            if start >= end:
                raise ValueError(f"{label}: Beginn muss vor dem Ende liegen.")
            day_blocks.append((start, end))
        day_blocks.sort()
        for (_, end_a), (start_b, _) in zip(day_blocks, day_blocks[1:]):
            if start_b < end_a:
                raise ValueError(f"{label}: Blöcke überlappen.")
        pause = day.get("pause_minutes")
        if pause is not None and (isinstance(pause, bool) or not isinstance(pause, int) or pause < 0):
            raise ValueError(f"{label}: Pause muss eine ganze Zahl ≥ 0 sein.")
        all_blocks.append(tuple(day_blocks))
        pauses.append(pause)
    if not any(all_blocks):
        return None
    return ParsedWeek(tuple(all_blocks), tuple(pauses))


def week_blocks_to_json(blocks: Optional[tuple], pauses: Optional[tuple]) -> Optional[list]:
    """Umkehrung von :func:`parse_week_blocks` — ``None`` bleibt ``None``."""
    if blocks is None:
        return None
    return [
        {
            "blocks": [{"start": minutes_to_hhmm(s), "end": minutes_to_hhmm(e)} for s, e in day],
            "pause_minutes": pause,
        }
        for day, pause in zip(blocks, pauses)
    ]


def is_legacy_week(parsed: Optional[ParsedWeek]) -> bool:
    """Spec 3.3: eine Zeile mit mindestens einem ``pause_minutes`` None ist eine
    Altzeile (Fenster aus Migration 073 — kappt, treibt kein Soll)."""
    return parsed is not None and any(p is None for p in parsed.pauses)
