import { describe, expect, it } from 'vitest';
import manifestJson from '../manifest.json';
import type { Handbook, Manifest } from '../types';
import { validateHandbook } from '../validate';
import { FORBIDDEN_TERMS } from './forbiddenTerms';
import { ALL_SHOTS, HANDBOOKS } from './index';

const manifest = manifestJson as unknown as Manifest;

/** Kapitel ohne Screenshot (Ruling R7), z. B. Häufige Fragen. Je Eintrag eine Begründung. */
const NO_SHOT_CHAPTERS: readonly string[] = [
  // Mitarbeitende „Häufige Fragen“: kurze Antworten, jede verweist auf die Aufgabe mit Bild.
  'haeufige-fragen',
];

/** Alle Zeichenketten eines Objekts (Texte, Titel, Alt-Texte, Locator-Namen …). */
function allStrings(v: unknown, out: string[] = []): string[] {
  if (typeof v === 'string') out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => allStrings(x, out));
  else if (v && typeof v === 'object') Object.values(v).forEach((x) => allStrings(x, out));
  return out;
}

const books = Object.values(HANDBOOKS) as Handbook[];

describe('Handbuch-Inhalte', () => {
  it('HANDBOOKS ist nach Handbuch-ID geschlüsselt', () => {
    for (const [key, h] of Object.entries(HANDBOOKS)) expect(h.id).toBe(key);
  });

  for (const h of books) {
    it(`${h.id}: validateHandbook liefert keine Fehler`, () => {
      expect(validateHandbook(h, manifest)).toEqual([]);
    });

    it(`${h.id}: jedes Kapitel hat eine Aufgabe mit Screenshot oder steht in NO_SHOT_CHAPTERS`, () => {
      const missing = h.chapters
        .filter((ch) => !NO_SHOT_CHAPTERS.includes(ch.id))
        .filter((ch) => !ch.blocks.some((b) => b.kind === 'task' && b.shot))
        .map((ch) => ch.id);
      expect(missing).toEqual([]);
    });

    it(`${h.id}: kein veralteter Begriff im Inhalt`, () => {
      const hits = allStrings(h).flatMap((s) => FORBIDDEN_TERMS.filter((t) => s.includes(t)).map((t) => `${t} ⇐ ${s}`));
      expect(hits).toEqual([]);
    });
  }

  it('ALL_SHOTS enthält jede Aufnahme jedes Handbuchs genau einmal', () => {
    const ids = ALL_SHOTS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.sort()).toEqual(books.flatMap((h) => h.shots.map((s) => s.id)).sort());
  });

  it('jede Aufnahme wird von einer Aufgabe genutzt', () => {
    for (const h of books) {
      const used = new Set(h.chapters.flatMap((ch) => ch.blocks.flatMap((b) => (b.kind === 'task' && b.shot ? [b.shot] : []))));
      expect(h.shots.map((s) => s.id).filter((id) => !used.has(id))).toEqual([]);
    }
  });

  it('das Manifest enthält nur Aufnahmen, die ein Handbuch definiert', () => {
    const known = new Set(ALL_SHOTS.map((s) => s.id));
    expect(Object.keys(manifest).filter((id) => !known.has(id))).toEqual([]);
  });
});
