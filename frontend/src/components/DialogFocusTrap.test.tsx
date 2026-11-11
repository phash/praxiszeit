import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DialogFocusTrap from './DialogFocusTrap';

// P2.1 (Handbuch-Funde): Ein Klick auf nicht fokussierbaren Text im Dialog gab
// den Fokus an <main tabIndex=-1> (außerhalb der Falle); focus-trap holte ihn
// aufs letzte Feld zurück und scrollte — der Klick ging daneben. Der Container
// muss deshalb selbst fokussierbar sein. jsdom mockt focus-trap-react
// (src/test/setup.ts); das Verhalten selbst ist per Playwright belegt.

describe('DialogFocusTrap', () => {
  it('macht den Dialog-Container fokussierbar (tabIndex -1), ohne Rahmen bei Fokus', () => {
    render(
      <DialogFocusTrap focusTrapOptions={{ allowOutsideClick: true }}>
        <div role="dialog" aria-label="Probe" className="bg-white p-6">
          <input aria-label="Feld" />
        </div>
      </DialogFocusTrap>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('tabindex', '-1');
    expect(dialog).toHaveClass('bg-white', 'p-6', 'focus:outline-hidden');
  });

  it('ein ausdrücklich gesetzter tabIndex bleibt', () => {
    render(
      <DialogFocusTrap>
        <div role="dialog" aria-label="Probe" tabIndex={0}>
          <button type="button">OK</button>
        </div>
      </DialogFocusTrap>,
    );
    expect(screen.getByRole('dialog')).toHaveAttribute('tabindex', '0');
  });

  it('kein Dialog nutzt focus-trap-react direkt (alle gehen über DialogFocusTrap)', () => {
    const sources = import.meta.glob(['../**/*.tsx', '../**/*.ts', '!../**/*.test.tsx', '!../**/*.test.ts', '!../test/**'], {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    expect(Object.keys(sources).length).toBeGreaterThan(50);
    const direct = Object.entries(sources)
      .filter(([path, src]) => !path.endsWith('/DialogFocusTrap.tsx') && /from ['"]focus-trap-react['"]/.test(src))
      .map(([path]) => path);
    expect(direct).toEqual([]);
  });
});
