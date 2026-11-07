"""Signatur der Datenbank-Sicherungen (Audit 2026-11-07, Fix-Runde S3-03).

Ein Restore spielt den Dump als PostgreSQL-Superuser ein. Eine präparierte
"Sicherung vom alten Rechner" könnte dabei mehr als Daten mitbringen
(``COPY … TO PROGRAM`` über einen ``DO``-Block, neue Rollen, ``BYPASSRLS``) —
eine Liste verbotener Anweisungen kann das nie vollständig ausschließen.
Deshalb trägt jede Sicherung, die PraxisZeit selbst schreibt, am Ende eine
Signaturzeile:

    -- praxiszeit-backup-hmac-v1 <64 Hex-Zeichen>

HMAC-SHA256 über alle Bytes des (entpackten) Dumps VOR dieser Zeile; der
Schlüssel wird aus dem ``SECRET_KEY`` der Installation abgeleitet. Die Zeile
ist für psql ein Kommentar, die Datei bleibt ein normaler Plain-SQL-Dump
(``gunzip -c … | psql`` geht weiter). Restore-Werkzeuge spielen eine Datei ohne
passende Signatur nur mit ausdrücklichem ``--force-unverified`` ein.

Dieselbe Rechnung steht (ohne Abhängigkeiten) in ``praxiszeit-server.py``
(``BackupMac``/``verify_backup_mac``); ``test_backup_mac.py`` hält beide gleich.

Kommandozeile (Docker-Skripte ``backup.sh``/``restore.sh``, im Backend-Container
mit dessen ``SECRET_KEY``)::

    python -m app.core.backup_mac sign    < dump.sql   # druckt die Signaturzeile
    python -m app.core.backup_mac verify  < dump.sql   # Exit 0 ok, 3 fehlt, 4 passt nicht
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import sys
from typing import BinaryIO, Optional

LABEL = b"praxiszeit-backup-hmac-v1"
MARKER = b"-- " + LABEL + b" "
_LINE_RE = re.compile(rb"^-- praxiszeit-backup-hmac-v1 ([0-9a-f]{64})$")
# Mehr als eine Signaturzeile (95 Bytes) zurückhalten, damit sie beim Lesen in
# Blöcken nie zerteilt in den HMAC geht.
_HOLDBACK = 256
_CHUNK = 1024 * 1024

OK = "ok"
MISSING = "missing"
MISMATCH = "mismatch"


def derive_key(secret_key: str) -> bytes:
    """Eigener Schlüssel je Zweck (nicht der SECRET_KEY selbst)."""
    return hmac.new(secret_key.encode("utf-8"), LABEL, hashlib.sha256).digest()


class BackupMac:
    """Signatur beim Schreiben mitrechnen: ``update`` je Block, am Ende
    ``trailer()`` in dieselbe Datei schreiben."""

    def __init__(self, secret_key: str):
        self._mac = hmac.new(derive_key(secret_key), digestmod=hashlib.sha256)
        self._last = b"\n"

    def update(self, data: bytes) -> None:
        if data:
            self._mac.update(data)
            self._last = data[-1:]

    def trailer(self) -> bytes:
        prefix = b""
        if self._last != b"\n":
            # Die Signatur muss auf einer eigenen Zeile stehen; der Zeilenumbruch
            # gehört zum signierten Inhalt.
            prefix = b"\n"
            self._mac.update(prefix)
            self._last = b"\n"
        return prefix + MARKER + self._mac.hexdigest().encode("ascii") + b"\n"


def verify_stream(stream: BinaryIO, secret_key: str) -> str:
    """Prüft die letzte Zeile des Datenstroms. ``ok``, ``missing`` (keine
    Signaturzeile) oder ``mismatch`` (Inhalt verändert / anderer Schlüssel)."""
    mac = hmac.new(derive_key(secret_key), digestmod=hashlib.sha256)
    tail = b""
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            break
        data = tail + chunk
        if len(data) > _HOLDBACK:
            mac.update(data[:-_HOLDBACK])
            tail = data[-_HOLDBACK:]
        else:
            tail = data
    if not tail.endswith(b"\n"):
        return MISSING
    cut = tail.rfind(b"\n", 0, len(tail) - 1)
    line = tail[cut + 1:-1].rstrip(b"\r")
    match = _LINE_RE.match(line)
    if not match:
        return MISSING
    mac.update(tail[:cut + 1])
    if hmac.compare_digest(mac.hexdigest().encode("ascii"), match.group(1)):
        return OK
    return MISMATCH


def _secret_key() -> Optional[str]:
    key = os.environ.get("SECRET_KEY", "").strip()
    return key or None


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("sign", "verify"):
        print("Aufruf: python -m app.core.backup_mac sign|verify < dump.sql", file=sys.stderr)
        return 2
    key = _secret_key()
    if not key:
        print("FEHLER: SECRET_KEY ist nicht gesetzt.", file=sys.stderr)
        return 2
    stdin = sys.stdin.buffer
    if argv[0] == "sign":
        signer = BackupMac(key)
        while True:
            chunk = stdin.read(_CHUNK)
            if not chunk:
                break
            signer.update(chunk)
        sys.stdout.buffer.write(signer.trailer())
        sys.stdout.buffer.flush()
        return 0
    status = verify_stream(stdin, key)
    if status == OK:
        return 0
    return 3 if status == MISSING else 4


if __name__ == "__main__":  # pragma: no cover - Kommandozeile
    sys.exit(main(sys.argv[1:]))
