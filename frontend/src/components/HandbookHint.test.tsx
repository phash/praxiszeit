import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HandbookHint from './HandbookHint';
import { handbookHints } from '../constants/handbookHints';

function renderHint() {
  return render(
    <MemoryRouter>
      <div>
        <HandbookHint hintId="wh-effective-date" />
        <button type="button">Außen</button>
      </div>
    </MemoryRouter>,
  );
}

const hint = handbookHints['wh-effective-date'];

describe('HandbookHint', () => {
  it('renders a closed help button labelled with the hint title', () => {
    renderHint();
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
  });

  it('opens on click and shows title, text and the handbook link', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    expect(screen.getByRole('button', { name: `Hilfe: ${hint.title}` })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(hint.text)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Mehr im Handbuch/ });
    expect(link.getAttribute('href')).toBe('/help/praxisleitung#rueckwirkend-aendern');
  });

  it('closes on Escape', () => {
    renderHint();
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    fireEvent.click(btn);
    fireEvent.keyDown(btn, { key: 'Escape' });
    expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
  });

  it('Escape on the hint does not reach a surrounding dialog listening on document', () => {
    // focus-trap (WorkingHoursModal) lauscht in der Bubble-Phase auf document – Esc darf dort nicht ankommen.
    const parentEsc = vi.fn();
    document.addEventListener('keydown', parentEsc);
    try {
      renderHint();
      const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
      fireEvent.click(btn);
      fireEvent.keyDown(btn, { key: 'Escape' });
      expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
      expect(parentEsc).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('keydown', parentEsc);
    }
  });

  it('lets Escape through to the surrounding dialog when the hint is closed', () => {
    const parentEsc = vi.fn();
    document.addEventListener('keydown', parentEsc);
    try {
      renderHint();
      fireEvent.keyDown(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }), { key: 'Escape' });
      expect(parentEsc).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener('keydown', parentEsc);
    }
  });

  it('closes on a click outside', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Außen' }));
    expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
  });

  it('stays open on a click inside the popover', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    fireEvent.mouseDown(screen.getByText(hint.text));
    expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).toBeInTheDocument();
  });

  it('closes when focus leaves the popover', () => {
    renderHint();
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    fireEvent.click(btn);
    const link = screen.getByRole('link', { name: /Mehr im Handbuch/ });
    fireEvent.blur(link, { relatedTarget: screen.getByRole('button', { name: 'Außen' }) });
    expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
  });

  it('stays open when focus moves from the button into the popover', () => {
    renderHint();
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    fireEvent.click(btn);
    const link = screen.getByRole('link', { name: /Mehr im Handbuch/ });
    fireEvent.blur(btn, { relatedTarget: link });
    expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).toBeInTheDocument();
  });

  it('aligns the popover to the left edge by default and to the right edge with align="end"', () => {
    const { unmount } = renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    expect(screen.getByRole('dialog', { name: hint.title }).className).toMatch(/(^|\s)sm:left-0(\s|$)/);
    unmount();

    render(
      <MemoryRouter>
        <HandbookHint hintId="wh-effective-date" align="end" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    const cls = screen.getByRole('dialog', { name: hint.title }).className;
    expect(cls).toMatch(/(^|\s)sm:right-0(\s|$)/);
    expect(cls).not.toMatch(/(^|\s)sm:left-0(\s|$)/);
    // das Bottom-Sheet unter 640 px bleibt
    expect(cls).toMatch(/(^|\s)inset-x-0(\s|$)/);
  });

  it('uses a bottom sheet below 640 px', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    const dialog = screen.getByRole('dialog', { name: hint.title });
    expect(dialog.className).toMatch(/(^|\s)fixed(\s|$)/);
    expect(dialog.className).toMatch(/(^|\s)inset-x-0(\s|$)/);
    expect(dialog.className).toMatch(/(^|\s)bottom-0(\s|$)/);
    expect(dialog.className).toMatch(/sm:absolute/);
  });

  it('Escape closes only the hint even when focus stays outside it (Safari), the dialog never sees it', () => {
    // Safari/Firefox (macOS) fokussieren Knöpfe beim Klick nicht: der Fokus bleibt im Feld davor.
    // focus-trap (Bubble auf document) und ChangeRequestForm (document) dürfen das Esc nicht sehen.
    const dialogEsc = vi.fn();
    document.addEventListener('keydown', dialogEsc);
    try {
      render(
        <MemoryRouter>
          <div role="dialog" aria-modal="true">
            <input aria-label="Notiz" />
            <HandbookHint hintId="wh-effective-date" />
          </div>
        </MemoryRouter>,
      );
      const input = screen.getByRole('textbox', { name: 'Notiz' });
      input.focus();
      // Schlimmster Fall: auch das programmatische focus() greift nicht, der Fokus bleibt im Feld.
      const focusSpy = vi.spyOn(HTMLButtonElement.prototype, 'focus').mockImplementation(() => {});
      fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
      focusSpy.mockRestore();
      expect(document.activeElement).toBe(input);
      expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).toBeInTheDocument();
      fireEvent.keyDown(input, { key: 'Escape' });
      expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
      expect(dialogEsc).not.toHaveBeenCalled();
      // geschlossen: das nächste Esc gehört wieder dem Dialog
      fireEvent.keyDown(input, { key: 'Escape' });
      expect(dialogEsc).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener('keydown', dialogEsc);
    }
  });

  it('focuses the help button on click (Safari does not), so focus handling works', () => {
    renderHint();
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    fireEvent.click(btn);
    expect(document.activeElement).toBe(btn);
  });

  it('stays open when a click on popover text moves focus to its nearest focusable ancestor', () => {
    // Chrome/Edge/Firefox (Windows) geben den Fokus beim Klick auf Text an den nächsten fokussierbaren
    // Vorfahren. Das muss das Popover selbst sein, nicht <main tabIndex=-1> drumherum.
    render(
      <MemoryRouter>
        <main tabIndex={-1} data-testid="main">
          <HandbookHint hintId="wh-effective-date" />
        </main>
      </MemoryRouter>,
    );
    const btn = screen.getByRole('button', { name: `Hilfe: ${hint.title}` });
    fireEvent.click(btn);
    const dialog = screen.getByRole('dialog', { name: hint.title });
    const focusTarget = screen.getByText(hint.text).closest('[tabindex], a, button, input');
    expect(focusTarget).toBe(dialog);
    expect(dialog).toHaveAttribute('tabindex', '-1');
    fireEvent.blur(btn, { relatedTarget: focusTarget });
    expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).toBeInTheDocument();
    // Fokus wirklich auf main (außerhalb) schließt weiterhin
    fireEvent.blur(dialog, { relatedTarget: screen.getByTestId('main') });
    expect(screen.queryByRole('link', { name: /Mehr im Handbuch/ })).toBeNull();
  });

  it('opens the handbook link in the same tab outside dialogs', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).not.toHaveAttribute('target');
  });

  it('opens the handbook link in a new tab inside a modal dialog, so unsaved input survives', () => {
    render(
      <MemoryRouter>
        <div role="dialog" aria-modal="true">
          <HandbookHint hintId="wh-effective-date" />
        </div>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    const link = screen.getByRole('link', { name: /Mehr im Handbuch/ });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toMatch(/noopener/);
    expect(link.getAttribute('href')).toBe('/help/praxisleitung#rueckwirkend-aendern');
  });

  it('newTab prop overrides the automatic choice', () => {
    render(
      <MemoryRouter>
        <HandbookHint hintId="wh-effective-date" newTab />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    expect(screen.getByRole('link', { name: /Mehr im Handbuch/ })).toHaveAttribute('target', '_blank');
  });

  describe('placement from 640 px', () => {
    const originalMatchMedia = window.matchMedia;

    function setup(opts: { sm: boolean; wrapperLeft: number; clipRight: number; align?: 'start' | 'end' }) {
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: (q: string) => ({ matches: opts.sm, media: q, addEventListener() {}, removeEventListener() {} }),
      });
      vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(288);
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        const r = (left: number, right: number) =>
          ({ left, right, width: right - left, top: 0, bottom: 16, height: 16, x: left, y: 0, toJSON() {} }) as DOMRect;
        if ((this as HTMLElement).dataset?.testid === 'clip') return r(0, opts.clipRight);
        if (this.querySelector?.(':scope > button[aria-label^="Hilfe:"]')) return r(opts.wrapperLeft, opts.wrapperLeft + 16);
        return r(0, 0);
      });
      render(
        <MemoryRouter>
          <div data-testid="clip" style={{ overflowX: 'hidden' }}>
            <HandbookHint hintId="wh-effective-date" align={opts.align} />
          </div>
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
      return screen.getByRole('dialog', { name: hint.title });
    }

    afterEach(() => {
      vi.restoreAllMocks();
      Object.defineProperty(window, 'matchMedia', { configurable: true, writable: true, value: originalMatchMedia });
    });

    it('shifts a left-aligned popover back inside a clipping ancestor near its right edge', () => {
      // „?“ bei 700 px, abschneidender Vorfahr endet bei 800 px: 700 + 288 ragte 188 px hinaus.
      const dialog = setup({ sm: true, wrapperLeft: 700, clipRight: 800 });
      // 800 − 8 Rand − 288 Breite − 700 = −196
      expect(dialog.style.left).toBe('-196px');
      expect(dialog.style.right).toBe('auto');
    });

    it('keeps the default position when the popover fits', () => {
      const dialog = setup({ sm: true, wrapperLeft: 100, clipRight: 800 });
      expect(dialog.style.left).toBe('0px');
    });

    it('shifts a right-aligned popover back inside near the left edge', () => {
      // align="end" bei 20 px: 20 + 16 − 288 < 0 → an den linken Rand + 8 px schieben (8 − 20 = −12)
      const dialog = setup({ sm: true, wrapperLeft: 20, clipRight: 800, align: 'end' });
      expect(dialog.style.left).toBe('-12px');
    });

    it('leaves the bottom sheet alone below 640 px', () => {
      const dialog = setup({ sm: false, wrapperLeft: 700, clipRight: 800 });
      expect(dialog.style.left).toBe('');
    });
  });
});
