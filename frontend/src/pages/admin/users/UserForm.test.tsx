import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../../../contexts/ToastContext';
import { useSystemStore } from '../../../stores/systemStore';
import UserForm from './UserForm';

// Exposed mocks so #383 tests can configure the /carryovers fetch and assert on
// the PUT. Defaults keep the existing tests' carryover-useEffect a no-op.
const getMock = vi.fn();
const putMock = vi.fn();
const postMock = vi.fn();
vi.mock('../../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));

beforeEach(() => {
  getMock.mockReset().mockResolvedValue({ data: [] });
  putMock.mockReset().mockResolvedValue({ data: {} });
  postMock.mockReset().mockResolvedValue({ data: { user: { id: 'new-user-1' } } });
});

function renderForm(props: Record<string, unknown> = {}) {
  return render(
    <ToastProvider>
      <UserForm onSaved={() => {}} {...props} />
    </ToastProvider>,
  );
}

describe('#377 UserForm MiLoG checkbox', () => {
  beforeEach(() => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', minimum_wage: { current: 13.9, since: '2026-01-01', next: null } },
      isLoaded: true,
    } as never);
  });

  it('renders the Arbeitszeitkonto checkbox (unchecked by default)', () => {
    renderForm();
    const cb = screen.getByLabelText(/Arbeitszeitkonto/i) as HTMLInputElement;
    expect(cb).toBeInTheDocument();
    expect(cb.checked).toBe(false);
  });

  it('shows the derived Mindestlohn/cap info line once enabled', () => {
    renderForm();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    // Default weekly_hours 40 → Monatszeit ≈ 173.3 h → Cap ≈ 86.7 h; Mindestlohn 13,90
    expect(screen.getByText(/13\.90 €\/h/)).toBeInTheDocument();
    expect(screen.getByText(/max\. Konto/)).toBeInTheDocument();
  });

  it('#382: does not crash if minimum_wage is present but has no numeric current', () => {
    // A malformed /system/info minimum_wage object used to throw
    // `minWage.current.toFixed(2)` → ErrorBoundary white-screen for milog users.
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', minimum_wage: {} },
      isLoaded: true,
    } as never);
    renderForm();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    // Renders the rest of the info line; the Mindestlohn prefix is simply omitted.
    expect(screen.getByText(/max\. Konto/)).toBeInTheDocument();
    expect(screen.queryByText(/Aktueller Mindestlohn/)).not.toBeInTheDocument();
  });

  it('prefills the checkbox from editUser', () => {
    renderForm({
      editUser: {
        id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
        weekly_hours: 7.62, vacation_days: 30, work_days_per_week: 5, track_hours: true,
        is_active: true, milog_working_time_account: true,
      },
    });
    expect((screen.getByLabelText(/Arbeitszeitkonto/i) as HTMLInputElement).checked).toBe(true);
  });

  it('#377 2a: shows the monthly-hours field only when the account flag is on', () => {
    renderForm();
    expect(screen.queryByLabelText(/Vereinbarte Monatsarbeitszeit/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/i));
    expect(screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/i)).toBeInTheDocument();
  });

  it('#377 2a: prefills agreed_monthly_hours from editUser', () => {
    renderForm({
      editUser: {
        id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
        weekly_hours: 20, vacation_days: 30, work_days_per_week: 5, track_hours: true,
        is_active: true, milog_working_time_account: true, agreed_monthly_hours: 33,
      },
    });
    expect((screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/i) as HTMLInputElement).value).toBe('33');
  });

  it('#377 2a: sends agreed_monthly_hours in the update payload', async () => {
    getMock.mockResolvedValue({ data: [] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={{
          id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
          weekly_hours: 20, vacation_days: 30, work_days_per_week: 5, track_hours: true,
          is_active: true, milog_working_time_account: true, agreed_monthly_hours: 33,
        } as never} />
      </ToastProvider>,
    );
    const field = screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/i);
    fireEvent.change(field, { target: { value: '40' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => /\/admin\/users\/u1$/.test(String(c[0])));
      expect(call).toBeTruthy();
      expect(call![1]).toMatchObject({ agreed_monthly_hours: 40 });
    });
  });
});

describe('#383 Übertrag Urlaubstage', () => {
  const editUser2026 = {
    id: 'u1', username: 'mj', first_name: 'M', last_name: 'J', role: 'employee',
    weekly_hours: 40, vacation_days: 30, work_days_per_week: 5, track_hours: true,
    is_active: true, first_work_day: '2026-06-01',
  };

  it('renders the field and prefills it from the start-year vacation_days carryover', async () => {
    getMock.mockResolvedValue({ data: [{ year: 2026, overtime_hours: 5, vacation_days: 8 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('8'));
  });

  it('saves the field value to /carryovers/{startYear} as vacation_days', async () => {
    getMock.mockResolvedValue({ data: [{ year: 2026, overtime_hours: 5, vacation_days: 8 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('8'));
    fireEvent.change(field, { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
      expect(call).toBeTruthy();
      expect(String(call![0])).toContain('/carryovers/2026');
      expect(call![1]).toMatchObject({ vacation_days: 10 });
    });
  });

  it('falls back to the current year when first_work_day is unset', async () => {
    const y = new Date().getFullYear();
    getMock.mockResolvedValue({ data: [{ year: y, overtime_hours: 0, vacation_days: 2 }] });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={{ ...editUser2026, first_work_day: undefined } as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe('2')); // loaded for current year
    fireEvent.change(field, { target: { value: '3.5' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => {
      const call = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
      expect(call).toBeTruthy();
      expect(String(call![0])).toContain(`/carryovers/${y}`);
      expect(call![1]).toMatchObject({ vacation_days: 3.5 });
    });
  });

  it('does not write a carryover when the prefill load failed (no clobber of an unknown value)', async () => {
    getMock.mockRejectedValue(new Error('network')); // /carryovers GET fails
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const field = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    fireEvent.change(field, { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(putMock).toHaveBeenCalled()); // the user PUT
    // loadedCarryoverYear stayed null → carryover write is suppressed …
    expect(putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'))).toBeUndefined();
    // … and the admin is warned (not silently told "erfolgreich").
    await waitFor(() =>
      expect(screen.getByText(/konnte nicht geladen werden und wurde NICHT gesetzt/i)).toBeInTheDocument(),
    );
  });

  it('re-prefills the carryover from the NEW start year when first_work_day is changed across a year (M-C1: no clobber)', async () => {
    getMock.mockResolvedValue({
      data: [
        { year: 2026, overtime_hours: 5, vacation_days: 8 },
        { year: 2027, overtime_hours: 9, vacation_days: 12 },
      ],
    });
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    const vac = await screen.findByLabelText(/Übertrag Urlaubstage/i);
    await waitFor(() => expect((vac as HTMLInputElement).value).toBe('8')); // 2026 row
    // Move first_work_day into 2027 → the field must reflect 2027's own carryover
    // (12), NOT copy 2026's value (8) into 2027 on save.
    fireEvent.change(screen.getByDisplayValue('2026-06-01'), { target: { value: '2027-03-01' } });
    await waitFor(() => expect((vac as HTMLInputElement).value).toBe('12'));
  });

  it('writes NO carryover row for an untouched user (both values 0, none existing)', async () => {
    getMock.mockResolvedValue({ data: [] }); // no existing carryover
    render(
      <ToastProvider>
        <UserForm onSaved={() => {}} editUser={editUser2026 as never} />
      </ToastProvider>,
    );
    await screen.findByLabelText(/Übertrag Urlaubstage/i);
    fireEvent.click(screen.getByRole('button', { name: /Speichern/i }));
    await waitFor(() => expect(putMock).toHaveBeenCalled()); // the user PUT itself
    const carryoverCall = putMock.mock.calls.find((c) => String(c[0]).includes('/carryovers/'));
    expect(carryoverCall).toBeUndefined();
  });
});
