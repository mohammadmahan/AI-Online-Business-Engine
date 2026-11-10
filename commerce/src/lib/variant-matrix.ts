import type { VariantPayload } from '@/contracts/catalog';

import type { ValidationIssue } from './validation';
import { MATRIX_MAX_ROWS, variantMatrixRequestSchema } from './variant-matrix-schema';
import type { VariantMatrixRequest } from './variant-matrix-schema';

export { MATRIX_MAX_ROWS };
export type { VariantMatrixRequest };

/**
 * D-172 §2.1 — the variant matrix generator, as a PURE module.
 *
 * It lives in `src/lib` (not `src/server`) because the browser renders it: the
 * merchant builds the matrix client-side, and the server re-validates the very
 * same rules on submit. One definition, two callers — the generator and the
 * refusal can never drift apart.
 */


function sizeToken(size: string, index: number): string {
  const cleaned = size
    .trim()
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase();
  return cleaned.length > 0 ? cleaned : `S${index + 1}`;
}

/**
 * Whether the generated rows still correspond to the palette/size selection.
 *
 * A FRESH builder has no selection and no rows, which is current — not stale.
 * A selection that has not been generated (or was generated and then edited) is
 * genuinely out of date and the merchant must regenerate.
 */
export function matrixOutOfDate(
  colorCount: number,
  sizeCount: number,
  rowCount: number,
): boolean {
  const expectedRows = colorCount * sizeCount;
  return expectedRows > 0 && expectedRows !== rowCount;
}

/**
 * Colours × sizes → one row per combination.
 *
 * The SKU is a PROPOSAL (`<PREFIX>-<SIZE>-<COLOUR#>`): the matrix table renders
 * it in an editable cell, and uniqueness is enforced again on submit by
 * `validateProduct` and by the database indexes, so a merchant edit can never
 * create a silent duplicate.
 */
export function buildVariantMatrix(request: VariantMatrixRequest): VariantPayload[] {
  const rows: VariantPayload[] = [];
  const prefix = (request.skuPrefix || 'SKU').trim().toUpperCase().replace(/[^A-Z0-9]+/g, '-');
  const stock = request.defaultStock ?? 0;
  const priceOverride = request.defaultPriceOverride ?? null;

  request.colors.forEach((color, colorIndex) => {
    request.sizes.forEach((size, sizeIndex) => {
      rows.push({
        sku: `${prefix}-${sizeToken(size, sizeIndex)}-${colorIndex + 1}`,
        colorName: color.name.trim(),
        colorHex: color.hex.trim(),
        size: size.trim(),
        stockQuantity: stock,
        priceOverride,
      });
    });
  });

  return rows;
}

/**
 * The same rules the browser gate uses, reported in the panel's `{field,message}`
 * shape. Delegating to the Zod schema (instead of re-listing the checks) is what
 * keeps the client hint and the refusal identical: one definition, two callers.
 */
export function validateMatrixRequest(request: VariantMatrixRequest): ValidationIssue[] {
  const parsed = variantMatrixRequestSchema.safeParse(request);
  if (parsed.success) {
    return [];
  }
  return parsed.error.issues.map((issue) => ({
    field: issue.path.length > 0 ? issue.path.map(String).join('.') : 'matrix',
    message: issue.message,
  }));
}

/** Minimal, deterministic rich-text fallback: escape, then paragraph breaks. */
export function toDescriptionHtml(raw: string): string {
  const escaped = raw
    .trim()
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  return escaped
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${paragraph.replace(/\n/g, '<br />')}</p>`)
    .join('');
}
