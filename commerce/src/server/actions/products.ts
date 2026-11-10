'use server';

import { revalidatePath } from 'next/cache';

import type {
  ProductCreatePayload,
  ProductImageSelectionEntry,
  ProductUpdatePayload,
} from '@/contracts/catalog';

import { withAdminRepository } from '../auth/with-admin';
import type { CommerceActionFailure, CommerceActionResult } from '../db-context';
import { MEDIA_NOT_CONFIGURED_MESSAGE, mediaUploadAllowed } from '../media';
import { updateProductImages } from '../services/product-images';
import { createProduct, updateProduct } from '../services/products';

/**
 * D-172 §2.1 — the only way a product enters the SSOT.
 *
 * Every action in this package returns a serializable result instead of
 * throwing, so the client can render the refusal verbatim: the panel never
 * shows an optimistic success for a write the server rejected.
 */

export interface CreateProductActionInput {
  product: ProductCreatePayload;
  /** Images chosen in the picker but not yet stored (see ../media.ts, G-5). */
  pendingUploads: number;
}

/**
 * §2.1 — persists a product with its variant matrix.
 *
 * Fail-closed order: the media gate is checked BEFORE any write, so a refused
 * submission leaves the catalog exactly as it was.
 */
export async function createProductAction(
  input: CreateProductActionInput,
): Promise<CommerceActionResult<{ productId: string; variantIds: string[] }>> {
  if (input.pendingUploads > 0 && !mediaUploadAllowed()) {
    const failure: CommerceActionFailure = {
      ok: false,
      code: 'MEDIA_NOT_CONFIGURED',
      message: MEDIA_NOT_CONFIGURED_MESSAGE,
      field: 'images',
    };
    return failure;
  }

  const result = await withAdminRepository(async (repository) => {
    const created = await createProduct(repository, input.product);
    if (!created.ok) {
      return {
        ok: false as const,
        code: 'VALIDATION_ERROR' as const,
        message: created.message,
        field: created.issues[0]?.field,
      };
    }
    return {
      ok: true as const,
      data: { productId: created.productId, variantIds: created.variantIds },
    };
  });

  if (result.ok) {
    revalidatePath('/admin/inventory');
    revalidatePath('/admin/products/new');
  }
  return result;
}

export interface UpdateProductActionInput {
  productId: string;
  product: ProductUpdatePayload;
}

/**
 * §2.1 — saves the product-level edit form.
 *
 * The session guard is the same one every admin action uses; the service then
 * validates, verifies the product and category exist, and writes ONE product
 * row. A refusal carries the field-level issues so the form can keep the
 * submitted values and mark the inputs it is complaining about.
 */
export async function updateProductAction(
  input: UpdateProductActionInput,
): Promise<CommerceActionResult<{ productId: string }>> {
  const result = await withAdminRepository(async (repository) => {
    // Inside the guard: an anonymous caller must learn nothing about the body.
    if (
      typeof input !== 'object' ||
      input === null ||
      typeof input.product !== 'object' ||
      input.product === null
    ) {
      return {
        ok: false as const,
        code: 'VALIDATION_ERROR' as const,
        message: 'دادهٔ فرم معتبر نیست.',
      };
    }

    const updated = await updateProduct(repository, input.productId, input.product);
    if (!updated.ok) {
      const issues = updated.code === 'VALIDATION_ERROR' ? updated.issues : undefined;
      return {
        ok: false as const,
        code: updated.code,
        message: updated.message,
        field: issues?.[0]?.field,
        issues,
      };
    }
    return { ok: true as const, data: { productId: updated.productId } };
  });

  if (result.ok) {
    revalidatePath('/admin');
    revalidatePath(`/admin/products/${input.productId}/edit`);
    revalidatePath(`/admin/products/${input.productId}/images`);
    revalidatePath('/admin/inventory');
    revalidatePath('/catalog');
    revalidatePath('/products/[slug]', 'page');
  }
  return result;
}

export interface UpdateProductImagesActionInput {
  productId: string;
  /** Ordered slots: existing rows by id, newly stored images by path + url. */
  images: ProductImageSelectionEntry[];
}

/**
 * §2.1 — saves an existing product's gallery (add / reorder / primary / remove).
 *
 * The session guard is HERE, not only in `proxy.ts`: an action id is a global
 * URL, and the proxy's path rule says which PAGE a POST came from, not which
 * repository operation it may perform (`withAdminRepository`). The service then
 * validates every submitted reference before the first write, so a refused edit
 * leaves the gallery exactly as it was.
 *
 * The storefront is revalidated too, because a product's photo and its order are
 * customer-visible; nothing else about the product changes.
 */
export async function updateProductImagesAction(
  input: UpdateProductImagesActionInput,
): Promise<CommerceActionResult<{ productId: string; imageIds: string[] }>> {
  if (!Array.isArray(input.images)) {
    const failure: CommerceActionFailure = {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: 'فهرست تصویرها معتبر نیست.',
      field: 'images',
    };
    return failure;
  }

  const result = await withAdminRepository(async (repository) => {
    const updated = await updateProductImages(repository, input.productId, input.images);
    if (!updated.ok) {
      return {
        ok: false as const,
        code: updated.code,
        message: updated.message,
        field: updated.field,
      };
    }
    return {
      ok: true as const,
      data: { productId: updated.productId, imageIds: updated.imageIds },
    };
  });

  if (result.ok) {
    revalidatePath('/admin');
    revalidatePath(`/admin/products/${input.productId}/images`);
    revalidatePath('/catalog');
    revalidatePath('/products/[slug]', 'page');
  }
  return result;
}
