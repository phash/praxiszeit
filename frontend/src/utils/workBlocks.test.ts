import { describe, it, expect } from 'vitest';
import { formatWeekBlocks, isLegacyWeek } from './workBlocks';
import type { WeekBlocks } from '../types/workBlocks';

const EMPTY_NEW = { blocks: [], pause_minutes: 0 };
const EMPTY_LEGACY = { blocks: [], pause_minutes: null };

const NEW_WEEK: WeekBlocks = [
  { blocks: [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }], pause_minutes: 30 },
  { blocks: [{ start: '08:00', end: '13:00' }], pause_minutes: 0 },
  EMPTY_NEW, EMPTY_NEW, EMPTY_NEW,
];

const LEGACY_WEEK: WeekBlocks = [
  { blocks: [{ start: '07:37', end: '16:30' }], pause_minutes: null },
  EMPTY_LEGACY, EMPTY_LEGACY, EMPTY_LEGACY,
  { blocks: [{ start: '07:30', end: '23:59' }], pause_minutes: null },
];

describe('formatWeekBlocks (Spec 12.2)', () => {
  it('nennt nur Tage mit Blöcken, Pause nur wenn > 0', () => {
    expect(formatWeekBlocks(NEW_WEEK)).toBe('Mo 08:00–12:00 + 15:00–18:00 (Pause 30 Min) · Di 08:00–13:00');
  });

  it('zeigt Altwerte und Platzhalter unverändert', () => {
    expect(formatWeekBlocks(LEGACY_WEEK)).toBe('Mo 07:37–16:30 · Fr 07:30–23:59');
  });

  it('liefert null ohne Blöcke', () => {
    expect(formatWeekBlocks(null)).toBeNull();
    expect(formatWeekBlocks(undefined)).toBeNull();
    expect(formatWeekBlocks([EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW, EMPTY_NEW])).toBeNull();
  });
});

describe('isLegacyWeek (Spec 3.3)', () => {
  it('erkennt Altzeilen an pause_minutes null', () => {
    expect(isLegacyWeek(LEGACY_WEEK)).toBe(true);
    expect(isLegacyWeek(NEW_WEEK)).toBe(false);
    expect(isLegacyWeek(null)).toBe(false);
  });
});
