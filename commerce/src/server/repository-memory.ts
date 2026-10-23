import type { CheckoutTotals, CouponRuleInput, StockLevel } from '@/contracts/storefront';
import type { CouponRow } from '@/contracts/promotions';
import type { OrderStatus, OrderStatusSource, ProductStatus } from '@/db/schema';
import { computeCheckoutTotals, evaluateCoupon } from '@/lib/checkout-rules';
import { stockLevelFor } from '@/lib/inventory-rules';
import { shippingAmountFor } from '@/lib/shipping';
import { normalizePhoneNumber, normalizePostalCode } from '@/lib/validation';

import {
  toImageRefs,
  toStorefrontCard,
  toVariantView,
  type CommerceRepository,
  type InventoryRow,
  type NewCouponInput,
  type NewProductGraph,
  type OrderDetail,
  type OrderItemView,
  type OrderListItem,
  type OrderStatusHistoryEntry,
  type PaymentAuthorizationRecord,
  type ProductListItem,
  type StorefrontHeadRow,
} from './repository';

/**
 * D-172 Phase 2/3 — deterministic in-memory repository.
 *
 * This is the TEST DOUBLE that lets the service layer be unit tested without a
 * database (`npm test`). It is deliberately NOT wired into any route: the admin
 * surface never renders invented data, and when `DATABASE_URL` is absent the
 * panel says so instead (see `db-context.ts`).
 *
 * What it models: identity generation, the joins the admin and the storefront
 * read, mutation semantics and the counters — including the checkout write path,
 * so the storefront's rules (price resolution D-024, coupon eligibility, PENDING
 * status) are exercised without PostgreSQL. What it does NOT model: the
 * database's CHECK/UNIQUE constraints and its row locks (those are verified
 * against real PostgreSQL 16 in the migration validation, `drizzle/` + D-172 §6)
 * — so a service test here proves the SERVICE rule, the schema test proves the
 * STORAGE rule, and `placeOrder`'s serialisation of two concurrent buyers is a
 * property of the SQL path that this double cannot demonstrate.
 *
 * The storefront read models are built through the SAME mappers the Postgres
 * implementation uses (`toStorefrontCard`, `toVariantView`), so the double can
 * never disagree with the real read path about a card's price, stock level or
 * image order.
 */
export interface MemoryRepositorySeed {
  categories?: Array<{ id: string; name: string; slug: string }>;
  productGraphs?: NewProductGraph[];
  orders?: Array<{
    id: string;
    customerName: string;
    customerPhone: string;
    postalCode: string;
    status: OrderStatus;
    totalAmount: number;
    discountAmount: number;
    shippingAmount: number;
    trackingCode: string | null;
    shippingAddress: string;
    paymentRefId: string | null;
    createdAt: Date;
    items: Array<{
      sku: string;
      productTitle: string;
      size: string;
      colorName: string;
      quantity: number;
      unitPrice: number;
    }>;
  }>;
  coupons?: Array<Partial<CouponRow> & { code: string }>;
  /**
   * Past audit rows for a seeded order. A fixture must STATE a history it did
   * not replay: the double records what it observes, and inventing a path for a
   * seeded status (was it PENDING first? PAID before SHIPPED?) would be the
   * double lying about the very trail this table exists to make honest. Omit it
   * and the seeded order simply has no trail yet — which is the truth about a
   * fixture that was never walked through the lifecycle.
   */
  history?: MemoryStatusHistorySeed[];
}

/** A seeded audit row; `id` and `createdAt` are generated when omitted. */
export interface MemoryStatusHistorySeed {
  orderId: string;
  fromStatus: OrderStatus | null;
  toStatus: OrderStatus;
  source: OrderStatusSource;
  metadata?: Record<string, unknown> | null;
  createdAt?: Date;
}

let sequence = 0;
function nextId(prefix: string): string {
  sequence += 1;
  return `${prefix}-${String(sequence).padStart(4, '0')}`;
}

/** A stored catalog row: the product columns the public read path needs. */
interface MemoryProductRow {
  id: string;
  title: string;
  slug: string;
  status: ProductStatus;
  basePrice: number;
  discountPrice: number | null;
  categoryId: string;
  categoryName: string;
  descriptionRaw: string;
  descriptionHtml: string;
  fabricType: string;
  season: string;
  careInstructions: string | null;
  createdAt: Date;
}

interface MemoryImageRow {
  productId: string;
  publicUrl: string;
  displayOrder: number;
  isPrimary: boolean;
  variantId: string | null;
}

interface MemoryCustomerRow {
  id: string;
  phoneNumber: string;
  fullName: string;
  address: string;
  postalCode: string;
}

/**
 * The double's stored order line: the public view plus the variant binding a
 * cancellation needs to return stock. PostgreSQL carries the same information in
 * `order_items.variant_id` — here it is spelled out on the row rather than kept
 * in a side table, so the double still has ONE source of truth per order.
 */
type MemoryOrderItem = OrderItemView & { variantId: string | null };

type MemoryOrderRow = Omit<OrderDetail, 'items'> & { items: MemoryOrderItem[] };

export function createMemoryRepository(seed: MemoryRepositorySeed = {}): CommerceRepository {
  const categories = seed.categories ?? [
    { id: 'cat-1', name: 'مانتو', slug: 'manto' },
    { id: 'cat-2', name: 'شومیز', slug: 'shomiz' },
  ];

  let createdAtCursor = new Date('2026-01-01T00:00:00.000Z').getTime();
  const productsTable: MemoryProductRow[] = [];
  const variantsTable: InventoryRow[] = [];
  const imagesTable: MemoryImageRow[] = [];
  const customersTable: MemoryCustomerRow[] = [];

  function addProduct(graph: NewProductGraph): { productId: string; variantIds: string[] } {
    const productId = nextId('prod');
    const category = categories.find((entry) => entry.id === graph.product.categoryId);
    createdAtCursor += 60_000;
    productsTable.push({
      id: productId,
      title: graph.product.title,
      slug: graph.product.slug,
      status: graph.product.status,
      basePrice: graph.product.basePrice,
      discountPrice: graph.product.discountPrice,
      categoryId: graph.product.categoryId,
      categoryName: category?.name ?? '',
      descriptionRaw: graph.product.descriptionRaw,
      descriptionHtml: graph.product.descriptionHtml,
      fabricType: graph.product.fabricType,
      season: graph.product.season,
      careInstructions: graph.product.careInstructions,
      createdAt: new Date(createdAtCursor),
    });
    const variantIds: string[] = [];
    graph.variants.forEach((variant) => {
      const variantId = nextId('var');
      variantIds.push(variantId);
      variantsTable.push({
        variantId,
        productId,
        productTitle: graph.product.title,
        productSlug: graph.product.slug,
        sku: variant.sku,
        size: variant.size,
        colorName: variant.colorName,
        colorHex: variant.colorHex,
        stockQuantity: variant.stockQuantity,
        priceOverride: variant.priceOverride,
        basePrice: graph.product.basePrice,
        isActive: true,
      });
    });
    graph.images.forEach((image, index) => {
      imagesTable.push({
        productId,
        publicUrl: image.publicUrl,
        displayOrder: image.displayOrder ?? index,
        isPrimary: image.isPrimary,
        // The write path binds an image to a variant through `variantIndex`
        // (`null` in Phase 2, so this is normally `null` as well).
        variantId: image.variantIndex === null ? null : (variantIds[image.variantIndex] ?? null),
      });
    });
    return { productId, variantIds };
  }

  (seed.productGraphs ?? []).forEach((graph) => {
    addProduct(graph);
  });

  const ordersTable: MemoryOrderRow[] = (seed.orders ?? []).map((order) => ({
    ...order,
    itemCount: order.items.reduce((total, item) => total + item.quantity, 0),
    // A seeded order carries no variant binding, so cancelling one restocks
    // nothing — the double cannot invent which variant it was.
    items: order.items.map((item) => ({ ...item, id: nextId('item'), variantId: null })),
  }));

  const couponsTable: CouponRow[] = (seed.coupons ?? []).map((coupon) => ({
    id: coupon.id ?? nextId('coupon'),
    code: coupon.code,
    discountType: coupon.discountType ?? 'PERCENT',
    discountValue: coupon.discountValue ?? 10,
    minSpend: coupon.minSpend ?? 0,
    expiresAt: coupon.expiresAt ?? null,
    usageLimit: coupon.usageLimit ?? null,
    usedCount: coupon.usedCount ?? 0,
    isActive: coupon.isActive ?? true,
    description: coupon.description ?? null,
    createdAt: coupon.createdAt ?? new Date('2026-01-01T00:00:00.000Z'),
    updatedAt: coupon.updatedAt ?? new Date('2026-01-01T00:00:00.000Z'),
  }));

    /* ------------------------------------------------------- audit trail */

  /** The instant the double's fixtures begin; every generated row steps past it. */
  const HISTORY_EPOCH = new Date('2026-03-01T00:00:00.000Z');

  const statusHistoryTable: OrderStatusHistoryEntry[] = (seed.history ?? []).map((row) => ({
    id: nextId('history'),
    orderId: row.orderId,
    fromStatus: row.fromStatus,
    toStatus: row.toStatus,
    source: row.source,
    metadata: row.metadata ?? null,
    createdAt: row.createdAt ?? HISTORY_EPOCH,
  }));

  /**
   * §6.1 — the provider authorisation held against an order, keyed by ORDER id.
   *
   * One record per order is what the real table models (three columns on
   * `commerce.orders`), so a second authorisation for the same order supersedes
   * the first here too. It is deliberately NOT a process-wide cache keyed by
   * authority alone: this double is a storage stand-in, and its shape must not
   * teach a caller something the database cannot do.
   */
  const paymentAuthorizationsTable = new Map<string, PaymentAuthorizationRecord>();

  /**
   * Appends one audit row, stamped one minute after the last one written. The
   * clock is deliberately synthetic and monotonic: "oldest first" must be a
   * property of the fixture, not of how fast the machine ran the test.
   */
  function appendStatusHistory(entry: {
    orderId: string;
    fromStatus: OrderStatus | null;
    toStatus: OrderStatus;
    source: OrderStatusSource;
    metadata?: Record<string, unknown> | null;
  }): void {
    const last = statusHistoryTable[statusHistoryTable.length - 1];
    statusHistoryTable.push({
      id: nextId('history'),
      orderId: entry.orderId,
      fromStatus: entry.fromStatus,
      toStatus: entry.toStatus,
      source: entry.source,
      metadata: entry.metadata ?? null,
      createdAt: new Date((last?.createdAt.getTime() ?? HISTORY_EPOCH.getTime()) + 60_000),
    });
  }

  /* ---------------------------------------------- storefront read plumbing */

  function headOf(product: MemoryProductRow): StorefrontHeadRow {
    return {
      id: product.id,
      slug: product.slug,
      title: product.title,
      categoryName: product.categoryName,
      basePrice: product.basePrice,
      discountPrice: product.discountPrice,
      createdAt: product.createdAt,
    };
  }

  function imageRowsOf(productId: string) {
    return imagesTable
      .filter((image) => image.productId === productId)
      .map((image) => ({
        productId: image.productId,
        publicUrl: image.publicUrl,
        displayOrder: image.displayOrder,
        isPrimary: image.isPrimary,
        variantId: image.variantId,
      }));
  }

  function variantRowsOf(productId: string) {
    return variantsTable
      .filter((variant) => variant.productId === productId)
      .map((variant) => ({
        variantId: variant.variantId,
        productId: variant.productId,
        size: variant.size,
        colorName: variant.colorName,
        colorHex: variant.colorHex,
        stockQuantity: variant.stockQuantity,
        priceOverride: variant.priceOverride,
        isActive: variant.isActive,
      }));
  }

  function cardOf(product: MemoryProductRow) {
    return toStorefrontCard(headOf(product), imageRowsOf(product.id), variantRowsOf(product.id));
  }

  function published(): MemoryProductRow[] {
    return productsTable
      .filter((product) => product.status === 'PUBLISHED')
      .sort((left, right) => right.createdAt.getTime() - left.createdAt.getTime());
  }

  return {
    async listCategories() {
      return categories;
    },

    async createProductGraph(graph) {
      return addProduct(graph);
    },

    async listProducts(): Promise<ProductListItem[]> {
      return productsTable.map((product) => ({
        id: product.id,
        title: product.title,
        slug: product.slug,
        status: product.status,
        basePrice: product.basePrice,
        discountPrice: product.discountPrice,
        variantCount: variantsTable.filter((row) => row.productId === product.id).length,
        imageCount: imagesTable.filter((row) => row.productId === product.id).length,
      }));
    },

    async listInventory() {
      return variantsTable;
    },

    async updateVariantStock(variantId, stockQuantity) {
      const row = variantsTable.find((entry) => entry.variantId === variantId);
      if (!row) {
        return false;
      }
      row.stockQuantity = stockQuantity;
      return true;
    },

    async updateVariantPrice(variantId, priceOverride) {
      const row = variantsTable.find((entry) => entry.variantId === variantId);
      if (!row) {
        return false;
      }
      row.priceOverride = priceOverride;
      return true;
    },

    async listOrders(): Promise<OrderListItem[]> {
      // The list view carries the head fields only — the address, postal code,
      // payment reference and line items belong to the detail read.
      return ordersTable.map((order) => ({
        id: order.id,
        customerName: order.customerName,
        customerPhone: order.customerPhone,
        status: order.status,
        totalAmount: order.totalAmount,
        discountAmount: order.discountAmount,
        shippingAmount: order.shippingAmount,
        trackingCode: order.trackingCode,
        itemCount: order.itemCount,
        createdAt: order.createdAt,
      }));
    },

    async getOrderDetail(orderId) {
      return ordersTable.find((order) => order.id === orderId) ?? null;
    },

    async updateOrderStatus(orderId, status, trigger) {
      const order = ordersTable.find((entry) => entry.id === orderId);
      if (!order) {
        return false;
      }
      // A repeat is a no-op that reports success and writes nothing — no second
      // restock and no second audit row. Mirrors the SQL path, where the same
      // branch is what makes a retried callback harmless.
      if (order.status === status) {
        return true;
      }
      // Cancelling returns the stock the order consumed — the same rule the SQL
      // path applies.
      if (status === 'CANCELLED') {
        for (const item of order.items) {
          if (item.variantId === null) {
            continue;
          }
          const variant = variantsTable.find((entry) => entry.variantId === item.variantId);
          if (variant) {
            variant.stockQuantity += item.quantity;
          }
        }
      }
      const previous = order.status;
      order.status = status;
      appendStatusHistory({
        orderId,
        fromStatus: previous,
        toStatus: status,
        source: trigger.source,
        metadata: trigger.metadata ?? null,
      });
      return true;
    },

    async listOrderStatusHistory(orderId) {
      return statusHistoryTable
        .filter((row) => row.orderId === orderId)
        .sort((left, right) => left.createdAt.getTime() - right.createdAt.getTime());
    },

    async updateOrderTracking(orderId, trackingCode) {
      const order = ordersTable.find((entry) => entry.id === orderId);
      if (!order) {
        return false;
      }
      order.trackingCode = trackingCode;
      return true;
    },

    async listCoupons() {
      return couponsTable;
    },

    async findCouponByCode(code) {
      return couponsTable.find((coupon) => coupon.code === code) ?? null;
    },

    async createCoupon(input: NewCouponInput) {
      const row: CouponRow = {
        ...input,
        id: nextId('coupon'),
        usedCount: 0,
        createdAt: new Date('2026-02-01T00:00:00.000Z'),
        updatedAt: new Date('2026-02-01T00:00:00.000Z'),
      };
      couponsTable.push(row);
      return row;
    },

    async setCouponActive(couponId, isActive) {
      const coupon = couponsTable.find((entry) => entry.id === couponId);
      if (!coupon) {
        return false;
      }
      coupon.isActive = isActive;
      return true;
    },

    /* ------------------------------------------------ §3.1–§3.3 reads */

    async listStorefrontProducts() {
      return published().map(cardOf);
    },

    async getStorefrontProduct(slug) {
      const product = productsTable.find(
        (entry) => entry.slug === slug && entry.status === 'PUBLISHED',
      );
      if (!product) {
        return null;
      }
      const card = cardOf(product);
      return {
        ...card,
        descriptionRaw: product.descriptionRaw,
        descriptionHtml: product.descriptionHtml,
        fabricType: product.fabricType,
        season: product.season,
        careInstructions: product.careInstructions,
        images: toImageRefs(imageRowsOf(product.id)),
        variants: variantsTable
          .filter((variant) => variant.productId === product.id && variant.isActive)
          .map((variant) =>
            toVariantView(
              {
                variantId: variant.variantId,
                productId: variant.productId,
                size: variant.size,
                colorName: variant.colorName,
                colorHex: variant.colorHex,
                stockQuantity: variant.stockQuantity,
                priceOverride: variant.priceOverride,
                isActive: variant.isActive,
              },
              card.effectivePrice,
            ),
          ),
      };
    },

    async listBestSellers(limit) {
      // Quantity shipped per product, `CANCELLED` orders excluded — the same
      // aggregate the SQL path computes, so the "پرفروش" rail means one thing.
      const sold = new Map<string, number>();
      for (const order of ordersTable) {
        if (order.status === 'CANCELLED') {
          continue;
        }
        for (const item of order.items) {
          const variant = variantsTable.find((entry) => entry.sku === item.sku);
          if (!variant) {
            continue;
          }
          sold.set(variant.productId, (sold.get(variant.productId) ?? 0) + item.quantity);
        }
      }

      return [...sold.entries()]
        .sort((left, right) => right[1] - left[1])
        .slice(0, Math.max(0, Math.trunc(limit)))
        .map(([productId]) => productsTable.find((entry) => entry.id === productId))
        .filter((product): product is MemoryProductRow => product !== undefined)
        .filter((product) => product.status === 'PUBLISHED')
        .map(cardOf);
    },

    async listStorefrontCategories() {
      return categories
        .map((category) => ({
          name: category.name,
          slug: category.slug,
          productCount: productsTable.filter(
            (product) => product.categoryId === category.id && product.status === 'PUBLISHED',
          ).length,
        }))
        .sort((left, right) => left.name.localeCompare(right.name, 'fa'));
    },

    async listVariantAvailability(items) {
      return items.map((item) => {
        const variant = variantsTable.find((entry) => entry.variantId === item.variantId);
        const product = variant
          ? productsTable.find((entry) => entry.id === variant.productId)
          : undefined;
        if (!variant || !product || !variant.isActive || product.status !== 'PUBLISHED') {
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
        const level = stockLevelFor(variant.stockQuantity);
        return {
          variantId: variant.variantId,
          productTitle: variant.productTitle,
          size: variant.size,
          colorName: variant.colorName,
          level,
          available: level !== 'OUT' && variant.stockQuantity >= item.quantity,
          effectivePrice: variant.priceOverride ?? product.discountPrice ?? product.basePrice,
        };
      });
    },

    /* ------------------------------------------------ §3.4 ordering */

    async placeOrder(input) {
      if (input.items.length === 0) {
        return { ok: false, code: 'EMPTY_CART', message: 'سبد خرید خالی است.' };
      }
      const shipping = shippingAmountFor(input.shippingMethodId);
      if (shipping === null) {
        return {
          ok: false,
          code: 'SHIPPING_UNKNOWN',
          message: 'روش ارسال انتخابی معتبر نیست.',
          field: 'shippingMethodId',
        };
      }

      const priced: Array<{ item: (typeof input.items)[number]; unitPrice: number }> = [];
      let subtotal = 0;

      for (const item of input.items) {
        const variant = variantsTable.find((entry) => entry.variantId === item.variantId);
        const product = variant
          ? productsTable.find((entry) => entry.id === variant.productId)
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
        const unitPrice = variant.priceOverride ?? product.discountPrice ?? product.basePrice;
        priced.push({ item, unitPrice });
        subtotal += unitPrice * item.quantity;
      }

      let discount = 0;
      let coupon: CouponRow | null = null;
      if (input.couponCode) {
        const found = couponsTable.find((entry) => entry.code === input.couponCode) ?? null;
        if (!found) {
          return {
            ok: false,
            code: 'COUPON_INVALID',
            message: 'کد تخفیف معتبر نیست.',
            field: 'couponCode',
          };
        }
        const ruleInput: CouponRuleInput = {
          id: found.id,
          code: found.code,
          discountType: found.discountType,
          discountValue: found.discountValue,
          minSpend: found.minSpend,
          expiresAt: found.expiresAt,
          usageLimit: found.usageLimit,
          usedCount: found.usedCount,
          isActive: found.isActive,
        };
        const decision = evaluateCoupon(ruleInput, subtotal);
        if (!decision.ok) {
          return { ok: false, code: 'COUPON_INVALID', message: decision.message, field: 'couponCode' };
        }
        discount = decision.discount;
        coupon = found;
      }

      // Consume the stock as the FIRST write of the order, mirroring the SQL
      // path: every refusal above happened before any state changed, so a
      // refused checkout leaves the double exactly as it was.
      for (const item of input.items) {
        const variant = variantsTable.find((entry) => entry.variantId === item.variantId);
        if (!variant) {
          continue;
        }
        variant.stockQuantity -= item.quantity;
      }

      const phoneNumber = normalizePhoneNumber(input.customer.phoneNumber);
      const existing = customersTable.find((entry) => entry.phoneNumber === phoneNumber);
      if (!existing) {
        customersTable.push({
          id: nextId('cust'),
          phoneNumber,
          fullName: input.customer.fullName.trim(),
          address: input.customer.address.trim(),
          postalCode: normalizePostalCode(input.customer.postalCode),
        });
      }
      const customer = customersTable.find((entry) => entry.phoneNumber === phoneNumber);
      if (!customer) {
        throw new Error('customer resolution returned no row');
      }

      const totals: CheckoutTotals = computeCheckoutTotals({
        subtotal,
        discount,
        shipping,
      });
      const orderId = nextId('order');

      ordersTable.unshift({
        id: orderId,
        customerName: customer.fullName,
        customerPhone: customer.phoneNumber,
        postalCode: customer.postalCode,
        status: 'PENDING',
        totalAmount: totals.total,
        discountAmount: totals.discount,
        shippingAmount: totals.shipping,
        trackingCode: null,
        shippingAddress: input.shippingAddress.trim(),
        paymentRefId: input.paymentRefId,
        createdAt: new Date('2026-03-01T00:00:00.000Z'),
        itemCount: input.items.reduce((total, item) => total + item.quantity, 0),
        items: priced.map(({ item, unitPrice }) => {
          const variant = variantsTable.find((entry) => entry.variantId === item.variantId);
          const product = productsTable.find((entry) => entry.id === variant?.productId);
          return {
            id: nextId('item'),
            variantId: item.variantId,
            sku: variant?.sku ?? '',
            productTitle: product?.title ?? '',
            size: variant?.size ?? '',
            colorName: variant?.colorName ?? '',
            quantity: item.quantity,
            unitPrice,
          };
        }),
      });

      if (coupon) {
        coupon.usedCount += 1;
      }

      // The trail's opening row, appended with the order itself: `fromStatus`
      // NULL because nothing preceded it, the source the caller's.
      appendStatusHistory({
        orderId,
        fromStatus: null,
        toStatus: 'PENDING',
        source: input.source,
        metadata: input.statusMetadata ?? null,
      });

      return {
        ok: true,
        orderId,
        customerId: customer.id,
        totals,
        couponApplied: coupon !== null,
        status: 'PENDING',
      };
    },

    async setOrderPaymentRef(orderId, paymentRefId) {
      const order = ordersTable.find((entry) => entry.id === orderId);
      if (!order) {
        return false;
      }
      order.paymentRefId = paymentRefId;
      return true;
    },

    async recordPaymentAuthorization(input) {
      const order = ordersTable.find((entry) => entry.id === input.orderId);
      if (!order || order.status !== 'PENDING') {
        return false;
      }
      // Mirrors `orders_payment_authority_unique`: one authority, one order.
      for (const [orderId, record] of paymentAuthorizationsTable) {
        if (
          orderId !== input.orderId &&
          record.provider === input.provider &&
          record.authority === input.authority
        ) {
          throw new Error('payment authority already recorded for another order');
        }
      }
      paymentAuthorizationsTable.set(input.orderId, {
        orderId: input.orderId,
        provider: input.provider,
        authority: input.authority,
        amount: input.amount,
      });
      return true;
    },

    async findPaymentAuthorization(provider, authority) {
      for (const record of paymentAuthorizationsTable.values()) {
        if (record.provider === provider && record.authority === authority) {
          return { ...record };
        }
      }
      return null;
    },
  };
}
