import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../../../contexts/ToastContext';
import { useSystemStore } from '../../../stores/systemStore';
import UserForm from './UserForm';

// carryover-fetch (nur im Edit-Modus) neutralisieren
vi.mock('../../../api/client', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn(), put: vi.fn() },
}));

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
});
