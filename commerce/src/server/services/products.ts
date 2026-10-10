import type { ProductCreatePayload } from '@/contracts/catalog';
import { toDescriptionHtml } from '@/lib/variant-matrix';
import { issuesToMessage, normalizeSku, validateProduct } from '@/lib/validation';

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

export async function createProduct(
  repo: CommerceRepository,
  payload: ProductCreatePayload,
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
    images: (payload.images ?? []).map((image, index) => ({
      variantIndex: null,
      storagePath: image.storagePath,
      publicUrl: image.publicUrl,
      displayOrder: image.displayOrder ?? index,
      isPrimary: image.isPrimary ?? index === 0,
    })),
  };

  const created = await repo.createProductGraph(graph);
  return { ok: true, ...created };
}

export async function listProducts(repo: CommerceRepository): Promise<ProductListItem[]> {
  return repo.listProducts();
}
