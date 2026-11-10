import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { fieldA11y } from '@/lib/field-a11y';

/**
 * The checkout audit found visible errors that were not connected to their
 * inputs. This pins the connection: an error always names the message element and
 * marks the control invalid, and a clean field carries neither attribute.
 */
describe('field accessibility wiring', () => {
  it('marks an invalid field and points at its rendered message', () => {
    const wiring = fieldA11y('نام الزامی است.', 'checkout-name-error');
    assert.equal(wiring.errorId, 'checkout-name-error');
    assert.deepEqual(wiring.inputProps, {
      'aria-invalid': true,
      'aria-describedby': 'checkout-name-error',
    });
  });

  it('adds nothing to a field without an error', () => {
    assert.deepEqual(fieldA11y(undefined, 'checkout-name-error'), {
      errorId: undefined,
      inputProps: {},
    });
    assert.deepEqual(fieldA11y('', 'checkout-name-error'), {
      errorId: undefined,
      inputProps: {},
    });
  });
});
