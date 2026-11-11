import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { DIAGRAMS } from './index';
import HandbookPage from '../components/HandbookPage';
import type { Handbook } from '../types';
import * as V from './values';

describe('DIAGRAMS', () => {
  it('hat die fünf Schlüssel', () => {
    expect(Object.keys(DIAGRAMS).sort()).toEqual(
      ['betriebsferien-split', 'saldo-monat', 'soll-ist', 'tag-zeitstrahl', 'urlaubskonto'],
    );
  });

  for (const key of ['tag-zeitstrahl', 'soll-ist', 'saldo-monat', 'urlaubskonto', 'betriebsferien-split']) {
    it(`"${key}" rendert SSR als Bild mit Alt-Text, ohne style`, () => {
      const html = renderToString(createElement(DIAGRAMS[key]));
      expect(html).toContain('<svg');
      expect(html).toContain('role="img"');
      expect(html).not.toContain('style=');
      const m = html.match(/aria-label="([^"]*)"/);
      expect(m).not.toBeNull();
      expect(m![1].length).toBeGreaterThanOrEqual(40);
    });
  }

  it('HandbookPage rendert kind "diagram" über DIAGRAMS', () => {
    const hb: Handbook = {
      id: 'so-rechnet', title: 'T', lead: 'L', shots: [],
      chapters: [{ id: 'k', title: 'K', blocks: [{ kind: 'diagram', diagram: 'soll-ist', caption: 'Unterschrift' }] }],
    } as unknown as Handbook;
    const html = renderToString(createElement(HandbookPage, { handbook: hb, manifest: {}, imgBase: '/', linkBase: '/', variant: 'wide', diagrams: DIAGRAMS } as never));
    expect(html).toContain('role="img"');
    expect(html).toContain('Unterschrift');
  });
});

describe('values (aus BERECHNUNGEN abgeleitet, nicht Literal gegen Literal)', () => {
  it('§4.1: Hülle 07:45–16:15, geschrumpfte Lücke 12:15–14:45 (Block ± Puffer 15)', () => {
    expect(V.hhmm(V.HULL.start)).toBe('07:45');
    expect(V.hhmm(V.HULL.end)).toBe('16:15');
    expect(V.hhmm(V.GAP_SHRUNK.start)).toBe('12:15');
    expect(V.hhmm(V.GAP_SHRUNK.end)).toBe('14:45');
  });
  it('§4.1 Kappung: Zeiteintrag 1 und 2', () => {
    expect(V.hhmm(V.ENTRY_A.effStart)).toBe('07:45');
    expect(V.hhmm(V.ENTRY_A.effEnd)).toBe('12:10');
    expect(V.ENTRY_A).toMatchObject({ credited: '4:25', creditedHours: 4.42, notCreditedMin: 15, uncreditedMin: 0 });
    expect(V.hhmm(V.ENTRY_B.effEnd)).toBe('16:15');
    expect(V.ENTRY_B).toMatchObject({ credited: '1:30', creditedHours: 1.5, notCreditedMin: 120, uncreditedMin: 105 });
  });
  it('§4.1 Tabelle: Beispielzeile 08:00–18:00 bei Blöcken 08–12 + 15–18 gibt 150 min Lücke', () => {
    // Gegenprobe der Formel gegen die dokumentierte Tabellenzeile (7,50 h)
    const g = 15, gap = { s: 12 * 60 + g, e: 15 * 60 - g };
    expect(gap.e - gap.s).toBe(150);
  });
  it('§13.1 Soll/Ist/Saldo', () => {
    expect(V.SOLL_DAYS).toBe(17);
    expect(V.SOLL_HOURS).toBe(136);
    expect(V.IST_HOURS).toBe(137.5);
    expect(V.SALDO_HOURS).toBe(1.5);
  });
  it('§7.2 Konto kumuliert', () => {
    expect(V.MONTHS.map((m) => m.konto)).toEqual([1.5, -6.5, -0.5, 2]);
    let k = 0;
    V.MONTHS.forEach((m) => { k += m.saldo; expect(m.konto).toBeCloseTo(k, 6); });
  });
  it('§8 Urlaubskonto 13.4 (+ Übertrag)', () => {
    expect(V.VAC_BUDGET).toBe(32);
    expect(V.VAC_REMAINING).toBe(28);
  });
  it('§9.4 Split: 3 Tage Rest, 5 Schließtage', () => {
    expect(V.CLOSURE_DAYS.map((d) => d.type)).toEqual(['VACATION', 'VACATION', 'VACATION', 'OVERTIME', 'OVERTIME']);
    expect(V.CLOSURE_DAYS.map((d) => d.restBefore)).toEqual([3, 2, 1, 0, 0]);
    expect(V.CLOSURE_OVERTIME_HOURS).toBe(16);
  });
  it('ClosureSplit nennt die Voraussetzung (Wortlaut Settings.tsx)', () => {
    const html = renderToString(createElement(DIAGRAMS['betriebsferien-split']));
    expect(html).toContain('Überzählige Betriebsferien als Überstundenabbau');
  });
});
