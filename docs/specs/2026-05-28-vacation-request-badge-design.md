# Spec: Urlaubsanträge mit roter Badge im Admin-Dashboard

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #140

---

## Überblick

Offene Urlaubsanträge werden in der Admin-Navigation nicht mit einer roten Zähler-Badge signalisiert, offene Änderungsanträge dagegen schon. Dieses Feature stellt Parität her: das Nav-Item „Anträge" erhält dieselbe Live-Badge wie „Änderungsanträge". Grundlage: User-Feedback `feedback/feedback_01.txt`, Punkt 1.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich **offene Urlaubsanträge im Dashboard mit einer roten Ziffer sehen**, damit ich **unbearbeitete Anträge sofort erkenne — genau wie bei Änderungsanträgen**.

- [ ] **REQ-1**: Das Nav-Item „Anträge" (`/admin/vacation-approvals`) zeigt eine rote Badge mit der Anzahl offener (`pending`) Urlaubsanträge, sobald diese > 0 ist.
- [ ] **REQ-2**: Der Zähler aktualisiert sich automatisch im 60-Sekunden-Intervall (identisch zum Änderungsantrags-Polling).
- [ ] **REQ-3**: Der Zähler ist tenant-bezogen (nur Anträge des eigenen Mandanten).

### Nicht-funktionale Anforderungen

- [ ] Sicherheit: Endpunkt nur für Admins; expliziter `tenant_id`-Filter (F-026) zusätzlich zu RLS.
- [ ] Performance: reine `COUNT`-Query, kein Laden der Antragsliste.
- [ ] Konsistenz: Implementierung spiegelt 1:1 das Änderungsantrags-Pattern.

### Out of Scope

- Kein gemeinsamer Sammel-Badge über mehrere Antragstypen.
- Keine Echtzeit-Push-Updates (Polling bleibt).

---

## Design

### Backend (FastAPI)

**Neuer Endpunkt** — analog zu `admin_change_requests.py:30`:

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/admin/vacation-requests/pending-count` | Admin | `{ "count": <int> }` offener Urlaubsanträge |

**Betroffene Datei:**
- `backend/app/routers/admin_vacations.py` (Endpunkt ergänzen)

**Skizze:**
```python
@router.get("/vacation-requests/pending-count")
def pending_count(db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    count = db.query(VacationRequest).filter(
        VacationRequest.tenant_id == current_user.tenant_id,   # F-026
        VacationRequest.status == VacationRequestStatus.PENDING,
    ).count()
    return {"count": count}
```

### Frontend (React/TypeScript)

**Betroffene Datei:** `frontend/src/components/Layout.tsx`

- State analog `pendingCRCount` (Z. 48): `const [pendingVRCount, setPendingVRCount] = useState(0)`
- `useEffect` analog Z. 52-64, das `/admin/vacation-requests/pending-count` alle 60 s pollt (nur `role === 'admin'`).
- Nav-Item Z. 170: `badge: pendingVRCount` statt `badge: 0`.
- Badge-Rendering existiert bereits (zeigt bei `badge > 0`).

---

## Tasks

### Backend
- [ ] **T-1**: `GET /vacation-requests/pending-count` in `admin_vacations.py` ergänzen (tenant-scoped).

### Frontend
- [ ] **T-2**: State `pendingVRCount` + Polling-`useEffect` in `Layout.tsx`.
- [ ] **T-3**: Nav-Item „Anträge" (Z. 170) auf `badge: pendingVRCount` umstellen.

### Tests & Qualität
- [ ] **T-4**: Backend-Test: Count nur `pending`, korrekt tenant-isoliert (vgl. `test_cross_tenant_api.py`).
- [ ] **T-5**: Manueller Test im Browser: Antrag stellen → Badge erscheint; genehmigen → Badge verschwindet.
- [ ] **T-6**: `npm run build` (tsc) grün.

### Abschluss
- [ ] **T-7**: Spec-Status auf „Done", Commit & Push.

---

## Offene Fragen

_Keine — klares Bug-/Paritäts-Feature._

---

## Notizen

- Referenz-Implementierung (Vorlage): `admin_change_requests.py:30` + `Layout.tsx:48,52-64,165`.
