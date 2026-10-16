"""#219: Shared Pydantic-Validator-Logik.

Diese Helfer bündeln Validierungs-Logik, die zuvor mehrfach byte-identisch in
verschiedenen Schemas dupliziert war (half_day-Einzeltag, Soll-Fenster-Reihenfolge,
absence_type-Set). Die Schemas behalten ihre dünnen ``@field_validator``/
``@model_validator``-Wrapper und rufen nur noch die gemeinsame Logik auf — so bleibt
das Verhalten exakt gleich, aber es gibt nur noch EINE Quelle der Wahrheit.
"""
from datetime import time
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator

from app.services.work_blocks_service import WEEK_SHAPE_TEXT, WEEKDAY_LABELS, derive_targets, hhmm_to_minutes


def truncate_to_minute(v: time) -> time:
    """Gesamtreview 1.20 (B1, PR1-Sicherheitsprüfung F2): Uhrzeiten eines
    Zeiteintrags sind minutengenau — wie Stempeln (``clock_in``/``clock_out``),
    XLS-Datei, Arbeitszeit-Blöcke und jede Rechnung über ``_min`` bzw.
    ``work_window_service.same_minute``. Über die API kamen Sekunden an, und
    dann zählte ``net_hours`` sie, die Lückenüberlappung nicht, und
    ``unclamp_input`` hielt das gekappte „07:45:30" für eine neue Eingabe (der
    Rohstempel ging verloren, §16). Abgeschnitten (nicht gerundet) wie beim
    Stempeln.

    Nachzug zu B1: Uhrzeiten mit Zeitzone („13:00:00Z", „08:00+02:00") werden
    abgelehnt (422). Gespeicherte Zeiten sind zeitzonenlos (Ortszeit der
    Praxis) — der Vergleich mit ihnen warf ``TypeError`` (HTTP 500), beim
    Anlegen fiel der Offset still weg. Abgelehnt statt ``tzinfo=None``: sonst
    würde ein „+02:00" wortlos umgedeutet."""
    if v.tzinfo is not None:
        raise ValueError("Uhrzeit ohne Zeitzone angeben (HH:MM)")
    return v.replace(second=0, microsecond=0)


# Eingangstyp für Uhrzeiten aller manuellen Schreibwege (Eintrag anlegen und
# bearbeiten in beiden Rollen, Änderungsantrag, XLS-Bestätigung). Läuft vor den
# ``@field_validator``-Prüfungen (z. B. „Endzeit muss nach Startzeit liegen").
MinuteTime = Annotated[time, AfterValidator(truncate_to_minute)]

# Erlaubte absence_type-Werte für Urlaubs-/Abwesenheitsanträge.
VACATION_REQUEST_ABSENCE_TYPES = {"vacation", "training", "overtime", "other"}

# Spec 2026-10-08 (11.4/E26): Präfix der mit Migration 073 entfallenen
# Fensterfelder. Erkannt wird NUR das Präfix — die vollen Feldnamen dürfen in
# app/ nicht mehr vorkommen (Guard-Test test_no_scheduled_columns.py).
LEGACY_WINDOW_FIELD_PREFIX = "scheduled_"


def validate_half_day_single_day(v: bool, info: Any) -> bool:
    """half_day ist ein Einzeltag-Konzept — ein Zeitraum mit half_day=True würde
    jeden Tag des Bereichs halbieren (überraschend, inkonsistent zur UI)."""
    if v:
        start = info.data.get("date")
        end = info.data.get("end_date")
        if end is not None and start is not None and end != start:
            raise ValueError("Halbe Tage sind nur für Einzeltage möglich")
    return v


def validate_vr_absence_type(v, *, allow_none: bool):
    """absence_type gegen die erlaubte Menge prüfen.

    ``allow_none=True`` (Update-Pfad) lässt ``None`` durch (Feld nicht gesetzt);
    ``allow_none=False`` (Create-Pfad) lehnt ``None`` ab wie zuvor.
    """
    if v is None and allow_none:
        return v
    if v not in VACATION_REQUEST_ABSENCE_TYPES:
        raise ValueError(f"absence_type muss einer von {VACATION_REQUEST_ABSENCE_TYPES} sein")
    return v


def validate_employment_order(model: Any) -> Any:
    """Erster < letzter Arbeitstag (#193). Die Soll-Fenster-Prüfung (#201)
    entfällt mit Migration 073 — Blöcke werden im Verlauf validiert (PR3)."""
    if model.first_work_day and model.last_work_day:
        if model.first_work_day >= model.last_work_day:
            raise ValueError("Erster Arbeitstag muss vor dem letzten Arbeitstag liegen")
    return model


def strip_legacy_window_fields(data: Any) -> Any:
    """``model_validator(mode="before")``-Kern für UserCreate/UserUpdate (E26).

    Ein gecachtes altes Frontend schickt die entfallenen Fensterfelder bei
    jedem Speichern. Pydantic verwürfe sie still — der Router meldete dann
    „gespeichert", ohne zu speichern. Stattdessen werden sie entfernt und das
    nie serialisierte Feld ``legacy_window_fields_sent`` gesetzt; der Router
    antwortet daraufhin mit 400 „Bitte Seite neu laden"."""
    if isinstance(data, dict) and any(
        isinstance(key, str) and key.startswith(LEGACY_WINDOW_FIELD_PREFIX) for key in data
    ):
        data = {
            key: value for key, value in data.items()
            if not (isinstance(key, str) and key.startswith(LEGACY_WINDOW_FIELD_PREFIX))
        }
        data["legacy_window_fields_sent"] = True
    return data


# Spec 3.4: Obergrenze der Wochensumme (bestehende Grenze der Wochenstunden,
# ``le=60`` in UserBase/WorkingHoursChangeBase). Geprüft wird die Σ der je Tag
# gerundeten Tagessolls (4.1) — exakt der Wert, den ``derive_targets`` speichert.
WEEK_LIMIT_HOURS = Decimal(60)


def _as_dict(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def validate_week_blocks(value: Any) -> list:
    """Spec 2026-10-08, 3.4 — strenge Prüfung NUR für Schreibschemas
    (``UserCreate``, ``WorkingHoursChangeCreate``), nie für Leseschemas (E29).

    Wirft ``ValueError`` mit dem deutschen Text der ERSTEN verletzten Regel und
    liefert sonst die kanonische JSON-Woche. Frontend-Zwilling:
    ``utils/workBlocks.ts::validateWeekBlocks`` (wortgleiche Texte und Fälle).
    Die ArbZG-Plausibilität des Plans ist KEINE Regel hier (P9: Hinweise)."""
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError(WEEK_SHAPE_TEXT)
    week = []
    for idx, raw_day in enumerate(value):
        day = _as_dict(raw_day)
        if not isinstance(day, dict):
            raise ValueError(WEEK_SHAPE_TEXT)
        label = WEEKDAY_LABELS[idx]
        raw_blocks = day.get("blocks") or []
        if not isinstance(raw_blocks, (list, tuple)):
            # Sonst iterierte ``for b in 5`` mit TypeError — in einem
            # Pydantic-Validator ein 500 statt einer Meldung. Wortlaut wie im
            # lesenden ``work_blocks_service.parse_week_blocks``.
            raise ValueError(f"{label}: Tag nicht in der Form {{blocks, pause_minutes}}.")
        blocks = [_as_dict(b) for b in raw_blocks]
        if len(blocks) > 3:
            raise ValueError(f"{label}: höchstens drei Blöcke je Tag.")
        spans = []
        for n, block in enumerate(blocks, start=1):
            try:
                start = hhmm_to_minutes(block.get("start"))
                end = hhmm_to_minutes(block.get("end"))
            except (ValueError, TypeError, AttributeError):
                raise ValueError(f"{label}, Block {n}: Uhrzeit im Format HH:MM angeben.") from None
            if start % 5 or end % 5:
                raise ValueError(f"{label}, Block {n}: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05).")
            if start >= end:
                raise ValueError(f"{label}, Block {n}: Beginn muss vor dem Ende liegen.")
            spans.append((start, end))
        for n in range(1, len(spans)):
            if spans[n][0] <= spans[n - 1][1]:
                raise ValueError(
                    f"{label}: Block {n + 1} muss nach dem Ende von Block {n} beginnen; "
                    "aneinandergrenzende Blöcke bitte als einen Block erfassen."
                )
        pause = day.get("pause_minutes")
        if pause is None:
            raise ValueError(f"{label}: Pause angeben (0, wenn keine).")
        if isinstance(pause, bool) or not isinstance(pause, int) or pause < 0 or pause % 5:
            raise ValueError(f"{label}: Pause in Minuten im 5-Minuten-Raster angeben.")
        if not spans and pause != 0:
            raise ValueError(f"{label}: Pause nur an Tagen mit Blöcken.")
        gross = sum(e - s for s, e in spans)
        if spans and pause >= gross:
            raise ValueError(f"{label}: Pause muss kürzer sein als die Gesamtzeit der Blöcke.")
        week.append({
            "blocks": [{"start": b["start"], "end": b["end"]} for b in blocks],
            "pause_minutes": pause,
        })
    if not any(d["blocks"] for d in week):
        raise ValueError("Mindestens ein Wochentag braucht einen Block.")
    # Nicht die ungerundeten Netto-Minuten: eine Woche mit genau 60:00 h, in der
    # mehrere Tage aufgerundet werden, ergäbe gespeichert 60,01 h — die lehnte
    # danach ``le=60`` mit einem fremden Text ab (Review Task 1).
    if derive_targets(week)["weekly_hours"] > WEEK_LIMIT_HOURS:
        raise ValueError("Die Wochensumme darf 60 Stunden nicht überschreiten.")
    return week
