"""PraxisZeit-specific sanitizer rules on top of the shared mrd-report-1 sanitizer.

The rules live in ``report_rules/praxiszeit-sanitize.json`` (same schema as the shared
``sanitize-vectors.json``) so the Windows setup (C#) can read the same file.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.report_sanitize import MAX_PASSES, Rule, sanitize_report_text

PZ_RULES_PATH = Path(__file__).parent / "report_rules" / "praxiszeit-sanitize.json"


def _load_rules() -> tuple[Rule, ...]:
    data = json.loads(PZ_RULES_PATH.read_text(encoding="utf-8"))
    return tuple(
        Rule(
            name=r["name"],
            category=r["category"],
            pattern=r["pattern"],
            replacement=r["replacement"],
            description=r["description"],
            flags=tuple(r.get("flags", ())),
        )
        for r in data["rules"]
    )


PZ_RULES: tuple[Rule, ...] = _load_rules()


def sanitize_praxiszeit_text(text: str) -> str:
    t = sanitize_report_text(text)
    for _ in range(MAX_PASSES):
        prev = t
        for rule in PZ_RULES:
            t = rule.apply(t)
        t = sanitize_report_text(t)
        if t == prev:
            break
    return t
