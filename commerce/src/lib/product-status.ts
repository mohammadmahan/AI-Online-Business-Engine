/**
 * D-172 §1.2 — the product lifecycle as the merchant panel presents it.
 *
 * The database enum is the authority (`src/db/schema/enums.ts`); this module is
 * the browser-safe mirror the pure validator and the RTL badges can import
 * without pulling Drizzle into a client bundle. `product-status.test.ts` asserts
 * the two lists are identical, so a schema migration that adds a status cannot
 * leave the form silently unable to select it.
 */

export const PRODUCT_STATUSES = ['DRAFT', 'PUBLISHED', 'ARCHIVED'] as const;

export type MerchantProductStatus = (typeof PRODUCT_STATUSES)[number];

export const PRODUCT_STATUS_LABELS: Record<MerchantProductStatus, string> = {
  DRAFT: 'پیش‌نویس',
  PUBLISHED: 'منتشرشده',
  ARCHIVED: 'بایگانی‌شده',
};

export function isProductStatus(value: unknown): value is MerchantProductStatus {
  return typeof value === 'string' && (PRODUCT_STATUSES as readonly string[]).includes(value);
}
