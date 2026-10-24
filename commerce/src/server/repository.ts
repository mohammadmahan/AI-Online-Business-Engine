import { and, asc, desc, eq, gte, inArray, lt, lte, ne, or, sql } from 'drizzle-orm';

import type {
  CartAvailabilityLine,
  CheckoutTotals,
  ColorSwatch,
  StockLevel,
  StorefrontImageRef,
  StorefrontProductCard,
  StorefrontProductDetail,
  StorefrontVariantView,
} from '@/contracts/storefront';
import type { CommerceDb } from '@/db';
import { sortSizes } from '@/lib/catalog-filters';
import { computeCheckoutTotals, evaluateCoupon } from '@/lib/checkout-rules';
import { stockLevelFor } from '@/lib/inventory-rules';
import {
  MAX_SMS_ATTEMPTS,
  NOTIFICATION_LEASE_MS,
  orderReference,
  type OrderNotificationChannel,
  type OrderNotificationKind,
} from '@/lib/notification-rules';
import { shippingAmountFor } from '@/lib/shipping';
import { normalizePhoneNumber, normalizePostalCode } from '@/lib/validation';
import {
  categories,
  coupons,
  customers,
  notificationOutbox,
  orderItems,
  orderStatusHistory,
  orders,
  productImages,
  productVariants,
  products,
} from '@/db/schema';
import type {
  DiscountType,
  NotificationStatus,
  OrderStatus,
  OrderStatusSource,
  ProductStatus,
} from '@/db/schema';

/**
 * D-172 Phase 2 — the single persistence seam of the merchant admin.
 *
 * Everything above this file (services, server actions, UI) talks to this
 * interface and never to Drizzle directly. Two consequences that matter:
 *
 *  - the service layer is a pure function of an injected repository, so the
 *    business rules are unit-testable with no database at all
 *    (`src/server/repository-memory.ts` is the test double);
 *  - the Postgres implementation is the only place that knows the schema, so a
 *    schema change lands in exactly one file.
 *
 * Read models below are DISPLAY aggregates (a product with its counts, an order
 * with its lines). They are deliberately not in `src/contracts/` — that module
 * is the persisted entity contract, this one is the admin's view of it.
 */

export interface ProductListItem {
  id: string;
  title: string;
  slug: string;
  status: ProductStatus;
  basePrice: number;
  discountPrice: number | null;
  variantCount: number;
  imageCount: number;
}

export interface InventoryRow {
  variantId: string;
  productId: string;
  productTitle: string;
  productSlug: string;
  sku: string;
  size: string;
  colorName: string;
  colorHex: string;
  stockQuantity: number;
  priceOverride: number | null;
  basePrice: number;
  isActive: boolean;
}

export interface OrderListItem {
  id: string;
  customerName: string;
  customerPhone: string;
  status: OrderStatus;
  totalAmount: number;
  discountAmount: number;
  shippingAmount: number;
  trackingCode: string | null;
  itemCount: number;
  createdAt: Date;
}

export interface OrderItemView {
  id: string;
  sku: string;
  productTitle: string;
  size: string;
  colorName: string;
  quantity: number;
  unitPrice: number;
}

export interface OrderDetail extends OrderListItem {
  shippingAddress: string;
  postalCode: string;
  paymentRefId: string | null;
  items: OrderItemView[];
}

/**
 * D-172 Phase 4 transition — one row of the order's audit trail, as read back.
 *
 * `fromStatus` is `null` only for the row that records the order's CREATION,
 * which is why the field is nullable rather than defaulted to the first status:
 * "there was nothing before this" and "it was PENDING before this" are different
 * facts, and an operator reading the trail needs to tell them apart.
 */
export interface OrderStatusHistoryEntry {
  id: string;
  orderId: string;
  fromStatus: OrderStatus | null;
  toStatus: OrderStatus;
  source: OrderStatusSource;
  /** Transition facts with no column of their own; never customer PII. */
  metadata: Record<string, unknown> | null;
  createdAt: Date;
}

/**
 * WHO is asking for a transition, and anything else worth recording with it.
 *
 * Required on every write that moves an order: the alternative — defaulting the
 * actor — would silently attribute a machine's transition to the merchant panel,
 * which is precisely the fact an audit trail exists to get right. `metadata` is
 * free-form because what is worth recording depends on the caller (a gateway
 * reference, a provider event id, a merchant note) and none of it is authority.
 */
export interface OrderTransitionTrigger {
  source: OrderStatusSource;
  metadata?: Record<string, unknown> | null;
}

/**
 * Thrown when the conditional stock decrement finds less stock than the locked
 * rows promised. It exists so a partial decrement can never commit: the throw
 * aborts the transaction, and `placeOrder` catches it OUTSIDE the transaction
 * and turns it into the ordinary `STOCK_INSUFFICIENT` refusal.
 */
class StockConflictError extends Error {
  readonly variantId: string;

  constructor(variantId: string) {
    super('stock was consumed by a concurrent order');
    this.name = 'StockConflictError';
    this.variantId = variantId;
  }
}

export interface NewProductGraph {
  product: {
    categoryId: string;
    title: string;
    slug: string;
    basePrice: number;
    discountPrice: number | null;
    descriptionRaw: string;
    descriptionHtml: string;
    fabricType: string;
    season: string;
    careInstructions: string | null;
    status: ProductStatus;
  };
  variants: Array<{
    sku: string;
    colorName: string;
    colorHex: string;
    size: string;
    stockQuantity: number;
    priceOverride: number | null;
  }>;
  images: Array<{
    variantIndex: number | null;
    storagePath: string;
    publicUrl: string;
    displayOrder: number;
    isPrimary: boolean;
  }>;
}

export interface NewCouponInput {
  code: string;
  discountType: DiscountType;
  discountValue: number;
  minSpend: number;
  expiresAt: Date | null;
  usageLimit: number | null;
  description: string | null;
  isActive: boolean;
}

/* ------------------------------------------------- §3.1–§3.4 storefront rows */

/**
 * The storefront composes its read models from three narrow row shapes, and the
 * MAPPERS below are exported because both implementations (PostgreSQL and the
 * in-memory double) build their cards through them. One definition means the
 * double cannot drift from the real read path — a class of bug the live
 * PostgreSQL pass already caught once (§6 of D-172).
 */
export interface StorefrontHeadRow {
  id: string;
  slug: string;
  title: string;
  categoryName: string;
  basePrice: number;
  discountPrice: number | null;
  createdAt: Date;
}

export interface StorefrontImageRow {
  productId: string;
  publicUrl: string;
  displayOrder: number;
  isPrimary: boolean;
  /** Set only when the photo is bound to a colour (see `StorefrontImageRef`). */
  variantId: string | null;
}

export interface StorefrontVariantRow {
  variantId: string;
  productId: string;
  size: string;
  colorName: string;
  colorHex: string;
  stockQuantity: number;
  priceOverride: number | null;
  isActive: boolean;
}

/** `discount_price ?? base_price`, which is the price the card advertises. */
export function productEffectivePrice(head: {
  basePrice: number;
  discountPrice: number | null;
}): number {
  return head.discountPrice ?? head.basePrice;
}

/** Primary first, then display order — the gallery contract §3.3 relies on. */
export function orderImages(rows: StorefrontImageRow[]): StorefrontImageRow[] {
  return [...rows].sort((left, right) => {
    if (left.isPrimary !== right.isPrimary) {
      return left.isPrimary ? -1 : 1;
    }
    return left.displayOrder - right.displayOrder;
  });
}

/**
 * Gallery references for the PDP, in the same order the card's `imageUrls` use.
 * A repeated public URL is kept once (the first occurrence wins), so the gallery
 * never shows the same photo twice with two different colour bindings.
 */
export function toImageRefs(rows: StorefrontImageRow[]): StorefrontImageRef[] {
  const seen = new Set<string>();
  const refs: StorefrontImageRef[] = [];
  for (const row of orderImages(rows)) {
    if (seen.has(row.publicUrl)) {
      continue;
    }
    seen.add(row.publicUrl);
    refs.push({ url: row.publicUrl, variantId: row.variantId });
  }
  return refs;
}

export function toVariantView(
  row: StorefrontVariantRow,
  productPrice: number,
): StorefrontVariantView {
  return {
    variantId: row.variantId,
    size: row.size,
    colorName: row.colorName,
    colorHex: row.colorHex,
    level: stockLevelFor(row.stockQuantity),
    // D-024: a variant override wins over the product price.
    effectivePrice: row.priceOverride ?? productPrice,
  };
}

/**
 * A card carries a stock LEVEL, never a quantity: the public surface states
 * «ناموجود / موجودی محدود / موجود» and the exact count stays in the panel.
 */
export function toStorefrontCard(
  head: StorefrontHeadRow,
  images: StorefrontImageRow[],
  variants: StorefrontVariantRow[],
): StorefrontProductCard {
  const active = variants.filter((variant) => variant.isActive);
  const ordered = orderImages(images);
  const imageUrls = [...new Set(ordered.map((image) => image.publicUrl))];
  const colors: ColorSwatch[] = [];
  for (const variant of active) {
    if (!colors.some((color) => color.name === variant.colorName)) {
      colors.push({ name: variant.colorName, hex: variant.colorHex });
    }
  }

  return {
    id: head.id,
    slug: head.slug,
    title: head.title,
    categoryName: head.categoryName,
    basePrice: head.basePrice,
    discountPrice: head.discountPrice,
    effectivePrice: productEffectivePrice(head),
    hasDiscount: head.discountPrice !== null && head.discountPrice < head.basePrice,
    primaryImageUrl: imageUrls[0] ?? null,
    imageUrls,
    sizes: sortSizes([...new Set(active.map((variant) => variant.size))]),
    colors,
    availability: active.some((variant) => variant.stockQuantity > 0) ? 'IN' : 'OUT',
    createdAt: head.createdAt,
  };
}

/* ------------------------------------------------------------ §3.4 ordering */

export interface PlaceOrderInput {
  customer: { fullName: string; phoneNumber: string; address: string; postalCode: string };
  shippingAddress: string;
  shippingMethodId: string;
  items: Array<{ variantId: string; quantity: number }>;
  /** Coupon code, already upper-cased by the caller; `null` for none. */
  couponCode: string | null;
  /** Recorded only when a gateway actually authorised (AC-8); `null` otherwise. */
  paymentRefId: string | null;
  /** WHO placed it — the trail's opening row states its origin, not just its status. */
  source: OrderStatusSource;
  /** Optional facts recorded with the opening row (never customer PII). */
  statusMetadata?: Record<string, unknown> | null;
}

export type PlaceOrderWriteResult =
  | {
      ok: true;
      orderId: string;
      customerId: string;
      totals: CheckoutTotals;
      couponApplied: boolean;
      /** The persisted status; the storefront never writes anything but PENDING. */
      status: 'PENDING';
    }
  | {
      ok: false;
      code:
        | 'EMPTY_CART'
        | 'VARIANT_UNAVAILABLE'
        | 'STOCK_INSUFFICIENT'
        | 'COUPON_INVALID'
        | 'SHIPPING_UNKNOWN';
      message: string;
      field?: string;
      variantId?: string;
    };

export interface StorefrontCategory {
  name: string;
  slug: string;
  productCount: number;
}

/**
 * §6.1 — a provider authorisation as it is PERSISTED, read back by the callback.
 *
 * `amount` is integer Toman (D-010): the amount the provider was asked to
 * collect at `authorize()` time, which is exactly what its verify call needs.
 * The record carries the ORDER id because that is the only correlation a
 * redirect callback can be resolved through — there is no client-supplied order
 * id to trust and no in-process map to consult.
 */
export interface PaymentAuthorizationRecord {
  orderId: string;
  provider: string;
  authority: string;
  amount: number;
}

export interface RecordPaymentAuthorizationInput {
  orderId: string;
  provider: string;
  authority: string;
  amount: number;
}

/**
 * §6.2 — what a transition asks to ANNOUNCE, recorded in the same transaction.
 *
 * The type is narrower than a message: it names a KIND and a CHANNEL, both from
 * the closed sets in `@/lib/notification-rules`. Nothing here is a body, a
 * recipient or a provider — those belong to the dispatcher, which is what keeps
 * the payment path free of SMS concerns.
 */
export interface OrderNotificationIntent {
  kind: OrderNotificationKind;
  channel: OrderNotificationChannel;
}

/** §6.2 — one row of the outbox, as read back. */
export interface OrderNotification {
  id: string;
  orderId: string;
  kind: OrderNotificationKind;
  channel: OrderNotificationChannel;
  status: NotificationStatus;
  attempts: number;
  lastError: string | null;
  providerMessageId: string | null;
  payload: Record<string, unknown>;
  nextAttemptAt: Date;
  createdAt: Date;
  updatedAt: Date;
  /** Set exactly when `status` is `SENT` (the schema's own check). */
  sentAt: Date | null;
}

/** §6.2 — a claimed row handed to a dispatcher. The recipient is NOT here. */
export interface NotificationWorkItem {
  id: string;
  orderId: string;
  kind: OrderNotificationKind;
  channel: OrderNotificationChannel;
  /** Attempts INCLUDING the claim that produced this item. */
  attempts: number;
  payload: Record<string, unknown>;
}

export interface CommerceRepository {
  listCategories(): Promise<Array<{ id: string; name: string; slug: string }>>;
  createProductGraph(graph: NewProductGraph): Promise<{ productId: string; variantIds: string[] }>;
  listProducts(): Promise<ProductListItem[]>;
  listInventory(): Promise<InventoryRow[]>;
  updateVariantStock(variantId: string, stockQuantity: number): Promise<boolean>;
  updateVariantPrice(variantId: string, priceOverride: number | null): Promise<boolean>;
  listOrders(): Promise<OrderListItem[]>;
  getOrderDetail(orderId: string): Promise<OrderDetail | null>;

  /**
   * Moves an order's status and APPENDS its audit row in ONE transaction
   * (D-172 Phase 4 transition).
   *
   * Contract, in order of precedence:
   *   - an unknown order                   → `false`, nothing written;
   *   - `status` equal to the current one  → `true`, and NOTHING written: no
   *     second audit row, no second restock. A repeat is a no-op, which is what
   *     makes a retried callback harmless;
   *   - otherwise the previous status is read under a row lock, a cancellation
   *     returns the stock the order consumed (exactly once, §3.4), the order row
   *     moves, and the history row (`from` = the previous status, `source` and
   *     `metadata` from the trigger) is appended — all in the same transaction,
   *     so a status change can never commit without its trail.
   *
   * The lifecycle MAP is not re-implemented here (that is `@/lib/order-rules`,
   * enforced by the service): this is the storage-level guard, and it is the
   * last line of defence for the restock and the trail rather than a second
   * authority on which edges are legal.
   *
   * `notifications` (§6.2) are enqueued IN THE SAME TRANSACTION, after the
   * trail row: a paid order that committed without its announcement is a message
   * no retry would ever send, so the queue entry is part of the same write. The
   * unique `(order_id, kind, channel)` index makes a repeat a no-op — which is
   * why a concurrent duplicate callback cannot produce a second SMS.
   */
  updateOrderStatus(
    orderId: string,
    status: OrderStatus,
    trigger: OrderTransitionTrigger,
    notifications?: OrderNotificationIntent[],
  ): Promise<boolean>;

  /** The order's audit trail, oldest first. Empty when the order is unknown. */
  listOrderStatusHistory(orderId: string): Promise<OrderStatusHistoryEntry[]>;

  /**
   * Records the postal tracking code. Deliberately NOT a status transition, so
   * it writes no audit row: `tracking_code` is an attribute of the parcel, and
   * the roadmap's SMS is triggered by this entry (Phase 6), not by a status.
   */
  updateOrderTracking(orderId: string, trackingCode: string): Promise<boolean>;
  listCoupons(): Promise<Array<typeof coupons.$inferSelect>>;
  findCouponByCode(code: string): Promise<typeof coupons.$inferSelect | null>;
  createCoupon(input: NewCouponInput): Promise<typeof coupons.$inferSelect>;
  setCouponActive(couponId: string, isActive: boolean): Promise<boolean>;

  /* §3.1–§3.3 — storefront reads. PUBLISHED products only, no quantities out. */
  listStorefrontProducts(): Promise<StorefrontProductCard[]>;
  getStorefrontProduct(slug: string): Promise<StorefrontProductDetail | null>;
  listBestSellers(limit: number): Promise<StorefrontProductCard[]>;
  listStorefrontCategories(): Promise<StorefrontCategory[]>;

  /**
   * §3.3 — the optimistic pre-flight read. Returns one line per REQUESTED item
   * (same order), answering whether the requested QUANTITY is on hand; a
   * variant that no longer exists or whose product is unpublished answers
   * `available: false` with no price. Raw quantities never leave this call.
   */
  listVariantAvailability(
    items: Array<{ variantId: string; quantity: number }>,
  ): Promise<CartAvailabilityLine[]>;

  /*
   * §3.4 — the ONE authoritative money path for a storefront order.
   *
   * Everything authoritative happens inside this call: prices, stock, coupon
   * eligibility and the totals are resolved from the SSOT under row locks, and
   * the caller's numbers are never trusted.
   *
   * RESERVATION POLICY — ratified for Phase 3 (D-172 §3.4/§6, G-1/G-2/G-3):
   *   (a) placing an order CONSUMES its stock atomically, in the same
   *       transaction as the order row, so a `PENDING` order always has the
   *       pieces it asked for and the last piece cannot be sold twice;
   *   (b) cancelling an order returns EXACTLY the quantities it consumed, once
   *       — the restock is guarded by the previous status, so a repeated
   *       transition cannot inflate the shelf;
   *   (c) a redeemed coupon is NOT refunded on cancellation: the usage counter
   *       stays where the redemption put it (the conservative direction for a
   *       discount counter).
   * An order can therefore never exist without the stock it reserved, and the
   * merchant's grid reads the SAME rows the storefront just changed.
   */
  placeOrder(input: PlaceOrderInput): Promise<PlaceOrderWriteResult>;

  /**
   * §3.4 / Phase 6.1 — records the gateway's reference on the order. Called only
   * with a reference a gateway actually issued; the order's STATUS is never
   * changed here (a paid transition is Phase 6.1's, not a mock's).
   */
  setOrderPaymentRef(orderId: string, paymentRefId: string): Promise<boolean>;

  /**
   * §6.1 — persists what a redirect-based provider AUTHORISED, against the order
   * it authorised.
   *
   * This is the durable half of the payment seam. A provider's callback carries
   * only its authority, while its verify call requires the amount that was
   * requested — so the pair must survive the process. Storing it on the order
   * (not in a cache) is what makes a callback verifiable after a restart or on
   * another instance (G-1: PostgreSQL is the SSOT).
   *
   * Contract:
   *   - unknown order, or an order that is no longer `PENDING` → `false`, and
   *     NOTHING is written: an authorisation belongs to an order that can still
   *     be paid;
   *   - an authority already recorded for a DIFFERENT order → the unique index
   *     refuses the write (throws), because resolving a callback to two orders
   *     is not a state this table may represent;
   *   - otherwise the provider, authority and amount are written together and
   *     `true` is returned. A repeated authorisation for the same order
   *     SUPERSEDES the previous one (the customer retried with a new authority;
   *     the newest is the one whose callback can still be honoured).
   *
   * Deliberately does NOT touch `status` or `payment_ref_id`: requesting a
   * payment moves no money (AC-8).
   */
  recordPaymentAuthorization(input: RecordPaymentAuthorizationInput): Promise<boolean>;

  /**
   * §6.1 — the callback lookup, by provider + authority. `null` when no order
   * holds that authorisation, which the adapter answers with a refusal rather
   * than a verify call made up with a guessed amount.
   */
  findPaymentAuthorization(
    provider: string,
    authority: string,
  ): Promise<PaymentAuthorizationRecord | null>;

  /*
   * §6.2 — the notification queue.
   *
   * The queue is a STORAGE fact, which is why these four calls live on the
   * repository and not in the dispatcher: claiming has to be atomic across
   * processes (`FOR UPDATE SKIP LOCKED`), and only PostgreSQL can do that. The
   * in-memory double models the same contract so the dispatcher is unit-testable,
   * but the concurrency claim is proven against a real server (`smoke:db`).
   */

  /**
   * Claims up to `limit` due notifications, oldest first, and marks them
   * `SENDING` with `attempts` incremented — one transaction, so two dispatchers
   * can never claim the same row (the loser skips it, it does not wait).
   *
   * A row is due when it is `PENDING` and `next_attempt_at <= now`, or when it is
   * `SENDING` whose lease is older than `NOTIFICATION_LEASE_MS` (a claimant
   * crashed). Rows that have spent their attempt budget are not claimable.
   */
  claimNotificationBatch(limit: number, now?: Date): Promise<NotificationWorkItem[]>;

  /** Records the provider's acceptance. Returns `false` for an unknown id. */
  markNotificationSent(
    id: string,
    providerMessageId: string | null,
    now?: Date,
  ): Promise<boolean>;

  /**
   * Records a refusal. `retryAt` non-null reschedules (`PENDING`); `null` is
   * terminal (`FAILED`). `code` is a stable adapter code, never a provider
   * message or a credential.
   */
  markNotificationFailed(
    id: string,
    code: string,
    retryAt: Date | null,
    now?: Date,
  ): Promise<boolean>;

  /** The order's queued notifications, oldest first (empty when unknown). */
  listOrderNotifications(orderId: string): Promise<OrderNotification[]>;
}

/** Postgres implementation — the only file that speaks SQL/schema. */
export function createPostgresRepository(db: CommerceDb): CommerceRepository {
  /* Three narrow reads composed in JS, rather than one wide aggregate: the
   * catalog is small (a boutique's published range), and this keeps the SQL
   * readable and the mapping shared with the in-memory double. */
  async function storefrontHeads(ids?: string[]): Promise<StorefrontHeadRow[]> {
    return db
      .select({
        id: products.id,
        slug: products.slug,
        title: products.title,
        categoryName: categories.name,
        basePrice: products.basePrice,
        discountPrice: products.discountPrice,
        createdAt: products.createdAt,
      })
      .from(products)
      .innerJoin(categories, eq(products.categoryId, categories.id))
      .where(
        ids
          ? and(eq(products.status, 'PUBLISHED'), inArray(products.id, ids))
          : eq(products.status, 'PUBLISHED'),
      )
      .orderBy(desc(products.createdAt));
  }

  async function storefrontImages(productIds: string[]): Promise<StorefrontImageRow[]> {
    if (productIds.length === 0) {
      return [];
    }
    return db
      .select({
        productId: productImages.productId,
        publicUrl: productImages.publicUrl,
        displayOrder: productImages.displayOrder,
        isPrimary: productImages.isPrimary,
        variantId: productImages.variantId,
      })
      .from(productImages)
      .where(inArray(productImages.productId, productIds))
      .orderBy(asc(productImages.displayOrder));
  }

  async function storefrontVariants(productIds: string[]): Promise<StorefrontVariantRow[]> {
    if (productIds.length === 0) {
      return [];
    }
    return db
      .select({
        variantId: productVariants.id,
        productId: productVariants.productId,
        size: productVariants.size,
        colorName: productVariants.colorName,
        colorHex: productVariants.colorHex,
        stockQuantity: productVariants.stockQuantity,
        priceOverride: productVariants.priceOverride,
        isActive: productVariants.isActive,
      })
      .from(productVariants)
      .where(inArray(productVariants.productId, productIds))
      .orderBy(asc(productVariants.colorName), asc(productVariants.size));
  }

  async function storefrontCards(ids?: string[]): Promise<StorefrontProductCard[]> {
    const heads = await storefrontHeads(ids);
    const productIds = heads.map((head) => head.id);
    const [images, variants] = await Promise.all([
      storefrontImages(productIds),
      storefrontVariants(productIds),
    ]);
    return heads.map((head) =>
      toStorefrontCard(
        head,
        images.filter((image) => image.productId === head.id),
        variants.filter((variant) => variant.productId === head.id),
      ),
    );
  }

  return {
    async listCategories() {
      return db
        .select({ id: categories.id, name: categories.name, slug: categories.slug })
        .from(categories)
        .orderBy(categories.name);
    },

    async createProductGraph(graph) {
      return db.transaction(async (tx) => {
        const [product] = await tx
          .insert(products)
          .values(graph.product)
          .returning({ id: products.id });
        if (!product) {
          throw new Error('product insert returned no row');
        }

        const variantIds: string[] = [];
        for (const variant of graph.variants) {
          const [row] = await tx
            .insert(productVariants)
            .values({ ...variant, productId: product.id })
            .returning({ id: productVariants.id });
          if (!row) {
            throw new Error('variant insert returned no row');
          }
          variantIds.push(row.id);
        }

        for (const image of graph.images) {
          const variantId =
            image.variantIndex === null ? null : (variantIds[image.variantIndex] ?? null);
          await tx.insert(productImages).values({
            productId: product.id,
            variantId,
            storagePath: image.storagePath,
            publicUrl: image.publicUrl,
            displayOrder: image.displayOrder,
            isPrimary: image.isPrimary,
          });
        }

        return { productId: product.id, variantIds };
      });
    },

    async listProducts() {
      /**
       * Counts arrive as `count(distinct …)` over LEFT JOINs, not as correlated
       * subqueries written in raw `sql`.
       *
       * Measured against live PostgreSQL (Phase 2 hardening): a raw `sql` chunk
       * renders its column references UNQUALIFIED, so
       * `(select count(*) from product_variants where product_id = id)` bound
       * BOTH names to `product_variants` — `product_variants.product_id =
       * product_variants.id` — and every product reported 0 variants and 0
       * images while the rows sat in the table. `distinct` is what keeps the two
       * one-to-many joins from multiplying each other's rows.
       */
      const rows = await db
        .select({
          id: products.id,
          title: products.title,
          slug: products.slug,
          status: products.status,
          basePrice: products.basePrice,
          discountPrice: products.discountPrice,
          variantCount: sql<number>`count(distinct ${productVariants.id})`,
          imageCount: sql<number>`count(distinct ${productImages.id})`,
        })
        .from(products)
        .leftJoin(productVariants, eq(productVariants.productId, products.id))
        .leftJoin(productImages, eq(productImages.productId, products.id))
        .groupBy(products.id)
        .orderBy(desc(products.createdAt));
      return rows.map((row) => ({
        ...row,
        variantCount: Number(row.variantCount),
        imageCount: Number(row.imageCount),
      }));
    },

    async listInventory() {
      const rows = await db
        .select({
          variantId: productVariants.id,
          productId: products.id,
          productTitle: products.title,
          productSlug: products.slug,
          sku: productVariants.sku,
          size: productVariants.size,
          colorName: productVariants.colorName,
          colorHex: productVariants.colorHex,
          stockQuantity: productVariants.stockQuantity,
          priceOverride: productVariants.priceOverride,
          basePrice: products.basePrice,
          isActive: productVariants.isActive,
        })
        .from(productVariants)
        .innerJoin(products, eq(productVariants.productId, products.id))
        .orderBy(products.title, productVariants.size);
      return rows;
    },

    async updateVariantStock(variantId, stockQuantity) {
      const rows = await db
        .update(productVariants)
        .set({ stockQuantity })
        .where(eq(productVariants.id, variantId))
        .returning({ id: productVariants.id });
      return rows.length === 1;
    },

    async updateVariantPrice(variantId, priceOverride) {
      const rows = await db
        .update(productVariants)
        .set({ priceOverride })
        .where(eq(productVariants.id, variantId))
        .returning({ id: productVariants.id });
      return rows.length === 1;
    },

    async listOrders() {
      // Same measured trap as `listProducts`: a raw `sql` subquery rendered
      // `where "order_id" = "id"` with BOTH names bound to `order_items`, so
      // every order reported a line count of 0 (vacuously, because the join
      // condition was never true). The aggregate over the LEFT JOIN is correct
      // and stays metadata-driven; `coalesce` keeps an order without lines at 0
      // rather than NULL.
      const rows = await db
        .select({
          id: orders.id,
          customerName: customers.fullName,
          customerPhone: customers.phoneNumber,
          status: orders.status,
          totalAmount: orders.totalAmount,
          discountAmount: orders.discountAmount,
          shippingAmount: orders.shippingAmount,
          trackingCode: orders.trackingCode,
          createdAt: orders.createdAt,
          itemCount: sql<number>`coalesce(sum(${orderItems.quantity}), 0)`,
        })
        .from(orders)
        .innerJoin(customers, eq(orders.customerId, customers.id))
        .leftJoin(orderItems, eq(orderItems.orderId, orders.id))
        .groupBy(orders.id, customers.id)
        .orderBy(desc(orders.createdAt));
      return rows.map((row) => ({ ...row, itemCount: Number(row.itemCount) }));
    },

    async getOrderDetail(orderId) {
      const [head] = await db
        .select({
          id: orders.id,
          customerName: customers.fullName,
          customerPhone: customers.phoneNumber,
          status: orders.status,
          totalAmount: orders.totalAmount,
          discountAmount: orders.discountAmount,
          shippingAmount: orders.shippingAmount,
          trackingCode: orders.trackingCode,
          createdAt: orders.createdAt,
          shippingAddress: orders.shippingAddress,
          postalCode: customers.postalCode,
          paymentRefId: orders.paymentRefId,
        })
        .from(orders)
        .innerJoin(customers, eq(orders.customerId, customers.id))
        .where(eq(orders.id, orderId));
      if (!head) {
        return null;
      }

      const items = await db
        .select({
          id: orderItems.id,
          sku: productVariants.sku,
          productTitle: products.title,
          size: productVariants.size,
          colorName: productVariants.colorName,
          quantity: orderItems.quantity,
          unitPrice: orderItems.unitPrice,
        })
        .from(orderItems)
        .innerJoin(productVariants, eq(orderItems.variantId, productVariants.id))
        .innerJoin(products, eq(productVariants.productId, products.id))
        .where(eq(orderItems.orderId, orderId))
        .orderBy(products.title);

      const itemCount = items.reduce((total, item) => total + item.quantity, 0);
      return { ...head, itemCount, items };
    },

    /**
     * Status change, with the TWO things a status change owes the record:
     * cancelling an order returns the stock that order consumed (§3.4
     * reservation), and EVERY transition appends its audit row (Phase 4
     * transition).
     *
     * All of it runs in one transaction with the order row locked first, so a
     * cancellation restocks exactly once under concurrent requests and a status
     * change can never commit without its trail. The previous status is what the
     * audit row's `from_status` carries — read under the lock, never re-derived
     * from the caller.
     *
     * A variant referenced by an order line can never have been deleted
     * (`order_items.variant_id` is RESTRICT), so every line has a row to credit.
     */
    async updateOrderStatus(orderId, status, trigger, notifications = []) {
      return db.transaction(async (tx) => {
        const [current] = await tx
          .select({ status: orders.status })
          .from(orders)
          .where(eq(orders.id, orderId))
          .for('update');
        if (!current) {
          return false;
        }

        // A repeat is a NO-OP that reports success and writes NOTHING: no second
        // restock, and no second audit row (which the unique index would refuse
        // anyway). This is what makes a retried provider callback harmless.
        if (current.status === status) {
          return true;
        }

        // Only reachable on a real move now, so the `previous !== 'CANCELLED'`
        // guard the earlier version needed is implied by the branch above.
        if (status === 'CANCELLED') {
          const lines = await tx
            .select({ variantId: orderItems.variantId, quantity: orderItems.quantity })
            .from(orderItems)
            .where(eq(orderItems.orderId, orderId));
          for (const line of lines) {
            await tx
              .update(productVariants)
              .set({ stockQuantity: sql`${productVariants.stockQuantity} + ${line.quantity}` })
              .where(eq(productVariants.id, line.variantId));
          }
        }

        const rows = await tx
          .update(orders)
          .set({ status, updatedAt: new Date() })
          .where(eq(orders.id, orderId))
          .returning({ id: orders.id });
        if (rows.length !== 1) {
          return false;
        }

        // The trail is appended LAST and in the same transaction: an order row
        // that moved without its history row would roll back together with it.
        await tx.insert(orderStatusHistory).values({
          orderId,
          fromStatus: current.status,
          toStatus: status,
          source: trigger.source,
          metadata: trigger.metadata ?? null,
        });

        // §6.2 — the announcement is part of the SAME commit. `DO NOTHING` is
        // the idempotency boundary: a concurrent duplicate that somehow reaches
        // this line (it cannot, the row lock serialises it) writes no second SMS.
        if (notifications.length > 0) {
          await tx
            .insert(notificationOutbox)
            .values(
              notifications.map((intent) => ({
                orderId,
                kind: intent.kind,
                channel: intent.channel,
                payload: { orderRef: orderReference(orderId) },
              })),
            )
            .onConflictDoNothing({
              target: [
                notificationOutbox.orderId,
                notificationOutbox.kind,
                notificationOutbox.channel,
              ],
            });
        }
        return true;
      });
    },

    /**
     * The audit trail, oldest first. `created_at` is the transaction's own
     * timestamp (`now()`, stable across a transaction), and an order acquires at
     * most one row per transaction, so the order is total without a tiebreaker.
     */
    async listOrderStatusHistory(orderId) {
      return db
        .select({
          id: orderStatusHistory.id,
          orderId: orderStatusHistory.orderId,
          fromStatus: orderStatusHistory.fromStatus,
          toStatus: orderStatusHistory.toStatus,
          source: orderStatusHistory.source,
          metadata: orderStatusHistory.metadata,
          createdAt: orderStatusHistory.createdAt,
        })
        .from(orderStatusHistory)
        .where(eq(orderStatusHistory.orderId, orderId))
        .orderBy(asc(orderStatusHistory.createdAt));
    },

    async updateOrderTracking(orderId, trackingCode) {
      const rows = await db
        .update(orders)
        .set({ trackingCode, updatedAt: new Date() })
        .where(eq(orders.id, orderId))
        .returning({ id: orders.id });
      return rows.length === 1;
    },

    async listCoupons() {
      return db.select().from(coupons).orderBy(desc(coupons.createdAt));
    },

    async findCouponByCode(code) {
      const [row] = await db.select().from(coupons).where(eq(coupons.code, code));
      return row ?? null;
    },

    async createCoupon(input) {
      const [row] = await db.insert(coupons).values(input).returning();
      if (!row) {
        throw new Error('coupon insert returned no row');
      }
      return row;
    },

    async setCouponActive(couponId, isActive) {
      const rows = await db
        .update(coupons)
        .set({ isActive, updatedAt: new Date() })
        .where(and(eq(coupons.id, couponId)))
        .returning({ id: coupons.id });
      return rows.length === 1;
    },

    /* ------------------------------------------------- §3.1–§3.3 reads */

    async listStorefrontProducts() {
      return storefrontCards();
    },

    async getStorefrontProduct(slug) {
      const [head] = await db
        .select({
          id: products.id,
          slug: products.slug,
          title: products.title,
          categoryName: categories.name,
          basePrice: products.basePrice,
          discountPrice: products.discountPrice,
          createdAt: products.createdAt,
          descriptionRaw: products.descriptionRaw,
          descriptionHtml: products.descriptionHtml,
          fabricType: products.fabricType,
          season: products.season,
          careInstructions: products.careInstructions,
        })
        .from(products)
        .innerJoin(categories, eq(products.categoryId, categories.id))
        .where(and(eq(products.slug, slug), eq(products.status, 'PUBLISHED')));
      if (!head) {
        return null;
      }

      const [images, variants] = await Promise.all([
        storefrontImages([head.id]),
        storefrontVariants([head.id]),
      ]);
      const active = variants.filter((variant) => variant.isActive);
      const card = toStorefrontCard(head, images, variants);

      return {
        ...card,
        descriptionRaw: head.descriptionRaw,
        descriptionHtml: head.descriptionHtml,
        fabricType: head.fabricType,
        season: head.season,
        careInstructions: head.careInstructions,
        images: toImageRefs(images),
        variants: active.map((variant) => toVariantView(variant, card.effectivePrice)),
      };
    },

    async listBestSellers(limit) {
      const ranked = await db
        .select({
          productId: productVariants.productId,
          sold: sql<number>`coalesce(sum(${orderItems.quantity}), 0)`,
        })
        .from(orderItems)
        .innerJoin(orders, eq(orderItems.orderId, orders.id))
        .innerJoin(productVariants, eq(orderItems.variantId, productVariants.id))
        .innerJoin(products, eq(productVariants.productId, products.id))
        .where(and(ne(orders.status, 'CANCELLED'), eq(products.status, 'PUBLISHED')))
        .groupBy(productVariants.productId)
        .orderBy(desc(sql`coalesce(sum(${orderItems.quantity}), 0)`))
        .limit(Math.max(0, Math.trunc(limit)));

      const ids = ranked.map((row) => row.productId);
      if (ids.length === 0) {
        return [];
      }
      const cards = await storefrontCards(ids);
      // Preserve the ranking order the database produced.
      return ids
        .map((id) => cards.find((card) => card.id === id))
        .filter((card): card is StorefrontProductCard => card !== undefined);
    },

    async listStorefrontCategories() {
      const rows = await db
        .select({
          name: categories.name,
          slug: categories.slug,
          productCount: sql<number>`count(${products.id})`,
        })
        .from(categories)
        .leftJoin(
          products,
          and(eq(products.categoryId, categories.id), eq(products.status, 'PUBLISHED')),
        )
        .groupBy(categories.id, categories.name, categories.slug)
        .orderBy(asc(categories.name));
      return rows.map((row) => ({ ...row, productCount: Number(row.productCount) }));
    },

    async listVariantAvailability(items) {
      const variantIds = items.map((item) => item.variantId);
      if (variantIds.length === 0) {
        return [];
      }
      const rows = await db
        .select({
          variantId: productVariants.id,
          productTitle: products.title,
          size: productVariants.size,
          colorName: productVariants.colorName,
          stockQuantity: productVariants.stockQuantity,
          priceOverride: productVariants.priceOverride,
          basePrice: products.basePrice,
          discountPrice: products.discountPrice,
          isActive: productVariants.isActive,
          status: products.status,
        })
        .from(productVariants)
        .innerJoin(products, eq(productVariants.productId, products.id))
        .where(inArray(productVariants.id, variantIds));

      return items.map((item): CartAvailabilityLine => {
        const row = rows.find((entry) => entry.variantId === item.variantId);
        if (!row || !row.isActive || row.status !== 'PUBLISHED') {
          // Not "zero in stock": the line is not sellable at all. No price and
          // no title are invented for it — the drawer keeps the customer's own
          // label and simply refuses the line.
          return {
            variantId: item.variantId,
            productTitle: '',
            size: '',
            colorName: '',
            level: 'OUT' as StockLevel,
            available: false,
            effectivePrice: null,
          };
        }
        const level = stockLevelFor(row.stockQuantity);
        return {
          variantId: row.variantId,
          productTitle: row.productTitle,
          size: row.size,
          colorName: row.colorName,
          level,
          available: level !== 'OUT' && row.stockQuantity >= item.quantity,
          effectivePrice: row.priceOverride ?? row.discountPrice ?? row.basePrice,
        };
      });
    },

    /* --------------------------------------------------------- §3.4 ordering */

    async placeOrder(input) {
      if (input.items.length === 0) {
        return { ok: false, code: 'EMPTY_CART', message: 'سبد خرید خالی است.' };
      }

      const shippingAmount = shippingAmountFor(input.shippingMethodId);
      if (shippingAmount === null) {
        return {
          ok: false,
          code: 'SHIPPING_UNKNOWN',
          message: 'روش ارسال انتخابی معتبر نیست.',
          field: 'shippingMethodId',
        };
      }

      try {
        return await db.transaction(async (tx) => {
          const variantIds = input.items.map((item) => item.variantId);

          // Lock the variant rows for the duration of the write: two customers
          // buying the last piece cannot both pass the availability check.
          //
          // The lock is taken with a SINGLE-TABLE select on purpose. The variant
          // rows are locked so catalog rows stay writeable, but PostgreSQL
          // refuses `for update of "commerce"."product_variants"` (42601:
          // "FOR UPDATE must specify unqualified relation names") and Drizzle
          // renders this schema-bound table qualified — so asking for `of: table`
          // on the join made EVERY checkout fail at the lock before it could
          // write anything. A lock on `product_variants` alone needs no `OF`
          // clause at all, and the product columns are read in the next query.
          // The live storefront suite is what caught this.
          const locked = await tx
            .select({
              variantId: productVariants.id,
              productId: productVariants.productId,
              isActive: productVariants.isActive,
              stockQuantity: productVariants.stockQuantity,
              priceOverride: productVariants.priceOverride,
            })
            .from(productVariants)
            .where(inArray(productVariants.id, variantIds))
            .for('update');

          const productIds = [...new Set(locked.map((row) => row.productId))];
          const productRows =
            productIds.length === 0
              ? []
              : await tx
                  .select({
                    id: products.id,
                    status: products.status,
                    basePrice: products.basePrice,
                    discountPrice: products.discountPrice,
                  })
                  .from(products)
                  .where(inArray(products.id, productIds));

          const unitPriceByVariant = new Map<string, number>();
          let subtotal = 0;

          for (const item of input.items) {
            const variant = locked.find((entry) => entry.variantId === item.variantId);
            const product = variant
              ? productRows.find((entry) => entry.id === variant.productId)
              : undefined;
            if (!variant || !product || !variant.isActive || product.status !== 'PUBLISHED') {
              return {
                ok: false,
                code: 'VARIANT_UNAVAILABLE',
                message: 'این گونه دیگر در دسترس نیست.',
                variantId: item.variantId,
              };
            }
            if (variant.stockQuantity < item.quantity) {
              return {
                ok: false,
                code: 'STOCK_INSUFFICIENT',
                message: 'موجودی این گونه کافی نیست.',
                variantId: item.variantId,
              };
            }
            // Same resolution the storefront displayed (D-024), re-read here.
            const unitPrice = variant.priceOverride ?? product.discountPrice ?? product.basePrice;
            unitPriceByVariant.set(item.variantId, unitPrice);
            subtotal += unitPrice * item.quantity;
          }

          let discount = 0;
          let couponId: string | null = null;
          if (input.couponCode) {
            const [coupon] = await tx
              .select()
              .from(coupons)
              .where(eq(coupons.code, input.couponCode))
              .for('update');
            if (!coupon) {
              return {
                ok: false,
                code: 'COUPON_INVALID',
                message: 'کد تخفیف معتبر نیست.',
                field: 'couponCode',
              };
            }
            const decision = evaluateCoupon(
              {
                id: coupon.id,
                code: coupon.code,
                discountType: coupon.discountType,
                discountValue: coupon.discountValue,
                minSpend: coupon.minSpend,
                expiresAt: coupon.expiresAt,
                usageLimit: coupon.usageLimit,
                usedCount: coupon.usedCount,
                isActive: coupon.isActive,
              },
              subtotal,
            );
            if (!decision.ok) {
              return { ok: false, code: 'COUPON_INVALID', message: decision.message, field: 'couponCode' };
            }
            discount = decision.discount;
            couponId = coupon.id;
          }

          // ── consume the stock, as the FIRST write of the transaction ────────
          // The rows are already locked `for update`, so nothing can slip between
          // the check above and this write; the conditional update still repeats
          // the bound (`stock_quantity >= quantity`, backed by the column's
          // `>= 0` CHECK) so check-and-consume is ONE statement per variant and
          // overselling stays impossible even if a future edit drops the lock.
          // A mismatch here is therefore an invariant violation, not a customer
          // error: it THROWS so the whole transaction rolls back (an order must
          // never exist without the stock it consumed), and the catch below turns
          // it into the ordinary refusal.
          for (const item of input.items) {
            const consumed = await tx
              .update(productVariants)
              .set({ stockQuantity: sql`${productVariants.stockQuantity} - ${item.quantity}` })
              .where(
                and(
                  eq(productVariants.id, item.variantId),
                  gte(productVariants.stockQuantity, item.quantity),
                ),
              )
              .returning({ id: productVariants.id });
            if (consumed.length !== 1) {
              throw new StockConflictError(item.variantId);
            }
          }

          const phoneNumber = normalizePhoneNumber(input.customer.phoneNumber);
          // Idempotent by identity, not by name: an existing customer row is
          // reused UNTOUCHED (no silent overwrite of the profile), while this
          // order carries the address the customer typed for THIS shipment.
          const [inserted] = await tx
            .insert(customers)
            .values({
              phoneNumber,
              fullName: input.customer.fullName.trim(),
              address: input.customer.address.trim(),
              postalCode: normalizePostalCode(input.customer.postalCode),
            })
            .onConflictDoNothing({ target: customers.phoneNumber })
            .returning({ id: customers.id });
          const customerId =
            inserted?.id ??
            (
              await tx
                .select({ id: customers.id })
                .from(customers)
                .where(eq(customers.phoneNumber, phoneNumber))
            )[0]?.id;
          if (!customerId) {
            throw new Error('customer resolution returned no row');
          }

          const totals = computeCheckoutTotals({ subtotal, discount, shipping: shippingAmount });
          const [order] = await tx
            .insert(orders)
            .values({
              customerId,
              totalAmount: totals.total,
              discountAmount: totals.discount,
              shippingAmount: totals.shipping,
              status: 'PENDING',
              paymentRefId: input.paymentRefId,
              shippingAddress: input.shippingAddress.trim(),
            })
            .returning({ id: orders.id });
          if (!order) {
            throw new Error('order insert returned no row');
          }

          await tx.insert(orderItems).values(
            input.items.map((item) => ({
              orderId: order.id,
              variantId: item.variantId,
              quantity: item.quantity,
              unitPrice: unitPriceByVariant.get(item.variantId) as number,
            })),
          );

          // The trail's opening row, written in the SAME transaction as the
          // order it describes: `from_status` is NULL because nothing preceded
          // it, and the source is the caller's (the storefront checkout today).
          await tx.insert(orderStatusHistory).values({
            orderId: order.id,
            fromStatus: null,
            toStatus: 'PENDING',
            source: input.source,
            metadata: input.statusMetadata ?? null,
          });

          if (couponId !== null) {
            await tx
              .update(coupons)
              .set({ usedCount: sql`${coupons.usedCount} + 1`, updatedAt: new Date() })
              .where(eq(coupons.id, couponId));
          }

          return {
            ok: true as const,
            orderId: order.id,
            customerId,
            totals,
            couponApplied: couponId !== null,
            status: 'PENDING' as const,
          };
        });
      } catch (error) {
        // The ONLY refusal raised from inside the transaction: the stock it was
        // about to consume had already moved. Reported as the same code the
        // pre-check uses, and never as a partial write.
        if (error instanceof StockConflictError) {
          return {
            ok: false,
            code: 'STOCK_INSUFFICIENT',
            message: 'موجودی این گونه کافی نیست.',
            variantId: error.variantId,
          };
        }
        throw error;
      }
    },

    async setOrderPaymentRef(orderId, paymentRefId) {
      const rows = await db
        .update(orders)
        .set({ paymentRefId, updatedAt: new Date() })
        .where(eq(orders.id, orderId))
        .returning({ id: orders.id });
      return rows.length === 1;
    },

    async recordPaymentAuthorization(input) {
      // The `PENDING` guard is part of the contract, not a convenience: an order
      // that has already been cancelled or paid must not acquire a fresh
      // authorisation, and the adapter treats `false` as "do not redirect".
      const rows = await db
        .update(orders)
        .set({
          paymentProvider: input.provider,
          paymentAuthority: input.authority,
          paymentAmount: input.amount,
          updatedAt: new Date(),
        })
        .where(and(eq(orders.id, input.orderId), eq(orders.status, 'PENDING')))
        .returning({ id: orders.id });
      return rows.length === 1;
    },

    async findPaymentAuthorization(provider, authority) {
      const [row] = await db
        .select({
          orderId: orders.id,
          provider: orders.paymentProvider,
          authority: orders.paymentAuthority,
          amount: orders.paymentAmount,
        })
        .from(orders)
        .where(and(eq(orders.paymentProvider, provider), eq(orders.paymentAuthority, authority)));

      // The check constraint makes a half-written authorisation impossible, but
      // the read is narrowed field by field anyway: a NULL amount is "nothing to
      // verify", never a zero.
      if (!row || row.provider === null || row.authority === null || row.amount === null) {
        return null;
      }
      return {
        orderId: row.orderId,
        provider: row.provider,
        authority: row.authority,
        amount: row.amount,
      };
    },

    /**
     * §6.2 — claim due notifications.
     *
     * Two statements in ONE transaction: select the candidate ids with
     * `FOR UPDATE SKIP LOCKED` (so a concurrent dispatcher skips them instead of
     * blocking behind them), then move exactly those rows to `SENDING` with the
     * attempt counter bumped. Because the claim is the status change, a row can
     * belong to exactly one claimant — that is what makes "one SMS" a property of
     * the storage rather than of the caller's good manners.
     *
     * `attempts < MAX_SMS_ATTEMPTS` keeps a spent row out of every future batch:
     * the budget, not a timer, is what finally stops a bad recipient.
     */
    async claimNotificationBatch(limit, now = new Date()) {
      if (!Number.isInteger(limit) || limit <= 0) {
        return [];
      }
      const leaseFloor = new Date(now.getTime() - NOTIFICATION_LEASE_MS);

      return db.transaction(async (tx) => {
        const due = await tx
          .select({ id: notificationOutbox.id })
          .from(notificationOutbox)
          .where(
            and(
              lt(notificationOutbox.attempts, MAX_SMS_ATTEMPTS),
              or(
                and(
                  eq(notificationOutbox.status, 'PENDING'),
                  lte(notificationOutbox.nextAttemptAt, now),
                ),
                // A crashed claimant's lease. Without this a deploy at the wrong
                // moment would strand `SENDING` rows forever.
                and(
                  eq(notificationOutbox.status, 'SENDING'),
                  lt(notificationOutbox.updatedAt, leaseFloor),
                ),
              ),
            ),
          )
          .orderBy(asc(notificationOutbox.createdAt))
          .limit(limit)
          .for('update', { skipLocked: true });

        if (due.length === 0) {
          return [];
        }

        const rows = await tx
          .update(notificationOutbox)
          .set({
            status: 'SENDING',
            attempts: sql`${notificationOutbox.attempts} + 1`,
            updatedAt: now,
          })
          .where(
            inArray(
              notificationOutbox.id,
              due.map((entry) => entry.id),
            ),
          )
          .returning({
            id: notificationOutbox.id,
            orderId: notificationOutbox.orderId,
            kind: notificationOutbox.kind,
            channel: notificationOutbox.channel,
            attempts: notificationOutbox.attempts,
            payload: notificationOutbox.payload,
          });

        return rows.map((row) => ({
          id: row.id,
          orderId: row.orderId,
          kind: row.kind as OrderNotificationKind,
          channel: row.channel as OrderNotificationChannel,
          attempts: row.attempts,
          payload: row.payload,
        }));
      });
    },

    async markNotificationSent(id, providerMessageId, now = new Date()) {
      const rows = await db
        .update(notificationOutbox)
        .set({
          status: 'SENT',
          providerMessageId,
          lastError: null,
          sentAt: now,
          updatedAt: now,
        })
        .where(eq(notificationOutbox.id, id))
        .returning({ id: notificationOutbox.id });
      return rows.length === 1;
    },

    async markNotificationFailed(id, code, retryAt, now = new Date()) {
      const rows = await db
        .update(notificationOutbox)
        .set({
          status: retryAt === null ? 'FAILED' : 'PENDING',
          lastError: code.slice(0, 64),
          updatedAt: now,
          // A terminal row keeps the instant it became due; only a rescheduled
          // one moves its clock forward, so "when did this give up" stays readable.
          ...(retryAt === null ? {} : { nextAttemptAt: retryAt }),
        })
        .where(eq(notificationOutbox.id, id))
        .returning({ id: notificationOutbox.id });
      return rows.length === 1;
    },

    async listOrderNotifications(orderId) {
      const rows = await db
        .select({
          id: notificationOutbox.id,
          orderId: notificationOutbox.orderId,
          kind: notificationOutbox.kind,
          channel: notificationOutbox.channel,
          status: notificationOutbox.status,
          attempts: notificationOutbox.attempts,
          lastError: notificationOutbox.lastError,
          providerMessageId: notificationOutbox.providerMessageId,
          payload: notificationOutbox.payload,
          nextAttemptAt: notificationOutbox.nextAttemptAt,
          createdAt: notificationOutbox.createdAt,
          updatedAt: notificationOutbox.updatedAt,
          sentAt: notificationOutbox.sentAt,
        })
        .from(notificationOutbox)
        .where(eq(notificationOutbox.orderId, orderId))
        .orderBy(asc(notificationOutbox.createdAt));

      return rows.map((row) => ({
        ...row,
        kind: row.kind as OrderNotificationKind,
        channel: row.channel as OrderNotificationChannel,
        status: row.status as NotificationStatus,
      }));
    },
  };
}
