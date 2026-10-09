#!/usr/bin/env python3
"""Mach-O-Abhaengigkeiten pruefen — ohne macOS-Werkzeuge (#482).

Die macOS-Pakete werden auf einem Linux-Host gebaut. Dort gibt es weder
``otool`` noch ``install_name_tool``; ``check_macos_binary_sanity`` in
``build-release.sh`` konnte deshalb nur pruefen, OB eine Datei ein Mach-O ist,
nicht WOGEGEN sie gelinkt ist. Genau so rutschten Load-Commands durch, die auf
den Build-Runner von theseus-rs zeigen
(``/Users/runner/work/postgresql-binaries/...``) — einen Pfad, den es auf
keinem Kunden-Mac gibt.

Dieses Skript liest die Load-Commands direkt aus den Mach-O-Kopfdaten
(duenne 32/64-Bit-Dateien und Universal-/Fat-Dateien) und meldet jede
Abhaengigkeit, die auf einem fremden Mac nicht aufloesbar ist.

Zulaessig sind:
  * ``@loader_path/``, ``@executable_path/``, ``@rpath/`` — relativ zum Paket
  * ``/usr/lib/`` und ``/System/Library/`` — Bestandteil jedes macOS

Alles andere (``/Users/...``, ``/opt/homebrew/...``, ``/usr/local/...``) ist ein
Fund.

``@rpath/`` ist nur so portabel wie die Suchpfade, gegen die dyld es aufloest.
Deshalb werden zusaetzlich die eigenen ``LC_RPATH``-Eintraege jeder Datei
geprueft: zulaessig sind ``@loader_path``/``@executable_path`` (mit oder ohne
Unterpfad), ``/usr/lib/`` und ``/System/Library/``; ein rpath auf den
Build-Runner oder nach Homebrew ist ein Fund (gemeldet als ``LC_RPATH <pfad>``).
Geerbte rpaths (vom ladenden Programm) zaehlen nicht als Fund — sie werden an
ihrer eigenen Datei geprueft. Aufruf::

    python3 tools/macho_deps.py [--prune] <verzeichnis> [<verzeichnis> ...]

``--prune`` entfernt vorher die Teile des theseus-PostgreSQL-Pakets, die
PraxisZeit nie ausfuehrt und die auf den Build-Runner zeigen (``PG_PRUNE``).
Exitcode 0 = keine Funde, 1 = Funde (Liste auf stdout), 2 = Aufruffehler.
Die Funktionen sind bewusst ohne Abhaengigkeiten ausserhalb der
Standardbibliothek, damit das Skript auf jedem Build-Host laeuft.

Stand theseus-rs 18.6.0 (#482, mit diesem Skript und ``llvm-objdump --macho
--dylibs-used`` gegengeprueft): ``dblink``, ``postgres_fdw`` und
``libpqwalreceiver`` laden ``libpq`` sauber ueber ``@loader_path``. Auf den
Runner zeigen nur die drei PGXS-Testtreiber unter ``lib/pgxs/src/test/``
(``pg_regress``, ``isolationtester``, ``pg_isolation_regress``) — Werkzeuge,
mit denen Entwickler selbst gebaute Erweiterungen testen (``make
installcheck``). PraxisZeit baut keine Erweiterungen; sie fallen weg.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
from typing import Iterable, List, Optional, Tuple

# Relativ zum PostgreSQL-Wurzelverzeichnis des Pakets (``bin/postgresql``).
PG_PRUNE = (
    "lib/pgxs/src/test",
)

# Mach-O-Magics (so, wie sie als Little-Endian-uint32 gelesen werden).
MH_MAGIC = 0xFEEDFACE  # 32 Bit
MH_MAGIC_64 = 0xFEEDFACF  # 64 Bit
MH_CIGAM = 0xCEFAEDFE  # 32 Bit, andere Bytereihenfolge
MH_CIGAM_64 = 0xCFFAEDFE  # 64 Bit, andere Bytereihenfolge
# Universal-/Fat-Header stehen immer Big-Endian in der Datei.
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF

# Load-Commands, die eine Bibliothek NACHLADEN (nicht LC_ID_DYLIB: das ist der
# eigene Installationsname einer Bibliothek und keine Abhaengigkeit).
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LAZY_LOAD_DYLIB = 0x20
LC_LOAD_UPWARD_DYLIB = 0x80000023
DYLIB_LOAD_COMMANDS = frozenset({
    LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB,
    LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB,
})
# Suchpfad fuer ``@rpath/``-Abhaengigkeiten (``struct rpath_command``: der
# Pfad-Offset steht wie beim dylib_command bei +8).
LC_RPATH = 0x8000001C

PORTABLE_PREFIXES = (
    "@loader_path/", "@executable_path/", "@rpath/",
    "/usr/lib/", "/System/Library/",
)
# Ein rpath darf selbst NICHT auf ``@rpath`` zeigen (loest nichts auf), dafuer
# aber ``@loader_path``/``@executable_path`` ohne Unterpfad sein.
PORTABLE_RPATH_PREFIXES = (
    "@loader_path/", "@executable_path/", "/usr/lib/", "/System/Library/",
)
PORTABLE_RPATH_EXACT = frozenset({"@loader_path", "@executable_path"})

# Ein Java-.class beginnt ebenfalls mit 0xCAFEBABE; dort steht an Stelle der
# Architektur-Anzahl die Versionsnummer (>= 45). Kein Universal-Binary hat so
# viele Architekturen.
_MAX_FAT_ARCHS = 30


def _read_cstr(data: bytes, start: int, end: int) -> str:
    nul = data.find(b"\x00", start, end)
    raw = data[start:nul if nul != -1 else end]
    return raw.decode("utf-8", errors="replace")


def _thin_refs(data: bytes, base: int) -> Optional[Tuple[List[str], List[str]]]:
    """(Abhaengigkeiten, rpaths) EINER Architektur ab Offset ``base`` — None,
    wenn dort kein Mach-O-Kopf steht."""
    if len(data) < base + 28:
        return None
    (magic_le,) = struct.unpack_from("<I", data, base)
    if magic_le in (MH_MAGIC, MH_MAGIC_64):
        endian = "<"
    elif magic_le in (MH_CIGAM, MH_CIGAM_64):
        endian = ">"
    else:
        return None
    is64 = magic_le in (MH_MAGIC_64, MH_CIGAM_64)
    _magic, _cpu, _sub, _ftype, ncmds, sizeofcmds, _flags = struct.unpack_from(
        endian + "7I", data, base)
    off = base + (32 if is64 else 28)
    limit = min(len(data), off + sizeofcmds)
    deps: List[str] = []
    rpaths_found: List[str] = []
    for _ in range(ncmds):
        if off + 8 > limit:
            break
        cmd, cmdsize = struct.unpack_from(endian + "2I", data, off)
        if cmdsize < 8 or off + cmdsize > limit:
            break  # kaputter Kopf: nicht weiterlesen statt Unsinn zu melden
        if (cmd in DYLIB_LOAD_COMMANDS or cmd == LC_RPATH) and cmdsize >= 12:
            (name_off,) = struct.unpack_from(endian + "I", data, off + 8)
            if 0 < name_off < cmdsize:
                value = _read_cstr(data, off + name_off, off + cmdsize)
                (rpaths_found if cmd == LC_RPATH else deps).append(value)
        off += cmdsize
    return deps, rpaths_found


def _merge(into: List[str], items: List[str]) -> None:
    for item in items:
        if item not in into:
            into.append(item)


def macho_refs(data: bytes) -> Optional[Tuple[List[str], List[str]]]:
    """(nachgeladene Bibliotheken, eigene LC_RPATH-Eintraege) einer Mach-O-Datei
    — alle Architekturen, Reihenfolge erhalten, ohne Doppelte. ``None``: keine
    Mach-O-Datei."""
    if len(data) < 8:
        return None
    (magic_be,) = struct.unpack_from(">I", data, 0)
    if magic_be in (FAT_MAGIC, FAT_MAGIC_64):
        (nfat,) = struct.unpack_from(">I", data, 4)
        if nfat == 0 or nfat > _MAX_FAT_ARCHS:
            return None
        entry = 32 if magic_be == FAT_MAGIC_64 else 20
        found: List[str] = []
        found_rpaths: List[str] = []
        any_arch = False
        for i in range(nfat):
            pos = 8 + i * entry
            if pos + entry > len(data):
                break
            if magic_be == FAT_MAGIC_64:
                _cpu, _sub, offset, _size = struct.unpack_from(">iiQQ", data, pos)
            else:
                _cpu, _sub, offset, _size = struct.unpack_from(">iiII", data, pos)
            refs = _thin_refs(data, offset)
            if refs is None:
                continue
            any_arch = True
            _merge(found, refs[0])
            _merge(found_rpaths, refs[1])
        return (found, found_rpaths) if any_arch else None
    return _thin_refs(data, 0)


def dylib_deps(data: bytes) -> Optional[List[str]]:
    """Alle nachgeladenen Bibliotheken einer Mach-O-Datei (alle Architekturen,
    Reihenfolge erhalten, ohne Doppelte). ``None``: keine Mach-O-Datei."""
    refs = macho_refs(data)
    return None if refs is None else refs[0]


def rpaths(data: bytes) -> Optional[List[str]]:
    """Die eigenen ``LC_RPATH``-Eintraege einer Mach-O-Datei. ``None``: keine
    Mach-O-Datei."""
    refs = macho_refs(data)
    return None if refs is None else refs[1]


def is_portable(dep: str) -> bool:
    """Laesst sich diese Abhaengigkeit auf einem beliebigen Mac aufloesen?"""
    return dep.startswith(PORTABLE_PREFIXES)


def is_portable_rpath(rpath: str) -> bool:
    """Zeigt dieser Suchpfad auf etwas, das es auf jedem Mac gibt bzw. das im
    Paket selbst liegt?"""
    return rpath in PORTABLE_RPATH_EXACT or rpath.startswith(PORTABLE_RPATH_PREFIXES)


def scan(roots: Iterable[str]) -> Tuple[int, List[Tuple[str, str]]]:
    """Durchsucht ``roots`` rekursiv. Liefert (Anzahl Mach-O-Dateien, Funde)
    mit Funden als ``(pfad, abhaengigkeit)``. Symlinks werden uebersprungen —
    ihr Ziel liegt im selben Baum und wird dort geprueft."""
    count = 0
    offenders: List[Tuple[str, str]] = []
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(dirpath, name)
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
                with open(path, "rb") as fh:
                    head = fh.read(8)
                    if len(head) < 8:
                        continue
                    (m_le,) = struct.unpack_from("<I", head, 0)
                    (m_be,) = struct.unpack_from(">I", head, 0)
                    if (m_le not in (MH_MAGIC, MH_MAGIC_64, MH_CIGAM, MH_CIGAM_64)
                            and m_be not in (FAT_MAGIC, FAT_MAGIC_64)):
                        continue
                    data = head + fh.read()
                refs = macho_refs(data)
                if refs is None:
                    continue
                count += 1
                deps, rps = refs
                for dep in deps:
                    if not is_portable(dep):
                        offenders.append((path, dep))
                for rp in rps:
                    if not is_portable_rpath(rp):
                        offenders.append((path, f"LC_RPATH {rp}"))
    return count, offenders


def prune(root: str) -> List[str]:
    """Entfernt ``PG_PRUNE`` unterhalb von ``root``; gibt die entfernten Pfade zurueck."""
    removed: List[str] = []
    for rel in PG_PRUNE:
        path = os.path.join(root, *rel.split("/"))
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
            removed.append(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(path)
    return removed


def main(argv: List[str]) -> int:
    args = argv[1:]
    do_prune = False
    if args and args[0] == "--prune":
        do_prune = True
        args = args[1:]
    roots = args
    if not roots:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("Aufruf: macho_deps.py [--prune] <verzeichnis> [<verzeichnis> ...]", file=sys.stderr)
        return 2
    for r in roots:
        if not os.path.isdir(r):
            print(f"Kein Verzeichnis: {r}", file=sys.stderr)
            return 2
    if do_prune:
        for r in roots:
            for path in prune(r):
                print(f"entfernt (wird nie ausgefuehrt): {path}", file=sys.stderr)
    count, offenders = scan(roots)
    if count == 0:
        # Ein leerer Fund waere sonst ein falsches „alles gut" (falscher Pfad,
        # kaputtes Paket) — dieselbe Falle wie die toten Pruefer in der CI.
        print("Keine Mach-O-Dateien gefunden — falscher Pfad?", file=sys.stderr)
        return 2
    for path, dep in offenders:
        print(f"{path}: {dep}")
    print(f"{count} Mach-O-Dateien geprueft, {len(offenders)} nicht portable Abhaengigkeit(en).",
          file=sys.stderr)
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
