"""#219: Shared Pydantic-Validator-Logik.

Diese Helfer bündeln Validierungs-Logik, die zuvor mehrfach byte-identisch in
verschiedenen Schemas dupliziert war (half_day-Einzeltag, Soll-Fenster-Reihenfolge,
absence_type-Set). Die Schemas behalten ihre dünnen ``@field_validator``/
``@model_validator``-Wrapper und rufen nur noch die gemeinsame Logik auf — so bleibt
das Verhalten exakt gleich, aber es gibt nur noch EINE Quelle der Wahrheit.
"""
from typing import Any

# Erlaubte absence_type-Werte für Urlaubs-/Abwesenheitsanträge.
VACATION_REQUEST_ABSENCE_TYPES = {"vacation", "training", "overtime", "other"}

# (start_field, end_field, Label) je Wochentag für die Soll-Arbeitszeit-Fenster (#201).
SCHEDULED_WINDOW_PAIRS = [
    ("scheduled_start_monday", "scheduled_end_monday", "Montag"),
    ("scheduled_start_tuesday", "scheduled_end_tuesday", "Dienstag"),
    ("scheduled_start_wednesday", "scheduled_end_wednesday", "Mittwoch"),
    ("scheduled_start_thursday", "scheduled_end_thursday", "Donnerstag"),
    ("scheduled_start_friday", "scheduled_end_friday", "Freitag"),
]


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


def validate_employment_and_window_order(model: Any) -> Any:
    """Erster < letzter Arbeitstag, und je Wochentag Soll-Beginn < Soll-Ende (#193/#201)."""
    if model.first_work_day and model.last_work_day:
        if model.first_work_day >= model.last_work_day:
            raise ValueError("Erster Arbeitstag muss vor dem letzten Arbeitstag liegen")
    for start_field, end_field, label in SCHEDULED_WINDOW_PAIRS:
        s = getattr(model, start_field, None)
        e = getattr(model, end_field, None)
        if s is not None and e is not None and s >= e:
            raise ValueError(f"Soll-Beginn muss vor Soll-Ende liegen ({label})")
    return model
