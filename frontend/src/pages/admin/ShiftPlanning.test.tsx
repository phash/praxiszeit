import { describe, it, expect } from 'vitest';
import { buildMovedSlotPayload } from './ShiftPlanning';
import type { ShiftSlot } from '../../api/shiftPlanning';

/**
 * #443 F-1 (Prüfrunde 2, CRITICAL): Regressionsschutz für den in Commit
 * `12171aa9` behobenen Datenverlust — Verschieben eines Slots per Drag & Drop
 * setzte `note` (und jedes andere im handgeschriebenen Payload nicht erwähnte
 * Feld) stillschweigend auf NULL, weil `PUT /slots/{id}` serverseitig ein
 * Vollersatz ist.
 *
 * Zuschnitt: `AdminShiftPlanning` selbst hängt an dnd-kit (echtes Drag lässt
 * sich in jsdom nicht sauber simulieren), Toast-Context, dem System-Store und
 * mehreren API-Aufrufen — ein Komponententest, der das nachstellt, würde vor
 * allem die Mocks testen. Der eigentliche Fehler steckt ausschließlich in der
 * Payload-Konstruktion, deshalb ist sie als reine Funktion `buildMovedSlotPayload`
 * aus `onDragEnd` herausgezogen (in ShiftPlanning.tsx neben dem Default-Export)
 * und wird hier ohne jeden Mock direkt geprüft. Das macht genau die Regel
 * prüfbar, die kaputtging, statt eine schwer testbare Komponente zu umzingeln.
 */

const baseSlot = (over: Partial<ShiftSlot> = {}): ShiftSlot => ({
  id: 'slot-1',
  workstation_id: 'ws-1',
  workstation_name: 'Empfang',
  color: '#2563eb',
  weekday: 0,
  start_time: '08:00',
  end_time: '12:00',
  min_staff: 1,
  note: 'Vertretung für Frau Schmidt',
  understaffed: false,
  unqualified: false,
  assignments: [{ id: 'a1', user_id: 'u1', user_name: 'Max Muster' }],
  ...over,
});

describe('buildMovedSlotPayload (admin/ShiftPlanning.tsx onDragEnd — #443 F-1)', () => {
  it('behält den Hinweis (note), wenn ein Slot per Drag verschoben wird', () => {
    const slot = baseSlot({ note: 'Einarbeitung Azubi' });
    const payload = buildMovedSlotPayload(slot, 2, 9 * 60, 13 * 60);
    expect(payload.note).toBe('Einarbeitung Azubi');
  });

  it('übernimmt Ziel-Wochentag sowie neue Start-/Endzeit', () => {
    const slot = baseSlot({ weekday: 0, start_time: '08:00', end_time: '12:00' });
    const payload = buildMovedSlotPayload(slot, 3, 9 * 60, 13 * 60);
    expect(payload.weekday).toBe(3);
    expect(payload.start_time).toBe('09:00');
    expect(payload.end_time).toBe('13:00');
  });

  it('übernimmt Arbeitsplatz und Mindestbesetzung unverändert', () => {
    const slot = baseSlot({ workstation_id: 'ws-42', min_staff: 3 });
    const payload = buildMovedSlotPayload(slot, 1, 8 * 60, 12 * 60);
    expect(payload.workstation_id).toBe('ws-42');
    expect(payload.min_staff).toBe(3);
  });

  it('entfernt die reinen Anzeige-Extrafelder von ShiftSlot aus der Nutzlast', () => {
    const slot = baseSlot();
    const payload = buildMovedSlotPayload(slot, 1, 8 * 60, 12 * 60) as Record<string, unknown>;
    expect(payload).not.toHaveProperty('id');
    expect(payload).not.toHaveProperty('workstation_name');
    expect(payload).not.toHaveProperty('color');
    expect(payload).not.toHaveProperty('understaffed');
    expect(payload).not.toHaveProperty('unqualified');
    expect(payload).not.toHaveProperty('assignments');
  });

  it('lässt einen fehlenden Hinweis (null) unverändert null', () => {
    const slot = baseSlot({ note: null });
    const payload = buildMovedSlotPayload(slot, 0, 8 * 60, 12 * 60);
    expect(payload.note).toBeNull();
  });
});
