"""Regression: eine Lizenz, die mit einem ANDEREN Schluessel als dem hinterlegten
Public Key signiert wurde (Key-Rotation-Szenario), muss einen klaren, NICHT
irrefuehrenden LicenseError werfen — nicht "corrupted/tampered".

Genau dieser Fall (Public-Key-Rotation KEY-A -> KEY-B) hat in 1.5.x einen
Produktiv-Server lahmgelegt: die alte Kundenlizenz wurde ungueltig. Seit 1.5.2
faengt main.py LicenseError ab und geht in Read-Only (kein sys.exit mehr) — und
die Meldung sagt klar, dass die Signatur nicht zum Schluessel passt.
"""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.license import validate_license, LicenseError


def _sign_with_foreign_key(claims: dict) -> str:
    priv = Ed25519PrivateKey.generate()  # NICHT der eingebettete Public Key
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwt.encode(claims, priv_pem, algorithm="EdDSA")


def test_foreign_key_signature_raises_clear_error(tmp_path):
    token = _sign_with_foreign_key(
        {"sub": "cust", "name": "Test", "max_employees": 5, "iat": 1700000000}
    )
    lic = tmp_path / "license.key"
    lic.write_text(token)

    with pytest.raises(LicenseError) as exc:
        validate_license(lic)

    msg = str(exc.value)
    # Klar + handlungsleitend (Schluessel-Hinweis), NICHT das irrefuehrende
    # "corrupted/tampered".
    assert "Schluessel" in msg
    assert "corrupt" not in msg.lower()
    assert "tamper" not in msg.lower()
