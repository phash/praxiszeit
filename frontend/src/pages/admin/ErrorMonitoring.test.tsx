import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

/**
 * Handbuch-Fund P5.3: Die Zähler zeigten die rohen API-Werte („open: 0“,
 * „ignored“, „resolved“) neben deutschen Reitern. Angezeigt wird jetzt Deutsch,
 * die API-Werte (Filter, PATCH) bleiben unverändert.
 */
const get = vi.fn(async (url: string) => {
  if (url.startsWith('/admin/errors/summary')) return { data: { open: 2, ignored: 1, resolved: 3 } };
  return { data: [] };
});
vi.mock('../../api/client', () => ({ default: { get: (u: string) => get(u), patch: vi.fn() } }));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import ErrorMonitoring from './ErrorMonitoring';

describe('ErrorMonitoring: deutsche Statusnamen', () => {
  it('zeigt die Zähler mit deutschen Namen, nie die API-Werte', async () => {
    const { container } = render(<ErrorMonitoring />);
    expect(await screen.findByText('Offen: 2')).toBeInTheDocument();
    expect(screen.getByText('Ignoriert: 1')).toBeInTheDocument();
    expect(screen.getByText('Behoben: 3')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\b(open|ignored|resolved):/);
  });

  it('der Filter fragt weiterhin mit dem API-Wert', async () => {
    render(<ErrorMonitoring />);
    await screen.findByText('Offen: 2');
    expect(get).toHaveBeenCalledWith('/admin/errors/?status=open');
  });
});
