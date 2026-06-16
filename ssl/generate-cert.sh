#!/bin/bash
# Generiert ein selbstsigniertes SSL-Zertifikat fuer PraxisZeit
# Gueltig fuer 10 Jahre, akzeptiert alle lokalen IPs

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Generiere selbstsigniertes SSL-Zertifikat..."

# Server-IP ermitteln
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Erkannte Server-IP: ${SERVER_IP:-<keine>}"

# SAN konditionell: leeres SERVER_IP (IPv6-only/loopback) sonst -> openssl-Fehler.
# Hostname mitnehmen (Zugriff via https://<host>/).
SAN="DNS:localhost,IP:127.0.0.1"
[ -n "$SERVER_IP" ] && SAN="$SAN,IP:$SERVER_IP"
HOST_FQDN=$(hostname -f 2>/dev/null || hostname 2>/dev/null || true)
[ -n "$HOST_FQDN" ] && [ "$HOST_FQDN" != "localhost" ] && SAN="$SAN,DNS:$HOST_FQDN"

# Zertifikat generieren (10 Jahre gueltig)
# End-Entity-Server-Zertifikat: CA:FALSE + keyUsage + extendedKeyUsage=serverAuth.
# Ohne diese Extensions ist es ein CA-Cert ohne serverAuth, das Browser nicht
# als Server-Zertifikat akzeptieren (Feldreport 2026-06, native ed25519-Variante).
openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$SCRIPT_DIR/key.pem" \
    -out "$SCRIPT_DIR/cert.pem" \
    -subj "/O=PraxisZeit/CN=praxiszeit" \
    -addext "subjectAltName=$SAN" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
    -addext "extendedKeyUsage=serverAuth"

echo ""
echo "Zertifikat erstellt:"
echo "  $SCRIPT_DIR/cert.pem"
echo "  $SCRIPT_DIR/key.pem"
echo ""
echo "Naechste Schritte:"
echo "  1. docker compose down"
echo "  2. docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d"
echo "  3. https://$SERVER_IP im Browser oeffnen"
echo "  4. Beim ersten Zugriff die Browser-Warnung akzeptieren"
