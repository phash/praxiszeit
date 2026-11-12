import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HelpPanel from './HelpPanel';

// auth-10: Escape im Feedback-Dialog darf das Hilfe-Panel nicht mitschließen.
vi.mock('./FeedbackDialog', () => ({ default: () => <div>Feedback-Dialog</div> }));

describe('<HelpPanel /> Escape', () => {
  it('schließt das Panel mit Escape, aber nicht bei offenem Feedback-Dialog', () => {
    const onClose = vi.fn();
    render(<MemoryRouter><HelpPanel isOpen onClose={onClose} /></MemoryRouter>);
    fireEvent.click(screen.getByText(/Fehler melden/));
    expect(screen.getByText('Feedback-Dialog')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
  it('schließt das Panel mit Escape ohne Dialog', () => {
    const onClose = vi.fn();
    render(<MemoryRouter><HelpPanel isOpen onClose={onClose} /></MemoryRouter>);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
