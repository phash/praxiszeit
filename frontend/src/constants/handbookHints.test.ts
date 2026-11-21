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

  it('every hint id is used as hintId="<id>" in a .tsx source', () => {
    // Quelltext aller Komponenten und Seiten, ohne Tests (dort steht nur der Testschlüssel).
    const sources = import.meta.glob('/src/**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    const code = Object.entries(sources)
      .filter(([path]) => !/\.test\.tsx$/.test(path))
      .map(([, src]) => src)
      .join('\n');
    const unused = entries.map(([id]) => id).filter((id) => !code.includes(`hintId="${id}"`));
    expect(unused, 'Registereinträge ohne Einsatzstelle').toEqual([]);
  });

  it('every hintId="…" in a .tsx source is a register key', () => {
    const sources = import.meta.glob('/src/**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    const used = new Set<string>();
    for (const [path, src] of Object.entries(sources)) {
      if (/\.test\.tsx$/.test(path)) continue;
      for (const m of src.matchAll(/hintId="([^"]+)"/g)) used.add(m[1]);
    }
    const unknown = [...used].filter((id) => !(id in handbookHints));
    expect(unknown).toEqual([]);
  });

  it('employee-facing hints link the employee handbook or the calculation guide', () => {
    // Mitarbeiterseiten (Dashboard, Zeiterfassung, Anträge) verlinken nie das Handbuch der Praxisleitung,
    // das Mitarbeitende unter /help nicht öffnen können.
    const employee: HintId[] = [
      'stamp-card', 'dashboard-month-balance', 'dashboard-overtime', 'dashboard-vacation',
      'not-credited', 'cr-create', 'cr-update', 'cr-delete', 'journal-balance',
    ];
    for (const id of employee) {
      expect(['mitarbeitende', 'so-rechnet'], id).toContain(handbookHints[id].book);
    }
  });
});

describe('sentenceCount helper', () => {
  it('counts sentence ends', () => {
    expect(sentenceCount('Eins. Zwei! Drei?')).toBe(3);
    expect(sentenceCount('Nur ein Satz.')).toBe(1);
  });
});
