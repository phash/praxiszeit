import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import Profile from './Profile';

// Review Task 10 (Spec 2026-10-08, 14 / E67): die Wochenstunden stehen im Profil
// nur noch datumsaufgelöst in der Karte „Meine Arbeitszeit". Das Datenraster las
// `user.weekly_hours` aus der User-Zeile, die eine zukunftsdatierte Änderung erst beim
// nächsten Schreibvorgang nachzieht (kein Scheduler, Spec 9.8) — die Seite nannte
// dann zwei verschiedene Werte.

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));
vi.mock('../components/MyWorkScheduleCard', () => ({ default: () => <div>Karte Meine Arbeitszeit</div> }));
vi.mock('../components/MyQualificationsCard', () => ({ default: () => null }));

const USER = {
  id: 'u1', username: 'employee', email: 'employee@test.de', first_name: 'Max', last_name: 'Mustermann',
  role: 'employee', weekly_hours: 40, vacation_days: 30, is_active: true, track_hours: true,
  totp_enabled: false, calendar_color: null,
};
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({ user: USER, setUser: vi.fn(), setTokens: vi.fn() }),
}));

describe('<Profile /> persönliche Daten', () => {
  it('zeigt die Wochenstunden nicht aus der User-Zeile, sondern nur über die Karte', () => {
    render(<Profile />);
    expect(screen.getByText('Rolle')).toBeInTheDocument();
    expect(screen.getByText('Urlaubstage')).toBeInTheDocument();
    expect(screen.queryByText('Wochenstunden')).not.toBeInTheDocument();
    expect(screen.queryByText('40 Stunden')).not.toBeInTheDocument();
    expect(screen.getByText('Karte Meine Arbeitszeit')).toBeInTheDocument();
  });
});
