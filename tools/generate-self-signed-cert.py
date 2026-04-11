"""PraxisZeit self-signed SSL cert generator.

Generates cert.pem + key.pem for native Windows/Linux/macOS installations
where a real CA-signed cert isn't available (customer LAN, self-hosted).
Writes 2048-bit RSA with SHA-256, SubjectAltName including DNS:localhost,
IP:127.0.0.1 and the target IP, 10-year validity.

Usage:
    python generate-self-signed-cert.py <ip> [<practice_name>] [<out_dir>]

Example:
    python generate-self-signed-cert.py 192.168.1.5 "Praxis Klotz-Roedig"
    python generate-self-signed-cert.py 10.0.0.20 "Praxis X" /opt/praxiszeit/config/ssl

The default out_dir is C:\\praxiszeit\\config\\ssl on Windows, otherwise
the first existing of /opt/praxiszeit/config/ssl or ./config/ssl.

Requires the `cryptography` package (already shipped with the backend
requirements.txt, so the bundled Python interpreter can run this script
without additional installs).
"""
from __future__ import annotations

import ipaddress
import os
import platform
import sys
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def default_out_dir() -> str:
    if platform.system() == "Windows":
        return r"C:\praxiszeit\config\ssl"
    for candidate in ("/opt/praxiszeit/config/ssl", "/usr/local/praxiszeit/config/ssl"):
        if os.path.isdir(os.path.dirname(candidate)):
            return candidate
    return os.path.abspath("./config/ssl")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    ip = sys.argv[1]
    practice = sys.argv[2] if len(sys.argv) > 2 else "PraxisZeit"
    out_dir = sys.argv[3] if len(sys.argv) > 3 else default_out_dir()

    try:
        ip_obj = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError as exc:
        print(f"ERROR: {ip!r} is not a valid IPv4 address: {exc}", file=sys.stderr)
        return 1

    os.makedirs(out_dir, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, ip),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, practice),
    ])

    # 1.3.4: timezone-aware UTC (datetime.utcnow() was deprecated in Py 3.12)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ip_obj),
            ]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path = os.path.join(out_dir, "cert.pem")
    key_path = os.path.join(out_dir, "key.pem")

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )

    # Lock down the key file on Unix (0600). Windows inherits from parent.
    if platform.system() != "Windows":
        os.chmod(key_path, 0o600)

    print(f"OK cert: {cert_path} ({os.path.getsize(cert_path)} bytes)")
    print(f"OK key:  {key_path} ({os.path.getsize(key_path)} bytes)")
    print(f"CN={ip}  SAN=localhost,127.0.0.1,{ip}")
    print("Valid for 10 years")
    return 0


if __name__ == "__main__":
    sys.exit(main())
