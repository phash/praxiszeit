import { describe, it, expect } from 'vitest';
import { safeHttpUrl } from './url';

describe('safeHttpUrl', () => {
  it('allows https URLs', () => {
    expect(safeHttpUrl('https://praxiszeit.mr-development.de')).toBe(
      'https://praxiszeit.mr-development.de/'
    );
  });

  it('allows http URLs', () => {
    expect(safeHttpUrl('http://example.com/path')).toBe('http://example.com/path');
  });

  it('rejects javascript: URLs (XSS vector)', () => {
    expect(safeHttpUrl("javascript:fetch('/api/users')")).toBeNull();
  });

  it('rejects data: URLs', () => {
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
  });

  it('rejects malformed / empty / nullish input', () => {
    expect(safeHttpUrl('not a url')).toBeNull();
    expect(safeHttpUrl('')).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
    expect(safeHttpUrl(undefined)).toBeNull();
  });
});
