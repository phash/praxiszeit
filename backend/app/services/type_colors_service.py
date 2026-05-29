"""Admin-konfigurierbare Farben pro Anwesenheits-/Abwesenheitstyp (#157).

Gespeichert als ein per-Tenant ``SystemSetting`` (Key ``type_colors``), dessen
``value`` eine JSON-Map ``{typ: "#RRGGBB"}`` ist. ``work`` steht für Anwesenheit
(Zeiteintrag), die übrigen Keys entsprechen den ``AbsenceType``-Werten.
"""
from __future__ import annotations

import json
import re
from typing import Dict

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting

TYPE_COLORS_KEY = "type_colors"

# Default-Palette (vom Admin überschreibbar). Keys: "work" (Anwesenheit) +
# AbsenceType-Werte (vacation/sick/training/overtime/other/paid_leave).
DEFAULT_TYPE_COLORS: Dict[str, str] = {
    "work": "#16A34A",        # Arbeit — grün
    "training": "#15803D",    # Fortbildung — grün (zählt als Arbeit)
    "vacation": "#2563EB",    # Urlaub — blau
    "sick": "#DC2626",        # Krank — rot
    "overtime": "#7C3AED",    # Überstundenausgleich — violett
    "other": "#6B7280",       # Sonstiges — grau
    "paid_leave": "#0D9488",  # Bezahlte Freistellung — teal
}

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _load_stored(db: Session, tenant_id) -> Dict[str, str]:
    """Read the persisted (possibly partial) color map; tolerate corruption."""
    row = (
        db.query(SystemSetting)
        .filter(
            SystemSetting.key == TYPE_COLORS_KEY,
            SystemSetting.tenant_id == tenant_id,
        )
        .first()
    )
    if not row or not row.value:
        return {}
    try:
        loaded = json.loads(row.value)
    except (ValueError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    # keep only known keys with valid hex
    return {
        k: v
        for k, v in loaded.items()
        if k in DEFAULT_TYPE_COLORS and isinstance(v, str) and _HEX_RE.match(v)
    }


def get_type_colors(db: Session, tenant_id) -> Dict[str, str]:
    """Return the effective color map: stored values merged over defaults."""
    merged = dict(DEFAULT_TYPE_COLORS)
    merged.update(_load_stored(db, tenant_id))
    return merged


def set_type_colors(db: Session, tenant_id, colors: Dict[str, str]) -> Dict[str, str]:
    """Validate + persist a (partial) color map. Returns the effective map.

    Raises ValueError on unknown type keys or invalid hex values. Partial
    updates are merged onto previously stored values.
    """
    if not isinstance(colors, dict):
        raise ValueError("colors muss ein Objekt {typ: '#RRGGBB'} sein")
    cleaned: Dict[str, str] = {}
    for k, v in colors.items():
        if k not in DEFAULT_TYPE_COLORS:
            raise ValueError(f"Unbekannter Typ: {k}")
        if not isinstance(v, str) or not _HEX_RE.match(v):
            raise ValueError(f"Ungültiger Farbwert für '{k}': erwartet #RRGGBB")
        cleaned[k] = v

    base = _load_stored(db, tenant_id)
    base.update(cleaned)
    payload = json.dumps(base)

    row = (
        db.query(SystemSetting)
        .filter(
            SystemSetting.key == TYPE_COLORS_KEY,
            SystemSetting.tenant_id == tenant_id,
        )
        .first()
    )
    if row:
        row.value = payload
    else:
        db.add(SystemSetting(
            key=TYPE_COLORS_KEY,
            tenant_id=tenant_id,
            value=payload,
            description="Farben pro Anwesenheits-/Abwesenheitstyp (#157)",
        ))
    db.commit()
    return get_type_colors(db, tenant_id)
