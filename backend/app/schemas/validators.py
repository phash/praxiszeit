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
