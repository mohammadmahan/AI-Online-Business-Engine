import type {
  CatalogSort,
  PaymentStatus,
  StockLevel,
  StorefrontImageRef,
} from '@/contracts/storefront';
import { MAX_LINE_QUANTITY } from '@/lib/checkout-rules';
import { LOW_STOCK_THRESHOLD } from '@/lib/inventory-rules';

/**
 * D-172 §3 — the storefront's WORDS, in one place.
 *
 * Two vocabularies already exist and must not be confused:
 *
 * - the merchant panel speaks about quantities («موجودی کم» at ≤ 3 units), and
 *   that is a number the owner manages;
 * - the customer surface speaks about LEVELS («موجودی محدود» / «ناموجود»), and
 *   D-172 §3 states that raw quantities never leave the server.
 *
 * This module is the storefront half of that split, plus the payment status
 * wording and the gallery rule. It is pure data and pure functions so the badge
 * the PDP renders and the badge a test asserts cannot drift apart.
 */

export const STOCK_LEVEL_LABELS: Record<StockLevel, string> = {
  IN: 'موجود',
  LOW: 'موجودی محدود',
  OUT: 'ناموجود',
};

export const STOCK_LEVEL_TONE: Record<StockLevel, 'success' | 'warning' | 'danger'> = {
  IN: 'success',
  LOW: 'warning',
  OUT: 'danger',
};

export function stockLevelLabel(level: StockLevel): string {
  return STOCK_LEVEL_LABELS[level];
}

/** A level is sellable when the piece can be shipped today. */
export function isSellableLevel(level: StockLevel): boolean {
  return level !== 'OUT';
}

/**
 * The most pieces a customer may put in the basket for a given level.
 *
 * «موجودی محدود» means the boutique is down to its last few, so the cap follows
 * the same threshold the merchant panel warns at rather than the cart's global
 * ceiling — this reduces (never guarantees) the chance of overselling a last
 * piece, and the write path re-checks the real quantity regardless.
 */
export function quantityCapForLevel(
  level: StockLevel,
  max = MAX_LINE_QUANTITY,
): number {
  if (level === 'OUT') {
    return 0;
  }
  return level === 'LOW' ? Math.min(LOW_STOCK_THRESHOLD, max) : max;
}

export const PAYMENT_STATUS_LABELS: Record<PaymentStatus, string> = {
  AUTHORIZED: 'پرداخت تأیید شد',
  DECLINED: 'پرداخت تأیید نشد',
  UNAVAILABLE: 'درگاه پرداخت متصل نیست',
};

export const PAYMENT_STATUS_TONE: Record<PaymentStatus, 'success' | 'warning' | 'danger'> = {
  AUTHORIZED: 'success',
  DECLINED: 'danger',
  UNAVAILABLE: 'warning',
};

export const CATALOG_SORT_OPTIONS: Array<{ value: CatalogSort; label: string }> = [
  { value: 'newest', label: 'جدیدترین' },
  { value: 'price-asc', label: 'ارزان‌ترین' },
  { value: 'price-desc', label: 'گران‌ترین' },
];

export const CHECKOUT_TOTAL_LABELS = {
  subtotal: 'جمع کالاها',
  discount: 'تخفیف',
  shipping: 'هزینهٔ ارسال',
  total: 'مبلغ قابل پرداخت',
} as const;

/**
 * The gallery a colour shows (§3.3 "dynamic colour selector updating primary
 * image preview").
 *
 * Photos bound to one of this colour's variants come first, unbound photos (the
 * product's general gallery) follow, and the original order is preserved so the
 * primary image stays primary. When the product has colour-tagged photos but
 * none for the selected colour, the whole gallery is shown — an empty gallery
 * would read as a broken page, and a product photo is not a false claim about
 * this colour the way an invented one would be.
 */
export function galleryForColor(
  refs: StorefrontImageRef[],
  colorVariantIds: string[],
): StorefrontImageRef[] {
  const mine = new Set(colorVariantIds);
  const visible = refs.filter((ref) => ref.variantId === null || mine.has(ref.variantId));
  return visible.length > 0 ? visible : refs;
}
