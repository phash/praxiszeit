import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios, { AxiosError } from 'axios';
import apiClient, {
  setAccessToken,
  getAccessToken,
  tryRefreshSession,
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
