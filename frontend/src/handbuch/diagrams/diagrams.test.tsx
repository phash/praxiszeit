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

describe('values (BERECHNUNGEN-Beispiele)', () => {
  it('Tageszeitstrahl: Hülle, Lücke, Zeiteinträge nach work_window_service', () => {
    expect(V.GRACE).toBe(15);
    expect(V.HULL).toEqual({ start: '07:45', end: '16:15' });
    expect(V.GAP_SHRUNK).toEqual({ start: '12:15', end: '14:45' });
    expect(V.ENTRY_A).toMatchObject({ credited: '4:25', creditedHours: 4.42, notCreditedMin: 15, uncreditedMin: 0 });
    expect(V.ENTRY_B).toMatchObject({ credited: '1:30', creditedHours: 1.5, notCreditedMin: 120, uncreditedMin: 105 });
  });
  it('Soll/Ist (13.1)', () => {
    expect(V.SOLL_DAYS).toBe(22 - 1 - 4);
    expect(V.SOLL_HOURS).toBe(136);
    expect(V.IST_HOURS).toBe(14 * 8 + 3 * 8.5);
    expect(V.SALDO_HOURS).toBe(1.5);
  });
  it('Konto kumuliert (7.2)', () => {
    let k = 0;
    V.MONTHS.forEach((m) => { k += m.saldo; expect(m.konto).toBeCloseTo(k, 6); });
  });
  it('Urlaubskonto (8.1–8.3)', () => {
    expect(V.VAC_BUDGET).toBe(V.VAC_ENTITLEMENT + V.VAC_CARRYOVER);
    expect(V.VAC_REMAINING).toBe(V.VAC_BUDGET - V.VAC_USED);
  });
  it('Betriebsferien-Split (9.4): Urlaub solange Rest ≥ 1', () => {
    let rest = V.CLOSURE_REST_BEFORE;
    V.CLOSURE_DAYS.forEach((d) => {
      const t = rest >= 1 ? 'VACATION' : 'OVERTIME';
      expect(d.type).toBe(t);
      if (t === 'VACATION') rest -= 1;
      expect(d.restAfter).toBe(rest);
    });
  });
});
