import { describe, it, expect } from 'vitest';
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

  it('uses a bottom sheet below 640 px', () => {
    renderHint();
    fireEvent.click(screen.getByRole('button', { name: `Hilfe: ${hint.title}` }));
    const dialog = screen.getByRole('dialog', { name: hint.title });
    expect(dialog.className).toMatch(/(^|\s)fixed(\s|$)/);
    expect(dialog.className).toMatch(/(^|\s)inset-x-0(\s|$)/);
    expect(dialog.className).toMatch(/(^|\s)bottom-0(\s|$)/);
    expect(dialog.className).toMatch(/sm:absolute/);
  });
});
