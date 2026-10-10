import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Settings from './Settings';

// #499: Admin-Schalter „Ausnahme ‚Pflicht-Pause war nicht möglich' erlauben".
// Default an; aus → Genehmigungs-Schalter ausgeblendet, gespeichert wird
// `break_exception_allowed`, danach lädt der systemStore neu.

const getMock = vi.fn();
const putMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));
vi.mock('../../components/AbsenceReasonsManager', () => ({ default: () => null }));

function mockSettings(rows: { key: string; value: string }[]) {
  getMock.mockImplementation((url: string) => {
    if (url === '/holidays/states') return Promise.resolve({ data: { states: [], current_state: 'BY' } });
    if (url === '/admin/settings') return Promise.resolve({ data: rows });
    if (url === '/admin/settings/special-days') {
      return Promise.resolve({
        data: {
          special_day_dec24_mode: 'working_day',
          special_day_dec24_counts_as_vacation: false,
          special_day_dec31_mode: 'working_day',
          special_day_dec31_counts_as_vacation: false,
        },
      });
    }
    if (url === '/admin/settings/type-colors') return Promise.resolve({ data: {} });
    if (url === '/system/info') return Promise.resolve({ data: { deployment_mode: 'onprem', version: '' } });
    return Promise.resolve({ data: [] });
  });
}

const SWITCH = /Ausnahme „Pflicht-Pause war nicht möglich“ erlauben/;

beforeEach(() => {
  getMock.mockReset();
  putMock.mockReset();
  putMock.mockResolvedValue({ data: {} });
});

describe('<Settings /> Pflicht-Pause-Ausnahme an/aus (#499)', () => {
  it('zeigt den Schalter standardmäßig an und den Genehmigungs-Schalter darunter', async () => {
    mockSettings([]);
    render(<Settings />);
    const toggle = await screen.findByRole('switch', { name: SWITCH });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(document.getElementById('break-approval-toggle')).toBeInTheDocument();
  });

  it('liest „false" und blendet den Genehmigungs-Schalter aus', async () => {
    mockSettings([{ key: 'break_exception_allowed', value: 'false' }]);
    render(<Settings />);
    const toggle = await screen.findByRole('switch', { name: SWITCH });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'));
    expect(document.getElementById('break-approval-toggle')).not.toBeInTheDocument();
  });

  it('speichert das Abschalten unter break_exception_allowed und lädt system/info neu', async () => {
    mockSettings([]);
    render(<Settings />);
    const toggle = await screen.findByRole('switch', { name: SWITCH });
    fireEvent.click(toggle);

    const card = toggle.closest('div.bg-white') as HTMLElement;
    fireEvent.click(card.querySelector('button:not([role="switch"])') as HTMLElement);

    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith('/admin/settings/break_exception_allowed', { value: 'false' }),
    );
    expect(putMock).not.toHaveBeenCalledWith('/admin/settings/break_exception_requires_approval', expect.anything());
    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/system/info'));
  });
});

describe('<Settings /> Puffer-Hinweis (Spec 2026-10-08, 12.3)', () => {
  it('nennt die Blockränder und dass Einträge ihren Puffer behalten', async () => {
    mockSettings([]);
    render(<Settings />);
    expect(await screen.findByText(
      /gilt an jedem Blockrand, auch zwischen zwei Blöcken; eine Lücke bis zum doppelten Puffer wird angerechnet/,
    )).toBeInTheDocument();
    expect(screen.getByText(/^Eine Änderung des Puffers wirkt auf neue Einträge\./)).toBeInTheDocument();
    expect(screen.getByText(
      /Bereits gespeicherte Einträge ändern sich durch das Speichern dieser Einstellung allein nicht\.$/,
    )).toBeInTheDocument();
  });
});
