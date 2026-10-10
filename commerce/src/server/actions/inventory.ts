'use server';

import { revalidatePath } from 'next/cache';

import { withRepository, type CommerceActionResult } from '../db-context';
import { updatePrice, updateStock } from '../services/inventory';

/**
 * D-172 §2.2 — inline edits from the inventory grid.
 *
 * Each action answers for exactly one cell, so a grid full of independent edits
 * cannot report a single blanket success. `unknown` is accepted on purpose: the
 * value arrives from a form and is validated by the service, never trusted.
 */

export interface UpdateStockActionInput {
  variantId: string;
  stockQuantity: unknown;
}

export async function updateStockAction(
  input: UpdateStockActionInput,
): Promise<CommerceActionResult<{ variantId: string }>> {
  const result = await withRepository(async (repository) => {
    const updated = await updateStock(repository, input.variantId, input.stockQuantity);
    return updated.ok
      ? { ok: true as const, data: { variantId: updated.variantId } }
      : {
          ok: false as const,
          code: updated.code,
          message: updated.message,
          field: updated.issues?.[0]?.field,
        };
  });
  if (result.ok) {
    revalidatePath('/admin/inventory');
  }
  return result;
}

export interface UpdatePriceActionInput {
  variantId: string;
  priceOverride: unknown;
}

export async function updatePriceAction(
  input: UpdatePriceActionInput,
): Promise<CommerceActionResult<{ variantId: string }>> {
  const result = await withRepository(async (repository) => {
    const updated = await updatePrice(repository, input.variantId, input.priceOverride);
    return updated.ok
      ? { ok: true as const, data: { variantId: updated.variantId } }
      : {
          ok: false as const,
          code: updated.code,
          message: updated.message,
          field: updated.issues?.[0]?.field,
        };
  });
  if (result.ok) {
    revalidatePath('/admin/inventory');
  }
  return result;
}
