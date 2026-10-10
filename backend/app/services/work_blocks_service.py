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
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, NamedTuple, Optional

WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr")
_LAST_MINUTE = 23 * 60 + 59


class ParsedWeek(NamedTuple):
    blocks: tuple   # 5 × tuple[(start_min, end_min), …], je Tag sortiert
    pauses: tuple   # 5 × Optional[int]; None = Altzeile (Soll nicht aus Blöcken)


def hhmm_to_minutes(value: str) -> int:
    """``"HH:MM"`` → Minuten seit Mitternacht (00:00–23:59).

    Nur ASCII-Ziffern: ``str.isdigit()`` ist auch für Vollbreiten- und
    arabisch-indische Ziffern wahr (``"０８:００"`` → 480), der Frontend-Zwilling
    lehnt sie ab — ein so gespeicherter Wert wäre im Editor nicht lesbar."""
    if not isinstance(value, str) or not value.isascii() or len(value) != 5 or value[2] != ":":
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


HOURS_FIELDS = ("hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday", "hours_friday")


def derive_targets(week_blocks: list) -> dict:
    """Spec 4.1 — DIE eine Soll-Ableitung aus NEUEN Blöcken (``pause_minutes`` int).

    Erwartet die bereits validierte kanonische JSON-Woche (``validate_week_blocks``).
    Tagessoll = (Σ Blockdauer − Pause) / 60, ``quantize(0.01, ROUND_HALF_EVEN)``;
    ``weekly_hours`` = Σ der gerundeten Tageswerte. Genutzt von
    ``WorkingHoursChangeCreate`` und ``UserCreate``; Frontend-Zwilling
    ``utils/workBlocks.ts::deriveTargets`` (wortgleiche Testfälle)."""
    hours = []
    for day in week_blocks:
        blocks = day.get("blocks") or []
        total = sum(hhmm_to_minutes(b["end"]) - hhmm_to_minutes(b["start"]) for b in blocks)
        net = total - int(day.get("pause_minutes") or 0) if blocks else 0
        hours.append((Decimal(net) / Decimal(60)).quantize(Decimal("0.01"), ROUND_HALF_EVEN))
    derived = dict(zip(HOURS_FIELDS, hours))
    derived.update(
        weekly_hours=sum(hours, Decimal("0")),
        work_days_per_week=sum(1 for d in week_blocks if d.get("blocks")),
        use_daily_schedule=True,
    )
    return derived


def changed_weekdays(old_blocks: Optional[tuple], new_blocks: Optional[tuple]) -> list:
    """Spec 9.1: Wochentage (0 = Mo … 4 = Fr), deren Blocklisten sich zwischen dem
    alten und dem neuen Snapshot unterscheiden — OHNE Pause (eine reine
    Pausenänderung kappt nichts neu). Schedule-Format: ``None`` == fünf leere Tage
    (3.3, der Resolver normalisiert bereits)."""
    old = old_blocks or ((),) * 5
    new = new_blocks or ((),) * 5
    return [i for i in range(5) if tuple(old[i]) != tuple(new[i])]


def blocks_text(blocks: tuple, pauses: Optional[tuple], *, compact: bool) -> str:
    """Blöcke als Klartext, nur Tage mit Blöcken.

    lang (Dashboard-Hinweis, Berichtstext 15.2):
    ``Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) / Di 08:00–13:00``;
    kurz (Sammelzeile „Vertrag:", PDF-Kurzform 15.2):
    ``Mo 08:00–12:00+15:00–18:00 P30 / Di 08:00–13:00``.
    „Pause" nur bei Pause > 0; Altzeilen (Pause ``None``) ohne Pausenangabe."""
    parts = []
    for idx, day in enumerate(blocks or ()):
        if not day:
            continue
        spans = [f"{minutes_to_hhmm(s)}–{minutes_to_hhmm(e)}" for s, e in day]
        pause = pauses[idx] if pauses else None
        if compact:
            text = "+".join(spans) + (f" P{pause}" if pause else "")
        else:
            text = " + ".join(spans) + (f" (Pause {pause} Min)" if pause else "")
        parts.append(f"{WEEKDAY_LABELS[idx]} {text}")
    return " / ".join(parts)
