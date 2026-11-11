import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import * as V from '../diagrams/values';
import type { Block, Chapter } from '../types';
import { HANDBOOKS } from './index';
import data from './rechenbeispiele.json';

/**
 * so-rechnet tables match rechenbeispiele.json.
 * Die JSON-Datei ist die gemeinsame Quelle; backend/tests/test_handbuch_rechenbeispiele.py rechnet jeden
 * Fall mit dem echten Berechnungscode nach, hier werden Tabellen (so-rechnet.ts) und Diagramm-Konstanten
 * (diagrams/values.ts) dagegen geprüft.
 */
type Val = { v: number | string; text: string; col?: number };
interface Case { id: string; topic?: string; section?: string; row?: string[]; diagram?: string; values: Record<string, Val> }
const cases = (data as unknown as { cases: Case[] }).cases;
const byId = new Map(cases.map((c) => [c.id, c]));
const book = HANDBOOKS['so-rechnet'];

const EXPECTED_CHAPTERS = [
  'grundbegriffe', 'tagessoll', 'ist-pausen', 'bloecke-kappung', 'monatssaldo', 'abwesenheiten',
  'urlaubskonto', 'betriebsferien', 'sondertage', 'minijob', 'jahresabschluss',
];
/** Diagramm je Kapitel (Spec 6.6: Diagramm, wo eines passt). */
const DIAGRAM_OF: Record<string, string> = {
  grundbegriffe: 'soll-ist', 'bloecke-kappung': 'tag-zeitstrahl', monatssaldo: 'saldo-monat',
  urlaubskonto: 'urlaubskonto', betriebsferien: 'betriebsferien-split',
};

function strings(b: Block): string[] {
  switch (b.kind) {
    case 'task': return [b.title, b.intro ?? '', ...b.steps.map((s) => s.text)];
    case 'tip': case 'comic': case 'prose': return [b.text];
    case 'diagram': return [b.caption];
    case 'table': return [...b.head, ...b.rows.flat()];
  }
}
const chapterText = (ch: Chapter) => ch.blocks.flatMap(strings).join('\n');
const chapter = (id: string) => book.chapters.find((c) => c.id === id)!;
const tables = (ch: Chapter) => ch.blocks.filter((b): b is Extract<Block, { kind: 'table' }> => b.kind === 'table');
const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

describe('So rechnet PraxisZeit: Aufbau', () => {
  it('hat die elf Themen in der Reihenfolge des Spec', () => {
    expect(book.chapters.map((c) => c.id)).toEqual(EXPECTED_CHAPTERS);
  });
  for (const id of EXPECTED_CHAPTERS) {
    it(`${id}: Kernsatz, Beispieltabelle, Technische Details`, () => {
      const ch = chapter(id);
      expect(ch.blocks[0].kind).toBe('prose');
      expect(tables(ch).some((t) => t.rows.length > 0)).toBe(true);
      const link = /\[Technische Details[^\]]*\]\(https:\/\/github\.com\/phash\/praxiszeit\/blob\/master\/docs\/BERECHNUNGEN\.md#([^)]+)\)/;
      expect(chapterText(ch)).toMatch(link);
    });
    if (DIAGRAM_OF[id]) {
      it(`${id}: Diagramm ${DIAGRAM_OF[id]}`, () => {
        const d = chapter(id).blocks.filter((b) => b.kind === 'diagram');
        expect(d.map((b) => (b as { diagram: string }).diagram)).toEqual([DIAGRAM_OF[id]]);
      });
    }
  }
  it('Anker der „Technische Details"-Links gibt es in docs/BERECHNUNGEN.md (GitHub-Slug)', () => {
    const md = readFileSync(resolve(__dirname, '../../../../docs/BERECHNUNGEN.md'), 'utf8');
    const slug = (h: string) => h.trim().toLowerCase().replace(/[^\p{L}\p{N}_\- ]/gu, '').replace(/ /g, '-');
    const anchors = new Set(md.split('\n').filter((l) => /^#{1,6} /.test(l)).map((l) => slug(l.replace(/^#+ /, ''))));
    const used = [...book.chapters.map(chapterText).join('\n').matchAll(/BERECHNUNGEN\.md#([^)\s]+)/g)].map((m) => m[1]);
    expect(used.length).toBeGreaterThanOrEqual(11);
    expect(used.filter((a) => !anchors.has(a))).toEqual([]);
  });
  it('Diagramme mit erfundenen Beispielwerten heißen in der Unterschrift „Beispiel"', () => {
    for (const id of ['monatssaldo', 'urlaubskonto', 'betriebsferien']) {
      const cap = chapter(id).blocks.find((b) => b.kind === 'diagram') as { caption: string };
      expect(cap.caption).toMatch(/Beispiel/);
    }
  });
});

describe('so-rechnet tables match rechenbeispiele.json', () => {
  it('jede JSON-Zeile steht wortgleich in einer Tabelle ihres Kapitels', () => {
    const missing = cases.filter((c) => c.row).filter((c) => {
      const ch = book.chapters.find((x) => x.id === c.topic);
      return !ch || !tables(ch).some((t) => t.rows.some((r) => same(r, c.row!)));
    }).map((c) => c.id);
    expect(missing).toEqual([]);
  });
  it('jeder Wert steht in der Tabellenzelle seiner Spalte', () => {
    const bad = cases.filter((c) => c.row).flatMap((c) =>
      Object.entries(c.values).filter(([, v]) => v.col === undefined || !c.row![v.col].includes(v.text)).map(([k]) => `${c.id}.${k}`));
    expect(bad).toEqual([]);
  });
  it('jeder Anzeigetext eines Falls steht im Text seines Kapitels', () => {
    const missing = cases.flatMap((c) => {
      const ch = book.chapters.find((x) => x.id === c.topic);
      const text = ch ? chapterText(ch) : '';
      return Object.entries(c.values).filter(([, v]) => !text.includes(v.text)).map(([k]) => `${c.id}.${k}`);
    });
    expect(missing).toEqual([]);
  });
  it('Tabellen mit gerechneten Zeilen enthalten NUR gerechnete Zeilen', () => {
    const offenders: string[] = [];
    for (const ch of book.chapters) {
      for (const t of tables(ch)) {
        const backed = t.rows.map((r) => cases.some((c) => c.row && c.topic === ch.id && same(c.row, r)));
        if (backed.some(Boolean) && !backed.every(Boolean)) offenders.push(`${ch.id}: ${t.head[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
  it('jedes Kapitel enthält mindestens eine gerechnete Tabelle, außer Grundbegriffe', () => {
    const none = book.chapters.filter((ch) => ch.id !== 'grundbegriffe')
      .filter((ch) => !cases.some((c) => c.row && c.topic === ch.id)).map((c) => c.id);
    expect(none).toEqual([]);
  });
  it('Fall-IDs sind eindeutig', () => {
    expect(new Set(cases.map((c) => c.id)).size).toBe(cases.length);
  });
});

describe('diagrams/values.ts stimmt mit rechenbeispiele.json überein', () => {
  const v = (id: string, k: string) => byId.get(id)!.values[k];
  const num = (id: string, k: string) => v(id, k).v as number;
  const hhmmOf = (m: number) => V.hhmm(m);

  it('Soll / Ist / Saldo (13.1)', () => {
    expect(V.SOLL_DAYS).toBe(num('monat-soll', 'soll_days'));
    expect(V.SOLL_HOURS).toBe(num('monat-soll', 'soll'));
    expect(V.IST_HOURS).toBe(num('monat-ist', 'ist'));
    expect(V.SALDO_HOURS).toBeCloseTo(num('monat-saldo', 'saldo'), 6);
    expect(V.DAY_TARGET).toBe(num('tagessoll-vollzeit', 'daily_target'));
  });
  it('Monate und Konto', () => {
    expect(V.MONTHS.map((m) => ({ name: m.name, saldo: m.saldo, konto: m.konto }))).toEqual(
      (data as unknown as { diagram_months: unknown[] }).diagram_months,
    );
    expect(V.MONTHS[0].saldo).toBe(num('monat-saldo', 'saldo'));
    expect(V.MONTHS[1].saldo).toBe(num('monat-ueberstundenausgleich', 'saldo'));
    expect(V.MONTHS[0].konto).toBe(num('monat-konto', 'jan'));
    expect(V.MONTHS[1].konto).toBe(num('monat-konto', 'feb'));
  });
  it('Zeitstrahl: Puffer, Hülle, Zeiteinträge A und B', () => {
    expect(hhmmOf(V.HULL.start)).toBe(v('diagram-huelle-luecke', 'hull_start').v);
    expect(hhmmOf(V.HULL.end)).toBe(v('diagram-huelle-luecke', 'hull_end').v);
    expect(V.GAP_SHRUNK!.end - V.GAP_SHRUNK!.start).toBe(num('diagram-huelle-luecke', 'gap_min'));
    expect(V.hhmm(V.ENTRY_A.effStart)).toBe('07:45');
    for (const [id, e] of [['diagram-eintrag-a', V.ENTRY_A], ['diagram-eintrag-b', V.ENTRY_B]] as const) {
      expect(hhmmOf(e.effStart)).toBe(v(id, 'eff_start').v);
      expect(hhmmOf(e.effEnd)).toBe(v(id, 'eff_end').v);
      expect(e.uncreditedMin).toBe(num(id, 'uncredited'));
      expect(e.notCreditedMin).toBe(num(id, 'not_credited'));
      expect(e.creditedHours).toBeCloseTo(num(id, 'net_hours'), 2);
      expect(`${e.credited} h`).toBe(v(id, 'net_hours').text);
    }
    expect(V.GRACE).toBe(15);
    // Puffer-Beispiel der Unterschrift: 07:30 → 07:45 (Block 08:00, Puffer 15)
    expect(hhmmOf(V.clampEntry(V.hm(7, 30), V.hm(12)).effStart)).toBe(v('kappung-puffer-07-30', 'eff_start').v);
  });
  it('Urlaubskonto', () => {
    expect(V.VAC_ENTITLEMENT).toBe(num('urlaub-mit-uebertrag', 'entitlement'));
    expect(V.VAC_CARRYOVER).toBe(num('urlaub-mit-uebertrag', 'carryover'));
    expect(V.VAC_BUDGET).toBe(num('urlaub-mit-uebertrag', 'budget'));
    expect(V.VAC_USED).toBe(num('urlaub-mit-uebertrag', 'used'));
    expect(V.VAC_REMAINING).toBe(num('urlaub-mit-uebertrag', 'rest'));
    expect(V.VAC_ENTITLEMENT - V.VAC_USED).toBe(num('urlaub-ohne-uebertrag', 'rest'));
  });
  it('Betriebsferien-Aufteilung', () => {
    const keys = ['mo', 'di', 'mi', 'do', 'fr'];
    const label = { VACATION: 'Urlaub', OVERTIME: 'Überstundenausgleich' } as const;
    V.CLOSURE_DAYS.forEach((d, i) => {
      const id = `betriebsferien-${keys[i]}`;
      expect(label[d.type]).toBe(v(id, 'buchung').v);
      expect(d.restBefore).toBe(num(id, 'rest_before'));
      expect(d.restAfter).toBe(num(id, 'rest_after'));
    });
    expect(-V.CLOSURE_OVERTIME_HOURS).toBe(num('betriebsferien-konto', 'konto'));
    expect(V.CLOSURE_REST_BEFORE).toBe(num('betriebsferien-mo', 'rest_before'));
  });
  it('Diagramm-Fälle nennen ein Diagramm, das es gibt', () => {
    const keys = ['soll-ist', 'tag-zeitstrahl', 'saldo-monat', 'urlaubskonto', 'betriebsferien-split'];
    expect(cases.filter((c) => c.diagram).filter((c) => !keys.includes(c.diagram!)).map((c) => c.id)).toEqual([]);
  });
});
