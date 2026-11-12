import type {
  ProductCreatePayload,
  ProductImagePayload,
  ProductUpdatePayload,
} from '@/contracts/catalog';
import { toDescriptionHtml } from '@/lib/variant-matrix';
import {
  isUuid,
  issuesToMessage,
  normalizeSku,
  validateProduct,
  validateProductUpdate,
} from '@/lib/validation';

import { MEDIA_NOT_CONFIGURED_MESSAGE, mediaPublicPrefix, type MediaEnvironment } from '../media';
import { validateStoredImageReference } from '../media/reference';
import type { CommerceRepository, NewProductGraph, ProductListItem } from '../repository';

/**
 * D-172 §2.1 — product ingestion (server half).
 *
 * The generator itself lives in `@/lib/variant-matrix` because the browser runs
 * it; this module owns the WRITE, and it validates everything first and then
 * persists the whole graph in ONE transaction, so a refused payload can never
 * leave a partial product behind.
 */

export { buildVariantMatrix, MATRIX_MAX_ROWS, toDescriptionHtml } from '@/lib/variant-matrix';

export type CreateProductResult =
  | { ok: true; productId: string; variantIds: string[] }
  | {
      ok: false;
      code: 'VALIDATION_ERROR';
      message: string;
      issues: Array<{ field: string; message: string }>;
    };

/**
 * New products may only carry images this store wrote.
 *
 * The gallery editor already enforces this; creation used to accept any
 * non-empty path/url pair, which let a crafted action hotlink a third-party
 * image (or a tracking pixel) into `product_images`. Reusing the same reference
 * gate keeps both write paths from drifting apart. Media is optional, but a
 * submitted reference is never trusted on its shape alone.
 */
export function productImageIssues(
  images: readonly ProductImagePayload[],
  env: MediaEnvironment = process.env,
): Array<{ field: string; message: string }> {
  if (images.length === 0) {
    return [];
  }
  if (mediaPublicPrefix(env) === null) {
    return [{ field: 'images', message: MEDIA_NOT_CONFIGURED_MESSAGE }];
  }

  const issues: Array<{ field: string; message: string }> = [];
  images.forEach((image, index) => {
    if (!image.storagePath.trim() || !image.publicUrl.trim()) {
      return; // the general validator already reports the missing half
    }
    const verdict = validateStoredImageReference(image.storagePath, image.publicUrl, env);
    if (!verdict.ok) {
      issues.push({ field: `images.${index}.publicUrl`, message: verdict.message });
    }
  });
  return issues;
}

/**
 * The two catalog uniqueness rules the DATABASE still owns, mapped to the field
 * the merchant can act on.
 *
 * `validateProduct` already refuses a duplicate SKU WITHIN one submission, but a
 * slug or SKU that another product already holds can only be caught by the unique
 * index. Letting that error surface as "unexpected database error" tells the
 * merchant nothing and reads like an outage, so the two constraints this write
 * can violate are translated here. Anything else is rethrown unchanged and keeps
 * the generic refusal from `withRepository`.
 */
const UNIQUE_VIOLATION = '23505';

const DUPLICATE_SLUG_ISSUE = {
  field: 'slug',
  message: 'این نشانی محصول قبلاً استفاده شده است؛ نشانی دیگری انتخاب کنید.',
};

const DUPLICATE_SKU_ISSUE = {
  field: 'variants',
  message: 'کد کالای یکی از سطرها قبلاً در کاتالوگ ثبت شده است؛ کد دیگری انتخاب کنید.',
};

const DUPLICATE_FIELDS: Record<string, { field: string; message: string }> = {
  products_slug_unique: DUPLICATE_SLUG_ISSUE,
  product_variants_sku_unique: DUPLICATE_SKU_ISSUE,
};

function duplicateIssue(
  error: unknown,
): { field: string; message: string } | null {
  // Drizzle wraps the driver's error (`DrizzleQueryError`), so the SQLSTATE and
  // constraint live on the CAUSE chain rather than on the thrown object. Walk it
  // a few levels; a cycle or a non-Error cause simply ends the search.
  let current: unknown = error;
  const seen = new Set<unknown>();
  for (let depth = 0; depth < 4 && typeof current === 'object' && current !== null; depth += 1) {
    if (seen.has(current)) {
      return null;
    }
    seen.add(current);
    const { code, constraint, cause } = current as {
      code?: unknown;
      constraint?: unknown;
      cause?: unknown;
    };
    if (code === UNIQUE_VIOLATION && typeof constraint === 'string') {
      return DUPLICATE_FIELDS[constraint] ?? null;
    }
    current = cause;
  }
  return null;
}

export async function createProduct(
  repo: CommerceRepository,
  payload: ProductCreatePayload,
  env: MediaEnvironment = process.env,
): Promise<CreateProductResult> {
  const validation = validateProduct(payload);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }

  const imageIssues = productImageIssues(payload.images ?? [], env);
  if (imageIssues.length > 0) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(imageIssues),
      issues: imageIssues,
    };
  }

  // Exactly one primary per gallery, decided HERE rather than by a per-row
  // `?? index === 0` default: that default turned an OMITTED flag on slot 0 into
  // `true` alongside a later explicit `true` (two primaries), and left a gallery
  // whose flags were all explicitly `false` with none. Validation has already
  // refused more than one explicit primary, so one winner is unambiguous.
  const images = payload.images ?? [];
  const requestedPrimary = images.findIndex((image) => image.isPrimary === true);
  const primaryIndex = requestedPrimary >= 0 ? requestedPrimary : 0;

  const graph: NewProductGraph = {
    product: {
      categoryId: payload.categoryId,
      title: payload.title.trim(),
      slug: payload.slug.trim(),
      basePrice: payload.basePrice,
      discountPrice: payload.discountPrice ?? null,
      descriptionRaw: payload.descriptionRaw.trim(),
      descriptionHtml: payload.descriptionHtml?.trim()
        ? payload.descriptionHtml
        : toDescriptionHtml(payload.descriptionRaw),
      fabricType: payload.fabricType.trim(),
      season: payload.season.trim(),
      careInstructions: payload.careInstructions?.trim() || null,
      status: payload.status ?? 'DRAFT',
    },
    variants: payload.variants.map((variant) => ({
      sku: normalizeSku(variant.sku),
      colorName: variant.colorName.trim(),
      colorHex: variant.colorHex.trim().toUpperCase(),
      size: variant.size.trim(),
      stockQuantity: variant.stockQuantity ?? 0,
      priceOverride: variant.priceOverride ?? null,
    })),
    // Variant binding is intentionally not accepted from the form in this phase
    // (G-5 media storage is still open): images attach to the product and carry
    // their order + primary flag here.
    images: images.map((image, index) => ({
      variantIndex: null,
      storagePath: image.storagePath,
      publicUrl: image.publicUrl,
      displayOrder: image.displayOrder ?? index,
      isPrimary: index === primaryIndex,
    })),
  };

  let created: { productId: string; variantIds: string[] };
  try {
    created = await repo.createProductGraph(graph);
  } catch (error) {
    const duplicate = duplicateIssue(error);
    if (duplicate === null) {
      throw error;
    }
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: duplicate.message,
      issues: [duplicate],
    };
  }
  return { ok: true, ...created };
}

export type UpdateProductResult =
  | { ok: true; productId: string }
  | {
      ok: false;
      code: 'VALIDATION_ERROR';
      message: string;
      issues: Array<{ field: string; message: string }>;
    }
  | { ok: false; code: 'NOT_FOUND'; message: string };

/**
 * D-172 §2.1 — edit the product-level fields of an EXISTING product.
 *
 * Deliberately narrow: it writes ONE `products` row. Variants, SKUs, stock,
 * media associations and order snapshots are not read for writing, recreated or
 * deleted, so an edit cannot disturb the inventory or gallery workflows.
 *
 * `descriptionHtml` is preserved when the raw text was not changed; when the
 * merchant edits the raw description, the stored body is re-derived through the
 * SAME escaping used at creation (the admin panel never submits HTML).
 */
export async function updateProduct(
  repo: CommerceRepository,
  productId: string,
  payload: ProductUpdatePayload,
): Promise<UpdateProductResult> {
  // A malformed id is "no such product", not a database cast error.
  if (!isUuid(productId)) {
    return { ok: false, code: 'NOT_FOUND', message: 'محصول مورد نظر پیدا نشد.' };
  }

  const validation = validateProductUpdate(payload);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }

  const existing = await repo.getProductForEdit(productId);
  if (existing === null) {
    return { ok: false, code: 'NOT_FOUND', message: 'محصول مورد نظر پیدا نشد.' };
  }

  // The category list is tiny and already feeds the form; checking membership
  // here turns a forged/stale id into a field message. The write still maps the
  // FK refusal, because another request may delete the category in between.
  const categories = await repo.listCategories();
  if (!categories.some((category) => category.id === payload.categoryId)) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: 'دستهٔ انتخاب‌شده وجود ندارد؛ یک دستهٔ معتبر انتخاب کنید.',
      issues: [{ field: 'categoryId', message: 'دستهٔ انتخاب‌شده وجود ندارد.' }],
    };
  }

  const descriptionRaw = payload.descriptionRaw.trim();
  const descriptionHtml =
    descriptionRaw === existing.descriptionRaw.trim()
      ? existing.descriptionHtml
      : toDescriptionHtml(descriptionRaw);

  const updated = await repo.updateProductDetails(productId, {
    categoryId: payload.categoryId,
    title: payload.title.trim(),
    slug: payload.slug.trim(),
    basePrice: payload.basePrice,
    discountPrice: payload.discountPrice ?? null,
    descriptionRaw,
    descriptionHtml,
    fabricType: payload.fabricType.trim(),
    season: payload.season.trim(),
    careInstructions:
      typeof payload.careInstructions === 'string' ? payload.careInstructions.trim() || null : null,
    status: payload.status,
  });

  if (updated.ok) {
    return { ok: true, productId };
  }
  if (updated.reason === 'NOT_FOUND') {
    return { ok: false, code: 'NOT_FOUND', message: 'محصول مورد نظر پیدا نشد.' };
  }
  if (updated.reason === 'DUPLICATE_SLUG') {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: DUPLICATE_SLUG_ISSUE.message,
      issues: [DUPLICATE_SLUG_ISSUE],
    };
  }
  return {
    ok: false,
    code: 'VALIDATION_ERROR',
    message: 'دستهٔ انتخاب‌شده وجود ندارد؛ یک دستهٔ معتبر انتخاب کنید.',
    issues: [{ field: 'categoryId', message: 'دستهٔ انتخاب‌شده وجود ندارد.' }],
  };
}

export async function listProducts(repo: CommerceRepository): Promise<ProductListItem[]> {
  return repo.listProducts();
}
