import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

/** Code-Review 2026-11-11: ops-06 (kein Cache bei fehlgeschlagener Prüfung), ops-07 (Storage-Guards, 404-Cache). */
const post = vi.hoisted(() => vi.fn());
vi.mock('../api/client', () => ({ default: { post } }));

import UpdateBanner from './UpdateBanner';

beforeEach(() => { post.mockReset(); sessionStorage.clear(); });
afterEach(() => { vi.restoreAllMocks(); });

describe('UpdateBanner', () => {
  it('zeigt das Banner und cached eine erfolgreiche Antwort', async () => {
    post.mockResolvedValue({ data: { update_available: true, update: { latest_version: '9.9.9', current_version: '1.0.0' }, download_page: 'https://x.example' } });
    render(<UpdateBanner />);
    expect(await screen.findByText(/Neue Version 9.9.9/)).toBeInTheDocument();
    expect(sessionStorage.getItem('pz-update-check')).not.toBeNull();
  });

  it('cached eine fehlgeschlagene Prüfung (check_failed) nicht', async () => {
    post.mockResolvedValue({ data: { update_available: false, check_failed: true } });
    render(<UpdateBanner />);
    await waitFor(() => expect(post).toHaveBeenCalled());
    await Promise.resolve();
    expect(sessionStorage.getItem('pz-update-check')).toBeNull();
  });

  it('merkt sich 404 (nicht konfiguriert) und fragt nicht erneut', async () => {
    post.mockRejectedValue({ response: { status: 404 } });
    const { unmount } = render(<UpdateBanner />);
    await waitFor(() => expect(sessionStorage.getItem('pz-update-check')).toBe('not-configured'));
    unmount();
    render(<UpdateBanner />);
    await Promise.resolve();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('stürzt bei gesperrtem Speicher nicht ab', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    post.mockResolvedValue({ data: { update_available: true, update: { latest_version: '9.9.9', current_version: '1.0.0' } } });
    render(<UpdateBanner />);
    expect(await screen.findByText(/Neue Version 9.9.9/)).toBeInTheDocument();
  });
});
