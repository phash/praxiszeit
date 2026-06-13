import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the api client so the store's auth flows can be driven deterministically.
vi.mock('../api/client', () => ({
  default: { post: vi.fn(), get: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

import apiClient, { setAccessToken, tryRefreshSession } from '../api/client';
import { useAuthStore } from './authStore';

const post = apiClient.post as unknown as ReturnType<typeof vi.fn>;
const get = apiClient.get as unknown as ReturnType<typeof vi.fn>;
const mockSetAccessToken = setAccessToken as unknown as ReturnType<typeof vi.fn>;
const mockTryRefresh = tryRefreshSession as unknown as ReturnType<typeof vi.fn>;

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
  useAuthStore.setState({ user: null, isAuthenticated: false, isHydrating: true });
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
});
