import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { CartLine } from '@/contracts/storefront';
import { CART_STORAGE_KEY } from '@/lib/cart-rules';
import {
  addCartLine,
  clearCart,
  getCartSnapshot,
  getServerCartSnapshot,
  removeCartLine,
  setCartLineQuantity,
  subscribeToCart,
} from '@/lib/cart-store';

/**
 * D-172 §3.2 — the cart store, as `useSyncExternalStore` sees it.
 *
 * The store is a singleton bound to a process-global key, so these tests run in
 * one deliberate sequence: the first subscription performs the ONLY adoption of
 * a pre-seeded basket, and every later read is driven through a mutation or
 * through the cross-tab `storage` event. That is also the honest order, because
 * a real page mount is exactly one adoption and then events.
 *
 * What is asserted is the contract React depends on: the server snapshot is
 * empty, stable and never the live one; every published snapshot is the PARSER's
 * output rather than the raw blob; and every write is visible in storage so a
 * reload reproduces it.
 */

type StorageListener = (event: { key: string | null }) => void;

const store = new Map<string, string>();
const listeners = new Map<string, StorageListener[]>();

const stubWindow = {
  localStorage: {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  },
  addEventListener: (type: string, handler: StorageListener) => {
    listeners.set(type, [...(listeners.get(type) ?? []), handler]);
  },
};

(globalThis as unknown as { window: unknown }).window = stubWindow;

/** A write performed by another tab, delivered as the browser would deliver it. */
function otherTabWrites(key: string | null, value: string | null): void {
  if (key === null) {
    store.clear();
  } else if (value === null) {
    store.delete(key);
  } else {
    store.set(key, value);
  }
  for (const handler of listeners.get('storage') ?? []) {
    handler({ key });
  }
}

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

describe('cart store (§3.2)', () => {
  it('offers an empty, stable server snapshot that is never the live one', () => {
    const first = getServerCartSnapshot();
    assert.deepEqual(first, { lines: [], hydrated: false });
    assert.equal(getServerCartSnapshot(), first, 'React compares identities; it must be one object');
  });

  it('adopts the stored basket on the first subscription, through the parser', () => {
    // Written by an older version: a duplicate row and a quantity above the cap.
    store.set(
      CART_STORAGE_KEY,
      JSON.stringify([
        line({ quantity: 2 }),
        line({ quantity: 999 }),
        { variantId: '', productSlug: 'x' },
      ]),
    );

    const unsubscribe = subscribeToCart(() => {});
    const snapshot = getCartSnapshot();

    assert.equal(snapshot.hydrated, true);
    assert.equal(snapshot.lines.length, 1, 'the malformed line is dropped, the duplicate merged');
    assert.equal(snapshot.lines[0]?.variantId, 'v1');
    assert.equal(snapshot.lines[0]?.quantity, 5, 'the stored quantity is clamped, never trusted');
    assert.notEqual(snapshot, getServerCartSnapshot());
    unsubscribe();
  });

  it('publishes mutations to subscribers and persists the parsed basket', () => {
    let notifications = 0;
    const unsubscribe = subscribeToCart(() => {
      notifications += 1;
    });

    addCartLine(line({ quantity: 2 }));
    assert.equal(notifications, 1);
    assert.equal(getCartSnapshot().lines[0]?.quantity, 5, 'adding merges with the capped line');

    setCartLineQuantity('v1', 3);
    assert.equal(getCartSnapshot().lines[0]?.quantity, 3);
    assert.deepEqual(
      JSON.parse(store.get(CART_STORAGE_KEY) ?? 'null'),
      getCartSnapshot().lines,
      'what a reload would read back is exactly what was published',
    );

    addCartLine(line({ variantId: 'v2', size: 'L' }));
    assert.equal(getCartSnapshot().lines.length, 2);

    setCartLineQuantity('v2', 0);
    assert.equal(getCartSnapshot().lines.length, 1, 'zero removes the line');
    removeCartLine('v1');
    assert.deepEqual(getCartSnapshot().lines, []);
    assert.equal(notifications, 5, 'every mutation notifies, including the ones that ended empty');

    unsubscribe();
    const settled = notifications;
    addCartLine(line());
    assert.equal(notifications, settled, 'an unsubscribed listener is not called again');
    clearCart();
    assert.deepEqual(getCartSnapshot().lines, []);
    assert.equal(store.get(CART_STORAGE_KEY), '[]');
  });

  it('adopts another tab’s basket from the storage event, and ignores unrelated keys', () => {
    otherTabWrites('some.other.key', 'noise');
    assert.deepEqual(getCartSnapshot().lines, [], 'an unrelated key is not our business');

    const theirs = [line({ variantId: 'v9', quantity: 2 })];
    otherTabWrites(CART_STORAGE_KEY, JSON.stringify(theirs));
    assert.deepEqual(getCartSnapshot().lines, theirs, 'the other tab’s basket wins; it is the same store');

    otherTabWrites(null, null);
    assert.deepEqual(getCartSnapshot().lines, [], 'a full clear empties our basket too');
    assert.equal(getCartSnapshot().hydrated, true);
  });

  it('degrades a hand-edited blob to an empty cart instead of throwing', () => {
    otherTabWrites(CART_STORAGE_KEY, '{ half written');
    const snapshot = getCartSnapshot();
    assert.deepEqual(snapshot.lines, []);
    assert.equal(snapshot.hydrated, true);

    otherTabWrites(CART_STORAGE_KEY, '"a string"');
    assert.deepEqual(getCartSnapshot().lines, []);

    clearCart();
    assert.equal(store.get(CART_STORAGE_KEY), '[]', 'an emptied cart is a real, readable value');
  });
});
