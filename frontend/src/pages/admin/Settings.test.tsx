import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Settings from './Settings';

// #499: Admin-Schalter „Ausnahme ‚Pflicht-Pause war nicht möglich' erlauben".
// Default an; aus → Genehmigungs-Schalter ausgeblendet, gespeichert wird
// `break_exception_allowed`, danach lädt der systemStore neu.

const getMock = vi.fn();
const putMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: vi.fn(),
  },
}));
// Stabile Referenz: Tests prüfen die Hinweise (Bundesland-Wechsel), und eine
// je Render neue Toast-Instanz wäre als Effekt-Abhängigkeit eine Ladeschleife.
const toastMock = vi.hoisted(() => ({
  error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn(),
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => toastMock,
}));
vi.mock('../../components/AbsenceReasonsManager', () => ({ default: () => null }));

function mockSettings(rows: { key: string; value: string }[]) {
  getMock.mockImplementation((url: string) => {
    if (url === '/holidays/states') {
      return Promise.resolve({ data: { states: ['Bayern', 'Berlin'], current_state: 'Bayern' } });
    }
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
  postMock.mockReset();
  Object.values(toastMock).forEach((fn) => fn.mockReset());
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

  // Gesamtreview 1.20 (Fund 11): Obergrenze wie im Backend (ein ganzer Tag).
  it('begrenzt das Puffer-Feld auf 0 bis 1439 Minuten', async () => {
    mockSettings([]);
    render(<Settings />);
    const input = await screen.findByLabelText('Puffer für Soll-Arbeitszeit-Fenster (Min.)');
    expect(input).toHaveAttribute('min', '0');
    expect(input).toHaveAttribute('max', '1439');
  });
});

describe('<Settings /> Bundesland-Wechsel (Gesamtreview 1.20 B9)', () => {
  async function switchToBerlin() {
    const select = (await screen.findByLabelText('Bundesland')) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('Bayern'));
    fireEvent.change(select, { target: { value: 'Berlin' } });
    const card = select.closest('div.bg-white') as HTMLElement;
    fireEvent.click(card.querySelector('button') as HTMLElement);
    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith('/admin/settings/holiday_state', { value: 'Berlin' }),
    );
  }

  it('nennt im Hinweistext auch die zurückliegenden Jahre', async () => {
    mockSettings([]);
    render(<Settings />);
    expect(await screen.findByText(
      /werden die gesetzlichen Feiertage aller Jahre automatisch neu berechnet, auch zurückliegender/,
    )).toBeInTheDocument();
  });

  it('zeigt den Hinweis auf ein abgeschlossenes Jahr aus der Antwort', async () => {
    mockSettings([]);
    const warning = 'Jahresabschluss 2025 bereits erfolgt — Carryover 2026 ist nun veraltet, bitte Jahresabschluss erneut ausführen.';
    putMock.mockResolvedValue({ data: { key: 'holiday_state', value: 'Berlin', warning } });
    render(<Settings />);
    await switchToBerlin();
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith(
      'Bundesland aktualisiert. Feiertage wurden neu berechnet.',
    ));
    expect(toastMock.warning).toHaveBeenCalledWith(warning);
  });

  it('zeigt ohne abgeschlossenes Jahr keinen Hinweis', async () => {
    mockSettings([]);
    putMock.mockResolvedValue({ data: { key: 'holiday_state', value: 'Berlin' } });
    render(<Settings />);
    await switchToBerlin();
    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
    expect(toastMock.warning).not.toHaveBeenCalled();
  });
});

describe('<Settings /> Eigener Feiertag im abgeschlossenen Jahr (Gesamtreview 1.20)', () => {
  it('zeigt nach dem Anlegen den Hinweis auf ein abgeschlossenes Jahr', async () => {
    mockSettings([]);
    const warning = 'Jahresabschluss 2025 bereits erfolgt — Carryover 2026 ist nun veraltet, bitte Jahresabschluss erneut ausführen.';
    postMock.mockResolvedValue({
      data: { id: 'h1', name: 'Schützenfest', date: '2025-08-15', year: 2025, is_custom: true, warning },
    });
    render(<Settings />);
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Schützenfest' } });
    fireEvent.change(screen.getByLabelText('Datum'), { target: { value: '2025-08-15' } });
    fireEvent.click(screen.getByRole('button', { name: /Hinzufügen/ }));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('Eigener Feiertag angelegt.'));
    expect(postMock).toHaveBeenCalledWith('/holidays/', { name: 'Schützenfest', date: '2025-08-15' });
    expect(toastMock.warning).toHaveBeenCalledWith(warning);
  });
});

describe('<Settings /> Sondertage im abgeschlossenen Jahr (Gesamtreview 1.20)', () => {
  it('zeigt den Hinweis aus der Antwort genau einmal', async () => {
    mockSettings([]);
    const warning = 'Jahresabschluss 2025 bereits erfolgt — Carryover 2026 ist nun veraltet, bitte Jahresabschluss erneut ausführen.';
    putMock.mockResolvedValue({ data: { key: 'special_day_dec24_mode', value: 'free', warning } });
    render(<Settings />);
    fireEvent.change(await screen.findByLabelText('Modus', { selector: '#special-dec24-mode' }), {
      target: { value: 'free' },
    });
    const card = screen.getByRole('heading', { name: 'Sondertage (24./31.12.)' }).parentElement!;
    fireEvent.click(within(card).getByRole('button', { name: /Speichern/ }));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('Sondertage (24./31.12.) gespeichert.'));
    expect(toastMock.warning).toHaveBeenCalledTimes(1);
    expect(toastMock.warning).toHaveBeenCalledWith(warning);
  });

  it('zeigt ohne abgeschlossenes Jahr keinen Hinweis', async () => {
    mockSettings([]);
    render(<Settings />);
    fireEvent.change(await screen.findByLabelText('Modus', { selector: '#special-dec31-mode' }), {
      target: { value: 'half_day' },
    });
    const card = screen.getByRole('heading', { name: 'Sondertage (24./31.12.)' }).parentElement!;
    fireEvent.click(within(card).getByRole('button', { name: /Speichern/ }));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('Sondertage (24./31.12.) gespeichert.'));
    expect(toastMock.warning).not.toHaveBeenCalled();
  });
});
