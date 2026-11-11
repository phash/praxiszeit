import { describe, expect, it } from 'vitest';
import { expandDateTokens, workdayBefore } from './dates';

describe('expandDateTokens', () => {
  const st = '2026-10-28'; // Mittwoch

  it('{{stichtag}} -> ISO', () => {
    expect(expandDateTokens('{{stichtag}}', st)).toBe('2026-10-28');
  });

  it('Kalendertage davor und danach, auch über Monatsgrenzen', () => {
    expect(expandDateTokens('{{stichtag-3d}}', st)).toBe('2026-10-25');
    expect(expandDateTokens('{{stichtag+5d}}', st)).toBe('2026-11-02');
    expect(expandDateTokens('{{stichtag-28d}}', st)).toBe('2026-09-30');
  });

  it('{{werktag-N}} überspringt Wochenenden', () => {
    expect(expandDateTokens('{{werktag-1}}', st)).toBe('2026-10-27');
    expect(expandDateTokens('{{werktag-3}}', st)).toBe('2026-10-23'); // Fr
    expect(expandDateTokens('{{werktag-4}}', st)).toBe('2026-10-22'); // Do der Vorwoche
    expect(workdayBefore('2026-11-02', 1)).toBe('2026-10-30'); // Mo -> Fr
  });

  it('{{montag+Nd}} = erster Montag ab Stichtag + N Tagen (Spiegel des Seeds)', () => {
    expect(expandDateTokens('{{montag+35d}}', st)).toBe('2026-12-07'); // 02.12. (Mi) -> Mo
    expect(expandDateTokens('{{montag+35d}}', '2026-10-26')).toBe('2026-11-30'); // 30.11. ist selbst Montag
    expect(expandDateTokens('{{montag+35d}}', '2026-10-25')).toBe('2026-11-30'); // 29.11. (So) -> Mo
  });

  it('lässt Text ohne Platzhalter unverändert und ersetzt mehrere', () => {
    expect(expandDateTokens('08:00', st)).toBe('08:00');
    expect(expandDateTokens('{{stichtag}} bis {{stichtag+1d}}', st)).toBe('2026-10-28 bis 2026-10-29');
  });

  it('unbekannte Platzhalter und kaputte Stichtage brechen ab', () => {
    expect(() => expandDateTokens('{{morgen}}', st)).toThrow(/Unbekannter Platzhalter/);
    expect(() => expandDateTokens('{{werktag-0}}', st)).toThrow();
    expect(() => expandDateTokens('{{stichtag}}', '28.10.2026')).toThrow(/ISO/);
  });
});
