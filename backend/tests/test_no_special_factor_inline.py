"""Teil B: ``special_day_target_factor(`` darf nur in special_days_service.py stehen.

Soll-Stellen rufen ``special_days_service.special_day_target``; der Faktor kennt
``max_hours`` nicht.
"""
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
OWNER = "app/services/special_days_service.py"


def test_special_day_target_factor_only_in_special_days_service():
    offenders = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel == OWNER:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "special_day_target_factor(" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{rel}:{i}")
    assert not offenders, "special_day_target_factor( ausserhalb des Service:\n" + "\n".join(offenders)
