import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios, { AxiosError } from 'axios';
import apiClient, {
  setAccessToken,
  getAccessToken,
  tryRefreshSession,
  setImpersonating,
} from './client';

// Tests for the security-critical auth plumbing in client.ts: the Bearer-token
// + CSRF request interceptor and the 401 → refresh → retry response interceptor
// (incl. parallel-refresh dedup and the session-expired event). We drive the
// real interceptor chain by swapping apiClient's adapter and spying on the
// raw axios.post the refresh uses. A custom adapter must settle itself, so
// `reply` resolves for 2xx and rejects with a real AxiosError otherwise.

const originalAdapter = apiClient.defaults.adapter;

function reply(config: any, status: number, data: any = {}) {
  const response = { data, status, statusText: '', headers: {}, config, request: {} };
  if (status >= 200 && status < 300) return Promise.resolve(response as any);
  return Promise.reject(new AxiosError('request failed', String(status), config, {}, response as any));
}

beforeEach(() => {
  setAccessToken(null);
  document.cookie.split('; ').forEach((c) => {
    const name = c.split('=')[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  });
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
  setAccessToken(null);
});

describe('access token storage', () => {
  it('round-trips via set/get and starts null', () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken('tok-123');
    expect(getAccessToken()).toBe('tok-123');
  });
});

describe('request interceptor', () => {
  it('attaches Authorization: Bearer when a token is set', async () => {
    setAccessToken('tok-abc');
    let seen: any;
    apiClient.defaults.adapter = (config) => {
      seen = config;
      return reply(config, 200);
    };
    await apiClient.get('/data');
    expect(seen.headers.Authorization).toBe('Bearer tok-abc');
  });

  it('omits Authorization when no token is set', async () => {
    let seen: any;
    apiClient.defaults.adapter = (config) => {
      seen = config;
      return reply(config, 200);
    };
    await apiClient.get('/data');
    expect(seen.headers.Authorization).toBeUndefined();
  });

  it('sends X-CSRF-Token from cookie on mutating methods', async () => {
    document.cookie = 'csrf_token=csrf-xyz';
    let seen: any;
    apiClient.defaults.adapter = (config) => {
      seen = config;
      return reply(config, 200);
    };
    await apiClient.post('/data', {});
    expect(seen.headers['X-CSRF-Token']).toBe('csrf-xyz');
  });

  it('does NOT send X-CSRF-Token on GET requests', async () => {
    document.cookie = 'csrf_token=csrf-xyz';
    let seen: any;
    apiClient.defaults.adapter = (config) => {
      seen = config;
      return reply(config, 200);
    };
    await apiClient.get('/data');
    expect(seen.headers['X-CSRF-Token']).toBeUndefined();
  });
});

describe('401 response interceptor', () => {
  it('refreshes once and retries the original request with the new token', async () => {
    const refresh = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { access_token: 'fresh-token' } } as any);

    let call = 0;
    const seenAuth: (string | undefined)[] = [];
    apiClient.defaults.adapter = (config) => {
      call++;
      seenAuth.push(config.headers?.Authorization as string | undefined);
      if (call === 1) return reply(config, 401, { detail: 'expired' });
      return reply(config, 200, { ok: true });
    };

    const res = await apiClient.get('/data');
    expect(res.data).toEqual({ ok: true });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledWith('/api/auth/refresh', null, {
      withCredentials: true,
    });
    expect(seenAuth[1]).toBe('Bearer fresh-token');
    expect(getAccessToken()).toBe('fresh-token');
  });

  it('deduplicates concurrent refreshes into a single /auth/refresh call', async () => {
    const refresh = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { access_token: 'fresh-token' } } as any);

    const seen = new Map<string, number>();
    apiClient.defaults.adapter = (config) => {
      const n = (seen.get(config.url!) || 0) + 1;
      seen.set(config.url!, n);
      if (n === 1) return reply(config, 401);
      return reply(config, 200, { url: config.url });
    };

    await Promise.all([apiClient.get('/a'), apiClient.get('/b')]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('dispatches auth:session-expired and clears the token when refresh fails', async () => {
    setAccessToken('stale');
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh denied'));
    const onExpired = vi.fn();
    window.addEventListener('auth:session-expired', onExpired);

    apiClient.defaults.adapter = (config) => reply(config, 401);

    await expect(apiClient.get('/data')).rejects.toBeTruthy();
    expect(onExpired).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
    window.removeEventListener('auth:session-expired', onExpired);
  });

  it('does NOT attempt refresh for /auth/login 401 (TOTP/invalid creds pass through)', async () => {
    const refresh = vi.spyOn(axios, 'post');
    apiClient.defaults.adapter = (config) => reply(config, 401);

    await expect(apiClient.post('/auth/login', {})).rejects.toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
  });

  it('does NOT attempt refresh for /auth/logout 401 (prevents logout↔refresh storm)', async () => {
    // A 401 on logout must NOT trigger the refresh path. Otherwise:
    // logout 401 → refresh fails → 'auth:session-expired' → logout() → ∞ loop
    // (real incident: logout 401 ×382, refresh 429 ×50, dashboard hangs).
    setAccessToken('stale');
    const refresh = vi
      .spyOn(axios, 'post')
      .mockRejectedValue(new Error('refresh must not be called from logout'));
    const onExpired = vi.fn();
    window.addEventListener('auth:session-expired', onExpired);

    apiClient.defaults.adapter = (config) => reply(config, 401);

    await expect(apiClient.post('/auth/logout')).rejects.toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
    // No refresh attempt ⇒ no session-expired re-dispatch ⇒ loop can't form.
    expect(onExpired).not.toHaveBeenCalled();
    window.removeEventListener('auth:session-expired', onExpired);
  });
});

describe('impersonation 401 handling (#370)', () => {
  it('does NOT refresh during impersonation and dispatches impersonation:expired', async () => {
    // An impersonation token is not refreshable — refreshing would silently
    // upgrade the read-only MA view to a full admin token (via the admin's
    // HttpOnly refresh cookie). On 401 we must bail back to the admin instead.
    setAccessToken('imp-token');
    setImpersonating(true);
    const refresh = vi.spyOn(axios, 'post');
    const onExpired = vi.fn();
    window.addEventListener('impersonation:expired', onExpired);

    apiClient.defaults.adapter = (config) => reply(config, 401);

    await expect(apiClient.get('/data')).rejects.toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
    expect(onExpired).toHaveBeenCalledTimes(1);

    window.removeEventListener('impersonation:expired', onExpired);
    setImpersonating(false);
  });
});

describe('#382 non-JSON (HTML) 200-body guard', () => {
  it('rejects a 200 response whose body is an HTML page (SPA/auth-proxy edge)', async () => {
    // A misrouted /api call resolving 200 with the SPA index.html used to reach
    // res.data.map/.toFixed downstream → render crash → ErrorBoundary. The
    // interceptor now converts it into a rejection so callers hit .catch.
    apiClient.defaults.adapter = (config) =>
      reply(config, 200, '<!doctype html><html><body>login</body></html>');
    await expect(apiClient.get('/admin/users/1/journal')).rejects.toBeTruthy();
  });

  it('passes a normal JSON array body through untouched', async () => {
    apiClient.defaults.adapter = (config) => reply(config, 200, [{ id: 1 }]);
    const res = await apiClient.get('/data');
    expect(res.data).toEqual([{ id: 1 }]);
  });

  it('passes a normal JSON object body through untouched', async () => {
    apiClient.defaults.adapter = (config) => reply(config, 200, { days: [] });
    const res = await apiClient.get('/data');
    expect(res.data).toEqual({ days: [] });
  });
});

describe('tryRefreshSession', () => {
  it('returns the new token on success', async () => {
    vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: 'restored' },
    } as any);
    await expect(tryRefreshSession()).resolves.toBe('restored');
    expect(getAccessToken()).toBe('restored');
  });

  it('returns null and clears the token on failure', async () => {
    setAccessToken('stale');
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('no cookie'));
    await expect(tryRefreshSession()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
  });
});
