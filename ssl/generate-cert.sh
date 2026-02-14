#!/bin/bash
# Generiert ein selbstsigniertes SSL-Zertifikat fuer PraxisZeit
# Gueltig fuer 10 Jahre, akzeptiert alle lokalen IPs

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Generiere selbstsigniertes SSL-Zertifikat..."

# Server-IP ermitteln
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Erkannte Server-IP: $SERVER_IP"

# Zertifikat generieren (10 Jahre gueltig)
openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$SCRIPT_DIR/key.pem" \
    -out "$SCRIPT_DIR/cert.pem" \
    -subj "/C=DE/ST=Bayern/L=Muenchen/O=Praxis Klotz-Roedig/CN=praxiszeit" \
    -addext "subjectAltName=IP:$SERVER_IP,IP:127.0.0.1,DNS:localhost"

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
