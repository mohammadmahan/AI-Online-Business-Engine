import { and, desc, eq, sql } from 'drizzle-orm';

import type { CommerceDb } from '@/db';
import {
  categories,
  coupons,
  customers,
  orderItems,
  orders,
  productImages,
  productVariants,
  products,
} from '@/db/schema';
import type { DiscountType, OrderStatus, ProductStatus } from '@/db/schema';

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

export interface CommerceRepository {
  listCategories(): Promise<Array<{ id: string; name: string; slug: string }>>;
  createProductGraph(graph: NewProductGraph): Promise<{ productId: string; variantIds: string[] }>;
  listProducts(): Promise<ProductListItem[]>;
  listInventory(): Promise<InventoryRow[]>;
  updateVariantStock(variantId: string, stockQuantity: number): Promise<boolean>;
  updateVariantPrice(variantId: string, priceOverride: number | null): Promise<boolean>;
  listOrders(): Promise<OrderListItem[]>;
  getOrderDetail(orderId: string): Promise<OrderDetail | null>;
  updateOrderStatus(orderId: string, status: OrderStatus): Promise<boolean>;
  updateOrderTracking(orderId: string, trackingCode: string): Promise<boolean>;
  listCoupons(): Promise<Array<typeof coupons.$inferSelect>>;
  findCouponByCode(code: string): Promise<typeof coupons.$inferSelect | null>;
  createCoupon(input: NewCouponInput): Promise<typeof coupons.$inferSelect>;
  setCouponActive(couponId: string, isActive: boolean): Promise<boolean>;
}

/** Postgres implementation — the only file that speaks SQL/schema. */
export function createPostgresRepository(db: CommerceDb): CommerceRepository {
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
      const rows = await db
        .select({
          id: products.id,
          title: products.title,
          slug: products.slug,
          status: products.status,
          basePrice: products.basePrice,
          discountPrice: products.discountPrice,
          variantCount: sql<number>`(select count(*) from ${productVariants} where ${productVariants.productId} = ${products.id})`,
          imageCount: sql<number>`(select count(*) from ${productImages} where ${productImages.productId} = ${products.id})`,
        })
        .from(products)
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
          itemCount: sql<number>`(select coalesce(sum(${orderItems.quantity}), 0) from ${orderItems} where ${orderItems.orderId} = ${orders.id})`,
        })
        .from(orders)
        .innerJoin(customers, eq(orders.customerId, customers.id))
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

    async updateOrderStatus(orderId, status) {
      const rows = await db
        .update(orders)
        .set({ status, updatedAt: new Date() })
        .where(eq(orders.id, orderId))
        .returning({ id: orders.id });
      return rows.length === 1;
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
  };
}
