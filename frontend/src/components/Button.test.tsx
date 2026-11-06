import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Button from './Button';

const bgClasses = (el: HTMLElement) =>
  el.className.split(/\s+/).filter((c) => /^bg-/.test(c));

describe('Button', () => {
  // #533: jede Variante trägt genau eine Hintergrundfarbe, sonst entscheidet
  // die CSS-Reihenfolge von Tailwind v4, welche gewinnt.
  it.each(['primary', 'secondary', 'danger', 'ghost', 'warning'] as const)(
    'Variante %s hat genau eine Hintergrundklasse',
    (variant) => {
      render(<Button variant={variant}>Knopf</Button>);
      expect(bgClasses(screen.getByRole('button', { name: 'Knopf' }))).toHaveLength(1);
    },
  );

  it('Variante warning ist bernsteinfarben mit weißer Schrift', () => {
    render(<Button variant="warning">Antrag</Button>);
    const button = screen.getByRole('button', { name: 'Antrag' });
    expect(button.className).toMatch(/(^|\s)bg-amber-500(\s|$)/);
    expect(button.className).toMatch(/(^|\s)text-white(\s|$)/);
  });
});
