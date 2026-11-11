import { describe, expect, it } from 'vitest';
import { toMarkdown } from './toMarkdown';
import type { Handbook, Manifest } from '../types';

const manifest: Manifest = {
  'shot-a': {
    file: 'shot-a.webp', width: 1440, height: 900, pxWidth: 2880, pxHeight: 1800,
    crop: { x: 0, y: 0, w: 1440, h: 900 }, markers: {},
  },
};

const hb: Handbook = {
  id: 'mitarbeitende',
  title: 'Handbuch für Mitarbeitende',
  lead: 'Kurz und **klar**.',
  shots: [],
  chapters: [
    {
      id: 'stempeln', title: 'Stempeln',
      blocks: [
        { kind: 'task', id: 'einstempeln', title: 'Einstempeln', intro: 'Beginn des Tages.', shot: 'shot-a',
          steps: [{ text: 'Öffnen Sie [[Zeiterfassung]].' }, { text: 'Klicken Sie auf **Einstempeln**.' }] },
        { kind: 'tip', tone: 'info', text: 'Siehe [Berechnung](handbuch:so-rechnet#saldo).' },
        { kind: 'tip', tone: 'warn', text: 'Vorsicht.' },
      ],
    },
  ],
};

describe('toMarkdown', () => {
  it('task renders as heading, numbered steps and image with alt', () => {
    const md = toMarkdown(hb, manifest, 'docs', '1.23.0');
    expect(md).toContain('<a id="einstempeln"></a>');
    expect(md).toContain('### Einstempeln');
    expect(md).toContain('1. Öffnen Sie `Zeiterfassung`.');
    expect(md).toContain('2. Klicken Sie auf **Einstempeln**.');
    expect(md).toContain('![Einstempeln](img/shot-a.webp)');
  });

  it('download target uses /help/img paths', () => {
    const md = toMarkdown(hb, manifest, 'download', '1.23.0');
    expect(md).toContain('](/help/img/shot-a.webp)');
    expect(md).not.toContain('](img/shot-a.webp)');
  });

  it('cross-handbook link maps to md file', () => {
    const md = toMarkdown(hb, manifest, 'docs', '1.23.0');
    expect(md).toContain('[Berechnung](SO-RECHNET-PRAXISZEIT.md#saldo)');
    expect(md).toContain('> **Gut zu wissen:**');
    expect(md).toContain('> **Achtung:**');
  });

  it('escapes table cells and plain-text block triggers', () => {
    const h2: Handbook = { ...hb, lead: '# Nicht Titel', chapters: [{ id: 'c', title: 'C', blocks: [
      { kind: 'table', head: ['A|B', 'C'], rows: [['x [[p|q]]', '<b>']] },
      { kind: 'prose', text: '1. kein Listenpunkt' },
    ] }] };
    const md = toMarkdown(h2, manifest, 'docs', '1.0.0');
    expect(md).toContain('\\# Nicht Titel');
    expect(md).toContain('| A\\|B | C |');
    expect(md).toContain('| x `p\\|q` | \\<b\\> |');
    expect(md).toContain('1\\. kein Listenpunkt');
  });

  it('header contains generated marker and version line', () => {
    const md = toMarkdown(hb, manifest, 'docs', '1.23.0');
    expect(md.split('\n')[0]).toBe('<!-- Erzeugt aus frontend/src/handbuch — nicht von Hand bearbeiten -->');
    expect(md).toMatch(/\*\*Stand:\*\* PraxisZeit 1\.23\.0/);
    expect(md).toContain('# Handbuch für Mitarbeitende');
  });
});
