import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RawStampNote } from './RawStampNote';

describe('RawStampNote (#462)', () => {
  it('nennt Rohwert und angerechnete Zeit für den Beginn', () => {
    render(<RawStampNote raw="07:37:00" effective="07:45:00" side="start" />);
    expect(screen.getByText(/gestempelt 07:37 · angerechnet ab 07:45/)).toBeInTheDocument();
  });

  it('sagt "bis" statt "ab", wenn das Ende gekappt wurde', () => {
    render(<RawStampNote raw="18:20:00" effective="17:15:00" side="end" />);
    expect(screen.getByText(/gestempelt 18:20 · angerechnet bis 17:15/)).toBeInTheDocument();
  });

  it('zeigt nichts, wenn kein Rohwert existiert (der Regelfall)', () => {
    const { container } = render(<RawStampNote raw={null} effective="08:00:00" side="start" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('zeigt nichts, wenn die effektive Zeit fehlt (offener Eintrag)', () => {
    const { container } = render(<RawStampNote raw="18:20:00" effective={null} side="end" />);
    expect(container).toBeEmptyDOMElement();
  });
});
