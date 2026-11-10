/**
 * D-172 §3.4 — the accessibility wiring for a validated form field.
 *
 * A visible error is not an accessible one: a screen reader only connects the
 * message to its input when the input carries `aria-invalid` and an
 * `aria-describedby` that resolves to the rendered text. Pairing those three
 * values by hand is easy to get half-right, so the decision lives here and is
 * unit tested; the field's `Field` wrapper takes `errorId` for the `<p>`.
 *
 * Absent error → no attributes at all. `undefined` is omitted by React, which
 * keeps the "valid" markup free of a dangling empty description.
 */

export interface FieldA11y {
  /** Id for the rendered error text, or undefined when there is no error. */
  errorId: string | undefined;
  /** Spread onto the input/select/textarea. */
  inputProps: {
    'aria-invalid'?: true;
    'aria-describedby'?: string;
  };
}

export function fieldA11y(error: string | undefined, errorId: string): FieldA11y {
  if (error === undefined || error === '') {
    return { errorId: undefined, inputProps: {} };
  }
  return {
    errorId,
    inputProps: { 'aria-invalid': true, 'aria-describedby': errorId },
  };
}
