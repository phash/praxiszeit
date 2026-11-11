import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HelpPanel from './HelpPanel';

vi.mock('./FeedbackDialog', () => ({ default: () => null }));

function open(path: string, onClose = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <HelpPanel isOpen onClose={onClose} />
    </MemoryRouter>,
  );
  return onClose;
}

describe('HelpPanel', () => {
  it('shows the handbook link for /time-tracking', () => {
    open('/time-tracking');
    const link = screen.getByRole('link', { name: /Im Handbuch ansehen/ });
    expect(link.getAttribute('href')).toBe('/help/mitarbeitende#zeiterfassung-stempeln-eintraege');
  });

  it('closes the panel when the link is clicked', () => {
    const onClose = open('/admin/users');
    const link = screen.getByRole('link', { name: /Im Handbuch ansehen/ });
    expect(link.getAttribute('href')).toMatch(/^\/help\/praxisleitung#/);
    fireEvent.click(link);
    expect(onClose).toHaveBeenCalled();
  });

  it('shows no handbook link on the fallback page', () => {
    open('/unbekannt');
    expect(screen.queryByRole('link', { name: /Im Handbuch ansehen/ })).toBeNull();
  });
});
