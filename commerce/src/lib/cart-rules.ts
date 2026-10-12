import type { CartLine } from '@/contracts/storefront';
import { MAX_DISTINCT_LINES, MAX_LINE_QUANTITY } from '@/lib/checkout-rules';
import { isHexColor, isMoney, isNonEmptyString } from '@/lib/validation';

/**
 * D-172 §3.2 — the client cart, as a PURE module.
 *
 * The cart lives in `localStorage` (the roadmap asks for a persistent cart) and
 * is therefore UNTRUSTED INPUT on the way back in: anything in that key could
 * have been written by an older version of this code, by another tab, or by
 * hand. `parseStoredCart` is consequently fail-closed — it drops malformed
 * lines instead of throwing, and a corrupt blob yields an empty cart rather
 * than a crashed page.
 *
 * The stored PRICES are for display only and are never trusted: the server
 * re-resolves every price, coupon and stock level inside the order transaction.
 * The cart also carries no customer data — phone, name and address are typed
 * once at checkout and are never persisted in client storage (D-114/D-124).
 */

export const CART_STORAGE_KEY = 'commerce.cart.v1';

function asLine(value: unknown): CartLine | null {
  if (typeof value !== 'object' || value === null) {
    return null;
  }
  const candidate = value as Record<string, unknown>;

  if (!isNonEmptyString(candidate.variantId) || !isNonEmptyString(candidate.productSlug)) {
    return null;
  }
  if (!isNonEmptyString(candidate.productTitle)) {
    return null;
  }
  if (typeof candidate.size !== 'string' || typeof candidate.colorName !== 'string') {
    return null;
  }
  if (typeof candidate.colorHex !== 'string' || !isHexColor(candidate.colorHex)) {
    return null;
  }
  if (typeof candidate.unitPrice !== 'number' || !isMoney(candidate.unitPrice)) {
    return null;
  }
  if (typeof candidate.quantity !== 'number' || !Number.isInteger(candidate.quantity)) {
    return null;
  }
  const quantity = Math.min(Math.max(candidate.quantity, 1), MAX_LINE_QUANTITY);
  const imageUrl =
    typeof candidate.imageUrl === 'string' && candidate.imageUrl.length > 0
      ? candidate.imageUrl
      : null;

  return {
    variantId: candidate.variantId,
    productSlug: candidate.productSlug,
    productTitle: candidate.productTitle,
    size: candidate.size,
    colorName: candidate.colorName,
    colorHex: candidate.colorHex,
    unitPrice: candidate.unitPrice,
    quantity,
    imageUrl,
  };
}

/** Never throws: malformed storage is an empty cart, not a broken page. */
export function parseStoredCart(raw: string | null): CartLine[] {
  if (raw === null || raw.length === 0) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    const lines = parsed
      .map(asLine)
      .filter((line): line is CartLine => line !== null)
      .slice(0, MAX_DISTINCT_LINES);

    // Collapse duplicates that an older version (or a second tab) may have left
    // behind, so the same variant can never occupy two lines.
    return lines.reduce<CartLine[]>((acc, line) => addLine(acc, line), []);
  } catch {
    return [];
  }
}

export function serializeCart(lines: CartLine[]): string {
  return JSON.stringify(lines);
}

/** Adds a line, merging with an existing row for the same variant. */
export function addLine(lines: CartLine[], line: CartLine, maxQuantity = MAX_LINE_QUANTITY): CartLine[] {
  const existing = lines.find((entry) => entry.variantId === line.variantId);
  if (existing) {
    return lines.map((entry) =>
      entry.variantId === line.variantId
        ? { ...entry, quantity: Math.min(entry.quantity + line.quantity, maxQuantity) }
        : entry,
    );
  }
  if (lines.length >= MAX_DISTINCT_LINES) {
    return lines;
  }
  return [...lines, { ...line, quantity: Math.min(Math.max(line.quantity, 1), maxQuantity) }];
}

/** Sets an absolute quantity; 0 (or less) removes the line. */
export function setLineQuantity(lines: CartLine[], variantId: string, quantity: number): CartLine[] {
  if (!Number.isInteger(quantity) || quantity <= 0) {
    return removeLine(lines, variantId);
  }
  const capped = Math.min(quantity, MAX_LINE_QUANTITY);
  return lines.map((entry) =>
    entry.variantId === variantId ? { ...entry, quantity: capped } : entry,
  );
}

export function removeLine(lines: CartLine[], variantId: string): CartLine[] {
  return lines.filter((entry) => entry.variantId !== variantId);
}

export function cartCount(lines: CartLine[]): number {
  return lines.reduce((total, line) => total + line.quantity, 0);
}

/** Display-only subtotal; the authoritative total is computed server-side. */
export function cartSubtotal(lines: CartLine[]): number {
  return lines.reduce((total, line) => total + line.unitPrice * line.quantity, 0);
}
