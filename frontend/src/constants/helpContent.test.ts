import { describe, it, expect } from 'vitest';
import { helpContent } from './helpContent';
import { HANDBOOKS } from '../handbuch/content';

const ADMIN_ONLY = new Set(['praxisleitung']);

describe('helpContent handbook links', () => {
  it('every route has a handbook link', () => {
    for (const [route, entry] of Object.entries(helpContent)) {
      expect(entry.handbook, route).toBeDefined();
    }
  });

  it('every helpContent handbook link resolves to an existing chapter or task id', () => {
    for (const [route, entry] of Object.entries(helpContent)) {
      const link = entry.handbook!;
      const book = HANDBOOKS[link.book];
      expect(book, `${route}: Buch ${link.book}`).toBeDefined();
      const ids = new Set<string>();
      for (const c of book.chapters) {
        ids.add(c.id);
        for (const b of c.blocks) if (b.kind === 'task') ids.add(b.id);
      }
      expect(ids.has(link.anchor), `${route}: Anker ${link.anchor} in ${link.book}`).toBe(true);
    }
  });

  it('employee routes link a book every role may open; admin routes the Praxisleitung book', () => {
    for (const [route, entry] of Object.entries(helpContent)) {
      const adminRoute = route.startsWith('/admin');
      expect(ADMIN_ONLY.has(entry.handbook!.book), route).toBe(adminRoute);
    }
  });
});
