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
