import {
  isUuid,
  issuesToMessage,
  validatePriceOverride,
  validateStockValue,
} from '@/lib/validation';
import type { CommerceRepository } from '../repository';

/**
 * D-172 §2.2 — inventory service (server half).
 *
 * The display rules (badge, filters, summary, effective price) live in
 * `@/lib/inventory-rules` because the browser renders them; this module owns
 * only the two WRITES, each validated before it reaches the database.
 */

export type InventoryMutationResult =
  | { ok: true; variantId: string }
  | {
      ok: false;
      code: 'VALIDATION_ERROR' | 'NOT_FOUND';
      message: string;
      issues?: Array<{ field: string; message: string }>;
    };

/**
 * A malformed id is invalid INPUT, not a missing row: refusing it here keeps the
 * driver out of the path, so the merchant sees a field message instead of the
 * repository boundary's coarse `UNEXPECTED` (D-171 §2.2).
 */
function invalidVariantId(): InventoryMutationResult {
  return {
    ok: false,
    code: 'VALIDATION_ERROR',
    message: 'شناسهٔ گونه معتبر نیست.',
    issues: [{ field: 'variantId', message: 'شناسهٔ گونه معتبر نیست.' }],
  };
}

export async function updateStock(
  repo: CommerceRepository,
  variantId: string,
  stockQuantity: unknown,
): Promise<InventoryMutationResult> {
  if (!isUuid(variantId)) {
    return invalidVariantId();
  }
  const validation = validateStockValue(stockQuantity);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }
  const updated = await repo.updateVariantStock(variantId, stockQuantity as number);
  return updated
    ? { ok: true, variantId }
    : { ok: false, code: 'NOT_FOUND', message: 'این گونه در فهرست موجودی پیدا نشد.' };
}

export async function updatePrice(
  repo: CommerceRepository,
  variantId: string,
  priceOverride: unknown,
): Promise<InventoryMutationResult> {
  if (!isUuid(variantId)) {
    return invalidVariantId();
  }
  const validation = validatePriceOverride(priceOverride);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }
  const updated = await repo.updateVariantPrice(
    variantId,
    priceOverride === null ? null : (priceOverride as number),
  );
  return updated
    ? { ok: true, variantId }
    : { ok: false, code: 'NOT_FOUND', message: 'این گونه در فهرست موجودی پیدا نشد.' };
}
