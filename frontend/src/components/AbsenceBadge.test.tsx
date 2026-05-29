import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AbsenceBadge from './AbsenceBadge';

describe('AbsenceBadge', () => {
  it('renders the initials and a circular badge with a ring + tooltip', () => {
    render(
      <AbsenceBadge type="vacation" userColor="#AB12CD" initials="EM" title="Erika Muster – Urlaub" />,
    );
    const el = screen.getByText('EM');
    expect(el).toHaveAttribute('title', 'Erika Muster – Urlaub');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('border-radius'); // circle
    expect(style).toContain('border'); // employee-colour ring
  });

  it('uses a neutral centre for the masked "absent" type', () => {
    render(<AbsenceBadge type="absent" userColor="#000000" initials="XY" />);
    const el = screen.getByText('XY');
    const style = (el.getAttribute('style') || '').toLowerCase();
    // #6B7280 fallback (rgb(107, 114, 128)) — accept hex or rgb serialisation
    expect(style).toMatch(/6b7280|107, ?114, ?128/);
  });
});
