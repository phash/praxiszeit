"""Spec 9.2 (E47–E50) und P1: Massen-Neukappung und Knickstellen-Prüfung."""
from datetime import date, time
from decimal import Decimal

from app.models import User, UserRole
from app.models.public_holiday import PublicHoliday
from app.services import rest_time_service, work_blocks_service, work_window_service as wws
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import add_row, entry, t
from tests.work_blocks_fixtures import block_week

MON = date(2026, 6, 1)
JUNE = (date(2026, 6, 1), date(2026, 6, 30))
OLD = block_week(mon=[("08:00", "18:00")], tue=[("08:00", "12:00")])
NEW = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")])


def _setup(db, user, old=OLD, new=NEW):
    add_row(db, user, date(2026, 1, 1), week=old)
    add_row(db, user, MON, week=new)
    return work_blocks_service.parse_week_blocks(old).blocks


def _run(db, user, prev, weekdays=(0,), grace=15):
    return wws.reclamp_time_entries(db, user, *JUNE, set(weekdays), prev, grace)


def _stored(e):
    return (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed)


def test_gap_is_withheld_and_stamps_stay(db, test_user):
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(18))
    result = _run(db, test_user, prev)
    [c] = result.changed
    assert (c.old_net, c.new_net, c.old_uncredited, c.new_uncredited) == (Decimal("10.00"), Decimal("7.50"), 0, 150)
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(8), t(18), None, None)
    assert (e.uncredited_minutes, e.clamp_grace_minutes, c.old_grace) == (150, 15, 15)
    assert result.skipped == [] and result.flagged == []


def test_hull_shrink_starts_from_the_raw_stamps(db, test_user):
    """E48: Quelle ist der Rohstempel — kein kumulatives Doppelkappen."""
    prev = _setup(db, test_user, new=block_week(mon=[("09:00", "17:00")], tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(7, 45), t(18, 15), raw_start=t(7), raw_end=t(19))
    [c] = _run(db, test_user, prev).changed
    assert (e.start_time, e.end_time, e.raw_start_time, e.raw_end_time) == (t(8, 45), t(17, 15), t(7), t(19))
    assert (c.old_net, c.new_net) == (Decimal("10.50"), Decimal("8.50"))


def test_unchanged_entry_only_gets_the_current_grace(db, test_user):
    """E47/E79: jeder geprüfte Eintrag an einem geänderten Wochentag bekommt den
    aktuellen Puffer — ohne Zeile in ``changed``."""
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(12), grace=None)
    result = _run(db, test_user, prev, grace=10)
    assert result.changed == [] and e.clamp_grace_minutes == 10


def test_unchanged_weekday_is_not_touched(db, test_user):
    prev = _setup(db, test_user)
    tue = entry(db, test_user, date(2026, 6, 2), t(8), t(12), grace=10)
    assert _run(db, test_user, prev, grace=15) == wws.ReclampResult([], [], [])
    assert tue.clamp_grace_minutes == 10


def test_every_skip_reason_is_reported(db, test_user):
    prev = _setup(db, test_user)
    db.add(PublicHoliday(date=date(2026, 6, 8), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    test_user.last_work_day = date(2026, 6, 20)
    db.commit()
    entry(db, test_user, MON, t(8), None)
    entry(db, test_user, date(2026, 6, 8), t(8), t(18))
    entry(db, test_user, date(2026, 6, 15), t(15), t(18), credit_override=True)
    entry(db, test_user, date(2026, 6, 22), t(8), t(18))
    reasons = {s.date: s.reason for s in _run(db, test_user, prev).skipped}
    invalidate_holiday_cache()
    assert reasons == {
        MON: "open",
        date(2026, 6, 8): "soll_free_day",
        date(2026, 6, 15): "credit_override",
        date(2026, 6, 22): "outside_employment",
    }


def test_skipped_entries_keep_their_grace(db, test_user):
    """17.5: übersprungene Einträge behalten ihren gespeicherten Puffer — auch der
    anerkannte (``credit_override``), dessen Zeiten unangetastet bleiben."""
    prev = _setup(db, test_user)
    open_today = entry(db, test_user, MON, t(8), None, grace=20)
    accepted = entry(db, test_user, date(2026, 6, 15), t(8), t(18), credit_override=True, grace=20)
    result = _run(db, test_user, prev, grace=10)
    assert result.changed == []
    assert [s.reason for s in result.skipped] == ["open", "credit_override"]
    assert (open_today.clamp_grace_minutes, accepted.clamp_grace_minutes) == (20, 20)
    assert (accepted.end_time, accepted.uncredited_minutes) == (t(18), 0)


def test_track_hours_off_skips_everything(db, default_tenant):
    lead = User(username="leitend", email="l@x.de", password_hash="h", first_name="L", last_name="T",
                role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
                track_hours=False, tenant_id=DEFAULT_TENANT_ID)
    db.add(lead)
    db.commit()
    prev = _setup(db, lead)
    e = entry(db, lead, MON, t(8), t(18))
    result = _run(db, lead, prev)
    assert [s.reason for s in result.skipped] == ["track_hours_off"]
    assert e.uncredited_minutes == 0


def test_unique_collision_keeps_the_entry(db, test_user):
    prev = _setup(db, test_user, old=block_week(mon=[("08:00", "12:00")]),
                  new=block_week(mon=[("08:05", "12:00")]))
    a = entry(db, test_user, MON, t(7, 45), t(9), raw_start=t(7, 30))
    entry(db, test_user, MON, t(7, 50), t(7, 55))
    result = _run(db, test_user, prev)
    assert [(s.entry_id, s.reason) for s in result.skipped] == [(a.id, "unique_collision")]
    assert (a.start_time, a.raw_start_time) == (t(7, 45), t(7, 30))


def test_not_extendable_at_the_old_edge(db, test_user):
    """E50: Rohstempel vor 1.19.1 verloren — gespeicherte Zeit liegt exakt auf der
    alten Kante, die neue Hülle ist weiter."""
    prev = _setup(db, test_user, old=block_week(mon=[("15:00", "18:00")]),
                  new=block_week(mon=[("15:00", "19:00")]))
    lost = entry(db, test_user, MON, t(15), t(18, 15))
    kept = entry(db, test_user, date(2026, 6, 8), t(15), t(18, 15), raw_end=t(18, 30))
    result = _run(db, test_user, prev)
    assert [(c.entry_id, c.not_extendable) for c in result.flagged] == [(lost.id, "end")]
    assert [c.entry_id for c in result.changed] == [kept.id]
    assert (kept.end_time, kept.raw_end_time) == (t(18, 30), None)


def test_not_extendable_when_the_weekday_loses_its_blocks(db, test_user):
    """E50 / 9.2 Schritt 12 (Review Task 7): fallen die Blöcke des Wochentags
    weg, gilt dort keine Hülle mehr — die weiteste mögliche, also „auf dieser
    Seite weiter". Hauptfall: ein Altfenster aus #201 wird entfernt, die
    Rohstempel gingen vor 1.19.1 verloren. Ohne Hinweis bliebe der Eintrag still
    gekappt. Am Feiertag kappte auch der alte Snapshot nicht (#484) — ein Treffer
    auf der Kante wäre dort Zufall, kein verlorener Stempel."""
    old = block_week(mon=[("15:00", "18:00")], tue=[("08:00", "12:00")])
    prev = _setup(db, test_user, old=old, new=block_week(tue=[("08:00", "12:00")]))
    db.add(PublicHoliday(date=date(2026, 6, 8), name="Testfeiertag", year=2026, tenant_id=DEFAULT_TENANT_ID))
    db.commit()
    invalidate_holiday_cache()
    lost_end = entry(db, test_user, MON, t(15), t(18, 15))
    holiday = entry(db, test_user, date(2026, 6, 8), t(15), t(18, 15))
    lost_start = entry(db, test_user, date(2026, 6, 15), t(14, 45), t(17))
    stamped = entry(db, test_user, date(2026, 6, 22), t(15), t(18, 15), raw_end=t(18, 40))
    result = _run(db, test_user, prev)
    invalidate_holiday_cache()
    assert [(c.entry_id, c.not_extendable) for c in result.flagged] == [
        (lost_end.id, "end"), (lost_start.id, "start")]
    assert [c.entry_id for c in result.changed] == [stamped.id]
    assert (stamped.end_time, stamped.raw_end_time) == (t(18, 40), None)
    assert (lost_end.end_time, holiday.end_time, lost_start.start_time) == (t(18, 15), t(18, 15), t(14, 45))
    assert result.skipped == []


def test_rest_time_after_reclamp_counts_from_the_raw_stamp(db, test_user):
    """Spec 17.4 / UC-Review R3: nach der Neukappung misst §5 weiter die tatsächliche
    Anwesenheit — Rohstempel 19:00, nicht das gekappte Ende 18:15. Ab 19:00 bis zum
    Folgetag 05:30 sind es 10,5 h (Verstoß); ab 18:15 wären es 11,25 h (keiner)."""
    prev = _setup(db, test_user, old=block_week(mon=[("08:00", "19:00")], tue=[("08:00", "12:00")]),
                  new=block_week(mon=[("08:00", "18:00")], tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(19))
    entry(db, test_user, date(2026, 6, 2), t(5, 30), t(9))   # Dienstag, nicht neu gekappt (weekdays={0})
    [c] = _run(db, test_user, prev).changed
    assert (c.entry_id, e.end_time, e.raw_end_time) == (e.id, t(18, 15), t(19))
    db.flush()
    [v] = rest_time_service.check_rest_time_violations(db, test_user, 2026, month=6)
    assert (v["day1_date"], v["day1_end"], v["day2_start"], v["actual_rest_hours"]) == (
        "2026-06-01", "19:00:00", "05:30:00", 10.5)


def test_second_run_changes_nothing(db, test_user):
    prev = _setup(db, test_user)
    entry(db, test_user, MON, t(8), t(18))
    assert len(_run(db, test_user, prev).changed) == 1
    db.flush()
    again = _run(db, test_user, prev)
    assert again.changed == [] and again.skipped == []


def test_split_stamps_around_the_planned_gap(db, test_user):
    """Review Focus 2: zwei Einträge um die Mittagslücke — Beginnzeiten bleiben,
    jeder Eintrag trägt seine eigenen Lückenminuten, keine Kollision."""
    prev = _setup(db, test_user)
    morning = entry(db, test_user, MON, t(8), t(12, 40))
    afternoon = entry(db, test_user, MON, t(14, 20), t(18))
    result = _run(db, test_user, prev)
    assert result.skipped == []
    assert (morning.start_time, morning.uncredited_minutes) == (t(8), 25)
    assert (afternoon.start_time, afternoon.uncredited_minutes) == (t(14, 20), 25)


# ── P18: automatisch geschlossene Einträge — 23:59 ist nie ein Stempel ─────


def test_auto_closed_entry_reclamps_from_its_effective_end(db, test_user):
    """K15 unter neuen Blöcken: das wirksame Ende 18:15 ist die Kappungseingabe,
    das Kennzeichen und das Protokoll-Rohende 23:59 bleiben (P18)."""
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(8), t(18, 15), raw_end=t(23, 59), auto_closed=True)
    result = _run(db, test_user, prev)
    [c] = result.changed
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed) == (t(18, 15), t(23, 59), 150, True)
    assert c.new_net == Decimal("7.75")
    # gleiche Hülle, nur eine neue Lücke: nichts zu erweitern, also kein Hinweis
    assert (c.not_extendable, result.flagged) == (None, [])


def test_auto_closed_entry_is_never_extended_to_the_synthetic_end(db, test_user):
    """P18 (PR1-Review F1/N2): eine spätere Hülle verlängert einen automatisch
    geschlossenen Eintrag nicht — mit 23:59 als Eingabe würde bis 20:15 angerechnet
    (9,75 h statt 7,75 h), ohne dass je jemand ausgestempelt hat. Das Rohende
    23:59 ist kein Stempel: das Ende gilt als „ohne Rohstempel – nicht
    erweiterbar" (E50, Review Task 7), sonst erführe niemand, warum der Eintrag
    bei 18:15 bleibt."""
    prev = _setup(db, test_user, new=block_week(mon=[("08:00", "12:00"), ("15:00", "20:00")],
                                                tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(18, 15), raw_end=t(23, 59), auto_closed=True)
    result = _run(db, test_user, prev)
    [c] = result.changed
    assert _stored(e) == (t(8), t(18, 15), None, t(23, 59), 150, True)
    assert (c.old_net, c.new_net, c.not_extendable) == (Decimal("10.25"), Decimal("7.75"), "end")
    assert [(f.entry_id, f.not_extendable) for f in result.flagged] == [(e.id, "end")]


def test_auto_closed_entry_with_a_carried_raw_end_is_extended_not_flagged(db, test_user):
    """Gegenstück: nach einem Verschieben trägt das Rohende das übernommene
    wirksame Ende (``end_input_for``) — das ist die Anrechnungsgrenze, bis zu der
    eine spätere Hülle den Eintrag wieder erweitern darf; kein Hinweis."""
    prev = _setup(db, test_user, old=block_week(mon=[("08:00", "16:00")], tue=[("08:00", "12:00")]),
                  new=block_week(mon=[("08:00", "18:00")], tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(16, 15), raw_end=t(18, 15), auto_closed=True)
    result = _run(db, test_user, prev)
    [c] = result.changed
    assert (e.end_time, c.not_extendable, result.flagged) == (t(18, 15), None, [])


def test_auto_closed_entry_shrinks_and_comes_back_byte_identical(db, test_user):
    """17.5 Reversibilität: kürzere Hülle → das bisher angerechnete Ende wandert ins
    Rohende (wie beim Verschieben, ``end_input_for``); Rücknahme der Änderung →
    wieder exakt der Zustand des Auto-Close (18:15 / Rohende 23:59)."""
    add_row(db, test_user, date(2026, 1, 1), week=OLD)
    shorter = block_week(mon=[("08:00", "16:00")], tue=[("08:00", "12:00")])
    row = add_row(db, test_user, MON, week=shorter)
    e = entry(db, test_user, MON, t(8), t(18, 15), raw_end=t(23, 59), auto_closed=True)
    before = _stored(e)

    [c] = _run(db, test_user, work_blocks_service.parse_week_blocks(OLD).blocks).changed
    assert _stored(e) == (t(8), t(16, 15), None, t(18, 15), 0, True)
    assert (c.old_net, c.new_net) == (Decimal("10.25"), Decimal("8.25"))

    db.delete(row)
    db.flush()
    [back] = _run(db, test_user, work_blocks_service.parse_week_blocks(shorter).blocks).changed
    assert _stored(e) == before
    assert back.new_net == Decimal("10.25")


def test_collapsed_auto_closed_entry_keeps_its_synthetic_raw_end(db, test_user):
    """P18 / 17.5: eingestempelt 19:00 hinter der Hülle 18:15 — der Auto-Close
    kollabiert auf 19:00–19:00, Rohbeginn 19:00, Rohende 23:59. Bringt die
    Änderung nur eine Lücke und lässt die Hülle gleich, ändert sich nichts: keine
    Scheinänderung (0,00 → 0,00 h samt Protokollzeile), und das Rohende bleibt
    der Protokollwert 23:59 — sonst läse es sich als echter Stempel 19:00 (auch
    für §5) und eine Rücknahme stellte den Zustand nicht byte-gleich wieder her."""
    prev = _setup(db, test_user)
    e = entry(db, test_user, MON, t(19), t(19), raw_start=t(19), raw_end=t(23, 59), auto_closed=True)
    result = _run(db, test_user, prev)
    assert (result.changed, result.skipped, result.flagged) == ([], [], [])
    assert _stored(e) == (t(19), t(19), t(19), t(23, 59), 0, True)


def test_auto_closed_entry_keeps_its_marker_without_blocks(db, test_user):
    """Fallen die Blöcke des Wochentags weg, bleibt der Eintrag unverändert:
    angerechnet bis zum wirksamen Ende, Rohende 23:59 als Protokoll — keine
    Scheinänderung, keine Anrechnung bis 23:59. Ohne Hülle wäre das Ende
    erweiterbar, ein echter Stempel fehlt aber: Hinweis „nicht erweiterbar"
    (E50, Review Task 7)."""
    prev = _setup(db, test_user, new=block_week(tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(18, 15), raw_end=t(23, 59), auto_closed=True)
    result = _run(db, test_user, prev)
    assert (result.changed, result.skipped) == ([], [])
    assert [(f.entry_id, f.not_extendable, f.old_end, f.new_end) for f in result.flagged] == [
        (e.id, "end", t(18, 15), t(18, 15))]
    assert _stored(e) == (t(8), t(18, 15), None, t(23, 59), 0, True)


def test_auto_closed_without_blocks_is_clamped_like_the_auto_close(db, test_user):
    """Ohne Blöcke geschlossen (Ende 23:59 ungekappt, kein Rohende): neue Blöcke
    kappen ihn genau so, wie der Auto-Close unter ihnen gekappt hätte (K15)."""
    prev = _setup(db, test_user, old=block_week(tue=[("08:00", "12:00")]))
    e = entry(db, test_user, MON, t(8), t(23, 59), auto_closed=True)
    [c] = _run(db, test_user, prev).changed
    assert _stored(e) == (t(8), t(18, 15), None, t(23, 59), 150, True)
    assert c.new_net == Decimal("7.75")


def test_credited_minutes_for():
    k = [(480, 720), (900, 1080)]
    assert wws.credited_minutes_for(k, 15, 480, 1080) == 450        # K1
    assert wws.credited_minutes_for(k, 15, 420, 1140) == 480        # K7: Hülle + Lücke
    assert wws.credited_minutes_for(k, 15, 300, 420) == 0           # K8: Kollaps
    assert wws.credited_minutes_for([], 15, 480, 1080) == 600


def test_open_entry_loses_checks_every_kink():
    old = [(480, 720)]
    assert wws.open_entry_loses(old, [(480, 780)], 15, time(8), time(10)) is False   # Verlängerung
    assert wws.open_entry_loses(old, [(480, 660)], 15, time(8), time(10)) is True    # Hülle kürzer
    assert wws.open_entry_loses(old, [(480, 660)], 15, time(8), time(13)) is True    # auch nach Hüllenende
    assert wws.open_entry_loses(old, [(540, 720)], 15, time(8), time(8, 10)) is True  # Beginn vor neuer Hülle
    assert wws.open_entry_loses([(480, 720), (900, 1080)], [(480, 720), (840, 1080)], 15,
                                time(8), time(10)) is False                          # Lücke kleiner
    # Verlust nur an der inneren Knickstelle 12:15 (alt 255 gegen neu 225 Min) —
    # bei „jetzt" (120/120) und 23:59 (255/285) verliert der Eintrag nichts
    assert wws.open_entry_loses([(480, 720)], [(480, 600), (660, 780)], 15, time(8), time(10)) is True
    assert wws.open_entry_loses([], [], 15, time(8), time(10)) is False
