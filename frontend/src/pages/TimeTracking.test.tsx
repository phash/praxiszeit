import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { format } from 'date-fns';
import TimeTracking from './TimeTracking';

// ---------------------------------------------------------------------------
// U2 (Audit 2026-07-31): ein noch LAUFENDER Zeiteintrag (ohne Ende) galt als
// bearbeitbar (geprueft wurde nur „ist von heute"). Das Bearbeiten-Formular
// belegte „Bis" mit dem festen Wert '17:00' vor und schickte `end_time` immer
// mit — der laufende Eintrag wurde also stillschweigend auf 17:00 geschlossen.
// Stempelte die Person danach erneut ein, entstand eine zweite, ueberlappende
// Zeile (es gibt keine Ueberschneidungspruefung); wer lange arbeitet, lief in
// die §4-Pausenpruefung und bekam eine verwirrende Meldung.
// ---------------------------------------------------------------------------

const getMock = vi.fn();
const putMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({
    user: {
      id: 'u1', role: 'employee', weekly_hours: 40, work_days_per_week: 5,
      exempt_from_arbzg: false,
    },
  }),
}));
vi.mock('../stores/uiStore', () => ({ useUIStore: () => ({ stampVersion: 0 }) }));

const today = format(new Date(), 'yyyy-MM-dd');

const openEntry = {
  id: 'te-open',
  date: today,
  start_time: '08:00:00',
  end_time: null,
  break_minutes: 0,
  net_hours: 0,
  note: '',
  is_editable: true,
  warnings: [],
  is_sunday_or_holiday: false,
  is_night_work: false,
};

const closedEntry = {
  ...openEntry,
  id: 'te-closed',
  end_time: '16:00:00',
  break_minutes: 30,
  net_hours: 7.5,
};

function mockEntries(entries: unknown[]) {
  getMock.mockImplementation((url: string) => {
    if (url.includes('/settings')) return Promise.resolve({ data: {} });
    if (url.includes('/time-entries')) return Promise.resolve({ data: entries });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TimeTracking />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  putMock.mockReset();
  postMock.mockReset();
  deleteMock.mockReset();
  putMock.mockResolvedValue({ status: 200, data: { ...openEntry, warnings: [] } });
});

describe('<TimeTracking /> laufender Eintrag (U2, Audit 2026-07-31)', () => {
  it('belegt „Bis" beim Bearbeiten eines laufenden Eintrags NICHT mit 17:00 vor', async () => {
    mockEntries([openEntry]);
    renderPage();

    const editBtn = await screen.findByLabelText(/bearbeiten/i);
    fireEvent.click(editBtn);

    const end = screen.getByLabelText('Bis') as HTMLInputElement;
    expect(end.value).toBe('');
    expect(end.required).toBe(false);
  });

  it('schickt `end_time` nicht mit, wenn der Eintrag noch laeuft', async () => {
    mockEntries([openEntry]);
    renderPage();

    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    fireEvent.change(screen.getByLabelText('Notiz'), { target: { value: 'Nachtrag' } });
    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);

    await waitFor(() => expect(putMock).toHaveBeenCalled());
    const [url, payload] = putMock.mock.calls[0];
    expect(url).toBe('/time-entries/te-open');
    expect(payload).not.toHaveProperty('end_time');
    expect(payload).toMatchObject({ note: 'Nachtrag', start_time: '08:00' });
  });

  it('Kontrolltest: ein geschlossener Eintrag wird unveraendert mit `end_time` gespeichert', async () => {
    mockEntries([closedEntry]);
    renderPage();

    fireEvent.click(await screen.findByLabelText(/bearbeiten/i));
    const end = screen.getByLabelText('Bis') as HTMLInputElement;
    expect(end.value).toBe('16:00');
    expect(end.required).toBe(true);

    fireEvent.submit(document.getElementById('time-entry-form') as HTMLFormElement);
    await waitFor(() => expect(putMock).toHaveBeenCalled());
    expect(putMock.mock.calls[0][1]).toMatchObject({
      start_time: '08:00', end_time: '16:00', break_minutes: 30,
    });
  });
});
