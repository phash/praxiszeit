// Vitest setup: registers @testing-library/jest-dom matchers (toBeInTheDocument
// etc.) and per-test cleanup so React trees don't leak between cases.
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import React from 'react';

// ---------------------------------------------------------------------------
// Web Storage guarantee (localStorage / sessionStorage)
//
// Node >= 22 ships its OWN `localStorage`/`sessionStorage` accessor on
// globalThis. It is installed as a NON-ENUMERABLE getter, so vitest's jsdom
// environment — which copies jsdom's window properties onto globalThis — does
// not replace it. Node's getter only returns a real Storage when the process
// was started with `--localstorage-file`; otherwise it emits
//   ExperimentalWarning: localStorage is not available because
//   --localstorage-file was not provided
// and evaluates to `undefined`.
//
// Net effect on Node 26 (this machine): `localStorage` is undefined INSIDE the
// jsdom environment, so zustand's `persist` middleware blows up with
// "Cannot read properties of undefined (reading 'setItem')" on the very first
// `setState` — which killed all 17 authStore + 3 ImpersonationBanner tests in
// `beforeEach`, before a single assertion ran. Under Node 20 (the
// `node:20-alpine` container used by scripts/local-ci.sh) jsdom's own Storage
// survives and the same tests pass, which is why this looked like flaky
// "known noise" instead of a hard environment break.
//
// We therefore only fill the gap when the ambient Storage is unusable: where
// jsdom's real implementation is present it stays in charge, so tests keep
// exercising the browser-equivalent object. The replacement is a faithful
// in-memory Storage (null for missing keys, string coercion, working
// length/key/clear), NOT a mock of the store or of zustand's persist — the
// persist middleware really serializes and rehydrates through it.
// ---------------------------------------------------------------------------
function createMemoryStorage(): Storage {
  let data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear() {
      data = new Map();
    },
    getItem(key: string) {
      const value = data.get(String(key));
      return value === undefined ? null : value;
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null;
    },
    removeItem(key: string) {
      data.delete(String(key));
    },
    setItem(key: string, value: string) {
      data.set(String(key), String(value));
    },
  } as Storage;
}

function ensureWebStorage(name: 'localStorage' | 'sessionStorage'): void {
  let usable = false;
  try {
    const existing = (globalThis as unknown as Record<string, Storage | undefined>)[name];
    usable = !!existing && typeof existing.setItem === 'function';
  } catch {
    // Some Node builds throw rather than returning undefined — treat as unusable.
    usable = false;
  }
  if (usable) return;

  const storage = createMemoryStorage();
  const descriptor: PropertyDescriptor = {
    value: storage,
    writable: true,
    configurable: true,
    enumerable: true,
  };
  Object.defineProperty(globalThis, name, descriptor);
  // In vitest's jsdom env `window === globalThis`; keep the two in sync anyway
  // so this does not silently depend on that implementation detail.
  if (typeof window !== 'undefined' && (window as unknown) !== globalThis) {
    Object.defineProperty(window, name, descriptor);
  }
}

ensureWebStorage('localStorage');
ensureWebStorage('sessionStorage');

afterEach(() => {
  cleanup();
  // Storage is shared process-wide within a test file; wipe it so a persisted
  // zustand entry (e.g. 'auth-storage') cannot leak into the next test.
  localStorage.clear();
  sessionStorage.clear();
});

// jsdom returns 0×0 from getBoundingClientRect, which makes the `tabbable`
// library (used by focus-trap-react) consider every focusable element
// non-tabbable and throw "must have at least one container with at least one
// tabbable node". Replacing FocusTrap with a passthrough Fragment keeps the
// rendered DOM identical for tests; the focus-trap behaviour itself is
// covered by E2E in the browser, where it actually works.
vi.mock('focus-trap-react', () => ({
  default: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  FocusTrap: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));
