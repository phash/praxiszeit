import { describe, it, expect } from 'vitest';
import { getErrorMessage } from './errorMessage';

describe('getErrorMessage', () => {
  it('returns the fallback when no error payload is present', () => {
    expect(getErrorMessage(undefined, 'fallback')).toBe('fallback');
    expect(getErrorMessage({}, 'fallback')).toBe('fallback');
  });

  it('extracts a string detail from a HTTPException response', () => {
    const err = { response: { data: { detail: 'Zeiteintrag nicht gefunden' } } };
    expect(getErrorMessage(err)).toBe('Zeiteintrag nicht gefunden');
  });

  it('joins Pydantic validation error arrays', () => {
    const err = {
      response: {
        data: {
          detail: [
            { msg: 'field required', loc: ['body', 'date'] },
            { msg: 'invalid time format', loc: ['body', 'start_time'] },
          ],
        },
      },
    };
    expect(getErrorMessage(err)).toBe('field required, invalid time format');
  });

  it('uses the default fallback when no custom fallback is given', () => {
    expect(getErrorMessage(null)).toBe('Ein Fehler ist aufgetreten');
  });
});

describe('U4 (Audit 2026-07-31): rate-limit (429) handling', () => {
  it('replaces slowapi\'s raw English {error} body with a German wait-message on 429', () => {
    const err = {
      response: {
        status: 429,
        data: { error: 'Rate limit exceeded: 5 per 1 minute' },
      },
    };
    const msg = getErrorMessage(err, 'Anmeldung fehlgeschlagen. Bitte versuchen Sie es erneut.');
    expect(msg).not.toContain('Rate limit exceeded');
    expect(msg).not.toBe('Anmeldung fehlgeschlagen. Bitte versuchen Sie es erneut.');
    expect(msg.toLowerCase()).toContain('warten');
    expect(msg.toLowerCase()).not.toContain('erneut versuchen.');
  });

  it('keeps the account-lockout 429 detail message unchanged (it is already self-explanatory)', () => {
    const err = {
      response: {
        status: 429,
        data: { detail: 'Konto vorübergehend gesperrt. Bitte in 15 Minuten erneut versuchen.' },
      },
    };
    expect(getErrorMessage(err)).toBe('Konto vorübergehend gesperrt. Bitte in 15 Minuten erneut versuchen.');
  });

  it('falls back to a data.error string for non-429 responses that use that shape', () => {
    const err = { response: { status: 500, data: { error: 'Etwas ist schiefgelaufen' } } };
    expect(getErrorMessage(err)).toBe('Etwas ist schiefgelaufen');
  });
});

describe('getBlobErrorMessage (S1-02)', () => {
  it('liest die JSON-Fehlermeldung aus einer Blob-Antwort', async () => {
    const { getBlobErrorMessage } = await import('./errorMessage');
    const blob = new Blob([JSON.stringify({ detail: 'Passwort ist falsch' })], { type: 'application/json' });
    const msg = await getBlobErrorMessage({ response: { status: 400, data: blob } }, 'Download fehlgeschlagen');
    expect(msg).toBe('Passwort ist falsch');
  });

  it('fällt bei unlesbarem Blob auf den Rückfalltext zurück', async () => {
    const { getBlobErrorMessage } = await import('./errorMessage');
    const blob = new Blob(['kein json']);
    const msg = await getBlobErrorMessage({ response: { status: 500, data: blob } }, 'Download fehlgeschlagen');
    expect(msg).toBe('Download fehlgeschlagen');
  });

  it('verhält sich ohne Blob wie getErrorMessage', async () => {
    const { getBlobErrorMessage } = await import('./errorMessage');
    const msg = await getBlobErrorMessage({ response: { status: 400, data: { detail: 'x' } } }, 'y');
    expect(msg).toBe('x');
  });
});
