import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  CHECKOUT_IDEMPOTENCY_STORAGE_KEY,
  checkoutIdempotencyKey,
  checkoutIntentFingerprint,
  clearCheckoutIdempotencyKey,
  type CheckoutIntent,
  type CheckoutKeyStorage,
} from '@/lib/checkout-idempotency';

/**
 * D-172 §3.3 — the client half of checkout idempotency.
 *
 * A retry must reuse the key, a deliberate edit must rotate it, and broken
 * storage must never stop checkout from submitting.
 */

function memoryStorage(initial: Record<string, string> = {}): CheckoutKeyStorage & {
  values: Map<string, string>;
} {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
    removeItem: (key) => {
      values.delete(key);
    },
  };
}

function intent(overrides: Partial<CheckoutIntent> = {}): CheckoutIntent {
  return {
    lines: [{ variantId: 'v1', quantity: 2 }],
    customer: {
      fullName: 'سارا احمدی',
      phoneNumber: '09121234567',
      address: 'خیابان ولیعصر ۱',
      postalCode: '1234567890',
    },
    couponCode: null,
    shippingMethodId: 'POST',
    ...overrides,
  };
}

function counter(): () => string {
  let next = 0;
  return () => {
    next += 1;
    return `00000000-0000-4000-8000-${String(next).padStart(12, '0')}`;
  };
}

describe('checkout idempotency key lifecycle', () => {
  it('reuses the key for an identical intent, including cart line order', () => {
    const storage = memoryStorage();
    const createKey = counter();
    const first = checkoutIdempotencyKey(
      intent({
        lines: [
          { variantId: 'v2', quantity: 1 },
          { variantId: 'v1', quantity: 2 },
        ],
      }),
      storage,
      createKey,
    );

    const retry = checkoutIdempotencyKey(
      intent({
        lines: [
          { variantId: 'v1', quantity: 2 },
          { variantId: 'v2', quantity: 1 },
        ],
      }),
      storage,
      createKey,
    );

    assert.equal(retry, first);
    assert.equal(
      checkoutIntentFingerprint(intent({ lines: [{ variantId: 'v1', quantity: 2 }] })),
      checkoutIntentFingerprint(intent({ lines: [{ variantId: 'v1', quantity: 2 }] })),
    );
  });

  it('rotates after a cart, recipient, coupon or shipping change', () => {
    const storage = memoryStorage();
    const createKey = counter();
    const first = checkoutIdempotencyKey(intent(), storage, createKey);

    const edits: CheckoutIntent[] = [
      intent({ lines: [{ variantId: 'v1', quantity: 3 }] }),
      intent({ customer: { ...intent().customer, address: 'خیابان دیگری' } }),
      intent({ customer: { ...intent().customer, phoneNumber: '09120000000' } }),
      intent({ couponCode: 'LIVE25' }),
      intent({ shippingMethodId: 'PICKUP' }),
    ];

    for (const edited of edits) {
      const next = checkoutIdempotencyKey(edited, storage, createKey);
      assert.notEqual(next, first);
      // The newly stored key is then stable for that edited intent.
      assert.equal(checkoutIdempotencyKey(edited, storage, createKey), next);
    }
  });

  it('normalises cosmetic text and coupon case without rotating', () => {
    const storage = memoryStorage();
    const createKey = counter();
    const first = checkoutIdempotencyKey(intent({ couponCode: ' live25 ' }), storage, createKey);
    const retry = checkoutIdempotencyKey(
      intent({
        couponCode: 'LIVE25',
        customer: { ...intent().customer, fullName: '  سارا احمدی  ' },
      }),
      storage,
      createKey,
    );
    assert.equal(retry, first);
  });

  it('creates a fresh key from corrupt storage instead of failing', () => {
    const storage = memoryStorage({ [CHECKOUT_IDEMPOTENCY_STORAGE_KEY]: '{not-json' });
    const key = checkoutIdempotencyKey(intent(), storage, counter());
    assert.match(key, /^[0-9a-f-]{36}$/);
    assert.ok(storage.values.has(CHECKOUT_IDEMPOTENCY_STORAGE_KEY));
  });

  it('still submits when storage is unavailable', () => {
    const blocked: CheckoutKeyStorage = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    };
    const key = checkoutIdempotencyKey(intent(), blocked, counter());
    assert.equal(key, '00000000-0000-4000-8000-000000000001');
    assert.doesNotThrow(() => clearCheckoutIdempotencyKey(blocked));
  });

  it('clears the stored intent once an order is confirmed', () => {
    const storage = memoryStorage();
    const createKey = counter();
    const first = checkoutIdempotencyKey(intent(), storage, createKey);
    clearCheckoutIdempotencyKey(storage);
    assert.equal(storage.values.size, 0);

    const afterOrder = checkoutIdempotencyKey(intent(), storage, createKey);
    assert.notEqual(afterOrder, first);
  });
});
