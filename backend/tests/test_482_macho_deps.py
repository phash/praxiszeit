"""#482: Mach-O-Abhaengigkeiten der macOS-Pakete auf dem Linux-Build-Host pruefen.

``tools/macho_deps.py`` liest die Load-Commands direkt aus den Mach-O-Koepfen
(ohne ``otool``) und meldet jede Bibliothek, die auf einem fremden Mac nicht
aufloesbar ist — etwa einen Pfad auf dem Build-Runner von theseus-rs.
``build-release.sh`` ruft es fuer beide macOS-Pakete auf und bricht bei einem
Fund ab.

Die Tests bauen kleine, aber formal gueltige Mach-O-Dateien selbst. Sie brauchen
das Repo-Wurzelverzeichnis (``../tools``) und ueberspringen sich im reinen
Backend-Container (wie ``test_native_pg_lifecycle.py``).
"""
from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TOOL = _REPO / "tools" / "macho_deps.py"
_BUILD = _REPO / "tools" / "build-release.sh"

pytestmark = pytest.mark.skipif(
    not _TOOL.is_file(), reason=f"tools/macho_deps.py nicht erreichbar unter {_TOOL}",
)

RUNNER = (
    "/Users/runner/work/postgresql-binaries/postgresql-binaries/"
    "postgresql-18.6.0-aarch64-apple-darwin/lib/libpq.5.dylib"
)
LIBPQ = "@loader_path/../lib/libpq.5.dylib"
LIBSYSTEM = "/usr/lib/libSystem.B.dylib"

LC_LOAD_DYLIB = 0xC
LC_ID_DYLIB = 0xD
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_RPATH = 0x8000001C


@pytest.fixture(scope="module")
def md():
    spec = importlib.util.spec_from_file_location("macho_deps", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dylib_cmd(cmd: int, name: str, endian: str) -> bytes:
    raw = name.encode() + b"\0"
    size = (24 + len(raw) + 7) & ~7
    body = struct.pack(endian + "6I", cmd, size, 24, 2, 0x50000, 0x50000) + raw
    return body + b"\0" * (size - len(body))


def _rpath_cmd(path: str, endian: str) -> bytes:
    raw = path.encode() + b"\0"
    size = (12 + len(raw) + 7) & ~7
    body = struct.pack(endian + "3I", LC_RPATH, size, 12) + raw
    return body + b"\0" * (size - len(body))


def _macho(deps, *, bits=64, endian="<", own_id=None, weak=(), rpath=None) -> bytes:
    cmds = []
    if own_id:
        cmds.append(_dylib_cmd(LC_ID_DYLIB, own_id, endian))
    cmds += [_dylib_cmd(LC_LOAD_DYLIB, d, endian) for d in deps]
    cmds += [_dylib_cmd(LC_LOAD_WEAK_DYLIB, d, endian) for d in weak]
    if rpath:
        cmds.append(_rpath_cmd(rpath, endian))
    blob = b"".join(cmds)
    magic = 0xFEEDFACF if bits == 64 else 0xFEEDFACE
    head = struct.pack(endian + "7I", magic, 0x0100000C, 0, 6, len(cmds), len(blob), 0)
    if bits == 64:
        head += b"\0" * 4  # reserved
    return head + blob


def _fat(*slices: bytes) -> bytes:
    header = struct.pack(">II", 0xCAFEBABE, len(slices))
    offset = 4096
    entries, payload = b"", b""
    for s in slices:
        entries += struct.pack(">iiIII", 0x0100000C, 0, offset + len(payload), len(s), 12)
        payload += s
    pad = b"\0" * (offset - len(header) - len(entries))
    return header + entries + pad + payload


# --- Parser ---------------------------------------------------------------

def test_reads_load_commands_and_ignores_own_install_name(md):
    data = _macho([LIBPQ, LIBSYSTEM], own_id=RUNNER)
    # LC_ID_DYLIB ist der eigene Name der Bibliothek, keine Abhaengigkeit.
    assert md.dylib_deps(data) == [LIBPQ, LIBSYSTEM]


def test_weak_dependencies_count_too(md):
    assert md.dylib_deps(_macho([LIBSYSTEM], weak=[RUNNER])) == [LIBSYSTEM, RUNNER]


def test_rpath_is_not_a_dependency(md):
    # LC_RPATH ist ein Suchpfad, keine Bibliothek — er steht in rpaths(), nicht
    # in dylib_deps(); geprueft wird er trotzdem (siehe scan-Tests unten).
    assert md.dylib_deps(_macho([LIBSYSTEM], rpath="/Users/runner/lib")) == [LIBSYSTEM]


def test_rpaths_are_read_from_thin_and_universal_files(md):
    assert md.rpaths(_macho([LIBSYSTEM], rpath="/Users/runner/lib")) == ["/Users/runner/lib"]
    assert md.rpaths(_macho([LIBSYSTEM])) == []
    fat = _fat(_macho([LIBSYSTEM], rpath="@loader_path/../lib"),
               _macho([LIBSYSTEM], rpath="/Users/runner/lib"))
    assert md.rpaths(fat) == ["@loader_path/../lib", "/Users/runner/lib"]
    assert md.rpaths(b"#!/bin/sh\n") is None


@pytest.mark.parametrize("rpath,ok", [
    ("@loader_path/../lib", True),
    ("@loader_path", True),
    ("@executable_path/../lib", True),
    ("/usr/lib/swift", True),
    ("/System/Library/Frameworks", True),
    ("/Users/runner/work/postgresql-binaries/lib", False),
    ("/opt/homebrew/lib", False),
    ("/usr/local/lib", False),
    # Ein rpath, der selbst wieder auf @rpath zeigt, loest nichts auf.
    ("@rpath/../lib", False),
])
def test_rpath_portability_rule(md, rpath, ok):
    assert md.is_portable_rpath(rpath) is ok


@pytest.mark.parametrize("bits,endian", [(64, "<"), (32, "<"), (64, ">"), (32, ">")])
def test_thin_files_of_every_width_and_byte_order(md, bits, endian):
    assert md.dylib_deps(_macho([RUNNER], bits=bits, endian=endian)) == [RUNNER]


def test_universal_binary_unions_all_architectures(md):
    data = _fat(_macho([LIBPQ, LIBSYSTEM]), _macho([RUNNER, LIBSYSTEM]))
    assert md.dylib_deps(data) == [LIBPQ, LIBSYSTEM, RUNNER]


def test_java_class_file_is_not_mistaken_for_a_universal_binary(md):
    # Gleiche Magic 0xCAFEBABE, an Stelle der Architektur-Anzahl die Version 52.
    assert md.dylib_deps(struct.pack(">IHH", 0xCAFEBABE, 0, 52) + b"\0" * 64) is None


@pytest.mark.parametrize("data", [b"", b"#!/bin/sh\necho hi\n", b"\x7fELF" + b"\0" * 60])
def test_other_files_are_not_mach_o(md, data):
    assert md.dylib_deps(data) is None


def test_truncated_header_does_not_crash(md):
    data = _macho([RUNNER, LIBSYSTEM])
    assert md.dylib_deps(data[:40]) == []


@pytest.mark.parametrize("dep,ok", [
    (LIBPQ, True),
    ("@rpath/libfoo.dylib", True),
    ("@executable_path/../lib/libx.dylib", True),
    (LIBSYSTEM, True),
    ("/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation", True),
    (RUNNER, False),
    ("/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib", False),
    ("/usr/local/opt/openssl@3/lib/libcrypto.3.dylib", False),
    ("libbare.dylib", False),
])
def test_portability_rule(md, dep, ok):
    assert md.is_portable(dep) is ok


# --- Verzeichnis-Pruefung + Bereinigung ----------------------------------

def _theseus_like_tree(root: Path) -> Path:
    """Nachbau des theseus-18.6.0-Befunds: Module sauber, PGXS-Testtreiber nicht."""
    pg = root / "bin" / "postgresql"
    (pg / "bin").mkdir(parents=True)
    (pg / "lib" / "pgxs" / "src" / "test" / "regress").mkdir(parents=True)
    (pg / "lib" / "pgxs" / "src" / "makefiles").mkdir(parents=True)
    (pg / "bin" / "postgres").write_bytes(_macho(["@loader_path/../lib/libssl.3.dylib", LIBSYSTEM]))
    for mod in ("dblink.dylib", "postgres_fdw.dylib", "libpqwalreceiver.dylib"):
        (pg / "lib" / mod).write_bytes(_macho([LIBPQ, LIBSYSTEM]))
    (pg / "lib" / "libpq.5.dylib").write_bytes(_macho([LIBSYSTEM], own_id=LIBPQ))
    (pg / "lib" / "libpq.dylib").symlink_to("libpq.5.dylib")
    (pg / "lib" / "pgxs" / "src" / "test" / "regress" / "pg_regress").write_bytes(
        _macho([RUNNER, LIBSYSTEM]))
    (pg / "lib" / "pgxs" / "src" / "makefiles" / "pgxs.mk").write_text("# make\n")
    return pg


def test_scan_reports_only_the_non_portable_file(md, tmp_path):
    pg = _theseus_like_tree(tmp_path)
    count, offenders = md.scan([str(pg)])
    assert count == 6  # Symlink und Makefile zaehlen nicht
    assert offenders == [(str(pg / "lib" / "pgxs" / "src" / "test" / "regress" / "pg_regress"), RUNNER)]


def test_scan_reports_a_runner_rpath(md, tmp_path):
    """#482 (Review-Nachzug): ``@rpath/`` gilt als portabel — aber nur, solange
    der rpath, gegen den es aufgeloest wird, selbst portabel ist. Ein kuenftiges
    theseus-Paket mit ``@rpath/libpq.5.dylib`` und ``LC_RPATH /Users/runner/...``
    kaeme sonst durch und laedt auf keinem Kunden-Mac (das #183-Muster)."""
    pg = _theseus_like_tree(tmp_path)
    mod = pg / "lib" / "dblink.dylib"
    mod.write_bytes(_macho(["@rpath/libpq.5.dylib", LIBSYSTEM],
                           rpath="/Users/runner/work/postgresql-binaries/lib"))
    md.prune(str(pg))
    _count, offenders = md.scan([str(pg)])
    assert offenders == [(str(mod), "LC_RPATH /Users/runner/work/postgresql-binaries/lib")]


def test_scan_accepts_a_package_relative_rpath(md, tmp_path):
    pg = _theseus_like_tree(tmp_path)
    (pg / "lib" / "dblink.dylib").write_bytes(
        _macho(["@rpath/libpq.5.dylib", LIBSYSTEM], rpath="@loader_path/../lib"))
    md.prune(str(pg))
    assert md.scan([str(pg)])[1] == []


def test_cli_fails_on_a_runner_rpath(md, tmp_path, capsys):
    pg = _theseus_like_tree(tmp_path)
    (pg / "bin" / "postgres").write_bytes(
        _macho(["@rpath/libssl.3.dylib", LIBSYSTEM], rpath="/opt/homebrew/opt/openssl@3/lib"))
    assert md.main(["macho_deps.py", "--prune", str(pg)]) == 1
    assert "LC_RPATH /opt/homebrew/opt/openssl@3/lib" in capsys.readouterr().out


def test_cli_fails_on_a_runner_path(md, tmp_path, capsys):
    pg = _theseus_like_tree(tmp_path)
    assert md.main(["macho_deps.py", str(pg)]) == 1
    assert RUNNER in capsys.readouterr().out


def test_cli_prune_removes_the_pgxs_test_drivers_and_passes(md, tmp_path):
    pg = _theseus_like_tree(tmp_path)
    assert md.main(["macho_deps.py", "--prune", str(pg)]) == 0
    assert not (pg / "lib" / "pgxs" / "src" / "test").exists()
    # Alles, was PraxisZeit braucht, bleibt — auch die drei Module aus #482,
    # die in 18.6.0 sauber ueber @loader_path laden.
    assert (pg / "lib" / "pgxs" / "src" / "makefiles" / "pgxs.mk").exists()
    for mod in ("dblink.dylib", "postgres_fdw.dylib", "libpqwalreceiver.dylib", "libpq.5.dylib"):
        assert (pg / "lib" / mod).exists(), mod


def test_cli_prune_does_not_hide_other_offenders(md, tmp_path, capsys):
    pg = _theseus_like_tree(tmp_path)
    (pg / "lib" / "dblink.dylib").write_bytes(_macho([RUNNER, LIBSYSTEM]))
    assert md.main(["macho_deps.py", "--prune", str(pg)]) == 1
    assert "dblink.dylib" in capsys.readouterr().out


def test_cli_refuses_a_tree_without_any_mach_o(md, tmp_path):
    # Ein falscher Pfad darf kein „alles sauber" ergeben.
    (tmp_path / "leer.txt").write_text("x")
    assert md.main(["macho_deps.py", str(tmp_path)]) == 2
    assert md.main(["macho_deps.py", str(tmp_path / "gibt-es-nicht")]) == 2
    assert md.main(["macho_deps.py"]) == 2


# --- Einbindung in den Build --------------------------------------------------

def test_build_release_checks_both_macos_packages():
    """Leitplanke: die Pruefung haengt im macOS-Bau und bricht ihn bei Fund ab."""
    src = _BUILD.read_text(encoding="utf-8")
    start = src.index("_build_macos_arch() {")
    end = src.index("\n    }\n", start)
    body = src[start:end]
    assert 'tools/macho_deps.py" --prune "${mac_dir}/bin/postgresql"' in body, body
    call = body.index("macho_deps.py")
    assert "exit 1" in body[call:call + 600], "Fund muss den Build abbrechen"
    # Vor dem Packen, nicht danach.
    assert call < body.index('tar -czf "${DIST_DIR}/praxiszeit-${APP_VERSION}-macos-${arch}.tar.gz"')
