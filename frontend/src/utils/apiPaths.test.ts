import { describe, it, expect } from 'vitest';
import { withCollectionSlash, COLLECTION_ROUTES } from './apiPaths';

// Log-Audit 2026-11-15 (Punkt 17, NET-3): 1149 HTTP-307 an einem Kundenserver,
// weil Basis-Routen (@router.get("/")) ohne Schrägstrich gerufen wurden.
describe('withCollectionSlash', () => {
  it('ergänzt den Schrägstrich an Basis-Routen', () => {
    expect(withCollectionSlash('/time-entries')).toBe('/time-entries/');
    expect(withCollectionSlash('/absences')).toBe('/absences/');
    expect(withCollectionSlash('/dashboard')).toBe('/dashboard/');
    expect(withCollectionSlash('/holidays')).toBe('/holidays/');
    expect(withCollectionSlash('/vacation-requests')).toBe('/vacation-requests/');
    expect(withCollectionSlash('/change-requests')).toBe('/change-requests/');
    expect(withCollectionSlash('/company-closures')).toBe('/company-closures/');
    expect(withCollectionSlash('/admin/reduced-days')).toBe('/admin/reduced-days/');
    expect(withCollectionSlash('/admin/errors')).toBe('/admin/errors/');
  });

  it('behält die Abfrage hinter dem Pfad', () => {
    expect(withCollectionSlash('/absences?year=2026')).toBe('/absences/?year=2026');
    expect(withCollectionSlash('/time-entries?month=2026-11&limit=500')).toBe('/time-entries/?month=2026-11&limit=500');
  });

  it('lässt Unterpfade, vorhandene Schrägstriche und fremde Routen unverändert', () => {
    expect(withCollectionSlash('/time-entries/clock-status')).toBe('/time-entries/clock-status');
    expect(withCollectionSlash('/absences/')).toBe('/absences/');
    expect(withCollectionSlash('/absences/calendar?year=2026')).toBe('/absences/calendar?year=2026');
    // Diese Routen sind mit "" registriert — ein Schrägstrich würde erst umleiten.
    expect(withCollectionSlash('/reduced-days')).toBe('/reduced-days');
    expect(withCollectionSlash('/admin/backups')).toBe('/admin/backups');
    expect(withCollectionSlash('/admin/change-requests/pending-count')).toBe('/admin/change-requests/pending-count');
  });

  it('lässt absolute URLs und leere Werte in Ruhe', () => {
    expect(withCollectionSlash(undefined)).toBeUndefined();
    expect(withCollectionSlash('')).toBe('');
    expect(withCollectionSlash('https://example.invalid/absences')).toBe('https://example.invalid/absences');
  });

  it('kennt nur Pfade ohne Schrägstrich am Ende', () => {
    for (const r of COLLECTION_ROUTES) expect(r.endsWith('/')).toBe(false);
  });
});
