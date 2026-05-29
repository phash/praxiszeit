"""Regression: nach der 1.5.x-Public-Key-Rotation waren Bestandslizenzen (mit
dem ALTEN Schlüssel signiert) im Backend ungültig, weil nur der NEUE Key
eingebettet war. Fix: `validate_license` akzeptiert beide Schlüssel (alt + neu).

Die echten alten/neuen Keys werden hier statisch geprüft; die Mehr-Schlüssel-
Mechanik funktional über ein synthetisches Keypaar (das echte alte Private-Key
liegt offline und gehört nicht ins Repo).
"""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app.core.license as lic
from app.core.license import validate_license, LicenseError


def _priv_pem(priv: Ed25519PrivateKey) -> bytes:
    return priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _pub_pem(priv: Ed25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_both_known_keys_are_configured():
    blob = b"\n".join(lic._PUBLIC_KEYS_PEM)
    # NEU (aktuelle Shop-Ausstellung) UND ALT (Bestandslizenzen vor der Rotation)
    assert b"t8zaDoRf" in blob, "neuer Public Key fehlt"
    assert b"B5ZiJro" in blob, "alter (Bestands-)Public Key fehlt"


def test_accepts_token_signed_by_any_configured_key(tmp_path, monkeypatch):
    # Zwei Keypaare; nur das ZWEITE ist nicht-erstes Element der Liste.
    first = Ed25519PrivateKey.generate()
    second = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "_PUBLIC_KEYS_PEM", [_pub_pem(first), _pub_pem(second)])

    token = jwt.encode(
        {"sub": "c", "name": "Test Müller", "max_employees": 5, "iat": 1700000000},
        _priv_pem(second),
        algorithm="EdDSA",
    )
    p = tmp_path / "license.key"
    p.write_text(token)

    info = validate_license(p)  # darf NICHT werfen — zweiter Key matcht
    assert info.customer_name == "Test Müller"
    assert info.max_employees == 5


def test_rejects_token_signed_by_unconfigured_key(tmp_path, monkeypatch):
    configured = Ed25519PrivateKey.generate()
    foreign = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "_PUBLIC_KEYS_PEM", [_pub_pem(configured)])

    token = jwt.encode(
        {"sub": "c", "name": "X", "max_employees": 1, "iat": 1700000000},
        _priv_pem(foreign),
        algorithm="EdDSA",
    )
    p = tmp_path / "license.key"
    p.write_text(token)

    with pytest.raises(LicenseError) as exc:
        validate_license(p)
    msg = str(exc.value)
    assert "corrupt" not in msg.lower() and "tamper" not in msg.lower()


def test_utf8_bom_license_file_is_read(tmp_path, monkeypatch):
    # Eine versehentlich mit BOM gespeicherte license.key (z.B. via Notepad)
    # darf nicht als „beschädigt" durchfallen.
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "_PUBLIC_KEYS_PEM", [_pub_pem(key)])
    token = jwt.encode(
        {"sub": "c", "name": "BOM", "max_employees": 2, "iat": 1700000000},
        _priv_pem(key),
        algorithm="EdDSA",
    )
    p = tmp_path / "license.key"
    p.write_bytes(b"\xef\xbb\xbf" + token.encode("ascii"))  # UTF-8 BOM + token

    info = validate_license(p)
    assert info.customer_name == "BOM"
