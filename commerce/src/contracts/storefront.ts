import type { DiscountType } from './promotions';

/**
 * D-172 Phase 3 — the storefront's read models and checkout contract.
 *
 * These are DELIBERATELY narrower than the admin read models in
 * `@/server/repository`. The storefront is the public surface, so:
 *
 * - raw stock **quantities never leave the server**: a variant exposes a LEVEL
 *   (`IN` / `LOW` / `OUT`), and the availability rules live in one place
 *   (`@/lib/inventory-rules`) so the storefront badge and the merchant panel
 *   can never disagree about what "low" means;
 * - only `PUBLISHED` products are readable (DRAFT and ARCHIVED are never
 *   rendered, never counted, never linked);
 * - customer PII is collected only at checkout, sent once, and never stored in
 *   client storage or a URL (D-114/D-124).
 *
 * Money is integer Iranian Toman (D-010) end to end; nothing here computes a
 * price, it only describes the shapes the write path and the UI agree on.
 */

export type StockLevel = 'IN' | 'LOW' | 'OUT';

/** A colour as the catalog stores it (data, never a design token). */
export interface ColorSwatch {
  name: string;
  hex: string;
}

export interface StorefrontVariantView {
  variantId: string;
  size: string;
  colorName: string;
  colorHex: string;
  level: StockLevel;
  /** `price_override ?? base_price` — resolved on the server (D-024). */
  effectivePrice: number;
}

/** Grid/carousel card. Carries no quantities, no cost, no draft state. */
export interface StorefrontProductCard {
  id: string;
  slug: string;
  title: string;
  categoryName: string;
  basePrice: number;
  discountPrice: number | null;
  effectivePrice: number;
  hasDiscount: boolean;
  primaryImageUrl: string | null;
  imageUrls: string[];
  sizes: string[];
  colors: ColorSwatch[];
  availability: 'IN' | 'OUT';
  createdAt: Date;
}

/**
 * One gallery image.
 *
 * `variantId` is set when the merchant bound the photo to a colour, which is
 * what lets the PDP's colour selector swap the primary preview. Phase 2's
 * uploader does NOT create that binding yet (media ↔ variant binding is open,
 * D-172 G-5), so `null` is the normal case and means "this photo belongs to the
 * product, not to one colour".
 */
export interface StorefrontImageRef {
  url: string;
  variantId: string | null;
}

/** PDP read model: everything a product page renders, nothing it must not. */
export interface StorefrontProductDetail extends StorefrontProductCard {
  /**
   * The merchant's plain-text copy, as stored.
   *
   * The storefront renders THIS, escaped as paragraphs, and deliberately not
   * `descriptionHtml`: that column is accepted verbatim from the merchant form
   * (it is the AI copy hub's target in Phase 4), and publishing merchant HTML to
   * customers would need a sanitizer this phase does not have. A raw string
   * rendered by React cannot inject markup.
   */
  descriptionRaw: string;
  descriptionHtml: string;
  fabricType: string;
  season: string;
  careInstructions: string | null;
  /** Gallery in display order (primary first); colour-bound photos included. */
  images: StorefrontImageRef[];
  variants: StorefrontVariantView[];
}

/* ---------------------------------------------------------------- §3.2 facets */

export interface CatalogFilters {
  /** `categoryName` of the published card, or `null` for the whole catalog. */
  category: string | null;
  sizes: string[];
  colors: string[];
  minPrice: number | null;
  maxPrice: number | null;
  onlyAvailable: boolean;
  query: string;
  sort: CatalogSort;
}

export type CatalogSort = 'newest' | 'price-asc' | 'price-desc';

export const EMPTY_CATALOG_FILTERS: CatalogFilters = {
  category: null,
  sizes: [],
  colors: [],
  minPrice: null,
  maxPrice: null,
  onlyAvailable: false,
  query: '',
  sort: 'newest',
};

/* ---------------------------------------------------------------- §3.4 checkout */

/** One cart line as the browser stores it. Prices are for DISPLAY only. */
export interface CartLine {
  variantId: string;
  productSlug: string;
  productTitle: string;
  size: string;
  colorName: string;
  colorHex: string;
  /** Display price at the time the line was added; the server re-resolves it. */
  unitPrice: number;
  quantity: number;
  imageUrl: string | null;
}

/** What the checkout form submits. No prices, no totals — those are server-side. */
export interface CheckoutDraft {
  customer: {
    fullName: string;
    phoneNumber: string;
    address: string;
    postalCode: string;
  };
  /** Optional coupon code; eligibility is re-checked against the SSOT. */
  couponCode: string | null;
  shippingMethodId: string;
  lines: Array<{ variantId: string; quantity: number }>;
}

/**
 * Per-line answer of the optimistic pre-flight check (§3.3).
 *
 * One entry is returned per REQUESTED line, always in request order. When a
 * variant no longer exists (or its product was unpublished) the entry carries
 * `level: 'OUT'`, `available: false`, EMPTY display fields and
 * `effectivePrice: null` — never a guessed price or a fabricated title. The
 * drawer keeps showing the customer's own label for that line and marks it
 * unavailable.
 */
export interface CartAvailabilityLine {
  variantId: string;
  productTitle: string;
  size: string;
  colorName: string;
  level: StockLevel;
  /** True only when the requested QUANTITY is on hand and sellable. */
  available: boolean;
  /** Server-resolved price, so the drawer can correct a stale client price. */
  effectivePrice: number | null;
}

export interface CheckoutTotals {
  subtotal: number;
  discount: number;
  shipping: number;
  total: number;
}

/** Standard status vocabulary every payment adapter must speak (§3.4, AC-8). */
export type PaymentStatus = 'AUTHORIZED' | 'DECLINED' | 'UNAVAILABLE';

export interface PaymentAttempt {
  status: PaymentStatus;
  /** Machine code, never a provider secret or a PAN (D-114/D-124). */
  code: string;
  /** Persian explanation shown to the customer / merchant. */
  message: string;
  /** Present only for an AUTHORIZED attempt. */
  reference: string | null;
}

export interface OrderPlaced {
  ok: true;
  orderId: string;
  totals: CheckoutTotals;
  payment: PaymentAttempt;
  /** True when the coupon was accepted AND its usage counter was incremented. */
  couponApplied: boolean;
  /** `PENDING` unless a gateway actually authorized (never faked — AC-8). */
  status: 'PENDING';
}

export interface OrderRefused {
  ok: false;
  code:
    | 'DB_NOT_CONFIGURED'
    | 'VALIDATION_ERROR'
    | 'EMPTY_CART'
    | 'VARIANT_UNAVAILABLE'
    | 'STOCK_INSUFFICIENT'
    | 'COUPON_INVALID'
    | 'SHIPPING_UNKNOWN'
    | 'UNEXPECTED';
  message: string;
  field?: string;
  variantId?: string;
}

export type PlaceOrderResult = OrderPlaced | OrderRefused;

/** Coupon row data the eligibility rule needs; keeps the rule pure. */
export interface CouponRuleInput {
  id: string;
  code: string;
  discountType: DiscountType;
  discountValue: number;
  minSpend: number;
  expiresAt: Date | null;
  usageLimit: number | null;
  usedCount: number;
  isActive: boolean;
}

export interface ShippingMethod {
  id: string;
  label: string;
  /** Integer Toman added to the order (0 = paid to the carrier on delivery). */
  amount: number;
  description: string;
}
