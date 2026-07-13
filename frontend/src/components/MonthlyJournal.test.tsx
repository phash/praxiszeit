import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { format } from 'date-fns';
import MonthlyJournal, { isJournalData } from './MonthlyJournal';

// #382: clicking a user opens the journal. A non-journal 200 body (e.g. an HTML
// login page returned in the auth-edge after a token_version-invalidated
// 401→refresh churn) used to reach `data.days.map` and throw → ErrorBoundary
// white-screen ("Etwas ist schiefgelaufen"). These tests pin the shape guard.

const getMock = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
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
