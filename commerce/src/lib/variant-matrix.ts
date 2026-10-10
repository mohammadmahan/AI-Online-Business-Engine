import type { VariantMatrixPayload, VariantPayload } from '@/contracts/catalog';

import { isNonEmptyString } from './validation';

/**
 * D-172 §2.1 — the variant matrix generator, as a PURE module.
 *
 * It lives in `src/lib` (not `src/server`) because the browser renders it: the
 * merchant builds the matrix client-side, and the server re-validates the very
 * same rules on submit. One definition, two callers — the generator and the
 * refusal can never drift apart.
 */

export interface VariantMatrixRequest extends VariantMatrixPayload {
  /** SKU namespace, e.g. the product slug upper-cased (`MANTO-KETI`). */
  skuPrefix: string;
  defaultStock?: number;
  defaultPriceOverride?: number | null;
}

export const MATRIX_MAX_ROWS = 240;

function sizeToken(size: string, index: number): string {
  const cleaned = size
    .trim()
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase();
  return cleaned.length > 0 ? cleaned : `S${index + 1}`;
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

export function validateMatrixRequest(request: VariantMatrixRequest): Array<{
  field: string;
  message: string;
}> {
  const issues: Array<{ field: string; message: string }> = [];
  if (!isNonEmptyString(request.skuPrefix)) {
    issues.push({ field: 'skuPrefix', message: 'پیشوند کد کالا الزامی است.' });
  }
  if (!Array.isArray(request.colors) || request.colors.length === 0) {
    issues.push({ field: 'colors', message: 'حداقل یک رنگ انتخاب کنید.' });
  }
  if (!Array.isArray(request.sizes) || request.sizes.length === 0) {
    issues.push({ field: 'sizes', message: 'حداقل یک سایز انتخاب کنید.' });
  }
  if (request.colors.length * request.sizes.length > MATRIX_MAX_ROWS) {
    issues.push({
      field: 'matrix',
      message: `تعداد سطرهای ماتریس بیش از حد مجاز (${MATRIX_MAX_ROWS}) است.`,
    });
  }
  return issues;
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
