# Spec: Benachrichtigungen & Warnungen

**Status:** Done
**Erstellt:** 2026-02-17
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #15

---

## Überblick

Benutzer erhalten Feedback über eine Toast-Notification-System (Erfolg, Fehler, Info, Warnung). Admins und Mitarbeiter werden über wichtige Zustände (offene Urlaubstage) informiert. Native `alert()`/`confirm()` Dialoge sind ersetzt durch styled Komponenten.

---

## Requirements

- [x] **REQ-1**: Toast-Benachrichtigungen (success, error, info, warning) für alle Aktionen
- [x] **REQ-2**: Bestätigungsdialoge statt nativer `confirm()` – styled, mit Varianten (danger, warning, info)
- [x] **REQ-3**: MA-Dashboard: Warnung wenn Resturlaub > 0 und Monat ≥ Oktober
- [x] **REQ-4**: Admin-Dashboard: Q4-Banner mit Liste der MAs mit offenem Urlaub

### Out of Scope

- E-Mail-Benachrichtigungen
- Push Notifications (PWA)
- Benachrichtigungen bei Urlaubsantrag

---

## Design

### Frontend-Komponenten

**Toast System:**
```typescript
// contexts/ToastContext.tsx
const toast = useToast()
toast.success('Eintrag gespeichert')
toast.error('Fehler beim Laden')
toast.info('Hinweis')
toast.warning('Warnung')
```

**Confirm Dialog:**
```typescript
// hooks/useConfirm.ts
const { confirm, ConfirmDialogComponent } = useConfirm()
const ok = await confirm({
  title: 'Löschen?',
  message: 'Wirklich löschen?',
  variant: 'danger'  // 'danger' | 'warning' | 'info'
})
if (ok) { /* ... */ }
```

**Betroffene Dateien:**
- `frontend/src/contexts/ToastContext.tsx`
- `frontend/src/components/ConfirmDialog.tsx`
- `frontend/src/hooks/useConfirm.ts`

---

## Tasks

- [x] **T-1**: ToastContext mit Provider
- [x] **T-2**: ConfirmDialog Komponente (styled, Varianten)
- [x] **T-3**: useConfirm Hook
- [x] **T-4**: ToastProvider in App.tsx eingebunden
- [x] **T-5**: Alle Pages auf useToast / useConfirm migriert
