import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { format } from 'date-fns';
import MonthlyJournal, { isJournalData } from './MonthlyJournal';

// #382: clicking a user opens the journal. A non-journal 200 body (e.g. an HTML
// login page returned in the auth-edge after a token_version-invalidated
// 401→refresh churn) used to reach `data.days.map` and throw → ErrorBoundary
// white-screen ("Etwas ist schiefgelaufen"). These tests pin the shape guard.

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}));
const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: toastError, success: toastSuccess, info: vi.fn(), warning: vi.fn() }),
}));
vi.mock('../api/absenceReasons', () => ({ myReasons: vi.fn().mockResolvedValue([]) }));

const validDay = {
  date: '2026-06-01',
  weekday: 'Mo',
  type: 'work' as const,
  is_holiday: false,
  holiday_name: null,
  time_entries: [],
  absences: [],
  actual_hours: 8,
  target_hours: 8,
  balance: 0,
};

const validJournal = {
  user: { id: 'u1', first_name: 'Test', last_name: 'User' },
  year: 2026,
  month: 6,
  days: [validDay],
  monthly_summary: { actual_hours: 8, target_hours: 8, balance: 0 },
  yearly_overtime: 0,
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  putMock.mockReset();
  deleteMock.mockReset();
  toastError.mockReset();
  toastSuccess.mockReset();
});

describe('isJournalData', () => {
  it('accepts a well-formed journal payload', () => {
    expect(isJournalData(validJournal)).toBe(true);
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['a string (HTML login page)', '<!doctype html><html>login</html>'],
    ['a number', 42],
    ['an empty object', {}],
    ['days not an array', { days: 'nope', monthly_summary: {}, yearly_overtime: 0 }],
    ['missing monthly_summary', { days: [], yearly_overtime: 0 }],
    ['missing yearly_overtime', { days: [], monthly_summary: {} }],
  ])('rejects %s', (_label, payload) => {
    expect(isJournalData(payload)).toBe(false);
  });
});

describe('<MonthlyJournal /> malformed-response hardening (#382)', () => {
  it('shows an error instead of crashing when the body is a non-journal object', async () => {
    getMock.mockResolvedValue({ data: {} }); // truthy but no .days
    render(<MonthlyJournal userId="u1" isAdminView />);
    await waitFor(() =>
      expect(screen.getByText(/Journal konnte nicht geladen werden/i)).toBeInTheDocument(),
    );
  });

  it('shows an error instead of crashing when the body is a string', async () => {
    getMock.mockResolvedValue({ data: '<!doctype html><html>login</html>' });
    render(<MonthlyJournal userId="u1" isAdminView />);
    await waitFor(() =>
      expect(screen.getByText(/Journal konnte nicht geladen werden/i)).toBeInTheDocument(),
    );
  });

  it('renders the table for a valid journal payload', async () => {
    getMock.mockImplementation((url: string) =>
      url.includes('/journal')
        ? Promise.resolve({ data: validJournal })
        : Promise.resolve({ data: [] }),
    );
    render(<MonthlyJournal userId="u1" isAdminView />);
    await waitFor(() => expect(screen.getByText('01.06.')).toBeInTheDocument());
  });

  it('does not crash when a day has a malformed date inside a valid payload', async () => {
    const journal = { ...validJournal, days: [{ ...validDay, date: 'not-a-date' }] };
    getMock.mockImplementation((url: string) =>
      url.includes('/journal')
        ? Promise.resolve({ data: journal })
        : Promise.resolve({ data: [] }),
    );
    render(<MonthlyJournal userId="u1" isAdminView />);
    // Renders the raw date fallback rather than throwing RangeError from format().
    await waitFor(() => expect(screen.getByText('not-a-date')).toBeInTheDocument());
  });

  it('#375: admin can add an entry/absence for TODAY (not only past days), future stays excluded', async () => {
    // Local calendar date (match the component's startOfDay(new Date()) notion of
    // "today"); toISOString() would be UTC and flake in the Berlin post-midnight window.
    const localToday = format(new Date(), 'yyyy-MM-dd');
    const past = { ...validDay, date: '2020-01-06', type: 'empty' as const };
    const today = { ...validDay, date: localToday, type: 'empty' as const };
    const future = { ...validDay, date: '2099-01-06', type: 'empty' as const };
    const journal = { ...validJournal, days: [past, today, future] };
    getMock.mockImplementation((url: string) =>
      url.includes('/journal')
        ? Promise.resolve({ data: journal })
        : Promise.resolve({ data: [] }),
    );
    const { unmount } = render(<MonthlyJournal userId="u1" isAdminView />);
    await waitFor(() =>
      expect(screen.getAllByTitle('Weiteren Eintrag hinzufügen').length).toBe(2),
    );
    // past + today offer the add "+", the future day does not.
    unmount();

    // Employee self-view stays past-only (today not editable — they use clock-in/out).
    render(<MonthlyJournal userId="u1" />);
    await waitFor(() =>
      expect(screen.getAllByTitle('Eintrag anlegen').length).toBe(1),
    );
  });

  it('does not crash when a day.date is null (date-fns v3 parseISO throws on non-string)', async () => {
    const journal = { ...validJournal, days: [{ ...validDay, date: null as unknown as string }] };
    getMock.mockImplementation((url: string) =>
      url.includes('/journal')
        ? Promise.resolve({ data: journal })
        : Promise.resolve({ data: [] }),
    );
    render(<MonthlyJournal userId="u1" isAdminView />);
    // Table still renders (aggregates present) instead of white-screening.
    await waitFor(() => expect(screen.getByText('Ist (Monat)')).toBeInTheDocument());
  });
});

// ---------------------------------------------------------------------------
// Audit 2026-07-31 / U1: ein Typwechsel im Journal darf den Eintrag nicht
// vernichten. Der Wechsel lief als ZWEI getrennt committende Aufrufe (erst
// DELETE, dann POST) — scheiterte der zweite Schritt, war der Datensatz weg,
// und der `catch`-Zweig lud weder neu noch verliess er den Bearbeitungsmodus.
// ---------------------------------------------------------------------------

const workDay = {
  ...validDay,
  date: '2026-06-09',
  type: 'work' as const,
  time_entries: [
    { id: 'te1', start_time: '09:00', end_time: '17:00', break_minutes: 30, net_hours: 7.5 },
  ],
  absences: [],
};

function mockJournal(days: unknown[]) {
  getMock.mockImplementation((url: string) =>
    url.includes('/journal')
      ? Promise.resolve({ data: { ...validJournal, days } })
      : Promise.resolve({ data: [] }),
  );
}

async function openTypeSwitch(entryTitle = '09:00–17:00 bearbeiten', to = 'sick') {
  await waitFor(() => expect(screen.getByTitle(entryTitle)).toBeInTheDocument());
  fireEvent.click(screen.getByTitle(entryTitle));
  const select = await screen.findByDisplayValue('Arbeit');
  fireEvent.change(select, { target: { value: to } });
  fireEvent.click(screen.getByTitle('Speichern'));
}

describe('<MonthlyJournal /> Typwechsel (U1, Audit 2026-07-31)', () => {
  it('verliert den Zeiteintrag nicht, wenn das Anlegen der Abwesenheit scheitert', async () => {
    mockJournal([workDay]);
    postMock.mockRejectedValue({
      response: { status: 400, data: { detail: 'Datum liegt vor dem ersten Arbeitstag' } },
    });

    render(<MonthlyJournal userId="u1" isAdminView />);
    await openTypeSwitch();

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    // Der Zeiteintrag darf NICHT vorab geloescht worden sein.
    expect(deleteMock).not.toHaveBeenCalledWith('/admin/time-entries/te1');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('laedt nach einem Fehlschlag neu und verlaesst den Bearbeitungsmodus', async () => {
    mockJournal([workDay]);
    postMock.mockRejectedValue({ response: { status: 409, data: { detail: 'Konflikt' } } });

    render(<MonthlyJournal userId="u1" isAdminView />);
    const journalCalls = () =>
      getMock.mock.calls.filter(c => String(c[0]).includes('/journal')).length;
    await waitFor(() => expect(journalCalls()).toBe(1));

    await openTypeSwitch();

    await waitFor(() => expect(journalCalls()).toBe(2)); // Wahrheitsstand nachgeladen
    // Bearbeitungsmodus beendet -> der Typ-Auswahlkasten ist wieder weg.
    await waitFor(() => expect(screen.queryByTitle('Speichern')).not.toBeInTheDocument());
  });

  it('nutzt den atomaren Weg: kein clientseitiges DELETE, Server raeumt selbst auf', async () => {
    mockJournal([workDay]);
    postMock.mockResolvedValue({ data: [{ id: 'ab1', type: 'sick', hours: 8 }] });

    render(<MonthlyJournal userId="u1" isAdminView />);
    await openTypeSwitch();

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(deleteMock).not.toHaveBeenCalled();
    const [url, body] = postMock.mock.calls[0];
    expect(url).toBe('/absences');
    expect(body).toMatchObject({ type: 'sick', keep_time_entries: false });
  });

  it('wertet eine leere Antwort als Fehler, nicht als Erfolg', async () => {
    mockJournal([workDay]);
    postMock.mockResolvedValue({ data: [] }); // 200/201 ohne angelegte Zeile

    render(<MonthlyJournal userId="u1" isAdminView />);
    await openTypeSwitch();

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('prueft Pflichtfelder VOR dem Loeschen (Abwesenheit -> Arbeit ohne Zeiten)', async () => {
    const absenceDay = {
      ...validDay,
      date: '2026-06-10',
      type: 'sick' as const,
      time_entries: [],
      absences: [{ id: 'ab9', type: 'sick', hours: 8, start_time: null, end_time: null }],
    };
    mockJournal([absenceDay]);

    render(<MonthlyJournal userId="u1" isAdminView />);
    await waitFor(() => expect(screen.getByTitle('Krank bearbeiten')).toBeInTheDocument());
    fireEvent.click(screen.getByTitle('Krank bearbeiten'));
    // startEdit setzt entryType auf den Abwesenheitstyp; auf "Arbeit" wechseln,
    // ohne Von/Bis zu fuellen.
    const select = await screen.findByDisplayValue('Krank');
    fireEvent.change(select, { target: { value: 'work' } });
    fireEvent.click(screen.getByTitle('Speichern'));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(deleteMock).not.toHaveBeenCalled();
    expect(postMock).not.toHaveBeenCalled();
  });
});
