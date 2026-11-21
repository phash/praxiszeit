import { describe, it, expect } from 'vitest';
import { handbookHints, type HintId } from './handbookHints';
import { anchorExists } from '../handbuch/validate';
import { FORBIDDEN_TERMS } from '../handbuch/content/forbiddenTerms';

/** Sätze zählen: Satzende = . ! ? vor Leerraum und Großbuchstabe/Anführung oder am Textende. */
function sentenceCount(text: string): number {
  return (text.trim().match(/[.!?](?=\s+[A-ZÄÖÜ„"]|\s*$)/g) ?? []).length;
}

describe('handbookHints register', () => {
  const entries = Object.entries(handbookHints) as [HintId, (typeof handbookHints)[HintId]][];

  it('has at least one entry', () => {
    expect(entries.length).toBeGreaterThan(0);
  });

  it('every hint points to an existing chapter or task anchor', () => {
    for (const [id, hint] of entries) {
      expect(anchorExists(hint.book, hint.anchor), `${id}: ${hint.book}#${hint.anchor}`).toBe(true);
    }
  });

  it('every hint text has 1 to 3 sentences and a title', () => {
    for (const [id, hint] of entries) {
      expect(hint.title.trim().length, `${id}: Titel`).toBeGreaterThan(0);
      const n = sentenceCount(hint.text);
      expect(n, `${id}: ${n} Sätze`).toBeGreaterThanOrEqual(1);
      expect(n, `${id}: ${n} Sätze`).toBeLessThanOrEqual(3);
    }
  });

  it('no hint uses a forbidden term', () => {
    for (const [id, hint] of entries) {
      for (const term of FORBIDDEN_TERMS) {
        expect(`${hint.title} ${hint.text}`.includes(term), `${id}: „${term}“`).toBe(false);
      }
    }
  });

  // Task 13 schaltet diesen Test scharf, sobald die Kurzhilfen an den Seiten sitzen:
  // jeder Schlüssel kommt in src/**/*.tsx als hintId="<schlüssel>" vor
  // (import.meta.glob('/src/**/*.tsx', { query: '?raw', import: 'default', eager: true })).
  it.todo('every hint id is used as hintId="<id>" in a .tsx source');
});

describe('sentenceCount helper', () => {
  it('counts sentence ends', () => {
    expect(sentenceCount('Eins. Zwei! Drei?')).toBe(3);
    expect(sentenceCount('Nur ein Satz.')).toBe(1);
  });
});
