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
# Spec 3.4, Regel „genau 5 Einträge" — eine Quelle für Lese-/Schreibprüfung und die
# 422/``blocked_reason`` bei falscher Form an der Wurzel (``admin_users._block_root_error``).
# Frontend-Zwilling: ``utils/workBlocks.ts::validateWeekBlocks`` (wortgleich).
WEEK_SHAPE_TEXT = "Arbeitszeit-Blöcke: genau fünf Wochentage (Mo–Fr) erwartet."
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
        raise ValueError(WEEK_SHAPE_TEXT)
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


def _hm(minutes: int) -> str:
    """Stunden als ``H:MM`` wie ``work_window_service._hm`` und der Frontend-Zwilling
    ``formatHoursHM`` — hier eigenständig, weil dieses Modul die unterste Schicht ist
    (``calculation_service`` → ``work_window_service`` importieren es; ein Import in
    die Gegenrichtung wäre zirkulär)."""
    return f"{minutes // 60}:{minutes % 60:02d}"


def _stretches(spans: list) -> list:
    """Zusammenhängende Arbeitsstrecken: Blöcke mit einer Lücke unter 15 Minuten
    gelten als eine Strecke (§ 4 ArbZG: Pausenabschnitte ab 15 Minuten)."""
    merged = []
    for start, end in spans:
        if merged and start - merged[-1][1] < 15:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def block_break_notices(week: Optional[list], grace: int, *, exempt: bool) -> list:
    """Spec P9 — nicht blockierende Plan-Hinweise aus dem GANZEN Tagesplan.

    (a) § 4: geplante Arbeit = Σ Blöcke − Pause, Bedarf 30 bzw. 45 Min; geplante
        Pausen = Pause (nur ab 15 Min, § 4 Satz 2) + Σ ROHE Lücken ≥ 15 Min; bei
        Pause unter 15 Min zusätzlich eine Strecke ohne Lücke ≥ 15 Min über 6 h.
    (b) Eine Lücke ≤ 2 × aktueller Puffer verschwindet in der Anrechnung.
    (c) § 3: Tagessoll > 10 h (geplanter Verstoß), > 8 h (24-Wochen-Schnitt),
        Wochensoll > 48 h.
    ``exempt`` (§ 18 ArbZG) unterdrückt (a) und (c). Erwartet eine gültige neue
    Woche (``validate_week_blocks``); ``None`` und Altzeilen (eine Pause ``None``,
    Spec 3.3/4.4 — kappen nur, treiben kein Soll) → keine Hinweise. Nie ein 422:
    die Prüfung beim Erfassen bleibt abschließend."""
    notices: list = []
    if not week or any(day.get("pause_minutes") is None for day in week):
        return notices
    weekly_net = 0
    for idx, day in enumerate(week):
        spans = sorted(
            (hhmm_to_minutes(b["start"]), hhmm_to_minutes(b["end"])) for b in day.get("blocks") or []
        )
        if not spans:
            continue
        label = WEEKDAY_LABELS[idx]
        pause = int(day.get("pause_minutes") or 0)
        net = sum(end - start for start, end in spans) - pause
        weekly_net += net
        gaps = [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)]
        if not exempt:
            need = 45 if net > 9 * 60 else 30 if net > 6 * 60 else 0
            # § 4 Satz 2 / A-M2, wie ``break_validation_service.daily_break_figures``:
            # eine Pause unter 15 Minuten ist kein Pausenabschnitt — die harte Prüfung
            # beim Erfassen zählt sie nicht (bzw. lehnt sie ab). Das Tagessoll ``net``
            # bleibt Σ Blöcke − Pause (4.1); nur der § 4-Vergleich lässt sie weg.
            counted_pause = pause if pause >= 15 else 0
            planned = counted_pause + sum(ge - gs for gs, ge in gaps if ge - gs >= 15)
            if need and planned < need:
                notices.append(
                    f"{label}: geplant {_hm(net)} h Arbeit, eingeplante Pausen {planned} Min – "
                    f"nach § 4 ArbZG sind mindestens {need} Minuten nötig."
                )
            elif counted_pause == 0:
                for start, end in _stretches(spans):
                    if end - start > 6 * 60:
                        notices.append(
                            f"{label}: geplant mehr als 6 Stunden am Stück ohne Lücke von mindestens "
                            f"15 Minuten ({minutes_to_hhmm(start)}–{minutes_to_hhmm(end)}) – nach § 4 ArbZG "
                            f"ist spätestens nach 6 Stunden eine Pause nötig."
                        )
                        break
        for gs, ge in gaps:
            if ge - gs <= 2 * grace:
                notices.append(
                    # Wortlaut zusammenhängend halten — das Doku-Gate (PR4) sucht ihn per grep.
                    f"{label}: Die Lücke {minutes_to_hhmm(gs)}–{minutes_to_hhmm(ge)} "
                    f"ist nicht länger als der doppelte Puffer ({grace} Min) und wird vollständig angerechnet. "
                    f"Eine geplante Pause bitte als „Pause innerhalb der Blöcke“ erfassen."
                )
        if not exempt:
            if net > 10 * 60:
                notices.append(
                    f"{label}: Tagessoll {_hm(net)} h – geplanter Verstoß gegen § 3 ArbZG; eine Erfassung "
                    f"nach diesem Plan lehnt die Zeiterfassung mit 400 ab."
                )
            elif net > 8 * 60:
                notices.append(
                    f"{label}: Tagessoll {_hm(net)} h – mehr als 8 Stunden sind nur zulässig, wenn im "
                    f"Durchschnitt von 24 Wochen 8 Stunden je Werktag nicht überschritten werden (§ 3 ArbZG)."
                )
    if not exempt and weekly_net > 48 * 60:
        notices.append(f"Wochensoll {_hm(weekly_net)} h – mehr als 48 Stunden je Woche (§ 3 ArbZG).")
    return notices
