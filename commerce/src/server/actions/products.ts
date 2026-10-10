'use server';

import { revalidatePath } from 'next/cache';

import type { ProductCreatePayload } from '@/contracts/catalog';

import {
  withRepository,
  type CommerceActionResult,
  type CommerceActionFailure,
} from '../db-context';
import { MEDIA_NOT_CONFIGURED_MESSAGE, mediaUploadAllowed } from '../media';
import { createProduct } from '../services/products';

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

  const result = await withRepository(async (repository) => {
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
