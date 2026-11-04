"""Teil A (Vertragsverlauf): die fünf historisierten Vertragsfelder
(``vacation_days``, ``track_hours``, ``milog_working_time_account``,
``agreed_monthly_hours``, ``use_fixed_monthly_target``) werden für einen Tag
bzw. Monat über den Snapshot aufgelöst (``get_schedule_for_date``,
``tracks_hours_on``, ``month_contract``, ``vacation_entitlement_days`` …), nie
live von der User-Zeile. Die User-Zeile ist nur Rückfall (keine Verlaufszeile)
und Spiegel der jüngsten Zeile ≤ heute.

Der Guard prüft per ``ast`` in ``app/services`` und ``app/routers`` jeden
Attributzugriff ``<empfänger>.<feld>`` und jedes
``getattr/setattr/hasattr(<empfänger>, "<feld>", …)``, wenn der Empfänger eine
User-Zeile ist: ein Name aus ``USER_NAMES`` oder ein Subscript/Aufruf (z. B.
``_participants_by_id[a.user_id].track_hours``, ``users.get(id).track_hours``).
Snapshot-Lesungen laufen über eine benannte Variable (``schedule``, ``mc``,
``norm``, ``row``) oder direkt am Resolver-Aufruf (``SNAPSHOT_RESOLVERS``,
z. B. ``month_contract(...).fixed_mode``); Request-Bodies (``user_data``, ``update_data``) und
Verlaufszeilen sind keine User-Zeilen und werden nicht gemeldet.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FIELDS = {
    "vacation_days",
    "track_hours",
    "milog_working_time_account",
    "agreed_monthly_hours",
    "use_fixed_monthly_target",
}
USER_NAMES = {"user", "u", "current_user", "employee", "emp", "User"}
# Aufrufe dieser Resolver liefern einen Snapshot (``Schedule``/``MonthContract``),
# keine User-Zeile: ``get_schedule_for_date(...).track_hours`` ist DIE erlaubte
# Lesart und wird deshalb nicht als Subscript/Call-Empfänger gemeldet.
SNAPSHOT_RESOLVERS = {"get_schedule_for_date", "month_contract"}
ALLOWED = {
    ("app/services/calculation_service.py", "get_schedule_for_date"),   # no-row fallback
    ("app/services/calculation_service.py", "get_daily_target"),        # legacy, classic export corner
    ("app/routers/admin_users.py", "_sync_user_from_change"),           # mirror
    ("app/routers/auth.py", "export_my_data"),                          # Art. 15/20 raw export
    ("app/services/lifecycle_service.py", "_user_dict"),
    ("app/routers/superadmin.py", "_user_dict"),
}


def _is_user_receiver(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id in USER_NAMES
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        return name not in SNAPSHOT_RESOLVERS
    return isinstance(node, ast.Subscript)


class _Finder(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel, self.stack, self.found = rel, [], set()

    def _scope(self):
        return self.stack[-1] if self.stack else "<modul>"

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node):
        if node.attr in FIELDS and _is_user_receiver(node.value):
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "hasattr")
                and len(node.args) >= 2 and _is_user_receiver(node.args[0])
                and isinstance(node.args[1], ast.Constant) and node.args[1].value in FIELDS):
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)


def _scan() -> set:
    found = set()
    for sub in ("app/services", "app/routers"):
        for path in sorted((BACKEND / sub).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            finder = _Finder(path.relative_to(BACKEND).as_posix())
            finder.visit(ast.parse(path.read_text(encoding="utf-8")))
            found |= finder.found
    return found


def test_contract_fields_are_read_live_only_where_allowed():
    found = _scan()
    # Nicht leer laufen: der Spiegel schreibt die Felder nachweislich.
    assert ("app/routers/admin_users.py", "_sync_user_from_change") in found
    assert sorted(found - ALLOWED) == [], "Live-Lesungen außerhalb der Erlaubnisliste"
    assert sorted(ALLOWED - found) == [], "Erlaubnisliste enthält überholte Einträge"


def test_finder_catches_getattr_and_subscript_receivers():
    src = (
        "def f(users, by_id):\n"
        "    getattr(user, 'track_hours', True)\n"
        "def g(users, by_id):\n"
        "    by_id[1].vacation_days\n"
        "def h(users):\n"
        "    users.get(1).agreed_monthly_hours\n"
        "def k(schedule, user_data):\n"
        "    schedule.track_hours; user_data.track_hours; getattr(row, 'track_hours')\n"
        "    get_schedule_for_date(db, user, d).track_hours\n"
        "    cs.month_contract(db, user, 2026, 1).use_fixed_monthly_target\n"
        "def m(employee):\n"
        "    setattr(employee, 'vacation_days', 30)\n"
    )
    finder = _Finder("x.py")
    finder.visit(ast.parse(src))
    assert finder.found == {("x.py", "f"), ("x.py", "g"), ("x.py", "h"), ("x.py", "m")}
