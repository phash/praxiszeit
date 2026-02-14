from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, time
from uuid import UUID
from app.models import TimeEntry


def _time_to_minutes(t: time) -> int:
    """Convert a time object to total minutes since midnight."""
    return t.hour * 60 + t.minute


def validate_daily_break(
    db: Session,
    user_id: UUID,
    entry_date: date,
    start_time: time,
    end_time: time,
    break_minutes: int,
    exclude_entry_id: Optional[UUID] = None,
) -> Optional[str]:
    """
    Validate that daily break requirements are met per ArbZG §4.
    >6h work requires at least 30min break (sum of all breaks + gaps between entries).

    Returns an error message string if invalid, None if valid.
    """
    # Get all entries for this user on this date
    query = db.query(TimeEntry).filter(
        TimeEntry.user_id == user_id,
        TimeEntry.date == entry_date,
    )
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)

    existing_entries = query.order_by(TimeEntry.start_time).all()

    # Build list of all time blocks (existing + the new/updated one)
    blocks = []
    for entry in existing_entries:
        blocks.append({
            "start": _time_to_minutes(entry.start_time),
            "end": _time_to_minutes(entry.end_time),
            "break_minutes": entry.break_minutes,
        })

    # Add the current entry being created/updated
    blocks.append({
        "start": _time_to_minutes(start_time),
        "end": _time_to_minutes(end_time),
        "break_minutes": break_minutes,
    })

    # Sort by start time
    blocks.sort(key=lambda b: b["start"])

    # Calculate total gross work time and total declared breaks
    total_gross_minutes = sum(b["end"] - b["start"] for b in blocks)
    total_declared_breaks = sum(b["break_minutes"] for b in blocks)

    # Calculate gaps between consecutive blocks (these count as breaks too)
    total_gap_minutes = 0
    for i in range(1, len(blocks)):
        gap = blocks[i]["start"] - blocks[i - 1]["end"]
        if gap > 0:
            total_gap_minutes += gap

    # Net work time = gross time - declared breaks
    net_work_minutes = total_gross_minutes - total_declared_breaks

    # Total effective break = declared breaks + gaps
    total_effective_break = total_declared_breaks + total_gap_minutes

    # ArbZG §4: >6h (360min) requires at least 30min break
    if net_work_minutes > 360 and total_effective_break < 30:
        return (
            f"Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4). "
            f"Aktuelle Netto-Arbeitszeit: {net_work_minutes // 60}h {net_work_minutes % 60}min, "
            f"Gesamtpause: {total_effective_break} Minuten."
        )

    return None
