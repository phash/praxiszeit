import json
from pathlib import Path

import pytest

import app
from app.core.report_sanitize import find_patient_data
from app.core.report_sanitize_pz import PZ_RULES, PZ_RULES_PATH, sanitize_praxiszeit_text

DATA = Path(__file__).parent / "data" / "mrd-report-1" / "sanitize-vectors.json"
SHARED = json.loads(DATA.read_text(encoding="utf-8"))
PZ = json.loads(PZ_RULES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", PZ["cases"], ids=lambda c: c["id"])
def test_pz_case(case):
    out = sanitize_praxiszeit_text(case["input"])
    assert out == case["expected"]
    assert sanitize_praxiszeit_text(out) == out


@pytest.mark.parametrize("case", SHARED["cases"], ids=lambda c: c["id"])
def test_pz_rules_keep_shared_guarantees(case):
    out = sanitize_praxiszeit_text(case["input"])
    assert sanitize_praxiszeit_text(out) == out
    assert find_patient_data(out) == []


def test_pz_rules_file_ships_inside_app_package():
    assert PZ_RULES_PATH.is_relative_to(Path(app.__file__).parent) and len(PZ_RULES) == 9
