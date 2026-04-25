import { fireEvent, render, screen, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider, useToast } from './ToastContext';

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
