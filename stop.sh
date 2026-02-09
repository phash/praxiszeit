#!/bin/bash

echo ""
echo "========================================"
echo "  PraxisZeit - Server stoppen"
echo "========================================"
echo ""

# Navigate to script directory
cd "$(dirname "$0")"

echo "Stoppe Docker Container..."
docker-compose down

if [ $? -ne 0 ]; then
    echo ""
    echo "FEHLER: Fehler beim Stoppen der Container."
    exit 1
fi

echo ""
echo "========================================"
echo "  Server erfolgreich gestoppt!"
echo "========================================"
echo ""
echo "Alle Container wurden gestoppt."
echo "Daten bleiben im Volume erhalten."
echo ""
