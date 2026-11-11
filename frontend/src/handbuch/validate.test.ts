import { describe, it, expect } from 'vitest';
import { validateHandbook } from './validate';
import type { Handbook, Manifest } from './types';

const ALT = 'Die Zeiterfassung mit dem Dialog zum Nachtragen eines Zeiteintrags in der Praxis.';

function fixture(): { h: Handbook; m: Manifest } {
  const h: Handbook = {
    id: 'mitarbeitende',
    title: 'Handbuch',
    lead: 'Einleitung mit [Link](#zeit).',
    chapters: [
      {
        id: 'zeit',
        title: 'Zeit',
        blocks: [
          {
            kind: 'task',
            id: 'zeiterfassung-nachtragen',
            title: 'Nachtragen',
            shot: 'nachtragen',
            steps: [
              { n: 1, text: 'Öffnen Sie [[Zeiterfassung]].' },
              { n: 2, text: 'Klicken Sie **Speichern**.' },
              { text: 'Fertig.' },
            ],
          },
        ],
      },
    ],
    shots: [
      {
        id: 'nachtragen', persona: 'maria', viewport: 'desktop', route: '/time-tracking',
        markers: [
          { n: 1, id: 'm1', locator: { text: 'Zeiterfassung' } },
          { n: 2, id: 'm2', locator: { text: 'Speichern' } },
        ],
        alt: ALT,
      },
    ],
  };
  const box = { x: 0, y: 0, w: 10, h: 10 };
  const m: Manifest = {
    nachtragen: {
      file: 'nachtragen.webp', width: 1440, height: 900, pxWidth: 2880, pxHeight: 1800,
      crop: box, markers: { m1: box, m2: box },
    },
  };
  return { h, m };
}

describe('validateHandbook', () => {
  it('accepts valid fixture', () => {
    const { h, m } = fixture();
    expect(validateHandbook(h, m)).toEqual([]);
  });

  it('rejects step number without marker', () => {
    const { h, m } = fixture();
    const task = h.chapters[0].blocks[0] as Extract<typeof h.chapters[0]['blocks'][0], { kind: 'task' }>;
    task.steps.push({ n: 3, text: 'Drittens.' });
    expect(validateHandbook(h, m)).toContain('task zeiterfassung-nachtragen: Schritt 3 ohne Markierung');
  });

  it('rejects marker without step', () => {
    const { h, m } = fixture();
    h.shots[0].markers.push({ n: 3, id: 'm3', locator: { text: 'X' } });
    m.nachtragen.markers.m3 = { x: 0, y: 0, w: 1, h: 1 };
    expect(validateHandbook(h, m)).toContain('task zeiterfassung-nachtragen: Markierung 3 ohne Schritt');
  });

  it('rejects shot missing in manifest', () => {
    const { h, m } = fixture();
    delete m.nachtragen;
    expect(validateHandbook(h, m)).toContain('shot nachtragen: fehlt im Manifest');
  });

  it('rejects marker missing in manifest', () => {
    const { h, m } = fixture();
    delete m.nachtragen.markers.m2;
    expect(validateHandbook(h, m)).toContain('shot nachtragen: Markierung 2 (m2) fehlt im Manifest');
  });

  it('rejects duplicate task/chapter ids across handbook', () => {
    const { h, m } = fixture();
    h.chapters.push({ id: 'zeit', title: 'Nochmal', blocks: [] });
    h.chapters.push({ id: 'x', title: 'X', blocks: [{ kind: 'task', id: 'zeiterfassung-nachtragen', title: 'T', steps: [] }] });
    const errs = validateHandbook(h, m);
    expect(errs).toContain('chapter zeit: doppelte ID');
    expect(errs).toContain('task zeiterfassung-nachtragen: doppelte ID');
  });

  it('rejects alt shorter than 40 chars', () => {
    const { h, m } = fixture();
    h.shots[0].alt = 'Zu kurz';
    expect(validateHandbook(h, m)).toContain('shot nachtragen: Alt-Text kürzer als 40 Zeichen');
  });

  it('rejects unknown handbuch: link target', () => {
    const { h, m } = fixture();
    h.chapters[0].blocks.push({ kind: 'prose', text: 'Siehe [dort](handbuch:gibtsnicht#a).' });
    const errs = validateHandbook(h, m);
    expect(errs.some((e) => e.includes('unbekanntes Handbuch "gibtsnicht"'))).toBe(true);
  });

  it.each(['javascript:alert1', 'data:text/html,x', '//evil.com'])('rejects invalid link target %s', (t) => {
    const { h, m } = fixture();
    h.chapters[0].blocks.push({ kind: 'prose', text: `Siehe [dort](${t}).` });
    expect(validateHandbook(h, m).some((e) => e.includes(`ungültiges Link-Ziel "${t}"`))).toBe(true);
  });

  it('accepts known handbuch: link target', () => {
    const { h, m } = fixture();
    h.chapters[0].blocks.push({ kind: 'prose', text: 'Siehe [dort](handbuch:so-rechnet#a).' });
    expect(validateHandbook(h, m)).toEqual([]);
  });
});
