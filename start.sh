#!/bin/bash

echo ""
echo "========================================"
echo "  PraxisZeit - Zeiterfassungssystem"
echo "========================================"
echo ""

# Navigate to script directory
cd "$(dirname "$0")"

echo "[1/3] Starte Docker Container..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo ""
    echo "FEHLER: Docker-Container konnten nicht gestartet werden."
    echo "Stelle sicher, dass Docker läuft."
    exit 1
fi

echo ""
echo "[2/3] Warte auf Services..."
sleep 5

echo ""
echo "[3/3] Prüfe Status..."
docker-compose ps

echo ""
echo "========================================"
echo "  Server erfolgreich gestartet!"
echo "========================================"
echo ""
echo "  Frontend:  http://localhost"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "  Login: admin@example.com / admin123"
echo ""
echo "========================================"
echo ""
echo "Zum Stoppen: ./stop.sh ausführen"
echo ""
