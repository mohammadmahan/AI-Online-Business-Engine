import type { ProductImageSelectionEntry } from '@/contracts/catalog';
import { normalizeImageSelection } from '@/lib/product-images';
import { isUuid } from '@/lib/validation';

import { MEDIA_NOT_CONFIGURED_MESSAGE, mediaPublicPrefix, type MediaEnvironment } from '../media';
import { validateStoredImageReference } from '../media/reference';
import type { CommerceRepository } from '../repository';

/**
 * D-172 §2.1 — editing an EXISTING product's gallery (server half).
 *
 * The roadmap's multi-image uploader was written into the ingestion form, so once
 * a product existed its photos were frozen: no way to add a colourway, replace a
 * bad shot, reorder the gallery or drop one. This service is the merchant path
 * for that, and it is deliberately narrow — it changes `product_images`
 * associations only. Title, prices, variants, stock and orders are not part of
 * this write, so a gallery edit cannot disturb the catalog around it.
 *
 * Order of refusal, all before any write:
 *   1. a malformed product id is invalid INPUT (never a driver error);
 *   2. the slot list must normalise (`@/lib/product-images`): one form per slot,
 *      no duplicates, at most one primary;
 *   3. NEW references must come from the configured media provider
 *      (`@/server/media/reference`). If the merchant adds nothing, an
 *      unconfigured provider does not block a reorder or a removal — those touch
 *      no bytes at all;
 *   4. ownership is decided by the repository inside the transaction, so an id
 *      belonging to another product is refused there rather than trusted here.
 */
export type ProductImagesUpdateResult =
  | { ok: true; productId: string; imageIds: string[] }
  | {
      ok: false;
      code: 'VALIDATION_ERROR' | 'NOT_FOUND' | 'MEDIA_NOT_CONFIGURED';
      message: string;
      field?: string;
    };

export async function updateProductImages(
  repo: CommerceRepository,
  productId: string,
  entries: readonly ProductImageSelectionEntry[],
  env: MediaEnvironment = process.env,
): Promise<ProductImagesUpdateResult> {
  if (!isUuid(productId)) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: 'شناسهٔ محصول معتبر نیست.',
      field: 'productId',
    };
  }

  const normalized = normalizeImageSelection(entries);
  if (!normalized.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: normalized.message,
      field: normalized.field,
    };
  }
  const { keep, add } = normalized.selection;

  if (add.length > 0) {
    if (mediaPublicPrefix(env) === null) {
      return {
        ok: false,
        code: 'MEDIA_NOT_CONFIGURED',
        message: MEDIA_NOT_CONFIGURED_MESSAGE,
        field: 'images',
      };
    }
    for (const entry of add) {
      const verdict = validateStoredImageReference(entry.storagePath, entry.publicUrl, env);
      if (!verdict.ok) {
        return {
          ok: false,
          code: 'VALIDATION_ERROR',
          message: verdict.message,
          field: `images.${entry.displayOrder}.publicUrl`,
        };
      }
    }
  }

  const written = await repo.replaceProductImages(productId, { keep, add });
  if (!written.ok) {
    if (written.reason === 'PRODUCT_NOT_FOUND') {
      return { ok: false, code: 'NOT_FOUND', message: 'این محصول پیدا نشد.', field: 'productId' };
    }
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: 'یکی از تصویرها به این محصول تعلق ندارد؛ گالری تغییر نکرد.',
      field: 'images',
    };
  }

  return { ok: true, productId, imageIds: written.imageIds };
}
