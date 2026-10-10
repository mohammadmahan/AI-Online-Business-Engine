import type { InferInsertModel, InferSelectModel } from 'drizzle-orm';

import type {
  ProductStatus,
  categories,
  productImages,
  productVariants,
  products,
} from '../db/schema';

/**
 * D-172 Phase 1 — typed contracts for the fashion catalog (§1.1–§1.4).
 *
 * Three layers, deliberately distinct:
 * - `Category` / `Product` / `ProductVariant` / `ProductImage` — the READ model
 *   (a full row as it comes back from PostgreSQL).
 * - `New…` — the raw INSERT model; mirrors a table row at the column level.
 * - `…Payload` — the write contract used by the admin panel and the API edge.
 *   These are the shapes the application layer may accept; they carry no
 *   authority by themselves and every write still passes the canonical
 *   validation and authorization path (D-026/D-027, D-045/D-139).
 *
 * Money is an integer number of Iranian Toman (D-010) — never a float. The
 * canonical write path enforces the 10¹² ceiling (D-114).
 */

/* ------------------------------------------------------------------ read */

export type Category = InferSelectModel<typeof categories>;
export type Product = InferSelectModel<typeof products>;
export type ProductVariant = InferSelectModel<typeof productVariants>;
export type ProductImage = InferSelectModel<typeof productImages>;

/** A product together with its variant matrix and media (Phase 3 PDP read). */
export interface ProductWithVariants extends Product {
  variants: ProductVariant[];
  images: ProductImage[];
}

/* ------------------------------------------------------------ raw inserts */

export type NewCategory = InferInsertModel<typeof categories>;
export type NewProduct = InferInsertModel<typeof products>;
export type NewProductVariant = InferInsertModel<typeof productVariants>;
export type NewProductImage = InferInsertModel<typeof productImages>;

/* ------------------------------------------------------------- §1.1 writes */

export interface CategoryCreatePayload {
  name: string;
  slug: string;
  parentId?: string | null;
  description?: string | null;
}

export type CategoryUpdatePayload = Partial<CategoryCreatePayload>;

/* ------------------------------------------------------------- §1.3 writes */

/** One cell of the size × color matrix (Phase 2.1 matrix generator output). */
export interface VariantPayload {
  sku: string;
  colorName: string;
  colorHex: string;
  size: string;
  stockQuantity?: number;
  priceOverride?: number | null;
  isActive?: boolean;
}

/** Generator input: the colors and sizes the merchant selects (Phase 2.1). */
export interface VariantMatrixPayload {
  colors: { name: string; hex: string }[];
  sizes: string[];
}

/** Inline stock edit (Phase 2.2, no page refresh). */
export interface VariantStockUpdatePayload {
  stockQuantity: number;
}

/** Inline price edit (Phase 2.2); `null` clears the override. */
export interface VariantPriceUpdatePayload {
  priceOverride: number | null;
}

export type VariantUpdatePayload = Partial<Omit<VariantPayload, 'sku'>>;

/* ------------------------------------------------------------- §1.4 writes */

/** One media row (§1.4); `variantId` binds the image to a color, if any. */
export interface ProductImagePayload {
  variantId?: string | null;
  storagePath: string;
  publicUrl: string;
  displayOrder?: number;
  isPrimary?: boolean;
}

/** Gallery reorder / primary-image selection (Phase 2.1 uploader). */
export interface ProductImageOrderPayload {
  images: { id: string; displayOrder: number }[];
  primaryImageId?: string | null;
}

/* ------------------------------------------------------------- §1.2 writes */

/**
 * A product is created as a unit with its matrix and media, which is how the
 * admin panel submits it (§2.1): one product, N variants, N images.
 */
export interface ProductCreatePayload {
  categoryId: string;
  title: string;
  slug: string;
  basePrice: number;
  discountPrice?: number | null;
  descriptionRaw: string;
  descriptionHtml: string;
  fabricType: string;
  season: string;
  careInstructions?: string | null;
  status?: ProductStatus;
  variants: VariantPayload[];
  images?: ProductImagePayload[];
}

export type ProductUpdatePayload = Partial<
  Omit<ProductCreatePayload, 'variants' | 'images'>
>;
