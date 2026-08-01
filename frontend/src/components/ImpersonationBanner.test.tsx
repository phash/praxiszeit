import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ImpersonationBanner from './ImpersonationBanner';
import { useAuthStore } from '../stores/authStore';

function renderBanner() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ImpersonationBanner />
    </MemoryRouter>,
  );
}

describe('ImpersonationBanner (#370)', () => {
  beforeEach(() => {
    useAuthStore.setState({ impersonation: null });
  });

  it('renders nothing when not impersonating', () => {
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the impersonated employee name while impersonating', () => {
    useAuthStore.setState({ impersonation: { targetName: 'Max Muster' } });
    renderBanner();
    expect(screen.getByText('Max Muster')).toBeInTheDocument();
    expect(screen.getByText(/nur Lesen/i)).toBeInTheDocument();
  });

  it('"Zurück zu Admin" calls stopImpersonation', async () => {
    const stop = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ impersonation: { targetName: 'Max Muster' }, stopImpersonation: stop });
    renderBanner();
    fireEvent.click(screen.getByRole('button', { name: /Zurück zu Admin/i }));
    await waitFor(() => expect(stop).toHaveBeenCalledTimes(1));
  });
});
