"""P4.4: ``users.vacation_carryover_deadline`` ist über PUT /api/admin/users/{id}
setz- und löschbar (die Benutzerform schickt das ISO-Datum bzw. null) und kommt in
den Leseschemas zurück (Edit-Reset-Regel: UserResponse + UserListResponse)."""
from datetime import date

from tests.test_child_sick import (  # noqa: F401  (Fixtures + Helfer wiederverwendet)
    USERS, _client_as, admin, db, default_tenant, employee,
)


def test_put_sets_and_clears_individual_deadline(db, admin, employee):
    client = _client_as(db, admin, admin)

    r = client.put(f"{USERS}/{employee.id}", json={"vacation_carryover_deadline": "2027-06-30"})
    assert r.status_code == 200, r.text
    assert r.json()["vacation_carryover_deadline"] == "2027-06-30"
    db.refresh(employee)
    assert employee.vacation_carryover_deadline == date(2027, 6, 30)

    listed = client.get(USERS).json()
    row = next(u for u in listed if u["id"] == str(employee.id))
    assert row["vacation_carryover_deadline"] == "2027-06-30"

    r = client.put(f"{USERS}/{employee.id}", json={"vacation_carryover_deadline": None})
    assert r.status_code == 200, r.text
    db.refresh(employee)
    assert employee.vacation_carryover_deadline is None
