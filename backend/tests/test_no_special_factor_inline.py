"""Teil B: den alten Faktor-Helfer ``special_day_target_factor`` gibt es nicht mehr.

Er kannte ``max_hours`` nicht (lieferte dort ``None`` = „normaler Tag``) und hielt
eine zweite, abweichende Soll-Regel am Leben. Soll-Stellen rufen
``special_days_service.special_day_target``, Tage-Kosten
``calculation_service.half_special_day_weight``, Modus-Weichen
``special_days_service.special_day_mode``.
"""
from pathlib import Path

from app.services import special_days_service

BACKEND = Path(__file__).resolve().parents[1]


def test_special_day_target_factor_removed():
    assert not hasattr(special_days_service, "special_day_target_factor")


def test_special_day_target_factor_not_referenced_in_app():
    offenders = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "special_day_target_factor" in line:
                offenders.append(f"{rel}:{i}")
    assert not offenders, "special_day_target_factor in app/:\n" + "\n".join(offenders)
