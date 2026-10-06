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

// #463: Bei fester Monatsarbeitszeit (#377 Baustein 2b) gibt es kein Tages-Soll.
// Die Tabelle zeigte trotzdem "Soll" und einen Tages-Saldo — Zahlen ohne
// definierte Bedeutung, aus denen der Melder auf einen Rechenfehler schloss.
// Zelltext einer Tageszeile unter der gegebenen Spaltenueberschrift.
function cellText(row: HTMLElement, header: string): string {
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent);
  const idx = headers.indexOf(header);
  if (idx < 0) throw new Error(`Spalte ${header} fehlt`);
  return (row.querySelectorAll('td')[idx]?.textContent ?? '').trim();
}

describe('<MonthlyJournal /> Stunden an Wochenend-/Feiertagen', () => {
  it('zeigt Ist und Saldo, wenn am Samstag gearbeitet wurde', async () => {
    const saturday = {
      ...validDay, date: '2026-06-06', weekday: 'Sa', type: 'weekend' as const,
      actual_hours: 3, target_hours: 0, balance: 3,
    };
    getMock.mockResolvedValue({ data: { ...validJournal, days: [saturday] } });
    render(<MonthlyJournal />);

    await screen.findByRole('columnheader', { name: 'Saldo' });
    const row = screen.getAllByRole('row')[1];
    expect(cellText(row, 'Ist')).toMatch(/^3/);
    expect(cellText(row, 'Saldo')).toMatch(/^\+3/);
    expect(cellText(row, 'Soll')).toBe('–');
  });

  it('zeigt Von–Bis und Pause des Samstagseintrags (Release-Review 1.19.2)', async () => {
    const saturday = {
      ...validDay, date: '2026-06-06', weekday: 'Sa', type: 'weekend' as const,
      time_entries: [{ id: 'e1', start_time: '08:00', end_time: '11:30', break_minutes: 30, net_hours: 3 }],
      actual_hours: 3, target_hours: 0, balance: 3,
    };
    getMock.mockResolvedValue({ data: { ...validJournal, days: [saturday] } });
    render(<MonthlyJournal />);

    await screen.findByRole('columnheader', { name: 'Saldo' });
    const row = screen.getAllByRole('row')[1];
    expect(cellText(row, 'Von–Bis')).toBe('08:00–11:30');
    expect(cellText(row, 'Pause')).toBe('30 min');
  });

  it('beschriftet den Samstagseintrag als "Arbeitszeit" (#479)', async () => {
    const saturday = {
      ...validDay, date: '2026-06-06', weekday: 'Sa', type: 'weekend' as const,
      time_entries: [{ id: 'e1', start_time: '08:00', end_time: '11:30', break_minutes: 30, net_hours: 3 }],
      actual_hours: 3, target_hours: 0, balance: 3,
    };
    getMock.mockResolvedValue({ data: { ...validJournal, days: [saturday] } });
    render(<MonthlyJournal />);

    await screen.findByRole('columnheader', { name: 'Saldo' });
    expect(cellText(screen.getAllByRole('row')[1], 'Typ')).toBe('Arbeitszeit');
  });
});

// #479: KV-Dienst am Sonntag. Die Aktionsspalte war an Wochenend- und
// Feiertagen gesperrt (`!isGray`) — weder die Admin noch die Mitarbeiterin
// konnten dort im Journal etwas eintragen, obwohl das Backend Wochenendarbeit
// annimmt (Admin direkt, MA per Aenderungsantrag).
describe('<MonthlyJournal /> Eintragen an Wochenend-/Feiertagen (#479)', () => {
  const sunday = {
    ...validDay, date: '2026-06-07', weekday: 'So', type: 'weekend' as const,
    actual_hours: 0, target_hours: 0, balance: 0,
  };
  const holiday = {
    ...validDay, date: '2026-06-04', weekday: 'Do', type: 'holiday' as const,
    is_holiday: true, holiday_name: 'Fronleichnam',
    actual_hours: 0, target_hours: 0, balance: 0,
  };

  it('Admin kann am vergangenen Sonntag einen Eintrag hinzufuegen', async () => {
    mockJournal([sunday]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    expect(await screen.findByTitle('Weiteren Eintrag hinzufügen')).toBeInTheDocument();
  });

  it('Admin kann am vergangenen Feiertag einen Eintrag hinzufuegen', async () => {
    mockJournal([holiday]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    expect(await screen.findByTitle('Weiteren Eintrag hinzufügen')).toBeInTheDocument();
  });

  it('Admin kann einen bestehenden Sonntagseintrag bearbeiten', async () => {
    mockJournal([{
      ...sunday,
      time_entries: [{ id: 'e1', start_time: '09:00', end_time: '16:00', break_minutes: 0, net_hours: 7 }],
      actual_hours: 7, balance: 7,
    }]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    expect(await screen.findByTitle('09:00–16:00 bearbeiten')).toBeInTheDocument();
  });

  it('Mitarbeiterin kann fuer den vergangenen Sonntag einen Antrag anlegen', async () => {
    mockJournal([sunday]);
    render(<MonthlyJournal />);
    expect(await screen.findByTitle('Eintrag anlegen')).toBeInTheDocument();
  });

  it('Mitarbeiterin reicht den Sonntagsdienst als Aenderungsantrag ein', async () => {
    mockJournal([sunday]);
    postMock.mockResolvedValue({ data: {} });
    const { container } = render(<MonthlyJournal />);
    fireEvent.click(await screen.findByTitle('Eintrag anlegen'));

    // Von/Bis muessen auch in einer grauen Zeile ohne Eintrag erscheinen.
    const [von, bis] = Array.from(container.querySelectorAll('input[type="time"]'));
    expect(von).toBeDefined();
    fireEvent.change(von, { target: { value: '09:00' } });
    fireEvent.change(bis, { target: { value: '16:00' } });
    fireEvent.click(screen.getByTitle('Speichern'));
    fireEvent.change(screen.getByPlaceholderText('Begründung eingeben (Pflicht)'), {
      target: { value: 'KV-Dienst' },
    });
    fireEvent.click(screen.getByText('Absenden'));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/change-requests/', expect.objectContaining({
      request_type: 'create',
      entry_kind: 'time_entry',
      proposed_date: '2026-06-07',
      proposed_start_time: '09:00',
      proposed_end_time: '16:00',
    })));
  });

  it('ein kuenftiger Sonntag bleibt ohne Aktion', async () => {
    mockJournal([{ ...sunday, date: '2099-06-07' }]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    await screen.findByRole('columnheader', { name: 'Saldo' });
    expect(screen.queryByTitle('Weiteren Eintrag hinzufügen')).toBeNull();
  });

  // Release-Review 1.19.2: der Admin-Direktweg bucht an Wochenend-/Feiertagen
  // keine Abwesenheit (create_absence filtert sie) — vorher loeschte das
  // Journal die alte Abwesenheit bzw. den Zeiteintrag VOR dem 400.
  it('Speichern einer Wochenend-Abwesenheit loescht sie nicht', async () => {
    mockJournal([{
      ...sunday,
      absences: [{ id: 'ab1', type: 'sick', hours: 8, start_time: null, end_time: null }],
    }]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('Krank bearbeiten'));
    fireEvent.click(screen.getByTitle('Speichern'));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(deleteMock).not.toHaveBeenCalled();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('bietet an Wochenend-/Feiertagen fuer einen Zeiteintrag keine Abwesenheitstypen an', async () => {
    mockJournal([{
      ...sunday,
      time_entries: [
        { id: 'e1', start_time: '08:00', end_time: '12:00', break_minutes: 0, net_hours: 4 },
        { id: 'e2', start_time: '18:00', end_time: '22:00', break_minutes: 0, net_hours: 4 },
      ],
      actual_hours: 8, balance: 8,
    }]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('18:00–22:00 bearbeiten'));
    const select = await screen.findByDisplayValue('Arbeit');
    expect(Array.from((select as HTMLSelectElement).options).map(o => o.value)).toEqual(['work']);
  });

  it('Mitarbeiterin beantragt die Loeschung des bearbeiteten, nicht des ersten Eintrags', async () => {
    mockJournal([{
      ...sunday,
      time_entries: [
        { id: 'e1', start_time: '08:00', end_time: '12:00', break_minutes: 0, net_hours: 4 },
        { id: 'e2', start_time: '18:00', end_time: '22:00', break_minutes: 0, net_hours: 4 },
      ],
      actual_hours: 8, balance: 8,
    }]);
    postMock.mockResolvedValue({ data: {} });
    render(<MonthlyJournal />);
    fireEvent.click(await screen.findByTitle('18:00–22:00 bearbeiten'));
    fireEvent.click(screen.getByTitle('Löschen'));
    fireEvent.click(await screen.findByText('Antrag stellen'));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/change-requests/', expect.objectContaining({
      request_type: 'delete', time_entry_id: 'e2',
    })));
  });
});

// Release-Review 1.19.2 (vorbestehend, seit #479 auch an Wochenenden): auf einem
// Misch-Tag hielt der Speicherpfad das Bearbeiten des Zeiteintrags fuer einen
// Wechsel Abwesenheit -> Arbeit — er legte einen ZWEITEN Eintrag an und loeschte
// die Abwesenheit.
describe('<MonthlyJournal /> Misch-Tag bearbeiten', () => {
  it('aendert den Zeiteintrag per PUT und laesst die Abwesenheit stehen', async () => {
    mockJournal([{
      ...validDay,
      date: '2026-06-10',
      type: 'mixed' as const,
      time_entries: [{ id: 'te1', start_time: '08:00', end_time: '12:00', break_minutes: 0, net_hours: 4 }],
      absences: [{ id: 'ab1', type: 'vacation', hours: 4, start_time: null, end_time: null }],
    }]);
    putMock.mockResolvedValue({ data: {} });
    const { container } = render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('08:00–12:00 bearbeiten'));
    const [, bis] = Array.from(container.querySelectorAll('input[type="time"]'));
    fireEvent.change(bis, { target: { value: '12:30' } });
    fireEvent.click(screen.getByTitle('Speichern'));

    await waitFor(() => expect(putMock).toHaveBeenCalledWith(
      '/admin/time-entries/te1', expect.objectContaining({ end_time: '12:30' }),
    ));
    expect(postMock).not.toHaveBeenCalled();
    expect(deleteMock).not.toHaveBeenCalled();
  });
});

describe('<MonthlyJournal /> feste Monatsarbeitszeit (#463)', () => {
  const fixedJournal = { ...validJournal, use_fixed_monthly_target: true };

  it('beschriftet die Spalte als "Geplant" und laesst den Tages-Saldo weg', async () => {
    getMock.mockResolvedValue({ data: fixedJournal });
    render(<MonthlyJournal />);

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Geplant' })).toBeInTheDocument());
    expect(screen.queryByRole('columnheader', { name: 'Soll' })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Saldo' })).not.toBeInTheDocument();
  });

  it('erklaert, dass die Monatsuebersicht verbindlich ist', async () => {
    getMock.mockResolvedValue({ data: fixedJournal });
    render(<MonthlyJournal />);

    await waitFor(() => expect(screen.getByText(/Feste Monatsarbeitszeit aktiv/)).toBeInTheDocument());
    expect(screen.getByText(/Monatsübersicht/)).toBeInTheDocument();
  });

  it('laesst die normale Ansicht unveraendert', async () => {
    getMock.mockResolvedValue({ data: validJournal });
    render(<MonthlyJournal />);

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Soll' })).toBeInTheDocument());
    expect(screen.getByRole('columnheader', { name: 'Saldo' })).toBeInTheDocument();
    expect(screen.queryByText(/Feste Monatsarbeitszeit aktiv/)).not.toBeInTheDocument();
  });

  // Tracker-Nachtrag zu 2d75bbe4: das Backend schreibt einem Feiertag auf
  // einem geplanten Tag die Planstunden gut (Geplant + Ist), die Tageszeile
  // blendete an Wochenend-/Feiertagen aber jede Zahl pauschal aus.
  it('zeigt an einem Feiertag die gutgeschriebenen Planstunden', async () => {
    const holiday = {
      ...validDay, date: '2026-06-04', type: 'holiday' as const,
      is_holiday: true, holiday_name: 'Fronleichnam',
      actual_hours: 6, target_hours: 6, balance: 0,
    };
    getMock.mockResolvedValue({ data: { ...fixedJournal, days: [holiday] } });
    render(<MonthlyJournal />);

    const row = (await screen.findByText('Fronleichnam')).closest('tr')!;
    expect(cellText(row, 'Ist')).toMatch(/^6/);
    expect(cellText(row, 'Geplant')).toMatch(/^6/);
  });

  it('laesst einen Feiertag ohne Stunden leer', async () => {
    const holiday = {
      ...validDay, date: '2026-06-04', type: 'holiday' as const,
      is_holiday: true, holiday_name: 'Fronleichnam',
      actual_hours: 0, target_hours: 0, balance: 0,
    };
    getMock.mockResolvedValue({ data: { ...fixedJournal, days: [holiday] } });
    render(<MonthlyJournal />);

    const row = (await screen.findByText('Fronleichnam')).closest('tr')!;
    expect(cellText(row, 'Ist')).toBe('');
    expect(cellText(row, 'Geplant')).toBe('');
  });

  it('faellt ohne das Feld auf die normale Ansicht zurueck (aeltere Antwort)', async () => {
    getMock.mockResolvedValue({ data: { ...validJournal, use_fixed_monthly_target: undefined } });
    render(<MonthlyJournal />);

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Soll' })).toBeInTheDocument());
  });
});

describe('<MonthlyJournal /> §10-Ausnahmegrund (#485)', () => {
  const sunday = {
    ...validDay, date: '2026-06-07', weekday: 'So', type: 'weekend' as const,
    actual_hours: 0, target_hours: 0, balance: 0,
  };
  const saturday = { ...sunday, date: '2026-06-06', weekday: 'Sa' };
  const holiday = {
    ...validDay, date: '2026-06-04', weekday: 'Do', type: 'holiday' as const,
    is_holiday: true, holiday_name: 'Fronleichnam',
    actual_hours: 0, target_hours: 0, balance: 0,
  };
  const label = 'Ausnahmegrund (§10 ArbZG)';

  it('Admin traegt am Sonntag einen Eintrag mit Ausnahmegrund ein', async () => {
    mockJournal([sunday]);
    postMock.mockResolvedValue({ data: { warnings: [] } });
    const { container } = render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('Weiteren Eintrag hinzufügen'));
    const [von, bis] = Array.from(container.querySelectorAll('input[type="time"]'));
    fireEvent.change(von, { target: { value: '09:00' } });
    fireEvent.change(bis, { target: { value: '13:00' } });
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'KV-Notdienst' } });
    fireEvent.click(screen.getByTitle('Hinzufügen'));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/admin/users/u1/time-entries',
      expect.objectContaining({ date: '2026-06-07', sunday_exception_reason: 'KV-Notdienst' }),
    ));
  });

  it('Bearbeiten belegt den gespeicherten Grund vor und schickt ihn mit', async () => {
    mockJournal([{
      ...sunday,
      time_entries: [{ id: 'e1', start_time: '09:00', end_time: '13:00', break_minutes: 0,
        net_hours: 4, sunday_exception_reason: 'Notdienst' }],
      actual_hours: 4, balance: 4,
    }]);
    putMock.mockResolvedValue({ data: { warnings: [] } });
    render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('09:00–13:00 bearbeiten'));
    expect(screen.getByLabelText(label)).toHaveValue('Notdienst');
    fireEvent.click(screen.getByTitle('Speichern'));

    await waitFor(() => expect(putMock).toHaveBeenCalledWith(
      '/admin/time-entries/e1',
      expect.objectContaining({ sunday_exception_reason: 'Notdienst' }),
    ));
  });

  it('Mitarbeiterin beantragt Feiertagsarbeit mit Ausnahmegrund', async () => {
    mockJournal([holiday]);
    postMock.mockResolvedValue({ data: {} });
    const { container } = render(<MonthlyJournal />);
    fireEvent.click(await screen.findByTitle('Eintrag anlegen'));
    const [von, bis] = Array.from(container.querySelectorAll('input[type="time"]'));
    fireEvent.change(von, { target: { value: '09:00' } });
    fireEvent.change(bis, { target: { value: '13:00' } });
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'Notdienst' } });
    fireEvent.click(screen.getByTitle('Speichern'));
    fireEvent.change(screen.getByPlaceholderText('Begründung eingeben (Pflicht)'), {
      target: { value: 'Dienst nachgetragen' },
    });
    fireEvent.click(screen.getByText('Absenden'));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/change-requests/', expect.objectContaining({
      proposed_date: '2026-06-04',
      proposed_sunday_exception_reason: 'Notdienst',
    })));
  });

  it('fragt am Samstag (kein Feiertag) nicht nach einem Ausnahmegrund', async () => {
    mockJournal([saturday]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    fireEvent.click(await screen.findByTitle('Weiteren Eintrag hinzufügen'));
    expect(screen.queryByLabelText(label)).toBeNull();
  });

  it('zeigt einen gespeicherten Grund und den Rohstempel in der Zeile', async () => {
    mockJournal([{
      ...sunday,
      time_entries: [{ id: 'e1', start_time: '09:00', end_time: '13:00', break_minutes: 0,
        net_hours: 4, sunday_exception_reason: 'KV-Notdienst', raw_start_time: '08:52' }],
      actual_hours: 4, balance: 4,
    }]);
    render(<MonthlyJournal userId="u1" isAdminView />);
    expect(await screen.findByText('§10: KV-Notdienst')).toBeInTheDocument();
    expect(screen.getByText(/gestempelt 08:52/)).toBeInTheDocument();
  });
});
