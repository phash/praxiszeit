import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Help from './Help';
import { useAuthStore } from '../stores/authStore';
import { HANDBOOKS } from '../handbuch/content';

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname}{l.hash}</div>;
}

function renderAt(path: string, role: 'admin' | 'employee') {
  useAuthStore.setState({ user: { role } as never });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes>
        <Route path="/help/:book?" element={<Help />} />
      </Routes>
    </MemoryRouter>,
  );
}

const tabNav = () => screen.getByRole('navigation', { name: 'Handbücher' });

describe('Help page (graphic handbook)', () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it('employee visiting /help/praxisleitung is redirected to /help/mitarbeitende', async () => {
    renderAt('/help/praxisleitung', 'employee');
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/help/mitarbeitende'));
  });

  it('/help redirects to the default book by role', async () => {
    renderAt('/help', 'admin');
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/help/praxisleitung'));
  });

  it('admin sees three tabs', () => {
    renderAt('/help/praxisleitung', 'admin');
    expect(tabNav().querySelectorAll('a')).toHaveLength(3);
  });

  it('employee sees two tabs', () => {
    renderAt('/help/mitarbeitende', 'employee');
    expect(tabNav().querySelectorAll('a')).toHaveLength(2);
    expect(tabNav().textContent).not.toContain('Praxisleitung');
  });

  it('renders chapter anchors from content', () => {
    const { container } = renderAt('/help/mitarbeitende', 'employee');
    for (const c of HANDBOOKS.mitarbeitende.chapters) {
      expect(container.querySelector(`#${c.id}`)).not.toBeNull();
    }
  });

  it('scrolls to the hash target inside the page', async () => {
    const id = HANDBOOKS.mitarbeitende.chapters[1].id;
    renderAt(`/help/mitarbeitende#${id}`, 'employee');
    await waitFor(() => expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled());
  });
});
