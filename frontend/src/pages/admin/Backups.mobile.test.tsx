import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// ui-20: Die Sicherungsliste muss auf 390 px horizontal scrollbar sein und lange
// Dateinamen umbrechen, sonst sind Aktionen (Download/Löschen) nicht erreichbar.
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(async () => ({
      data: {
        backups: [{ filename: 'praxiszeit_backup_2026-11-11_020000_with_a_very_long_name.sql.gz', size_bytes: 2048, created_at: '2026-11-11T02:00:00Z' }],
        config: { enabled: false, hour: 2, retention_days: 30, location: '' },
      },
    })),
  },
}));
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import Backups from './Backups';

describe('Backups Liste auf schmalen Bildschirmen (ui-20)', () => {
  it('liegt in einem horizontal scrollbaren Container, Dateiname bricht um', async () => {
    render(<Backups />);
    const cell = await screen.findByText(/praxiszeit_backup_2026-11-11/);
    expect(cell.className).toMatch(/break-all/);
    expect(cell.closest('table')?.parentElement?.className).toMatch(/overflow-x-auto/);
  });
});
