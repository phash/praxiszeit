import { fireEvent, render, screen, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider, useToast } from './ToastContext';
import { useReportStore } from '../stores/reportStore';
import { useAuthStore } from '../stores/authStore';

// Test harness: a child component that exposes the toast API to the test.
function ToastConsumer({ onMount }: { onMount: (api: ReturnType<typeof useToast>) => void }) {
  const api = useToast();
  // useEffect would do, but onMount lets the test capture the API
  // synchronously and then call it deterministically via act().
  if (!(window as unknown as { _toastApi?: unknown })._toastApi) {
    (window as unknown as { _toastApi: unknown })._toastApi = api;
    onMount(api);
  }
  return null;
}

const renderWithProvider = () => {
  let api!: ReturnType<typeof useToast>;
  render(
    <ToastProvider>
      <ToastConsumer
        onMount={(a) => {
          api = a;
        }}
      />
    </ToastProvider>,
  );
  return api;
};

describe('ToastProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    delete (window as unknown as { _toastApi?: unknown })._toastApi;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws when useToast is called outside the provider', () => {
    // Suppress React's noisy error boundary log for this test
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    function NakedConsumer() {
      useToast();
      return null;
    }
    expect(() => render(<NakedConsumer />)).toThrow(/within a ToastProvider/);
    spy.mockRestore();
  });

  it('renders a success toast with role="alert" and the message text', () => {
    const api = renderWithProvider();
    act(() => api.success('Eintrag gespeichert'));
    expect(screen.getByRole('alert')).toHaveTextContent('Eintrag gespeichert');
  });

  it('exposes severity-keyed shortcuts (success/error/info/warning)', () => {
    const api = renderWithProvider();
    act(() => {
      api.success('S');
      api.error('E');
      api.info('I');
      api.warning('W');
    });
    const alerts = screen.getAllByRole('alert');
    const texts = alerts.map((a) => a.textContent);
    expect(texts).toEqual(expect.arrayContaining(['S', 'E', 'I', 'W']));
  });

  it('auto-dismisses success toasts after 3000ms (severity default)', () => {
    const api = renderWithProvider();
    act(() => api.success('ok'));
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // Just before the default success duration: still visible.
    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(screen.queryByRole('alert')).toBeInTheDocument();

    // After the default tips over: gone.
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps error toasts on screen ~8s — severity gets more reading time', () => {
    const api = renderWithProvider();
    act(() => api.error('Server-Fehler'));

    // After 5s an error must STILL be visible (would be gone at the
    // success-default of 3s).
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // After 8.001s it should be gone.
    act(() => {
      vi.advanceTimersByTime(3002);
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('explicit duration overrides the severity default', () => {
    const api = renderWithProvider();
    act(() => api.success('schnell weg', 100));
    act(() => {
      vi.advanceTimersByTime(101);
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('duration=0 keeps the toast until manually dismissed', () => {
    // userEvent doesn't compose well with fake timers (its internal
    // pointer-event delays would race the clock). fireEvent.click is a
    // synchronous synthetic dispatch — perfect for a fake-timer test.
    const api = renderWithProvider();
    act(() => api.showToast('info', 'sticky', 0));

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByRole('alert')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Benachrichtigung schließen' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows multiple toasts simultaneously without losing any', () => {
    const api = renderWithProvider();
    act(() => {
      api.error('first');
      api.warning('second');
      api.info('third');
    });
    expect(screen.getAllByRole('alert')).toHaveLength(3);
  });

  it('assigns unique IDs even when toasts fire in the same tick', async () => {
    // Regression for F-056: collisions in the previous random-ID scheme
    // showed up as duplicate React keys + un-dismissable toasts. Stub
    // crypto.randomUUID to return a fresh value each call so we can
    // inspect the contract directly.
    const original = (globalThis.crypto as Crypto | undefined)?.randomUUID;
    let counter = 0;
    Object.defineProperty(globalThis.crypto, 'randomUUID', {
      configurable: true,
      writable: true,
      value: () =>
        `00000000-0000-0000-0000-${(counter++).toString().padStart(12, '0')}` as `${string}-${string}-${string}-${string}-${string}`,
    });
    const api = renderWithProvider();
    act(() => {
      api.success('a');
      api.success('b');
      api.success('c');
    });
    // Keys are not directly observable; the proof that no collision
    // happened is that all three render and all three can be removed.
    expect(screen.getAllByRole('alert')).toHaveLength(3);

    // Restore
    if (original) {
      Object.defineProperty(globalThis.crypto, 'randomUUID', {
        configurable: true,
        writable: true,
        value: original,
      });
    }
  });
});

describe('Fehler-Toast mit „An Entwickler schicken“ (#557)', () => {
  const hint = { status: 500, method: 'POST', path: '/api/time-entries/' };
  const setRole = (role: 'admin' | 'employee' | null) =>
    useAuthStore.setState({ user: role ? ({ id: 'u1', role } as never) : null });

  beforeEach(() => {
    vi.useFakeTimers();
    delete (window as unknown as { _toastApi?: unknown })._toastApi;
    useReportStore.setState({ lastServerError: null, request: null });
  });
  afterEach(() => {
    vi.useRealTimers();
    setRole(null);
  });

  it('admin error toast after 5xx shows action', () => {
    setRole('admin');
    const api = renderWithProvider();
    useReportStore.getState().recordServerError(hint);
    act(() => api.error('Speichern fehlgeschlagen'));
    expect(screen.getByRole('button', { name: 'An Entwickler schicken' })).toBeInTheDocument();
    // längere Anzeige (15 s) für den Aktions-Toast
    act(() => { vi.advanceTimersByTime(9000); });
    expect(screen.getByText('Speichern fehlgeschlagen')).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(6001); });
    expect(screen.queryByText('Speichern fehlgeschlagen')).toBeNull();
  });

  it('employee error toast after 5xx shows no action', () => {
    setRole('employee');
    const api = renderWithProvider();
    useReportStore.getState().recordServerError(hint);
    act(() => api.error('Speichern fehlgeschlagen'));
    expect(screen.getByText('Speichern fehlgeschlagen')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'An Entwickler schicken' })).toBeNull();
  });

  it('error toast without recent 5xx shows no action', () => {
    setRole('admin');
    const api = renderWithProvider();
    act(() => api.error('Eingabe ungültig'));
    expect(screen.queryByRole('button', { name: 'An Entwickler schicken' })).toBeNull();
  });

  it('action opens report request with path and status', () => {
    setRole('admin');
    const api = renderWithProvider();
    useReportStore.getState().recordServerError(hint);
    act(() => api.error('Speichern fehlgeschlagen'));
    fireEvent.click(screen.getByRole('button', { name: 'An Entwickler schicken' }));
    expect(useReportStore.getState().request).toEqual({
      serverError: hint,
      initialTitle: 'Serverfehler 500 bei POST /api/time-entries/',
    });
    expect(screen.queryByText('Speichern fehlgeschlagen')).toBeNull();
  });

  it('F13: title has no UUIDs/numeric ids and is capped at 200', () => {
    setRole('admin');
    const api = renderWithProvider();
    const path = '/api/admin/users/3fa85f64-5717-4562-b3fc-2c963f66afa6/working-hours-changes/42/' + 'x'.repeat(300);
    useReportStore.getState().recordServerError({ status: 500, method: 'PUT', path });
    act(() => api.error('Speichern fehlgeschlagen'));
    fireEvent.click(screen.getByRole('button', { name: 'An Entwickler schicken' }));
    const title = useReportStore.getState().request!.initialTitle;
    expect(title).toContain('/api/admin/users/<id>/working-hours-changes/<id>/');
    expect(title).not.toContain('3fa85f64');
    expect(title.length).toBeLessThanOrEqual(200);
  });

  it('F19: action of a newer toast keeps an open report and its toast', () => {
    setRole('admin');
    const api = renderWithProvider();
    useReportStore.getState().openReport({ serverError: hint, initialTitle: 'offen' });
    useReportStore.getState().recordServerError({ status: 503, method: 'GET', path: '/api/x/' });
    act(() => api.error('Zweiter Fehler'));
    fireEvent.click(screen.getByRole('button', { name: 'An Entwickler schicken' }));
    expect(useReportStore.getState().request?.initialTitle).toBe('offen');
    expect(screen.getByText('Zweiter Fehler')).toBeInTheDocument();
  });
});
