# Spec: [Feature-Name]

**Status:** Draft | Ready | In Progress | Done
**Erstellt:** YYYY-MM-DD
**Zuletzt aktualisiert:** YYYY-MM-DD
**Zugehörige Issues:** #XX

---

## Überblick

_Kurzbeschreibung in 2–3 Sätzen: Was macht dieses Feature, und warum wird es gebraucht?_

---

## Requirements

### Funktionale Anforderungen

Als **[Rolle: MA/Admin]** möchte ich **[Aktion]**, damit ich **[Nutzen]**.

- [ ] **REQ-1**: _Konkretes, messbares Akzeptanzkriterium_
- [ ] **REQ-2**: _..._
- [ ] **REQ-3**: _..._

### Nicht-funktionale Anforderungen

- [ ] Performance: _z.B. "Antwort in < 500ms"_
- [ ] Sicherheit: _z.B. "Nur Admins dürfen X"_
- [ ] Validierung: _z.B. "Datum darf nicht in der Vergangenheit liegen"_

### Out of Scope

- _Was explizit **nicht** in diesem Feature enthalten ist_

---

## Design

### Datenbank

```sql
-- Neue Tabelle oder Änderung
ALTER TABLE users ADD COLUMN new_field TYPE;

-- oder neue Tabelle:
CREATE TABLE new_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- ...
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Migration:** `backend/alembic/versions/YYYY_MM_DD_HHMM-NNN_beschreibung.py`

### Backend (FastAPI)

**Neue/geänderte Endpunkte:**

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/resource` | Employee | Listet alle Einträge |
| `POST` | `/api/resource` | Admin | Erstellt neuen Eintrag |
| `DELETE` | `/api/resource/{id}` | Admin | Löscht Eintrag |

**Betroffene Dateien:**
- `backend/app/models/new_model.py` (neu)
- `backend/app/schemas/new_schema.py` (neu)
- `backend/app/routers/new_router.py` (neu)
- `backend/app/main.py` (Router einbinden)

**Pydantic Schemas:**
```python
class ResourceCreate(BaseModel):
    name: str
    # ...

class ResourceResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
```

### Frontend (React/TypeScript)

**Neue/geänderte Seiten:**
- `frontend/src/pages/NewPage.tsx` (neu)
- `frontend/src/pages/admin/AdminPage.tsx` (geändert)

**Navigation:**
- Admin-Nav: `{ path: '/admin/resource', label: 'Label', icon: IconName }`

**State:**
```typescript
interface Resource {
  id: string;
  name: string;
  // ...
}
```

---

## Tasks

### Voraussetzungen
- [ ] _Abhängigkeit 1 (z.B. anderes Feature muss fertig sein)_

### Backend
- [ ] **T-1**: Migration erstellen: `NNN_beschreibung`
- [ ] **T-2**: SQLAlchemy Model erstellen: `models/new_model.py`
- [ ] **T-3**: Pydantic Schemas erstellen: `schemas/new_schema.py`
- [ ] **T-4**: Router erstellen: `routers/new_router.py`
- [ ] **T-5**: Router in `main.py` registrieren

### Frontend
- [ ] **T-6**: Seite erstellen: `pages/NewPage.tsx`
- [ ] **T-7**: Route in `App.tsx` registrieren
- [ ] **T-8**: Navigation in `Layout.tsx` ergänzen

### Tests & Qualität
- [ ] **T-9**: Manuelle Tests im Browser
- [ ] **T-10**: TypeScript Build prüfen: `npm run build`

### Abschluss
- [ ] **T-11**: Spec aktualisieren (falls Abweichungen)
- [ ] **T-12**: Commit & Push

---

## Offene Fragen

_Ungeklärte Entscheidungen, die vor der Implementierung beantwortet werden müssen:_

1. _Frage 1?_
2. _Frage 2?_

---

## Notizen

_Erkenntnisse, Abweichungen vom Design, Troubleshooting-Hinweise_
