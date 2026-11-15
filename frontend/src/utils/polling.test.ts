import { describe, it, expect } from 'vitest';
import { isAuthPollFailure } from './polling';

// Log-Audit 2026-11-15 (Punkt 17): ~1400 Polls mit 401 nach Ablauf der Sitzung.
describe('isAuthPollFailure', () => {
  it('erkennt 401 und 403', () => {
    expect(isAuthPollFailure({ response: { status: 401 } })).toBe(true);
    expect(isAuthPollFailure({ response: { status: 403 } })).toBe(true);
  });
  it('ignoriert Netzfehler, 5xx und 429', () => {
    expect(isAuthPollFailure(new Error('Network Error'))).toBe(false);
    expect(isAuthPollFailure({ response: { status: 503 } })).toBe(false);
    expect(isAuthPollFailure({ response: { status: 429 } })).toBe(false);
    expect(isAuthPollFailure(null)).toBe(false);
    expect(isAuthPollFailure(undefined)).toBe(false);
  });
});
