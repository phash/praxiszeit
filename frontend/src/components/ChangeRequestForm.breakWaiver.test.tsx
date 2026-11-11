import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ChangeRequestForm from './ChangeRequestForm';
import { useSystemStore } from '../stores/systemStore';

// #499: Antragsformular — das Zusatzfeld „Pflicht-Pause war nicht möglich" gibt es
// nur, solange der Mandant die Ausnahme erlaubt.

const postMock = vi.fn();
vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: (...a: unknown[]) => postMock(...a), put: vi.fn(), delete: vi.fn() },
}));

const S4 = 'Bei mehr als 6 Stunden Arbeitszeit ist eine Pause von mindestens 30 Minuten erforderlich (ArbZG §4).';

function rejectOnce(detail: string) {
  postMock.mockRejectedValueOnce(Object.assign(new Error(detail), { response: { status: 400, data: { detail } } }));
}

async function submitCreate() {
  render(<ChangeRequestForm entry={null} requestType="create" onClose={vi.fn()} onSuccess={vi.fn()} />);
  fireEvent.change(screen.getByPlaceholderText('Warum ist diese Änderung notwendig?'), {
    target: { value: 'vergessen' },
  });
  fireEvent.submit(document.querySelector('form') as HTMLFormElement);
  await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
}

beforeEach(() => {
  postMock.mockReset();
});

describe('<ChangeRequestForm /> Pflicht-Pause-Ausnahme (#499)', () => {
  it('bietet das Begründungsfeld nach einem §4-Fehler an (Default)', async () => {
    useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
    rejectOnce(S4);
    await submitCreate();
    expect(await screen.findByText(/Pflicht-Pause war nicht möglich – Begründung/)).toBeInTheDocument();
  });

  it('bietet kein Begründungsfeld an, wenn die Praxis die Ausnahme abgeschaltet hat', async () => {
    useSystemStore.setState({
      info: { deployment_mode: 'onprem', version: '', break_exception_allowed: false },
      isLoaded: true,
    });
    rejectOnce(S4);
    await submitCreate();
    expect(await screen.findByText(/ArbZG §4/)).toBeInTheDocument();
    expect(screen.queryByText(/Pflicht-Pause war nicht möglich – Begründung/)).not.toBeInTheDocument();
  });
});

// Gesamtreview 1.20 (Fund 16): die Ausnahme-Begründung ist mit ihrem Label verknüpft.
describe('<ChangeRequestForm /> Pflicht-Pause-Ausnahme — Label (Gesamtreview Fund 16)', () => {
  it('das Begründungsfeld der Ausnahme trägt sein Label als Namen', async () => {
    useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
    rejectOnce(S4);
    await submitCreate();
    const field = await screen.findByLabelText(/Pflicht-Pause war nicht möglich – Begründung/);
    expect(field.tagName).toBe('TEXTAREA');
  });
});

// Review 2026-11-11 (antrag-05/15)
describe('<ChangeRequestForm /> Review 2026-11-11', () => {
  it('bietet bei „Pause so lang wie der Eintrag“ keine Ausnahme an (antrag-05)', async () => {
    useSystemStore.setState({ info: { deployment_mode: 'onprem', version: '' }, isLoaded: true });
    rejectOnce('Die Pause (45 Min.) ist so lang wie der Eintrag oder länger (30 Min.). Bitte die tatsächliche Pause eintragen.');
    await submitCreate();
    expect(await screen.findByText(/so lang wie der Eintrag/)).toBeInTheDocument();
    expect(screen.queryByText(/Pflicht-Pause war nicht möglich – Begründung/)).not.toBeInTheDocument();
  });

  it('lässt das Pausenfeld leeren und sendet dann 0 (antrag-15)', async () => {
    postMock.mockResolvedValue({ data: {} });
    render(<ChangeRequestForm entry={null} requestType="create" onClose={vi.fn()} onSuccess={vi.fn()} />);
    const pause = screen.getByLabelText('Pause (Min.)') as HTMLInputElement;
    fireEvent.change(pause, { target: { value: '45' } });
    fireEvent.change(pause, { target: { value: '' } });
    expect(pause.value).toBe('');
    fireEvent.change(screen.getByPlaceholderText('Warum ist diese Änderung notwendig?'), { target: { value: 'x' } });
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/change-requests',
      expect.objectContaining({ proposed_break_minutes: 0 })));
  });

  it('begrenzt das Datum auf gestern und meldet Fehler per role=alert (antrag-15)', async () => {
    rejectOnce('Änderungsanträge sind nur für vergangene Tage möglich');
    await submitCreate();
    expect(await screen.findByRole('alert')).toHaveTextContent('nur für vergangene Tage');
    const max = (screen.getByLabelText('Datum') as HTMLInputElement).max;
    expect(max).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(max < new Date().toISOString().slice(0, 10) || max === new Date(Date.now() - 864e5).toISOString().slice(0, 10)).toBe(true);
  });
});
