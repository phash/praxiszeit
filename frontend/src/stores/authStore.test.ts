import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the api client so the store's auth flows can be driven deterministically.
vi.mock('../api/client', () => ({
  default: { post: vi.fn(), get: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  tryRefreshSession: vi.fn(),
  setImpersonating: vi.fn(),
}));

import apiClient, { setAccessToken, tryRefreshSession, getAccessToken, setImpersonating } from '../api/client';
import { useAuthStore } from './authStore';

const post = apiClient.post as unknown as ReturnType<typeof vi.fn>;
const get = apiClient.get as unknown as ReturnType<typeof vi.fn>;
const mockSetAccessToken = setAccessToken as unknown as ReturnType<typeof vi.fn>;
const mockTryRefresh = tryRefreshSession as unknown as ReturnType<typeof vi.fn>;
const mockGetAccessToken = getAccessToken as unknown as ReturnType<typeof vi.fn>;
const mockSetImpersonating = setImpersonating as unknown as ReturnType<typeof vi.fn>;

const TARGET = {
  id: '9',
  username: 'max',
  email: 'max@t.local',
  first_name: 'Max',
  last_name: 'Muster',
  role: 'employee',
};

const USER = {
  id: '1',
  username: 'erika',
  email: 'e@t.local',
  first_name: 'Erika',
  last_name: 'Muster',
  role: 'employee',
};

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null, isAuthenticated: false, isHydrating: true, impersonation: null });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('login', () => {
  it('stores user + token and marks authenticated, then merges /auth/me', async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'tok', user: USER } });
    get.mockResolvedValueOnce({ data: { profile_picture: 'data:img' } });

    await useAuthStore.getState().login('erika', 'pw');

    expect(mockSetAccessToken).toHaveBeenCalledWith('tok');
    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(true);
    expect(s.isHydrating).toBe(false);
    expect(s.user?.username).toBe('erika');
    expect(s.user?.profile_picture).toBe('data:img'); // merged from /auth/me
  });

  it('forwards the TOTP code when provided', async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'tok', user: USER } });
    get.mockResolvedValueOnce({ data: {} });

    await useAuthStore.getState().login('erika', 'pw', '123456');

    expect(post).toHaveBeenCalledWith('/auth/login', {
      username: 'erika',
      password: 'pw',
      totp_code: '123456',
    });
  });

  it('stays authenticated even if the /auth/me profile fetch fails', async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'tok', user: USER } });
    get.mockRejectedValueOnce(new Error('me failed'));

    await useAuthStore.getState().login('erika', 'pw');

    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(true);
    expect(s.user?.username).toBe('erika');
  });
});

describe('logout', () => {
  it('clears state and token and calls the server logout', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    post.mockResolvedValueOnce({ data: {} });

    await useAuthStore.getState().logout();

    expect(post).toHaveBeenCalledWith('/auth/logout');
    expect(mockSetAccessToken).toHaveBeenCalledWith(null);
    const s = useAuthStore.getState();
    expect(s.user).toBeNull();
    expect(s.isAuthenticated).toBe(false);
  });

  it('still clears client state when the server logout call fails', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    post.mockRejectedValueOnce(new Error('network'));

    await useAuthStore.getState().logout();

    expect(mockSetAccessToken).toHaveBeenCalledWith(null);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});

describe('hydrate', () => {
  it('just unlocks the UI when nothing is persisted', async () => {
    useAuthStore.setState({ user: null, isAuthenticated: false, isHydrating: true });

    await useAuthStore.getState().hydrate();

    expect(mockTryRefresh).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isHydrating).toBe(false);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('restores the session via refresh cookie and re-fetches the profile', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: false, isHydrating: true });
    mockTryRefresh.mockResolvedValueOnce('restored-token');
    get.mockResolvedValueOnce({ data: { ...USER, profile_picture: 'data:img' } });

    await useAuthStore.getState().hydrate();

    expect(mockTryRefresh).toHaveBeenCalledTimes(1);
    const s = useAuthStore.getState();
    expect(s.isAuthenticated).toBe(true);
    expect(s.isHydrating).toBe(false);
    expect(s.user?.profile_picture).toBe('data:img');
  });

  it('wipes the persisted user when the refresh cookie is gone', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: true });
    mockTryRefresh.mockResolvedValueOnce(null);

    await useAuthStore.getState().hydrate();

    const s = useAuthStore.getState();
    expect(s.user).toBeNull();
    expect(s.isAuthenticated).toBe(false);
    expect(s.isHydrating).toBe(false);
    expect(get).not.toHaveBeenCalled(); // no profile fetch after failed refresh
  });
});

describe('impersonation (#370)', () => {
  it('startImpersonation swaps to the impersonation token and records the target', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } });
    get.mockResolvedValueOnce({ data: TARGET });

    await useAuthStore.getState().startImpersonation('9', 'Max Muster');

    expect(post).toHaveBeenCalledWith('/admin/users/9/impersonate');
    expect(mockSetAccessToken).toHaveBeenCalledWith('imp-tok');
    expect(mockSetImpersonating).toHaveBeenCalledWith(true);
    const s = useAuthStore.getState();
    expect(s.isImpersonating()).toBe(true);
    expect(s.impersonation?.targetName).toBe('Max Muster');
    expect(s.user?.username).toBe('max');
  });

  it('stopImpersonation ends the session and restores the admin token + identity', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } }); // impersonate
    get.mockResolvedValueOnce({ data: TARGET }); // /auth/me as target
    await useAuthStore.getState().startImpersonation('9', 'Max Muster');

    post.mockResolvedValueOnce({ data: {} }); // /admin/impersonate/end
    get.mockResolvedValueOnce({ data: USER }); // /auth/me as admin again
    await useAuthStore.getState().stopImpersonation();

    expect(post).toHaveBeenCalledWith('/admin/impersonate/end');
    expect(mockSetImpersonating).toHaveBeenLastCalledWith(false);
    expect(mockSetAccessToken).toHaveBeenLastCalledWith('admin-tok');
    const s = useAuthStore.getState();
    expect(s.isImpersonating()).toBe(false);
    expect(s.impersonation).toBeNull();
    expect(s.user?.username).toBe('erika');
  });

  it('stopImpersonation still restores admin even if the end call fails', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } });
    get.mockResolvedValueOnce({ data: TARGET });
    await useAuthStore.getState().startImpersonation('9', 'Max');

    post.mockRejectedValueOnce(new Error('end failed'));
    get.mockResolvedValueOnce({ data: USER });
    await useAuthStore.getState().stopImpersonation();

    expect(mockSetAccessToken).toHaveBeenLastCalledWith('admin-tok');
    expect(useAuthStore.getState().isImpersonating()).toBe(false);
  });

  it('concurrent stopImpersonation calls dedup: end fires once, admin token restored (not nulled)', async () => {
    // MEDIUM #4: banner click + impersonation:expired event can race. A shared
    // in-flight guard must prevent the second call from nulling the restored token.
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } });
    get.mockResolvedValueOnce({ data: TARGET });
    await useAuthStore.getState().startImpersonation('9', 'Max');

    post.mockResolvedValue({ data: {} });
    get.mockResolvedValue({ data: USER });
    await Promise.all([
      useAuthStore.getState().stopImpersonation(),
      useAuthStore.getState().stopImpersonation(),
    ]);

    const endCalls = post.mock.calls.filter((c) => c[0] === '/admin/impersonate/end').length;
    expect(endCalls).toBe(1);
    // The restored admin token must never be clobbered back to null by the racing call.
    expect(mockSetAccessToken).toHaveBeenLastCalledWith('admin-tok');
    expect(useAuthStore.getState().isImpersonating()).toBe(false);
  });

  it('logout while impersonating resets impersonation state and clears the flag', async () => {
    // HIGH #1/#2: a normal "Abmelden" during impersonation must reset impersonation
    // state (so it can't leak into the next SPA session) and end up logged out.
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } });
    get.mockResolvedValueOnce({ data: TARGET });
    await useAuthStore.getState().startImpersonation('9', 'Max');

    post.mockResolvedValueOnce({ data: {} }); // /auth/logout
    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().isImpersonating()).toBe(false);
    expect(useAuthStore.getState().impersonation).toBeNull();
    expect(mockSetImpersonating).toHaveBeenLastCalledWith(false);
    expect(post).toHaveBeenCalledWith('/auth/logout');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('login resets any stale impersonation state', async () => {
    // HIGH #2: stale impersonation flags must never survive into a fresh login.
    useAuthStore.setState({ impersonation: { targetName: 'Ghost' } as any });
    post.mockResolvedValueOnce({ data: { access_token: 'tok', user: USER } });
    get.mockResolvedValueOnce({ data: {} });

    await useAuthStore.getState().login('erika', 'pw');

    expect(useAuthStore.getState().impersonation).toBeNull();
    expect(mockSetImpersonating).toHaveBeenCalledWith(false);
  });
});

describe('impersonation:expired listener (#370)', () => {
  it('returns to the admin session when the event fires', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    mockGetAccessToken.mockReturnValue('admin-tok');
    post.mockResolvedValueOnce({ data: { access_token: 'imp-tok', user: TARGET } });
    get.mockResolvedValueOnce({ data: TARGET });
    await useAuthStore.getState().startImpersonation('9', 'Max');

    post.mockResolvedValue({ data: {} });
    get.mockResolvedValue({ data: USER });
    window.dispatchEvent(new CustomEvent('impersonation:expired'));

    await vi.waitFor(() => {
      expect(useAuthStore.getState().isImpersonating()).toBe(false);
    });
  });
});

describe('auth:session-expired listener', () => {
  it('logs the user out when the global event fires', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    post.mockResolvedValue({ data: {} });

    window.dispatchEvent(new CustomEvent('auth:session-expired'));
    // logout() is async; let its microtasks flush
    await vi.waitFor(() => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
    expect(post).toHaveBeenCalledWith('/auth/logout');
  });

  it('collapses a burst of session-expired events into a single logout', async () => {
    useAuthStore.setState({ user: USER as any, isAuthenticated: true, isHydrating: false });
    post.mockResolvedValue({ data: {} });

    // A broken session fires many events at once (e.g. dashboard's 7 parallel
    // requests all fail the shared refresh). The re-entrancy guard must turn
    // this into exactly one server logout.
    window.dispatchEvent(new CustomEvent('auth:session-expired'));
    window.dispatchEvent(new CustomEvent('auth:session-expired'));
    window.dispatchEvent(new CustomEvent('auth:session-expired'));

    await vi.waitFor(() => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('/auth/logout');
  });
});
