"""Conformance of the mrd-report-1 text sanitizer against the shared vector file."""
import json
from pathlib import Path

import pytest

from app.core.report_sanitize import RULES, find_patient_data, sanitize_report_text

VECTORS = json.loads((Path(__file__).parent / "data/mrd-report-1/sanitize-vectors.json").read_text("utf-8"))


def _rule_dict(r):
    return {
        "name": r.name,
        "category": r.category,
        "flags": list(r.flags),
        "pattern": r.pattern,
        "replacement": r.replacement,
        "condition": r.condition,
        "patient_value_group": r.patient_value_group,
    }


def _published(r):
    return {
        "name": r["name"],
        "category": r["category"],
        "flags": list(r.get("flags", [])),
        "pattern": r["pattern"],
        "replacement": r["replacement"],
        "condition": r.get("condition"),
        "patient_value_group": r.get("patient_value_group"),
    }


def test_vector_file_is_mrd_report_1():
    assert VECTORS["protocol"] == "mrd-report-1"
    assert len(VECTORS["cases"]) >= 259 and len(VECTORS["rules"]) >= 53


def test_rule_table_matches_vector_file():
    assert [_rule_dict(r) for r in RULES] == [_published(r) for r in VECTORS["rules"]]


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["id"])
def test_case(case):
    assert sanitize_report_text(case["input"]) == case["expected"]
    assert sanitize_report_text(case["expected"]) == case["expected"]
    assert bool(find_patient_data(case["input"])) is case["patient_data"]
    assert find_patient_data(case["expected"]) == []
