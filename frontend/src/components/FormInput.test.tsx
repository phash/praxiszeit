import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FormInput from './FormInput';
import FormSelect from './FormSelect';
import FormTextarea from './FormTextarea';

describe('Form-Felder (ui-16)', () => {
  it('reicht required und aria-required an das Element weiter', () => {
    render(
      <>
        <FormInput label="Name" required />
        <FormSelect label="Wahl" required><option>a</option></FormSelect>
        <FormTextarea label="Text" required />
      </>
    );
    for (const l of ['Name', 'Wahl', 'Text']) {
      const el = screen.getByLabelText(new RegExp(l));
      expect(el).toBeRequired();
      expect(el).toHaveAttribute('aria-required', 'true');
    }
  });

  it('behaelt die ID ueber Re-Renders stabil', () => {
    const { rerender } = render(<FormInput label="Name" />);
    const first = screen.getByLabelText('Name').id;
    rerender(<FormInput label="Name" />);
    expect(screen.getByLabelText('Name').id).toBe(first);
  });
});
