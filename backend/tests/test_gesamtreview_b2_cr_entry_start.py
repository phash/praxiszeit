"""Gesamtreview 1.20 (B2, Folgefund): die Antragsprüfung kennt den AKTUELLEN
angerechneten Beginn des Zieleintrags (``entry_start_time``) — Gegenstück zu
``entry_end_time`` (``test_gesamtreview_b2_cr_entry_end.py``).

Die Prüfung legt neben einen offenen Änderungsantrag die Stempel des Eintrags
und meldet rot „Zeiten weichen von den Stempeln ab", wenn die beantragten
Zeiten nicht die Stempel sind (Gesamtreview PR2, Fund 2). Ein gewöhnlicher
Antrag schickt aber die vorbelegten ANGERECHNETEN Zeiten zurück (07:45–18:15
bei Stempel 07:00–19:00). Die Genehmigung wertet das als Echo
(``request_start_for_approval``/``request_end_for_approval`` + ``unclamp_input``)
und rechnet mit den Stempeln weiter — „genehmigen und anerkennen" erkennt
07:00–19:00 an. Echo ist der angerechnete Wert zum Zeitpunkt des Antrags
(``original_*``) ODER der aktuelle (``entry_start_time``/``entry_end_time``);
die Prüfung braucht beide, um dieselbe Regel anzuwenden.
"""
from datetime import time

import pytest

from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.test_gesamtreview_b2_request_echo import (
    LATER_START, _as_admin, _echo_request, _reclamp_monday, _stamped,
)


def test_response_carries_current_effective_start(_db_session, employee_user, admin_user,
                                                  employee_client):
    """Nach einer Neukappung (Hülle ab 08:45) weicht der aktuelle angerechnete
    Beginn vom damaligen (07:45) ab; der Stempel bleibt 07:00."""
    e = _stamped(_db_session, employee_user, time(7, 0), time(18, 0))
    cr = _echo_request(employee_client, _db_session, e)
    _reclamp_monday(_db_session, employee_user, LATER_START)

    _as_admin(admin_user)
    body = employee_client.get(f"/api/admin/change-requests/{cr.id}").json()
    assert body["original_start_time"] == "07:45:00"
    assert body["entry_start_time"] == "08:45:00"
    assert body["entry_raw_start_time"] == "07:00:00"


def test_list_carries_current_effective_start(_db_session, employee_user, admin_user,
                                              employee_client):
    """Die Prüfliste (Batch-Enricher) trägt das Feld ebenso."""
    e = _stamped(_db_session, employee_user, time(7, 0), time(18, 0))
    _echo_request(employee_client, _db_session, e)

    _as_admin(admin_user)
    rows = employee_client.get("/api/admin/change-requests?status=pending").json()
    assert [(r["entry_start_time"], r["entry_raw_start_time"]) for r in rows] == [
        ("07:45:00", "07:00:00"),
    ]


@pytest.mark.parametrize("reclamped", [False, True], ids=["ohne-neukappung", "nach-neukappung"])
def test_echo_request_granted_credits_the_stamps(_db_session, employee_user, admin_user,
                                                 employee_client, reclamped):
    """Die Regel, der die Prüfung folgt: ein Antrag mit den vorbelegten
    angerechneten Zeiten (07:45–18:15), genehmigt UND anerkannt, rechnet die
    Stempel 07:00–19:00 an — nicht die angezeigten beantragten Zeiten. Auch
    nach einer Neukappung (Echo = damaliger Wert ``original_*``)."""
    e = _stamped(_db_session, employee_user, time(7, 0), time(19, 0))
    assert (e.start_time, e.end_time) == (time(7, 45), time(18, 15))
    cr = _echo_request(employee_client, _db_session, e)
    if reclamped:
        _reclamp_monday(_db_session, employee_user, LATER_START)

    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve", "grant_credit_override": True})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert e.credit_override is True
    assert (e.start_time, e.end_time) == (time(7, 0), time(19, 0))
