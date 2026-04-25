// Vitest setup: registers @testing-library/jest-dom matchers (toBeInTheDocument
// etc.) and per-test cleanup so React trees don't leak between cases.
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import React from 'react';

afterEach(() => {
  cleanup();
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
