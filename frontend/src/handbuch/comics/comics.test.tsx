import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { COMIC_SCENES } from './scenes';

describe('COMIC_SCENES', () => {
  it('enthält die fünf Broschüren-Szenen', () => {
    expect(Object.keys(COMIC_SCENES).sort()).toEqual(['hero', 'nachweise', 'stempeln', 'uebersicht', 'urlaub']);
  });

  for (const key of ['hero', 'stempeln', 'uebersicht', 'urlaub', 'nachweise']) {
    it(`Szene "${key}" rendert als SVG ohne style-Attribut`, () => {
      const Scene = COMIC_SCENES[key];
      const html = renderToString(createElement(Scene));
      expect(html).toContain('<svg');
      expect(html).not.toContain('style=');
    });
  }
});
