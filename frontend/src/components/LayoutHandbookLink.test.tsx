import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import Layout from './Layout';
import { useAuthStore } from '../stores/authStore';

vi.mock('../api/client', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  setImpersonating: vi.fn(),
  tryRefreshSession: vi.fn(),
}));

function linkFor(role: 'admin' | 'employee') {
  useAuthStore.setState({
    user: { role, first_name: 'A', last_name: 'B', username: 'ab' } as never,
  });
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<div />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByText(role === 'admin' ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch').closest('a');
}

describe('sidebar handbook button', () => {
  it('sidebar handbook button links to /help/mitarbeitende for employees', () => {
    expect(linkFor('employee')?.getAttribute('href')).toBe('/help/mitarbeitende');
  });
});
