import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../api/client', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

import OnboardingModal from './OnboardingModal';
import { useAuthStore } from '../stores/authStore';
import { useSystemStore } from '../stores/systemStore';

function setUser(extra: Record<string, unknown>) {
  useAuthStore.setState({
    user: { id: 'u1', username: 'maria', role: 'employee', first_name: 'Maria', last_name: 'H', ...extra } as never,
    isAuthenticated: true,
    impersonation: null,
  });
}

describe('OnboardingModal', () => {
  beforeEach(() => {
    useSystemStore.setState({ info: { onboarding_enabled: true } as never, isLoaded: true });
  });

  it('stays hidden while the profile is not loaded yet (login response has no onboarding field)', () => {
    // Die Login-Antwort trägt onboarding_completed_at nicht; erst /auth/me liefert es.
    // Bis dahin darf das Fenster nicht aufblitzen (Rückschritt durch die sofortige
    // Weiterleitung der Anmeldeseite, auth-06).
    setUser({});
    render(<OnboardingModal />);
    expect(screen.queryByRole('button', { name: "Los geht's" })).toBeNull();
  });

  it('stays hidden once onboarding is completed', () => {
    setUser({ onboarding_completed_at: '2026-10-28T09:30:00Z' });
    render(<OnboardingModal />);
    expect(screen.queryByRole('button', { name: "Los geht's" })).toBeNull();
  });

  it('shows when the server reports onboarding as not completed', () => {
    setUser({ onboarding_completed_at: null });
    render(<OnboardingModal />);
    expect(screen.getByRole('button', { name: "Los geht's" })).toBeInTheDocument();
  });
});
