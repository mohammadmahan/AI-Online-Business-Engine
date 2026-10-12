import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { CartLine } from '@/contracts/storefront';
import {
  addLine,
  cartCount,
  cartSubtotal,
  parseStoredCart,
  removeLine,
  serializeCart,
  setLineQuantity,
} from '@/lib/cart-rules';
import { MAX_LINE_QUANTITY } from '@/lib/checkout-rules';

/**
 * D-172 §3.2 — the client cart.
 *
 * `localStorage` is untrusted input, so the parsing tests are the important
 * ones: a blob written by an older version, a half-finished write or a
 * hand-edited value must degrade to a valid cart, never to a crashed page and
 * never to a cart the write path would then have to trust.
 */

function line(overrides: Partial<CartLine> = {}): CartLine {
  return {
    variantId: 'v1',
    productSlug: 'manto-katan',
    productTitle: 'مانتو کتان',
    size: 'M',
    colorName: 'مشکی',
    colorHex: '#111111',
    unitPrice: 2_450_000,
    quantity: 1,
    imageUrl: null,
    ...overrides,
  };
}

describe('cart lines (§3.2)', () => {
  it('merges the same variant instead of adding a second row, capped at the line maximum', () => {
    const once = addLine([], line({ quantity: 2 }));
    const twice = addLine(once, line({ quantity: 2 }));
    assert.equal(twice.length, 1);
    assert.equal(twice[0]?.quantity, 4);

    const overfilled = addLine(twice, line({ quantity: 5 }));
    assert.equal(overfilled[0]?.quantity, MAX_LINE_QUANTITY);
  });

  it('keeps different variants apart and reports count and subtotal', () => {
    const cart = addLine(addLine([], line()), line({ variantId: 'v2', size: 'L', quantity: 3 }));
    assert.equal(cart.length, 2);
    assert.equal(cartCount(cart), 4);
    assert.equal(cartSubtotal(cart), 2_450_000 * 4);
  });

  it('sets an absolute quantity, removes on zero, and caps above the maximum', () => {
    const cart = addLine([], line());
    assert.equal(setLineQuantity(cart, 'v1', 3)[0]?.quantity, 3);
    assert.equal(setLineQuantity(cart, 'v1', 99)[0]?.quantity, MAX_LINE_QUANTITY);
    assert.deepEqual(setLineQuantity(cart, 'v1', 0), []);
    assert.deepEqual(removeLine(cart, 'v1'), []);
    assert.deepEqual(setLineQuantity(cart, 'v1', 1.5), [], 'a fractional quantity removes the line');
  });
});

describe('cart persistence is fail-closed (§3.2)', () => {
  it('round-trips a valid cart', () => {
    const cart = addLine([], line({ quantity: 2 }));
    assert.deepEqual(parseStoredCart(serializeCart(cart)), cart);
  });

  it('yields an empty cart for absent, empty, non-JSON, or non-array storage', () => {
    assert.deepEqual(parseStoredCart(null), []);
    assert.deepEqual(parseStoredCart(''), []);
    assert.deepEqual(parseStoredCart('{not json'), []);
    assert.deepEqual(parseStoredCart('{"variantId":"v1"}'), []);
    assert.deepEqual(parseStoredCart('"a string"'), []);
  });

  it('drops only the malformed lines and keeps the rest', () => {
    const good = line();
    const stored = JSON.stringify([
      good,
      { ...good, variantId: '' },
      { ...good, variantId: 'v2', unitPrice: -5 },
      { ...good, variantId: 'v3', colorHex: 'not-a-hex' },
      { ...good, variantId: 'v4', quantity: 'two' },
      null,
      'nope',
    ]);
    const parsed = parseStoredCart(stored);
    assert.equal(parsed.length, 1);
    assert.equal(parsed[0]?.variantId, 'v1');
  });

  it('clamps a stored quantity into range rather than trusting it', () => {
    const parsed = parseStoredCart(JSON.stringify([line({ quantity: 999 })]));
    assert.equal(parsed[0]?.quantity, MAX_LINE_QUANTITY);

    const negatives = parseStoredCart(JSON.stringify([line({ quantity: -3 })]));
    assert.equal(negatives[0]?.quantity, 1, 'a nonsense quantity becomes the smallest valid one');
  });

  it('collapses duplicate variants left behind by an older version', () => {
    const parsed = parseStoredCart(JSON.stringify([line({ quantity: 1 }), line({ quantity: 2 })]));
    assert.equal(parsed.length, 1);
    assert.equal(parsed[0]?.quantity, 3);
  });

  it('keeps a price cap: a stored price is display data, never authority', () => {
    // A hand-edited price parses (the shape is valid) but is only ever rendered;
    // the write path re-resolves every price from the SSOT.
    const parsed = parseStoredCart(JSON.stringify([line({ unitPrice: 1 })]));
    assert.equal(parsed[0]?.unitPrice, 1);
    assert.equal(cartSubtotal(parsed), 1);
  });
});
