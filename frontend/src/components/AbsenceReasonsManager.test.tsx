import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ToastProvider } from '../contexts/ToastContext';
import AbsenceReasonsManager from './AbsenceReasonsManager';
import * as api from '../api/absenceReasons';

// #376: keine Netz-Calls im Test — listReasons liefert leer, so dass alle
// Presets als "noch nicht aktiviert" gerendert werden.
beforeEach(() => {
  vi.spyOn(api, 'listReasons').mockResolvedValue([]);
});

describe('AbsenceReasonsManager (#376 presets)', () => {
  it('offers the Kind-krank preset button', async () => {
    render(
      <ToastProvider>
        <AbsenceReasonsManager />
      </ToastProvider>,
    );
    expect(await screen.findByText('+ Kind krank')).toBeInTheDocument();
  });
});
