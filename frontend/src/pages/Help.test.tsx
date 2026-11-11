import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Help from './Help';
import { useAuthStore } from '../stores/authStore';
import { HANDBOOKS } from '../handbuch/content';

// Die Inhalte enthalten (noch) keine buchübergreifenden Links: Testlinks in den Lead einschleusen.
vi.mock('../handbuch/content', async (orig) => {
  const m = await orig<typeof import('../handbuch/content')>();
  const mit = {
    ...m.HANDBOOKS.mitarbeitende,
    lead: `${m.HANDBOOKS.mitarbeitende.lead} [XBook](handbuch:so-rechnet#tagessoll) [Lokal](#zeiterfassung-stempeln-eintraege)`,
  };
  return { ...m, HANDBOOKS: { ...m.HANDBOOKS, mitarbeitende: mit } };
});

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

  it('cross-book /help/ link navigates in-app without a reload', async () => {
    renderAt('/help/mitarbeitende', 'employee');
    const a = screen.getByRole('link', { name: 'XBook' });
    const notPrevented = fireEvent.click(a);
    expect(notPrevented).toBe(false);
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/help/so-rechnet#tagessoll'));
  });

  it('ctrl-click on a /help/ link is not intercepted', () => {
    renderAt('/help/mitarbeitende', 'employee');
    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'XBook' }), { ctrlKey: true });
    expect(notPrevented).toBe(true);
    expect(screen.getByTestId('where').textContent).toBe('/help/mitarbeitende');
  });

  it('a #anchor link is left to the browser', () => {
    renderAt('/help/mitarbeitende', 'employee');
    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'Lokal' }));
    expect(notPrevented).toBe(true);
  });

  it('switching book without hash scrolls main to the top', async () => {
    const main = document.createElement('main');
    main.scrollTo = vi.fn() as never;
    document.body.appendChild(main);
    try {
      renderAt('/help/mitarbeitende', 'employee');
      (main.scrollTo as ReturnType<typeof vi.fn>).mockClear();
      fireEvent.click(tabNav().querySelectorAll('a')[1]);
      await waitFor(() => expect(main.scrollTo).toHaveBeenCalledWith({ top: 0 }));
    } finally {
      main.remove();
    }
  });
});
