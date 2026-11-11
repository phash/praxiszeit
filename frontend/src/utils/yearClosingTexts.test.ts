import { describe, it, expect } from 'vitest';
import { yearClosingMessage } from './yearClosingTexts';

describe('yearClosingMessage', () => {
  it('abgeschlossenes Jahr ohne manuelle Übernahmen: wie bisher, keine Warnung', () => {
    const m = yearClosingMessage(2025, false, 0);
    expect(m).toContain('als Übernahme in 2026 gespeichert');
    expect(m).not.toContain('noch nicht zu Ende');
    expect(m).not.toContain('von Hand');
  });
  it('laufendes Jahr warnt vor dem Soll ohne Ist', () => {
    expect(yearClosingMessage(2026, true, 0)).toContain('2026 ist noch nicht zu Ende');
  });
  it('nennt die Zahl der von Hand eingetragenen Übernahmen', () => {
    expect(yearClosingMessage(2025, false, 1)).toContain('1 Übernahme von Hand');
    expect(yearClosingMessage(2025, false, 3)).toContain('3 Übernahmen von Hand');
  });
});
