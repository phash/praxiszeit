import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { COMIC_SCENES } from './scenes';

describe('COMIC_SCENES', () => {
  it('enthält die Broschüren-Szenen und die Szenen der Handbücher', () => {
    expect(Object.keys(COMIC_SCENES).sort()).toEqual([
      'antrag', 'bloecke', 'einrichtung', 'handy', 'hero', 'nachweise', 'neuimteam', 'schichtplan', 'stempeln',
      'uebersicht', 'urlaub', 'zweifaktor',
    ]);
  });

  for (const key of Object.keys(COMIC_SCENES)) {
    it(`Szene "${key}" rendert als SVG ohne style-Attribut`, () => {
      const Scene = COMIC_SCENES[key];
      const html = renderToString(createElement(Scene));
      expect(html).toContain('<svg');
      expect(html).not.toContain('style=');
    });
  }
});
