#!/usr/bin/env python3
"""
PraxisZeit License Generator

Generates Ed25519-signed JWT license keys for native PraxisZeit installations.

Usage:
    # 1. Generate a keypair (once)
    python license-generator.py generate-keypair

    # 2. Generate a license
    python license-generator.py generate \
        --customer-id "praxis-mueller" \
        --customer-name "Praxis Dr. Mueller" \
        --max-employees 20 \
        --expires 2027-12-31 \
        --private-key private.pem \
        --output license.key

    # 3. Verify a license
    python license-generator.py verify \
        --license license.key \
        --public-key public.pem

    # 4. Show license info
    python license-generator.py info --license license.key
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
        load_pem_private_key,
        load_pem_public_key,
    )
except ImportError:
    print("Error: Required packages not installed.")
    print("Run: pip install PyJWT[crypto] cryptography")
    sys.exit(1)


def cmd_generate_keypair(args):
    """Generate an Ed25519 keypair for license signing."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    private_path = Path(args.private_key)
    public_path = Path(args.public_key)

    if private_path.exists() and not args.force:
        print(f"Error: {private_path} already exists. Use --force to overwrite.")
        sys.exit(1)

    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)
    public_path.write_bytes(public_pem)

    print(f"Private key: {private_path} (KEEP THIS SECRET!)")
    print(f"Public key:  {public_path}")
    print()
    print("Next steps:")
    print(f"  1. Copy the public key into backend/app/core/license.py (_PUBLIC_KEY_PEM)")
    print(f"  2. Set _PUBLIC_KEY_CONFIGURED = True in license.py")
    print(f"  3. Store {private_path} securely (NOT in the repository!)")


def cmd_generate(args):
    """Generate a signed license JWT."""
    private_path = Path(args.private_key)
    if not private_path.is_file():
        print(f"Error: Private key not found: {private_path}")
        print("Run: python license-generator.py generate-keypair")
        sys.exit(1)

    private_pem = private_path.read_bytes()
    private_key = load_pem_private_key(private_pem, password=None)

    if not isinstance(private_key, Ed25519PrivateKey):
        print("Error: Private key is not Ed25519")
        sys.exit(1)

    now = datetime.now(timezone.utc)

    payload = {
        "sub": args.customer_id,
        "name": args.customer_name,
        "max_employees": args.max_employees,
        "features": args.features.split(",") if args.features else ["base"],
        "iat": int(now.timestamp()),
        "v": 1,
    }

    if args.no_expiry:
        expires_dt = None
    else:
        try:
            expires_dt = datetime.strptime(args.expires, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            print(f"Error: Invalid date format '{args.expires}'. Use YYYY-MM-DD.")
            sys.exit(1)

    if expires_dt:
        payload["exp"] = int(expires_dt.timestamp())

    token = jwt.encode(payload, private_key, algorithm="EdDSA")

    output_path = Path(args.output)
    output_path.write_text(token)

    print(f"License generated: {output_path}")
    print(f"  Customer:  {args.customer_name} ({args.customer_id})")
    print(f"  Employees: max {args.max_employees}")
    print(f"  Features:  {payload['features']}")
    print(f"  Expires:   {'NEVER' if not expires_dt else args.expires}")
    print(f"  Issued:    {now.strftime('%Y-%m-%d %H:%M UTC')}")


def cmd_verify(args):
    """Verify a license file against a public key."""
    license_path = Path(args.license)
    public_path = Path(args.public_key)

    if not license_path.is_file():
        print(f"Error: License file not found: {license_path}")
        sys.exit(1)
    if not public_path.is_file():
        print(f"Error: Public key not found: {public_path}")
        sys.exit(1)

    token = license_path.read_text().strip()
    public_pem = public_path.read_bytes()
    public_key = load_pem_public_key(public_pem)

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["EdDSA"],
            options={"verify_exp": False},
        )
    except jwt.InvalidSignatureError:
        print("INVALID: License signature verification failed!")
        sys.exit(1)
    except jwt.DecodeError as e:
        print(f"INVALID: Not a valid JWT: {e}")
        sys.exit(1)

    expires_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None
    is_expired = expires_dt and datetime.now(timezone.utc) > expires_dt

    print("VALID: License signature verified.")
    print(f"  Customer:  {payload.get('name', '?')} ({payload.get('sub', '?')})")
    print(f"  Employees: max {payload.get('max_employees', '?')}")
    print(f"  Features:  {payload.get('features', ['base'])}")
    if expires_dt:
        print(f"  Expires:   {expires_dt.strftime('%Y-%m-%d')}" + (" [EXPIRED]" if is_expired else ""))
    else:
        print(f"  Expires:   NEVER")


def cmd_info(args):
    """Show license info without verification (decode only)."""
    license_path = Path(args.license)
    if not license_path.is_file():
        print(f"Error: License file not found: {license_path}")
        sys.exit(1)

    token = license_path.read_text().strip()

    try:
        # Decode without verification to show contents
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["EdDSA"],
        )
    except jwt.DecodeError as e:
        print(f"Error: Not a valid JWT: {e}")
        sys.exit(1)

    expires_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None
    issued_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else None

    print("License info (NOT verified):")
    print(f"  Customer ID:   {payload.get('sub', '?')}")
    print(f"  Customer Name: {payload.get('name', '?')}")
    print(f"  Max Employees: {payload.get('max_employees', '?')}")
    print(f"  Features:      {payload.get('features', ['base'])}")
    print(f"  Version:       {payload.get('v', '?')}")
    if issued_dt:
        print(f"  Issued:        {issued_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    if expires_dt:
        is_expired = datetime.now(timezone.utc) > expires_dt
        print(f"  Expires:       {expires_dt.strftime('%Y-%m-%d')}" + (" [EXPIRED]" if is_expired else ""))

    if args.json:
        print("\nRaw payload:")
        print(json.dumps(payload, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="PraxisZeit License Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate-keypair
    kp = subparsers.add_parser("generate-keypair", help="Generate Ed25519 keypair")
    kp.add_argument("--private-key", default="private.pem", help="Output private key path (default: private.pem)")
    kp.add_argument("--public-key", default="public.pem", help="Output public key path (default: public.pem)")
    kp.add_argument("--force", action="store_true", help="Overwrite existing files")
    kp.set_defaults(func=cmd_generate_keypair)

    # generate
    gen = subparsers.add_parser("generate", help="Generate a signed license")
    gen.add_argument("--customer-id", required=True, help="Customer identifier (e.g. praxis-mueller)")
    gen.add_argument("--customer-name", required=True, help="Customer display name")
    gen.add_argument("--max-employees", type=int, required=True, help="Maximum number of employees")
    gen.add_argument("--expires", default=None, help="Expiry date (YYYY-MM-DD)")
    gen.add_argument("--no-expiry", action="store_true", help="License never expires")
    gen.add_argument("--features", default="base", help="Comma-separated feature list (default: base)")
    gen.add_argument("--private-key", default="private.pem", help="Private key path (default: private.pem)")
    gen.add_argument("--output", "-o", default="license.key", help="Output license file (default: license.key)")
    gen.set_defaults(func=cmd_generate)

    # verify
    ver = subparsers.add_parser("verify", help="Verify a license against public key")
    ver.add_argument("--license", required=True, help="License file to verify")
    ver.add_argument("--public-key", default="public.pem", help="Public key path (default: public.pem)")
    ver.set_defaults(func=cmd_verify)

    # info
    inf = subparsers.add_parser("info", help="Show license info (no verification)")
    inf.add_argument("--license", required=True, help="License file")
    inf.add_argument("--json", action="store_true", help="Also show raw JSON payload")
    inf.set_defaults(func=cmd_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
