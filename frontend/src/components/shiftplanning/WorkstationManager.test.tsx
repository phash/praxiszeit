import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/shiftPlanning', () => ({
  updateWorkstation: vi.fn(),
  createWorkstation: vi.fn(),
  deleteWorkstation: vi.fn(),
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import * as api from '../../api/shiftPlanning';
import WorkstationManager from './WorkstationManager';
import type { Workstation } from '../../api/shiftPlanning';

const ws = (over: Partial<Workstation> = {}): Workstation => ({
  id: 'w1',
  name: 'Tresen',
  location_id: null,
  location_name: null,
  color: '#93C5FD',
  sort_order: 7,
  ...over,
} as Workstation);

describe('WorkstationManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.updateWorkstation as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  // #461 K-3: `PUT /workstations/{id}` ist serverseitig ein Vollersatz und setzt
  // `ws.sort_order = data.sort_order`. Ein Rumpf, der das Feld nicht aufzählt,
  // schrieb bei JEDEM Speichern still 0 zurück — und seit #452 bestimmt genau
  // dieses Feld die Zeilenreihenfolge des PDF-Aushangs. Ein Arbeitsplatz
  // umzubenennen warf also die Reihenfolge des Ausdrucks um.
  it('behält sort_order beim Bearbeiten bei', async () => {
    render(<WorkstationManager workstations={[ws()]} locations={[]} onChanged={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Bearbeiten'));
    fireEvent.change(screen.getByDisplayValue('Tresen'), { target: { value: 'Tresen vorn' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/ }));

    await waitFor(() => expect(api.updateWorkstation).toHaveBeenCalled());
    const [id, body] = (api.updateWorkstation as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(id).toBe('w1');
    expect(body.name).toBe('Tresen vorn');
    expect(body.sort_order).toBe(7);
  });

  it('legt einen neuen Arbeitsplatz mit sort_order 0 an', async () => {
    (api.createWorkstation as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render(<WorkstationManager workstations={[]} locations={[]} onChanged={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: 'Labor' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/ }));

    await waitFor(() => expect(api.createWorkstation).toHaveBeenCalled());
    expect((api.createWorkstation as ReturnType<typeof vi.fn>).mock.calls[0][0].sort_order).toBe(0);
  });
});
