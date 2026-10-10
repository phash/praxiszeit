import { describe, it, expect } from 'vitest';
import {
  blocksSpan, formatWeekBlocks, gapSegments, hhmmToMinutes, isInBlockGap, isLegacyWeek,
  notCreditedMinutes, stampNoteProps,
} from './workBlocks';
import { K_CASES_FE } from './workBlocksCases';
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

describe('notCreditedMinutes — Zwilling von not_credited_minutes (Spec 6.3, P19)', () => {
  it.each(K_CASES_FE.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    expect(notCreditedMinutes(k.stored)).toBe(k.notCredited);
  });
});

describe('gapSegments — Zwilling von gap_segments (Σ = uncredited_minutes)', () => {
  const closed = K_CASES_FE.filter((k) => k.end !== null && !k.creditOverride);
  it.each(closed.map((k) => [k.id, k] as const))('%s', (_id, k) => {
    const sum = gapSegments(k.dayBlocks, 15, k.start, k.end!).reduce((a, b) => a + b, 0);
    expect(sum).toBe(k.stored.uncredited_minutes);
  });

  it('liefert die Segmente je Lücke (K17)', () => {
    const k17 = K_CASES_FE.find((k) => k.id === 'K17')!;
    expect(gapSegments(k17.dayBlocks, 15, '07:00', '19:00')).toEqual([30, 150]);
  });

  it('eine Lücke ≤ 2 × Puffer verschwindet (K6)', () => {
    const k6 = K_CASES_FE.find((k) => k.id === 'K6')!;
    expect(gapSegments(k6.dayBlocks, 15, '08:00', '16:00')).toEqual([]);
  });

  it('akzeptiert Zeiten mit Sekunden aus der API', () => {
    const k1 = K_CASES_FE.find((k) => k.id === 'K1')!;
    expect(gapSegments(k1.dayBlocks, 15, '08:00:00', '18:00:00')).toEqual([150]);
  });

  // E80: der Puffer ist die variable Eingabe (gespeicherter Puffer des offenen
  // Eintrags bzw. Mandanten-Puffer, clamp_grace_minutes je Eintrag) — Werte wie
  // work_window_service.credit_gaps (test_clamp_grace.py: Puffer 0/10/120).
  it('rechnet mit dem übergebenen Puffer (E80), nicht mit festen 15', () => {
    const B = K_CASES_FE.find((k) => k.id === 'K1')!.dayBlocks;
    expect(gapSegments(B, 0, '08:00', '18:00')).toEqual([180]);
    expect(gapSegments(B, 30, '08:00', '18:00')).toEqual([120]);
    expect(gapSegments(B, 90, '08:00', '18:00')).toEqual([]); // Lücke 180 ≤ 2 × 90
  });
});

describe('isInBlockGap — ungeschrumpfte Lücke (Spec 14, E69)', () => {
  const B = [{ start: '08:00', end: '12:00' }, { start: '15:00', end: '18:00' }];
  it.each([
    ['07:30', false], ['11:59', false], ['12:00', true], ['12:05', true],
    ['13:00', true], ['14:59', true], ['15:00', false], ['18:30', false],
  ] as const)('%s → %s', (t, expected) => {
    expect(isInBlockGap(B, hhmmToMinutes(t))).toBe(expected);
  });

  it('ohne zweiten Block gibt es keine Lücke', () => {
    expect(isInBlockGap([{ start: '08:00', end: '16:00' }], hhmmToMinutes('12:00'))).toBe(false);
    expect(isInBlockGap(undefined, 600)).toBe(false);
  });
});

describe('blocksSpan', () => {
  it('erster Beginn bis letztes Ende', () => {
    expect(blocksSpan([{ start: '15:00', end: '18:00' }, { start: '08:00', end: '12:00' }]))
      .toEqual({ start: '08:00', end: '18:00' });
    expect(blocksSpan([])).toBeNull();
  });
});

describe('stampNoteProps', () => {
  it('baut Roh- und angerechnete Spanne (K7) und nimmt den Serverwert, wenn vorhanden', () => {
    const k7 = K_CASES_FE.find((k) => k.id === 'K7')!;
    const props = stampNoteProps(k7.stored);
    expect(props).toMatchObject({
      rawSpan: '07:00–19:00', effSpan: '07:45–18:15', uncreditedMinutes: 150,
      notCreditedMinutes: 240, creditedHours: 8, breakMinutes: 0, autoClosed: false, creditOverride: false,
    });
    expect(stampNoteProps({ ...k7.stored, not_credited_minutes: 241 }).notCreditedMinutes).toBe(241);
  });
});
