"""Spec 2026-10-08, 17.1 (SQLite-Teil): die reinen Helfer der Migration 073.

Der Lauf gegen echtes PostgreSQL (Backfill unter RLS, Downgrade, Round-Trip)
steht in ``test_073_migration_pg.py``. Hier: die Backfill-Regeln je
Bestandsfalle (5.3), die Hülle beim Downgrade (5.5), die Diagnose-Texte (5.4)
und die Kappungsparität — ``clamp`` nach 073 liefert für Altfenster dieselben
Zeiten wie der 072-Code (eingefrorene Kopie unten).
"""
import importlib.util
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from app.models import User, UserRole
from app.services import calculation_service
from app.services import work_window_service as wws

MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
             / "2026_10_08_1200-073_work_blocks.py")


def _load():
    spec = importlib.util.spec_from_file_location("mig073", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()
EMPTY = {"blocks": [], "pause_minutes": None}


def _win(**kw):
    """``mon=(time|None, time|None)`` → 072-Spaltenwerte."""
    names = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday"}
    out = {}
    for key, (start, end) in kw.items():
        out[f"scheduled_start_{names[key]}"] = start
        out[f"scheduled_end_{names[key]}"] = end
    return out


def test_revision_ids():
    assert M.revision == "073_work_blocks" and len(M.revision) <= 32
    assert M.down_revision == "072_cr_sunday_reason"


def test_two_sided_window_becomes_one_legacy_block():
    week, notes = M.build_week(_win(mon=(time(7, 30), time(16, 30))))
    assert week == [{"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": None}] + [EMPTY] * 4
    assert notes == []


def test_half_open_windows_get_placeholders_and_a_note():
    week, notes = M.build_week(_win(mon=(time(7, 30), None), tue=(None, time(16, 30))))
    assert week[0]["blocks"] == [{"start": "07:30", "end": "23:59"}]
    assert week[1]["blocks"] == [{"start": "00:00", "end": "16:30"}]
    assert notes == [
        "halboffen: Mo ab 07:30 → Ende 23:59 (Kappung unverändert)",
        "halboffen: Di bis 16:30 → Beginn 00:00 (Kappung unverändert)",
    ]


def test_seconds_are_truncated_with_a_note():
    week, notes = M.build_week(_win(mon=(time(7, 30, 45), time(16, 30))))
    assert week[0]["blocks"] == [{"start": "07:30", "end": "16:30"}]
    assert notes == ["Sekunden abgeschnitten: Mo 07:30:45 → 07:30"]


def test_inverted_window_is_dropped_with_a_note():
    week, notes = M.build_week(_win(mon=(time(17, 0), time(8, 0)), tue=(time(8, 0), time(16, 0))))
    assert week[0] == EMPTY
    assert week[1]["blocks"] == [{"start": "08:00", "end": "16:00"}]
    assert notes == [
        "nicht übernommen: Mo 17:00–08:00 (Beginn nicht vor Ende); "
        "Einträge an diesem Wochentag werden künftig nicht mehr gekappt"
    ]


def test_only_inverted_windows_give_none():
    """Spec 3.3/5.2: fünf leere Tage == NULL — es wird nichts geschrieben."""
    week, notes = M.build_week(_win(wed=(time(17, 0), time(8, 0))))
    assert week is None and len(notes) == 1


def test_no_window_gives_none():
    assert M.build_week(_win()) == (None, [])


def test_hull_for_multi_block_days_and_placeholders():
    week = [
        {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], "pause_minutes": 0},
        {"blocks": [{"start": "07:00", "end": "10:00"}, {"start": "11:00", "end": "13:00"},
                    {"start": "16:00", "end": "19:00"}], "pause_minutes": 0},
        {"blocks": [{"start": "07:30", "end": "16:30"}], "pause_minutes": None},
        {"blocks": [{"start": "00:00", "end": "16:30"}], "pause_minutes": None},
        {"blocks": [], "pause_minutes": 0},
    ]
    values, notes = M.window_from_week(week)
    assert (values["scheduled_start_monday"], values["scheduled_end_monday"]) == (time(8, 0), time(18, 0))
    assert (values["scheduled_start_tuesday"], values["scheduled_end_tuesday"]) == (time(7, 0), time(19, 0))
    assert (values["scheduled_start_wednesday"], values["scheduled_end_wednesday"]) == (time(7, 30), time(16, 30))
    assert (values["scheduled_start_thursday"], values["scheduled_end_thursday"]) == (None, time(16, 30))
    assert (values["scheduled_start_friday"], values["scheduled_end_friday"]) == (None, None)
    assert notes == [
        "Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 (wieder angerechnete Lücken: 12:00–15:00)",
        "Di 07:00–10:00 + 11:00–13:00 + 16:00–19:00 → Fenster 07:00–19:00 "
        "(wieder angerechnete Lücken: 10:00–11:00, 13:00–16:00)",
    ]


@pytest.mark.parametrize("window", [
    _win(mon=(time(7, 30), time(16, 30))),
    _win(mon=(time(7, 30), None), fri=(None, time(13, 0))),
    _win(tue=(time(7, 37), time(16, 22)), thu=(time(6, 0), time(14, 0))),
])
def test_round_trip_073_072_073_is_identical_for_single_blocks(window):
    week, _ = M.build_week(window)
    values, notes = M.window_from_week(week)
    assert notes == []
    assert {k: v for k, v in values.items() if v is not None} == {
        k: v for k, v in window.items() if v is not None}
    assert M.build_week(values)[0] == week


def test_upgrade_report_format():
    text = M.upgrade_report(7, 23, ["mfa.mueller (Mandant 0000…0001): halboffen: Fr ab 07:30 → Ende 23:59 (Kappung unverändert)"])
    assert "*** HINWEIS (Migration 073) ***" in text
    assert "Arbeitszeit-Fenster wurden in Arbeitszeit-Blöcke übernommen: 7 Konten, 23 Verlaufszeilen." in text
    assert "  - mfa.mueller (Mandant 0000…0001): halboffen" in text
    assert text.rstrip().endswith("*** ENDE HINWEIS ***")
    assert "Besonderheiten" not in M.upgrade_report(0, 0, [])


def test_downgrade_report_names_everyone():
    text = M.downgrade_report(
        ["sek (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00 → Fenster 08:00–18:00 (wieder angerechnete Lücken: 12:00–15:00)"],
        [("zwei (Mandant 0000…0001)", 3, 450)],
        [("zwei (Mandant 0000…0001)", 1)],
        2,
    )
    assert "sek (Mandant 0000…0001): Mo 08:00–12:00 + 15:00–18:00" in text
    assert "zwei (Mandant 0000…0001): 3 Einträge, zusammen 7,50 h" in text
    assert "Anerkannte Einträge" in text
    assert "2 offene Anträge" in text


def test_tenant_label():
    assert M.tenant_label("00000000-0000-0000-0000-000000000001") == "0000…0001"


# ── Kappungsparität (Spec 17.1) ──────────────────────────────────────────────

def _shift_072(t, minutes):
    total = max(0, min(t.hour * 60 + t.minute + minutes, 23 * 60 + 59))
    return time(total // 60, total % 60)


def _clamp_072(soll_start, soll_end, start, end, grace):
    """Eingefrorene Kopie von work_window_service.clamp aus 1.19.3 (ohne die
    Feiertags-/track_hours-Zweige, die hier nicht variieren)."""
    eff_start, eff_end, raw_start, raw_end = start, end, None, None
    if soll_start is not None and start is not None:
        floor = _shift_072(soll_start, -grace)
        if start < floor:
            eff_start, raw_start = floor, start
    if soll_end is not None and end is not None:
        ceil = _shift_072(soll_end, grace)
        if end > ceil:
            eff_end, raw_end = ceil, end
    if eff_start is not None and eff_end is not None and eff_start >= eff_end:
        return (start, start, start, end)
    return (eff_start, eff_end, raw_start, raw_end)


WINDOWS = [
    (time(8, 0), time(17, 0)), (time(8, 0), None), (None, time(17, 0)),
    (time(7, 37), time(16, 22)), (None, time(23, 50)), (time(0, 10), time(23, 50)),
]
STAMPS = [time(h, m) for h, m in (
    (0, 0), (5, 0), (7, 0), (7, 22), (7, 44), (7, 45), (7, 50), (8, 0), (12, 0),
    (16, 0), (16, 37), (17, 14), (17, 15), (17, 16), (18, 30), (23, 59))]
MON = date(2026, 6, 1)


def _user(window):
    week, _ = M.build_week({"scheduled_start_monday": window[0], "scheduled_end_monday": window[1]})
    return User(username="p", email="p@x.de", password_hash="h", first_name="P", last_name="P",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5,
                vacation_days=30, track_hours=True, work_blocks=week)


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("grace", [0, 15, 30])
def test_clamp_parity_with_072(db, window, grace):
    user = _user(window)
    for start in STAMPS:
        for end in [None] + [s for s in STAMPS if s > start]:
            r = wws.clamp(db, user, MON, start, end, grace, credit_override=False)
            assert (r.eff_start, r.eff_end, r.raw_start, r.raw_end) == _clamp_072(
                window[0], window[1], start, end, grace), (window, grace, start, end)
            assert r.uncredited_minutes == 0


def test_blocks_do_not_feed_the_target(db):
    """E10/E18: Altfenster treiben kein Soll — das Tagessoll ist mit und ohne
    übernommenes Fenster identisch (Saldo-Identität auf echten Daten: Task 17)."""
    user = _user((time(7, 30), time(12, 0)))
    with_window = calculation_service.get_daily_target_for_date(
        user, MON, calculation_service.get_schedule_for_date(db, user, MON))
    user.work_blocks = None
    without = calculation_service.get_daily_target_for_date(
        user, MON, calculation_service.get_schedule_for_date(db, user, MON))
    assert with_window == without == Decimal("8")
