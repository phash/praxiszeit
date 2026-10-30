import { describe, expect, it } from 'vitest';
import {
  axisRange, compactSpan, coverage, departmentsOf, moveBlock, resizeBlock, sameWeek, snapMinutes,
} from './teamSchedule';
import type { WeekBlocks } from '../types/workBlocks';

const week = (mon: [string, string][], tue: [string, string][] = []): WeekBlocks => [
  { blocks: mon.map(([start, end]) => ({ start, end })), pause_minutes: 0 },
  { blocks: tue.map(([start, end]) => ({ start, end })), pause_minutes: 0 },
  { blocks: [], pause_minutes: 0 },
  { blocks: [], pause_minutes: 0 },
  { blocks: [], pause_minutes: 0 },
];

describe('snapMinutes', () => {
  it('rundet auf das 15-Minuten-Raster', () => {
    expect(snapMinutes(7)).toBe(0);
    expect(snapMinutes(8)).toBe(15);
    expect(snapMinutes(-8)).toBe(-15);
    expect(snapMinutes(37, 5)).toBe(35);
  });
});

describe('moveBlock', () => {
  it('verschiebt einen Block samt Dauer, andere Tage und Blöcke bleiben', () => {
    const w = week([['07:30', '13:00'], ['15:00', '18:00']], [['08:00', '12:00']]);
    const out = moveBlock(w, 0, 1, 60);
    expect(out[0].blocks).toEqual([{ start: '07:30', end: '13:00' }, { start: '16:00', end: '19:00' }]);
    expect(out[1]).toEqual(w[1]);
    expect(w[0].blocks[1]).toEqual({ start: '15:00', end: '18:00' }); // unverändert (keine Mutation)
  });
  it('bleibt im Tag: nicht vor 00:00, nicht nach 23:55', () => {
    expect(moveBlock(week([['01:00', '03:00']]), 0, 0, -180)[0].blocks[0]).toEqual({ start: '00:00', end: '02:00' });
    expect(moveBlock(week([['20:00', '22:00']]), 0, 0, 240)[0].blocks[0]).toEqual({ start: '21:55', end: '23:55' });
  });
});

describe('Nachbarblöcke', () => {
  const w = week([['08:00', '12:00'], ['15:00', '18:00']]);
  it('Verschieben stoppt 5 Minuten vor dem Nachbarn', () => {
    expect(moveBlock(w, 0, 0, 240)[0].blocks[0]).toEqual({ start: '10:55', end: '14:55' });
    expect(moveBlock(w, 0, 1, -240)[0].blocks[1]).toEqual({ start: '12:05', end: '15:05' });
  });
  it('Ziehen eines Randes stoppt ebenso', () => {
    expect(resizeBlock(w, 0, 0, 'end', 300)[0].blocks[0]).toEqual({ start: '08:00', end: '14:55' });
    expect(resizeBlock(w, 0, 1, 'start', -300)[0].blocks[1]).toEqual({ start: '12:05', end: '18:00' });
  });
});

describe('compactSpan', () => {
  it('kürzt volle Stunden und führende Nullen', () => {
    expect(compactSpan('08:00', '12:00')).toBe('8–12');
    expect(compactSpan('07:30', '13:00')).toBe('7:30–13');
    expect(compactSpan('14:30', '18:45')).toBe('14:30–18:45');
  });
});

describe('resizeBlock', () => {
  it('zieht Beginn oder Ende, mindestens 15 Minuten Dauer', () => {
    const w = week([['08:00', '12:00']]);
    expect(resizeBlock(w, 0, 0, 'end', 90)[0].blocks[0]).toEqual({ start: '08:00', end: '13:30' });
    expect(resizeBlock(w, 0, 0, 'start', -30)[0].blocks[0]).toEqual({ start: '07:30', end: '12:00' });
    expect(resizeBlock(w, 0, 0, 'start', 600)[0].blocks[0]).toEqual({ start: '11:45', end: '12:00' });
    expect(resizeBlock(w, 0, 0, 'end', 900)[0].blocks[0]).toEqual({ start: '08:00', end: '23:55' });
  });
});

describe('axisRange', () => {
  it('volle Stunden um alle Blöcke, mindestens 07–19 Uhr', () => {
    expect(axisRange([week([['07:30', '13:00']]), null])).toEqual({ start: 7 * 60, end: 19 * 60 });
    expect(axisRange([week([['06:10', '20:20']])])).toEqual({ start: 6 * 60, end: 21 * 60 });
    expect(axisRange([])).toEqual({ start: 7 * 60, end: 19 * 60 });
  });
});

describe('coverage', () => {
  it('zählt je Zeitfenster die Personen mit einem Block darin', () => {
    const a = week([['08:00', '12:00']]);
    const b = week([['10:00', '11:00'], ['11:30', '12:30']]);
    // 08–13 in Stunden: 08 → a; 09 → a; 10 → a+b; 11 → a+b (b ab 11:30); 12 → b
    expect(coverage([a, b, null], 0, 8 * 60, 13 * 60, 60)).toEqual([1, 1, 2, 2, 1]);
    expect(coverage([a, b], 2, 8 * 60, 10 * 60, 60)).toEqual([0, 0]);
  });
});

describe('departmentsOf', () => {
  it('sortiert, ohne Leerwerte und Dubletten', () => {
    expect(departmentsOf([{ department: 'MFA' }, { department: 'Ärzte' }, { department: null },
      { department: ' ' }, { department: 'MFA' }])).toEqual(['Ärzte', 'MFA']);
  });
});

describe('sameWeek', () => {
  it('vergleicht Blöcke und Pausen', () => {
    const w = week([['08:00', '12:00']]);
    expect(sameWeek(w, week([['08:00', '12:00']]))).toBe(true);
    expect(sameWeek(w, moveBlock(w, 0, 0, 15))).toBe(false);
    expect(sameWeek(null, null)).toBe(true);
  });
});
