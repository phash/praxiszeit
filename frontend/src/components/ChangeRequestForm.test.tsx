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
