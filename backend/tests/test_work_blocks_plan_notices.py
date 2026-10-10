"""Spec P9: Plan-Hinweise über den GANZEN Tagesplan — nicht blockierend."""
from app.services.work_blocks_service import block_break_notices
from tests.work_blocks_fixtures import block_week, legacy_week


def test_gap_under_15_minutes_is_no_break_and_disappears():
    week = block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])
    notices = block_break_notices(week, 15, exempt=False)
    assert "Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." in notices
    assert ("Mo: Die Lücke 12:00–12:10 ist nicht länger als der doppelte Puffer (15 Min) und wird vollständig "
            "angerechnet. Eine geplante Pause bitte als „Pause innerhalb der Blöcke“ erfassen.") in notices
    assert any(n.startswith("Mo: Tagessoll 10:00 h – mehr als 8 Stunden") for n in notices)


def test_two_20_minute_gaps_are_not_enough_for_10_20_hours():
    week = block_week(mon=[("07:00", "10:40"), ("11:00", "14:20"), ("14:40", "18:00")])
    notices = block_break_notices(week, 0, exempt=False)
    assert "Mo: geplant 10:20 h Arbeit, eingeplante Pausen 40 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." in notices
    assert ("Mo: Tagessoll 10:20 h – geplanter Verstoß gegen § 3 ArbZG; eine Erfassung nach diesem Plan lehnt "
            "die Zeiterfassung mit 400 ab.") in notices


def test_lunch_gap_of_30_minutes_at_grace_15_disappears():
    notices = block_break_notices(block_week(mon=[("08:00", "12:00"), ("12:30", "16:30")]), 15, exempt=False)
    assert any(n.startswith("Mo: Die Lücke 12:00–12:30 ist nicht länger als der doppelte Puffer (15 Min)") for n in notices)


def test_long_stretch_without_gap_when_pause_is_zero():
    notices = block_break_notices(block_week(mon=[("07:00", "14:00"), ("14:30", "16:00")]), 0, exempt=False)
    assert ("Mo: geplant mehr als 6 Stunden am Stück ohne Lücke von mindestens 15 Minuten (07:00–14:00) – "
            "nach § 4 ArbZG ist spätestens nach 6 Stunden eine Pause nötig.") in notices


def test_pause_under_15_minutes_is_no_break_section():
    """Review Task 5 (Spec P9 (a), Entschieden 2026-10-10): eine Pause unter 15 Minuten
    ist kein Pausenabschnitt (§ 4 Satz 2, A-M2 in ``daily_break_figures``) — die harte
    Prüfung beim Erfassen zählt sie nicht bzw. lehnt sie ab. 10 + 35 Min Lücke sehen nach
    45 aus, wirksam sind nur die 35."""
    week = block_week(pause=10, mon=[("07:00", "12:00"), ("12:35", "17:45")])
    notices = block_break_notices(week, 15, exempt=False)
    assert "Mo: geplant 10:00 h Arbeit, eingeplante Pausen 35 Min – nach § 4 ArbZG sind mindestens 45 Minuten nötig." in notices


def test_long_stretch_is_checked_when_pause_is_under_15_minutes():
    """Pause 10 zählt nicht als Abschnitt → die 6-h-Streckenprüfung greift wie bei Pause 0."""
    notices = block_break_notices(block_week(pause=10, mon=[("07:00", "13:30"), ("14:00", "16:00")]), 0, exempt=False)
    assert ("Mo: geplant mehr als 6 Stunden am Stück ohne Lücke von mindestens 15 Minuten (07:00–13:30) – "
            "nach § 4 ArbZG ist spätestens nach 6 Stunden eine Pause nötig.") in notices


def test_pause_inside_the_blocks_counts_for_section_4():
    assert block_break_notices(block_week(pause=45, mon=[("07:00", "17:00")]), 15, exempt=False) == [
        "Mo: Tagessoll 9:15 h – mehr als 8 Stunden sind nur zulässig, wenn im Durchschnitt von 24 Wochen "
        "8 Stunden je Werktag nicht überschritten werden (§ 3 ArbZG)."
    ]


def test_week_over_48_hours():
    """Wochensoll = Σ (Blöcke − Pause) (Spec P9 (c)): 5 × 10 h brutto mit Pause 45
    sind 46:15 h und damit KEIN Wochenhinweis — wer die Bruttozeit summiert, käme
    auf 50:00 h. Mit Pause 15 bleiben 48:45 h, also genau ein Hinweis mit Nettowert."""
    day = [("07:00", "17:00")]
    notices = block_break_notices(block_week(pause=45, mon=day, tue=day, wed=day, thu=day, fri=day), 15, exempt=False)
    assert not any(n.startswith("Wochensoll") for n in notices)
    notices = block_break_notices(block_week(pause=15, mon=day, tue=day, wed=day, thu=day, fri=day), 15, exempt=False)
    assert [n for n in notices if n.startswith("Wochensoll")] == [
        "Wochensoll 48:45 h – mehr als 48 Stunden je Woche (§ 3 ArbZG)."
    ]
    week = block_week(mon=day, tue=day, wed=day, thu=day, fri=day)
    assert "Wochensoll 50:00 h – mehr als 48 Stunden je Woche (§ 3 ArbZG)." in block_break_notices(week, 15, exempt=False)


def test_exempt_keeps_only_the_gap_notice():
    week = block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])
    notices = block_break_notices(week, 15, exempt=True)
    assert len(notices) == 1 and notices[0].startswith("Mo: Die Lücke 12:00–12:10")


def test_plain_plan_and_empty_input_give_no_notice():
    assert block_break_notices(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")]), 15, exempt=False) == []
    assert block_break_notices(None, 15, exempt=False) == []


def test_legacy_window_gives_no_notice():
    """Altfenster (Pause None, Spec 3.3/4.4) kappen nur und treiben kein Soll — ein
    Tagessoll-/Pausenhinweis wäre dort falsch (07:00–23:59 hieße sonst „Verstoß")."""
    week = legacy_week(mon=("07:00", None), tue=("08:00", "12:00"))
    assert block_break_notices(week, 15, exempt=False) == []
