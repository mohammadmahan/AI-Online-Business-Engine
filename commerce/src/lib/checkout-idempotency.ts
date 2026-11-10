/**
 * D-172 §3.3 — browser-owned checkout intent identity.
 *
 * One intent is one `idempotencyKey`. A transport retry or a page reload with
 * the SAME cart, recipient, coupon and shipping choice reuses the key; any
 * deliberate change rotates it. The server never derives this key: it only
 * enforces that one key names at most one order.
 *
 * Kept free of React and of the browser globals so the lifecycle can be unit
 * tested with an injected storage and UUID generator.
 */

export const CHECKOUT_IDEMPOTENCY_STORAGE_KEY = 'commerce.checkout.idempotency.v1';

export interface CheckoutIntent {
  lines: ReadonlyArray<{ variantId: string; quantity: number }>;
  customer: {
    fullName: string;
    phoneNumber: string;
    address: string;
    postalCode: string;
  };
  couponCode: string | null;
  shippingMethodId: string;
}

export interface CheckoutIdempotencyRecord {
  fingerprint: string;
  key: string;
}

/** The small slice of `sessionStorage` this module needs (injectable in tests). */
export interface CheckoutKeyStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Canonical description of the intent. Line order is irrelevant (the cart is a
 * set of variant/quantity pairs); text is trimmed and the coupon is normalised
 * exactly as the server will normalise it, so cosmetic whitespace does not
 * rotate the key while a real edit does.
 */
export function checkoutIntentFingerprint(intent: CheckoutIntent): string {
  return JSON.stringify({
    lines: [...intent.lines]
      .map((line) => ({ variantId: line.variantId, quantity: line.quantity }))
      .sort((a, b) =>
        a.variantId === b.variantId
          ? a.quantity - b.quantity
          : a.variantId.localeCompare(b.variantId),
      ),
    customer: {
      fullName: intent.customer.fullName.trim(),
      phoneNumber: intent.customer.phoneNumber.trim(),
      address: intent.customer.address.trim(),
      postalCode: intent.customer.postalCode.trim(),
    },
    couponCode: intent.couponCode?.trim().toUpperCase() ?? null,
    shippingMethodId: intent.shippingMethodId,
  });
}

function readRecord(storage: CheckoutKeyStorage): CheckoutIdempotencyRecord | null {
  try {
    const raw = storage.getItem(CHECKOUT_IDEMPOTENCY_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      typeof (parsed as CheckoutIdempotencyRecord).fingerprint !== 'string' ||
      typeof (parsed as CheckoutIdempotencyRecord).key !== 'string' ||
      !UUID_PATTERN.test((parsed as CheckoutIdempotencyRecord).key)
    ) {
      return null;
    }
    return parsed as CheckoutIdempotencyRecord;
  } catch {
    // Corrupt JSON or a blocked storage (private mode) must never block checkout.
    return null;
  }
}

/**
 * Returns the key for this exact intent, reusing the stored one when the
 * fingerprint still matches, otherwise creating (and best-effort persisting) a
 * fresh key. Storage failures degrade to a per-submission key, never a refusal.
 */
export function checkoutIdempotencyKey(
  intent: CheckoutIntent,
  storage: CheckoutKeyStorage,
  createKey: () => string = () => crypto.randomUUID(),
): string {
  const fingerprint = checkoutIntentFingerprint(intent);
  const stored = readRecord(storage);
  if (stored && stored.fingerprint === fingerprint) {
    return stored.key;
  }

  const key = createKey();
  try {
    storage.setItem(CHECKOUT_IDEMPOTENCY_STORAGE_KEY, JSON.stringify({ fingerprint, key }));
  } catch {
    // A full/blocked storage only loses cross-submission reuse; this submission
    // still carries a valid key, so the server's uniqueness guard still holds.
  }
  return key;
}

/** Called once an order is confirmed (including an idempotent replay). */
export function clearCheckoutIdempotencyKey(storage: CheckoutKeyStorage): void {
  try {
    storage.removeItem(CHECKOUT_IDEMPOTENCY_STORAGE_KEY);
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}
