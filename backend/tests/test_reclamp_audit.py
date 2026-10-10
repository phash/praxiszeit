"""Spec 10.1/10.2: Notizen der Neukappung, Sammelzeile schreiben UND lesen (P7).

Round-Trip für n = 0, 1, 2, 14, Saldo Δ negativ/0/positiv, mit/ohne Verkürzung,
mit Löschkennzeichen, mit Rücksetzung. Die Grundtyp-Präfixe sind eingefroren
(19.1 Nr. 7) — die Sammelzeile trägt nie eine Beschriftung, nur das Präfix.
"""
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import TimeEntry, TimeEntryAuditLog
from app.routers.admin_time_entries import _audit_note_is_health_sensitive
from app.services import calculation_service, reclamp_audit as ra, work_blocks_service
from app.services.work_window_service import credit_summary_text
from tests.work_blocks_fixtures import block_week, legacy_week

EFF = date(2026, 9, 1)


def _schedule(*, week=None, weekly=Decimal("40"), daily=None, work_days=5):
    parsed = work_blocks_service.parse_week_blocks(week) if week else None
    return calculation_service.Schedule(
        weekly_hours=weekly,
        use_daily_schedule=daily is not None,
        day_hours=tuple(Decimal(str(v)) if v else None for v in (daily or (None,) * 5)),
        work_days_per_week=work_days,
        blocks=parsed.blocks if parsed else None,
        block_pauses=parsed.pauses if parsed else None,
    )


def _summary(**overrides):
    kwargs = dict(
        effective_from=EFF, deleted=False, count=3, delta_minutes=-135, saldo_delta_minutes=105,
        skipped={"credit_override": 1}, grace=15, credit_reductions=0, reset_of=None,
        shortening=True, reason_type="erfassungsfehler",
        reason_text_value="Mo-Nachmittagsblock war seit 01.09. mit 18:00 statt 17:00 hinterlegt",
        contract_before="Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00",
        contract_after="Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00",
    )
    kwargs.update(overrides)
    return ra.summary_note(**kwargs)


class TestReasonTypes:
    def test_keys_prefixes_and_labels_are_the_decided_ones(self):
        assert {k: (v.prefix, v.label) for k, v in ra.REASON_TYPES.items()} == {
            "erfassungsfehler": ("[Erfassungsfehler korrigiert]", "Arbeitszeit war falsch hinterlegt (Fehlerkorrektur)"),
            "einvernehmlich": ("[Einvernehmlich vereinbart]", "Mit der beschäftigten Person vereinbart"),
            "sonstiges": ("[Sonstiges]", "Sonstiges"),
        }

    def test_compose_change_note(self):
        assert ra.compose_change_note("Teilzeit", None, None) == "Teilzeit"
        assert ra.compose_change_note(None, "einvernehmlich", "Montags bis 19 Uhr vereinbart") == (
            "[Einvernehmlich vereinbart] Montags bis 19 Uhr vereinbart")
        assert ra.compose_change_note("Vertrag v. 01.09.", "sonstiges", "  Ganz anderer Grund  ") == (
            "[Sonstiges] Ganz anderer Grund · Vertrag v. 01.09.")

    @pytest.mark.parametrize("key", ["erfassungsfehler", "einvernehmlich", "sonstiges"])
    def test_prefix_without_free_text_is_not_health_sensitive(self, key):
        """Spec 9.5: „[Sonstiges]" enthält das Label des maskierten Typs OTHER und
        entgeht dem Token „Sonstiges " nur durch die schließende Klammer."""
        summary = _summary(reason_type=key, reason_text_value="")
        entry_note = ra.entry_new_note("angerechnet 7:30 h", effective_from=EFF, deleted=False, old_grace=15,
                                       grace=15, shortening=True, reason_type=key, reason_text_value="")
        for note in (summary, entry_note):
            assert not _audit_note_is_health_sensitive(TimeEntryAuditLog(old_note=None, new_note=note)), note


class TestContractText:
    def test_new_blocks_compact_and_long(self):
        sched = _schedule(week=block_week(pause=30, mon=[("08:00", "12:00"), ("15:00", "18:00")]))
        assert ra.contract_text(sched, compact=True) == "Mo 08:00–12:00+15:00–18:00 P30"
        assert ra.contract_text(sched, compact=False) == "Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min)"

    def test_without_blocks(self):
        assert ra.contract_text(_schedule(weekly=Decimal("20")), compact=True) == "20,0 h/Woche (gleichmäßig, 5 Tage)"
        assert ra.contract_text(_schedule(weekly=Decimal("8"), work_days=1), compact=True) == "8,0 h/Woche (gleichmäßig, 1 Tag)"
        assert ra.contract_text(_schedule(weekly=Decimal("17"), daily=(8, 5, 4, 0, 0), work_days=3),
                                compact=False) == "Mo 8,0 / Di 5,0 / Mi 4,0 = 17,0 h/Woche"

    def test_legacy_window_names_hours_and_window(self):
        sched = _schedule(weekly=Decimal("40"), week=legacy_week(mon=("07:30", "16:30"), fri=("07:30", None)))
        assert ra.contract_text(sched, compact=True) == (
            "40,0 h/Woche (gleichmäßig, 5 Tage) · Mo 07:30–16:30 / Fr 07:30–23:59 (nur Kappung)")


class TestSummaryNote:
    def test_spec_example_one(self):
        assert _summary() == (
            "Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min, "
            "1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] "
            "Mo-Nachmittagsblock war seit 01.09. mit 18:00 statt 17:00 hinterlegt · Vertrag: "
            "Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → "
            "Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00"
        )

    def test_spec_example_without_entries(self):
        assert _summary(effective_from=date(2026, 11, 1), count=0, delta_minutes=0, saldo_delta_minutes=0,
                        skipped={}, shortening=False, reason_type=None, reason_text_value=None,
                        contract_before="20,0 h/Woche (gleichmäßig, 5 Tage)",
                        contract_after="25,0 h/Woche (gleichmäßig, 5 Tage)") == (
            "Arbeitszeit-Änderung ab 01.11.2026: 0 Einträge neu berechnet, Δ +0 Min, Saldo Δ +0 Min "
            "· Puffer 15 Min · Vertrag: 20,0 h/Woche (gleichmäßig, 5 Tage) → 25,0 h/Woche (gleichmäßig, 5 Tage)"
        )

    def test_credit_reductions_reset_and_deleted(self):
        assert " · 1 Abwesenheits-Gutschrift gesenkt · " in _summary(credit_reductions=1)
        assert " · 2 Abwesenheits-Gutschriften gesenkt · " in _summary(credit_reductions=2)
        reset = _summary(reset_of=EFF, effective_from=date(2026, 10, 9), shortening=False, reason_type=None)
        assert " · Rücksetzung der Änderung ab 01.09.2026 · " in reset
        assert _summary(deleted=True).startswith("Arbeitszeit-Änderung ab 01.09.2026 gelöscht: ")

    def test_skipped_breakdown_lists_every_reason(self):
        note = _summary(skipped={"credit_override": 1, "open": 1, "unique_collision": 2})
        assert ", 4 übersprungen (1 anerkannt, 1 offen, 2 Überschneidung) · " in note

    def test_unknown_skip_reason_fails_loudly(self):
        """Ein neuer ``ReclampSkip.reason`` ohne Wort in :data:`SKIP_LABELS` darf
        nicht still aus der Aufzählung fallen — sonst stünde „2 übersprungen
        (1 anerkannt)" im Protokoll."""
        with pytest.raises(ValueError, match="neuer_grund"):
            _summary(skipped={"credit_override": 1, "neuer_grund": 1})

    @pytest.mark.parametrize("count", [0, 1, 2, 14])
    @pytest.mark.parametrize("saldo", [-225, 0, 15])
    @pytest.mark.parametrize("shortening, reason", [(False, None), (True, "erfassungsfehler"),
                                                    (True, "einvernehmlich"), (True, "sonstiges")])
    @pytest.mark.parametrize("deleted", [False, True])
    @pytest.mark.parametrize("reset_of", [None, date(2026, 3, 1)])
    def test_round_trip(self, count, saldo, shortening, reason, deleted, reset_of):
        note = _summary(count=count, delta_minutes=-count * 45, saldo_delta_minutes=saldo,
                        shortening=shortening, reason_type=reason, deleted=deleted, reset_of=reset_of,
                        reason_text_value="Freitext · Verkürzung · Rücksetzung der Änderung ab 01.01.2020 · ")
        parsed = ra.parse_summary_note(note)
        assert parsed == ra.SummaryNote(EFF, deleted, count, -count * 45, saldo, shortening, reason, reset_of)
        assert ("1 Eintrag neu" in note) == (count == 1)

    def test_free_text_never_fakes_flags(self):
        """P12: der Freitext nach „Grund:" wird nie gelesen."""
        note = _summary(shortening=True, reason_type="sonstiges",
                        reason_text_value="x · Rücksetzung der Änderung ab 01.01.2020 · y")
        assert ra.parse_summary_note(note).reset_of is None

    @pytest.mark.parametrize("note", [None, "", "Krank 4,0 h — Arbeitszeit-Änderung ab 01.09.2026",
                                      "angerechnet 7:30 h — Arbeitszeit-Änderung ab 01.09.2026"])
    def test_foreign_notes_are_not_summaries(self, note):
        assert ra.parse_summary_note(note) is None


class TestEntryNote:
    def test_trigger_grace_and_reason(self):
        assert ra.entry_new_note("angerechnet 2:15 h, nicht angerechnet 0:45 h", effective_from=EFF,
                                 deleted=False, old_grace=15, grace=10, shortening=True,
                                 reason_type="erfassungsfehler", reason_text_value="Falsch hinterlegt seit 09") == (
            "angerechnet 2:15 h, nicht angerechnet 0:45 h — Arbeitszeit-Änderung ab 01.09.2026 · Puffer 15 → 10 Min "
            "· Grund: [Erfassungsfehler korrigiert] Falsch hinterlegt seit 09")

    def test_delete_trigger_and_no_grace_note_for_null_or_equal(self):
        assert ra.entry_new_note("angerechnet 3:00 h", effective_from=EFF, deleted=True, old_grace=None, grace=15,
                                 shortening=False, reason_type=None, reason_text_value=None) == (
            "angerechnet 3:00 h — Löschung der Arbeitszeit-Änderung ab 01.09.2026")
        assert " · Puffer" not in ra.entry_new_note("x", effective_from=EFF, deleted=False, old_grace=15, grace=15,
                                                     shortening=False, reason_type=None, reason_text_value=None)


class TestCreditSummaryText:
    def _e(self, start, end, unc=0, brk=0, raw_start=None, raw_end=None):
        return TimeEntry(start_time=start, end_time=end, raw_start_time=raw_start, raw_end_time=raw_end,
                         break_minutes=brk, uncredited_minutes=unc, auto_closed=False)

    def test_k1_gap_only(self):
        # PR2 Task 1: „davon …" auch, wenn die Lücke die Gesamtzahl ist (Beispiele 10.1/13.3).
        assert credit_summary_text(self._e(time(8), time(18), unc=150)) == (
            "angerechnet 7:30 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken")

    def test_k7_hull_and_gap(self):
        assert credit_summary_text(self._e(time(7, 45), time(18, 15), unc=150, raw_start=time(7), raw_end=time(19))) == (
            "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken")

    def test_k9_with_pause(self):
        assert credit_summary_text(self._e(time(8), time(18), unc=150, brk=30)) == (
            "angerechnet 7:00 h, nicht angerechnet 2:30 h, davon 2:30 h zwischen den Blöcken, Pause 0:30 h")

    def test_nothing_withheld(self):
        assert credit_summary_text(self._e(time(8), time(12))) == "angerechnet 4:00 h"
