import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ToastProvider } from '../../contexts/ToastContext';
import Users from './Users';
import type { User } from '../../types/user';

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const deleteMock = vi.fn();
vi.mock('../../api/client', () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
  // authStore.ts (imported transitively via useAuthStore) pulls these named
  // exports in — never invoked in this test, but the mock module must expose
  // them so the import itself doesn't blow up.
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

// Release-Review 1.17.0 (Fund 2, MEDIUM): this test targets Users.tsx's OWN
// orchestration (fetchUsers / editingUser state) — NOT UserForm's or
// WorkingHoursModal's internals, which have their own dedicated test files.
// The fake UserForm reproduces the ONE behavior that actually caused the
// regression: the real UserForm resets its formData wholesale in
// `useEffect(..., [editUser])` (UserForm.tsx:82-126) whenever it receives a
// NEW `editUser` OBJECT REFERENCE — even for the very same user id. A PR #423
// effect in Users.tsx (removed by this fix) replaced `editingUser` with a
// fresh object from `users` after every fetchUsers(), which fires WHILE the
// form is still open (e.g. the Wochenstunden-/Carryover-Dialogs' onChanged).
// If Users.tsx ever again hands UserForm a new reference after such a
// background refetch, this fake fails exactly like the real component did.
// Named (capitalized) function components, not anonymous arrows assigned to
// `default` — react-hooks/rules-of-hooks identifies hook-eligible functions by
// name (PascalCase or `use*`); an anonymous `default: (props) => {...}` that
// calls useState/useEffect trips the lint rule despite being valid React.
function FakeUserForm(props: {
  editUser: User | null;
  displayWeeklyHours?: number;
  // Task-11-Review Fix-Runde 1 (Important): analog zu displayWeeklyHours —
  // die Fake exponiert den Prop, damit dieser Test (Users.tsx' EIGENE
  // Orchestration, nicht UserForm's Rendering) nachweist, dass Users.tsx
  // auch die frischen Tageswerte nach jedem fetchUsers() nachzieht, während
  // das Formular offen bleibt.
  displayDayHours?: (number | null)[];
  // Abschluss-Review #431, Fund 3: dieselbe Bauart für die beiden übrigen
  // soll-treibenden Felder, die der Dialog schreibt.
  displayWorkDays?: number;
  displayUseDailySchedule?: boolean;
  onOpenHoursHistory?: (u: User) => void;
}) {
  const [unsavedDept, setUnsavedDept] = useState('');
  useEffect(() => {
    setUnsavedDept('');
  }, [props.editUser]);
  return (
    <div data-testid="fake-user-form">
      <input
        aria-label="Abteilung (unsaved)"
        value={unsavedDept}
        onChange={(e) => setUnsavedDept(e.target.value)}
      />
      <span data-testid="display-weekly-hours">{props.displayWeeklyHours ?? ''}</span>
      <span data-testid="display-day-hours">{(props.displayDayHours ?? []).join(',')}</span>
      <span data-testid="display-work-days">{props.displayWorkDays ?? ''}</span>
      <span data-testid="display-use-daily-schedule">
        {props.displayUseDailySchedule === undefined ? '' : String(props.displayUseDailySchedule)}
      </span>
      <button
        type="button"
        onClick={() => props.editUser && props.onOpenHoursHistory?.(props.editUser)}
      >
        Wochenstunden anpassen…
      </button>
    </div>
  );
}

// Release-Review 1.17.0 (Fund 2, MEDIUM): this test targets Users.tsx's OWN
// orchestration (fetchUsers / editingUser state) — NOT UserForm's or
// WorkingHoursModal's internals, which have their own dedicated test files.
// The fake UserForm reproduces the ONE behavior that actually caused the
// regression: the real UserForm resets its formData wholesale in
// `useEffect(..., [editUser])` (UserForm.tsx:82-126) whenever it receives a
// NEW `editUser` OBJECT REFERENCE — even for the very same user id. A PR #423
// effect in Users.tsx (removed by this fix) replaced `editingUser` with a
// fresh object from `users` after every fetchUsers(), which fires WHILE the
// form is still open (e.g. the Wochenstunden-/Carryover-Dialogs' onChanged).
// If Users.tsx ever again hands UserForm a new reference after such a
// background refetch, this fake fails exactly like the real component did.
vi.mock('./users/UserForm', () => ({
  default: FakeUserForm,
}));

// The dialog's OWN correctness (preview, sequence guard, stale display …) is
// covered exhaustively in WorkingHoursModal.test.tsx — faked here to a single
// button so this test stays focused on how Users.tsx reacts to `onChanged`.
function FakeWorkingHoursModal(props: { onChanged: () => void }) {
  return (
    <button type="button" onClick={props.onChanged}>
      Stundenänderung speichern (simuliert)
    </button>
  );
}
vi.mock('./users/WorkingHoursModal', () => ({
  default: FakeWorkingHoursModal,
}));

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    username: 'jd',
    email: null,
    first_name: 'Jane',
    last_name: 'Doe',
    role: 'employee',
    weekly_hours: 40,
    vacation_days: 30,
    work_days_per_week: 5,
    track_hours: true,
    exempt_from_arbzg: false,
    is_night_worker: false,
    receives_company_closures: true,
    is_active: true,
    is_hidden: false,
    calendar_color: '#fecaca',
    totp_enabled: false,
    use_daily_schedule: false,
    hours_monday: null,
    hours_tuesday: null,
    hours_wednesday: null,
    hours_thursday: null,
    hours_friday: null,
    scheduled_start_monday: null,
    scheduled_end_monday: null,
    scheduled_start_tuesday: null,
    scheduled_end_tuesday: null,
    scheduled_start_wednesday: null,
    scheduled_end_wednesday: null,
    scheduled_start_thursday: null,
    scheduled_end_thursday: null,
    scheduled_start_friday: null,
    scheduled_end_friday: null,
    first_work_day: null,
    last_work_day: null,
    deactivated_at: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
        <Users />
      </ToastProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset().mockResolvedValue({ data: {} });
  putMock.mockReset().mockResolvedValue({ data: {} });
  deleteMock.mockReset().mockResolvedValue({ data: {} });
});

describe('Release-Review 1.17.0 Fund 2: editingUser-Sync darf offene Eingaben nicht verwerfen', () => {
  it('verwirft NICHT die unsaved Eingabe im offenen Formular, wenn der Wochenstunden-Dialog speichert — zieht aber die Anzeige (Summe UND Tagesbreakdown) nach', async () => {
    let currentWeeklyHours = 40;
    // Task-11-Review Fix-Runde 1: die Tageswerte müssen GENAUSO frisch
    // nachgezogen werden wie die Summe — sonst zeigt UserForm's read-only
    // Box (#431) einen frischen Total neben einem eingefrorenen Breakdown.
    let currentDayHours: (number | null)[] = [8, 8, 8, 8, 8];
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/admin/users-overview')) return Promise.resolve({ data: [] });
      if (String(url) === '/admin/users') {
        return Promise.resolve({
          data: [makeUser({
            weekly_hours: currentWeeklyHours,
            use_daily_schedule: true,
            hours_monday: currentDayHours[0],
            hours_tuesday: currentDayHours[1],
            hours_wednesday: currentDayHours[2],
            hours_thursday: currentDayHours[3],
            hours_friday: currentDayHours[4],
          })],
        });
      }
      return Promise.resolve({ data: [] });
    });

    renderPage();
    await screen.findAllByText('Doe, Jane');

    fireEvent.click(screen.getAllByTitle('Bearbeiten')[0]);
    await screen.findByTestId('fake-user-form');
    expect(screen.getByTestId('display-weekly-hours')).toHaveTextContent('40');
    expect(screen.getByTestId('display-day-hours')).toHaveTextContent('8,8,8,8,8');

    // Admin types something unsaved, THEN opens the Wochenstunden-Dialog from
    // within the still-open form (exactly the path UserForm.tsx:385 offers).
    fireEvent.change(screen.getByLabelText('Abteilung (unsaved)'), { target: { value: 'Labor' } });
    expect(screen.getByLabelText('Abteilung (unsaved)')).toHaveValue('Labor');

    fireEvent.click(screen.getByText('Wochenstunden anpassen…'));

    // Simulate the dialog having saved a change — Di 8→5, server now reports
    // 37h total (20h in the pre-existing weekly_hours-only assertion below).
    currentWeeklyHours = 20;
    currentDayHours = [8, 5, 0, 0, 0];
    fireEvent.click(screen.getByText('Stundenänderung speichern (simuliert)'));

    // The refetch must update the LIVE weekly-hours display …
    await waitFor(() => expect(screen.getByTestId('display-weekly-hours')).toHaveTextContent('20'));
    // … AND the live day-hours breakdown, in the SAME refetch …
    expect(screen.getByTestId('display-day-hours')).toHaveTextContent('8,5,0,0,0');
    // … WITHOUT wiping what the admin had typed into the still-open form.
    expect(screen.getByLabelText('Abteilung (unsaved)')).toHaveValue('Labor');
  });

  it('setzt formData zurück, wenn ein ANDERER Nutzer zum Bearbeiten geöffnet wird', async () => {
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/admin/users-overview')) return Promise.resolve({ data: [] });
      if (String(url) === '/admin/users') {
        return Promise.resolve({
          data: [
            makeUser({ id: 'u1', first_name: 'Jane', last_name: 'Doe', weekly_hours: 40 }),
            makeUser({ id: 'u2', first_name: 'Max', last_name: 'Muster', weekly_hours: 30 }),
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });

    renderPage();
    await screen.findAllByText('Doe, Jane');

    fireEvent.click(screen.getAllByTitle('Bearbeiten')[0]);
    await screen.findByTestId('fake-user-form');
    fireEvent.change(screen.getByLabelText('Abteilung (unsaved)'), { target: { value: 'Labor' } });
    expect(screen.getByLabelText('Abteilung (unsaved)')).toHaveValue('Labor');

    // Switching to a DIFFERENT user is a real edit-session change — the
    // fake's reset-on-new-reference is expected to fire here (unlike the
    // same-user background refetch above).
    fireEvent.click(screen.getAllByTitle('Bearbeiten')[1]);
    await waitFor(() => expect(screen.getByTestId('display-weekly-hours')).toHaveTextContent('30'));
    expect(screen.getByLabelText('Abteilung (unsaved)')).toHaveValue('');
  });
});

describe('Abschluss-Review #431 Fund 3: Arbeitstage und Modus werden mit nachgezogen', () => {
  it('zieht work_days_per_week und use_daily_schedule in derselben Refetch-Runde nach', async () => {
    // Der gemeldete Fall: MA gleichmäßig 40 h auf 5 Tage; der Admin öffnet
    // „Bearbeiten", dann im offenen Formular den Dialog, trägt „20 h auf 4
    // Tage, gültig ab heute" ein und speichert. Danach zeigte das Formular
    // „20,0 h/Woche" NEBEN „Arbeitstage pro Woche: 5" — der Server hatte 4.
    let weekly = 40;
    let workDays = 5;
    let daily = false;
    getMock.mockImplementation((url: string) => {
      if (String(url).includes('/admin/users-overview')) return Promise.resolve({ data: [] });
      if (String(url) === '/admin/users') {
        return Promise.resolve({
          data: [makeUser({
            weekly_hours: weekly, work_days_per_week: workDays, use_daily_schedule: daily,
          })],
        });
      }
      return Promise.resolve({ data: [] });
    });

    renderPage();
    await screen.findAllByText('Doe, Jane');

    fireEvent.click(screen.getAllByTitle('Bearbeiten')[0]);
    await screen.findByTestId('fake-user-form');
    expect(screen.getByTestId('display-work-days')).toHaveTextContent('5');
    expect(screen.getByTestId('display-use-daily-schedule')).toHaveTextContent('false');

    fireEvent.change(screen.getByLabelText('Abteilung (unsaved)'), { target: { value: 'Labor' } });
    fireEvent.click(screen.getByText('Wochenstunden anpassen…'));

    weekly = 20;
    workDays = 4;
    daily = true;
    fireEvent.click(screen.getByText('Stundenänderung speichern (simuliert)'));

    await waitFor(() => expect(screen.getByTestId('display-weekly-hours')).toHaveTextContent('20'));
    expect(screen.getByTestId('display-work-days')).toHaveTextContent('4');
    expect(screen.getByTestId('display-use-daily-schedule')).toHaveTextContent('true');
    // Und weiterhin ohne die offene Eingabe zu verwerfen — der Grund, warum
    // hier schmale Props stehen und nicht ein neues `editingUser`.
    expect(screen.getByLabelText('Abteilung (unsaved)')).toHaveValue('Labor');
  });
});
