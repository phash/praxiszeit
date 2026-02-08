# PraxisZeit - Zeiterfassungssystem

Webbasiertes Zeiterfassungssystem für eine Arztpraxis in Bayern.

## Features

- ✅ Zeiterfassung (von–bis mit Pausen)
- ✅ Soll/Ist-Vergleich mit Überstundenkonto
- ✅ Urlaubsverwaltung (stundenbasiert)
- ✅ Bayerischer Feiertagskalender
- ✅ Abwesenheitskalender für alle Mitarbeiterinnen
- ✅ Excel-Export für Lohnbuchhaltung

## Technologie-Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL
- **Frontend:** React + TypeScript + Vite + Tailwind CSS
- **Deployment:** Docker Compose

## Installation

### Voraussetzungen

- Docker & Docker Compose
- (optional) Node.js 20+ für lokale Frontend-Entwicklung
- (optional) Python 3.12+ für lokale Backend-Entwicklung

### Setup

1. Repository klonen und ins Verzeichnis wechseln:
```bash
cd praxiszeit
```

2. Environment-Variablen konfigurieren:
```bash
cp .env.example .env
# Bearbeite .env und setze sichere Passwörter und Secret Key
```

3. Docker Container starten:
```bash
docker-compose up -d
```

4. Anwendung öffnen:
```
http://localhost
```

### Initiales Admin-Login

Die Zugangsdaten für den Admin-Account sind in der `.env`-Datei definiert:
- Email: Siehe `ADMIN_EMAIL`
- Passwort: Siehe `ADMIN_PASSWORD`

## Entwicklung

### Backend lokal ausführen

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend lokal ausführen

```bash
cd frontend
npm install
npm run dev
```

## Lizenz

Proprietär - Alle Rechte vorbehalten
