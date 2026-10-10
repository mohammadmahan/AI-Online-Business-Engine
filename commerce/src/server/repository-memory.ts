import type { CouponRow } from '@/contracts/promotions';
import type { OrderStatus, ProductStatus } from '@/db/schema';

import type {
  CommerceRepository,
  InventoryRow,
  NewCouponInput,
  NewProductGraph,
  OrderDetail,
  OrderListItem,
  ProductListItem,
} from './repository';

/**
 * D-172 Phase 2 — deterministic in-memory repository.
 *
 * This is the TEST DOUBLE that lets the service layer be unit tested without a
 * database (`npm test`). It is deliberately NOT wired into any route: the admin
 * surface never renders invented data, and when `DATABASE_URL` is absent the
 * panel says so instead (see `db-context.ts`).
 *
 * What it models: identity generation, the joins the admin reads, mutation
 * semantics and the counters. What it does NOT model: the database's CHECK and
 * UNIQUE constraints (those are verified against real PostgreSQL 16 in the
 * migration validation, `drizzle/` + D-172 §6) — so a service test here proves
 * the SERVICE rule, and the schema test proves the STORAGE rule.
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
}

let sequence = 0;
function nextId(prefix: string): string {
  sequence += 1;
  return `${prefix}-${String(sequence).padStart(4, '0')}`;
}

export function createMemoryRepository(seed: MemoryRepositorySeed = {}): CommerceRepository {
  const categories = seed.categories ?? [
    { id: 'cat-1', name: 'مانتو', slug: 'manto' },
    { id: 'cat-2', name: 'شومیز', slug: 'shomiz' },
  ];

  const productsTable: Array<{
    id: string;
    title: string;
    slug: string;
    status: ProductStatus;
    basePrice: number;
    discountPrice: number | null;
    categoryId: string;
  }> = [];
  const variantsTable: InventoryRow[] = [];
  const imagesTable: Array<{ productId: string; isPrimary: boolean }> = [];

  (seed.productGraphs ?? []).forEach((graph) => {
    const productId = nextId('prod');
    productsTable.push({
      id: productId,
      title: graph.product.title,
      slug: graph.product.slug,
      status: graph.product.status,
      basePrice: graph.product.basePrice,
      discountPrice: graph.product.discountPrice,
      categoryId: graph.product.categoryId,
    });
    graph.variants.forEach((variant) => {
      variantsTable.push({
        variantId: nextId('var'),
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
    graph.images.forEach((image) => {
      imagesTable.push({ productId, isPrimary: image.isPrimary });
    });
  });

  const ordersTable: OrderDetail[] = (seed.orders ?? []).map((order) => ({
    ...order,
    itemCount: order.items.reduce((total, item) => total + item.quantity, 0),
    items: order.items.map((item) => ({ ...item, id: nextId('item') })),
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

  return {
    async listCategories() {
      return categories;
    },

    async createProductGraph(graph) {
      const productId = nextId('prod');
      productsTable.push({
        id: productId,
        title: graph.product.title,
        slug: graph.product.slug,
        status: graph.product.status,
        basePrice: graph.product.basePrice,
        discountPrice: graph.product.discountPrice,
        categoryId: graph.product.categoryId,
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
      graph.images.forEach((image) => {
        imagesTable.push({ productId, isPrimary: image.isPrimary });
      });
      return { productId, variantIds };
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

    async updateOrderStatus(orderId, status) {
      const order = ordersTable.find((entry) => entry.id === orderId);
      if (!order) {
        return false;
      }
      order.status = status;
      return true;
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
  };
}
