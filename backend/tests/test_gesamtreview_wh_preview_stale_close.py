"""Gesamtreview 1.20 (Fund 10): die Überstunden-Zeile der Vorschau zählt das
P23-Schließen nicht mit.

``run_change`` schließt in Schritt 2 offene Einträge vergangener Tage und hält
erst danach den Saldo „vorher" fest — das Schließen ist nicht Wirkung der
Änderung (Spec 9.3). Beide Vorschauen erhoben ``overtime_before`` aber VOR dem
Lauf: ein offener Eintrag zählt dort 0 h, nach dem Schließen mit der Hülle. Das
Überstunden-Δ der Box enthielt so die Stunden eines vergessenen Ausstempelns,
Soll- und Angerechnet-Δ daneben nicht (Spec 9.5 (b): ohne abgeschlossenes Jahr
ist ``saldo_delta_hours`` genau ``overtime_after − overtime_before``).

Anna (Spec 12.1) hat am Mo 05.10.2026 vergessen auszustempeln (offen ab 08:00);
heute ist Do 08.10. Ab 01.10. entfällt ihr Donnerstagsblock — eine reine
Soll-Senkung, die Montage fasst sie nicht an."""
from datetime import date

import pytest

from app.models import TimeEntry
from tests.test_endpoints import test_app
from tests.wh_change_helpers import ANNA_WEEK, add_row, admin_client, entry, freeze, t
from tests.work_blocks_fixtures import block_week

EFF = date(2026, 10, 1)
STALE_DAY = date(2026, 10, 5)
NO_THURSDAY = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")])


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _post(client, url, body):
    resp = client.post(url, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assert_box_is_consistent(body):
    assert body["stale_entries_closed"] == 1
    # Δ Überstunden = Δ angerechnet − Δ Soll — ohne die Stunden des geschlossenen
    # Eintrags (vorher: +4,00 + 7,75 = +11,75).
    assert body["overtime_after"] - body["overtime_before"] == pytest.approx(body["saldo_delta_hours"])


def test_create_preview_overtime_delta_excludes_the_stale_close(client, db, test_user):
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    stale = entry(db, test_user, STALE_DAY, t(8), None)

    body = _post(client, f"/api/admin/users/{test_user.id}/working-hours-changes/preview",
                 {"effective_from": EFF.isoformat(), "blocks": NO_THURSDAY})

    assert (body["changed_weekdays"], body["affected_time_entries"]) == ([3], 0)
    assert (body["target_delta_hours"], body["credited_delta_hours"], body["saldo_delta_hours"]) == (-4.0, 0.0, 4.0)
    _assert_box_is_consistent(body)
    # Strikt lesend: der Eintrag bleibt offen.
    db.expire_all()
    assert db.get(TimeEntry, stale.id).end_time is None


def test_delete_preview_overtime_delta_excludes_the_stale_close(client, db, test_user):
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    row = add_row(db, test_user, EFF, week=NO_THURSDAY)
    stale = entry(db, test_user, STALE_DAY, t(8), None)

    body = _post(client, f"/api/admin/users/{test_user.id}/working-hours-changes/{row.id}/delete-preview", {})

    assert (body["target_delta_hours"], body["credited_delta_hours"], body["saldo_delta_hours"]) == (4.0, 0.0, -4.0)
    _assert_box_is_consistent(body)
    db.expire_all()
    assert db.get(TimeEntry, stale.id).end_time is None


def test_without_stale_entry_the_values_stay_the_current_account(client, db, test_user):
    """Kontrolle: ohne offenen Alteintrag ist „bisher" der aktuelle Kontostand
    (wie bisher vor dem Lauf erhoben). Ein geschlossener Eintrag, damit das Konto
    überhaupt beginnt (``get_overtime_account`` startet beim ersten Eintrag)."""
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    entry(db, test_user, date(2026, 9, 28), t(8), t(12))
    plain = _post(client, f"/api/admin/users/{test_user.id}/working-hours-changes/preview",
                  {"effective_from": EFF.isoformat(), "blocks": ANNA_WEEK})
    body = _post(client, f"/api/admin/users/{test_user.id}/working-hours-changes/preview",
                 {"effective_from": EFF.isoformat(), "blocks": NO_THURSDAY})
    assert body["stale_entries_closed"] == 0
    assert body["overtime_before"] == pytest.approx(plain["overtime_before"])
    assert body["overtime_after"] - body["overtime_before"] == pytest.approx(body["saldo_delta_hours"])
