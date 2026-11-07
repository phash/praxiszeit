"""Audit 2026-11-07 S3-05: die nativen Pakete installieren die Python-
Abhaengigkeiten nur aus ``requirements.lock`` (exakte Versionen, SHA256 je
Datei, ``pip install --require-hashes``).

Die Tests halten die Lock-Datei an ``requirements.txt``: jede Anforderung muss
dort mit einer passenden Version stehen, jede Zeile gepinnt und gehasht sein.
Faellt ein Test, ``bash tools/lock-requirements.sh`` ausfuehren und den Diff
pruefen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

try:  # packaging liegt im Image transitiv vor, sonst die pip-eigene Kopie
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import Version
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.requirements import Requirement  # type: ignore
    from pip._vendor.packaging.utils import canonicalize_name  # type: ignore
    from pip._vendor.packaging.version import Version  # type: ignore

_BACKEND = Path(__file__).resolve().parents[1]
_REQ = _BACKEND / "requirements.txt"
_LOCK = _BACKEND / "requirements.lock"
_BUILD_REQ = _BACKEND / "requirements-build.txt"
_BUILD_LOCK = _BACKEND / "requirements-build.lock"


def _requirements(path: Path = _REQ) -> list[Requirement]:
    reqs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            reqs.append(Requirement(line))
    return reqs


def _lock_entries(path: Path = _LOCK) -> dict[str, list[tuple[Version, str, list[str]]]]:
    """name -> [(version, marker, hashes)] (ein Paket kann je Plattform/Marker
    mehrfach vorkommen)."""
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    entries: dict[str, list] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert not line.startswith(("-i", "--index-url", "--extra-index-url", "-e")), line
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)\s*(?:;\s*([^-]+?))?\s*((?:--hash=sha256:[0-9a-f]{64}\s*)+)$", line)
        assert m, f"Zeile nicht exakt gepinnt und gehasht: {line[:120]}"
        name, ver, marker, hashes = m.groups()
        entries.setdefault(canonicalize_name(name), []).append(
            (Version(ver), (marker or "").strip(), re.findall(r"[0-9a-f]{64}", hashes)))
    return entries


def test_lock_exists_next_to_requirements():
    assert _LOCK.is_file(), "backend/requirements.lock fehlt - bash tools/lock-requirements.sh"


def test_every_lock_line_is_pinned_and_hashed():
    entries = _lock_entries()
    assert len(entries) >= 30
    for name, versions in entries.items():
        for _ver, _marker, hashes in versions:
            assert hashes, name


@pytest.mark.parametrize("req", _requirements(), ids=lambda r: r.name)
def test_every_requirement_is_satisfied_by_the_lock(req):
    entries = _lock_entries()
    name = canonicalize_name(req.name)
    assert name in entries, f"{req.name} fehlt in requirements.lock - neu erzeugen"
    for ver, _marker, _hashes in entries[name]:
        assert req.specifier.contains(ver, prereleases=True), (
            f"{req.name}: requirements.txt verlangt {req.specifier}, Lock hat {ver} - "
            "bash tools/lock-requirements.sh"
        )


def test_windows_only_dependencies_are_in_the_lock():
    """Universal-Lock: unter Windows braucht click (uvicorn) colorama. Ein nur
    unter Linux erzeugter Lock scheiterte dort an --require-hashes."""
    entries = _lock_entries()
    assert "colorama" in entries
    assert any("win32" in marker for _v, marker, _h in entries["colorama"])


def test_build_lock_pins_hashed_setuptools_for_the_sdist_only_package():
    """odfpy hat auf PyPI nur ein Quellarchiv: die Pakete bauen es mit dem
    gehashten setuptools aus requirements-build.lock ohne Build-Isolation."""
    build = _lock_entries(_BUILD_LOCK)
    assert set(build) == {"setuptools"}
    for req in _requirements(_BUILD_REQ):
        for ver, _m, hashes in build[canonicalize_name(req.name)]:
            assert req.specifier.contains(ver) and hashes
    odfpy = _lock_entries()["odfpy"]
    assert odfpy and all(len(h) == 1 for _v, _m, h in odfpy)  # nur das sdist
