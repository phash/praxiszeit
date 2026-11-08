"""Signatur der Sicherungen (Audit 2026-11-07, Fix-Runde S3-03).

``app.core.backup_mac`` (Backend, Docker-Skripte) und ``praxiszeit-server.py``
(nativ, ohne Abhaengigkeiten) rechnen dieselbe Signatur - eine Sicherung der
Weboberflaeche muss sich mit ``praxiszeit-server.py restore`` einspielen lassen
und umgekehrt.
"""
from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import backup_mac

_SERVER = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"
_KEY = "k" * 64
_DUMP = b"--\n-- PostgreSQL database dump\n--\nCREATE TABLE t ();\n-- PostgreSQL database dump complete\n"


def _signed(data: bytes, key: str = _KEY) -> bytes:
    signer = backup_mac.BackupMac(key)
    for i in range(0, len(data), 7):  # in Bloecken wie beim Schreiben
        signer.update(data[i:i + 7])
    return data + signer.trailer()


def test_trailer_is_one_comment_line():
    signed = _signed(_DUMP)
    trailer = signed[len(_DUMP):]
    assert trailer.startswith(b"-- praxiszeit-backup-hmac-v1 ") and trailer.endswith(b"\n")
    assert trailer.count(b"\n") == 1 and len(trailer) == 29 + 64 + 1


def test_verify_ok_missing_mismatch():
    signed = _signed(_DUMP)
    assert backup_mac.verify_stream(io.BytesIO(signed), _KEY) == backup_mac.OK
    assert backup_mac.verify_stream(io.BytesIO(_DUMP), _KEY) == backup_mac.MISSING
    assert backup_mac.verify_stream(io.BytesIO(signed), "anders") == backup_mac.MISMATCH
    tampered = signed.replace(b"CREATE TABLE t", b"CREATE TABLE u")
    assert backup_mac.verify_stream(io.BytesIO(tampered), _KEY) == backup_mac.MISMATCH
    # angehaengte Zeilen nach der Signatur = keine Signatur am Ende
    assert backup_mac.verify_stream(io.BytesIO(signed + b"DROP TABLE t;\n"), _KEY) == backup_mac.MISSING


def test_large_dump_across_read_chunks():
    big = b"".join(b"INSERT %d;\n" % i for i in range(300_000))  # > 1 MiB Leseblock
    signed = _signed(big)
    assert backup_mac.verify_stream(io.BytesIO(signed), _KEY) == backup_mac.OK


def test_dump_without_final_newline_gets_one_inside_the_signature():
    signed = _signed(b"SELECT 1;")
    assert signed.startswith(b"SELECT 1;\n-- praxiszeit-backup-hmac-v1 ")
    assert backup_mac.verify_stream(io.BytesIO(signed), _KEY) == backup_mac.OK


def test_cli_sign_and_verify(tmp_path, monkeypatch):
    env = {"SECRET_KEY": _KEY, "PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(backup_mac.__file__).parents[2])}
    sign = subprocess.run([sys.executable, "-m", "app.core.backup_mac", "sign"], input=_DUMP,
                          capture_output=True, env=env, check=True)
    assert sign.stdout == _signed(_DUMP)[len(_DUMP):]
    ok = subprocess.run([sys.executable, "-m", "app.core.backup_mac", "verify"],
                        input=_DUMP + sign.stdout, capture_output=True, env=env)
    assert ok.returncode == 0
    missing = subprocess.run([sys.executable, "-m", "app.core.backup_mac", "verify"],
                             input=_DUMP, capture_output=True, env=env)
    assert missing.returncode == 3
    bad = subprocess.run([sys.executable, "-m", "app.core.backup_mac", "verify"],
                         input=_DUMP + sign.stdout, capture_output=True, env={**env, "SECRET_KEY": "x"})
    assert bad.returncode == 4
    nokey = subprocess.run([sys.executable, "-m", "app.core.backup_mac", "sign"], input=_DUMP,
                           capture_output=True, env={**env, "SECRET_KEY": ""})
    assert nokey.returncode == 2 and nokey.stdout == b""


@pytest.mark.skipif(not _SERVER.exists(), reason="praxiszeit-server.py nicht im Container")
def test_native_and_backend_compute_the_same_signature():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_mac", _SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    native = srv.BackupMac(_KEY)
    native.update(_DUMP)
    assert native.trailer() == _signed(_DUMP)[len(_DUMP):]
    assert srv.verify_backup_mac(io.BytesIO(_signed(_DUMP)), _KEY) == "ok"
    assert srv.verify_backup_mac(io.BytesIO(_DUMP), _KEY) == "missing"
    assert srv.verify_backup_mac(io.BytesIO(_signed(_DUMP, "x")), _KEY) == "mismatch"
