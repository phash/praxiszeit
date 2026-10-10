"""Spec E9/E56/9.8: ``users.work_blocks`` ist Rückfall NUR für Tage vor der
ersten Verlaufszeile und Spiegel der jüngsten Zeile ≤ heute. Wer es live für
eine Berechnung läse, hebelte zukunftsdatierte Änderungen aus (kein Scheduler).

Der Guard prüft per ``ast`` jeden Attributzugriff ``.work_blocks`` und jedes
``getattr/setattr/hasattr(…, "work_blocks", …)`` in ``app/`` und vergleicht die
Fundstellen (Datei, umschließende Funktion) mit der Erlaubnisliste. PR2 ergänzt
den Art.-15/20-Export (``lifecycle_service._user_dict``, ``auth`` ``/me/export``)
und den §16-Notfallexport (``superadmin._user_dict``).
``work_blocks_today`` ist ein anderer Name und entsteht über den Resolver.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ALLOWED = {
    ("app/services/calculation_service.py", "get_schedule_for_date"),
    ("app/routers/admin_users.py", "_sync_user_from_change"),
    # PR2 (Spec 15.3 / E72): Auskunfts- und §16-Notfallexporte geben den
    # gespeicherten Rückfallwert unverändert aus — keine Berechnung.
    ("app/services/lifecycle_service.py", "_user_dict"),
    ("app/routers/auth.py", "export_my_data"),
    ("app/routers/superadmin.py", "_user_dict"),
}


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
        if node.attr == "work_blocks":
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "hasattr")
                and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "work_blocks"):
            self.found.add((self.rel, self._scope()))
        self.generic_visit(node)


def test_work_blocks_is_read_only_where_allowed():
    found = set()
    for path in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        finder = _Finder(path.relative_to(BACKEND).as_posix())
        finder.visit(ast.parse(path.read_text(encoding="utf-8")))
        found |= finder.found
    assert found == ALLOWED
