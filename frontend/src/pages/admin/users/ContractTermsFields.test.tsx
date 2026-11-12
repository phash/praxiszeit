import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { useSystemStore } from '../../../stores/systemStore';
import ContractTermsFields from './ContractTermsFields';
import type { ContractTerms } from './workingHoursTypes';

const BASE: ContractTerms = {
  vacation_days: 24, track_hours: true, milog_working_time_account: false,
  agreed_monthly_hours: null, use_fixed_monthly_target: false,
};

function Harness({
  initial = BASE, mode = 'change', suggestion = null, idPrefix = 'wh-', spy,
}: {
  initial?: ContractTerms; mode?: 'create' | 'change'; suggestion?: number | null; idPrefix?: string;
  spy?: (v: ContractTerms) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <ContractTermsFields
      value={value}
      onChange={(v) => { spy?.(v); setValue(v); }}
      mode={mode}
      suggestion={suggestion}
      idPrefix={idPrefix}
      weeklyHours={20}
    />
  );
}

beforeEach(() => {
  useSystemStore.setState({
    info: { deployment_mode: 'onprem', version: '', minimum_wage: { current: 13.9, since: '2026-01-01', next: null } },
    isLoaded: true,
  } as never);
});

describe('ContractTermsFields', () => {
  it('create mode keeps the element ids of the user form (E2E)', () => {
    const { container } = render(<Harness mode="create" idPrefix="" />);
    expect(container.querySelector('#f-vacation')).toBeInTheDocument();
    expect(container.querySelector('#track_hours')).toBeInTheDocument();
    expect(container.querySelector('#milog_working_time_account')).toBeInTheDocument();
    expect(screen.getByLabelText('Urlaubstage')).toHaveValue(24);
  });

  it('change mode prefixes every id and names the entitlement field', () => {
    const { container } = render(<Harness initial={{ ...BASE, milog_working_time_account: true }} />);
    expect(screen.getByLabelText('Urlaubsanspruch pro Jahr ab diesem Datum')).toHaveAttribute('step', '0.1');
    expect(container.querySelector('#wh-track_hours')).toBeInTheDocument();
    expect(container.querySelector('#wh-milog_working_time_account')).toBeInTheDocument();
    expect(container.querySelector('#wh-use_fixed_monthly_target')).toBeInTheDocument();
    expect(container.querySelector('#track_hours')).not.toBeInTheDocument();
    expect(container.querySelector('#milog_working_time_account')).not.toBeInTheDocument();
  });

  it('change mode offers „Vorschlag übernehmen (N)" only when the value differs from the suggestion', () => {
    const spy = vi.fn();
    render(<Harness initial={{ ...BASE, vacation_days: 28 }} suggestion={13.1} spy={spy} />);
    fireEvent.click(screen.getByRole('button', { name: 'Vorschlag übernehmen (13,1)' }));
    expect(spy).toHaveBeenLastCalledWith({ ...BASE, vacation_days: 13.1 });
    expect(screen.queryByRole('button', { name: /Vorschlag übernehmen/ })).not.toBeInTheDocument();
  });

  it('change mode reports an emptied entitlement as NaN (the dialog blocks it)', () => {
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    fireEvent.change(screen.getByLabelText('Urlaubsanspruch pro Jahr ab diesem Datum'), { target: { value: '' } });
    expect(spy.mock.calls.at(-1)![0].vacation_days).toBeNaN();
  });

  it('MiLoG controls keep their dependencies: monthly hours and fixed target only with the account', () => {
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    expect(screen.queryByLabelText(/Vereinbarte Monatsarbeitszeit/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/));
    fireEvent.change(screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/), { target: { value: '43.5' } });
    fireEvent.click(screen.getByLabelText(/Feste Monatsarbeitszeit/));
    expect(spy).toHaveBeenLastCalledWith({
      ...BASE, milog_working_time_account: true, agreed_monthly_hours: 43.5, use_fixed_monthly_target: true,
    });
    fireEvent.click(screen.getByLabelText(/Stundenzählung aktiv/));
    expect(spy.mock.calls.at(-1)![0].track_hours).toBe(false);
  });

  it('F009: switching off MiLoG or Stundenzählung clears the (then hidden) fixed monthly target', () => {
    const spy = vi.fn();
    const fixed = { ...BASE, milog_working_time_account: true, agreed_monthly_hours: 43.3, use_fixed_monthly_target: true };
    const { unmount } = render(<Harness initial={fixed} spy={spy} />);
    fireEvent.click(screen.getByLabelText(/Arbeitszeitkonto/));
    // user-12: auch die dann verborgene vereinbarte Monatszahl wird geleert
    expect(spy).toHaveBeenLastCalledWith({ ...fixed, milog_working_time_account: false, use_fixed_monthly_target: false, agreed_monthly_hours: null });
    unmount();
    render(<Harness initial={fixed} spy={spy} />);
    fireEvent.click(screen.getByLabelText(/Stundenzählung aktiv/));
    expect(spy).toHaveBeenLastCalledWith({ ...fixed, track_hours: false, use_fixed_monthly_target: false });
  });

  it('user-17: „0,5“ bleibt in der vereinbarten Monatsarbeitszeit tippbar (die 0 verschwindet nicht)', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ ...BASE, milog_working_time_account: true }} />);
    const input = screen.getByLabelText(/Vereinbarte Monatsarbeitszeit/) as HTMLInputElement;
    await user.type(input, '0.5');
    expect(input.value).toBe('0.5');
  });

  it('user-17: create-Modus — Urlaubstage leeren und neu tippen ergibt „30“, nicht „030“', async () => {
    const user = userEvent.setup();
    render(<Harness mode="create" idPrefix="f-" />);
    const input = screen.getByLabelText(/Urlaubstage/) as HTMLInputElement;
    await user.clear(input);
    expect(input.value).toBe('');
    await user.type(input, '30');
    expect(input.value).toBe('30');
  });
});
